"""Atualização pelo GitHub: avisa que existe versão nova, quem decide é o usuário.

Como funciona:
  1. `publicar.py` compila, empacota o .exe num .zip e cria uma **Release** no GitHub
     com a tag `vX.Y` (é o autor quem publica; o cliente nunca vê isso).
  2. Toda vez que o sistema abre, `verificar_em_segundo_plano` consulta
     `releases/latest` sem incomodar ninguém. Achando versão maior que a instalada,
     mostra um aviso discreto no menu — **não** baixa nada e **não** interrompe.
  3. Só quando o usuário clica é que o download e a troca do .exe acontecem.

Uma versão pode ser dispensada ("não avisar mais desta"): fica em
`[ATUALIZACAO] versao_ignorada` no config.ini e volta a avisar na seguinte.
"""
import urllib.request
import ssl
import json
import os
import sys
import threading
import zipfile
import subprocess
import re
import tempfile
import configparser
import tkinter as tk
from tkinter import messagebox, ttk
from datetime import datetime
import shutil
from version import VERSAO
from utils.logger import get_logger
from utils import tema

_log = get_logger('updater')

# Repositório público onde as Releases são publicadas. Público de propósito: a API
# de release de repositório privado exige token, e o cliente não tem token nenhum.
GITHUB_REPO = "cunharc/importador-sistec"

SECAO_CFG = 'ATUALIZACAO'
NOME_EXE = 'Importador_Sistec.exe'
URL_RELEASES = f"https://github.com/{GITHUB_REPO}/releases/latest"


# --------------------------------------------------------------------- TLS
_ctx_ssl = None


def contexto_ssl():
    """Contexto TLS que valida como o Windows valida.

    `urlopen` sem contexto usa `ssl.create_default_context()`, que tira uma FOTO
    do repositório de raízes do Windows e não busca certificado intermediário
    faltante (o navegador busca, pelo campo AIA). Nas máquinas de cliente isso
    aparece como `CERTIFICATE_VERIFY_FAILED: unable to get local issuer
    certificate` — a atualização morria ali, mesmo com o GitHub abrindo no
    navegador da mesma máquina. Antivírus e proxy que inspecionam TLS caem no
    mesmo erro: o certificado que chega é o deles, e a raiz deles está no
    repositório do Windows, não na foto.

    Ordem: `truststore` (delega ao Schannel do Windows — mesma validação do
    navegador, com AIA e raízes corporativas), `certifi` (raízes da Mozilla,
    para repositório do Windows vazio ou quebrado) e, por fim, o padrão.
    Verificação NUNCA é desligada: o que se baixa aqui é um .exe que vai ser
    executado, e aceitar certificado inválido seria abrir a porta para trocarem
    o executável no meio do caminho.
    """
    global _ctx_ssl
    if _ctx_ssl is not None:
        return _ctx_ssl
    try:
        import truststore
        _ctx_ssl = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        _log.info("TLS: validação pelo repositório de certificados do Windows (truststore)")
        return _ctx_ssl
    except Exception as e:
        _log.info(f"TLS: truststore indisponível ({e})")
    try:
        import certifi
        _ctx_ssl = ssl.create_default_context(cafile=certifi.where())
        _log.info("TLS: validação pelas raízes do certifi")
        return _ctx_ssl
    except Exception as e:
        _log.info(f"TLS: certifi indisponível ({e})")
    _ctx_ssl = ssl.create_default_context()
    _log.info("TLS: contexto padrão do Python")
    return _ctx_ssl


def erro_de_certificado(e):
    """O erro é de validação de certificado? (a saída para o usuário é outra)"""
    if isinstance(e, ssl.SSLCertVerificationError):
        return True
    return 'CERTIFICATE_VERIFY_FAILED' in str(e) or 'certificate verify failed' in str(e)


def _texto_erro_consulta(e):
    """Mensagem do erro de consulta, com o caminho de saída quando é certificado."""
    if erro_de_certificado(e):
        return ("Não foi possível validar o certificado do GitHub nesta máquina.\n\n"
                "Isso costuma ser antivírus ou proxy da rede inspecionando a conexão, "
                "ou o certificado raiz faltando no Windows. O site abre no navegador "
                "porque o navegador valida de outro jeito.\n\n"
                "Baixe a nova versão pelo navegador e substitua o executável:\n"
                f"{URL_RELEASES}\n\n"
                f"Detalhe técnico: {e}")
    return ("Não foi possível consultar o GitHub.\n"
            "Verifique sua internet.\n\n"
            f"Detalhe: {e}")


# ------------------------------------------------------------------ versões
def normalizar_versao(texto):
    """'v4.9' / 'centralsistec-v2.0' / ' 4.9 ' -> (4, 9). Devolve () se não achar."""
    m = re.search(r'(\d+(?:\.\d+)*)', str(texto or ''))
    if not m:
        return ()
    return tuple(int(p) for p in m.group(1).split('.'))


def comparar_versoes(v_nova, v_atual):
    """True quando `v_nova` é maior. Compara número a número, não texto.

    Comparar como texto dizia que '4.10' é menor que '4.9', e comparar listas de
    tamanhos diferentes fazia 4.9 perder para 4.9.1 mas dava confusão com 4.10 vs 4.9.
    Aqui as duas são igualadas em tamanho com zeros: (4,10) > (4,9) e (4,9,1) > (4,9,0).
    """
    a, b = normalizar_versao(v_nova), normalizar_versao(v_atual)
    if not a:
        return False
    if not b:
        return True
    n = max(len(a), len(b))
    a += (0,) * (n - len(a))
    b += (0,) * (n - len(b))
    return a > b


def extrair_versao(texto):
    """Mantida por compatibilidade: a versão como texto ('v4.9' -> '4.9')."""
    v = normalizar_versao(texto)
    return '.'.join(str(p) for p in v) if v else str(texto or '').replace('v', '').strip()


def escolher_asset(assets):
    """O arquivo da Release que deve ser baixado.

    Prefere `.zip` (é o que o instalador espera) e só depois um `.exe` solto. Pegar
    `assets[0]` cegamente baixava o que estivesse primeiro — um `.txt` de notas de
    versão anexado por engano bastava para quebrar a atualização de todo mundo.
    """
    if not assets:
        return None
    for ext in ('.zip', '.exe'):
        for a in assets:
            if str(a.get('name', '')).lower().endswith(ext):
                return a
    return None


# ------------------------------------------------------------------ consulta
def consultar_release(timeout=8):
    """Consulta a Release mais recente. Devolve dict ou levanta exceção.

    Sem Tk e sem thread de propósito: é a parte testável.
    """
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Importador-Sistec-Updater',   # a API do GitHub exige
        'Accept': 'application/vnd.github+json',
    })
    with urllib.request.urlopen(req, timeout=timeout, context=contexto_ssl()) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    return {
        'versao': extrair_versao(data.get('tag_name', '')),
        'tag': data.get('tag_name', ''),
        'notas': data.get('body') or '',
        'assets': data.get('assets') or [],
        'publicada_em': data.get('published_at') or '',
    }


def tem_novidade(release, versao_local=None):
    """A release consultada é mais nova que a instalada?"""
    return comparar_versoes(release.get('versao'), versao_local or VERSAO)


# ------------------------------------------------------- versão dispensada
def _cfg():
    c = configparser.ConfigParser()
    try:
        c.read('config.ini', encoding='utf-8')
    except Exception:
        pass
    return c


def versao_ignorada():
    return _cfg().get(SECAO_CFG, 'versao_ignorada', fallback='').strip()


def ignorar_versao(versao):
    """Guarda a versão que o usuário mandou não avisar mais."""
    c = _cfg()
    if not c.has_section(SECAO_CFG):
        c.add_section(SECAO_CFG)
    c.set(SECAO_CFG, 'versao_ignorada', str(versao))
    try:
        with open('config.ini', 'w', encoding='utf-8') as f:
            c.write(f)
    except Exception as e:
        _log.warning(f"Não foi possível guardar a versão dispensada: {e}")


def deve_avisar(release):
    """Avisa se é mais nova E não foi dispensada por quem usa."""
    if not tem_novidade(release):
        return False
    ign = versao_ignorada()
    return not (ign and not comparar_versoes(release['versao'], ign))


# ------------------------------------------------------------------ fluxos
def verificar_em_segundo_plano(root, ao_encontrar):
    """Checagem da abertura do sistema: silenciosa, sem travar nada.

    `ao_encontrar(release)` é chamado na thread da interface só quando há versão nova
    não dispensada. Falha de rede não gera aviso nenhum — abrir o sistema sem internet
    é normal e não é problema do usuário.
    """
    def task():
        try:
            rel = consultar_release()
        except Exception as e:
            _log.info(f"Checagem de versão não concluída: {e}")
            return
        if deve_avisar(rel):
            try:
                root.after(0, ao_encontrar, rel)
            except Exception:
                pass          # janela já fechada

    threading.Thread(target=task, daemon=True).start()


def _avisar_falha_consulta(root, e):
    """Erro da consulta. Em falha de certificado, oferece o download manual.

    Máquina que não valida o certificado não consegue se atualizar sozinha — de
    nada serve só informar o erro; o caminho que funciona é o navegador.
    """
    _log.warning(f"Consulta de versão falhou: {e}")
    if erro_de_certificado(e):
        if messagebox.askyesno("Erro de conexão",
                               _texto_erro_consulta(e) + "\n\nAbrir a página agora?"):
            try:
                import webbrowser
                webbrowser.open(URL_RELEASES)
            except Exception as e2:
                messagebox.showerror("Erro", f"Não foi possível abrir o navegador:\n{e2}")
        return
    messagebox.showerror("Erro de conexão", _texto_erro_consulta(e))


def verificar_e_atualizar(root, silencioso=False):
    """O botão "Atualizar sistema": consulta e, havendo versão nova, pergunta."""
    def task():
        try:
            rel = consultar_release()
        except Exception as e:
            if not silencioso:
                root.after(0, lambda e=e: _avisar_falha_consulta(root, e))
            return
        if tem_novidade(rel):
            root.after(0, perguntar_atualizacao, root, rel)
        elif not silencioso:
            root.after(0, lambda: messagebox.showinfo(
                "Atualização",
                f"Você já está na versão mais recente (v{VERSAO})."))

    threading.Thread(target=task, daemon=True).start()


def perguntar_atualizacao(root, release):
    """Pergunta se quer atualizar. Três saídas: agora, depois, não avisar mais."""
    versao_nova = release['versao']
    asset = escolher_asset(release['assets'])
    if not asset:
        messagebox.showwarning(
            "Atualização",
            f"A versão {versao_nova} foi publicada, mas a Release não tem o arquivo "
            ".zip do programa anexado.\n\nAvise o suporte.")
        return

    JanelaAtualizacao(root, release, asset)


class JanelaAtualizacao(tk.Toplevel):
    """Aviso de versão nova. Nada é baixado antes de o usuário mandar."""

    def __init__(self, parent, release, asset):
        super().__init__(parent)
        self.release = release
        self.asset = asset
        self.title("Atualização disponível")
        self.transient(parent)
        self.resizable(False, False)

        corpo = tk.Frame(self, bg=tema.CARD, padx=18, pady=14)
        corpo.pack(fill=tk.BOTH, expand=True)

        tk.Label(corpo, text=f"Versão {release['versao']} disponível",
                 font=(tema.FONTE, 13, "bold"), bg=tema.CARD,
                 fg=tema.SISTEC_BLUE).pack(anchor="w")
        tk.Label(corpo, text=f"Você está na v{VERSAO}.", font=(tema.FONTE, 9),
                 bg=tema.CARD, fg=tema.TEXT_SECOND).pack(anchor="w", pady=(0, 8))

        notas = (release.get('notas') or '').strip()
        if notas:
            quadro = tk.Frame(corpo, bg=tema.SURFACE)
            quadro.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
            txt = tk.Text(quadro, height=8, width=62, wrap=tk.WORD, bd=0,
                          bg=tema.SURFACE, fg=tema.TEXT, font=(tema.FONTE, 9),
                          padx=8, pady=6)
            txt.insert("1.0", notas)
            txt.config(state=tk.DISABLED)
            txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            sb = ttk.Scrollbar(quadro, command=txt.yview)
            txt.config(yscrollcommand=sb.set)
            sb.pack(side=tk.RIGHT, fill=tk.Y)

        mb = self.asset.get('size') or 0
        tk.Label(corpo, text=f"Download: {self.asset.get('name')} "
                             f"({mb / (1024 * 1024):.1f} MB)  ·  "
                             "seus logs e o config.ini não são alterados",
                 font=(tema.FONTE, 8), bg=tema.CARD,
                 fg=tema.TEXT_SECOND).pack(anchor="w", pady=(0, 10))

        botoes = tk.Frame(corpo, bg=tema.CARD)
        botoes.pack(fill=tk.X)
        tema.estilo_botao(botoes, "⬇  Atualizar agora", self._atualizar,
                          variante="primary").pack(side=tk.LEFT)
        tema.estilo_botao(botoes, "Depois", self.destroy,
                          variante="ghost").pack(side=tk.LEFT, padx=6)
        tema.estilo_botao(botoes, "Não avisar desta versão", self._ignorar,
                          variante="neutro").pack(side=tk.RIGHT)

        tema.centralizar(self)
        self.grab_set()

    def _ignorar(self):
        ignorar_versao(self.release['versao'])
        self.destroy()

    def _atualizar(self):
        pai = self.master
        url = self.asset.get('browser_download_url')
        nome = self.asset.get('name', '')
        versao = self.release['versao']
        self.destroy()
        _baixar_e_aplicar(pai, url, versao, nome)


# ------------------------------------------------------------------ aplicação
def _localizar_exe(pasta):
    """Acha o Importador_Sistec.exe extraído, esteja na raiz do zip ou numa subpasta."""
    direto = os.path.join(pasta, NOME_EXE)
    if os.path.isfile(direto):
        return direto
    for raiz, _dirs, arquivos in os.walk(pasta):
        for a in arquivos:
            if a.lower() == NOME_EXE.lower():
                return os.path.join(raiz, a)
    for raiz, _dirs, arquivos in os.walk(pasta):
        for a in arquivos:
            if a.lower().endswith('.exe'):
                return os.path.join(raiz, a)
    return None


def _baixar_e_aplicar(root, url, versao_nova="Desconhecida", nome_asset=""):
    if not getattr(sys, 'frozen', False):
        return messagebox.showinfo(
            "Somente na versão compilada",
            "A troca automática do executável só funciona no .exe.\n"
            "Rodando pelo código-fonte, use o git.")

    aviso = tk.Toplevel(root)
    aviso.title("Atualizando...")
    aviso.transient(root)
    tema.centralizar(aviso, 350, 150)
    aviso.grab_set()

    lbl = tk.Label(aviso, text="Baixando atualização...\nIsso pode levar alguns minutos.",
                   font=("Segoe UI", 11))
    lbl.pack(pady=10)

    progress = ttk.Progressbar(aviso, orient=tk.HORIZONTAL, length=280, mode='determinate')
    progress.pack(pady=5)

    lbl_status = tk.Label(aviso, text="0%", font=("Segoe UI", 9))
    lbl_status.pack()
    root.update_idletasks()

    def update_gui(pct, down_mb, tot_mb):
        progress['value'] = pct
        if tot_mb > 0:
            lbl_status.config(text=f"{pct}% ({down_mb:.1f} MB de {tot_mb:.1f} MB)")
        else:
            lbl_status.config(text=f"Baixado: {down_mb:.1f} MB")

    def falhar(msg):
        root.after(0, aviso.destroy)
        root.after(0, lambda: messagebox.showerror("Erro na atualização", msg))

    def task():
        try:
            temp_dir = tempfile.gettempdir()
            eh_zip = not str(nome_asset).lower().endswith('.exe')
            baixado = os.path.join(temp_dir,
                                   "atualizacao_sistec.zip" if eh_zip else NOME_EXE)
            extract_dir = os.path.join(temp_dir, "sistec_update")

            if os.path.exists(extract_dir):
                shutil.rmtree(extract_dir, ignore_errors=True)
            os.makedirs(extract_dir, exist_ok=True)

            # 1. Baixa o arquivo da Release com barra de progresso
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            # mesmo contexto TLS da consulta: o asset vem de outro host
            # (objects.githubusercontent.com) e cairia no mesmo erro de certificado
            with urllib.request.urlopen(req, context=contexto_ssl()) as response, \
                    open(baixado, 'wb') as out_file:
                total_size = int(response.getheader('Content-Length', 0))
                downloaded = 0
                while True:
                    chunk = response.read(16384)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    down_mb = downloaded / (1024 * 1024)
                    tot_mb = total_size / (1024 * 1024)
                    pct = int((downloaded / total_size) * 100) if total_size > 0 else 0
                    root.after(0, update_gui, pct, down_mb, tot_mb)

            root.after(0, lambda: lbl_status.config(text="Extraindo arquivos..."))

            # 2. Extrai (ou usa o .exe direto) e ACHA o executável antes de seguir.
            #    O .bat antigo copiava um caminho fixo: zip com o exe numa subpasta
            #    caía na tela de "FALHA NA ATUALIZACAO" sem dizer o motivo real.
            if eh_zip:
                with zipfile.ZipFile(baixado, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                novo_exe = _localizar_exe(extract_dir)
            else:
                novo_exe = baixado

            if not novo_exe:
                return falhar(
                    f"O arquivo baixado não contém o {NOME_EXE}.\n\n"
                    f"Conteúdo em: {extract_dir}")

            install_dir = os.path.dirname(sys.executable)
            exe_name = os.path.basename(sys.executable)
            destino = os.path.join(install_dir, exe_name)
            bat_path = os.path.join(temp_dir, "atualizar.bat")
            log_path_bat = os.path.join(temp_dir, "sistec_update_log.txt")

            bat_content = f"""@echo off
setlocal enabledelayedexpansion
set LOG={log_path_bat}
echo [%date% %time%] Iniciando atualizacao... > %LOG%

:: Mata o processo atual
echo [%date% %time%] Matando processo {exe_name}... >> %LOG%
taskkill /F /IM "{exe_name}" > NUL 2>&1
if %errorlevel% neq 0 (
    echo [%date% %time%] Aviso: processo ja estava encerrado >> %LOG%
)

:: Aguarda o sistema liberar o arquivo
echo [%date% %time%] Aguardando 3 segundos... >> %LOG%
timeout /t 3 /nobreak > NUL

:: Tenta copiar sem elevacao (funciona em Downloads, Desktop, etc.)
echo [%date% %time%] Tentando copiar sem elevacao... >> %LOG%
copy /y "{novo_exe}" "{destino}" >> %LOG% 2>&1
if %errorlevel% equ 0 (
    echo [%date% %time%] Copia sem elevacao OK >> %LOG%
    goto :sucesso
)

:: Se falhou, tenta com elevacao de administrador (so para copiar)
echo [%date% %time%] Copia sem elevacao falhou, tentando com admin... >> %LOG%
powershell -Command "Start-Process cmd -ArgumentList '/c copy /y \"\"{novo_exe}\"\" \"\"{destino}\"\"' -Verb RunAs -Wait"
if %errorlevel% equ 0 (
    echo [%date% %time%] Copia com admin OK >> %LOG%
    start "" /D "{install_dir}" "{destino}"
    goto :fim
)

:: Se chegou aqui, tudo falhou
echo [%date% %time%] ERRO: Nao foi possivel copiar o arquivo! >> %LOG%
echo ========================================
echo        FALHA NA ATUALIZACAO
echo ========================================
echo.
echo Nao foi possivel substituir o arquivo:
echo   {destino}
echo.
echo Motivo: provavelmente falta de permissao de escrita.
echo Tente executar o programa como Administrador e tentar novamente.
echo.
echo Detalhes em: %LOG%
pause
exit /b 1

:sucesso
echo [%date% %time%] Iniciando novo executavel... >> %LOG%
start "" /D "{install_dir}" "{destino}"

:fim
echo [%date% %time%] Concluido >> %LOG%
del "%~f0"
"""
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(bat_content)

            # --- REGISTRO DE HISTÓRICO DE ATUALIZAÇÃO ---
            log_path = os.path.join(install_dir, "historico_atualizacoes.log")
            try:
                data_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open(log_path, "a", encoding="utf-8") as f_log:
                    f_log.write(f"[{data_hora}] Atualização aplicada: "
                                f"da versão v{VERSAO} para v{versao_nova}\n")
            except Exception as e:
                _log.warning(f"Aviso: Não foi possível gravar o log de atualização: {e}")

            # Dispara o BAT fora do Python e desliga a aplicação (liberando o arquivo)
            if os.name == 'nt':
                subprocess.Popen(f'"{bat_path}"', shell=True,
                                 creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                subprocess.Popen(f'"{bat_path}"', shell=True)

            import time
            time.sleep(1)
            os._exit(0)

        except Exception as e:
            if erro_de_certificado(e):
                return falhar(_texto_erro_consulta(e))
            falhar(f"Erro ao baixar/aplicar a atualização:\n{e}")

    threading.Thread(target=task, daemon=True).start()


# nome antigo, mantido para não quebrar quem já importava
_perguntar_atualizacao = perguntar_atualizacao

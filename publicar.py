# -*- coding: utf-8 -*-
"""Publica uma versão nova no GitHub: compila, empacota, marca a tag e cria a Release.

Um comando só:

    .venv/Scripts/python.exe publicar.py

O que ele faz, na ordem, e para em qualquer passo que não feche:

  1. Lê a versão de `version.py` e confere que a tag `vX.Y` ainda não existe.
  2. Compila (`compilar.py`) — ou reaproveita o `dist/Importador_Sistec.exe` com
     `--sem-compilar`, quando o build já foi feito.
  3. Empacota o .exe num `Importador_Sistec_vX.Y.zip` com o .exe **na raiz**, que é
     onde o `utils/updater.py` procura.
  4. Cria a tag e envia (`git tag` + `git push`).
  5. Cria a Release no GitHub e sobe o .zip, usando as notas da versão que estão no
     `VERSION.md` (a seção "VERSÃO X.Y").

Nada disso é feito pelo cliente: ele só recebe o aviso de que existe versão nova.

## Token — normalmente não precisa fazer nada

Criar a Release exige um token com escopo `repo`. Na maioria das máquinas ele **já
existe**: quem consegue dar `git push` neste repositório tem um token guardado pelo
Git Credential Manager, e é dele que o script se serve por último. Nada para
configurar, nada para colar.

A ordem de procura é: `--token`, variável `GITHUB_TOKEN`, arquivo `.github_token` na
raiz (está no .gitignore) e, por fim, `git credential fill`. O token encontrado é
conferido por uma chamada de leitura **antes** de compilar, porque descobrir que falta
permissão depois da tag enviada obriga a apagar tag local e remota.

Sem token nenhum, o script vai até o passo 4 e para dizendo o que falta — a tag fica
pronta e a Release pode ser criada à mão em github.com.
"""
import argparse
import json
import mimetypes
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from version import VERSAO, DATA_VERSAO          # noqa: E402
from utils.updater import GITHUB_REPO, NOME_EXE  # noqa: E402

RAIZ = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(RAIZ, 'dist')
API = "https://api.github.com"
UPLOADS = "https://uploads.github.com"


def passo(txt):
    print(f"\n=== {txt}")


def erro(txt, codigo=1):
    print(f"\n❌ {txt}")
    sys.exit(codigo)


def rodar(cmd, **kw):
    print(f"  $ {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True,
                       encoding='utf-8', errors='replace', **kw)
    if r.stdout.strip():
        print("    " + r.stdout.strip().replace("\n", "\n    "))
    if r.returncode != 0:
        print("    " + (r.stderr or '').strip().replace("\n", "\n    "))
    return r


# ------------------------------------------------------------------ token
def token_do_git():
    """O token que o Git Credential Manager já guardou do seu `git push`.

    É o caminho que não exige configurar nada: quem consegue dar `git push` neste
    repositório já tem, no Windows Credential Manager, um token com escopo `repo` —
    e `repo` é o que a API pede para criar Release. O `gh` faz exatamente isso.

    Devolve None quando não há credencial guardada (nunca deu push, ou o helper é
    outro), e nunca imprime o valor.
    """
    try:
        r = subprocess.run(['git', 'credential', 'fill'],
                           input="protocol=https\nhost=github.com\n\n",
                           cwd=RAIZ, capture_output=True, text=True, timeout=25)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    for linha in (r.stdout or '').splitlines():
        if linha.startswith('password='):
            return linha[len('password='):].strip() or None
    return None


def obter_token(arg_token=None):
    """Token, na ordem: --token, GITHUB_TOKEN, .github_token, credencial do Git.

    Devolve (token, origem) para o log dizer de onde veio sem mostrar o valor.
    """
    if arg_token:
        return arg_token.strip(), '--token'
    if os.environ.get('GITHUB_TOKEN'):
        return os.environ['GITHUB_TOKEN'].strip(), 'variável GITHUB_TOKEN'
    caminho = os.path.join(RAIZ, '.github_token')
    if os.path.isfile(caminho):
        with open(caminho, encoding='utf-8') as f:
            conteudo = f.read().strip()
        if conteudo:
            return conteudo, 'arquivo .github_token'
    tok = token_do_git()
    if tok:
        return tok, 'credencial que o Git já guardou (git credential)'
    return None, None


def conferir_token(token):
    """Confirma que o token serve ANTES de compilar 23 MB e criar tag.

    Descobrir que falta permissão depois da tag enviada obriga a apagar tag local e
    remota para tentar de novo. Aqui a checagem é uma chamada de leitura.
    """
    try:
        req = urllib.request.Request(f"{API}/repos/{GITHUB_REPO}")
        req.add_header('Authorization', f'Bearer {token}')
        req.add_header('Accept', 'application/vnd.github+json')
        req.add_header('User-Agent', 'Importador-Sistec-Publicador')
        with urllib.request.urlopen(req, timeout=15) as resp:
            escopos = resp.headers.get('x-oauth-scopes') or ''
            dados = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return False, f"o GitHub recusou o token ({e.code} {e.reason})"
    except Exception as e:
        return False, f"não foi possível falar com o GitHub: {e}"

    if not dados.get('permissions', {}).get('push'):
        return False, f"o token não tem permissão de escrita em {GITHUB_REPO}"
    # token clássico/OAuth anuncia escopos; o fine-grained vem com o header vazio e
    # aí quem manda é o permissions.push que já foi conferido acima
    if escopos and 'repo' not in [e.strip() for e in escopos.split(',')]:
        return False, (f"o token não tem o escopo 'repo' (tem: {escopos}) — "
                       f"sem ele a API não cria Release")
    return True, f"escopos: {escopos or '(fine-grained)'} · push: sim"


def api(metodo, url, token, dados=None, binario=None, content_type=None):
    req = urllib.request.Request(url, method=metodo)
    req.add_header('Authorization', f'Bearer {token}')
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('User-Agent', 'Importador-Sistec-Publicador')
    corpo = None
    if dados is not None:
        corpo = json.dumps(dados).encode('utf-8')
        req.add_header('Content-Type', 'application/json')
    elif binario is not None:
        corpo = binario
        req.add_header('Content-Type', content_type or 'application/octet-stream')
        req.add_header('Content-Length', str(len(binario)))
    try:
        with urllib.request.urlopen(req, corpo) as resp:
            texto = resp.read().decode('utf-8')
        return json.loads(texto) if texto else {}
    except urllib.error.HTTPError as e:
        detalhe = e.read().decode('utf-8', 'replace')
        raise RuntimeError(f"{e.code} {e.reason} em {url}\n{detalhe}") from None


# ------------------------------------------------------------------ passos
def notas_da_versao(versao):
    """As linhas do VERSION.md da seção desta versão, viradas em texto de release."""
    caminho = os.path.join(RAIZ, 'VERSION.md')
    if not os.path.isfile(caminho):
        return f"Versão {versao}"
    with open(caminho, encoding='utf-8') as f:
        linhas = f.read().splitlines()

    inicio = None
    for i, l in enumerate(linhas):
        if re.match(rf'^#+\s*.*VERS[ÃA]O\s+{re.escape(versao)}\b', l, re.I):
            inicio = i + 1
            break
    if inicio is None:
        return f"Versão {versao} — {DATA_VERSAO}"

    corpo = []
    for l in linhas[inicio:]:
        if re.match(r'^#+\s*.*VERS[ÃA]O\s', l, re.I):
            break
        corpo.append(l)

    # a tabela do VERSION.md vira lista: "| Módulo | Status | Descrição |"
    itens = []
    for l in corpo:
        l = l.strip()
        if not l.startswith('|') or set(l) <= set('|-: '):
            continue
        celulas = [c.strip() for c in l.strip('|').split('|')]
        if len(celulas) >= 3 and 'Descrição' not in celulas[2]:
            itens.append(f"- **{celulas[0]}** — {celulas[2]}")
    texto = "\n".join(itens) if itens else "\n".join(corpo).strip()
    return f"### Versão {versao} — {DATA_VERSAO}\n\n{texto}"


def conferir_tag(tag):
    r = rodar(['git', 'tag', '-l', tag])
    if r.stdout.strip():
        erro(f"A tag {tag} já existe localmente.\n"
             f"   Suba a versão em version.py antes de publicar, ou apague a tag:\n"
             f"   git tag -d {tag}")
    r = rodar(['git', 'ls-remote', '--tags', 'origin', tag])
    if tag in (r.stdout or ''):
        erro(f"A tag {tag} já existe no GitHub. Suba a versão em version.py.")


def conferir_arvore_limpa():
    r = rodar(['git', 'status', '--porcelain'])
    sujos = [l for l in (r.stdout or '').splitlines()
             if l.strip() and not l.endswith('.pyc')]
    if sujos:
        print(f"  ⚠ {len(sujos)} arquivo(s) não commitado(s). A Release aponta para o "
              f"último commit, então o que não foi commitado NÃO estará no código "
              f"publicado (o .exe do zip é o compilado agora, esse sim está atual).")
    return not sujos


def compilar():
    passo("Compilando")
    exe = os.path.join(DIST, NOME_EXE)
    if os.path.exists(exe):
        try:
            os.replace(exe, exe + '.anterior')
        except PermissionError:
            erro(f"O {NOME_EXE} está em uso. Feche o programa e rode de novo.")
    r = subprocess.run([sys.executable, 'compilar.py'], cwd=RAIZ)
    if r.returncode != 0 or not os.path.exists(exe):
        erro("A compilação falhou. Veja a saída acima.")
    print(f"  ✔ {exe} ({os.path.getsize(exe):,} bytes)")
    return exe


def empacotar(exe, versao):
    passo("Empacotando o .zip")
    zip_path = os.path.join(DIST, f"Importador_Sistec_v{versao}.zip")
    # o .exe vai na RAIZ do zip: é onde o updater o procura primeiro
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(exe, NOME_EXE)
    with zipfile.ZipFile(zip_path) as z:
        nomes = z.namelist()
    if NOME_EXE not in nomes:
        erro(f"O zip saiu sem o {NOME_EXE} na raiz: {nomes}")
    print(f"  ✔ {zip_path} ({os.path.getsize(zip_path):,} bytes) — conteúdo: {nomes}")
    return zip_path


def marcar_e_enviar(tag, versao):
    passo("Marcando a tag e enviando")
    r = rodar(['git', 'tag', '-a', tag, '-m', f'Versao {versao}'])
    if r.returncode != 0:
        erro("Não foi possível criar a tag.")
    r = rodar(['git', 'push', 'origin', 'HEAD'])
    if r.returncode != 0:
        print("  ⚠ push do branch falhou (segue para a tag)")
    r = rodar(['git', 'push', 'origin', tag])
    if r.returncode != 0:
        erro("Não foi possível enviar a tag para o GitHub.")


def criar_release(token, tag, versao, notas, zip_path):
    passo("Criando a Release no GitHub")
    rel = api('POST', f"{API}/repos/{GITHUB_REPO}/releases", token, dados={
        'tag_name': tag,
        'name': f"Versão {versao}",
        'body': notas,
        'draft': False,
        'prerelease': False,
    })
    print(f"  ✔ Release criada: {rel.get('html_url')}")

    passo("Subindo o .zip")
    nome = os.path.basename(zip_path)
    with open(zip_path, 'rb') as f:
        binario = f.read()
    url = (f"{UPLOADS}/repos/{GITHUB_REPO}/releases/{rel['id']}/assets"
           f"?name={urllib.request.quote(nome)}")
    tipo = mimetypes.guess_type(nome)[0] or 'application/zip'
    asset = api('POST', url, token, binario=binario, content_type=tipo)
    print(f"  ✔ {asset.get('name')} ({asset.get('size', 0):,} bytes)")
    return rel


def conferir_do_lado_do_cliente(versao):
    """Consulta a API do mesmo jeito que o sistema instalado consulta."""
    passo("Conferindo como o cliente vê")
    from utils import updater
    rel = updater.consultar_release()
    asset = updater.escolher_asset(rel['assets'])
    print(f"  releases/latest -> {rel['tag']} (versão {rel['versao']})")
    print(f"  asset escolhido -> {asset and asset.get('name')}")
    if rel['versao'] != versao:
        erro(f"A API ainda devolve {rel['versao']}. Espere alguns segundos e confira "
             f"em github.com/{GITHUB_REPO}/releases")
    if not asset or not asset['name'].lower().endswith('.zip'):
        erro("O asset escolhido não é o .zip.")
    print("  ✔ um sistema em versão anterior vai receber o aviso desta.")


def main():
    p = argparse.ArgumentParser(description="Publica a versão atual no GitHub")
    p.add_argument('--sem-compilar', action='store_true',
                   help="usa o dist/Importador_Sistec.exe que já existe")
    p.add_argument('--token', help="token do GitHub (senão usa GITHUB_TOKEN ou .github_token)")
    p.add_argument('--so-empacotar', action='store_true',
                   help="compila e gera o zip, sem tocar no git nem no GitHub")
    args = p.parse_args()

    versao = str(VERSAO).strip()
    tag = f"v{versao}"
    print(f"Publicando a versão {versao} ({DATA_VERSAO}) como {tag} em {GITHUB_REPO}")

    token, origem = obter_token(args.token)
    if not args.so_empacotar:
        passo("Conferindo o acesso ao GitHub")
        if not token:
            print("  ⚠ Nenhum token encontrado. Vou compilar, empacotar e marcar a "
                  "tag,\n    mas a Release você terá de criar à mão.\n"
                  "    Como resolver: leia o cabeçalho deste arquivo (publicar.py).")
        else:
            print(f"  token: {origem}")
            serve, detalhe = conferir_token(token)
            print(f"  {'✔' if serve else '✖'} {detalhe}")
            if not serve:
                erro("O token encontrado não serve para publicar.\n"
                     "   Use --token, ou grave um em .github_token.")

        passo("Conferindo a versão e a tag")
        conferir_tag(tag)
        conferir_arvore_limpa()

    if args.sem_compilar:
        exe = os.path.join(DIST, NOME_EXE)
        if not os.path.exists(exe):
            erro(f"Não existe {exe}. Rode sem --sem-compilar.")
        print(f"\n=== Reaproveitando {exe} ({os.path.getsize(exe):,} bytes)")
    else:
        exe = compilar()

    zip_path = empacotar(exe, versao)
    if args.so_empacotar:
        print(f"\n✅ Pronto para subir à mão: {zip_path}")
        return

    notas = notas_da_versao(versao)
    print(f"\n=== Notas que vão para a Release\n{notas[:800]}")

    marcar_e_enviar(tag, versao)

    if not token:
        print(f"\n⚠ Tag {tag} enviada. Falta criar a Release e anexar:\n   {zip_path}")
        print(f"   https://github.com/{GITHUB_REPO}/releases/new?tag={tag}")
        return

    criar_release(token, tag, versao, notas, zip_path)
    conferir_do_lado_do_cliente(versao)
    print(f"\n✅ Versão {versao} publicada. Quem estiver em versão anterior vai ver o "
          f"aviso na próxima vez que abrir o sistema.")


if __name__ == '__main__':
    main()

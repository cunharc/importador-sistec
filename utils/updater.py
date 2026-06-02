import urllib.request
import json
import os
import sys
import threading
import zipfile
import subprocess
import re
import tempfile
import tkinter as tk
from tkinter import messagebox, ttk
from datetime import datetime
import shutil
from version import VERSAO

# IMPORTANTE: Coloque o seu usuário e repositório oficial do GitHub (precisa ser um repositório Público)
# Exemplo: "RafaelCunha/importador-sistec"
GITHUB_REPO = "cunharc/importador-sistec"

def comparar_versoes(v_nova, v_atual):
    try:
        nova = [int(i) for i in v_nova.split('.')]
        atual = [int(i) for i in v_atual.split('.')]
        return nova > atual
    except Exception:
        return v_nova > v_atual

def extrair_versao(texto):
    # Extrai magicamente apenas a parte numérica de qualquer tag (ex: 'centralsistec-v2.0' -> '2.0')
    match = re.search(r'(\d+\.\d+(?:\.\d+)?)', texto)
    return match.group(1) if match else texto.replace('v', '').strip()

def verificar_e_atualizar(root, silencioso=False):
    if not getattr(sys, 'frozen', False):
        if not silencioso: messagebox.showinfo("Aviso", "O sistema não está rodando compilado (.exe). A atualização automática via GitHub só funciona na versão final empacotada.")
        return

    if GITHUB_REPO == "SEU_USUARIO/SEU_REPOSITORIO":
        if not silencioso: messagebox.showwarning("Atenção", "Você precisa configurar a variável GITHUB_REPO no arquivo utils/updater.py antes de usar!")
        return

    def task():
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Python-urllib') # Necessário para a API do GitHub autorizar o robô
            
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
            
            versao_github = extrair_versao(data.get('tag_name', ''))
            versao_local = str(VERSAO).replace('v', '').strip()
            
            if comparar_versoes(versao_github, versao_local):
                root.after(0, _perguntar_atualizacao, root, versao_github, data.get('assets', []))
            else:
                if not silencioso: root.after(0, lambda: messagebox.showinfo("Atualização", "Você já possui a versão mais recente do sistema!"))
        except Exception as e:
            if not silencioso: root.after(0, lambda e=e: messagebox.showerror("Erro de Conexão", f"Não foi possível consultar o GitHub.\nVerifique sua internet ou a configuração do repositório.\nDetalhe: {e}"))
            
    threading.Thread(target=task, daemon=True).start()

def _perguntar_atualizacao(root, versao_nova, assets):
    if not assets:
        messagebox.showwarning("Aviso", "Nova versão encontrada, mas não há um arquivo ZIP anexado na Release do GitHub.")
        return
        
    resp = messagebox.askyesno("Atualização Disponível", 
        f"A versão {versao_nova} está disponível!\nSua versão atual é a {VERSAO}.\n\n"
        "Deseja baixar e atualizar agora?\n\n(Os seus logs e configurações não serão afetados)")
    if resp:
        # Baixa o primeiro asset do GitHub (o seu arquivo .zip compilado)
        download_url = assets[0]['browser_download_url']
        _baixar_e_aplicar(root, download_url, versao_nova)

def _baixar_e_aplicar(root, url, versao_nova="Desconhecida"):
    aviso = tk.Toplevel(root)
    aviso.title("Atualizando...")
    aviso.geometry("350x150")
    aviso.transient(root)
    aviso.grab_set()
    
    lbl = tk.Label(aviso, text="Baixando atualização...\nIsso pode levar alguns minutos.", font=("Segoe UI", 11))
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

    def task():
        try:
            temp_dir = tempfile.gettempdir()
            zip_path = os.path.join(temp_dir, "atualizacao_sistec.zip")
            extract_dir = os.path.join(temp_dir, "sistec_update")
            
            if os.path.exists(extract_dir):
                shutil.rmtree(extract_dir)
            os.makedirs(extract_dir, exist_ok=True)
            
            # 1. Baixa o ZIP do GitHub com barra de progresso
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response, open(zip_path, 'wb') as out_file:
                total_size = int(response.getheader('Content-Length', 0))
                downloaded = 0
                chunk_size = 16384
                
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    
                    down_mb = downloaded / (1024 * 1024)
                    tot_mb = total_size / (1024 * 1024)
                    pct = int((downloaded / total_size) * 100) if total_size > 0 else 0
                    
                    root.after(0, update_gui, pct, down_mb, tot_mb)
                    
            root.after(0, lambda: lbl_status.config(text="Extraindo arquivos..."))
            
            # 2. Extrai silenciosamente para a pasta temporária
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
                
            # 3. Cria um arquivo .bat que fecha o software, troca os arquivos e o reinicia automaticamente
            bat_path = os.path.join(temp_dir, "atualizar.bat")
            current_dir = os.getcwd()
            exe_name = os.path.basename(sys.executable)
            
            bat_content = f"""@echo off
:: Solicita privilegios de administrador caso seja necessario (Resolve C:\\Program Files)
net session >nul 2>&1
if %errorLevel% neq 0 (
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo Atualizando o Sistema Sistec... Por favor, aguarde a tela preta fechar sozinha.
timeout /t 2 /nobreak > NUL
taskkill /F /IM "{exe_name}" > NUL 2>&1
xcopy /s /y /q "{extract_dir}\\*" "{current_dir}\\"
start "" /D "{current_dir}" "{current_dir}\\Importador_Sistec.exe"
del "%~f0"
"""
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(bat_content)
            
            # --- REGISTRO DE HISTÓRICO DE ATUALIZAÇÃO ---
            log_path = os.path.join(current_dir, "historico_atualizacoes.log")
            try:
                data_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open(log_path, "a", encoding="utf-8") as f_log:
                    f_log.write(f"[{data_hora}] Atualização aplicada: da versão v{VERSAO} para v{versao_nova}\n")
            except Exception as e:
                print(f"Aviso: Não foi possível gravar o log de atualização: {e}")

            # Dispara o BAT fora do Python e desliga a aplicação atual (liberando os arquivos para serem substituídos)
            if os.name == 'nt':
                subprocess.Popen(f'"{bat_path}"', shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                subprocess.Popen(f'"{bat_path}"', shell=True)
            
            os._exit(0)
            
        except Exception as e:
            root.after(0, aviso.destroy)
            root.after(0, lambda e=e: messagebox.showerror("Erro", f"Erro ao baixar/aplicar a atualização:\n{e}"))

    threading.Thread(target=task, daemon=True).start()
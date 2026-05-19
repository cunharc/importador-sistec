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
from tkinter import messagebox
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
        _baixar_e_aplicar(root, download_url)

def _baixar_e_aplicar(root, url):
    aviso = tk.Toplevel(root)
    aviso.title("Atualizando...")
    aviso.geometry("320x120")
    aviso.transient(root)
    aviso.grab_set()
    
    lbl = tk.Label(aviso, text="Baixando atualização...\nIsso pode levar alguns minutos.", font=("Segoe UI", 11))
    lbl.pack(expand=True)
    root.update_idletasks()

    def task():
        try:
            temp_dir = tempfile.gettempdir()
            zip_path = os.path.join(temp_dir, "atualizacao_sistec.zip")
            extract_dir = os.path.join(temp_dir, "sistec_update")
            
            # 1. Baixa o ZIP do GitHub
            urllib.request.urlretrieve(url, zip_path)
            
            # 2. Extrai silenciosamente para uma pasta temporária
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
                
            # 3. Cria um arquivo .bat que fecha o software, troca os arquivos e o reinicia automaticamente
            bat_path = os.path.join(temp_dir, "atualizar.bat")
            current_dir = os.getcwd()
            
            bat_content = f"""@echo off
echo Atualizando o Sistema Sistec... Por favor, aguarde a tela preta fechar sozinha.
timeout /t 3 /nobreak > NUL
xcopy /s /y /q "{extract_dir}\\*" "{current_dir}\\"
start "" "{current_dir}\\Importador_Sistec.exe"
del "%~f0"
"""
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(bat_content)
            
            # Dispara o BAT fora do Python e desliga a aplicação atual (liberando os arquivos para serem substituídos)
            subprocess.Popen([bat_path], shell=True)
            root.after(0, root.quit)
            
        except Exception as e:
            root.after(0, aviso.destroy)
            root.after(0, lambda e=e: messagebox.showerror("Erro", f"Erro ao baixar/aplicar a atualização:\n{e}"))

    threading.Thread(target=task, daemon=True).start()
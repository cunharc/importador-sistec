import locale
# Correção para erro da biblioteca fdb em versões recentes do Python (3.11+)
if not hasattr(locale, 'resetlocale'):
    locale.resetlocale = lambda: locale.setlocale(locale.LC_ALL, "")

import tkinter as tk
import os
import sys
from PIL import Image, ImageTk
from tkinter import ttk
from telas.tela_inicial import TelaInicial
from utils.logger import get_logger
from utils import tema
from version import VERSAO, DATA_VERSAO

_log = get_logger('main')

def resource_path(relative_path):
    """Obtém o caminho absoluto para os recursos, funcionando no dev e no PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class MainContainer(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.pack(fill=tk.BOTH, expand=True)
        self.content = tk.Frame(self, bg="#F0F0F0")
        self.content.pack(fill=tk.BOTH, expand=True)

if __name__ == '__main__':
    root = tk.Tk()
    # Oculta a janela principal enquanto carrega o splash
    root.withdraw()
    
    # --- TELA DE CARREGAMENTO (SPLASH SCREEN) ---
    splash = tk.Toplevel(root)
    splash.overrideredirect(True) # Remove as bordas do Windows
    splash.configure(bg="white", highlightbackground=tema.SISTEC_BLUE, highlightthickness=3)

    splash_width = 400
    splash_height = 200
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    
    x = (screen_width / 2) - (splash_width / 2)
    y = (screen_height / 2) - (splash_height / 2)
    splash.geometry(f'{splash_width}x{splash_height}+{int(x)}+{int(y)}')
    splash.configure(bg="white")
    
    logo_path = resource_path("Logo oficial grupos - Sistec.png")
    if os.path.exists(logo_path):
        try:
            img = Image.open(logo_path)
            img.thumbnail((150, 150))
            splash_img = ImageTk.PhotoImage(img)
            lbl_img = tk.Label(splash, image=splash_img, bg="white")
            lbl_img.pack(expand=True)
        except Exception as e:
            _log.warning(f"Não foi possível carregar o logo da splash screen: {e}")
            
    lbl_texto = tk.Label(splash, text="Carregando Implantação Sistec...",
                         font=("Segoe UI", 10, "bold"), bg="white", fg=tema.SISTEC_BLUE)
    lbl_texto.pack(side=tk.BOTTOM, pady=10)
    
    splash.update() # Força a tela a aparecer imediatamente
    
    # --- CONFIGURAÇÃO DA JANELA PRINCIPAL ---
    root.title(f"Implantação Sistec v{VERSAO}")
    
    # Força a janela a abrir sempre maximizada
    try:
        root.state('zoomed')
    except tk.TclError:
        root.attributes('-zoomed', True)
    
    icon_path = resource_path("icon.ico")
    if os.path.exists(icon_path):
        root.iconbitmap(icon_path)

    # --- IDENTIDADE VISUAL GLOBAL (Sistecweb) ---
    tema.aplicar_tema(root)

    container = MainContainer(root)
    app = TelaInicial(container.content)
    
    # Função para fechar o splash e mostrar o app após 1.5 segundos
    def iniciar_app():
        splash.destroy()
        root.deiconify() # Mostra a janela principal
        
    root.after(1500, iniciar_app)
    root.mainloop()

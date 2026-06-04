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

        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0, bg="#F0F0F0")
        self.scrollbar_y = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollbar_x = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.scrollable_frame = tk.Frame(self.canvas, bg="#F0F0F0")

        self.scrollable_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        self.window_id = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar_y.set, xscrollcommand=self.scrollbar_x.set)

        self.scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_frame_configure(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._check_resize()

    def _on_canvas_configure(self, event=None):
        self._check_resize()

    def _check_resize(self):
        # Estica a tela se o monitor for grande, senão mantém o mínimo necessário e rola
        new_width = max(self.canvas.winfo_width(), self.scrollable_frame.winfo_reqwidth())
        new_height = max(self.canvas.winfo_height(), self.scrollable_frame.winfo_reqheight())
        self.canvas.itemconfig(self.window_id, width=new_width, height=new_height)

    def _on_mousewheel(self, event):
        widget = self.winfo_containing(event.x_root, event.y_root)
        if not widget or widget.winfo_toplevel() != self.winfo_toplevel():
            return # Ignora se o mouse estiver sobre um modal/popup
        if self.scrollable_frame.winfo_reqheight() > self.canvas.winfo_height():
            # Evita roubar o scroll se o usuário estiver rolando uma tabela (Treeview) ou combobox
            if widget.winfo_class() in ("Treeview", "Text", "Listbox", "Canvas", "TCombobox", "Scrollbar"):
                return
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

if __name__ == '__main__':
    root = tk.Tk()
    # Oculta a janela principal enquanto carrega o splash
    root.withdraw()
    
    # --- TELA DE CARREGAMENTO (SPLASH SCREEN) ---
    splash = tk.Toplevel(root)
    splash.overrideredirect(True) # Remove as bordas do Windows
    
    splash_width = 400
    splash_height = 200
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    
    x = (screen_width / 2) - (splash_width / 2)
    y = (screen_height / 2) - (splash_height / 2)
    splash.geometry(f'{splash_width}x{splash_height}+{int(x)}+{int(y)}')
    splash.configure(bg="white")
    
    logo_path = resource_path("sistec.jpg")
    if os.path.exists(logo_path):
        try:
            img = Image.open(logo_path)
            img.thumbnail((300, 120))
            splash_img = ImageTk.PhotoImage(img)
            lbl_img = tk.Label(splash, image=splash_img, bg="white")
            lbl_img.pack(expand=True)
        except Exception as e:
            _log.warning(f"Não foi possível carregar o logo da splash screen: {e}")
            
    lbl_texto = tk.Label(splash, text="Carregando Implantação Sistec...", font=("Arial", 10), bg="white")
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

    # --- IDENTIDADE VISUAL GLOBAl (Grades/Treeview) ---
    style = ttk.Style()
    if "clam" in style.theme_names():
        style.theme_use("clam") # Clam permite customizar a cor de fundo facilmente no Windows
        
    style.configure("Treeview.Heading", background="#003399", foreground="white", font=('Segoe UI', 10, 'bold'))
    style.map("Treeview", background=[('selected', '#D0E4FF')], foreground=[('selected', '#1A1A1A')])

    # Inicia o Container Responsivo Global
    container = MainContainer(root)
    
    # Inicia a nova Home (Hub) por dentro do container com scroll
    app = TelaInicial(container.scrollable_frame)
    
    # Função para fechar o splash e mostrar o app após 1.5 segundos
    def iniciar_app():
        splash.destroy()
        root.deiconify() # Mostra a janela principal
        
    root.after(1500, iniciar_app)
    root.mainloop()

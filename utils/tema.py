# -*- coding: utf-8 -*-
"""
Identidade visual Sistecweb (Sistec Manager) aplicada ao app desktop (tkinter).

O design system oficial é web (glassmorphism/CSS). Aqui fazemos a tradução fiel
possível em tkinter: paleta de marca, tipografia, superfícies, cores semânticas
e estilo global dos widgets ttk (grades, abas, botões, campos, scrollbars).

Uso:
    from utils import tema
    tema.aplicar_tema(root)          # 1x no main, reestiliza todos os ttk
    header = tema.montar_header(frame, "TÍTULO", "subtítulo")
    badge  = tema.montar_badge(frame, "OK", "ok")
"""

import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont

# ============================ MARCA ============================
SISTEC_BLUE = "#14146E"       # primary / navy institucional
SISTEC_BLUE_DARK = "#141132"  # texto forte / navy profundo
SISTEC_RED = "#C80000"        # accent institucional
SISTEC_RED_DARK = "#960000"   # hover/pressed do vermelho
SISTEC_ORANGE = "#FF6A14"     # Sistec IA / microdestaques

# Apoio Material (quando o azul puro pesar)
BLUE_SOFT = "#575992"
BLUE_CONTAINER = "#E1E0FF"    # chips, seleção de grade, badges suaves

# ========================= SUPERFÍCIES (light) =========================
BG_BASE = "#F7F9FB"
SURFACE = "#F2F4F6"
CARD = "#FFFFFF"
BORDER = "#E2E6EA"
TEXT = "#141132"
TEXT_SECOND = "#444651"
TEXT_ON_BRAND = "#FFFFFF"
TEXT_ON_BRAND_SOFT = "#C0C1FF"

# ========================= SEMÂNTICAS (light) =========================
SUCCESS = "#22C55E"; SUCCESS_CT = "#DCFCE7"; SUCCESS_TX = "#166534"
ERROR = "#BA1A1A";   ERROR_CT = "#FFDAD6";   ERROR_TX = "#93000A"
WARNING = "#FACC15"; WARNING_CT = "#FEF3C7"; WARNING_TX = "#92400E"
INFO = "#3B82F6";    INFO_CT = "#DBEAFE";    INFO_TX = "#1E40AF"

# ========================= TIPOGRAFIA =========================
# Inter é a fonte oficial; cai para Segoe UI (Windows) e depois genérica.
FONTE = "Segoe UI"


def _familia_disponivel(root):
    try:
        familias = set(tkfont.families(root))
    except Exception:
        familias = set()
    for f in ("Inter", "Segoe UI", "Calibri"):
        if f in familias:
            return f
    return "TkDefaultFont"


def fonte(tam=10, peso="normal"):
    """Atalho para (familia, tamanho, peso) usando a fonte da marca vigente."""
    if peso in ("bold", "italic"):
        return (FONTE, tam, peso)
    return (FONTE, tam)


def aplicar_tema(root):
    """Aplica a identidade Sistecweb globalmente aos widgets ttk."""
    global FONTE
    FONTE = _familia_disponivel(root)
    fam = FONTE

    try:
        root.configure(bg=BG_BASE)
    except Exception:
        pass

    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    # ---- base ----
    style.configure(".", font=(fam, 10), background=BG_BASE, foreground=TEXT)
    style.configure("TFrame", background=BG_BASE)
    style.configure("TLabel", background=BG_BASE, foreground=TEXT)

    # ---- LabelFrame (painéis) ----
    style.configure("TLabelframe", background=CARD, bordercolor=BORDER,
                    relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", background=CARD, foreground=SISTEC_BLUE,
                    font=(fam, 10, "bold"))

    # ---- Botões ttk (primário navy) ----
    style.configure("TButton", font=(fam, 9, "bold"), background=SISTEC_BLUE,
                    foreground="white", borderwidth=0, focuscolor=SISTEC_BLUE,
                    padding=(12, 5))
    style.map("TButton",
              background=[("pressed", SISTEC_BLUE_DARK), ("active", BLUE_SOFT),
                          ("disabled", "#B7BCC4")],
              foreground=[("disabled", "#EDEDED")])

    # Variantes de botão ttk
    style.configure("Accent.TButton", background=SISTEC_RED)
    style.map("Accent.TButton", background=[("pressed", SISTEC_RED_DARK), ("active", "#B10000")])
    style.configure("Success.TButton", background=SUCCESS)
    style.map("Success.TButton", background=[("pressed", "#15803D"), ("active", "#16A34A")])
    style.configure("Ghost.TButton", background=SURFACE, foreground=SISTEC_BLUE)
    style.map("Ghost.TButton", background=[("active", BLUE_CONTAINER)])

    # ---- Campos ----
    style.configure("TEntry", fieldbackground="white", foreground=TEXT,
                    bordercolor=BORDER, borderwidth=1, padding=4)
    style.map("TEntry", bordercolor=[("focus", SISTEC_BLUE)])
    style.configure("TCombobox", fieldbackground="white", foreground=TEXT,
                    bordercolor=BORDER, borderwidth=1, padding=4, arrowcolor=SISTEC_BLUE)
    style.map("TCombobox",
              fieldbackground=[("readonly", "white")],
              bordercolor=[("focus", SISTEC_BLUE)])
    style.configure("TSpinbox", fieldbackground="white", bordercolor=BORDER,
                    borderwidth=1, arrowcolor=SISTEC_BLUE)

    # ---- Notebook (abas) ----
    style.configure("TNotebook", background=BG_BASE, borderwidth=0, tabmargins=(2, 4, 2, 0))
    style.configure("TNotebook.Tab", font=(fam, 9, "bold"), padding=(14, 6),
                    background=SURFACE, foreground=TEXT_SECOND, borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", SISTEC_BLUE)],
              foreground=[("selected", "white")],
              expand=[("selected", (1, 1, 1, 0))])

    # ---- Treeview (grades) ----
    style.configure("Treeview", font=(fam, 9), rowheight=24,
                    fieldbackground="white", background="white",
                    foreground=TEXT, bordercolor=BORDER, borderwidth=1)
    style.configure("Treeview.Heading", font=(fam, 10, "bold"),
                    background=SISTEC_BLUE, foreground="white", relief="flat", padding=4)
    style.map("Treeview.Heading", background=[("active", SISTEC_BLUE_DARK)])
    style.map("Treeview",
              background=[("selected", BLUE_CONTAINER)],
              foreground=[("selected", TEXT)])

    # ---- Scrollbar ----
    style.configure("TScrollbar", background=SURFACE, troughcolor=BG_BASE,
                    bordercolor=BG_BASE, arrowcolor=SISTEC_BLUE)
    style.configure("Vertical.TScrollbar", background=SURFACE, troughcolor=BG_BASE,
                    bordercolor=BG_BASE, arrowcolor=SISTEC_BLUE)
    style.configure("Horizontal.TScrollbar", background=SURFACE, troughcolor=BG_BASE,
                    bordercolor=BG_BASE, arrowcolor=SISTEC_BLUE)

    # ---- Check / Radio ----
    style.configure("TCheckbutton", background=BG_BASE, foreground=TEXT, font=(fam, 9))
    style.map("TCheckbutton", foreground=[("disabled", "#9AA0A6")])
    style.configure("TRadiobutton", background=BG_BASE, foreground=TEXT, font=(fam, 9))

    # ---- Progressbar / Separador ----
    style.configure("TProgressbar", background=SISTEC_BLUE, troughcolor=SURFACE, borderwidth=0)
    style.configure("TSeparator", background=BORDER)

    return fam


# ==================== HELPERS PARA WIDGETS tk (não-ttk) ====================
def montar_header(parent, titulo, subtitulo=None, cor=None):
    """Cabeçalho padrão de módulo: barra navy com título e subtítulo opcional.
    Retorna o Frame (já com título dentro); só faça .pack()/.grid() nele."""
    cor = cor or SISTEC_BLUE
    header = tk.Frame(parent, bg=cor, padx=16, pady=10)
    tk.Label(header, text=titulo, font=(FONTE, 14, "bold"), bg=cor, fg="white").pack(anchor="w")
    if subtitulo:
        tk.Label(header, text=subtitulo, font=(FONTE, 9), bg=cor,
                 fg=TEXT_ON_BRAND_SOFT).pack(anchor="w")
    return header


def montar_badge(parent, texto, tipo="info"):
    """Badge de status na camada semântica: tipo in {ok, warn, danger, info}."""
    mapa = {
        "ok": (SUCCESS_CT, SUCCESS_TX),
        "warn": (WARNING_CT, WARNING_TX),
        "danger": (ERROR_CT, ERROR_TX),
        "info": (INFO_CT, INFO_TX),
    }
    bgc, fgc = mapa.get(tipo, mapa["info"])
    return tk.Label(parent, text=texto, bg=bgc, fg=fgc,
                    font=(FONTE, 8, "bold"), padx=8, pady=2)


# Cores do menu lateral (navy profundo da identidade Sistecweb) — iguais ao main
SIDEBAR_BG = "#141132"
SIDEBAR_HOVER = "#232152"
SIDEBAR_ACTIVE = "#2E2C6E"
SIDEBAR_FG = "#B9BBE0"
SIDEBAR_FG_MUTED = "#6E6FA8"
SIDEBAR_FG_DISABLED = "#5B5C86"


def centralizar(win, largura=None, altura=None):
    """Centraliza um Toplevel sobre a janela-mãe (ou na tela, se não houver).
    Passe largura/altura para fixar o tamanho; senão usa o tamanho atual/solicitado."""
    try:
        win.update_idletasks()
    except Exception:
        pass
    w = largura or win.winfo_width()
    h = altura or win.winfo_height()
    if not w or w <= 1:
        w = win.winfo_reqwidth()
    if not h or h <= 1:
        h = win.winfo_reqheight()

    x = y = None
    try:
        master = win.master
        if master is not None and master.winfo_ismapped() and int(master.winfo_width()) > 1:
            x = master.winfo_rootx() + (master.winfo_width() - w) // 2
            y = master.winfo_rooty() + (master.winfo_height() - h) // 2
    except Exception:
        x = y = None

    if x is None or y is None:
        x = (win.winfo_screenwidth() - w) // 2
        y = (win.winfo_screenheight() - h) // 2

    win.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")


def largura_sidebar(root=None):
    """210px numa tela normal, 168px em console de servidor (< 1300px de largura).

    Em 1024px o menu de 210 come 20% da tela útil e a grade fica impossível.
    """
    try:
        tela = (root or tk._default_root).winfo_screenwidth()
    except Exception:
        return 210
    return 210 if tela >= 1300 else 168


def montar_sidebar(parent, largura=210):
    """Cria a coluna do menu lateral (navy) no padrão do main.
    Retorna o Frame já empacotado à esquerda; adicione itens com botao_sidebar()."""
    sb = tk.Frame(parent, bg=SIDEBAR_BG, width=largura)
    sb.pack(side=tk.LEFT, fill=tk.Y)
    sb.pack_propagate(False)
    return sb


def titulo_sidebar(parent, texto):
    """Rótulo de seção do menu lateral (ex.: 'AÇÕES')."""
    return tk.Label(parent, text=texto, font=(FONTE, 8, "bold"),
                    bg=SIDEBAR_BG, fg=SIDEBAR_FG_MUTED, anchor="w", padx=18)


def botao_sidebar(parent, texto, comando, cor_fg=None):
    """Item de menu lateral (navy) que ocupa a largura toda — visual do main.
    Continua sendo um tk.Button, então aceita .config(state=tk.DISABLED/NORMAL)."""
    fg = cor_fg or SIDEBAR_FG
    b = tk.Button(parent, text=texto, command=comando,
                  bg=SIDEBAR_BG, fg=fg,
                  activebackground=SIDEBAR_ACTIVE, activeforeground="white",
                  disabledforeground=SIDEBAR_FG_DISABLED,
                  font=(FONTE, 10, "bold"), relief=tk.FLAT, bd=0,
                  cursor="hand2", anchor="w", padx=18, pady=9)

    def _enter(_e):
        if str(b["state"]) != "disabled":
            b.config(bg=SIDEBAR_HOVER, fg="white")

    def _leave(_e):
        b.config(bg=SIDEBAR_BG, fg=fg)

    b.bind("<Enter>", _enter)
    b.bind("<Leave>", _leave)
    return b


def estilo_botao(parent, texto, comando, variante="primary", **kw):
    """Cria um tk.Button já na paleta da marca.
    variante in {primary, accent, success, ghost, neutro}."""
    paleta = {
        "primary": (SISTEC_BLUE, "white"),
        "accent": (SISTEC_RED, "white"),
        "success": (SUCCESS, "white"),
        "ghost": (SURFACE, SISTEC_BLUE),
        "neutro": ("#95A5A6", "white"),
    }
    bgc, fgc = paleta.get(variante, paleta["primary"])
    return tk.Button(parent, text=texto, command=comando, bg=bgc, fg=fgc,
                     font=(FONTE, 9, "bold"), relief=tk.FLAT, cursor="hand2",
                     activebackground=bgc, activeforeground=fgc,
                     padx=kw.pop("padx", 12), pady=kw.pop("pady", 5), **kw)


class BarraFluida(ttk.LabelFrame):
    """Barra de controles que quebra em várias linhas quando a largura não dá.

    Em console de servidor (1024px ou menos) uma barra com 10 controles numa única
    linha simplesmente sai para fora da tela: não há scroll horizontal e o usuário
    não tem como saber que existe algo ali. Aqui cada grupo (rótulo + campo) é uma
    célula do grid e o número de colunas é recalculado no <Configure>.

    Nasceu na tela de produtos por XML e vive aqui porque três telas já precisam
    dela — a de NCM foi a terceira.
    """

    def __init__(self, parent, texto, **kw):
        super().__init__(parent, text=texto, padding=6, **kw)
        self._grupos = []
        self._colunas = 0
        self.bind("<Configure>", self._on_configure)

    def grupo(self):
        """Cria e devolve o frame de um grupo de controles."""
        f = ttk.Frame(self)
        self._grupos.append(f)
        return f

    def montar(self):
        """Chame depois de criar todos os grupos."""
        self._dispor(len(self._grupos))

    def _dispor(self, por_linha):
        por_linha = max(1, min(len(self._grupos), int(por_linha)))
        if por_linha == self._colunas or not self._grupos:
            return
        self._colunas = por_linha
        for i, f in enumerate(self._grupos):
            f.grid(row=i // por_linha, column=i % por_linha,
                   padx=(0, 12), pady=2, sticky=tk.W)

    _GAP = 12          # o padx entre células, igual ao usado no _dispor

    def _largura_com(self, por_linha):
        """Largura que o grid ocuparia com esta quantidade de colunas.

        No grid do Tk cada coluna assume a largura do seu MAIOR ocupante — não a
        do maior grupo da barra inteira. Somar coluna a coluna é o cálculo exato;
        dimensionar tudo pelo grupo mais largo (o que este código fazia antes)
        superestimava a largura e quebrava a barra em linhas que cabiam. Numa
        barra com um controle largo e cinco estreitos, isso custava duas linhas
        a mais mesmo em monitor de 1920.
        """
        larguras = [f.winfo_reqwidth() for f in self._grupos]
        colunas = [max(larguras[c::por_linha]) for c in range(min(por_linha, len(larguras)))]
        return sum(colunas) + self._GAP * len(colunas)

    def _on_configure(self, event):
        if not self._grupos:
            return
        # a maior quantidade de colunas que ainda cabe; 1 é o piso
        cabe = 1
        for n in range(1, len(self._grupos) + 1):
            if self._largura_com(n) <= event.width:
                cabe = n
        self._dispor(cabe)


def rotulo_campo(parent, texto):
    """Rótulo em negrito de um campo dentro de uma BarraFluida."""
    return tk.Label(parent, text=texto, font=(FONTE, 9, "bold"))

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import configparser
import threading
import re
import os
import datetime

from utils.excel_reader import obter_abas_planilha, ler_planilha_produtos
from utils.firebird_service import FirebirdService
from utils import tema


class DropdownListbox(tk.Frame):
    """Entry + dropdown Listbox com destaque visual por cor."""

    def __init__(self, parent, width=50, height=8, **kwargs):
        super().__init__(parent)
        self._var = tk.StringVar()
        self._items = []
        self._highlight_set = set()
        self._height = height

        self.entry = ttk.Entry(self, textvariable=self._var, width=width, state="readonly")
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.entry.bind("<Button-1>", self._show_dropdown)

        self.btn = ttk.Button(self, text="\u25bc", width=3, command=self._show_dropdown)
        self.btn.pack(side=tk.RIGHT)

        self._top = tk.Toplevel(self)
        self._top.withdraw()
        self._top.overrideredirect(True)
        self._top.attributes("-topmost", True)

        self.listbox = tk.Listbox(self._top, width=width, height=height, exportselection=False,
                                  font=("Segoe UI", 9))
        self.listbox.pack(fill=tk.BOTH, expand=True)
        self.listbox.bind("<ButtonRelease-1>", self._on_select)
        self.listbox.bind("<Escape>", lambda e: self._hide_dropdown())
        self.listbox.bind("<Return>", self._on_select)
        self._top.bind("<FocusOut>", lambda e: self.after(100, self._hide_dropdown))

    def _show_dropdown(self, event=None):
        if not self._items:
            return
        self.listbox.delete(0, tk.END)
        for item in self._items:
            idx = self.listbox.size()
            self.listbox.insert(tk.END, item)
            if item in self._highlight_set:
                self.listbox.itemconfig(idx, foreground="#0066CC")

        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        self._top.geometry(f"+{x}+{y}")
        self._top.deiconify()
        self._top.lift()
        self.listbox.focus_set()

    def _hide_dropdown(self):
        self._top.withdraw()

    def _on_select(self, event=None):
        sel = self.listbox.curselection()
        if sel:
            self._var.set(self._items[sel[0]])
        self._hide_dropdown()

    def get(self):
        return self._var.get()

    def set(self, value):
        self._var.set(value)

    def current(self, index):
        if 0 <= index < len(self._items):
            self._var.set(self._items[index])

    def set_items(self, items, bold_items=None):
        self._items = items
        self._highlight_set = set(bold_items) if bold_items else set()

    def config_state(self, state):
        self.entry.config(state=state)

CAMPOS_DISPONIVEIS = [
    ("C\u00f3digo (produto/import./aux.) *", "codigo", True),
    ("Descri\u00e7\u00e3o", "descricao", False),
    ("Pre\u00e7o *", "preco", True),
    ("NCM", "ncm", False),
    ("C\u00f3d. Barras", "ean", False),
]

SERIE_PADRAO = '1'


class TelaImportacaoPlanilhaListaPrecos(ttk.Frame):
    def __init__(self, parent, callback_voltar=None):
        super().__init__(parent, padding="10")
        self.parent = parent
        self.callback_voltar = callback_voltar
        self.pack(fill=tk.BOTH, expand=True)

        self.registros_lidos = []
        self.caminho_arquivo = ""
        self.listas_existentes = []

        self.config = configparser.ConfigParser()
        self.config.read('config.ini', encoding='utf-8')
        self.config_db = {
            'host': self.config.get('FIREBIRD', 'servidor', fallback='127.0.0.1'),
            'port': self.config.get('FIREBIRD', 'porta', fallback='3050'),
            'database': self.config.get('FIREBIRD', 'caminho_banco', fallback=''),
            'user': self.config.get('FIREBIRD', 'usuario', fallback='SYSDBA'),
            'password': self.config.get('FIREBIRD', 'senha', fallback='masterkey'),
            'fbclient': self.config.get('FIREBIRD', 'fbclient', fallback='')
        }

        self._criar_widgets()
        rotulo_salvo = self._ler_rotulo_lista_salvo()
        self.after(100, self._carregar_todas_configs)
        self.after(500, lambda: self._carregar_listas_existentes(rotulo_salvo))

    def _criar_widgets(self):
        # Header do m\u00f3dulo (identidade Sistecweb)
        tema.montar_header(
            self, "Importar Lista de Pre\u00e7os (Excel)",
            "Importa\u00e7\u00e3o de tabela de pre\u00e7os via planilha (XLSX/CSV) com valida\u00e7\u00e3o contra o ERP"
        ).pack(fill=tk.X)

        # ===================== CORPO: menu lateral + conte\u00fado =====================
        corpo = tk.Frame(self, bg=tema.BG_BASE)
        corpo.pack(fill=tk.BOTH, expand=True)

        # -------- MENU LATERAL (padr\u00e3o do main) --------
        sidebar = tema.montar_sidebar(corpo)

        # Rodap\u00e9 do menu: Voltar
        rodape_sb = tk.Frame(sidebar, bg=tema.SIDEBAR_BG)
        rodape_sb.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 8))
        self.btn_voltar = tema.botao_sidebar(rodape_sb, "\u238b   Voltar", self._fechar_tela)
        self.btn_voltar.pack(fill=tk.X)

        tema.titulo_sidebar(sidebar, "A\u00c7\u00d5ES").pack(fill=tk.X, pady=(16, 4))

        self.btn_analisar = tema.botao_sidebar(sidebar, "\U0001f50d   Carregar e Analisar Planilha", self._iniciar_analise)
        self.btn_analisar.pack(fill=tk.X)

        self.btn_exportar = tema.botao_sidebar(sidebar, "\U0001f4e4   Exportar por Status", self._exportar_por_status)
        self.btn_exportar.config(state=tk.DISABLED)
        self.btn_exportar.pack(fill=tk.X)

        self.btn_importar = tema.botao_sidebar(sidebar, "\U0001f680   Injetar Pre\u00e7os no ERP", self._iniciar_importacao, cor_fg="#7EE0A0")
        self.btn_importar.config(state=tk.DISABLED)
        self.btn_importar.pack(fill=tk.X)

        # -------- CONTE\u00daDO --------
        content = tk.Frame(corpo, bg=tema.BG_BASE)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=16, pady=12)

        # === CONFIG LISTA ===
        frame_lista = ttk.LabelFrame(content, text="Configura\u00e7\u00e3o da Lista de Pre\u00e7os", padding="10")
        frame_lista.pack(fill=tk.X, pady=5)

        self.var_modo = tk.StringVar(self, value="EXISTENTE")

        rb_existente = ttk.Radiobutton(frame_lista, text="Atualizar Lista Existente:", variable=self.var_modo, value="EXISTENTE", command=self._toggle_modo)
        rb_existente.grid(row=0, column=0, sticky=tk.W, padx=5)

        self.cb_listas = DropdownListbox(frame_lista, width=50)
        self.cb_listas.grid(row=0, column=1, columnspan=3, padx=5, sticky=tk.W)

        rb_nova = ttk.Radiobutton(frame_lista, text="Criar Nova Lista:", variable=self.var_modo, value="NOVA", command=self._toggle_modo)
        rb_nova.grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)

        ttk.Label(frame_lista, text="C\u00f3digo:").grid(row=1, column=1, sticky=tk.E, padx=5)
        self.ent_cod_lista = ttk.Entry(frame_lista, width=10, state=tk.DISABLED)
        self.ent_cod_lista.grid(row=1, column=2, sticky=tk.W, padx=5)

        ttk.Label(frame_lista, text="Descri\u00e7\u00e3o:").grid(row=1, column=3, sticky=tk.E, padx=5)
        self.ent_desc_lista = ttk.Entry(frame_lista, width=40, state=tk.DISABLED)
        self.ent_desc_lista.grid(row=1, column=4, sticky=tk.W, padx=5)

        # === FILE SELECTION ===
        file_row = ttk.Frame(content)
        file_row.pack(fill=tk.X, pady=5)

        tk.Label(file_row, text="Arquivo:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 2))
        self.ent_arquivo = ttk.Entry(file_row)
        self.ent_arquivo.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        ttk.Button(file_row, text="\U0001f4c1 Selecionar", command=self._selecionar_arquivo).pack(side=tk.LEFT, padx=2)

        tk.Label(file_row, text="Aba:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(10, 2))
        self.cb_abas = ttk.Combobox(file_row, width=16, state="readonly")
        self.cb_abas.pack(side=tk.LEFT, padx=2)

        tk.Label(file_row, text="Linha Inicial:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(10, 2))
        self.ent_linha_ini = ttk.Entry(file_row, width=6)
        self.ent_linha_ini.insert(0, "2")
        self.ent_linha_ini.pack(side=tk.LEFT, padx=2)

        # === COLUMN MAPPING ===
        frame_map = ttk.LabelFrame(content, text="Mapeamento de Colunas (Insira a letra: A, B, C...)", padding="8")
        frame_map.pack(fill=tk.X, pady=4)

        self.entradas_map = {}
        for i, (lbl_texto, chave, obrigatorio) in enumerate(CAMPOS_DISPONIVEIS):
            col = i * 2
            tk.Label(frame_map, text=lbl_texto, font=("Segoe UI", 8, "bold")).grid(row=0, column=col, padx=(5, 1), pady=4, sticky=tk.E)
            ent = ttk.Entry(frame_map, width=5)
            ent.grid(row=0, column=col + 1, padx=(0, 8), pady=4, sticky=tk.W)
            self.entradas_map[chave] = ent

        self._carregar_config_mapeamento()

        # === ACTIONS (inline: sele\u00e7\u00e3o/dicas/progresso) ===
        actions_row = ttk.Frame(content)
        actions_row.pack(fill=tk.X, pady=4)

        ttk.Button(actions_row, text="\u2611 Marcar Todos", command=self._marcar_todos).pack(side=tk.LEFT, padx=3)
        ttk.Button(actions_row, text="\u2610 Desmarcar", command=self._desmarcar_todos).pack(side=tk.LEFT, padx=3)

        ttk.Label(actions_row, text="\U0001f4a1 Duplo clique no PRE\u00c7O para editar manualmente",
                  foreground="#14146E", font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT, padx=10)

        self.progresso = ttk.Progressbar(actions_row, orient=tk.HORIZONTAL, mode='determinate', length=120)
        self.progresso.pack(side=tk.LEFT, padx=8)

        self.lbl_status = ttk.Label(actions_row, text="Aguardando configura\u00e7\u00e3o...", foreground="#555")
        self.lbl_status.pack(side=tk.LEFT, padx=2)

        # === TREEVIEW ===
        self.colunas = ("SEL", "STATUS", "C\u00d3D. PLANILHA", "DESCR. PLANILHA", "C\u00d3D. ERP", "DESCR. ERP", "PRE\u00c7O")
        self._sort_directions = {col: False for col in self.colunas}

        frame_grade = ttk.Frame(content)
        frame_grade.pack(fill=tk.BOTH, expand=True, pady=4)

        self.tree = ttk.Treeview(frame_grade, columns=self.colunas, show="headings")

        larguras = [40, 90, 100, 220, 100, 220, 100]
        for col, larg in zip(self.colunas, larguras):
            self.tree.heading(col, text=col + " \u2195", command=lambda c=col: self._sort_treeview(c))
            self.tree.column(col, width=larg, anchor=tk.W if "DESCR" in col else tk.CENTER)

        self.tree.tag_configure('OK', background='#EAFAF1')
        self.tree.tag_configure('ERRO', background='#FADBD8')

        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)
        self.tree.bind("<Double-1>", self._on_tree_double_click)

        scroll_y = ttk.Scrollbar(frame_grade, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

    # ==================== HELPERS ====================

    def _salvar_config_mapeamento(self):
        if not self.config.has_section('IMPORTACAO_LISTA_PRECO'):
            self.config.add_section('IMPORTACAO_LISTA_PRECO')
        for chave, ent in self.entradas_map.items():
            self.config.set('IMPORTACAO_LISTA_PRECO', f'mapa_{chave}', ent.get().strip())
        self.config['IMPORTACAO_LISTA_PRECO']['ultimo_arquivo'] = self.caminho_arquivo
        self.config['IMPORTACAO_LISTA_PRECO']['ultima_aba'] = self.cb_abas.get()
        self.config['IMPORTACAO_LISTA_PRECO']['linha_inicial'] = self.ent_linha_ini.get()
        self.config['IMPORTACAO_LISTA_PRECO']['modo'] = self.var_modo.get()
        self.config['IMPORTACAO_LISTA_PRECO']['lista_selecionada'] = self.cb_listas.get()
        self.config['IMPORTACAO_LISTA_PRECO']['nova_lista_codigo'] = self.ent_cod_lista.get()
        self.config['IMPORTACAO_LISTA_PRECO']['nova_lista_descricao'] = self.ent_desc_lista.get()
        try:
            with open('config.ini', 'w', encoding='utf-8') as f:
                self.config.write(f)
        except Exception:
            pass

    def _carregar_config_mapeamento(self):
        if self.config.has_section('IMPORTACAO_LISTA_PRECO'):
            for chave, ent in self.entradas_map.items():
                valor = self.config.get('IMPORTACAO_LISTA_PRECO', f'mapa_{chave}', fallback='')
                if valor:
                    ent.insert(0, valor)

    def _carregar_todas_configs(self):
        if not self.config.has_section('IMPORTACAO_LISTA_PRECO'):
            return
        cfg = self.config['IMPORTACAO_LISTA_PRECO']
        arquivo = cfg.get('ultimo_arquivo', '')
        if arquivo and os.path.isfile(arquivo):
            self.ent_arquivo.delete(0, tk.END)
            self.ent_arquivo.insert(0, arquivo)
            self.caminho_arquivo = arquivo
            abas = obter_abas_planilha(arquivo)
            self.cb_abas['values'] = abas
            aba = cfg.get('ultima_aba', '')
            if aba and aba in abas:
                self.cb_abas.set(aba)
            elif abas:
                self.cb_abas.current(0)
        self.ent_linha_ini.delete(0, tk.END)
        self.ent_linha_ini.insert(0, cfg.get('linha_inicial', '2'))
        modo = cfg.get('modo', '')
        if modo in ('EXISTENTE', 'NOVA'):
            self.var_modo.set(modo)
            self._toggle_modo()
        cod_lista = cfg.get('nova_lista_codigo', '')
        if cod_lista:
            self.ent_cod_lista.delete(0, tk.END)
            self.ent_cod_lista.insert(0, cod_lista)
        desc_lista = cfg.get('nova_lista_descricao', '')
        if desc_lista:
            self.ent_desc_lista.delete(0, tk.END)
            self.ent_desc_lista.insert(0, desc_lista)

    def _ler_rotulo_lista_salvo(self):
        if self.config.has_section('IMPORTACAO_LISTA_PRECO'):
            return self.config.get('IMPORTACAO_LISTA_PRECO', 'lista_selecionada', fallback='')
        return ''

    def _toggle_modo(self):
        if self.var_modo.get() == "NOVA":
            self.cb_listas.config_state(tk.DISABLED)
            self.ent_cod_lista.config(state=tk.NORMAL)
            self.ent_desc_lista.config(state=tk.NORMAL)
        else:
            self.cb_listas.config_state("readonly")
            self.ent_cod_lista.config(state=tk.DISABLED)
            self.ent_desc_lista.config(state=tk.DISABLED)

    def _carregar_listas_existentes(self, restaurar_rotulo=''):
        try:
            with FirebirdService(self.config_db) as fb:
                emp = int(self.config.get('IMPORTACAO', 'empresa', fallback='1'))
                fil = int(self.config.get('IMPORTACAO', 'filial', fallback='1'))
                sql = """
                    SELECT LIS_CODIGO, LIS_DESCRICAO, LIS_DATA
                    FROM TABELA_LISTA_PRECOS
                    WHERE LIS_EMPRESA = ? AND LIS_FILIAL = ?
                    ORDER BY LIS_CODIGO, LIS_DATA DESC
                """
                listas = fb.query(sql, [emp, fil])
                self.listas_existentes = []
                self.listas_info = {}
                bold_items = []
                cod_ja_visto = set()
                for lst in listas:
                    cod = str(lst.get('lis_codigo', '')).strip()
                    desc = str(lst.get('lis_descricao', '')).strip()
                    data = lst.get('lis_data', '')
                    rotulo = f"{cod} - {desc} ({data})"
                    if rotulo not in self.listas_existentes:
                        self.listas_existentes.append(rotulo)
                    if cod not in cod_ja_visto:
                        bold_items.append(rotulo)
                        cod_ja_visto.add(cod)
                    self.listas_info[rotulo] = {'codigo': cod, 'descricao': desc, 'data': data, 'serie': '1'}
                self.cb_listas.set_items(self.listas_existentes, bold_items=bold_items)
                if restaurar_rotulo and restaurar_rotulo in self.listas_existentes:
                    self.cb_listas.set(restaurar_rotulo)
                elif self.listas_existentes:
                    self.cb_listas.current(0)
        except Exception as e:
            print(f"Aviso: N\u00e3o foi poss\u00edvel carregar as listas de pre\u00e7os. {e}")

    def _selecionar_arquivo(self):
        path = filedialog.askopenfilename(filetypes=[("Arquivos Suportados", "*.xlsx *.csv"), ("Excel", "*.xlsx"), ("CSV", "*.csv")])
        if path:
            self.ent_arquivo.delete(0, tk.END)
            self.ent_arquivo.insert(0, path)
            self.caminho_arquivo = path
            abas = obter_abas_planilha(path)
            self.cb_abas['values'] = abas
            if abas:
                self.cb_abas.current(0)

    def _fechar_tela(self):
        self.destroy()
        if self.callback_voltar:
            self.callback_voltar()

    def _on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            if column == "#1":
                item_id = self.tree.identify_row(event.y)
                if not item_id:
                    return
                valores = list(self.tree.item(item_id, 'values'))
                if "ERRO" in valores[1]:
                    return
                valores[0] = "\u2611" if valores[0] == "\u2610" else "\u2610"
                self.tree.item(item_id, values=valores)

    def _on_tree_double_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            if column == "#7":
                item = self.tree.identify_row(event.y)
                if not item: return
                valores = list(self.tree.item(item, "values"))
                if "N\u00c3O ENCONTRADO" in valores[1]: return

                novo_preco = simpledialog.askstring(
                    "Editar Pre\u00e7o",
                    f"Informe o novo pre\u00e7o para:\n{valores[3]}",
                    initialvalue=valores[6]
                )
                if novo_preco is not None:
                    try:
                        preco_float = float(novo_preco.replace(',', '.'))
                        valores[6] = f"{preco_float:.2f}"
                        self.tree.item(item, values=valores)
                    except ValueError:
                        messagebox.showwarning("Erro", "Valor inv\u00e1lido. Use apenas n\u00fameros e ponto.")

    def _marcar_todos(self):
        for item in self.tree.get_children():
            v = list(self.tree.item(item, "values"))
            if "ERRO" not in v[1]:
                v[0] = "\u2611"
                self.tree.item(item, values=v)

    def _desmarcar_todos(self):
        for item in self.tree.get_children():
            v = list(self.tree.item(item, "values"))
            if "ERRO" not in v[1]:
                v[0] = "\u2610"
                self.tree.item(item, values=v)

    def _sort_treeview(self, col):
        self._sort_directions[col] = not self._sort_directions[col]
        reverse = self._sort_directions[col]
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]

        def valor_para_ordenar(val):
            v = str(val).strip()
            if not v or v == '-':
                return (1, '')
            try:
                return (0, float(v.replace(',', '.')))
            except ValueError:
                return (1, v.lower())

        l.sort(key=lambda t: valor_para_ordenar(t[0]), reverse=reverse)
        for index, (_, k) in enumerate(l):
            self.tree.move(k, '', index)
        for c in self.colunas:
            arrow = " \u25bc" if self._sort_directions[c] else " \u25b2" if c == col else " \u2195"
            self.tree.heading(c, text=c + arrow, command=lambda x=c: self._sort_treeview(x))

    # ==================== ANALISE ====================

    def _iniciar_analise(self):
        aba = self.cb_abas.get()
        try:
            linha_ini = int(self.ent_linha_ini.get())
        except ValueError:
            return messagebox.showerror("Erro", "A linha inicial deve ser um n\u00famero.")

        if not self.caminho_arquivo or not aba:
            return messagebox.showwarning("Aviso", "Selecione o arquivo e a aba antes de continuar.")

        mapa_colunas = {chave: ent.get().strip() for chave, ent in self.entradas_map.items()}
        if not mapa_colunas.get('codigo'):
            return messagebox.showwarning("Aviso", "Voc\u00ea precisa mapear a coluna 'C\u00f3digo Produto'.")
        if not mapa_colunas.get('preco'):
            return messagebox.showwarning("Aviso", "Voc\u00ea precisa mapear a coluna 'Pre\u00e7o'.")

        self._salvar_config_mapeamento()
        self.btn_analisar.config(state=tk.DISABLED)
        self.btn_importar.config(state=tk.DISABLED)
        self.btn_exportar.config(state=tk.DISABLED)
        self.lbl_status.config(text="Lendo planilha e consultando ERP...")
        self.progresso['value'] = 10

        self.tree.delete(*self.tree.get_children())

        threading.Thread(target=self._analisar_bg, args=(aba, mapa_colunas, linha_ini), daemon=True).start()

    def _analisar_bg(self, aba, mapa_colunas, linha_ini):
        try:
            self.parent.after(0, lambda: self.lbl_status.config(text="Lendo planilha..."))
            self.registros_lidos = ler_planilha_produtos(self.caminho_arquivo, aba, mapa_colunas, linha_ini)
            if not self.registros_lidos:
                self.parent.after(0, lambda: messagebox.showwarning("Aviso", "Nenhum registro encontrado na planilha."))
                self.parent.after(0, lambda: self.btn_analisar.config(state=tk.NORMAL))
                return

            self.parent.after(0, lambda: self.lbl_status.config(text=f"{len(self.registros_lidos)} registros lidos. Consultando ERP..."))
            self.parent.after(0, lambda: self.progresso.config(value=30))

            emp = int(self.config.get('IMPORTACAO', 'empresa', fallback='1'))
            fil = int(self.config.get('IMPORTACAO', 'filial', fallback='1'))

            # Mapas separados por tipo de código, para casar por prioridade
            # e mostrar POR QUAL campo o produto foi encontrado.
            map_codigo, map_import, map_aux, map_cbarra, map_desc = {}, {}, {}, {}, {}
            try:
                with FirebirdService(self.config_db) as fb:
                    rows = fb.query(
                        "SELECT PRODUTO_CODIGO, PRODUTO_COD_IMPORTACAO, PRODUTO_COD_AUXILIAR, "
                        "PRODUTO_DESCRICAO, PRODUTO_CBARRA "
                        "FROM TABELA_PRODUTO WHERE PRODUTO_EMPRESA = ? AND PRODUTO_FILIAL = ?",
                        [emp, fil]
                    )
                    for row in rows:
                        cod = str(row.get('produto_codigo', '') or '').strip()
                        imp = str(row.get('produto_cod_importacao', '') or '').strip()
                        aux = str(row.get('produto_cod_auxiliar', '') or '').strip()
                        desc = str(row.get('produto_descricao', '') or '').strip()
                        cb = str(row.get('produto_cbarra', '') or '').strip()
                        info = {'codigo': cod, 'descricao': desc}
                        if cod: map_codigo.setdefault(cod, info)
                        if imp: map_import.setdefault(imp, info)
                        if aux: map_aux.setdefault(aux, info)
                        if cb:  map_cbarra.setdefault(cb, info)
                        if desc: map_desc.setdefault(desc.lower(), info)
            except Exception as e:
                self.parent.after(0, lambda err=e: messagebox.showwarning("Erro DB", f"Falha ao consultar ERP:\n{err}"))
                self.parent.after(0, lambda: self.btn_analisar.config(state=tk.NORMAL))
                return

            self.parent.after(0, lambda: self.lbl_status.config(text="Processando e montando tabela..."))
            self.parent.after(0, lambda: self.progresso.config(value=50))

            self.dados_analisados = []
            total = len(self.registros_lidos)

            def match_produto(cod_planilha, desc_planilha):
                # Prioridade: código -> importação -> auxiliar -> cód. barras -> descrição exata
                for label, mapa in (
                    ("OK (código)", map_codigo),
                    ("OK (cód. importação)", map_import),
                    ("OK (cód. auxiliar)", map_aux),
                    ("OK (cód. barras)", map_cbarra),
                ):
                    info = mapa.get(cod_planilha)
                    if info:
                        return label, info['codigo'], info
                if desc_planilha:
                    info = map_desc.get(desc_planilha.lower())
                    if info:
                        return "OK (~desc)", info['codigo'], info
                return None, None, None

            for idx, reg in enumerate(self.registros_lidos):
                cod_planilha = str(reg.get('codigo', '')).strip()
                desc_planilha = str(reg.get('descricao', '')).strip()
                preco_str = str(reg.get('preco', '0')).strip()
                try:
                    preco = float(preco_str.replace(',', '.'))
                except ValueError:
                    preco = 0.0

                match_label, matched_cod, matched_info = match_produto(cod_planilha, desc_planilha)
                if match_label:
                    status = match_label
                    tag = "OK"
                    sel = "\u2611"
                    cod_erp = matched_info['codigo']
                    desc_erp = matched_info['descricao']
                else:
                    status = "N\u00c3O ENCONTRADO"
                    tag = "ERRO"
                    sel = "\u2610"
                    cod_erp = cod_planilha
                    desc_erp = "-"

                item = {
                    'sel': sel, 'status': status, 'tag': tag,
                    'cod_planilha': cod_planilha, 'desc_planilha': desc_planilha,
                    'cod_erp': cod_erp, 'desc_erp': desc_erp, 'preco': preco,
                }

                self.dados_analisados.append(item)
                if idx > 0 and idx % 100 == 0:
                    pct = 50 + int((idx / total) * 40)
                    self.parent.after(0, lambda i=idx, t=total, p=pct: (
                        self.lbl_status.config(text=f"Processando {i}/{t} produtos..."),
                        self.progresso.config(value=p)
                    ))

            self.parent.after(0, self._renderizar_preview)
        except Exception as e:
            self.parent.after(0, lambda err=e: messagebox.showerror("Erro", f"Falha na an\u00e1lise:\n{err}"))
            self.parent.after(0, lambda: self.btn_analisar.config(state=tk.NORMAL))

    def _renderizar_preview(self):
        # Selo deste render. A grade e preenchida em blocos com after(), entao um
        # render antigo pode continuar inserindo DEPOIS que outro limpou a tela —
        # a grade acumula duas analises e os totais somam tudo. O selo faz os
        # blocos do render antigo pararem.
        self._render_seq = getattr(self, '_render_seq', 0) + 1
        meu_seq = self._render_seq

        total = len(self.dados_analisados)
        if total == 0:
            self.btn_analisar.config(state=tk.NORMAL)
            self.lbl_status.config(text="Nenhum registro v\u00e1lido encontrado.")
            return

        self.lbl_status.config(text=f"Renderizando tabela com {total} produtos...")
        self.progresso['value'] = 92

        chunk_size = 30

        def render_chunk(start_idx):
            if meu_seq != self._render_seq:
                return  # um render mais novo assumiu a grade
            end_idx = min(start_idx + chunk_size, total)
            dados = self.dados_analisados
            for i in range(start_idx, end_idx):
                item = dados[i]
                self.tree.insert("", tk.END, values=(
                    item['sel'], item['status'], item['cod_planilha'],
                    item['desc_planilha'], item['cod_erp'],
                    item['desc_erp'], f"{item['preco']:.2f}"
                ), tags=(item['tag'],))

            if end_idx < total:
                self.lbl_status.config(text=f"Renderizando {end_idx}/{total}...")
                self.update_idletasks()
                self.parent.after(5, render_chunk, end_idx)
            else:
                self.btn_analisar.config(state=tk.NORMAL)
                ok_count = sum(1 for d in dados if d['tag'] == 'OK')
                if ok_count > 0:
                    self.btn_importar.config(state=tk.NORMAL)
                self.btn_exportar.config(state=tk.NORMAL)
                self.progresso['value'] = 100
                self.lbl_status.config(
                    text=f"Pronto. {ok_count} produtos encontrados no ERP de {total} lidos na planilha."
                )

        render_chunk(0)

    # ==================== EXPORTACAO ====================

    def _exportar_por_status(self):
        from tkinter import filedialog
        caminho = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile="PRODUTOS_POR_STATUS.txt",
            filetypes=[("Arquivo de Texto", "*.txt"), ("CSV", "*.csv")]
        )
        if not caminho:
            return

        dados = self.dados_analisados
        nao_encontrados = [d for d in dados if d['tag'] == 'ERRO']
        ok_desc = [d for d in dados if d['status'] == "OK (~desc)"]
        ok_exato = [d for d in dados if d['tag'] == 'OK' and d['status'] != "OK (~desc)"]

        linhas = []
        linhas.append("=" * 80)
        linhas.append("RELATORIO DE PRODUTOS POR STATUS - LISTA DE PRECOS")
        linhas.append("=" * 80)
        linhas.append("")
        linhas.append(f"Total de produtos na planilha: {len(dados)}")
        linhas.append(f"OK (match exato):           {len(ok_exato)}")
        linhas.append(f"OK (~desc) (aprox. desc.):  {len(ok_desc)}")
        linhas.append(f"Nao encontrados no ERP:     {len(nao_encontrados)}")
        linhas.append("")
        linhas.append("-" * 80)
        linhas.append("PRODUTOS NAO ENCONTRADOS NO ERP (precisa cadastrar primeiro)")
        linhas.append("-" * 80)
        if nao_encontrados:
            linhas.append(f"{'CODIGO':<15} {'DESCRICAO':<50} {'PRECO':<10}")
            linhas.append("-" * 80)
            for d in nao_encontrados:
                linhas.append(f"{d['cod_planilha']:<15} {d['desc_planilha']:<50} {d['preco']:<10.2f}")
        else:
            linhas.append("(nenhum)")
        linhas.append("")
        linhas.append("-" * 80)
        linhas.append("PRODUTOS OK (~desc) - MATCH APROXIMADO POR DESCRICAO")
        linhas.append("-" * 80)
        if ok_desc:
            linhas.append(f"{'COD PLANILHA':<15} {'DESC PLANILHA':<30} {'COD ERP':<15} {'DESC ERP':<30} {'PRECO':<10}")
            linhas.append("-" * 80)
            for d in ok_desc:
                linhas.append(f"{d['cod_planilha']:<15} {d['desc_planilha'][:28]:<30} {d['cod_erp']:<15} {d['desc_erp'][:28]:<30} {d['preco']:<10.2f}")
        else:
            linhas.append("(nenhum)")
        linhas.append("")
        linhas.append("-" * 80)
        linhas.append("PRODUTOS OK - MATCH EXATO")
        linhas.append("-" * 80)
        if ok_exato:
            linhas.append(f"{'COD PLANILHA':<15} {'DESC PLANILHA':<30} {'COD ERP':<15} {'DESC ERP':<30} {'PRECO':<10}")
            linhas.append("-" * 80)
            for d in ok_exato:
                linhas.append(f"{d['cod_planilha']:<15} {d['desc_planilha'][:28]:<30} {d['cod_erp']:<15} {d['desc_erp'][:28]:<30} {d['preco']:<10.2f}")
        else:
            linhas.append("(nenhum)")
        linhas.append("")
        linhas.append("=" * 80)

        try:
            with open(caminho, 'w', encoding='utf-8') as f:
                f.write('\n'.join(linhas))
            messagebox.showinfo("Exportado", f"Relat\u00f3rio salvo em:\n{caminho}")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao salvar:\n{e}")

    # ==================== IMPORTACAO ====================

    def _iniciar_importacao(self):
        modo = self.var_modo.get()

        if modo == "EXISTENTE":
            selecao = self.cb_listas.get()
            if not selecao:
                return messagebox.showwarning("Aten\u00e7\u00e3o", "Selecione uma lista existente.")
            info = self.listas_info.get(selecao)
            if not info:
                return messagebox.showerror("Erro", "Lista selecionada n\u00e3o encontrada.")
            lis_codigo = info['codigo']
            lis_descricao = info['descricao']
            lis_data = info['data']
            lis_serie = info['serie']
        else:
            lis_codigo = self.ent_cod_lista.get().strip()
            lis_descricao = self.ent_desc_lista.get().strip().upper()
            if not lis_codigo or not lis_codigo.isdigit():
                return messagebox.showwarning("Aten\u00e7\u00e3o", "Informe um C\u00f3digo num\u00e9rico v\u00e1lido para a Nova Lista.")
            if not lis_descricao:
                return messagebox.showwarning("Aten\u00e7\u00e3o", "Informe uma Descri\u00e7\u00e3o para a Nova Lista.")
            lis_data = datetime.date.today().isoformat()
            lis_serie = SERIE_PADRAO

        selecionados = []
        for item_id in self.tree.get_children():
            valores = self.tree.item(item_id, "values")
            if valores[0] == "\u2611" and "N\u00c3O ENCONTRADO" not in valores[1]:
                selecionados.append(valores)

        if not selecionados:
            return messagebox.showwarning("Aten\u00e7\u00e3o", "Nenhum produto v\u00e1lido marcado para importar.")

        resp = messagebox.askyesno(
            "Confirmar",
            f"Inserir/Atualizar {len(selecionados)} produtos na Lista de Pre\u00e7os {lis_codigo}?"
        )
        if not resp:
            return

        self.btn_importar.config(state=tk.DISABLED)
        self.btn_analisar.config(state=tk.DISABLED)
        self.lbl_status.config(text="Salvando no banco de dados...")

        threading.Thread(
            target=self._importacao_bg,
            args=(selecionados, lis_codigo, lis_descricao, lis_data, lis_serie),
            daemon=True
        ).start()

    def _importacao_bg(self, selecionados, lis_codigo, lis_descricao, lis_data, lis_serie='1'):
        try:
            emp = int(self.config.get('IMPORTACAO', 'empresa', fallback='1'))
            fil = int(self.config.get('IMPORTACAO', 'filial', fallback='1'))
            hoje = datetime.date.today().isoformat()
            inseridos = 0

            if not lis_data:
                lis_data = hoje

            with FirebirdService(self.config_db) as fb:
                cursor = None
                if hasattr(fb, 'conn'):
                    cursor = fb.conn.cursor()
                elif hasattr(fb, 'connection'):
                    cursor = fb.connection.cursor()

                sql = """
                    UPDATE OR INSERT INTO TABELA_LISTA_PRECOS (
                        LIS_EMPRESA, LIS_FILIAL, LIS_DATA, LIS_CODIGO,
                        LIS_PRODUTO_EMPRESA, LIS_PRODUTO_FILIAL, LIS_PRODUTO,
                        LIS_DESCRICAO, LIS_PRECO, LIS_DATA_ULT_ALTERACAO
                    ) VALUES (
                        ?, ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?
                    ) MATCHING (LIS_EMPRESA, LIS_FILIAL, LIS_CODIGO, LIS_DATA, LIS_PRODUTO)
                """

                total = len(selecionados)
                for idx, v in enumerate(selecionados):
                    cod_erp = v[4]
                    try:
                        preco = float(v[6])
                    except ValueError:
                        preco = 0.0

                    params = (
                        emp, fil, lis_data, int(lis_codigo),
                        emp, fil, cod_erp,
                        lis_descricao[:100], preco, hoje
                    )
                    if cursor:
                        cursor.execute(sql, params)
                    else:
                        fb.execute(sql, params)
                    inseridos += 1

                    if idx % 50 == 0:
                        self.parent.after(0, lambda i=idx, t=total: self.lbl_status.config(
                            text=f"Salvando {i+1}/{t} produtos..."
                        ))

                fb.conn.commit()

            self.parent.after(0, lambda: messagebox.showinfo(
                "Sucesso",
                f"Lista de pre\u00e7os atualizada!\n{inseridos} produtos inseridos/atualizados."
            ))
            self.parent.after(0, self._carregar_listas_existentes)

            log_str = f"--- LOG DE IMPORTACAO DE LISTA DE PRECOS VIA PLANILHA ---\n\n"
            log_str += f"Data: {hoje}\n"
            log_str += f"Lista: {lis_codigo} - {lis_descricao}\n"
            log_str += f"Total processado: {total}\n"
            log_str += f"Inseridos/Atualizados: {inseridos}\n\n"
            log_str += "--- DETALHES DOS PRODUTOS ---\n\n"
            for v in selecionados:
                log_str += f"C\u00f3d: {v[2]} | Desc: {v[3]} | C\u00f3d ERP: {v[4]} | Pre\u00e7o: {v[6]}\n"

            def _log_callback():
                resp = messagebox.askyesno("Log da Importa\u00e7\u00e3o",
                    "Deseja salvar um arquivo .txt com o log detalhado da importa\u00e7\u00e3o?")
                if resp:
                    caminho = filedialog.asksaveasfilename(
                        defaultextension=".txt",
                        initialfile="LOG_IMPORTACAO_LISTA_PRECOS.txt",
                        filetypes=[("Arquivos de Texto", "*.txt")]
                    )
                    if caminho:
                        try:
                            with open(caminho, 'w', encoding='utf-8') as f:
                                f.write(log_str)
                            messagebox.showinfo("Log Salvo", f"Arquivo salvo em:\n{caminho}")
                            if messagebox.askyesno("Abrir Log", "Deseja abrir o arquivo de log agora?"):
                                try:
                                    os.startfile(caminho)
                                except Exception as e:
                                    messagebox.showerror("Erro", f"Erro ao abrir arquivo:\n{e}")
                        except Exception as e:
                            messagebox.showerror("Erro", f"Erro ao salvar log:\n{e}")
            self.parent.after(500, _log_callback)

        except Exception as e:
            self.parent.after(0, lambda err=e: messagebox.showerror("Erro", f"Falha ao salvar no banco:\n{err}"))
        finally:
            self.parent.after(0, lambda: self.btn_analisar.config(state=tk.NORMAL))
            self.parent.after(0, lambda: self.btn_importar.config(state=tk.NORMAL))
            self.parent.after(0, lambda: self.lbl_status.config(text="Pronto."))

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import configparser
from utils import tema
from utils import tipo_cadastro
import utils.xml_reader as xml_reader
import utils.firebird_conn as fb
import re
import threading
import csv

class ToolTip(object):
    """Cria uma caixa de texto (tooltip) ao passar o mouse sobre o widget."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        self.id = None
        self.x = self.y = 0
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)
        self.widget.bind("<ButtonPress>", self.leave)

    def enter(self, event=None):
        self.schedule()

    def leave(self, event=None):
        self.unschedule()
        self.hidetip()

    def schedule(self):
        self.unschedule()
        self.id = self.widget.after(500, self.showtip)

    def unschedule(self):
        id = self.id
        self.id = None
        if id:
            self.widget.after_cancel(id)

    def showtip(self, event=None):
        if not self.widget.winfo_exists():
            return
        
        x = self.widget.winfo_rootx() + 25
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry("+%d+%d" % (x, y))
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                         background="#ffffe0", foreground="#1A1A1A", relief=tk.SOLID, borderwidth=1,
                         font=("Segoe UI", 9, "normal"), padx=5, pady=3)
        label.pack(ipadx=1)

    def hidetip(self):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()

class DialogoVincularCondPagto(tk.Toplevel):
    """Modal para o usuário decidir entre criar ou vincular condições de pagamento novas."""
    def __init__(self, parent, condicoes_novas, condicoes_existentes):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("Vincular Condições de Pagamento Novas")
        w = min(900, int(self.winfo_screenwidth() * 0.85))
        h = min(700, int(self.winfo_screenheight() * 0.8))
        self.geometry(f"{w}x{h}")
        self.minsize(640, 480)
        self.protocol("WM_DELETE_WINDOW", self._cancelar)

        self.condicoes_novas = sorted(condicoes_novas)
        self.condicoes_existentes = sorted(condicoes_existentes, key=lambda x: x[1]) # Sort by description
        self.mapeamento = {}
        self.mapeamento_final = None

        self._criar_widgets()
        self._popular_listas()
        tema.centralizar(self, w, h)

    def _criar_widgets(self):
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.rowconfigure(1, weight=3)
        main_frame.rowconfigure(2, weight=2)
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(2, weight=1)

        ttk.Label(main_frame, text="Condições Novas (do XML)", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, pady=5)
        ttk.Label(main_frame, text="Condições Existentes (no ERP)", font=("Segoe UI", 10, "bold")).grid(row=0, column=2, pady=5)

        frame_novas = ttk.Frame(main_frame)
        frame_novas.grid(row=1, column=0, sticky="nsew", padx=(0, 5))
        scroll_novas = ttk.Scrollbar(frame_novas, orient=tk.VERTICAL)
        self.list_novas = tk.Listbox(frame_novas, selectmode=tk.EXTENDED, yscrollcommand=scroll_novas.set)
        scroll_novas.config(command=self.list_novas.yview)
        scroll_novas.pack(side=tk.RIGHT, fill=tk.Y)
        self.list_novas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        frame_existentes = ttk.Frame(main_frame)
        frame_existentes.grid(row=1, column=2, sticky="nsew", padx=(5, 0))
        scroll_existentes = ttk.Scrollbar(frame_existentes, orient=tk.VERTICAL)
        self.list_existentes = tk.Listbox(frame_existentes, selectmode=tk.SINGLE, yscrollcommand=scroll_existentes.set)
        scroll_existentes.config(command=self.list_existentes.yview)
        scroll_existentes.pack(side=tk.RIGHT, fill=tk.Y)
        self.list_existentes.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        frame_botoes = ttk.Frame(main_frame)
        frame_botoes.grid(row=1, column=1, padx=10)
        ttk.Button(frame_botoes, text="Vincular →", command=self._vincular).pack(pady=5)
        ttk.Button(frame_botoes, text="Criar Nova →", command=self._marcar_para_criar).pack(pady=5)
        ttk.Button(frame_botoes, text="Ignorar (Em branco) →", command=self._marcar_para_ignorar).pack(pady=5)
        ttk.Button(frame_botoes, text="← Desfazer", command=self._desfazer).pack(pady=20)

        frame_preview = ttk.LabelFrame(main_frame, text="Mapeamento a ser Aplicado", padding=5)
        frame_preview.grid(row=2, column=0, columnspan=3, sticky="ew", pady=10)
        frame_preview.columnconfigure(0, weight=1)
        
        self.tree_preview = ttk.Treeview(frame_preview, columns=("Ação", "Vinculado a"), show="headings", height=5)
        self.tree_preview.heading("#0", text="Condição Nova (XML)")
        self.tree_preview.heading("Ação", text="Ação")
        self.tree_preview.heading("Vinculado a", text="Vinculado a (ID - Descrição)")
        self.tree_preview.column("#0", width=250)
        self.tree_preview.column("Ação", width=100, anchor=tk.CENTER)
        self.tree_preview.column("Vinculado a", width=350)
        self.tree_preview.pack(fill=tk.X, expand=True)

        frame_fim = ttk.Frame(self, padding=10)
        frame_fim.pack(fill=tk.X)
        ttk.Button(frame_fim, text="Cancelar", command=self._cancelar).pack(side=tk.LEFT)
        ttk.Button(frame_fim, text="Confirmar e Importar", command=self._confirmar, style="Accent.TButton").pack(side=tk.RIGHT)

    def _popular_listas(self):
        for item in self.condicoes_novas: self.list_novas.insert(tk.END, item)
        for cod, desc in self.condicoes_existentes: self.list_existentes.insert(tk.END, f"{cod} - {desc}")

    def _atualizar_preview(self):
        for i in self.tree_preview.get_children(): self.tree_preview.delete(i)
        for cond_nova, acao in sorted(self.mapeamento.items()):
            if acao == 'CRIAR':
                vinculado_a, acao_desc = "", "CRIAR NOVA"
            elif acao == 'IGNORAR':
                vinculado_a, acao_desc = "", "IGNORAR (EM BRANCO)"
            else:
                desc_vinculada = next((desc for cod, desc in self.condicoes_existentes if cod == acao), "N/A")
                vinculado_a, acao_desc = f"{acao} - {desc_vinculada}", "VINCULAR"
            self.tree_preview.insert("", tk.END, text=cond_nova, values=(acao_desc, vinculado_a))

    def _vincular(self):
        sel_novas_idx = self.list_novas.curselection()
        sel_existente_idx = self.list_existentes.curselection()
        if not sel_novas_idx or not sel_existente_idx: return messagebox.showwarning("Aviso", "Selecione itens em ambas as listas.", parent=self)
        cod_existente, _ = self.condicoes_existentes[sel_existente_idx[0]]
        for i in reversed(sel_novas_idx): self.mapeamento[self.list_novas.get(i)] = cod_existente; self.list_novas.delete(i)
        self._atualizar_preview()

    def _marcar_para_criar(self):
        sel_novas_idx = self.list_novas.curselection()
        if not sel_novas_idx: return messagebox.showwarning("Aviso", "Selecione uma condição para marcar para criação.", parent=self)
        for i in reversed(sel_novas_idx): self.mapeamento[self.list_novas.get(i)] = 'CRIAR'; self.list_novas.delete(i)
        self._atualizar_preview()

    def _marcar_para_ignorar(self):
        sel_novas_idx = self.list_novas.curselection()
        if not sel_novas_idx: return messagebox.showwarning("Aviso", "Selecione uma condição para ignorar.", parent=self)
        for i in reversed(sel_novas_idx): self.mapeamento[self.list_novas.get(i)] = 'IGNORAR'; self.list_novas.delete(i)
        self._atualizar_preview()

    def _desfazer(self):
        sel_preview = self.tree_preview.selection()
        if not sel_preview: return messagebox.showwarning("Aviso", "Selecione um mapeamento para desfazer.", parent=self)
        for item_id in sel_preview:
            cond_nova = self.tree_preview.item(item_id, 'text')
            if cond_nova in self.mapeamento: del self.mapeamento[cond_nova]; self.list_novas.insert(tk.END, cond_nova)
        self._atualizar_preview()

    def _confirmar(self):
        if self.list_novas.size() > 0:
            resposta = messagebox.askyesnocancel(
                "Atenção", 
                f"Ainda existem {self.list_novas.size()} condições de pagamento na lista sem mapeamento.\n\n"
                "• SIM: Para CRIAR essas condições no sistema.\n"
                "• NÃO: Para IGNORAR e deixá-las em branco no cadastro.\n"
                "• CANCELAR: Para voltar e revisar o mapeamento.", 
                parent=self
            )
            if resposta is True:
                for item in self.list_novas.get(0, tk.END): self.mapeamento[item] = 'CRIAR'
            elif resposta is False:
                for item in self.list_novas.get(0, tk.END): self.mapeamento[item] = 'IGNORAR'
            else:
                return
        self.mapeamento_final = self.mapeamento
        self.destroy()

    def _cancelar(self):
        self.mapeamento_final = None
        self.destroy()

class DialogoConciliacao(tk.Toplevel):
    def __init__(self, parent, dados_xml, dados_erp, empresa, filial):
        super().__init__(parent)
        self.title(f"Conciliação XML vs ERP — Empresa {empresa} Filial {filial}")
        w = min(1200, int(self.winfo_screenwidth() * 0.92))
        h = min(800, int(self.winfo_screenheight() * 0.85))
        self.geometry(f"{w}x{h}")
        self.minsize(640, 480)
        self.transient(parent)
        self.grab_set()

        self.dados_xml = dados_xml
        self.dados_erp = dados_erp

        self._criar_widgets()
        self._popular()
        tema.centralizar(self, w, h)

    def _criar_widgets(self):
        topo = ttk.Frame(self)
        topo.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(topo, text="Comparação dos dados do XML com o cadastro no ERP", font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)

        ttk.Button(topo, text="Fechar", command=self.destroy).pack(side=tk.RIGHT)

        cols = ("CAMPO", "XML", "ERP", "STATUS")
        frame_tree = ttk.Frame(self)
        frame_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.tree = ttk.Treeview(frame_tree, columns=cols, show="tree headings", height=20)
        self.tree.heading("#0", text="Cliente (CNPJ)")
        self.tree.heading("CAMPO", text="Campo")
        self.tree.heading("XML", text="Valor no XML")
        self.tree.heading("ERP", text="Valor no ERP")
        self.tree.heading("STATUS", text="Status")

        self.tree.column("#0", width=280, minwidth=200)
        self.tree.column("CAMPO", width=130, anchor=tk.CENTER)
        self.tree.column("XML", width=200)
        self.tree.column("ERP", width=200)
        self.tree.column("STATUS", width=80, anchor=tk.CENTER)

        self.tree.tag_configure('ok', foreground='#006400')
        self.tree.tag_configure('divergente', foreground='#CC3300')
        self.tree.tag_configure('novo', foreground='#005B96')
        self.tree.tag_configure('ausente', foreground='#996600')
        self.tree.tag_configure('campo_ok', foreground='#2E7D32')
        self.tree.tag_configure('campo_diff', foreground='#C62828')

        scroll = ttk.Scrollbar(frame_tree, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        legenda = ttk.Frame(self)
        legenda.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(legenda, text="✅ Ok", foreground='#006400').pack(side=tk.LEFT, padx=10)
        ttk.Label(legenda, text="⚠ Divergente", foreground='#CC3300').pack(side=tk.LEFT, padx=10)
        ttk.Label(legenda, text="🆕 Apenas no XML", foreground='#005B96').pack(side=tk.LEFT, padx=10)
        ttk.Label(legenda, text="❗ Apenas no ERP", foreground='#996600').pack(side=tk.LEFT, padx=10)
        ttk.Label(legenda, text=f"Total: {len(self.dados_xml)} XML(s) × {len(self.dados_erp)} ERP(s)").pack(side=tk.RIGHT)

    def _normalizar(self, val):
        if val is None: return ''
        s = str(val).strip().upper()
        s = re.sub(r'\s+', ' ', s)
        return s

    def _comparar_campos(self, val_xml, val_erp):
        return self._normalizar(val_xml) == self._normalizar(val_erp)

    def _popular(self):
        xml_por_doc = {}
        for d in self.dados_xml:
            reg = d['reg_completo']
            doc = re.sub(r'\D', '', str(reg.get('documento', '')))
            xml_por_doc[doc] = reg

        docs_erp = set(self.dados_erp.keys())
        docs_xml = set(xml_por_doc.keys())

        campos = [
            ('Razão Social', 'razao', 'razao'),
            ('Fantasia', 'fantasia', 'fantasia'),
            ('Insc. Estadual', 'ie', 'ie'),
            ('Endereço', 'endereco', 'endereco'),
            ('Número', 'nro_end', 'nro_end'),
            ('Bairro', 'bairro', 'bairro'),
            ('CEP', 'cep', 'cep'),
            ('Telefone', 'fone1', 'fone1'),
            ('E-mail', 'email', 'email'),
        ]

        # Clientes em ambos (comparação)
        for doc in sorted(docs_xml & docs_erp):
            reg = xml_por_doc[doc]
            erp = self.dados_erp[doc]
            doc_fmt = reg.get('documento_formatado', doc)

            divergencias = 0
            filhos = []
            for nome_campo, chave_xml, chave_erp in campos:
                v_xml = str(reg.get(chave_xml, ''))
                v_erp = str(erp.get(chave_erp, ''))
                igual = self._comparar_campos(v_xml, v_erp)
                if not igual:
                    divergencias += 1
                tag = 'campo_ok' if igual else 'campo_diff'
                status = '✓' if igual else '✗'
                filhos.append((nome_campo, v_xml, v_erp, status, tag))

            razao_xml = reg.get('razao', '')
            tag_pai = 'ok' if divergencias == 0 else 'divergente'
            status_pai = '✓ OK' if divergencias == 0 else f'⚠ {divergencias} divergência(s)'
            pai_id = self.tree.insert("", tk.END, text=f"{doc_fmt} — {razao_xml}", values=("", "", "", status_pai), tags=(tag_pai,), open=False)
            for nome_campo, v_xml, v_erp, status, tag in filhos:
                self.tree.insert(pai_id, tk.END, text="", values=(nome_campo, v_xml, v_erp, status), tags=(tag,))

        # Apenas no XML
        for doc in sorted(docs_xml - docs_erp):
            reg = xml_por_doc[doc]
            doc_fmt = reg.get('documento_formatado', doc)
            razao_xml = reg.get('razao', '')
            pai_id = self.tree.insert("", tk.END, text=f"{doc_fmt} — {razao_xml}", values=("", "", "", "🆕 NOVO"), tags=('novo',), open=False)
            for nome_campo, chave_xml, _ in campos:
                v_xml = str(reg.get(chave_xml, ''))
                self.tree.insert(pai_id, tk.END, text="", values=(nome_campo, v_xml, "—", "—"), tags=('novo',))

        # Apenas no ERP
        for doc in sorted(docs_erp - docs_xml):
            erp = self.dados_erp[doc]
            razao_erp = erp.get('razao', '')
            pai_id = self.tree.insert("", tk.END, text=f"{doc} — {razao_erp}", values=("", "", "", "❗ AUSENTE"), tags=('ausente',), open=False)
            for nome_campo, _, chave_erp in campos:
                v_erp = str(erp.get(chave_erp, ''))
                self.tree.insert(pai_id, tk.END, text="", values=(nome_campo, "—", v_erp, "—"), tags=('ausente',))

    def _ajustar_larguras(self):
        for col in ("#0", "CAMPO", "XML", "ERP", "STATUS"):
            max_w = self.tree.column(col, 'width')
            for item in self.tree.get_children():
                texto = self.tree.item(item, 'text') if col == '#0' else (self.tree.set(item, col) or '')
                w = self._estimar_largura(texto)
                if w > max_w: max_w = w
            self.tree.column(col, width=max_w + 15)

    def _estimar_largura(self, texto):
        return min(len(str(texto)) * 8, 400)


class TelaNFe(ttk.Frame):
    def __init__(self, parent, callback_voltar=None):
        super().__init__(parent, padding="10")
        self.parent = parent
        self.callback_voltar = callback_voltar
        self.pack(fill=tk.BOTH, expand=True)
        print("✅ Instância de TelaNFe criada.")

        self.xml_files = []
        self.dados_completos = []
        self.dados_nfe_lidos = {}
        self.colunas = ("SELECIONAR", "NF", "TIPO", "CNPJ/CPF", "RAZÃO SOCIAL", "CÓD. ANTIGO", "CONDIÇÃO PGTO", "CÓD. ERP", "STATUS")
        self.filtros_ativos = {'TIPO': set(), 'CONDIÇÃO PGTO': set(), 'STATUS': set()}
        self._sort_directions = {col: False for col in self.colunas}

        self.config = configparser.ConfigParser()
        self.config.read('config.ini', encoding='utf-8')

        self._criar_widgets()
        self._carregar_config_iniciais()

    def _criar_widgets(self):
        # === HEADER ===
        tema.montar_header(
            self, "Clientes/Fornecedores NF-e",
            "Importação automática de clientes e fornecedores via leitura de XML de NF-e 4.00"
        ).pack(fill=tk.X)

        # ===================== CORPO: menu lateral + conteúdo =====================
        corpo = tk.Frame(self, bg=tema.BG_BASE)
        corpo.pack(fill=tk.BOTH, expand=True)

        # -------- MENU LATERAL (padrão do main) --------
        self.sidebar = tema.montar_sidebar(corpo, tema.largura_sidebar(self))
        sidebar = self.sidebar

        # Rodapé do menu: Voltar
        rodape_sb = tk.Frame(sidebar, bg=tema.SIDEBAR_BG)
        rodape_sb.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 8))
        self.btn_voltar = tema.botao_sidebar(rodape_sb, "⎋   Voltar", self._fechar_tela)
        self.btn_voltar.pack(fill=tk.X)

        tema.titulo_sidebar(sidebar, "AÇÕES").pack(fill=tk.X, pady=(16, 4))

        self.btn_analisar = tema.botao_sidebar(sidebar, "🔍   LER XMLs", self._adicionar_xmls)
        self.btn_analisar.pack(fill=tk.X)

        self.btn_limpar = tema.botao_sidebar(sidebar, "🗑   Limpar", self._limpar_lista)
        self.btn_limpar.pack(fill=tk.X)

        self.btn_importar = tema.botao_sidebar(sidebar, "🚀   Importar Selecionados", self._importar_selecionados, cor_fg="#7EE0A0")
        self.btn_importar.config(state=tk.DISABLED)
        self.btn_importar.pack(fill=tk.X)

        # O menu tem largura fixa (pack_propagate(False)); se o maior rótulo pedir
        # mais, ele fica cortado. 'Importar Selecionados' pedia 211px num menu de
        # 210 — um pixel. Em vez de chutar outro número, o menu passa a caber o
        # maior botão, e continua assim se algum rótulo mudar.
        preciso = max(b.winfo_reqwidth()
                      for b in (self.btn_voltar, self.btn_analisar,
                                self.btn_limpar, self.btn_importar))
        if preciso > int(sidebar.cget('width')):
            sidebar.config(width=preciso)

        # -------- CONTEÚDO --------
        # A tela roda em console de servidor (1024x768 é comum). O padding de 16
        # de cada lado eram 32px roubados da grade; num monitor apertado isso é
        # uma coluna inteira.
        pad = 16 if self.winfo_screenwidth() >= 1300 else 6
        content = tk.Frame(corpo, bg=tema.BG_BASE)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=pad, pady=(8 if pad > 6 else 4))

        # === PARAMETERS BAR ===
        param_bar = ttk.Frame(content)
        param_bar.pack(fill=tk.X, pady=2)

        tk.Label(param_bar, text="Empresa:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 2))
        self.ent_empresa = ttk.Entry(param_bar, width=10, font=("Segoe UI", 9))
        self.ent_empresa.pack(side=tk.LEFT, padx=(0, 15))

        tk.Label(param_bar, text="Filial:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 2))
        self.ent_filial = ttk.Entry(param_bar, width=10, font=("Segoe UI", 9))
        self.ent_filial.pack(side=tk.LEFT)

        # === FILE SELECTION ===
        file_row = ttk.Frame(content)
        file_row.pack(fill=tk.X, pady=4)

        tk.Label(file_row, text="XMLs:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 2))
        # Os botões entram ANTES do campo, ancorados à direita: quem cede largura
        # é o caminho da pasta (que já tem tooltip e rola), não o botão. Com o
        # campo empacotado primeiro, uma janela estreita cortava o 'Arquivos'.
        self.btn_add_xml = ttk.Button(file_row, text="📄 Arquivos", command=self._selecionar_arquivos)
        self.btn_add_xml.pack(side=tk.RIGHT, padx=2)

        self.btn_add_pasta = ttk.Button(file_row, text="📁 Pasta", command=self._selecionar_pasta)
        self.btn_add_pasta.pack(side=tk.RIGHT, padx=2)

        self.ent_pasta = ttk.Entry(file_row, font=("Segoe UI", 9))
        self.ent_pasta.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        # === PROGRESS + TOTAL ===
        info_row = ttk.Frame(content)
        info_row.pack(fill=tk.X, pady=2)

        # mesma ordem do file_row: o texto do total é reservado primeiro e a
        # barra de progresso fica com o que sobrar
        self.lbl_total = ttk.Label(info_row, text="Total: 0 arquivo(s)",
                                   font=("Segoe UI", 10, "bold"), foreground="#14146E")
        self.lbl_total.pack(side=tk.RIGHT, padx=5)

        self.progresso = ttk.Progressbar(info_row, orient=tk.HORIZONTAL, mode='determinate')
        self.progresso.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 10))

        # === FILTERS BAR ===
        # BarraFluida: cada botão é uma célula do grid e o número de colunas é
        # recalculado no <Configure>. Numa janela estreita a barra quebra em duas
        # linhas em vez de jogar os últimos botões para fora da tela.
        filter_bar = tema.BarraFluida(content, "Filtros")
        filter_bar.pack(fill=tk.X, pady=4)
        for texto, cmd in (("Tipo", lambda: self._abrir_filtro('TIPO')),
                           ("Cond. Pgto.", lambda: self._abrir_filtro('CONDIÇÃO PGTO')),
                           ("Status", lambda: self._abrir_filtro('STATUS')),
                           ("✕ Limpar Filtros", self._limpar_filtros)):
            ttk.Button(filter_bar.grupo(), text=texto, command=cmd).pack()
        filter_bar.montar()

        # === TREEVIEW ===
        # grid em vez de pack: com as duas barras de rolagem no pack, a horizontal
        # empurrava a grade e a vertical ficava fora do canto.
        #
        # ORDEM DE EMPACOTAMENTO: a barra de ações e o log são criados aqui mas
        # empacotados ao rodapé ANTES da grade (ver o final deste método). No pack
        # do Tk quem é empacotado primeiro reserva o seu espaço; com a grade
        # primeiro, numa janela de 700px de altura o log era empurrado para fora
        # da tela — os botões voltavam, mas o log sumia.
        frame_grade = ttk.Frame(content)
        frame_grade.rowconfigure(0, weight=1)
        frame_grade.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(frame_grade, columns=self.colunas, show="headings")

        # TIPO precisa caber "Cliente e Fornecedor" — a coluna é clicável e alterna entre
        # os quatro tipos, então o texto não pode ficar cortado.
        larguras = [80, 80, 150, 140, 250, 80, 120, 80, 160]
        for col, larg in zip(self.colunas, larguras):
            self.tree.heading(col, text=col + " ↕", command=lambda c=col: self._sort_treeview(c))
            self.tree.column(col, width=larg, anchor=tk.CENTER if col != "RAZÃO SOCIAL" else tk.W)

        self.tree.tag_configure('NOVO', background='#EAFAF1')
        self.tree.tag_configure('CADASTRADO', background='#FADBD8')

        self.tree.bind("<ButtonRelease-1>", self._toggle_checkbox)

        scroll_y = ttk.Scrollbar(frame_grade, orient=tk.VERTICAL, command=self.tree.yview)
        # As 9 colunas somam ~1.140px. Sem barra horizontal, numa janela de 1024
        # as últimas (CÓD. ANTERIOR, CONDIÇÃO PGTO, STATUS) ficavam inalcançáveis
        # e sem nenhum sinal de que existiam.
        scroll_x = ttk.Scrollbar(frame_grade, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscroll=scroll_y.set, xscroll=scroll_x.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")

        # === ACTIONS BAR ===
        # Era aqui que a tela quebrava: 6 controles com side=LEFT numa linha só,
        # e em 1024px o 'Aplicar aos ☑' e o checkbox de condição de pagamento
        # saíam pela direita, sem scroll e sem pista de que estavam lá.
        actions_row = tema.BarraFluida(content, "Ações da lista")

        ttk.Button(actions_row.grupo(), text="☑ Marcar Novos",
                   command=self._marcar_novos).pack()
        ttk.Button(actions_row.grupo(), text="☐ Desmarcar Todos",
                   command=self._desmarcar_todos).pack()
        btn_rem_consumidor = ttk.Button(actions_row.grupo(), text="🧹 Remover Consumidor",
                                        command=self._remover_consumidor)
        btn_rem_consumidor.pack()
        ToolTip(btn_rem_consumidor, "Remove da lista os registros cuja Razão Social seja\n'CONSUMIDOR', 'CONSUMIDOR FINAL', etc. (comum em NFC-e).")
        ttk.Button(actions_row.grupo(), text="📊 Conciliação",
                   command=self._abrir_conciliacao).pack()

        # Tipo + Aplicar andam juntos: são um controle só, não podem cair em
        # linhas diferentes.
        g_tipo = actions_row.grupo()
        tema.rotulo_campo(g_tipo, "Tipo:").pack(side=tk.LEFT, padx=(0, 4))
        self.cb_tipo_lote = ttk.Combobox(g_tipo, values=tipo_cadastro.TIPOS,
                                         state="readonly", width=20, font=("Segoe UI", 9))
        self.cb_tipo_lote.set(tipo_cadastro.CLIENTE)
        self.cb_tipo_lote.pack(side=tk.LEFT)
        btn_tipo = ttk.Button(g_tipo, text="Aplicar aos ☑", command=self._aplicar_tipo_marcados)
        btn_tipo.pack(side=tk.LEFT, padx=(4, 0))
        ToolTip(btn_tipo, "Define cliente / fornecedor / os dois / outros nos registros marcados.\n"
                          "Também dá para clicar direto na coluna TIPO de uma linha para alternar.")

        self.var_auto_criar_cond_pagto = tk.BooleanVar(self, value=True)
        chk_auto = ttk.Checkbutton(actions_row.grupo(), text="Criar Cond. Pgto. Automaticamente",
                                   variable=self.var_auto_criar_cond_pagto,
                                   onvalue=True, offvalue=False)
        chk_auto.pack()
        ToolTip(chk_auto, "Se marcado: Cria condições de pagamento inexistentes automaticamente no banco.\nSe desmarcado: Abre janela para vincular as condições do XML com as já existentes.")
        actions_row.montar()

        # === LOG ===
        log_frame = ttk.LabelFrame(content, text="Log de Importação", padding="5")
        self.txt_log = tk.Text(log_frame, height=5, state=tk.DISABLED, bg="#F9F9F9",
                               font=("Segoe UI", 9))
        self.txt_log.pack(fill=tk.X)

        # Rodapé primeiro (de baixo para cima), grade por último: assim o log e os
        # botões têm a sua altura garantida e é a GRADE que encolhe.
        log_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(4, 0))
        actions_row.pack(side=tk.BOTTOM, fill=tk.X, pady=4)
        frame_grade.pack(fill=tk.BOTH, expand=True, pady=4)
        # O log fixo em 5 linhas comia a grade quando a janela encurtava; quem
        # está conferindo a lista quer ver linhas, não área de log vazia.
        self.bind("<Configure>", self._ajustar_layout)

    def _ajustar_layout(self, _evt=None):
        """Ajusta ao tamanho da JANELA: altura do log e largura do menu.

        Chamado a cada <Configure>, então só escreve quando o alvo muda — do
        contrário cada reconfiguração dispara outro <Configure> e o Tk entra em
        laço.
        """
        if not self.winfo_exists():
            return
        h, w = self.winfo_height(), self.winfo_width()
        alvo_log = 2 if h < 720 else (3 if h < 900 else 5)
        if getattr(self, '_altura_log', None) != alvo_log:
            self._altura_log = alvo_log
            self.txt_log.config(height=alvo_log)
        # O menu NÃO encolhe com a janela: a 168px o rótulo "Importar Selecionados"
        # ficava cortado — troquei 42px de grade por um botão ilegível. Os 210px
        # são a largura de que o maior rótulo precisa.
        del w

    def _toggle_checkbox(self, event):
        """Inverte o valor do checkbox se o usuário clicar na primeira coluna."""
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            item = self.tree.identify_row(event.y)
            if not item: return

            if column == "#1": # Coluna 'SELECIONAR'
                valores = list(self.tree.item(item, "values"))
                novo_valor = "☑" if valores[0] == "☐" else "☐"
                valores[0] = novo_valor
                self.tree.item(item, values=valores)

                reg_completo = self.dados_nfe_lidos.get(item)
                for r in self.dados_completos:
                    if r['reg_completo'] == reg_completo:
                        r['valores'][0] = novo_valor
                        break

            elif column == "#3": # Coluna 'TIPO'
                valores = list(self.tree.item(item, "values"))
                self._definir_tipo(item, tipo_cadastro.proximo(valores[2]))

    def _definir_tipo(self, item, novo_tipo):
        """Grava o tipo do cadastro na linha, no registro e na lista completa.

        O tipo tem de viver no `reg_completo`: é ele que a importação lê, e é dele
        que `_renderizar_tabela` reconstrói a grade depois de um filtro — só na
        célula, a escolha se perderia no próximo filtro.
        """
        valores = list(self.tree.item(item, "values"))
        valores[2] = novo_tipo
        self.tree.item(item, values=valores)

        reg_completo = self.dados_nfe_lidos.get(item)
        if reg_completo is not None:
            reg_completo['tipo'] = novo_tipo
        for r in self.dados_completos:
            if r['reg_completo'] == reg_completo:
                r['valores'][2] = novo_tipo
                break

    def _aplicar_tipo_marcados(self):
        """Aplica o tipo escolhido no combo às linhas marcadas com ☑ e ainda NOVAS."""
        novo_tipo = self.cb_tipo_lote.get()
        alterados = 0
        for item in self.tree.get_children():
            valores = list(self.tree.item(item, "values"))
            if valores[0] == "☑" and "NOVO" in valores[-1]:
                self._definir_tipo(item, novo_tipo)
                alterados += 1
        if alterados == 0:
            messagebox.showinfo("Nada a alterar",
                                "Nenhum registro NOVO está marcado com ☑.\n"
                                "O tipo só vale para quem ainda vai ser cadastrado.")
        else:
            self.lbl_total.config(text=f"{alterados} registro(s) → {novo_tipo}")

    def _marcar_novos(self):
        """Marca todos os que estão com status NOVO."""
        for item in self.tree.get_children():
            valores = list(self.tree.item(item, "values"))
            if "NOVO" in valores[-1]:
                valores[0] = "☑"
            self.tree.item(item, values=valores)
        for r in self.dados_completos:
            if "NOVO" in r['valores'][-1]:
                r['valores'][0] = "☑"
        self._renderizar_tabela()

    def _desmarcar_todos(self):
        """Desmarca todos os registros da grade."""
        for r in self.dados_completos:
            r['valores'][0] = "☐"
        self._renderizar_tabela()

    def _remover_consumidor(self):
        """Remove da lista os registros genéricos de 'CONSUMIDOR' (comum em NFC-e)."""
        if not self.dados_completos:
            return messagebox.showwarning("Aviso", "Leia os XMLs primeiro.")

        # Casa 'CONSUMIDOR', 'CONSUMIDOR FINAL', 'CONSUMIDOR NAO IDENTIFICADO', etc.
        padrao = re.compile(r'\bCONSUMIDOR(ES)?\b', re.IGNORECASE)
        antes = len(self.dados_completos)
        self.dados_completos = [
            r for r in self.dados_completos
            if not padrao.search(str(r['valores'][4]))  # índice 4 = RAZÃO SOCIAL
        ]
        removidos = antes - len(self.dados_completos)

        self._renderizar_tabela()

        if not any(r['tag'] == 'NOVO' for r in self.dados_completos):
            self.btn_importar.config(state=tk.DISABLED)

        messagebox.showinfo(
            "Remover Consumidor",
            f"{removidos} registro(s) de 'CONSUMIDOR' removido(s) da lista." if removidos
            else "Nenhum registro de 'CONSUMIDOR' encontrado na lista."
        )

    def _limpar_filtros(self):
        for k in self.filtros_ativos:
            self.filtros_ativos[k] = set()
        self._renderizar_tabela()

    def _renderizar_tabela(self):
        for item in self.tree.get_children():
            valores = list(self.tree.item(item, "values"))
            valores[0] = "☐"
            self.tree.item(item, values=valores)
            self.tree.delete(item)

        self.dados_nfe_lidos = {}
        linhas_filtradas = []
        for r in self.dados_completos:
            tipo = str(r['valores'][2])
            cond_pgto = str(r['valores'][6])
            status = str(r['valores'][8])

            if self.filtros_ativos.get('TIPO') and tipo not in self.filtros_ativos['TIPO']: continue
            if self.filtros_ativos.get('CONDIÇÃO PGTO') and cond_pgto not in self.filtros_ativos['CONDIÇÃO PGTO']: continue
            if self.filtros_ativos.get('STATUS') and status not in self.filtros_ativos['STATUS']: continue

            linhas_filtradas.append(r)

        for r in linhas_filtradas:
            item_id = self.tree.insert("", tk.END, values=r['valores'], tags=(r['tag'],))
            self.dados_nfe_lidos[item_id] = r['reg_completo']

        for col in self.colunas:
            self.tree.heading(col, text=col + " ↕", command=lambda c=col: self._sort_treeview(c))
            self._sort_directions[col] = False

    def _abrir_filtro(self, coluna):
        if not self.dados_completos: 
            return messagebox.showwarning("Aviso", "Leia os XMLs primeiro.")
        
        idx = self.colunas.index(coluna)
        valores_unicos = sorted(list(set(str(r['valores'][idx]) for r in self.dados_completos)))
        
        top = tk.Toplevel(self)
        top.title(f"Filtrar por {coluna}")
        w = min(400, int(self.winfo_screenwidth() * 0.4))
        h = min(500, int(self.winfo_screenheight() * 0.6))
        top.minsize(300, 300)
        top.transient(self.winfo_toplevel())
        tema.centralizar(top, w, h)
        top.grab_set()

        frame_search = ttk.Frame(top)
        frame_search.pack(fill=tk.X, padx=10, pady=(10, 0))
        ttk.Label(frame_search, text="Buscar:").pack(side=tk.LEFT)
        ent_search = ttk.Entry(frame_search)
        ent_search.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        frame_list = ttk.Frame(top)
        frame_list.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        scrollbar = ttk.Scrollbar(frame_list)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        lb = tk.Listbox(frame_list, selectmode=tk.MULTIPLE, yscrollcommand=scrollbar.set)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=lb.yview)

        for val in valores_unicos:
            lb.insert(tk.END, val)
            if not self.filtros_ativos[coluna] or val in self.filtros_ativos[coluna]:
                lb.selection_set(tk.END)

        def on_search(event):
            texto = ent_search.get().lower()
            if not texto: return
            items = lb.get(0, tk.END)
            for i, val in enumerate(items):
                if texto in val.lower():
                    lb.see(i)
                    break
        ent_search.bind("<KeyRelease>", on_search)

        def aplicar():
            selecionados = [lb.get(i) for i in lb.curselection()]
            if len(selecionados) == len(valores_unicos) or not selecionados:
                self.filtros_ativos[coluna] = set()
            else:
                self.filtros_ativos[coluna] = set(selecionados)
            self._renderizar_tabela()
            top.destroy()

        def marcar_todos():
            lb.selection_set(0, tk.END)

        def desmarcar_todos():
            lb.selection_clear(0, tk.END)

        frame_btn = ttk.Frame(top)
        frame_btn.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(frame_btn, text="☑ Todos", command=marcar_todos).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_btn, text="☐ Nenhum", command=desmarcar_todos).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_btn, text="Aplicar Filtro", command=aplicar).pack(side=tk.RIGHT, padx=2)

    def _sort_treeview(self, col):
        self._sort_directions[col] = not self._sort_directions[col]
        reverse = self._sort_directions[col]
        
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        
        def valor_para_ordenar(val):
            v = str(val).replace('%', '').strip()
            if not v or v == '-':
                return -999999 if reverse else 999999
            try:
                return float(v)
            except ValueError:
                return v.lower()
                
        l.sort(key=lambda t: valor_para_ordenar(t[0]), reverse=reverse)
        
        for index, (_, k) in enumerate(l):
            self.tree.move(k, '', index)
            
        for c in self.colunas:
            if c == col:
                arrow = " ▼" if self._sort_directions[c] else " ▲"
            else:
                arrow = " ↕"
            self.tree.heading(c, text=c + arrow, command=lambda x=c: self._sort_treeview(x))

    def _aplicar_mascara_cpf_cnpj(self, documento: str) -> str:
        doc = ''.join(filter(str.isdigit, str(documento)))
        if len(doc) == 11:
            return f"{doc[:3]}.{doc[3:6]}.{doc[6:9]}-{doc[9:]}"
        elif len(doc) == 14:
            return f"{doc[:2]}.{doc[2:5]}.{doc[5:8]}/{doc[8:12]}-{doc[12:]}"
        return documento

    def _carregar_config_iniciais(self):
        # Puxa do módulo NF-e, mas se não existir, pega do que foi usado no Plano de Contas
        empresa = self.config.get('NFE', 'empresa', fallback=self.config.get('IMPORTACAO', 'empresa', fallback='1'))
        filial = self.config.get('NFE', 'filial', fallback=self.config.get('IMPORTACAO', 'filial', fallback='1'))
        self.ent_empresa.insert(0, empresa)
        self.ent_filial.insert(0, filial)

    def _salvar_config(self):
        config = configparser.ConfigParser()
        config.read('config.ini', encoding='utf-8')
        if not config.has_section('NFE'):
            config.add_section('NFE')
        config.set('NFE', 'empresa', self.ent_empresa.get())
        config.set('NFE', 'filial', self.ent_filial.get())
        with open('config.ini', 'w', encoding='utf-8') as f:
            config.write(f)
        self.config = config

    def _selecionar_pasta(self):
        pasta = filedialog.askdirectory()
        if pasta:
            self.ent_pasta.delete(0, tk.END)
            self.ent_pasta.insert(0, pasta)
            self.pasta_xmls = pasta
            self.arquivos_selecionados = []

    def _selecionar_arquivos(self):
        arquivos = filedialog.askopenfilenames(filetypes=[("Arquivos XML", "*.xml")])
        if arquivos:
            self.ent_pasta.delete(0, tk.END)
            self.ent_pasta.insert(0, f"{len(arquivos)} arquivo(s) selecionado(s)")
            self.arquivos_selecionados = list(arquivos)
            self.pasta_xmls = ""

    def _adicionar_xmls(self):
        if not hasattr(self, 'pasta_xmls'): self.pasta_xmls = ""
        if not hasattr(self, 'arquivos_selecionados'): self.arquivos_selecionados = []
            
        arquivos = []
        if self.arquivos_selecionados:
            arquivos = self.arquivos_selecionados
        elif self.pasta_xmls:
            import glob
            import os
            pattern = os.path.join(self.pasta_xmls, '**', '*.xml')
            arquivos = glob.glob(pattern, recursive=True)
            
        if not arquivos:
            messagebox.showwarning("Atenção", "Selecione uma pasta ou arquivos XML válidos.")
            return
            
        try:
            emp = int(self.ent_empresa.get())
            fil = int(self.ent_filial.get())
        except ValueError:
            messagebox.showerror("Erro", "Os campos Empresa e Filial devem ser numéricos.")
            return
        
        self._salvar_config()
        self._estado_botoes(tk.DISABLED)

        # Lê os CNPJs que já estão na grade para não duplicar
        documentos_existentes = set()
        for item in self.tree.get_children():
            doc = self.tree.item(item, "values")[3] # Índice 3 é a coluna CNPJ/CPF
            doc_limpo = re.sub(r'\D', '', doc)
            documentos_existentes.add(doc_limpo)
        
        self.progresso['value'] = 0
        self.lbl_total.config(text="Iniciando leitura...")

        # Executa o processamento pesado em background
        thread = threading.Thread(
            target=self._processar_arquivos_bg,
            args=(arquivos, emp, fil, documentos_existentes),
            daemon=True
        )
        thread.start()

    def _processar_arquivos_bg(self, arquivos, emp, fil, documentos_existentes):
        conn = None
        try:
            conn = fb.conectar()
            clientes_db = fb.buscar_clientes_existentes(conn, emp, fil)
        except Exception as e:
            self.parent.after(0, lambda e=e: messagebox.showerror("Erro de Banco", f"Falha ao checar cadastros no Firebird:\n{e}"))
            self.parent.after(0, self._finalizar_carregamento_erro)
            return
        finally:
            if conn:
                conn.close()

        resultados = []
        erros_leitura = []
        total = len(arquivos)

        for i, arq in enumerate(arquivos):
            nome_arq = arq.split('/')[-1]
            try:
                dados_xml = xml_reader.ler_nfe(arq)
                for reg in dados_xml:
                    try:
                        doc_limpo = str(reg.get('documento') or '').strip()
                        
                        if not doc_limpo or doc_limpo in documentos_existentes:
                            continue # Ignora duplicações ou XMLs sem CNPJ/CPF
                            
                        documentos_existentes.add(doc_limpo)
                        
                        # Extrair código antigo da Razão Social (Aceita "123 - Nome" ou "123-Nome")
                        razao_limpa = str(reg.get('razao') or '').strip()
                        match = re.match(r'^(\d+)\s*[-–]\s*(.+)$', razao_limpa)
                        if match:
                            reg['cf_cod_antigo'] = match.group(1)
                            reg['razao'] = match.group(2).strip()
                        else:
                            reg['cf_cod_antigo'] = None

                        if doc_limpo in clientes_db:
                            status, check, tag = "JÁ CADASTRADO", "☐", "CADASTRADO"
                            cod_erp = clientes_db[doc_limpo]
                        else:
                            status, check, tag = "NOVO - IMPORTAR", "☑", "NOVO"
                            cod_erp = "-"
                            
                        cond_pagto_desc = reg.get('condicao_pagamento_desc', 'N/I')
                        documento_formatado = reg.get('documento_formatado')
                        if not documento_formatado:
                            documento_formatado = self._aplicar_mascara_cpf_cnpj(doc_limpo)
                            reg['documento_formatado'] = documento_formatado
                        resultados.append({
                            'check': check, 'tipo': reg.get('tipo', 'XML NF-e'), 'documento': doc_limpo,
                            'documento_formatado': documento_formatado,
                            'razao': reg.get('razao', ''), 'status': status, 'tag': tag,
                            'cod_erp': cod_erp,
                            'cond_pagto_desc': cond_pagto_desc,
                            'reg_completo': reg
                        })
                    except Exception as e_reg:
                        erros_leitura.append(f"⚠️ Aviso no cliente do arquivo {nome_arq}: {e_reg}")
            except Exception as e:
                erros_leitura.append(f"❌ Falha ao ler XML {nome_arq}: {e}")
                
            # Atualiza a barra de progresso no frontend de forma segura (a cada 15 arquivos ou no último)
            if i % 15 == 0 or i == total - 1:
                self.parent.after(0, self._atualizar_progresso, i + 1, total)

        # Devolve o resultado processado para a thread principal construir a árvore
        self.parent.after(0, self._finalizar_carregamento, arquivos, resultados, erros_leitura)

    def _atualizar_progresso(self, atual, total):
        percent = (atual / total) * 100
        self.progresso['value'] = percent
        self.lbl_total.config(text=f"Lendo: {atual}/{total} ({percent:.1f}%)")

    def _finalizar_carregamento_erro(self):
        self.lbl_total.config(text=f"Total: {len(self.xml_files)} arquivo(s)")
        self.progresso['value'] = 0
        self._estado_botoes(tk.NORMAL)

    def _finalizar_carregamento(self, novos_arquivos, resultados, erros_leitura=None):
        # Impede a thread órfã de injetar dados numa interface já destruída
        if not self.winfo_exists(): return
        
        self.xml_files.extend(novos_arquivos)
        
        if not hasattr(self, 'dados_nfe_lidos'):
            self.dados_nfe_lidos = {}

        for res in resultados:
            doc_formatado = res.get('documento_formatado', self._aplicar_mascara_cpf_cnpj(res['documento']))
            cod_ant = res['reg_completo'].get('cf_cod_antigo') or "-"
            cond_pgto = res.get('cond_pagto_desc', 'N/I')
            item_id = self.tree.insert("", tk.END, values=(res['check'], "XML NF-e", res['tipo'], doc_formatado, res['razao'], cod_ant, cond_pgto, res.get('cod_erp', '-'), res['status']), tags=(res['tag'],))
            self.dados_nfe_lidos[item_id] = res['reg_completo']
            linha = [res['check'], "XML NF-e", res['tipo'], doc_formatado, res['razao'], cod_ant, cond_pgto, res.get('cod_erp', '-'), res['status']]
            self.dados_completos.append({
                'valores': linha,
                'tag': res['tag'],
                'reg_completo': res['reg_completo']
            })

        self._limpar_filtros()

        self.lbl_total.config(text=f"Total: {len(self.xml_files)} arquivo(s)")
        self.progresso['value'] = 0
        self._estado_botoes(tk.NORMAL)
        
        if erros_leitura:
            self.txt_log.config(state=tk.NORMAL)
            for erro in erros_leitura:
                self.txt_log.insert(tk.END, f"{erro}\n")
            self.txt_log.config(state=tk.DISABLED)
            self.txt_log.see(tk.END)

        if any(r['tag'] == 'NOVO' for r in resultados):
            self.btn_importar.config(state=tk.NORMAL)
            
    def _estado_botoes(self, estado):
        self.btn_add_xml.config(state=estado)
        self.btn_add_pasta.config(state=estado)
        self.btn_analisar.config(state=estado)
        self.btn_limpar.config(state=estado)

    def _limpar_lista(self):
        self.xml_files = []
        self.dados_completos = []
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.lbl_total.config(text="Total: 0 arquivo(s)")

    def _fechar_tela(self):
        print("❌ Instância de TelaNFe destruída.")
        self.destroy()
        if self.callback_voltar:
            self.callback_voltar()

    def _abrir_conciliacao(self):
        if not self.dados_completos:
            messagebox.showwarning("Aviso", "Leia os XMLs primeiro.")
            return
        try:
            emp = int(self.ent_empresa.get())
            fil = int(self.ent_filial.get())
        except ValueError:
            messagebox.showerror("Erro", "Empresa e Filial devem ser numéricos.")
            return

        conn = None
        try:
            conn = fb.conectar()
            dados_erp = fb.buscar_dados_completos_clientes(conn, emp, fil)
        except Exception as e:
            messagebox.showerror("Erro de Banco", f"Falha ao buscar dados do ERP:\n{e}")
            return
        finally:
            if conn: conn.close()

        DialogoConciliacao(self, self.dados_completos, dados_erp, emp, fil)

    def _importar_selecionados(self):
        selecionados = []
        # Filtra apenas os que estão marcados com o "☑"
        for item in self.tree.get_children():
            valores = list(self.tree.item(item, "values"))
            if valores[0] == "☑" and "NOVO" in valores[-1]:
                selecionados.append((item, valores))

        if not selecionados:
            messagebox.showwarning("Aviso", "Nenhum registro NOVO foi selecionado para importação.")
            return

        emp = int(self.ent_empresa.get())
        fil = int(self.ent_filial.get())

        try:
            conn = fb.conectar()
        except Exception as e:
            messagebox.showerror("Erro de Banco", f"Falha ao conectar no Firebird:\n{e}")
            return

        mapeamento_condicoes = {}
        condicoes_existentes_tuplas = []
        auto_criar = self.var_auto_criar_cond_pagto.get()
        
        if not auto_criar:
            condicoes_xml = set(v[6] for item, v in selecionados if v[6] != 'N/I')
            
            conn_temp = None
            try:
                conn_temp = fb.conectar()
                condicoes_existentes_tuplas = fb.listar_condicoes_pagamento(conn_temp)
                condicoes_existentes_desc = {desc.strip().upper() for _, desc in condicoes_existentes_tuplas}
                
                condicoes_novas_desc = [desc for desc in condicoes_xml if desc.strip().upper() not in condicoes_existentes_desc]
                
                if condicoes_novas_desc:
                    dialog = DialogoVincularCondPagto(self, condicoes_novas_desc, condicoes_existentes_tuplas)
                    self.wait_window(dialog)
                    
                    if dialog.mapeamento_final is not None:
                        mapeamento_condicoes = dialog.mapeamento_final
                    else:
                        messagebox.showinfo("Cancelado", "Importação cancelada pelo usuário.")
                        return
                elif condicoes_xml:
                    self.txt_log.config(state=tk.NORMAL)
                    self.txt_log.insert(tk.END, "\nℹ️ Todas as condições do XML já existem no ERP. Pulando janela de mapeamento manual.\n")
                    self.txt_log.see(tk.END)
                    self.txt_log.config(state=tk.DISABLED)
            finally:
                if conn_temp: conn_temp.close()

        self.txt_log.config(state=tk.NORMAL)
        self.txt_log.insert(tk.END, "\n" + "="*45 + "\n")
        self.txt_log.insert(tk.END, f"⚙️ Criar condições automáticas: {'SIM' if auto_criar else 'NÃO'}\n")
        self.txt_log.see(tk.END)

        try:
            registros_para_inserir = []
            
            for item, valores in selecionados:
                reg = self.dados_nfe_lidos[item]
                
                # Busca o código interno da cidade na TABELA_CIDADES usando o IBGE
                cid_codigo = fb.buscar_cidade_ibge(conn, reg.get('cidade_ibge', ''), emp, fil)
                if not cid_codigo:
                    self.txt_log.insert(tk.END, f"⚠️ Aviso: Cidade IBGE {reg.get('cidade_ibge')} não encontrada para {reg['razao']}. Ficará em branco.\n")
                
                cond_pagto_id = None
                desc_cond = reg.get('condicao_pagamento_desc', 'N/I')
                duplicatas = reg.get('condicao_pagamento', [])

                if desc_cond != 'N/I' and duplicatas:
                    try:
                        if not auto_criar:
                            if desc_cond in mapeamento_condicoes:
                                acao = mapeamento_condicoes.get(desc_cond)
                                if acao == 'CRIAR': cond_pagto_id = fb.buscar_ou_criar_condicao_pgto(conn, duplicatas, desc_cond); self.txt_log.insert(tk.END, f"💰 Nova condição '{desc_cond}' criada com ID {cond_pagto_id}.\n")
                                elif acao == 'IGNORAR':
                                    cond_pagto_id = None
                                    self.txt_log.insert(tk.END, f"💰 Condição '{desc_cond}' ignorada (ficará em branco).\n")
                                else: cond_pagto_id = int(acao); self.txt_log.insert(tk.END, f"💰 Condição '{desc_cond}' vinculada ao ID {cond_pagto_id}.\n")
                            else:
                                cond_pagto_id = next((cod for cod, d in condicoes_existentes_tuplas if d.strip().upper() == desc_cond.strip().upper()), None)
                                if cond_pagto_id: self.txt_log.insert(tk.END, f"💰 Condição '{desc_cond}' já existente vinculada ao ID {cond_pagto_id}.\n")
                        else:
                            cond_pagto_id = fb.buscar_ou_criar_condicao_pgto(conn, duplicatas, desc_cond)
                            if cond_pagto_id: self.txt_log.insert(tk.END, f"💰 Condição pgto '{desc_cond}' (ID {cond_pagto_id}) vinculada/criada.\n")
                    except Exception as e:
                        self.txt_log.insert(tk.END, f"⚠️ Aviso: Erro ao processar condição de pagto para {reg['razao']}: {e}\n")
                elif desc_cond == 'N/I': self.txt_log.insert(tk.END, f"ℹ️ Info: XML sem dados de duplicatas/cobrança a prazo para {reg['razao']}.\n")
                
                reg_final = reg.copy()
                
                # Passa o código preferencial extraído da Razão Social (ex: "123 - Nome" → código 123)
                cf_cod_antigo = reg.get('cf_cod_antigo')
                if cf_cod_antigo and cf_cod_antigo != '-':
                    try:
                        reg_final['codigo_insercao'] = int(cf_cod_antigo)
                    except (ValueError, TypeError):
                        pass
                
                reg_final['cidade_ibge'] = cid_codigo
                reg_final['documento_formatado'] = reg.get('documento_formatado', reg['documento'])
                reg_final['cond_pagto_id'] = cond_pagto_id
                
                # --- BLINDAGEM EXTREMA ---
                # Se o ID ficou vazio, esvaziamos a matriz de duplicatas do registro. 
                # Isso impede FISICAMENTE que o motor de banco de dados tente criar condições ignoradas.
                if cond_pagto_id is None:
                    reg_final['condicao_pagamento'] = []
                
                registros_para_inserir.append(reg_final)
                
            sucesso, inseridos, erros = fb.inserir_clientes_nfe(conn, registros_para_inserir, emp, fil)
            
            if sucesso:
                messagebox.showinfo("Sucesso", f"{inseridos} registro(s) importados com sucesso!\nErros: {erros}")
                
                for (item, valores), r in zip(selecionados, registros_para_inserir):
                    if r.get('_status_importacao') == 'OK':
                        valores[0] = "☐"
                        valores[-2] = r['codigo_gerado'] # Atualiza o CÓD. ERP gerado na tabela
                        valores[-1] = "JÁ CADASTRADO"
                        self.tree.item(item, values=valores, tags=('CADASTRADO',))
                        
                        reg_completo = self.dados_nfe_lidos.get(item)
                        for d in self.dados_completos:
                            if d['reg_completo'] == reg_completo:
                                d['valores'] = valores
                                d['tag'] = 'CADASTRADO'
                                break
                        self.txt_log.insert(tk.END, f"✅ Importado: {r['razao']} (Cód: {r['codigo_gerado']})\n")
                    else:
                        erro_msg = r.get('_erro_importacao', 'Erro desconhecido')
                        self.txt_log.insert(tk.END, f"❌ Erro em {r['razao']}: {erro_msg}\n")
                    
                self._oferecer_log(registros_para_inserir)
        except Exception as e:
            messagebox.showerror("Erro na Importação", f"Ocorreu um erro ao gravar no banco:\n{e}")
        finally:
            self.txt_log.config(state=tk.DISABLED)
            self.txt_log.see(tk.END)
            conn.close()

    def _oferecer_log(self, registros_importados=None):
        conteudo_log = self.txt_log.get("1.0", tk.END).strip()
        if not conteudo_log:
            return
            
        resp = messagebox.askyesno("Exportar Log", "Deseja salvar um arquivo .txt com o log da importação (avisos de cidades e sucessos)?")
        if resp:
            caminho = filedialog.asksaveasfilename(defaultextension=".txt", initialfile="LOG_IMPORTACAO_NFE.txt", filetypes=[("Text Files", "*.txt")])
            if caminho:
                try:
                    with open(caminho, 'w', encoding='utf-8') as f:
                        f.write(conteudo_log)
                    messagebox.showinfo("Log Salvo", f"Arquivo salvo em:\n{caminho}")
                    if messagebox.askyesno("Abrir Log", "Deseja abrir o arquivo de log agora?"):
                        try:
                            caminho = os.path.normpath(caminho)
                            os.startfile(caminho)
                        except Exception as e:
                            messagebox.showerror("Erro", f"Erro ao abrir arquivo:\n{e}")
                except Exception as e:
                    messagebox.showerror("Erro", f"Erro ao salvar o arquivo de log:\n{e}")
                    
        if registros_importados:
            resp_csv = messagebox.askyesno("Exportar Relatório", "Deseja também salvar uma planilha (CSV) com os dados detalhados dos clientes importados para conferência?")
            if resp_csv:
                caminho_csv = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="RELATORIO_CLIENTES_IMPORTADOS.csv", filetypes=[("CSV Files", "*.csv")])
                if caminho_csv:
                    try:
                        with open(caminho_csv, 'w', newline='', encoding='utf-8-sig') as f:
                            # Pega as chaves ignorando dados aninhados complexos
                            chaves = [k for k in registros_importados[0].keys() if not isinstance(registros_importados[0][k], (dict, list))]
                            writer = csv.DictWriter(f, fieldnames=chaves, delimiter=';')
                            writer.writeheader()
                            for r in registros_importados:
                                linha = {k: v for k, v in r.items() if k in chaves}
                                writer.writerow(linha)
                    except Exception as e:
                        messagebox.showerror("Erro", f"Erro ao salvar o relatório CSV:\n{e}")
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import configparser
import threading
import re
import os
import unicodedata

from utils import tema
from utils import tipo_cadastro
from utils import multivalor
from utils.excel_reader import obter_abas_planilha, ler_planilha_produtos
from utils.firebird_service import FirebirdService

# opção do filtro de status para as linhas em que uma célula trazia vários valores
FILTRO_MULTIVALOR = "⚠ MAIS DE UM VALOR"

CAMPOS_DISPONIVEIS = [
    ("Código (CF_CODIGO)", "cf_codigo", False),
    ("CPF/CNPJ *", "documento", True),
    ("Razão Social *", "razao", True),
    ("Fantasia", "fantasia", False),
    ("IE (Insc. Estadual)", "ie", False),
    ("Endereço", "endereco", False),
    ("Número", "numero", False),
    ("Complemento", "complemento", False),
    ("Bairro", "bairro", False),
    ("Cidade (nome)", "cidade_nome", False),
    ("UF", "uf", False),
    ("CEP", "cep", False),
    ("Fone1", "fone1", False),
    ("Fone2", "fone2", False),
    ("Email", "email", False),
    # CF_EMAIL_NFE é VARCHAR(1): uma FLAG ("manda NF-e por e-mail?"), não um
    # endereço. O rótulo dizia "Email NF-e" e a coluna mapeada era lida da
    # planilha e jogada fora — o INSERT gravava 'S' fixo para todo mundo.
    ("Envia NF-e por e-mail (S/N)", "email_nfe", False),
    ("Vendedor (cód. ou nome)", "vendedor_nome", False),
    ("Limite de Crédito", "limite_credito", False),
    ("Ativo (S/N)", "ativo", False),
    ("Cond. Pagto Venda (cód. ou descr.)", "cond_pgto_venda", False),
    ("Cond. Pagto Compra (cód. ou descr.)", "cond_pgto_compra", False),
    ("Transportadora (cód. ou nome)", "transportadora", False),
    ("Prazo Máximo (dias)", "prazo_maximo", False),
    ("Desconto (%)", "desconto", False),
    ("SUFRAMA", "suframa", False),
    ("Bloqueado (S/N)", "bloquear", False),
    ("Simples Nacional (S/N)", "simples_nacional", False),
    ("Observação", "observacao", False),
]

# --- modos de operação -------------------------------------------------------
MODO_INSERIR = "Só inserir novos"
MODO_AMBOS = "Inserir novos e atualizar existentes"
MODO_ATUALIZAR = "Só atualizar existentes"
MODOS = [MODO_INSERIR, MODO_AMBOS, MODO_ATUALIZAR]

FILTRO_ATUALIZAR = "ATUALIZAR"
FILTRO_IGNORADO = "IGNORADO (novo)"

# Campos que o INSERT clássico não cobre: viram coluna direta, tanto no INSERT
# (acrescentados ao fim) quanto no UPDATE. chave do mapeamento -> (coluna, tipo).
# Sem isto, mapear "Prazo Máximo" seria lido da planilha e jogado fora calado —
# foi o que acontecia (e ainda acontece) com "Email NF-e", que no banco é uma
# FLAG VARCHAR(1) e não um endereço.
# (chave, coluna, tipo, tamanho do texto no banco)
CAMPOS_EXTRA = [
    ('cond_pgto_venda',  'CF_COND_PGTO_VENDA',  'condpgto', None),
    ('cond_pgto_compra', 'CF_COND_PGTO_COMPRA', 'condpgto', None),
    ('transportadora',   'CF_TRANSPORTADORA',   'transportadora', None),
    ('prazo_maximo',     'CF_PRAZO_MAXIMO',     'inteiro', None),
    ('desconto',         'CF_DESCONTO',         'decimal', None),
    ('suframa',          'CF_SUFRAMA',          'texto', 10),
    ('bloquear',         'CF_BLOQUEAR',         'sn', None),
    ('simples_nacional', 'CF_SIMPLES_NACIONAL', 'sn', None),
    ('observacao',       'CF_OBSERVACAO',       'texto', None),   # BLOB
]

# Campos clássicos e a coluna que cada um atualiza. Endereço, cidade, vendedor,
# IE e limite têm tratamento próprio (mais de uma coluna ou resolução no ERP).
CAMPOS_SIMPLES_UPDATE = [
    ('razao', 'CF_RAZAO'),
    ('fantasia', 'CF_FANTASIA'),
    ('bairro', 'CF_BAIRRO'),
    ('cep', 'CF_CEP'),
    ('fone1', 'CF_FONE1'),
    ('fone2', 'CF_FONE2'),
    ('email', 'CF_EMAIL'),
    ('ativo', 'CF_ATIVO'),
    ('email_nfe', 'CF_EMAIL_NFE'),
]

class TelaImportacaoPlanilhaClientes(ttk.Frame):
    def __init__(self, parent, callback_voltar=None):
        super().__init__(parent, padding="10")
        self.parent = parent
        self.callback_voltar = callback_voltar
        self.pack(fill=tk.BOTH, expand=True)

        self.registros_lidos = []
        self.caminho_arquivo = ""
        self.dados_grid = {}
        self._sort_directions = {}

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
        self._carregar_config_mapeamento()

    def _criar_widgets(self):
        # === HEADER ===
        tema.montar_header(
            self, "Importar Clientes (Excel)",
            "Importação de clientes com mapeamento de colunas via planilha (XLSX/CSV)"
        ).pack(fill=tk.X)

        # ===================== CORPO: menu lateral + conteúdo =====================
        corpo = tk.Frame(self, bg=tema.BG_BASE)
        corpo.pack(fill=tk.BOTH, expand=True)

        # -------- MENU LATERAL (padrão do main) --------
        sidebar = tema.montar_sidebar(corpo)

        # Rodapé do menu: Voltar
        rodape_sb = tk.Frame(sidebar, bg=tema.SIDEBAR_BG)
        rodape_sb.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 8))
        self.btn_voltar = tema.botao_sidebar(rodape_sb, "⎋   Voltar", self._fechar_tela)
        self.btn_voltar.pack(fill=tk.X)

        tema.titulo_sidebar(sidebar, "AÇÕES").pack(fill=tk.X, pady=(16, 4))

        self.btn_analisar = tema.botao_sidebar(sidebar, "🔍   Carregar e Analisar Planilha",
                                               self._iniciar_analise)
        self.btn_analisar.pack(fill=tk.X)

        self.btn_importar = tema.botao_sidebar(sidebar, "🚀   Processar e Injetar no ERP",
                                               self._iniciar_importacao, cor_fg="#7EE0A0")
        self.btn_importar.config(state=tk.DISABLED)
        self.btn_importar.pack(fill=tk.X)

        # -------- CONTEÚDO --------
        content = tk.Frame(corpo, bg=tema.BG_BASE)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=16, pady=12)

        # === FILE SELECTION ROW ===
        file_row = ttk.Frame(content)
        file_row.pack(fill=tk.X, pady=2)

        tk.Label(file_row, text="Arquivo:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 2))
        self.ent_arquivo = ttk.Entry(file_row, font=("Segoe UI", 9))
        self.ent_arquivo.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        self.btn_selecionar = ttk.Button(file_row, text="📁 Selecionar", command=self._selecionar_arquivo)
        self.btn_selecionar.pack(side=tk.LEFT, padx=2)

        tk.Label(file_row, text="Aba:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(10, 2))
        self.cb_abas = ttk.Combobox(file_row, width=16, state="readonly", font=("Segoe UI", 9))
        self.cb_abas.pack(side=tk.LEFT, padx=2)

        tk.Label(file_row, text="Linha Inicial:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(10, 2))
        self.ent_linha_ini = ttk.Entry(file_row, width=6, font=("Segoe UI", 9))
        self.ent_linha_ini.insert(0, "2")
        self.ent_linha_ini.pack(side=tk.LEFT, padx=2)

        # O que fazer com quem JÁ existe no ERP. Atualizar mexe em cadastro que
        # está em uso, então é escolha explícita — nunca o padrão.
        modo_row = ttk.Frame(content)
        modo_row.pack(fill=tk.X, pady=2)
        tk.Label(modo_row, text="Modo:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 2))
        self.cb_modo = ttk.Combobox(modo_row, values=MODOS, state="readonly", width=36,
                                    font=("Segoe UI", 9))
        self.cb_modo.set(MODO_INSERIR)
        self.cb_modo.pack(side=tk.LEFT, padx=2)
        self.cb_modo.bind("<<ComboboxSelected>>", self._on_modo_mudou)
        self.lbl_modo = tk.Label(modo_row, text="", font=("Segoe UI", 8), fg="#555")
        self.lbl_modo.pack(side=tk.LEFT, padx=(8, 0))

        self.btn_upd_todos = ttk.Button(modo_row, text="✎ todos", width=9,
                                        command=lambda: self._marcar_campos_update(True))
        self.btn_upd_nenhum = ttk.Button(modo_row, text="✎ nenhum", width=10,
                                         command=lambda: self._marcar_campos_update(False))
        self.btn_upd_nenhum.pack(side=tk.RIGHT, padx=(2, 5))
        self.btn_upd_todos.pack(side=tk.RIGHT, padx=2)
        tk.Label(modo_row, text="sobrescrever:", font=("Segoe UI", 8, "bold"),
                 fg="#555").pack(side=tk.RIGHT, padx=(10, 2))

        # === COLUMN MAPPING (responsivo: reflui conforme a largura) ===
        self.frame_map = ttk.LabelFrame(
            content, text="Mapeamento de Colunas (Insira a letra: A, B, C...) — "
                          "o ✎ ao lado diz se aquele campo pode SOBRESCREVER o que está no ERP",
            padding="8")
        self.frame_map.pack(fill=tk.X, pady=4)
        # os campos vivem num quadro interno para poder recolher o bloco inteiro:
        # com 28 campos, o mapeamento aberto come a altura da grade em 1024x700
        self.box_map = ttk.Frame(self.frame_map)
        self.box_map.pack(fill=tk.X)

        self.entradas_map = {}
        # Mapear uma coluna e sobrescrever o cadastro são decisões diferentes: dá
        # para ter o Endereço na planilha (usado no cadastro NOVO) e não querer que
        # ele mexa no endereço de quem já existe. Este ✎ é essa segunda decisão.
        self.upd_campos = {}
        self._map_cells = []
        for (lbl_texto, chave, obrigatorio) in CAMPOS_DISPONIVEIS:
            cell = ttk.Frame(self.box_map)
            fg_color = "#C8001E" if obrigatorio else "#1A1A1A"
            tk.Label(cell, text=lbl_texto, font=("Segoe UI", 8, "bold"),
                     fg=fg_color).pack(side=tk.LEFT, padx=(0, 4))
            ent = ttk.Entry(cell, width=5, font=("Segoe UI", 9))
            ent.pack(side=tk.LEFT)
            self.entradas_map[chave] = ent
            if chave not in self.CHAVES_FORA_DO_UPDATE:
                var = tk.BooleanVar(value=True)
                chk = ttk.Checkbutton(cell, text="✎", variable=var,
                                      command=self._atualizar_dica_campos)
                chk.pack(side=tk.LEFT, padx=(3, 0))
                self.upd_campos[chave] = (var, chk)
            self._map_cells.append(cell)

        self._map_cols = 0
        self.frame_map.bind("<Configure>", self._on_map_resize)
        self.after(100, self._on_map_resize)

        self.btn_recolher_map = ttk.Button(modo_row, text="⊟ mapeamento", width=15,
                                           command=self._alternar_mapa)
        self.btn_recolher_map.pack(side=tk.RIGHT, padx=(10, 2))

        # === ACTIONS + PROGRESS ===
        actions_row = ttk.Frame(content)
        actions_row.pack(fill=tk.X, pady=4)
        self.actions_row = actions_row     # âncora para recolher/mostrar o mapeamento

        ttk.Button(actions_row, text="☑ Marcar Todos", command=self._marcar_todos).pack(side=tk.LEFT, padx=3)
        ttk.Button(actions_row, text="☐ Desmarcar", command=self._desmarcar_todos).pack(side=tk.LEFT, padx=3)
        ttk.Separator(actions_row, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=4, fill=tk.Y)
        ttk.Button(actions_row, text="👥 Todos Cliente", command=self._marcar_todos_cliente).pack(side=tk.LEFT, padx=2)
        ttk.Button(actions_row, text="🏭 Todos Fornecedor", command=self._marcar_todos_fornecedor).pack(side=tk.LEFT, padx=2)
        ttk.Button(actions_row, text="👥🏭 Cliente + Fornecedor",
                   command=self._marcar_todos_cliente_fornecedor).pack(side=tk.LEFT, padx=2)
        ttk.Button(actions_row, text="📦 Todos Outros", command=self._marcar_todos_outros).pack(side=tk.LEFT, padx=2)

        self.progresso = ttk.Progressbar(actions_row, orient=tk.HORIZONTAL, mode='determinate', length=120)
        self.progresso.pack(side=tk.LEFT, padx=8)

        self.lbl_status = ttk.Label(actions_row, text="Aguardando configuração...", font=("Segoe UI", 9), foreground="#555")
        self.lbl_status.pack(side=tk.LEFT, padx=2)

        # === FILTER ROW ===
        filter_row = ttk.Frame(content)
        filter_row.pack(fill=tk.X, pady=(2, 0))

        tk.Label(filter_row, text="Filtrar Status:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 2))
        self.cb_filtro_status = ttk.Combobox(filter_row,
                                              values=["Todos", "OK", FILTRO_ATUALIZAR, "ERRO",
                                                      "JÁ CADASTRADO", FILTRO_IGNORADO,
                                                      FILTRO_MULTIVALOR],
                                              state="readonly", width=26, font=("Segoe UI", 9))
        self.cb_filtro_status.current(0)
        self.cb_filtro_status.pack(side=tk.LEFT, padx=2)
        self.cb_filtro_status.bind("<<ComboboxSelected>>", self._filtrar_status)

        # === TREEVIEW ===
        frame_grade = ttk.Frame(content)
        frame_grade.pack(fill=tk.BOTH, expand=True, pady=4)

        self.colunas = ("SEL", "STATUS", "CLI", "FOR", "OUT", "CPF/CNPJ", "RAZÃO SOCIAL", "FANTASIA", "CIDADE", "VENDEDOR", "LIMITE", "ATIVO", "CÓDIGO")
        self._sort_directions = {col: False for col in self.colunas}
        self.tree = ttk.Treeview(frame_grade, columns=self.colunas, show="headings")

        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)

        larguras = [40, 100, 36, 36, 36, 150, 250, 150, 120, 120, 90, 70, 80]
        for col, larg in zip(self.colunas, larguras):
            self.tree.heading(col, text=col + " ↕", command=lambda c=col: self._sort_treeview(c))
            self.tree.column(col, width=larg, anchor=tk.CENTER if col not in ("RAZÃO SOCIAL",) else tk.W)

        self.tree.tag_configure('ERRO', background='#FADBD8')
        self.tree.tag_configure('OK', background='#EAFAF1')
        self.tree.tag_configure('AVISO', background='#FEF5D3')
        self.tree.tag_configure('ATU', background='#E4EEFB')   # vai ser atualizado
        self.tree.tag_configure('NEUTRO', background='#F1F5F9')

        scroll_y = ttk.Scrollbar(frame_grade, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

    def _salvar_config_mapeamento(self):
        config = configparser.ConfigParser()
        config.read('config.ini', encoding='utf-8')
        secao = 'IMPORTACAO_CLIENTES'
        if not config.has_section(secao):
            config.add_section(secao)
        config.set(secao, 'ultimo_arquivo', self.caminho_arquivo)
        config.set(secao, 'ultima_aba', self.cb_abas.get())
        config.set(secao, 'linha_inicial', self.ent_linha_ini.get())
        config.set(secao, 'modo', self.cb_modo.get())
        for chave, ent in self.entradas_map.items():
            config.set(secao, f'map_{chave}', ent.get().strip())
        for chave, (var, _chk) in self.upd_campos.items():
            config.set(secao, f'upd_{chave}', 'S' if var.get() else 'N')
        with open('config.ini', 'w', encoding='utf-8') as f:
            config.write(f)
        self.config = config

    def _carregar_config_mapeamento(self):
        secao = 'IMPORTACAO_CLIENTES'
        if not self.config.has_section(secao):
            self._on_modo_mudou()
            return
        modo = self.config.get(secao, 'modo', fallback=MODO_INSERIR)
        self.cb_modo.set(modo if modo in MODOS else MODO_INSERIR)
        for chave, (var, _chk) in self.upd_campos.items():
            var.set(self.config.get(secao, f'upd_{chave}', fallback='S').upper() == 'S')
        self._on_modo_mudou()
        arquivo = self.config.get(secao, 'ultimo_arquivo', fallback='')
        if arquivo and os.path.exists(arquivo):
            self.caminho_arquivo = arquivo
            self.ent_arquivo.delete(0, tk.END)
            self.ent_arquivo.insert(0, arquivo)
            abas = obter_abas_planilha(arquivo)
            self.cb_abas['values'] = abas
            aba_salva = self.config.get(secao, 'ultima_aba', fallback='')
            if aba_salva and aba_salva in abas:
                self.cb_abas.set(aba_salva)
            elif abas:
                self.cb_abas.current(0)
            linha = self.config.get(secao, 'linha_inicial', fallback='2')
            self.ent_linha_ini.delete(0, tk.END)
            self.ent_linha_ini.insert(0, linha)
            for chave in self.entradas_map:
                valor = self.config.get(secao, f'map_{chave}', fallback='')
                if valor:
                    self.entradas_map[chave].delete(0, tk.END)
                    self.entradas_map[chave].insert(0, valor)

    def _on_map_resize(self, event=None):
        try:                                  # o after() ainda dispara na tela fechada
            if not self.frame_map.winfo_exists():
                return
        except tk.TclError:
            return
        largura = self.frame_map.winfo_width()
        if largura <= 1:
            return
        # + o checkbox ✎ ao lado da letra da coluna
        por_campo = 235  # px por campo, largo o suficiente p/ o maior rótulo caber inteiro
        cols = max(1, (largura - 24) // por_campo)
        cols = min(cols, len(self._map_cells))
        if cols == self._map_cols:
            return
        self._map_cols = cols
        self._reflow_mapa(cols)

    def _alternar_mapa(self):
        """Recolhe/mostra o bloco de mapeamento, devolvendo a altura para a grade.

        Some o LabelFrame inteiro (não só o conteúdo): esvaziar o quadro por dentro
        não faz o Tk recalcular a altura que ele já pediu, e a grade continuava do
        mesmo tamanho.
        """
        if self.frame_map.winfo_ismapped():
            self.frame_map.pack_forget()
            self.btn_recolher_map.config(text="⊞ mapeamento")
        else:
            self.frame_map.pack(fill=tk.X, pady=4, before=self.actions_row)
            self.btn_recolher_map.config(text="⊟ mapeamento")
            self._map_cols = 0            # força o reflow ao reabrir
            self.after(50, self._on_map_resize)

    def _reflow_mapa(self, cols):
        for cell in self._map_cells:
            cell.grid_forget()
        # Sem 'uniform': o peso só faz a coluna CRESCER para preencher a faixa,
        # nunca encolher abaixo do conteúdo (evita cortar os rótulos).
        for c in range(len(self._map_cells)):
            self.frame_map.grid_columnconfigure(c, weight=1 if c < cols else 0)
        for idx, cell in enumerate(self._map_cells):
            r, c = divmod(idx, cols)
            cell.grid(row=r, column=c, sticky=tk.W, padx=10, pady=5)

    def _selecionar_arquivo(self):
        path = filedialog.askopenfilename(filetypes=[("Arquivos Suportados", "*.xlsx *.csv"), ("Excel", "*.xlsx"), ("CSV", "*.csv")])
        if path:
            self.ent_arquivo.delete(0, tk.END)
            self.ent_arquivo.insert(0, path)
            self.caminho_arquivo = path

            abas = obter_abas_planilha(path)
            self.cb_abas['values'] = abas
            if abas: self.cb_abas.current(0)

    def _fechar_tela(self):
        self.destroy()
        if self.callback_voltar: self.callback_voltar()

    def _iniciar_analise(self):
        aba = self.cb_abas.get()
        try:
            linha_ini = int(self.ent_linha_ini.get())
        except ValueError:
            return messagebox.showerror("Erro", "A linha inicial deve ser um número.")

        if not self.caminho_arquivo or not aba:
            return messagebox.showwarning("Aviso", "Selecione o arquivo e a aba antes de continuar.")

        mapa_colunas = {chave: ent.get().strip() for chave, ent in self.entradas_map.items()}
        if not mapa_colunas.get('documento'):
            return messagebox.showwarning("Aviso", "Você precisa mapear obrigatoriamente a coluna 'CPF/CNPJ'.")
        # A razão social é obrigatória para CADASTRAR. Para só atualizar não é: o
        # CPF/CNPJ já identifica o cliente, e exigir a coluna obrigaria a
        # sobrescrever o nome de quem está no ERP mesmo quando se quer mudar só o
        # limite de crédito.
        if not mapa_colunas.get('razao') and self._pode_inserir():
            return messagebox.showwarning(
                "Aviso", "Para inserir clientes novos você precisa mapear a coluna "
                         "'Razão Social'.\n\nSe a planilha só serve para atualizar, "
                         "escolha o modo 'Só atualizar existentes'.")

        self._salvar_config_mapeamento()
        self.btn_analisar.config(state=tk.DISABLED)
        self.btn_selecionar.config(state=tk.DISABLED)
        self.lbl_status.config(text="Lendo planilha...")
        self.progresso['value'] = 20

        threading.Thread(target=self._analisar_bg, args=(aba, mapa_colunas, linha_ini), daemon=True).start()

    def _analisar_bg(self, aba, mapa_colunas, linha_ini):
        try:
            self.registros_lidos = ler_planilha_produtos(self.caminho_arquivo, aba, mapa_colunas, linha_ini)
            dados_existentes = {'documentos': {}, 'nomes': {}, 'codigos': set(), 'razoes': {}}
            try:
                with FirebirdService(self.config_db) as fb:
                    emp = int(self.config.get('IMPORTACAO', 'empresa', fallback='1'))
                    fil = int(self.config.get('IMPORTACAO', 'filial', fallback='1'))
                    rows = fb.query(
                        "SELECT CF_CODIGO, CF_CPF_CGC, CF_RAZAO FROM TABELA_CLI_FOR WHERE CF_EMPRESA = ? AND CF_FILIAL = ?",
                        [emp, fil]
                    )
                    for row in rows:
                        cod = re.sub(r'\D', '', str(row['cf_codigo'] or ''))
                        if cod:
                            dados_existentes['codigos'].add(cod)
                        # o VALOR é o CF_CODIGO do ERP, não um simples True: é ele
                        # que o UPDATE usa para achar o cliente certo
                        doc = re.sub(r'\D', '', str(row['cf_cpf_cgc'] or ''))
                        if doc:
                            dados_existentes['documentos'].setdefault(doc, row['cf_codigo'])
                        nome = self._remover_acentos(str(row['cf_razao'] or '')).strip().upper()
                        if nome:
                            dados_existentes['nomes'].setdefault(nome, row['cf_codigo'])
                        # quem a planilha vai atualizar aparece na grade com o nome
                        # QUE ESTÁ NO ERP: atualizar às cegas é o que não pode
                        dados_existentes['razoes'][row['cf_codigo']] = str(row['cf_razao'] or '').strip()
            except Exception:
                pass
            self.parent.after(0, lambda: self._renderizar_preview(dados_existentes))
            self.parent.after(0, lambda: self.btn_selecionar.config(state=tk.NORMAL))
        except Exception as e:
            self.parent.after(0, lambda err=e: messagebox.showerror("Erro", f"Falha na leitura da planilha:\n{err}"))
            self.parent.after(0, lambda: self.btn_analisar.config(state=tk.NORMAL))
            self.parent.after(0, lambda: self.btn_selecionar.config(state=tk.NORMAL))
            self.parent.after(0, lambda: self.lbl_status.config(text="Erro."))

    def _normalizar_documento(self, valor):
        # Duas empresas na mesma célula ('11.111.111/0001-11, 22.222.222/0001-22')
        # davam 28 dígitos: documento inválido que nunca mais casava com nada.
        return multivalor.um_documento(valor)[0]

    def _normalizar_ie(self, valor):
        return re.sub(r'\D', '', multivalor.um_valor(valor)[0])

    def _parse_ativo(self, valor):
        """Interpreta a coluna Ativo. Retorna 'S' (ativo) ou 'N' (inativo). Vazio -> 'S'."""
        s = self._remover_acentos(str(valor or '')).strip().upper()
        if not s:
            return 'S'
        if s in ('N', 'NAO', 'INATIVO', 'I', '0', 'FALSE', 'F', 'DESATIVADO', 'BLOQUEADO'):
            return 'N'
        if s in ('S', 'SIM', 'ATIVO', 'A', '1', 'TRUE', 'T'):
            return 'S'
        if s.startswith('INAT') or s.startswith('DESAT') or s.startswith('BLOQ'):
            return 'N'
        return 'S'

    def _parse_limite(self, valor):
        """Converte o limite de crédito da planilha em float. Retorna None se vazio/inválido/<=0."""
        s = str(valor or '').strip()
        if not s:
            return None
        s = re.sub(r'[^\d,.\-]', '', s)  # remove R$, espaços, etc.
        if not s:
            return None
        if ',' in s and '.' in s:
            # formato BR: 1.234,56 -> 1234.56
            s = s.replace('.', '').replace(',', '.')
        elif ',' in s:
            s = s.replace(',', '.')
        try:
            v = float(s)
        except ValueError:
            return None
        return v if v > 0 else None

    def _limpar_nome_cidade(self, nome):
        nome = str(nome or '').strip()
        nome = re.sub(r'\s*\([A-Z]{2}\)\s*$', '', nome)
        return nome.strip()

    def _remover_acentos(self, texto):
        texto = unicodedata.normalize('NFKD', str(texto))
        return texto.encode('ASCII', 'ignore').decode('ASCII')

    def _parse_endereco_completo(self, endereco, numero, complemento):
        """Extrai número e complemento do endereço quando vierem tudo junto."""
        end = str(endereco or '').strip()
        num = str(numero or '').strip()
        comp = str(complemento or '').strip()

        if not end:
            return (end, num, comp)

        if num or comp:
            return (end, num, comp)

        m = re.match(r'^(.+),\s*(\d+)\s*[-–]\s*(.+)$', end)
        if m:
            return (m.group(1).strip(), m.group(2), m.group(3).strip())

        m = re.match(r'^(.+),\s*(\d+)\s*,\s*(.+)$', end)
        if m:
            return (m.group(1).strip(), m.group(2), m.group(3).strip())

        m = re.match(r'^(.+),\s*(\d+)\s*$', end)
        if m:
            return (m.group(1).strip(), m.group(2), '')

        m = re.match(r'^(.+?)\s+(\d+)\s*[-–]\s*(.+)$', end)
        if m:
            return (m.group(1).strip(), m.group(2), m.group(3).strip())

        m = re.match(r'^(.+?)\s+(\d+)\s*$', end)
        if m:
            return (m.group(1).strip(), m.group(2), '')

        return (end, '', comp)

    # ===================== MODO DE OPERAÇÃO E CAMPOS A ATUALIZAR =============
    def _modo(self):
        modo = self.cb_modo.get()
        return modo if modo in MODOS else MODO_INSERIR

    def _pode_atualizar(self):
        return self._modo() in (MODO_AMBOS, MODO_ATUALIZAR)

    def _pode_inserir(self):
        return self._modo() in (MODO_AMBOS, MODO_INSERIR)

    def _on_modo_mudou(self, _evento=None):
        # os ✎ só fazem sentido quando existe UPDATE; fora disso ficam desligados
        # para não parecer que estão comandando alguma coisa
        estado = tk.NORMAL if self._pode_atualizar() else tk.DISABLED
        for _var, chk in self.upd_campos.values():
            chk.config(state=estado)
        for btn in (self.btn_upd_todos, self.btn_upd_nenhum):
            btn.config(state=estado)
        if self._pode_atualizar():
            self._atualizar_dica_campos()
        else:
            self.lbl_modo.config(text="quem já existe no ERP é apenas listado, não é tocado",
                                 fg="#555")

    def _atualizar_dica_campos(self):
        if not self._pode_atualizar():
            return
        campos = self._campos_atualizaveis_mapeados()
        self.lbl_modo.config(
            text=(f"⚠ vai sobrescrever {len(campos)} campo(s) de quem já existe; "
                  f"célula vazia não apaga nada" if campos
                  else "nenhum campo marcado para sobrescrever — só inserção"),
            fg="#B45309" if campos else "#555")

    def _marcar_campos_update(self, ligado):
        for var, _chk in self.upd_campos.values():
            var.set(ligado)
        self._atualizar_dica_campos()

    def _sobrescreve(self, chave):
        """O ✎ deste campo está marcado? (campo sem ✎ nunca sobrescreve)"""
        par = self.upd_campos.get(chave)
        return bool(par and par[0].get())

    # a identificação da linha não é campo a atualizar
    CHAVES_FORA_DO_UPDATE = {'documento', 'cf_codigo'}
    # estas entram junto de outro campo (endereço e cidade), não sozinhas
    CHAVES_ACOPLADAS = {'numero', 'complemento', 'uf'}

    def _campos_atualizaveis_mapeados(self):
        """Rótulos dos campos mapeados que um UPDATE vai mexer."""
        rotulos = []
        for (lbl, chave, _obrig) in CAMPOS_DISPONIVEIS:
            if chave in self.CHAVES_FORA_DO_UPDATE or chave in self.CHAVES_ACOPLADAS:
                continue
            if self.entradas_map[chave].get().strip() and self._sobrescreve(chave):
                rotulos.append(lbl.replace(' *', ''))
        return rotulos

    # ===================== CONVERSORES ======================================
    @staticmethod
    def _inteiro(valor):
        """'30', '30.0' e '1.234' -> int. None quando não é número puro."""
        s = str(valor or '').strip().replace(' ', '')
        if not s:
            return None
        if re.fullmatch(r'-?\d+([.,]0+)?', s):
            return int(float(s.replace(',', '.')))
        if re.fullmatch(r'-?\d{1,3}(\.\d{3})+', s):     # 1.234 -> 1234
            return int(s.replace('.', ''))
        return None

    @staticmethod
    def _decimal(valor):
        """Número da planilha em float, aceitando 1.234,56 e 1234.56. Zero VALE.

        Diferente de `_parse_limite`, que descarta zero: um desconto de 0% é uma
        informação (zera o desconto), não uma célula vazia.
        """
        s = re.sub(r'[^\d,.\-]', '', str(valor or '').strip())
        if not s:
            return None
        if ',' in s and '.' in s:
            s = s.replace('.', '').replace(',', '.')
        elif ',' in s:
            s = s.replace(',', '.')
        try:
            return float(s)
        except ValueError:
            return None

    def _sn(self, valor):
        """'S'/'N' a partir de sim/não/1/0/ativo/inativo. Vazio -> None."""
        if not str(valor or '').strip():
            return None
        return self._parse_ativo(valor)

    def _resolver_ref(self, valor, por_nome, codigos, rotulo):
        """Resolve "código OU nome/descrição" num código do ERP.

        Devolve (codigo, aviso). Número que existe no ERP vale por si; texto é
        procurado pelo nome/descrição (sem acento, maiúsculas). Não achou, ou
        achou MAIS DE UM: o campo fica FORA do UPDATE e o log diz por quê —
        gravar código que não existe é chave estrangeira quebrada, e escolher
        sozinho entre dois é pior ainda. Descrição repetida acontece de verdade:
        na base do cliente, 'A VISTA' é a condição 0 **e** a 236.
        """
        s = str(valor or '').strip()
        if not s:
            return None, None
        n = self._inteiro(s)
        if n is not None:
            if n in codigos:
                return n, None
            return None, f"{rotulo} '{s}': este código não existe no ERP"
        achados = por_nome.get(self._remover_acentos(s).strip().upper())
        if not achados:
            return None, f"{rotulo} '{s}': não encontrado(a) pela descrição/nome"
        if len(achados) > 1:
            return None, (f"{rotulo} '{s}': a descrição está em {len(achados)} cadastros "
                          f"({', '.join(str(c) for c in achados)}) — informe o CÓDIGO")
        return achados[0], None

    def _planejar_codigos(self, itens, codigos_ocupados, docs_db, nomes_db, codigo_mapeado,
                          cod_por_doc=None, cod_por_nome=None):
        """
        Define o código final de cada item em DUAS passadas, sem cascata:
          1) reserva os códigos da planilha que ainda estão LIVRES no sistema;
          2) os que colidem (código já ocupado no sistema ou já reservado) recebem
             o MENOR número livre disponível, respeitando os reservados.
        Também aplica a unicidade de documento (CF_CPF_CGC) e o de-para por nome.
        Marca em cada item: _plan_acao ('inserir'|'atualizar'|'ja_cadastrado'|
        'ignorado_novo'|'pular_doc'|'erro'), _plan_codigo (int), _cod_orig
        (int|None), _plan_remap (bool) e _casou_por (como bateu com o ERP).

        Quem já existe no ERP é reconhecido por CPF/CNPJ, pelo código mapeado ou
        pela razão social (nessa ordem) e, no modo que atualiza, sai com
        'atualizar' e o código QUE ELE JÁ TEM — nunca remanejado, senão o UPDATE
        cairia noutro cliente.
        """
        existentes = set()
        for c in codigos_ocupados:
            cs = re.sub(r'\D', '', str(c))
            if cs:
                existentes.add(int(cs))

        reservados = set()
        conflitos = []
        docs_db = set(docs_db)
        nomes_db = set(nomes_db)
        # o que já apareceu NA PLANILHA, separado do que já está no ERP: um é
        # linha repetida (sempre pula), o outro é cliente existente (que no modo
        # de atualizar é justamente o que se quer)
        docs_seen = set()
        nomes_seen = set()
        pode_atualizar = self._pode_atualizar()
        cod_por_doc = cod_por_doc or {}
        cod_por_nome = cod_por_nome or {}

        for it in itens:
            razao = str(it.get('razao', '')).strip()
            # Detecta aqui, antes de qualquer decisão: o documento usado na
            # unicidade tem de ser o já limpo, senão dois CNPJs na mesma célula
            # passam como um documento novo e o cliente entra duplicado.
            it['_multivalor'] = multivalor.limpar_registro(it)
            documento = self._normalizar_documento(it.get('documento', ''))
            it['documento_limpo'] = documento
            razao_norm = self._remover_acentos(razao).strip().upper()[:50]
            cod = re.sub(r'\D', '', str(it.get('cf_codigo', '')).strip())
            it['_cod_orig'] = None
            it['_plan_remap'] = False
            it['_plan_codigo'] = None
            it['_casou_por'] = None

            # sem razão social não há como CADASTRAR; para atualizar, o documento
            # (ou o código) já identifica quem é
            if not razao and not (pode_atualizar and (documento or cod)):
                it['_plan_acao'] = 'erro'
                continue
            if documento and documento in docs_seen:
                it['_plan_acao'] = 'pular_doc'          # repetido na própria planilha
                continue
            if razao_norm and not documento and razao_norm in nomes_seen:
                it['_plan_acao'] = 'pular_doc'
                continue

            # --- já existe no ERP? por documento, por código mapeado ou por nome
            achou_cod = None
            if documento and documento in docs_db:
                achou_cod, it['_casou_por'] = cod_por_doc.get(documento), 'CPF/CNPJ'
            elif codigo_mapeado and cod and int(cod) in existentes:
                achou_cod, it['_casou_por'] = int(cod), 'código'
            elif not documento and razao_norm and razao_norm in nomes_db:
                achou_cod, it['_casou_por'] = cod_por_nome.get(razao_norm), 'razão social'

            if it['_casou_por']:
                if pode_atualizar and achou_cod is not None:
                    it['_plan_acao'] = 'atualizar'
                    it['_plan_codigo'] = int(achou_cod)
                else:
                    it['_plan_acao'] = 'ja_cadastrado'
                if documento:
                    docs_seen.add(documento)
                elif razao_norm:
                    nomes_seen.add(razao_norm)
                continue

            if not self._pode_inserir():
                it['_plan_acao'] = 'ignorado_novo'
                if documento:
                    docs_seen.add(documento)
                elif razao_norm:
                    nomes_seen.add(razao_norm)
                continue

            if codigo_mapeado and cod:
                c = int(cod)
                if c in existentes or c in reservados:
                    it['_plan_acao'] = 'conflito'
                    it['_cod_orig'] = c
                    conflitos.append(it)
                else:
                    reservados.add(c)
                    it['_plan_acao'] = 'inserir'
                    it['_plan_codigo'] = c
            else:
                it['_plan_acao'] = 'conflito'
                conflitos.append(it)

            if documento:
                docs_seen.add(documento)
            elif razao_norm:
                nomes_seen.add(razao_norm)

        # PASSADA 2 — encaixa os conflitos no menor número livre
        ocupados = existentes | reservados
        prox = 1
        for it in conflitos:
            while prox in ocupados:
                prox += 1
            it['_plan_codigo'] = prox
            it['_plan_acao'] = 'inserir'
            it['_plan_remap'] = it.get('_cod_orig') is not None
            ocupados.add(prox)

    def _renderizar_preview(self, dados_existentes=None):
        # Selo deste render. A grade e preenchida em blocos com after(), entao um
        # render antigo pode continuar inserindo DEPOIS que outro limpou a tela —
        # a grade acumula duas analises e os totais somam tudo. O selo faz os
        # blocos do render antigo pararem.
        self._render_seq = getattr(self, '_render_seq', 0) + 1
        meu_seq = self._render_seq

        for i in self.tree.get_children(): self.tree.delete(i)
        self.dados_grid.clear()

        docs_existentes = dados_existentes.get('documentos', {}) if dados_existentes else {}
        nomes_existentes = dados_existentes.get('nomes', {}) if dados_existentes else {}
        codigos_existentes = dados_existentes.get('codigos', set()) if dados_existentes else set()

        codigo_mapeado = bool(self.entradas_map['cf_codigo'].get().strip())

        # Planeja os códigos de TODAS as linhas (reserva antigos + encaixa conflitos)
        self._planejar_codigos(
            self.registros_lidos, codigos_existentes,
            set(docs_existentes.keys()), set(nomes_existentes.keys()), codigo_mapeado,
            docs_existentes, nomes_existentes
        )
        campos_upd = self._campos_atualizaveis_mapeados()

        self._contagem = {'ok': 0, 'ja': 0, 'doc_rep': 0, 'remap': 0, 'multi': 0,
                          'atu': 0, 'ign': 0}
        items = []
        validos = 0
        razoes_erp = dados_existentes.get('razoes', {}) if dados_existentes else {}
        for reg in self.registros_lidos:
            documento = reg.get('documento_limpo', '')
            razao = str(reg.get('razao', '')).strip()
            acao = reg.get('_plan_acao')
            if acao == 'atualizar' and not razao:
                # planilha sem coluna de razão: mostra de quem é o cadastro
                razao = f"[ERP] {razoes_erp.get(reg.get('_plan_codigo'), '')}"
            cod_sheet = re.sub(r'\D', '', str(reg.get('cf_codigo', '')).strip())

            if acao == 'erro':
                status = "ERRO (Sem Razão Social)"
            elif acao == 'pular_doc':
                status = "DOC. REPETIDO"                 # repetido na própria planilha
                self._contagem['doc_rep'] += 1
            elif acao == 'ja_cadastrado':
                status = "JÁ CADASTRADO"
                self._contagem['ja'] += 1
            elif acao == 'ignorado_novo':
                status = "IGNORADO (novo)"               # modo 'só atualizar'
                self._contagem['ign'] += 1
            elif acao == 'atualizar':
                # diz de saída quantos campos vão mudar: atualização de zero
                # campo é mapeamento incompleto, e passar batido seria pior
                status = (f"ATUALIZAR ({len(campos_upd)} campo(s))" if campos_upd
                          else "ATUALIZAR (nada mapeado)")
                validos += 1
                self._contagem['atu'] += 1
            else:  # inserir
                status = "OK"
                validos += 1
                self._contagem['ok'] += 1
                if reg.get('_plan_remap'):
                    self._contagem['remap'] += 1

            reg['_status'] = status
            check = "☑" if status == "OK" or acao == 'atualizar' else "☐"

            pode_editar = status == "OK"
            if acao == 'atualizar':
                # nada marcado = não mexer no tipo de quem já existe; marcar um
                # aqui é o que autoriza o UPDATE a mudar CLI/FOR/OUTROS
                cli = forn = out = "☐"
            elif pode_editar:
                cli = "☐"
                forn = "☐"
                out = "☑"
            else:
                cli = forn = out = "☐"

            fantasia = str(reg.get('fantasia', ''))[:60]
            cidade = str(reg.get('cidade_nome', ''))[:60]
            vendedor = str(reg.get('vendedor_nome', ''))[:60]

            limite_val = self._parse_limite(reg.get('limite_credito', ''))
            reg['_limite'] = limite_val
            limite_fmt = f"{limite_val:.2f}" if limite_val is not None else "-"

            ativo_flag = self._parse_ativo(reg.get('ativo', ''))
            reg['_ativo'] = ativo_flag
            # no UPDATE, célula vazia não é "ativar": é "não mexer no CF_ATIVO"
            ativo_fmt = ("-" if acao == 'atualizar' and self._sn(reg.get('ativo', '')) is None
                         else ("Ativo" if ativo_flag == 'S' else "Inativo"))

            cod_final = reg.get('_plan_codigo')
            if acao == 'atualizar':
                cod_fmt = f"{cod_final} ({reg.get('_casou_por')})"   # o que já existe no ERP
            elif acao != 'inserir':
                cod_fmt = cod_sheet or "-"
            elif reg.get('_plan_remap'):
                cod_fmt = f"{reg.get('_cod_orig')}→{cod_final}"   # antigo ocupado, remanejado
            elif not cod_sheet:
                cod_fmt = f"{cod_final} (auto)"                   # sem código na planilha
            else:
                cod_fmt = str(cod_final)                          # manteve o código antigo

            # linha âmbar quando alguma célula trazia mais de um valor: o cadastro
            # entra, mas com um valor só, e isso tem de ficar visível antes de gravar
            if status == 'OK' or acao == 'atualizar':
                if reg.get('_multivalor'):
                    tag = 'AVISO'
                    self._contagem['multi'] += 1
                else:
                    tag = 'ATU' if acao == 'atualizar' else 'OK'
            elif acao in ('ja_cadastrado', 'ignorado_novo'):
                tag = 'NEUTRO'
            else:
                tag = 'ERRO'
            reg['_tipo'] = {
                'cliente': cli == "☑",
                'fornecedor': forn == "☑",
                'outros': out == "☑"
            }
            items.append((
                (check, status, cli, forn, out, reg.get('documento', ''), razao,
                 fantasia, cidade, vendedor, limite_fmt, ativo_fmt, cod_fmt),
                tag, reg
            ))

        total = len(items)
        if total == 0:
            self.btn_analisar.config(state=tk.NORMAL)
            self.lbl_status.config(text="Nenhum registro válido encontrado.")
            return

        self.lbl_status.config(text=f"Renderizando tabela com {total} registros...")
        self.progresso['value'] = 92

        chunk_size = 30

        def render_chunk(start_idx):
            if meu_seq != self._render_seq:
                return  # um render mais novo assumiu a grade
            end_idx = min(start_idx + chunk_size, total)
            for i in range(start_idx, end_idx):
                values, tag, reg = items[i]
                item_id = self.tree.insert("", tk.END, values=values, tags=(tag,))
                self.dados_grid[item_id] = reg

            if end_idx < total:
                self.lbl_status.config(text=f"Renderizando {end_idx}/{total}...")
                self.update_idletasks()
                self.parent.after(5, render_chunk, end_idx)
            else:
                self.btn_analisar.config(state=tk.NORMAL)
                self.tree.tag_configure('OK', background='#EAFAF1')
                if validos > 0: self.btn_importar.config(state=tk.NORMAL)
                self.progresso['value'] = 100
                c = getattr(self, '_contagem', {})
                extra = ""
                if c.get('multi'):
                    extra = (f" · ⚠ {c['multi']} com mais de um valor na célula "
                             f"(filtre por '{FILTRO_MULTIVALOR}')")
                if c.get('atu'):
                    campos = self._campos_atualizaveis_mapeados()
                    extra += (f" · campos a atualizar: "
                              f"{', '.join(campos) if campos else 'NENHUM mapeado'}")
                self.lbl_status.config(
                    text=(f"Pronto. {total} lidos · novos: {c.get('ok', 0)} · "
                          f"a atualizar: {c.get('atu', 0)} · "
                          f"já cadastrados (intocados): {c.get('ja', 0)} · "
                          f"ignorados (novos): {c.get('ign', 0)} · "
                          f"doc. repetido: {c.get('doc_rep', 0)} · "
                          f"remanejados: {c.get('remap', 0)}{extra}")
                )
                self.cb_filtro_status.current(0)
                self._filtrar_status()

        render_chunk(0)

    @staticmethod
    def _linha_acionavel(status):
        """Linha que o usuário pode marcar/editar: só quem vai inserir ou atualizar.

        'JÁ CADASTRADO' e 'IGNORADO (novo)' são informativos — o modo escolhido
        já disse que não se mexe neles.
        """
        s = str(status or '')
        return not ('ERRO' in s or 'JÁ CADASTRADO' in s or 'IGNORADO' in s
                    or 'DOC. REPETIDO' in s)

    def _on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            item_id = self.tree.identify_row(event.y)
            if not item_id: return
            valores = list(self.tree.item(item_id, 'values'))

            if not self._linha_acionavel(valores[1]):
                return

            # SEL column
            if column == "#1":
                valores[0] = "☑" if valores[0] == "☐" else "☐"
                self.tree.item(item_id, values=valores)
                return

            # CLI, FOR, OUT columns
            col_map = {"#3": "cliente", "#4": "fornecedor", "#5": "outros"}
            if column in col_map:
                chave = col_map[column]
                tipo = self.dados_grid[item_id].get('_tipo', {})
                tipo[chave] = not tipo.get(chave, False)

                # CLIENTE e FORNECEDOR convivem — quem compra e vende é os dois, e
                # o ERP aceita as duas colunas em 'S'. OUTROS é que significa "nem
                # um nem outro", então esse sim continua exclusivo.
                if chave == 'outros':
                    if tipo['outros']:
                        tipo['cliente'] = tipo['fornecedor'] = False
                elif tipo[chave]:
                    tipo['outros'] = False

                # Cadastro NOVO precisa sair com um dos três; em quem já existe,
                # desmarcar tudo é justamente dizer "não mexa no tipo dele".
                if not any(tipo.values()) and self.dados_grid[item_id].get('_plan_acao') != 'atualizar':
                    tipo['outros'] = True

                self._pintar_tipo(item_id, tipo, valores)

    def _marcar_todos(self):
        for item in self.tree.get_children():
            v = list(self.tree.item(item, "values"))
            if self._linha_acionavel(v[1]):
                v[0] = "☑"
                self.tree.item(item, values=v)

    def _desmarcar_todos(self):
        for item in self.tree.get_children():
            v = list(self.tree.item(item, "values"))
            if self._linha_acionavel(v[1]):
                v[0] = "☐"
                self.tree.item(item, values=v)

    def _pintar_tipo(self, item_id, tipo, valores=None):
        """Escreve as três colunas de tipo a partir do dicionário `_tipo`."""
        v = list(valores if valores is not None else self.tree.item(item_id, "values"))
        v[2] = "☑" if tipo.get('cliente') else "☐"
        v[3] = "☑" if tipo.get('fornecedor') else "☐"
        v[4] = "☑" if tipo.get('outros') else "☐"
        self.tree.item(item_id, values=v)

    def _marcar_todos_tipo(self, rotulo):
        """Aplica um dos tipos de `utils.tipo_cadastro` a todas as linhas editáveis."""
        for item in self.tree.get_children():
            v = list(self.tree.item(item, "values"))
            if not self._linha_acionavel(v[1]):
                continue
            tipo = tipo_cadastro.flags(rotulo)
            if item in self.dados_grid:
                self.dados_grid[item]['_tipo'] = tipo
            self._pintar_tipo(item, tipo, v)

    def _marcar_todos_cliente(self):
        self._marcar_todos_tipo(tipo_cadastro.CLIENTE)

    def _marcar_todos_fornecedor(self):
        self._marcar_todos_tipo(tipo_cadastro.FORNECEDOR)

    def _marcar_todos_cliente_fornecedor(self):
        self._marcar_todos_tipo(tipo_cadastro.CLIENTE_FORNECEDOR)

    def _marcar_todos_outros(self):
        self._marcar_todos_tipo(tipo_cadastro.OUTROS)

    def _sort_treeview(self, col):
        self._sort_directions[col] = not self._sort_directions[col]
        reverse = self._sort_directions[col]
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        def valor_para_ordenar(val):
            # Tupla (grupo, valor) evita comparar str com float: números primeiro (grupo 0), texto depois (grupo 1)
            v = str(val).strip()
            if not v or v == '-':
                return (2, '')
            try:
                return (0, float(v.replace(',', '.')))
            except ValueError:
                return (1, v.lower())
        l.sort(key=lambda t: valor_para_ordenar(t[0]), reverse=reverse)
        for index, (_, k) in enumerate(l): self.tree.move(k, '', index)
        for c in self.colunas:
            arrow = " ▼" if self._sort_directions[c] else " ▲" if c == col else " ↕"
            self.tree.heading(c, text=c + arrow, command=lambda x=c: self._sort_treeview(x))

    def _filtrar_status(self, event=None):
        filtro = self.cb_filtro_status.get()
        for item in self.tree.get_children():
            self.tree.detach(item)
        for item_id, reg in self.dados_grid.items():
            status = reg.get('_status', '')
            # o multivalor não é um status: é um aviso que pode cair em qualquer linha,
            # então tem entrada própria no filtro em vez de substituir o status
            if filtro == FILTRO_MULTIVALOR:
                if reg.get('_multivalor'):
                    self.tree.move(item_id, '', tk.END)
                continue
            # 'ATUALIZAR' e 'IGNORADO' carregam a contagem de campos no próprio
            # texto ('ATUALIZAR (3 campo(s))'), então casam por prefixo
            if (filtro == "Todos" or status == filtro
                    or (filtro in (FILTRO_ATUALIZAR, FILTRO_IGNORADO)
                        and status.startswith(filtro.split(' ')[0]))
                    or (filtro == "ERRO" and (status.startswith("ERRO")
                                              or status in ("DUPLICADO NA PLANILHA", "DOC. REPETIDO")))):
                self.tree.move(item_id, '', tk.END)

    def _iniciar_importacao(self):
        selecionados = []
        for item_id in self.tree.get_children():
            valores = self.tree.item(item_id, "values")
            if valores[0] == "☑":
                selecionados.append(self.dados_grid[item_id])

        if not selecionados:
            messagebox.showwarning("Aviso", "Selecione pelo menos um cliente para importar.")
            return

        novos = sum(1 for s in selecionados if s.get('_plan_acao') == 'inserir')
        atualizar = sum(1 for s in selecionados if s.get('_plan_acao') == 'atualizar')
        campos = self._campos_atualizaveis_mapeados()

        linhas = [f"Selecionados: {len(selecionados)}",
                  f"  a inserir:   {novos}",
                  f"  a atualizar: {atualizar}", ""]
        if atualizar:
            if not campos:
                return messagebox.showwarning(
                    "Nada a atualizar",
                    "Nenhum campo atualizável está mapeado — só CPF/CNPJ e código, que "
                    "servem para achar o cliente.\n\nMapeie as colunas que você quer "
                    "atualizar (vendedor, condição de pagamento, limite de crédito...) "
                    "e analise de novo.")
            linhas += ["Nos que já existem, estes campos serão SOBRESCRITOS:",
                       "  • " + "\n  • ".join(campos), "",
                       "Célula vazia não apaga o que está no ERP — o campo fica como está.",
                       "Endereço, número e complemento entram no endereço principal; os",
                       "endereços 2, 3 e 4 do cadastro não são tocados."]
            if self.entradas_map['ie'].get().strip():
                # o próprio ERP faz isso por trigger; quem manda a planilha tem de saber
                linhas += ["", "⚠ A IE está mapeada: o ERP tem trigger que, ao mudar a",
                           "   inscrição estadual, reescreve NFS_INSC_EST das notas de",
                           "   saída dos últimos 90 dias desse cliente."]
            linhas += ["", "Essa ação não pode ser desfeita."]
        else:
            linhas += ["Essa ação não pode ser desfeita."]

        resp = messagebox.askyesno("Confirmar", "\n".join(linhas))
        if resp:
            self._salvar_config_mapeamento()
            self.btn_importar.config(state=tk.DISABLED)
            self.btn_analisar.config(state=tk.DISABLED)
            self.lbl_status.config(text="Importando clientes...")
            threading.Thread(target=self._importacao_bg, args=(selecionados,), daemon=True).start()

    def _importacao_bg(self, selecionados):
        log_linhas = []
        try:
            emp = int(self.config.get('IMPORTACAO', 'empresa', fallback='1'))
            fil = int(self.config.get('IMPORTACAO', 'filial', fallback='1'))

            with FirebirdService(self.config_db) as fb:
                sql_codigos = "SELECT CF_CODIGO FROM TABELA_CLI_FOR WHERE CF_EMPRESA = ? AND CF_FILIAL = ?"
                codigos_usados = set(row['cf_codigo'] for row in fb.query(sql_codigos, [emp, fil]))

                sql_clientes = ("SELECT CF_CPF_CGC, CF_CODIGO, CF_RAZAO, CF_LIMITE_CREDITO "
                                "FROM TABELA_CLI_FOR WHERE CF_EMPRESA = ? AND CF_FILIAL = ?")
                clientes_existentes = {}
                nomes_existentes = {}
                limite_atual = {}       # CF_CODIGO -> limite hoje, para o histórico OLD->NEW
                razoes_erp = {}         # CF_CODIGO -> razão no ERP (log de quem foi mexido)
                for row in fb.query(sql_clientes, [emp, fil]):
                    doc = re.sub(r'\D', '', str(row['cf_cpf_cgc'] or ''))
                    if doc:
                        clientes_existentes[doc] = row['cf_codigo']
                    nome = self._remover_acentos(str(row['cf_razao'] or '')).strip().upper()
                    if nome:
                        nomes_existentes[nome] = row['cf_codigo']
                    limite_atual[row['cf_codigo']] = row['cf_limite_credito']
                    razoes_erp[row['cf_codigo']] = str(row['cf_razao'] or '').strip()

                inseridos = 0
                erros = 0
                atualizados = 0
                ignorados_novos = 0   # novos, no modo que só atualiza
                campos_tocados = 0    # colunas efetivamente gravadas nos UPDATEs
                remapeados = 0    # códigos que estavam ocupados e foram remanejados
                pulados_doc = 0   # documento repetido/já cadastrado
                pulados_nome = 0  # nome já cadastrado (sem documento)
                codigo_mapeado = bool(self.entradas_map['cf_codigo'].get().strip())

                dados_existentes = {
                    'documentos': dict(clientes_existentes),
                    'nomes': dict(nomes_existentes)
                }

                # Planeja os códigos finais dos selecionados (autoritativo, com base atual do ERP)
                self._planejar_codigos(
                    selecionados, codigos_usados,
                    set(clientes_existentes.keys()), set(nomes_existentes.keys()), codigo_mapeado,
                    clientes_existentes, nomes_existentes
                )

                # ---- Histórico de limite de crédito ----
                usuario_hist = (self.config_db.get('user') or 'IMPORTADOR').upper()[:30]
                hist_state = {'mode': None, 'next': 1}  # mode: None (indef) / 'auto' / 'manual'

                def _gravar_historico_limite(cf_codigo, nome_cli, limite, limite_old=None):
                    # No UPDATE existe um valor anterior de verdade, e é ele que dá
                    # sentido ao histórico. (O ERP ainda registra por conta própria em
                    # TABELA_CLI_FOR_ALT_LCR, pelo trigger TRG_CLI_FOR_GERA_ALT_LCR.)
                    cols = ("HIST_EMPRESA, HIST_FILIAL, HIST_CLIENTE, HIST_CLIENTE_NOME, "
                            "HIST_LIMITE_CREDITO_OLD, HIST_LIMITE_CREDITO_NEW, "
                            "HIST_LIMITE_CREDITO_DATA_ALT, HIST_USUARIO")
                    vals = "?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?"
                    params = [emp, fil, cf_codigo, str(nome_cli)[:60], limite_old, limite,
                              usuario_hist]
                    # Tenta deixar o banco gerar o HIST_ID (trigger/generator)
                    if hist_state['mode'] != 'manual':
                        try:
                            fb.execute(f"INSERT INTO HISTORICO_LIMITE_CREDITO ({cols}) VALUES ({vals})", params)
                            hist_state['mode'] = 'auto'
                            return
                        except Exception:
                            hist_state['mode'] = 'manual'
                            try:
                                r = fb.query("SELECT COALESCE(MAX(HIST_ID), 0) AS M FROM HISTORICO_LIMITE_CREDITO")
                                hist_state['next'] = int(r[0]['m']) + 1
                            except Exception:
                                hist_state['next'] = 1
                    # Modo manual: informa o HIST_ID
                    hid = hist_state['next']
                    fb.execute(
                        f"INSERT INTO HISTORICO_LIMITE_CREDITO (HIST_ID, {cols}) VALUES (?, {vals})",
                        [hid] + params
                    )
                    hist_state['next'] = hid + 1

                # ---- Caches (evitam consulta por linha; principal causa de lentidão) ----
                self.parent.after(0, lambda: self.lbl_status.config(text="Carregando cidades e vendedores..."))

                cid_por_ibge = {}
                max_cid = 0
                for r in fb.query("SELECT CID_CODIGO, CID_CODIGO_IBGE FROM TABELA_CIDADE WHERE CID_EMPRESA=? AND CID_FILIAL=?", [emp, fil]):
                    ib = str(r['cid_codigo_ibge'] or '').strip()
                    if ib:
                        cid_por_ibge.setdefault(ib, r['cid_codigo'])
                    try:
                        max_cid = max(max_cid, int(r['cid_codigo']))
                    except (TypeError, ValueError):
                        pass

                ibge_por_desc = {}
                ibge_por_desc_uf = {}
                for r in fb.query("SELECT CIDIBGE_CODIGO, CIDIBGE_DESCRICAO, CIDIBGE_ESTADO FROM TABELA_CIDADES_IBGE"):
                    d = self._remover_acentos(str(r['cidibge_descricao'] or '')).strip().upper()
                    if not d:
                        continue
                    ibge_por_desc.setdefault(d, r['cidibge_codigo'])
                    est = str(r['cidibge_estado'] or '').strip().upper()
                    ibge_por_desc_uf.setdefault((d, est), r['cidibge_codigo'])

                vend_por_nome = {}
                vend_codigos = set()
                max_vend = 0
                vend_criados = 0      # vendedores novos cadastrados nesta rodada
                vend_vinculados = 0   # clientes que sairam com CF_REPRESENTANTE preenchido
                vend_sem = 0          # clientes sem vendedor na planilha
                vend_usados = set()
                for r in fb.query("SELECT VEND_CODIGO, VEND_NOME FROM TABELA_VENDEDOR WHERE VEND_EMPRESA=? AND VEND_FILIAL=?", [emp, fil]):
                    n = self._remover_acentos(str(r['vend_nome'] or '')).strip().upper()
                    if n:
                        vend_por_nome.setdefault(n, []).append(r['vend_codigo'])
                    try:
                        vend_codigos.add(int(r['vend_codigo']))
                        max_vend = max(max_vend, int(r['vend_codigo']))
                    except (TypeError, ValueError):
                        pass

                # Condição de pagamento e transportadora: a planilha pode trazer o
                # CÓDIGO ou a DESCRIÇÃO/NOME, então cabe um índice de cada.
                # a descrição guarda TODOS os códigos que a usam: repetida, ela não
                # identifica ninguém, e o resolvedor pede o código em vez de chutar
                cond_por_desc, cond_codigos = {}, set()
                for r in fb.query("SELECT CONDPGTO_CODIGO, CONDPDTO_DESCRICAO FROM TABELA_CONDICAOPGTO"):
                    d = self._remover_acentos(str(r['condpdto_descricao'] or '')).strip().upper()
                    if d:
                        cond_por_desc.setdefault(d, []).append(r['condpgto_codigo'])
                    try:
                        cond_codigos.add(int(r['condpgto_codigo']))
                    except (TypeError, ValueError):
                        pass

                transp_por_nome, transp_codigos = {}, set()
                try:
                    for r in fb.query("SELECT TRANS_CODIGO, TRANS_DESCRICAO FROM TABELA_TRANSPORTADORA "
                                      "WHERE TRANS_EMPRESA=? AND TRANS_FILIAL=?", [emp, fil]):
                        d = self._remover_acentos(str(r['trans_descricao'] or '')).strip().upper()
                        if d:
                            transp_por_nome.setdefault(d, []).append(r['trans_codigo'])
                        try:
                            transp_codigos.add(int(r['trans_codigo']))
                        except (TypeError, ValueError):
                            pass
                except Exception:
                    pass

                refs = {
                    'condpgto': (cond_por_desc, cond_codigos, 'Condição de pagamento'),
                    'transportadora': (transp_por_nome, transp_codigos, 'Transportadora'),
                }

                def _resolver_vendedor(valor):
                    """Vendedor por CÓDIGO ou por NOME. Devolve (codigo, aviso).

                    Nome que não existe é CADASTRADO (é como a tela sempre funcionou:
                    a planilha do cliente é a fonte da carteira). Código que não
                    existe não dá para inventar — avisa e deixa o campo de fora.
                    """
                    s = str(valor or '').strip()
                    if not s:
                        return None, None
                    n = self._inteiro(s)
                    if n is not None:
                        if n in vend_codigos:
                            return n, None
                        return None, f"Vendedor de código {s} não existe no ERP"
                    nome_sql = self._remover_acentos(s).upper()[:50]   # VEND_NOME VARCHAR(50)
                    achados = vend_por_nome.get(nome_sql) or []
                    if len(achados) > 1:
                        return None, (f"Vendedor '{s}' existe em {len(achados)} cadastros "
                                      f"({', '.join(str(c) for c in achados)}) — informe o CÓDIGO")
                    if achados:
                        return achados[0], None
                    nonlocal max_vend, vend_criados
                    try:
                        max_vend += 1
                        fb.execute("""
                            INSERT INTO TABELA_VENDEDOR (
                                VEND_EMPRESA, VEND_FILIAL, VEND_CODIGO,
                                VEND_NOME, VEND_ATIVO, VEND_COMISSAO_FATURAMENTO
                            ) VALUES (?, ?, ?, ?, 'S', 0)
                        """, [emp, fil, max_vend, nome_sql])
                        vend_por_nome[nome_sql] = [max_vend]
                        vend_codigos.add(max_vend)
                        vend_criados += 1
                        log_linhas.append(f"✅ Vendedor '{nome_sql}' criado (código {max_vend})")
                        return max_vend, None
                    except Exception as e:
                        return None, f"Erro ao criar vendedor '{s}': {e}"

                def _extras_do_item(item):
                    """(coluna, valor) dos campos EXTRA mapeados e preenchidos, + avisos.

                    Vale para o INSERT e para o UPDATE: mapear "Prazo Máximo" tem de
                    gravar nos dois, senão a coluna é lida da planilha e descartada.
                    """
                    cols, avisos = [], []
                    for chave, coluna, tipo, limite in CAMPOS_EXTRA:
                        if not self.entradas_map[chave].get().strip():
                            continue
                        bruto = str(item.get(chave, '') or '').strip()
                        if not bruto:
                            continue
                        if tipo in refs:
                            por_nome, codigos, rotulo = refs[tipo]
                            valor, aviso = self._resolver_ref(bruto, por_nome, codigos, rotulo)
                            if aviso:
                                avisos.append(aviso)
                                continue
                        elif tipo == 'inteiro':
                            valor = self._inteiro(bruto)
                            if valor is None:
                                avisos.append(f"{coluna}: '{bruto}' não é um número inteiro")
                                continue
                        elif tipo == 'decimal':
                            valor = self._decimal(bruto)
                            if valor is None:
                                avisos.append(f"{coluna}: '{bruto}' não é um número")
                                continue
                        elif tipo == 'sn':
                            valor = self._sn(bruto)
                        else:
                            valor = bruto[:limite] if limite else bruto
                        cols.append((coluna, valor, chave))
                    return cols, avisos

                total = len(selecionados)
                for _i, item in enumerate(selecionados):
                    if _i % 20 == 0:
                        self.parent.after(0, lambda d=_i, t=total: self.lbl_status.config(
                            text=f"Importando {d+1}/{t}..."))
                    acao = item.get('_plan_acao')
                    documento = item.get('documento_limpo', '')

                    # Decisões vindas do planejador (documento único / de-para por nome)
                    if acao == 'erro':
                        continue
                    if acao == 'pular_doc':
                        pulados_doc += 1
                        log_linhas.append(f"⚠ {item.get('razao', '')[:60]} — documento {documento} repetido na planilha, pulando")
                        continue
                    if acao == 'ja_cadastrado':
                        pulados_nome += 1
                        log_linhas.append(f"⚠ {item.get('razao', '')[:60]} — já cadastrado no ERP, não tocado")
                        continue
                    if acao == 'ignorado_novo':
                        ignorados_novos += 1
                        log_linhas.append(f"⚠ {item.get('razao', '')[:60]} — não existe no ERP; "
                                          f"o modo é só atualizar, pulando")
                        continue

                    razao = str(item.get('razao', '')).strip().upper()[:50]
                    razao_norm = self._remover_acentos(item.get('razao', '')).strip().upper()[:50]
                    fantasia = str(item.get('fantasia', '')).strip().upper()[:50]
                    ie = self._normalizar_ie(item.get('ie', ''))[:20]
                    endereco, numero, complemento = self._parse_endereco_completo(
                        item.get('endereco', ''),
                        item.get('numero', ''),
                        item.get('complemento', '')
                    )
                    if complemento:
                        endereco = f"{endereco}, {complemento}"[:50]
                    else:
                        endereco = endereco[:50]
                    numero = numero[:10]
                    bairro = str(item.get('bairro', '')).strip()[:50]
                    cep = re.sub(r'\D', '', str(item.get('cep', '')))[:10]
                    # Célula com mais de um valor: fica um só. Dois e-mails no
                    # CF_EMAIL_NFE fazem a SEFAZ rejeitar a nota, e dois telefones
                    # colados viravam um número de 15 dígitos que não existe.
                    fone1 = multivalor.um_fone(item.get('fone1', ''))[0][:15]
                    fone2 = multivalor.um_fone(item.get('fone2', ''))[0][:15]
                    email = multivalor.um_email(item.get('email', ''))[0][:50]
                    # flag S/N; sem coluna mapeada segue o padrão histórico ('S')
                    envia_nfe = self._sn(item.get('email_nfe', '')) or 'S'
                    for aviso in item.get('_multivalor', []):
                        log_linhas.append(f"⚠ {razao[:40]} — {aviso}")
                    uf = str(item.get('uf', '')).strip().upper()[:2]

                    tipo = item.get('_tipo', {})
                    is_cliente = 'S' if tipo.get('cliente') else 'N'
                    is_fornecedor = 'S' if tipo.get('fornecedor') else 'N'
                    is_outros = 'S' if tipo.get('outros') else 'N'

                    if not ie or ie == 'ISENTO':
                        rg_ie = 'ISENTO'
                        cf_icms = 2
                    else:
                        rg_ie = ie
                        cf_icms = 1

                    if len(documento) == 11:
                        tipo_inscr = 1
                    elif len(documento) == 14:
                        tipo_inscr = 2
                    else:
                        # Sem documento válido (ex.: CONSUMIDOR): usa 99 (evita FK -530 com tipo 0)
                        tipo_inscr = 99

                    cidade_codigo = None
                    cidade_nome = self._limpar_nome_cidade(item.get('cidade_nome', ''))
                    cidade_nome_sql = self._remover_acentos(cidade_nome).upper()
                    if cidade_nome:
                        try:
                            ibge_cod = ibge_por_desc_uf.get((cidade_nome_sql, uf)) if uf else None
                            if ibge_cod is None:
                                ibge_cod = ibge_por_desc.get(cidade_nome_sql)
                            if ibge_cod is not None:
                                ib_key = str(ibge_cod).strip()
                                cidade_codigo = cid_por_ibge.get(ib_key)
                                if cidade_codigo is None:
                                    max_cid += 1
                                    novo_cid = max_cid
                                    fb.execute("""
                                        INSERT INTO TABELA_CIDADE (
                                            CID_EMPRESA, CID_FILIAL, CID_CODIGO, CID_DESCRICAO,
                                            CID_CEP, CID_UF, CID_CODIGO_IBGE, CID_PAIS
                                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 1058)
                                    """, [emp, fil, novo_cid, cidade_nome.upper(), cep, uf, ibge_cod])
                                    cid_por_ibge[ib_key] = novo_cid
                                    cidade_codigo = novo_cid
                                    log_linhas.append(f"🏙 Cidade '{cidade_nome}' auto-cadastrada (IBGE {ibge_cod}, código {novo_cid})")
                            else:
                                log_linhas.append(f"⚠ Cidade '{cidade_nome}' não encontrada na TABELA_CIDADES_IBGE para {razao}")
                        except Exception as e:
                            log_linhas.append(f"⚠ Erro ao processar cidade '{cidade_nome}': {e}")

                    # Vendedor: procura pelo nome; se nao existe, cadastra. O codigo
                    # resultante vai para CF_REPRESENTANTE no INSERT do cliente
                    # (o ERP casa por CF_REPRESENTANTE_EMP/FILIAL + CF_REPRESENTANTE).
                    # Celula em branco => cliente fica SEM representante (NULL).
                    vendedor_codigo = None
                    vendedor_nome = str(item.get('vendedor_nome', '')).strip()
                    if vendedor_nome:
                        vendedor_codigo, aviso_vend = _resolver_vendedor(vendedor_nome)
                        if aviso_vend:
                            log_linhas.append(f"⚠ {razao[:40]} — {aviso_vend}")
                    if vendedor_codigo is not None:
                        vend_vinculados += 1
                        vend_usados.add(vendedor_codigo)
                    else:
                        vend_sem += 1

                    cf_codigo = item['_plan_codigo']

                    cgc_formatado = documento
                    if len(documento) == 11:
                        cgc_formatado = f"{documento[:3]}.{documento[3:6]}.{documento[6:9]}-{documento[9:]}"
                    elif len(documento) == 14:
                        cgc_formatado = f"{documento[:2]}.{documento[2:5]}.{documento[5:8]}/{documento[8:12]}-{documento[12:]}"

                    cf_ativo = self._parse_ativo(item.get('ativo', ''))
                    limite = self._parse_limite(item.get('limite_credito', ''))
                    cf_limite = limite  # None -> grava NULL em CF_LIMITE_CREDITO quando não há valor

                    extras, avisos_extras = _extras_do_item(item)
                    for aviso in avisos_extras:
                        log_linhas.append(f"⚠ {razao[:40]} — {aviso} (campo não atualizado)")

                    # ---------------------------------------------------- ATUALIZAR
                    if acao == 'atualizar':
                        cf_codigo = item['_plan_codigo']
                        # sem coluna de razão na planilha, o log e o histórico usam o
                        # nome que está no ERP — "atualizado: (vazio)" não diz nada
                        nome_log = razao or razoes_erp.get(cf_codigo, f"cliente {cf_codigo}")
                        sets = []

                        def por(chave, coluna, valor):
                            """Só entra no UPDATE o que está MAPEADO e PREENCHIDO.

                            Célula vazia não zera coluna: a planilha do cliente traz um
                            punhado de campos, e apagar o que ela não traz destruiria
                            cadastro em uso — que é o oposto do que se pediu.
                            """
                            if not self.entradas_map[chave].get().strip():
                                return
                            if not self._sobrescreve(chave):
                                return
                            if str(item.get(chave, '') or '').strip() == '':
                                return
                            sets.append((coluna, valor))

                        for chave, coluna in CAMPOS_SIMPLES_UPDATE:
                            valor = {'razao': razao, 'fantasia': fantasia, 'bairro': bairro,
                                     'cep': cep, 'fone1': fone1, 'fone2': fone2,
                                     'email': email, 'ativo': cf_ativo,
                                     'email_nfe': envia_nfe}[chave]
                            por(chave, coluna, valor)

                        # IE: acompanha o CF_ICMS (isento x contribuinte), como no INSERT
                        if (self.entradas_map['ie'].get().strip() and self._sobrescreve('ie')
                                and str(item.get('ie', '')).strip()):
                            sets.append(('CF_RG_IE', rg_ie))
                            sets.append(('CF_ICMS', cf_icms))
                        # endereço principal apenas; os endereços 2/3/4 podem ter sido
                        # ajustados à mão no ERP (entrega, cobrança) e não são cópia
                        if (self.entradas_map['endereco'].get().strip()
                                and self._sobrescreve('endereco') and endereco):
                            sets.append(('CF_ENDERECO', endereco))
                            if numero:
                                sets.append(('CF_NRO_END', numero))
                        if (cidade_codigo is not None and self._sobrescreve('cidade_nome')
                                and self.entradas_map['cidade_nome'].get().strip()):
                            sets.append(('CF_CIDADE', cidade_codigo))
                            sets.append(('CF_CIDADE_EMPRESA', emp))
                            sets.append(('CF_CIDADE_FILIAL', fil))
                        if vendedor_codigo is not None and self._sobrescreve('vendedor_nome'):
                            sets.append(('CF_REPRESENTANTE', vendedor_codigo))
                            sets.append(('CF_REPRESENTANTE_EMP', emp))
                            sets.append(('CF_REPRESENTANTE_FILIAL', fil))
                        if limite is not None and self._sobrescreve('limite_credito'):
                            sets.append(('CF_LIMITE_CREDITO', limite))
                        # tipo (cliente/fornecedor/outros) só muda se o usuário marcou
                        # alguma das três colunas na grade desta linha
                        if any(tipo.values()):
                            sets += [('CF_CLIENTE', is_cliente), ('CF_FORNECEDOR', is_fornecedor),
                                     ('CF_OUTROS', is_outros)]
                        # os extras também obedecem ao ✎ de cada campo
                        sets += [(c, v) for c, v, chave in extras if self._sobrescreve(chave)]

                        if not sets:
                            log_linhas.append(f"⚠ {nome_log} (cod {cf_codigo}) — nada preenchido "
                                              f"para atualizar, nada foi feito")
                            continue
                        try:
                            colunas_sql = ", ".join(f"{c} = ?" for c, _ in sets)
                            fb.execute(
                                f"UPDATE TABELA_CLI_FOR SET {colunas_sql} "
                                f"WHERE CF_EMPRESA = ? AND CF_FILIAL = ? AND CF_CODIGO = ?",
                                [v for _, v in sets] + [emp, fil, cf_codigo]
                            )
                            atualizados += 1
                            campos_tocados += len(sets)
                            log_linhas.append(
                                f"🔄 {nome_log} (cod {cf_codigo}, casou por {item.get('_casou_por')}) "
                                f"atualizado: " + ", ".join(f"{c}={v}" for c, v in sets))
                            if limite is not None:
                                try:
                                    _gravar_historico_limite(cf_codigo, nome_log, limite,
                                                             limite_atual.get(cf_codigo))
                                    log_linhas.append(
                                        f"   💳 Limite {limite_atual.get(cf_codigo)} → {limite:.2f} "
                                        f"(histórico gravado)")
                                except Exception as e_lim:
                                    log_linhas.append(f"   ⚠ Falha ao gravar histórico de limite: {e_lim}")
                        except Exception as e:
                            erros += 1
                            log_linhas.append(f"❌ Erro ao atualizar {nome_log} (cod {cf_codigo}): {e}")
                        continue

                    try:
                        # as colunas extra mapeadas entram no fim do INSERT: mapear
                        # "Cond. Pagto" e ver o campo em branco no cadastro novo seria
                        # o mesmo descarte silencioso de antes
                        cols_extra = "".join(f", {c}" for c, _v, _k in extras)
                        vals_extra = ", ?" * len(extras)
                        fb.execute(f"""
                            INSERT INTO TABELA_CLI_FOR (
                                CF_EMPRESA, CF_FILIAL, CF_CODIGO,
                                CF_DATA, CF_DATA_ALT,
                                CF_CPF_CGC, CF_RAZAO, CF_FANTASIA,
                                CF_ATIVO, CF_TIPO_INSCR,
                                CF_CLIENTE, CF_FORNECEDOR, CF_OUTROS,
                                CF_RG_IE, CF_ICMS, CF_ATIVIDADE,
                                CF_ENDERECO, CF_NRO_END, CF_BAIRRO,
                                CF_CIDADE, CF_CEP,
                                CF_ENDERECO2, CF_NRO_END2, CF_BAIRRO2,
                                CF_CIDADE2, CF_CEP2,
                                CF_ENDERECO3, CF_BAIRRO3, CF_CIDADE3, CF_CEP3,
                                CF_ENDERECO4, CF_BAIRRO4, CF_CIDADE4, CF_CEP4,
                                CF_CIDADE_EMPRESA, CF_CIDADE_FILIAL,
                                CF_REPRESENTANTE_EMP, CF_REPRESENTANTE_FILIAL, CF_REPRESENTANTE,
                                CF_FONE1, CF_FONE2, CF_FAX,
                                CF_EMAIL,
                                CF_EMAIL_NFE,
                                CF_COD_ANTIGO,
                                CF_LIMITE_CREDITO{cols_extra}
                            ) VALUES (
                                ?, ?, ?,
                                CURRENT_DATE, CURRENT_DATE,
                                ?, ?, ?,
                                ?, ?,
                                ?, ?, ?,
                                ?, ?, 1,
                                ?, ?, ?,
                                ?, ?,
                                ?, ?, ?,
                                ?, ?,
                                ?, ?, ?, ?,
                                ?, ?, ?, ?,
                                ?, ?,
                                ?, ?, ?,
                                ?, ?, '',
                                ?,
                                ?,
                                NULL,
                                ?{vals_extra}
                            )
                        """, [
                            emp, fil, cf_codigo,
                            cgc_formatado, razao, fantasia,
                            cf_ativo, tipo_inscr, is_cliente, is_fornecedor, is_outros,
                            rg_ie, cf_icms,
                            endereco, numero, bairro,
                            cidade_codigo, cep,
                            endereco, numero, bairro,
                            cidade_codigo, cep,
                            endereco, bairro, cidade_codigo, cep,
                            endereco, bairro, cidade_codigo, cep,
                            emp, fil,
                            emp, fil, vendedor_codigo,
                            fone1, fone2,
                            email,
                            envia_nfe,
                            cf_limite,
                        ] + [v for _c, v, _k in extras])
                        inseridos += 1
                        codigos_usados.add(cf_codigo)
                        if item.get('_plan_remap'):
                            remapeados += 1
                            log_linhas.append(
                                f"✅ {razao} — código {item.get('_cod_orig')} estava ocupado → gravado como {cf_codigo}"
                            )
                        else:
                            log_linhas.append(f"✅ {razao} (cod {cf_codigo}) inserido com sucesso")
                        if documento:
                            dados_existentes['documentos'][documento] = cf_codigo
                        if razao_norm:
                            dados_existentes['nomes'][razao_norm] = cf_codigo

                        if limite is not None:
                            try:
                                _gravar_historico_limite(cf_codigo, razao, limite)
                                log_linhas.append(f"   💳 Limite de crédito {limite:.2f} gravado (CF_LIMITE_CREDITO + histórico)")
                            except Exception as e_lim:
                                log_linhas.append(f"   ⚠ Falha ao gravar histórico de limite de {razao}: {e_lim}")
                    except Exception as e:
                        erros += 1
                        log_linhas.append(f"❌ Erro ao inserir {razao}: {e}")

                total_sel = len(selecionados)
                pulados = pulados_doc + pulados_nome + ignorados_novos
                conta = (total_sel == inseridos + atualizados + pulados + erros)
                msg = (
                    f"Processamento concluído!\n\n"
                    f"Selecionados:         {total_sel}\n"
                    f"Inseridos:            {inseridos}\n"
                    f"  dos quais remanej.: {remapeados}\n"
                    f"Atualizados:          {atualizados}\n"
                    f"  colunas gravadas:   {campos_tocados}\n"
                    f"Pulados (doc repet.): {pulados_doc}\n"
                    f"Pulados (já no ERP):  {pulados_nome}\n"
                    f"Ignorados (novos):    {ignorados_novos}\n"
                    f"Erros:                {erros}\n"
                    f"\n"
                    f"Vendedor vinculado:   {vend_vinculados} cliente(s) "
                    f"em {len(vend_usados)} vendedor(es)\n"
                    f"  vendedores criados: {vend_criados}\n"
                    f"  sem vendedor:       {vend_sem}\n"
                )
                if not conta:
                    msg += (f"\n(atenção: {total_sel} ≠ {inseridos}+{atualizados}+"
                            f"{pulados}+{erros})")
                if erros:
                    msg += "\nHouve erro(s) — veja o log para detalhes."
                self.parent.after(0, lambda m=msg: self._safe_showinfo("Concluído", m))

                resumo = (
                    f"RESUMO ({self._modo()}): selecionados={total_sel} | "
                    f"inseridos={inseridos} "
                    f"(remanejados={remapeados}) | "
                    f"atualizados={atualizados} ({campos_tocados} colunas) | "
                    f"pulados(doc repetido)={pulados_doc} | "
                    f"pulados(já no ERP)={pulados_nome} | "
                    f"ignorados(novos)={ignorados_novos} | erros={erros} | "
                    f"vendedor vinculado={vend_vinculados} (criados={vend_criados}, "
                    f"sem vendedor={vend_sem})"
                )
                log_linhas.insert(0, resumo)
                log_linhas.insert(1, "")
                log_str = "\n".join(log_linhas)
                self.parent.after(0, lambda l=log_str: self._oferecer_log(l))

                dados_existentes['codigos'] = {str(c) for c in codigos_usados}
                self.parent.after(0, lambda de=dados_existentes: self._renderizar_preview(de))

        except Exception as e:
            self.parent.after(0, lambda err=e: self._safe_showerror("Erro de Importação", f"Ocorreu um erro estrutural:\n{err}"))
        finally:
            self.parent.after(0, lambda: self._resetar_ui())
            self.parent.after(0, lambda: self.lbl_status.config(text="Pronto."))

    def _safe_showinfo(self, titulo, msg):
        try:
            if self.winfo_exists():
                messagebox.showinfo(titulo, msg, parent=self)
        except tk.TclError:
            pass

    def _safe_showerror(self, titulo, msg):
        try:
            if self.winfo_exists():
                messagebox.showerror(titulo, msg, parent=self)
        except tk.TclError:
            pass

    def _resetar_ui(self):
        try:
            if self.btn_analisar.winfo_exists():
                self.btn_analisar.config(state=tk.NORMAL)
        except tk.TclError:
            pass
        try:
            if self.btn_importar.winfo_exists():
                self.btn_importar.config(state=tk.NORMAL)
        except tk.TclError:
            pass

    def _oferecer_log(self, log_str):
        if not log_str.strip():
            return
        resp = messagebox.askyesno("Log da Importação",
            "Deseja salvar um arquivo .txt com o log detalhado da importação?")
        if resp:
            caminho = filedialog.asksaveasfilename(
                defaultextension=".txt",
                initialfile="LOG_IMPORTACAO_CLIENTES.txt",
                filetypes=[("Arquivos de Texto", "*.txt")]
            )
            if caminho:
                try:
                    with open(caminho, 'w', encoding='utf-8') as f:
                        f.write("--- LOG DE IMPORTACAO DE CLIENTES VIA PLANILHA ---\n\n")
                        f.write(log_str)
                    messagebox.showinfo("Log Salvo", f"Arquivo salvo em:\n{caminho}")
                    if messagebox.askyesno("Abrir Log", "Deseja abrir o arquivo de log agora?"):
                        try:
                            os.startfile(caminho)
                        except Exception as e:
                            messagebox.showerror("Erro", f"Erro ao abrir arquivo:\n{e}")
                except Exception as e:
                    messagebox.showerror("Erro", f"Erro ao salvar log:\n{e}")

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
    ("Email NF-e", "email_nfe", False),
    ("Vendedor (nome)", "vendedor_nome", False),
    ("Limite de Crédito", "limite_credito", False),
    ("Ativo (S/N)", "ativo", False),
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

        # === COLUMN MAPPING (responsivo: reflui conforme a largura) ===
        self.frame_map = ttk.LabelFrame(content, text="Mapeamento de Colunas (Insira a letra: A, B, C...)", padding="8")
        self.frame_map.pack(fill=tk.X, pady=4)

        self.entradas_map = {}
        self._map_cells = []
        for (lbl_texto, chave, obrigatorio) in CAMPOS_DISPONIVEIS:
            cell = ttk.Frame(self.frame_map)
            fg_color = "#C8001E" if obrigatorio else "#1A1A1A"
            tk.Label(cell, text=lbl_texto, font=("Segoe UI", 8, "bold"),
                     fg=fg_color).pack(side=tk.LEFT, padx=(0, 4))
            ent = ttk.Entry(cell, width=5, font=("Segoe UI", 9))
            ent.pack(side=tk.LEFT)
            self.entradas_map[chave] = ent
            self._map_cells.append(cell)

        self._map_cols = 0
        self.frame_map.bind("<Configure>", self._on_map_resize)
        self.after(100, self._on_map_resize)

        # === ACTIONS + PROGRESS ===
        actions_row = ttk.Frame(content)
        actions_row.pack(fill=tk.X, pady=4)

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
                                              values=["Todos", "OK", "ERRO", "JÁ CADASTRADO",
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
        for chave, ent in self.entradas_map.items():
            config.set(secao, f'map_{chave}', ent.get().strip())
        with open('config.ini', 'w', encoding='utf-8') as f:
            config.write(f)
        self.config = config

    def _carregar_config_mapeamento(self):
        secao = 'IMPORTACAO_CLIENTES'
        if not self.config.has_section(secao):
            return
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
        largura = self.frame_map.winfo_width()
        if largura <= 1:
            return
        por_campo = 205  # px por campo, largo o suficiente p/ o maior rótulo caber inteiro
        cols = max(1, (largura - 24) // por_campo)
        cols = min(cols, len(self._map_cells))
        if cols == self._map_cols:
            return
        self._map_cols = cols
        self._reflow_mapa(cols)

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
        if not mapa_colunas.get('razao'):
            return messagebox.showwarning("Aviso", "Você precisa mapear obrigatoriamente a coluna 'Razão Social'.")

        self._salvar_config_mapeamento()
        self.btn_analisar.config(state=tk.DISABLED)
        self.btn_selecionar.config(state=tk.DISABLED)
        self.lbl_status.config(text="Lendo planilha...")
        self.progresso['value'] = 20

        threading.Thread(target=self._analisar_bg, args=(aba, mapa_colunas, linha_ini), daemon=True).start()

    def _analisar_bg(self, aba, mapa_colunas, linha_ini):
        try:
            self.registros_lidos = ler_planilha_produtos(self.caminho_arquivo, aba, mapa_colunas, linha_ini)
            dados_existentes = {'documentos': {}, 'nomes': {}, 'codigos': set()}
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
                        doc = re.sub(r'\D', '', str(row['cf_cpf_cgc'] or ''))
                        if doc:
                            dados_existentes['documentos'][doc] = True
                        nome = self._remover_acentos(str(row['cf_razao'] or '')).strip().upper()
                        if nome:
                            dados_existentes['nomes'][nome] = True
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

    def _planejar_codigos(self, itens, codigos_ocupados, docs_db, nomes_db, codigo_mapeado):
        """
        Define o código final de cada item em DUAS passadas, sem cascata:
          1) reserva os códigos da planilha que ainda estão LIVRES no sistema;
          2) os que colidem (código já ocupado no sistema ou já reservado) recebem
             o MENOR número livre disponível, respeitando os reservados.
        Também aplica a unicidade de documento (CF_CPF_CGC) e o de-para por nome.
        Marca em cada item: _plan_acao ('inserir'|'pular_doc'|'pular_nome'|'erro'),
        _plan_codigo (int), _cod_orig (int|None) e _plan_remap (bool).
        """
        existentes = set()
        for c in codigos_ocupados:
            cs = re.sub(r'\D', '', str(c))
            if cs:
                existentes.add(int(cs))

        reservados = set()
        conflitos = []
        docs_seen = set(docs_db)
        nomes_seen = set(nomes_db)

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

            if not razao:
                it['_plan_acao'] = 'erro'
                continue
            if documento and documento in docs_seen:
                it['_plan_acao'] = 'pular_doc'
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
                if (not codigo_mapeado) and (not documento) and razao_norm and razao_norm in nomes_seen:
                    it['_plan_acao'] = 'pular_nome'
                    continue
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
            set(docs_existentes.keys()), set(nomes_existentes.keys()), codigo_mapeado
        )

        self._contagem = {'ok': 0, 'ja': 0, 'doc_rep': 0, 'remap': 0, 'multi': 0}
        items = []
        validos = 0
        for reg in self.registros_lidos:
            documento = reg.get('documento_limpo', '')
            razao = str(reg.get('razao', '')).strip()
            acao = reg.get('_plan_acao')
            cod_sheet = re.sub(r'\D', '', str(reg.get('cf_codigo', '')).strip())

            if acao == 'erro':
                status = "ERRO (Sem Razão Social)"
            elif acao == 'pular_doc':
                if documento and documento in docs_existentes:
                    status = "JÁ CADASTRADO"            # documento já existe no ERP
                    self._contagem['ja'] += 1
                else:
                    status = "DOC. REPETIDO"             # documento repetido na própria planilha
                    self._contagem['doc_rep'] += 1
            elif acao == 'pular_nome':
                status = "JÁ CADASTRADO"
                self._contagem['ja'] += 1
            else:  # inserir
                status = "OK"
                validos += 1
                self._contagem['ok'] += 1
                if reg.get('_plan_remap'):
                    self._contagem['remap'] += 1

            reg['_status'] = status
            check = "☑" if status == "OK" else "☐"

            pode_editar = status == "OK"
            if pode_editar:
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
            ativo_fmt = "Ativo" if ativo_flag == 'S' else "Inativo"

            cod_final = reg.get('_plan_codigo')
            if acao != 'inserir':
                cod_fmt = cod_sheet or "-"
            elif reg.get('_plan_remap'):
                cod_fmt = f"{reg.get('_cod_orig')}→{cod_final}"   # antigo ocupado, remanejado
            elif not cod_sheet:
                cod_fmt = f"{cod_final} (auto)"                   # sem código na planilha
            else:
                cod_fmt = str(cod_final)                          # manteve o código antigo

            # linha âmbar quando alguma célula trazia mais de um valor: o cadastro
            # entra, mas com um valor só, e isso tem de ficar visível antes de gravar
            if status == 'OK':
                if reg.get('_multivalor'):
                    tag = 'AVISO'
                    self._contagem['multi'] += 1
                else:
                    tag = 'OK'
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
                self.lbl_status.config(
                    text=(f"Pronto. {validos} novos de {total} lidos · "
                          f"já cadastrados: {c.get('ja', 0)} · "
                          f"doc. repetido: {c.get('doc_rep', 0)} · "
                          f"remanejados: {c.get('remap', 0)}{extra}")
                )
                self.cb_filtro_status.current(0)
                self._filtrar_status()

        render_chunk(0)

    def _on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            item_id = self.tree.identify_row(event.y)
            if not item_id: return
            valores = list(self.tree.item(item_id, 'values'))

            if "ERRO" in valores[1] or "JÁ CADASTRADO" in valores[1]:
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

                if not any(tipo.values()):
                    tipo['outros'] = True

                self._pintar_tipo(item_id, tipo, valores)

    def _marcar_todos(self):
        for item in self.tree.get_children():
            v = list(self.tree.item(item, "values"))
            if "ERRO" not in v[1]:
                v[0] = "☑"
                self.tree.item(item, values=v)

    def _desmarcar_todos(self):
        for item in self.tree.get_children():
            v = list(self.tree.item(item, "values"))
            if "ERRO" not in v[1]:
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
            if "ERRO" in v[1] or "JÁ CADASTRADO" in v[1]:
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
            if (filtro == "Todos" or status == filtro
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

        resp = messagebox.askyesno("Confirmar",
            f"Deseja injetar os {len(selecionados)} clientes selecionados no Banco de Dados?\n"
            "Essa ação não pode ser desfeita.")
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

                sql_clientes = "SELECT CF_CPF_CGC, CF_CODIGO, CF_RAZAO FROM TABELA_CLI_FOR WHERE CF_EMPRESA = ? AND CF_FILIAL = ?"
                clientes_existentes = {}
                nomes_existentes = {}
                for row in fb.query(sql_clientes, [emp, fil]):
                    doc = re.sub(r'\D', '', str(row['cf_cpf_cgc'] or ''))
                    if doc:
                        clientes_existentes[doc] = row['cf_codigo']
                    nome = self._remover_acentos(str(row['cf_razao'] or '')).strip().upper()
                    if nome:
                        nomes_existentes[nome] = row['cf_codigo']

                inseridos = 0
                erros = 0
                atualizados = 0
                remapeados = 0    # códigos que estavam ocupados e foram remanejados
                pulados_doc = 0   # documento repetido/já cadastrado
                pulados_nome = 0  # nome já cadastrado (sem documento)
                codigo_mapeado = bool(self.entradas_map['cf_codigo'].get().strip())

                dados_existentes = {
                    'documentos': {doc: True for doc in clientes_existentes},
                    'nomes': {nome: True for nome in nomes_existentes}
                }

                # Planeja os códigos finais dos selecionados (autoritativo, com base atual do ERP)
                self._planejar_codigos(
                    selecionados, codigos_usados,
                    set(clientes_existentes.keys()), set(nomes_existentes.keys()), codigo_mapeado
                )

                # ---- Histórico de limite de crédito ----
                usuario_hist = (self.config_db.get('user') or 'IMPORTADOR').upper()[:30]
                hist_state = {'mode': None, 'next': 1}  # mode: None (indef) / 'auto' / 'manual'

                def _gravar_historico_limite(cf_codigo, nome_cli, limite):
                    cols = ("HIST_EMPRESA, HIST_FILIAL, HIST_CLIENTE, HIST_CLIENTE_NOME, "
                            "HIST_LIMITE_CREDITO_OLD, HIST_LIMITE_CREDITO_NEW, "
                            "HIST_LIMITE_CREDITO_DATA_ALT, HIST_USUARIO")
                    vals = "?, ?, ?, ?, NULL, ?, CURRENT_TIMESTAMP, ?"
                    params = [emp, fil, cf_codigo, str(nome_cli)[:60], limite, usuario_hist]
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
                max_vend = 0
                vend_criados = 0      # vendedores novos cadastrados nesta rodada
                vend_vinculados = 0   # clientes que sairam com CF_REPRESENTANTE preenchido
                vend_sem = 0          # clientes sem vendedor na planilha
                vend_usados = set()
                for r in fb.query("SELECT VEND_CODIGO, VEND_NOME FROM TABELA_VENDEDOR WHERE VEND_EMPRESA=? AND VEND_FILIAL=?", [emp, fil]):
                    n = self._remover_acentos(str(r['vend_nome'] or '')).strip().upper()
                    if n:
                        vend_por_nome.setdefault(n, r['vend_codigo'])
                    try:
                        max_vend = max(max_vend, int(r['vend_codigo']))
                    except (TypeError, ValueError):
                        pass

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
                        log_linhas.append(f"⚠ {item.get('razao', '')[:60]} — documento {documento} repetido/já cadastrado, pulando")
                        continue
                    if acao == 'pular_nome':
                        pulados_nome += 1
                        log_linhas.append(f"⚠ {item.get('razao', '')[:60]} — nome já cadastrado, pulando")
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
                    email_nfe = multivalor.um_email(item.get('email_nfe', ''))[0][:50]
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
                        # VEND_NOME e VARCHAR(50) NOT NULL
                        vendedor_nome_sql = self._remover_acentos(vendedor_nome).upper()[:50]
                        try:
                            vendedor_codigo = vend_por_nome.get(vendedor_nome_sql)
                            if vendedor_codigo is None:
                                max_vend += 1
                                novo_cod = max_vend
                                fb.execute("""
                                    INSERT INTO TABELA_VENDEDOR (
                                        VEND_EMPRESA, VEND_FILIAL, VEND_CODIGO,
                                        VEND_NOME, VEND_ATIVO, VEND_COMISSAO_FATURAMENTO
                                    ) VALUES (?, ?, ?, ?, 'S', 0)
                                """, [emp, fil, novo_cod, vendedor_nome_sql])
                                vend_por_nome[vendedor_nome_sql] = novo_cod
                                vendedor_codigo = novo_cod
                                vend_criados += 1
                                log_linhas.append(f"✅ Vendedor '{vendedor_nome_sql}' criado (código {novo_cod})")
                        except Exception as e:
                            log_linhas.append(f"⚠ Erro vendedor '{vendedor_nome}': {e}")
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

                    try:
                        fb.execute("""
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
                                CF_LIMITE_CREDITO
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
                                'S',
                                NULL,
                                ?
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
                            cf_limite,
                        ])
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
                            dados_existentes['documentos'][documento] = True
                        if razao_norm:
                            dados_existentes['nomes'][razao_norm] = True

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
                pulados = pulados_doc + pulados_nome
                conta = (total_sel == inseridos + pulados + erros)
                msg = (
                    f"Processamento concluído!\n\n"
                    f"Selecionados:         {total_sel}\n"
                    f"Inseridos:            {inseridos}\n"
                    f"  dos quais remanej.: {remapeados}\n"
                    f"Pulados (doc repet.): {pulados_doc}\n"
                    f"Pulados (nome):       {pulados_nome}\n"
                    f"Erros:                {erros}\n"
                    f"\n"
                    f"Vendedor vinculado:   {vend_vinculados} cliente(s) "
                    f"em {len(vend_usados)} vendedor(es)\n"
                    f"  vendedores criados: {vend_criados}\n"
                    f"  sem vendedor:       {vend_sem}\n"
                )
                if not conta:
                    msg += f"\n(atenção: {total_sel} ≠ {inseridos}+{pulados}+{erros})"
                if erros:
                    msg += "\nHouve erro(s) — veja o log para detalhes."
                self.parent.after(0, lambda m=msg: self._safe_showinfo("Concluído", m))

                resumo = (
                    f"RESUMO: selecionados={total_sel} | inseridos={inseridos} "
                    f"(remanejados={remapeados}) | pulados(doc)={pulados_doc} | "
                    f"pulados(nome)={pulados_nome} | erros={erros} | "
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

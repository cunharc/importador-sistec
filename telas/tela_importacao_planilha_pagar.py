import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import configparser
import threading
import re
import os
import unicodedata
import datetime

from utils.excel_reader import obter_abas_planilha, ler_planilha_produtos
from utils.firebird_service import FirebirdService
from utils import tema
from utils import rateio_contabil
from utils import multivalor

CAMPOS_DISPONIVEIS = [
    ("N\u00famero Documento *", "numero_doc", True),
    ("Parcela", "parcela", False),
    ("Fornecedor (CNPJ/CPF)", "documento", False),
    ("Fornecedor (Raz\u00e3o Social)", "razao", False),
    ("Valor da Conta *", "valor", True),
    ("Valor Pago", "valor_recebido", False),
    ("Valor a Pagar", "valor_a_pagar", False),
    ("Data Emiss\u00e3o", "emissao", False),
    ("Vencimento", "vencimento", False),
    ("Data Registro", "data_registro", False),
    ("Data Pagamento", "data_recebimento", False),
    ("Desconto", "desconto", False),
    ("Juros e Multa", "juros", False),
    ("S\u00e9rie", "serie", False),
    ("N\u00famero Boleto", "boleto", False),
    ("Observa\u00e7\u00e3o", "observacao", False),
    ("Situa\u00e7\u00e3o / Status", "situacao_status", False),
]

SERIE_PADRAO = "IMP"

# Valores da coluna "Situa\u00e7\u00e3o / Status" que marcam o t\u00edtulo como cancelado.
# S\u00f3 agem quando essa coluna est\u00e1 mapeada.
STATUS_CANCELADO = {"CANCELADO", "CANCELADA", "CANCEL", "CANCELED",
                    "INATIVO", "INATIVA", "ESTORNADO", "ESTORNADA"}

# EXCLUIDO/SUBSTITUIDO N\u00c3O s\u00e3o descartados: entram baixados na data de emiss\u00e3o
# (valor total quitado no dia da emiss\u00e3o) com o STATUS na observa\u00e7\u00e3o do t\u00edtulo.
# Assim comp\u00f5em o total do banco do cliente sem inflar o "em aberto".
STATUS_EXCLUIR = {"EXCLUIDO", "EXCLUIDA", "SUBSTITUIDO", "SUBSTITUIDA"}


class DialogoFornecedoresNaoEncontrados(tk.Toplevel):
    """Pop-up que lista os fornecedores buscados por nome e nao localizados no cadastro,
    permitindo cadastra-los como fornecedor 'Outros' (sem documento) antes da importacao."""
    def __init__(self, parent, faltantes):
        super().__init__(parent)
        self.title("Fornecedores nao encontrados")
        w = min(560, int(self.winfo_screenwidth() * 0.6))
        h = min(560, int(self.winfo_screenheight() * 0.7))
        self.geometry(f"{w}x{h}")
        self.minsize(420, 380)
        self.transient(parent)
        self.grab_set()

        # faltantes: dict {nome: qtd_titulos}
        self.faltantes = sorted(faltantes.items(), key=lambda x: x[0].lower())
        self._nomes = [nome for nome, _ in self.faltantes]
        self.selecionados = None
        self.acao = None

        self._criar_widgets()
        tema.centralizar(self, w, h)

    def _criar_widgets(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill=tk.X)
        ttk.Label(top, text="Fornecedores nao localizados no cadastro",
                  font=("Segoe UI", 12, "bold")).pack(anchor=tk.W)
        ttk.Label(top, justify=tk.LEFT, foreground="#555",
                  text=("Estes fornecedores foram buscados por nome e nao existem no cadastro.\n"
                        "Marque os que deseja cadastrar como fornecedor 'Outros' (sem CNPJ/CPF).\n"
                        "Os que ficarem desmarcados terao suas linhas puladas na importacao.")
                  ).pack(anchor=tk.W, pady=(4, 0))

        frame_list = ttk.Frame(self, padding=(10, 0))
        frame_list.pack(fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(frame_list, orient=tk.VERTICAL)
        self.lb = tk.Listbox(frame_list, selectmode=tk.EXTENDED, yscrollcommand=sb.set)
        sb.config(command=self.lb.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        for nome, qtd in self.faltantes:
            self.lb.insert(tk.END, f"{nome}   ({qtd} titulo(s))")
        self.lb.selection_set(0, tk.END)

        sel_row = ttk.Frame(self, padding=(10, 4))
        sel_row.pack(fill=tk.X)
        ttk.Button(sel_row, text="Marcar Todos",
                   command=lambda: self.lb.selection_set(0, tk.END)).pack(side=tk.LEFT, padx=2)
        ttk.Button(sel_row, text="Desmarcar",
                   command=lambda: self.lb.selection_clear(0, tk.END)).pack(side=tk.LEFT, padx=2)

        bot = ttk.Frame(self, padding=10)
        bot.pack(fill=tk.X)
        ttk.Button(bot, text="Cancelar importacao", command=self._cancelar).pack(side=tk.LEFT)
        ttk.Button(bot, text="Cadastrar marcados e continuar",
                   command=self._confirmar, style="Accent.TButton").pack(side=tk.RIGHT)

    def _confirmar(self):
        idxs = self.lb.curselection()
        self.selecionados = [self._nomes[i] for i in idxs]
        self.acao = 'continuar'
        self.destroy()

    def _cancelar(self):
        self.acao = 'cancelar'
        self.destroy()


class TelaImportacaoPlanilhaPagar(ttk.Frame):
    def __init__(self, parent, callback_voltar=None):
        super().__init__(parent, padding="10")
        self.parent = parent
        self.callback_voltar = callback_voltar
        self.pack(fill=tk.BOTH, expand=True)

        self.registros_lidos = []
        self.caminho_arquivo = ""
        self.dados_grid = {}
        self._sort_directions = {}
        self.locais_cobranca = {}

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
        # Header do m\u00f3dulo (identidade Sistecweb)
        tema.montar_header(
            self, "Importar Contas a Pagar (Excel)",
            "Importa\u00e7\u00e3o de t\u00edtulos e parcelas de contas a pagar via planilha (XLSX/CSV)"
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

        self.btn_analisar = tema.botao_sidebar(sidebar, "\ud83d\udd0d   Carregar e Analisar Planilha",
                                               self._iniciar_analise)
        self.btn_analisar.pack(fill=tk.X)

        self.btn_importar = tema.botao_sidebar(sidebar, "\ud83d\ude80   Processar e Injetar no ERP",
                                               self._iniciar_importacao, cor_fg="#7EE0A0")
        self.btn_importar.config(state=tk.DISABLED)
        self.btn_importar.pack(fill=tk.X)

        # -------- CONTE\u00daDO --------
        content = tk.Frame(corpo, bg=tema.BG_BASE)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=16, pady=12)

        file_row = ttk.Frame(content)
        file_row.pack(fill=tk.X, pady=2)

        tk.Label(file_row, text="Arquivo:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 2))
        self.ent_arquivo = ttk.Entry(file_row, font=("Segoe UI", 9))
        self.ent_arquivo.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        ttk.Button(file_row, text="📁 Selecionar", command=self._selecionar_arquivo).pack(side=tk.LEFT, padx=2)

        tk.Label(file_row, text="Aba:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(10, 2))
        self.cb_abas = ttk.Combobox(file_row, width=16, state="readonly", font=("Segoe UI", 9))
        self.cb_abas.pack(side=tk.LEFT, padx=2)

        tk.Label(file_row, text="Linha Inicial:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(10, 2))
        self.ent_linha_ini = ttk.Entry(file_row, width=6, font=("Segoe UI", 9))
        self.ent_linha_ini.insert(0, "2")
        self.ent_linha_ini.pack(side=tk.LEFT, padx=2)

        frame_map = ttk.LabelFrame(content, text="Mapeamento de Colunas (Insira a letra: A, B, C...)", padding="8")
        frame_map.pack(fill=tk.X, pady=4)

        self.entradas_map = {}
        linhas_campos = [CAMPOS_DISPONIVEIS[i:i+4] for i in range(0, len(CAMPOS_DISPONIVEIS), 4)]
        for i_linha, grupo in enumerate(linhas_campos):
            for i_col, (lbl_texto, chave, obrigatorio) in enumerate(grupo):
                col = i_col * 2
                fg_color = "#C8001E" if obrigatorio else "#1A1A1A"
                tk.Label(frame_map, text=lbl_texto, font=("Segoe UI", 8, "bold"),
                         fg=fg_color).grid(row=i_linha, column=col, padx=(5, 1), pady=2, sticky=tk.E)
                ent = ttk.Entry(frame_map, width=4, font=("Segoe UI", 9))
                ent.grid(row=i_linha, column=col + 1, padx=(0, 5), pady=2, sticky=tk.W)
                self.entradas_map[chave] = ent

        actions_row = ttk.Frame(content)
        actions_row.pack(fill=tk.X, pady=4)

        ttk.Button(actions_row, text="☑ Marcar Todos", command=self._marcar_todos).pack(side=tk.LEFT, padx=3)
        ttk.Button(actions_row, text="☐ Desmarcar", command=self._desmarcar_todos).pack(side=tk.LEFT, padx=3)

        self.progresso = ttk.Progressbar(actions_row, orient=tk.HORIZONTAL, mode='determinate', length=120)
        self.progresso.pack(side=tk.LEFT, padx=8)

        self.lbl_status = ttk.Label(actions_row, text="Aguardando configura\u00e7\u00e3o...", font=("Segoe UI", 9), foreground="#555")
        self.lbl_status.pack(side=tk.LEFT, padx=2)

        filter_row = ttk.Frame(content)
        filter_row.pack(fill=tk.X, pady=(2, 0))

        tk.Label(filter_row, text="Filtrar Status:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 2))
        self.cb_filtro_status = ttk.Combobox(filter_row, values=["Todos", "OK", "ERRO", "J\u00c1 CADASTRADO"],
                                              state="readonly", width=14, font=("Segoe UI", 9))
        self.cb_filtro_status.current(0)
        self.cb_filtro_status.pack(side=tk.LEFT, padx=2)
        self.cb_filtro_status.bind("<<ComboboxSelected>>", self._filtrar_grade)

        tk.Label(filter_row, text="Filtrar Situa\u00e7\u00e3o:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(10, 2))
        self.cb_filtro_situacao = ttk.Combobox(filter_row, values=["Todas", "Aberto", "Parcial", "Pago", "Cancelado"],
                                               state="readonly", width=12, font=("Segoe UI", 9))
        self.cb_filtro_situacao.current(0)
        self.cb_filtro_situacao.pack(side=tk.LEFT, padx=2)
        self.cb_filtro_situacao.bind("<<ComboboxSelected>>", self._filtrar_grade)

        tk.Label(filter_row, text="Local Cobran\u00e7a:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(10, 2))
        self.cb_local_cobranca = ttk.Combobox(filter_row, state="readonly", width=24, font=("Segoe UI", 9))
        self.cb_local_cobranca.pack(side=tk.LEFT, padx=2)
        self._carregar_locais_cobranca()

        # Rateio gerencial/contabil do titulo (opcional, 100% no valor). Em linha
        # propria porque a filter_row ja passa da largura numa tela de servidor.
        rateio_row = ttk.Frame(content)
        rateio_row.pack(fill=tk.X, pady=2)
        tk.Label(rateio_row, text="Centro de custo:",
                 font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 2))
        self.cb_centro_custo = ttk.Combobox(rateio_row, state="readonly", width=30,
                                            font=("Segoe UI", 9))
        self.cb_centro_custo.pack(side=tk.LEFT, padx=2)
        tk.Label(rateio_row, text="Conta contábil:",
                 font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(12, 2))
        self.cb_conta_contabil = ttk.Combobox(rateio_row, state="readonly", width=34,
                                              font=("Segoe UI", 9))
        self.cb_conta_contabil.pack(side=tk.LEFT, padx=2)
        ttk.Button(rateio_row, text="↻", width=3,
                   command=self._carregar_rateio).pack(side=tk.LEFT, padx=(4, 0))
        tk.Label(rateio_row, text="(opcional — vai no título importado)",
                 font=("Segoe UI", 8), fg="#555").pack(side=tk.LEFT, padx=(6, 0))
        self._exercicio_contabil = None
        self._conta_reduzido = {}
        self._carregar_rateio()

        # Virada de ano: titulo emitido em 2022 com parcela vencendo em 2023 fica
        # bloqueado como JA CADASTRADO. Ligado, confere parcela a parcela.
        self.var_trazer_parcelas = tk.BooleanVar(value=False)
        ttk.Checkbutton(filter_row, text="Trazer parcelas novas de t\u00edtulos j\u00e1 cadastrados",
                        variable=self.var_trazer_parcelas,
                        command=self._on_toggle_trazer_parcelas).pack(side=tk.LEFT, padx=(12, 2))

        frame_grade = ttk.Frame(content)
        frame_grade.pack(fill=tk.BOTH, expand=True, pady=4)

        self.colunas = ("SEL", "STATUS", "DOCUMENTO", "PARCELA", "C\u00d3DIGO", "FORNECEDOR", "VALOR", "VENCIMENTO", "SITUA\u00c7\u00c3O")
        self._sort_directions = {col: False for col in self.colunas}
        self.tree = ttk.Treeview(frame_grade, columns=self.colunas, show="headings")
        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)

        larguras = [40, 100, 120, 60, 70, 250, 120, 110, 80]
        for col, larg in zip(self.colunas, larguras):
            self.tree.heading(col, text=col + " \u2195", command=lambda c=col: self._sort_treeview(c))
            self.tree.column(col, width=larg, anchor=tk.CENTER if col not in ("FORNECEDOR",) else tk.W)

        self.tree.tag_configure('ERRO', background='#FADBD8')
        self.tree.tag_configure('OK', background='#EAFAF1')

        scroll_y = ttk.Scrollbar(frame_grade, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        cards_row = tk.Frame(content, bg="#eef1f5")
        cards_row.pack(fill=tk.X, pady=(4, 0))
        self.card_titulos = self._criar_card(cards_row, "TÍTULOS", "#14146E")
        self.card_parcelas = self._criar_card(cards_row, "PARCELAS", "#8e44ad")
        self.card_valor = self._criar_card(cards_row, "VALOR TOTAL", "#22C55E")
        self.card_pago = self._criar_card(cards_row, "VALOR PAGO", "#0E7490")
        self.card_aberto = self._criar_card(cards_row, "A PAGAR (EM ABERTO)", "#C80000")

    def _criar_card(self, parent, titulo, cor):
        card = tk.Frame(parent, bg="white", bd=1, relief=tk.SOLID, padx=12, pady=6)
        card.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=4, pady=4)
        tk.Frame(card, bg=cor, height=3).pack(fill=tk.X, side=tk.TOP)
        tk.Label(card, text=titulo, font=("Segoe UI", 8, "bold"),
                 bg="white", fg="#7f8c8d").pack(anchor=tk.W, pady=(4, 0))
        lbl_valor = tk.Label(card, text="-", font=("Segoe UI", 14, "bold"),
                             bg="white", fg=cor)
        lbl_valor.pack(anchor=tk.W)
        return lbl_valor

    def _fmt_moeda(self, valor):
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _atualizar_cards(self, n_titulos=0, n_parcelas=0, valor_total=0.0,
                         em_aberto=0.0, valor_pago=0.0):
        try:
            self.card_titulos.config(text=f"{n_titulos:,}".replace(",", "."))
            self.card_parcelas.config(text=f"{n_parcelas:,}".replace(",", "."))
            self.card_valor.config(text=self._fmt_moeda(valor_total))
            self.card_pago.config(text=self._fmt_moeda(valor_pago))
            self.card_aberto.config(text=self._fmt_moeda(em_aberto))
        except tk.TclError:
            pass

    def _atualizar_cards_resumo(self):
        """Recalcula os cards com os valores REAIS que vão para o ERP.

        Roda no fim da análise, ao filtrar e ao ligar/desligar o checkbox, sempre
        sobre as linhas visíveis. Com "trazer parcelas novas" ligado os cancelados
        (e os EXCLUIDO/SUBSTITUIDO) contam como pago, porque entram baixados —
        assim VALOR TOTAL = VALOR PAGO + A PAGAR e dá pra conferir a carga.
        """
        trazer = bool(getattr(self, 'var_trazer_parcelas', None) and self.var_trazer_parcelas.get())
        total = pago_tot = aberto_tot = 0.0
        n_parcelas = 0
        titulos = set()

        for item_id in self.tree.get_children():
            reg = self.dados_grid.get(item_id)
            if not reg:
                continue
            status = reg.get('_status', '')
            if status != 'OK' and not trazer:
                continue
            valor, pago, a_pagar = self._valores_cache(reg)
            situacao = reg.get('_situacao', '')

            total += valor
            if situacao == "Cancelado":
                # entra baixado na emissão: o valor todo vira pago
                pago_tot += valor
                n_parcelas += 1
            elif situacao == "Pago":
                pago_tot += pago or valor
                n_parcelas += 1
            elif situacao == "Parcial":
                pago_tot += pago
                aberto_tot += a_pagar
                n_parcelas += 2  # o parcial é gravado como duas parcelas
            else:  # Aberto
                aberto_tot += a_pagar or valor
                n_parcelas += 1

            cod = reg.get('_codigo_tit') or reg.get('_numero_doc_auto')
            if cod is not None:
                titulos.add((str(cod), reg.get('_serie', SERIE_PADRAO), reg.get('_forn_key', '')))

        self._atualizar_cards(len(titulos), n_parcelas, total, aberto_tot, pago_tot)

    def _on_toggle_trazer_parcelas(self):
        """Re-renderiza usando o snapshot do ERP já em memória (sem reconsultar)."""
        if not getattr(self, 'registros_lidos', None):
            return
        self._renderizar_preview()

    def _salvar_config_mapeamento(self):
        config = configparser.ConfigParser()
        config.read('config.ini', encoding='utf-8')
        secao = 'IMPORTACAO_PAGAR'
        if not config.has_section(secao):
            config.add_section(secao)
        config.set(secao, 'ultimo_arquivo', self.caminho_arquivo)
        config.set(secao, 'ultima_aba', self.cb_abas.get())
        config.set(secao, 'linha_inicial', self.ent_linha_ini.get())
        for chave, ent in self.entradas_map.items():
            config.set(secao, f'map_{chave}', ent.get().strip())
        config.set(secao, 'local_cobranca', self.cb_local_cobranca.get())
        config.set(secao, 'centro_custo', self.cb_centro_custo.get())
        config.set(secao, 'conta_contabil', self.cb_conta_contabil.get())
        with open('config.ini', 'w', encoding='utf-8') as f:
            config.write(f)
        self.config = config

    def _carregar_config_mapeamento(self):
        secao = 'IMPORTACAO_PAGAR'
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
        # Mapeamento e linha inicial carregam SEMPRE, mesmo que o arquivo salvo
        # tenha mudado de nome/lugar — senão o mapa se perde em silencio a cada
        # reexportacao da planilha.
        linha = self.config.get(secao, 'linha_inicial', fallback='2')
        self.ent_linha_ini.delete(0, tk.END)
        self.ent_linha_ini.insert(0, linha)
        for chave in self.entradas_map:
            valor = self.config.get(secao, f'map_{chave}', fallback='')
            if valor:
                self.entradas_map[chave].delete(0, tk.END)
                self.entradas_map[chave].insert(0, valor)

    def _selecionar_arquivo(self):
        path = filedialog.askopenfilename(filetypes=[("Arquivos Suportados", "*.xlsx *.csv"), ("Excel", "*.xlsx"), ("CSV", "*.csv")])
        if path:
            self.ent_arquivo.delete(0, tk.END)
            self.ent_arquivo.insert(0, path)
            self.caminho_arquivo = path
            abas = obter_abas_planilha(path)
            self.cb_abas['values'] = abas
            if abas: self.cb_abas.current(0)

    def _carregar_locais_cobranca(self):
        self.locais_cobranca = {}
        try:
            with FirebirdService(self.config_db) as fb:
                rows = fb.query(
                    "SELECT LC_EMPRESA, LC_FILIAL, LC_CODIGO, LC_DESCRICAO "
                    "FROM TABELA_LOCAL_COBRANCA ORDER BY LC_CODIGO", []
                )
            opcoes = []
            for r in rows:
                emp_lc = r['lc_empresa']
                fil_lc = r['lc_filial']
                cod_lc = r['lc_codigo']
                desc = (r['lc_descricao'] or '').strip()
                rotulo = f"{cod_lc} - {desc}" if desc else str(cod_lc)
                opcoes.append(rotulo)
                self.locais_cobranca[rotulo] = (emp_lc, fil_lc, cod_lc)
            self.cb_local_cobranca['values'] = opcoes
            if opcoes:
                secao = 'IMPORTACAO_PAGAR'
                salvo = self.config.get(secao, 'local_cobranca', fallback='')
                if salvo in opcoes:
                    self.cb_local_cobranca.set(salvo)
                else:
                    self.cb_local_cobranca.current(0)
        except Exception:
            self.cb_local_cobranca['values'] = ["Sem conex\u00e3o"]
            self.cb_local_cobranca.current(0)

    def _avisar_rateio(self, msg):
        self._erro_rateio = msg
        print(f"[rateio] falha ao ler centro de custo / conta contabil: {msg}")

    def _carregar_rateio(self):
        """Popula centro de custo e conta contábil, restaurando o que foi salvo."""
        self._erro_rateio = None
        emp, fil = self._emp_fil_rateio()
        rot_cc, rot_ct, self._exercicio_contabil, self._conta_reduzido = \
            rateio_contabil.carregar_opcoes(self.config_db, emp, fil,
                                            ao_falhar=self._avisar_rateio)
        if self._erro_rateio:
            # sem isso a tela mostraria so "(nenhum)", como se o ERP nao tivesse
            # centro de custo cadastrado — e o usuario procuraria no lugar errado
            rot_cc = [rateio_contabil.ROTULO_SEM_CC, "Sem conexão com o ERP"]
            rot_ct = [rateio_contabil.ROTULO_SEM_CONTA, "Sem conexão com o ERP"]
        secao = 'IMPORTACAO_PAGAR'
        for combo, valores, chave in ((self.cb_centro_custo, rot_cc, 'centro_custo'),
                                      (self.cb_conta_contabil, rot_ct, 'conta_contabil')):
            atual = combo.get()
            combo['values'] = valores
            salvo = self.config.get(secao, chave, fallback='') if \
                self.config.has_section(secao) else ''
            escolha = atual if atual in valores else (salvo if salvo in valores else valores[0])
            combo.set(escolha)

    def _emp_fil_rateio(self):
        """Empresa/filial da seção de importação (os títulos usam as mesmas)."""
        try:
            emp = int(self.config.get('IMPORTACAO', 'empresa', fallback='1'))
            fil = int(self.config.get('IMPORTACAO', 'filial', fallback='1'))
        except ValueError:
            emp = fil = 1
        return emp, fil

    def _rateio_escolhido(self):
        """(cc, conta) escolhidos na tela — lidos na thread da UI, nunca na de gravação."""
        return (rateio_contabil.codigo_do_rotulo(self.cb_centro_custo.get()),
                rateio_contabil.codigo_do_rotulo(self.cb_conta_contabil.get()))

    def _fechar_tela(self):
        self.destroy()
        if self.callback_voltar: self.callback_voltar()

    def _iniciar_analise(self):
        aba = self.cb_abas.get()
        try:
            linha_ini = int(self.ent_linha_ini.get())
        except ValueError:
            return messagebox.showerror("Erro", "A linha inicial deve ser um n\u00famero.")

        if not self.caminho_arquivo or not aba:
            return messagebox.showwarning("Aviso", "Selecione o arquivo e a aba antes de continuar.")

        mapa_colunas = {chave: ent.get().strip() for chave, ent in self.entradas_map.items()}
        if not mapa_colunas.get('numero_doc'):
            return messagebox.showwarning("Aviso", "Voc\u00ea precisa mapear obrigatoriamente a coluna 'N\u00famero Documento'.")
        if not mapa_colunas.get('valor'):
            return messagebox.showwarning("Aviso", "Voc\u00ea precisa mapear obrigatoriamente a coluna 'Valor da Conta'.")

        self._salvar_config_mapeamento()
        self.btn_analisar.config(state=tk.DISABLED)
        self.lbl_status.config(text="Lendo planilha...")
        self.progresso['value'] = 20

        threading.Thread(target=self._analisar_bg, args=(aba, mapa_colunas, linha_ini), daemon=True).start()

    def _normalizar_documento(self, valor):
        # Dois documentos na mesma celula davam 28 digitos e o fornecedor
        # nunca era encontrado no ERP. Fica o primeiro.
        return multivalor.um_documento(valor)[0]

    def _remover_acentos(self, texto):
        texto = unicodedata.normalize('NFKD', str(texto))
        return texto.encode('ASCII', 'ignore').decode('ASCII')

    def _status_cancelado(self, texto):
        """A coluna Situação/Status indica título cancelado/estornado?"""
        s = self._remover_acentos(str(texto or '')).strip().upper()
        if not s:
            return False
        if s in STATUS_CANCELADO:
            return True
        return s.startswith("CANCEL") or s.startswith("INATIV") or s.startswith("ESTORN")

    def _status_excluido(self, texto):
        """A coluna Situação/Status indica EXCLUIDO/SUBSTITUIDO?

        Alguns exports truncam o valor (ex.: 'SUBSTITUID'), por isso o startswith.
        """
        s = self._remover_acentos(str(texto or '')).strip().upper()
        if not s:
            return False
        if s in STATUS_EXCLUIR:
            return True
        return s.startswith("EXCLU") or s.startswith("SUBSTIT")

    def _calcular_situacao(self, valor, pago, a_pagar, usar_status, cancelado_status):
        """Situação da linha. Com a coluna Status mapeada ela manda; senão usa os valores."""
        if usar_status:
            if cancelado_status:
                return "Cancelado"
            if valor > 0 and pago >= valor:
                return "Pago"
            if pago > 0:
                return "Parcial"
            return "Aberto"
        # Regra por valores (comportamento antigo): sem pago e sem saldo = cancelado
        if valor > 0 and pago == 0 and a_pagar == 0:
            return "Cancelado"
        if valor > 0 and pago >= valor:
            return "Pago"
        if pago > 0:
            return "Parcial"
        return "Aberto"

    def _valores_linha(self, reg, ap_mapeado):
        """Valor da conta, pago e a pagar de uma linha, já normalizados.

        Regra do saldo (igual ao Receber): quando a coluna "Valor a Pagar" está
        mapeada ela é a fonte de verdade; quando não está, calcula valor - pago.
        Guarda o resultado no próprio dict para o import usar exatamente os
        mesmos números que a tela mostrou.
        """
        valor = self._parse_valor(reg.get('valor', '0'))
        pago = self._parse_valor(reg.get('valor_recebido', '0'))
        a_pagar = self._parse_valor(reg.get('valor_a_pagar', '0'))
        if valor == 0.0 and a_pagar > 0:
            valor = a_pagar
        if not ap_mapeado:
            a_pagar = max(valor - pago, 0.0)
        reg['_valor_calc'] = valor
        reg['_pago_calc'] = pago
        reg['_ap_calc'] = a_pagar
        return valor, pago, a_pagar

    def _valores_cache(self, item):
        """Relê os valores já calculados na análise (fallback: reparseia a linha)."""
        valor = item.get('_valor_calc')
        pago = item.get('_pago_calc')
        a_pagar = item.get('_ap_calc')
        if valor is None or pago is None or a_pagar is None:
            ap_mapeado = bool(self.entradas_map['valor_a_pagar'].get().strip())
            return self._valores_linha(item, ap_mapeado)
        return valor, pago, a_pagar

    def _parse_valor(self, valor):
        if valor is None:
            return 0.0
        if isinstance(valor, (int, float)):
            return float(valor)
        v = str(valor).strip().replace(' ', '')
        if not v:
            return 0.0
        if ',' in v and '.' in v:
            v = v.replace('.', '').replace(',', '.')
        elif ',' in v:
            v = v.replace(',', '.')
        try:
            return float(v)
        except ValueError:
            return 0.0

    def _parse_data(self, valor):
        if not valor:
            return None
        v = str(valor).strip()
        tentativas = ['%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d', '%d-%m-%Y']
        for fmt in tentativas:
            try:
                return datetime.datetime.strptime(v[:10], fmt).date()
            except ValueError:
                continue
        tentativas_hora = ['%Y-%m-%d %H:%M:%S', '%d/%m/%Y %H:%M:%S', '%Y-%m-%dT%H:%M:%S']
        for fmt in tentativas_hora:
            try:
                return datetime.datetime.strptime(v[:19], fmt).date()
            except ValueError:
                continue
        return None

    def _parse_parcela(self, valor):
        v = str(valor or '1').strip()
        m = re.match(r'.*?(\d+).*', v)
        if m:
            return int(m.group(1))
        return 1

    def _parse_boleto(self, valor):
        v = str(valor or '').strip()
        m = re.search(r'(\d+)-?\d?$', v.replace('/', ''))
        if m:
            return int(m.group(1))
        return None

    def _valor_efetivo(self, item):
        """Valor da conta, com fallback para 'Valor a Pagar' quando a coluna
        'Valor da Conta' vem vazia (algumas linhas so preenchem uma delas)."""
        valor = self._parse_valor(item.get('valor', '0'))
        if valor == 0.0:
            valor_a_pagar = self._parse_valor(item.get('valor_a_pagar', '0'))
            if valor_a_pagar > 0:
                return valor_a_pagar
        return valor

    def _codigo_valido(self, numero_doc):
        """Codigo do titulo a partir do numero do documento: so digitos, sem
        zeros a esquerda. Retorna None quando nao ha numero, quando sobra vazio
        ou quando passa de 10 caracteres (TIT_CODIGO e CHAR(10)) — nesses casos
        o item recebe codigo automatico.

        Alguns exports trazem o numero no formato "DOC/PARCELA" (ex: "2413/1"),
        onde a parcela repete a coluna C — descarta esse sufixo antes de
        extrair os digitos, senao ele se funde ao codigo do titulo e cada
        parcela vira um titulo separado."""
        s = str(numero_doc or '').strip().split('/')[0]
        cod = re.sub(r'\D', '', s).lstrip('0')
        if cod and len(cod) <= 10:
            return cod
        return None

    def _buscar_conta_padrao(self, fb, emp, fil):
        exercicio = int(self.config.get('IMPORTACAO', 'exercicio', fallback='2026'))
        rows = fb.query(
            "SELECT PLANO_CONTA, PLANO_REDUZIDO FROM TABELA_PLANO "
            "WHERE PLANO_EMPRESA = ? AND PLANO_FILIAL = ? AND PLANO_EXERCICIO = ? AND PLANO_ATIVO = 'S'",
            [emp, fil, exercicio]
        )
        for row in rows:
            pc = row['plano_conta']
            pr = row['plano_reduzido']
            if pc is not None:
                return (exercicio, int(pc), int(pr or 0))
        return (exercicio, 1, 1)

    def _analisar_bg(self, aba, mapa_colunas, linha_ini):
        try:
            self.registros_lidos = ler_planilha_produtos(self.caminho_arquivo, aba, mapa_colunas, linha_ini)
            dados_existentes = {'parc_existentes': {}, 'fornecedor_cache': {},
                                'proximo_codigo': 1, 'parcelas_tit': set()}
            try:
                with FirebirdService(self.config_db) as fb:
                    emp = int(self.config.get('IMPORTACAO', 'empresa', fallback='1'))
                    fil = int(self.config.get('IMPORTACAO', 'filial', fallback='1'))
                    rows = fb.query(
                        "SELECT TPARC_CODIGO, TPARC_SERIE, TPARC_PARCELA, TPARC_FORNECEDOR, "
                        "       TPARC_VENCIMENTO, TPARC_VALOR "
                        "FROM TABELA_TITULO_PARCELA WHERE TPARC_EMPRESA = ? AND TPARC_FILIAL = ?",
                        [emp, fil]
                    )
                    for row in rows:
                        cod = str(row['tparc_codigo'] or '').strip().lstrip('0')
                        chave = (cod,
                                 int(row['tparc_parcela'] or 1),
                                 int(row['tparc_fornecedor'] or 0))
                        dados_existentes['parc_existentes'][chave] = True
                        # Assinatura por vencimento+valor: e o que permite trazer
                        # uma parcela NOVA de um titulo que ja existe sem duplicar
                        # as que ja estao gravadas.
                        dados_existentes['parcelas_tit'].add((
                            cod,
                            str(row['tparc_serie'] or '').strip(),
                            row['tparc_vencimento'].isoformat() if row['tparc_vencimento'] else '',
                            round(float(row['tparc_valor'] or 0), 2),
                        ))

                    fornecedor_cache = {}
                    for reg in self.registros_lidos:
                        doc = self._normalizar_documento(reg.get('documento', ''))
                        razao = str(reg.get('razao', '')).strip()
                        chave = (doc, razao)
                        if chave not in fornecedor_cache and (doc or razao):
                            try:
                                cod = self._buscar_fornecedor(fb, emp, fil, doc, razao)
                                fornecedor_cache[chave] = cod
                            except Exception:
                                fornecedor_cache[chave] = None
                        elif chave not in fornecedor_cache:
                            fornecedor_cache[chave] = None
                    dados_existentes['fornecedor_cache'] = fornecedor_cache
                    self._forn_cache = fornecedor_cache

                    dados_existentes['proximo_codigo'] = self._gerar_codigo_titulo(fb, emp, fil)

                    # Codigos de titulo ja existentes agrupados por fornecedor.
                    # O titulo do pagar e unico por (codigo, serie, fornecedor),
                    # entao o codigo automatico de itens sem numero de documento
                    # so precisa nao colidir com os codigos DAQUELE fornecedor.
                    codigos_por_forn = {}
                    for row in fb.query(
                        "SELECT TIT_CODIGO, TIT_FORNECEDOR FROM TABELA_TITULO "
                        "WHERE TIT_EMPRESA = ? AND TIT_FILIAL = ?",
                        [emp, fil]
                    ):
                        f = int(row['tit_fornecedor'] or 0)
                        c = str(row['tit_codigo'] or '').strip().lstrip('0')
                        if c:
                            codigos_por_forn.setdefault(f, set()).add(c)
                    dados_existentes['codigos_por_forn'] = codigos_por_forn

                    # Itens sem numero (ou com codigo longo demais) recebem
                    # codigo automatico novo a cada importacao. Para nao
                    # reimportar em duplicidade, marcamos como ja importado
                    # quando ja existe um titulo IMP com o mesmo fornecedor +
                    # valor + vencimento.
                    avulsos_existentes = set()
                    for row in fb.query(
                        "SELECT TIT_FORNECEDOR, TIT_TOTAL, TIT_VENCIMENTO FROM TABELA_TITULO "
                        "WHERE TIT_EMPRESA = ? AND TIT_FILIAL = ? AND TIT_ORIGEM = 'IMP'",
                        [emp, fil]
                    ):
                        avulsos_existentes.add((
                            int(row['tit_fornecedor'] or 0),
                            round(float(row['tit_total'] or 0), 2),
                            row['tit_vencimento'].isoformat() if row['tit_vencimento'] else ''
                        ))
                    for reg in self.registros_lidos:
                        reg['_avulso_dup'] = False
                        if self._codigo_valido(reg.get('numero_doc', '')) is not None:
                            continue
                        doc = self._normalizar_documento(reg.get('documento', ''))
                        razao = str(reg.get('razao', '')).strip()
                        forn = fornecedor_cache.get((doc, razao))
                        if forn is None:
                            continue
                        valor = self._valor_efetivo(reg)
                        emissao = self._parse_data(reg.get('emissao', ''))
                        vencimento = self._parse_data(reg.get('vencimento', ''))
                        if vencimento is None:
                            base = emissao or datetime.date.today()
                            vencimento = base + datetime.timedelta(days=30)
                        if (int(forn), round(valor, 2), vencimento.isoformat()) in avulsos_existentes:
                            reg['_avulso_dup'] = True
            except Exception:
                pass
            self.parent.after(0, lambda: self._renderizar_preview(dados_existentes))
            self.parent.after(0, self._carregar_locais_cobranca)
        except Exception as e:
            self.parent.after(0, lambda err=e: messagebox.showerror("Erro", f"Falha na leitura da planilha:\n{err}"))
            self.parent.after(0, lambda: self.btn_analisar.config(state=tk.NORMAL))
            self.parent.after(0, lambda: self.lbl_status.config(text="Erro."))

    def _renderizar_preview(self, dados_existentes=None):
        # Selo deste render. A grade e preenchida em blocos com after(), entao um
        # render antigo pode continuar inserindo DEPOIS que outro limpou a tela —
        # a grade acumula duas analises e os totais somam tudo. O selo faz os
        # blocos do render antigo pararem.
        self._render_seq = getattr(self, '_render_seq', 0) + 1
        meu_seq = self._render_seq

        for i in self.tree.get_children(): self.tree.delete(i)
        self.dados_grid.clear()

        # Guarda o snapshot do ERP para o toggle do checkbox re-renderizar sem
        # precisar consultar o banco de novo.
        if dados_existentes is not None:
            self._dados_existentes = dados_existentes
        else:
            dados_existentes = getattr(self, '_dados_existentes', None)

        parc_existentes = dados_existentes.get('parc_existentes', {}) if dados_existentes else {}
        forn_cache = dados_existentes.get('fornecedor_cache', {}) if dados_existentes else {}
        codigos_por_forn = dados_existentes.get('codigos_por_forn', {}) if dados_existentes else {}
        parcelas_tit = dados_existentes.get('parcelas_tit', set()) if dados_existentes else set()

        usar_status = bool(self.entradas_map['situacao_status'].get().strip())
        ap_mapeado = bool(self.entradas_map['valor_a_pagar'].get().strip())
        trazer_parcelas = bool(getattr(self, 'var_trazer_parcelas', None) and self.var_trazer_parcelas.get())

        def _forn_de(reg):
            d = self._normalizar_documento(reg.get('documento', ''))
            r = str(reg.get('razao', '')).strip()
            fc = forn_cache.get((d, r))
            return int(fc) if fc else 0

        # Codigos validos da planilha agrupados por fornecedor. O titulo do pagar
        # e unico por (codigo, serie, fornecedor), entao o codigo automatico dos
        # itens sem numero de documento so precisa nao colidir com os codigos
        # (do banco + da planilha) DAQUELE fornecedor.
        codigos_planilha_por_forn = {}
        for r in self.registros_lidos:
            cv = self._codigo_valido(r.get('numero_doc', ''))
            if cv:
                codigos_planilha_por_forn.setdefault(_forn_de(r), set()).add(cv)

        # Estado do gerador sequencial por fornecedor.
        usados_por_forn = {}
        next_por_forn = {}

        def _proximo_codigo_forn(fkey):
            if fkey not in usados_por_forn:
                usados_por_forn[fkey] = (set(codigos_por_forn.get(fkey, set()))
                                         | codigos_planilha_por_forn.get(fkey, set()))
            usados = usados_por_forn[fkey]
            n = next_por_forn.get(fkey, 1)
            while str(n) in usados:
                n += 1
            usados.add(str(n))
            next_por_forn[fkey] = n + 1
            return n

        validos = 0
        auto_grupos = {}
        for idx, reg in enumerate(self.registros_lidos):
            num_doc = str(reg.get('numero_doc', '') or '').strip()
            if not num_doc:
                continue
            chave = (num_doc, self._normalizar_documento(reg.get('documento', '')), str(reg.get('razao', '')).strip())
            auto_grupos.setdefault(chave, []).append(idx)

        for chave, indices in auto_grupos.items():
            if len(indices) <= 1:
                continue
            has_unset = any(not str(self.registros_lidos[i].get('parcela', '') or '').strip() for i in indices)
            if not has_unset:
                continue
            seen = set()
            next_n = 1
            for idx in indices:
                reg = self.registros_lidos[idx]
                raw = str(reg.get('parcela', '') or '').strip()
                if raw:
                    seen.add(self._parse_parcela(raw))
                    continue
                parc_key = (self._parse_valor(reg.get('valor', '0')), self._parse_data(reg.get('vencimento', '')))
                if parc_key not in seen:
                    while next_n in seen:
                        next_n += 1
                    seen.add(next_n)
                    reg['_parcela_auto'] = next_n
                    next_n += 1

        items = []
        soma_valor = 0.0
        soma_aberto = 0.0
        n_parcelas = 0
        grupos_titulo = set()
        for reg in self.registros_lidos:
            parcela = self._parse_parcela(reg.get('parcela', ''))
            valor, valor_pago, valor_a_pagar = self._valores_linha(reg, ap_mapeado)
            # EXCLUIDO/SUBSTITUIDO entram baixados na emissão -> compõem o TOTAL
            eh_excluido = usar_status and self._status_excluido(reg.get('situacao_status', ''))
            reg['_eh_excluido'] = eh_excluido
            razao = str(reg.get('razao', '')).strip()
            documento = self._normalizar_documento(reg.get('documento', ''))
            serie = str(reg.get('serie', '')).strip().upper() or SERIE_PADRAO
            numero_doc = str(reg.get('numero_doc', '')).strip()

            cod_valido = self._codigo_valido(numero_doc)  # None => avulso/auto

            codigo_auto = None
            if cod_valido is None:
                # Numero sequencial por fornecedor, sem colidir com os codigos
                # ja existentes (banco + planilha) daquele fornecedor.
                codigo_auto = _proximo_codigo_forn(_forn_de(reg))

            if cod_valido is None:
                if numero_doc:
                    numero_doc_exib = f"AUTO-{codigo_auto} ({numero_doc})"
                else:
                    numero_doc_exib = f"AUTO-{codigo_auto}"
                status = "J\u00c1 CADASTRADO" if reg.get('_avulso_dup') else "OK"
            elif valor <= 0:
                numero_doc_exib = numero_doc
                status = "ERRO (Valor inv\u00e1lido)"
            elif not razao and not documento:
                numero_doc_exib = numero_doc
                status = "ERRO (Sem Fornecedor)"
            else:
                forn_cod = forn_cache.get((documento, razao))
                numero_doc_exib = numero_doc
                ja_existe = bool(forn_cod and parc_existentes
                                 and (cod_valido, parcela, forn_cod) in parc_existentes)
                if ja_existe and trazer_parcelas:
                    # Confere a parcela em si (vencimento + valor). Se ela ainda
                    # nao esta gravada, entra como parcela nova do titulo existente.
                    venc_chk = self._parse_data(reg.get('vencimento', ''))
                    sig = (cod_valido, serie,
                           venc_chk.isoformat() if venc_chk else '',
                           round(valor, 2))
                    if sig in parcelas_tit:
                        status = "J\u00c1 CADASTRADO"
                    else:
                        status = "OK"
                        validos += 1
                elif ja_existe:
                    status = "J\u00c1 CADASTRADO"
                else:
                    status = "OK"
                    validos += 1

            if cod_valido is None and status == "OK":
                validos += 1

            reg['_status'] = status
            reg['_serie'] = serie
            reg['_parcela'] = parcela
            reg['_documento_limpo'] = documento
            if codigo_auto is not None:
                reg['_numero_doc_auto'] = str(codigo_auto)
            else:
                reg['_numero_doc_auto'] = None
            check = "☑" if status == "OK" else "☐"

            vencimento = self._parse_data(reg.get('vencimento', ''))
            venc_str = vencimento.strftime('%d/%m/%Y') if vencimento else '-'

            # Situacao vale para toda linha (nao so as OK), senao o filtro de
            # situacao e os cards nao veem os JA CADASTRADO trazidos pelo checkbox.
            cancelado_status = (self._status_cancelado(reg.get('situacao_status', '')) or eh_excluido) \
                if usar_status else False
            situacao = self._calcular_situacao(valor, valor_pago, valor_a_pagar,
                                               usar_status, cancelado_status)
            reg['_eh_cancelado'] = (situacao == "Cancelado")

            if situacao == "Cancelado":
                aberto_item = 0.0
                pago_item = valor
            else:
                aberto_item = round(valor_a_pagar, 2)
                pago_item = round(valor - aberto_item, 2)
                if pago_item < 0:
                    pago_item = 0.0
                    aberto_item = round(valor, 2)

            # Observacao: mantem a da planilha e prefixa o motivo quando cancelado.
            obs_planilha = str(reg.get('observacao', '') or '').strip()
            if situacao == "Cancelado":
                motivo = (str(reg.get('situacao_status', '')).strip() or "EXCLUIDO") \
                    if eh_excluido else "Título cancelado"
                reg['_observacao'] = f"{motivo} | {obs_planilha}" if obs_planilha else motivo
            else:
                reg['_observacao'] = obs_planilha

            codigo_tit = str(codigo_auto) if codigo_auto is not None else cod_valido
            reg['_codigo_tit'] = codigo_tit
            reg['_forn_key'] = _forn_de(reg)
            reg['_situacao'] = situacao

            if status == "OK":
                # Acumula totais dos itens que serao importados (confronto entre sistemas)
                soma_valor += valor
                soma_aberto += aberto_item
                n_parcelas += 2 if (aberto_item > 0 and pago_item > 0) else 1
                grupos_titulo.add((codigo_tit, serie, reg['_forn_key']))

            forn_codigo = forn_cache.get((documento, razao))
            reg['_forn_codigo'] = forn_codigo or ''

            parcela_exib = str(reg.get('_parcela_auto', parcela))
            tag = 'OK' if status == 'OK' else 'ERRO'
            cliente_nome = razao or str(reg.get('documento', '')) or "-"
            items.append((
                (check, status, numero_doc_exib, parcela_exib, str(reg['_forn_codigo']), cliente_nome[:60],
                 f"{valor:.2f}", venc_str, situacao),
                tag, reg
            ))

        total = len(items)
        if total == 0:
            self.btn_analisar.config(state=tk.NORMAL)
            self.lbl_status.config(text="Nenhum registro v\u00e1lido encontrado.")
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
                if validos > 0: self.btn_importar.config(state=tk.NORMAL)
                self.progresso['value'] = 100
                self.lbl_status.config(
                    text=f"Pronto. {validos} t\u00edtulos de {total} lidos."
                )
                self.cb_filtro_status.current(0)
                self.cb_filtro_situacao.current(0)
                self._filtrar_grade()
                self._atualizar_cards_resumo()

        render_chunk(0)

    def _on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            item_id = self.tree.identify_row(event.y)
            if not item_id: return
            valores = list(self.tree.item(item_id, 'values'))

            if "ERRO" in str(valores[1]) or "J\u00c1 CADASTRADO" in str(valores[1]):
                return

            if column == "#1":
                valores[0] = "☑" if valores[0] == "☐" else "☐"
                self.tree.item(item_id, values=valores)

    def _marcar_todos(self):
        for item in self.tree.get_children():
            v = list(self.tree.item(item, "values"))
            if "ERRO" not in str(v[1]):
                v[0] = "☑"
                self.tree.item(item, values=v)

    def _desmarcar_todos(self):
        for item in self.tree.get_children():
            v = list(self.tree.item(item, "values"))
            if "ERRO" not in str(v[1]):
                v[0] = "☐"
                self.tree.item(item, values=v)

    def _sort_treeview(self, col):
        self._sort_directions[col] = not self._sort_directions[col]
        reverse = self._sort_directions[col]
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        def valor_para_ordenar(val):
            v = str(val).strip()
            if not v or v == '-': return (1, '')
            try: return (0, float(v.replace(',', '.')))
            except ValueError: return (2, v.lower())
        l.sort(key=lambda t: valor_para_ordenar(t[0]), reverse=reverse)
        for index, (_, k) in enumerate(l): self.tree.move(k, '', index)
        for c in self.colunas:
            arrow = " \u25bc" if self._sort_directions[c] else " \u25b2" if c == col else " \u2195"
            self.tree.heading(c, text=c + arrow, command=lambda x=c: self._sort_treeview(x))

    def _filtrar_grade(self, event=None):
        filtro_status = self.cb_filtro_status.get()
        filtro_situacao = self.cb_filtro_situacao.get()
        for item in self.tree.get_children():
            self.tree.detach(item)
        for item_id, reg in self.dados_grid.items():
            status = reg.get('_status', '')
            situacao = reg.get('_situacao', '')
            ok_status = filtro_status == "Todos" or status == filtro_status or (filtro_status == "ERRO" and "ERRO" in status)
            ok_situacao = filtro_situacao == "Todas" or situacao == filtro_situacao
            if ok_status and ok_situacao:
                self.tree.move(item_id, '', tk.END)
        self._atualizar_cards_resumo()

    def _iniciar_importacao(self):
        selecionados = []
        for item_id in self.tree.get_children():
            valores = self.tree.item(item_id, "values")
            if valores[0] == "☑":
                selecionados.append(self.dados_grid[item_id])

        if not selecionados:
            messagebox.showwarning("Aviso", "Selecione pelo menos um t\u00edtulo para importar.")
            return

        resp = messagebox.askyesno("Confirmar",
            f"Deseja injetar os {len(selecionados)} t\u00edtulo(s) selecionados no Banco de Dados?\n"
            "Essa a\u00e7\u00e3o n\u00e3o pode ser desfeita.")
        if resp:
            rotulo_lc = self.cb_local_cobranca.get()
            lc_selecionado = self.locais_cobranca.get(rotulo_lc)

            # Fornecedores buscados por nome e nao encontrados: oferece cadastrar
            # como 'Outros' (sem documento) antes de importar. Retorna False = abortar.
            if not self._tratar_fornecedores_nao_encontrados(selecionados):
                return

            # o rateio e lido AQUI, na thread da UI — a de gravacao nao toca widget
            cc_sel, conta_sel = self._rateio_escolhido()
            rateio = (cc_sel, conta_sel, self._exercicio_contabil, self._conta_reduzido)
            self._salvar_config_mapeamento()
            self.btn_importar.config(state=tk.DISABLED)
            self.btn_analisar.config(state=tk.DISABLED)
            self.lbl_status.config(text="Importando contas a pagar...")
            threading.Thread(target=self._importacao_bg,
                             args=(selecionados, lc_selecionado, rateio), daemon=True).start()

    def _gerar_codigo_titulo(self, fb, emp, fil):
        rows = fb.query(
            "SELECT TIT_CODIGO FROM TABELA_TITULO WHERE TIT_EMPRESA = ? AND TIT_FILIAL = ?",
            [emp, fil]
        )
        existentes = set()
        for row in rows:
            try:
                existentes.add(int(row['tit_codigo']))
            except (ValueError, TypeError):
                pass
        if not existentes:
            return 1
        for i in range(1, max(existentes) + 2):
            if i not in existentes:
                return i
        return max(existentes) + 1

    def _proxima_parcela(self, fb, emp, fil, codigo, serie):
        res = fb.query(
            "SELECT COALESCE(MAX(TPARC_PARCELA), 0) + 1 AS PROX FROM TABELA_TITULO_PARCELA "
            "WHERE TPARC_EMPRESA = ? AND TPARC_FILIAL = ? AND TPARC_CODIGO = ? AND TPARC_SERIE = ?",
            [emp, fil, codigo, serie]
        )
        return int(res[0]['prox'])

    def _tratar_fornecedores_nao_encontrados(self, selecionados):
        """Detecta fornecedores buscados por nome que nao existem no cadastro e,
        via pop-up, oferece cadastra-los como 'Outros' (sem documento).
        Retorna True para prosseguir com a importacao, False para abortar."""
        forn_cache = getattr(self, '_forn_cache', {})
        faltantes = {}
        for item in selecionados:
            razao = str(item.get('razao', '')).strip()
            if not razao:
                continue
            doc = item.get('_documento_limpo', '') or self._normalizar_documento(item.get('documento', ''))
            if not forn_cache.get((doc, razao)):
                faltantes[razao] = faltantes.get(razao, 0) + 1

        if not faltantes:
            return True

        dialog = DialogoFornecedoresNaoEncontrados(self, faltantes)
        self.wait_window(dialog)
        if dialog.acao == 'cancelar':
            return False

        nomes = dialog.selecionados or []
        if not nomes:
            # Segue sem cadastrar: as linhas sem fornecedor serao puladas na importacao.
            return True

        try:
            emp = int(self.config.get('IMPORTACAO', 'empresa', fallback='1'))
            fil = int(self.config.get('IMPORTACAO', 'filial', fallback='1'))
            with FirebirdService(self.config_db) as fb:
                criados = self._cadastrar_fornecedores_outros(fb, emp, fil, nomes)
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao cadastrar fornecedores:\n{e}")
            return False

        # Atualiza o cache para a importacao localizar os codigos recem-criados
        for item in selecionados:
            razao = str(item.get('razao', '')).strip()
            cod = criados.get(razao.upper()[:50])
            if cod:
                doc = item.get('_documento_limpo', '') or self._normalizar_documento(item.get('documento', ''))
                forn_cache[(doc, razao)] = cod
        self._forn_cache = forn_cache

        messagebox.showinfo(
            "Fornecedores cadastrados",
            f"{len(criados)} fornecedor(es) cadastrado(s) como 'Outros' (sem documento)."
        )
        return True

    def _cadastrar_fornecedores_outros(self, fb, emp, fil, nomes):
        """Insere fornecedores genericos 'Outros' (sem documento) na TABELA_CLI_FOR.
        Retorna {razao_normalizada: codigo_gerado}. Usa o mesmo conjunto de colunas
        da importacao de clientes/fornecedores por XML, que ja funciona neste banco."""
        rows = fb.query(
            "SELECT CF_CODIGO FROM TABELA_CLI_FOR WHERE CF_EMPRESA = ? AND CF_FILIAL = ?",
            [emp, fil]
        )
        usados = set()
        for r in rows:
            try:
                usados.add(int(r['cf_codigo']))
            except (TypeError, ValueError):
                pass
        proximo = (max(usados) + 1) if usados else 1

        sql = """
            INSERT INTO TABELA_CLI_FOR (
                CF_EMPRESA, CF_FILIAL, CF_CODIGO, CF_DATA, CF_DATA_ALT,
                CF_CPF_CGC, CF_RAZAO, CF_FANTASIA,
                CF_ATIVO, CF_TIPO_INSCR, CF_CLIENTE, CF_FORNECEDOR,
                CF_RG_IE, CF_ICMS, CF_ATIVIDADE,
                CF_ENDERECO, CF_NRO_END, CF_BAIRRO, CF_CIDADE, CF_CEP,
                CF_ENDERECO2, CF_NRO_END2, CF_BAIRRO2, CF_CIDADE2, CF_CEP2,
                CF_ENDERECO3, CF_BAIRRO3, CF_CIDADE3, CF_CEP3,
                CF_ENDERECO4, CF_BAIRRO4, CF_CIDADE4, CF_CEP4,
                CF_CIDADE_EMPRESA, CF_CIDADE_FILIAL,
                CF_REPRESENTANTE_EMP, CF_REPRESENTANTE_FILIAL,
                CF_FONE1, CF_FONE2, CF_FAX,
                CF_EMAIL, CF_EMAIL_NFE,
                CF_COND_PGTO_VENDA, CF_COND_PGTO_COMPRA,
                CF_COD_ANTIGO
            ) VALUES (
                ?, ?, ?, CURRENT_DATE, CURRENT_DATE,
                ?, ?, ?,
                'S', ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?,
                ?, ?,
                ?, ?, ?,
                ?, 'S',
                ?, ?,
                ?
            )
        """

        criados = {}
        for nome in nomes:
            while proximo in usados:
                proximo += 1
            cod = proximo
            usados.add(cod)
            razao = str(nome).strip()[:50]
            params = [
                emp, fil, cod,
                '', razao, razao,
                2, 'N', 'S',
                'ISENTO', 2, 1,
                '', '', '', None, '',
                '', '', '', None, '',
                '', '', None, '',
                '', '', None, '',
                emp, fil,
                emp, fil,
                '', '', '',
                '',
                None, None,
                None
            ]
            fb.execute(sql, params)
            criados[razao.upper()] = cod
        return criados

    def _buscar_fornecedor(self, fb, emp, fil, documento, razao):
        if documento:
            doc_clean = re.sub(r'\D', '', str(documento))
            rows = fb.query(
                "SELECT CF_CODIGO FROM TABELA_CLI_FOR WHERE CF_EMPRESA = ? AND CF_FILIAL = ? "
                "AND REPLACE(REPLACE(REPLACE(CF_CPF_CGC, '.', ''), '/', ''), '-', '') = ?",
                [emp, fil, doc_clean]
            )
            if rows:
                return rows[0]['cf_codigo']

        if razao:
            razao_norm = str(razao).strip().upper()[:50]
            rows = fb.query(
                "SELECT CF_CODIGO FROM TABELA_CLI_FOR WHERE CF_EMPRESA = ? AND CF_FILIAL = ? "
                "AND TRIM(UPPER(CF_RAZAO)) = ?",
                [emp, fil, razao_norm]
            )
            if rows:
                return rows[0]['cf_codigo']

            rows2 = fb.query(
                "SELECT CF_CODIGO FROM TABELA_CLI_FOR WHERE CF_EMPRESA = ? AND CF_FILIAL = ? "
                "AND TRIM(UPPER(CF_FANTASIA)) = ?",
                [emp, fil, razao_norm]
            )
            if rows2:
                return rows2[0]['cf_codigo']

        return None

    def _importacao_bg(self, selecionados, lc_selecionado=None, rateio=None):
        cc_rateio, conta_rateio, exerc_rateio, red_rateio = rateio or (None, None, None, {})
        log_linhas = []
        inseridos = 0
        erros = 0
        try:
            emp = int(self.config.get('IMPORTACAO', 'empresa', fallback='1'))
            fil = int(self.config.get('IMPORTACAO', 'filial', fallback='1'))
            if lc_selecionado is None:
                lc_emp, lc_fil, lc_cod = emp, fil, 1
            else:
                lc_emp, lc_fil, lc_cod = lc_selecionado
            agora = datetime.datetime.now()
            ult_grav = agora.strftime('%Y-%m-%d %H:%M:%S')

            with FirebirdService(self.config_db) as fb:
                conta_pagar = self._buscar_conta_padrao(fb, emp, fil)

                # A PK do titulo (e o alvo da FK_TITPARC_TITULO) inclui a SERIE.
                # Sem a serie na chave, um titulo que existe na serie '1' fazia o
                # codigo pular o INSERT do cabecalho da serie 'IMP' -> a parcela
                # ficava sem cabecalho e morria com SQLCODE -530.
                tit_existentes = {}
                for row in fb.query(
                    "SELECT TIT_CODIGO, TIT_SERIE, TIT_FORNECEDOR FROM TABELA_TITULO "
                    "WHERE TIT_EMPRESA = ? AND TIT_FILIAL = ?",
                    [emp, fil]
                ):
                    cod = str(row['tit_codigo'] or '').strip()
                    ser = str(row['tit_serie'] or '').strip().upper()
                    forn = int(row['tit_fornecedor'] or 0)
                    if cod:
                        tit_existentes[(cod, ser, forn)] = True

                # Assinaturas de avulsos ja importados (fornecedor + valor +
                # vencimento) para nao reimportar em duplicidade.
                avulsos_existentes = set()
                for row in fb.query(
                    "SELECT TIT_FORNECEDOR, TIT_TOTAL, TIT_VENCIMENTO FROM TABELA_TITULO "
                    "WHERE TIT_EMPRESA = ? AND TIT_FILIAL = ? AND TIT_ORIGEM = 'IMP'",
                    [emp, fil]
                ):
                    avulsos_existentes.add((
                        int(row['tit_fornecedor'] or 0),
                        round(float(row['tit_total'] or 0), 2),
                        row['tit_vencimento'].isoformat() if row['tit_vencimento'] else ''
                    ))

                # Agrupa por (codigo, serie, fornecedor) — parcelas do mesmo
                # titulo ficam juntas (mesmo TPARC_CODIGO/SERIE/FORNECEDOR,
                # mudando so o TPARC_PARCELA). O codigo e gravado sem zeros a
                # esquerda (trigger TR_TITULO_PAG_TRIM_CODIGO) e a parcela usa o
                # mesmo valor, senao a FK quebra. Numero vazio ou com mais de 10
                # digitos recebe codigo automatico.
                # Fornecedores em memoria: uma query no lugar de 3 consultas com
                # REPLACE/TRIM(UPPER(...)) por fornecedor (nao usam indice).
                self.parent.after(0, lambda: self.lbl_status.config(text="Carregando fornecedores..."))
                forn_por_doc, forn_por_nome = {}, {}
                for row in fb.query(
                    "SELECT CF_CODIGO, CF_CPF_CGC, CF_RAZAO, CF_FANTASIA FROM TABELA_CLI_FOR "
                    "WHERE CF_EMPRESA = ? AND CF_FILIAL = ?", [emp, fil]
                ):
                    cod = row['cf_codigo']
                    d = re.sub(r'\D', '', str(row['cf_cpf_cgc'] or ''))
                    if d:
                        forn_por_doc.setdefault(d, cod)
                    for campo in ('cf_razao', 'cf_fantasia'):
                        nome = str(row[campo] or '').strip().upper()
                        if nome:
                            forn_por_nome.setdefault(nome, cod)

                def _forn_lookup(documento, razao):
                    """Busca em memoria; cai para o SQL so se nao achar."""
                    if documento:
                        c = forn_por_doc.get(re.sub(r'\D', '', documento))
                        if c is not None:
                            return c
                    if razao:
                        rn = razao.strip().upper()
                        c = forn_por_nome.get(rn) or forn_por_nome.get(rn[:50])
                        if c is not None:
                            return c
                    return self._buscar_fornecedor(fb, emp, fil, documento, razao)

                cache_forn = {}
                grupos = {}
                for item in selecionados:
                    if item.get('_status') != 'OK':
                        continue
                    serie = item.get('_serie', SERIE_PADRAO)
                    codigo_tit = item.get('_numero_doc_auto') or self._codigo_valido(item.get('numero_doc', ''))
                    if not codigo_tit:
                        continue
                    documento = item.get('_documento_limpo', '')
                    razao = str(item.get('razao', '')).strip()
                    ck = (documento, razao.upper())
                    if ck in cache_forn:
                        fornecedor_codigo = cache_forn[ck]
                    else:
                        fornecedor_codigo = _forn_lookup(documento, razao)
                        cache_forn[ck] = fornecedor_codigo
                    if fornecedor_codigo is None:
                        log_linhas.append(f"\u26a0 {codigo_tit} \u2014 Fornecedor nao encontrado, pulando linha")
                        erros += 1
                        continue
                    grupos.setdefault((codigo_tit, serie, int(fornecedor_codigo)), []).append(item)

                # Cursor unico + commit em lote: commit por grupo em carga grande
                # e o que mais pesa no Firebird. Para nao perder a atomicidade,
                # cada grupo roda dentro de um SAVEPOINT — um erro desfaz so
                # aquele titulo, nao o lote inteiro.
                cur_lote = fb.conn.cursor()
                total_grupos = len(grupos)

                def _savepoint(nome):
                    try:
                        cur_lote.execute(f"SAVEPOINT {nome}")
                        return True
                    except Exception:
                        return False

                def _rollback_savepoint(nome):
                    try:
                        cur_lote.execute(f"ROLLBACK TO SAVEPOINT {nome}")
                        return True
                    except Exception:
                        return False

                for gi, ((codigo_tit, serie, fornecedor_codigo), itens_grupo) in enumerate(grupos.items()):
                    num_doc = codigo_tit
                    if gi % 50 == 0:
                        self.parent.after(0, lambda d=gi, t=total_grupos: self.lbl_status.config(
                            text=f"Gravando {d + 1}/{t} títulos..."))
                    try:
                        ref = itens_grupo[0]
                        doc_original = str(ref.get('numero_doc', '') or '').strip() or str(codigo_tit)

                        emissao = self._parse_data(ref.get('emissao', '')) or agora.date()
                        vencimento = self._parse_data(ref.get('vencimento', ''))
                        data_registro = self._parse_data(ref.get('data_registro', '')) or agora.date()
                        if vencimento is None:
                            vencimento = emissao + datetime.timedelta(days=30)
                        dias = (vencimento - emissao).days if vencimento else 0

                        titulo_existe = (codigo_tit, str(serie).strip().upper(),
                                         fornecedor_codigo) in tit_existentes

                        parc_existentes = set()
                        if titulo_existe:
                            for row in fb.query(
                                "SELECT TPARC_PARCELA FROM TABELA_TITULO_PARCELA WHERE TPARC_EMPRESA = ? AND TPARC_FILIAL = ? "
                                "AND TPARC_CODIGO = ? AND TPARC_SERIE = ? AND TPARC_FORNECEDOR = ?",
                                [emp, fil, codigo_tit, serie, fornecedor_codigo]
                            ):
                                parc_existentes.add(int(row['tparc_parcela']))

                        # Numeros de parcela unicos dentro do titulo (nao descarta nada)
                        itens_novos = []
                        usados_parc = set(parc_existentes)
                        for item in itens_grupo:
                            pn = item.get('_parcela_auto') or self._parse_parcela(item.get('parcela', ''))
                            while pn in usados_parc:
                                pn += 1
                            usados_parc.add(pn)
                            item['_parcela_final'] = pn
                            itens_novos.append(item)

                        # Usa os MESMOS valores que a tela mostrou (cache da analise)
                        total_grupo = sum(self._valores_cache(item)[0] for item in itens_novos)
                        # Observacao ja combinada na analise (motivo do cancelamento + a da planilha)
                        observacao_tit = next(
                            (str(it.get('_observacao', '')).strip() for it in itens_novos
                             if str(it.get('_observacao', '')).strip()), None)

                        # Importa TODAS as linhas da planilha. Avulsos com mesmo
                        # fornecedor + valor + vencimento sao titulos distintos
                        # (nao duplicidade) \u2014 cada um recebe um codigo automatico
                        # proprio por fornecedor, sem colisao de chave.

                        # Monta o plano de parcelas garantindo:
                        #  - TIT_TOTAL = soma das parcelas (= valor da conta)
                        #  - em aberto no ERP = coluna "Valor a Pagar" (parcela PG='N')
                        #  - cancelado (sem pago e sem a pagar) entra com o valor
                        #    TOTAL, porem BAIXADO na data de emissao
                        plano = []
                        prox_parcela_saldo = max(usados_parc) + 1
                        for item in itens_novos:
                            parcela = item['_parcela_final']
                            valor, _pago_lido, valor_a_pagar = self._valores_cache(item)
                            desconto = self._parse_valor(item.get('desconto', '0'))
                            juros = self._parse_valor(item.get('juros', '0'))
                            venc_parc = self._parse_data(item.get('vencimento', '')) or vencimento
                            item_emissao = self._parse_data(item.get('emissao', '')) or emissao
                            dias_parc = (venc_parc - item_emissao).days if venc_parc else dias
                            boleto = str(item.get('boleto', '') or '').strip()
                            obs_parc = f"IMP {doc_original} {str(item.get('razao',''))[:30]}".strip()
                            data_receb = self._parse_data(item.get('data_recebimento', ''))

                            if item.get('_eh_cancelado'):
                                plano.append((parcela, valor, valor, 'S', desconto, juros, venc_parc, item_emissao, dias_parc, boleto, obs_parc, item_emissao))
                                log_linhas.append(f"  {num_doc} \u2014 Parcela {parcela} valor {valor:.2f} CANCELADO (baixado na emissao)")
                                continue

                            aberto = round(valor_a_pagar, 2)
                            pago_ef = round(valor - aberto, 2)
                            if pago_ef < 0:
                                pago_ef = 0.0
                                aberto = round(valor, 2)
                            # Data da baixa (pagamento). Sem ela, a ERP mostra a
                            # parcela como em aberto mesmo com PG='S' e VALOR_PG.
                            data_pgto = data_receb or venc_parc or item_emissao

                            if aberto <= 0.0:
                                plano.append((parcela, valor, valor, 'S', desconto, juros, venc_parc, item_emissao, dias_parc, boleto, obs_parc, data_pgto))
                                log_linhas.append(f"  {num_doc} \u2014 Parcela {parcela} valor {valor:.2f} pago")
                            elif pago_ef <= 0.0:
                                plano.append((parcela, valor, 0.0, 'N', desconto, juros, venc_parc, item_emissao, dias_parc, boleto, obs_parc, None))
                                log_linhas.append(f"  {num_doc} \u2014 Parcela {parcela} valor {valor:.2f} em aberto")
                            else:
                                plano.append((parcela, pago_ef, pago_ef, 'S', desconto, juros, venc_parc, item_emissao, dias_parc, boleto, obs_parc, data_pgto))
                                plano.append((prox_parcela_saldo, aberto, 0.0, 'N', 0.0, 0.0, venc_parc, item_emissao, dias_parc, boleto, obs_parc, None))
                                log_linhas.append(f"  {num_doc} \u2014 Parcela {parcela} parcial: pago {pago_ef:.2f}, saldo {aberto:.2f} vira parcela {prox_parcela_saldo}")
                                prox_parcela_saldo += 1

                        n_parcelas = len(plano)

                        sql_parc = """
                            INSERT INTO TABELA_TITULO_PARCELA (
                                TPARC_EMPRESA, TPARC_FILIAL, TPARC_CODIGO, TPARC_SERIE,
                                TPARC_PARCELA,
                                TPARC_FORNECEDOR_EMPRESA, TPARC_FORNECEDOR_FILIAL, TPARC_FORNECEDOR,
                                TPARC_EMISSAO, TPARC_DIAS,
                                TPARC_VENCIMENTO,
                                TPARC_MOEDA_EMPRESA, TPARC_MOEDA_FILIAL,
                                TPARC_VALOR,
                                TPARC_TOTAL,
                                TPARC_IRRF, TPARC_INSS,
                                TPARC_LC_EMPRESA, TPARC_LC_FILIAL, TPARC_LOCAL_COBRANCA,
                                TPARC_VALOR_PG, TPARC_PG,
                                TPARC_DATA, TPARC_TIPO_PGTO,
                                TPARC_DESCONTO, TPARC_JUROS,
                                TPARC_CORRECAO, TPARC_DESP_BANCO,
                                TPARC_ORIGEM,
                                TPARC_ULT_GRAVACAO,
                                TPARC_MULTA,
                                TPARC_NOSSONUMERO,
                                TPARC_OBS,
                                TPARC_CONTA_EMPRESA, TPARC_CONTA_FILIAL, TPARC_CONTA_EXERCICIO, TPARC_CONTA, TPARC_CONTA_REDUZIDO,
                                TPARC_LIBERADO
                            ) VALUES (
                                ?, ?, ?, ?,
                                ?,
                                ?, ?, ?,
                                ?, ?,
                                ?,
                                ?, ?,
                                ?,
                                ?,
                                ?, ?,
                                ?, ?, ?,
                                ?, ?,
                                ?, ?,
                                ?, ?,
                                ?, ?,
                                'IMP',
                                ?,
                                ?,
                                ?,
                                ?,
                                ?, ?, ?, ?, ?,
                                'S'
                            )
                        """

                        def processar_grupo(cur):
                            if not titulo_existe:
                                cur.execute("""
                                    INSERT INTO TABELA_TITULO (
                                        TIT_EMPRESA, TIT_FILIAL, TIT_CODIGO, TIT_SERIE,
                                        TIT_FORNECEDOR_EMPRESA, TIT_FORNECEDOR_FILIAL, TIT_FORNECEDOR,
                                        TIT_EMISSAO, TIT_DATA,
                                        TIT_TL_EMPRESA, TIT_TL_FILIAL, TIT_TIPO_LANCAMENTO,
                                        TIT_PARCELAS, TIT_VENCIMENTO,
                                        TIT_SENAR, TIT_SEST_SENAT, TIT_GILRAT,
                                        TIT_DIAS,
                                        TIT_ORIGEM,
                                        TIT_VALOR,
                                        TIT_DESCONTO, TIT_IRRF, TIT_INSS, TIT_FUNRURAL, TIT_JUROS,
                                        TIT_MOEDA_EMPRESA, TIT_MOEDA_FILIAL,
                                        TIT_QTD_MOEDA,
                                        TIT_TOTAL, TIT_TOTAL_CC,
                                        TIT_OBS,
                                        TIT_TOTAL_CONTABIL, TIT_TOTAL_PARCELAS,
                                        TIT_USUARIO,
                                        TIT_COD_IMPORTACAO,
                                        TIT_ULT_GRAVACAO,
                                        TIT_LC_EMPRESA, TIT_LC_FILIAL, TIT_LOCAL_COBRANCA
                                    ) VALUES (
                                        ?, ?, ?, ?,
                                        ?, ?, ?,
                                        ?, ?,
                                        ?, ?, ?,
                                        ?, ?,
                                        ?, ?, ?,
                                        ?,
                                        ?,
                                        ?,
                                        ?, ?, ?, ?, ?,
                                        ?, ?,
                                        ?,
                                        ?, ?,
                                        ?,
                                        ?, ?,
                                        ?,
                                        ?,
                                        ?,
                                        ?, ?, ?
                                    )
                                """, [
                                    emp, fil, codigo_tit, serie,
                                    emp, fil, fornecedor_codigo,
                                    emissao, data_registro,
                                    emp, fil, 2,
                                    n_parcelas, vencimento,
                                    0.0, 0.0, 0.0,
                                    dias,
                                    'IMP',
                                    total_grupo,
                                    0.0, 0.0, 0.0, 0.0, 0.0,
                                    emp, fil,
                                    0.0,
                                    total_grupo, total_grupo,
                                    observacao_tit,
                                    total_grupo, total_grupo,
                                    'SISTEC_IMP',
                                    doc_original[:30],
                                    ult_grav,
                                    lc_emp, lc_fil, lc_cod
                                ])
                                # rateio no mesmo cursor/transacao do titulo: se o
                                # titulo cair, o centro de custo nao fica orfao.
                                # So no titulo NOVO — titulo que ja existia no ERP
                                # nao e da importacao e nao leva rateio dela.
                                rateio_contabil.rateio_pagar(
                                    cur, emp, fil, codigo_tit, serie, fornecedor_codigo,
                                    emissao, total_grupo, cc=cc_rateio,
                                    conta=conta_rateio, exercicio=exerc_rateio,
                                    reduzidos=red_rateio)
                            else:
                                # Titulo ja existe: soma no cabecalho o valor e a
                                # quantidade das parcelas novas, senao TIT_TOTAL /
                                # TIT_PARCELAS ficam defasados (o ERP passa a
                                # mostrar menos do que realmente tem em parcelas).
                                cur.execute("""
                                    UPDATE TABELA_TITULO SET
                                        TIT_VALOR = COALESCE(TIT_VALOR, 0) + ?,
                                        TIT_TOTAL = COALESCE(TIT_TOTAL, 0) + ?,
                                        TIT_TOTAL_CC = COALESCE(TIT_TOTAL_CC, 0) + ?,
                                        TIT_TOTAL_CONTABIL = COALESCE(TIT_TOTAL_CONTABIL, 0) + ?,
                                        TIT_TOTAL_PARCELAS = COALESCE(TIT_TOTAL_PARCELAS, 0) + ?,
                                        TIT_PARCELAS = COALESCE(TIT_PARCELAS, 0) + ?,
                                        TIT_ULT_GRAVACAO = ?
                                    WHERE TIT_EMPRESA = ? AND TIT_FILIAL = ?
                                      AND TIT_CODIGO = ? AND TIT_SERIE = ? AND TIT_FORNECEDOR = ?
                                """, [
                                    total_grupo, total_grupo, total_grupo, total_grupo,
                                    total_grupo, n_parcelas, ult_grav,
                                    emp, fil, codigo_tit, serie, fornecedor_codigo
                                ])
                                # Se o UPDATE nao achou o cabecalho, as parcelas
                                # morreriam na FK_TITPARC_TITULO. Aborta o grupo
                                # com mensagem clara em vez de deixar o -530.
                                if cur.rowcount == 0:
                                    raise ValueError(
                                        f"cabecalho do titulo nao existe "
                                        f"(codigo={codigo_tit}, serie={serie}, "
                                        f"fornecedor={fornecedor_codigo}) — parcelas nao gravadas")
                                log_linhas.append(
                                    f"  {num_doc} — titulo existente: +{n_parcelas} parcela(s), "
                                    f"+{total_grupo:.2f} no cabecalho")

                            for (parcela_num, valor_parc, valor_pg, pg_sn, val_desc, val_juros, parc_venc, item_emissao, dias_parc, parc_boleto, obs_parc, data_baixa) in plano:
                                tipo_pgto = 1 if pg_sn == 'S' else None
                                params_parc = [
                                    emp, fil, codigo_tit, serie,
                                    parcela_num,
                                    emp, fil, fornecedor_codigo,
                                    item_emissao, dias_parc,
                                    parc_venc,
                                    emp, fil,
                                    valor_parc, valor_parc,
                                    0.0, 0.0,
                                    lc_emp, lc_fil, lc_cod,
                                    valor_pg, pg_sn,
                                    data_baixa if pg_sn == 'S' else None, tipo_pgto,
                                    val_desc, val_juros,
                                    0.0, 0.0,
                                    ult_grav,
                                    0.0,
                                    parc_boleto or None,
                                    obs_parc,
                                    emp, fil, conta_pagar[0], conta_pagar[1], conta_pagar[2],
                                ]
                                try:
                                    cur.execute(sql_parc, params_parc)
                                except Exception as e:
                                    log_linhas.append(f"  !!! PARCEL INSERT ERROR: {e}")
                                    log_linhas.append(f"  !!! Key: (emp={emp}, fil={fil}, cod={codigo_tit}, serie={serie}, parc={parcela_num}, forn={fornecedor_codigo})")
                                    raise

                        tem_sp = _savepoint("SP_GRUPO")
                        try:
                            processar_grupo(cur_lote)
                        except Exception:
                            if tem_sp:
                                _rollback_savepoint("SP_GRUPO")
                            raise
                        inseridos += 1
                        if not titulo_existe:
                            tit_existentes[(codigo_tit, str(serie).strip().upper(),
                                            fornecedor_codigo)] = True

                    except Exception as e:
                        erros += 1
                        log_linhas.append(f"\u274c Erro ao inserir {num_doc}: {e}")

                    if (gi + 1) % 300 == 0:
                        try:
                            fb.conn.commit()
                            cur_lote = fb.conn.cursor()
                        except Exception:
                            pass

                fb.conn.commit()  # grava o restante

            msg = f"Processamento concluido!\n\n{inseridos} titulo(s) cadastrados."
            if erros:
                msg += f"\n{erros} erro(s) durante a importacao. Veja o log para detalhes."
            self.parent.after(0, lambda m=msg: self._safe_showinfo("Concluido", m))

            log_str = "\n".join(log_linhas)
            self.parent.after(0, lambda l=log_str: self._oferecer_log(l))

            try:
                with FirebirdService(self.config_db) as fb:
                    emp_r = int(self.config.get('IMPORTACAO', 'empresa', fallback='1'))
                    fil_r = int(self.config.get('IMPORTACAO', 'filial', fallback='1'))
                    rows = fb.query(
                        "SELECT TPARC_CODIGO, TPARC_SERIE, TPARC_PARCELA, TPARC_FORNECEDOR, "
                        "       TPARC_VENCIMENTO, TPARC_VALOR "
                        "FROM TABELA_TITULO_PARCELA WHERE TPARC_EMPRESA = ? AND TPARC_FILIAL = ?",
                        [emp_r, fil_r]
                    )
                    parc_existentes = {}
                    parcelas_tit_novo = set()
                    for row in rows:
                        cod = str(row['tparc_codigo'] or '').strip().lstrip('0')
                        chave = (cod,
                                 int(row['tparc_parcela'] or 1),
                                 int(row['tparc_fornecedor'] or 0))
                        parc_existentes[chave] = True
                        parcelas_tit_novo.add((
                            cod,
                            str(row['tparc_serie'] or '').strip(),
                            row['tparc_vencimento'].isoformat() if row['tparc_vencimento'] else '',
                            round(float(row['tparc_valor'] or 0), 2),
                        ))
                    # Re-marca avulsos ja importados para nao reimportar
                    avulsos_ex = set()
                    for row in fb.query(
                        "SELECT TIT_FORNECEDOR, TIT_TOTAL, TIT_VENCIMENTO FROM TABELA_TITULO "
                        "WHERE TIT_EMPRESA = ? AND TIT_FILIAL = ? AND TIT_ORIGEM = 'IMP'",
                        [emp_r, fil_r]
                    ):
                        avulsos_ex.add((int(row['tit_fornecedor'] or 0), round(float(row['tit_total'] or 0), 2),
                                        row['tit_vencimento'].isoformat() if row['tit_vencimento'] else ''))
                    forn_cache = getattr(self, '_forn_cache', {})
                    for reg in self.registros_lidos:
                        reg['_avulso_dup'] = False
                        if self._codigo_valido(reg.get('numero_doc', '')) is not None:
                            continue
                        doc = self._normalizar_documento(reg.get('documento', ''))
                        razao = str(reg.get('razao', '')).strip()
                        forn = forn_cache.get((doc, razao))
                        if forn is None:
                            continue
                        valor = self._valor_efetivo(reg)
                        emiss = self._parse_data(reg.get('emissao', ''))
                        venc = self._parse_data(reg.get('vencimento', ''))
                        if venc is None:
                            venc = (emiss or datetime.date.today()) + datetime.timedelta(days=30)
                        if (int(forn), round(valor, 2), venc.isoformat()) in avulsos_ex:
                            reg['_avulso_dup'] = True
                    codigos_por_forn = {}
                    for row in fb.query(
                        "SELECT TIT_CODIGO, TIT_FORNECEDOR FROM TABELA_TITULO "
                        "WHERE TIT_EMPRESA = ? AND TIT_FILIAL = ?",
                        [emp_r, fil_r]
                    ):
                        f = int(row['tit_fornecedor'] or 0)
                        c = str(row['tit_codigo'] or '').strip().lstrip('0')
                        if c:
                            codigos_por_forn.setdefault(f, set()).add(c)
                    dados_existentes = {'parc_existentes': parc_existentes,
                                        'fornecedor_cache': forn_cache,
                                        'codigos_por_forn': codigos_por_forn,
                                        'parcelas_tit': parcelas_tit_novo}
                self.parent.after(0, lambda de=dados_existentes: self._renderizar_preview(de))
            except Exception:
                self.parent.after(0, lambda: self._renderizar_preview())

        except Exception as e:
            self.parent.after(0, lambda err=e: self._safe_showerror("Erro de Importacao", f"Ocorreu um erro estrutural:\n{err}"))
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
        resp = messagebox.askyesno("Log da Importa\u00e7\u00e3o",
            "Deseja salvar um arquivo .txt com o log detalhado da importa\u00e7\u00e3o?")
        if resp:
            caminho = filedialog.asksaveasfilename(
                defaultextension=".txt",
                initialfile="LOG_IMPORTACAO_PAGAR.txt",
                filetypes=[("Arquivos de Texto", "*.txt")]
            )
            if caminho:
                try:
                    with open(caminho, 'w', encoding='utf-8') as f:
                        f.write("--- LOG DE IMPORTACAO DE CONTAS A PAGAR VIA PLANILHA ---\n\n")
                        f.write(log_str)
                    messagebox.showinfo("Log Salvo", f"Arquivo salvo em:\n{caminho}")
                    if messagebox.askyesno("Abrir Log", "Deseja abrir o arquivo de log agora?"):
                        try:
                            os.startfile(caminho)
                        except Exception as e:
                            messagebox.showerror("Erro", f"Erro ao abrir arquivo:\n{e}")
                except Exception as e:
                    messagebox.showerror("Erro", f"Erro ao salvar log:\n{e}")

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import configparser
import threading
import re
import os
import unicodedata
import csv
import datetime

from utils.excel_reader import obter_abas_planilha, ler_planilha_produtos
from utils.firebird_service import FirebirdService
from utils import tema
from utils import rateio_contabil
from utils import multivalor
from utils import combo_busca

CAMPOS_DISPONIVEIS = [
    ("N\u00famero Documento *", "numero_doc", True),
    ("Parcela", "parcela", False),
    ("Cliente (CNPJ/CPF)", "documento", False),
    ("Cliente (Raz\u00e3o Social)", "razao", False),
    ("Valor da Conta *", "valor", True),
    ("Valor Recebido", "valor_recebido", False),
    ("Valor a Receber", "valor_a_receber", False),
    ("Data Emiss\u00e3o", "emissao", False),
    ("Vencimento", "vencimento", False),
    ("Data Registro", "data_registro", False),
    ("Data Recebimento", "data_recebimento", False),
    ("Desconto", "desconto", False),
    ("Juros e Multa", "juros", False),
    ("S\u00e9rie", "serie", False),
    ("N\u00famero Boleto", "boleto", False),
    ("Observa\u00e7\u00e3o", "observacao", False),
    ("Situa\u00e7\u00e3o / Status", "situacao_status", False),
]

# Textos (na coluna Status) que indicam t\u00edtulo CANCELADO
STATUS_CANCELADO = {"CANCELADO", "CANCELADA", "CANCEL", "CANCELED",
                    "INATIVO", "INATIVA", "ESTORNADO", "ESTORNADA"}

# Textos (na coluna Status) de t\u00edtulos que N\u00c3O devem ser importados
# (anulados/trocados no sistema antigo). S\u00e3o simplesmente descartados.
STATUS_EXCLUIR = {"EXCLUIDO", "EXCLUIDA", "SUBSTITUIDO", "SUBSTITUIDA"}

SERIE_PADRAO = "IMP"

class TelaImportacaoPlanilhaReceber(ttk.Frame):
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
            self, "Importar Contas a Receber (Excel)",
            "Importa\u00e7\u00e3o de t\u00edtulos e parcelas de contas a receber via planilha (XLSX/CSV)"
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

        self.btn_analisar = tema.botao_sidebar(sidebar, "\ud83d\udd0d   Carregar e Analisar Planilha", self._iniciar_analise)
        self.btn_analisar.pack(fill=tk.X)

        self.btn_importar = tema.botao_sidebar(sidebar, "\ud83d\ude80   Processar e Injetar no ERP", self._iniciar_importacao, cor_fg="#7EE0A0")
        self.btn_importar.config(state=tk.DISABLED)
        self.btn_importar.pack(fill=tk.X)

        self.btn_recalcular = tema.botao_sidebar(sidebar, "\ud83d\udd01   Recalcular T\u00edtulos", self._recalcular_titulos)
        self.btn_recalcular.pack(fill=tk.X)

        # -------- CONTE\u00daDO --------
        content = tk.Frame(corpo, bg=tema.BG_BASE)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=16, pady=12)

        # --- CARDS DE RESUMO ---
        frame_cards = ttk.Frame(content)
        frame_cards.pack(fill=tk.X, pady=(8, 2), padx=5)

        self.card_total_conta = self._criar_card(frame_cards, "Valor da Conta", "R$ 0,00", "#14146E")
        self.card_total_conta.pack(side=tk.LEFT, padx=5)

        self.card_recebido = self._criar_card(frame_cards, "Valor Recebido", "R$ 0,00", "#22C55E")
        self.card_recebido.pack(side=tk.LEFT, padx=5)

        self.card_aberto = self._criar_card(frame_cards, "Saldo em Aberto", "R$ 0,00", "#E67E22")
        self.card_aberto.pack(side=tk.LEFT, padx=5)

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
        self.cb_filtro_situacao = ttk.Combobox(filter_row, values=["Todas", "Aberto", "Parcial", "Recebido", "Cancelado"],
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
        self.cb_centro_custo = ttk.Combobox(rateio_row, width=30, font=("Segoe UI", 9))
        combo_busca.tornar_pesquisavel(self.cb_centro_custo)
        self.cb_centro_custo.pack(side=tk.LEFT, padx=2)
        tk.Label(rateio_row, text="Conta cont\u00e1bil:",
                 font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(12, 2))
        self.cb_conta_contabil = ttk.Combobox(rateio_row, width=34, font=("Segoe UI", 9))
        combo_busca.tornar_pesquisavel(self.cb_conta_contabil)
        self.cb_conta_contabil.pack(side=tk.LEFT, padx=2)
        ttk.Button(rateio_row, text="\u21bb", width=3,
                   command=self._carregar_rateio).pack(side=tk.LEFT, padx=(4, 0))
        tk.Label(rateio_row, text="(opcional \u2014 vai no t\u00edtulo importado)",
                 font=("Segoe UI", 8), fg="#555").pack(side=tk.LEFT, padx=(6, 0))
        self._exercicio_contabil = None
        self._conta_reduzido = {}
        self._carregar_rateio()

        # Virada de ano: parcelas novas de titulos que ja existem no ERP.
        # Quando marcado, um titulo ja cadastrado deixa de bloquear a linha
        # inteira; cada parcela e avaliada individualmente (por vencimento +
        # valor). Parcela que ja existe continua "JA CADASTRADO"; parcela nova
        # vira "OK" e entra como mais uma parcela do titulo (sem duplicar).
        self.var_trazer_parcelas = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            filter_row,
            text="Trazer parcelas novas de t\u00edtulos j\u00e1 cadastrados",
            variable=self.var_trazer_parcelas,
            command=self._on_toggle_trazer_parcelas
        ).pack(side=tk.LEFT, padx=(12, 2))

        frame_grade = ttk.Frame(content)
        frame_grade.pack(fill=tk.BOTH, expand=True, pady=4)

        self.colunas = ("SEL", "STATUS", "DOCUMENTO", "CLIENTE", "VALOR", "VENCIMENTO", "SITUA\u00c7\u00c3O")
        self._sort_directions = {col: False for col in self.colunas}
        self.tree = ttk.Treeview(frame_grade, columns=self.colunas, show="headings")
        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)

        larguras = [40, 100, 150, 250, 120, 110, 80]
        for col, larg in zip(self.colunas, larguras):
            self.tree.heading(col, text=col + " ↕", command=lambda c=col: self._sort_treeview(c))
            self.tree.column(col, width=larg, anchor=tk.CENTER if col not in ("CLIENTE",) else tk.W)

        self.tree.tag_configure('ERRO', background='#FADBD8')
        self.tree.tag_configure('OK', background='#EAFAF1')

        scroll_y = ttk.Scrollbar(frame_grade, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

    def _criar_card(self, parent, titulo, valor_inicial, cor_texto):
        """Cria um card de resumo para os totais."""
        card = tk.Frame(parent, bg="#FFFFFF", highlightbackground="#CCCCCC", highlightthickness=1, padx=15, pady=8)
        lbl_titulo = tk.Label(card, text=titulo, font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#555")
        lbl_titulo.pack(anchor=tk.E)
        lbl_valor = tk.Label(card, text=valor_inicial, font=("Segoe UI", 14, "bold"), bg="#FFFFFF", fg=cor_texto)
        lbl_valor.pack(anchor=tk.E)
        card.lbl_valor = lbl_valor
        return card

    def _salvar_config_mapeamento(self):
        config = configparser.ConfigParser()
        config.read('config.ini', encoding='utf-8')
        secao = 'IMPORTACAO_RECEBER'
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
        secao = 'IMPORTACAO_RECEBER'
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
                # Tenta restaurar salvo
                secao = 'IMPORTACAO_RECEBER'
                salvo = self.config.get(secao, 'local_cobranca', fallback='')
                if salvo in opcoes:
                    self.cb_local_cobranca.set(salvo)
                else:
                    self.cb_local_cobranca.current(0)
        except Exception:
            self.cb_local_cobranca['values'] = ["Sem conexão"]
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
        secao = 'IMPORTACAO_RECEBER'
        for combo, valores, chave in ((self.cb_centro_custo, rot_cc, 'centro_custo'),
                                      (self.cb_conta_contabil, rot_ct, 'conta_contabil')):
            atual = combo.get()
            salvo = self.config.get(secao, chave, fallback='') if \
                self.config.has_section(secao) else ''
            escolha = atual if atual in valores else (salvo if salvo in valores else valores[0])
            combo_busca.definir_valores(combo, valores, manter=escolha)

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
        # Dois documentos na mesma celula davam 28 digitos e o cliente
        # nunca era encontrado no ERP. Fica o primeiro.
        return multivalor.um_documento(valor)[0]

    def _num_doc_digitos(self, valor):
        """Número do documento só com dígitos (remove letras/símbolos, ex.: 'R00099' -> '00099')."""
        return re.sub(r'\D', '', str(valor or ''))

    def _remover_acentos(self, texto):
        texto = unicodedata.normalize('NFKD', str(texto))
        return texto.encode('ASCII', 'ignore').decode('ASCII')

    def _status_cancelado(self, texto):
        """True se o texto da coluna Status indicar título cancelado."""
        s = self._remover_acentos(str(texto or '')).strip().upper()
        if not s:
            return False
        if s in STATUS_CANCELADO:
            return True
        return s.startswith("CANCEL") or s.startswith("INATIV") or s.startswith("ESTORN")

    def _status_excluido(self, texto):
        """True se o Status indicar título excluído/substituído (não importa)."""
        s = self._remover_acentos(str(texto or '')).strip().upper()
        if not s:
            return False
        if s in STATUS_EXCLUIR:
            return True
        return s.startswith("EXCLU") or s.startswith("SUBSTIT")

    def _calcular_situacao(self, valor, recebido, a_receber, usar_status, cancelado_status):
        """
        Se usar_status: Cancelado vem da coluna Status; o resto (Aberto/Parcial/
        Recebido) sai dos valores. Senão: regra antiga 100% por valores.
        """
        if usar_status:
            if cancelado_status:
                return "Cancelado"
            if valor > 0 and recebido >= valor:
                return "Recebido"
            if recebido > 0:
                return "Parcial"
            return "Aberto"
        # Regra por valores (compatível com o comportamento antigo)
        if valor > 0 and recebido == 0 and a_receber == 0:
            return "Cancelado"
        if valor > 0 and recebido >= valor:
            return "Recebido"
        if recebido > 0:
            return "Parcial"
        return "Aberto"

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
        # Tenta parsing direto (string cortada no 10 se tiver hora)
        tentativas = ['%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d', '%d-%m-%Y']
        for fmt in tentativas:
            try:
                return datetime.datetime.strptime(v[:10], fmt).date()
            except ValueError:
                continue
        # Tenta com parte de hora
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

    def _analisar_bg(self, aba, mapa_colunas, linha_ini):
        try:
            self.registros_lidos = ler_planilha_produtos(self.caminho_arquivo, aba, mapa_colunas, linha_ini)
            dados_existentes = {'documentos_tit': {}, 'nomes_tit': {}, 'proximo_codigo': 1,
                                'parcelas_tit': set()}
            try:
                with FirebirdService(self.config_db) as fb:
                    emp = int(self.config.get('IMPORTACAO', 'empresa', fallback='1'))
                    fil = int(self.config.get('IMPORTACAO', 'filial', fallback='1'))
                    rows = fb.query(
                        "SELECT TIT_CODIGO, TIT_SERIE FROM TABELA_TITULO_REC WHERE TIT_EMPRESA = ? AND TIT_FILIAL = ?",
                        [emp, fil]
                    )
                    for row in rows:
                        chave = (str(row['tit_codigo'] or '').strip(), str(row['tit_serie'] or '').strip())
                        if chave[0]:
                            dados_existentes['documentos_tit'][chave] = True
                    dados_existentes['proximo_codigo'] = self._gerar_codigo_titulo(fb, emp, fil)

                    # Assinatura das PARCELAS ja gravadas: (codigo, serie,
                    # vencimento, valor). Usado para, quando "trazer parcelas
                    # novas" estiver ligado, reconhecer parcela por parcela e
                    # nao reimportar as que ja existem (evita duplicidade).
                    for row in fb.query(
                        "SELECT TPARC_CODIGO, TPARC_SERIE, TPARC_VENCIMENTO, TPARC_VALOR "
                        "FROM TABELA_TITULO_PARCELA_REC WHERE TPARC_EMPRESA = ? AND TPARC_FILIAL = ?",
                        [emp, fil]
                    ):
                        cod = str(row['tparc_codigo'] or '').strip().lstrip('0')
                        ser = str(row['tparc_serie'] or '').strip()
                        venc = row['tparc_vencimento'].isoformat() if row['tparc_vencimento'] else ''
                        val = round(float(row['tparc_valor'] or 0), 2)
                        dados_existentes['parcelas_tit'].add((cod, ser, venc, val))

                    # Itens sem numero de documento (avulsos) recebem codigo
                    # automatico novo a cada importacao, entao nao da para
                    # reconhece-los pelo codigo. Para nao reimportar/duplicar,
                    # marcamos como ja importado quando ja existe um titulo IMP
                    # com o mesmo cliente + valor + vencimento.
                    avulsos_existentes = set()
                    for row in fb.query(
                        "SELECT TIT_CLIENTE, TIT_TOTAL, TIT_VENCIMENTO FROM TABELA_TITULO_REC "
                        "WHERE TIT_EMPRESA = ? AND TIT_FILIAL = ? AND TIT_ORIGEM = 'IMP'",
                        [emp, fil]
                    ):
                        avulsos_existentes.add((
                            row['tit_cliente'],
                            round(float(row['tit_total'] or 0), 2),
                            row['tit_vencimento'].isoformat() if row['tit_vencimento'] else ''
                        ))
                    cache_cli = {}
                    for reg in self.registros_lidos:
                        reg['_avulso_dup'] = False
                        if self._num_doc_digitos(reg.get('numero_doc', '')):
                            continue
                        valor = self._parse_valor(reg.get('valor', '0'))
                        va = self._parse_valor(reg.get('valor_a_receber', '0'))
                        if valor == 0.0 and va > 0:
                            valor = va
                        documento = self._normalizar_documento(reg.get('documento', ''))
                        razao = str(reg.get('razao', '')).strip()
                        ck = (documento, razao.upper())
                        if ck in cache_cli:
                            cli = cache_cli[ck]
                        else:
                            cli = self._buscar_cliente(fb, emp, fil, documento, razao)
                            cache_cli[ck] = cli
                        if cli is None:
                            continue
                        emissao = self._parse_data(reg.get('emissao', ''))
                        vencimento = self._parse_data(reg.get('vencimento', ''))
                        if vencimento is None:
                            base = emissao or datetime.date.today()
                            vencimento = base + datetime.timedelta(days=30)
                        sig = (cli, round(valor, 2), vencimento.isoformat())
                        if sig in avulsos_existentes:
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
        # Guarda o ultimo snapshot do ERP para re-renderizar quando o usuario
        # (des)marca "trazer parcelas novas" sem precisar reconsultar o banco.
        if dados_existentes is not None:
            self._dados_existentes = dados_existentes
        else:
            dados_existentes = getattr(self, '_dados_existentes', None)

        # Selo deste render. A grade e preenchida em blocos com after(), entao um
        # render antigo pode continuar inserindo DEPOIS que outro limpou a tela —
        # a grade acumula duas analises e os cards somam tudo. O selo faz os
        # blocos do render antigo pararem.
        self._render_seq = getattr(self, '_render_seq', 0) + 1
        meu_seq = self._render_seq

        for i in self.tree.get_children(): self.tree.delete(i)
        self.dados_grid.clear()

        docs_existentes = dados_existentes.get('documentos_tit', {}) if dados_existentes else {}
        parcelas_existentes = dados_existentes.get('parcelas_tit', set()) if dados_existentes else set()
        trazer_parcelas = bool(getattr(self, 'var_trazer_parcelas', None) and self.var_trazer_parcelas.get())
        prox_cod = dados_existentes.get('proximo_codigo', 1) if dados_existentes else 1
        codigos_usados = set()
        # Codigos ja usados pela planilha (numero de documento cru). O codigo
        # automatico dos itens sem numero nao pode colidir com nenhum deles,
        # senao um item avulso seria juntado a um titulo real.
        codigos_planilha = {
            self._num_doc_digitos(r.get('numero_doc', '')).lstrip('0')
            for r in self.registros_lidos
            if self._num_doc_digitos(r.get('numero_doc', '')).lstrip('0')
        }

        # Flags de mapeamento (definem o comportamento de situação e "a receber")
        usar_status = bool(self.entradas_map['situacao_status'].get().strip())
        ar_mapeado = bool(self.entradas_map['valor_a_receber'].get().strip())

        items = []
        validos = 0
        total_conta = 0.0
        total_recebido = 0.0
        total_aberto = 0.0
        for reg in self.registros_lidos:
            parcela = self._parse_parcela(reg.get('parcela', ''))
            valor = self._parse_valor(reg.get('valor', '0'))
            valor_recebido = self._parse_valor(reg.get('valor_recebido', '0'))
            valor_a_receber = self._parse_valor(reg.get('valor_a_receber', '0'))
            if valor == 0.0 and valor_a_receber > 0:
                valor = valor_a_receber
            # "Valor a Receber" não mapeado -> calcula = Conta - Recebido
            if not ar_mapeado:
                valor_a_receber = max(valor - valor_recebido, 0.0)
            # Guarda os valores JÁ calculados para o import usar os mesmos
            reg['_valor_calc'] = valor
            reg['_recebido_calc'] = valor_recebido
            reg['_ar_calc'] = valor_a_receber
            razao = str(reg.get('razao', '')).strip()
            documento = self._normalizar_documento(reg.get('documento', ''))
            serie = str(reg.get('serie', '')).strip().upper() or SERIE_PADRAO
            numero_doc = self._num_doc_digitos(reg.get('numero_doc', ''))  # remove letras (R00099 -> 00099)
            reg['_numero_doc_limpo'] = numero_doc

            eh_excluido = usar_status and self._status_excluido(reg.get('situacao_status', ''))
            reg['_eh_excluido'] = eh_excluido

            # EXCLUIDO/SUBSTITUIDO entram baixados na emissão -> compõem o TOTAL do banco
            total_conta += valor

            codigo_auto = None
            if not numero_doc:
                while (str(prox_cod) in codigos_usados
                       or str(prox_cod) in codigos_planilha
                       or (str(prox_cod), serie) in docs_existentes):
                    prox_cod += 1
                codigo_auto = prox_cod
                prox_cod += 1
                codigos_usados.add(str(codigo_auto))

            if not numero_doc:
                numero_doc_exib = f"AUTO-{codigo_auto}"
                status = "JÁ CADASTRADO" if reg.get('_avulso_dup') else "OK"
            elif valor <= 0:
                numero_doc_exib = numero_doc
                status = "ERRO (Valor inv\u00e1lido)"
            elif not razao and not documento:
                numero_doc_exib = numero_doc
                status = "ERRO (Sem Cliente)"
            elif docs_existentes and (numero_doc.lstrip('0'), serie) in docs_existentes:
                numero_doc_exib = numero_doc
                # Titulo ja existe no ERP. Por padrao a linha inteira e
                # bloqueada. Com "trazer parcelas novas" ligado, olhamos parcela
                # a parcela: se ESTA parcela (mesmo vencimento + valor) ja existe,
                # continua bloqueada; se e nova, entra como mais uma parcela.
                if trazer_parcelas:
                    venc_chk = self._parse_data(reg.get('vencimento', ''))
                    sig_parc = (numero_doc.lstrip('0'), serie,
                                venc_chk.isoformat() if venc_chk else '',
                                round(valor, 2))
                    if sig_parc in parcelas_existentes:
                        status = "J\u00c1 CADASTRADO"
                    else:
                        status = "OK"
                        validos += 1
                else:
                    status = "J\u00c1 CADASTRADO"
            else:
                numero_doc_exib = numero_doc
                status = "OK"
                validos += 1

            if not numero_doc and status == "OK":
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

            # EXCLUIDO/SUBSTITUIDO seguem a regra antiga: entram baixados na data de
            # emiss\u00e3o (n\u00e3o ficam em aberto) e levam o STATUS na observa\u00e7\u00e3o, para
            # compor o total do banco do cliente.
            cancelado_status = (self._status_cancelado(reg.get('situacao_status', '')) or eh_excluido) if usar_status else False
            situacao = self._calcular_situacao(valor, valor_recebido, valor_a_receber,
                                               usar_status, cancelado_status)
            reg['_eh_cancelado'] = (situacao == "Cancelado")
            if situacao == "Cancelado":
                if eh_excluido:
                    reg['_observacao'] = str(reg.get('situacao_status', '')).strip() or "EXCLUIDO"
                else:
                    reg['_observacao'] = "T\u00edtulo cancelado"

            # Totais da barra de status. Normalmente s\u00f3 os t\u00edtulos que entram
            # (status OK). Com "trazer parcelas novas" ligado, tudo conta pelos
            # valores reais que v\u00e3o ao ERP: inclui os j\u00e1 cadastrados e os
            # cancelados/baixados (que entram baixados = recebido). Assim
            # Conta = Recebido + Aberto e d\u00e1 para conferir o total.
            conta_no_resumo = (status == "OK") or trazer_parcelas
            if conta_no_resumo:
                if situacao == "Cancelado":
                    if trazer_parcelas:
                        total_recebido += valor
                else:
                    rec_item, ab_item, _n = self._reparticao(valor, valor_a_receber, False)
                    total_recebido += rec_item
                    total_aberto += ab_item
            reg['_situacao'] = situacao

            tag = 'OK' if status == 'OK' else 'ERRO'
            cliente_nome = razao or str(reg.get('documento', '')) or "-"
            items.append((
                (check, status, numero_doc_exib, cliente_nome[:60],
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
                if len(self.registros_lidos) > 0 and hasattr(self, 'btn_exportar_csv'): self.btn_exportar_csv.config(state=tk.NORMAL)
                self.progresso['value'] = 100
                self.lbl_status.config(
                    text=f"Pronto. {validos} t\u00edtulos de {total} lidos. "
                         f"Conta: R$ {total_conta:,.2f} | Recebido: R$ {total_recebido:,.2f} | Aberto: R$ {total_aberto:,.2f}"
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
            if not v or v == '-': return -999999 if reverse else 999999
            try: return float(v.replace(',', '.'))
            except ValueError: return v.lower()
        l.sort(key=lambda t: valor_para_ordenar(t[0]), reverse=reverse)
        for index, (_, k) in enumerate(l): self.tree.move(k, '', index)
        for c in self.colunas:
            arrow = " ▼" if self._sort_directions[c] else " ▲" if c == col else " ↕"
            self.tree.heading(c, text=c + arrow, command=lambda x=c: self._sort_treeview(x))

    def _on_toggle_trazer_parcelas(self):
        # Reavalia a grade com o mesmo snapshot do ERP (nao reconsulta o banco).
        if not getattr(self, 'registros_lidos', None):
            return
        self._renderizar_preview()

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

    @staticmethod
    def _reparticao(valor, valor_a_receber, cancelado):
        """Como o valor da linha se divide entre BAIXADO e EM ABERTO no ERP.

        Mesma decisão do plano de parcelas da importação. Existe porque os cards
        usavam `valor_a_receber or valor`: com a coluna de saldo mapeada, saldo 0
        é informação (título quitado), mas 0.0 é falso em Python e o `or` trocava
        pelo valor cheio da conta — o card mostrava mais "em aberto" do que o ERP
        recebia. Devolve (recebido, aberto, qtde_parcelas).
        """
        if cancelado:
            return valor, 0.0, 1                  # baixado na data de emissão
        aberto = round(valor_a_receber, 2)
        recebido = round(valor - aberto, 2)
        if recebido < 0:                           # saldo maior que o valor
            recebido, aberto = 0.0, round(valor, 2)
        if aberto <= 0.0:
            return valor, 0.0, 1                   # parcela baixada
        if recebido <= 0.0:
            return 0.0, valor, 1                   # parcela em aberto
        return recebido, aberto, 2                 # parcial: baixado + saldo

    def _atualizar_cards_resumo(self):
        """Calcula e atualiza os valores nos cards de resumo."""
        total_conta = 0.0
        total_recebido = 0.0
        total_aberto = 0.0

        # Com "trazer parcelas novas" ligado, os cards mostram os valores REAIS
        # que vao para o ERP: os cancelados/excluidos entram BAIXADOS na emissao,
        # entao contam como recebido/baixado. Assim Conta = Recebido + Aberto e da
        # para conferir o total (import anterior + esta) contra o relatorio.
        trazer = bool(getattr(self, 'var_trazer_parcelas', None) and self.var_trazer_parcelas.get())

        for item_id in self.tree.get_children():
            reg = self.dados_grid.get(item_id)
            if not reg:
                continue

            # Usa os valores já calculados no preview (auto-cálculo de "a receber" incluso)
            valor = reg.get('_valor_calc')
            if valor is None:
                valor = self._parse_valor(reg.get('valor', '0'))
            valor_recebido = reg.get('_recebido_calc')
            if valor_recebido is None:
                valor_recebido = self._parse_valor(reg.get('valor_recebido', '0'))
            valor_a_receber = reg.get('_ar_calc')
            if valor_a_receber is None:
                valor_a_receber = self._parse_valor(reg.get('valor_a_receber', '0'))
            situacao = reg.get('_situacao', '')

            total_conta += valor

            if situacao == "Cancelado":
                # Baixado na emissao -> conta como recebido/baixado (so quando
                # "trazer" esta ligado, para os cards fecharem com o ERP).
                if trazer:
                    total_recebido += valor
            else:
                rec_item, ab_item, _n = self._reparticao(valor, valor_a_receber, False)
                total_recebido += rec_item
                total_aberto += ab_item

        self.card_total_conta.lbl_valor.config(text=f"R$ {total_conta:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        self.card_recebido.lbl_valor.config(text=f"R$ {total_recebido:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        self.card_aberto.lbl_valor.config(text=f"R$ {total_aberto:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

    def _exportar_csv(self):
        """Exporta os dados atualmente visíveis na grade para um arquivo CSV."""
        if not self.tree.get_children():
            messagebox.showwarning("Aviso", "Não há dados na grade para exportar.", parent=self)
            return

        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("Arquivo CSV", "*.csv")],
            initialfile="export_contas_receber.csv",
            title="Salvar Visão Atual como CSV"
        )

        if not filepath:
            return

        try:
            with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(self.colunas)  # Escreve o cabeçalho
                for item_id in self.tree.get_children():
                    writer.writerow(self.tree.item(item_id, 'values'))
            messagebox.showinfo("Sucesso", f"Dados exportados com sucesso para:\n{filepath}", parent=self)
        except Exception as e:
            messagebox.showerror("Erro", f"Ocorreu um erro ao exportar o arquivo:\n{e}", parent=self)

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
            # o rateio e lido AQUI, na thread da UI — a de gravacao nao toca widget
            cc_sel, conta_sel = self._rateio_escolhido()
            rateio = (cc_sel, conta_sel, self._exercicio_contabil, self._conta_reduzido)
            self._salvar_config_mapeamento()
            self.btn_importar.config(state=tk.DISABLED)
            self.btn_analisar.config(state=tk.DISABLED)
            self.lbl_status.config(text="Importando contas a receber...")
            threading.Thread(target=self._importacao_bg,
                             args=(selecionados, lc_selecionado, rateio), daemon=True).start()

    def _gerar_codigo_titulo(self, fb, emp, fil):
        """Retorna o primeiro inteiro ausente na sequencia de TIT_CODIGO (preenche lacunas)."""
        rows = fb.query(
            "SELECT TIT_CODIGO FROM TABELA_TITULO_REC WHERE TIT_EMPRESA = ? AND TIT_FILIAL = ?",
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
        # Procura a primeira lacuna
        for i in range(1, max(existentes) + 2):
            if i not in existentes:
                return i
        return max(existentes) + 1

    def _proxima_parcela(self, fb, emp, fil, codigo, serie):
        """Retorna o proximo numero de parcela disponivel para um titulo."""
        res = fb.query(
            "SELECT COALESCE(MAX(TPARC_PARCELA), 0) + 1 AS PROX FROM TABELA_TITULO_PARCELA_REC "
            "WHERE TPARC_EMPRESA = ? AND TPARC_FILIAL = ? AND TPARC_CODIGO = ? AND TPARC_SERIE = ?",
            [emp, fil, codigo, serie]
        )
        return int(res[0]['prox'])

    def _buscar_cliente(self, fb, emp, fil, documento, razao):
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

    def _buscar_vendedor_cliente(self, fb, emp, fil, cliente_codigo):
        try:
            res = fb.query(
                "SELECT VEND_CODIGO FROM TABELA_VENDEDOR WHERE VEND_EMPRESA = ? AND VEND_FILIAL = ? "
                "AND TRIM(UPPER(VEND_NOME)) = ("
                "  SELECT TRIM(UPPER(CF_REPRESENTANTE)) FROM TABELA_CLI_FOR "
                "  WHERE CF_EMPRESA = ? AND CF_FILIAL = ? AND CF_CODIGO = ?"
                ")",
                [emp, fil, emp, fil, cliente_codigo]
            )
            if res:
                return res[0]['vend_codigo']
        except Exception:
            pass
        res = fb.query(
            "SELECT FIRST 1 VEND_CODIGO FROM TABELA_VENDEDOR WHERE VEND_EMPRESA = ? AND VEND_FILIAL = ? AND VEND_ATIVO = 'S'",
            [emp, fil]
        )
        return res[0]['vend_codigo'] if res else 1

    def _recalcular_titulos(self):
        resp = messagebox.askyesno("Recalcular Títulos",
            "Isso vai recalcular TIT_TOTAL de todos os títulos importados pelo sistema\n"
            "(ORIGEM='IMP') somando o valor de todas as parcelas de cada título.\n\n"
            "Deseja continuar?")
        if not resp:
            return

        self.btn_recalcular.config(state=tk.DISABLED, text="⏳ Recalculando...")
        self.lbl_status.config(text="Recalculando títulos...")
        threading.Thread(target=self._recalcular_bg, daemon=True).start()

    def _recalcular_bg(self):
        corrigidos = 0
        erros = 0
        try:
            emp = int(self.config.get('IMPORTACAO', 'empresa', fallback='1'))
            fil = int(self.config.get('IMPORTACAO', 'filial', fallback='1'))
            agora = datetime.datetime.now()
            ult_grav = agora.strftime('%Y-%m-%d %H:%M:%S')

            with FirebirdService(self.config_db) as fb:
                titulos = fb.query(
                    "SELECT TIT_CODIGO, TIT_SERIE FROM TABELA_TITULO_REC "
                    "WHERE TIT_EMPRESA = ? AND TIT_FILIAL = ? AND TIT_ORIGEM = 'IMP'",
                    [emp, fil]
                )

                for tit in titulos:
                    try:
                        cod = tit['tit_codigo']
                        ser = tit['tit_serie']

                        rows = fb.query(
                            "SELECT COALESCE(SUM(TPARC_VALOR), 0) AS TOTAL "
                            "FROM TABELA_TITULO_PARCELA_REC "
                            "WHERE TPARC_EMPRESA = ? AND TPARC_FILIAL = ? AND TPARC_CODIGO = ? AND TPARC_SERIE = ?",
                            [emp, fil, cod, ser]
                        )
                        total = rows[0]['total'] if rows else 0.0

                        fb.execute("""
                            UPDATE TABELA_TITULO_REC SET
                                TIT_TOTAL = ?,
                                TIT_TOTAL_PARCELAS = ?,
                                TIT_TOTAL_CC = ?,
                                TIT_TOTAL_CONTABIL = ?,
                                TIT_VALOR = ?,
                                TIT_TOTAL_NF = ?,
                                TIT_ULT_GRAVACAO = ?
                            WHERE TIT_EMPRESA = ? AND TIT_FILIAL = ? AND TIT_CODIGO = ? AND TIT_SERIE = ?
                        """, [total, total, total, total, total, total,
                              ult_grav, emp, fil, cod, ser])

                        corrigidos += 1
                    except Exception:
                        erros += 1

            msg = f"Recálculo concluído!\n\n{corrigidos} títulos corrigidos."
            if erros:
                msg += f"\n{erros} erro(s) durante o recálculo."
            self.parent.after(0, lambda m=msg: self._safe_showinfo("Concluído", m))

        except Exception as e:
            self.parent.after(0, lambda err=e: self._safe_showerror("Erro", f"Erro no recálculo:\n{err}"))
        finally:
            self.parent.after(0, lambda: self.btn_recalcular.config(state=tk.NORMAL, text="🔁 Recalcular Títulos"))
            self.parent.after(0, lambda: self.lbl_status.config(text="Pronto."))

    def _importacao_bg(self, selecionados, lc_selecionado=None, rateio=None):
        cc_rateio, conta_rateio, exerc_rateio, red_rateio = rateio or (None, None, None, {})
        log_linhas = []
        inseridos = 0
        erros = 0
        excluidos = 0
        pulados_avulso = 0     # avulsos que já estavam no ERP
        sem_cliente = 0        # linhas cujo cliente não existe no cadastro
        titulos_existentes = 0 # títulos que já existiam (só parcelas novas)
        grupos_sem_novidade = 0
        try:
            emp = int(self.config.get('IMPORTACAO', 'empresa', fallback='1'))
            fil = int(self.config.get('IMPORTACAO', 'filial', fallback='1'))
            if lc_selecionado is None:
                lc_emp, lc_fil, lc_cod = emp, fil, 1
            else:
                lc_emp, lc_fil, lc_cod = lc_selecionado
            agora = datetime.datetime.now()

            with FirebirdService(self.config_db) as fb:
                tit_existentes = {}
                for row in fb.query(
                    "SELECT TIT_CODIGO, TIT_SERIE, TIT_CLIENTE FROM TABELA_TITULO_REC WHERE TIT_EMPRESA = ? AND TIT_FILIAL = ?",
                    [emp, fil]
                ):
                    k = (str(row['tit_codigo'] or '').strip(), str(row['tit_serie'] or '').strip(), row['tit_cliente'])
                    tit_existentes[k] = True

                # Assinaturas de avulsos ja importados (cliente + valor +
                # vencimento). Como avulsos ganham codigo novo a cada vez, esta e
                # a unica forma de nao reimporta-los em duplicidade.
                # Guarda o codigo/serie de quem ja esta la, para o log dizer
                # QUAL titulo bloqueou a linha (antes so dizia "ja importado").
                avulsos_existentes = {}
                for row in fb.query(
                    "SELECT TIT_CODIGO, TIT_SERIE, TIT_CLIENTE, TIT_TOTAL, TIT_VENCIMENTO "
                    "FROM TABELA_TITULO_REC "
                    "WHERE TIT_EMPRESA = ? AND TIT_FILIAL = ? AND TIT_ORIGEM = 'IMP'",
                    [emp, fil]
                ):
                    sig = (row['tit_cliente'],
                           round(float(row['tit_total'] or 0), 2),
                           row['tit_vencimento'].isoformat() if row['tit_vencimento'] else '')
                    avulsos_existentes.setdefault(
                        sig, f"{str(row['tit_codigo'] or '').strip()}/"
                             f"{str(row['tit_serie'] or '').strip()}")

                # ---- Caches (eliminam consulta de cliente/vendedor por título) ----
                self.parent.after(0, lambda: self.lbl_status.config(text="Carregando clientes e vendedores..."))
                cli_por_doc = {}
                cli_por_nome = {}
                rep_por_cliente = {}
                for row in fb.query(
                    "SELECT CF_CODIGO, CF_CPF_CGC, CF_RAZAO, CF_FANTASIA, CF_REPRESENTANTE "
                    "FROM TABELA_CLI_FOR WHERE CF_EMPRESA = ? AND CF_FILIAL = ?",
                    [emp, fil]
                ):
                    cod = row['cf_codigo']
                    d = re.sub(r'\D', '', str(row['cf_cpf_cgc'] or ''))
                    if d:
                        cli_por_doc.setdefault(d, cod)
                    nome = str(row['cf_razao'] or '').strip().upper()
                    if nome:
                        cli_por_nome.setdefault(nome, cod)
                    fant = str(row['cf_fantasia'] or '').strip().upper()
                    if fant:
                        cli_por_nome.setdefault(fant, cod)
                    rep_por_cliente[cod] = str(row['cf_representante'] or '').strip().upper()

                vend_por_nome = {}
                for row in fb.query(
                    "SELECT VEND_CODIGO, VEND_NOME FROM TABELA_VENDEDOR WHERE VEND_EMPRESA = ? AND VEND_FILIAL = ?",
                    [emp, fil]
                ):
                    n = str(row['vend_nome'] or '').strip().upper()
                    if n:
                        vend_por_nome.setdefault(n, row['vend_codigo'])
                _vd = fb.query(
                    "SELECT FIRST 1 VEND_CODIGO FROM TABELA_VENDEDOR "
                    "WHERE VEND_EMPRESA = ? AND VEND_FILIAL = ? AND VEND_ATIVO = 'S'",
                    [emp, fil]
                )
                vend_default = _vd[0]['vend_codigo'] if _vd else 1
                vend_cache = {}

                def _vend_for(cli):
                    if cli in vend_cache:
                        return vend_cache[cli]
                    rep = rep_por_cliente.get(cli, '')
                    v = vend_por_nome.get(rep) if rep else None
                    if v is None:
                        v = vend_default
                    vend_cache[cli] = v
                    return v

                # Cursor único + commit em lote (evita 1 commit por INSERT)
                cur = fb.conn.cursor()

                # Agrupa por (codigo, serie, cliente) — as parcelas do mesmo
                # titulo ficam juntas (mesmo TPARC_CODIGO/SERIE/CLIENTE, mudando
                # so o TPARC_PARCELA). O codigo e gravado SEM zeros a esquerda
                # porque o banco tem o trigger TR_TITULO_REC_TRIM_CODIGO que faz
                # TRIM(LEADING '0') no TIT_CODIGO; a parcela nao tem esse trigger,
                # entao precisamos ja mandar o codigo sem zeros nos dois, senao a
                # FK da parcela quebra. Como '72' e '0000072' viram o MESMO codigo
                # no ERP, eles caem no mesmo titulo (como parcelas diferentes) —
                # nada e descartado. O cliente entra na chave para que o mesmo
                # numero de documento de clientes diferentes vire titulos separados.
                cache_cliente = {}
                grupos = {}
                for item in selecionados:
                    if item.get('_status') != 'OK':
                        continue
                    if item.get('_eh_excluido'):
                        excluidos += 1
                    num_doc = (item.get('_numero_doc_auto', '')
                               or item.get('_numero_doc_limpo')
                               or self._num_doc_digitos(item.get('numero_doc', '')))
                    serie = item.get('_serie', SERIE_PADRAO)
                    codigo_tit = num_doc.lstrip('0') or num_doc

                    documento = item.get('_documento_limpo', '')
                    razao = str(item.get('razao', '')).strip()
                    chave_cli = (documento, razao.upper())
                    if chave_cli in cache_cliente:
                        cliente_codigo = cache_cliente[chave_cli]
                    else:
                        cliente_codigo = None
                        if documento:
                            cliente_codigo = cli_por_doc.get(re.sub(r'\D', '', documento))
                        if cliente_codigo is None and razao:
                            rn = razao.upper()
                            cliente_codigo = cli_por_nome.get(rn) or cli_por_nome.get(rn[:50])
                        cache_cliente[chave_cli] = cliente_codigo

                    if cliente_codigo is None:
                        # Dizer QUEM não foi achado: sem isso não há como
                        # corrigir o cadastro nem saber quanto ficou de fora.
                        log_linhas.append(
                            f"⚠ {num_doc} — Cliente não encontrado no ERP, linha fora: "
                            f"documento '{documento}' / razão '{razao[:40]}' "
                            f"(valor {self._parse_valor(item.get('valor', '0')):.2f})")
                        sem_cliente += 1
                        erros += 1
                        continue

                    grupos.setdefault((codigo_tit, serie, cliente_codigo), []).append(item)

                ult_grav = agora.strftime('%Y-%m-%d %H:%M:%S')

                grupos_lista = list(grupos.items())
                total_grp = len(grupos_lista)
                for gi, ((codigo_tit, serie, cliente_codigo), itens_grupo) in enumerate(grupos_lista):
                    if gi % 50 == 0:
                        self.parent.after(0, lambda d=gi, t=total_grp: self.lbl_status.config(
                            text=f"Gravando {d+1}/{t} títulos..."))
                    num_doc = codigo_tit  # usado apenas nas mensagens de log
                    try:
                        ref = itens_grupo[0]

                        vendedor_codigo = _vend_for(cliente_codigo)

                        # Dados do titulo (usando primeiro item como referencia)
                        emissao = self._parse_data(ref.get('emissao', '')) or agora.date()
                        vencimento = self._parse_data(ref.get('vencimento', ''))
                        data_registro = self._parse_data(ref.get('data_registro', '')) or agora.date()
                        if vencimento is None:
                            vencimento = emissao + datetime.timedelta(days=30)
                        dias = (vencimento - emissao).days if vencimento else 0

                        titulo_existe = (codigo_tit, serie, cliente_codigo) in tit_existentes

                        parc_existentes = set()
                        if titulo_existe:
                            for row in fb.query(
                                "SELECT TPARC_PARCELA FROM TABELA_TITULO_PARCELA_REC WHERE TPARC_EMPRESA = ? AND TPARC_FILIAL = ? "
                                "AND TPARC_CODIGO = ? AND TPARC_SERIE = ? AND TPARC_CLIENTE = ?",
                                [emp, fil, codigo_tit, serie, cliente_codigo]
                            ):
                                parc_existentes.add(int(row['tparc_parcela']))

                        # Monta as parcelas novas do titulo. NAO deduplica nada
                        # (todos os valores da planilha precisam entrar); apenas
                        # garante numero de parcela unico dentro do titulo, para
                        # que TIT_TOTAL = soma das parcelas gravadas.
                        itens_novos = []
                        usados_parc = set(parc_existentes)
                        for item in itens_grupo:
                            parcela_num = item.get('_parcela_auto') or self._parse_parcela(item.get('parcela', ''))

                            while parcela_num in usados_parc:
                                parcela_num += 1
                            usados_parc.add(parcela_num)
                            item['_parcela_final'] = parcela_num
                            itens_novos.append(item)

                        if not itens_novos:
                            log_linhas.append(f"⚠ {num_doc} — Todas as parcelas já existem, pulando grupo")
                            grupos_sem_novidade += 1
                            continue

                        total_grupo = sum(self._parse_valor(item.get('valor', '0')) for item in itens_novos)

                        # Trava anti-duplicidade dos avulsos (linhas sem número de
                        # documento, que ganham código novo a cada importação):
                        # confere ANTES de montar o plano, senão o log escreve as
                        # parcelas e só depois diz que pulou — parecia que tinha
                        # importado e desfeito.
                        eh_avulso = bool(ref.get('_numero_doc_auto'))
                        sig_avulso = (cliente_codigo, round(total_grupo, 2),
                                      vencimento.isoformat() if vencimento else '')
                        if eh_avulso and sig_avulso in avulsos_existentes:
                            onde = avulsos_existentes[sig_avulso]
                            venc_txt = vencimento.strftime('%d/%m/%Y') if vencimento else '-'
                            log_linhas.append(
                                f"⏭ Avulso já estava no ERP — título {onde}, cliente "
                                f"{cliente_codigo}, valor {total_grupo:.2f}, venc {venc_txt}. "
                                f"Não reimportado.")
                            pulados_avulso += 1
                            continue

                        def inserir_titulo(valor_tit, num_parcelas, observacao=''):
                            sql = """
                                INSERT INTO TABELA_TITULO_REC (
                                    TIT_EMPRESA, TIT_FILIAL, TIT_CODIGO, TIT_SERIE,
                                    TIT_CLIENTE_EMPRESA, TIT_CLIENTE_FILIAL, TIT_CLIENTE,
                                    TIT_EMISSAO, TIT_DATA,
                                    TIT_TL_EMPRESA, TIT_TL_FILIAL, TIT_TIPO_LANCAMENTO,
                                    TIT_PARCELAS, TIT_VENCIMENTO, TIT_DIAS,
                                    TIT_TOTAL_NF, TIT_ORIGEM,
                                    TIT_VALOR, TIT_MOEDA_EMPRESA, TIT_MOEDA_FILIAL,
                                    TIT_VENDEDOR_EMPRESA, TIT_VENDEDOR_FILIAL, TIT_VENDEDOR,
                                    TIT_VALOR_MOEDA, TIT_QTDE_MOEDA,
                                    TIT_TOTAL, TIT_TOTAL_CC, TIT_TOTAL_CONTABIL, TIT_TOTAL_PARCELAS,
                                    TIT_DEVOLUCAO,
                                    TIT_SEGMENTO_EMP, TIT_SEGMENTO_FIL,
                                    TIT_STATUS, TIT_USUARIO,
                                    TIT_MOV_EMPRESA, TIT_MOV_FILIAL,
                                    TIT_ANIMAL_EMP, TIT_ANIMAL_FIL,
                                    TIT_ULT_GRAVACAO,
                                    TIT_COD_CONDPGTO,
                                    TIT_NAT_OP_EMPRESA, TIT_NAT_OP_FILIAL
                            """
                            params = [
                                emp, fil, codigo_tit, serie,
                                emp, fil, cliente_codigo,
                                emissao, data_registro,
                                emp, fil, 2,
                                num_parcelas, vencimento, dias,
                                valor_tit, 'IMP',
                                valor_tit, emp, fil,
                                emp, fil, vendedor_codigo,
                                0.0, 0.0,
                                valor_tit, valor_tit, valor_tit, valor_tit,
                                'N',
                                emp, fil,
                                'N', 'SISTEC_IMP',
                                emp, fil,
                                emp, fil,
                                ult_grav,
                                None,
                                emp, fil
                            ]
                            if observacao:
                                sql += ", TIT_OBS"
                                sql += ") VALUES ("
                                sql += ", ".join("?" for _ in params) + ", ?)"
                                params.append(observacao)
                            else:
                                sql += ") VALUES ("
                                sql += ", ".join("?" for _ in params) + ")"
                            cur.execute(sql, params)
                            # rateio no mesmo cursor/transacao do titulo: se o titulo
                            # cair, o centro de custo dele nao fica orfao
                            rateio_contabil.rateio_receber(
                                cur, emp, fil, codigo_tit, serie, cliente_codigo,
                                emissao, valor_tit, cc=cc_rateio, conta=conta_rateio,
                                exercicio=exerc_rateio, reduzidos=red_rateio)

                        def inserir_parcela(parcela_num, valor_parc, valor_pg, pg_sn, baixa_data, data_cred,
                                            val_desc, val_juros, situacao_pg, venc_parc, parc_boleto=''):
                            if pg_sn == 'S' and baixa_data:
                                tp_data_cred = data_cred or baixa_data
                            else:
                                tp_data_cred = None

                            dias_parc = (venc_parc - emissao).days if venc_parc else dias

                            sql_parc = """
                                INSERT INTO TABELA_TITULO_PARCELA_REC (
                                    TPARC_EMPRESA, TPARC_FILIAL, TPARC_CODIGO, TPARC_SERIE,
                                    TPARC_PARCELA,
                                    TPARC_CLIENTE_EMPRESA, TPARC_CLIENTE_FILIAL, TPARC_CLIENTE,
                                    TPARC_EMISSAO, TPARC_DIGITACAO, TPARC_DIAS,
                                    TPARC_VENCIMENTO,
                                    TPARC_MOEDA_EMPRESA, TPARC_MOEDA_FILIAL,
                                    TPARC_VALOR,
                                    TPARC_ABATIMENTO,
                                    TPARC_VENDEDOR_EMPRESA, TPARC_VENDEDOR_FILIAL,
                                    TPARC_LC_EMPRESA, TPARC_LC_FILIAL, TPARC_LOCAL_COBRANCA,
                                    TPARC_TC_EMPRESA, TPARC_TC_FILIAL, TPARC_TIPO_COBRANCA,
                                    TPARC_VALOR_PG, TPARC_PG,
                                    TPARC_DESCONTO, TPARC_JUROS,
                                    TPARC_CORRECAO, TPARC_DESPESA_BANCO, TPARC_DESPESA_CARTORIO,
                                    TPARC_LOCAL_RECEBIMENTO,
                                    TPARC_ORIGEM,
                                    TPARC_DUPLICATA,
                                    TPARC_COMISSAO_VENDEDOR, TPARC_COMISSAO_COMPRADOR,
                                    TPARC_NEGATIVADO,
                                    TPARC_TIPO_BAIXA,
                                    TPARC_ULT_GRAVACAO,
                                     TPARC_CX_TIPO_PAGTO_EMP, TPARC_CX_TIPO_PAGTO_FIL,
                                     TPARC_VALOR_MULTA, TPARC_JUROS_MORA,
                                     TPARC_VMULTA,
                                     TPARC_NOSSO_NUMERO
                                 ) VALUES (
                                     ?, ?, ?, ?,
                                     ?,
                                     ?, ?, ?,
                                     ?, ?, ?,
                                     ?,
                                     ?, ?,
                                     ?,
                                     ?,
                                     ?, ?,
                                     ?, ?, ?,
                                     ?, ?, ?,
                                     ?, ?,
                                     ?, ?,
                                     ?, ?, ?,
                                     ?,
                                     'IMP',
                                     'N',
                                     ?, ?,
                                     'N',
                                     ?,
                                     ?,
                                     ?, ?,
                                     ?, ?,
                                     ?,
                                     ?
                                )
                            """
                            params_parc = [
                                emp, fil, codigo_tit, serie,
                                parcela_num,
                                emp, fil, cliente_codigo,
                                emissao, data_registro, dias_parc,
                                venc_parc,
                                emp, fil,
                                valor_parc,
                                0.0,
                                emp, fil,
                                lc_emp, lc_fil, lc_cod,
                                emp, fil, 1,
                                valor_pg, pg_sn,
                                val_desc, val_juros,
                                0.0, 0.0, 0.0,
                                1,
                                vendedor_codigo, 0.0, # TPARC_COMISSAO_VENDEDOR, TPARC_COMISSAO_COMPRADOR
                                1 if pg_sn == 'S' else None,
                                 ult_grav,
                                 emp, fil,
                                 0.0, val_juros if situacao_pg else 0.0,
                                 0.0,
                                 parc_boleto or None
                             ]

                            try:
                                cur.execute(sql_parc, params_parc)
                            except Exception as e:
                                log_linhas.append(f"  !!! PARCEL INSERT ERROR: {e}")
                                log_linhas.append(f"  !!! Key: (emp={emp}, fil={fil}, cod={codigo_tit}, serie={serie}, parc={parcela_num}, cli={cliente_codigo})")
                                raise

                            if pg_sn == 'S' and baixa_data:
                                try:
                                    cur.execute("""
                                        UPDATE TABELA_TITULO_PARCELA_REC SET
                                            TPARC_BAIXA = ?,
                                            TPARC_DATA_CREDITO = ?,
                                            TPARC_DATA_CREDITO_BAIXA = ?
                                        WHERE TPARC_EMPRESA = ? AND TPARC_FILIAL = ? AND TPARC_CODIGO = ? AND TPARC_SERIE = ? AND TPARC_PARCELA = ?
                                    """, [baixa_data, tp_data_cred, tp_data_cred, emp, fil, codigo_tit, serie, parcela_num])
                                except Exception as e:
                                    log_linhas.append(f"  !!! PARCEL UPDATE ERROR: {e}")

                        observacao_tit = next((item.get('_observacao', '') for item in itens_novos if item.get('_observacao')), '')

                        # Monta o plano de parcelas garantindo:
                        #  - TIT_TOTAL = soma das parcelas (= valor da conta)
                        #  - em aberto no ERP = valor a receber (parcela com PG=N)
                        #  - cancelado (sem recebido e sem a receber) entra com o valor
                        #    TOTAL, porem BAIXADO na data de emissao
                        plano = []
                        prox_parcela_saldo = max(usados_parc) + 1
                        for item in itens_novos:
                            parcela = item['_parcela_final']
                            # Usa os valores JÁ calculados no preview (inclui auto-cálculo
                            # de "a receber" quando a coluna não foi mapeada) — garante que
                            # o gravado bate com o que foi validado na tela.
                            valor = item.get('_valor_calc')
                            if valor is None:
                                valor = self._parse_valor(item.get('valor', '0'))
                            valor_a_receber = item.get('_ar_calc')
                            if valor_a_receber is None:
                                valor_a_receber = self._parse_valor(item.get('valor_a_receber', '0'))
                            if valor == 0.0 and valor_a_receber > 0:
                                valor = valor_a_receber
                            desconto = self._parse_valor(item.get('desconto', '0'))
                            juros = self._parse_valor(item.get('juros', '0'))
                            venc_parc = self._parse_data(item.get('vencimento', '')) or vencimento
                            boleto = str(item.get('boleto', '') or '').strip()
                            emissao_item = self._parse_data(item.get('emissao', '')) or emissao
                            data_receb = self._parse_data(item.get('data_recebimento', ''))

                            if item.get('_eh_cancelado'):
                                plano.append((parcela, valor, valor, 'S', emissao_item, emissao_item,
                                              desconto, juros, True, venc_parc, boleto))
                                log_linhas.append(f"  {num_doc} \u2014 Parcela {parcela} valor {valor:.2f} CANCELADO (baixado na emissao)")
                                continue

                            # Mesma repartição que os cards mostram (uma função só)
                            pago, aberto, _n_parc = self._reparticao(
                                valor, valor_a_receber, False)
                            baixa = data_receb or emissao_item

                            if aberto <= 0.0:
                                plano.append((parcela, valor, valor, 'S', baixa, baixa,
                                              desconto, juros, True, venc_parc, boleto))
                                log_linhas.append(f"  {num_doc} \u2014 Parcela {parcela} valor {valor:.2f} baixado")
                            elif pago <= 0.0:
                                plano.append((parcela, valor, 0.0, 'N', None, None,
                                              desconto, juros, False, venc_parc, boleto))
                                log_linhas.append(f"  {num_doc} \u2014 Parcela {parcela} valor {valor:.2f} em aberto")
                            else:
                                plano.append((parcela, pago, pago, 'S', baixa, baixa,
                                              desconto, juros, True, venc_parc, boleto))
                                plano.append((prox_parcela_saldo, aberto, 0.0, 'N', None, None,
                                              0.0, 0.0, False, venc_parc, boleto))
                                log_linhas.append(f"  {num_doc} \u2014 Parcela {parcela} parcial: baixado {pago:.2f}, saldo {aberto:.2f} vira parcela {prox_parcela_saldo}")
                                prox_parcela_saldo += 1

                        n_parcelas = len(plano)

                        if eh_avulso:
                            # marca o que acabou de entrar, para a mesma planilha
                            # não gravar o mesmo avulso duas vezes
                            avulsos_existentes[sig_avulso] = f"{codigo_tit}/{serie}"

                        if not titulo_existe:
                            inserir_titulo(total_grupo, n_parcelas, observacao_tit)
                            inseridos += 1
                            tit_existentes[(codigo_tit, serie, cliente_codigo)] = True
                        else:
                            log_linhas.append(f"  {num_doc} \u2014 Titulo existente, inserindo apenas parcelas novas")
                            titulos_existentes += 1
                            cur.execute("""
                                UPDATE TABELA_TITULO_REC SET
                                    TIT_TOTAL = COALESCE(TIT_TOTAL, 0) + ?,
                                    TIT_TOTAL_PARCELAS = COALESCE(TIT_TOTAL_PARCELAS, 0) + ?,
                                    TIT_TOTAL_CC = COALESCE(TIT_TOTAL_CC, 0) + ?,
                                    TIT_TOTAL_CONTABIL = COALESCE(TIT_TOTAL_CONTABIL, 0) + ?,
                                    TIT_VALOR = COALESCE(TIT_VALOR, 0) + ?,
                                    TIT_TOTAL_NF = COALESCE(TIT_TOTAL_NF, 0) + ?,
                                    TIT_PARCELAS = COALESCE(TIT_PARCELAS, 0) + ?,
                                    TIT_ULT_GRAVACAO = ?
                                WHERE TIT_EMPRESA = ? AND TIT_FILIAL = ? AND TIT_CODIGO = ? AND TIT_SERIE = ? AND TIT_CLIENTE = ?
                            """, [total_grupo, total_grupo, total_grupo, total_grupo, total_grupo, total_grupo,
                                  n_parcelas, ult_grav, emp, fil, codigo_tit, serie, cliente_codigo])

                        for p_parc in plano:
                            inserir_parcela(*p_parc)

                    except Exception as e:
                        erros += 1
                        log_linhas.append(f"❌ Erro ao inserir {num_doc}: {e}")

                    # Commit em lote (não 1 por INSERT) — o que mais acelera
                    if (gi + 1) % 300 == 0:
                        try:
                            fb.conn.commit()
                            cur = fb.conn.cursor()
                        except Exception:
                            pass

                fb.conn.commit()  # grava o restante

            msg = f"Processamento conclu\u00eddo!\n\n{inseridos} t\u00edtulo(s) cadastrados."
            if titulos_existentes:
                msg += f"\n{titulos_existentes} t\u00edtulo(s) j\u00e1 existiam \u2014 entraram s\u00f3 as parcelas novas."
            if pulados_avulso:
                msg += (f"\n{pulados_avulso} avulso(s) sem n\u00famero de documento j\u00e1 estavam "
                        f"no ERP e N\u00c3O foram reimportados.")
            if sem_cliente:
                msg += f"\n{sem_cliente} linha(s) ficaram fora: cliente n\u00e3o cadastrado."
            if excluidos:
                msg += f"\n{excluidos} t\u00edtulo(s) EXCLU\u00cdDO/SUBSTITU\u00cdDO trazidos baixados (comp\u00f5em o total)."
            if erros:
                msg += f"\n{erros} erro(s) durante a importa\u00e7\u00e3o. Veja o log para detalhes."
            if excluidos:
                log_linhas.append(f"RESUMO: {excluidos} t\u00edtulo(s) EXCLU\u00cdDO/SUBSTITU\u00cdDO trazidos baixados na emiss\u00e3o, com o STATUS na observa\u00e7\u00e3o.")
            self.parent.after(0, lambda m=msg: self._safe_showinfo("Conclu\u00eddo", m))

            # Resumo no TOPO do log: sem isso o arquivo abre em centenas de
            # linhas "pulando" e parece que a importacao falhou, quando na
            # verdade aquelas linhas ja estavam no ERP.
            resumo = [
                "RESUMO DESTA IMPORTACAO",
                f"  titulos cadastrados agora            : {inseridos}",
                f"  titulos que ja existiam (so parcelas): {titulos_existentes}",
                f"  grupos sem parcela nova              : {grupos_sem_novidade}",
                f"  avulsos que ja estavam no ERP        : {pulados_avulso}",
                f"  linhas sem cliente cadastrado        : {sem_cliente}",
                f"  erros                                : {erros - sem_cliente}",
                "",
                "Avulso = linha sem numero de documento. Como ela recebe um codigo",
                "novo a cada importacao, a unica forma de nao duplicar e comparar",
                "cliente + valor + vencimento com o que ja esta no ERP.",
                "",
            ]
            log_linhas = resumo + log_linhas
            log_str = "\n".join(log_linhas)
            self.parent.after(0, lambda l=log_str: self._oferecer_log(l))

            try:
                with FirebirdService(self.config_db) as fb:
                    rows = fb.query(
                        "SELECT TIT_CODIGO, TIT_SERIE FROM TABELA_TITULO_REC WHERE TIT_EMPRESA = ? AND TIT_FILIAL = ?",
                        [emp, fil]
                    )
                    dados_existentes = {'documentos_tit': {}, 'parcelas_tit': set()}
                    for row in rows:
                        k = (str(row['tit_codigo'] or '').strip(), str(row['tit_serie'] or '').strip())
                        if k[0]:
                            dados_existentes['documentos_tit'][k] = True
                    # Recarrega tambem as parcelas ja gravadas, para o preview
                    # pos-import reconhecer o que acabou de entrar (com "trazer
                    # parcelas novas" ligado, elas voltam a ser JA CADASTRADO).
                    for row in fb.query(
                        "SELECT TPARC_CODIGO, TPARC_SERIE, TPARC_VENCIMENTO, TPARC_VALOR "
                        "FROM TABELA_TITULO_PARCELA_REC WHERE TPARC_EMPRESA = ? AND TPARC_FILIAL = ?",
                        [emp, fil]
                    ):
                        cod = str(row['tparc_codigo'] or '').strip().lstrip('0')
                        ser = str(row['tparc_serie'] or '').strip()
                        venc = row['tparc_vencimento'].isoformat() if row['tparc_vencimento'] else ''
                        val = round(float(row['tparc_valor'] or 0), 2)
                        dados_existentes['parcelas_tit'].add((cod, ser, venc, val))
                self.parent.after(0, lambda de=dados_existentes: self._renderizar_preview(de))
            except Exception:
                self.parent.after(0, lambda: self._renderizar_preview())

        except Exception as e:
            self.parent.after(0, lambda err=e: self._safe_showerror("Erro de Importa\u00e7\u00e3o", f"Ocorreu um erro estrutural:\n{err}"))
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
                initialfile="LOG_IMPORTACAO_RECEBER.txt",
                filetypes=[("Arquivos de Texto", "*.txt")]
            )
            if caminho:
                try:
                    with open(caminho, 'w', encoding='utf-8') as f:
                        f.write("--- LOG DE IMPORTACAO DE CONTAS A RECEBER VIA PLANILHA ---\n\n")
                        f.write(log_str)
                    messagebox.showinfo("Log Salvo", f"Arquivo salvo em:\n{caminho}")
                    if messagebox.askyesno("Abrir Log", "Deseja abrir o arquivo de log agora?"):
                        try:
                            os.startfile(caminho)
                        except Exception as e:
                            messagebox.showerror("Erro", f"Erro ao abrir arquivo:\n{e}")
                except Exception as e:
                    messagebox.showerror("Erro", f"Erro ao salvar log:\n{e}")

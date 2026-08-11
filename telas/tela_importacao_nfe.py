# -*- coding: utf-8 -*-
"""
Importa notas fiscais (XML de NF-e) emitidas em outro sistema para o ERP.

Fluxo em 4 fases, na ordem: a nota só entra quando as três primeiras estão
resolvidas.

  Fase 1  Cliente/Fornecedor  — a contraparte da nota está em TABELA_CLI_FOR?
  Fase 2  Natureza de operação (CFOP) — está cadastrada, com fluxo de caixa,
          contabilidade e estoque definidos?
  Fase 3  Produto — o cProd do XML casa por código, cód. de importação ou
          cód. auxiliar?
  Fase 4  Notas — grava a nota (cabeçalho, itens, ICMS, obs, parcelas) e o
          título no financeiro.

Escopo: somente notas de EMISSÃO PRÓPRIA (o CNPJ do <emit> é o da empresa),
tanto de saída (tpNF=1) quanto de entrada (tpNF=0).

Estoque NÃO é movimentado — verificado empiricamente: inserir a nota não altera
TABELA_PRODUTO, TABELA_PRODUTO_ESTOQUE nem ESTOQUE_TEMP nesta base (todos os
produtos têm PRODUTO_CONTROLE_QTDE='N' e o motor de estoque novo está desligado).
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import configparser
import threading
import datetime
import csv
import os
import sys

from utils import tema
from utils.firebird_service import FirebirdService
from utils.nfe_completa import (ler_pasta_notas, so_digitos, SITD_REGULAR,
                                SITD_CANCELADO, SITD_DENEGADA, SITD_COMPLEMENTAR)

# rótulo curto de cada situação, para a grade e o log (a descrição completa está
# na TABELA_SIT_DOCUM_FISCAL do ERP)
SITD_DESCRICAO = {
    SITD_CANCELADO: 'CANCELADA',
    SITD_DENEGADA: 'DENEGADA',
    SITD_COMPLEMENTAR: 'COMPLEMENTAR',
}
from utils.transformer import DataTransformer
from utils.importer import FirebirdImporter
from utils import rateio_contabil
from utils import tipo_cadastro
from utils import multivalor
# Reuso direto do casamento de produto (código / importação / auxiliar) já
# validado no módulo de etiquetas — inclui o tratamento de '10000.0' e '10.000'.
from telas.tela_importacao_planilha_estoque_producao import (
    TelaImportacaoPlanilhaEstoqueProducao as _Etq,
)

SERIE_PADRAO = '1'
ORIGEM_IMPORTACAO = 'IMP'          # NFS_ORIGEM / TIT_ORIGEM (VARCHAR(5))
USUARIO_PADRAO = 'SISTEC_IMP'
LOTE_COMMIT = 100
TAM_OBS = 200                      # NFOBS_OBS1..OBS20 sao VARCHAR(200)
QTDE_OBS = 20

# Escopo da gravação. Saída e entrada recebem centro de custo e conta contábil
# diferentes, então cada uma é importada na sua passada, com o seu rateio.
ESCOPO_SAIDA = 'Só saídas'
ESCOPO_ENTRADA = 'Só entradas'
ESCOPO_AMBAS = 'Saídas + Entradas'
# sufixo das chaves do config.ini onde o par centro de custo + conta é guardado
SUFIXO_ESCOPO = {ESCOPO_SAIDA: 'saida', ESCOPO_ENTRADA: 'entrada', ESCOPO_AMBAS: 'saida'}

# Tipo do cadastro da contraparte na fase 1. O automático deduz do papel nas notas.
TIPO_CF_AUTOMATICO = 'Automático (pela nota)'

# Colunas numéricas que o ERP sempre grava com ZERO e que a importação deixaria
# nulas. NULL em campo numérico faz a emissão da DANFE quebrar na validação
# ("O valor ... não é válido"), então entram zeradas. A lista foi levantada
# comparando as notas reais do FRIGOMASTER: são colunas 100% preenchidas lá e
# sempre com valor 0 — nenhuma carrega informação da nota.
ZERO_NFP = (
    'NFP_RATEIO_DESC_TOTAL', 'NFP_RATEIO_DESP_ASSES', 'NFP_COMISSAO_VENDEDOR',
    'NFP_VALOR_PAUTA', 'NFP_IVA_ST', 'NFP_BC_ISS', 'NFP_ISS', 'NFP_VALOR_ISS',
    'NFP_ICMS_ST', 'NFP_REDUCAO_ST', 'NFP_ICMS_SIMPLES', 'NFP_VALOR_ICMS_SIMPLES',
    'NFP_BC_ICMS_ST_RET', 'NFP_ICMS_ST_RET', 'NFP_PER_DIF_ST',
    'NFP_INCIDE_IMP_PRECO_VENDA', 'NFP_IMP_PRECO_VENDA', 'NFP_PERC_ACORDO_COMERC',
    'NFP_INCID_IMP_PRE_VEN_FED', 'NFP_INCID_IMP_PRE_VEN_EST',
    'NFP_INCID_IMP_PRE_VEN_MUN', 'NFP_IMP_PRE_VEN_FED', 'NFP_IMP_PRE_VEN_EST',
    'NFP_IMP_PRE_VEN_MUN', 'NFP_INSS_DESONERACAO', 'NFP_BC_ICMS_DIFERIDO',
    'NFP_VR_ICMS_DIFERIDO', 'NFP_RED_ICMS_DIFERIDO', 'NFP_ICMS_DIFERIDO',
    'NFP_ICMS_DESTINO', 'NFP_VR_DIF_ICMS_ORIGEM', 'NFP_VR_DIF_ICMS_DESTINO',
    'NFP_ICMS_FCP', 'NFP_VR_ICMS_FCP', 'NFP_VR_ST_FCP', 'NFP_REDUCAO_EFETIVO',
    'NFP_BC_ICMS_EFETIVO', 'NFP_ICMS_EFETIVO', 'NFP_VALOR_ICMS_EFETIVO',
    'NFP_QTDE_FAT_PCP_EST_FAT', 'NFP_FRETE_UNITARIO', 'NFP_DESCONTO_UNITARIO',
    'NFP_VALOR_DESCONTO_PROD', 'NFP_VALOR_ICMS_SUBSTITUTO', 'NFP_PRECO_LISTA_MINIMO',
)

# o mesmo, para o item da nota de ENTRADA (a tabela é outra e tem colunas próprias)
ZERO_NFEP = (
    'NFP_RATEIO_SEGURO', 'NFP_RATEIO_DESP_ASSES', 'NFP_RATEIO_SIT_TRIBUT',
    'NFP_VALOR_DIF_ICMS', 'NFP_BASE_SUBST_TRIB', 'NFP_VALOR_ICMS_SUBST_TRIB',
    'NFP_IVA_ST', 'NFP_OS_EMPRESA', 'NFP_OS_FILIAL', 'NFP_REDUCAO_IPI',
    'NFP_VALOR_TOTAL_IPI_2', 'NFP_INSS_DESONERACAO', 'NFP_BC_ICMS_DIFERIDO',
    'NFP_VR_ICMS_DIFERIDO', 'NFP_VR_DIF_ICMS_ORIGEM', 'NFP_VR_DIF_ICMS_DESTINO',
    'NFP_COMISSAO_VENDEDOR',
)

CORES_STATUS = {
    'OK': ('#EAFAF1', '#16A34A'),
    'AVISO': ('#FFF8E1', '#B45309'),
    'ERRO': ('#FDECEA', '#C8001E'),
    'NEUTRO': ('#F1F5F9', '#475569'),
}


class TelaImportacaoNFe(ttk.Frame):
    """Tela de importação de notas fiscais a partir dos XMLs."""

    # --- casamento de produto reusado do módulo de etiquetas ---
    _chaves_produto = _Etq._chaves_produto
    _indexar_produtos = _Etq._indexar_produtos
    _resolver_produto = _Etq._resolver_produto
    _descr_modo = _Etq._descr_modo

    def __init__(self, parent, callback_voltar=None):
        super().__init__(parent, padding="10")
        self.parent = parent
        self.callback_voltar = callback_voltar
        self.pack(fill=tk.BOTH, expand=True)

        self.pasta_xml = ""
        self.notas = []              # todas as notas lidas
        self.analise = None          # resultado da análise (dict)
        self._grids = {}             # aba -> {item_id: dado}
        # código do XML -> código do produto no ERP, escolhido à mão na aba 3
        # quando o mesmo código está em dois produtos ativos (ver
        # _escolher_produto_ambiguo). Guardado no config.ini, por banco.
        self._prod_escolhido = {}

        self.config = configparser.ConfigParser()
        self.config.read('config.ini', encoding='utf-8')
        fbcli = self.config.get('FIREBIRD', 'fbclient', fallback='').strip()
        self.config_db = {
            'host': self.config.get('FIREBIRD', 'servidor', fallback='127.0.0.1'),
            'port': self.config.get('FIREBIRD', 'porta', fallback='3050'),
            'database': self.config.get('FIREBIRD', 'caminho_banco', fallback=''),
            'user': self.config.get('FIREBIRD', 'usuario', fallback='SYSDBA'),
            'password': self.config.get('FIREBIRD', 'senha', fallback='masterkey'),
            'fbclient': self._resource_path(fbcli) if fbcli else '',
        }

        self._criar_widgets()
        self._carregar_config()

    def _resource_path(self, relative_path):
        if os.path.isabs(relative_path):
            return relative_path
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    # ------------------------------------------------------------------ UI
    def _criar_widgets(self):
        tema.montar_header(
            self, "Importar Notas Fiscais (XML)",
            "Traz notas de emissão própria (entrada e saída) dos XMLs para o ERP, "
            "validando cliente, natureza de operação e produto antes de gravar"
        ).pack(fill=tk.X)

        corpo = tk.Frame(self, bg=tema.BG_BASE)
        corpo.pack(fill=tk.BOTH, expand=True)

        sidebar = tema.montar_sidebar(corpo)
        rodape_sb = tk.Frame(sidebar, bg=tema.SIDEBAR_BG)
        rodape_sb.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 8))
        tema.botao_sidebar(rodape_sb, "⎋   Voltar", self._fechar_tela).pack(fill=tk.X)

        tema.titulo_sidebar(sidebar, "AÇÕES").pack(fill=tk.X, pady=(16, 4))

        self.btn_analisar = tema.botao_sidebar(
            sidebar, "🔍   Ler XMLs e Analisar", self._iniciar_analise)
        self.btn_analisar.pack(fill=tk.X)

        self.btn_cadastrar = tema.botao_sidebar(
            sidebar, "✚   Cadastrar Pendências da Aba", self._cadastrar_aba, cor_fg="#FFC48F")
        self.btn_cadastrar.config(state=tk.DISABLED)
        self.btn_cadastrar.pack(fill=tk.X)

        self.btn_importar = tema.botao_sidebar(
            sidebar, "🚀   Importar Notas no ERP", self._iniciar_importacao, cor_fg="#7EE0A0")
        self.btn_importar.config(state=tk.DISABLED)
        self.btn_importar.pack(fill=tk.X)

        # Nota que JÁ está no ERP não é reimportada — e as importadas por versões
        # anteriores entraram sem a situação do documento e sem a data de
        # cancelamento. Este botão acerta essas, lendo dos mesmos XMLs.
        self.btn_situacao = tema.botao_sidebar(
            sidebar, "🚫   Corrigir Situação das Já Importadas",
            self._iniciar_situacao, cor_fg="#FFB4B4")
        self.btn_situacao.config(state=tk.DISABLED)
        self.btn_situacao.pack(fill=tk.X)

        self.btn_exportar = tema.botao_sidebar(
            sidebar, "📋   Exportar Análise (CSV)", self._exportar_analise, cor_fg="#8FD8FF")
        self.btn_exportar.config(state=tk.DISABLED)
        self.btn_exportar.pack(fill=tk.X)

        content = tk.Frame(corpo, bg=tema.BG_BASE)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=16, pady=12)

        # --- CARDS ---
        frame_cards = ttk.Frame(content)
        frame_cards.pack(fill=tk.X, pady=(8, 2), padx=5)
        self.card_notas = self._criar_card(frame_cards, "Notas a Importar", "0", "#14146E")
        self.card_notas.pack(side=tk.LEFT, padx=5)
        self.card_valor = self._criar_card(frame_cards, "Valor Total", "R$ 0,00", "#22C55E")
        self.card_valor.pack(side=tk.LEFT, padx=5)
        self.card_pendencias = self._criar_card(frame_cards, "Pendências (fases 1-3)", "0", "#E67E22")
        self.card_pendencias.pack(side=tk.LEFT, padx=5)
        self.card_ignoradas = self._criar_card(frame_cards, "Já Import./Terceiros", "0", "#475569")
        self.card_ignoradas.pack(side=tk.LEFT, padx=5)

        # --- PASTA + EMPRESA ---
        linha = ttk.Frame(content)
        linha.pack(fill=tk.X, pady=2)
        tk.Label(linha, text="Pasta dos XMLs:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 2))
        self.ent_pasta = ttk.Entry(linha, font=("Segoe UI", 9))
        self.ent_pasta.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        ttk.Button(linha, text="📁 Selecionar", command=self._selecionar_pasta).pack(side=tk.LEFT, padx=2)

        linha2 = ttk.Frame(content)
        linha2.pack(fill=tk.X, pady=2)
        tk.Label(linha2, text="Empresa:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 2))
        self.ent_empresa = ttk.Entry(linha2, width=5, font=("Segoe UI", 9))
        self.ent_empresa.insert(0, "1")
        self.ent_empresa.pack(side=tk.LEFT, padx=2)
        tk.Label(linha2, text="Filial:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(8, 2))
        self.ent_filial = ttk.Entry(linha2, width=5, font=("Segoe UI", 9))
        self.ent_filial.insert(0, "1")
        self.ent_filial.pack(side=tk.LEFT, padx=2)
        # trocar empresa/filial recarrega o CNPJ do cadastro da filial
        for ent in (self.ent_empresa, self.ent_filial):
            ent.bind("<FocusOut>", lambda e: self._atualizar_cnpj_filial())
            ent.bind("<Return>", lambda e: self._atualizar_cnpj_filial())

        tk.Label(linha2, text="CNPJ:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(14, 2))
        self.ent_cnpj = ttk.Entry(linha2, width=20, font=("Segoe UI", 9))
        self.ent_cnpj.pack(side=tk.LEFT, padx=2)
        # o ↻ relê o CNPJ da filial E as combos (vendedor, local de cobrança, centro
        # de custo, conta) — cadastrar no ERP com a tela aberta era não achar nada
        ttk.Button(linha2, text="↻", width=3,
                   command=lambda: self._atualizar_cnpj_filial(
                       forcar=True, recarregar_combos=True)).pack(side=tk.LEFT)
        self.lbl_filial = tk.Label(linha2, text="", font=("Segoe UI", 8), fg="#555")
        self.lbl_filial.pack(side=tk.LEFT, padx=(4, 0))

        # A NOTA entra numa filial; os CADASTROS que ela aponta podem estar em
        # outra. É o caso de quem mantém cliente, produto e natureza numa filial
        # só e faz as demais olharem para lá por configuração do ERP. Sem esta
        # separação, importar na filial 2 procurava cliente e produto na 2 (onde
        # não há nada) e não achava nada.
        linha2a = ttk.Frame(content)
        linha2a.pack(fill=tk.X, pady=2)
        tk.Label(linha2a, text="Cadastros (cliente / produto / natureza) na Empresa:",
                 font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 2))
        self.ent_empresa_cad = ttk.Entry(linha2a, width=5, font=("Segoe UI", 9))
        self.ent_empresa_cad.insert(0, "1")
        self.ent_empresa_cad.pack(side=tk.LEFT, padx=2)
        tk.Label(linha2a, text="Filial:", font=("Segoe UI", 9, "bold")).pack(
            side=tk.LEFT, padx=(8, 2))
        self.ent_filial_cad = ttk.Entry(linha2a, width=5, font=("Segoe UI", 9))
        self.ent_filial_cad.insert(0, "1")
        self.ent_filial_cad.pack(side=tk.LEFT, padx=2)
        for ent in (self.ent_empresa_cad, self.ent_filial_cad):
            ent.bind("<FocusOut>", lambda e: self._atualizar_aviso_cadastros())
            ent.bind("<Return>", lambda e: self._atualizar_aviso_cadastros())
        self.lbl_cad = tk.Label(linha2a, text="", font=("Segoe UI", 8), fg="#555")
        self.lbl_cad.pack(side=tk.LEFT, padx=(8, 0))

        self.var_gerar_fin = tk.BooleanVar(value=True)
        ttk.Checkbutton(linha2, text="Gerar financeiro (parcelas + título)",
                        variable=self.var_gerar_fin,
                        command=self._on_gerar_fin_mudou).pack(side=tk.LEFT, padx=(16, 2))

        # O XML não traz local de cobrança nem vendedor — são cadastros do ERP.
        # Um valor para todas as notas; o vendedor do cliente, quando existe,
        # tem prioridade sobre o padrão escolhido aqui.
        linha2b = ttk.Frame(content)
        linha2b.pack(fill=tk.X, pady=2)
        tk.Label(linha2b, text="Local de cobrança:", font=("Segoe UI", 9, "bold")).pack(
            side=tk.LEFT, padx=(5, 2))
        self.cmb_lc = ttk.Combobox(linha2b, width=26, state="readonly", font=("Segoe UI", 9))
        self.cmb_lc.pack(side=tk.LEFT, padx=2)
        tk.Label(linha2b, text="Vendedor padrão:", font=("Segoe UI", 9, "bold")).pack(
            side=tk.LEFT, padx=(14, 2))
        self.cmb_vend = ttk.Combobox(linha2b, width=30, state="readonly", font=("Segoe UI", 9))
        self.cmb_vend.pack(side=tk.LEFT, padx=2)
        tk.Label(linha2b, text="(o vendedor do cliente tem prioridade)",
                 font=("Segoe UI", 8), fg="#555").pack(side=tk.LEFT, padx=(6, 0))

        # Como a contraparte é cadastrada na fase 1. No automático, quem aparece como
        # destinatário de saída E emitente de entrada entra como cliente E fornecedor —
        # as três colunas do ERP são independentes. Os tipos fixos servem para forçar
        # tudo de uma vez, quando o cliente já sabe o que quer.
        tk.Label(linha2b, text="Cadastrar como:", font=("Segoe UI", 9, "bold")).pack(
            side=tk.LEFT, padx=(14, 2))
        self.cmb_tipo_cf = ttk.Combobox(
            linha2b, width=26, state="readonly", font=("Segoe UI", 9),
            values=[TIPO_CF_AUTOMATICO] + tipo_cadastro.TIPOS)
        self.cmb_tipo_cf.set(TIPO_CF_AUTOMATICO)
        self.cmb_tipo_cf.pack(side=tk.LEFT, padx=2)

        # Saída e entrada têm classificação contábil e centro de custo diferentes,
        # então a importação é feita em passadas separadas: escolhe-se o escopo, o
        # rateio daquele escopo, e grava. O par centro de custo + conta contábil é
        # guardado por escopo, para não ter de lembrar o que foi usado na outra
        # passada nem correr o risco de gravar entrada com o rateio da saída.
        linha2c = ttk.Frame(content)
        linha2c.pack(fill=tk.X, pady=2)
        tk.Label(linha2c, text="Importar:", font=("Segoe UI", 9, "bold")).pack(
            side=tk.LEFT, padx=(5, 2))
        self.cmb_escopo = ttk.Combobox(linha2c, width=17, state="readonly",
                                       font=("Segoe UI", 9),
                                       values=[ESCOPO_AMBAS, ESCOPO_SAIDA, ESCOPO_ENTRADA])
        self.cmb_escopo.set(ESCOPO_SAIDA)
        self.cmb_escopo.pack(side=tk.LEFT, padx=2)
        self.cmb_escopo.bind("<<ComboboxSelected>>", self._on_escopo_mudou)

        tk.Label(linha2c, text="Centro de custo:", font=("Segoe UI", 9, "bold")).pack(
            side=tk.LEFT, padx=(14, 2))
        self.cmb_cc = ttk.Combobox(linha2c, width=30, state="readonly", font=("Segoe UI", 9))
        self.cmb_cc.pack(side=tk.LEFT, padx=2)
        tk.Label(linha2c, text="Conta contábil:", font=("Segoe UI", 9, "bold")).pack(
            side=tk.LEFT, padx=(14, 2))
        self.cmb_conta = ttk.Combobox(linha2c, width=34, state="readonly", font=("Segoe UI", 9))
        self.cmb_conta.pack(side=tk.LEFT, padx=2)
        self.lbl_escopo = tk.Label(linha2c, text="", font=("Segoe UI", 8), fg="#555")
        self.lbl_escopo.pack(side=tk.LEFT, padx=(6, 0))

        # Quem decide se a nota gera financeiro no ERP é o FLUXO DE CAIXA da natureza
        # de operação, não esta importação: com NAT_FLUXO_CAIXA='S' o faturamento
        # (CONFAT) gera o título ao passar pela nota, mesmo que a importação não tenha
        # gerado nada. Para o cliente cujo financeiro já veio por planilha, a natureza
        # tem de entrar com 'N'; para os outros, com 'S'. Daí ser escolha por rodada.
        linha2d = ttk.Frame(content)
        linha2d.pack(fill=tk.X, pady=2)
        tk.Label(linha2d, text="Naturezas de operação:", font=("Segoe UI", 9, "bold")).pack(
            side=tk.LEFT, padx=(5, 2))
        self.var_nat_fluxo = tk.BooleanVar(value=True)
        ttk.Checkbutton(linha2d, text="Fluxo de caixa (gera financeiro no ERP)",
                        variable=self.var_nat_fluxo).pack(side=tk.LEFT, padx=(4, 10))
        self.var_nat_contab = tk.BooleanVar(value=True)
        ttk.Checkbutton(linha2d, text="Contabilidade",
                        variable=self.var_nat_contab).pack(side=tk.LEFT, padx=(0, 10))
        tk.Label(linha2d, text="(natureza que já existe não é alterada: se nenhuma "
                               "variação do CFOP atender, entra uma nova)",
                 font=("Segoe UI", 8), fg="#555").pack(side=tk.LEFT, padx=(6, 0))
        tk.Label(linha2d, text="(estoque sempre N)", font=("Segoe UI", 8),
                 fg="#555").pack(side=tk.LEFT, padx=(6, 0))

        # --- PROGRESSO ---
        linha3 = ttk.Frame(content)
        linha3.pack(fill=tk.X, pady=4)
        self.progresso = ttk.Progressbar(linha3, orient=tk.HORIZONTAL, mode='determinate', length=180)
        self.progresso.pack(side=tk.LEFT, padx=8)
        self.lbl_status = ttk.Label(linha3, text="Selecione a pasta dos XMLs e clique em Analisar.",
                                    font=("Segoe UI", 9), foreground="#555")
        self.lbl_status.pack(side=tk.LEFT, padx=2)

        # --- ABAS DAS FASES ---
        self.abas = ttk.Notebook(content)
        self.abas.pack(fill=tk.BOTH, expand=True, pady=6)

        self.tree_cli = self._criar_aba(
            'clientes', "1. Cliente / Fornecedor",
            ("STATUS", "CNPJ/CPF", "RAZÃO SOCIAL", "UF", "CIDADE", "NOTAS", "CÓD. ERP"),
            (150, 140, 260, 45, 150, 60, 80))
        self.tree_nat = self._criar_aba(
            'naturezas', "2. Natureza de Operação (CFOP)",
            ("STATUS", "CFOP", "TIPO", "DESCRIÇÃO NO ERP", "FLUXO CAIXA",
             "CONTÁBIL", "ESTOQUE", "NOTAS"),
            (180, 70, 70, 220, 85, 75, 70, 55))
        self.tree_prod = self._criar_aba(
            'produtos', "3. Produto",
            ("STATUS", "CÓD. XML", "DESCRIÇÃO NO XML", "NCM", "UN",
             "CÓD. ERP", "CASOU POR", "ITENS"),
            (170, 100, 250, 90, 45, 80, 95, 50))
        # duplo clique desempata produto AMBÍGUO (o mesmo código em dois cadastros)
        self.tree_prod.bind("<Double-1>", self._on_dblclick_produto)
        self.tree_nota = self._criar_aba(
            'notas', "4. Notas",
            ("SEL", "STATUS", "SIT.", "TIPO", "NÚMERO", "SÉRIE", "EMISSÃO",
             "CONTRAPARTE", "VALOR", "ITENS", "PARC.", "MOTIVO"),
            (40, 150, 110, 60, 80, 45, 80, 230, 100, 45, 45, 240))
        self.tree_nota.bind("<ButtonRelease-1>", self._on_click_nota)
        # botão direito: copiar a chave da NF-e (é o que se leva para consultar a
        # nota no portal da SEFAZ, no ERP ou num SELECT)
        self.tree_nota.bind("<Button-3>", self._menu_nota)

        tk.Label(content, text="Dica: resolva as abas 1, 2 e 3 (botão “Cadastrar Pendências da Aba”) "
                               "antes de importar. Na aba 3, duplo clique numa linha AMBÍGUA escolhe "
                               "qual produto do ERP usar. Na aba 4, clique na coluna SEL para "
                               "marcar/desmarcar e no botão direito para copiar a chave da NF-e.",
                 font=("Segoe UI", 8), bg=tema.BG_BASE, fg="#555").pack(anchor=tk.W, padx=5)

    def _criar_aba(self, chave, titulo, colunas, larguras):
        frame = ttk.Frame(self.abas)
        self.abas.add(frame, text=titulo)
        tree = ttk.Treeview(frame, columns=colunas, show="headings")
        for col, larg in zip(colunas, larguras):
            tree.heading(col, text=col)
            anchor = tk.W if col in ("RAZÃO SOCIAL", "DESCRIÇÃO NO XML", "DESCRIÇÃO NO ERP",
                                     "CONTRAPARTE", "MOTIVO", "CIDADE") else tk.CENTER
            tree.column(col, width=larg, anchor=anchor)
        for tag, (bg, fg) in CORES_STATUS.items():
            tree.tag_configure(tag, background=bg, foreground=fg)
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscroll=scroll.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._grids[chave] = {}
        tree._chave_aba = chave
        return tree

    def _criar_card(self, parent, titulo, valor_inicial, cor_texto):
        card = tk.Frame(parent, bg="#FFFFFF", highlightbackground="#CCCCCC",
                        highlightthickness=1, padx=15, pady=8)
        tk.Label(card, text=titulo, font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#555").pack(anchor=tk.E)
        lbl = tk.Label(card, text=valor_inicial, font=("Segoe UI", 14, "bold"), bg="#FFFFFF", fg=cor_texto)
        lbl.pack(anchor=tk.E)
        card.lbl_valor = lbl
        return card

    # -------------------------------------------------------------- CONFIG
    SECAO = 'IMPORTACAO_NFE'

    def _id_banco(self):
        """Identifica a conexão atual, para saber quando o banco foi trocado."""
        return (f"{self.config_db.get('host', '')}/{self.config_db.get('port', '')}:"
                f"{self.config_db.get('database', '')}").upper()

    def _aplicar_primeira_filial(self):
        """Põe empresa/filial na primeira filial cadastrada no banco conectado."""
        try:
            with FirebirdService(self.config_db) as fb:
                r = fb.query("SELECT FIRST 1 FILIAL_EMPRESA E, FILIAL_CODIGO F "
                             "FROM TABELA_FILIAL ORDER BY FILIAL_EMPRESA, FILIAL_CODIGO")
        except Exception:
            return
        if not r:
            return
        for ent, valor in ((self.ent_empresa, r[0]['e']), (self.ent_filial, r[0]['f']),
                           (self.ent_empresa_cad, r[0]['e']), (self.ent_filial_cad, r[0]['f'])):
            ent.delete(0, tk.END)
            ent.insert(0, str(valor))

    @staticmethod
    def _ler_prod_escolhido(texto):
        """`3345=10381; MDC131=553` -> {'3345': 10381, 'MDC131': 553}."""
        escolhas = {}
        for par in (texto or '').split(';'):
            if '=' not in par:
                continue
            cod, _, erp = par.rpartition('=')
            cod, erp = cod.strip(), erp.strip()
            if cod and erp.isdigit():
                escolhas[cod] = int(erp)
        return escolhas

    def _carregar_config(self):
        s = self.SECAO
        # O que está guardado na seção — pasta dos XMLs, CNPJ, empresa/filial,
        # local de cobrança, vendedor, centro de custo e conta — é tudo de UM
        # cliente. Apontar o config.ini para outro banco (o normal na
        # implantação) e reabrir a tela trazia essas escolhas do cliente
        # anterior: a filial salva não existe no banco novo, nada é encontrado,
        # e a tela mostra o CNPJ e o vendedor da outra base como se fossem daqui.
        # Só as preferências de comportamento atravessam a troca de banco.
        mesmo_banco = (self.config.has_section(s)
                       and self.config.get(s, 'banco', fallback='') == self._id_banco())
        if self.config.has_section(s):
            if mesmo_banco:
                pasta = self.config.get(s, 'ultima_pasta', fallback='')
                if pasta and os.path.isdir(pasta):
                    self.pasta_xml = pasta
                    self.ent_pasta.delete(0, tk.END)
                    self.ent_pasta.insert(0, pasta)
                self.ent_cnpj.delete(0, tk.END)
                self.ent_cnpj.insert(0, self.config.get(s, 'cnpj_empresa', fallback=''))
                for ent, chave, padrao in (
                        (self.ent_empresa, 'empresa', '1'),
                        (self.ent_filial, 'filial', '1'),
                        # sem chave salva, os cadastros ficam na mesma da nota
                        (self.ent_empresa_cad, 'empresa_cadastros',
                         self.config.get(s, 'empresa', fallback='1')),
                        (self.ent_filial_cad, 'filial_cadastros',
                         self.config.get(s, 'filial', fallback='1'))):
                    ent.delete(0, tk.END)
                    ent.insert(0, self.config.get(s, chave, fallback=padrao))
            self.var_gerar_fin.set(
                self.config.get(s, 'gerar_financeiro', fallback='S').upper() == 'S')
            # o fluxo de caixa da natureza acompanha o financeiro por padrão, mas é
            # guardado à parte: dá para importar sem gerar título e ainda assim
            # deixar a natureza gerando pelo faturamento (ou o contrário)
            self.var_nat_fluxo.set(
                self.config.get(s, 'nat_fluxo_caixa',
                                fallback='S' if self.var_gerar_fin.get() else 'N'
                                ).upper() == 'S')
            self.var_nat_contab.set(
                self.config.get(s, 'nat_contabilidade', fallback='S').upper() == 'S')
            self.cmb_escopo.set(self.config.get(s, 'escopo', fallback=ESCOPO_SAIDA))
            tipo_salvo = self.config.get(s, 'tipo_cadastro_cf', fallback=TIPO_CF_AUTOMATICO)
            self.cmb_tipo_cf.set(tipo_salvo if tipo_salvo in ([TIPO_CF_AUTOMATICO] + tipo_cadastro.TIPOS)
                                 else TIPO_CF_AUTOMATICO)
            if mesmo_banco:
                self.cmb_lc.set(self.config.get(s, 'local_cobranca', fallback=''))
                self.cmb_vend.set(self.config.get(s, 'vendedor_padrao', fallback=''))
                self._prod_escolhido = self._ler_prod_escolhido(
                    self.config.get(s, 'produtos_ambiguos', fallback=''))
                self._carregar_rateio_do_escopo()
        if not mesmo_banco:
            # banco novo: a filial vem do próprio cadastro dele
            self._aplicar_primeira_filial()
        self._carregar_combos_erp()
        self._atualizar_dica_escopo()
        self._atualizar_aviso_cadastros()
        # O CNPJ é do cadastro da filial e o banco tem a palavra final: se o
        # config.ini guardasse um CNPJ de outra base (trocar de banco é comum
        # na implantação), a análise marcaria todas as notas como de terceiros.
        # O valor salvo só sobra quando a filial está sem CNPJ no cadastro.
        self._atualizar_cnpj_filial(forcar=True)

    def _salvar_config(self):
        s = self.SECAO
        if not self.config.has_section(s):
            self.config.add_section(s)
        # o banco a que estas escolhas pertencem: reabrir noutro banco as descarta
        self.config.set(s, 'banco', self._id_banco())
        self.config.set(s, 'ultima_pasta', self.pasta_xml)
        self.config.set(s, 'cnpj_empresa', self.ent_cnpj.get().strip())
        self.config.set(s, 'empresa', self.ent_empresa.get().strip())
        self.config.set(s, 'filial', self.ent_filial.get().strip())
        self.config.set(s, 'empresa_cadastros', self.ent_empresa_cad.get().strip())
        self.config.set(s, 'filial_cadastros', self.ent_filial_cad.get().strip())
        self.config.set(s, 'gerar_financeiro', 'S' if self.var_gerar_fin.get() else 'N')
        self.config.set(s, 'nat_fluxo_caixa', 'S' if self.var_nat_fluxo.get() else 'N')
        self.config.set(s, 'nat_contabilidade', 'S' if self.var_nat_contab.get() else 'N')
        self.config.set(s, 'local_cobranca', self.cmb_lc.get())
        self.config.set(s, 'vendedor_padrao', self.cmb_vend.get())
        self.config.set(s, 'produtos_ambiguos',
                        '; '.join(f"{cod}={erp}" for cod, erp
                                  in sorted(self._prod_escolhido.items())))
        self.config.set(s, 'escopo', self.cmb_escopo.get())
        self.config.set(s, 'tipo_cadastro_cf', self.cmb_tipo_cf.get())
        self._salvar_rateio_do_escopo()
        try:
            with open('config.ini', 'w', encoding='utf-8') as f:
                self.config.write(f)
        except Exception:
            pass

    # ------------------------------------- FINANCEIRO × FLUXO DE CAIXA DA NATUREZA
    def _on_gerar_fin_mudou(self):
        """Desmarcar 'Gerar financeiro' desmarca o fluxo de caixa da natureza.

        São as duas pontas da mesma decisão: sem gerar aqui mas com fluxo de caixa
        na natureza, o faturamento do ERP gera o título depois e o financeiro
        aparece de qualquer jeito (foi o que aconteceu ao passar pelo CONFAT).
        O usuário ainda pode destravar um do outro marcando à mão.
        """
        self.var_nat_fluxo.set(self.var_gerar_fin.get())

    def _flags_nat(self):
        """(fluxo, contabilidade, estoque) para gravar na natureza de operação."""
        return ('S' if self.var_nat_fluxo.get() else 'N',
                'S' if self.var_nat_contab.get() else 'N',
                'N')

    # _aplicar_flags_naturezas foi REMOVIDO de propósito.
    #
    # Ele dava UPDATE em NAT_FLUXO_CAIXA / NAT_CONTABILIDADE de naturezas que já
    # existiam no ERP. Natureza cadastrada é imutável: as notas antigas e outras
    # rotinas do ERP dependem das flags que ela tem. Mudar a natureza para atender
    # esta importação mudava o comportamento de tudo que já passou por ela.
    #
    # No lugar disso, a fase 2 procura uma VARIAÇÃO do CFOP que atenda (NAT_CODIGO é
    # CFOP + 2 dígitos: 510101, 510102...) e, não achando, cadastra uma variação nova.
        self._oferecer_log(log, "LOG_FLAGS_NATUREZAS.txt")

    # ------------------------------------------------- ESCOPO (saída × entrada)
    def _escopo(self):
        return self.cmb_escopo.get() or ESCOPO_SAIDA

    def _tipos_do_escopo(self, escopo=None):
        """tp_nf que o escopo aceita: 1=saída, 0=entrada."""
        esc = escopo or self._escopo()
        if esc == ESCOPO_SAIDA:
            return {1}
        if esc == ESCOPO_ENTRADA:
            return {0}
        return {0, 1}

    def _carregar_rateio_do_escopo(self):
        """Traz o centro de custo / conta contábil guardados para o escopo atual."""
        s = self.SECAO
        if not self.config.has_section(s):
            return
        suf = SUFIXO_ESCOPO.get(self._escopo(), 'saida')
        # fallback nas chaves antigas (sem sufixo), de antes da separação por escopo
        self.cmb_cc.set(self.config.get(s, f'centro_custo_{suf}',
                                        fallback=self.config.get(s, 'centro_custo',
                                                                 fallback='')))
        self.cmb_conta.set(self.config.get(s, f'conta_contabil_{suf}',
                                           fallback=self.config.get(s, 'conta_contabil',
                                                                    fallback='')))
        # o guardado pode não existir mais no banco conectado (ver _carregar_config)
        for cmb in (self.cmb_cc, self.cmb_conta):
            if cmb.get() and cmb['values'] and cmb.get() not in cmb['values']:
                cmb.set('')

    def _salvar_rateio_do_escopo(self):
        s = self.SECAO
        suf = SUFIXO_ESCOPO.get(self._escopo(), 'saida')
        self.config.set(s, f'centro_custo_{suf}', self.cmb_cc.get())
        self.config.set(s, f'conta_contabil_{suf}', self.cmb_conta.get())

    def _on_escopo_mudou(self, _evento=None):
        # o par que estava na tela pertence ao escopo ANTERIOR: grava nele antes
        # de trocar, senão a escolha da outra passada é sobrescrita.
        s = self.SECAO
        if not self.config.has_section(s):
            self.config.add_section(s)
        anterior = getattr(self, '_escopo_anterior', None)
        if anterior and anterior != self._escopo():
            suf = SUFIXO_ESCOPO.get(anterior, 'saida')
            self.config.set(s, f'centro_custo_{suf}', self.cmb_cc.get())
            self.config.set(s, f'conta_contabil_{suf}', self.cmb_conta.get())
        self._escopo_anterior = self._escopo()
        self._carregar_rateio_do_escopo()
        self._atualizar_dica_escopo()
        self._marcar_pelo_escopo()

    def _atualizar_dica_escopo(self):
        if self._escopo() == ESCOPO_AMBAS:
            texto = "⚠ mesmo rateio nas saídas e nas entradas"
        else:
            texto = "(rateio guardado por escopo)"
        self.lbl_escopo.config(text=texto)
        self._escopo_anterior = self._escopo()

    def _marcar_pelo_escopo(self):
        """Marca na grade só as notas do escopo — o que está marcado é o que grava."""
        if not self.analise:
            return
        tipos = self._tipos_do_escopo()
        for iid, f in self._grids['notas'].items():
            if f['status'] != 'OK':
                continue
            f['marcado'] = f['nota']['tp_nf'] in tipos
            try:
                vals = list(self.tree_nota.item(iid, 'values'))
                vals[0] = "☑" if f['marcado'] else "☐"
                self.tree_nota.item(iid, values=vals)
            except tk.TclError:
                pass
        self._atualizar_cards()

    def _fechar_tela(self):
        # as threads de leitura/gravação continuam vivas depois do destroy();
        # a flag faz os callbacks pendentes desistirem em vez de mexer em
        # widget que já não existe (TclError "invalid command name").
        self._morta = True
        self.destroy()
        if self.callback_voltar:
            self.callback_voltar()

    def destroy(self):
        self._morta = True
        super().destroy()

    def _viva(self):
        if getattr(self, '_morta', False):
            return False
        try:
            return bool(self.winfo_exists())
        except Exception:
            return False

    def _ui(self, fn, atraso=0):
        """Agenda `fn` na thread da UI, e só roda se a tela ainda estiver aberta."""
        if not self._viva():
            return

        def seguro():
            if not self._viva():
                return
            try:
                fn()
            except tk.TclError:
                pass          # a tela foi fechada entre o agendamento e a execução
        try:
            self.parent.after(atraso, seguro)
        except tk.TclError:
            pass

    def _selecionar_pasta(self):
        pasta = filedialog.askdirectory(title="Pasta com os XMLs das notas")
        if not pasta:
            return
        self.pasta_xml = pasta
        self.ent_pasta.delete(0, tk.END)
        self.ent_pasta.insert(0, pasta)

    def _emp_fil(self):
        """Empresa/filial DA NOTA — onde ela vai ser gravada."""
        try:
            emp = int(self.ent_empresa.get().strip() or 1)
        except ValueError:
            emp = 1
        try:
            fil = int(self.ent_filial.get().strip() or 1)
        except ValueError:
            fil = 1
        return emp, fil

    def _emp_fil_cad(self):
        """Empresa/filial DOS CADASTROS — onde estão cliente, produto e natureza.

        Em branco cai na da nota, que é o caso comum de quem tem tudo na mesma.
        """
        emp_nota, fil_nota = self._emp_fil()
        try:
            emp = int(self.ent_empresa_cad.get().strip() or emp_nota)
        except ValueError:
            emp = emp_nota
        try:
            fil = int(self.ent_filial_cad.get().strip() or fil_nota)
        except ValueError:
            fil = fil_nota
        return emp, fil

    def _emp_fil_analise(self, cadastros=False):
        """O par empresa/filial da análise em tela.

        `cadastros=True` devolve o par dos cadastros. Uma análise feita antes de
        este par existir não tem as chaves — aí cai na da nota em vez de estourar
        um KeyError no meio de um cadastro em lote.
        """
        emp = self.analise['emp']
        fil = self.analise['fil']
        if not cadastros:
            return emp, fil
        return self.analise.get('emp_cad', emp), self.analise.get('fil_cad', fil)

    def _atualizar_aviso_cadastros(self):
        """Diz em uma linha quando nota e cadastros estão em filiais diferentes."""
        emp, fil = self._emp_fil()
        empc, filc = self._emp_fil_cad()
        if (emp, fil) == (empc, filc):
            self.lbl_cad.config(text="(mesma da nota)", fg="#555")
        else:
            self.lbl_cad.config(
                text=f"⚠ nota vai para {emp}/{fil}; cliente, produto e natureza "
                     f"são lidos e cadastrados em {empc}/{filc}", fg="#B45309")

    def _carregar_combos_erp(self):
        """Preenche local de cobrança, vendedor, centro de custo e conta contábil
        com o que existe no ERP.

        Todos são CADASTROS, então saem da filial dos cadastros — não da filial
        em que a nota vai entrar.
        """
        emp, fil = self._emp_fil_cad()
        lcs = vends = ccs = contas = []
        self._exercicio = None
        try:
            with FirebirdService(self.config_db) as fb:
                lcs = fb.query("SELECT LC_CODIGO C, LC_DESCRICAO D FROM TABELA_LOCAL_COBRANCA "
                               "WHERE LC_EMPRESA = ? AND LC_FILIAL = ? ORDER BY LC_CODIGO",
                               [emp, fil])
                vends = fb.query("SELECT VEND_CODIGO C, VEND_NOME D FROM TABELA_VENDEDOR "
                                 "WHERE VEND_EMPRESA = ? AND VEND_FILIAL = ? ORDER BY VEND_NOME",
                                 [emp, fil])
                # só os centros analíticos: CC_MOVIMENTO='S' é o que aceita lançamento
                ccs = fb.query(
                    "SELECT CC_CODIGO C, CC_DESCRICAO D FROM TABELA_CC "
                    "WHERE CC_EMPRESA = ? AND CC_FILIAL = ? AND CC_MOVIMENTO = 'S' "
                    "  AND COALESCE(CC_DESATIVADO, 'N') = 'N' ORDER BY CC_DESCRICAO",
                    [emp, fil])
                # conta contábil do exercício mais recente do plano
                ex = fb.query("SELECT MAX(PLANO_EXERCICIO) E FROM TABELA_PLANO "
                              "WHERE PLANO_EMPRESA = ? AND PLANO_FILIAL = ?", [emp, fil])
                self._exercicio = ex[0]['e'] if ex and ex[0]['e'] else None
                if self._exercicio:
                    contas = fb.query(
                        "SELECT DISTINCT PLANO_CODIGO C, PLANO_CONTA CT, PLANO_REDUZIDO R, "
                        "       PLANO_DESCRICAO D FROM TABELA_PLANO "
                        "WHERE PLANO_EMPRESA = ? AND PLANO_FILIAL = ? AND PLANO_EXERCICIO = ? "
                        "  AND PLANO_REDUZIDO IS NOT NULL ORDER BY PLANO_CONTA",
                        [emp, fil, self._exercicio])
        except Exception:
            pass
        self.cmb_lc['values'] = [f"{r['c']} - {r['d']}" for r in lcs]
        self.cmb_vend['values'] = ["(nenhum)"] + [f"{r['c']} - {r['d']}" for r in vends]
        self.cmb_cc['values'] = ["(nenhum)"] + [f"{r['c']} - {r['d']}" for r in ccs]
        # o código guardado é PLANO_CODIGO; a classificação vai só no rótulo
        self._conta_reduzido = {int(r['c']): r['r'] for r in contas}
        self.cmb_conta['values'] = ["(nenhuma)"] + [
            f"{r['c']} - {r['ct']} {r['d']}" for r in contas]
        # Texto que não está mais na lista — registro apagado, filial trocada,
        # banco trocado — não pode ficar em tela: ele seria gravado na nota como
        # um código que não existe neste banco.
        for cmb in (self.cmb_lc, self.cmb_vend, self.cmb_cc, self.cmb_conta):
            if cmb.get() and cmb.get() not in cmb['values']:
                cmb.set('')
        if lcs and not self.cmb_lc.get():
            self.cmb_lc.current(0)
        for cmb in (self.cmb_vend, self.cmb_cc, self.cmb_conta):
            if not cmb.get():
                cmb.current(0)

    def _codigo_combo(self, combo):
        """Código numérico de um item '12 - DESCRIÇÃO' do combo; None se vazio."""
        txt = (combo.get() or '').strip()
        if not txt or txt.startswith('('):
            return None
        try:
            return int(txt.split('-')[0].strip())
        except (ValueError, IndexError):
            return None

    def _cnpj_filial(self, emp, fil):
        """CNPJ e razão social da filial logada, do próprio cadastro do ERP."""
        try:
            with FirebirdService(self.config_db) as fb:
                r = fb.query("SELECT FILIAL_CGC, FILIAL_RAZAO FROM TABELA_FILIAL "
                             "WHERE FILIAL_EMPRESA = ? AND FILIAL_CODIGO = ?", [emp, fil])
            if r:
                return (str(r[0].get('filial_cgc') or '').strip(),
                        str(r[0].get('filial_razao') or '').strip())
        except Exception:
            pass
        return '', ''

    def _atualizar_cnpj_filial(self, forcar=False, recarregar_combos=False):
        """Traz o CNPJ do cadastro da filial. Só sobrescreve o que está na tela
        quando o campo está vazio ou quando o usuário pede (botão ↻).

        Com recarregar_combos, relê também local de cobrança, vendedor, centro de
        custo e conta contábil: quem cadastra um vendedor no ERP com a tela já
        aberta espera achá-lo no combo sem ter de fechar e reabrir.
        """
        if not self._viva():
            return          # <FocusOut> ainda dispara durante o fechamento da tela
        emp, fil = self._emp_fil()
        if (emp, fil) == getattr(self, '_ef_cnpj', None) and not forcar:
            return
        cnpj, razao = self._cnpj_filial(emp, fil)
        self._ef_cnpj = (emp, fil)
        if cnpj and (forcar or not self.ent_cnpj.get().strip()):
            self.ent_cnpj.delete(0, tk.END)
            self.ent_cnpj.insert(0, cnpj)
        if razao:
            self.lbl_filial.config(text=f"↳ {razao[:38]}", fg="#555")
        else:
            self.lbl_filial.config(
                text=f"↳ empresa {emp}/filial {fil} não encontrada", fg="#C0392B")
        if recarregar_combos:
            self._carregar_combos_erp()

    # ------------------------------------------------------------- ANALISE
    def _iniciar_analise(self):
        pasta = self.ent_pasta.get().strip()
        if not pasta or not os.path.isdir(pasta):
            return messagebox.showwarning("Aviso", "Selecione uma pasta válida com os XMLs.")
        if not self.ent_cnpj.get().strip():
            self._atualizar_cnpj_filial(forcar=True)
        cnpj = so_digitos(self.ent_cnpj.get())
        if len(cnpj) not in (11, 14):
            emp, fil = self._emp_fil()
            return messagebox.showwarning(
                "Aviso", f"Não achei o CNPJ da empresa {emp} / filial {fil} em "
                         f"TABELA_FILIAL.\n\nConfira empresa e filial, use o botão ↻ ou "
                         f"digite o CNPJ — é ele que define quais notas são de "
                         f"emissão própria.")
        self.pasta_xml = pasta
        self._salvar_config()
        self.btn_analisar.config(state=tk.DISABLED)
        self.btn_importar.config(state=tk.DISABLED)
        self.btn_cadastrar.config(state=tk.DISABLED)
        self.progresso['value'] = 0
        self.lbl_status.config(text="Lendo XMLs...")
        # empresa/filial lidos aqui, na thread da UI — a thread de análise não
        # pode tocar em widget (some se a tela for fechada no meio).
        emp, fil = self._emp_fil()
        emp_cad, fil_cad = self._emp_fil_cad()
        # as flags desejadas também: é por elas que a fase 2 decide se alguma
        # variação do CFOP serve ou se é preciso cadastrar uma nova
        self._flags_desejadas = self._flags_nat()
        threading.Thread(target=self._analisar_bg,
                         args=(pasta, cnpj, emp, fil, emp_cad, fil_cad),
                         daemon=True).start()

    def _analisar_bg(self, pasta, cnpj, emp, fil, emp_cad, fil_cad):
        try:
            def prog(i, total):
                if total and (i % 25 == 0 or i == total):
                    pct = int((i / total) * 40)
                    self._ui(lambda: (
                        self.lbl_status.config(text=f"Lendo XMLs {i}/{total}..."),
                        self.progresso.config(value=pct)))

            notas = ler_pasta_notas(pasta, cnpj, prog)
            if not self._viva():
                return
            if not notas:
                self._ui(lambda: messagebox.showwarning(
                    "Aviso", "Nenhum XML de NF-e válido encontrado na pasta."))
                self._ui(lambda: self.btn_analisar.config(state=tk.NORMAL))
                return

            self._ui(lambda: (
                self.lbl_status.config(text=f"{len(notas)} nota(s) lida(s). Consultando o ERP..."),
                self.progresso.config(value=45)))

            dados = self._carregar_erp(emp, fil, emp_cad, fil_cad)
            analise = self._classificar(notas, dados, emp, fil, cnpj,
                                        emp_cad, fil_cad)
            if not self._viva():
                return
            self.notas = notas
            self.analise = analise
            self._ui(lambda: self._renderizar(analise))
        except Exception as e:
            msg = str(e)
            self._ui(lambda: messagebox.showerror("Erro", f"Falha na análise:\n{msg}"))
            self._ui(lambda: self.btn_analisar.config(state=tk.NORMAL))

    def _carregar_erp(self, emp, fil, emp_cad=None, fil_cad=None):
        """Fotografa o que o ERP já tem: clientes, naturezas, produtos e chaves de NF.

        DOIS pares de empresa/filial, e a distinção importa:
          (emp_cad, fil_cad) — onde estão os CADASTROS: cliente/fornecedor,
              natureza de operação, produto. É onde procuro e onde cadastro.
          (emp, fil) — onde a NOTA vai entrar. É de lá que saem as chaves de NF-e
              e os títulos já existentes, senão a checagem de duplicidade olharia
              para uma filial que não é a que vai receber a nota.
        """
        emp_cad = emp if emp_cad is None else emp_cad
        fil_cad = fil if fil_cad is None else fil_cad
        d = {'emp_cad': emp_cad, 'fil_cad': fil_cad}
        with FirebirdService(self.config_db) as fb:
            cli_por_doc = {}
            for r in fb.query(
                "SELECT CF_CODIGO, CF_CPF_CGC, CF_RAZAO, CF_ENDERECO, CF_NRO_END, CF_BAIRRO, "
                "       CF_CEP, CF_CIDADE, CF_CIDADE_EMPRESA, CF_CIDADE_FILIAL, CF_FONE1, "
                "       CF_RG_IE, CF_CLIENTE, CF_FORNECEDOR, CF_REPRESENTANTE "
                "FROM TABELA_CLI_FOR WHERE CF_EMPRESA = ? AND CF_FILIAL = ?",
                [emp_cad, fil_cad]
            ):
                doc = so_digitos(r.get('cf_cpf_cgc'))
                if doc:
                    cli_por_doc.setdefault(doc, r)
            d['clientes'] = cli_por_doc

            for rot, tab, pref in (('nat_saida', 'TABELA_NAT_OPERACAO_SAIDA', 'NAT'),
                                   ('nat_entrada', 'TABELA_NAT_OPERACAO_ENTRADA', 'NAT')):
                nats = {}
                for r in fb.query(
                    f"SELECT {pref}_CODIGO, {pref}_DESCRICAO_ABR, {pref}_FLUXO_CAIXA, "
                    f"       {pref}_CONTABILIDADE, {pref}_ESTOQUE, {pref}_DESATIVADO "
                    f"FROM {tab} WHERE {pref}_EMPRESA = ? AND {pref}_FILIAL = ?",
                    [emp_cad, fil_cad]
                ):
                    cod = str(r.get(f'{pref.lower()}_codigo') or '').strip()
                    if cod:
                        nats[cod] = r
                d[rot] = nats

            prods = fb.query(
                "SELECT PRODUTO_CODIGO, PRODUTO_DESCRICAO, PRODUTO_ATIVO, "
                "       PRODUTO_COD_IMPORTACAO, PRODUTO_COD_AUXILIAR "
                "FROM TABELA_PRODUTO WHERE PRODUTO_EMPRESA = ? AND PRODUTO_FILIAL = ?",
                [emp_cad, fil_cad])
            d['indices_produto'] = self._indexar_produtos(prods)

            chaves = set()
            for tab, col in (('TABELA_NF_SAIDA', 'NFS_CHAVE_DANFE'),
                             ('TABELA_NF_ENTRADA', 'NFE_CHAVE_DANFE')):
                for r in fb.query(f"SELECT {col} FROM {tab} WHERE {col} IS NOT NULL"):
                    k = so_digitos(list(r.values())[0])
                    if k:
                        chaves.add(k)
            d['chaves'] = chaves

            # (numero, serie, cliente/fornecedor) para o fallback de duplicidade
            docs = set()
            for r in fb.query("SELECT NFS_NRO_NF, NFS_SERIE, NFS_CLIENTE FROM TABELA_NF_SAIDA "
                              "WHERE NFS_EMPRESA = ? AND NFS_FILIAL = ?", [emp, fil]):
                docs.add(('S', int(r.get('nfs_nro_nf') or 0),
                          str(r.get('nfs_serie') or '').strip(), int(r.get('nfs_cliente') or 0)))
            for r in fb.query("SELECT NFE_NRO_NF, NFE_NFE_SERIE, NFE_FORNECEDOR FROM TABELA_NF_ENTRADA "
                              "WHERE NFE_EMPRESA = ? AND NFE_FILIAL = ?", [emp, fil]):
                docs.add(('E', int(r.get('nfe_nro_nf') or 0),
                          str(r.get('nfe_nfe_serie') or '').strip(), int(r.get('nfe_fornecedor') or 0)))
            d['docs_nf'] = docs

            # títulos já existentes (para não duplicar o financeiro já importado)
            tit_rec, tit_pag = set(), set()
            for r in fb.query("SELECT TIT_CODIGO, TIT_SERIE, TIT_CLIENTE FROM TABELA_TITULO_REC "
                              "WHERE TIT_EMPRESA = ? AND TIT_FILIAL = ?", [emp, fil]):
                tit_rec.add((str(r.get('tit_codigo') or '').strip().lstrip('0'),
                             str(r.get('tit_serie') or '').strip().upper(),
                             int(r.get('tit_cliente') or 0)))
            for r in fb.query("SELECT TIT_CODIGO, TIT_SERIE, TIT_FORNECEDOR FROM TABELA_TITULO "
                              "WHERE TIT_EMPRESA = ? AND TIT_FILIAL = ?", [emp, fil]):
                tit_pag.add((str(r.get('tit_codigo') or '').strip().lstrip('0'),
                             str(r.get('tit_serie') or '').strip().upper(),
                             int(r.get('tit_fornecedor') or 0)))
            d['tit_rec'], d['tit_pag'] = tit_rec, tit_pag
        return d

    def _classificar(self, notas, dados, emp, fil, cnpj_emp='',
                     emp_cad=None, fil_cad=None):
        """Monta as 4 listas de análise a partir das notas e da foto do ERP."""
        emp_cad = dados.get('emp_cad', emp) if emp_cad is None else emp_cad
        fil_cad = dados.get('fil_cad', fil) if fil_cad is None else fil_cad
        clientes = dados['clientes']
        indices = dados['indices_produto']
        cnpj_emp = so_digitos(cnpj_emp)

        # Radiografia da pasta: quem emitiu os XMLs que estão ali. É o que permite
        # confiar (ou desconfiar) do resultado num olhar — pasta com CNPJ trocado ou
        # misturada com notas de compra fica evidente aqui, em vez de virar um monte
        # de linhas 'TERCEIROS (ignorada)' sem explicação.
        emitentes = {}
        for n in notas:
            e = n.get('emit') or {}
            doc = so_digitos(e.get('documento') or '')
            reg = emitentes.setdefault(doc, {
                'documento': doc,
                'formatado': e.get('documento_formatado') or doc,
                'razao': str(e.get('razao') or e.get('nome') or '')[:44],
                'notas': 0, 'propria': doc == cnpj_emp if cnpj_emp else None,
                'como_dest': 0})
            reg['notas'] += 1
            if so_digitos((n.get('dest') or {}).get('documento') or '') == cnpj_emp:
                reg['como_dest'] += 1
        emitentes = sorted(emitentes.values(), key=lambda r: -r['notas'])

        # ---- fase 1: contrapartes
        contrapartes = {}
        for n in notas:
            if not n.get('emissao_propria'):
                continue
            c = n.get('contraparte') or {}
            doc = c.get('documento', '')
            if not doc:
                continue
            reg = contrapartes.setdefault(doc, {'dados': c, 'notas': 0, 'erp': None})
            reg['notas'] += 1
            reg['erp'] = clientes.get(doc)
        fase1 = []
        for doc, reg in sorted(contrapartes.items(), key=lambda kv: -kv[1]['notas']):
            existe = reg['erp'] is not None
            fase1.append({
                'documento': doc, 'dados': reg['dados'], 'notas': reg['notas'],
                'erp': reg['erp'],
                'codigo_erp': int(reg['erp']['cf_codigo']) if existe else None,
                'status': 'OK' if existe else 'NÃO CADASTRADO',
                'tag': 'OK' if existe else 'ERRO',
            })

        # ---- fase 2: naturezas de operação (CFOP)
        cfops = {}
        for n in notas:
            if not n.get('emissao_propria'):
                continue
            tipo = 'S' if n['tp_nf'] == 1 else 'E'
            for item in n['itens']:
                cf = str(item.get('cfop') or '').strip()
                if not cf:
                    continue
                reg = cfops.setdefault((tipo, cf), {'notas': set(), 'desc': n.get('nat_op', '')})
                reg['notas'].add(n['chave'])
        # NAT_CODIGO é o CFOP + 2 dígitos de variação: o CFOP 5101 aparece como
        # 510101, 510102... cada variação com as suas flags. Natureza já cadastrada
        # é IMUTÁVEL — outras rotinas do ERP e as notas antigas dependem dela. Então
        # a regra é: existe variação que atenda exatamente? usa. Não existe? cadastra
        # uma variação NOVA. Nunca altera a que está lá.
        fluxo_q, contab_q, estoq_q = getattr(self, '_flags_desejadas', ('S', 'S', 'N'))
        fase2 = []
        for (tipo, cf), reg in sorted(cfops.items()):
            nats = dados['nat_saida'] if tipo == 'S' else dados['nat_entrada']
            variacoes = sorted((cod, r) for cod, r in nats.items()
                               if cod == cf or cod.startswith(cf))

            def flags_de(r):
                return (str(r.get('nat_fluxo_caixa') or '').strip().upper(),
                        str(r.get('nat_contabilidade') or '').strip().upper(),
                        str(r.get('nat_estoque') or '').strip().upper())

            perfeita = next((c for c, r in variacoes
                             if flags_de(r) == (fluxo_q, contab_q, estoq_q)), None)

            if perfeita:
                achou = dict(variacoes)[perfeita]
                cod_erp = perfeita
                fluxo, contab, estoq = flags_de(achou)
                desc_erp = str(achou.get('nat_descricao_abr') or '').strip()
                status = 'OK' if len(variacoes) == 1 else f'OK (variação {perfeita})'
                tag = 'OK'
            elif variacoes:
                # tem o CFOP, mas nenhuma variação com estas flags
                cod_erp, achou = None, None
                fluxo = contab = estoq = '—'
                desc_erp = ' / '.join(
                    f"{c}: fluxo={flags_de(r)[0] or '—'} contab={flags_de(r)[1] or '—'} "
                    f"estoq={flags_de(r)[2] or '—'}" for c, r in variacoes)
                status = (f'CADASTRAR VARIAÇÃO — as {len(variacoes)} existentes não têm '
                          f'fluxo={fluxo_q} contab={contab_q} estoq={estoq_q}')
                tag = 'ERRO'
            else:
                cod_erp, achou = None, None
                status, tag = 'NÃO CADASTRADO', 'ERRO'
                fluxo = contab = estoq = '—'
                desc_erp = ''

            fase2.append({
                'tipo': tipo, 'cfop': cf, 'codigo_erp': cod_erp, 'desc_erp': desc_erp,
                'desc_xml': reg['desc'], 'fluxo': fluxo, 'contabil': contab,
                'estoque': estoq, 'notas': len(reg['notas']),
                'variacoes': [c for c, _ in variacoes],
                'status': status, 'tag': tag,
            })

        # A VARIAÇÃO ESCOLHIDA AQUI É A QUE VAI PARA A NOTA. Sem este mapa, a
        # gravação reescolhia por conta própria ("a primeira que começa com o
        # CFOP") e vinculava a nota à 510101 (fluxo=S) numa importação SEM
        # financeiro: o ERP passava a esperar parcelas, não achava, e recusava
        # imprimir o DANFE.
        dados['nat_escolhida'] = {(f['tipo'], f['cfop']): f['codigo_erp']
                                  for f in fase2 if f['codigo_erp']}

        # ---- fase 3: produtos
        prods = {}
        for n in notas:
            if not n.get('emissao_propria'):
                continue
            for item in n['itens']:
                cod = str(item.get('c_prod') or '').strip()
                if not cod:
                    continue
                reg = prods.setdefault(cod, {'item': item, 'qtde': 0})
                reg['qtde'] += 1
        fase3 = []
        for cod, reg in sorted(prods.items(), key=lambda kv: -kv[1]['qtde']):
            info, campo, ambiguos = self._resolver_produto(cod, indices, 'auto')
            # os candidatos ficam na linha: é com eles que o duplo clique monta a
            # escolha, sem ter de varrer o índice de novo
            cands = self._infos_produto(dados, ambiguos) if ambiguos else []
            escolhido = self._prod_escolhido.get(cod)
            if ambiguos and escolhido in ambiguos:
                # o usuário já desempatou na tela (duplo clique na aba 3). Sem essa
                # saída, um código ambíguo travava toda nota que o cita, e nem
                # sempre há como inativar um dos gêmeos — os dois estão em uso.
                info = next((c for c in cands if c['codigo'] == escolhido), None)
                status = f'OK (escolhido na tela: {escolhido})'
                tag = 'OK'
            elif ambiguos:
                # só chega aqui com mais de um produto ATIVO; gêmeo inativo o
                # resolvedor já descarta. Mostrar os códigos evita ter de ir
                # garimpar no ERP qual é o par em conflito.
                status = f'AMBÍGUO ({len(ambiguos)}: {", ".join(map(str, ambiguos))})'
                tag = 'ERRO'
            elif info is None:
                status, tag = 'NÃO ENCONTRADO', 'ERRO'
            elif info.get('casou_degradado'):
                # achou pelos dígitos, ignorando as letras do código do XML. Não
                # bloqueia (é o que o resolvedor tem), mas nunca passa calado:
                # letra diferente costuma ser produto diferente.
                status = (f"OK (casou só pelos dígitos {info['casou_degradado']} — "
                          f"confira se é o produto certo)")
                tag = 'AVISO'
            elif info.get('gemeos_inativos'):
                status = ('OK (gêmeo inativo ignorado: '
                          + ', '.join(map(str, info['gemeos_inativos'])) + ')')
                tag = 'OK'
            elif info.get('ativo') == 'N':
                # A nota é histórico: o produto que ela usou foi esse mesmo, e o
                # cliente pode tê-lo inativado depois. Inativo NÃO impede importar
                # — só avisa, para não parecer que passou batido.
                status, tag = 'OK (produto inativo no ERP — nota antiga)', 'AVISO'
            else:
                status, tag = 'OK', 'OK'
            fase3.append({
                'cod_xml': cod, 'item': reg['item'], 'itens': reg['qtde'],
                'codigo_erp': info['codigo'] if info else None,
                'desc_erp': info['descricao'] if info else '',
                'casou_por': campo or '', 'status': status, 'tag': tag,
                'ambiguos': cands,
            })

        # ---- fase 4: notas
        pend_cli = {f['documento'] for f in fase1 if f['tag'] != 'OK'}
        pend_nat = {(f['tipo'], f['cfop']) for f in fase2 if f['tag'] == 'ERRO'}
        # só ERRO bloqueia: 'AVISO' na fase 3 é produto inativo, que importa igual
        pend_prod = {f['cod_xml'] for f in fase3 if f['tag'] == 'ERRO'}
        # ambiguidade e produto faltando bloqueiam pelo mesmo caminho, mas a saída
        # é diferente (escolher x cadastrar) — o motivo da nota diz qual é qual
        amb_prod = {f['cod_xml'] for f in fase3 if f['tag'] == 'ERRO' and f['ambiguos']}
        fase4 = []
        for n in sorted(notas, key=lambda x: (x['tp_nf'], x['nro_nf'])):
            tipo = 'SAÍDA' if n['tp_nf'] == 1 else 'ENTRADA'
            c = n.get('contraparte') or {}
            doc = c.get('documento', '')
            cod_cp = None
            if doc in clientes:
                cod_cp = int(clientes[doc]['cf_codigo'])
            chave_doc = ('S' if n['tp_nf'] == 1 else 'E', n['nro_nf'],
                         str(n['serie']).strip(), cod_cp or 0)
            motivos = []
            if not n.get('emissao_propria'):
                status, tag = 'TERCEIROS (ignorada)', 'NEUTRO'
                # dizer QUAL é o papel da empresa na nota, não só "não é a empresa":
                # nota recebida de fornecedor e nota de outra empresa são coisas
                # diferentes e exigem providências diferentes de quem separou a pasta
                emit_doc = so_digitos((n.get('emit') or {}).get('documento') or '')
                dest_doc = so_digitos((n.get('dest') or {}).get('documento') or '')
                emit_nome = str((n.get('emit') or {}).get('razao') or '')[:34]
                if dest_doc and dest_doc == cnpj_emp:
                    motivos.append(f"nota RECEBIDA — a empresa é o destinatário; "
                                   f"quem emitiu foi {emit_nome}")
                elif emit_doc:
                    motivos.append(f"nota de OUTRA empresa — emitente {emit_nome}, "
                                   f"destinatário {str((n.get('dest') or {}).get('razao') or '')[:26]}")
                else:
                    motivos.append("emitente sem CNPJ no XML")
            elif n['chave'] and n['chave'] in dados['chaves']:
                status, tag = 'JÁ IMPORTADA', 'NEUTRO'
                motivos.append('chave da NF-e já existe no ERP')
            elif cod_cp is not None and chave_doc in dados['docs_nf']:
                status, tag = 'JÁ IMPORTADA', 'NEUTRO'
                motivos.append('número + série + contraparte já existem no ERP')
            else:
                if doc in pend_cli:
                    motivos.append('fase 1: contraparte não cadastrada')
                cfs = [('S' if n['tp_nf'] == 1 else 'E', str(i.get('cfop') or '').strip())
                       for i in n['itens']]
                if any(cf in pend_nat for cf in cfs):
                    motivos.append('fase 2: natureza de operação não cadastrada')
                cods_pend = sorted({c for c in (str(i.get('c_prod') or '').strip()
                                                for i in n['itens']) if c in pend_prod})
                ambig = [c for c in cods_pend if c in amb_prod]
                if ambig:
                    motivos.append('fase 3: produto ambíguo — duplo clique na aba 3 para '
                                   'escolher qual usar (' + ', '.join(ambig[:4])
                                   + (', ...' if len(ambig) > 4 else '') + ')')
                if any(c not in amb_prod for c in cods_pend):
                    motivos.append('fase 3: produto não encontrado')
                if motivos:
                    status, tag = 'PENDENTE FASES 1-3', 'ERRO'
                else:
                    status, tag = 'OK', 'OK'
                    # Situação do documento fiscal: cancelada e denegada entram
                    # (a escrituração precisa delas) mas SEM financeiro. O STATUS
                    # continua 'OK' de propósito — é ele que marca a nota para
                    # importar e que os contadores comparam; a situação tem coluna
                    # própria na grade e aparece no motivo.
                    sit = str(n.get('sit_documento') or SITD_REGULAR)
                    if sit != SITD_REGULAR:
                        tag = 'AVISO'
                        if sit in (SITD_CANCELADO, SITD_DENEGADA):
                            motivos.append(f'{SITD_DESCRICAO.get(sit, sit)} (situação {sit}) — '
                                           f'entra para a escrituração, sem gerar financeiro')
                        else:
                            motivos.append(f'{SITD_DESCRICAO.get(sit, sit)} (situação {sit})')
                    # aviso de título já existente (não bloqueia)
                    cod_tit = str(n['nro_nf']).lstrip('0')
                    serie = str(n['serie']).strip().upper()
                    conj = dados['tit_rec'] if n['tp_nf'] == 1 else dados['tit_pag']
                    if cod_cp is not None and (cod_tit, serie, cod_cp) in conj:
                        motivos.append('título já existe no financeiro — será vinculado, não duplicado')
                        tag = 'AVISO'
                    # ICMS desonerado: o total da nota no ERP é calculado por
                    # TR_NF_SAIDA_TOTAL, que não desconta a desoneração. O total
                    # ficará acima do da DANFE (itens e financeiro ficam certos).
                    deson = float(n['totais'].get('vICMSDeson') or 0.0)
                    if n['tp_nf'] == 1 and deson > 0.005:
                        motivos.append(f'ICMS desonerado de {self._brl(deson)} — total no ERP '
                                       f'ficará {self._brl(deson)} acima do da DANFE')
                        tag = 'AVISO'
            fase4.append({
                'nota': n, 'tipo': tipo, 'contraparte_cod': cod_cp,
                'status': status, 'tag': tag, 'motivo': '; '.join(motivos),
                'marcado': status == 'OK',
            })
        return {'fase1': fase1, 'fase2': fase2, 'fase3': fase3, 'fase4': fase4,
                'dados': dados, 'emp': emp, 'fil': fil,
                'emp_cad': emp_cad, 'fil_cad': fil_cad,
                'emitentes': emitentes, 'cnpj_emp': cnpj_emp}

    def _infos_produto(self, dados, codigos):
        """Código, descrição e situação dos produtos do ERP em conflito."""
        alvo = set(codigos or [])
        achados = {}
        for indice in dados['indices_produto'].values():
            for lista in indice.values():
                for info in lista:
                    if info['codigo'] in alvo:
                        achados.setdefault(info['codigo'], info)
        return [achados[c] for c in sorted(alvo) if c in achados]

    # ------------------------------------------- PRODUTO AMBÍGUO (desempate)
    def _on_dblclick_produto(self, _evento=None):
        sel = self.tree_prod.selection()
        f = self._grids['produtos'].get(sel[0]) if sel else None
        if not f:
            return
        if not f.get('ambiguos'):
            if f['tag'] == 'ERRO':      # NÃO ENCONTRADO: aqui não há o que escolher
                messagebox.showinfo(
                    "Nada a escolher", f"O código {f['cod_xml']} não existe no ERP "
                                       f"({f['status']}).\n\nUse “Cadastrar Pendências da "
                                       f"Aba”. O duplo clique só desempata código que está "
                                       f"em mais de um produto.")
            return
        self._escolher_produto_ambiguo(f)

    def _escolher_produto_ambiguo(self, f):
        """Deixa o usuário dizer qual dos produtos em conflito a nota usa.

        O sistema de origem do cliente emite o mesmo código para dois cadastros
        do ERP e nem sempre há como inativar um deles — os dois estão em uso.
        Sem saída na tela, um código ambíguo deixava em 'PENDENTE FASES 1-3'
        TODA nota que o citasse, e a importação inteira ficava parada por um
        empate que só o usuário desempata. A escolha vale para todas as notas
        com aquele código e fica guardada no config.ini (por banco), então
        reanalisar não obriga a escolher de novo.
        """
        cands = f['ambiguos']
        it = f['item']
        top = tk.Toplevel(self)
        top.title("Qual produto do ERP esta nota usa?")
        top.transient(self.winfo_toplevel())
        top.resizable(False, False)

        tk.Label(top, text=f"Código {f['cod_xml']} no XML — {(it.get('x_prod') or '')[:58]}",
                 font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, padx=14, pady=(12, 2))
        tk.Label(top, text=f"NCM {it.get('ncm') or '—'} · {it.get('u_com') or '—'} · "
                           f"{f['itens']} item(ns) nas notas · casou por "
                           f"{(f['casou_por'] or '—').upper()}",
                 font=("Segoe UI", 8), fg="#555").pack(anchor=tk.W, padx=14)
        tk.Label(top, text="Este código está em mais de um produto ATIVO do ERP. Escolha qual "
                           "deles a nota usa —\na escolha vale para todas as notas com este "
                           "código e fica guardada para as próximas análises.",
                 font=("Segoe UI", 9), justify=tk.LEFT).pack(anchor=tk.W, padx=14, pady=(10, 8))

        var = tk.StringVar(value=str(self._prod_escolhido.get(f['cod_xml'],
                                                             cands[0]['codigo'])))
        quadro = tk.Frame(top)
        quadro.pack(fill=tk.X, padx=14)
        for c in cands:
            sit = '' if c.get('ativo') != 'N' else '   (INATIVO)'
            ttk.Radiobutton(
                quadro, variable=var, value=str(c['codigo']),
                text=f"{c['codigo']}  —  {c['descricao'][:52]}{sit}\n"
                     f"        cód. de importação: {c.get('cod_importacao') or '—'}"
                     f"   ·   auxiliar: {c.get('cod_auxiliar') or '—'}"
            ).pack(anchor=tk.W, pady=4)

        def aplicar(escolha):
            if escolha is None:
                self._prod_escolhido.pop(f['cod_xml'], None)
            else:
                self._prod_escolhido[f['cod_xml']] = escolha
            top.destroy()
            self._salvar_config()
            self._reclassificar()

        rodape = tk.Frame(top)
        rodape.pack(fill=tk.X, padx=14, pady=12)
        ttk.Button(rodape, text="Usar este produto",
                   command=lambda: aplicar(int(var.get()))).pack(side=tk.LEFT)
        if f['cod_xml'] in self._prod_escolhido:
            ttk.Button(rodape, text="Desfazer a escolha",
                       command=lambda: aplicar(None)).pack(side=tk.LEFT, padx=6)
        ttk.Button(rodape, text="Cancelar", command=top.destroy).pack(side=tk.RIGHT)
        top.grab_set()

    def _reclassificar(self):
        """Refaz a análise com o que já está em memória, sem reler os XMLs.

        Desempatar um produto muda a fase 3 e, com ela, quais notas continuam
        pendentes na fase 4 — reclassificar tudo é mais seguro que remendar as
        duas grades à mão, e não custa consulta ao banco (a foto do ERP já está
        em `analise['dados']`).
        """
        a = self.analise
        if not a or not self.notas:
            return
        self.lbl_status.config(text="Reavaliando as fases...")
        nova = self._classificar(self.notas, a['dados'], a['emp'], a['fil'],
                                 a['cnpj_emp'], a['emp_cad'], a['fil_cad'])
        self.analise = nova
        # a radiografia da pasta é da análise; repeti-la a cada desempate seria
        # um popup no meio do trabalho
        self._sem_radiografia = True
        self._renderizar(nova)

    # ----------------------------------------------------------- RENDER
    def _renderizar(self, analise):
        for chave, tree in (('clientes', self.tree_cli), ('naturezas', self.tree_nat),
                            ('produtos', self.tree_prod), ('notas', self.tree_nota)):
            for i in tree.get_children():
                tree.delete(i)
            self._grids[chave].clear()

        for f in analise['fase1']:
            d = f['dados']
            iid = self.tree_cli.insert("", tk.END, values=(
                f['status'], d.get('documento_formatado', ''), (d.get('razao') or '')[:60],
                d.get('uf', ''), d.get('cidade_nome', ''), f['notas'],
                f['codigo_erp'] if f['codigo_erp'] else '—'), tags=(f['tag'],))
            self._grids['clientes'][iid] = f

        for f in analise['fase2']:
            iid = self.tree_nat.insert("", tk.END, values=(
                f['status'], f['cfop'], 'SAÍDA' if f['tipo'] == 'S' else 'ENTRADA',
                (f['desc_erp'] or f['desc_xml'])[:50], f['fluxo'], f['contabil'],
                f['estoque'], f['notas']), tags=(f['tag'],))
            self._grids['naturezas'][iid] = f

        for f in analise['fase3']:
            it = f['item']
            iid = self.tree_prod.insert("", tk.END, values=(
                f['status'], f['cod_xml'], (it.get('x_prod') or '')[:55],
                it.get('ncm', ''), it.get('u_com', ''),
                f['codigo_erp'] if f['codigo_erp'] else '—',
                f['casou_por'].upper() if f['casou_por'] else '—', f['itens']), tags=(f['tag'],))
            self._grids['produtos'][iid] = f

        total = len(analise['fase4'])
        chunk = 60
        # token de geração: uma reanálise durante o render descarta a cadeia
        # antiga, senão as duas escrevem na mesma grade e os cards somam duas vezes
        self._render_seq = getattr(self, '_render_seq', 0) + 1
        meu_seq = self._render_seq

        def render_chunk(ini):
            if meu_seq != self._render_seq or not self._viva():
                return  # um render mais novo assumiu a grade, ou a tela fechou
            fim = min(ini + chunk, total)
            for k in range(ini, fim):
                f = analise['fase4'][k]
                n = f['nota']
                c = n.get('contraparte') or {}
                sit = str(n.get('sit_documento') or SITD_REGULAR)
                iid = self.tree_nota.insert("", tk.END, values=(
                    "☑" if f['marcado'] else "☐", f['status'],
                    f"{sit} {SITD_DESCRICAO.get(sit, 'REGULAR')}",
                    f['tipo'], n['nro_nf'],
                    n['serie'],
                    n['data_emissao'].strftime('%d/%m/%Y') if n['data_emissao'] else '—',
                    (c.get('razao') or c.get('documento_formatado') or '')[:55],
                    self._brl(n['totais'].get('vNF', 0.0)),
                    len(n['itens']), len(n['parcelas']), f['motivo'][:70]), tags=(f['tag'],))
                self._grids['notas'][iid] = f
            if fim < total:
                self.lbl_status.config(text=f"Montando a grade {fim}/{total}...")
                self.update_idletasks()
                self.parent.after(5, render_chunk, fim)
            else:
                self._pos_render(analise)

        if total:
            render_chunk(0)
        else:
            self._pos_render(analise)

    def _pos_render(self, analise):
        self.progresso['value'] = 100
        self.btn_analisar.config(state=tk.NORMAL)
        self.btn_cadastrar.config(state=tk.NORMAL)
        self.btn_exportar.config(state=tk.NORMAL)
        self.btn_situacao.config(
            state=tk.NORMAL if self._notas_para_situacao(analise) else tk.DISABLED)
        # a grade nasce marcada só no escopo escolhido — o que está marcado é
        # exatamente o que vai ser gravado nesta passada
        self._marcar_pelo_escopo()
        self._atualizar_cards()
        ok = sum(1 for f in analise['fase4'] if f['status'] == 'OK')
        tipos = self._tipos_do_escopo()
        no_escopo = sum(1 for f in analise['fase4']
                        if f['status'] == 'OK' and f['nota']['tp_nf'] in tipos)
        self.btn_importar.config(state=tk.NORMAL if no_escopo else tk.DISABLED)
        pend = (sum(1 for f in analise['fase1'] if f['tag'] != 'OK')
                + sum(1 for f in analise['fase2'] if f['tag'] == 'ERRO')
                + sum(1 for f in analise['fase3'] if f['tag'] == 'ERRO'))
        fora = ok - no_escopo
        extra = f" ({fora} fora do escopo '{self._escopo()}')" if fora else ""
        self.lbl_status.config(
            text=f"Pronto. {len(analise['fase4'])} nota(s) lida(s) | {no_escopo} pronta(s) "
                 f"para importar{extra} | {pend} pendência(s) nas fases 1-3")
        self._conferir_emitentes(analise)

    def _conferir_emitentes(self, analise):
        """Mostra de quem são os XMLs da pasta e avisa quando não fecha.

        O silêncio aqui já custou caro: com o CNPJ de uma empresa e a pasta de outra,
        TODAS as notas viram 'TERCEIROS (ignorada)' e a tela não dizia por quê.
        """
        if getattr(self, '_sem_radiografia', False):
            self._sem_radiografia = False
            return
        emits = analise.get('emitentes') or []
        if not emits:
            return
        cnpj_emp = analise.get('cnpj_emp') or ''
        total = sum(r['notas'] for r in emits)
        propria = sum(r['notas'] for r in emits if r['documento'] == cnpj_emp)
        recebidas = sum(r['como_dest'] for r in emits if r['documento'] != cnpj_emp)
        outras = total - propria - recebidas

        linhas = [f"Pasta com {total} nota(s) de {len(emits)} emitente(s):", ""]
        for r in emits[:8]:
            if r['documento'] == cnpj_emp:
                papel = "A EMPRESA (serão importadas)"
            elif r['como_dest'] == r['notas']:
                papel = "fornecedor (nota recebida)"
            elif r['como_dest']:
                papel = f"fornecedor em {r['como_dest']} de {r['notas']}"
            else:
                papel = "OUTRA empresa"
            linhas.append(f"  {r['notas']:>5}  {r['formatado']:<20} {r['razao'][:32]:<32} {papel}")
        if len(emits) > 8:
            linhas.append(f"  ... e mais {len(emits) - 8} emitente(s)")
        linhas += ["",
                   f"Emissão própria (CNPJ {cnpj_emp or '—'}): {propria}",
                   f"Notas recebidas de fornecedor:            {recebidas}",
                   f"Notas de outra empresa:                   {outras}"]

        if not propria:
            linhas += ["", "⚠ NENHUMA nota foi emitida pelo CNPJ informado.",
                       "Confira se o banco conectado é o da empresa certa e se a",
                       "pasta é a dela — do jeito que está, nada será importado."]
            return messagebox.showerror("Pasta e CNPJ não combinam", "\n".join(linhas))
        if recebidas or outras:
            linhas += ["", "As notas recebidas e as de outra empresa são ignoradas —",
                       "esta rotina só importa o que a empresa emitiu."]
            return messagebox.showwarning("Confira os emitentes da pasta", "\n".join(linhas))
        messagebox.showinfo("Emitentes da pasta", "\n".join(linhas))

    def _atualizar_cards(self):
        if not self.analise:
            return
        marcadas = [f for f in self.analise['fase4'] if f['marcado'] and f['status'] == 'OK']
        valor = sum(f['nota']['totais'].get('vNF', 0.0) for f in marcadas)
        ignoradas = sum(1 for f in self.analise['fase4']
                        if f['status'] in ('JÁ IMPORTADA', 'TERCEIROS (ignorada)'))
        pend = (sum(1 for f in self.analise['fase1'] if f['tag'] != 'OK')
                + sum(1 for f in self.analise['fase2'] if f['tag'] == 'ERRO')
                + sum(1 for f in self.analise['fase3'] if f['tag'] == 'ERRO'))
        self.card_notas.lbl_valor.config(text=str(len(marcadas)))
        self.card_valor.lbl_valor.config(text=self._brl(valor))
        self.card_pendencias.lbl_valor.config(text=str(pend))
        self.card_ignoradas.lbl_valor.config(text=str(ignoradas))

    def _brl(self, valor):
        try:
            s = f"{float(valor):,.2f}"
        except (TypeError, ValueError):
            return "R$ 0,00"
        return "R$ " + s.replace(',', 'X').replace('.', ',').replace('X', '.')

    def _on_click_nota(self, event):
        if self.tree_nota.identify_region(event.x, event.y) != "cell":
            return
        if self.tree_nota.identify_column(event.x) != "#1":
            return
        iid = self.tree_nota.identify_row(event.y)
        if not iid:
            return
        f = self._grids['notas'].get(iid)
        if not f or f['status'] != 'OK':
            return
        f['marcado'] = not f['marcado']
        vals = list(self.tree_nota.item(iid, 'values'))
        vals[0] = "☑" if f['marcado'] else "☐"
        self.tree_nota.item(iid, values=vals)
        self._atualizar_cards()

    # ------------------------------------------------- COPIAR DADOS DA NOTA
    def _copiar(self, texto, rotulo):
        """Manda para a área de transferência e diz o que foi copiado."""
        if not texto:
            return messagebox.showinfo("Nada a copiar",
                                       f"Não há {rotulo.lower()} nesta nota.")
        self.clipboard_clear()
        self.clipboard_append(texto)
        self.update()          # sem isto o Windows pode perder o que foi copiado
        linhas = texto.splitlines()
        resumo = linhas[0][:57] + '...' if len(linhas[0]) > 60 else linhas[0]
        if len(linhas) > 1:
            resumo += f"  (+{len(linhas) - 1})"
        self.lbl_status.config(text=f"Copiado — {rotulo}: {resumo}")

    def _menu_nota(self, event):
        """Botão direito na aba 4: copia a chave da NF-e e o resto do identificador.

        A chave é o que se leva para fora — consulta no portal da SEFAZ, busca no
        ERP, `WHERE NFS_CHAVE_DANFE IN (...)`. Sem isto, só dava para lê-la da
        tela e digitar 44 dígitos à mão.
        """
        iid = self.tree_nota.identify_row(event.y)
        if not iid:
            return
        self.tree_nota.selection_set(iid)
        f = self._grids['notas'].get(iid)
        if not f:
            return
        n = f['nota']
        c = n.get('contraparte') or {}
        marcadas = [g['nota']['chave'] for g in self._grids['notas'].values()
                    if g['marcado'] and g['nota'].get('chave')]

        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="📋 Copiar a chave da NF-e (44 dígitos)",
                         command=lambda: self._copiar(n.get('chave') or '', "Chave da NF-e"))
        menu.add_command(label=f"📋 Copiar número e série ({n['nro_nf']}/{n['serie']})",
                         command=lambda: self._copiar(f"{n['nro_nf']}/{n['serie']}",
                                                     "Número e série"))
        menu.add_command(label="📋 Copiar CNPJ/CPF da contraparte",
                         command=lambda: self._copiar(c.get('documento_formatado')
                                                     or c.get('documento') or '',
                                                     "CNPJ/CPF da contraparte"))
        menu.add_separator()
        # para levar de uma vez ao SELECT: as chaves das notas marcadas, uma por linha
        menu.add_command(
            label=f"📋 Copiar as chaves das {len(marcadas)} nota(s) marcada(s)",
            state=tk.NORMAL if marcadas else tk.DISABLED,
            command=lambda: self._copiar("\n".join(marcadas),
                                         f"{len(marcadas)} chave(s)"))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # ------------------------------------------------- CADASTROS (FASES 1-3)
    def _cadastrar_aba(self):
        if not self.analise:
            return
        idx = self.abas.index(self.abas.select())
        if idx == 0:
            self._cadastrar_clientes()
        elif idx == 1:
            self._cadastrar_naturezas()
        elif idx == 2:
            self._cadastrar_produtos()
        else:
            messagebox.showinfo("Aviso", "Escolha a aba 1, 2 ou 3 para cadastrar as pendências.")

    def _cadastrar_clientes(self):
        pend = [f for f in self.analise['fase1'] if f['tag'] != 'OK']
        if not pend:
            return messagebox.showinfo("Aviso", "Nenhuma contraparte pendente.")
        if not messagebox.askyesno("Confirmar", f"Cadastrar {len(pend)} cliente(s)/fornecedor(es)?"):
            return
        # cadastro vai para a filial DOS CADASTROS, não para a da nota
        emp, fil = self._emp_fil_analise(cadastros=True)
        criados, erros, log = 0, 0, []
        try:
            with FirebirdService(self.config_db) as fb:
                r = fb.query("SELECT COALESCE(MAX(CF_CODIGO), 0) AS M FROM TABELA_CLI_FOR "
                             "WHERE CF_EMPRESA = ? AND CF_FILIAL = ?", [emp, fil])
                prox = int(r[0]['m']) + 1
                cid_por_ibge = {}
                for c in fb.query("SELECT CID_CODIGO, CID_CODIGO_IBGE FROM TABELA_CIDADE "
                                  "WHERE CID_EMPRESA = ? AND CID_FILIAL = ?", [emp, fil]):
                    ib = so_digitos(c.get('cid_codigo_ibge'))
                    if ib:
                        cid_por_ibge.setdefault(ib, c['cid_codigo'])
                for f in pend:
                    d = f['dados']
                    try:
                        cidade = cid_por_ibge.get(so_digitos(d.get('cidade_ibge')))
                        # CF_TIPO_INSCR aponta para TABELA_TIPO_INSCRICAO
                        # (1=CPF, 2=CNPJ, 99=OUTROS) — é o tipo do documento,
                        # não o indIEDest do XML (que não tem código 9 aqui).
                        doc = so_digitos(d.get('documento'))
                        if len(doc) == 11:
                            tipo_inscr = 1
                        elif len(doc) == 14:
                            tipo_inscr = 2
                        else:
                            tipo_inscr = 99
                        # CF_ICMS aponta para TABELA_ICMS: 1=CONTRIBUINTE,
                        # 2=NAO CONTRIBUINTE. É inteiro, não flag S/N.
                        ie = (d.get('ie') or 'ISENTO').strip()
                        cf_icms = 2 if ie.upper() in ('', 'ISENTO') else 1
                        rot_tipo = self._tipo_contraparte(f)
                        fb.execute("""
                            INSERT INTO TABELA_CLI_FOR (
                                CF_EMPRESA, CF_FILIAL, CF_CODIGO, CF_DATA, CF_DATA_ALT,
                                CF_CPF_CGC, CF_RAZAO, CF_FANTASIA, CF_ATIVO, CF_TIPO_INSCR,
                                CF_CLIENTE, CF_FORNECEDOR, CF_OUTROS, CF_RG_IE, CF_ICMS,
                                CF_ATIVIDADE, CF_ENDERECO, CF_NRO_END, CF_BAIRRO,
                                CF_CIDADE, CF_CEP, CF_CIDADE_EMPRESA, CF_CIDADE_FILIAL,
                                CF_REPRESENTANTE_EMP, CF_REPRESENTANTE_FILIAL,
                                CF_FONE1, CF_EMAIL_NFE
                            ) VALUES (?, ?, ?, CURRENT_DATE, CURRENT_DATE,
                                      ?, ?, ?, 'S', ?, ?, ?, ?, ?, ?, 1,
                                      ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'S')
                        """, [
                            emp, fil, prox,
                            d.get('documento_formatado', ''), (d.get('razao') or '')[:50],
                            (d.get('fantasia') or d.get('razao') or '')[:50],
                            tipo_inscr,
                            *tipo_cadastro.sn(rot_tipo),
                            ie[:20], cf_icms,
                            (d.get('endereco') or '')[:50], (d.get('nro_end') or '')[:10],
                            (d.get('bairro') or '')[:50], cidade, d.get('cep', ''),
                            emp, fil, emp, fil,
                            multivalor.um_fone(d.get('fone1'))[0][:15],
                        ])
                        f['codigo_erp'] = prox
                        f['status'], f['tag'] = 'OK', 'OK'
                        log.append(f"✅ {d.get('razao', '')[:45]} -> código {prox} [{rot_tipo}]")
                        prox += 1
                        criados += 1
                    except Exception as e:
                        erros += 1
                        log.append(f"❌ {d.get('razao', '')[:45]}: {e}")
        except Exception as e:
            return messagebox.showerror("Erro", f"Falha ao cadastrar:\n{e}")
        messagebox.showinfo("Concluído",
                            f"{criados} cadastrado(s), {erros} erro(s).\n\nReanalise para atualizar as fases.")
        self._oferecer_log(log, "LOG_CLIENTES_NFE.txt")

    def _tipo_contraparte(self, f):
        """Rótulo de `utils.tipo_cadastro` com que a contraparte será cadastrada.

        O combo manda quando o usuário escolhe um tipo fixo. No automático, o papel
        sai de TODAS as notas em que o documento aparece: destinatário de saída é
        cliente, emitente de entrada é fornecedor, e quem é os dois entra como os
        dois. A versão anterior parava na primeira nota encontrada, então quem compra
        e vende saía com uma flag só e tinha de ser corrigido à mão no ERP.
        """
        escolha = self.cmb_tipo_cf.get()
        if escolha in tipo_cadastro.TIPOS:
            return escolha

        doc = f['documento']
        cliente = fornecedor = False
        for item in self.analise['fase4']:
            n = item['nota']
            if (n.get('contraparte') or {}).get('documento') != doc:
                continue
            if n['tp_nf'] == 1:
                cliente = True
            else:
                fornecedor = True
        if not (cliente or fornecedor):
            cliente = True          # sem nota casada, o destino menos surpreendente
        return tipo_cadastro.rotulo(cliente=cliente, fornecedor=fornecedor)

    def _cadastrar_naturezas(self):
        pend = [f for f in self.analise['fase2'] if f['tag'] == 'ERRO']
        if not pend:
            return messagebox.showinfo(
                "Aviso", "Toda natureza de operação usada por estas notas já tem uma "
                         "variação com as flags escolhidas.")
        fluxo, contab, estoq = self._flags_nat()
        novas = sum(1 for f in pend if not f.get('variacoes'))
        variantes = len(pend) - novas
        if not messagebox.askyesno(
                "Confirmar",
                f"Cadastrar {len(pend)} natureza(s) de operação?\n\n"
                + (f"• {novas} CFOP(s) que não existem no ERP\n" if novas else "")
                + (f"• {variantes} CFOP(s) que existem, mas sem variação com estas "
                   f"flags — entra uma variação NOVA\n" if variantes else "")
                + f"\nFluxo de caixa = {fluxo}\n"
                f"Contabilidade  = {contab}\n"
                f"Estoque        = {estoq}  (a importação não movimenta estoque)\n\n"
                + ("Com fluxo de caixa = N as notas NÃO geram financeiro no ERP.\n\n"
                   if fluxo == 'N' else "")
                + "Nenhuma natureza existente é alterada."):
            return
        # a natureza é cadastro: entra na filial dos cadastros
        emp, fil = self._emp_fil_analise(cadastros=True)
        criados, erros, log = 0, 0, []
        try:
            with FirebirdService(self.config_db) as fb:
                for f in pend:
                    tab = ('TABELA_NAT_OPERACAO_SAIDA' if f['tipo'] == 'S'
                           else 'TABELA_NAT_OPERACAO_ENTRADA')
                    try:
                        # o próximo sufixo livre: 5101 com 510101 e 510102 -> 510103.
                        # Relê do banco em vez de confiar na análise: entre analisar e
                        # cadastrar alguém pode ter criado uma variação no ERP.
                        usados = {str(r['nat_codigo']).strip() for r in fb.query(
                            f"SELECT NAT_CODIGO FROM {tab} WHERE NAT_EMPRESA = ? "
                            f"AND NAT_FILIAL = ? AND NAT_CODIGO STARTING WITH ?",
                            [emp, fil, f['cfop']])}
                        codigo = next((f"{f['cfop']}{i:02d}" for i in range(1, 100)
                                       if f"{f['cfop']}{i:02d}" not in usados), None)
                        if not codigo:
                            raise RuntimeError(
                                f"as 99 variações do CFOP {f['cfop']} já existem")
                        desc = (f['desc_xml'] or f"CFOP {f['cfop']}")[:30]
                        # INSERT puro, sem UPDATE OR INSERT: natureza que já existe é
                        # imutável, outras rotinas e as notas antigas dependem dela.
                        fb.execute(f"""
                            INSERT INTO {tab} (
                                NAT_EMPRESA, NAT_FILIAL, NAT_CODIGO, NAT_DESCRICAO_ABR,
                                NAT_DESCRICAO_COMP, NAT_FLUXO_CAIXA, NAT_CONTABILIDADE,
                                NAT_ESTOQUE, NAT_DESATIVADO
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'N')
                        """, [emp, fil, codigo, desc, (f['desc_xml'] or desc)[:50],
                              fluxo, contab, estoq])
                        f['codigo_erp'] = codigo
                        f['status'] = ('OK' if not f.get('variacoes')
                                       else f'OK (variação {codigo})')
                        f['tag'] = 'OK'
                        f['fluxo'], f['contabil'], f['estoque'] = fluxo, contab, estoq
                        anteriores = f.get('variacoes') or []
                        f['variacoes'] = sorted(anteriores + [codigo])
                        log.append(
                            f"✅ CFOP {f['cfop']} -> natureza {codigo} ({desc}) "
                            f"fluxo={fluxo} contabilidade={contab} estoque={estoq}"
                            + (f" [conviva com {', '.join(anteriores)}, não alterada(s)]"
                               if anteriores else ""))
                        criados += 1
                    except Exception as e:
                        erros += 1
                        log.append(f"❌ CFOP {f['cfop']}: {e}")
        except Exception as e:
            return messagebox.showerror("Erro", f"Falha ao cadastrar:\n{e}")
        messagebox.showinfo("Concluído", f"{criados} natureza(s) criada(s), {erros} erro(s).\n\n"
                                         "Reanalise para atualizar as fases.")
        self._oferecer_log(log, "LOG_NATUREZAS_NFE.txt")

    def _cadastrar_produtos(self):
        pend = [f for f in self.analise['fase3'] if f['status'] == 'NÃO ENCONTRADO']
        if not pend:
            ambig = sum(1 for f in self.analise['fase3'] if f['tag'] == 'ERRO' and f['ambiguos'])
            return messagebox.showinfo(
                "Aviso", "Nenhum produto faltando."
                + (f"\n\n{ambig} código(s) AMBÍGUO(s) — o mesmo código está em mais de um "
                   f"produto do ERP. Dê DUPLO CLIQUE na linha para escolher qual deles a "
                   f"nota usa; cadastrar outro produto só criaria uma terceira via do "
                   f"mesmo item." if ambig else ""))
        if not messagebox.askyesno(
                "Confirmar",
                f"Cadastrar {len(pend)} produto(s)?\n\n"
                "O código do XML vai para o Código Auxiliar e o de Importação,\n"
                "e o produto recebe o próximo código livre do ERP."):
            return
        # o produto é cadastro: entra na filial dos cadastros
        emp, fil = self._emp_fil_analise(cadastros=True)
        tipo = self.config.get('IMPORTACAO', 'tipo', fallback='4')
        try:
            tipo_id = int(str(tipo).split('-')[0].strip())
        except (ValueError, IndexError):
            tipo_id = 4
        log = []
        try:
            with FirebirdService(self.config_db) as fb:
                usados = set()
                for r in fb.query("SELECT PRODUTO_CODIGO FROM TABELA_PRODUTO "
                                  "WHERE PRODUTO_EMPRESA = ? AND PRODUTO_FILIAL = ?", [emp, fil]):
                    usados.add(str(r['produto_codigo']).strip())
                prox = max((int(c) for c in usados if c.isdigit()), default=0) + 1
                registros = []
                for f in pend:
                    it = f['item']
                    xml_mock = {
                        'x_prod': (it.get('x_prod') or '')[:60],
                        'ncm': it.get('ncm', ''),
                        'c_ean': it.get('c_ean', ''),
                        'u_com': (it.get('u_com') or 'UN').upper(),
                    }
                    d = DataTransformer.prepare_produto(
                        xml_mock, {'empresa': emp, 'filial': fil},
                        {'tipo': tipo_id, 'grupo_id': 1, 'subgrupo_id': 1, 'producao_sistec': 'N'})
                    d['PRODUTO_CODIGO'] = str(prox)
                    d['PRODUTO_COD_AUXILIAR'] = f['cod_xml']
                    d['PRODUTO_COD_IMPORTACAO'] = f['cod_xml']
                    d['_ACAO'] = 'INSERT'
                    registros.append(d)
                    f['codigo_erp'] = str(prox)
                    f['status'], f['tag'], f['casou_por'] = 'OK', 'OK', 'importacao'
                    log.append(f"✅ {f['cod_xml']} {xml_mock['x_prod'][:40]} -> produto {prox}")
                    prox += 1
                res = FirebirdImporter(fb).import_produtos(registros)
        except Exception as e:
            return messagebox.showerror("Erro", f"Falha ao cadastrar produtos:\n{e}")
        inseridos = res.get('inseridos', 0)
        erros = res.get('erros', [])
        if erros:
            log.append("")
            for e in erros:
                log.append(f"❌ {e.get('erro', e)}")
        messagebox.showinfo(
            "Concluído",
            f"{inseridos} produto(s) cadastrado(s)."
            + (f"\n\n{len(erros)} erro(s) — o lote de produtos é tudo-ou-nada, "
               f"veja o log." if erros else "\n\nReanalise para atualizar as fases."))
        self._oferecer_log(log, "LOG_PRODUTOS_NFE.txt")

    # ------------------------------------------------------------ IMPORTAR
    def _iniciar_importacao(self):
        escopo = self._escopo()
        tipos = self._tipos_do_escopo(escopo)
        # o escopo é aplicado aqui também, e não só na marcação da grade: se o
        # usuário marcar à mão uma nota do outro tipo, ela receberia o rateio
        # errado — que é exatamente o motivo de as passadas serem separadas.
        marcadas = [f for f in (self.analise or {}).get('fase4', [])
                    if f['marcado'] and f['status'] == 'OK'
                    and f['nota']['tp_nf'] in tipos]
        if not marcadas:
            return messagebox.showwarning(
                "Aviso", f"Nenhuma nota marcada dentro do escopo '{escopo}'.")
        n_saida = sum(1 for f in marcadas if f['nota']['tp_nf'] == 1)
        n_entrada = len(marcadas) - n_saida
        valor = sum(f['nota']['totais'].get('vNF', 0.0) for f in marcadas)
        fin = "COM" if self.var_gerar_fin.get() else "SEM"
        cc = self.cmb_cc.get().strip() or '(nenhum)'
        conta = self.cmb_conta.get().strip() or '(nenhuma)'
        # A nota vai amarrada à variação que a fase 2 escolheu, e ela casa com as
        # flags pedidas. Se ainda assim sobrar fluxo=S numa importação SEM
        # financeiro, é incoerência da análise — a nota entraria pedindo parcela
        # que ninguém vai gravar, e o ERP recusaria imprimir o DANFE.
        fluxos = {f['fluxo'] for f in self.analise['fase2']
                  if f.get('codigo_erp') and f['tipo'] == ('S' if 1 in tipos else 'E')}
        alerta = ""
        if not self.var_gerar_fin.get() and fluxos & {'S'}:
            alerta = ("\n⚠ ATENÇÃO: há natureza escolhida com FLUXO DE CAIXA = S numa\n"
                      "importação SEM financeiro. Reanalise antes de importar — a\n"
                      "análise em tela é anterior à mudança do checkbox.\n")
        if not messagebox.askyesno(
                "Confirmar importação",
                f"Escopo: {escopo}\n\n"
                f"Importar {len(marcadas)} nota(s)?\n\n"
                f"Saídas: {n_saida}   |   Entradas: {n_entrada}\n"
                f"Valor total: {self._brl(valor)}\n\n"
                f"Centro de custo: {cc}\n"
                f"Conta contábil: {conta}\n\n"
                f"{fin} geração de financeiro (parcelas + título).\n"
                f"Fluxo de caixa das naturezas: {', '.join(sorted(fluxos)) or '—'}\n"
                f"Estoque NÃO será movimentado.\n"
                + alerta):
            return
        # lidos aqui, na thread da UI — a thread de gravação não toca em widget
        self._lc_padrao = self._codigo_combo(self.cmb_lc)
        self._vend_padrao = self._codigo_combo(self.cmb_vend)
        self._cc_padrao = self._codigo_combo(self.cmb_cc)
        self._conta_padrao = self._codigo_combo(self.cmb_conta)
        self._gerar_fin = self.var_gerar_fin.get()
        self.btn_importar.config(state=tk.DISABLED)
        self.btn_analisar.config(state=tk.DISABLED)
        self.progresso['value'] = 0
        threading.Thread(target=self._importacao_bg, args=(marcadas,), daemon=True).start()

    def _proximo(self, cur, tabela, coluna, emp, fil):
        cur.execute(f"SELECT COALESCE(MAX({coluna}), 0) + 1 FROM {tabela} "
                    f"WHERE {tabela.replace('TABELA_NF_', 'NF')[:3]}_EMPRESA = ? ", [emp])
        return int(cur.fetchone()[0])

    def _proximo_numero(self, cur, sql, params):
        cur.execute(sql, params)
        return int(cur.fetchone()[0] or 1)

    def _importacao_bg(self, marcadas):
        emp, fil = self.analise['emp'], self.analise['fil']
        dados = self.analise['dados']
        gerar_fin = getattr(self, '_gerar_fin', True)
        agora = datetime.datetime.now()
        ult_grav = agora.strftime('%Y-%m-%d %H:%M:%S')
        log = ["--- LOG DE IMPORTACAO DE NOTAS FISCAIS (XML) ---", ""]
        ok = erros = 0
        try:
            with FirebirdService(self.config_db) as fb:
                cur = fb.conn.cursor()
                total = len(marcadas)
                for idx, f in enumerate(marcadas):
                    n = f['nota']
                    rot = f"NF {n['nro_nf']}/{n['serie']} ({f['tipo']})"
                    if idx % 10 == 0:
                        pct = int((idx / total) * 100)
                        self._ui(lambda d=idx, t=total, p=pct: (
                            self.lbl_status.config(text=f"Gravando {d + 1}/{t} notas..."),
                            self.progresso.config(value=p)))
                    tem_sp = False
                    try:
                        cur.execute("SAVEPOINT SP_NF")
                        tem_sp = True
                    except Exception:
                        pass
                    try:
                        if n['tp_nf'] == 1:
                            self._gravar_saida(cur, n, f, emp, fil, dados, gerar_fin, ult_grav, log)
                        else:
                            self._gravar_entrada(cur, n, f, emp, fil, dados, gerar_fin, ult_grav, log)
                        ok += 1
                    except Exception as e:
                        erros += 1
                        log.append(f"❌ {rot}: {e}")
                        if tem_sp:
                            try:
                                cur.execute("ROLLBACK TO SAVEPOINT SP_NF")
                            except Exception:
                                pass
                        continue
                    if (idx + 1) % LOTE_COMMIT == 0:
                        try:
                            fb.conn.commit()
                            cur = fb.conn.cursor()
                        except Exception:
                            pass
                fb.conn.commit()
        except Exception as e:
            msg = str(e)
            self._ui(lambda: messagebox.showerror(
                "Erro de Importação", f"Ocorreu um erro estrutural:\n{msg}"))
            self._ui(self._pos_importacao)
            return

        resumo = f"{ok} nota(s) importada(s), {erros} com erro."
        log.insert(1, f"RESUMO: {resumo}")
        self._ui(lambda: messagebox.showinfo(
            "Concluído", f"Importação concluída!\n\n{resumo}\n\n"
                         f"Reanalise para ver as notas como JÁ IMPORTADA."))
        self._ui(lambda: self._oferecer_log(log, "LOG_IMPORTACAO_NFE.txt"))
        self._ui(self._pos_importacao)

    def _pos_importacao(self):
        self.btn_importar.config(state=tk.DISABLED)
        self.btn_analisar.config(state=tk.NORMAL)
        self.progresso['value'] = 100
        self.lbl_status.config(text="Importação finalizada. Clique em Analisar para reconferir.")

    # ------------------------- CORRIGIR A SITUAÇÃO DAS NOTAS JÁ IMPORTADAS
    @staticmethod
    def _notas_para_situacao(analise):
        """Notas da análise que já estão no ERP e têm chave para localizá-las.

        Existe porque nota que já está no ERP não é reimportada: as importadas por
        versões anteriores ficaram com NFS_SITD_CODIGO NULL e, quando canceladas,
        sem NFS_DATA_CANCELA — ou seja, contando como venda boa. A única fonte da
        situação são os mesmos XMLs, então a correção sai daqui.

        As regulares entram na lista de propósito: o 00 é tão necessário à
        escrituração quanto o 02.
        """
        return [f for f in (analise or {}).get('fase4', [])
                if f['status'] == 'JÁ IMPORTADA' and (f['nota'].get('chave') or '')]

    def _iniciar_situacao(self):
        alvo = self._notas_para_situacao(self.analise)
        if not alvo:
            return messagebox.showwarning(
                "Aviso", "Nenhuma nota desta pasta está marcada como JÁ IMPORTADA "
                         "com chave de NF-e. Nada a corrigir.")
        por_sit = {}
        for f in alvo:
            por_sit[self._sit_documento(f['nota'])] = \
                por_sit.get(self._sit_documento(f['nota']), 0) + 1
        detalhe = "\n".join(
            f"   {sit} {SITD_DESCRICAO.get(sit, 'REGULAR')}: {qtd} nota(s)"
            for sit, qtd in sorted(por_sit.items()))
        if not messagebox.askyesno(
                "Corrigir situação das já importadas",
                f"{len(alvo)} nota(s) desta pasta já estão no ERP:\n\n{detalhe}\n\n"
                f"Conferir e acertar no ERP a situação do documento fiscal e, nas "
                f"canceladas, a data e a justificativa do cancelamento?\n\n"
                f"Só é alterado o que estiver diferente. Nada mais da nota é "
                f"tocado: valores, itens, parcelas e títulos ficam como estão.\n\n"
                f"⚠ Financeiro já gerado para nota cancelada NÃO é apagado — "
                f"conferir no Receber/Pagar depois."):
            return
        self.btn_situacao.config(state=tk.DISABLED)
        self.btn_analisar.config(state=tk.DISABLED)
        self.progresso['value'] = 0
        threading.Thread(target=self._situacao_bg, args=(alvo,), daemon=True).start()

    def _situacao_bg(self, alvo):
        log = ["--- LOG DE CORRECAO DA SITUACAO DO DOCUMENTO FISCAL ---", ""]
        corrigidas = iguais = nao_achou = erros = 0
        try:
            with FirebirdService(self.config_db) as fb:
                cur = fb.conn.cursor()
                total = len(alvo)
                for idx, f in enumerate(alvo):
                    n = f['nota']
                    saida = n['tp_nf'] == 1
                    rot = f"NF {n['nro_nf']}/{n['serie']} ({f['tipo']})"
                    if idx % 20 == 0:
                        pct = int((idx / total) * 100)
                        self._ui(lambda d=idx, t=total, p=pct: (
                            self.lbl_status.config(text=f"Conferindo {d + 1}/{t} notas..."),
                            self.progresso.config(value=p)))
                    sit = self._sit_documento(n)
                    data_canc, motivo_canc = self._cancelamento(n)
                    try:
                        if saida:
                            cur.execute(
                                "SELECT NFS_EMPRESA, NFS_FILIAL, NFS_NUMERO, "
                                "NFS_SITD_CODIGO, NFS_DATA_CANCELA "
                                "FROM TABELA_NF_SAIDA WHERE NFS_CHAVE_DANFE = ?",
                                [n['chave'][:44]])
                        else:
                            cur.execute(
                                "SELECT NFE_EMPRESA, NFE_FILIAL, NFE_LANCAMENTO, "
                                "NFE_SITD_CODIGO, NFE_DATA_CANCELAMENTO "
                                "FROM TABELA_NF_ENTRADA WHERE NFE_CHAVE_DANFE = ?",
                                [n['chave'][:44]])
                        linhas = cur.fetchall()
                    except Exception as e:
                        erros += 1
                        log.append(f"❌ {rot}: {e}")
                        continue
                    if not linhas:
                        nao_achou += 1
                        log.append(f"   – {rot}: chave não encontrada no ERP "
                                   f"(a nota casou por número/série na análise)")
                        continue
                    for emp_r, fil_r, num_r, sit_erp, data_erp in linhas:
                        sets, params, mudou = [], [], []
                        if str(sit_erp or '').strip() != sit:
                            sets.append(("NFS_SITD_CODIGO = ?" if saida
                                         else "NFE_SITD_CODIGO = ?"))
                            params.append(sit)
                            mudou.append(f"situação {str(sit_erp or 'NULL').strip()} -> "
                                         f"{sit} {SITD_DESCRICAO.get(sit, 'REGULAR')}")
                        # data já preenchida não é sobrescrita: se o ERP registrou o
                        # cancelamento, a data dele é a boa.
                        if data_canc and not data_erp:
                            if saida:
                                sets.append("NFS_DATA_CANCELA = ?")
                                params.append(data_canc)
                                sets.append("NFS_MOTIVO_CANCELA = ?")
                                params.append(motivo_canc)
                                sets.append("NFS_USUARIO_CANCELAMENTO = ?")
                                params.append(USUARIO_PADRAO)
                            else:
                                sets.append("NFE_DATA_CANCELAMENTO = ?")
                                params.append(data_canc)
                            mudou.append(f"cancelamento em {self._data_br(data_canc)}")
                        if not sets:
                            iguais += 1
                            continue
                        tabela, chaves = (
                            ('TABELA_NF_SAIDA',
                             'NFS_EMPRESA = ? AND NFS_FILIAL = ? AND NFS_NUMERO = ?')
                            if saida else
                            ('TABELA_NF_ENTRADA',
                             'NFE_EMPRESA = ? AND NFE_FILIAL = ? AND NFE_LANCAMENTO = ?'))
                        try:
                            cur.execute(
                                f"UPDATE {tabela} SET {', '.join(sets)} WHERE {chaves}",
                                params + [emp_r, fil_r, num_r])
                            corrigidas += 1
                            log.append(f"✅ {rot} registro {num_r}: "
                                       + "; ".join(mudou))
                        except Exception as e:
                            erros += 1
                            log.append(f"❌ {rot}: {e}")
                    if (idx + 1) % LOTE_COMMIT == 0:
                        try:
                            fb.conn.commit()
                            cur = fb.conn.cursor()
                        except Exception:
                            pass
                fb.conn.commit()
        except Exception as e:
            msg = str(e)
            self._ui(lambda: messagebox.showerror(
                "Erro", f"Falha ao corrigir a situação das notas:\n{msg}"))
            self._ui(self._pos_situacao)
            return

        resumo = (f"{corrigidas} nota(s) corrigida(s), {iguais} já estava(m) certa(s), "
                  f"{nao_achou} não localizada(s) pela chave, {erros} com erro.")
        log.insert(1, f"RESUMO: {resumo}")
        self._ui(lambda: messagebox.showinfo("Concluído", resumo))
        self._ui(lambda: self._oferecer_log(log, "LOG_SITUACAO_NOTAS.txt"))
        self._ui(self._pos_situacao)

    def _pos_situacao(self):
        self.btn_analisar.config(state=tk.NORMAL)
        self.btn_situacao.config(state=tk.NORMAL)
        self.progresso['value'] = 100
        self.lbl_status.config(text="Situação conferida. Clique em Analisar para reconferir.")

    # ---- helpers do motor
    def _nat_para(self, dados, tipo, cfop):
        """Variação de natureza que a FASE 2 escolheu para este CFOP.

        Não reescolhe nada aqui. O `for cod in nats: if cod.startswith(cfop)`
        que estava neste lugar pegava a primeira variação que aparecesse na
        ordem do dicionário — com 510101 (fluxo=S) e 510102 (fluxo=N) no ERP,
        uma importação SEM financeiro caía na 510101. A nota entrava amarrada a
        uma natureza que gera financeiro, o ERP ficava esperando parcelas que
        ninguém gravou e o DANFE não imprimia.

        Nota só chega à gravação com as três fases sem ERRO, então todo CFOP
        dela tem escolha aqui. Devolver None é bug, não caso normal.
        """
        return (dados.get('nat_escolhida') or {}).get((tipo, cfop))

    def _valores_parcelas(self, n, total_erp, log):
        """Valores das parcelas fechando EXATAMENTE no total que o ERP calculou.

        O ERP se recusa a imprimir o DANFE quando a soma das parcelas não bate
        com NFS_VALOR_TOTAL_NOTA — e esse total não é o que eu mando, é o que o
        trigger TR_NF_SAIDA_TOTAL recalcula (produto + IPI + ST + frete + seguro
        + despesas − desconto). As duplicatas do XML somam o vNF da DANFE, que
        difere desse total quando há ICMS desonerado. A diferença vai para a
        ÚLTIMA parcela e fica registrada no log — uma nota que não imprime é
        pior que uma parcela com centavos deslocados, mas isso não pode
        acontecer calado.
        """
        valores = [round(float(p.get('v_dup') or 0.0), 2) for p in n['parcelas']]
        alvo = round(float(total_erp or 0.0), 2)
        dif = round(alvo - round(sum(valores), 2), 2)
        if dif and valores:
            valores[-1] = round(valores[-1] + dif, 2)
            aviso = "arredondamento" if abs(dif) <= 0.05 else "ATENÇÃO: diferença grande"
            log.append(f"   ⚠ NF {n['nro_nf']}: parcelas somavam "
                       f"{self._brl(alvo - dif)} e o total da nota no ERP é "
                       f"{self._brl(alvo)} — {self._brl(dif)} somado à última "
                       f"parcela para o DANFE poder ser impresso ({aviso})")
        return valores

    def _prod_para(self, dados, c_prod):
        info, _campo, ambiguos = self._resolver_produto(c_prod, dados['indices_produto'], 'auto')
        # O desempate feito na aba 3 tem a palavra final — é a única informação que
        # o resolvedor não tem como deduzir (dois produtos ativos com o mesmo
        # código). Mas só vale entre os que ainda estão em conflito: escolha velha
        # (produto apagado, banco trocado) não pode virar um NFP_PRODUTO que não
        # existe. Fora daí a linha volta a AMBÍGUO na fase 3 e nada é gravado.
        escolhido = self._prod_escolhido.get(str(c_prod or '').strip())
        if escolhido and ambiguos and escolhido in ambiguos:
            return int(escolhido)
        return int(info['codigo']) if info else None

    # ------------------------------------------- SITUAÇÃO DO DOCUMENTO FISCAL
    @staticmethod
    def _sit_documento(nota):
        """Código do NFS_SITD_CODIGO / NFE_SITD_CODIGO desta nota.

        A leitura da pasta já decidiu (`utils.nfe_completa.situacao_documento`):
        aqui é só o valor que vai para a coluna, com o regular como piso para
        nunca gravar NULL — a coluna tem FK para TABELA_SIT_DOCUM_FISCAL e a
        escrituração usa esse código.
        """
        return str(nota.get('sit_documento') or SITD_REGULAR)[:2]

    @staticmethod
    def _sem_valor_fiscal(nota):
        """Nota cancelada ou denegada: entra na escrituração, não no financeiro.

        Ela precisa existir no ERP (o SPED cobra o documento com a situação 02 /
        04), mas gerar título e parcela de uma nota que não vale seria inventar
        recebimento — o cliente teria de sair caçando título fantasma depois.
        """
        return str(nota.get('sit_documento') or '') in (SITD_CANCELADO, SITD_DENEGADA)

    @classmethod
    def _cancelamento(cls, nota):
        """(data, motivo) do cancelamento — o que o ERP realmente lê.

        Gravar só o NFS_SITD_CODIGO = '02' não faz a nota aparecer como cancelada
        no ERP: a tela de notas, o livro fiscal (PROC_LIVRO_SAIDA), o SPED
        (PROC_COFIS_431/435) e todos os painéis testam `NFS_DATA_CANCELA IS NULL`.
        Sem a data, a nota cancelada continua contando como venda.

        A data vem do evento de cancelamento (dhRegEvento). Quando o XML do evento
        não traz carimbo, cai na emissão da nota — data errada por dias é ruim, mas
        nota cancelada contando como venda é pior. Denegada NÃO entra aqui: ela não
        foi cancelada, e o ERP tem situação própria (04) para ela.
        """
        if cls._sit_documento(nota) != SITD_CANCELADO:
            return None, None
        canc = nota.get('cancelamento') or {}
        data = canc.get('data') or nota.get('data_emissao')
        motivo = (canc.get('motivo') or '').strip() or 'Cancelamento homologado na SEFAZ'
        prot = (canc.get('protocolo') or '').strip()
        if prot:
            motivo = f"{motivo} (protocolo do evento {prot})"
        return data, motivo[:400]

    def _obs_chunks(self, texto):
        t = (texto or '').strip()
        return [t[i:i + TAM_OBS] for i in range(0, min(len(t), TAM_OBS * QTDE_OBS), TAM_OBS)]

    # ---- centro de custo e conta contábil (opcionais, escolhidos na tela)
    def _cc_nota_saida(self, cur, emp, fil, num, valor, emp_cad=None, fil_cad=None):
        cc = getattr(self, '_cc_padrao', None)
        if not cc:
            return
        # NFCC_EMPRESA/FILIAL amarra na nota; NFCC_CC_* aponta para TABELA_CC
        empc = emp if emp_cad is None else emp_cad
        filc = fil if fil_cad is None else fil_cad
        cur.execute("""
            INSERT INTO TABELA_NF_SAIDA_CC (
                NFCC_EMPRESA, NFCC_FILIAL, NFCC_NUMERO, NFCC_LANCAMENTO,
                NFCC_CC_EMPRESA, NFCC_CC_FILIAL, NFCC_CC,
                NFCC_PORCENTAGEM, NFCC_VALOR
            ) VALUES (?,?,?,1, ?,?,?, 100, ?)
        """, [emp, fil, num, empc, filc, cc, float(valor or 0.0)])

    def _cc_nota_entrada(self, cur, emp, fil, lan, forn, valor,
                         emp_cad=None, fil_cad=None):
        cc = getattr(self, '_cc_padrao', None)
        if not cc:
            return
        # NFCC_FORNECEDOR_* e NFCC_CC_* são cadastros; NFCC_EMPRESA/FILIAL é a nota
        empc = emp if emp_cad is None else emp_cad
        filc = fil if fil_cad is None else fil_cad
        cur.execute("""
            INSERT INTO TABELA_NF_ENTRADA_CC (
                NFCC_EMPRESA, NFCC_FILIAL, NFCC_LANCAMENTO,
                NFCC_FORNECEDOR_EMPRESA, NFCC_FORNECEDOR_FILIAL, NFCC_FORNECEDOR,
                NFCC_CODIGO, NFCC_CC_EMPRESA, NFCC_CC_FILIAL, NFCC_CODIGO_CC,
                NFCC_PORCENTAGEM, NFCC_VALOR, NFCC_USUARIO_INCL
            ) VALUES (?,?,?, ?,?,?, 1, ?,?,?, 100, ?, ?)
        """, [emp, fil, lan, empc, filc, forn, empc, filc, cc,
              float(valor or 0.0), USUARIO_PADRAO])

    def _rateio_titulo_rec(self, cur, emp, fil, cod, serie, cli, emissao, valor,
                           emp_cad=None, fil_cad=None):
        """Centro de custo e conta contábil do título no Receber."""
        rateio_contabil.rateio_receber(
            cur, emp, fil, cod, serie, cli, emissao, valor,
            cc=getattr(self, '_cc_padrao', None),
            conta=getattr(self, '_conta_padrao', None),
            exercicio=getattr(self, '_exercicio', None),
            reduzidos=getattr(self, '_conta_reduzido', {}),
            emp_cad=emp_cad, fil_cad=fil_cad)

    def _rateio_titulo_pagar(self, cur, emp, fil, cod, serie, forn, emissao, valor,
                             emp_cad=None, fil_cad=None):
        """Centro de custo e conta contábil do título no Pagar."""
        rateio_contabil.rateio_pagar(
            cur, emp, fil, cod, serie, forn, emissao, valor,
            cc=getattr(self, '_cc_padrao', None),
            conta=getattr(self, '_conta_padrao', None),
            exercicio=getattr(self, '_exercicio', None),
            reduzidos=getattr(self, '_conta_reduzido', {}),
            emp_cad=emp_cad, fil_cad=fil_cad)

    def _qtde_volume(self, qvol):
        """NFS_QTDE_VOLUME é VARCHAR(10): gravar um float viraria o texto '2.0' e
        a emissão da DANFE recusa ("O valor 2.0 não é válido"). O ERP grava
        inteiro puro ('1', '556') ou vazio."""
        try:
            n = int(round(float(qvol or 0)))
        except (TypeError, ValueError):
            return ''
        return str(n) if n > 0 else ''

    def _gravar_saida(self, cur, n, f, emp, fil, dados, gerar_fin, ult_grav, log):
        # (emp, fil) é a filial DA NOTA; (empc, filc) é a dos CADASTROS. Cada
        # coluna vai no par que a FK dela aponta — conferido em RDB$REF_CONSTRAINTS:
        #   NFS_EMPRESA/FILIAL -> TABELA_FILIAL ................. nota
        #   NFS_CLIENTE_*, NFS_CIDADE_*, NFS_NAT_OPERACAO_*,
        #   NFS_LC_*, NFS_VENDEDOR_* ............................ cadastros
        # Só NFP_ESTOQUE_* não tem FK e fica na filial da nota: é o lugar do
        # movimento, não um cadastro (e esta rotina não movimenta estoque).
        empc, filc = dados.get('emp_cad', emp), dados.get('fil_cad', fil)
        cli = f['contraparte_cod']
        erp = dados['clientes'].get((n.get('contraparte') or {}).get('documento', ''), {})
        cur.execute("SELECT COALESCE(MAX(NFS_NUMERO), 0) + 1 FROM TABELA_NF_SAIDA "
                    "WHERE NFS_EMPRESA = ? AND NFS_FILIAL = ?", [emp, fil])
        num = int(cur.fetchone()[0])
        t = n['totais']
        tr = n['transporte']
        cfop_primeiro = (n['itens'][0].get('cfop') if n['itens'] else '') or ''
        nat = self._nat_para(dados, 'S', str(cfop_primeiro).strip())
        if not nat:
            raise ValueError(
                f"CFOP {cfop_primeiro} sem variação de natureza escolhida na análise — "
                f"reanalise antes de importar")
        # Nota cancelada ou denegada não gera financeiro, mesmo com a opção
        # marcada: ela existe para a escrituração, e criar título de nota que não
        # vale é inventar recebimento (ver _sem_valor_fiscal).
        if self._sem_valor_fiscal(n) and gerar_fin:
            gerar_fin = False
            log.append(f"   ⚠ nota {n['nro_nf']} com situação "
                       f"{self._sit_documento(n)} — importada sem financeiro")
        # Sem gerar financeiro não existe parcela nenhuma. Dizer no cabeçalho que
        # a nota tem N parcelas e não gravar nenhuma é o que fazia o ERP recusar o
        # DANFE ("valor das parcelas diferente do valor total da nota").
        qtde_parc = len(n['parcelas']) if gerar_fin else 0
        # Local de cobrança e vendedor não vêm no XML. O local é o escolhido na
        # tela; o vendedor sai do cadastro do cliente (CF_REPRESENTANTE) e cai no
        # padrão da tela quando o cliente não tem um vinculado.
        lc = getattr(self, '_lc_padrao', None)
        vend = erp.get('cf_representante') or getattr(self, '_vend_padrao', None)
        data_canc, motivo_canc = self._cancelamento(n)

        cur.execute("""
            INSERT INTO TABELA_NF_SAIDA (
                NFS_EMPRESA, NFS_FILIAL, NFS_NUMERO, NFS_NRO_NF, NFS_SERIE,
                NFS_CLIENTE_EMPRESA, NFS_CLIENTE_FILIAL, NFS_CLIENTE,
                NFS_RAZAO, NFS_ENDERECO, NFS_NRO_END, NFS_BAIRRO, NFS_CEP,
                NFS_FONE, NFS_CNPJ, NFS_INSC_EST,
                NFS_CIDADE_EMPRESA, NFS_CIDADE_FILIAL, NFS_CIDADE,
                NFS_NAT_OPERACAO_EMPRESA, NFS_NAT_OPERACAO_FILIAL, NFS_NAT_OPERACAO,
                NFS_NAT_OPERACAO_DESC,
                NFS_DATA_EMISSAO, NFS_DATA_SAIDA, NFS_HORA_EMISSAO,
                NFS_VALOR_TOTAL_PRODUTO, NFS_VALOR_TOTAL_NOTA, NFS_VALOR_DESCONTO,
                NFS_FRETE, NFS_SEGURO, NFS_OUTRAS_DESPESAS1, NFS_VALOR_IPI, NFS_SUBST_TRIB,
                NFS_PESO_BRUTO, NFS_PESO_LIQUIDO, NFS_QTDE_VOLUME, NFS_TIPO_FRETE,
                NFS_TRANS_DESCRICAO, NFS_TRANS_CGC, NFS_TRANS_IE, NFS_VEICULO, NFS_VEICULO_UF,
                NFS_QTDE_PARCELAS, NFS_EMITIDO, NFS_ORIGEM, NFS_CHAVE_DANFE,
                NFS_TIPO_EMISSAO_NFE, NFS_DFIS_CODIGO, NFS_DADOS_ADICIONAIS,
                NFS_PROTOCOLO_NFE, NFS_AMBIENTE_NFE, NFS_XML_NFE, NFS_USUARIO_GRAVACAO,
                NFS_LC_EMPRESA, NFS_LC_FILIAL, NFS_LOCAL_COBRANCA,
                NFS_VENDEDOR_EMPRESA, NFS_VENDEDOR_FILIAL, NFS_VENDEDOR,
                NFS_TRANS_EMPRESA, NFS_TRANS_FILIAL,
                NFS_SITD_CODIGO,
                NFS_DATA_CANCELA, NFS_MOTIVO_CANCELA, NFS_USUARIO_CANCELAMENTO,
                NFS_DIAS_INTERVALO, NFS_VALOR_TROCO
            ) VALUES (?,?,?,?,?,
                      ?,?,?,
                      ?,?,?,?,?,
                      ?,?,?,
                      ?,?,?,
                      ?,?,?,
                      ?,
                      ?,?,?,
                      ?,?,?,
                      ?,?,?,?,?,
                      ?,?,?,?,
                      ?,?,?,?,?,
                      ?,'S',?,?,
                      '1',?,?,
                      ?,1,'F',?,
                      ?,?,?,
                      ?,?,?,
                      ?,?,
                      ?,
                      ?,?,?,
                      0,0)
        """, [
            emp, fil, num, n['nro_nf'], str(n['serie'])[:3],
            empc, filc, cli,
            (erp.get('cf_razao') or (n['contraparte'].get('razao') or ''))[:50],
            (erp.get('cf_endereco') or n['contraparte'].get('endereco') or '')[:50],
            str(erp.get('cf_nro_end') or n['contraparte'].get('nro_end') or '')[:10],
            (erp.get('cf_bairro') or n['contraparte'].get('bairro') or '')[:50],
            str(erp.get('cf_cep') or n['contraparte'].get('cep') or '')[:9],
            str(erp.get('cf_fone1') or n['contraparte'].get('fone1') or '')[:15],
            (n['contraparte'].get('documento_formatado') or '')[:18],
            str(erp.get('cf_rg_ie') or n['contraparte'].get('ie') or '')[:20],
            erp.get('cf_cidade_empresa') or empc, erp.get('cf_cidade_filial') or filc,
            erp.get('cf_cidade'),
            empc, filc, nat, (n.get('nat_op') or '')[:50],
            n['data_emissao'], n['data_saida'] or n['data_emissao'], n['hora_emissao'],
            # TR_NF_SAIDA_PRODUTO_NF acumula estes campos a cada item inserido:
            # entram zerados e são acertados no UPDATE após os itens, senão dobram.
            0.0, 0.0, 0.0,
            t.get('vFrete', 0.0), t.get('vSeg', 0.0), t.get('vOutro', 0.0),
            0.0, 0.0,
            0.0, 0.0, self._qtde_volume(t.get('qVol')),
            tr.get('mod_frete', 9),
            (tr['transportadora'].get('razao') or '')[:50],
            (tr['transportadora'].get('documento_formatado') or '')[:18],
            (tr['transportadora'].get('ie') or '')[:20],
            (tr.get('placa') or '')[:10], (tr.get('placa_uf') or '')[:2],
            qtde_parc, ORIGEM_IMPORTACAO, n['chave'][:44],
            str(n.get('modelo') or '55')[:2], (n.get('inf_cpl') or '')[:5000],
            (n.get('protocolo') or '')[:20], USUARIO_PADRAO,
            empc, filc, lc,            # NFS_LC_* -> TABELA_LOCAL_COBRANCA
            empc, filc, vend,          # NFS_VENDEDOR_* -> TABELA_VENDEDOR
            empc, filc,                # NFS_TRANS_* (transportadora é cadastro)
            # situação do documento fiscal (FK -> TABELA_SIT_DOCUM_FISCAL):
            # cancelada entra como 02, denegada 04, complementar 06. Ficava NULL.
            self._sit_documento(n),
            # e a data/justificativa do cancelamento, que é por onde o ERP
            # reconhece a nota como cancelada (ver _cancelamento). NULL nas outras.
            data_canc, motivo_canc,
            USUARIO_PADRAO if data_canc else None,
        ])

        # As colunas de ZERO_NFP entram com 0 em vez de NULL — ver o comentário
        # da constante. São só zeros, não consomem parâmetro.
        cols_zero = "".join(f", {c}" for c in ZERO_NFP)
        vals_zero = ", 0" * len(ZERO_NFP)
        for item in n['itens']:
            prod = self._prod_para(dados, str(item.get('c_prod') or ''))
            nat_it = self._nat_para(dados, 'S', str(item.get('cfop') or '').strip()) or nat
            cur.execute(f"""
                INSERT INTO TABELA_NF_SAIDA_PRODUTO (
                    NFP_EMPRESA, NFP_FILIAL, NFP_NUMERO, NFP_LANCAMENTO,
                    NFP_PRODUTO_EMPRESA, NFP_PRODUTO_FILIAL, NFP_PRODUTO,
                    NFP_PRODUTO_DESCRICAO, NFP_UNIDADE_PRODUTO, NFP_DATA_EMISSAO,
                    NFP_QTDE_PRODUTO, NFP_QTDE_REAL, NFP_PRECO_UNITARIO, NFP_PRECO_LISTA,
                    NFP_TOTAL_PRODUTO, NFP_DESCONTO, NFP_RATEIO_FRETE, NFP_RATEIO_SEGURO,
                    NFP_NAT_OP_EMP, NFP_NAT_OP_FIL, NFP_NAT_OP,
                    NFP_SIT_TRIBUTARIA, NFP_ICMS, NFP_REDUCAO, NFP_BC_ICMS, NFP_VALOR_ICMS,
                    NFP_BASE_SUBST_TRIB, NFP_VALOR_ICMS_SUBST_TRIB,
                    NFP_IPI, NFP_VALOR_IPI, NFP_BC_IPI,
                    NFP_BC_PIS, NFP_VALOR_PIS, NFP_BC_COFINS, NFP_VALOR_COFINS,
                    NFP_CTS_PIS, NFP_CTS_COFINS, NFP_CTS_IPI,
                    NFP_CLASS_FISCAL, NFP_CBENEF, NFP_LE_EMP, NFP_LE_FIL, NFP_LOC_ESTOQUE,
                    NFP_ESTOQUE_EMPRESA, NFP_ESTOQUE_FILIAL,
                    NFP_VENDEDOR_EMPRESA, NFP_VENDEDOR_FILIAL, NFP_VENDEDOR,
                    NFP_FATOR, NFP_OBS_CFOP{cols_zero}
                ) VALUES (?,?,?,?, ?,?,?, ?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?,
                          ?,?,?,?,?, ?,?, ?,?,?, ?,?,?,?, ?,?,?,
                          ?,?,?,?,1, ?,?, ?,?,?, 1, '*'{vals_zero})
            """, [
                emp, fil, num, item['n_item'],
                empc, filc, prod,          # NFP_PRODUTO_* -> TABELA_PRODUTO
                (item.get('x_prod') or '')[:60], (item.get('u_com') or 'UN')[:2],
                n['data_emissao'],
                item.get('q_com', 0.0), item.get('q_com', 0.0),
                item.get('v_un_com', 0.0), item.get('v_un_com', 0.0),
                item.get('v_prod', 0.0), item.get('v_desc', 0.0),
                item.get('v_frete', 0.0), item.get('v_seg', 0.0),
                empc, filc, nat_it,        # NFP_NAT_OP_* -> TABELA_NAT_OPERACAO_SAIDA
                str(item.get('icms_cst') or '')[:3],
                item.get('p_icms', 0.0), item.get('p_red_bc', 0.0),
                item.get('v_bc_icms', 0.0), item.get('v_icms', 0.0),
                item.get('v_bc_st', 0.0), item.get('v_st', 0.0),
                item.get('p_ipi', 0.0), item.get('v_ipi', 0.0), item.get('v_bc_ipi', 0.0),
                item.get('v_bc_pis', 0.0), item.get('v_pis', 0.0),
                item.get('v_bc_cofins', 0.0), item.get('v_cofins', 0.0),
                str(item.get('pis_cst') or '')[:3],
                str(item.get('cofins_cst') or '')[:3],
                str(item.get('ipi_cst') or '99')[:3],
                (item.get('ncm') or '')[:14], (item.get('c_benef') or '')[:10],
                empc, filc,                # NFP_LE_* -> TABELA_LOCAL_ESTOQUE
                emp, fil,                  # NFP_ESTOQUE_* (sem FK): filial do movimento
                empc, filc, vend,          # NFP_VENDEDOR_* -> TABELA_VENDEDOR
            ])

        # Os itens já dispararam o trigger que acumula os totais; aqui os campos
        # do cabeçalho recebem o que está no XML.
        # ATENÇÃO: NFS_VALOR_TOTAL_NOTA é DERIVADA — TR_NF_SAIDA_TOTAL (BEFORE
        # INSERT OR UPDATE) recalcula sempre, como produto + IPI + ST + frete +
        # seguro + despesas - desconto. O valor mandado aqui é descartado; ele
        # vai junto só para o caso de o trigger ser desativado no futuro.
        cur.execute("""
            UPDATE TABELA_NF_SAIDA SET
                NFS_VALOR_TOTAL_PRODUTO = ?, NFS_VALOR_TOTAL_NOTA = ?,
                NFS_VALOR_DESCONTO = ?, NFS_VALOR_IPI = ?, NFS_SUBST_TRIB = ?,
                NFS_PESO_BRUTO = ?, NFS_PESO_LIQUIDO = ?
            WHERE NFS_EMPRESA = ? AND NFS_FILIAL = ? AND NFS_NUMERO = ?
        """, [t.get('vProd', 0.0), t.get('vNF', 0.0), t.get('vDesc', 0.0),
              t.get('vIPI', 0.0), t.get('vST', 0.0),
              t.get('pesoB', 0.0), t.get('pesoL', 0.0), emp, fil, num])

        # Confere o total que o ERP calculou contra o vNF do XML. A fórmula do
        # trigger não tem termo para ICMS desonerado (CST 40/41 com motivo), então
        # nota desonerada fica com o total do ERP acima do total da DANFE. Não é
        # corrigível por aqui — o ERP não tem campo de desoneração de ICMS na
        # saída — e o financeiro não é afetado (as parcelas vêm das duplicatas).
        cur.execute("SELECT NFS_VALOR_TOTAL_NOTA FROM TABELA_NF_SAIDA "
                    "WHERE NFS_EMPRESA = ? AND NFS_FILIAL = ? AND NFS_NUMERO = ?",
                    [emp, fil, num])
        total_erp = float(cur.fetchone()[0] or 0.0)
        if abs(total_erp - float(t.get('vNF') or 0.0)) > 0.05:
            deson = float(t.get('vICMSDeson') or 0.0)
            causa = (f"ICMS desonerado de {self._brl(deson)}" if deson > 0.005
                     else "diferença na fórmula do total")
            log.append(f"   ⚠ NF {n['nro_nf']}: total no ERP {self._brl(total_erp)} != "
                       f"vNF da DANFE {self._brl(t.get('vNF', 0.0))} ({causa}) — "
                       f"itens, impostos e financeiro estão corretos")

        cur.execute("""
            INSERT INTO TABELA_NF_SAIDA_ICMS (
                NFICMS_EMPRESA, NFICMS_FILIAL, NFICMS_NUMERO, NFICMS_FAIXA,
                NFICMS_ALIQUOTA_BASE, NFICMS_BASE_ICMS, NFICMS_VALOR_OPERACAO,
                NFICMS_VALOR_ICMS, NFICMS_BASE_IPI, NFICMS_VALOR_IPI,
                NFICMS_BASE_SUBS_TRIB, NFICMS_VALOR_SUBS_TRIB, NFICMS_ALIQUOTA_REDUCAO,
                NFICMS_NAT_OP_EMP, NFICMS_NAT_OP_FIL, NFICMS_NAT_OP
            ) VALUES (?,?,?,1, 0,?,?,?, 0,?, ?,?, 0, ?,?,?)
        """, [emp, fil, num, t.get('vBC', 0.0), t.get('vNF', 0.0), t.get('vICMS', 0.0),
              t.get('vIPI', 0.0), t.get('vBCST', 0.0), t.get('vST', 0.0),
              empc, filc, nat])   # NFICMS_NAT_OP_* -> TABELA_NAT_OPERACAO_SAIDA

        chunks = self._obs_chunks(n.get('inf_cpl'))
        if chunks:
            cols = ", ".join(f"NFOBS_OBS{i + 1}" for i in range(len(chunks)))
            marks = ", ".join("?" for _ in chunks)
            cur.execute(
                f"INSERT INTO TABELA_NF_SAIDA_OBS (NFOBS_EMPRESA, NFOBS_FILIAL, "
                f"NFOBS_NUMERO, NFOBS_LANCAMENTO, {cols}) VALUES (?,?,?,1, {marks})",
                [emp, fil, num] + chunks)

        self._cc_nota_saida(cur, emp, fil, num, t.get('vNF', 0.0), empc, filc)

        if gerar_fin and n['parcelas']:
            self._gravar_parcelas_saida(cur, n, num, cli, emp, fil, dados,
                                        ult_grav, log, total_erp)
        log.append(f"✅ NF {n['nro_nf']}/{n['serie']} SAÍDA -> NFS_NUMERO {num}, "
                   f"{len(n['itens'])} item(ns), {self._brl(t.get('vNF', 0.0))}"
                   + (f" — CANCELADA em {self._data_br(data_canc)}" if data_canc else ""))

    def _gravar_parcelas_saida(self, cur, n, num, cli, emp, fil, dados, ult_grav,
                               log, total_erp):
        empc, filc = dados.get('emp_cad', emp), dados.get('fil_cad', fil)
        erp = dados['clientes'].get((n.get('contraparte') or {}).get('documento', ''), {})
        lc = getattr(self, '_lc_padrao', None)
        vend = erp.get('cf_representante') or getattr(self, '_vend_padrao', None)
        valores = self._valores_parcelas(n, total_erp, log)
        for i, (p, val) in enumerate(zip(n['parcelas'], valores), start=1):
            venc = self._data_iso(p.get('d_venc')) or n['data_emissao']
            cur.execute("""
                INSERT INTO TABELA_NF_SAIDA_PARCELA (
                    NFPARC_EMPRESA, NFPARC_FILIAL, NFPARC_NUMERO, NFPARC_PARCELA,
                    NFPARC_QTDE_DIAS, NFPARC_DATA_PARCELA, NFPARC_VALOR_PARCELA,
                    NFPARC_LC_EMPRESA, NFPARC_LC_FILIAL, NFPARC_LOCAL_COBRANCA,
                    NFPARC_TC_EMPRESA, NFPARC_TC_FILIAL
                ) VALUES (?,?,?,?, ?,?,?, ?,?,?, ?,?)
            """, [emp, fil, num, i, int(p.get('dias') or 0), venc,
                  val, empc, filc, lc,   # NFPARC_LC_* -> TABELA_LOCAL_COBRANCA
                  empc, filc])           # NFPARC_TC_* -> TABELA_TIPO_COBRANCA

        cod_tit = str(n['nro_nf']).lstrip('0') or '0'
        serie = str(n['serie']).strip().upper()[:3]
        if (cod_tit, serie, cli) in dados['tit_rec']:
            log.append(f"   ⚠ título {cod_tit}/{serie} já existe no Receber — "
                       f"parcelas da nota gravadas, título NÃO duplicado")
            return
        total = round(sum(valores), 2)
        venc1 = self._data_iso(n['parcelas'][0].get('d_venc')) or n['data_emissao']
        dias1 = int(n['parcelas'][0].get('dias') or 0)
        cur.execute("""
            INSERT INTO TABELA_TITULO_REC (
                TIT_EMPRESA, TIT_FILIAL, TIT_CODIGO, TIT_SERIE,
                TIT_CLIENTE_EMPRESA, TIT_CLIENTE_FILIAL, TIT_CLIENTE,
                TIT_EMISSAO, TIT_DATA, TIT_TL_EMPRESA, TIT_TL_FILIAL, TIT_TIPO_LANCAMENTO,
                TIT_PARCELAS, TIT_VENCIMENTO, TIT_DIAS, TIT_TOTAL_NF, TIT_ORIGEM, TIT_VALOR,
                TIT_MOEDA_EMPRESA, TIT_MOEDA_FILIAL, TIT_VALOR_MOEDA, TIT_QTDE_MOEDA,
                TIT_TOTAL, TIT_TOTAL_CC, TIT_TOTAL_CONTABIL, TIT_TOTAL_PARCELAS,
                TIT_DEVOLUCAO, TIT_SEGMENTO_EMP, TIT_SEGMENTO_FIL, TIT_STATUS,
                TIT_USUARIO, TIT_ULT_GRAVACAO, TIT_NAT_OP_EMPRESA, TIT_NAT_OP_FILIAL,
                TIT_VENDEDOR_EMPRESA, TIT_VENDEDOR_FILIAL, TIT_VENDEDOR
            ) VALUES (?,?,?,?, ?,?,?, ?,?,?,?,2, ?,?,?,?,?,?, ?,?,0,0,
                      ?,?,?,?, 'N',?,?,'N', ?,?,?,?, ?,?,?)
        """, [emp, fil, cod_tit, serie,      # TIT_EMPRESA/FILIAL -> TABELA_FILIAL (nota)
              empc, filc, cli,               # TIT_CLIENTE_* -> TABELA_CLI_FOR
              n['data_emissao'], n['data_emissao'], empc, filc,   # TIT_TL_* (tipo lanç.)
              len(n['parcelas']), venc1, dias1, total, ORIGEM_IMPORTACAO, total,
              empc, filc,                    # TIT_MOEDA_* -> TABELA_MOEDA
              total, total, total, total,
              empc, filc,                    # TIT_SEGMENTO_* -> SEGMENTO_OPERACIONAL
              USUARIO_PADRAO, ult_grav,
              empc, filc,                    # TIT_NAT_OP_* -> NAT_OPERACAO_SAIDA
              empc, filc, vend])             # TIT_VENDEDOR_* -> TABELA_VENDEDOR
        for i, (p, val) in enumerate(zip(n['parcelas'], valores), start=1):
            venc = self._data_iso(p.get('d_venc')) or n['data_emissao']
            cur.execute("""
                INSERT INTO TABELA_TITULO_PARCELA_REC (
                    TPARC_EMPRESA, TPARC_FILIAL, TPARC_CODIGO, TPARC_SERIE, TPARC_PARCELA,
                    TPARC_CLIENTE_EMPRESA, TPARC_CLIENTE_FILIAL, TPARC_CLIENTE,
                    TPARC_EMISSAO, TPARC_DIGITACAO, TPARC_DIAS, TPARC_VENCIMENTO,
                    TPARC_MOEDA_EMPRESA, TPARC_MOEDA_FILIAL, TPARC_VALOR, TPARC_ABATIMENTO,
                    TPARC_VALOR_PG, TPARC_PG, TPARC_DESCONTO, TPARC_JUROS, TPARC_CORRECAO,
                    TPARC_DESPESA_BANCO, TPARC_DESPESA_CARTORIO, TPARC_ORIGEM,
                    TPARC_DUPLICATA, TPARC_NEGATIVADO, TPARC_JUROS_MORA,
                    TPARC_ULT_GRAVACAO,
                    TPARC_LC_EMPRESA, TPARC_LC_FILIAL, TPARC_LOCAL_COBRANCA,
                    TPARC_VENDEDOR_EMPRESA, TPARC_VENDEDOR_FILIAL, TPARC_VENDEDOR
                ) VALUES (?,?,?,?,?, ?,?,?, ?,?,?,?, ?,?,?,0, 0,'N',0,0,0, 0,0,?, 'S','N',0, ?,
                          ?,?,?, ?,?,?)
            """, [emp, fil, cod_tit, serie, i,
                  empc, filc, cli,           # TPARC_CLIENTE_* -> TABELA_CLI_FOR
                  n['data_emissao'], n['data_emissao'], int(p.get('dias') or 0), venc,
                  empc, filc, val, ORIGEM_IMPORTACAO,   # TPARC_MOEDA_*
                  ult_grav,
                  empc, filc, lc,            # TPARC_LC_* -> TABELA_LOCAL_COBRANCA
                  empc, filc, vend])         # TPARC_VENDEDOR_* -> TABELA_VENDEDOR
        self._rateio_titulo_rec(cur, emp, fil, cod_tit, serie, cli,
                                n['data_emissao'], total, empc, filc)
        log.append(f"   💰 título {cod_tit}/{serie} no Receber, "
                   f"{len(n['parcelas'])} parcela(s), {self._brl(total)}")

    def _gravar_entrada(self, cur, n, f, emp, fil, dados, gerar_fin, ult_grav, log):
        # mesma separação da saída: NFE_EMPRESA/FILIAL -> TABELA_FILIAL (a nota);
        # NFE_FORNECEDOR_*, NFE_NAT_OPERACAO_*, NFE_CID_*, NFE_LOC_COBR_*,
        # NFE_COBRADOR_*, NFE_SEGMENTO_*, NFE_TF_* -> cadastros.
        empc, filc = dados.get('emp_cad', emp), dados.get('fil_cad', fil)
        forn = f['contraparte_cod']
        erp = dados['clientes'].get((n.get('contraparte') or {}).get('documento', ''), {})
        cur.execute("SELECT COALESCE(MAX(NFE_LANCAMENTO), 0) + 1 FROM TABELA_NF_ENTRADA "
                    "WHERE NFE_EMPRESA = ? AND NFE_FILIAL = ?", [emp, fil])
        lan = int(cur.fetchone()[0])
        t = n['totais']
        cfop_primeiro = (n['itens'][0].get('cfop') if n['itens'] else '') or ''
        nat = self._nat_para(dados, 'E', str(cfop_primeiro).strip())
        if not nat:
            raise ValueError(
                f"CFOP {cfop_primeiro} sem variação de natureza escolhida na análise — "
                f"reanalise antes de importar")
        # cancelada/denegada não gera financeiro nem aqui (ver _sem_valor_fiscal)
        if self._sem_valor_fiscal(n) and gerar_fin:
            gerar_fin = False
            log.append(f"   ⚠ nota {n['nro_nf']} com situação "
                       f"{self._sit_documento(n)} — importada sem financeiro")
        # mesma regra da saída: sem financeiro, o cabeçalho declara 0 parcelas
        qtde_parc = len(n['parcelas']) if gerar_fin else 0
        lc = getattr(self, '_lc_padrao', None)
        vend = erp.get('cf_representante') or getattr(self, '_vend_padrao', None)
        data_canc, _motivo_canc = self._cancelamento(n)

        cur.execute("""
            INSERT INTO TABELA_NF_ENTRADA (
                NFE_EMPRESA, NFE_FILIAL, NFE_LANCAMENTO,
                NFE_FORNECEDOR_EMPRESA, NFE_FORNECEDOR_FILIAL, NFE_FORNECEDOR,
                NFE_NRO_NF, NFE_NFE_SERIE,
                NFE_NAT_OPERACAO_EMPRESA, NFE_NAT_OPERACAO_FILIAL, NFE_NAT_OPERACAO,
                NFE_DATA_EMISSAO, NFE_DATA_ENTRADA, NFE_DATA_DIGITACAO, NFE_DATA_FATURA,
                NFE_DESCONTO_TOTAL, NFE_FRETE, NFE_SEGURO, NFE_DESP_ACESS_1,
                NFE_TOTAL_NOTA, NFE_VALOR_ICMS, NFE_VALOR_IPI,
                NFE_PESO_BRUTO, NFE_PESO_LIQUIDO,
                NFE_SERIE_EMPRESA, NFE_SERIE_FILIAL,
                NFE_QTDE_PARCELAS, NFE_TIPO_EMISSAO, NFE_TIPO_EMISSAO_NFE,
                NFE_CHAVE_DANFE, NFE_HORA_EMISSAO,
                NFE_EMITIDO, NFE_SITD_CODIGO, NFE_XML_NFE, NFE_DFIS_CODIGO,
                NFE_AVISTA, NFE_TIPO_ICMS, NFE_FLAG_DESC, NFE_RATEIO_TIPO,
                NFE_FRETE_CONTA, NFE_DIAS_INTERVALO, NFE_VALOR_ISS,
                NFE_ENDERECO, NFE_BAIRRO, NFE_CEP,
                NFE_CID_EMPRESA, NFE_CID_FILIAL, NFE_CIDADE,
                NFE_DADOS_ADICIONAIS, NFE_PROTOCOLO_NFE,
                NFE_VENDEDOR_EMPRESA, NFE_VENDEDOR_FILIAL, NFE_VENDEDOR,
                NFE_LOC_COBR_EMP, NFE_LOC_COBR_FIL, NFE_LOC_COBR,
                NFE_COBRADOR_EMPRESA, NFE_COBRADOR_FILIAL,
                NFE_SEGMENTO_EMP, NFE_SEGMENTO_FIL, NFE_TF_EMPRESA, NFE_TF_FILIAL,
                NFE_USUARIO_INCL, NFE_USUARIO_ALT, NFE_ULT_GRAVACAO,
                NFE_DATA_CANCELAMENTO
            ) VALUES (?,?,?, ?,?,?, ?,?, ?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?, ?,?, ?,?,
                      ?, 'P','1', ?,?,
                      'S',?,'F',?,
                      'N','1','T','T',
                      '0',0,0,
                      ?,?,?,
                      ?,?,?,
                      ?,?,
                      ?,?,?,
                      ?,?,?,
                      ?,?,
                      ?,?,?,?,
                      ?,?,?,
                      ?)
        """, [
            emp, fil, lan,
            empc, filc, forn,          # NFE_FORNECEDOR_* -> TABELA_CLI_FOR
            n['nro_nf'], str(n['serie'])[:3],
            empc, filc, nat,           # NFE_NAT_OPERACAO_* -> NAT_OPERACAO_ENTRADA
            n['data_emissao'], n['data_emissao'], datetime.date.today(), n['data_emissao'],
            t.get('vDesc', 0.0), t.get('vFrete', 0.0), t.get('vSeg', 0.0), t.get('vOutro', 0.0),
            # TR_NF_ENTRADA_PRODUTO_NF acumula total/peso/IPI a cada item:
            # zerados aqui, acertados no UPDATE após os itens.
            0.0, t.get('vICMS', 0.0), 0.0,
            0.0, 0.0,
            emp, fil, qtde_parc, n['chave'][:44], n['hora_emissao'],
            # NFE_EMITIDO = 'S' porque só importamos emissão própria: no ERP
            # 'S' acompanha NFE_TIPO_EMISSAO='P' e 'N' acompanha 'T'. Sem isso a
            # nota aparece como INCOMPLETA na tela de notas de entrada.
            # A situação era '00' fixa: nota cancelada entrava como regular.
            self._sit_documento(n),
            str(n.get('modelo') or '55')[:2],
            (erp.get('cf_endereco') or n['contraparte'].get('endereco') or '')[:50],
            (erp.get('cf_bairro') or n['contraparte'].get('bairro') or '')[:20],
            str(erp.get('cf_cep') or n['contraparte'].get('cep') or '')[:15],
            erp.get('cf_cidade_empresa') or empc, erp.get('cf_cidade_filial') or filc,
            erp.get('cf_cidade'),      # NFE_CID_* -> TABELA_CIDADE
            (n.get('inf_cpl') or '')[:1000], (n.get('protocolo') or '')[:20],
            empc, filc, vend,          # NFE_VENDEDOR_*
            empc, filc, lc,            # NFE_LOC_COBR_* -> TABELA_LOCAL_COBRANCA
            empc, filc,                # NFE_COBRADOR_* -> TABELA_CLI_FOR
            empc, filc, empc, filc,    # NFE_SEGMENTO_* e NFE_TF_* (TIPO_FLUXO)
            USUARIO_PADRAO, USUARIO_PADRAO, ult_grav,
            # data do cancelamento: é o que o ERP testa (NFE_DATA_CANCELAMENTO IS
            # NULL) nos livros, no SPED e nos painéis. A entrada não tem campo de
            # justificativa como a saída.
            data_canc,
        ])

        cols_zero = "".join(f", {c}" for c in ZERO_NFEP)
        vals_zero = ", 0" * len(ZERO_NFEP)
        for item in n['itens']:
            prod = self._prod_para(dados, str(item.get('c_prod') or ''))
            cur.execute(f"""
                INSERT INTO TABELA_NF_ENTRADA_PRODUTO (
                    NFP_EMPRESA, NFP_FILIAL, NFP_LANCAMENTO_NF,
                    NFP_FORNECEDOR_EMPRESA, NFP_FORNECEDOR_FILIAL, NFP_FORNECEDOR,
                    NFP_LANCAMENTO, NFP_PRODUTO_EMPRESA, NFP_PRODUTO_FILIAL, NFP_PRODUTO,
                    NFP_PRODUTO_DESCRICAO, NFP_UNIDADE_PRODUTO, NFP_DATA_EMISSAO,
                    NFP_QTDE_PRODUTO, NFP_QTDE_REAL, NFP_PRECO_UNITARIO, NFP_TOTAL_PRODUTO,
                    NFP_SIT_TRIBUTARIA, NFP_ICMS, NFP_BC_ICMS, NFP_VALOR_TOTAL_ICMS,
                    NFP_IPI, NFP_VALOR_TOTAL_IPI,
                    NFP_CTS_PIS, NFP_CTS_COFINS,
                    NFP_ESTOQUE_EMPRESA, NFP_ESTOQUE_FILIAL, NFP_FATOR{cols_zero}
                ) VALUES (?,?,?, ?,?,?, ?,?,?,?, ?,?,?, ?,?,?,?, ?,?,?,?, ?,?,
                          ?,?, ?,?, 1{vals_zero})
            """, [
                emp, fil, lan, empc, filc, forn,     # FK -> TABELA_NF_ENTRADA
                item['n_item'], empc, filc, prod,    # NFP_PRODUTO_* -> TABELA_PRODUTO
                (item.get('x_prod') or '')[:60], (item.get('u_com') or 'UN')[:2],
                n['data_emissao'],
                item.get('q_com', 0.0), item.get('q_com', 0.0),
                item.get('v_un_com', 0.0), item.get('v_prod', 0.0),
                str(item.get('icms_cst') or '')[:3], item.get('p_icms', 0.0),
                item.get('v_bc_icms', 0.0), item.get('v_icms', 0.0),
                item.get('p_ipi', 0.0), item.get('v_ipi', 0.0),
                str(item.get('pis_cst') or '')[:3], str(item.get('cofins_cst') or '')[:3],
                emp, fil,          # NFP_ESTOQUE_* (sem FK): filial do movimento
            ])

        cur.execute("""
            UPDATE TABELA_NF_ENTRADA SET
                NFE_TOTAL_NOTA = ?, NFE_VALOR_TOTAL_PRODUTOS = ?, NFE_VALOR_IPI = ?,
                NFE_PESO_BRUTO = ?, NFE_PESO_LIQUIDO = ?
            WHERE NFE_EMPRESA = ? AND NFE_FILIAL = ? AND NFE_LANCAMENTO = ?
              AND NFE_FORNECEDOR_EMPRESA = ? AND NFE_FORNECEDOR_FILIAL = ?
              AND NFE_FORNECEDOR = ?
        """, [t.get('vNF', 0.0), t.get('vProd', 0.0), t.get('vIPI', 0.0),
              t.get('pesoB', 0.0), t.get('pesoL', 0.0),
              emp, fil, lan, empc, filc, forn])

        obs = (n.get('inf_cpl') or '').strip()
        if obs:
            cur.execute("""
                INSERT INTO TABELA_NF_ENTRADA_OBS (
                    NFOBS_EMPRESA, NFOBS_FILIAL, NFOBS_LANCAMENTO,
                    NFOBS_FORNECEDOR_EMPRESA, NFOBS_FORNECEDOR_FILIAL, NFOBS_FORNECEDOR,
                    NFOBS_OBS, NFOBS_USUARIO_INCL
                ) VALUES (?,?,?, ?,?,?, ?,?)
            """, [emp, fil, lan, empc, filc, forn, obs[:200], USUARIO_PADRAO])

        if gerar_fin and n['parcelas']:
            # mesma regra da saída: a soma tem de fechar com o total que o ERP
            # calculou, senão a nota não imprime
            cur.execute("SELECT NFE_TOTAL_NOTA FROM TABELA_NF_ENTRADA "
                        "WHERE NFE_EMPRESA = ? AND NFE_FILIAL = ? AND NFE_LANCAMENTO = ? "
                        "AND NFE_FORNECEDOR_EMPRESA = ? AND NFE_FORNECEDOR_FILIAL = ? "
                        "AND NFE_FORNECEDOR = ?", [emp, fil, lan, empc, filc, forn])
            total_erp = float(cur.fetchone()[0] or 0.0)
            valores = self._valores_parcelas(n, total_erp, log)
            for i, (p, val) in enumerate(zip(n['parcelas'], valores), start=1):
                venc = self._data_iso(p.get('d_venc')) or n['data_emissao']
                cur.execute("""
                    INSERT INTO TABELA_NF_ENTRADA_PARCELA (
                        NFPARC_EMPRESA, NFPARC_FILIAL, NFPARC_LANCAMENTO,
                        NFPARC_FORNECEDOR_EMPRESA, NFPARC_FORNECEDOR_FILIAL, NFPARC_FORNECEDOR,
                        NFPARC_PARCELA, NFPARC_QTDE_DIAS, NFPARC_DATA_PARCELA,
                        NFPARC_VALOR_PARCELA, NFPARC_USUARIO_INCL, NFPARC_ULT_GRAVACAO
                    ) VALUES (?,?,?, ?,?,?, ?,?,?, ?,?,?)
                """, [emp, fil, lan, empc, filc, forn, i, int(p.get('dias') or 0), venc,
                      val, USUARIO_PADRAO, ult_grav])
            self._gravar_titulo_pagar(cur, n, forn, emp, fil, dados, ult_grav, log,
                                      valores)
        self._cc_nota_entrada(cur, emp, fil, lan, forn, t.get('vNF', 0.0), empc, filc)
        log.append(f"✅ NF {n['nro_nf']}/{n['serie']} ENTRADA -> NFE_LANCAMENTO {lan}, "
                   f"{len(n['itens'])} item(ns), {self._brl(t.get('vNF', 0.0))}"
                   + (f" — CANCELADA em {self._data_br(data_canc)}" if data_canc else ""))

    def _gravar_titulo_pagar(self, cur, n, forn, emp, fil, dados, ult_grav, log, valores):
        empc, filc = dados.get('emp_cad', emp), dados.get('fil_cad', fil)
        cod_tit = str(n['nro_nf']).lstrip('0') or '0'
        serie = str(n['serie']).strip().upper()[:3]
        if (cod_tit, serie, forn) in dados['tit_pag']:
            log.append(f"   ⚠ título {cod_tit}/{serie} já existe no Pagar — "
                       f"parcelas da nota gravadas, título NÃO duplicado")
            return
        # os mesmos valores gravados nas parcelas da nota, para o título não
        # divergir dela por causa do acerto do último centavo
        total = round(sum(valores), 2)
        venc1 = self._data_iso(n['parcelas'][0].get('d_venc')) or n['data_emissao']
        dias1 = int(n['parcelas'][0].get('dias') or 0)
        cur.execute("""
            INSERT INTO TABELA_TITULO (
                TIT_EMPRESA, TIT_FILIAL, TIT_CODIGO, TIT_SERIE,
                TIT_FORNECEDOR_EMPRESA, TIT_FORNECEDOR_FILIAL, TIT_FORNECEDOR,
                TIT_EMISSAO, TIT_DATA, TIT_TL_EMPRESA, TIT_TL_FILIAL, TIT_TIPO_LANCAMENTO,
                TIT_PARCELAS, TIT_VENCIMENTO, TIT_DIAS, TIT_ORIGEM, TIT_VALOR,
                TIT_MOEDA_EMPRESA, TIT_MOEDA_FILIAL, TIT_QTD_MOEDA,
                TIT_TOTAL, TIT_TOTAL_CC, TIT_TOTAL_CONTABIL, TIT_TOTAL_PARCELAS,
                TIT_USUARIO, TIT_ULT_GRAVACAO
            ) VALUES (?,?,?,?, ?,?,?, ?,?,?,?,2, ?,?,?,?,?, ?,?,0, ?,?,?,?, ?,?)
        """, [emp, fil, cod_tit, serie,
              empc, filc, forn,        # TIT_FORNECEDOR_* -> TABELA_CLI_FOR
              n['data_emissao'], n['data_emissao'], empc, filc,   # TIT_TL_*
              len(n['parcelas']), venc1, dias1, ORIGEM_IMPORTACAO, total,
              empc, filc,              # TIT_MOEDA_* -> TABELA_MOEDA
              total, total, total, total, USUARIO_PADRAO, ult_grav])
        for i, (p, val) in enumerate(zip(n['parcelas'], valores), start=1):
            venc = self._data_iso(p.get('d_venc')) or n['data_emissao']
            cur.execute("""
                INSERT INTO TABELA_TITULO_PARCELA (
                    TPARC_EMPRESA, TPARC_FILIAL, TPARC_CODIGO, TPARC_SERIE, TPARC_PARCELA,
                    TPARC_FORNECEDOR_EMPRESA, TPARC_FORNECEDOR_FILIAL, TPARC_FORNECEDOR,
                    TPARC_EMISSAO, TPARC_DIAS, TPARC_VENCIMENTO,
                    TPARC_MOEDA_EMPRESA, TPARC_MOEDA_FILIAL, TPARC_VALOR, TPARC_TOTAL,
                    TPARC_IRRF, TPARC_INSS, TPARC_VALOR_PG, TPARC_PG,
                    TPARC_DESCONTO, TPARC_JUROS, TPARC_CORRECAO, TPARC_ORIGEM,
                    TPARC_ULT_GRAVACAO, TPARC_LIBERADO
                ) VALUES (?,?,?,?,?, ?,?,?, ?,?,?, ?,?,?,?, 0,0,0,'N', 0,0,0,?, ?,'S')
            """, [emp, fil, cod_tit, serie, i,
                  empc, filc, forn,    # TPARC_FORNECEDOR_* -> TABELA_CLI_FOR
                  n['data_emissao'], int(p.get('dias') or 0), venc,
                  empc, filc, val, val,     # TPARC_MOEDA_*
                  ORIGEM_IMPORTACAO, ult_grav])
        self._rateio_titulo_pagar(cur, emp, fil, cod_tit, serie, forn,
                                  n['data_emissao'], total, empc, filc)
        log.append(f"   💰 título {cod_tit}/{serie} no Pagar, "
                   f"{len(n['parcelas'])} parcela(s), {self._brl(total)}")

    def _data_iso(self, texto):
        if not texto:
            return None
        try:
            return datetime.datetime.strptime(str(texto)[:10], '%Y-%m-%d').date()
        except Exception:
            return None

    @staticmethod
    def _data_br(data):
        """date -> dd/mm/aaaa, para o log e as mensagens (aceita None)."""
        try:
            return data.strftime('%d/%m/%Y')
        except Exception:
            return str(data or '')

    # ------------------------------------------------------------ EXPORTAR
    def _exportar_analise(self):
        if not self.analise:
            return
        caminho = filedialog.asksaveasfilename(
            defaultextension=".csv", initialfile="ANALISE_NOTAS_XML.csv",
            filetypes=[("CSV", "*.csv")])
        if not caminho:
            return
        try:
            with open(caminho, 'w', newline='', encoding='utf-8-sig') as fh:
                w = csv.writer(fh, delimiter=';')
                w.writerow(["FASE 1 - CLIENTE/FORNECEDOR"])
                w.writerow(["STATUS", "CNPJ/CPF", "RAZAO", "UF", "CIDADE", "NOTAS", "COD_ERP"])
                for f in self.analise['fase1']:
                    d = f['dados']
                    w.writerow([f['status'], d.get('documento_formatado', ''), d.get('razao', ''),
                                d.get('uf', ''), d.get('cidade_nome', ''), f['notas'],
                                f['codigo_erp'] or ''])
                w.writerow([])
                w.writerow(["FASE 2 - NATUREZA DE OPERACAO (CFOP)"])
                w.writerow(["STATUS", "CFOP", "TIPO", "COD_ERP", "DESCRICAO",
                            "FLUXO_CAIXA", "CONTABIL", "ESTOQUE", "NOTAS"])
                for f in self.analise['fase2']:
                    w.writerow([f['status'], f['cfop'],
                                'SAIDA' if f['tipo'] == 'S' else 'ENTRADA',
                                f['codigo_erp'] or '', f['desc_erp'] or f['desc_xml'],
                                f['fluxo'], f['contabil'], f['estoque'], f['notas']])
                w.writerow([])
                w.writerow(["FASE 3 - PRODUTO"])
                w.writerow(["STATUS", "COD_XML", "DESCRICAO_XML", "NCM", "UN",
                            "COD_ERP", "CASOU_POR", "ITENS"])
                for f in self.analise['fase3']:
                    it = f['item']
                    w.writerow([f['status'], f['cod_xml'], it.get('x_prod', ''),
                                it.get('ncm', ''), it.get('u_com', ''),
                                f['codigo_erp'] or '', f['casou_por'], f['itens']])
                w.writerow([])
                w.writerow(["FASE 4 - NOTAS"])
                w.writerow(["STATUS", "SITUACAO", "TIPO", "NUMERO", "SERIE", "EMISSAO", "CHAVE",
                            "CONTRAPARTE", "DOCUMENTO", "VALOR", "ITENS", "PARCELAS",
                            "MOTIVO", "ARQUIVO"])
                for f in self.analise['fase4']:
                    n = f['nota']
                    c = n.get('contraparte') or {}
                    w.writerow([
                        f['status'],
                        str(n.get('sit_documento') or SITD_REGULAR),
                        f['tipo'], n['nro_nf'], n['serie'],
                        n['data_emissao'].strftime('%d/%m/%Y') if n['data_emissao'] else '',
                        n['chave'], c.get('razao', ''), c.get('documento_formatado', ''),
                        f"{n['totais'].get('vNF', 0.0):.2f}".replace('.', ','),
                        len(n['itens']), len(n['parcelas']), f['motivo'],
                        os.path.basename(n.get('arquivo', '')),
                    ])
            messagebox.showinfo("Exportado", f"Análise salva em:\n{caminho}")
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao exportar:\n{e}")

    def _oferecer_log(self, linhas, nome):
        if not linhas:
            return
        texto = "\n".join(str(l) for l in linhas)
        if not messagebox.askyesno("Log", "Deseja salvar o log desta operação?"):
            return
        caminho = filedialog.asksaveasfilename(
            defaultextension=".txt", initialfile=nome, filetypes=[("Texto", "*.txt")])
        if not caminho:
            return
        try:
            with open(caminho, 'w', encoding='utf-8') as fh:
                fh.write(texto)
            if messagebox.askyesno("Log salvo", "Abrir o arquivo agora?"):
                os.startfile(caminho)
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível salvar o log:\n{e}")

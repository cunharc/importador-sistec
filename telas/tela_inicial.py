import tkinter as tk
from tkinter import ttk, messagebox
import os
import configparser
import sys
from PIL import Image, ImageTk
import datetime
import getpass
import socket
from telas.tela_importacao import TelaImportacao
from telas.tela_conexao import TelaConexao
from telas.tela_nfe import TelaNFe
from telas.tela_xml_produtos import TelaXmlProdutos
from telas.tela_ncm import TelaNcm
from telas.tela_cfop import TelaCfop
from telas.tela_icms import TelaIcms
from telas.tela_rt import TelaRt
from telas.tela_lista_precos import TelaListaPrecos
from telas.tela_auditoria_geral import TelaAuditoriaGeral
from telas.tela_auditoria_por_produto import TelaAuditoriaPorProduto
from telas.tela_sobre import TelaSobre
from telas.tela_importacao_planilha_produtos import TelaImportacaoPlanilhaProdutos
from telas.tela_importacao_planilha_clientes import TelaImportacaoPlanilhaClientes
from telas.tela_importacao_planilha_receber import TelaImportacaoPlanilhaReceber
from telas.tela_importacao_planilha_pagar import TelaImportacaoPlanilhaPagar
from telas.tela_importacao_planilha_lista_precos import TelaImportacaoPlanilhaListaPrecos
from telas.tela_importacao_planilha_tributacao import TelaImportacaoPlanilhaTributacao
from telas.tela_importacao_planilha_estoque_producao import TelaImportacaoPlanilhaEstoqueProducao
from telas.tela_importacao_planilha_transportadora import TelaImportacaoPlanilhaTransportadora
from telas.tela_importacao_nfe import TelaImportacaoNFe
from telas.tela_duplicar_empresa import TelaDuplicarEmpresa
from telas.tela_vinculo_cc import TelaVinculoCC
from busca_logs import BuscaLogsWindow
from utils.firebird_service import FirebirdService
from utils.updater import (verificar_e_atualizar, verificar_em_segundo_plano,
                           perguntar_atualizacao)
from utils import tema
from version import get_info

# Cores do sidebar (navy profundo da identidade Sistecweb)
_SIDEBAR = "#141132"
_SIDEBAR_HOVER = "#232152"
_SIDEBAR_ACTIVE = "#2E2C6E"

class TelaInicial(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg="#F0F0F0")
        self.parent = parent
        self.tela_atual = None
        self.nome_tela_atual = None
        self.pack(fill=tk.BOTH, expand=True)
        self._criar_widgets()
        
        self.parent.bind('<Escape>', self._on_escape)
        self.parent.bind('<F5>', self._on_f5)
        
        self._limpar_logs_antigos()

    def resource_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def _criar_widgets(self):
        self.categoria_atual = 'todos'
        self.nav_botoes = {}

        AZUL = tema.SISTEC_BLUE
        BASE = tema.BG_BASE
        TXT = tema.TEXT
        TXT2 = tema.TEXT_SECOND

        # ===================== TOPBAR =====================
        topbar = tk.Frame(self, bg=AZUL, height=62)
        topbar.pack(fill=tk.X, side=tk.TOP)
        topbar.pack_propagate(False)

        left = tk.Frame(topbar, bg=AZUL)
        left.pack(side=tk.LEFT, padx=16)
        logo_path = self.resource_path("Logo oficial grupos - Sistec.png")
        if os.path.exists(logo_path):
            try:
                img = Image.open(logo_path)
                img.thumbnail((46, 46))
                self.logo_img = ImageTk.PhotoImage(img)
                tk.Label(left, image=self.logo_img, bg=AZUL).pack(side=tk.LEFT, pady=8)
            except Exception:
                pass
        tk.Label(left, text="Central de Implantação", font=("Segoe UI", 15, "bold"),
                 bg=AZUL, fg="white").pack(side=tk.LEFT, padx=(12, 0))

        right = tk.Frame(topbar, bg=AZUL)
        right.pack(side=tk.RIGHT, padx=16)

        tk.Label(right, text=get_info(), font=("Segoe UI", 8),
                 bg=AZUL, fg="#9A9CD8").pack(side=tk.RIGHT, padx=(12, 0))

        btn_config_db = tk.Button(right, text="⚙  Configurar Banco", font=("Segoe UI", 9, "bold"),
                                  bg="#2E2C6E", fg="white", activebackground="#3A3888",
                                  activeforeground="white", relief=tk.FLAT, bd=0,
                                  cursor="hand2", padx=12, pady=4, command=self._abrir_config_banco)
        btn_config_db.pack(side=tk.RIGHT, padx=(12, 0))

        self.cb_filial = ttk.Combobox(right, width=26, state="readonly", cursor="hand2")
        self.cb_filial.pack(side=tk.RIGHT, padx=(12, 0))
        self.cb_filial.bind("<<ComboboxSelected>>", self._salvar_filial_selecionada)
        self.filiais_data = []

        status_labels = tk.Frame(right, bg=AZUL)
        status_labels.pack(side=tk.RIGHT)
        self.lbl_status_db = tk.Label(status_labels, text="Verificando...", font=("Segoe UI", 10, "bold"),
                                      bg=AZUL, fg="#FACC15")
        self.lbl_status_db.pack(anchor=tk.E)
        self.lbl_path_db = tk.Label(status_labels, text="", font=("Segoe UI", 8), bg=AZUL, fg="#9A9CD8")
        self.lbl_path_db.pack(anchor=tk.E)

        # ===================== CORPO =====================
        body = tk.Frame(self, bg=BASE)
        body.pack(fill=tk.BOTH, expand=True)

        # -------- SIDEBAR --------
        sidebar = tk.Frame(body, bg=_SIDEBAR, width=214)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)

        rodape_sb = tk.Frame(sidebar, bg=_SIDEBAR)
        rodape_sb.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 8))
        self._nav_item(rodape_sb, "⎋", "Sair do sistema", self.parent.quit)

        tk.Label(sidebar, text="NAVEGAÇÃO", font=("Segoe UI", 8, "bold"),
                 bg=_SIDEBAR, fg="#6E6FA8", anchor="w", padx=18).pack(fill=tk.X, pady=(16, 4))
        cats = [("📋", "Todos", "todos"), ("📊", "Excel", "excel"),
                ("📄", "XML", "xml"), ("🧰", "Outros", "outros")]
        for emoji, nome, chave in cats:
            n = len(self._filtrar_modulos(chave, ""))
            self._nav_item(sidebar, emoji, f"{nome}  ({n})",
                           lambda c=chave: self._aplicar_filtro(c), chave=chave)

        tk.Frame(sidebar, bg="#2A2A55", height=1).pack(fill=tk.X, padx=16, pady=(14, 0))
        tk.Label(sidebar, text="AÇÕES", font=("Segoe UI", 8, "bold"),
                 bg=_SIDEBAR, fg="#6E6FA8", anchor="w", padx=18).pack(fill=tk.X, pady=(12, 4))
        self._nav_item(sidebar, "📖", "Sobre o sistema", self._abrir_sobre)
        self._nav_item(sidebar, "📄", "Ver logs de hoje", self._abrir_logs)
        self.item_atualizar = self._nav_item(
            sidebar, "🔄", "Atualizar sistema",
            lambda: verificar_e_atualizar(self.winfo_toplevel()))

        # Aviso discreto de versão nova. Aparece só quando existe, some quando o
        # usuário dispensa, e nunca interrompe o trabalho: o sistema abre normal e a
        # consulta acontece em segundo plano. Quem decide atualizar é ele.
        self.aviso_versao = tk.Frame(sidebar, bg=_SIDEBAR)
        self._release_pendente = None
        self.after(2500, self._checar_versao_nova)

        # -------- CONTEÚDO --------
        content = tk.Frame(body, bg=BASE)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=18, pady=16)

        head = tk.Frame(content, bg=BASE)
        head.pack(fill=tk.X, pady=(0, 14))
        tk.Label(head, text="Módulos", font=("Segoe UI", 18, "bold"), bg=BASE, fg=TXT).pack(side=tk.LEFT)
        self.lbl_subtitulo = tk.Label(head, text="", font=("Segoe UI", 10), bg=BASE, fg=TXT2)
        self.lbl_subtitulo.pack(side=tk.LEFT, padx=(12, 0))

        busca_wrap = tk.Frame(head, bg=tema.CARD, highlightbackground=tema.BORDER, highlightthickness=1)
        busca_wrap.pack(side=tk.RIGHT)
        tk.Label(busca_wrap, text="🔎", bg=tema.CARD, fg=TXT2).pack(side=tk.LEFT, padx=(8, 2))
        self.ent_busca = tk.Entry(busca_wrap, width=28, relief=tk.FLAT, bg=tema.CARD, fg=TXT,
                                  font=("Segoe UI", 10))
        self.ent_busca.pack(side=tk.LEFT, ipady=4, padx=(0, 6))
        self.ent_busca.bind("<KeyRelease>", lambda e: self._render_cards())

        # área de cards com rolagem (Canvas + Scrollbar)
        cards_wrap = tk.Frame(content, bg=BASE)
        cards_wrap.pack(fill=tk.BOTH, expand=True)
        self.cards_canvas = tk.Canvas(cards_wrap, bg=BASE, highlightthickness=0)
        vsb = ttk.Scrollbar(cards_wrap, orient="vertical", command=self.cards_canvas.yview)
        self.cards_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.cards_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._cols_atual = 0  # nº de colunas renderizadas (p/ re-render só quando muda)
        self.card_container = tk.Frame(self.cards_canvas, bg=BASE)
        self._card_window = self.cards_canvas.create_window((0, 0), window=self.card_container, anchor="nw")
        self.card_container.bind(
            "<Configure>",
            lambda e: self.cards_canvas.configure(scrollregion=self.cards_canvas.bbox("all")))
        self.cards_canvas.bind("<Configure>", self._on_canvas_resize)
        self.cards_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        self._restyle_nav()
        self._render_cards()
        self.after(800, self._atualizar_status)

    def _calc_cols(self, largura):
        # largura mínima confortável por card (inclui os paddings da célula)
        CARD_MIN = 300
        if largura <= 0:
            return 3
        return max(2, min(6, largura // CARD_MIN))

    def _on_canvas_resize(self, event):
        # ajusta a largura da área interna e re-renderiza só se o nº de colunas mudou
        self.cards_canvas.itemconfig(self._card_window, width=event.width)
        novo = self._calc_cols(event.width)
        if novo != self._cols_atual:
            self._cols_atual = novo
            self._render_cards()

    def _on_mousewheel(self, event):
        # só rola quando a central está visível (evita interferir nos módulos abertos)
        try:
            if self.cards_canvas.winfo_ismapped():
                self.cards_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def _nav_item(self, parent, icone, texto, comando, chave=None):
        it = tk.Frame(parent, bg=_SIDEBAR, cursor="hand2")
        it.pack(fill=tk.X)
        # faixa de destaque à esquerda (indica item ativo)
        strip = tk.Frame(it, bg=_SIDEBAR, width=4)
        strip.pack(side=tk.LEFT, fill=tk.Y)
        # coluna FIXA para o ícone: garante que todo texto comece no mesmo x,
        # independente da largura de cada emoji
        ico_wrap = tk.Frame(it, bg=_SIDEBAR, width=26)
        ico_wrap.pack(side=tk.LEFT, fill=tk.Y, padx=(14, 0))
        ico_wrap.pack_propagate(False)
        lbl_ic = tk.Label(ico_wrap, text=icone, font=("Segoe UI", 12), bg=_SIDEBAR, fg="#B9BBE0")
        # alinhado à ESQUERDA (borda esquerda igual p/ todos) e centralizado na vertical
        lbl_ic.place(relx=0.0, rely=0.5, anchor="w")
        lbl = tk.Label(it, text=texto, font=("Segoe UI", 10, "bold"), bg=_SIDEBAR, fg="#B9BBE0", anchor="w")
        lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 12), pady=10)
        grupo = (it, strip, ico_wrap, lbl_ic, lbl)
        for w in grupo:
            w.bind("<Button-1>", lambda e: comando())

        def enter(e):
            if chave != self.categoria_atual:
                for w in (it, ico_wrap, lbl_ic, lbl):
                    w.config(bg=_SIDEBAR_HOVER)
                strip.config(bg=_SIDEBAR_HOVER)

        def leave(e):
            self._restyle_nav()
            if chave is None:
                for w in (it, ico_wrap, lbl_ic, lbl):
                    w.config(bg=_SIDEBAR)
                strip.config(bg=_SIDEBAR)

        for w in grupo:
            w.bind("<Enter>", enter)
            w.bind("<Leave>", leave)
        if chave is not None:
            self.nav_botoes[chave] = (it, strip, ico_wrap, lbl_ic, lbl)
        return it

    # ------------------------------------------------- AVISO DE VERSÃO NOVA
    def _checar_versao_nova(self):
        """Consulta o GitHub em segundo plano, 2,5s depois de abrir.

        O atraso é para o sistema aparecer na tela primeiro: consulta de rede na
        abertura é o tipo de coisa que faz o programa parecer travado.
        """
        try:
            verificar_em_segundo_plano(self.winfo_toplevel(), self._mostrar_aviso_versao)
        except Exception:
            pass          # sem internet o sistema abre normal, sem reclamar

    def _mostrar_aviso_versao(self, release):
        if not self.winfo_exists():
            return
        self._release_pendente = release
        for w in self.aviso_versao.winfo_children():
            w.destroy()

        faixa = tk.Frame(self.aviso_versao, bg="#2E2C6E", cursor="hand2")
        faixa.pack(fill=tk.X, padx=10, pady=(10, 0))
        tk.Label(faixa, text=f"🔔  Versão {release['versao']} disponível",
                 font=("Segoe UI", 9, "bold"), bg="#2E2C6E", fg="#FFD48A",
                 anchor="w", padx=8, pady=6, cursor="hand2").pack(fill=tk.X)
        tk.Label(faixa, text="clique para ver o que mudou",
                 font=("Segoe UI", 8), bg="#2E2C6E", fg="#B9BBE0",
                 anchor="w", padx=8, cursor="hand2").pack(fill=tk.X, pady=(0, 6))

        def abrir(_e=None):
            perguntar_atualizacao(self.winfo_toplevel(), self._release_pendente)

        for w in (faixa,) + tuple(faixa.winfo_children()):
            w.bind("<Button-1>", abrir)
        self.aviso_versao.pack(fill=tk.X)

    def _restyle_nav(self):
        for chave, (it, strip, ico_wrap, lbl_ic, lbl) in self.nav_botoes.items():
            if chave == self.categoria_atual:
                for w in (it, ico_wrap, lbl_ic, lbl):
                    w.config(bg=_SIDEBAR_ACTIVE)
                lbl.config(fg="white")
                lbl_ic.config(fg="white")
                strip.config(bg=tema.SISTEC_ORANGE)
            else:
                for w in (it, ico_wrap, lbl_ic, lbl):
                    w.config(bg=_SIDEBAR)
                lbl.config(fg="#B9BBE0")
                lbl_ic.config(fg="#B9BBE0")
                strip.config(bg=_SIDEBAR)

    def _lista_modulos(self):
        return [
            ("Plano de Contas", "Importação estruturada do plano de contas via planilha Excel diretamente para o banco de dados Firebird.",
             "#C8001E", "_abrir_importacao", None, "📑", ("excel",)),
            ("Clientes/Fornec. NF-e", "Importação automática de clientes e fornecedores via leitura de arquivos XML de Notas Fiscais (NF-e 4.00).",
             "#F39C12", "_abrir_nfe", None, "👥", ("xml",)),
            ("Faixas de ICMS", "Construção e auditoria das regras de ICMS por estado baseado no histórico de XMLs.",
             "#8E44AD", "_abrir_icms", None, "🗺️", ("xml",)),
            ("Tributação por NCM", "Gestão de regras tributárias e alíquotas baseadas na Nomenclatura Comum do Mercosul.",
             "#2980B9", "_abrir_ncm", None, "🏷️", ("xml",)),
            ("Tributação CFOP", "Definição de naturezas de operação e regras contábeis por CFOP.",
             "#D35400", "_abrir_cfop", None, "🚚", ("xml",)),
            ("Produtos & Consolidado", "Auditoria final por produto, cruzando NCM, CFOP e ICMS para cadastro e correção.",
             "#27AE60", "_abrir_xml_produtos", None, "📦", ("xml",)),
            ("Reforma Tributária (RT)", "Construção e auditoria das regras de IBS e CBS baseadas nos XMLs.",
             "#F012BE", "_abrir_rt", None, "🏛️", ("xml",)),
            ("Lista de Preços XML", "Crie ou atualize Listas de Preços de Venda capturando automaticamente o valor unitário dos XMLs.",
             "#16A085", "_abrir_lista_precos", None, "💲", ("xml",)),
            ("Visão Gerencial (Completa)", "Auditoria completa agrupando Produto, NCM, CFOP, ICMS, PIS/COF e RT com exportação.",
             "#34495E", "_abrir_auditoria_geral", None, "📊", ("xml",)),
            ("Importar Produtos (Excel)", "Importação e auto-cadastro de produtos, grupos e subgrupos via planilha (XLSX/CSV).",
             "#27AE60", "_abrir_importacao_planilha_produtos", None, "📝", ("excel",)),
            ("Auditoria por Produto", "Auditoria cruzando todas as variações de tributação que um mesmo produto sofreu nos XMLs.",
             "#8E44AD", "_abrir_auditoria_produto", None, "🔎", ("xml",)),
            ("Busca em Logs ERP", "Varredura avançada e rápida em arquivos .txt de log gerados pelo ERP.",
             "#F39C12", "_abrir_busca_logs", None, "🕵️", ("outros",)),
            ("Importar Clientes (Excel)", "Importação de clientes com mapeamento de colunas via planilha (XLSX/CSV) para cadastro no ERP.",
             "#14146E", "_abrir_importacao_planilha_clientes", None, "👤", ("excel",)),
            ("Importar Transportadoras (Excel)", "Cadastro de transportadoras via planilha (XLSX/CSV) com mapeamento de colunas, validação de CNPJ/CPF e resolução da cidade pelo IBGE ou pelo nome+UF.",
             "#0E7490", "_abrir_importacao_planilha_transportadora", None, "🚚", ("excel",)),
            ("Importar Contas a Receber (Excel)", "Importação de títulos e parcelas de contas a receber com mapeamento de colunas via planilha (XLSX/CSV).",
             "#E67E22", "_abrir_importacao_planilha_receber", None, "💰", ("excel",)),
            ("Importar Contas a Pagar (Excel)", "Importação de títulos e parcelas de contas a pagar com mapeamento de colunas via planilha (XLSX/CSV).",
             "#C0392B", "_abrir_importacao_planilha_pagar", None, "💳", ("excel",)),
            ("Importar Lista de Preços (Excel)", "Importação de tabela de preços com mapeamento de colunas via planilha (XLSX/CSV) e validação contra o cadastro do ERP.",
             "#E67E22", "_abrir_importacao_planilha_lista_precos", None, "📊", ("excel",)),
            ("Importar Tributação (Excel)", "Importação completa de tributação por NCM via planilha: ICMS, PIS, COFINS e Reforma Tributária com criação de faixas e regras.",
             "#F012BE", "_abrir_importacao_planilha_tributacao", None, "📋", ("excel",)),
            ("Importar Estoque de Produção (Excel)", "Importação do estoque de Produto Acabado por etiquetas: gera a Ordem de Desossa de inventário, os itens PA e as pesagens (etiqueta, peso, validade e produção).",
             "#0E7490", "_abrir_importacao_planilha_estoque_producao", None, "🏭", ("excel",)),
            ("Importar Notas Fiscais (XML)", "Traz notas de emissão própria (entrada e saída) dos XMLs para o ERP. Valida em fases: cliente/fornecedor, natureza de operação (fluxo de caixa, contábil) e produto — cadastrando o que faltar — e grava a nota com itens, impostos, parcelas e o título no financeiro. Não movimenta estoque.",
             "#1F6F8B", "_abrir_importacao_nfe", None, "🧾", ("xml",)),
            ("Duplicar / Configurar Empresa", "Clona uma empresa/filial existente (EMPRESA, PARAM, FILIAL, CONFIG NF-e) e permite ajustar cada configuração campo a campo antes de gravar.",
             "#6C3483", "_abrir_duplicar_empresa", None, "⧉", ("outros",)),
            ("Vínculo CC × Plano de Contas", "Vincula os centros de custo às contas do plano (contabilização automática) em massa, estilo planilha, com árvore de CC e busca do plano.",
             "#117A65", "_abrir_vinculo_cc", None, "🔗", ("outros",)),
        ]

    def _filtrar_modulos(self, categoria, texto):
        txt = (texto or "").strip().lower()
        res = []
        for m in self._lista_modulos():
            if categoria != 'todos' and categoria not in m[6]:
                continue
            if txt and txt not in m[0].lower() and txt not in m[1].lower():
                continue
            res.append(m)
        return res

    def _render_cards(self):
        for w in self.card_container.winfo_children():
            w.destroy()

        texto = self.ent_busca.get() if hasattr(self, 'ent_busca') else ""
        mods = self._filtrar_modulos(self.categoria_atual, texto)
        self.lbl_subtitulo.config(text=f"{len(mods)} módulo(s) disponível(is)")

        if not mods:
            tk.Label(self.card_container, text="Nenhum módulo encontrado para esta busca.",
                     font=("Segoe UI", 11), bg=tema.BG_BASE, fg=tema.TEXT_SECOND).pack(pady=40)
            return

        cols = self._cols_atual or self._calc_cols(self.cards_canvas.winfo_width())
        grid = tk.Frame(self.card_container, bg=tema.BG_BASE)
        grid.pack(fill=tk.BOTH, expand=True)
        for i in range(cols):
            grid.grid_columnconfigure(i, weight=1, uniform="col", minsize=250)
        rows = (len(mods) + cols - 1) // cols
        for i in range(rows):
            grid.grid_rowconfigure(i, uniform="row")

        for idx, mod in enumerate(mods):
            self._criar_card(grid, idx // cols, idx % cols, mod)

        # atualiza a região rolável e volta ao topo
        self.card_container.update_idletasks()
        self.cards_canvas.configure(scrollregion=self.cards_canvas.bbox("all"))
        self.cards_canvas.yview_moveto(0)

    def _aplicar_filtro(self, filtro):
        self.categoria_atual = filtro
        self._restyle_nav()
        self._render_cards()

    def _criar_card(self, parent, row, col, mod):
        titulo, descricao, cor, nome_comando, _icone_path, emoji, _cat = mod
        comando = getattr(self, nome_comando)
        CARD = tema.CARD
        HOVER = "#F7F8FF"

        # descrição enxuta (~2 linhas) para manter os cards baixos e evitar rolagem
        desc_curta = descricao if len(descricao) <= 110 else descricao[:107].rstrip() + "…"

        cell = tk.Frame(parent, bg=tema.BG_BASE)
        cell.grid(row=row, column=col, sticky="nsew", padx=5, pady=5)

        card = tk.Frame(cell, bg=CARD, highlightbackground=tema.BORDER, highlightthickness=1, cursor="hand2")
        card.pack(fill=tk.BOTH, expand=True)

        accent = tk.Frame(card, bg=cor, width=5)
        accent.pack(side=tk.LEFT, fill=tk.Y)

        body = tk.Frame(card, bg=CARD, cursor="hand2")
        body.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=12, pady=9)

        topo = tk.Frame(body, bg=CARD)
        topo.pack(fill=tk.X)
        lbl_ic = tk.Label(topo, text=emoji, font=("Segoe UI", 16), bg=CARD, fg=cor)
        lbl_ic.pack(side=tk.LEFT)
        lbl_titulo = tk.Label(topo, text=titulo, font=("Segoe UI", 10, "bold"), bg=CARD,
                              fg=tema.TEXT, anchor="w", justify=tk.LEFT, wraplength=210)
        lbl_titulo.pack(side=tk.LEFT, padx=(9, 0), fill=tk.X, expand=True)

        lbl_desc = tk.Label(body, text=desc_curta, font=("Segoe UI", 9), bg=CARD,
                            fg=tema.TEXT_SECOND, justify=tk.LEFT, anchor="w", wraplength=250)
        lbl_desc.pack(fill=tk.X, anchor=tk.W, pady=(6, 0))

        lbl_abrir = tk.Label(body, text="Abrir  →", font=("Segoe UI", 9, "bold"), bg=CARD, fg=cor)
        lbl_abrir.pack(anchor=tk.W, pady=(7, 0))

        internos = [body, topo, lbl_ic, lbl_titulo, lbl_desc, lbl_abrir]
        for el in [card] + internos:
            el.bind("<Button-1>", lambda e: comando())

        def on_enter(e):
            card.config(highlightbackground=cor)
            for el in internos:
                el.config(bg=HOVER)

        def on_leave(e):
            card.config(highlightbackground=tema.BORDER)
            for el in internos:
                el.config(bg=CARD)

        for el in [card] + internos:
            el.bind("<Enter>", on_enter)
            el.bind("<Leave>", on_leave)
            
    def _abrir_logs(self):
        try:
            data_atual = datetime.datetime.now().strftime('%Y-%m-%d')
            nome_arquivo = f"acessos_modulos_{data_atual}.log"
            if os.path.exists(nome_arquivo):
                os.startfile(os.path.normpath(nome_arquivo)) # Abre nativamente no Bloco de Notas do Windows
            else:
                messagebox.showinfo("Logs", "Nenhum log registrado para o dia de hoje ainda.")
        except Exception as e:
            print(f"Erro ao abrir logs: {e}")

    def _registrar_log(self, modulo, acao):
        try:
            usuario = getpass.getuser()
            computador = socket.gethostname()
            data_atual = datetime.datetime.now()
            nome_arquivo = f"acessos_modulos_{data_atual.strftime('%Y-%m-%d')}.log"
            with open(nome_arquivo, "a", encoding="utf-8") as f:
                data_hora = data_atual.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{data_hora}] [{computador}\\{usuario}] {acao}: {modulo}\n")
        except Exception as e:
            print(f"Erro ao registrar log: {e}")

    def _limpar_logs_antigos(self):
        try:
            hoje = datetime.datetime.now()
            for arquivo in os.listdir("."):
                if arquivo.startswith("acessos_modulos_") and arquivo.endswith(".log"):
                    try:
                        data_str = arquivo.replace("acessos_modulos_", "").replace(".log", "")
                        data_arquivo = datetime.datetime.strptime(data_str, "%Y-%m-%d")
                        if (hoje - data_arquivo).days > 30:
                            os.remove(arquivo)
                    except ValueError:
                        pass # Ignora caso a data do arquivo não consiga ser lida
        except Exception as e:
            print(f"Erro ao limpar logs antigos: {e}")

    def _on_escape(self, event):
        # Evita acionar o "Voltar" se o usuário estiver num Pop-up ou Toplevel
        focus_widget = self.winfo_toplevel().focus_get()
        if focus_widget and focus_widget.winfo_toplevel() != self.winfo_toplevel():
            return 
            
        if self.tela_atual and hasattr(self.tela_atual, '_fechar_tela'):
            self.tela_atual._fechar_tela()

    def _on_f5(self, event=None):
        # Força a atualização do status do banco de dados/filiais e do combo
        self._atualizar_status()

    def _auto_descobrir_banco(self):
        caminho_ini = ""
        if os.path.exists(r"C:\UTILIT\SISTEC.INI"):
            caminho_ini = r"C:\UTILIT\SISTEC.INI"
        elif os.path.exists(r"C:\Sistec\launcher.ini"):
            caminho_ini = r"C:\Sistec\launcher.ini"
            
        if not caminho_ini:
            return None, None, None, None, None
            
        try:
            nome_arquivo = os.path.basename(caminho_ini).lower()
            if nome_arquivo == 'launcher.ini':
                config_l = configparser.ConfigParser(strict=False)
                try:
                    config_l.read(caminho_ini, encoding='utf-8')
                except Exception:
                    config_l.read(caminho_ini, encoding='latin-1')
                    
                if config_l.has_section('Sistec'):
                    db_str = config_l.get('Sistec', 'Database', fallback='')
                    usuario = config_l.get('Sistec', 'User_Name', fallback='sysdba')
                    senha = config_l.get('Sistec', 'Password', fallback='masterkey')
                    if db_str:
                        parts = db_str.split(':', 1)
                        if len(parts) == 2 and len(parts[0]) > 1:
                            servidor_porta = parts[0]
                            caminho_banco = parts[1]
                            if '/' in servidor_porta:
                                srv_parts = servidor_porta.split('/')
                                servidor = srv_parts[0]
                                porta = srv_parts[1]
                            else:
                                servidor = servidor_porta
                                porta = '3050'
                        else:
                            servidor = 'localhost'
                            porta = '3050'
                            caminho_banco = db_str
                        return caminho_banco, servidor, porta, usuario, senha
            else:
                with open(caminho_ini, 'r', encoding='latin-1', errors='ignore') as f:
                    dentro_bancos_local = False
                    for linha in f:
                        linha = linha.strip()
                        if "BANCOS LOCAL" in linha.upper():
                            dentro_bancos_local = True
                            continue
                        if dentro_bancos_local and linha.lower().startswith('database='):
                            db_path = linha.split('=', 1)[1].strip()
                            return db_path, "localhost", "3050", "SYSDBA", "masterkey"
        except Exception:
            pass
        return None, None, None, None, None

    def _atualizar_status(self):
        config = configparser.ConfigParser()
        try:
            config.read('config.ini', encoding='utf-8-sig')
        except Exception:
            config.read('config.ini', encoding='latin-1')
        caminho_banco = config.get('FIREBIRD', 'caminho_banco', fallback='')
        
        # AUTO-DISCOVERY SE NÃO ESTIVER CONFIGURADO
        if not caminho_banco:
            caminho_banco, servidor, porta, usuario, senha = self._auto_descobrir_banco()
            if caminho_banco:
                if not config.has_section('FIREBIRD'):
                    config.add_section('FIREBIRD')
                config.set('FIREBIRD', 'servidor', servidor)
                config.set('FIREBIRD', 'porta', porta)
                config.set('FIREBIRD', 'caminho_banco', caminho_banco)
                config.set('FIREBIRD', 'usuario', usuario)
                config.set('FIREBIRD', 'senha', senha)
                try:
                    with open('config.ini', 'w', encoding='utf-8') as f:
                        config.write(f)
                except Exception:
                    pass

        texto_banco = ""
        if caminho_banco:
            nome_arquivo = os.path.basename(caminho_banco)
            if os.path.exists(caminho_banco):
                tamanho_mb = os.path.getsize(caminho_banco) / (1024 * 1024)
                texto_banco = f"{nome_arquivo} ({tamanho_mb:.1f} MB)"
            else:
                texto_banco = nome_arquivo
                
        fbclient_ini = config.get('FIREBIRD', 'fbclient', fallback='').strip()
        fbclient_path = self.resource_path(fbclient_ini) if fbclient_ini else ''

        config_db = {
            'host': config.get('FIREBIRD', 'servidor', fallback='127.0.0.1'),
            'port': config.get('FIREBIRD', 'porta', fallback='3050'),
            'database': config.get('FIREBIRD', 'caminho_banco', fallback=''),
            'user': config.get('FIREBIRD', 'usuario', fallback='SYSDBA'),
            'password': config.get('FIREBIRD', 'senha', fallback='masterkey'),
            'fbclient': fbclient_path
        }

        try:
            with FirebirdService(config_db) as fb_conn:
                self.lbl_status_db.config(text="🟢 Conectado ao Banco", fg="#27AE60")
                self.lbl_path_db.config(text=texto_banco)
                
                sql = "SELECT F.FILIAL_EMPRESA, F.FILIAL_CODIGO, F.FILIAL_FANTASIA, F.FILIAL_UF, E.EMP_NOME FROM TABELA_FILIAL F JOIN TABELA_EMPRESA E ON F.FILIAL_EMPRESA = E.EMP_CODIGO"
                self.filiais_data = fb_conn.query(sql)
                
                combo_values = []
                selecionado_idx = 0
                emp_salva = config.get('IMPORTACAO', 'empresa', fallback='')
                fil_salva = config.get('IMPORTACAO', 'filial', fallback='')
                
                for idx, fil in enumerate(self.filiais_data):
                    emp_cod = str(fil.get('filial_empresa', ''))
                    fil_cod = str(fil.get('filial_codigo', ''))
                    fantasia = str(fil.get('filial_fantasia') or fil.get('emp_nome', ''))
                    uf = str(fil.get('filial_uf', ''))
                    desc = f"Emp: {emp_cod} | Fil: {fil_cod} - {fantasia} ({uf})"
                    combo_values.append(desc)
                    if emp_cod == emp_salva and fil_cod == fil_salva:
                        selecionado_idx = idx
                        
                self.cb_filial['values'] = combo_values
                if combo_values:
                    self.cb_filial.current(selecionado_idx)
                    self._salvar_filial_selecionada(None)
        except Exception as e:
            # Fallback: pergunta se deseja usar o banco descoberto automaticamente
            if caminho_banco:
                caminho_auto, servidor_auto, porta_auto, usuario_auto, senha_auto = self._auto_descobrir_banco()
                if caminho_auto and caminho_auto != caminho_banco:
                    resposta = messagebox.askyesno(
                        "Banco não encontrado",
                        f"O banco configurado não foi encontrado:\n{caminho_banco}\n\n"
                        f"Foi detectado um banco em:\n{caminho_auto}\n\n"
                        "Deseja usar este banco?",
                        parent=self.parent
                    )
                    if resposta:
                        try:
                            config_auto = {
                                'host': servidor_auto, 'port': porta_auto, 'database': caminho_auto,
                                'user': usuario_auto, 'password': senha_auto,
                                'fbclient': self.resource_path(config.get('FIREBIRD', 'fbclient', fallback='').strip()) or ''
                            }
                            with FirebirdService(config_auto) as _:
                                config.set('FIREBIRD', 'servidor', servidor_auto)
                                config.set('FIREBIRD', 'porta', porta_auto)
                                config.set('FIREBIRD', 'caminho_banco', caminho_auto)
                                config.set('FIREBIRD', 'usuario', usuario_auto)
                                config.set('FIREBIRD', 'senha', senha_auto)
                                with open('config.ini', 'w', encoding='utf-8') as f:
                                    config.write(f)
                                self.after(100, self._atualizar_status)
                                return
                        except Exception:
                            pass
            print("Erro na auto-conexão da Tela Inicial:", e)
            self.lbl_status_db.config(text="🔴 Não Conectado", fg="#E74C3C")
            self.lbl_path_db.config(text="")
            self.cb_filial.set('')
            self.cb_filial['values'] = []

    def _salvar_filial_selecionada(self, event):
        idx = self.cb_filial.current()
        if idx >= 0 and idx < len(self.filiais_data):
            fil = self.filiais_data[idx]
            config = configparser.ConfigParser()
            config.read('config.ini', encoding='utf-8')
            if not config.has_section('IMPORTACAO'):
                config.add_section('IMPORTACAO')
            
            config.set('IMPORTACAO', 'empresa', str(fil.get('filial_empresa', '')))
            config.set('IMPORTACAO', 'filial', str(fil.get('filial_codigo', '')))
            config.set('IMPORTACAO', 'uf', str(fil.get('filial_uf', '')))
            
            with open('config.ini', 'w', encoding='utf-8') as f:
                config.write(f)

    def _abrir_config_banco(self):
        TelaConexao(self.winfo_toplevel(), callback_status=self._atualizar_status)

    def _abrir_nfe(self):
        self.pack_forget() 
        self.winfo_toplevel().title("Clientes/Fornec. NF-e - Implantação Sistec")
        self.nome_tela_atual = "Clientes/Fornec. NF-e"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaNFe(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_xml_produtos(self):
        self.pack_forget()
        self.winfo_toplevel().title("Produtos & Consolidado - Implantação Sistec")
        self.nome_tela_atual = "Produtos & Consolidado"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaXmlProdutos(self.parent, callback_voltar=self._voltar_inicial)
        
    def _abrir_ncm(self):
        self.pack_forget()
        self.winfo_toplevel().title("Tributação por NCM - Implantação Sistec")
        self.nome_tela_atual = "Tributação por NCM"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaNcm(self.parent, callback_voltar=self._voltar_inicial)
        
    def _abrir_cfop(self):
        self.pack_forget()
        self.winfo_toplevel().title("Tributação CFOP - Implantação Sistec")
        self.nome_tela_atual = "Tributação CFOP"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaCfop(self.parent, callback_voltar=self._voltar_inicial)
        
    def _abrir_icms(self):
        self.pack_forget()
        self.winfo_toplevel().title("Faixas de ICMS - Implantação Sistec")
        self.nome_tela_atual = "Faixas de ICMS"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaIcms(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_rt(self):
        self.pack_forget()
        self.winfo_toplevel().title("Reforma Tributária (RT) - Implantação Sistec")
        self.nome_tela_atual = "Reforma Tributária (RT)"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaRt(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_lista_precos(self):
        self.pack_forget()
        self.winfo_toplevel().title("Lista de Preços XML - Implantação Sistec")
        self.nome_tela_atual = "Lista de Preços XML"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaListaPrecos(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_auditoria_geral(self):
        self.pack_forget()
        self.winfo_toplevel().title("Visão Gerencial (Completa) - Implantação Sistec")
        self.nome_tela_atual = "Visão Gerencial (Completa)"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaAuditoriaGeral(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_importacao(self):
        self.pack_forget() # Oculta a tela inicial temporariamente
        self.winfo_toplevel().title("Plano de Contas - Implantação Sistec")
        self.nome_tela_atual = "Plano de Contas"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaImportacao(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_importacao_planilha_produtos(self):
        self.pack_forget()
        self.winfo_toplevel().title("Importação de Produtos via Planilha - Implantação Sistec")
        self.nome_tela_atual = "Importação de Produtos via Planilha"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaImportacaoPlanilhaProdutos(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_importacao_planilha_clientes(self):
        self.pack_forget()
        self.winfo_toplevel().title("Importa\u00e7\u00e3o de Clientes via Planilha - Implanta\u00e7\u00e3o Sistec")
        self.nome_tela_atual = "Importa\u00e7\u00e3o de Clientes via Planilha"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaImportacaoPlanilhaClientes(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_importacao_planilha_transportadora(self):
        self.pack_forget()
        self.winfo_toplevel().title("Importação de Transportadoras via Planilha - Implantação Sistec")
        self.nome_tela_atual = "Importação de Transportadoras via Planilha"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaImportacaoPlanilhaTransportadora(
            self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_importacao_planilha_receber(self):
        self.pack_forget()
        self.winfo_toplevel().title("Importa\u00e7\u00e3o de Contas a Receber via Planilha - Implanta\u00e7\u00e3o Sistec")
        self.nome_tela_atual = "Importa\u00e7\u00e3o de Contas a Receber via Planilha"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaImportacaoPlanilhaReceber(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_importacao_planilha_pagar(self):
        self.pack_forget()
        self.winfo_toplevel().title("Importa\u00e7\u00e3o de Contas a Pagar via Planilha - Implanta\u00e7\u00e3o Sistec")
        self.nome_tela_atual = "Importa\u00e7\u00e3o de Contas a Pagar via Planilha"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaImportacaoPlanilhaPagar(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_importacao_planilha_lista_precos(self):
        self.pack_forget()
        self.winfo_toplevel().title("Importação de Lista de Preços via Planilha - Implantação Sistec")
        self.nome_tela_atual = "Importação de Lista de Preços via Planilha"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaImportacaoPlanilhaListaPrecos(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_importacao_planilha_tributacao(self):
        self.pack_forget()
        self.winfo_toplevel().title("Importação de Tributação via Planilha - Implantação Sistec")
        self.nome_tela_atual = "Importação de Tributação via Planilha"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaImportacaoPlanilhaTributacao(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_importacao_planilha_estoque_producao(self):
        self.pack_forget()
        self.winfo_toplevel().title("Importação de Estoque de Produção via Planilha - Implantação Sistec")
        self.nome_tela_atual = "Importação de Estoque de Produção via Planilha"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaImportacaoPlanilhaEstoqueProducao(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_importacao_nfe(self):
        self.pack_forget()
        self.winfo_toplevel().title("Importação de Notas Fiscais (XML) - Implantação Sistec")
        self.nome_tela_atual = "Importação de Notas Fiscais (XML)"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaImportacaoNFe(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_duplicar_empresa(self):
        self.pack_forget()
        self.winfo_toplevel().title("Duplicar / Configurar Empresa - Implantação Sistec")
        self.nome_tela_atual = "Duplicar / Configurar Empresa"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaDuplicarEmpresa(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_vinculo_cc(self):
        self.pack_forget()
        self.winfo_toplevel().title("Vínculo CC × Plano de Contas - Implantação Sistec")
        self.nome_tela_atual = "Vínculo CC × Plano de Contas"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaVinculoCC(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_auditoria_produto(self):
        self.pack_forget()
        self.winfo_toplevel().title("Auditoria por Produto - Implantação Sistec")
        self.nome_tela_atual = "Auditoria por Produto"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaAuditoriaPorProduto(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_busca_logs(self):
        self._registrar_log("Busca de Logs ERP", "ABRIU")
        # Abre como uma janela sobreposta sem fechar a central (Toplevel nativo do módulo)
        BuscaLogsWindow(parent=self.winfo_toplevel())

    def _abrir_sobre(self):
        self._registrar_log("Sobre o Sistema", "ABRIU")
        TelaSobre(self.winfo_toplevel())

    def _voltar_inicial(self):
        if self.nome_tela_atual:
            self._registrar_log(self.nome_tela_atual, "SAIU")
            self.nome_tela_atual = None
        self.tela_atual = None # Limpa a referência para o Garbage Collector destruir a tela fechada
        self.winfo_toplevel().title("Implantação Sistec")
        self.pack(fill=tk.BOTH, expand=True) # Mostra a tela inicial de volta
        # Reassume a rolagem da roda do mouse (um módulo pode ter capturado o bind global)
        if hasattr(self, 'cards_canvas'):
            self.cards_canvas.bind_all("<MouseWheel>", self._on_mousewheel)


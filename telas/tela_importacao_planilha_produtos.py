import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import configparser
import threading
import os
import re

from utils.excel_reader import obter_abas_planilha, ler_planilha_produtos
from utils.firebird_service import FirebirdService
from utils.transformer import DataTransformer
from utils.importer import FirebirdImporter
from utils import tema

class TelaImportacaoPlanilhaProdutos(ttk.Frame):
    # Campos que a acao "Atualizar" pode gravar num produto que ja existe.
    # (chave, rotulo na tela, colunas da TABELA_PRODUTO)
    CAMPOS_UPDATE = [
        ('descricao', 'Descrição', ['PRODUTO_DESCRICAO', 'PRODUTO_DESCRICAO2']),
        ('ncm', 'NCM', ['PRODUTO_CLASS_FISCAL']),
        ('ean', 'Cód. Barras (EAN)', ['PRODUTO_CBARRA']),
        ('unidade', 'Unidade', ['PRODUTO_UNIDADE_CV', 'PRODUTO_UNIDADE_EST',
                                'PRODUTO_UN_EXP']),
        ('grupo', 'Grupo/Subgrupo', ['PRODUTO_GRUPO', 'PRODUTO_GRUPO_EMPRESA',
                                     'PRODUTO_GRUPO_FILIAL', 'PRODUTO_SUBGRUPO',
                                     'PRODUTO_SUBGRUPO_EMPRESA', 'PRODUTO_SUBGRUPO_FILIAL']),
        ('tipo', 'Tipo', ['PRODUTO_TIPO', 'PRODUTO_TIPO_PRODUTO_SPED']),
    ]

    def __init__(self, parent, callback_voltar=None):
        super().__init__(parent, padding="10")
        self.parent = parent
        self.callback_voltar = callback_voltar
        self.pack(fill=tk.BOTH, expand=True)

        self.registros_lidos = []
        self.caminho_arquivo = ""
        self.dados_grid = {}
        self.dados_analisados = []
        
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
            self, "Importar Produtos (Excel)",
            "Importação e auto-cadastro de produtos, grupos e subgrupos via planilha (XLSX/CSV)"
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
        ttk.Button(file_row, text="📁 Selecionar", command=self._selecionar_arquivo).pack(side=tk.LEFT, padx=2)

        tk.Label(file_row, text="Aba:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(10, 2))
        self.cb_abas = ttk.Combobox(file_row, width=16, state="readonly", font=("Segoe UI", 9))
        self.cb_abas.pack(side=tk.LEFT, padx=2)

        tk.Label(file_row, text="Linha Inicial:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(10, 2))
        self.ent_linha_ini = ttk.Entry(file_row, width=6, font=("Segoe UI", 9))
        self.ent_linha_ini.insert(0, "2")
        self.ent_linha_ini.pack(side=tk.LEFT, padx=2)

        # === CONFIG ROW ===
        config_row = ttk.Frame(content)
        config_row.pack(fill=tk.X, pady=2)

        tk.Label(config_row, text="Tipo:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 2))
        self.cb_tipo = ttk.Combobox(config_row, width=20, state="readonly", font=("Segoe UI", 9), values=[
            "1 - Revenda", "2 - Consumo", "3 - Matéria Prima",
            "4 - Produto Acabado", "5 - Serviços", "6 - Outros"
        ])
        self.cb_tipo.pack(side=tk.LEFT, padx=2)
        self.cb_tipo.set("4 - Produto Acabado")
        self.cb_tipo.bind("<<ComboboxSelected>>", lambda e: self._atualizar_tipo_preview())

        self.var_producao = tk.BooleanVar(self, value=False)
        ttk.Checkbutton(config_row, text="Produção Sistec", variable=self.var_producao).pack(side=tk.LEFT, padx=10)

        self.var_copiar_cod_import = tk.BooleanVar(self, value=False)
        ttk.Checkbutton(config_row, text="Cód. antigo → Auxiliar + Importação",
                        variable=self.var_copiar_cod_import).pack(side=tk.LEFT, padx=10)

        ttk.Separator(config_row, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=2)

        tk.Label(config_row, text="Código:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 2))
        self.var_modo_codigo = tk.StringVar(value="xml")
        ttk.Radiobutton(config_row, text="Seguir planilha", variable=self.var_modo_codigo, value="xml").pack(side=tk.LEFT, padx=2)
        ttk.Radiobutton(config_row, text="Sequencial", variable=self.var_modo_codigo, value="sequencial").pack(side=tk.LEFT, padx=2)

        # === CAMPOS QUE O "ATUALIZAR" GRAVA ===
        # Sem isso o UPDATE levava o dicionario inteiro do cadastro novo e
        # zerava tributacao, estoque e datas de um produto que ja existia.
        frame_upd = ttk.LabelFrame(
            content, text="Produto já cadastrado → 'Atualizar' grava só estes campos", padding="6")
        frame_upd.pack(fill=tk.X, pady=2)

        self.vars_update = {}
        marcados_padrao = {'ncm', 'ean', 'unidade'}
        for chave, rotulo, _cols in self.CAMPOS_UPDATE:
            var = tk.BooleanVar(self, value=chave in marcados_padrao)
            self.vars_update[chave] = var
            ttk.Checkbutton(frame_upd, text=rotulo, variable=var).pack(side=tk.LEFT, padx=6)
        tk.Label(frame_upd, text="(célula vazia na planilha não apaga o que está no ERP)",
                 font=("Segoe UI", 8, "italic"), fg="#666").pack(side=tk.LEFT, padx=10)

        # === COLUMN MAPPING ===
        self.frame_map = ttk.LabelFrame(
            content, padding="8",
            text="Mapeamento de Colunas (Insira a letra: A, B, C...)  •  "
                 "Grupo/Subgrupo aceitam código, descrição ou \"14 - MAIALE DUROC\"")
        self.frame_map.pack(fill=tk.X, pady=4)
        frame_map = self.frame_map

        labels_map = [
            ("Código Antigo:", "codigo_antigo"),
            ("Código Atual:", "codigo_atual"),
            ("Descrição *:", "descricao"),
            ("Grupo:", "grupo"),
            ("Subgrupo:", "subgrupo"),
            ("NCM:", "ncm"),
            ("Cód. Barras:", "ean"),
            ("Unidade:", "unidade"),
            ("Tipo:", "tipo"),
            ("Tipo Prod. Produção:", "tipo_prod_producao"),
        ]

        self.entradas_map = {}
        self._map_widgets = []   # (label, entry) para o rearranjo responsivo
        for lbl_texto, chave in labels_map:
            lbl = tk.Label(frame_map, text=lbl_texto, font=("Segoe UI", 8, "bold"))
            ent = ttk.Entry(frame_map, width=5, font=("Segoe UI", 9))
            self.entradas_map[chave] = ent
            self._map_widgets.append((lbl, ent))

        self._map_por_linha = 0
        self._reorganizar_mapa(por_linha=4)  # layout inicial
        # Recalcula quantos campos cabem por linha conforme a largura (tela pequena → quebra)
        self.frame_map.bind("<Configure>", self._on_map_resize)

        # === ACTIONS + PROGRESS ===
        actions_row = ttk.Frame(content)
        actions_row.pack(fill=tk.X, pady=4)

        ttk.Button(actions_row, text="☑ Marcar Todos", command=self._marcar_todos).pack(side=tk.LEFT, padx=3)
        ttk.Button(actions_row, text="☐ Desmarcar", command=self._desmarcar_todos).pack(side=tk.LEFT, padx=3)
        ttk.Button(actions_row, text="🔄 Marcar Já Cadastrados p/ Atualizar",
                   command=self._marcar_atualizar).pack(side=tk.LEFT, padx=3)

        self.lbl_hint = tk.Label(actions_row, text="Clique em SEL ou AÇÃO para alterar",
                                 font=("Segoe UI", 8, "italic"), fg="#666")
        self.lbl_hint.pack(side=tk.LEFT, padx=10)

        self.progresso = ttk.Progressbar(actions_row, orient=tk.HORIZONTAL, mode='determinate', length=120)
        self.progresso.pack(side=tk.LEFT, padx=8)

        self.lbl_status = ttk.Label(actions_row, text="Aguardando configuração...", font=("Segoe UI", 9), foreground="#555")
        self.lbl_status.pack(side=tk.LEFT, padx=2)

        # === TREEVIEW ===
        frame_grade = ttk.Frame(content)
        frame_grade.pack(fill=tk.BOTH, expand=True, pady=4)

        self.colunas = ("SEL", "AÇÃO", "STATUS", "CÓDIGO ANTIGO", "DESCRIÇÃO NA PLANILHA",
                        "CÓD. ERP", "DESCRIÇÃO NO ERP", "TIPO", "GRUPO", "SUBGRUPO",
                        "NCM", "EAN", "UNID", "CÓD. ATUAL")
        # Índice de cada coluna pelo nome. As posições mudam quando se acrescenta
        # coluna; ler por nome evita o bug de pegar o valor da coluna vizinha.
        self._ci = {nome: i for i, nome in enumerate(self.colunas)}
        self.tree = ttk.Treeview(frame_grade, columns=self.colunas, show="headings")

        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)

        larguras = [40, 100, 190, 100, 230, 70, 230, 120, 150, 150, 80, 100, 60, 100]
        esquerda = {"DESCRIÇÃO NA PLANILHA", "DESCRIÇÃO NO ERP", "GRUPO", "SUBGRUPO"}
        for col, larg in zip(self.colunas, larguras):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=larg, anchor=tk.W if col in esquerda else tk.CENTER)

        self.tree.tag_configure('ERRO', background=tema.ERROR_CT)
        self.tree.tag_configure('OK', background=tema.SUCCESS_CT)
        self.tree.tag_configure('NOVO', background=tema.INFO_CT)
        self.tree.tag_configure('DIVERGENTE', background=tema.WARNING_CT)

        scroll_y = ttk.Scrollbar(frame_grade, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        # === FILTER BAR ===
        filter_frame = ttk.Frame(content)
        filter_frame.pack(fill=tk.X, pady=(2, 4))

        tk.Label(filter_frame, text="Filtrar Status:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 5))
        self.cb_filtro_status = ttk.Combobox(filter_frame, values=["TODOS", "NOVO", "JÁ CADASTRADO", "DIVERGENTE", "ERRO"],
                                              state="readonly", width=18, font=("Segoe UI", 9))
        self.cb_filtro_status.pack(side=tk.LEFT, padx=2)
        self.cb_filtro_status.set("TODOS")
        self.cb_filtro_status.bind("<<ComboboxSelected>>", self._aplicar_filtro_status)

        self.lbl_filtro_info = tk.Label(filter_frame, text="", font=("Segoe UI", 8), fg="#555")
        self.lbl_filtro_info.pack(side=tk.LEFT, padx=10)

    def _reorganizar_mapa(self, por_linha):
        """Reposiciona os campos de mapeamento em N por linha (quebra em tela estreita)."""
        por_linha = max(1, int(por_linha))
        if por_linha == self._map_por_linha:
            return
        self._map_por_linha = por_linha
        for i, (lbl, ent) in enumerate(self._map_widgets):
            linha = i // por_linha
            col = (i % por_linha) * 2
            lbl.grid(row=linha, column=col, padx=(5, 1), pady=4, sticky=tk.E)
            ent.grid(row=linha, column=col + 1, padx=(0, 8), pady=4, sticky=tk.W)

    def _on_map_resize(self, event):
        """Recalcula quantos campos cabem por linha conforme a largura disponível."""
        total = len(self._map_widgets)
        por_linha = max(1, min(total, event.width // 150))  # ~150px por campo
        self._reorganizar_mapa(por_linha)

    def _selecionar_arquivo(self):
        path = filedialog.askopenfilename(filetypes=[("Arquivos Suportados", "*.xlsx *.csv"), ("Excel", "*.xlsx"), ("CSV", "*.csv")])
        if path:
            self.ent_arquivo.delete(0, tk.END)
            self.ent_arquivo.insert(0, path)
            self.caminho_arquivo = path
            
            abas = obter_abas_planilha(path)
            self.cb_abas['values'] = abas
            if abas: self.cb_abas.current(0)

    def _salvar_config_mapeamento(self):
        self.config['IMPORTACAO_PRODUTOS'] = {
            'ultimo_arquivo': self.caminho_arquivo,
            'ultima_aba': self.cb_abas.get(),
            'linha_inicial': self.ent_linha_ini.get(),
            'tipo': self.cb_tipo.get(),
            'producao_sistec': 'S' if self.var_producao.get() else 'N',
            'modo_codigo': self.var_modo_codigo.get(),
            'copiar_cod_import': 'S' if self.var_copiar_cod_import.get() else 'N',
        }
        for chave, ent in self.entradas_map.items():
            self.config['IMPORTACAO_PRODUTOS'][f'mapa_{chave}'] = ent.get().strip()
        for chave, var in self.vars_update.items():
            self.config['IMPORTACAO_PRODUTOS'][f'upd_{chave}'] = 'S' if var.get() else 'N'
        with open('config.ini', 'w', encoding='utf-8') as f:
            self.config.write(f)

    def _carregar_config_mapeamento(self):
        if self.config.has_section('IMPORTACAO_PRODUTOS'):
            cfg = self.config['IMPORTACAO_PRODUTOS']
            arquivo = cfg.get('ultimo_arquivo', '')
            if arquivo:
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
            tipo = cfg.get('tipo', '')
            if tipo in self.cb_tipo['values']:
                self.cb_tipo.set(tipo)
            self.var_producao.set(cfg.get('producao_sistec', 'N') == 'S')
            self.var_modo_codigo.set(cfg.get('modo_codigo', 'xml'))
            self.var_copiar_cod_import.set(cfg.get('copiar_cod_import', 'N') == 'S')
            for chave, ent in self.entradas_map.items():
                val = cfg.get(f'mapa_{chave}', '')
                if val:
                    ent.delete(0, tk.END)
                    ent.insert(0, val)
            for chave, var in self.vars_update.items():
                val = cfg.get(f'upd_{chave}', '')
                if val:
                    var.set(val == 'S')

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
        if not mapa_colunas.get('descricao'):
            return messagebox.showwarning("Aviso", "Você precisa mapear obrigatoriamente a letra da coluna 'Descrição'.")

        self._salvar_config_mapeamento()
        self.btn_analisar.config(state=tk.DISABLED)
        self.lbl_status.config(text="Lendo planilha...")
        self.progresso['value'] = 20
        
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

            produtos_erp = {}
            codigos_pk_erp = set()   # só PRODUTO_CODIGO (a PK) — sem os auxiliares
            g_cod = g_desc = s_cod = s_desc = None
            try:
                with FirebirdService(self.config_db) as fb:
                    g_cod, g_desc, s_cod, s_desc = self._carregar_grupos_erp(fb, emp, fil)
                    rows = fb.query(
                        "SELECT PRODUTO_CODIGO, PRODUTO_COD_AUXILIAR, PRODUTO_DESCRICAO, "
                        "PRODUTO_CLASS_FISCAL, PRODUTO_UNIDADE_CV "
                        "FROM TABELA_PRODUTO WHERE PRODUTO_EMPRESA = ? AND PRODUTO_FILIAL = ?",
                        [emp, fil]
                    )
                    for row in rows:
                        cod = str(row.get('produto_codigo', '')).strip()
                        aux = str(row.get('produto_cod_auxiliar', '')).strip()
                        desc = str(row.get('produto_descricao', '')).strip()
                        info = {'codigo': cod, 'descricao': desc,
                                'ncm': str(row.get('produto_class_fiscal') or '').strip(),
                                'unidade': str(row.get('produto_unidade_cv') or '').strip()}
                        if cod:
                            produtos_erp[cod] = info
                            codigos_pk_erp.add(cod)
                        if aux: produtos_erp[aux] = info
            except Exception as e:
                self.parent.after(0, lambda err=e: messagebox.showwarning("Erro DB", f"Falha ao consultar ERP:\n{err}"))
                self.parent.after(0, lambda: self.btn_analisar.config(state=tk.NORMAL))
                return

            self.parent.after(0, lambda: self.lbl_status.config(text="Processando e montando tabela..."))
            self.parent.after(0, lambda: self.progresso.config(value=50))

            self.dados_analisados = []
            total = len(self.registros_lidos)
            # "Código Atual" vira o PRODUTO_CODIGO (a PK). Precisa ser conferido
            # aqui: se colidir com o ERP ou repetir na planilha, o INSERT morre
            # com SQLCODE -803 e a transacao inteira e descartada.
            cod_atual_vistos = {}

            def match_produto(cod_planilha, desc_planilha, reg=None):
                if cod_planilha and cod_planilha in produtos_erp:
                    info = produtos_erp[cod_planilha]
                    desc_erp = info['descricao'].lower().strip()
                    desc_plan = desc_planilha.lower().strip()
                    # O que exatamente divergiu — antes so dizia "DIVERGENTE" e
                    # nao havia como saber olhando a tela.
                    difs = []
                    if not (desc_plan == desc_erp or (desc_plan and desc_erp and
                            (desc_plan in desc_erp or desc_erp in desc_plan))):
                        difs.append('descrição')
                    ncm_p = re.sub(r'\D', '', str((reg or {}).get('ncm') or ''))
                    ncm_e = re.sub(r'\D', '', info.get('ncm') or '')
                    if ncm_p and ncm_e and ncm_p != ncm_e:
                        difs.append(f"NCM {ncm_e}→{ncm_p}")
                    un_p = str((reg or {}).get('unidade') or '').strip().upper()[:2]
                    un_e = (info.get('unidade') or '').strip().upper()[:2]
                    if un_p and un_e and un_p != un_e:
                        difs.append(f"unidade {un_e}→{un_p}")
                    if difs:
                        return f"DIVERGENTE ({', '.join(difs)})", info
                    return 'JÁ CADASTRADO', info
                if desc_planilha:
                    # Só considera duplicado por nome quando a descrição é IDÊNTICA.
                    # (Antes usava "contida em", que cruzava produtos sem relação:
                    #  ex. "PEITO" batia com "FILE DE PEITO".)
                    dl = desc_planilha.lower().strip()
                    for p_cod, p_info in produtos_erp.items():
                        if dl == p_info['descricao'].lower().strip():
                            return "JÁ CADASTRADO (~desc)", p_info
                return None, None

            for idx, reg in enumerate(self.registros_lidos):
                cod_planilha = str(reg.get('codigo_antigo', '')).strip()
                cod_atual_planilha = str(reg.get('codigo_atual', '')).strip()
                desc_planilha = str(reg.get('descricao', '')).strip()

                if not desc_planilha:
                    status = "ERRO (Sem Descrição)"
                    tag = "ERRO"
                    sel = "☐"
                    acao = "—"
                else:
                    match_label, matched_info = match_produto(cod_planilha, desc_planilha, reg)
                    if match_label and match_label.startswith('DIVERGENTE'):
                        status = match_label
                        tag = "DIVERGENTE"
                        sel = "☐"
                        acao = "Atualizar"
                    elif match_label:
                        status = match_label
                        tag = "OK"
                        sel = "☐"
                        acao = "Criar Novo" if "~desc" in match_label else "Ignorar"
                    else:
                        status = "NOVO"
                        tag = "NOVO"
                        sel = "☑"
                        acao = "Importar"

                # Validacao do "Código Atual" — só para as linhas que vao INSERIR
                # (as "Atualizar" gravam no codigo que ja existe no ERP).
                if cod_atual_planilha and acao in ("Importar", "Criar Novo"):
                    if cod_atual_planilha in codigos_pk_erp:
                        ocupa = produtos_erp[cod_atual_planilha]['descricao']
                        status = (f"ERRO (Cód. Atual {cod_atual_planilha} já é do "
                                  f"produto '{ocupa[:28]}')")
                        tag, sel, acao = "ERRO", "☐", "—"
                    elif cod_atual_planilha in cod_atual_vistos:
                        outra = cod_atual_vistos[cod_atual_planilha]
                        status = (f"ERRO (Cód. Atual {cod_atual_planilha} repetido na "
                                  f"planilha — linha {outra})")
                        tag, sel, acao = "ERRO", "☐", "—"
                    else:
                        cod_atual_vistos[cod_atual_planilha] = linha_ini + idx

                # Tipo: se a coluna foi mapeada e a celula tem valor, usa ela;
                # senao, cai no seletor global da tela (tipo_id = None).
                tipo_id_plan, tipo_label = self._resolver_tipo(reg.get('tipo', ''))
                if tipo_id_plan is None:
                    tipo_label = self.cb_tipo.get()

                # Grupo/Subgrupo: a celula pode trazer codigo, descricao ou os
                # dois. Resolver aqui deixa visivel na grade o que sera gravado
                # (antes, "14" era tratado como nome e criava um grupo "14").
                cel_grupo = reg.get('grupo', '')
                cel_sub = reg.get('subgrupo', '')
                grupo_id = subgrupo_id = None
                grupo_lbl = sub_lbl = ''
                erro_gs = ''
                if g_cod is not None:
                    grupo_id, grupo_lbl, err = self._resolver_grupo(cel_grupo, g_cod, g_desc)
                    if err:
                        erro_gs = f"Grupo: {err}"
                    elif not str(cel_grupo).strip():
                        grupo_lbl = "⚠ sem grupo → 1"
                    if not str(cel_sub).strip():
                        # Subgrupo em branco herda o nome do grupo (como antes),
                        # agora tambem quando o grupo veio por codigo.
                        cel_sub = (g_cod.get(grupo_id) if grupo_id is not None
                                   else self._ref_grupo(cel_grupo)[1])
                    if grupo_id is not None:
                        subgrupo_id, sub_lbl, err = self._resolver_grupo(
                            cel_sub, s_cod.get(grupo_id, {}), s_desc.get(grupo_id, {}))
                        if err and not erro_gs:
                            erro_gs = f"Subgrupo: {err}"
                    else:
                        # o grupo ainda vai ser criado, entao codigo de subgrupo
                        # nao tem contra o que ser conferido
                        cod_sub, desc_sub = self._ref_grupo(cel_sub)
                        if cod_sub is not None and not desc_sub:
                            if not erro_gs:
                                erro_gs = (f"Subgrupo: código {cod_sub} não pode ser "
                                           f"usado porque o grupo ainda será criado")
                        elif desc_sub:
                            sub_lbl = f"➕ NOVO: {desc_sub}"

                if erro_gs and tag != "ERRO":
                    status = f"ERRO ({erro_gs})"
                    tag, sel, acao = "ERRO", "☐", "—"

                # nomes usados na auto-criacao, quando nao existirem no ERP
                grupo_desc_nova = self._ref_grupo(cel_grupo)[1]
                subgrupo_desc_nova = self._ref_grupo(cel_sub)[1]

                item = {
                    'sel': sel, 'acao': acao, 'status': status, 'tag': tag,
                    'codigo_antigo': cod_planilha, 'codigo_atual': cod_atual_planilha,
                    'descricao': desc_planilha,
                    'codigo_erp': matched_info.get('codigo', '') if matched_info else '',
                    'desc_erp': matched_info.get('descricao', '') if matched_info else '',
                    'tipo': tipo_label,
                    'tipo_id': tipo_id_plan,
                    'grupo': cel_grupo,
                    'subgrupo': reg.get('subgrupo', ''),
                    'grupo_id': grupo_id,
                    'subgrupo_id': subgrupo_id,
                    'grupo_label': grupo_lbl,
                    'subgrupo_label': sub_lbl,
                    'grupo_desc_nova': grupo_desc_nova,
                    'subgrupo_desc_nova': subgrupo_desc_nova,
                    'ncm': reg.get('ncm', ''),
                    'ean': reg.get('ean', ''),
                    'unidade': reg.get('unidade', ''),
                    'tipo_prod_producao': str(reg.get('tipo_prod_producao', '')).strip(),
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
            self.parent.after(0, lambda err=e: messagebox.showerror("Erro", f"Falha na análise:\n{err}"))
            self.parent.after(0, lambda: self.btn_analisar.config(state=tk.NORMAL))

    def _valores_linha(self, item):
        """Valores da linha, na ordem de self.colunas."""
        return (
            item['sel'], item['acao'], item['status'],
            item['codigo_antigo'], item['descricao'],
            item.get('codigo_erp', ''), item.get('desc_erp', ''),
            item['tipo'],
            item.get('grupo_label') or item.get('grupo', ''),
            item.get('subgrupo_label') or item.get('subgrupo', ''),
            item['ncm'], item['ean'], item['unidade'],
            item.get('codigo_atual', ''),
        )

    def _dados_linha(self, item):
        """O que a importação precisa da linha (guardado por item_id da grade)."""
        return {
            'codigo_antigo': item['codigo_antigo'],
            'codigo_atual': item.get('codigo_atual', ''),
            'descricao': item['descricao'],
            'codigo_erp': item.get('codigo_erp', ''),
            'desc_erp': item.get('desc_erp', ''),
            'tipo': item.get('tipo', ''),
            'tipo_id': item.get('tipo_id'),
            'grupo': item.get('grupo', ''),
            'subgrupo': item.get('subgrupo', ''),
            'grupo_id': item.get('grupo_id'),
            'subgrupo_id': item.get('subgrupo_id'),
            'grupo_desc_nova': item.get('grupo_desc_nova', ''),
            'subgrupo_desc_nova': item.get('subgrupo_desc_nova', ''),
            'ncm': item['ncm'],
            'ean': item['ean'],
            'unidade': item['unidade'],
            'tipo_prod_producao': item.get('tipo_prod_producao', ''),
            '_status': 'OK' if item['tag'] == 'NOVO' else 'SKIP',
        }

    def _renderizar_preview(self):
        # Selo deste render. A grade e preenchida em blocos com after(), entao um
        # render antigo pode continuar inserindo DEPOIS que outro limpou a tela —
        # a grade acumula duas analises e os totais somam tudo. O selo faz os
        # blocos do render antigo pararem.
        self._render_seq = getattr(self, '_render_seq', 0) + 1
        meu_seq = self._render_seq

        for i in self.tree.get_children(): self.tree.delete(i)
        self.dados_grid.clear()

        total = len(self.dados_analisados)
        if total == 0:
            self.btn_analisar.config(state=tk.NORMAL)
            self.lbl_status.config(text="Nenhum registro válido encontrado.")
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
                item_id = self.tree.insert("", tk.END, values=self._valores_linha(item),
                                           tags=(item['tag'],))
                self.dados_grid[item_id] = self._dados_linha(item)

            if end_idx < total:
                self.lbl_status.config(text=f"Renderizando {end_idx}/{total}...")
                self.update_idletasks()
                self.parent.after(5, render_chunk, end_idx)
            else:
                self.btn_analisar.config(state=tk.NORMAL)
                novo_count = sum(1 for d in dados if d['tag'] == 'NOVO')
                div_count = sum(1 for d in dados if d['tag'] == 'DIVERGENTE')
                # 'JÁ CADASTRADO' agora tambem pode ser atualizado, entao o botao
                # nao depende mais de existir novo/divergente
                if any(self._ciclo_acoes(d['status']) for d in dados):
                    self.btn_importar.config(state=tk.NORMAL)
                self.progresso['value'] = 100
                status_parts = [f"{novo_count} novos"]
                if div_count:
                    status_parts.append(f"{div_count} divergentes")
                status_parts.append(f"{total} lidos")
                self.lbl_status.config(
                    text=f"Pronto. {', '.join(status_parts)} na planilha."
                )
                self.lbl_filtro_info.config(text=f"Exibindo {total} de {total} registros")

        render_chunk(0)

    def _atualizar_tipo_preview(self):
        if not self.tree.get_children(): return
        novo_tipo = self.cb_tipo.get()
        for item in self.tree.get_children():
            dg = self.dados_grid.get(item, {})
            if dg.get('tipo_id'):  # tipo veio mapeado da planilha, nao sobrescreve
                continue
            valores = list(self.tree.item(item, "values"))
            valores[self._ci['TIPO']] = novo_tipo
            self.tree.item(item, values=valores)

    def _resolver_tipo(self, valor):
        """Resolve o valor da coluna 'Tipo' da planilha para (id, label).
        Aceita numero (1-6) ou nome (Revenda, Consumo, Materia Prima, Produto
        Acabado, Servicos, Outros). Retorna (None, '') quando vazio ou nao
        reconhecido, sinalizando que deve usar o seletor global da tela."""
        import re as _re
        import unicodedata
        v = str(valor or '').strip()
        if not v:
            return None, ''
        labels = {1: '1 - Revenda', 2: '2 - Consumo', 3: '3 - Matéria Prima',
                  4: '4 - Produto Acabado', 5: '5 - Serviços', 6: '6 - Outros'}
        m = _re.match(r'(\d+)', v)
        if m:
            tid = int(m.group(1))
            return (tid, labels[tid]) if 1 <= tid <= 6 else (None, '')
        chave = ''.join(c for c in unicodedata.normalize('NFKD', v.upper())
                        if not unicodedata.combining(c)).strip()
        nomes = {
            'REVENDA': 1, 'CONSUMO': 2, 'MATERIA PRIMA': 3, 'MATERIA-PRIMA': 3,
            'PRODUTO ACABADO': 4, 'SERVICOS': 5, 'SERVICO': 5, 'OUTROS': 6,
        }
        tid = nomes.get(chave)
        return (tid, labels[tid]) if tid else (None, '')

    # ============ Grupo / Subgrupo: aceita código OU descrição ============

    @staticmethod
    def _ref_grupo(valor):
        """Interpreta a célula de Grupo/Subgrupo da planilha.

        Aceita as três formas que o cliente usa: código ("14", ou "14.0" quando
        o Excel entrega a célula como número), descrição ("MAIALE DUROC") ou as
        duas juntas ("14 - MAIALE DUROC"). Devolve (codigo|None, descrição|'').
        """
        v = str(valor or '').strip()
        if not v:
            return None, ''
        m = re.match(r'^(\d+)(?:[.,]0+)?$', v)
        if m:
            return int(m.group(1)), ''
        # "14 - MAIALE DUROC": exige letra depois do traço para não quebrar
        # descrição do tipo "13-15 KG".
        m = re.match(r'^(\d+)\s*[-–]\s*([^\W\d_].*)$', v, re.UNICODE)
        if m:
            return int(m.group(1)), m.group(2).strip().upper()
        return None, v.upper()

    @staticmethod
    def _resolver_grupo(valor, por_codigo, por_desc):
        """Resolve a célula contra o cadastro do ERP.

        por_codigo: {codigo: descricao} | por_desc: {DESCRICAO: codigo}
        Devolve (codigo|None, label, erro|''):
          - achou            -> (14, '14 - MAIALE DUROC', '')
          - vazio            -> (None, '', '')
          - descrição nova   -> (None, '➕ NOVO: LINGUICAS', '')   (será criada)
          - código inexistente -> (None, '', 'Grupo 99 não existe no ERP')
        """
        cod, desc = TelaImportacaoPlanilhaProdutos._ref_grupo(valor)
        if cod is None and not desc:
            return None, '', ''
        if cod is not None:
            if cod in por_codigo:
                return cod, f"{cod} - {por_codigo[cod]}", ''
            # veio código, mas ele não existe: criar um grupo chamado "99" seria
            # lixo no cadastro do cliente, então a linha para aqui.
            if desc and desc in por_desc:
                achado = por_desc[desc]
                return achado, f"{achado} - {por_codigo[achado]}", ''
            return None, '', f"código {cod} não existe no ERP"
        if desc in por_desc:
            achado = por_desc[desc]
            return achado, f"{achado} - {por_codigo[achado]}", ''
        return None, f"➕ NOVO: {desc}", ''

    def _carregar_grupos_erp(self, fb, emp, fil):
        """Lê grupos e subgrupos do ERP para resolver as células da planilha."""
        g_cod, g_desc = {}, {}
        for g in fb.query("SELECT GRUPO_CODIGO, GRUPO_DESCRICAO FROM TABELA_GRUPO "
                          "WHERE GRUPO_EMPRESA = ? AND GRUPO_FILIAL = ?", [emp, fil]):
            cod = int(g.get('grupo_codigo') or 0)
            desc = str(g.get('grupo_descricao') or '').strip().upper()
            g_cod[cod] = desc
            g_desc.setdefault(desc, cod)
        # subgrupo é por grupo: o código 1 existe em vários grupos
        s_cod, s_desc = {}, {}
        for s in fb.query("SELECT SUBGRUPO_CODIGO, SUBGRUPO_DESCRICAO, SUBGRUPO_GRUPO "
                          "FROM TABELA_SUBGRUPO WHERE SUBGRUPO_EMPRESA = ? "
                          "AND SUBGRUPO_FILIAL = ?", [emp, fil]):
            grp = int(s.get('subgrupo_grupo') or 0)
            cod = int(s.get('subgrupo_codigo') or 0)
            desc = str(s.get('subgrupo_descricao') or '').strip().upper()
            s_cod.setdefault(grp, {})[cod] = desc
            s_desc.setdefault(grp, {}).setdefault(desc, cod)
        return g_cod, g_desc, s_cod, s_desc

    @staticmethod
    def _ciclo_acoes(status):
        """Ações possíveis para a linha, na ordem em que o clique alterna.
        A primeira é a que o ☑ assume. Lista vazia = linha travada."""
        if "ERRO" in status:
            return []
        if status == "NOVO":
            return ["Importar", "Ignorar"]
        if "DIVERGENTE" in status:
            return ["Atualizar", "Criar Novo", "Ignorar"]
        if "~desc" in status:
            return ["Criar Novo", "Atualizar", "Ignorar"]
        if "JÁ CADASTRADO" in status:
            # antes ficava travado em "Ignorar"; agora permite atualizar os
            # campos marcados na tela (NCM, EAN, unidade...)
            return ["Atualizar", "Ignorar"]
        return []

    def _on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell": return
        column = self.tree.identify_column(event.x)
        item_id = self.tree.identify_row(event.y)
        if not item_id: return

        valores = list(self.tree.item(item_id, 'values'))
        status = valores[2]  # STATUS está no índice 2
        if "ERRO" in status: return
        ciclo = self._ciclo_acoes(status)
        if not ciclo: return

        if column == "#1":  # SEL
            if valores[0] == "☑":
                valores[0] = "☐"
                valores[1] = "Ignorar"
            else:
                valores[0] = "☑"
                valores[1] = ciclo[0]
            self.tree.item(item_id, values=valores)

        elif column == "#2":  # AÇÃO
            try:
                idx = ciclo.index(valores[1])
                valores[1] = ciclo[(idx + 1) % len(ciclo)]
            except ValueError:
                valores[1] = ciclo[0]
            valores[0] = "☑" if valores[1] != "Ignorar" else "☐"
            self.tree.item(item_id, values=valores)

    def _marcar_todos(self):
        """Marca novos/divergentes. Nao mexe nos 'JÁ CADASTRADO' exatos —
        atualizar em massa quem ja esta certo tem botao proprio."""
        for item in self.tree.get_children():
            v = list(self.tree.item(item, "values"))
            st = v[2]
            if st.startswith("JÁ CADASTRADO") and "~desc" not in st:
                continue
            ciclo = self._ciclo_acoes(st)
            if not ciclo:
                continue
            v[0] = "☑"
            v[1] = ciclo[0]
            self.tree.item(item, values=v)

    def _marcar_atualizar(self):
        """Marca para 'Atualizar' tudo que ja existe no ERP (exato, divergente
        ou casado pela descricao)."""
        n = 0
        for item in self.tree.get_children():
            v = list(self.tree.item(item, "values"))
            if "Atualizar" not in self._ciclo_acoes(v[2]):
                continue
            if not str(self.dados_grid.get(item, {}).get('codigo_erp', '')).strip():
                continue
            v[0] = "☑"
            v[1] = "Atualizar"
            self.tree.item(item, values=v)
            n += 1
        campos = [r for c, r, _ in self.CAMPOS_UPDATE if self.vars_update[c].get()]
        self.lbl_status.config(
            text=f"{n} linha(s) marcadas para Atualizar "
                 f"({', '.join(campos) if campos else 'NENHUM campo marcado!'})")

    def _desmarcar_todos(self):
        for item in self.tree.get_children():
            v = list(self.tree.item(item, "values"))
            if v[0] == "☑":
                v[0] = "☐"
                v[1] = "Ignorar"
                self.tree.item(item, values=v)

    def _aplicar_filtro_status(self, event=None):
        filtro = self.cb_filtro_status.get()
        for i in self.tree.get_children():
            self.tree.delete(i)
        self.dados_grid.clear()

        dados = self.dados_analisados
        if not dados:
            self.lbl_filtro_info.config(text="")
            return

        filtro_para_tags = {
            "NOVO": {"NOVO"},
            "JÁ CADASTRADO": {"OK"},
            "DIVERGENTE": {"DIVERGENTE"},
            "ERRO": {"ERRO"},
        }
        tags_ativas = filtro_para_tags.get(filtro)
        total = len(dados)
        count = 0

        for item in dados:
            if tags_ativas is not None and item['tag'] not in tags_ativas:
                continue
            count += 1
            item_id = self.tree.insert("", tk.END, values=self._valores_linha(item),
                                       tags=(item['tag'],))
            self.dados_grid[item_id] = self._dados_linha(item)

        self.lbl_filtro_info.config(text=f"Exibindo {count} de {total} registros")

    def _iniciar_importacao(self):
        selecionados = []
        for item_id in self.tree.get_children():
            valores = self.tree.item(item_id, "values")
            if valores[0] == "☑":
                dados = dict(self.dados_grid[item_id])
                dados['_acao'] = valores[1]
                selecionados.append(dados)

        if not selecionados:
            messagebox.showwarning("Aviso", "Selecione pelo menos um produto para importar.")
            return

        n_upd = sum(1 for d in selecionados if d.get('_acao') == 'Atualizar')
        n_ins = len(selecionados) - n_upd
        campos = [r for c, r, _cols in self.CAMPOS_UPDATE if self.vars_update[c].get()]
        if n_upd and not campos:
            return messagebox.showwarning(
                "Aviso", f"{n_upd} linha(s) estão como 'Atualizar', mas nenhum campo "
                         f"está marcado em \"Produto já cadastrado → 'Atualizar' grava "
                         f"só estes campos\".\n\nMarque o que deve ser atualizado "
                         f"(NCM, EAN, unidade...) ou troque a ação para Ignorar.")

        partes = []
        if n_ins:
            partes.append(f"cadastrar {n_ins} produto(s) novo(s)")
        if n_upd:
            partes.append(f"atualizar {n_upd} já existente(s) — só {', '.join(campos)}")
        resp = messagebox.askyesno(
            "Confirmar",
            "Deseja " + " e ".join(partes) + " no Banco de Dados?\n"
            "Essa ação não pode ser desfeita.")
        if resp:
            self.btn_importar.config(state=tk.DISABLED)
            self.btn_analisar.config(state=tk.DISABLED)
            self.lbl_status.config(text="Construindo grupos e injetando produtos...")

            # Coleta os valores da interface na thread principal (evita falha silenciosa de leitura no background)
            tipo_sel = self.cb_tipo.get()
            prod_sistec = 'S' if self.var_producao.get() else 'N'
            modo_codigo = self.var_modo_codigo.get()
            copiar_cod_import = self.var_copiar_cod_import.get()
            campos_update = {c for c, _r, _cols in self.CAMPOS_UPDATE
                             if self.vars_update[c].get()}

            threading.Thread(target=self._importacao_bg,
                             args=(selecionados, tipo_sel, prod_sistec, modo_codigo,
                                   copiar_cod_import, campos_update),
                             daemon=True).start()

    def _resolver_ids_gravacao(self, fb, emp, fil, grupo_id, subgrupo_id,
                               desc_grupo, desc_sub, mapa_grupos, mapa_subgrupos):
        """Devolve (grupo_id, subgrupo_id) para gravar.

        O que a análise já resolveu (por código ou por descrição existente) é
        usado direto. Só cria grupo/subgrupo quando a planilha trouxe um nome
        que não existe no ERP — e nunca cria grupo chamado "14", porque código
        inexistente já barra a linha na análise.
        """
        if grupo_id is None and desc_grupo:
            if desc_grupo in mapa_grupos:
                grupo_id = mapa_grupos[desc_grupo]
            else:
                res = fb.query("SELECT COALESCE(MAX(GRUPO_CODIGO), 0) + 1 AS NOVO FROM TABELA_GRUPO WHERE GRUPO_EMPRESA = ? AND GRUPO_FILIAL = ?", [emp, fil])
                grupo_id = int(res[0]['novo'])
                fb.execute("INSERT INTO TABELA_GRUPO (GRUPO_EMPRESA, GRUPO_FILIAL, GRUPO_CODIGO, GRUPO_DESCRICAO) VALUES (?, ?, ?, ?)", [emp, fil, grupo_id, desc_grupo[:60]])
                mapa_grupos[desc_grupo] = grupo_id

        if grupo_id is None:
            return 1, 1

        if subgrupo_id is None and desc_sub:
            chave_sub = f"{grupo_id}_{desc_sub}"
            if chave_sub in mapa_subgrupos:
                subgrupo_id = mapa_subgrupos[chave_sub]
            else:
                res = fb.query("SELECT COALESCE(MAX(SUBGRUPO_CODIGO), 0) + 1 AS NOVO FROM TABELA_SUBGRUPO WHERE SUBGRUPO_EMPRESA = ? AND SUBGRUPO_FILIAL = ? AND SUBGRUPO_GRUPO = ?", [emp, fil, grupo_id])
                subgrupo_id = int(res[0]['novo'])
                fb.execute("INSERT INTO TABELA_SUBGRUPO (SUBGRUPO_EMPRESA, SUBGRUPO_FILIAL, SUBGRUPO_GRUPO_EMPRESA, SUBGRUPO_GRUPO_FILIAL, SUBGRUPO_GRUPO, SUBGRUPO_CODIGO, SUBGRUPO_DESCRICAO) VALUES (?, ?, ?, ?, ?, ?, ?)", [emp, fil, emp, fil, grupo_id, subgrupo_id, desc_sub[:60]])
                mapa_subgrupos[chave_sub] = subgrupo_id

        return grupo_id, (subgrupo_id if subgrupo_id is not None else 1)

    def _montar_update(self, item, base, campos_on):
        """SET do UPDATE: só os campos marcados na tela e que realmente têm
        valor na planilha (célula vazia não apaga o que está no ERP)."""
        tem_valor = {
            'descricao': bool(str(item.get('descricao', '')).strip()),
            'ncm': bool(str(item.get('ncm', '')).strip()),
            'ean': bool(base.get('PRODUTO_CBARRA')),
            'unidade': bool(str(item.get('unidade', '')).strip()),
            'grupo': item.get('grupo_id') is not None or bool(
                str(item.get('grupo_desc_nova') or '').strip()),
            'tipo': True,
        }
        upd = {}
        for chave, _rotulo, colunas in self.CAMPOS_UPDATE:
            if chave not in campos_on or not tem_valor.get(chave):
                continue
            for col in colunas:
                if col in base:
                    upd[col] = base[col]
        return upd

    @staticmethod
    def _sanitizar(texto):
        if not isinstance(texto, str):
            return texto
        return texto.encode('cp1252', errors='replace').decode('cp1252')

    def _importacao_bg(self, selecionados, tipo_sel, prod_sistec, modo_codigo='xml',
                       copiar_cod_import=False, campos_update=None):
        sucesso = False
        campos_update = set(campos_update or ())
        sem_campo_update = []          # marcados p/ Atualizar sem nenhum campo a gravar
        tipos_prod_ignorados = set()   # valores de "Tipo Prod. Produção" que não eram numéricos
        try:
            emp = int(self.config.get('IMPORTACAO', 'empresa', fallback='1'))
            fil = int(self.config.get('IMPORTACAO', 'filial', fallback='1'))

            with FirebirdService(self.config_db) as fb:
                # Cache Grupos
                grupos_db = fb.query("SELECT GRUPO_CODIGO, GRUPO_DESCRICAO FROM TABELA_GRUPO WHERE GRUPO_EMPRESA = ? AND GRUPO_FILIAL = ?", [emp, fil])
                mapa_grupos = {str(g.get('grupo_descricao') or '').strip().upper(): int(g.get('grupo_codigo', 0)) for g in grupos_db}
                
                # Cache Subgrupos
                subgrupos_db = fb.query("SELECT SUBGRUPO_CODIGO, SUBGRUPO_DESCRICAO, SUBGRUPO_GRUPO FROM TABELA_SUBGRUPO WHERE SUBGRUPO_EMPRESA = ? AND SUBGRUPO_FILIAL = ?", [emp, fil])
                mapa_subgrupos = {f"{s.get('subgrupo_grupo')}_{str(s.get('subgrupo_descricao') or '').strip().upper()}": int(s.get('subgrupo_codigo', 0)) for s in subgrupos_db}

                # Cache Códigos Existentes (Proteção contra colisão)
                sql_codigos = "SELECT PRODUTO_CODIGO FROM TABELA_PRODUTO WHERE PRODUTO_EMPRESA = ? AND PRODUTO_FILIAL = ?"
                existentes_codigos = set(str(p['produto_codigo']) for p in fb.query(sql_codigos, [emp, fil]))

                produtos_para_inserir = []
                produtos_para_atualizar = []

                for item in selecionados:
                    tag = item.get('tag', '')
                    acao = item.get('_acao', 'Importar')

                    # Sanitiza campos textuais para compatibilidade com charset WIN1252
                    for campo_str in ['descricao', 'grupo', 'subgrupo', 'ncm', 'ean', 'unidade']:
                        item[campo_str] = self._sanitizar(item.get(campo_str, ''))

                    # Grupo/Subgrupo já resolvidos na análise (célula podia trazer
                    # código, descrição ou os dois). Só cai na auto-criação quando
                    # a descrição não existe no ERP.
                    grupo_id = item.get('grupo_id')
                    subgrupo_id = item.get('subgrupo_id')
                    desc_grupo = str(item.get('grupo_desc_nova') or '').strip().upper()
                    desc_sub_nova = str(item.get('subgrupo_desc_nova') or '').strip().upper()
                    grupo_id, subgrupo_id = self._resolver_ids_gravacao(
                        fb, emp, fil, grupo_id, subgrupo_id, desc_grupo,
                        desc_sub_nova, mapa_grupos, mapa_subgrupos)

                    # Proteção da Unidade vazia
                    unidade_planilha = str(item.get('unidade', '')).strip().upper()
                    if not unidade_planilha: unidade_planilha = 'UN'

                    config_prod = {'empresa': emp, 'filial': fil}
                    # Tipo por linha (planilha) quando mapeado; senao, dropdown da tela
                    tipo_produto = item.get('tipo_id') or tipo_sel
                    classificacao = {'tipo': tipo_produto, 'grupo_id': grupo_id, 'subgrupo_id': subgrupo_id, 'producao_sistec': prod_sistec}

                    # Tipo Prod. Produção: campo NUMÉRICO no ERP. Só envia se for número;
                    # texto (ex.: "CONGELADO") seria rejeitado (-303), então ignora e avisa.
                    tipo_prod_prod = str(item.get('tipo_prod_producao', '')).strip()
                    if tipo_prod_prod and not tipo_prod_prod.isdigit():
                        tipos_prod_ignorados.add(tipo_prod_prod)
                        tipo_prod_prod = ''

                    # Mocka objeto como se fosse XML para reuso blindado de regras do Sistec
                    xml_mock = {
                        'x_prod': item.get('descricao', ''), 'ncm': item.get('ncm', ''),
                        'c_ean': item.get('ean', ''), 'u_com': unidade_planilha
                    }

                    if acao == "Atualizar":
                        codigo_erp = str(item.get('codigo_erp', '')).strip()
                        if codigo_erp:
                            base = DataTransformer.prepare_produto(xml_mock, config_prod, classificacao)
                            # Antes ia o dicionario inteiro do cadastro novo, o que
                            # zerava tributacao, estoque, peso e datas de um produto
                            # que ja existia. Agora vao so os campos marcados.
                            update_dict = self._montar_update(item, base, campos_update)
                            cod_ant_upd = str(item.get('codigo_antigo', '')).strip()
                            if copiar_cod_import and cod_ant_upd:
                                update_dict['PRODUTO_COD_AUXILIAR'] = cod_ant_upd
                                update_dict['PRODUTO_COD_IMPORTACAO'] = cod_ant_upd
                            if tipo_prod_prod and 'tipo' in campos_update:
                                update_dict['PRODUTO_TIPO_PROD_PRODUCAO'] = tipo_prod_prod
                            if not update_dict:
                                sem_campo_update.append(item.get('descricao', ''))
                            else:
                                update_dict['PRODUTO_EMPRESA'] = emp
                                update_dict['PRODUTO_FILIAL'] = fil
                                update_dict['PRODUTO_DATA_ALT'] = base['PRODUTO_DATA_ALT']
                                update_dict['PRODUTO_ULT_GRAVACAO'] = base['PRODUTO_ULT_GRAVACAO']
                                update_dict['PRODUTO_CODIGO'] = codigo_erp
                                update_dict['_ACAO'] = 'UPDATE'
                                produtos_para_atualizar.append(update_dict)
                    else:
                        # "Importar" ou "Criar Novo"
                        cod_antigo = str(item.get('codigo_antigo', '')).strip()
                        cod_atual = str(item.get('codigo_atual', '')).strip()
                        if cod_atual:
                            # Cliente informou o código atual → vira o PRODUTO_CODIGO (mantido);
                            # o código antigo continua indo para o auxiliar (PRODUTO_COD_AUXILIAR).
                            # Rede de segurança: colisao aqui viraria -803 e derrubaria o
                            # lote inteiro (import_produtos e all-or-nothing).
                            if cod_atual in existentes_codigos:
                                raise ValueError(
                                    f"Código {cod_atual} ('{item.get('descricao', '')}') já está "
                                    f"em uso — corrija a coluna 'Código Atual' da planilha "
                                    f"e reanalise. Nenhum produto foi gravado.")
                            codigo_final = cod_atual
                            cod_aux = cod_antigo or None
                        elif not cod_antigo or modo_codigo == 'sequencial':
                            max_num = 0
                            for code in existentes_codigos:
                                if str(code).isdigit():
                                    max_num = max(max_num, int(code))
                            codigo_final = str(max_num + 1)
                            cod_aux = None
                        else:
                            codigo_final, cod_aux = DataTransformer.prepare_codigo_produto(cod_antigo, existentes_codigos, modo=modo_codigo)

                        existentes_codigos.add(codigo_final)

                        novo_dict = DataTransformer.prepare_produto(xml_mock, config_prod, classificacao)
                        novo_dict['PRODUTO_CODIGO'] = codigo_final
                        novo_dict['PRODUTO_COD_AUXILIAR'] = cod_aux
                        if tipo_prod_prod:
                            novo_dict['PRODUTO_TIPO_PROD_PRODUCAO'] = tipo_prod_prod
                        # Flag: leva o código antigo para Auxiliar + Importação
                        if copiar_cod_import and cod_antigo:
                            novo_dict['PRODUTO_COD_AUXILIAR'] = cod_antigo
                            novo_dict['PRODUTO_COD_IMPORTACAO'] = cod_antigo
                        novo_dict['_ACAO'] = 'INSERT'
                        produtos_para_inserir.append(novo_dict)

                importer = FirebirdImporter(fb)
                res_imp = importer.import_produtos(produtos_para_inserir)
                res_upd = importer.update_produtos(produtos_para_atualizar)

                inseridos = res_imp.get('inseridos', 0)
                atualizados = res_upd.get('atualizados', 0)
                erros = res_imp.get('erros', []) + res_upd.get('erros', [])
                
                partes = []
                if inseridos: partes.append(f"{inseridos} cadastrados")
                if atualizados: partes.append(f"{atualizados} atualizados")
                msg = f"Processamento concluído!\n\n{', '.join(partes) if partes else 'Nenhum'} produto processado com sucesso."
                if erros:
                    msg += f"\n\nHouve {len(erros)} erro(s) durante a importação. Veja o log para mais detalhes."
                if sem_campo_update:
                    msg += (f"\n\n⚠️ {len(sem_campo_update)} linha(s) marcadas para "
                            f"Atualizar não tinham nada a gravar (os campos marcados "
                            f"estão vazios na planilha) — ex.: "
                            f"{', '.join(sem_campo_update[:3])}")
                if tipos_prod_ignorados:
                    exemplos = ', '.join(sorted(tipos_prod_ignorados)[:5])
                    msg += (f"\n\n⚠️ 'Tipo Prod. Produção' é um campo numérico — "
                            f"{len(tipos_prod_ignorados)} valor(es) de texto foram IGNORADOS "
                            f"(ex.: {exemplos}). Mapeie a coluna com o código numérico, se necessário.")
                    
                self.parent.after(0, lambda m=msg: messagebox.showinfo("Concluído", m))
                
                if erros:
                    log_erros_str = "--- LOG DE ERROS DE IMPORTACAO VIA PLANILHA ---\n\n"
                    for erro in erros:
                        detalhe = erro.get('erro', str(erro))
                        log_erros_str += f"[ERRO NO BANCO DE DADOS]:\n--> {detalhe}\n\n"
                        
                    def mostrar_log(log_str):
                        resp = messagebox.askyesno(
                            "Log de Erros", 
                            "Foram encontrados erros. Deseja salvar um arquivo de texto com os detalhes do erro para validar?", 
                            parent=self.parent
                        )
                        if resp:
                            caminho_log = filedialog.asksaveasfilename(
                                defaultextension=".txt", 
                                initialfile="LOG_ERROS_PLANILHA.txt", 
                                filetypes=[("Arquivos de Texto", "*.txt")],
                                parent=self.parent
                            )
                            if caminho_log:
                                try:
                                    with open(caminho_log, 'w', encoding='utf-8') as f:
                                        f.write(log_str)
                                    messagebox.showinfo("Log Salvo", f"Arquivo de log salvo em:\n{caminho_log}", parent=self.parent)
                                    if messagebox.askyesno("Abrir Log", "Deseja abrir o arquivo de log agora?", parent=self.parent):
                                        try:
                                            os.startfile(caminho_log)
                                        except Exception as e:
                                            messagebox.showerror("Erro", f"Erro ao abrir arquivo:\n{e}", parent=self.parent)
                                except Exception as ex:
                                    messagebox.showerror("Erro ao Salvar", f"Não foi possível salvar o log:\n{ex}", parent=self.parent)
                                    
                    self.parent.after(0, lambda l=log_erros_str: mostrar_log(l))

                sucesso = True

        except Exception as e:
            err_msg = self._sanitizar(str(e))
            self.parent.after(0, lambda m=err_msg: messagebox.showerror("Erro de Importação", f"Ocorreu um erro estrutural:\n{m}"))
        finally:
            self.parent.after(0, lambda ok=sucesso: self._pos_importacao(ok))

    def _pos_importacao(self, sucesso):
        """Após importar: recarrega a tela (re-analisa) se deu certo; senão só libera os botões."""
        self.btn_importar.config(state=tk.NORMAL)
        if sucesso and self.caminho_arquivo and self.cb_abas.get():
            # Re-analisa para a grade refletir o novo estado do ERP (itens viram "JÁ CADASTRADO")
            self._iniciar_analise()
        else:
            self.btn_analisar.config(state=tk.NORMAL)
            self.lbl_status.config(text="Pronto.")
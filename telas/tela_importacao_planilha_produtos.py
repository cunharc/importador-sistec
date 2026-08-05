import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import configparser
import threading
import os

from utils.excel_reader import obter_abas_planilha, ler_planilha_produtos
from utils.firebird_service import FirebirdService
from utils.transformer import DataTransformer
from utils.importer import FirebirdImporter
from utils import tema

class TelaImportacaoPlanilhaProdutos(ttk.Frame):
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

        # === COLUMN MAPPING ===
        self.frame_map = ttk.LabelFrame(content, text="Mapeamento de Colunas (Insira a letra: A, B, C...)", padding="8")
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

        self.colunas = ("SEL", "AÇÃO", "STATUS", "CÓDIGO ANTIGO", "DESCRIÇÃO", "TIPO", "GRUPO", "SUBGRUPO", "NCM", "EAN", "UNID", "CÓD. ATUAL")
        self.tree = ttk.Treeview(frame_grade, columns=self.colunas, show="headings")

        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)

        larguras = [40, 100, 100, 100, 250, 120, 120, 120, 80, 100, 60, 100]
        for col, larg in zip(self.colunas, larguras):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=larg, anchor=tk.CENTER if col != "DESCRIÇÃO" else tk.W)

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
            try:
                with FirebirdService(self.config_db) as fb:
                    rows = fb.query(
                        "SELECT PRODUTO_CODIGO, PRODUTO_COD_AUXILIAR, PRODUTO_DESCRICAO "
                        "FROM TABELA_PRODUTO WHERE PRODUTO_EMPRESA = ? AND PRODUTO_FILIAL = ?",
                        [emp, fil]
                    )
                    for row in rows:
                        cod = str(row.get('produto_codigo', '')).strip()
                        aux = str(row.get('produto_cod_auxiliar', '')).strip()
                        desc = str(row.get('produto_descricao', '')).strip()
                        info = {'codigo': cod, 'descricao': desc}
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

            def match_produto(cod_planilha, desc_planilha):
                if cod_planilha and cod_planilha in produtos_erp:
                    info = produtos_erp[cod_planilha]
                    desc_erp = info['descricao'].lower().strip()
                    desc_plan = desc_planilha.lower().strip()
                    if desc_plan == desc_erp or (desc_plan and desc_erp and (desc_plan in desc_erp or desc_erp in desc_plan)):
                        return 'JÁ CADASTRADO', info
                    return 'DIVERGENTE', info
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
                    match_label, matched_info = match_produto(cod_planilha, desc_planilha)
                    if match_label == 'DIVERGENTE':
                        status = "DIVERGENTE"
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

                item = {
                    'sel': sel, 'acao': acao, 'status': status, 'tag': tag,
                    'codigo_antigo': cod_planilha, 'codigo_atual': cod_atual_planilha,
                    'descricao': desc_planilha,
                    'codigo_erp': matched_info.get('codigo', '') if matched_info else '',
                    'desc_erp': matched_info.get('descricao', '') if matched_info else '',
                    'tipo': tipo_label,
                    'tipo_id': tipo_id_plan,
                    'grupo': reg.get('grupo', ''),
                    'subgrupo': reg.get('subgrupo', ''),
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

                # Auto-preenche subgrupo com grupo se vazio
                if str(item.get('grupo', '')).strip() and not str(item.get('subgrupo', '')).strip():
                    item['subgrupo'] = item['grupo']

                item_id = self.tree.insert("", tk.END, values=(
                    item['sel'], item['acao'], item['status'],
                    item['codigo_antigo'], item['descricao'],
                    item['tipo'], item['grupo'],
                    item['subgrupo'], item['ncm'],
                    item['ean'], item['unidade'], item.get('codigo_atual', '')
                ), tags=(item['tag'],))
                self.dados_grid[item_id] = {
                    'codigo_antigo': item['codigo_antigo'],
                    'codigo_atual': item.get('codigo_atual', ''),
                    'descricao': item['descricao'],
                    'codigo_erp': item.get('codigo_erp', ''),
                    'desc_erp': item.get('desc_erp', ''),
                    'tipo': item.get('tipo', ''),
                    'tipo_id': item.get('tipo_id'),
                    'grupo': item['grupo'],
                    'subgrupo': item['subgrupo'],
                    'ncm': item['ncm'],
                    'ean': item['ean'],
                    'unidade': item['unidade'],
                    'tipo_prod_producao': item.get('tipo_prod_producao', ''),
                    '_status': 'OK' if item['tag'] == 'NOVO' else 'SKIP'
                }

            if end_idx < total:
                self.lbl_status.config(text=f"Renderizando {end_idx}/{total}...")
                self.update_idletasks()
                self.parent.after(5, render_chunk, end_idx)
            else:
                self.btn_analisar.config(state=tk.NORMAL)
                novo_count = sum(1 for d in dados if d['tag'] == 'NOVO')
                div_count = sum(1 for d in dados if d['tag'] == 'DIVERGENTE')
                if novo_count > 0 or div_count > 0:
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
            valores[5] = novo_tipo
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

    def _on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell": return
        column = self.tree.identify_column(event.x)
        item_id = self.tree.identify_row(event.y)
        if not item_id: return

        valores = list(self.tree.item(item_id, 'values'))
        status = valores[2]  # STATUS está no índice 2
        if "ERRO" in status: return
        eh_exato = (status == "JÁ CADASTRADO")

        if column == "#1":  # SEL
            if eh_exato: return
            if valores[0] == "☑":
                valores[0] = "☐"
                valores[1] = "Ignorar"
            else:
                valores[0] = "☑"
                if status == "NOVO":
                    valores[1] = "Importar"
                elif "DIVERGENTE" in status:
                    valores[1] = "Atualizar"
                elif "~desc" in status:
                    valores[1] = "Criar Novo"
            self.tree.item(item_id, values=valores)

        elif column == "#2":  # AÇÃO
            if eh_exato: return
            if status == "NOVO":
                ciclo = ["Importar", "Ignorar"]
            elif "DIVERGENTE" in status:
                ciclo = ["Atualizar", "Criar Novo", "Ignorar"]
            elif "~desc" in status:
                ciclo = ["Criar Novo", "Ignorar"]
            else:
                return
            try:
                idx = ciclo.index(valores[1])
                valores[1] = ciclo[(idx + 1) % len(ciclo)]
            except ValueError:
                valores[1] = ciclo[0]
            valores[0] = "☑" if valores[1] != "Ignorar" else "☐"
            self.tree.item(item_id, values=valores)

    def _marcar_todos(self):
        for item in self.tree.get_children():
            v = list(self.tree.item(item, "values"))
            st = v[2]
            if st == "NOVO":
                v[0] = "☑"
                v[1] = "Importar"
                self.tree.item(item, values=v)
            elif "DIVERGENTE" in st:
                v[0] = "☑"
                v[1] = "Atualizar"
                self.tree.item(item, values=v)
            elif "~desc" in st:
                v[0] = "☑"
                v[1] = "Criar Novo"
                self.tree.item(item, values=v)

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

            if str(item.get('grupo', '')).strip() and not str(item.get('subgrupo', '')).strip():
                item['subgrupo'] = item['grupo']

            item_id = self.tree.insert("", tk.END, values=(
                item['sel'], item['acao'], item['status'],
                item['codigo_antigo'], item['descricao'],
                item['tipo'], item['grupo'],
                item['subgrupo'], item['ncm'],
                item['ean'], item['unidade']
            ), tags=(item['tag'],))
            self.dados_grid[item_id] = {
                'codigo_antigo': item['codigo_antigo'],
                'descricao': item['descricao'],
                'codigo_erp': item.get('codigo_erp', ''),
                'desc_erp': item.get('desc_erp', ''),
                'tipo': item.get('tipo', ''),
                'tipo_id': item.get('tipo_id'),
                'grupo': item['grupo'],
                'subgrupo': item['subgrupo'],
                'ncm': item['ncm'],
                'ean': item['ean'],
                'unidade': item['unidade'],
                '_status': 'OK' if item['tag'] == 'NOVO' else 'SKIP'
            }

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

        resp = messagebox.askyesno("Confirmar", f"Deseja injetar os {len(selecionados)} produtos selecionados e seus grupos no Banco de Dados?\nEssa ação não pode ser desfeita.")
        if resp:
            self.btn_importar.config(state=tk.DISABLED)
            self.btn_analisar.config(state=tk.DISABLED)
            self.lbl_status.config(text="Construindo grupos e injetando produtos...")

            # Coleta os valores da interface na thread principal (evita falha silenciosa de leitura no background)
            tipo_sel = self.cb_tipo.get()
            prod_sistec = 'S' if self.var_producao.get() else 'N'
            modo_codigo = self.var_modo_codigo.get()
            copiar_cod_import = self.var_copiar_cod_import.get()

            threading.Thread(target=self._importacao_bg, args=(selecionados, tipo_sel, prod_sistec, modo_codigo, copiar_cod_import), daemon=True).start()

    @staticmethod
    def _sanitizar(texto):
        if not isinstance(texto, str):
            return texto
        return texto.encode('cp1252', errors='replace').decode('cp1252')

    def _importacao_bg(self, selecionados, tipo_sel, prod_sistec, modo_codigo='xml', copiar_cod_import=False):
        sucesso = False
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

                    # Auto-Criação de Grupo
                    desc_grupo = str(item.get('grupo', '')).strip().upper()
                    if not desc_grupo: grupo_id = 1
                    elif desc_grupo in mapa_grupos: grupo_id = mapa_grupos[desc_grupo]
                    else:
                        res = fb.query("SELECT COALESCE(MAX(GRUPO_CODIGO), 0) + 1 AS NOVO FROM TABELA_GRUPO WHERE GRUPO_EMPRESA = ? AND GRUPO_FILIAL = ?", [emp, fil])
                        grupo_id = int(res[0]['novo'])
                        fb.execute("INSERT INTO TABELA_GRUPO (GRUPO_EMPRESA, GRUPO_FILIAL, GRUPO_CODIGO, GRUPO_DESCRICAO) VALUES (?, ?, ?, ?)", [emp, fil, grupo_id, desc_grupo[:60]])
                        mapa_grupos[desc_grupo] = grupo_id

                    # Auto-Criação de Subgrupo
                    desc_sub = str(item.get('subgrupo', '')).strip().upper()
                    if not desc_sub and desc_grupo:
                        desc_sub = desc_grupo
                        
                    if not desc_sub: subgrupo_id = 1
                    else:
                        chave_sub = f"{grupo_id}_{desc_sub}"
                        if chave_sub in mapa_subgrupos: subgrupo_id = mapa_subgrupos[chave_sub]
                        else:
                            res = fb.query("SELECT COALESCE(MAX(SUBGRUPO_CODIGO), 0) + 1 AS NOVO FROM TABELA_SUBGRUPO WHERE SUBGRUPO_EMPRESA = ? AND SUBGRUPO_FILIAL = ? AND SUBGRUPO_GRUPO = ?", [emp, fil, grupo_id])
                            subgrupo_id = int(res[0]['novo'])
                            fb.execute("INSERT INTO TABELA_SUBGRUPO (SUBGRUPO_EMPRESA, SUBGRUPO_FILIAL, SUBGRUPO_GRUPO_EMPRESA, SUBGRUPO_GRUPO_FILIAL, SUBGRUPO_GRUPO, SUBGRUPO_CODIGO, SUBGRUPO_DESCRICAO) VALUES (?, ?, ?, ?, ?, ?, ?)", [emp, fil, emp, fil, grupo_id, subgrupo_id, desc_sub[:60]])
                            mapa_subgrupos[chave_sub] = subgrupo_id

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
                            update_dict = DataTransformer.prepare_produto(xml_mock, config_prod, classificacao)
                            update_dict['PRODUTO_CODIGO'] = codigo_erp
                            if tipo_prod_prod:
                                update_dict['PRODUTO_TIPO_PROD_PRODUCAO'] = tipo_prod_prod
                            # Flag: leva o código antigo para Auxiliar + Importação
                            cod_ant_upd = str(item.get('codigo_antigo', '')).strip()
                            if copiar_cod_import and cod_ant_upd:
                                update_dict['PRODUTO_COD_AUXILIAR'] = cod_ant_upd
                                update_dict['PRODUTO_COD_IMPORTACAO'] = cod_ant_upd
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
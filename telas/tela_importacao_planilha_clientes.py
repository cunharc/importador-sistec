import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import configparser
import threading
import re
import os
import unicodedata

from utils.excel_reader import obter_abas_planilha, ler_planilha_produtos
from utils.firebird_service import FirebirdService

CAMPOS_DISPONIVEIS = [
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
        header = tk.Frame(self, bg="#003399", padx=15, pady=8)
        header.pack(fill=tk.X, pady=(0, 10))
        tk.Label(header, text="IMPORTAÇÃO DE CLIENTES VIA PLANILHA (Excel/CSV)",
                 font=("Segoe UI", 14, "bold"), bg="#003399", fg="white").pack(anchor=tk.W)

        # === FILE SELECTION ROW ===
        file_row = ttk.Frame(self)
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

        # === COLUMN MAPPING ===
        frame_map = ttk.LabelFrame(self, text="Mapeamento de Colunas (Insira a letra: A, B, C...)", padding="8")
        frame_map.pack(fill=tk.X, pady=4)

        self.entradas_map = {}
        linhas_campos = [CAMPOS_DISPONIVEIS[i:i+4] for i in range(0, len(CAMPOS_DISPONIVEIS), 4)]
        for i_linha, grupo in enumerate(linhas_campos):
            for i_col, (lbl_texto, chave, obrigatorio) in enumerate(grupo):
                col = i_col * 2
                texto = lbl_texto
                fg_color = "#C8001E" if obrigatorio else "#1A1A1A"
                tk.Label(frame_map, text=texto, font=("Segoe UI", 8, "bold"),
                         fg=fg_color).grid(row=i_linha, column=col, padx=(5, 1), pady=2, sticky=tk.E)
                ent = ttk.Entry(frame_map, width=4, font=("Segoe UI", 9))
                ent.grid(row=i_linha, column=col + 1, padx=(0, 5), pady=2, sticky=tk.W)
                self.entradas_map[chave] = ent

        # === ACTIONS + PROGRESS ===
        actions_row = ttk.Frame(self)
        actions_row.pack(fill=tk.X, pady=4)

        self.btn_analisar = tk.Button(actions_row, text="🔍 Carregar e Analisar Planilha",
                                       font=("Segoe UI", 9, "bold"), bg="#2980b9", fg="white",
                                       cursor="hand2", padx=12, pady=1,
                                       command=self._iniciar_analise)
        self.btn_analisar.pack(side=tk.LEFT, padx=5)

        ttk.Button(actions_row, text="☑ Marcar Todos", command=self._marcar_todos).pack(side=tk.LEFT, padx=3)
        ttk.Button(actions_row, text="☐ Desmarcar", command=self._desmarcar_todos).pack(side=tk.LEFT, padx=3)
        ttk.Separator(actions_row, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=4, fill=tk.Y)
        ttk.Button(actions_row, text="👥 Todos Cliente", command=self._marcar_todos_cliente).pack(side=tk.LEFT, padx=2)
        ttk.Button(actions_row, text="🏭 Todos Fornecedor", command=self._marcar_todos_fornecedor).pack(side=tk.LEFT, padx=2)
        ttk.Button(actions_row, text="📦 Todos Outros", command=self._marcar_todos_outros).pack(side=tk.LEFT, padx=2)

        self.progresso = ttk.Progressbar(actions_row, orient=tk.HORIZONTAL, mode='determinate', length=120)
        self.progresso.pack(side=tk.LEFT, padx=8)

        self.lbl_status = ttk.Label(actions_row, text="Aguardando configuração...", font=("Segoe UI", 9), foreground="#555")
        self.lbl_status.pack(side=tk.LEFT, padx=2)

        # === FILTER ROW ===
        filter_row = ttk.Frame(self)
        filter_row.pack(fill=tk.X, pady=(2, 0))

        tk.Label(filter_row, text="Filtrar Status:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 2))
        self.cb_filtro_status = ttk.Combobox(filter_row, values=["Todos", "OK", "ERRO", "JÁ CADASTRADO"],
                                              state="readonly", width=18, font=("Segoe UI", 9))
        self.cb_filtro_status.current(0)
        self.cb_filtro_status.pack(side=tk.LEFT, padx=2)
        self.cb_filtro_status.bind("<<ComboboxSelected>>", self._filtrar_status)

        # === TREEVIEW ===
        frame_grade = ttk.Frame(self)
        frame_grade.pack(fill=tk.BOTH, expand=True, pady=4)

        self.colunas = ("SEL", "STATUS", "CLI", "FOR", "OUT", "CPF/CNPJ", "RAZÃO SOCIAL", "FANTASIA", "CIDADE", "VENDEDOR")
        self._sort_directions = {col: False for col in self.colunas}
        self.tree = ttk.Treeview(frame_grade, columns=self.colunas, show="headings")

        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)

        larguras = [40, 100, 36, 36, 36, 150, 250, 150, 120, 120]
        for col, larg in zip(self.colunas, larguras):
            self.tree.heading(col, text=col + " ↕", command=lambda c=col: self._sort_treeview(c))
            self.tree.column(col, width=larg, anchor=tk.CENTER if col not in ("RAZÃO SOCIAL",) else tk.W)

        self.tree.tag_configure('ERRO', background='#FADBD8')
        self.tree.tag_configure('OK', background='#EAFAF1')

        scroll_y = ttk.Scrollbar(frame_grade, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        # === FOOTER ===
        footer = tk.Frame(self, bg="#f0f0f0", padx=10, pady=6)
        footer.pack(fill=tk.X, pady=(4, 0))

        tk.Button(footer, text="⬅ VOLTAR", command=self._fechar_tela,
                  font=("Segoe UI", 9, "bold"), bg="#95a5a6", fg="white",
                  cursor="hand2", padx=12, pady=2).pack(side=tk.LEFT)

        self.btn_importar = tk.Button(footer, text="🚀 Processar e Injetar no ERP", state=tk.DISABLED,
                                       font=("Segoe UI", 9, "bold"), bg="#003399", fg="white",
                                       cursor="hand2", padx=14, pady=2,
                                       command=self._iniciar_importacao)
        self.btn_importar.pack(side=tk.RIGHT, padx=3)

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
            dados_existentes = {'documentos': {}, 'nomes': {}}
            try:
                with FirebirdService(self.config_db) as fb:
                    emp = int(self.config.get('IMPORTACAO', 'empresa', fallback='1'))
                    fil = int(self.config.get('IMPORTACAO', 'filial', fallback='1'))
                    rows = fb.query(
                        "SELECT CF_CPF_CGC, CF_RAZAO FROM TABELA_CLI_FOR WHERE CF_EMPRESA = ? AND CF_FILIAL = ?",
                        [emp, fil]
                    )
                    for row in rows:
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
        return re.sub(r'\D', '', str(valor or ''))

    def _normalizar_ie(self, valor):
        return re.sub(r'\D', '', str(valor or ''))

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

    def _renderizar_preview(self, dados_existentes=None):
        for i in self.tree.get_children(): self.tree.delete(i)
        self.dados_grid.clear()

        docs_existentes = dados_existentes.get('documentos', {}) if dados_existentes else {}
        nomes_existentes = dados_existentes.get('nomes', {}) if dados_existentes else {}

        items = []
        validos = 0
        for reg in self.registros_lidos:
            documento = self._normalizar_documento(reg.get('documento', ''))
            razao = str(reg.get('razao', '')).strip()
            reg['documento_limpo'] = documento

            if not razao:
                status = "ERRO (Sem Razão Social)"
            elif docs_existentes and documento and documento in docs_existentes:
                status = "JÁ CADASTRADO"
            elif nomes_existentes and not documento and self._remover_acentos(razao).strip().upper()[:50] in nomes_existentes:
                status = "JÁ CADASTRADO"
            else:
                status = "OK"
                validos += 1

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

            tag = 'OK' if status == 'OK' else 'ERRO'
            reg['_tipo'] = {
                'cliente': cli == "☑",
                'fornecedor': forn == "☑",
                'outros': out == "☑"
            }
            items.append((
                (check, status, cli, forn, out, reg.get('documento', ''), razao,
                 fantasia, cidade, vendedor),
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
                self.lbl_status.config(
                    text=f"Pronto. {validos} novos clientes de {total} lidos."
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
            col_map = {"#3": ("cliente", 2), "#4": ("fornecedor", 3), "#5": ("outros", 4)}
            if column in col_map:
                chave, idx = col_map[column]
                tipo = self.dados_grid[item_id].get('_tipo', {})
                novo = not tipo.get(chave, False)
                tipo[chave] = novo

                if chave == 'outros' and novo:
                    tipo['cliente'] = False
                    tipo['fornecedor'] = False
                    valores[2] = "☐"
                    valores[3] = "☐"
                elif chave != 'outros' and novo:
                    tipo['outros'] = False
                    valores[4] = "☐"

                if not any(tipo.values()):
                    tipo['outros'] = True
                    valores[4] = "☑"

                valores[idx] = "☑" if tipo[chave] else "☐"
                if chave == 'outros' and novo:
                    valores[2] = "☐"
                    valores[3] = "☐"
                elif chave != 'outros' and not any(tipo.values()):
                    pass  # already handled above

                # Sync remaining columns
                if chave != 'outros':
                    valores[2] = "☑" if tipo['cliente'] else "☐"
                    valores[3] = "☑" if tipo['fornecedor'] else "☐"
                    valores[4] = "☑" if tipo['outros'] else "☐"

                self.tree.item(item_id, values=valores)

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

    def _marcar_todos_cliente(self):
        for item in self.tree.get_children():
            v = list(self.tree.item(item, "values"))
            if "ERRO" not in v[1] and "JÁ CADASTRADO" not in v[1]:
                v[2] = "☑"
                v[3] = "☐"
                v[4] = "☐"
                self.tree.item(item, values=v)
                if item in self.dados_grid:
                    self.dados_grid[item]['_tipo'] = {'cliente': True, 'fornecedor': False, 'outros': False}

    def _marcar_todos_fornecedor(self):
        for item in self.tree.get_children():
            v = list(self.tree.item(item, "values"))
            if "ERRO" not in v[1] and "JÁ CADASTRADO" not in v[1]:
                v[2] = "☐"
                v[3] = "☑"
                v[4] = "☐"
                self.tree.item(item, values=v)
                if item in self.dados_grid:
                    self.dados_grid[item]['_tipo'] = {'cliente': False, 'fornecedor': True, 'outros': False}

    def _marcar_todos_outros(self):
        for item in self.tree.get_children():
            v = list(self.tree.item(item, "values"))
            if "ERRO" not in v[1] and "JÁ CADASTRADO" not in v[1]:
                v[2] = "☐"
                v[3] = "☐"
                v[4] = "☑"
                self.tree.item(item, values=v)
                if item in self.dados_grid:
                    self.dados_grid[item]['_tipo'] = {'cliente': False, 'fornecedor': False, 'outros': True}

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

    def _filtrar_status(self, event=None):
        filtro = self.cb_filtro_status.get()
        for item in self.tree.get_children():
            self.tree.detach(item)
        for item_id, reg in self.dados_grid.items():
            status = reg.get('_status', '')
            if filtro == "Todos" or status == filtro or (filtro == "ERRO" and status.startswith("ERRO")):
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

                res_emp = fb.query("SELECT EMP_NOME FROM TABELA_EMPRESA WHERE EMP_CODIGO = ?", [emp])
                nome_empresa = (res_emp[0]['emp_nome'] or '').strip().upper() if res_emp else f"EMPRESA {emp}"

                dados_existentes = {
                    'documentos': {doc: True for doc in clientes_existentes},
                    'nomes': {nome: True for nome in nomes_existentes}
                }

                for item in selecionados:
                    if item.get('_status') != 'OK': continue

                    documento = item.get('documento_limpo', '')
                    razao_norm = self._remover_acentos(str(item.get('razao', ''))).strip().upper()[:50]

                    if documento and documento in dados_existentes['documentos']:
                        log_linhas.append(f"⚠ {item.get('razao', '')[:60]} — CPF/CNPJ já cadastrado, pulando")
                        continue
                    elif not documento and razao_norm and razao_norm in dados_existentes['nomes']:
                        log_linhas.append(f"⚠ {item.get('razao', '')[:60]} — nome já cadastrado, pulando")
                        continue

                    razao = str(item.get('razao', '')).strip().upper()[:50]
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
                    fone1 = re.sub(r'\D', '', str(item.get('fone1', '')))[:15]
                    fone2 = re.sub(r'\D', '', str(item.get('fone2', '')))[:15]
                    email = str(item.get('email', '')).strip()[:50]
                    email_nfe = str(item.get('email_nfe', '')).strip()[:50]
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

                    if is_outros == 'S':
                        tipo_inscr = 99
                    elif len(documento) == 11:
                        tipo_inscr = 1
                    elif len(documento) == 14:
                        tipo_inscr = 2
                    else:
                        tipo_inscr = 0

                    cidade_codigo = None
                    cidade_nome = self._limpar_nome_cidade(item.get('cidade_nome', ''))
                    cidade_nome_sql = self._remover_acentos(cidade_nome).upper()
                    if cidade_nome:
                        try:
                            res = fb.query("""
                                SELECT CIDIBGE_CODIGO FROM TABELA_CIDADES_IBGE
                                WHERE TRIM(UPPER(CIDIBGE_DESCRICAO)) = ?
                            """, [cidade_nome_sql])
                            if not res and uf:
                                res = fb.query("""
                                    SELECT CIDIBGE_CODIGO FROM TABELA_CIDADES_IBGE
                                    WHERE TRIM(UPPER(CIDIBGE_DESCRICAO)) = ? AND CIDIBGE_ESTADO = ?
                                """, [cidade_nome_sql, uf])
                            if res:
                                ibge_cod = res[0]['cidibge_codigo']
                                res2 = fb.query("""
                                    SELECT CID_CODIGO FROM TABELA_CIDADE
                                    WHERE CID_CODIGO_IBGE = ? AND CID_EMPRESA = ? AND CID_FILIAL = ?
                                """, [ibge_cod, emp, fil])
                                if res2:
                                    cidade_codigo = res2[0]['cid_codigo']
                                else:
                                    res2 = fb.query("""
                                        SELECT CID_CODIGO FROM TABELA_CIDADE
                                        WHERE CID_CODIGO = ? AND CID_EMPRESA = ? AND CID_FILIAL = ?
                                    """, [ibge_cod, emp, fil])
                                    if res2:
                                        cidade_codigo = res2[0]['cid_codigo']
                                    else:
                                        res2 = fb.query("""
                                            SELECT COALESCE(MAX(CID_CODIGO), 0) + 1 AS NOVO
                                            FROM TABELA_CIDADE
                                            WHERE CID_EMPRESA = ? AND CID_FILIAL = ?
                                        """, [emp, fil])
                                        novo_cid = int(res2[0]['novo'])
                                        fb.execute("""
                                            INSERT INTO TABELA_CIDADE (
                                                CID_EMPRESA, CID_FILIAL, CID_CODIGO, CID_DESCRICAO,
                                                CID_CEP, CID_UF, CID_CODIGO_IBGE, CID_PAIS
                                            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1058)
                                        """, [emp, fil, novo_cid, cidade_nome.upper(), cep, uf, ibge_cod])
                                        cidade_codigo = novo_cid
                                        log_linhas.append(f"🏙 Cidade '{cidade_nome}' auto-cadastrada (IBGE {ibge_cod}, código {novo_cid})")
                            else:
                                log_linhas.append(f"⚠ Cidade '{cidade_nome}' não encontrada na TABELA_CIDADES_IBGE para {razao}")
                        except Exception as e:
                            log_linhas.append(f"⚠ Erro ao processar cidade '{cidade_nome}': {e}")

                    vendedor_codigo = None
                    vendedor_nome = str(item.get('vendedor_nome', '')).strip()
                    if not vendedor_nome:
                        vendedor_nome = nome_empresa
                    vendedor_nome_sql = self._remover_acentos(vendedor_nome).upper()
                    try:
                        res = fb.query("""
                            SELECT VEND_CODIGO FROM TABELA_VENDEDOR
                            WHERE VEND_EMPRESA = ? AND VEND_FILIAL = ?
                            AND TRIM(UPPER(VEND_NOME)) = ?
                        """, [emp, fil, vendedor_nome_sql])
                        if res:
                            vendedor_codigo = res[0]['vend_codigo']
                        else:
                            res = fb.query("""
                                SELECT COALESCE(MAX(VEND_CODIGO), 0) + 1 AS NOVO
                                FROM TABELA_VENDEDOR
                                WHERE VEND_EMPRESA = ? AND VEND_FILIAL = ?
                            """, [emp, fil])
                            novo_cod = int(res[0]['novo'])
                            fb.execute("""
                                INSERT INTO TABELA_VENDEDOR (
                                    VEND_EMPRESA, VEND_FILIAL, VEND_CODIGO,
                                    VEND_NOME, VEND_ATIVO, VEND_COMISSAO_FATURAMENTO
                                ) VALUES (?, ?, ?, ?, 'S', 0)
                            """, [emp, fil, novo_cod, vendedor_nome_sql])
                            vendedor_codigo = novo_cod
                            log_linhas.append(f"✅ Vendedor '{vendedor_nome}' criado (código {novo_cod})")
                    except Exception as e:
                        log_linhas.append(f"⚠ Erro vendedor '{vendedor_nome}': {e}")

                    cf_codigo = 1
                    while cf_codigo in codigos_usados:
                        cf_codigo += 1
                    codigos_usados.add(cf_codigo)

                    cgc_formatado = documento
                    if len(documento) == 11:
                        cgc_formatado = f"{documento[:3]}.{documento[3:6]}.{documento[6:9]}-{documento[9:]}"
                    elif len(documento) == 14:
                        cgc_formatado = f"{documento[:2]}.{documento[2:5]}.{documento[5:8]}/{documento[8:12]}-{documento[12:]}"

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
                                CF_REPRESENTANTE_EMP, CF_REPRESENTANTE_FILIAL,
                                CF_FONE1, CF_FONE2, CF_FAX,
                                CF_EMAIL,
                                CF_EMAIL_NFE,
                                CF_COD_ANTIGO
                            ) VALUES (
                                ?, ?, ?,
                                CURRENT_DATE, CURRENT_DATE,
                                ?, ?, ?,
                                'S', ?,
                                ?, ?, ?,
                                ?, ?, 1,
                                ?, ?, ?,
                                ?, ?,
                                ?, ?, ?,
                                ?, ?,
                                ?, ?, ?, ?,
                                ?, ?, ?, ?,
                                ?, ?,
                                ?, ?,
                                ?, ?, '',
                                ?,
                                'S',
                                NULL
                            )
                        """, [
                            emp, fil, cf_codigo,
                            cgc_formatado, razao, fantasia,
                            tipo_inscr, is_cliente, is_fornecedor, is_outros,
                            rg_ie, cf_icms,
                            endereco, numero, bairro,
                            cidade_codigo, cep,
                            endereco, numero, bairro,
                            cidade_codigo, cep,
                            endereco, bairro, cidade_codigo, cep,
                            endereco, bairro, cidade_codigo, cep,
                            emp, fil,
                            emp, fil,
                            fone1, fone2,
                            email,
                        ])
                        inseridos += 1
                        log_linhas.append(f"✅ {razao} (cod {cf_codigo}) inserido com sucesso")
                        if documento:
                            dados_existentes['documentos'][documento] = True
                        if razao_norm:
                            dados_existentes['nomes'][razao_norm] = True
                    except Exception as e:
                        erros += 1
                        log_linhas.append(f"❌ Erro ao inserir {razao}: {e}")

                msg = f"Processamento concluído!\n\n{inseridos} cliente(s) cadastrados."
                if erros:
                    msg += f"\n{erros} erro(s) durante a importação. Veja o log para detalhes."
                self.parent.after(0, lambda m=msg: self._safe_showinfo("Concluído", m))

                log_str = "\n".join(log_linhas)
                self.parent.after(0, lambda l=log_str: self._oferecer_log(l))

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

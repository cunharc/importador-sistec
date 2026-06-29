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

CAMPOS_DISPONIVEIS = [
    ("N\u00famero Documento *", "numero_doc", True),
    ("Parcela", "parcela", False),
    ("Fornecedor (CNPJ/CPF)", "documento", False),
    ("Fornecedor (Raz\u00e3o Social)", "razao", False),
    ("Valor da Conta *", "valor", True),
    ("Valor Pago", "valor_recebido", False),
    ("Data Emiss\u00e3o", "emissao", False),
    ("Vencimento", "vencimento", False),
    ("Data Registro", "data_registro", False),
    ("Data Pagamento", "data_recebimento", False),
    ("Desconto", "desconto", False),
    ("Juros e Multa", "juros", False),
    ("S\u00e9rie", "serie", False),
    ("N\u00famero Boleto", "boleto", False),
    ("Observa\u00e7\u00e3o", "observacao", False),
]

SERIE_PADRAO = "IMP"

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
        header = tk.Frame(self, bg="#003399", padx=15, pady=8)
        header.pack(fill=tk.X, pady=(0, 10))
        tk.Label(header, text="IMPORTA\u00c7\u00c3O DE CONTAS A PAGAR VIA PLANILHA (Excel/CSV)",
                 font=("Segoe UI", 14, "bold"), bg="#003399", fg="white").pack(anchor=tk.W)

        file_row = ttk.Frame(self)
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

        frame_map = ttk.LabelFrame(self, text="Mapeamento de Colunas (Insira a letra: A, B, C...)", padding="8")
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

        actions_row = ttk.Frame(self)
        actions_row.pack(fill=tk.X, pady=4)

        self.btn_analisar = tk.Button(actions_row, text="🔍 Carregar e Analisar Planilha",
                                       font=("Segoe UI", 9, "bold"), bg="#2980b9", fg="white",
                                       cursor="hand2", padx=12, pady=1,
                                       command=self._iniciar_analise)
        self.btn_analisar.pack(side=tk.LEFT, padx=5)

        ttk.Button(actions_row, text="☑ Marcar Todos", command=self._marcar_todos).pack(side=tk.LEFT, padx=3)
        ttk.Button(actions_row, text="☐ Desmarcar", command=self._desmarcar_todos).pack(side=tk.LEFT, padx=3)

        self.progresso = ttk.Progressbar(actions_row, orient=tk.HORIZONTAL, mode='determinate', length=120)
        self.progresso.pack(side=tk.LEFT, padx=8)

        self.lbl_status = ttk.Label(actions_row, text="Aguardando configura\u00e7\u00e3o...", font=("Segoe UI", 9), foreground="#555")
        self.lbl_status.pack(side=tk.LEFT, padx=2)

        filter_row = ttk.Frame(self)
        filter_row.pack(fill=tk.X, pady=(2, 0))

        tk.Label(filter_row, text="Filtrar Status:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 2))
        self.cb_filtro_status = ttk.Combobox(filter_row, values=["Todos", "OK", "ERRO", "J\u00c1 CADASTRADO"],
                                              state="readonly", width=14, font=("Segoe UI", 9))
        self.cb_filtro_status.current(0)
        self.cb_filtro_status.pack(side=tk.LEFT, padx=2)
        self.cb_filtro_status.bind("<<ComboboxSelected>>", self._filtrar_grade)

        tk.Label(filter_row, text="Filtrar Situa\u00e7\u00e3o:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(10, 2))
        self.cb_filtro_situacao = ttk.Combobox(filter_row, values=["Todas", "Aberto", "Parcial", "Pago"],
                                               state="readonly", width=12, font=("Segoe UI", 9))
        self.cb_filtro_situacao.current(0)
        self.cb_filtro_situacao.pack(side=tk.LEFT, padx=2)
        self.cb_filtro_situacao.bind("<<ComboboxSelected>>", self._filtrar_grade)

        tk.Label(filter_row, text="Local Cobran\u00e7a:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(10, 2))
        self.cb_local_cobranca = ttk.Combobox(filter_row, state="readonly", width=24, font=("Segoe UI", 9))
        self.cb_local_cobranca.pack(side=tk.LEFT, padx=2)
        self._carregar_locais_cobranca()

        frame_grade = ttk.Frame(self)
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
        secao = 'IMPORTACAO_PAGAR'
        if not config.has_section(secao):
            config.add_section(secao)
        config.set(secao, 'ultimo_arquivo', self.caminho_arquivo)
        config.set(secao, 'ultima_aba', self.cb_abas.get())
        config.set(secao, 'linha_inicial', self.ent_linha_ini.get())
        for chave, ent in self.entradas_map.items():
            config.set(secao, f'map_{chave}', ent.get().strip())
        config.set(secao, 'local_cobranca', self.cb_local_cobranca.get())
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
        return re.sub(r'\D', '', str(valor or ''))

    def _remover_acentos(self, texto):
        texto = unicodedata.normalize('NFKD', str(texto))
        return texto.encode('ASCII', 'ignore').decode('ASCII')

    def _parse_valor(self, valor):
        v = str(valor or '0').strip()
        v = v.replace('.', '').replace(',', '.')
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
            dados_existentes = {'parc_existentes': {}, 'fornecedor_cache': {}, 'proximo_codigo': 1}
            try:
                with FirebirdService(self.config_db) as fb:
                    emp = int(self.config.get('IMPORTACAO', 'empresa', fallback='1'))
                    fil = int(self.config.get('IMPORTACAO', 'filial', fallback='1'))
                    rows = fb.query(
                        "SELECT TPARC_CODIGO, TPARC_PARCELA, TPARC_FORNECEDOR "
                        "FROM TABELA_TITULO_PARCELA WHERE TPARC_EMPRESA = ? AND TPARC_FILIAL = ?",
                        [emp, fil]
                    )
                    for row in rows:
                        chave = (str(row['tparc_codigo'] or '').strip().lstrip('0'),
                                 int(row['tparc_parcela'] or 1),
                                 int(row['tparc_fornecedor'] or 0))
                        dados_existentes['parc_existentes'][chave] = True

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
            except Exception:
                pass
            self.parent.after(0, lambda: self._renderizar_preview(dados_existentes))
            self.parent.after(0, self._carregar_locais_cobranca)
        except Exception as e:
            self.parent.after(0, lambda err=e: messagebox.showerror("Erro", f"Falha na leitura da planilha:\n{err}"))
            self.parent.after(0, lambda: self.btn_analisar.config(state=tk.NORMAL))
            self.parent.after(0, lambda: self.lbl_status.config(text="Erro."))

    def _renderizar_preview(self, dados_existentes=None):
        for i in self.tree.get_children(): self.tree.delete(i)
        self.dados_grid.clear()

        parc_existentes = dados_existentes.get('parc_existentes', {}) if dados_existentes else {}
        forn_cache = dados_existentes.get('fornecedor_cache', {}) if dados_existentes else {}
        prox_cod = dados_existentes.get('proximo_codigo', 1) if dados_existentes else 1
        codigos_usados = set()

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
        for reg in self.registros_lidos:
            parcela = self._parse_parcela(reg.get('parcela', ''))
            valor = self._parse_valor(reg.get('valor', '0'))
            razao = str(reg.get('razao', '')).strip()
            documento = self._normalizar_documento(reg.get('documento', ''))
            serie = str(reg.get('serie', '')).strip().upper() or SERIE_PADRAO
            numero_doc = str(reg.get('numero_doc', '')).strip()

            codigo_auto = None
            if not numero_doc:
                while str(prox_cod) in codigos_usados or (str(prox_cod), serie) in parc_existentes:
                    prox_cod += 1
                codigo_auto = prox_cod
                prox_cod += 1
                codigos_usados.add(str(codigo_auto))

            if not numero_doc:
                numero_doc_exib = f"AUTO-{codigo_auto}"
                status = "OK"
            elif valor <= 0:
                numero_doc_exib = numero_doc
                status = "ERRO (Valor inv\u00e1lido)"
            elif not razao and not documento:
                numero_doc_exib = numero_doc
                status = "ERRO (Sem Fornecedor)"
            else:
                forn_cod = forn_cache.get((documento, razao))
                numero_doc_clean = re.sub(r'\D', '', numero_doc).lstrip('0') or '0'
                if forn_cod and parc_existentes and (numero_doc_clean, parcela, forn_cod) in parc_existentes:
                    numero_doc_exib = numero_doc
                    status = "J\u00c1 CADASTRADO"
                else:
                    numero_doc_exib = numero_doc
                    status = "OK"
                    validos += 1

            if not numero_doc:
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

            if status == "OK":
                situacao = "Aberto"
                vrec = self._parse_valor(reg.get('valor_recebido', '0'))
                if vrec >= valor:
                    situacao = "Pago"
                elif vrec > 0:
                    situacao = "Parcial"
            else:
                situacao = ""
            reg['_situacao'] = situacao

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
            self._salvar_config_mapeamento()
            self.btn_importar.config(state=tk.DISABLED)
            self.btn_analisar.config(state=tk.DISABLED)
            self.lbl_status.config(text="Importando contas a pagar...")
            threading.Thread(target=self._importacao_bg, args=(selecionados, lc_selecionado), daemon=True).start()

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

    def _importacao_bg(self, selecionados, lc_selecionado=None):
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

            with FirebirdService(self.config_db) as fb:
                conta_pagar = self._buscar_conta_padrao(fb, emp, fil)

                tit_existentes = {}
                for row in fb.query(
                    "SELECT TIT_CODIGO, TIT_FORNECEDOR FROM TABELA_TITULO WHERE TIT_EMPRESA = ? AND TIT_FILIAL = ?",
                    [emp, fil]
                ):
                    cod = str(row['tit_codigo'] or '').strip().lstrip('0')
                    forn = int(row['tit_fornecedor'] or 0)
                    if cod:
                        tit_existentes[(cod, forn)] = True

                grupos = {}
                for item in selecionados:
                    if item.get('_status') != 'OK':
                        continue
                    num_doc = item.get('_numero_doc_auto', '') or str(item.get('numero_doc', '')).strip()
                    serie = item.get('_serie', SERIE_PADRAO)
                    documento = item.get('_documento_limpo', '')
                    razao = str(item.get('razao', '')).strip()
                    emissao_key = self._parse_data(item.get('emissao', '')) or ''
                    grupos.setdefault((num_doc, serie, documento, razao, emissao_key), []).append(item)

                ult_grav = agora.strftime('%Y-%m-%d %H:%M:%S')

                for (num_doc, serie, documento, razao, emissao_key), itens_grupo in grupos.items():
                    try:
                        ref = itens_grupo[0]

                        fornecedor_codigo = self._buscar_fornecedor(fb, emp, fil, documento, razao)
                        if fornecedor_codigo is None:
                            log_linhas.append(f"\u26a0 {num_doc} — Fornecedor n\u00e3o encontrado, pulando grupo")
                            erros += 1
                            continue

                        emissao = self._parse_data(ref.get('emissao', '')) or agora.date()
                        vencimento = self._parse_data(ref.get('vencimento', ''))
                        data_registro = self._parse_data(ref.get('data_registro', '')) or agora.date()
                        if vencimento is None:
                            vencimento = emissao + datetime.timedelta(days=30)
                        dias = (vencimento - emissao).days if vencimento else 0

                        if num_doc.startswith('AUTO-'):
                            codigo_tit = self._gerar_codigo_titulo(fb, emp, fil)
                        else:
                            codigo_tit = re.sub(r'\D', '', num_doc).lstrip('0')

                        titulo_existe = (codigo_tit, fornecedor_codigo) in tit_existentes

                        parc_existentes = set()
                        if titulo_existe:
                            for row in fb.query(
                                "SELECT TPARC_PARCELA FROM TABELA_TITULO_PARCELA WHERE TPARC_EMPRESA = ? AND TPARC_FILIAL = ? "
                                "AND TPARC_CODIGO = ? AND TPARC_FORNECEDOR = ?",
                                [emp, fil, codigo_tit, fornecedor_codigo]
                            ):
                                parc_existentes.add(int(row['tparc_parcela']))

                        itens_novos = []
                        for item in itens_grupo:
                            parcela_num = item.get('_parcela_auto') or self._parse_parcela(item.get('parcela', ''))
                            if parcela_num in parc_existentes:
                                log_linhas.append(f"\u26a0 {num_doc} \u2014 Parcela {parcela_num} j\u00e1 existe, pulando")
                                continue
                            itens_novos.append(item)

                        if not itens_novos:
                            continue

                        total_grupo = sum(self._parse_valor(item.get('valor', '0')) for item in itens_novos)

                        def processar_grupo(cur):
                            if not titulo_existe:
                                cur.execute(
                                    "DELETE FROM TABELA_TITULO_PARCELA WHERE TPARC_EMPRESA = ? AND TPARC_FILIAL = ? "
                                    "AND TPARC_CODIGO = ? AND TPARC_SERIE = ? AND TPARC_FORNECEDOR = ?",
                                    [emp, fil, codigo_tit, serie, fornecedor_codigo]
                                )
                                cur.execute(
                                    "DELETE FROM TABELA_TITULO WHERE TIT_EMPRESA = ? AND TIT_FILIAL = ? "
                                    "AND TIT_CODIGO = ? AND TIT_SERIE = ? AND TIT_FORNECEDOR = ?",
                                    [emp, fil, codigo_tit, serie, fornecedor_codigo]
                                )
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
                                        ?, ?,
                                        ?,
                                        ?, ?,
                                        ?,
                                        ?,
                                        ?,
                                        ?, ?, ?, ?,
                                        ?, ?,
                                        ?, ?,
                                        ?, ?,
                                        ?, ?,
                                        ?,
                                        ?,
                                        ?,
                                        ?, ?
                                    )
                                """, [
                                    emp, fil, codigo_tit, serie,
                                    emp, fil, fornecedor_codigo,
                                    emissao, data_registro,
                                    emp, fil, 2,
                                    len(itens_novos), vencimento,
                                    0.0, 0.0, 0.0,
                                    dias,
                                    'IMP',
                                    total_grupo,
                                    0.0, 0.0, 0.0, 0.0, 0.0,
                                    emp, fil,
                                    0.0,
                                    total_grupo, total_grupo,
                                    None,
                                    total_grupo, total_grupo,
                                    'SISTEC_IMP',
                                    str(codigo_tit),
                                    ult_grav,
                                    lc_emp, lc_fil, lc_cod
                                ])

                            max_parcela = max(
                                item.get('_parcela_auto') or self._parse_parcela(item.get('parcela', ''))
                                for item in itens_novos
                            )
                            prox_parcela_saldo = self._proxima_parcela(fb, emp, fil, codigo_tit, serie)
                            if prox_parcela_saldo <= max_parcela:
                                prox_parcela_saldo = max_parcela + 1

                            for item in itens_novos:
                                parcela = item.get('_parcela_auto') or self._parse_parcela(item.get('parcela', ''))
                                valor = self._parse_valor(item.get('valor', '0'))
                                valor_recebido = self._parse_valor(item.get('valor_recebido', '0'))
                                desconto = self._parse_valor(item.get('desconto', '0'))
                                juros = self._parse_valor(item.get('juros', '0'))
                                venc_parc = self._parse_data(item.get('vencimento', '')) or vencimento
                                item_emissao = self._parse_data(item.get('emissao', '')) or emissao
                                dias_parc = (venc_parc - item_emissao).days if venc_parc else dias

                                tp_valor_pg = valor_recebido if valor_recebido > 0 else 0
                                data_recebimento = self._parse_data(item.get('data_recebimento', ''))
                                boleto = str(item.get('boleto', '') or '').strip()

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
                                        ?,
                                        ?,
                                        ?, ?, ?, ?,
                                        ?, ?, ?,
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

                                def inserir_parcela_cur(parcela_num, valor_parc, valor_pg, pg_sn,
                                                        val_desc, val_juros, parc_venc, parc_boleto=''):
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
                                        val_desc, val_juros,
                                        0.0, 0.0,
                                        ult_grav,
                                        0.0,
                                        parc_boleto or None,
                                        f"IMP {num_doc} {str(item.get('razao',''))[:30]}".strip(),
                                        emp, fil, conta_pagar[0], conta_pagar[1], conta_pagar[2],
                                    ]
                                    try:
                                        cur.execute(sql_parc, params_parc)
                                    except Exception as e:
                                        log_linhas.append(f"  !!! PARCEL INSERT ERROR: {e}")
                                        log_linhas.append(f"  !!! Key: (emp={emp}, fil={fil}, cod={codigo_tit}, serie={serie}, parc={parcela_num}, forn={fornecedor_codigo})")
                                        raise

                                if tp_valor_pg > 0 and tp_valor_pg < valor:
                                    saldo = valor - tp_valor_pg
                                    inserir_parcela_cur(parcela, tp_valor_pg, tp_valor_pg, 'S',
                                                        desconto, juros, venc_parc, boleto)
                                    inserir_parcela_cur(prox_parcela_saldo, saldo, 0, 'N',
                                                        0.0, 0.0, venc_parc, boleto)
                                    prox_parcela_saldo += 1
                                    log_linhas.append(f"  {num_doc} \u2014 Parcela {parcela} parcial: pago {tp_valor_pg:.2f}, saldo {saldo:.2f} vira parcela {prox_parcela_saldo - 1}")
                                elif tp_valor_pg >= valor and data_recebimento:
                                    juros_excedente = tp_valor_pg - valor
                                    inserir_parcela_cur(parcela, valor, valor, 'S',
                                                        desconto, juros_excedente if juros_excedente > 0 else juros, venc_parc, boleto)
                                    log_linhas.append(f"  {num_doc} \u2014 Parcela {parcela} valor {valor:.2f} pago integral")
                                else:
                                    inserir_parcela_cur(parcela, valor, 0, 'N',
                                                        desconto, juros, venc_parc, boleto)
                                    log_linhas.append(f"  {num_doc} \u2014 Parcela {parcela} valor {valor:.2f} em aberto")

                        fb.transaction(processar_grupo)
                        inseridos += 1
                        if not titulo_existe:
                            tit_existentes[(codigo_tit, fornecedor_codigo)] = True

                    except Exception as e:
                        erros += 1
                        log_linhas.append(f"\u274c Erro ao inserir {num_doc}: {e}")

            msg = f"Processamento conclu\u00eddo!\n\n{inseridos} t\u00edtulo(s) cadastrados."
            if erros:
                msg += f"\n{erros} erro(s) durante a importa\u00e7\u00e3o. Veja o log para detalhes."
            self.parent.after(0, lambda m=msg: self._safe_showinfo("Conclu\u00eddo", m))

            log_str = "\n".join(log_linhas)
            self.parent.after(0, lambda l=log_str: self._oferecer_log(l))

            try:
                with FirebirdService(self.config_db) as fb:
                    emp_r = int(self.config.get('IMPORTACAO', 'empresa', fallback='1'))
                    fil_r = int(self.config.get('IMPORTACAO', 'filial', fallback='1'))
                    rows = fb.query(
                        "SELECT TPARC_CODIGO, TPARC_PARCELA, TPARC_FORNECEDOR "
                        "FROM TABELA_TITULO_PARCELA WHERE TPARC_EMPRESA = ? AND TPARC_FILIAL = ?",
                        [emp_r, fil_r]
                    )
                    parc_existentes = {}
                    for row in rows:
                        chave = (str(row['tparc_codigo'] or '').strip().lstrip('0'),
                                 int(row['tparc_parcela'] or 1),
                                 int(row['tparc_fornecedor'] or 0))
                        parc_existentes[chave] = True
                    dados_existentes = {'parc_existentes': parc_existentes, 'fornecedor_cache': getattr(self, '_forn_cache', {})}
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

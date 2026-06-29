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

CAMPOS_DISPONIVEIS = [
    ("N\u00famero Documento *", "numero_doc", True),
    ("Parcela", "parcela", False),
    ("Cliente (CNPJ/CPF)", "documento", False),
    ("Cliente (Raz\u00e3o Social)", "razao", False),
    ("Valor da Conta *", "valor", True),
    ("Valor Recebido", "valor_recebido", False),
    ("Data Emiss\u00e3o", "emissao", False),
    ("Vencimento", "vencimento", False),
    ("Data Registro", "data_registro", False),
    ("Data Recebimento", "data_recebimento", False),
    ("Desconto", "desconto", False),
    ("Juros e Multa", "juros", False),
    ("S\u00e9rie", "serie", False),
    ("N\u00famero Boleto", "boleto", False),
    ("Observa\u00e7\u00e3o", "observacao", False),
]

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
        header = tk.Frame(self, bg="#003399", padx=15, pady=8)
        header.pack(fill=tk.X, pady=(0, 10))
        tk.Label(header, text="IMPORTA\u00c7\u00c3O DE CONTAS A RECEBER VIA PLANILHA (Excel/CSV)",
                 font=("Segoe UI", 14, "bold"), bg="#003399", fg="white").pack(anchor=tk.W)

        # --- CARDS DE RESUMO ---
        frame_cards = ttk.Frame(self)
        frame_cards.pack(fill=tk.X, pady=(8, 2), padx=5)

        self.card_recebido = self._criar_card(frame_cards, "Valor Recebido", "R$ 0,00", "#27AE60")
        self.card_recebido.pack(side=tk.RIGHT, padx=5)

        self.card_aberto = self._criar_card(frame_cards, "Valor em Aberto", "R$ 0,00", "#E67E22")
        self.card_aberto.pack(side=tk.RIGHT, padx=5)

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
        self.cb_filtro_situacao = ttk.Combobox(filter_row, values=["Todas", "Aberto", "Parcial", "Recebido"],
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

        footer = tk.Frame(self, bg="#f0f0f0", padx=10, pady=6)
        footer.pack(fill=tk.X, pady=(4, 0))

        tk.Button(footer, text="⬅ VOLTAR", command=self._fechar_tela,
                  font=("Segoe UI", 9, "bold"), bg="#95a5a6", fg="white",
                  cursor="hand2", padx=12, pady=2).pack(side=tk.LEFT)

        self.btn_recalcular = tk.Button(footer, text="🔁 Recalcular Títulos",
                                         font=("Segoe UI", 9, "bold"), bg="#E67E22", fg="white",
                                         cursor="hand2", padx=12, pady=2,
                                         command=self._recalcular_titulos)
        self.btn_recalcular.pack(side=tk.RIGHT, padx=3)

        self.btn_importar = tk.Button(footer, text="🚀 Processar e Injetar no ERP", state=tk.DISABLED,
                                       font=("Segoe UI", 9, "bold"), bg="#003399", fg="white",
                                       cursor="hand2", padx=14, pady=2,
                                       command=self._iniciar_importacao)
        self.btn_importar.pack(side=tk.RIGHT, padx=3)

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
            dados_existentes = {'documentos_tit': {}, 'nomes_tit': {}, 'proximo_codigo': 1}
            try:
                with FirebirdService(self.config_db) as fb:
                    emp = int(self.config.get('IMPORTACAO', 'empresa', fallback='1'))
                    fil = int(self.config.get('IMPORTACAO', 'filial', fallback='1'))
                    rows = fb.query(
                        "SELECT TIT_CODIGO, TIT_SERIE FROM TABELA_TITULO_REC WHERE TIT_EMPRESA = ? AND TIT_FILIAL = ?",
                        [emp, fil]
                    )
                    for row in rows:
                        chave = (str(row['tit_codigo'] or '').strip().lstrip('0'), str(row['tit_serie'] or '').strip())
                        if chave[0]:
                            dados_existentes['documentos_tit'][chave] = True
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

        docs_existentes = dados_existentes.get('documentos_tit', {}) if dados_existentes else {}
        prox_cod = dados_existentes.get('proximo_codigo', 1) if dados_existentes else 1
        codigos_usados = set()

        items = []
        validos = 0
        for reg in self.registros_lidos:
            parcela = self._parse_parcela(reg.get('parcela', ''))
            valor = self._parse_valor(reg.get('valor', '0'))
            razao = str(reg.get('razao', '')).strip()
            documento = self._normalizar_documento(reg.get('documento', ''))
            serie = str(reg.get('serie', '')).strip().upper() or SERIE_PADRAO
            numero_doc = str(reg.get('numero_doc', '')).strip()

            codigo_auto = None
            if not numero_doc:
                while str(prox_cod) in codigos_usados or (str(prox_cod), serie) in docs_existentes:
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
                status = "ERRO (Sem Cliente)"
            elif docs_existentes and (numero_doc.lstrip('0'), serie) in docs_existentes:
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
                    situacao = "Recebido"
                elif vrec > 0:
                    situacao = "Parcial"
            else:
                situacao = ""
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
            if not v or v == '-': return -999999 if reverse else 999999
            try: return float(v.replace(',', '.'))
            except ValueError: return v.lower()
        l.sort(key=lambda t: valor_para_ordenar(t[0]), reverse=reverse)
        for index, (_, k) in enumerate(l): self.tree.move(k, '', index)
        for c in self.colunas:
            arrow = " ▼" if self._sort_directions[c] else " ▲" if c == col else " ↕"
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

    def _atualizar_cards_resumo(self):
        """Calcula e atualiza os valores nos cards de resumo."""
        total_aberto = 0.0
        total_recebido = 0.0

        # Itera apenas sobre os itens visíveis na grade
        for item_id in self.tree.get_children():
            reg = self.dados_grid.get(item_id)
            if not reg:
                continue

            valor = self._parse_valor(reg.get('valor', '0'))
            valor_recebido = self._parse_valor(reg.get('valor_recebido', '0'))
            situacao = reg.get('_situacao', '')

            if situacao == "Aberto":
                total_aberto += valor
            elif situacao == "Recebido":
                total_recebido += valor
            elif situacao == "Parcial":
                total_recebido += valor_recebido
                total_aberto += (valor - valor_recebido)

        self.card_aberto.lbl_valor.config(text=f"R$ {total_aberto:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        self.card_recebido.lbl_valor.config(text=f"R$ {total_recebido:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

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
            self._salvar_config_mapeamento()
            self.btn_importar.config(state=tk.DISABLED)
            self.btn_analisar.config(state=tk.DISABLED)
            self.lbl_status.config(text="Importando contas a receber...")
            threading.Thread(target=self._importacao_bg, args=(selecionados, lc_selecionado), daemon=True).start()

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
                tit_existentes = {}
                for row in fb.query(
                    "SELECT TIT_CODIGO, TIT_SERIE FROM TABELA_TITULO_REC WHERE TIT_EMPRESA = ? AND TIT_FILIAL = ?",
                    [emp, fil]
                ):
                    k = (str(row['tit_codigo'] or '').strip().lstrip('0'), str(row['tit_serie'] or '').strip())
                    tit_existentes[k] = True

                # Agrupa por (numero_doc, serie)
                grupos = {}
                for item in selecionados:
                    if item.get('_status') != 'OK':
                        continue
                    num_doc = item.get('_numero_doc_auto', '') or str(item.get('numero_doc', '')).strip()
                    serie = item.get('_serie', SERIE_PADRAO)
                    grupos.setdefault((num_doc, serie), []).append(item)

                ult_grav = agora.strftime('%Y-%m-%d %H:%M:%S')

                for (num_doc, serie), itens_grupo in grupos.items():
                    try:
                        ref = itens_grupo[0]
                        documento = ref.get('_documento_limpo', '')
                        razao = str(ref.get('razao', '')).strip()

                        cliente_codigo = self._buscar_cliente(fb, emp, fil, documento, razao)
                        if cliente_codigo is None:
                            log_linhas.append(f"⚠ {num_doc} — Cliente n\u00e3o encontrado, pulando grupo")
                            erros += 1
                            continue

                        vendedor_codigo = self._buscar_vendedor_cliente(fb, emp, fil, cliente_codigo)

                        # Dados do titulo (usando primeiro item como referencia)
                        emissao = self._parse_data(ref.get('emissao', '')) or agora.date()
                        vencimento = self._parse_data(ref.get('vencimento', ''))
                        data_registro = self._parse_data(ref.get('data_registro', '')) or agora.date()
                        if vencimento is None:
                            vencimento = emissao + datetime.timedelta(days=30)
                        dias = (vencimento - emissao).days if vencimento else 0

                        # Gera codigo se for auto
                        if num_doc.startswith('AUTO-'):
                            codigo_tit = self._gerar_codigo_titulo(fb, emp, fil)
                        else:
                            codigo_tit = num_doc.lstrip('0')

                        titulo_existe = (codigo_tit, serie) in tit_existentes

                        parc_existentes = set()
                        if titulo_existe:
                            for row in fb.query(
                                "SELECT TPARC_PARCELA FROM TABELA_TITULO_PARCELA_REC WHERE TPARC_EMPRESA = ? AND TPARC_FILIAL = ? "
                                "AND TPARC_CODIGO = ? AND TPARC_SERIE = ? AND TPARC_CLIENTE = ?",
                                [emp, fil, codigo_tit, serie, cliente_codigo]
                            ):
                                parc_existentes.add(int(row['tparc_parcela']))

                        itens_novos = []
                        for item in itens_grupo:
                            parcela_num = item.get('_parcela_auto') or self._parse_parcela(item.get('parcela', ''))
                            if parcela_num in parc_existentes:
                                log_linhas.append(f"  {num_doc} — Parcela {parcela_num} j\u00e1 existe, pulando")
                                continue
                            itens_novos.append(item)

                        if not itens_novos:
                            log_linhas.append(f"\u26a0 {num_doc} — Todas as parcelas j\u00e1 existem, pulando grupo")
                            continue

                        total_grupo = sum(self._parse_valor(item.get('valor', '0')) for item in itens_novos)

                        def inserir_titulo(valor_tit):
                            fb.execute("""
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
                                ) VALUES (
                                    ?, ?, ?, ?,
                                    ?, ?, ?,
                                    ?, ?,
                                    ?, ?, ?,
                                    ?, ?, ?,
                                    ?, ?,
                                    ?, ?, ?,
                                    ?, ?, ?,
                                    ?, ?,
                                    ?, ?, ?, ?,
                                    'N',
                                    ?, ?,
                                    'N', 'SISTEC_IMP',
                                    ?, ?,
                                    ?, ?,
                                    ?,
                                    NULL,
                                    ?, ?
                                )
                            """, [
                                emp, fil, codigo_tit, serie,
                                emp, fil, cliente_codigo,
                                emissao, data_registro,
                                emp, fil, 2,
                                1, vencimento, dias,
                                valor_tit, 'IMP',
                                valor_tit, emp, fil,
                                emp, fil, vendedor_codigo,
                                0.0, 0.0,
                                valor_tit, valor_tit, valor_tit, valor_tit,
                                emp, fil,
                                emp, fil,
                                emp, fil,
                                ult_grav,
                                emp, fil
                            ])

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
                                vendedor_codigo, 0.0,
                                1 if pg_sn == 'S' else None,
                                 ult_grav,
                                 emp, fil,
                                 0.0, val_juros if situacao_pg else 0.0,
                                 0.0,
                                 parc_boleto or None
                             ]

                            try:
                                fb.execute(sql_parc, params_parc)
                            except Exception as e:
                                log_linhas.append(f"  !!! PARCEL INSERT ERROR: {e}")
                                log_linhas.append(f"  !!! Key: (emp={emp}, fil={fil}, cod={codigo_tit}, serie={serie}, parc={parcela_num}, cli={cliente_codigo})")
                                raise

                            if pg_sn == 'S' and baixa_data:
                                try:
                                    fb.execute("""
                                        UPDATE TABELA_TITULO_PARCELA_REC SET
                                            TPARC_BAIXA = ?,
                                            TPARC_DATA_CREDITO = ?,
                                            TPARC_DATA_CREDITO_BAIXA = ?
                                        WHERE TPARC_EMPRESA = ? AND TPARC_FILIAL = ? AND TPARC_CODIGO = ? AND TPARC_SERIE = ? AND TPARC_PARCELA = ?
                                    """, [baixa_data, tp_data_cred, tp_data_cred, emp, fil, codigo_tit, serie, parcela_num])
                                except Exception as e:
                                    log_linhas.append(f"  !!! PARCEL UPDATE ERROR: {e}")

                        # Cria o titulo apenas se for novo
                        if not titulo_existe:
                            inserir_titulo(total_grupo)
                            inseridos += 1
                            tit_existentes[(codigo_tit, serie)] = True
                        else:
                            log_linhas.append(f"  {num_doc} — T\u00edtulo existente, inserindo apenas parcelas novas")
                            fb.execute("""
                                UPDATE TABELA_TITULO_REC SET
                                    TIT_TOTAL = COALESCE(TIT_TOTAL, 0) + ?,
                                    TIT_TOTAL_PARCELAS = COALESCE(TIT_TOTAL_PARCELAS, 0) + ?,
                                    TIT_TOTAL_CC = COALESCE(TIT_TOTAL_CC, 0) + ?,
                                    TIT_TOTAL_CONTABIL = COALESCE(TIT_TOTAL_CONTABIL, 0) + ?,
                                    TIT_VALOR = COALESCE(TIT_VALOR, 0) + ?,
                                    TIT_TOTAL_NF = COALESCE(TIT_TOTAL_NF, 0) + ?,
                                    TIT_ULT_GRAVACAO = ?
                                WHERE TIT_EMPRESA = ? AND TIT_FILIAL = ? AND TIT_CODIGO = ? AND TIT_SERIE = ?
                            """, [total_grupo, total_grupo, total_grupo, total_grupo, total_grupo, total_grupo,
                                  ult_grav, emp, fil, codigo_tit, serie])

                        # Descobre o maior numero de parcela do grupo para sequenciar saldos
                        max_parcela = max(self._parse_parcela(item.get('parcela', '')) for item in itens_novos)
                        prox_parcela_saldo = self._proxima_parcela(fb, emp, fil, codigo_tit, serie)
                        if prox_parcela_saldo <= max_parcela:
                            prox_parcela_saldo = max_parcela + 1

                        # Cria as parcelas
                        for item in itens_novos:
                            parcela = self._parse_parcela(item.get('parcela', ''))
                            valor = self._parse_valor(item.get('valor', '0'))
                            valor_recebido = self._parse_valor(item.get('valor_recebido', '0'))
                            desconto = self._parse_valor(item.get('desconto', '0'))
                            juros = self._parse_valor(item.get('juros', '0'))
                            venc_parc = self._parse_data(item.get('vencimento', '')) or vencimento

                            tp_valor_pg = valor_recebido if valor_recebido > 0 else 0
                            data_recebimento = self._parse_data(item.get('data_recebimento', ''))

                            boleto = str(item.get('boleto', '') or '').strip()

                            if tp_valor_pg > 0 and tp_valor_pg < valor:
                                # Pagamento parcial: divide em duas parcelas
                                saldo = valor - tp_valor_pg

                                inserir_parcela(parcela, tp_valor_pg, tp_valor_pg, 'S',
                                                data_recebimento, data_recebimento,
                                                desconto, juros, True, venc_parc, boleto)

                                inserir_parcela(prox_parcela_saldo, saldo, 0, 'N',
                                                None, None,
                                                0.0, 0.0, False, venc_parc, boleto)
                                prox_parcela_saldo += 1

                                log_linhas.append(f"  {num_doc} — Parcela {parcela} parcial: pago {tp_valor_pg:.2f}, saldo {saldo:.2f} vira parcela {prox_parcela_saldo - 1}")
                            elif tp_valor_pg >= valor and data_recebimento:
                                juros_excedente = tp_valor_pg - valor
                                inserir_parcela(parcela, valor, valor, 'S',
                                                data_recebimento, data_recebimento,
                                                desconto, juros_excedente if juros_excedente > 0 else juros, True, venc_parc, boleto)
                                log_linhas.append(f"  {num_doc} — Parcela {parcela} valor {valor:.2f} recebido integral")
                            else:
                                inserir_parcela(parcela, valor, 0, 'N',
                                                None, None,
                                                desconto, juros, False, venc_parc, boleto)
                                log_linhas.append(f"  {num_doc} — Parcela {parcela} valor {valor:.2f} em aberto")

                    except Exception as e:
                        erros += 1
                        log_linhas.append(f"❌ Erro ao inserir {num_doc}: {e}")

            msg = f"Processamento conclu\u00eddo!\n\n{inseridos} t\u00edtulo(s) cadastrados."
            if erros:
                msg += f"\n{erros} erro(s) durante a importa\u00e7\u00e3o. Veja o log para detalhes."
            self.parent.after(0, lambda m=msg: self._safe_showinfo("Conclu\u00eddo", m))

            log_str = "\n".join(log_linhas)
            self.parent.after(0, lambda l=log_str: self._oferecer_log(l))

            try:
                with FirebirdService(self.config_db) as fb:
                    rows = fb.query(
                        "SELECT TIT_CODIGO, TIT_SERIE FROM TABELA_TITULO_REC WHERE TIT_EMPRESA = ? AND TIT_FILIAL = ?",
                        [emp, fil]
                    )
                    dados_existentes = {'documentos_tit': {}}
                    for row in rows:
                        k = (str(row['tit_codigo'] or '').strip().lstrip('0'), str(row['tit_serie'] or '').strip())
                        if k[0]:
                            dados_existentes['documentos_tit'][k] = True
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

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import configparser
import threading
import re
import os

from utils.excel_reader import obter_abas_planilha, ler_planilha_produtos
from utils.firebird_service import FirebirdService


CAMPOS_MAPEAMENTO = [
    ("NCM *", "ncm", True),
    ("Descrição", "descricao", False),
    ("ICMS - UF", "icms_uf", False),
    ("ICMS - CST", "icms_cst", False),
    ("ICMS - Alíquota %", "icms_aliquota", False),
    ("ICMS - Redução %", "icms_reducao", False),
    ("PIS - CST", "pis_cst", False),
    ("PIS - %", "pis_pct", False),
    ("COFINS - CST", "cofins_cst", False),
    ("COFINS - %", "cofins_pct", False),
    ("RT - Classe Trib", "rt_class", False),
    ("RT - CST", "rt_cst", False),
    ("IBS - %", "ibs_pct", False),
    ("CBS - %", "cbs_pct", False),
]

class TelaImportacaoPlanilhaTributacao(ttk.Frame):
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
        header = tk.Frame(self, bg="#003399", padx=15, pady=8)
        header.pack(fill=tk.X, pady=(0, 10))
        tk.Label(header, text="IMPORTAÇÃO DE TRIBUTAÇÃO VIA PLANILHA (Excel/CSV)",
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
        linhas_campos = [CAMPOS_MAPEAMENTO[i:i+4] for i in range(0, len(CAMPOS_MAPEAMENTO), 4)]
        for i_linha, grupo in enumerate(linhas_campos):
            for i_col, (lbl_texto, chave, obrigatorio) in enumerate(grupo):
                col = i_col * 2
                fg_color = "#C8001E" if obrigatorio else "#1A1A1A"
                tk.Label(frame_map, text=lbl_texto, font=("Segoe UI", 8, "bold"),
                         fg=fg_color).grid(row=i_linha, column=col, padx=(5, 1), pady=2, sticky=tk.E)
                ent = ttk.Entry(frame_map, width=5, font=("Segoe UI", 9))
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

        self.lbl_status = ttk.Label(actions_row, text="Aguardando configuração...", font=("Segoe UI", 9), foreground="#555")
        self.lbl_status.pack(side=tk.LEFT, padx=2)

        filter_row = ttk.Frame(self)
        filter_row.pack(fill=tk.X, pady=(2, 0))

        tk.Label(filter_row, text="Filtrar Status:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 2))
        self.cb_filtro_status = ttk.Combobox(filter_row, values=["Todos", "NOVO", "OK"],
                                              state="readonly", width=18, font=("Segoe UI", 9))
        self.cb_filtro_status.current(0)
        self.cb_filtro_status.pack(side=tk.LEFT, padx=2)
        self.cb_filtro_status.bind("<<ComboboxSelected>>", self._filtrar_status)

        frame_grade = ttk.Frame(self)
        frame_grade.pack(fill=tk.BOTH, expand=True, pady=4)

        self.colunas = ("SEL", "STATUS", "NCM", "DESCRIÇÃO", "ICMS", "PIS", "COFINS", "RT")
        self._sort_directions = {col: False for col in self.colunas}
        self.tree = ttk.Treeview(frame_grade, columns=self.colunas, show="headings")

        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)

        larguras = [40, 80, 100, 250, 60, 60, 60, 60]
        for col, larg in zip(self.colunas, larguras):
            self.tree.heading(col, text=col + " ↕", command=lambda c=col: self._sort_treeview(c))
            self.tree.column(col, width=larg, anchor=tk.CENTER if col not in ("DESCRIÇÃO", "NCM") else tk.W)

        self.tree.tag_configure('NOVO', background='#EAFAF1', foreground='#1E8449')
        self.tree.tag_configure('OK', background='#FFFFFF', foreground='black')

        scroll_y = ttk.Scrollbar(frame_grade, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        footer = tk.Frame(self, bg="#f0f0f0", padx=10, pady=6)
        footer.pack(fill=tk.X, pady=(4, 0))

        tk.Button(footer, text="⬅ VOLTAR", command=self._fechar_tela,
                  font=("Segoe UI", 9, "bold"), bg="#95a5a6", fg="white",
                  cursor="hand2", padx=12, pady=2).pack(side=tk.LEFT)

        self.btn_importar = tk.Button(footer, text="🚀 Importar Tributação no ERP", state=tk.DISABLED,
                                       font=("Segoe UI", 9, "bold"), bg="#003399", fg="white",
                                       cursor="hand2", padx=14, pady=2,
                                       command=self._iniciar_importacao)
        self.btn_importar.pack(side=tk.RIGHT, padx=3)

    def _salvar_config_mapeamento(self):
        secao = 'IMPORTACAO_TRIBUTACAO'
        if not self.config.has_section(secao):
            self.config.add_section(secao)
        self.config.set(secao, 'ultimo_arquivo', self.caminho_arquivo)
        self.config.set(secao, 'ultima_aba', self.cb_abas.get())
        self.config.set(secao, 'linha_inicial', self.ent_linha_ini.get())
        for chave, ent in self.entradas_map.items():
            self.config.set(secao, f'map_{chave}', ent.get().strip())
        with open('config.ini', 'w', encoding='utf-8') as f:
            self.config.write(f)

    def _carregar_config_mapeamento(self):
        secao = 'IMPORTACAO_TRIBUTACAO'
        if not self.config.has_section(secao):
            return
        arquivo = self.config.get(secao, 'ultimo_arquivo', fallback='')
        if arquivo and os.path.isfile(arquivo):
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
            if abas:
                self.cb_abas.current(0)

    def _fechar_tela(self):
        self.destroy()
        if self.callback_voltar:
            self.callback_voltar()

    def _iniciar_analise(self):
        aba = self.cb_abas.get()
        try:
            linha_ini = int(self.ent_linha_ini.get())
        except ValueError:
            return messagebox.showerror("Erro", "A linha inicial deve ser um número.")

        if not self.caminho_arquivo or not aba:
            return messagebox.showwarning("Aviso", "Selecione o arquivo e a aba antes de continuar.")

        mapa_colunas = {chave: ent.get().strip() for chave, ent in self.entradas_map.items()}
        if not mapa_colunas.get('ncm'):
            return messagebox.showwarning("Aviso", "Você precisa mapear obrigatoriamente a coluna 'NCM'.")

        self._salvar_config_mapeamento()
        self.btn_analisar.config(state=tk.DISABLED)
        self.lbl_status.config(text="Lendo planilha...")
        self.progresso['value'] = 20

        threading.Thread(target=self._analisar_bg, args=(aba, mapa_colunas, linha_ini), daemon=True).start()

    def _formatar_ncm(self, ncm_raw):
        ncm = re.sub(r'\D', '', str(ncm_raw or '')).strip()
        if len(ncm) == 10 and '.' in str(ncm_raw):
            ncm = ncm.replace('.', '')
        ncm = ncm.zfill(8)[:8]
        return ncm

    def _float_br(self, valor):
        if not valor or str(valor).strip() == '':
            return None
        try:
            return float(str(valor).replace(',', '.'))
        except ValueError:
            return None

    def _analisar_bg(self, aba, mapa_colunas, linha_ini):
        try:
            raw = ler_planilha_produtos(self.caminho_arquivo, aba, mapa_colunas, linha_ini)
            self.registros_lidos = raw[:]
            uf_padrao = self.config.get('IMPORTACAO', 'uf', fallback='SP').strip().upper()

            dados_erp = None
            try:
                with FirebirdService(self.config_db) as fb:
                    emp = self.config.get('IMPORTACAO', 'empresa', fallback='1')
                    fil = self.config.get('IMPORTACAO', 'filial', fallback='1')

                    sql_ncm = """SELECT CFIS_CODIGO, CFIS_DESCRICAO, CFIS_ICMS_VENDA,
                                        CFIS_PIS, CFIS_COFINS, CFIS_CST_PIS, CFIS_CST_COFINS
                                 FROM TABELA_class_fiscal
                                 WHERE CFIS_EMPRESA = ? AND CFIS_FILIAL = ?"""
                    rows_ncm = fb.query(sql_ncm, [emp, fil])
                    class_fiscal_map = {}
                    for r in rows_ncm:
                        cod = re.sub(r'\D', '', str(r['cfis_codigo'] or '')).strip()
                        if cod:
                            class_fiscal_map[cod] = r

                    sql_icms = """SELECT AICMS_FAIXA, AICMS_ESTADO, AICMS_SITUACAO_CONT,
                                         AICMS_ALIQUOTA_CONT, AICMS_REDUCAO_CONT
                                  FROM TABELA_ALIQUOTA_ICMS
                                  WHERE AICMS_EMPRESA = ? AND AICMS_FILIAL = ?"""
                    rows_icms = fb.query(sql_icms, [emp, fil])
                    faixas_icms = []
                    for r in rows_icms:
                        faixas_icms.append({
                            'faixa': str(r.get('aicms_faixa', '')).strip(),
                            'estado': str(r.get('aicms_estado', '')).strip().upper(),
                            'cst': str(r.get('aicms_situacao_cont') or '').replace('.', '').lstrip('0').zfill(3),
                            'aliquota': float(r.get('aicms_aliquota_cont') or 0),
                            'reducao': float(r.get('aicms_reducao_cont') or 0),
                        })

                    sql_rt = """SELECT TRT_ID, TRT_CLASS_TRIB_ID, TRT_CST,
                                       TRT_ALIQ_IBS_ESTADUAL, TRT_ALIQ_CBS
                                FROM TABELA_RT_CONFIG_2025_2026"""
                    rows_rt = fb.query(sql_rt, [])
                    regras_rt = []
                    for r in rows_rt:
                        regras_rt.append({
                            'id': str(r.get('trt_id', '')).strip(),
                            'class': str(r.get('trt_class_trib_id') or '').strip().lstrip('0') or '0',
                            'cst': str(r.get('trt_cst') or '').strip().lstrip('0') or '0',
                            'ibs': float(r.get('trt_aliq_ibs_estadual') or 0),
                            'cbs': float(r.get('trt_aliq_cbs') or 0),
                        })

                    dados_erp = {
                        'class_fiscal': class_fiscal_map,
                        'faixas_icms': faixas_icms,
                        'regras_rt': regras_rt,
                        'empresa': emp,
                        'filial': fil,
                    }
            except Exception as e:
                self.parent.after(0, lambda err=e: messagebox.showerror("Erro", f"Falha ao consultar ERP:\n{err}"))
                self.parent.after(0, lambda: self.btn_analisar.config(state=tk.NORMAL))
                return

            self.parent.after(0, lambda: self._renderizar_preview(dados_erp, uf_padrao))
        except Exception as e:
            self.parent.after(0, lambda err=e: messagebox.showerror("Erro", f"Falha na leitura da planilha:\n{err}"))
            self.parent.after(0, lambda: self.btn_analisar.config(state=tk.NORMAL))

    def _renderizar_preview(self, dados_erp, uf_padrao):
        for i in self.tree.get_children():
            self.tree.delete(i)
        self.dados_grid.clear()

        class_fiscal_map = dados_erp.get('class_fiscal', {})
        faixas_icms = dados_erp.get('faixas_icms', [])
        regras_rt = dados_erp.get('regras_rt', [])
        items = []
        validos = 0

        for reg in self.registros_lidos:
            ncm = self._formatar_ncm(reg.get('ncm', ''))
            if not ncm:
                continue
            ncm_fmt = f"{ncm[:4]}.{ncm[4:6]}.{ncm[6:]}"

            descricao = str(reg.get('descricao', '')).strip()
            icms_uf = (str(reg.get('icms_uf', '')).strip().upper() or uf_padrao)
            icms_cst = str(reg.get('icms_cst', '')).replace('.', '').lstrip('0').zfill(3)
            icms_aliquota = self._float_br(reg.get('icms_aliquota'))
            icms_reducao = self._float_br(reg.get('icms_reducao'))
            pis_cst = str(reg.get('pis_cst', '')).strip().zfill(2)
            pis_pct = self._float_br(reg.get('pis_pct'))
            cofins_cst = str(reg.get('cofins_cst', '')).strip().zfill(2)
            cofins_pct = self._float_br(reg.get('cofins_pct'))
            rt_class = str(reg.get('rt_class', '')).strip().lstrip('0') or '0'
            rt_cst = str(reg.get('rt_cst', '')).strip().lstrip('0') or '0'
            ibs_pct = self._float_br(reg.get('ibs_pct')) or 0
            cbs_pct = self._float_br(reg.get('cbs_pct')) or 0

            cf_row = class_fiscal_map.get(ncm)
            ncm_status = "OK" if cf_row else "NOVO"

            icms_faixa_encontrada = None
            icms_status = ""
            if icms_cst or icms_aliquota is not None:
                for f in faixas_icms:
                    if (f['estado'] == icms_uf and f['cst'] == icms_cst and
                        abs(f['aliquota'] - (icms_aliquota or 0)) < 0.01 and
                        abs(f['reducao'] - (icms_reducao or 0)) < 0.01):
                        icms_faixa_encontrada = f['faixa']
                        break
                if icms_faixa_encontrada:
                    icms_status = "OK"
                else:
                    icms_status = "CRIAR"
                reg['_icms_faixa_criar'] = icms_faixa_encontrada
            reg['_icms_faixa'] = icms_faixa_encontrada

            pis_status = ""
            if pis_pct is not None:
                if cf_row:
                    pis_erp = float(cf_row.get('cfis_pis') or 0)
                    if abs(pis_erp - pis_pct) < 0.01:
                        pis_status = "OK"
                    else:
                        pis_status = "ALT"
                else:
                    pis_status = "OK"

            cofins_status = ""
            if cofins_pct is not None:
                if cf_row:
                    cofins_erp = float(cf_row.get('cfis_cofins') or 0)
                    if abs(cofins_erp - cofins_pct) < 0.01:
                        cofins_status = "OK"
                    else:
                        cofins_status = "ALT"
                else:
                    cofins_status = "OK"

            rt_id_encontrado = None
            rt_status = ""
            if rt_class != '0' and rt_cst != '0':
                for r in regras_rt:
                    if (r['class'] == rt_class and r['cst'] == rt_cst and
                        abs(r['ibs'] - ibs_pct) < 0.01 and abs(r['cbs'] - cbs_pct) < 0.01):
                        rt_id_encontrado = r['id']
                        break
                if rt_id_encontrado:
                    rt_status = "OK"
                else:
                    rt_status = "CRIAR"
                reg['_rt_id_criar'] = rt_id_encontrado
            reg['_rt_id'] = rt_id_encontrado

            status_geral = "NOVO" if ncm_status == "NOVO" else "OK"

            reg['_ncm_limpo'] = ncm
            reg['_ncm_formatado'] = ncm_fmt
            reg['_ncm_status'] = ncm_status
            reg['_icms_status'] = icms_status
            reg['_icms_uf'] = icms_uf
            reg['_icms_cst'] = icms_cst
            reg['_icms_aliquota'] = icms_aliquota
            reg['_icms_reducao'] = icms_reducao
            reg['_pis_status'] = pis_status
            reg['_pis_cst'] = pis_cst
            reg['_pis_pct'] = pis_pct
            reg['_cofins_status'] = cofins_status
            reg['_cofins_cst'] = cofins_cst
            reg['_cofins_pct'] = cofins_pct
            reg['_rt_status'] = rt_status
            reg['_rt_class'] = rt_class
            reg['_rt_cst'] = rt_cst
            reg['_ibs_pct'] = ibs_pct
            reg['_cbs_pct'] = cbs_pct
            reg['_cf_row'] = cf_row
            reg['_status_geral'] = status_geral

            if status_geral == "NOVO":
                validos += 1

            check = "☑" if status_geral == "NOVO" else "☐"
            tag = 'NOVO' if status_geral == 'NOVO' else 'OK'

            icms_display = f"{icms_status} ({icms_faixa_encontrada})" if icms_faixa_encontrada else (icms_status if icms_status else '-')
            pis_display = f"{pis_status} ({pis_cst})" if pis_status and pis_cst else (pis_status if pis_status else '-')
            cofins_display = f"{cofins_status} ({cofins_cst})" if cofins_status and cofins_cst else (cofins_status if cofins_status else '-')
            rt_display = rt_status if rt_status else '-'
            if rt_status and rt_class:
                rt_display = f"{rt_status} (Cl.{rt_class})"

            items.append((
                (check, status_geral, ncm, descricao or '-',
                 icms_display, pis_display, cofins_display, rt_display),
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
                if validos > 0:
                    self.btn_importar.config(state=tk.NORMAL)
                self.progresso['value'] = 100
                self.lbl_status.config(
                    text=f"Pronto. {validos} NCMs novos de {total} lidos."
                )
                self.cb_filtro_status.current(0)
                self._filtrar_status()

        render_chunk(0)

    def _on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            item_id = self.tree.identify_row(event.y)
            if not item_id:
                return
            if column == "#1":
                valores = list(self.tree.item(item_id, 'values'))
                valores[0] = "☑" if valores[0] == "☐" else "☐"
                self.tree.item(item_id, values=valores)
                return
            self._update_import_button()

    def _update_import_button(self):
        has_checked = any(
            self.tree.item(item, "values")[0] == "☑"
            for item in self.tree.get_children()
        )
        self.btn_importar.config(state=tk.NORMAL if has_checked else tk.DISABLED)

    def _marcar_todos(self):
        for item in self.tree.get_children():
            v = list(self.tree.item(item, "values"))
            v[0] = "☑"
            self.tree.item(item, values=v)
        self._update_import_button()

    def _desmarcar_todos(self):
        for item in self.tree.get_children():
            v = list(self.tree.item(item, "values"))
            v[0] = "☐"
            self.tree.item(item, values=v)
        self._update_import_button()

    def _sort_treeview(self, col):
        self._sort_directions[col] = not self._sort_directions[col]
        reverse = self._sort_directions[col]
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        def valor_para_ordenar(val):
            v = str(val).strip()
            if not v or v == '-':
                return -999999 if reverse else 999999
            try:
                return float(v.replace(',', '.'))
            except ValueError:
                return v.lower()
        l.sort(key=lambda t: valor_para_ordenar(t[0]), reverse=reverse)
        for index, (_, k) in enumerate(l):
            self.tree.move(k, '', index)
        for c in self.colunas:
            arrow = " ▼" if self._sort_directions[c] else " ▲" if c == col else " ↕"
            self.tree.heading(c, text=c + arrow, command=lambda x=c: self._sort_treeview(x))

    def _filtrar_status(self, event=None):
        filtro = self.cb_filtro_status.get()
        for item in self.tree.get_children():
            self.tree.detach(item)
        for item_id, reg in self.dados_grid.items():
            status = reg.get('_status_geral', '')
            if filtro == "Todos" or status == filtro:
                self.tree.move(item_id, '', tk.END)

    def _iniciar_importacao(self):
        selecionados = []
        for item_id in self.tree.get_children():
            valores = self.tree.item(item_id, "values")
            if valores[0] == "☑":
                selecionados.append(self.dados_grid[item_id])

        if not selecionados:
            messagebox.showwarning("Aviso", "Selecione pelo menos um NCM para importar.")
            return

        resp = messagebox.askyesno("Confirmar",
            f"Deseja importar a tributa\u00e7\u00e3o de {len(selecionados)} NCM(s) no ERP?\n\n"
            "Ser\u00e3o criadas faixas ICMS e regras RT se necess\u00e1rio,\n"
            "e os NCMs ser\u00e3o inseridos/atualizados na classifica\u00e7\u00e3o fiscal.")
        if resp:
            self._salvar_config_mapeamento()
            self.btn_importar.config(state=tk.DISABLED)
            self.btn_analisar.config(state=tk.DISABLED)
            self.lbl_status.config(text="Importando tributação...")
            threading.Thread(target=self._importacao_bg, args=(selecionados,), daemon=True).start()

    def _importacao_bg(self, selecionados):
        log_linhas = []
        try:
            emp = self.config.get('IMPORTACAO', 'empresa', fallback='1')
            fil = self.config.get('IMPORTACAO', 'filial', fallback='1')

            with FirebirdService(self.config_db) as fb:
                inseridos_ncm = 0
                atualizados_ncm = 0
                criados_icms = 0
                criados_rt = 0
                erros = 0

                for reg in selecionados:
                    try:
                        ncm = reg['_ncm_limpo']
                        ncm_fmt = reg['_ncm_formatado']
                        icms_status = reg.get('_icms_status', '')
                        icms_faixa = reg.get('_icms_faixa', '')
                        pis_pct = reg.get('_pis_pct')
                        cofins_pct = reg.get('_cofins_pct')
                        pis_cst = reg.get('_pis_cst', '')
                        cofins_cst = reg.get('_cofins_cst', '')
                        rt_status = reg.get('_rt_status', '')
                        rt_id = reg.get('_rt_id', '')

                        if icms_status == "CRIAR":
                            uf = reg['_icms_uf']
                            cst = reg['_icms_cst']
                            aliq = reg['_icms_aliquota']
                            red = reg['_icms_reducao']

                            res = fb.query(
                                "SELECT COALESCE(MAX(CAST(AICMS_FAIXA AS INTEGER)), 0) + 1 AS NOVO FROM TABELA_ALIQUOTA_ICMS WHERE AICMS_EMPRESA = ? AND AICMS_FILIAL = ?",
                                [emp, fil]
                            )
                            nova_faixa = str(int(res[0]['novo']))
                            data_vig = "01/01/2025"

                            sql_icms_ins = """INSERT INTO TABELA_ALIQUOTA_ICMS
                                (AICMS_EMPRESA, AICMS_FILIAL, AICMS_DATA, AICMS_FAIXA, AICMS_ESTADO,
                                 AICMS_COMPRA_VENDA, AICMS_SITUACAO_CONT, AICMS_ALIQUOTA_CONT, AICMS_REDUCAO_CONT)
                                VALUES (?, ?, ?, ?, ?, 'V', ?, ?, ?)"""
                            fb.execute(sql_icms_ins, [emp, fil, data_vig, nova_faixa, uf, cst, aliq, red])
                            icms_faixa = nova_faixa
                            criados_icms += 1
                            log_linhas.append(f"✅ Faixa ICMS {nova_faixa} criada para {uf} CST {cst}")

                        if rt_status == "CRIAR":
                            rt_class = reg['_rt_class']
                            rt_cst_val = reg['_rt_cst']
                            ibs = reg['_ibs_pct']
                            cbs = reg['_cbs_pct']

                            res = fb.query(
                                "SELECT COALESCE(MAX(CAST(TRT_ID AS INTEGER)), 0) + 1 AS NOVO FROM TABELA_RT_CONFIG_2025_2026"
                            )
                            novo_rt_id = str(int(res[0]['novo']))

                            sql_rt_ins = """INSERT INTO TABELA_RT_CONFIG_2025_2026
                                (TRT_ID, TRT_CLASS_TRIB_ID, TRT_CST, TRT_ALIQ_IBS_ESTADUAL, TRT_ALIQ_CBS)
                                VALUES (?, ?, ?, ?, ?)"""
                            fb.execute(sql_rt_ins, [novo_rt_id, rt_class, rt_cst_val, ibs, cbs])
                            rt_id = novo_rt_id
                            criados_rt += 1
                            log_linhas.append(f"✅ Regra RT {novo_rt_id} criada para Classe {rt_class} CST {rt_cst_val}")

                        descricao = str(reg.get('descricao', '')).strip() or reg.get('_descricao', '')
                        if not descricao:
                            cf = reg.get('_cf_row')
                            if cf and cf.get('cfis_descricao'):
                                descricao = str(cf['cfis_descricao'])

                        if reg['_ncm_status'] == "NOVO":
                            sql_ins = """INSERT INTO TABELA_class_fiscal
                                (CFIS_EMPRESA, CFIS_FILIAL, CFIS_CODIGO, CFIS_DESCRICAO,
                                 CFIS_ICMS_VENDA, CFIS_PIS, CFIS_COFINS, CFIS_CST_PIS, CFIS_CST_COFINS,
                                 CFIS_IPI, CFIS_CST_IPI, CFIS_SUBST_TRIBUTARIA, CFIS_ST_COMPRA)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, '53', 'N', 'N')"""
                            params = [emp, fil, ncm_fmt, descricao or ncm,
                                      icms_faixa if icms_faixa else None,
                                      pis_pct if pis_pct is not None else 0,
                                      cofins_pct if cofins_pct is not None else 0,
                                      pis_cst if pis_cst else '',
                                      cofins_cst if cofins_cst else '']
                            fb.execute(sql_ins, params)
                            inseridos_ncm += 1
                            log_linhas.append(f"✅ NCM {ncm} inserido na classificação fiscal")
                        else:
                            sets = []
                            params_upd = []
                            if descricao:
                                sets.append("CFIS_DESCRICAO = ?")
                                params_upd.append(descricao)
                            if icms_faixa:
                                sets.append("CFIS_ICMS_VENDA = ?")
                                params_upd.append(icms_faixa)
                            if pis_pct is not None:
                                sets.append("CFIS_PIS = ?")
                                params_upd.append(pis_pct)
                            if cofins_pct is not None:
                                sets.append("CFIS_COFINS = ?")
                                params_upd.append(cofins_pct)
                            if pis_cst:
                                sets.append("CFIS_CST_PIS = ?")
                                params_upd.append(pis_cst)
                            if cofins_cst:
                                sets.append("CFIS_CST_COFINS = ?")
                                params_upd.append(cofins_cst)
                            if sets:
                                sql_up = f"UPDATE TABELA_class_fiscal SET {', '.join(sets)} WHERE CFIS_EMPRESA = ? AND CFIS_FILIAL = ? AND CFIS_CODIGO = ?"
                                params_upd.extend([emp, fil, ncm_fmt])
                                fb.execute(sql_up, params_upd)
                                atualizados_ncm += 1
                                log_linhas.append(f"✅ NCM {ncm} atualizado na classificação fiscal")

                    except Exception as e:
                        erros += 1
                        ncm_atual = reg.get('_ncm_limpo', '?')
                        log_linhas.append(f"❌ Erro ao processar NCM {ncm_atual}: {e}")

            msg = f"Processamento concluído!\n\n{inseridos_ncm} NCMs inseridos.\n{atualizados_ncm} NCMs atualizados.\n{criados_icms} faixas ICMS criadas.\n{criados_rt} regras RT criadas."
            if erros:
                msg += f"\n{erros} erro(s). Veja o log."

            self.parent.after(0, lambda m=msg: self._safe_showinfo("Concluído", m))

            log_str = "\n".join(log_linhas)
            self.parent.after(0, lambda l=log_str: self._oferecer_log(l))
            self.parent.after(0, lambda: self._limpar_e_reiniciar())

        except Exception as e:
            self.parent.after(0, lambda err=e: self._safe_showerror("Erro de Importação", f"Ocorreu um erro estrutural:\n{err}"))
        finally:
            self.parent.after(0, lambda: self._resetar_ui())

    def _limpar_e_reiniciar(self):
        self.tree.delete(*self.tree.get_children())
        self.dados_grid.clear()
        self.btn_importar.config(state=tk.DISABLED)
        self.lbl_status.config(text="Pronto. Aguardando nova análise...")
        self.progresso['value'] = 0

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
            "Deseja salvar um arquivo .txt com o log detalhado?")
        if resp:
            caminho = filedialog.asksaveasfilename(
                defaultextension=".txt",
                initialfile="LOG_IMPORTACAO_TRIBUTACAO.txt",
                filetypes=[("Arquivos de Texto", "*.txt")]
            )
            if caminho:
                try:
                    with open(caminho, 'w', encoding='utf-8') as f:
                        f.write("--- LOG DE IMPORTACAO DE TRIBUTACAO VIA PLANILHA ---\n\n")
                        f.write(log_str)
                    messagebox.showinfo("Log Salvo", f"Arquivo salvo em:\n{caminho}")
                    if messagebox.askyesno("Abrir Log", "Deseja abrir o arquivo de log agora?"):
                        try:
                            os.startfile(caminho)
                        except Exception as e:
                            messagebox.showerror("Erro", f"Erro ao abrir arquivo:\n{e}")
                except Exception as e:
                    messagebox.showerror("Erro", f"Erro ao salvar log:\n{e}")

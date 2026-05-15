import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import configparser
import threading
import json
import os
import sys
import csv
import glob
import logging

from utils.xml_reader import parse_nfe_folder, parse_nfe
from utils.firebird_service import FirebirdService

logging.basicConfig(
    filename='sistema_erros.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - [NCM Sync] - %(message)s'
)

class TelaNcm(ttk.Frame):
    def __init__(self, parent, callback_voltar=None):
        super().__init__(parent, padding="10")
        self.parent = parent
        self.callback_voltar = callback_voltar
        self.pack(fill=tk.BOTH, expand=True)

        self.arquivos_selecionados = []
        self.pasta_xmls = ""
        self.dados_sistema = {}
        self.faixas_icms = {}
        self.dados_agrupados = []
        self.dados_grid = {}
        self.valores_tree = []
        self.selecionados_lote = []
        self.cancel_event = threading.Event()
        self.analysis_thread = None
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

    def resource_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def _criar_widgets(self):
        lbl_title = tk.Label(self, text="ANÁLISE DE TRIBUTAÇÃO POR NCM", font=("Segoe UI", 14, "bold"), fg="#2980B9")
        lbl_title.pack(anchor=tk.W, pady=(0, 10))

        frame_dir = ttk.Frame(self)
        frame_dir.pack(fill=tk.X, pady=10)
        
        self.ent_pasta = ttk.Entry(frame_dir, width=60)
        self.ent_pasta.pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_dir, text="📁 Pasta", command=self._selecionar_pasta).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_dir, text="📄 Arquivos", command=self._selecionar_arquivos).pack(side=tk.LEFT, padx=2)
        
        self.btn_analisar = ttk.Button(frame_dir, text="🔍 Analisar NCMs", command=self._iniciar_analise)
        self.btn_analisar.pack(side=tk.RIGHT, padx=5)

        self.btn_cancelar = ttk.Button(frame_dir, text="✖ Cancelar", command=self._cancelar_analise, state=tk.DISABLED)
        self.btn_cancelar.pack(side=tk.RIGHT, padx=5)

        self.btn_sincronizar = tk.Button(
            frame_dir, text="🔄 Sincronizar NCMs Gov.", 
            font=("Segoe UI", 9, "bold"), bg="#8E44AD", fg="#FFFFFF", 
            cursor="hand2", padx=10, command=self._sincronizar_ncm_erp
        )
        self.btn_sincronizar.pack(side=tk.RIGHT, padx=5)

        self.progresso = ttk.Progressbar(frame_dir, orient=tk.HORIZONTAL, mode='determinate', length=200)
        self.progresso.pack(side=tk.RIGHT, padx=10)

        frame_filtro = ttk.Frame(self)
        frame_filtro.pack(fill=tk.X, pady=(5, 10))

        self.var_filtro = tk.StringVar()
        self.var_filtro_ncm = tk.StringVar()
        self.var_filtro_uf = tk.StringVar()
        self.var_filtro_cfop = tk.StringVar()
        self.var_status_filtro = tk.StringVar(value="Todos")

        ttk.Label(frame_filtro, text="Buscar:").pack(side=tk.LEFT, padx=(0, 5))
        self.ent_filtro = ttk.Entry(frame_filtro, textvariable=self.var_filtro, width=20)
        self.ent_filtro.pack(side=tk.LEFT, padx=(0, 5))
        self.ent_filtro.bind('<KeyRelease>', lambda event: self._filtrar_treeview())

        ttk.Label(frame_filtro, text="NCM:").pack(side=tk.LEFT, padx=(10, 5))
        self.ent_filtro_ncm = ttk.Entry(frame_filtro, textvariable=self.var_filtro_ncm, width=12)
        self.ent_filtro_ncm.pack(side=tk.LEFT, padx=(0, 5))
        self.ent_filtro_ncm.bind('<KeyRelease>', lambda event: self._filtrar_treeview())

        ttk.Label(frame_filtro, text="UF:").pack(side=tk.LEFT, padx=(10, 5))
        self.ent_filtro_uf = ttk.Entry(frame_filtro, textvariable=self.var_filtro_uf, width=6)
        self.ent_filtro_uf.pack(side=tk.LEFT, padx=(0, 5))
        self.ent_filtro_uf.bind('<KeyRelease>', lambda event: self._filtrar_treeview())

        ttk.Label(frame_filtro, text="CFOP:").pack(side=tk.LEFT, padx=(10, 5))
        self.ent_filtro_cfop = ttk.Entry(frame_filtro, textvariable=self.var_filtro_cfop, width=8)
        self.ent_filtro_cfop.pack(side=tk.LEFT, padx=(0, 5))
        self.ent_filtro_cfop.bind('<KeyRelease>', lambda event: self._filtrar_treeview())

        ttk.Label(frame_filtro, text="Status:").pack(side=tk.LEFT, padx=(10, 5))
        self.cmb_status_filtro = ttk.Combobox(frame_filtro, textvariable=self.var_status_filtro, values=["Todos", "NOVO", "DIFERENTE", "OK"], state="readonly", width=10)
        self.cmb_status_filtro.pack(side=tk.LEFT, padx=(0, 5))
        self.cmb_status_filtro.bind('<<ComboboxSelected>>', lambda event: self._filtrar_treeview())

        ttk.Button(frame_filtro, text="Limpar filtro", command=self._limpar_filtro).pack(side=tk.LEFT, padx=(10, 0))

        self.lbl_status = ttk.Label(self, text="Aguardando arquivos...", font=("Segoe UI", 9))
        self.lbl_status.pack(anchor=tk.W, padx=10)

        frame_grade = ttk.Frame(self)
        frame_grade.pack(fill=tk.BOTH, expand=True, pady=5)

        colunas = ("SEL", "QTD", "NCM", "STATUS", "DESCRIÇÃO", "UF", "CFOP", "TIPO", 
                   "CST ICMS", "ICMS%", "RED.BC%", "FCP%", "MVA ST%", "ICMS ST%",
                   "CBENEF", "C.CRED", "P.CRED",
                   "CST PIS", "PIS%", "PIS% ERP",
                   "CST COF", "COF%", "COF% ERP",
                   "C. CLASSE RT", "CST RT", "IBS%", "CBS%",
                   "FAIXA ICMS", "FAIXA ERP", "REGRA RT ERP")

        self._sort_directions = {col: False for col in colunas}
        self.tree = ttk.Treeview(frame_grade, columns=colunas, show="headings", height=10)
        
        larguras = [40, 40, 80, 80, 200, 40, 50, 45,
                    70, 60, 60, 50, 60, 70,
                    80, 70, 60,
                    60, 60, 60,
                    60, 60, 60,
                    90, 60, 50, 50,
                    80, 80, 90]
        
        for col, larg in zip(colunas, larguras):
            self.tree.heading(col, text=col + " ↕", command=lambda c=col: self._sort_treeview(c))
            anchor = tk.W if col in ("DESCRIÇÃO",) else tk.CENTER
            self.tree.column(col, width=larg, anchor=anchor)

        self.tree.tag_configure('NOVO', background='#EAFAF1', foreground='#1E8449') 
        self.tree.tag_configure('DIFERENTE', background='#FEF9E7', foreground='#D35400')
        self.tree.tag_configure('OK', background='#FFFFFF', foreground='black')

        scroll_y = ttk.Scrollbar(frame_grade, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.tree.bind("<<TreeviewSelect>>", self._on_selecionar_item)
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Double-1>", self._on_tree_double_click)

        frame_botoes = ttk.Frame(self)
        frame_botoes.pack(fill=tk.X, pady=5)
        
        ttk.Button(frame_botoes, text="☑ Selecionar Todos", command=self._selecionar_todos).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_botoes, text="☐ Limpar", command=self._limpar_selecao).pack(side=tk.LEFT, padx=2)
        
        self.btn_edicao_lote = tk.Button(
            frame_botoes, text="📝 Editar em Lote", font=("Segoe UI", 9, "bold"),
            bg="#27AE60", fg="#FFFFFF", cursor="hand2", state=tk.DISABLED, command=self._abrir_edicao_lote
        )
        self.btn_edicao_lote.pack(side=tk.LEFT, padx=5)

        frame_edicao = ttk.LabelFrame(self, text="Edição do NCM Selecionado", padding="10")
        frame_edicao.pack(fill=tk.X, padx=5, pady=5)
        
        self.var_ncm = tk.StringVar()
        self.var_desc = tk.StringVar()
        self.var_faixa = tk.StringVar()
        self.var_pis = tk.DoubleVar(value=0.0)
        self.var_cofins = tk.DoubleVar(value=0.0)
        self.var_cst_pis = tk.StringVar()
        self.var_cst_cofins = tk.StringVar()
        
        ttk.Label(frame_edicao, text="NCM:").grid(row=0, column=0, sticky=tk.W, padx=5)
        ttk.Entry(frame_edicao, textvariable=self.var_ncm, state="readonly", width=15).grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(frame_edicao, text="Descrição:").grid(row=0, column=2, sticky=tk.W, padx=5)
        ttk.Entry(frame_edicao, textvariable=self.var_desc, width=30).grid(row=0, column=3, columnspan=3, padx=5, pady=2, sticky=tk.W)

        ttk.Label(frame_edicao, text="Faixa ICMS:").grid(row=1, column=0, sticky=tk.W, padx=5)
        ttk.Entry(frame_edicao, textvariable=self.var_faixa, width=10).grid(row=1, column=1, padx=5, pady=2, sticky=tk.W)
        tk.Label(frame_edicao, text="(CFIS_ICMS_VENDA)", font=("Segoe UI", 7), fg="gray").grid(row=2, column=1, sticky=tk.W, padx=5)

        ttk.Label(frame_edicao, text="PIS %:").grid(row=1, column=2, sticky=tk.W, padx=5)
        ttk.Entry(frame_edicao, textvariable=self.var_pis, width=8).grid(row=1, column=3, padx=5, pady=2, sticky=tk.W)

        ttk.Label(frame_edicao, text="CST PIS:").grid(row=1, column=4, sticky=tk.E, padx=5)
        ttk.Entry(frame_edicao, textvariable=self.var_cst_pis, width=5).grid(row=1, column=5, padx=5, pady=2, sticky=tk.W)

        ttk.Label(frame_edicao, text="COFINS %:").grid(row=2, column=2, sticky=tk.W, padx=5)
        ttk.Entry(frame_edicao, textvariable=self.var_cofins, width=8).grid(row=2, column=3, padx=5, pady=2, sticky=tk.W)

        ttk.Label(frame_edicao, text="CST COF:").grid(row=2, column=4, sticky=tk.E, padx=5)
        ttk.Entry(frame_edicao, textvariable=self.var_cst_cofins, width=5).grid(row=2, column=5, padx=5, pady=2, sticky=tk.W)

        frame_btn = ttk.Frame(frame_edicao)
        frame_btn.grid(row=3, column=0, columnspan=6, pady=10)
        
        self.btn_copiar_xml = ttk.Button(frame_btn, text="⬇ Copiar do XML", state=tk.DISABLED, command=self._copiar_xml)
        self.btn_copiar_xml.pack(side=tk.LEFT, padx=5)
        
        self.btn_salvar = ttk.Button(frame_btn, text="💾 Salvar no ERP", state=tk.DISABLED, command=self._salvar_ncm)
        self.btn_salvar.pack(side=tk.LEFT, padx=5)

        frame_fim = ttk.Frame(self)
        frame_fim.pack(fill=tk.X, pady=10)
        ttk.Button(frame_fim, text="⬅ VOLTAR", command=self._fechar_tela).pack(side=tk.LEFT, padx=5)
        
        self.btn_exportar = ttk.Button(frame_fim, text="📋 Exportar CSV", state=tk.DISABLED, command=self._exportar_csv)
        self.btn_exportar.pack(side=tk.RIGHT, padx=5)

    def _atualizar_progresso(self, valor, texto):
        if hasattr(self, 'progresso'):
            self.progresso['value'] = valor
        self.lbl_status.config(text=texto)

    def _sort_treeview(self, col):
        self._sort_directions[col] = not self._sort_directions[col]
        reverse = self._sort_directions[col]
        
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        
        def valor_para_ordenar(val):
            v = str(val).replace('%', '').strip()
            if not v or v == '-':
                return -999999 if reverse else 999999
            try:
                return float(v)
            except ValueError:
                return v.lower()
                
        l.sort(key=lambda t: valor_para_ordenar(t[0]), reverse=reverse)
        
        for index, (_, k) in enumerate(l):
            self.tree.move(k, '', index)
            
        for c in self._sort_directions:
            if c == col:
                arrow = " ▼" if self._sort_directions[c] else " ▲"
            else:
                arrow = " ↕"
            self.tree.heading(c, text=c + arrow, command=lambda x=c: self._sort_treeview(x))

    def _formatar_cst(self, valor):
        if not valor: return ''
        return str(valor).zfill(2)

    def _selecionar_pasta(self):
        pasta = filedialog.askdirectory()
        if pasta:
            self.ent_pasta.delete(0, tk.END); self.ent_pasta.insert(0, pasta)
            self.pasta_xmls = pasta; self.arquivos_selecionados = []

    def _selecionar_arquivos(self):
        arquivos = filedialog.askopenfilenames(filetypes=[("XML", "*.xml")])
        if arquivos:
            self.ent_pasta.delete(0, tk.END); self.ent_pasta.insert(0, f"{len(arquivos)} arquivo(s)")
            self.arquivos_selecionados = list(arquivos); self.pasta_xmls = ""

    def _fechar_tela(self):
        if self.winfo_manager():
            self.pack_forget()
        self.destroy()
        if self.callback_voltar: 
            self.callback_voltar()

    def _carregar_faixas_icms(self):
        try:
            with FirebirdService(self.config_db) as fb:
                sql = """SELECT t1.AICMS_FAIXA, t1.AICMS_ESTADO, t1.AICMS_ALIQUOTA_CONT, t1.AICMS_REDUCAO_CONT,
                         t1.AICMS_SITUACAO_CONT, t1.AICMS_CBENEF_CONT, t1.AICMS_ALIQUOTA_NCONT, t1.AICMS_REDUCAO_NCONT,
                         t1.AICMS_SITUACAO_NCONT, t1.AICMS_CBENEF_NCONT, t1.AICMS_ALIQUOTA_SIMP_NAC, t1.AICMS_REDUCAO_SIMP_NAC,
                         t1.AICMS_SITUACAO_SIMP_NAC,
                         t1.AICMS_CBENEF_SIMP_NAC, t3.CBE_C_CREDPRESUMIDO, t3.CBE_P_CREDPRESUMIDO
                         FROM TABELA_ALIQUOTA_ICMS t1
                         LEFT JOIN TABELA_ALIQUOTA_ICMS_CBENEF t2 ON 
                             t1.AICMS_EMPRESA = t2.TACB_AICMS_EMPRESA AND 
                             t1.AICMS_FILIAL = t2.TACB_AICMS_FILIAL AND 
                             t1.AICMS_DATA = t2.TACB_AICMS_DATA AND 
                             t1.AICMS_FAIXA = t2.TACB_AICMS_FAIXA AND 
                             t1.AICMS_ESTADO = t2.TACB_AICMS_ESTADO
                         LEFT JOIN TABELA_CBENEF t3 ON t2.TACB_CBE_ID = t3.CBE_ID"""
                raw_faixas = fb.query(sql, [])
                
                self.faixas_icms = {}
                for r in raw_faixas:
                    est = str(r.get('aicms_estado') or '').strip().upper()
                    if est not in self.faixas_icms:
                        self.faixas_icms[est] = []
                    
                    r['_cst_cont'] = str(r.get('aicms_situacao_cont') or '').replace('.','').lstrip('0').zfill(3)
                    r['_cbenef_cont'] = str(r.get('aicms_cbenef_cont') or '').strip().upper()
                    r['_alq_cont'] = float(r.get('aicms_aliquota_cont') or 0)
                    r['_red_cont'] = float(r.get('aicms_reducao_cont') or 0)
                    
                    r['_cst_ncont'] = str(r.get('aicms_situacao_ncont') or '').replace('.','').lstrip('0').zfill(3)
                    r['_cbenef_ncont'] = str(r.get('aicms_cbenef_ncont') or '').strip().upper()
                    r['_alq_ncont'] = float(r.get('aicms_aliquota_ncont') or 0)
                    r['_red_ncont'] = float(r.get('aicms_reducao_ncont') or 0)
                    
                    r['_cst_sn'] = str(r.get('aicms_situacao_simp_nac') or '').replace('.','').lstrip('0').zfill(3)
                    r['_cbenef_sn'] = str(r.get('aicms_cbenef_simp_nac') or '').strip().upper()
                    r['_alq_sn'] = float(r.get('aicms_aliquota_simp_nac') or 0)
                    r['_red_sn'] = float(r.get('aicms_reducao_simp_nac') or 0)
                    
                    r['_dccred'] = str(r.get('cbe_c_credpresumido') or '').strip().upper()
                    r['_dpcred'] = float(r.get('cbe_p_credpresumido') or 0)
                    
                    self.faixas_icms[est].append(r)
        except Exception as e:
            logging.error(f"Erro ao carregar faixas ICMS: {e}")
            self.faixas_icms = {}

    def _buscar_faixa_para_ncm(self, grupo):
        """Busca faixa no banco baseada em cbenef + gcred + UF + CST."""
        uf_dest = str(grupo.get('uf_dest') or '').strip().upper()
        faixas_estado = self.faixas_icms.get(uf_dest, [])
        if not faixas_estado: return None
        
        ncm = grupo.get('ncm', '')
        cbenef = str(grupo.get('c_benef') or '').strip().upper()
        c_cred = str(grupo.get('c_cred') or '').strip().upper()
        p_cred = float(grupo.get('p_cred') or 0)
        tipo_cli = grupo.get('tipo_cliente', 'CT')
        icms_cst = str(grupo.get('icms_cst') or '').replace('.','').lstrip('0').zfill(3)
        p_icms = float(grupo.get('p_icms') or 0)
        p_red = float(grupo.get('p_red_bc') or 0)
        
        faixas_encontradas = set()
        
        for r in faixas_estado:
            if tipo_cli == 'NC':
                dcst, dcbenef, daliquota = r['_cst_ncont'], r['_cbenef_ncont'], r['_alq_ncont']
            elif tipo_cli == 'SN':
                dcst, dcbenef, daliquota = r['_cst_sn'], r['_cbenef_sn'], r['_alq_ncont']
            else:
                dcst, dcbenef, daliquota = r['_cst_cont'], r['_cbenef_cont'], r['_alq_cont']
            
            dccred, dpcred = r['_dccred'], r['_dpcred']
            
            cbenef_match = cbenef and cbenef in [dcbenef] if dcbenef else False
            gcred_match = c_cred and c_cred == dccred and abs(p_cred - dpcred) < 0.01
            
            if (dcst == icms_cst and abs(daliquota - p_icms) < 0.01 and 
                (cbenef_match or gcred_match or (not cbenef and not c_cred))):
                faixas_encontradas.add(str(r.get('aicms_faixa')))
        
        if faixas_encontradas:
            return sorted(list(faixas_encontradas), key=lambda x: int(x) if x.isdigit() else x)[0]
        return None

    def _buscar_regra_rt(self, grupo):
        xclass = str(grupo.get('c_class_trib', '')).strip().lstrip('0')
        if not xclass: xclass = '0'
        xcst = str(grupo.get('ibscbs_cst', '')).strip().lstrip('0')
        if not xcst: xcst = '0'
        xibs = float(grupo.get('p_ibs_uf') or 0)
        xcbs = float(grupo.get('p_cbs') or 0)
        
        matches = set()
        for r in getattr(self, 'regras_rt', []):
            if r['class'] == xclass and r['cst'] == xcst and abs(r['ibs'] - xibs) < 0.01 and abs(r['cbs'] - xcbs) < 0.01:
                matches.add(r['id'])
                
        return ", ".join(sorted(list(matches))) if matches else "-"

    def _on_tree_click(self, event):
        """Permite marcar/desmarcar itens clicando na coluna SEL."""
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            if column == "#1":  # Coluna SEL
                item_id = self.tree.identify_row(event.y)
                if item_id:
                    valores = list(self.tree.item(item_id, 'values'))
                    valores[0] = '☐' if valores[0] == '☑' else '☑'
                    self.tree.item(item_id, values=valores)
                    self._atualizar_selecionados()
                    return "break"  # Impede seleção da linha

    def _on_tree_double_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            item_id = self.tree.identify_row(event.y)
            if item_id:
                grupo = self.dados_grid.get(item_id)
                valores = self.tree.item(item_id, 'values')
                sys_item = self.dados_sistema.get(grupo['ncm']) if grupo else None
                if grupo and valores:
                    DialogoDetalhesNcm(self, grupo, valores, sys_item)

    def _atualizar_selecionados(self):
        """Atualiza a lista de itens selecionados."""
        self.selecionados_lote = [item for item in self.tree.get_children() 
                                  if self.tree.item(item, 'values')[0] == '☑']
        if len(self.selecionados_lote) >= 1:
            self.btn_edicao_lote.config(state=tk.NORMAL)
        else:
            self.btn_edicao_lote.config(state=tk.DISABLED)

    def _on_selecionar_item(self, event):
        selecao = self.tree.selection()
        
        if len(self.selecionados_lote) > 1:
            self.btn_copiar_xml.config(state=tk.DISABLED)
            self.btn_salvar.config(state=tk.DISABLED)
            return
        
        if not selecao:
            self.btn_copiar_xml.config(state=tk.DISABLED)
            self.btn_salvar.config(state=tk.DISABLED)
            return
            
        self.btn_copiar_xml.config(state=tk.NORMAL)
        self.btn_salvar.config(state=tk.NORMAL)
        
        item_id = selecao[0]
        valores = self.tree.item(item_id, "values")
        
        self.var_ncm.set(valores[2])
        self.var_desc.set(valores[4])
        self.var_faixa.set(valores[28] if valores[28] != '-' else '')
        
        status = valores[3]
        if status == "NOVO":
            self.var_pis.set(valores[18] if valores[18] != '-' else 0.0)
            self.var_cofins.set(valores[21] if valores[21] != '-' else 0.0)
            self.var_cst_pis.set(self._formatar_cst(valores[17]) if valores[17] != '-' else '')
            self.var_cst_cofins.set(self._formatar_cst(valores[20]) if valores[20] != '-' else '')
            self.btn_salvar.config(text="➕ Cadastrar NCM")
        else:
            self.var_pis.set(valores[19] if valores[19] != '-' else 0.0)
            self.var_cofins.set(valores[22] if valores[22] != '-' else 0.0)
            self.var_cst_pis.set(self._formatar_cst(valores[17]))
            self.var_cst_cofins.set(self._formatar_cst(valores[20]))
            self.btn_salvar.config(text="💾 Atualizar NCM")

    def _selecionar_todos(self):
        for item in self.tree.get_children():
            valores = list(self.tree.item(item, 'values'))
            valores[0] = '☑'
            self.tree.item(item, values=valores)
        self._atualizar_selecionados()

    def _limpar_selecao(self):
        self._limpar_filtro()
        self._atualizar_selecionados()

    def _copiar_xml(self):
        valores = self.tree.item(self.tree.selection()[0], "values")
        self.var_faixa.set(valores[27] if valores[27] != '-' else '')
        self.var_pis.set(valores[18] if valores[18] != '-' else 0.0)
        self.var_cofins.set(valores[21] if valores[21] != '-' else 0.0)
        self.var_cst_pis.set(self._formatar_cst(valores[17]) if valores[17] != '-' else '')
        self.var_cst_cofins.set(self._formatar_cst(valores[20]) if valores[20] != '-' else '')
        messagebox.showinfo("Copiado", "Dados do XML copiados. Verifique a Faixa ICMS sugerida.")

    def _salvar_ncm(self):
        ncm_limpo = self.var_ncm.get()
        if not ncm_limpo: return
            
        empresa = self.config.get('IMPORTACAO', 'empresa', fallback='1')
        filial = self.config.get('IMPORTACAO', 'filial', fallback='1')
        
        ncm_fmt = f"{ncm_limpo[:4]}.{ncm_limpo[4:6]}.{ncm_limpo[6:]}" if len(ncm_limpo) == 8 else ncm_limpo
        faixa = self.var_faixa.get().strip()
        
        try:
            pis = float(self.var_pis.get())
            cofins = float(self.var_cofins.get())
        except ValueError:
            return messagebox.showwarning("Aviso", "Alíquotas inválidas.")
            
        cst_pis = self._formatar_cst(self.var_cst_pis.get())
        cst_cof = self._formatar_cst(self.var_cst_cofins.get())
        
        msg = f"NCM: {ncm_fmt}\n\nCampos:\n• CFIS_ICMS_VENDA = {faixa or '(vazio)'}\n• PIS = {pis}% | CST = {cst_pis}\n• COFINS = {cofins}% | CST = {cst_cof}"
        
        if not messagebox.askyesno("Confirmar", msg):
            return
        
        try:
            with FirebirdService(self.config_db) as fb:
                sql_check = "SELECT 1 FROM TABELA_class_fiscal WHERE CFIS_EMPRESA = ? AND CFIS_FILIAL = ? AND CFIS_CODIGO = ?"
                existe = fb.query(sql_check, [empresa, filial, ncm_fmt])
                cursor = fb.conn.cursor() if hasattr(fb, 'conn') else None
                
                desc = self.var_desc.get().strip()[:200]
                
                if existe:
                    campos = ["CFIS_PIS = ?", "CFIS_COFINS = ?", "CFIS_CST_PIS = ?", "CFIS_CST_COFINS = ?"]
                    params = [pis, cofins, cst_pis, cst_cof]
                    if desc:
                        campos.append("CFIS_DESCRICAO = ?")
                        params.append(desc)
                    if faixa:
                        campos.append("CFIS_ICMS_VENDA = ?")
                        params.append(faixa)
                    sql_up = f"UPDATE TABELA_class_fiscal SET {', '.join(campos)} WHERE CFIS_EMPRESA = ? AND CFIS_FILIAL = ? AND CFIS_CODIGO = ?"
                    params.extend([empresa, filial, ncm_fmt])
                    if cursor: cursor.execute(sql_up, params)
                    else: fb.execute(sql_up, params)
                else:
                    sql_in = """INSERT INTO TABELA_class_fiscal 
                        (CFIS_EMPRESA, CFIS_FILIAL, CFIS_CODIGO, CFIS_DESCRICAO, CFIS_ICMS_VENDA, 
                         CFIS_PIS, CFIS_COFINS, CFIS_CST_PIS, CFIS_CST_COFINS, CFIS_IPI, CFIS_CST_IPI) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, '53')"""
                    params = (empresa, filial, ncm_fmt, desc, faixa, pis, cofins, cst_pis, cst_cof)
                    if cursor: cursor.execute(sql_in, params)
                    else: fb.execute(sql_in, params)
                
                if cursor: fb.conn.commit()
                
            messagebox.showinfo("Sucesso", f"NCM {ncm_fmt} gravado!\n\nCFIS_ICMS_VENDA = {faixa}")
            self._iniciar_analise()
        except Exception as e:
            logging.error(f"Erro ao salvar NCM {ncm_fmt}: {e}")
            messagebox.showerror("Erro", f"Erro ao gravar:\n{e}")

    def _abrir_edicao_lote(self):
        if len(self.selecionados_lote) < 1:
            return messagebox.showwarning("Aviso", "Selecione pelo menos 1 item.")
        ModalEdicaoLoteNcm(self, self.selecionados_lote, self.config_db, self.config)

    def _iniciar_analise(self):
        if not self.pasta_xmls and not self.arquivos_selecionados:
            return messagebox.showwarning("Atenção", "Selecione XMLs.")
            
        self.btn_analisar.config(state=tk.DISABLED)
        self.btn_cancelar.config(state=tk.NORMAL)
        self.lbl_status.config(text="Agrupando NCMs e buscando faixas no banco...")
        for item in self.tree.get_children(): self.tree.delete(item)
        self.selecionados_lote = []
        self.btn_edicao_lote.config(state=tk.DISABLED)
        self.cancel_event.clear()
        self._carregar_faixas_icms()
        self.analysis_thread = threading.Thread(target=self._pipeline_bg, daemon=True)
        self.analysis_thread.start()

    def _cancelar_analise(self):
        self.cancel_event.set()
        self.btn_cancelar.config(state=tk.DISABLED)
        self.lbl_status.config(text="Cancelando análise... Aguarde.")

    def _finalizar_cancelamento(self):
        self.btn_analisar.config(state=tk.NORMAL)
        self.btn_cancelar.config(state=tk.DISABLED)
        self._atualizar_progresso(0, "Análise cancelada.")

    def _pipeline_bg(self):
        try:
            self.parent.after(0, lambda: self._atualizar_progresso(5, "Lendo arquivos XML..."))
            itens_xml = []
            if self.arquivos_selecionados:
                for arq in self.arquivos_selecionados:
                    if self.cancel_event.is_set():
                        self.parent.after(0, self._finalizar_cancelamento)
                        return
                    try: itens_xml.extend(parse_nfe(arq)['itens'])
                    except: pass
            else:
                itens_xml = parse_nfe_folder(self.pasta_xmls)

            if self.cancel_event.is_set():
                self.parent.after(0, self._finalizar_cancelamento)
                return

            self.parent.after(0, self._atualizar_progresso, 30, "Agrupando itens por NCM...")
            self.dados_agrupados = self._agrupar_ncm(itens_xml)
            
            if self.cancel_event.is_set():
                self.parent.after(0, self._finalizar_cancelamento)
                return

            self.parent.after(0, self._atualizar_progresso, 35, "Consultando tabelas no Firebird...")
            empresa = self.config.get('IMPORTACAO', 'empresa', fallback='1')
            filial = self.config.get('IMPORTACAO', 'filial', fallback='1')
            try:
                with FirebirdService(self.config_db) as fb:
                    sql = """SELECT CFIS_CODIGO, CFIS_DESCRICAO, CFIS_ICMS_VENDA, CFIS_PIS, CFIS_COFINS,
                             CFIS_CST_PIS, CFIS_CST_COFINS FROM TABELA_class_fiscal 
                             WHERE CFIS_EMPRESA = ? AND CFIS_FILIAL = ?"""
                    ncm_db = fb.query(sql, [empresa, filial])
                    self.dados_sistema = {str(row['cfis_codigo']).replace('.', '').strip(): row for row in ncm_db}
                    
                    try:
                        sql_gov = "SELECT NCM_CODIGO, NCM_DESCRICAO FROM TABELA_NCM"
                        gov_db = fb.query(sql_gov, [])
                        self.ncm_governo = {str(row['ncm_codigo']).replace('.', '').strip(): str(row.get('ncm_descricao', '')) for row in gov_db}
                    except Exception:
                        self.ncm_governo = {}
                        
                    try:
                        sql_rt = "SELECT TRT_ID, TRT_CLASS_TRIB_ID, TRT_CST, TRT_ALIQ_IBS_ESTADUAL, TRT_ALIQ_CBS FROM TABELA_RT_CONFIG_2025_2026"
                        raw_rt = fb.query(sql_rt, [])
                        self.regras_rt = []
                        for r in raw_rt:
                            self.regras_rt.append({
                                'id': str(r.get('trt_id')),
                                'class': str(r.get('trt_class_trib_id') or '').strip().lstrip('0') or '0',
                                'cst': str(r.get('trt_cst') or '').strip().lstrip('0') or '0',
                                'ibs': float(r.get('trt_aliq_ibs_estadual') or 0),
                                'cbs': float(r.get('trt_aliq_cbs') or 0)
                            })
                    except Exception:
                        self.regras_rt = []
            except Exception as db_err:
                self.dados_sistema = {}
                self.ncm_governo = {}

            if self.cancel_event.is_set():
                self.parent.after(0, self._finalizar_cancelamento)
                return

            total_grupos = len(self.dados_agrupados)
            valores_tree = []
            
            for idx, grupo in enumerate(self.dados_agrupados):
                if self.cancel_event.is_set():
                    self.parent.after(0, self._finalizar_cancelamento)
                    return

                ncm = grupo['ncm']
                sys_item = self.dados_sistema.get(ncm)
                
                faixa_xml = self._buscar_faixa_para_ncm(grupo)
                faixa_erp = sys_item.get('cfis_icms_venda', '-') if sys_item else '-'
                
                regra_rt = self._buscar_regra_rt(grupo)
                
                if not sys_item:
                    status, tag = "NOVO", "NOVO"
                elif str(faixa_xml or '') != str(faixa_erp or ''):
                    status, tag = "DIFERENTE", "DIFERENTE"
                else:
                    status, tag = "OK", "OK"
                
                desc_oficial = getattr(self, 'ncm_governo', {}).get(ncm)
                desc_sys = sys_item.get('cfis_descricao') if sys_item else None
                
                desc_exibicao = desc_oficial if desc_oficial else (desc_sys if desc_sys else grupo['descricao'])
                
                valores = (
                    '☐', grupo['ocorrencias'], ncm, status, desc_exibicao,
                    grupo['uf_dest'], grupo['cfop'], grupo['tipo_cliente'],
                    grupo['icms_cst'], f"{grupo['p_icms']}%", f"{grupo['p_red_bc']}%", f"{grupo['p_fcp']}%", f"{grupo['p_mvast']}%", f"{grupo['p_icmsst']}%",
                    grupo['c_benef'] or '-', grupo['c_cred'] or '-', f"{grupo['p_cred']}%" if grupo['p_cred'] else '-',
                    self._formatar_cst(grupo['pis_cst']), f"{grupo['pis_alq']}%", 
                    f"{sys_item.get('cfis_pis', '-') if sys_item else '-'}" if sys_item else '-',
                    self._formatar_cst(grupo['cofins_cst']), f"{grupo['cofins_alq']}%",
                    f"{sys_item.get('cfis_cofins', '-') if sys_item else '-'}" if sys_item else '-',
                    grupo['c_class_trib'] or '-', grupo['ibscbs_cst'] or '-', f"{grupo['p_ibs_uf']}%", f"{grupo['p_cbs']}%",
                    faixa_xml or '-', faixa_erp, regra_rt
                )
                valores_tree.append((valores, tag, grupo))
                
                if idx % max(1, total_grupos // 20) == 0:
                    self.parent.after(0, self._atualizar_progresso, 40 + (idx / max(1, total_grupos)) * 55, f"Cruzando NCMs: {idx}/{total_grupos}")

            self.parent.after(0, self._atualizar_progresso, 95, "Renderizando Tabela Visual...")
            self.parent.after(0, lambda v=valores_tree: self._renderizar_resultados(v))
        except Exception as e:
            self.parent.after(0, lambda: messagebox.showerror("Erro", str(e)))
            self.parent.after(0, lambda: self.btn_analisar.config(state=tk.NORMAL))

    def _agrupar_ncm(self, itens):
        mapa = {}
        for i in itens:
            ncm_xml = str(i.get('ncm', '')).replace('.', '').strip()
            if not ncm_xml: continue
            
            g = i.get('cred_presumidos', [])
            c_cred = str(g[0].get('c_cred', '')).strip() if g else ''
            p_cred = float(g[0].get('p_cred', 0.0)) if g else 0.0
            
            c_class_trib = str(i.get('c_class_trib') or '').strip().lstrip('0')
            ibscbs_cst = str(i.get('ibscbs_cst') or '').strip().lstrip('0')
            
            key = (ncm_xml, i.get('uf_dest', ''), i.get('cfop', ''), i.get('tipo_cliente', 'CT'),
                   i.get('icms_cst', ''), i.get('pis_cst', ''), i.get('cofins_cst', ''),
                   i.get('c_benef', ''), c_cred, c_class_trib, ibscbs_cst)
            
            if key not in mapa:
                mapa[key] = {
                    'ncm': ncm_xml,
                    'descricao': str(i.get('x_prod', ''))[:100],
                    'uf_dest': i.get('uf_dest', ''),
                    'cfop': i.get('cfop', ''),
                    'tipo_cliente': i.get('tipo_cliente', 'CT'),
                    'ocorrencias': 1,
                    'c_benef': i.get('c_benef', ''),
                    'c_cred': c_cred,
                    'p_cred': p_cred,
                    'icms_cst': i.get('icms_cst', ''),
                    'p_icms': i.get('p_icms', 0),
                    'p_red_bc': i.get('p_red_bc', 0),
                    'p_fcp': i.get('p_fcp', 0),
                    'p_icmsst': i.get('p_icmsst', 0),
                    'p_mvast': i.get('p_mvast', 0),
                    'pis_cst': i.get('pis_cst', ''),
                    'pis_alq': i.get('p_pis', 0),
                    'cofins_cst': i.get('cofins_cst', ''),
                    'cofins_alq': i.get('p_cofins', 0),
                    'c_class_trib': c_class_trib,
                    'ibscbs_cst': ibscbs_cst,
                    'p_ibs_uf': i.get('p_ibs_uf') or 0.0,
                    'p_cbs': i.get('p_cbs') or 0.0,
                }
            else:
                mapa[key]['ocorrencias'] += 1
        return list(mapa.values())

    def _renderizar_resultados(self, valores_tree):
        self.valores_tree = valores_tree
        self.filtered_tree = valores_tree[:]
        self.btn_analisar.config(state=tk.NORMAL)
        self.btn_cancelar.config(state=tk.DISABLED)
        self.btn_exportar.config(state=tk.NORMAL)
        self._atualizar_progresso(100, f"Renderizando tabela...")
        self._renderizar_tudo()

    def _renderizar_tudo(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.dados_grid.clear()

        for valores, tag, grupo in self.filtered_tree:
            item_id = self.tree.insert("", tk.END, values=valores, tags=(tag,))
            self.dados_grid[item_id] = grupo

        self.lbl_status.config(text=f"Pronto. {len(self.filtered_tree)} resultados exibidos.")

    def _filtrar_treeview(self):
        filtro = self.var_filtro.get().strip().lower()
        filtro_ncm = self.var_filtro_ncm.get().strip().lower()
        filtro_uf = self.var_filtro_uf.get().strip().lower()
        filtro_cfop = self.var_filtro_cfop.get().strip().lower()
        status = self.var_status_filtro.get()
        if not self.valores_tree:
            return

        filtrados = []
        for valores, tag, grupo in self.valores_tree:
            if status != "Todos" and valores[3] != status:
                continue

            if filtro:
                texto_procura = filtro
                valores_busca = (
                    valores[2], valores[4], valores[5], valores[6], valores[7], valores[3]
                )
                if not any(texto_procura in str(v).lower() for v in valores_busca):
                    continue

            if filtro_ncm and filtro_ncm not in str(valores[2]).lower():
                continue

            if filtro_uf and filtro_uf not in str(valores[5]).lower():
                continue

            if filtro_cfop and filtro_cfop not in str(valores[6]).lower():
                continue

            filtrados.append((valores, tag, grupo))

        self.filtered_tree = filtrados
        self._renderizar_tudo()

    def _limpar_filtro(self):
        self.var_filtro.set("")
        self.var_filtro_ncm.set("")
        self.var_filtro_uf.set("")
        self.var_filtro_cfop.set("")
        self.var_status_filtro.set("Todos")
        self.filtered_tree = self.valores_tree[:]
        self._renderizar_tudo()

    def _sincronizar_ncm_erp(self):
        caminho_json = filedialog.askopenfilename(title="JSON do Governo", filetypes=[("JSON", "*.json")])
        if not caminho_json: return

        try:
            with open(caminho_json, 'r', encoding='utf-8') as f:
                dados_json = json.load(f)
        except Exception as e:
            return messagebox.showerror("Erro", f"Ler JSON: {e}")

        lista_ncm = dados_json.get("Nomenclaturas", dados_json)
        ncms_para_inserir = []
        for item in lista_ncm:
            codigo = str(item.get("Codigo", "")).replace(".", "").strip()
            descricao = str(item.get("Descricao", "")).strip()
            descricao = descricao.encode('cp1252', errors='ignore').decode('cp1252')
            if len(codigo) == 8:
                ncms_para_inserir.append((codigo, descricao[:200]))

        if not ncms_para_inserir:
            return messagebox.showwarning("Aviso", "Nenhum NCM de 8 dígitos.")

        if not messagebox.askyesno("Confirmação", f"Inserir {len(ncms_para_inserir)} NCMs na TABELA_NCM?"):
            return

        def task():
            self.parent.after(0, lambda: self.btn_sincronizar.config(state=tk.DISABLED, text="Enviando..."))
            try:
                inseridos = 0
                with FirebirdService(self.config_db) as fb:
                    cursor = fb.conn.cursor() if hasattr(fb, 'conn') else None
                    for cod, desc in ncms_para_inserir:
                        sql = """MERGE INTO TABELA_NCM T USING 
                                 (SELECT CAST(? AS VARCHAR(10)) AS NCM_CODIGO, CAST(? AS VARCHAR(250)) FROM RDB$DATABASE) S 
                                 ON T.NCM_CODIGO = S.NCM_CODIGO WHEN NOT MATCHED THEN INSERT VALUES (S.NCM_CODIGO, S.NCM_DESCRICAO)"""
                        try:
                            if cursor: cursor.execute(sql, (cod, desc))
                            else: fb.execute(sql, (cod, desc))
                            inseridos += 1
                        except: pass
                    if cursor: fb.conn.commit()
                self.parent.after(0, lambda: messagebox.showinfo("Sucesso", f"{inseridos} NCMs inseridos!"))
            except Exception as e:
                self.parent.after(0, lambda: messagebox.showerror("Erro", str(e)))
            finally:
                self.parent.after(0, lambda: self.btn_sincronizar.config(state=tk.NORMAL, text="🔄 Sincronizar NCMs p/ ERP"))

        threading.Thread(target=task, daemon=True).start()

    def _exportar_csv(self):
        caminho = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="NCM_Analise.csv")
        if not caminho: return
        try:
            with open(caminho, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f, delimiter=';')
                
                colunas = ("QTD", "NCM", "STATUS", "DESCRIÇÃO", "UF", "CFOP", "TIPO", 
                           "CST ICMS", "ICMS%", "RED.BC%", "FCP%", "MVA ST%", "ICMS ST%",
                           "CBENEF", "C.CRED", "P.CRED",
                           "CST PIS", "PIS%", "PIS% ERP",
                           "CST COF", "COF%", "COF% ERP",
                           "C. CLASSE RT", "CST RT", "IBS%", "CBS%",
                           "FAIXA ICMS", "FAIXA ERP", "REGRA RT ERP")
                           
                writer.writerow(colunas)
                for child in self.tree.get_children():
                    v = self.tree.item(child, "values")
                    writer.writerow(v[1:]) # Pula a coluna SEL
            messagebox.showinfo("Sucesso", "CSV exportado!")
        except Exception as e:
            messagebox.showerror("Erro", str(e))


class DialogoDetalhesNcm(tk.Toplevel):
    """Modal para comparação detalhada lado-a-lado de tributação (XML vs ERP)."""
    def __init__(self, parent_tela, grupo, valores, sys_item):
        super().__init__(parent_tela)
        self.parent_tela = parent_tela
        self.grupo = grupo
        self.valores = valores
        self.sys_item = sys_item
        
        ncm = grupo['ncm']
        ncm_fmt = f"{ncm[:4]}.{ncm[4:6]}.{ncm[6:]}" if len(ncm) >= 8 else ncm
        
        self.title(f"Auditoria Detalhada Lado-a-Lado - NCM: {ncm_fmt}")
        self.geometry("900x550")
        self.transient(parent_tela.winfo_toplevel())
        self.grab_set()
        
        self._criar_widgets()

    def _criar_widgets(self):
        frame_top = ttk.Frame(self, padding=15)
        frame_top.pack(fill=tk.X)
        
        ncm = self.grupo['ncm']
        ncm_fmt = f"{ncm[:4]}.{ncm[4:6]}.{ncm[6:]}" if len(ncm) >= 8 else ncm
        desc_oficial = getattr(self.parent_tela, 'ncm_governo', {}).get(ncm, "Descrição oficial não localizada.")
        
        ttk.Label(frame_top, text=f"NCM: {ncm_fmt}", font=("Segoe UI", 16, "bold"), foreground="#003399").pack(anchor=tk.W)
        ttk.Label(frame_top, text=desc_oficial, font=("Segoe UI", 10), wraplength=800).pack(anchor=tk.W, pady=(5,0))
        
        status_geral = self.valores[3]
        bg_color = "#EAFAF1" if status_geral == "NOVO" else ("#FEF9E7" if status_geral == "DIFERENTE" else "#E8F8F5")
        fg_color = "#1E8449" if status_geral == "NOVO" else ("#D35400" if status_geral == "DIFERENTE" else "#117A65")
        
        lbl_status = tk.Label(frame_top, text=f" STATUS GERAL: {status_geral} ", font=("Segoe UI", 10, "bold"), bg=bg_color, fg=fg_color)
        lbl_status.place(relx=1.0, rely=0.0, anchor=tk.NE)
        
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        
        self.tab_icms = ttk.Frame(self.notebook, padding=15)
        self.tab_piscof = ttk.Frame(self.notebook, padding=15)
        self.tab_rt = ttk.Frame(self.notebook, padding=15)
        
        self.notebook.add(self.tab_icms, text="   ICMS (Operação)   ")
        self.notebook.add(self.tab_piscof, text="   PIS / COFINS   ")
        self.notebook.add(self.tab_rt, text="   Reforma Tributária   ")
        
        self._popular_icms()
        self._popular_piscof()
        self._popular_rt()
        
        frame_bot = ttk.Frame(self, padding=15)
        frame_bot.pack(fill=tk.X, side=tk.BOTTOM)
        
        ttk.Button(frame_bot, text="Fechar", command=self.destroy).pack(side=tk.RIGHT, padx=5)
        btn_editar = ttk.Button(frame_bot, text="✏️ Editar este NCM", command=self._enviar_para_edicao)
        btn_editar.pack(side=tk.LEFT, padx=5)

    def _criar_cabecalho(self, parent):
        ttk.Label(parent, text="ATRIBUTO", font=("Segoe UI", 10, "bold"), width=30).grid(row=0, column=0, sticky=tk.W, pady=10)
        ttk.Label(parent, text="XML (Nota Fiscal)", font=("Segoe UI", 10, "bold"), foreground="#003399", width=25).grid(row=0, column=1, sticky=tk.W, pady=10)
        ttk.Label(parent, text="ERP (Sistema)", font=("Segoe UI", 10, "bold"), foreground="#16A085", width=25).grid(row=0, column=2, sticky=tk.W, pady=10)
        ttk.Label(parent, text="STATUS", font=("Segoe UI", 10, "bold"), width=15).grid(row=0, column=3, sticky=tk.W, pady=10)
        ttk.Separator(parent, orient="horizontal").grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0,10))

    def _add_linha(self, parent, row, label, val_xml, val_erp, compare=True):
        ttk.Label(parent, text=label, font=("Segoe UI", 10)).grid(row=row, column=0, sticky=tk.W, pady=6)
        ttk.Label(parent, text=str(val_xml) if val_xml else "-", font=("Segoe UI", 10, "bold")).grid(row=row, column=1, sticky=tk.W, pady=6)
        ttk.Label(parent, text=str(val_erp) if val_erp else "-", font=("Segoe UI", 10, "bold")).grid(row=row, column=2, sticky=tk.W, pady=6)
        
        if compare:
            str_xml = str(val_xml).strip().replace(".0", "").replace("%", "")
            str_erp = str(val_erp).strip().replace(".0", "").replace("%", "")
            
            if not str_xml: str_xml = "-"
            if not str_erp or str_erp == "None": str_erp = "-"
            
            if str_xml == str_erp:
                status, color = "✅ IGUAL", "#27AE60"
            else:
                status, color = "❌ DIVERGE", "#E74C3C"
                
            ttk.Label(parent, text=status, foreground=color, font=("Segoe UI", 10, "bold")).grid(row=row, column=3, sticky=tk.W, pady=6)
        else:
            ttk.Label(parent, text="-", foreground="#7F8C8D").grid(row=row, column=3, sticky=tk.W, pady=6)

    def _popular_icms(self):
        self._criar_cabecalho(self.tab_icms)
        faixa_xml = self.valores[27]
        faixa_erp = self.valores[28]
        
        self._add_linha(self.tab_icms, 2, "Tipo Cliente / CFOP", f"{self.grupo['tipo_cliente']} / {self.grupo['cfop']}", "N/A", False)
        self._add_linha(self.tab_icms, 3, "UF Destino", self.grupo['uf_dest'], "N/A", False)
        self._add_linha(self.tab_icms, 4, "CST ICMS", self.grupo['icms_cst'], "N/A", False)
        self._add_linha(self.tab_icms, 5, "Alíquota ICMS", f"{self.grupo['p_icms']}%", "N/A", False)
        self._add_linha(self.tab_icms, 6, "Redução BC / FCP", f"{self.grupo['p_red_bc']}% / {self.grupo['p_fcp']}%", "N/A", False)
        self._add_linha(self.tab_icms, 7, "Código Benefício (cBenef)", self.grupo['c_benef'], "N/A", False)
        ttk.Separator(self.tab_icms, orient="horizontal").grid(row=8, column=0, columnspan=4, sticky="ew", pady=10)
        self._add_linha(self.tab_icms, 9, "➜ FAIXA ICMS (Alíquota)", faixa_xml, faixa_erp, True)

    def _popular_piscof(self):
        self._criar_cabecalho(self.tab_piscof)
        sys = self.sys_item or {}
        
        pis_cst_xml = self.parent_tela._formatar_cst(self.grupo.get('pis_cst', ''))
        pis_cst_erp = self.parent_tela._formatar_cst(sys.get('cfis_cst_pis', '-'))
        pis_alq_xml = self.valores[18]
        pis_alq_erp = self.valores[19]
        cof_cst_xml = self.parent_tela._formatar_cst(self.grupo.get('cofins_cst', ''))
        cof_cst_erp = self.parent_tela._formatar_cst(sys.get('cfis_cst_cofins', '-'))
        cof_alq_xml = self.valores[21]
        cof_alq_erp = self.valores[22]
        
        self._add_linha(self.tab_piscof, 2, "CST PIS", pis_cst_xml, pis_cst_erp, True)
        self._add_linha(self.tab_piscof, 3, "Alíquota PIS", pis_alq_xml, pis_alq_erp, True)
        ttk.Separator(self.tab_piscof, orient="horizontal").grid(row=4, column=0, columnspan=4, sticky="ew", pady=10)
        self._add_linha(self.tab_piscof, 5, "CST COFINS", cof_cst_xml, cof_cst_erp, True)
        self._add_linha(self.tab_piscof, 6, "Alíquota COFINS", cof_alq_xml, cof_alq_erp, True)

    def _popular_rt(self):
        self._criar_cabecalho(self.tab_rt)
        regra_erp = self.valores[29]
        
        self._add_linha(self.tab_rt, 2, "Cód. Classe Tributária", self.grupo['c_class_trib'], "N/A", False)
        self._add_linha(self.tab_rt, 3, "CST IBS/CBS", self.grupo['ibscbs_cst'], "N/A", False)
        self._add_linha(self.tab_rt, 4, "Alíquota IBS", f"{self.grupo['p_ibs_uf']}%", "N/A", False)
        self._add_linha(self.tab_rt, 5, "Alíquota CBS", f"{self.grupo['p_cbs']}%", "N/A", False)
        ttk.Separator(self.tab_rt, orient="horizontal").grid(row=6, column=0, columnspan=4, sticky="ew", pady=10)
        self._add_linha(self.tab_rt, 7, "➜ Regra RT Encontrada (ERP)", "Sugerido pelo XML", regra_erp, False)

    def _enviar_para_edicao(self):
        # Localiza o registro na tabela principal, seleciona-o e preenche o painel de edição
        for item in self.parent_tela.tree.get_children():
            if self.parent_tela.tree.item(item, 'values')[2] == self.grupo['ncm']:
                self.parent_tela.tree.selection_set(item)
                self.parent_tela.tree.see(item)
                self.parent_tela._on_selecionar_item(None)
                break
        self.destroy()


class ModalEdicaoLoteNcm(tk.Toplevel):
    def __init__(self, parent, itens, config_db, config):
        super().__init__(parent)
        self.parent = parent
        self.itens = itens
        self.config_db = config_db
        self.config = config
        self.itens_data = []
        
        self.title("Edição em Lote de NCMs")
        self.geometry("1200x600")
        self.transient(parent)
        self.grab_set()
        
        self._criar_widgets()
        self._carregar()

    def _criar_widgets(self):
        ttk.Label(self, text=f"Edição em Lote: {len(self.itens)} NCM(s)", 
                  font=("Segoe UI", 12, "bold")).pack(anchor=tk.W, padx=10, pady=5)
        
        frame_grid = ttk.Frame(self)
        frame_grid.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        colunas = ("NCM", "DESCRIÇÃO", "UF", "TIPO", "CBENEF", "COD.CRED", "PCT.CRED",
                   "ICMS%", "PIS%", "PIS% ERP", "COF%", "COF% ERP",
                   "FAIXA ERP", "FAIXA XML", "SALVAR FAIXA", "SALVAR PIS", "SALVAR COF")
        
        self.tree = ttk.Treeview(frame_grid, columns=colunas, show="headings", height=15)
        
        larguras = [90, 200, 50, 50, 80, 70, 60, 60, 60, 70, 60, 70, 80, 80, 90, 80, 80]
        for col, larg in zip(colunas, larguras):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=larg, anchor=tk.CENTER)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y = ttk.Scrollbar(frame_grid, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scroll_y.set)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Botões
        frame_btn = ttk.Frame(self)
        frame_btn.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(frame_btn, text="📋 Copiar Faixa ERP→SALVAR", 
                   command=self._copiar_faixa_erp).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_btn, text="📋 Copiar Faixa XML→SALVAR", 
                   command=self._copiar_faixa_xml).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_btn, text="📋 Copiar PIS ERP→SALVAR", 
                   command=self._copiar_pis_erp).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_btn, text="📋 Copiar PIS XML→SALVAR", 
                   command=self._copiar_pis_xml).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_btn, text="📋 Copiar COF ERP→SALVAR", 
                   command=self._copiar_cof_erp).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_btn, text="📋 Copiar COF XML→SALVAR", 
                   command=self._copiar_cof_xml).pack(side=tk.LEFT, padx=2)
        
        frame_rodape = ttk.Frame(self)
        frame_rodape.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(frame_rodape, text="❌ Cancelar", command=self.destroy).pack(side=tk.LEFT)
        ttk.Button(frame_rodape, text="💾 SALVAR NO BANCO", 
                   style="Accent.TButton", command=self._salvar).pack(side=tk.RIGHT)

    def _copiar_faixa_erp(self):
        for item in self.tree.get_children():
            valores = list(self.tree.item(item, 'values'))
            if valores[12] and valores[12] != '-':
                valores[14] = valores[12]
                self.tree.item(item, values=valores)

    def _copiar_faixa_xml(self):
        for item in self.tree.get_children():
            valores = list(self.tree.item(item, 'values'))
            if valores[13] and valores[13] != '-':
                valores[14] = valores[13]
                self.tree.item(item, values=valores)

    def _copiar_pis_erp(self):
        for item in self.tree.get_children():
            valores = list(self.tree.item(item, 'values'))
            if valores[9] and valores[9] != '-':
                valores[15] = valores[9]
                self.tree.item(item, values=valores)

    def _copiar_cof_erp(self):
        for item in self.tree.get_children():
            valores = list(self.tree.item(item, 'values'))
            if valores[11] and valores[11] != '-':
                valores[16] = valores[11]
                self.tree.item(item, values=valores)

    def _copiar_pis_xml(self):
        for item in self.tree.get_children():
            valores = list(self.tree.item(item, 'values'))
            if valores[18] and valores[18] != '-':
                valores[15] = valores[18]
                self.tree.item(item, values=valores)

    def _copiar_cof_xml(self):
        for item in self.tree.get_children():
            valores = list(self.tree.item(item, 'values'))
            if valores[21] and valores[21] != '-':
                valores[16] = valores[21]
                self.tree.item(item, values=valores)

    def _carregar(self):
        for item_id in self.itens:
            v = self.parent.tree.item(item_id, 'values')
            
            ncm = str(v[2]) if len(v) > 2 else ''
            desc = str(v[4])[:60] if len(v) > 4 else ''
            uf = str(v[5]) if len(v) > 5 else ''
            tipo = str(v[7]) if len(v) > 7 else ''
            cbenef = str(v[14]) if len(v) > 14 and v[14] != '-' else '-'
            cod_cred = str(v[15]) if len(v) > 15 and v[15] != '-' else '-'
            pct_cred = str(v[16]) if len(v) > 16 and v[16] != '-' else '-'
            
            icms = str(v[9]) if len(v) > 9 else '-'
            pis_xml = str(v[18]) if len(v) > 18 else '-'
            pis_erp = str(v[19]) if len(v) > 19 and v[19] != '-' else '-'
            cof_xml = str(v[21]) if len(v) > 21 else '-'
            cof_erp = str(v[22]) if len(v) > 22 and v[22] != '-' else '-'
            
            faixa_erp = str(v[28]) if len(v) > 28 and v[28] != '-' else '-'
            faixa_xml = str(v[27]) if len(v) > 27 and v[27] != '-' else '-'
            
            self.tree.insert("", tk.END, values=(
                ncm, desc, uf, tipo, cbenef, cod_cred, pct_cred,
                icms, pis_xml, pis_erp, cof_xml, cof_erp,
                faixa_erp, faixa_xml, '', '', ''
            ))

    def _salvar(self):
        empresa = self.config.get('IMPORTACAO', 'empresa', fallback='1')
        filial = self.config.get('IMPORTACAO', 'filial', fallback='1')
        
        registros = []
        for item_id in self.tree.get_children():
            valores = self.tree.item(item_id, 'values')
            ncm = str(valores[0])
            ncm_fmt = f"{ncm[:4]}.{ncm[4:6]}.{ncm[6:]}" if len(ncm) >= 8 else ncm
            desc = str(valores[1])[:200]
            
            faixa = str(valores[14]).strip()
            pis = str(valores[15]).strip()
            cof = str(valores[16]).strip()
            
            registros.append({
                'ncm': ncm,
                'ncm_fmt': ncm_fmt,
                'desc': desc,
                'faixa': faixa,
                'pis': pis,
                'cof': cof
            })
        
        if not registros:
            return messagebox.showwarning("Aviso", "Nenhum NCM para salvar.", parent=self)
        
        msg = f"Salvar {len(registros)} NCM(s)?\n\n"
        for r in registros[:10]:
            parts = [f"{r['ncm']}"]
            if r['faixa']: parts.append(f"Faixa={r['faixa']}")
            if r['pis']: parts.append(f"PIS={r['pis']}")
            if r['cof']: parts.append(f"COF={r['cof']}")
            msg += "• " + " | ".join(parts) + "\n"
        if len(registros) > 10:
            msg += f"... e mais {len(registros) - 10}\n"
        msg += "\nContinuar?"
        
        if not messagebox.askyesno("Confirmar", msg, parent=self):
            return
        
        try:
            with FirebirdService(self.config_db) as fb:
                cursor = fb.conn.cursor() if hasattr(fb, 'conn') else None
                ins = upd = 0
                
                for r in registros:
                    existe = fb.query("SELECT 1 FROM TABELA_class_fiscal WHERE CFIS_EMPRESA = ? AND CFIS_FILIAL = ? AND CFIS_CODIGO = ?",
                                      [empresa, filial, r['ncm_fmt']])
                    
                    if existe:
                        campos = ["CFIS_DESCRICAO = ?"]
                        params = [r['desc']]
                        if r['faixa']: campos.append("CFIS_ICMS_VENDA = ?"); params.append(r['faixa'])
                        if r['pis']: campos.append("CFIS_PIS = ?"); params.append(float(r['pis']))
                        if r['cof']: campos.append("CFIS_COFINS = ?"); params.append(float(r['cof']))
                        
                        sql = f"UPDATE TABELA_class_fiscal SET {', '.join(campos)} WHERE CFIS_EMPRESA = ? AND CFIS_FILIAL = ? AND CFIS_CODIGO = ?"
                        params.extend([empresa, filial, r['ncm_fmt']])
                        if cursor: cursor.execute(sql, params)
                        else: fb.execute(sql, params)
                        upd += 1
                    else:
                        sql = """INSERT INTO TABELA_class_fiscal (CFIS_EMPRESA, CFIS_FILIAL, CFIS_CODIGO, CFIS_DESCRICAO, CFIS_ICMS_VENDA, CFIS_PIS, CFIS_COFINS, CFIS_IPI, CFIS_CST_IPI) 
                                 VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, '53')"""
                        params = (empresa, filial, r['ncm_fmt'], r['desc'], r['faixa'] or None,
                                  float(r['pis']) if r['pis'] else 0.0, float(r['cof']) if r['cof'] else 0.0)
                        if cursor: cursor.execute(sql, params)
                        else: fb.execute(sql, params)
                        ins += 1
                
                if cursor: fb.conn.commit()
            
            messagebox.showinfo("Sucesso", f"Salvo!\n\n• {upd} atualizado(s)\n• {ins} inserido(s)", parent=self)
            self.destroy()
            self.parent._iniciar_analise()
        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("Erro", f"Erro:\n{e}", parent=self)

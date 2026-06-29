import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import configparser
import threading
import json
import os
import sys
import csv

from utils.firebird_service import FirebirdService
from utils.xml_reader import parse_nfe_folder, parse_nfe


_ABREV = {
    'VENDA': 'VDA', 'COMPRA': 'CPRA',
    'DEVOLUCAO': 'DEV', 'DEVOLUÇÃO': 'DEV',
    'MERCADORIA': 'MERC',
    'ESTABELECIMENTO': 'ESTAB',
    'PRODUCAO': 'PROD', 'PRODUÇÃO': 'PROD',
    'OPERACAO': 'OPER', 'OPERAÇÃO': 'OPER',
    'ADQUIRIDA': 'ADQ', 'ADQUIRIDO': 'ADQ',
    'RECEBIDA': 'REC', 'RECEBIDO': 'REC',
    'TERCEIROS': 'TERC',
    'ENTRADA': 'ENT',
    'SAIDA': 'SAI', 'SAÍDA': 'SAI',
    'INTERESTADUAL': 'INTEREST',
    'EXTERIOR': 'EXT',
    'ATIVO': 'ATV',
    'IMOBILIZADO': 'IMOB',
    'CONSUMO': 'CONS',
    'INSUMO': 'INS',
    'SERVICO': 'SERV', 'SERVIÇO': 'SERV',
    'TRANSPORTE': 'TRANSP',
    'ENERGIA': 'ENERG',
    'ELETRICA': 'ELETR', 'ELÉTRICA': 'ELETR',
    'COMUNICACAO': 'COMUN', 'COMUNICAÇÃO': 'COMUN',
    'TRIBUTARIA': 'TRIB', 'TRIBUTÁRIA': 'TRIB',
    'SUBSTITUICAO': 'SUBST', 'SUBSTITUIÇÃO': 'SUBST',
    'COMERCIALIZACAO': 'COMERC', 'COMERCIALIZAÇÃO': 'COMERC',
    'INDUSTRIALIZACAO': 'INDUST', 'INDUSTRIALIZAÇÃO': 'INDUST',
    'CONTRIBUINTE': 'CONTRIB',
    'CREDITO': 'CRED', 'CRÉDITO': 'CRED',
    'ICMS': 'ICMS',
    'IPI': 'IPI',
}


def resumir_descricao(texto, max_chars=30):
    if not texto:
        return ''
    original = texto.upper().strip()
    stopwords = {'DE', 'DA', 'DO', 'EM', 'COM', 'PARA', 'POR', 'A', 'O', 'E', 'UM', 'UMA', 'OS', 'AS', 'NO', 'NA', 'AO'}
    palavras = [p for p in original.split() if p not in stopwords]
    texto = ' '.join(palavras) if palavras else original
    palavras = texto.split()
    texto = ' '.join(_ABREV.get(p, p) for p in palavras)
    if len(texto) > max_chars:
        texto = texto[:max_chars]
        ult_esp = texto.rfind(' ')
        if ult_esp > len(texto) // 2:
            texto = texto[:ult_esp]
    return texto.capitalize()


class TelaCfop(ttk.Frame):
    def __init__(self, parent, callback_voltar=None):
        super().__init__(parent, padding="10")
        self.parent = parent
        self.callback_voltar = callback_voltar
        self.pack(fill=tk.BOTH, expand=True)

        self.cfop_governo = {}
        self.cfops_erp = []
        self.cfops_erp_set = set()
        self.erp_bases = set()
        self.xml_cfop_data = {}
        self.editando_codigo = None
        self.all_tree_iids = []


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
        self.empresa = self.config.get('IMPORTACAO', 'empresa', fallback='1')
        self.filial = self.config.get('IMPORTACAO', 'filial', fallback='1')
        self.exercicio = self.config.get('IMPORTACAO', 'exercicio', fallback='2026')

        self._carregar_cfop_governo()
        self._criar_widgets()
        self._carregar_cfops_erp()

    def resource_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def _carregar_cfop_governo(self):
        caminho = self.resource_path("cfop_governo.json")
        if os.path.exists(caminho):
            try:
                with open(caminho, 'r', encoding='utf-8') as f:
                    for row in json.load(f):
                        cod = str(row.get('cfop') or row.get('codigo', ''))
                        if cod:
                            self.cfop_governo[cod] = row
            except Exception as e:
                print(f"Erro ao carregar cfop_governo.json: {e}")

    def _criar_widgets(self):
        lbl_title = tk.Label(self, text="IMPORTAÇÃO DE CFOP VIA XML (TABELA_NAT_OPERACAO_SAIDA)",
                             font=("Segoe UI", 14, "bold"), fg="#D35400")
        lbl_title.pack(anchor=tk.W, pady=(0, 10))

        frame_acoes = ttk.Frame(self)
        frame_acoes.pack(fill=tk.X, pady=(0, 5))

        ttk.Button(frame_acoes, text="📂 Carregar XMLs", command=self._analisar_xmls).pack(side=tk.LEFT, padx=2)
        self.btn_importar = ttk.Button(frame_acoes, text="💾 Importar Selecionados", command=self._importar_selecionados, state=tk.DISABLED)
        self.btn_importar.pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_acoes, text="➕ Novo", command=self._novo_cfop).pack(side=tk.LEFT, padx=2)
        self.btn_salvar = ttk.Button(frame_acoes, text="💾 Salvar", command=self._salvar_cfop)
        self.btn_salvar.pack(side=tk.LEFT, padx=2)
        self.btn_excluir = ttk.Button(frame_acoes, text="🗑 Desativar", command=self._desativar_cfop)
        self.btn_excluir.pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_acoes, text="📋 Exportar CSV", command=self._exportar_csv).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_acoes, text="⬅ VOLTAR", command=self._fechar_tela).pack(side=tk.RIGHT, padx=5)

        frame_filtro = ttk.Frame(self)
        frame_filtro.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(frame_filtro, text="Buscar:").pack(side=tk.LEFT, padx=(0, 5))
        self.var_filtro = tk.StringVar(self)
        self.ent_filtro = ttk.Entry(frame_filtro, textvariable=self.var_filtro, width=30)
        self.ent_filtro.pack(side=tk.LEFT, padx=(0, 5))
        self.ent_filtro.bind('<KeyRelease>', self._filtrar_tree)

        self.lbl_info = ttk.Label(self, text="Carregando CFOPs do ERP...", font=("Segoe UI", 9))
        self.lbl_info.pack(anchor=tk.W)

        frame_principal = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        frame_principal.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

        frame_tree = ttk.Frame(frame_principal)
        frame_form = ttk.Frame(frame_principal)

        frame_principal.add(frame_tree, weight=2)
        frame_principal.add(frame_form, weight=1)

        colunas = ("CÓDIGO", "DESCRIÇÃO", "QTD XML", "STATUS ERP", "ICMS", "PIS", "COFINS", "ATIVO")
        self._sort_directions = {col: False for col in colunas}
        self.tree = ttk.Treeview(frame_tree, columns=colunas, show="headings", height=15)
        larguras = [80, 250, 70, 100, 50, 50, 50, 60]
        for col, larg in zip(colunas, larguras):
            self.tree.heading(col, text=col + " ↕", command=lambda c=col: self._sort_treeview(c))
            self.tree.column(col, width=larg, anchor=tk.W if col in ("DESCRIÇÃO", "CÓDIGO") else tk.CENTER)
        scroll_y = ttk.Scrollbar(frame_tree, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.tag_configure('INATIVO', foreground='#999999')
        self.tree.tag_configure('NOVO', foreground='#C0392B', font=("Segoe UI", 9, "bold"))

        self._criar_form_edicao(frame_form)

    def _criar_form_edicao(self, parent):
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        f = scroll_frame

        g1 = ttk.LabelFrame(f, text="Identificação", padding="8")
        g1.pack(fill=tk.X, padx=5, pady=3)

        ttk.Label(g1, text="CFOP (4 dígitos):").grid(row=0, column=0, sticky=tk.W, padx=3, pady=2)
        self.var_cfop_base = tk.StringVar(self)
        self.cmb_cfop_base = ttk.Combobox(g1, textvariable=self.var_cfop_base, width=16)
        cfop_list = sorted(self.cfop_governo.keys(), key=lambda x: int(x) if x.isdigit() else x)
        self.cmb_cfop_base['values'] = cfop_list
        self.cmb_cfop_base.grid(row=0, column=1, sticky=tk.W, padx=3, pady=2)
        self.cmb_cfop_base.bind('<<ComboboxSelected>>', self._on_cfop_base_select)
        self.cmb_cfop_base.bind('<KeyRelease>', lambda e: self._atualizar_codigo_completo())

        ttk.Label(g1, text="Sequencial (2 dígitos):").grid(row=0, column=2, sticky=tk.W, padx=3, pady=2)
        self.var_cfop_seq = tk.StringVar(self)
        self.ent_cfop_seq = ttk.Entry(g1, textvariable=self.var_cfop_seq, width=6)
        self.ent_cfop_seq.grid(row=0, column=3, sticky=tk.W, padx=3, pady=2)
        self.ent_cfop_seq.bind('<KeyRelease>', lambda e: self._atualizar_codigo_completo())

        ttk.Label(g1, text="Código completo:").grid(row=0, column=4, sticky=tk.W, padx=3, pady=2)
        self.lbl_codigo_completo = ttk.Label(g1, text="______", font=("Consolas", 10, "bold"))
        self.lbl_codigo_completo.grid(row=0, column=5, sticky=tk.W, padx=3, pady=2)

        ttk.Label(g1, text="Descrição Abreviada:").grid(row=1, column=0, sticky=tk.W, padx=3, pady=2)
        self.var_desc_abr = tk.StringVar(self)
        ttk.Entry(g1, textvariable=self.var_desc_abr, width=50).grid(row=1, column=1, columnspan=5, sticky=tk.W, padx=3, pady=2)

        ttk.Label(g1, text="Descrição Completa:").grid(row=2, column=0, sticky=tk.W, padx=3, pady=2)
        self.var_desc_comp = tk.StringVar(self)
        ttk.Entry(g1, textvariable=self.var_desc_comp, width=50).grid(row=2, column=1, columnspan=5, sticky=tk.W, padx=3, pady=2)

        ttk.Label(g1, text="Observação:").grid(row=3, column=0, sticky=tk.W, padx=3, pady=2)
        self.var_obs = tk.StringVar(self)
        ttk.Entry(g1, textvariable=self.var_obs, width=50).grid(row=3, column=1, columnspan=5, sticky=tk.W, padx=3, pady=2)

        g2 = ttk.LabelFrame(f, text="Tributação no CFOP", padding="8")
        g2.pack(fill=tk.X, padx=5, pady=3)

        ops_sn = ["", "S", "N"]
        ops_sn_obrig = ["S", "N"]

        row2 = 0
        ttk.Label(g2, text="ICMS:").grid(row=row2, column=0, sticky=tk.W, padx=3, pady=2)
        self.var_icms = tk.StringVar(self)
        ttk.Combobox(g2, textvariable=self.var_icms, values=ops_sn, width=6, state='readonly').grid(row=row2, column=1, sticky=tk.W, padx=3, pady=2)

        ttk.Label(g2, text="PIS:").grid(row=row2, column=2, sticky=tk.W, padx=3, pady=2)
        self.var_pis_flag = tk.StringVar(self)
        ttk.Combobox(g2, textvariable=self.var_pis_flag, values=ops_sn, width=6, state='readonly').grid(row=row2, column=3, sticky=tk.W, padx=3, pady=2)

        ttk.Label(g2, text="COFINS:").grid(row=row2, column=4, sticky=tk.W, padx=3, pady=2)
        self.var_cofins_flag = tk.StringVar(self)
        ttk.Combobox(g2, textvariable=self.var_cofins_flag, values=ops_sn, width=6, state='readonly').grid(row=row2, column=5, sticky=tk.W, padx=3, pady=2)

        row2 = 1
        ttk.Label(g2, text="ST (ICMS ST):").grid(row=row2, column=0, sticky=tk.W, padx=3, pady=2)
        self.var_st = tk.StringVar(self)
        ttk.Combobox(g2, textvariable=self.var_st, values=ops_sn, width=6, state='readonly').grid(row=row2, column=1, sticky=tk.W, padx=3, pady=2)

        ttk.Label(g2, text="IPI:").grid(row=row2, column=2, sticky=tk.W, padx=3, pady=2)
        self.var_ipi_flag = tk.StringVar(self)
        ttk.Combobox(g2, textvariable=self.var_ipi_flag, values=ops_sn, width=6, state='readonly').grid(row=row2, column=3, sticky=tk.W, padx=3, pady=2)

        ttk.Label(g2, text="Desativado:").grid(row=row2, column=4, sticky=tk.W, padx=3, pady=2)
        self.var_desativado = tk.StringVar(self, value="N")
        ttk.Combobox(g2, textvariable=self.var_desativado, values=ops_sn_obrig, width=6, state='readonly').grid(row=row2, column=5, sticky=tk.W, padx=3, pady=2)

        g3 = ttk.LabelFrame(f, text="Alíquotas e CSTs", padding="8")
        g3.pack(fill=tk.X, padx=5, pady=3)

        row3 = 0
        ttk.Label(g3, text="Aliq. PIS %:").grid(row=row3, column=0, sticky=tk.W, padx=3, pady=2)
        self.var_aliq_pis = tk.StringVar(self)
        ttk.Entry(g3, textvariable=self.var_aliq_pis, width=8).grid(row=row3, column=1, sticky=tk.W, padx=3, pady=2)

        ttk.Label(g3, text="CST PIS:").grid(row=row3, column=2, sticky=tk.W, padx=3, pady=2)
        self.var_cst_pis = tk.StringVar(self)
        ttk.Entry(g3, textvariable=self.var_cst_pis, width=6).grid(row=row3, column=3, sticky=tk.W, padx=3, pady=2)

        ttk.Label(g3, text="Aliq. COFINS %:").grid(row=row3, column=4, sticky=tk.W, padx=3, pady=2)
        self.var_aliq_cofins = tk.StringVar(self)
        ttk.Entry(g3, textvariable=self.var_aliq_cofins, width=8).grid(row=row3, column=5, sticky=tk.W, padx=3, pady=2)

        ttk.Label(g3, text="CST COFINS:").grid(row=row3, column=6, sticky=tk.W, padx=3, pady=2)
        self.var_cst_cofins = tk.StringVar(self)
        ttk.Entry(g3, textvariable=self.var_cst_cofins, width=6).grid(row=row3, column=7, sticky=tk.W, padx=3, pady=2)

        row3 = 1
        ttk.Label(g3, text="Aliq. IPI %:").grid(row=row3, column=0, sticky=tk.W, padx=3, pady=2)
        self.var_aliq_ipi = tk.StringVar(self)
        ttk.Entry(g3, textvariable=self.var_aliq_ipi, width=8).grid(row=row3, column=1, sticky=tk.W, padx=3, pady=2)

        ttk.Label(g3, text="CST IPI:").grid(row=row3, column=2, sticky=tk.W, padx=3, pady=2)
        self.var_cst_ipi = tk.StringVar(self)
        ttk.Entry(g3, textvariable=self.var_cst_ipi, width=6).grid(row=row3, column=3, sticky=tk.W, padx=3, pady=2)

        g4 = ttk.LabelFrame(f, text="Configuração Operacional", padding="8")
        g4.pack(fill=tk.X, padx=5, pady=3)

        row4 = 0
        ttk.Label(g4, text="Estoque:").grid(row=row4, column=0, sticky=tk.W, padx=3, pady=2)
        self.var_estoque = tk.StringVar(self, value="S")
        ttk.Combobox(g4, textvariable=self.var_estoque, values=ops_sn_obrig, width=6, state='readonly').grid(row=row4, column=1, sticky=tk.W, padx=3, pady=2)

        ttk.Label(g4, text="Fluxo Caixa:").grid(row=row4, column=2, sticky=tk.W, padx=3, pady=2)
        self.var_fluxo_caixa = tk.StringVar(self, value="S")
        ttk.Combobox(g4, textvariable=self.var_fluxo_caixa, values=ops_sn_obrig, width=6, state='readonly').grid(row=row4, column=3, sticky=tk.W, padx=3, pady=2)

        ttk.Label(g4, text="Livros Fiscais:").grid(row=row4, column=4, sticky=tk.W, padx=3, pady=2)
        self.var_livros_fiscais = tk.StringVar(self, value="S")
        ttk.Combobox(g4, textvariable=self.var_livros_fiscais, values=ops_sn_obrig, width=6, state='readonly').grid(row=row4, column=5, sticky=tk.W, padx=3, pady=2)

        row4 = 1
        ttk.Label(g4, text="Contabilidade:").grid(row=row4, column=0, sticky=tk.W, padx=3, pady=2)
        self.var_contabilidade = tk.StringVar(self, value="S")
        ttk.Combobox(g4, textvariable=self.var_contabilidade, values=ops_sn_obrig, width=6, state='readonly').grid(row=row4, column=1, sticky=tk.W, padx=3, pady=2)

        ttk.Label(g4, text="Custo:").grid(row=row4, column=2, sticky=tk.W, padx=3, pady=2)
        self.var_custo = tk.StringVar(self, value="S")
        ttk.Combobox(g4, textvariable=self.var_custo, values=ops_sn_obrig, width=6, state='readonly').grid(row=row4, column=3, sticky=tk.W, padx=3, pady=2)

        ttk.Label(g4, text="Exige Pedido:").grid(row=row4, column=4, sticky=tk.W, padx=3, pady=2)
        self.var_pedido = tk.StringVar(self, value="N")
        ttk.Combobox(g4, textvariable=self.var_pedido, values=ops_sn_obrig, width=6, state='readonly').grid(row=row4, column=5, sticky=tk.W, padx=3, pady=2)

        row4 = 2
        ttk.Label(g4, text="Devolução:").grid(row=row4, column=0, sticky=tk.W, padx=3, pady=2)
        self.var_devolucao = tk.StringVar(self)
        ttk.Combobox(g4, textvariable=self.var_devolucao, values=ops_sn, width=6, state='readonly').grid(row=row4, column=1, sticky=tk.W, padx=3, pady=2)

        row4 = 3
        ttk.Label(g4, text="Complemento ICMS:").grid(row=row4, column=0, sticky=tk.W, padx=3, pady=2)
        self.var_compl_icms = tk.StringVar(self)
        ttk.Combobox(g4, textvariable=self.var_compl_icms, values=ops_sn, width=6, state='readonly').grid(row=row4, column=1, sticky=tk.W, padx=3, pady=2)

    def _on_cfop_base_select(self, event=None):
        cfop = self.var_cfop_base.get()
        if cfop and cfop in self.cfop_governo:
            row = self.cfop_governo[cfop]
            desc = row.get('descricao', '')
            if not self.var_desc_abr.get() or self.var_desc_abr.get() == '':
                self.var_desc_abr.set(resumir_descricao(desc))
            if not self.var_desc_comp.get() or self.var_desc_comp.get() == '':
                self.var_desc_comp.set(resumir_descricao(desc, 50))
        self._atualizar_codigo_completo()

    def _atualizar_codigo_completo(self):
        base = self.var_cfop_base.get().strip()
        seq = self.var_cfop_seq.get().strip().zfill(2) if self.var_cfop_seq.get().strip() else "__"
        cod = f"{base}{seq}" if base else "______"
        self.lbl_codigo_completo.config(text=cod)

    def _carregar_cfops_erp(self):
        self.lbl_info.config(text="Carregando CFOPs do ERP...")
        self.btn_salvar.config(state=tk.DISABLED)
        self.btn_excluir.config(state=tk.DISABLED)
        threading.Thread(target=self._carregar_cfops_bg, daemon=True).start()

    def _carregar_cfops_bg(self):
        try:
            with FirebirdService(self.config_db) as fb:
                sql = """SELECT * FROM TABELA_NAT_OPERACAO_SAIDA 
                         WHERE NAT_EMPRESA = ? AND NAT_FILIAL = ?
                         ORDER BY NAT_CODIGO"""
                self.cfops_erp = fb.query(sql, [self.empresa, self.filial])
            self.parent.after(0, self._preencher_tree)
        except Exception as e:
            self.parent.after(0, lambda e=e: self.lbl_info.config(text=f"Erro ao carregar ERP: {e}"))

    def _preencher_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.all_tree_iids = []
        self.cfops_erp_set = set()
        self.erp_bases = set()
        for cfop in self.cfops_erp:
            cod = str(cfop.get('nat_codigo', ''))
            self.cfops_erp_set.add(cod)
            self.erp_bases.add(cod[:4] if len(cod) >= 4 else cod)
            qtd_xml = self._get_xml_qtd(cod[:4] if len(cod) >= 4 else cod)
            desc_abr = str(cfop.get('nat_descricao_abr', ''))
            icms = str(cfop.get('nat_icms', '') or '-')
            pis = str(cfop.get('nat_pis', '') or '-')
            cofins = str(cfop.get('nat_cofins', '') or '-')
            desativado = str(cfop.get('nat_desativado', 'N'))
            tag = ('INATIVO',) if desativado == 'S' else ()
            self.tree.insert("", tk.END, iid=cod,
                             values=(cod, desc_abr, qtd_xml, "Cadastrado", icms, pis, cofins, desativado),
                             tags=tag)
            self.all_tree_iids.append(cod)

        if self.xml_cfop_data:
            self._adicionar_novos_da_analise()
            self.btn_importar.config(state=tk.NORMAL)

        self.atualizar_info()
        self.btn_salvar.config(state=tk.NORMAL)
        self.btn_excluir.config(state=tk.NORMAL)

    def _get_xml_qtd(self, base):
        if base in self.xml_cfop_data:
            return str(self.xml_cfop_data[base]['ocorrencias'])
        return "-"

    def _adicionar_novos_da_analise(self):
        for base, data in self.xml_cfop_data.items():
            if base not in self.erp_bases:
                iid = f"NOVO_{base}"
                desc = self.cfop_governo.get(base, {}).get('descricao', '') if base in self.cfop_governo else ''
                qtd = str(data['ocorrencias'])
                self.tree.insert("", tk.END, iid=iid,
                                 values=(f"{base}__", desc, qtd, "Novo", "", "", "", ""),
                                 tags=('NOVO',))
                self.all_tree_iids.append(iid)

    def atualizar_info(self):
        total_erp = len(self.cfops_erp)
        total_xml = sum(d['ocorrencias'] for d in self.xml_cfop_data.values()) if self.xml_cfop_data else 0
        bases_xml = set(self.xml_cfop_data.keys()) if self.xml_cfop_data else set()
        novos = len(bases_xml - self.erp_bases)
        if self.xml_cfop_data:
            self.lbl_info.config(
                text=f"{total_erp} CFOPs no ERP  |  {total_xml} ocorrências em XMLs  |  {novos} novos para importar"
            )
        else:
            self.lbl_info.config(text=f"{total_erp} CFOPs carregados do ERP. Clique em 'Carregar XMLs' para analisar.")

    def _on_tree_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        cod = sel[0]
        if cod.startswith("NOVO_"):
            base = cod.replace("NOVO_", "")
            self._limpar_form()
            self.var_cfop_base.set(base)
            self.var_cfop_seq.set("01")
            gov = self.cfop_governo.get(base)
            if gov:
                desc = gov.get('descricao', '')
                self.var_desc_abr.set(resumir_descricao(desc))
                self.var_desc_comp.set(resumir_descricao(desc, 50))
            self._atualizar_codigo_completo()
            self.editando_codigo = None
            return

        self.editando_codigo = cod
        cfop = None
        for c in self.cfops_erp:
            if str(c.get('nat_codigo', '')) == cod:
                cfop = c
                break
        if not cfop:
            return

        cod_raw = str(cfop.get('nat_codigo', ''))
        base = cod_raw[:4] if len(cod_raw) >= 4 else cod_raw
        seq = cod_raw[4:6] if len(cod_raw) >= 6 else ''

        self.var_cfop_base.set(base)
        self.var_cfop_seq.set(seq)
        self.var_desc_abr.set(str(cfop.get('nat_descricao_abr', '')))
        self.var_desc_comp.set(str(cfop.get('nat_descricao_comp', '')))
        self.var_obs.set(str(cfop.get('nat_observacao', '') or ''))

        self.var_icms.set(str(cfop.get('nat_icms', '') or ''))
        self.var_pis_flag.set(str(cfop.get('nat_pis', '') or ''))
        self.var_cofins_flag.set(str(cfop.get('nat_cofins', '') or ''))
        self.var_st.set(str(cfop.get('nat_st', '') or ''))
        self.var_ipi_flag.set(str(cfop.get('nat_ipi', '') or ''))
        self.var_desativado.set(str(cfop.get('nat_desativado', 'N')))

        self.var_aliq_pis.set(str(cfop.get('nat_aliq_pis', '') or ''))
        self.var_aliq_cofins.set(str(cfop.get('nat_aliq_cofins', '') or ''))
        self.var_aliq_ipi.set(str(cfop.get('nat_aliq_ipi', '') or ''))
        self.var_cst_pis.set(str(cfop.get('nat_sit_pis', '') or ''))
        self.var_cst_cofins.set(str(cfop.get('nat_sit_cofins', '') or ''))
        self.var_cst_ipi.set(str(cfop.get('nat_sit_ipi', '') or ''))

        self.var_estoque.set(str(cfop.get('nat_estoque', 'S')))
        self.var_fluxo_caixa.set(str(cfop.get('nat_fluxo_caixa', 'S')))
        self.var_livros_fiscais.set(str(cfop.get('nat_livros_fiscais', 'S')))
        self.var_contabilidade.set(str(cfop.get('nat_contabilidade', 'S')))
        self.var_custo.set(str(cfop.get('nat_custo', 'S')))
        self.var_pedido.set(str(cfop.get('nat_pedido', 'N')))
        self.var_devolucao.set(str(cfop.get('nat_devolucao', '') or ''))
        self.var_compl_icms.set(str(cfop.get('nat_complemento_icms', '') or ''))

        self._atualizar_codigo_completo()

    def _limpar_form(self):
        self.editando_codigo = None
        self.var_cfop_base.set('')
        self.var_cfop_seq.set('')
        self.var_desc_abr.set('')
        self.var_desc_comp.set('')
        self.var_obs.set('')
        self.var_icms.set('')
        self.var_pis_flag.set('')
        self.var_cofins_flag.set('')
        self.var_st.set('')
        self.var_ipi_flag.set('')
        self.var_desativado.set('N')
        self.var_aliq_pis.set('')
        self.var_aliq_cofins.set('')
        self.var_aliq_ipi.set('')
        self.var_cst_pis.set('')
        self.var_cst_cofins.set('')
        self.var_cst_ipi.set('')
        self.var_estoque.set('S')
        self.var_fluxo_caixa.set('S')
        self.var_livros_fiscais.set('S')
        self.var_contabilidade.set('S')
        self.var_custo.set('S')
        self.var_pedido.set('N')
        self.var_devolucao.set('')
        self.var_compl_icms.set('')
        self._atualizar_codigo_completo()

    def _novo_cfop(self):
        self._limpar_form()
        self.tree.selection_remove(self.tree.selection())
        self.var_cfop_base.focus_set()

    def _upsert_cfop(self, colunas_valores):
        with FirebirdService(self.config_db) as fb:
            cursor = fb.conn.cursor()
            key_map = {c: v for c, v in colunas_valores if c in ('NAT_EMPRESA', 'NAT_FILIAL', 'NAT_CODIGO')}
            cursor.execute("SELECT COUNT(*) FROM TABELA_NAT_OPERACAO_SAIDA WHERE NAT_EMPRESA=? AND NAT_FILIAL=? AND NAT_CODIGO=?",
                           (key_map['NAT_EMPRESA'], key_map['NAT_FILIAL'], key_map['NAT_CODIGO']))
            exists = cursor.fetchone()[0] > 0
            if exists:
                set_items = [(c, v) for c, v in colunas_valores if c not in ('NAT_EMPRESA', 'NAT_FILIAL', 'NAT_CODIGO')]
                if not set_items:
                    return
                set_clause = ", ".join(f"{c}=?" for c, _ in set_items)
                cursor.execute(f"UPDATE TABELA_NAT_OPERACAO_SAIDA SET {set_clause} WHERE NAT_EMPRESA=? AND NAT_FILIAL=? AND NAT_CODIGO=?",
                               tuple(v for _, v in set_items) + (key_map['NAT_EMPRESA'], key_map['NAT_FILIAL'], key_map['NAT_CODIGO']))
            else:
                cols = ", ".join(c for c, _ in colunas_valores)
                qmarks = ", ".join("?" for _ in colunas_valores)
                cursor.execute(f"INSERT INTO TABELA_NAT_OPERACAO_SAIDA ({cols}) VALUES ({qmarks})",
                               tuple(v for _, v in colunas_valores))
            fb.conn.commit()

    def _salvar_cfop(self):
        base = self.var_cfop_base.get().strip()
        seq = self.var_cfop_seq.get().strip().zfill(2)
        if not base or not seq:
            return messagebox.showwarning("Validação", "Informe o CFOP (4 dígitos) e o Sequencial (2 dígitos).")
        if not base.isdigit() or len(base) != 4:
            return messagebox.showwarning("Validação", "CFOP deve ter exatamente 4 dígitos numéricos.")
        if not seq.isdigit() or len(seq) != 2:
            return messagebox.showwarning("Validação", "Sequencial deve ter exatamente 2 dígitos numéricos.")
        if not self.var_desc_abr.get().strip():
            return messagebox.showwarning("Validação", "Informe a descrição abreviada.")

        codigo = base + seq

        def _extrair_float(v):
            if not v or not str(v).strip():
                return 0.0
            try:
                return float(str(v).replace(',', '.').replace('%', '').strip())
            except ValueError:
                return 0.0

        pis_val = _extrair_float(self.var_aliq_pis.get())
        cofins_val = _extrair_float(self.var_aliq_cofins.get())
        ipi_val = _extrair_float(self.var_aliq_ipi.get())

        vazio_ou_nulo = lambda v: v if v else None
        sn_ou_nulo = lambda v: v if v in ('S', 'N') else None

        def task():
            try:
                colunas_valores = [
                    ("NAT_EMPRESA", int(self.empresa)),
                    ("NAT_FILIAL", int(self.filial)),
                    ("NAT_CODIGO", codigo),
                    ("NAT_DESCRICAO_ABR", resumir_descricao(self.var_desc_abr.get().strip())),
                    ("NAT_DESCRICAO_COMP", vazio_ou_nulo(resumir_descricao(self.var_desc_comp.get().strip(), 50))),
                    ("NAT_OBSERVACAO", vazio_ou_nulo(self.var_obs.get().strip())),
                    ("NAT_ICMS", sn_ou_nulo(self.var_icms.get())),
                    ("NAT_PIS", sn_ou_nulo(self.var_pis_flag.get())),
                    ("NAT_COFINS", sn_ou_nulo(self.var_cofins_flag.get())),
                    ("NAT_ST", sn_ou_nulo(self.var_st.get())),
                    ("NAT_IPI", sn_ou_nulo(self.var_ipi_flag.get())),
                    ("NAT_COMPLEMENTO_ICMS", sn_ou_nulo(self.var_compl_icms.get())),
                    ("NAT_ALIQ_PIS", pis_val),
                    ("NAT_ALIQ_COFINS", cofins_val),
                    ("NAT_ALIQ_IPI", ipi_val),
                    ("NAT_SIT_PIS", vazio_ou_nulo(self.var_cst_pis.get().strip())),
                    ("NAT_SIT_COFINS", vazio_ou_nulo(self.var_cst_cofins.get().strip())),
                    ("NAT_SIT_IPI", vazio_ou_nulo(self.var_cst_ipi.get().strip())),
                    ("NAT_ESTOQUE", self.var_estoque.get()),
                    ("NAT_FLUXO_CAIXA", self.var_fluxo_caixa.get()),
                    ("NAT_LIVROS_FISCAIS", self.var_livros_fiscais.get()),
                    ("NAT_CONTABILIDADE", self.var_contabilidade.get()),
                    ("NAT_CUSTO", self.var_custo.get()),
                    ("NAT_PEDIDO", self.var_pedido.get()),
                    ("NAT_DEVOLUCAO", sn_ou_nulo(self.var_devolucao.get())),
                    ("NAT_DESATIVADO", self.var_desativado.get()),
                    ("NAT_TRANSF_ICMS", None),
                    ("NAT_PROD_EMP", int(self.empresa)),
                    ("NAT_PROD_FIL", int(self.filial)),
                    ("NAT_CONTABIL_EMPRESA", int(self.empresa)),
                    ("NAT_CONTABIL_FILIAL", int(self.filial)),
                    ("NAT_CONTABIL_EXERCICIO", int(self.exercicio)),
                    ("NAT_HIST_CONTABIL_EMP", int(self.empresa)),
                    ("NAT_HIST_CONTABIL_FILIAL", int(self.filial)),
                    ("NAT_HIST_CONTABIL", 1),
                    ("NAT_CC_EMPRESA", int(self.empresa)),
                    ("NAT_CC_FILIAL", int(self.filial)),
                    ("NAT_CC_CODIGO", 11),
                    ("NAT_TLC_CREDITO_ICMS_EMPRESA", int(self.empresa)),
                    ("NAT_TLC_CREDITO_ICMS_FILIAL", int(self.filial)),
                    ("NAT_TLC_ESTORNO_PIS_EMPRESA", int(self.empresa)),
                    ("NAT_TLC_ESTORNO_PIS_FILIAL", int(self.filial)),
                    ("NAT_TLC_ESTORNO_COFINS_EMPRESA", int(self.empresa)),
                    ("NAT_TLC_ESTORNO_COFINS_FILIAL", int(self.filial)),
                    ("NAT_NAO_ESCR_SPED_CONT", 'N'),
                    ("NAT_DEDUZIR_ICMS_BASE_PISCOFINS", 'N'),
                    ("NAT_N_DEDUZIR_ICMS_BASE_PISCOFI", 'N'),
                    ("NAT_DEDUZIR_ICMS_BASE_PIS", 'N'),
                    ("NAT_DEDUZIR_ICMS_BASE_COFINS", 'N'),
                ]
                self._upsert_cfop(colunas_valores)
                self.parent.after(0, lambda: self._pos_salvar(codigo))
            except Exception as e:
                self.parent.after(0, lambda e=e: messagebox.showerror("Erro", f"Falha ao salvar CFOP {codigo}:\n{e}"))

        threading.Thread(target=task, daemon=True).start()

    def _pos_salvar(self, codigo):
        messagebox.showinfo("Sucesso", f"CFOP {codigo} salvo com sucesso!")
        self._carregar_cfops_erp()

    def _desativar_cfop(self):
        if not self.editando_codigo:
            return messagebox.showwarning("Aviso", "Selecione um CFOP na lista.")
        codigo = self.editando_codigo
        if not messagebox.askyesno("Confirmar", f"Desativar CFOP {codigo}?"):
            return
        def task(cod):
            try:
                with FirebirdService(self.config_db) as fb:
                    cursor = fb.conn.cursor()
                    cursor.execute(
                        "UPDATE TABELA_NAT_OPERACAO_SAIDA SET NAT_DESATIVADO = 'S' WHERE NAT_EMPRESA = ? AND NAT_FILIAL = ? AND NAT_CODIGO = ?",
                        (int(self.empresa), int(self.filial), cod)
                    )
                    fb.conn.commit()
                self.parent.after(0, self._carregar_cfops_erp)
            except Exception as e:
                self.parent.after(0, lambda e=e: messagebox.showerror("Erro", str(e)))
        threading.Thread(target=task, args=(codigo,), daemon=True).start()

    def _filtrar_tree(self, event=None):
        filtro = self.var_filtro.get().strip().lower()
        for item in self.tree.get_children():
            self.tree.detach(item)
        for item in self.all_tree_iids:
            if not filtro:
                self.tree.reattach(item, '', 'end')
            else:
                vals = self.tree.item(item, 'values')
                if any(filtro in str(v).lower() for v in vals):
                    self.tree.reattach(item, '', 'end')

    def _sort_treeview(self, col):
        self._sort_directions[col] = not self._sort_directions[col]
        reverse = self._sort_directions[col]
        items = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        def sort_key(v):
            try:
                return (0, float(str(v[0]).replace('%', '').strip()))
            except ValueError:
                return (1, str(v[0]).lower())
        items.sort(key=sort_key, reverse=reverse)
        for idx, (_, k) in enumerate(items):
            self.tree.move(k, '', idx)
        for c in self._sort_directions:
            if c == col:
                arrow = " ▼" if self._sort_directions[c] else " ▲"
            else:
                arrow = " ↕"
            self.tree.heading(c, text=c + arrow, command=lambda x=c: self._sort_treeview(x))

    def _exportar_csv(self):
        caminho = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="CFOP_ERP.csv", filetypes=[("CSV", "*.csv")])
        if not caminho: return
        try:
            with open(caminho, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(["CÓDIGO", "DESCRIÇÃO ABR", "DESCRIÇÃO COMP", "ICMS", "PIS", "COFINS",
                                 "ST", "IPI", "ESTOQUE", "FLUXO CAIXA", "LIVROS FISCAIS",
                                 "CONTABILIDADE", "CUSTO", "PEDIDO", "DEVOLUÇÃO", "ATIVO"])
                for c in self.cfops_erp:
                    writer.writerow([
                        c.get('nat_codigo', ''),
                        c.get('nat_descricao_abr', ''),
                        c.get('nat_descricao_comp', ''),
                        c.get('nat_icms', ''),
                        c.get('nat_pis', ''),
                        c.get('nat_cofins', ''),
                        c.get('nat_st', ''),
                        c.get('nat_ipi', ''),
                        c.get('nat_estoque', ''),
                        c.get('nat_fluxo_caixa', ''),
                        c.get('nat_livros_fiscais', ''),
                        c.get('nat_contabilidade', ''),
                        c.get('nat_custo', ''),
                        c.get('nat_pedido', ''),
                        c.get('nat_devolucao', ''),
                        c.get('nat_desativado', 'N')
                    ])
            messagebox.showinfo("Sucesso", "CSV exportado!")
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def _analisar_xmls(self):
        resposta = messagebox.askyesnocancel("Selecionar XMLs",
            "Sim = Selecionar pasta com XMLs\nNão = Selecionar arquivos individuais\nCancelar = Voltar")
        if resposta is None:
            return

        if resposta:
            pasta = filedialog.askdirectory(title="Selecionar pasta com XMLs")
            if not pasta:
                return
            arquivos = None
            pasta_path = pasta
        else:
            arquivos = filedialog.askopenfilenames(title="Selecionar XMLs", filetypes=[("XML", "*.xml")])
            if not arquivos:
                return
            pasta_path = None

        self.lbl_info.config(text="Analisando XMLs... Aguarde.")
        self.btn_importar.config(state=tk.DISABLED)
        threading.Thread(target=self._analisar_xmls_bg, args=(pasta_path, arquivos), daemon=True).start()

    def _analisar_xmls_bg(self, pasta_path, arquivos):
        try:
            itens_xml = []
            if arquivos:
                for arq in arquivos:
                    try:
                        itens_xml.extend(parse_nfe(arq)['itens'])
                    except Exception:
                        pass
            else:
                itens_xml = parse_nfe_folder(pasta_path)

            mapa = {}
            for i in itens_xml:
                cfop = str(i.get('cfop', '')).strip()
                if not cfop:
                    continue
                base = cfop[:4] if len(cfop) >= 4 else cfop
                if base not in mapa:
                    mapa[base] = {'cfop': base, 'ocorrencias': 1}
                else:
                    mapa[base]['ocorrencias'] += 1

            self.xml_cfop_data = mapa
            self.parent.after(0, self._mesclar_resultado_xml)
        except Exception as e:
            self.parent.after(0, lambda e=e: self.lbl_info.config(text=f"Erro na análise: {e}"))

    def _mesclar_resultado_xml(self):
        if not self.xml_cfop_data:
            return messagebox.showinfo("Análise", "Nenhum CFOP encontrado nos XMLs.")

        for item in self.tree.get_children():
            self.tree.delete(item)
        self.all_tree_iids = []

        for cfop in self.cfops_erp:
            cod = str(cfop.get('nat_codigo', ''))
            base = cod[:4] if len(cod) >= 4 else cod
            qtd_xml = self._get_xml_qtd(base)
            desc_abr = str(cfop.get('nat_descricao_abr', ''))
            icms = str(cfop.get('nat_icms', '') or '-')
            pis = str(cfop.get('nat_pis', '') or '-')
            cofins = str(cfop.get('nat_cofins', '') or '-')
            desativado = str(cfop.get('nat_desativado', 'N'))
            tag = ('INATIVO',) if desativado == 'S' else ()
            self.tree.insert("", tk.END, iid=cod,
                             values=(cod, desc_abr, qtd_xml, "Cadastrado", icms, pis, cofins, desativado),
                             tags=tag)
            self.all_tree_iids.append(cod)

        self._adicionar_novos_da_analise()
        self.atualizar_info()

        if any(i.startswith("NOVO_") for i in self.all_tree_iids):
            self.btn_importar.config(state=tk.NORMAL)
            messagebox.showinfo("Análise",
                f"{len(self.xml_cfop_data)} CFOPs encontrados nos XMLs.\n"
                f"Selecione os 'Novo' na lista e clique em 'Importar Selecionados' para criar todos de uma vez, "
                f"ou clique em um item 'Novo' para editar antes de salvar.")
        else:
            messagebox.showinfo("Análise",
                "Todos os CFOPs encontrados nos XMLs já estão cadastrados no ERP.")

    def _importar_selecionados(self):
        sel = self.tree.selection()
        novos = [item for item in sel if item.startswith("NOVO_")]
        if not novos:
            return messagebox.showwarning("Importar", "Selecione CFOPs com status 'Novo' na lista.\n(Mantenha Ctrl pressionado para selecionar vários.)")

        if not messagebox.askyesno("Importar", f"Importar {len(novos)} CFOP(s) com seq=01 e valores padrão?\n\nDepois você pode editar individualmente."):
            return

        def task():
            importados = 0
            erros = []
            for iid in novos:
                base = iid.replace("NOVO_", "")
                codigo = base + "01"
                if codigo in self.cfops_erp_set:
                    erros.append(f"{codigo}: já existe")
                    continue
                desc = self.cfop_governo.get(base, {}).get('descricao', '')
                try:
                    colunas_valores = [
                        ("NAT_EMPRESA", int(self.empresa)),
                        ("NAT_FILIAL", int(self.filial)),
                        ("NAT_CODIGO", codigo),
                        ("NAT_DESCRICAO_ABR", desc),
                        ("NAT_DESCRICAO_COMP", resumir_descricao(desc, 50)),
                        ("NAT_ESTOQUE", 'S'),
                        ("NAT_FLUXO_CAIXA", 'S'),
                        ("NAT_LIVROS_FISCAIS", 'S'),
                        ("NAT_CONTABILIDADE", 'S'),
                        ("NAT_CUSTO", 'S'),
                        ("NAT_PEDIDO", 'N'),
                        ("NAT_DESATIVADO", 'N'),
                        ("NAT_PROD_EMP", int(self.empresa)),
                        ("NAT_PROD_FIL", int(self.filial)),
                        ("NAT_CONTABIL_EMPRESA", int(self.empresa)),
                        ("NAT_CONTABIL_FILIAL", int(self.filial)),
                        ("NAT_CONTABIL_EXERCICIO", int(self.exercicio)),
                        ("NAT_HIST_CONTABIL_EMP", int(self.empresa)),
                        ("NAT_HIST_CONTABIL_FILIAL", int(self.filial)),
                        ("NAT_HIST_CONTABIL", 1),
                        ("NAT_CC_EMPRESA", int(self.empresa)),
                        ("NAT_CC_FILIAL", int(self.filial)),
                        ("NAT_CC_CODIGO", 11),
                        ("NAT_TLC_CREDITO_ICMS_EMPRESA", int(self.empresa)),
                        ("NAT_TLC_CREDITO_ICMS_FILIAL", int(self.filial)),
                        ("NAT_TLC_ESTORNO_PIS_EMPRESA", int(self.empresa)),
                        ("NAT_TLC_ESTORNO_PIS_FILIAL", int(self.filial)),
                        ("NAT_TLC_ESTORNO_COFINS_EMPRESA", int(self.empresa)),
                        ("NAT_TLC_ESTORNO_COFINS_FILIAL", int(self.filial)),
                        ("NAT_NAO_ESCR_SPED_CONT", 'N'),
                        ("NAT_DEDUZIR_ICMS_BASE_PISCOFINS", 'N'),
                        ("NAT_N_DEDUZIR_ICMS_BASE_PISCOFI", 'N'),
                        ("NAT_DEDUZIR_ICMS_BASE_PIS", 'N'),
                        ("NAT_DEDUZIR_ICMS_BASE_COFINS", 'N'),
                    ]
                    self._upsert_cfop(colunas_valores)
                    importados += 1
                except Exception as e:
                    erros.append(f"{codigo}: {e}")

            self.parent.after(0, lambda: self._pos_importar(importados, erros))

        threading.Thread(target=task, daemon=True).start()

    def _pos_importar(self, importados, erros):
        if erros:
            msg = f"{importados} importados com sucesso.\n{len(erros)} erro(s):\n" + "\n".join(erros[:5])
            if len(erros) > 5:
                msg += f"\n... e mais {len(erros)-5} erro(s)"
            messagebox.showwarning("Importação parcial", msg)
        else:
            messagebox.showinfo("Sucesso", f"{importados} CFOP(s) importados com sucesso!")
        self._carregar_cfops_erp()
        self.btn_importar.config(state=tk.DISABLED)
        self.xml_cfop_data = {}

    def _fechar_tela(self):
        self.destroy()
        if self.callback_voltar:
            self.callback_voltar()

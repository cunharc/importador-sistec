import tkinter as tk
from tkinter import ttk, messagebox
import json

class TelaTributacaoNCM(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.dados_sistema = {}
        self.dados_xml = []
        self.item_selecionado = None
        
        self.colunas = ("ncm", "status", "descricao", "icms_xml", "icms_sys", "pis_xml", "pis_sys", "cofins_xml", "cofins_sys")
        self.titulos_colunas = {
            "ncm": "NCM", "status": "Status", "descricao": "Descrição (Sistema/XML)",
            "icms_xml": "ICMS XML", "icms_sys": "ICMS Sis.", "pis_xml": "PIS XML",
            "pis_sys": "PIS Sis.", "cofins_xml": "COFINS XML", "cofins_sys": "COFINS Sis."
        }
        self._sort_directions = {col: False for col in self.colunas}
        
        self.configurar_interface()
        self.carregar_dados_mock()
        self.processar_comparacao()

    def configurar_interface(self):
        # --- FRAME TOPO: Controles ---
        frame_topo = tk.Frame(self, pady=10, padx=10)
        frame_topo.pack(side=tk.TOP, fill=tk.X)
        
        tk.Label(frame_topo, text="Auditoria de Tributação NCM (XML vs Sistema)", font=("Segoe UI", 16, "bold"), fg="#003399").pack(side=tk.LEFT)
        
        btn_carregar = ttk.Button(frame_topo, text="↻ Recarregar Dados", command=self.processar_comparacao)
        btn_carregar.pack(side=tk.RIGHT, padx=5)

        # --- FRAME MEIO: Tabela (Treeview) ---
        frame_tabela = tk.Frame(self, padx=10)
        frame_tabela.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        self.tree = ttk.Treeview(frame_tabela, columns=self.colunas, show="headings", height=10)
        
        # Configuração dos Cabeçalhos e Colunas
        for col in self.colunas:
            self.tree.heading(col, text=self.titulos_colunas[col] + " ↕", command=lambda c=col: self._sort_treeview(c))
            self.tree.column(col, width=80, anchor=tk.CENTER)
            
        self.tree.column("descricao", width=250, anchor=tk.W)
        self.tree.column("status", width=90)
        
        # Tags de cores para status
        self.tree.tag_configure("novo", background="#e6ffe6", foreground="#006600") # Verde claro
        self.tree.tag_configure("diferente", background="#fff3e6", foreground="#cc6600") # Laranja claro
        self.tree.tag_configure("ok", background="#ffffff", foreground="black") # Branco
        
        # Scrollbar
        scroll_y = ttk.Scrollbar(frame_tabela, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll_y.set)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.tree.bind("<<TreeviewSelect>>", self.on_selecionar_item)

        # --- FRAME BASE: Painel de Edição/Ação ---
        frame_base = tk.LabelFrame(self, text="Detalhes e Ações do NCM Selecionado", padx=10, pady=10, font=("Segoe UI", 10, "bold"))
        frame_base.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        
        # Variáveis de controle
        self.var_ncm = tk.StringVar()
        self.var_desc = tk.StringVar()
        self.var_icms = tk.DoubleVar()
        self.var_pis = tk.DoubleVar()
        self.var_cofins = tk.DoubleVar()
        
        # Grid de edição
        tk.Label(frame_base, text="NCM:").grid(row=0, column=0, sticky=tk.W, pady=2)
        tk.Entry(frame_base, textvariable=self.var_ncm, state="readonly", width=15).grid(row=0, column=1, pady=2, padx=5)
        
        tk.Label(frame_base, text="Descrição:").grid(row=0, column=2, sticky=tk.W, pady=2)
        tk.Entry(frame_base, textvariable=self.var_desc, width=45).grid(row=0, column=3, columnspan=3, pady=2, padx=5)
        
        tk.Label(frame_base, text="ICMS Venda (%):").grid(row=1, column=0, sticky=tk.W, pady=2)
        tk.Entry(frame_base, textvariable=self.var_icms, width=10).grid(row=1, column=1, pady=2, padx=5, sticky=tk.W)
        
        tk.Label(frame_base, text="PIS (%):").grid(row=1, column=2, sticky=tk.W, pady=2)
        tk.Entry(frame_base, textvariable=self.var_pis, width=10).grid(row=1, column=3, pady=2, padx=5, sticky=tk.W)
        
        tk.Label(frame_base, text="COFINS (%):").grid(row=1, column=4, sticky=tk.W, pady=2)
        tk.Entry(frame_base, textvariable=self.var_cofins, width=10).grid(row=1, column=5, pady=2, padx=5, sticky=tk.W)

        # Botões de Ação
        frame_acoes = tk.Frame(frame_base)
        frame_acoes.grid(row=2, column=0, columnspan=6, pady=10)
        
        self.btn_copiar_xml = ttk.Button(frame_acoes, text="⬇ Copiar Impostos do XML", command=self.copiar_dados_xml)
        self.btn_copiar_xml.pack(side=tk.LEFT, padx=5)
        
        self.btn_salvar = ttk.Button(frame_acoes, text="💾 Salvar no Sistema", command=self.salvar_ncm)
        self.btn_salvar.pack(side=tk.LEFT, padx=5)

    def carregar_dados_mock(self):
        """
        Simula o carregamento do JSON do banco de dados e do XML da nota fiscal.
        Na prática, você substituirá isso pelas suas funções de leitura de arquivo/banco.
        """
        # 1. Carregando o JSON fornecido (Sistema)
        json_string = """{
            "SELECT * FROM TABELA_class_fiscal": [
                {"CFIS_CODIGO": "0804.40.00", "CFIS_DESCRICAO": "ABACATES FRESCOS OU SECOS", "CFIS_IPI": 0.0, "CFIS_PIS": 0.0, "CFIS_COFINS": 0.0, "CFIS_ICMS_VENDA": 1.0},
                {"CFIS_CODIGO": "0808.10.00", "CFIS_DESCRICAO": "MACAS FRESCAS", "CFIS_IPI": 0.0, "CFIS_PIS": 0.0, "CFIS_COFINS": 0.0, "CFIS_ICMS_VENDA": 1.0},
                {"CFIS_CODIGO": "0201.20.20", "CFIS_DESCRICAO": "QUARTOS TRASEIROS,DE BOVINO", "CFIS_IPI": 0.0, "CFIS_PIS": 0.0, "CFIS_COFINS": 0.0, "CFIS_ICMS_VENDA": 7.0}
            ]
        }"""
        dados_brutos = json.loads(json_string)
        
        # Transformar em um dicionário para busca rápida: { "0804.40.00": {dict...} }
        self.dados_sistema = {}
        for item in dados_brutos["SELECT * FROM TABELA_class_fiscal"]:
            self.dados_sistema[item["CFIS_CODIGO"]] = item

        # 2. Simulando leitura de um XML de Entrada
        self.dados_xml = [
            # NCM existe e está IGUAL ao sistema
            {"ncm": "0804.40.00", "descricao": "ABACATES DIVERSOS", "icms": 1.0, "pis": 0.0, "cofins": 0.0},
            # NCM existe, mas impostos estão DIFERENTES
            {"ncm": "0201.20.20", "descricao": "QUARTOS TRASEIROS BOVINO", "icms": 12.0, "pis": 1.65, "cofins": 7.6},
            # NCM NOVO, não existe no sistema
            {"ncm": "1905.90.90", "descricao": "OUTROS PAES E BOLOS", "icms": 18.0, "pis": 1.65, "cofins": 7.6}
        ]

    def processar_comparacao(self):
        """Compara os dados do XML com os do Sistema e popula a Treeview"""
        # Limpa a tabela
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        for item_xml in self.dados_xml:
            ncm = item_xml["ncm"]
            xml_icms = item_xml["icms"]
            xml_pis = item_xml["pis"]
            xml_cofins = item_xml["cofins"]
            
            sys_item = self.dados_sistema.get(ncm)
            
            if not sys_item:
                status = "NOVO"
                tag = "novo"
                desc_sys = "--- NÃO CADASTRADO ---"
                sys_icms, sys_pis, sys_cofins = "-", "-", "-"
            else:
                sys_icms = sys_item.get("CFIS_ICMS_VENDA", 0.0)
                sys_pis = sys_item.get("CFIS_PIS", 0.0)
                sys_cofins = sys_item.get("CFIS_COFINS", 0.0)
                desc_sys = sys_item.get("CFIS_DESCRICAO", "")
                
                # Lógica de divergência
                if float(xml_icms) != float(sys_icms) or float(xml_pis) != float(sys_pis) or float(xml_cofins) != float(sys_cofins):
                    status = "DIFERENTE"
                    tag = "diferente"
                else:
                    status = "OK"
                    tag = "ok"
            
            # Mostrar descrição do XML se for novo, senão mostrar do sistema
            desc_exibicao = item_xml["descricao"] if status == "NOVO" else desc_sys
            
            valores = (
                ncm, status, desc_exibicao, 
                xml_icms, sys_icms, 
                xml_pis, sys_pis, 
                xml_cofins, sys_cofins
            )
            
            self.tree.insert("", tk.END, values=valores, tags=(tag,))

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
            
        for c in self.colunas:
            if c == col:
                arrow = " ▼" if self._sort_directions[c] else " ▲"
            else:
                arrow = " ↕"
            self.tree.heading(c, text=self.titulos_colunas[c] + arrow, command=lambda x=c: self._sort_treeview(x))

    def on_selecionar_item(self, event):
        """Preenche os campos de edição ao clicar em uma linha da tabela"""
        selecao = self.tree.selection()
        if not selecao:
            return
            
        self.item_selecionado = self.tree.item(selecao[0])
        valores = self.item_selecionado["values"]
        
        ncm = str(valores[0])
        status = valores[1]
        
        self.var_ncm.set(ncm)
        self.var_desc.set(valores[2])
        
        # Se for novo, sugere os impostos do XML, se já existir, puxa do sistema para edição
        if status == "NOVO":
            self.var_icms.set(valores[3])
            self.var_pis.set(valores[5])
            self.var_cofins.set(valores[7])
            self.btn_salvar.config(text="➕ Cadastrar Novo NCM")
        else:
            # Puxa os dados do sistema
            self.var_icms.set(valores[4] if valores[4] != "-" else 0.0)
            self.var_pis.set(valores[6] if valores[6] != "-" else 0.0)
            self.var_cofins.set(valores[8] if valores[8] != "-" else 0.0)
            self.btn_salvar.config(text="💾 Atualizar NCM no Sistema")

    def copiar_dados_xml(self):
        """Pega as alíquotas da coluna XML e joga nos campos de edição (Entry)"""
        if not self.item_selecionado:
            messagebox.showwarning("Aviso", "Selecione um item na lista primeiro.")
            return
            
        valores = self.item_selecionado["values"]
        self.var_icms.set(valores[3])
        self.var_pis.set(valores[5])
        self.var_cofins.set(valores[7])
        messagebox.showinfo("Sucesso", "Dados do XML transferidos para o formulário. Clique em Salvar para efetivar.")

    def salvar_ncm(self):
        """Salva ou atualiza os dados no dicionário interno (Sistema) e recarrega a tabela"""
        ncm = self.var_ncm.get()
        if not ncm:
            messagebox.showwarning("Aviso", "Nenhum NCM selecionado.")
            return
            
        # Lógica para salvar no dicionário do sistema (simulando um UPDATE/INSERT no Banco de Dados)
        if ncm in self.dados_sistema:
            # UPDATE
            self.dados_sistema[ncm]["CFIS_DESCRICAO"] = self.var_desc.get()
            self.dados_sistema[ncm]["CFIS_ICMS_VENDA"] = self.var_icms.get()
            self.dados_sistema[ncm]["CFIS_PIS"] = self.var_pis.get()
            self.dados_sistema[ncm]["CFIS_COFINS"] = self.var_cofins.get()
            msg = f"NCM {ncm} atualizado com sucesso!"
        else:
            # INSERT
            self.dados_sistema[ncm] = {
                "CFIS_CODIGO": ncm,
                "CFIS_DESCRICAO": self.var_desc.get(),
                "CFIS_ICMS_VENDA": self.var_icms.get(),
                "CFIS_PIS": self.var_pis.get(),
                "CFIS_COFINS": self.var_cofins.get(),
                "CFIS_IPI": 0.0 # Valor default
            }
            msg = f"NCM {ncm} cadastrado com sucesso!"
            
        messagebox.showinfo("Sucesso", msg)
        
        # Recalcula a grade após a alteração
        self.processar_comparacao()

# Código para você conseguir testar a tela isoladamente (Standalone)
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Módulo de Tributação - SISTEC")
    root.geometry("900x500")
    
    # Configurando o estilo
    style = ttk.Style()
    if "clam" in style.theme_names():
        style.theme_use("clam")
    style.configure("Treeview.Heading", background="#003399", foreground="white", font=('Segoe UI', 9, 'bold'))
    style.map("Treeview", background=[('selected', '#D0E4FF')], foreground=[('selected', '#1A1A1A')])
    
    app = TelaTributacaoNCM(root)
    app.pack(fill=tk.BOTH, expand=True)
    root.mainloop()
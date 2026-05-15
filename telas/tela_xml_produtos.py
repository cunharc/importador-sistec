import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import configparser
import threading
import os
from utils.firebird_service import FirebirdService
from utils.xml_reader import parse_nfe_folder, parse_nfe
from utils.validator import ValidatorFiscal
from utils.report_generator import generate_audit_report
from utils.transformer import DataTransformer
from utils.importer import FirebirdImporter

class ModalPreviewProdutos(tk.Toplevel):
    def __init__(self, parent, itens, config, config_db, classificacao, grupos_db, subgrupos_db, callback_importar):
        super().__init__(parent)
        self.title("Preview de Cadastro de Produtos")
        self.geometry("1000x600")
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        
        self.itens = itens
        self.config = config
        self.config_db = config_db
        self.classificacao = classificacao
        self.grupos_db = grupos_db
        self.subgrupos_db = subgrupos_db
        self.callback_importar = callback_importar
        self.produtos_para_inserir = []
        
        self._criar_widgets()
        self._preparar_dados()
        
    def _preparar_dados(self):
        emp = int(self.config.get('IMPORTACAO', 'empresa', fallback='1'))
        fil = int(self.config.get('IMPORTACAO', 'filial', fallback='1'))
        
        def task():
            try:
                with FirebirdService(self.config_db) as fb:
                    sql_codigos = "SELECT PRODUTO_CODIGO FROM TABELA_PRODUTO WHERE PRODUTO_EMPRESA = ? AND PRODUTO_FILIAL = ?"
                    existentes = fb.query(sql_codigos, [emp, fil])
                    existentes_codigos = set(str(p.get('produto_codigo', '')) for p in existentes)
                    
                    config_prod = {'empresa': emp, 'filial': fil}
                    
                    for r in self.itens:
                        item = r['xml']
                        acao = r.get('acao_escolhida', 'CADASTRAR NOVO')
                        erp_match = r['validacao'].erp_match or {}
                        
                        novo_dict = DataTransformer.prepare_produto(item, config_prod, self.classificacao)
                        
                        if acao == "ATUALIZAR ERP":
                            novo_dict['PRODUTO_CODIGO'] = erp_match.get('produto_codigo')
                            novo_dict['_ACAO'] = 'UPDATE'
                        else:
                            codigo_final, cod_aux = DataTransformer.prepare_codigo_produto(item.get('c_prod', ''), existentes_codigos)
                            novo_dict['PRODUTO_CODIGO'] = codigo_final
                            novo_dict['PRODUTO_COD_AUXILIAR'] = cod_aux
                            novo_dict['_ACAO'] = 'INSERT'
                            existentes_codigos.add(codigo_final)
                            
                        self.produtos_para_inserir.append(novo_dict)
                        
                self.after(0, self._renderizar_dados)
            except Exception as e:
                self.after(0, lambda e=e: messagebox.showerror("Erro", f"Erro ao preparar dados:\n{e}", parent=self))
                self.after(0, self.destroy)
                
        threading.Thread(target=task, daemon=True).start()

    def _criar_widgets(self):
        self.lbl_titulo = ttk.Label(self, text="Carregando produtos para visualização...", font=("Segoe UI", 12, "bold"))
        self.lbl_titulo.pack(anchor=tk.W, padx=10, pady=10)
        
        frame_edicao = ttk.LabelFrame(self, text="Editar Grupo/Subgrupo do(s) Produto(s) Selecionado(s)", padding="5")
        frame_edicao.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(frame_edicao, text="Grupo:").grid(row=0, column=0, padx=5, sticky=tk.W)
        self.cb_grupo = ttk.Combobox(frame_edicao, width=30, state="readonly")
        self.cb_grupo.grid(row=0, column=1, padx=5)
        self.cb_grupo.bind("<<ComboboxSelected>>", self._on_grupo_selecionado)
        
        ttk.Label(frame_edicao, text="Subgrupo:").grid(row=0, column=2, padx=5, sticky=tk.W)
        self.cb_subgrupo = ttk.Combobox(frame_edicao, width=30, state="readonly")
        self.cb_subgrupo.grid(row=0, column=3, padx=5)
        
        ttk.Button(frame_edicao, text="Aplicar Seleção", command=self._aplicar_grupo_subgrupo).grid(row=0, column=4, padx=10)

        valores_grupo = [f"{g.get('grupo_codigo')} - {g.get('grupo_descricao', '')}" for g in self.grupos_db]
        self.cb_grupo['values'] = valores_grupo

        frame_grid = ttk.Frame(self)
        frame_grid.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        colunas = ("AÇÃO", "CÓDIGO ERP", "DESCRIÇÃO", "NCM", "C. BARRAS", "CEST", "UNID", "GRUPO", "SUBGRUPO")
        self.tree = ttk.Treeview(frame_grid, columns=colunas, show="headings", selectmode="extended")
        
        larguras = [100, 100, 250, 80, 100, 80, 50, 120, 120]
        for col, larg in zip(colunas, larguras):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=larg, anchor=tk.CENTER if col != "DESCRIÇÃO" else tk.W)
            
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        scroll_y = ttk.Scrollbar(frame_grid, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        frame_bot = ttk.Frame(self, padding="10")
        frame_bot.pack(fill=tk.X, side=tk.BOTTOM)
        
        ttk.Button(frame_bot, text="❌ CANCELAR", command=self.destroy).pack(side=tk.LEFT, padx=5)
        self.btn_confirmar = ttk.Button(frame_bot, text="✅ CONFIRMAR E CADASTRAR", command=self._confirmar, state=tk.DISABLED)
        self.btn_confirmar.pack(side=tk.RIGHT, padx=5)
        
    def _renderizar_dados(self):
        for item in self.tree.get_children(): self.tree.delete(item)
        self.lbl_titulo.config(text=f"Produtos que serão processados ({len(self.produtos_para_inserir)} itens):")
        for idx, p in enumerate(self.produtos_para_inserir):
            acao_str = "📝 ATUALIZAR" if p.get('_ACAO') == 'UPDATE' else "✨ NOVO"
            
            grupo_nome = self._get_nome_grupo(p.get('PRODUTO_GRUPO'))
            subgrupo_nome = self._get_nome_subgrupo(p.get('PRODUTO_GRUPO'), p.get('PRODUTO_SUBGRUPO'))

            self.tree.insert("", tk.END, iid=str(idx), values=(
                acao_str,
                p.get('PRODUTO_CODIGO', ''),
                p.get('PRODUTO_DESCRICAO', ''),
                p.get('PRODUTO_CLASS_FISCAL', ''),
                p.get('PRODUTO_CBARRA', ''),
                p.get('PRODUTO_CEST', ''),
                p.get('PRODUTO_UNIDADE_CV', ''),
                grupo_nome,
                subgrupo_nome
            ))
        self.btn_confirmar.config(state=tk.NORMAL)
            
    def _get_nome_grupo(self, grupo_id):
        for g in self.grupos_db:
            if str(g.get('grupo_codigo', '')) == str(grupo_id):
                return f"{g.get('grupo_codigo')} - {g.get('grupo_descricao', '')}"
        return str(grupo_id) if grupo_id else ""

    def _get_nome_subgrupo(self, grupo_id, subgrupo_id):
        for s in self.subgrupos_db:
            if str(s.get('subgrupo_grupo', '')) == str(grupo_id) and str(s.get('subgrupo_codigo', '')) == str(subgrupo_id):
                return f"{s.get('subgrupo_codigo')} - {s.get('subgrupo_descricao', '')}"
        return str(subgrupo_id) if subgrupo_id else ""

    def _on_grupo_selecionado(self, event):
        sel = self.cb_grupo.get()
        if not sel: return
        
        grupo_cod = sel.split('-')[0].strip()
        subgrupos_filtrados = [
            f"{s.get('subgrupo_codigo')} - {s.get('subgrupo_descricao', '')}" 
            for s in self.subgrupos_db if str(s.get('subgrupo_grupo', '')) == grupo_cod
        ]
        self.cb_subgrupo['values'] = subgrupos_filtrados
        self.cb_subgrupo.set('')
        if subgrupos_filtrados:
            self.cb_subgrupo.current(0)

    def _on_tree_select(self, event):
        sel = self.tree.selection()
        if not sel: return
        idx = int(sel[0])
        p = self.produtos_para_inserir[idx]
        
        grupo_nome = self._get_nome_grupo(p.get('PRODUTO_GRUPO'))
        if grupo_nome in self.cb_grupo['values']:
            self.cb_grupo.set(grupo_nome)
            self._on_grupo_selecionado(None)
            subgrupo_nome = self._get_nome_subgrupo(p.get('PRODUTO_GRUPO'), p.get('PRODUTO_SUBGRUPO'))
            if subgrupo_nome in self.cb_subgrupo['values']:
                self.cb_subgrupo.set(subgrupo_nome)
            else:
                self.cb_subgrupo.set('')
        else:
            self.cb_grupo.set('')
            self.cb_subgrupo.set('')

    def _aplicar_grupo_subgrupo(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Selecione um ou mais produtos na lista para aplicar a alteração.", parent=self)
            return
            
        grupo_str = self.cb_grupo.get()
        subgrupo_str = self.cb_subgrupo.get()
        
        grupo_id = grupo_str.split('-')[0].strip() if grupo_str else '1'
        subgrupo_id = subgrupo_str.split('-')[0].strip() if subgrupo_str else '1'
        
        for item_id in sel:
            idx = int(item_id)
            p = self.produtos_para_inserir[idx]
            p['PRODUTO_GRUPO'] = grupo_id
            p['PRODUTO_SUBGRUPO'] = subgrupo_id
            
            valores = list(self.tree.item(item_id, 'values'))
            valores[7] = grupo_str
            valores[8] = subgrupo_str
            self.tree.item(item_id, values=valores)
            
        messagebox.showinfo("Sucesso", "Classificação aplicada aos produtos selecionados.", parent=self)

    def _confirmar(self):
        self.callback_importar(self.produtos_para_inserir)
        self.destroy()

class TelaXmlProdutos(ttk.Frame):
    def __init__(self, parent, callback_voltar=None):
        super().__init__(parent, padding="10")
        self.parent = parent
        self.callback_voltar = callback_voltar
        self.pack(fill=tk.BOTH, expand=True)
        print("✅ Instância de TelaXmlProdutos criada.")

        self.resultados_validacao = []
        self.pasta_xmls = ""
        self.arquivos_selecionados = []
        self.dados_grid = {}
        self.grupos_db = []
        self.subgrupos_db = []
        
        self.colunas = ("SEL", "AÇÃO", "CÓD. XML", "CÓD. ERP", "PRODUTO XML", "PRODUTO ERP", "NCM XML", "NCM ERP", "DIVERGÊNCIAS")
        self._sort_directions = {col: False for col in self.colunas}

        self.config = configparser.ConfigParser()
        self.config.read('config.ini', encoding='utf-8')

        self._criar_widgets()
        self._carregar_config_iniciais()
        self.after(500, self._carregar_grupos_db) # Carrega os grupos 0.5s após abrir a tela

    def _criar_widgets(self):
        # Header
        lbl_title = tk.Label(self, text="AUDITORIA E IMPORTAÇÃO DE PRODUTOS VIA XML", font=("Segoe UI", 14, "bold"), fg="#27AE60")
        lbl_title.pack(anchor=tk.W, pady=(0, 10))

        # Frame Parâmetros
        frame_config = ttk.LabelFrame(self, text="Parâmetros Fiscais", padding="10")
        frame_config.pack(fill=tk.X, pady=5)

        ttk.Label(frame_config, text="Empresa:").grid(row=0, column=0, padx=5)
        self.ent_empresa = ttk.Entry(frame_config, width=8)
        self.ent_empresa.grid(row=0, column=1, padx=5)

        ttk.Label(frame_config, text="Filial:").grid(row=0, column=2, padx=5)
        self.ent_filial = ttk.Entry(frame_config, width=8)
        self.ent_filial.grid(row=0, column=3, padx=5)
        
        ttk.Label(frame_config, text="UF Padrão (ICMS):").grid(row=0, column=4, padx=5)
        self.ent_uf = ttk.Entry(frame_config, width=5)
        self.ent_uf.grid(row=0, column=5, padx=5)
        self.ent_uf.insert(0, "SP")

        # Frame Classificação em Lote (Comboboxes)
        frame_classif = ttk.LabelFrame(self, text="⚙️ Classificação em Lote (Será aplicada aos produtos selecionados)", padding="10")
        frame_classif.pack(fill=tk.X, pady=5)
        
        ttk.Label(frame_classif, text="Tipo:").grid(row=0, column=0, padx=5, sticky=tk.W)
        self.cb_tipo = ttk.Combobox(frame_classif, width=20, state="readonly", values=[
            "1 - Revenda", "2 - Consumo", "3 - Matéria Prima", 
            "4 - Produto Acabado", "5 - Serviços", "6 - Outros"
        ])
        self.cb_tipo.grid(row=0, column=1, padx=5)
        self.cb_tipo.set("4 - Produto Acabado")
        
        ttk.Label(frame_classif, text="Grupo:").grid(row=0, column=2, padx=5, sticky=tk.W)
        self.cb_grupo = ttk.Combobox(frame_classif, width=30, state="readonly")
        self.cb_grupo.grid(row=0, column=3, padx=5)
        self.cb_grupo.bind("<<ComboboxSelected>>", self._on_grupo_selecionado)
        
        ttk.Label(frame_classif, text="Subgrupo:").grid(row=0, column=4, padx=5, sticky=tk.W)
        self.cb_subgrupo = ttk.Combobox(frame_classif, width=30, state="readonly")
        self.cb_subgrupo.grid(row=0, column=5, padx=5)
        
        ttk.Button(frame_classif, text="🔄 Recarregar Grupos", command=self._carregar_grupos_db).grid(row=0, column=6, padx=15)
        
        self.var_producao_sistec = tk.BooleanVar(value=False)
        self.chk_producao_sistec = ttk.Checkbutton(frame_classif, text="Integra Produção Sistec", variable=self.var_producao_sistec)
        self.chk_producao_sistec.grid(row=1, column=0, columnspan=7, sticky=tk.W, padx=5, pady=5)

        # Frame Diretório
        frame_dir = ttk.Frame(self)
        frame_dir.pack(fill=tk.X, pady=10)
        
        ttk.Label(frame_dir, text="Pasta com XMLs:").pack(side=tk.LEFT, padx=5)
        self.ent_pasta = ttk.Entry(frame_dir, width=60)
        self.ent_pasta.pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_dir, text="📁 Pasta", command=self._selecionar_pasta).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_dir, text="📄 Arquivos", command=self._selecionar_arquivos).pack(side=tk.LEFT, padx=2)
        
        self.btn_analisar = ttk.Button(frame_dir, text="🔍 Analisar XMLs", command=self._iniciar_analise)
        self.btn_analisar.pack(side=tk.RIGHT, padx=5)

        # Progresso
        self.progresso = ttk.Progressbar(self, orient=tk.HORIZONTAL, mode='determinate')
        self.progresso.pack(fill=tk.X, pady=5)
        self.lbl_status = ttk.Label(self, text="Aguardando arquivos...", font=("Segoe UI", 9))
        self.lbl_status.pack(anchor=tk.W)

        # Frame Ações Meio (Seleção)
        frame_meio = ttk.Frame(self)
        frame_meio.pack(fill=tk.X, pady=5)
        
        ttk.Button(frame_meio, text="☑ Marcar Novos", command=self._marcar_novos).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_meio, text="☐ Desmarcar Todos", command=self._desmarcar_todos).pack(side=tk.LEFT, padx=5)

        ttk.Label(frame_meio, text="💡 DICA: Clique na coluna 'AÇÃO' de um produto para alternar entre CADASTRAR NOVO, ATUALIZAR ERP ou IGNORAR.", foreground="#003399", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=15)

        # Treeview (Grade de Resultados)
        frame_grade = ttk.Frame(self)
        frame_grade.pack(fill=tk.BOTH, expand=True, pady=10)

        self.tree = ttk.Treeview(frame_grade, columns=self.colunas, show="headings")
        
        larguras = [40, 120, 80, 80, 200, 200, 80, 80, 150]
        for col, larg in zip(self.colunas, larguras):
            self.tree.heading(col, text=col + " ↕", command=lambda c=col: self._sort_treeview(c))
            anchor = tk.W if col in ["PRODUTO XML", "PRODUTO ERP", "DIVERGÊNCIAS"] else tk.CENTER
            self.tree.column(col, width=larg, anchor=anchor)

        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)

        # Estilos das tags
        self.tree.tag_configure('VALIDADO', background='#EAFAF1') # Verde claro
        self.tree.tag_configure('DIVERGENTE', background='#FEF9E7') # Amarelo/Laranja claro
        self.tree.tag_configure('NAO_ENCONTRADO', background='#FADBD8') # Vermelho claro

        scroll_y = ttk.Scrollbar(frame_grade, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        # Ações de Rodapé
        frame_fim = ttk.Frame(self)
        frame_fim.pack(fill=tk.X, pady=10)

        ttk.Button(frame_fim, text="⬅ VOLTAR", command=self._fechar_tela).pack(side=tk.LEFT, padx=5)
        
        self.btn_relatorio = ttk.Button(frame_fim, text="📊 Gerar CSV de Auditoria", state=tk.DISABLED, command=self._gerar_relatorio)
        self.btn_relatorio.pack(side=tk.RIGHT, padx=5)

        self.btn_importar = ttk.Button(frame_fim, text="🚀 Processar Produtos Selecionados", state=tk.DISABLED, command=self._iniciar_importacao)
        self.btn_importar.pack(side=tk.RIGHT, padx=5)

    def _carregar_config_iniciais(self):
        self.config.read('config.ini', encoding='utf-8')
        empresa = self.config.get('IMPORTACAO', 'empresa', fallback='1')
        filial = self.config.get('IMPORTACAO', 'filial', fallback='1')
        uf = self.config.get('IMPORTACAO', 'uf', fallback='SP')
        
        self.ent_empresa.config(state=tk.NORMAL)
        self.ent_empresa.delete(0, tk.END)
        self.ent_empresa.insert(0, empresa)
        self.ent_empresa.config(state='readonly')
        
        self.ent_filial.config(state=tk.NORMAL)
        self.ent_filial.delete(0, tk.END)
        self.ent_filial.insert(0, filial)
        self.ent_filial.config(state='readonly')
        
        self.ent_uf.config(state=tk.NORMAL)
        self.ent_uf.delete(0, tk.END)
        self.ent_uf.insert(0, uf)
        self.ent_uf.config(state='readonly')

    def _carregar_grupos_db(self):
        """Busca Grupos e Subgrupos do Firebird"""
        config_db = {
            'host': self.config.get('FIREBIRD', 'servidor', fallback='127.0.0.1'),
            'port': self.config.get('FIREBIRD', 'porta', fallback='3050'),
            'database': self.config.get('FIREBIRD', 'caminho_banco', fallback=''),
            'user': self.config.get('FIREBIRD', 'usuario', fallback='SYSDBA'),
            'password': self.config.get('FIREBIRD', 'senha', fallback='masterkey'),
            'fbclient': self.config.get('FIREBIRD', 'fbclient', fallback='')
        }
        emp = int(self.ent_empresa.get() or 1)
        fil = int(self.ent_filial.get() or 1)
        
        try:
            with FirebirdService(config_db) as fb:
                # Query de Grupos
                self.grupos_db = fb.query("SELECT GRUPO_CODIGO, GRUPO_DESCRICAO FROM TABELA_GRUPO WHERE GRUPO_EMPRESA = ? AND GRUPO_FILIAL = ?", [emp, fil])
                
                # Query de Subgrupos
                self.subgrupos_db = fb.query("SELECT SUBGRUPO_CODIGO, SUBGRUPO_DESCRICAO, SUBGRUPO_GRUPO FROM TABELA_SUBGRUPO WHERE SUBGRUPO_EMPRESA = ? AND SUBGRUPO_FILIAL = ?", [emp, fil])
                
            # Popula Combobox de Grupo
            valores_grupo = [f"{g.get('grupo_codigo')} - {g.get('grupo_descricao', '')}" for g in self.grupos_db]
            self.cb_grupo['values'] = valores_grupo
            if valores_grupo:
                self.cb_grupo.current(0)
                self._on_grupo_selecionado(None) # Força popular os subgrupos
        except Exception as e:
            print(f"Aviso: Não foi possível carregar grupos do ERP. O banco pode estar vazio ou a estrutura é diferente. {e}")

    def _on_grupo_selecionado(self, event):
        sel = self.cb_grupo.get()
        if not sel: return
        
        grupo_cod = sel.split('-')[0].strip()
        subgrupos_filtrados = [
            f"{s.get('subgrupo_codigo')} - {s.get('subgrupo_descricao', '')}" 
            for s in self.subgrupos_db if str(s.get('subgrupo_grupo', '')) == grupo_cod
        ]
        self.cb_subgrupo['values'] = subgrupos_filtrados
        self.cb_subgrupo.set('')
        if subgrupos_filtrados:
            self.cb_subgrupo.current(0)

    def _selecionar_pasta(self):
        pasta = filedialog.askdirectory(title="Selecione a pasta com os XMLs de NF-e")
        if pasta:
            self.ent_pasta.delete(0, tk.END)
            self.ent_pasta.insert(0, pasta)
            self.pasta_xmls = pasta
            self.arquivos_selecionados = []

    def _selecionar_arquivos(self):
        arquivos = filedialog.askopenfilenames(title="Selecione os arquivos XML de NF-e", filetypes=[("XML", "*.xml")])
        if arquivos:
            self.ent_pasta.delete(0, tk.END)
            self.ent_pasta.insert(0, f"{len(arquivos)} arquivo(s) selecionado(s)")
            self.arquivos_selecionados = list(arquivos)
            self.pasta_xmls = ""

    def _fechar_tela(self):
        self.destroy()
        if self.callback_voltar:
            self.callback_voltar()

    def _on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            item_id = self.tree.identify_row(event.y)
            if not item_id: return
            
            valores = list(self.tree.item(item_id, 'values'))
            if valores[0] == '-': return
            
            if column == "#1": # Coluna SEL
                valores[0] = '☑' if valores[0] == '☐' else '☐'
                if valores[0] == '☐':
                    valores[1] = 'IGNORAR'
                else:
                    if valores[3] != '-':
                        valores[1] = 'ATUALIZAR ERP'
                    else:
                        valores[1] = 'CADASTRAR NOVO'
                self.tree.item(item_id, values=valores)
                
            elif column == "#2": # Coluna AÇÃO
                if valores[3] != '-': # Tem CÓD. ERP
                    acoes = ["ATUALIZAR ERP", "IGNORAR", "CADASTRAR NOVO"]
                else:
                    acoes = ["CADASTRAR NOVO", "IGNORAR"]
                
                try:
                    idx = acoes.index(valores[1])
                    valores[1] = acoes[(idx + 1) % len(acoes)]
                except ValueError:
                    valores[1] = acoes[0]
                    
                if valores[1] != "IGNORAR":
                    valores[0] = '☑'
                else:
                    valores[0] = '☐'
                    
                self.tree.item(item_id, values=valores)

    def _marcar_novos(self):
        for item in self.tree.get_children():
            valores = list(self.tree.item(item, "values"))
            if valores[0] != '-':
                if valores[3] == '-': # Não tem código ERP
                    valores[0] = "☑"
                    valores[1] = "CADASTRAR NOVO"
                    self.tree.item(item, values=valores)

    def _desmarcar_todos(self):
        for item in self.tree.get_children():
            valores = list(self.tree.item(item, "values"))
            if valores[0] != '-':
                valores[0] = "☐"
                valores[1] = "IGNORAR"
                self.tree.item(item, values=valores)

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
            self.tree.heading(c, text=c + arrow, command=lambda x=c: self._sort_treeview(x))

    def _iniciar_analise(self):
        if not self.pasta_xmls and not self.arquivos_selecionados:
            messagebox.showwarning("Atenção", "Selecione uma pasta ou arquivos XML válidos.")
            return
            
        self.btn_analisar.config(state=tk.DISABLED)
        self.btn_relatorio.config(state=tk.DISABLED)
        self.progresso['value'] = 0
        self.lbl_status.config(text="Lendo arquivos XML e carregando dados do ERP...")
        
        # Limpa a grid
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        self.resultados_validacao = []

        # Inicia Thread (O famoso Main Pipeline / Orquestrador)
        threading.Thread(target=self._pipeline_auditoria_bg, daemon=True).start()

    def _pipeline_auditoria_bg(self):
        """Este é o PIPELINE (Comando 07) rodando em background conectado na Interface."""
        try:
            emp = self.ent_empresa.get()
            fil = self.ent_filial.get()
            uf_dest = self.ent_uf.get()
            
            # 1. Conectar e buscar dados do ERP usando FirebirdService
            # (Lembrar que o FirebirdService usa chaves em letras minúsculas por padrão)
            config_db = {
                'host': self.config.get('FIREBIRD', 'servidor', fallback='127.0.0.1'),
                'port': self.config.get('FIREBIRD', 'porta', fallback='3050'),
                'database': self.config.get('FIREBIRD', 'caminho_banco', fallback=''),
                'user': self.config.get('FIREBIRD', 'usuario', fallback='SYSDBA'),
                'password': self.config.get('FIREBIRD', 'senha', fallback='masterkey'),
                'fbclient': self.config.get('FIREBIRD', 'fbclient', fallback='')
            }
            
            with FirebirdService(config_db) as fb:
                # Busca Produtos
                sql_produtos = "SELECT PRODUTO_CODIGO, PRODUTO_COD_AUXILIAR, PRODUTO_DESCRICAO, PRODUTO_CLASS_FISCAL, PRODUTO_CBARRA, PRODUTO_ICMS, PRODUTO_UNIDADE_CV FROM TABELA_PRODUTO WHERE PRODUTO_EMPRESA = ? AND PRODUTO_FILIAL = ?"
                erp_produtos = fb.query(sql_produtos, [emp, fil])
                
                # Limpar espaços em branco à direita (comuns em colunas CHAR do Firebird) para evitar falsas divergências
                for p in erp_produtos:
                    for k, v in p.items():
                        if isinstance(v, str):
                            p[k] = v.strip()
                            
                # Busca Regras ICMS
                sql_icms = "SELECT AICMS_FAIXA, AICMS_ESTADO, AICMS_SITUACAO_CONT, AICMS_ALIQUOTA_CONT, AICMS_REDUCAO_CONT, AICMS_CBENEF_CONT, AICMS_SITUACAO_NCONT, AICMS_ALIQUOTA_NCONT, AICMS_REDUCAO_NCONT, AICMS_CBENEF_NCONT, AICMS_DATA FROM TABELA_ALIQUOTA_ICMS WHERE AICMS_EMPRESA = ? AND AICMS_FILIAL = ?"
                regras_icms = fb.query(sql_icms, [emp, fil])
                
                for r in regras_icms:
                    for k, v in r.items():
                        if isinstance(v, str):
                            r[k] = v.strip()
                
                # Busca CFOPs
                sql_cfops = "SELECT NAT_CODIGO FROM TABELA_NAT_OPERACAO_SAIDA WHERE NAT_EMPRESA = ? AND NAT_FILIAL = ?"
                cfops_erp = fb.query(sql_cfops, [emp, fil])
                
            # 2. Ler todos os itens dos XMLs
            self.parent.after(0, lambda: self.lbl_status.config(text="Analisando notas fiscais (Parsing XML)..."))
            
            if self.arquivos_selecionados:
                itens_xml = []
                for arq in self.arquivos_selecionados:
                    try:
                        nfe_data = parse_nfe(arq)
                        for item in nfe_data['itens']:
                            item['chave_nfe'] = nfe_data['chave_nfe']
                            item['inf_cpl'] = nfe_data['inf_cpl']
                            itens_xml.append(item)
                    except Exception as e:
                        print(f"Erro ao ler {arq}: {e}")
                    except Exception:
                        pass
            else:
                itens_xml = parse_nfe_folder(self.pasta_xmls)
            
            if not itens_xml:
                self.parent.after(0, lambda: messagebox.showinfo("Aviso", "Nenhum produto/item encontrado nos arquivos XML válidos."))
                self.parent.after(0, self._finalizar_pipeline)
                return
                
            # Remover itens duplicados pelo código do produto
            mapa_produtos_xml = {}
            for item in itens_xml:
                ncm_raw = str(item.get('ncm') or item.get('NCM') or '').replace('.', '').strip()
                if len(ncm_raw) == 8:
                    ncm_fmt = f"{ncm_raw[:4]}.{ncm_raw[4:6]}.{ncm_raw[6:]}"
                    item['ncm'] = ncm_fmt
                    if 'NCM' in item:
                        item['NCM'] = ncm_fmt
                    
                c_prod = str(item.get('c_prod') or item.get('cProd') or '').strip()
                if c_prod and c_prod not in mapa_produtos_xml:
                    mapa_produtos_xml[c_prod] = item
                    
            lista_unicos_xml = list(mapa_produtos_xml.values())
                
            # 3. Instanciar o Validador
            validador = ValidatorFiscal(erp_produtos, regras_icms, [], cfops_erp, [])
            
            total = len(lista_unicos_xml)
            for i, item in enumerate(lista_unicos_xml):
                # 4. Valida cada item
                result = validador.validate(item, uf_dest)
                
                self.resultados_validacao.append({
                    'xml': item,
                    'validacao': result
                })
                
                # Atualiza interface a cada lote
                if i % 50 == 0 or i == total - 1:
                    percent = ((i + 1) / total) * 100
                    self.parent.after(0, self._atualizar_progresso, percent, f"Validando {i+1}/{total} itens fiscais...")
            
            # Conclui
            self.parent.after(0, self._renderizar_resultados)
            
        except Exception as e:
            self.parent.after(0, lambda: messagebox.showerror("Erro de Processamento", f"Falha ao executar auditoria:\n{e}"))
            self.parent.after(0, self._finalizar_pipeline)

    def _atualizar_progresso(self, valor, texto):
        self.progresso['value'] = valor
        self.lbl_status.config(text=texto)

    def _renderizar_resultados(self):
        self.dados_grid.clear()
        self.lbl_status.config(text="Renderizando resultados na tabela...")
        self.btn_analisar.config(state=tk.DISABLED)
        
        chunk_size = 200
        total = len(self.resultados_validacao)
        
        def render_chunk(start_idx):
            end_idx = min(start_idx + chunk_size, total)
            for i in range(start_idx, end_idx):
                r = self.resultados_validacao[i]
                xml = r['xml']
                val = r['validacao']
                erp = val.erp_match or {}
                
                # Prepara visualização
                status = val.status
                divs = " | ".join(val.divergencias) if val.divergencias else "OK"
                
                acao = "IGNORAR"
                if status == 'NAO_ENCONTRADO':
                    divs = "Produto não existe no ERP"
                    sel = "☑"
                    acao = "CADASTRAR NOVO"
                elif status == 'DIVERGENTE':
                    sel = "☐"
                    acao = "ATUALIZAR ERP"
                else:
                    sel = "☐"
                    acao = "IGNORAR"
                    
                item_id = self.tree.insert("", tk.END, values=(
                    sel,
                    acao,
                    xml.get('c_prod', ''),
                    erp.get('produto_codigo', '-'),
                    xml.get('x_prod', ''),
                    erp.get('produto_descricao', '-'),
                    xml.get('ncm', ''),
                    erp.get('produto_class_fiscal', '-'),
                    divs
                ), tags=(status,))
                
                self.dados_grid[item_id] = r
                
            if end_idx < total:
                self.progresso['value'] = (end_idx / total) * 100
                self.lbl_status.config(text=f"Renderizando {end_idx}/{total} itens na tabela...")
                self.parent.after(10, render_chunk, end_idx)
            else:
                self.btn_relatorio.config(state=tk.NORMAL)
                
                if total > 0:
                    self.btn_importar.config(state=tk.NORMAL)
                    
                self._finalizar_pipeline()
                messagebox.showinfo("Concluído", "Auditoria de produtos finalizada com sucesso!")

        # Inicia a renderização em pedaços para não travar a tela
        if total > 0:
            render_chunk(0)
        else:
            self._finalizar_pipeline()

    def _finalizar_pipeline(self):
        self.btn_analisar.config(state=tk.NORMAL)
        self.lbl_status.config(text=f"Pronto. {len(self.resultados_validacao)} itens analisados.")

    def _gerar_relatorio(self):
        caminho = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="Auditoria_Fiscal_Produtos.csv", filetypes=[("CSV", "*.csv")])
        if caminho:
            try:
                generate_audit_report(self.resultados_validacao, caminho)
                messagebox.showinfo("Relatório Salvo", f"Auditoria exportada para:\n{caminho}")
            except Exception as e:
                messagebox.showerror("Erro", f"Falha ao salvar CSV:\n{e}")

    def _iniciar_importacao(self):
        selecionados = []
        for item_id in self.tree.get_children():
            valores = self.tree.item(item_id, "values")
            if valores[0] == "☑":
                dados = self.dados_grid[item_id]
                dados['acao_escolhida'] = valores[1]
                selecionados.append(dados)
                
        if not selecionados:
            messagebox.showwarning("Aviso", "Selecione pelo menos um produto para processar (marcados com ☑).")
            return
            
        # Extrai os IDs da Classificação escolhida
        tipo_selecionado = self.cb_tipo.get()
        grupo_selecionado = self.cb_grupo.get()
        subgrupo_selecionado = self.cb_subgrupo.get()
        
        grupo_id = 1
        subgrupo_id = 1
        if grupo_selecionado:
            grupo_id = int(grupo_selecionado.split('-')[0].strip())
        if subgrupo_selecionado:
            subgrupo_id = int(subgrupo_selecionado.split('-')[0].strip())
            
        classificacao = {
            'tipo': tipo_selecionado,
            'grupo_id': grupo_id,
            'subgrupo_id': subgrupo_id,
            'producao_sistec': 'S' if self.var_producao_sistec.get() else None
        }
        
        config_db = {
            'host': self.config.get('FIREBIRD', 'servidor', fallback='127.0.0.1'),
            'port': self.config.get('FIREBIRD', 'porta', fallback='3050'),
            'database': self.config.get('FIREBIRD', 'caminho_banco', fallback=''),
            'user': self.config.get('FIREBIRD', 'usuario', fallback='SYSDBA'),
            'password': self.config.get('FIREBIRD', 'senha', fallback='masterkey'),
            'fbclient': self.config.get('FIREBIRD', 'fbclient', fallback='')
        }
        
        ModalPreviewProdutos(self.parent, selecionados, self.config, config_db, classificacao, self.grupos_db, self.subgrupos_db, self._executar_importacao)

    def _executar_importacao(self, produtos_para_inserir):
        self.btn_importar.config(state=tk.DISABLED)
        self.btn_relatorio.config(state=tk.DISABLED)
        self.btn_analisar.config(state=tk.DISABLED)
        self.lbl_status.config(text="Processando produtos...")
        
        threading.Thread(target=self._importar_produtos_bg, args=(produtos_para_inserir,), daemon=True).start()

    def _importar_produtos_bg(self, produtos_para_inserir):
        try:
            emp = int(self.ent_empresa.get())
            fil = int(self.ent_filial.get())
            
            config_db = {
                'host': self.config.get('FIREBIRD', 'servidor', fallback='127.0.0.1'),
                'port': self.config.get('FIREBIRD', 'porta', fallback='3050'),
                'database': self.config.get('FIREBIRD', 'caminho_banco', fallback=''),
                'user': self.config.get('FIREBIRD', 'usuario', fallback='SYSDBA'),
                'password': self.config.get('FIREBIRD', 'senha', fallback='masterkey'),
                'fbclient': self.config.get('FIREBIRD', 'fbclient', fallback='')
            }
            
            with FirebirdService(config_db) as fb:
                cursor = fb.conn.cursor() if hasattr(fb, 'conn') else None
                self.parent.after(0, lambda: self.lbl_status.config(text=f"Processando {len(produtos_para_inserir)} produtos no Firebird..."))
                
                inserts = [p for p in produtos_para_inserir if p.get('_ACAO') == 'INSERT']
                updates = [p for p in produtos_para_inserir if p.get('_ACAO') == 'UPDATE']
                
                importer = FirebirdImporter(fb)
                res_imp = importer.import_produtos(inserts) if inserts else {'inseridos': 0, 'erros': []}
                
                inseridos = res_imp.get('inseridos', 0)
                erros = res_imp.get('erros', [])
                
                atualizados = 0
                for p in updates:
                    try:
                        sql_up = "UPDATE TABELA_PRODUTO SET PRODUTO_DESCRICAO = ?, PRODUTO_CLASS_FISCAL = ?, PRODUTO_CBARRA = ?, PRODUTO_CEST = ?, PRODUTO_UNIDADE_CV = ?, PRODUTO_PRODUCAO_SISTEC = ? WHERE PRODUTO_EMPRESA = ? AND PRODUTO_FILIAL = ? AND PRODUTO_CODIGO = ?"
                        params_up = [p.get('PRODUTO_DESCRICAO', '')[:200], p.get('PRODUTO_CLASS_FISCAL', '')[:8], p.get('PRODUTO_CBARRA', '')[:14], p.get('PRODUTO_CEST', '')[:7], p.get('PRODUTO_UNIDADE_CV', '')[:2], p.get('PRODUTO_PRODUCAO_SISTEC'), emp, fil, p.get('PRODUTO_CODIGO')]
                        if cursor: cursor.execute(sql_up, params_up)
                        else: fb.execute(sql_up, params_up)
                        
                        # Inserir também a unidade na TABELA_PRODUTO_UNIDADE
                        unidade_cod = p.get('_UNIDADE_CODIGO', 2)
                        sql_unid = """
                            UPDATE OR INSERT INTO TABELA_PRODUTO_UNIDADE 
                            (TPU_PROD_EMPRESA, TPU_PROD_FILIAL, TPU_PRODUTO, TPU_COD_UNIDADE, TPU_UNIDADE_PADRAO)
                            VALUES (?, ?, ?, ?, 'S')
                            MATCHING (TPU_PROD_EMPRESA, TPU_PROD_FILIAL, TPU_PRODUTO, TPU_COD_UNIDADE)
                        """
                        if cursor: cursor.execute(sql_unid, [emp, fil, p.get('PRODUTO_CODIGO'), unidade_cod])
                        else: fb.execute(sql_unid, [emp, fil, p.get('PRODUTO_CODIGO'), unidade_cod])
                        
                        atualizados += 1
                    except Exception as e_up:
                        erros.append({'produto': p, 'detalhe': f"Erro no UPDATE: {e_up}"})
                        
                if cursor: fb.conn.commit()
                
            msg = f"Processamento finalizado!\n\n{inseridos} novos produtos cadastrados.\n{atualizados} produtos atualizados no ERP."
            
            if erros:
                msg += f"\n\nOcorreram {len(erros)} erro(s) durante a importação."
                
            self.parent.after(0, lambda m=msg: messagebox.showinfo("Importação Concluída", m))
            
            if erros:
                log_erros_str = "--- LOG DE ERROS NO PROCESSAMENTO DE PRODUTOS ---\n\n"
                for erro in erros:
                    if 'produto' in erro:
                        cod_prod = erro.get('produto', {}).get('PRODUTO_CODIGO', 'N/A')
                        desc_prod = erro.get('produto', {}).get('PRODUTO_DESCRICAO', 'N/A')
                        acao_prod = erro.get('produto', {}).get('_ACAO', 'N/A')
                        detalhe_erro = erro.get('detalhe', str(erro))
                        log_erros_str += f"[{acao_prod}] Produto Cód: {cod_prod} ({desc_prod})\n--> Erro: {detalhe_erro}\n\n"
                    else:
                        detalhe_erro = erro.get('erro', str(erro))
                        log_erros_str += f"[INSERT] Erro no Banco de Dados:\n--> {detalhe_erro}\n\n"

                resp = messagebox.askyesno(
                    "Log de Erros", 
                    "Foram encontrados erros durante o processamento. Deseja salvar um arquivo de log com os detalhes?", 
                    parent=self.parent
                )
                if resp:
                    caminho_log = filedialog.asksaveasfilename(
                        defaultextension=".txt", 
                        initialfile="LOG_ERROS_PRODUTOS.txt", 
                        filetypes=[("Arquivos de Texto", "*.txt")],
                        parent=self.parent
                    )
                    if caminho_log:
                        try:
                            with open(caminho_log, 'w', encoding='utf-8') as f:
                                f.write(log_erros_str)
                            messagebox.showinfo("Log Salvo", f"Arquivo de log salvo em:\n{caminho_log}", parent=self.parent)
                        except Exception as e:
                            messagebox.showerror("Erro ao Salvar", f"Não foi possível salvar o log:\n{e}", parent=self.parent)

            # Atualiza e recarrega a auditoria instantaneamente
            self.parent.after(0, self._iniciar_analise)
            
        except Exception as e:
            self.parent.after(0, lambda err=e: messagebox.showerror("Erro no Processamento", f"Falha ao cadastrar/atualizar produtos:\n{err}"))
        finally:
            self.parent.after(0, lambda: self.btn_importar.config(state=tk.NORMAL))
            self.parent.after(0, lambda: self.btn_relatorio.config(state=tk.NORMAL))
            self.parent.after(0, lambda: self.btn_analisar.config(state=tk.NORMAL))
            self.parent.after(0, lambda: self.lbl_status.config(text="Pronto."))
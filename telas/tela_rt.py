import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import configparser
import threading
import os
import sys

from utils.firebird_service import FirebirdService
from utils.xml_reader import parse_nfe_folder, parse_nfe
from utils.importer import FirebirdImporter

REGRAS_RT_MAP = {
    "000001": {"descricao": "Situações tributadas integralmente pelo IBS e CBS", "red_ibs": "0%", "red_cbs": "0%", "regra": "Tributação Integral"},
    "000002": {"descricao": "Exploração de via", "red_ibs": "0%", "red_cbs": "0%", "regra": "Tributação Integral"},
    "000003": {"descricao": "Regime automotivo - projetos incentivados (art. 311)", "red_ibs": "0%", "red_cbs": "0%", "regra": "Tributação Integral"},
    "000004": {"descricao": "Regime automotivo - projetos incentivados (art. 312)", "red_ibs": "0%", "red_cbs": "0%", "regra": "Tributação Integral"},
    "000005": {"descricao": "Operação com EAC (biocombustível)", "red_ibs": "0%", "red_cbs": "0%", "regra": "Tributação Integral"},
    "010001": {"descricao": "Operações do FGTS (fora CEF)", "red_ibs": "0%", "red_cbs": "0%", "regra": "Tributação Integral"},
    "010002": {"descricao": "Operações do serviço financeiro", "red_ibs": "0%", "red_cbs": "0%", "regra": "Tributação Integral"},
    "110001": {"descricao": "Planos de assistência funerária", "red_ibs": "60%", "red_cbs": "60%", "regra": "Redução de Alíquota"},
    "110002": {"descricao": "Planos de assistência à saúde", "red_ibs": "60%", "red_cbs": "60%", "regra": "Redução de Alíquota"},
    "110003": {"descricao": "Intermediação de planos de saúde", "red_ibs": "60%", "red_cbs": "60%", "regra": "Redução de Alíquota"},
    "110005": {"descricao": "Saúde de animais domésticos", "red_ibs": "30%", "red_cbs": "30%", "regra": "Redução de Alíquota"},
    "200001": {"descricao": "Transporte de bens ZPE / Exportação", "red_ibs": "100%", "red_cbs": "100%", "regra": "Isenção (Redução 100%)"},
    "200003": {"descricao": "Vendas de produtos alimentação humana (Anexo I)", "red_ibs": "100%", "red_cbs": "100%", "regra": "Isenção (Redução 100%)"},
    "200004": {"descricao": "Dispositivos médicos (Anexo XII)", "red_ibs": "100%", "red_cbs": "100%", "regra": "Isenção (Redução 100%)"},
    "200009": {"descricao": "Medicamentos registrados na Anvisa", "red_ibs": "100%", "red_cbs": "100%", "regra": "Isenção (Redução 100%)"},
    "200013": {"descricao": "Absorventes higiênicos", "red_ibs": "100%", "red_cbs": "100%", "regra": "Isenção (Redução 100%)"},
    "200014": {"descricao": "Hortícolas, frutas e ovos (Anexo XV)", "red_ibs": "100%", "red_cbs": "100%", "regra": "Isenção (Redução 100%)"},
    "200025": {"descricao": "Serviços de educação (Prouni)", "red_ibs": "60%", "red_cbs": "100%", "regra": "Redução Mista"},
    "200026": {"descricao": "Locação de imóveis (zonas reabilitadas)", "red_ibs": "80%", "red_cbs": "80%", "regra": "Redução de Alíquota"},
    "200027": {"descricao": "Locação e arrendamento de imóveis", "red_ibs": "70%", "red_cbs": "70%", "regra": "Redução de Alíquota"},
    "200028": {"descricao": "Serviços de educação (Anexo II)", "red_ibs": "60%", "red_cbs": "60%", "regra": "Redução de Alíquota"},
    "200029": {"descricao": "Serviços de saúde humana (Anexo III)", "red_ibs": "60%", "red_cbs": "60%", "regra": "Redução de Alíquota"},
    "200034": {"descricao": "Alimentos para consumo humano (Anexo VII)", "red_ibs": "60%", "red_cbs": "60%", "regra": "Redução de Alíquota"},
    "200041": {"descricao": "Insumos agropecuários (Anexo VIII)", "red_ibs": "60%", "red_cbs": "60%", "regra": "Redução de Alíquota"},
    "200044": {"descricao": "Produtos de higiene pessoal (Anexo IX)", "red_ibs": "60%", "red_cbs": "60%", "regra": "Redução de Alíquota"},
    "200048": {"descricao": "Insumos aquícolas (Anexo X)", "red_ibs": "60%", "red_cbs": "60%", "regra": "Redução de Alíquota"}
}

class DialogoExportarRt(tk.Toplevel):
    def __init__(self, parent, itens, fb_config, callback_sucesso):
        super().__init__(parent)
        self.title("Definir Regras da Reforma Tributária (ERP)")
        self.transient(parent)
        self.grab_set()
        
        largura = int(self.winfo_screenwidth() * 0.95)
        altura = int(self.winfo_screenheight() * 0.85)
        x = int((self.winfo_screenwidth() - largura) / 2)
        y = int((self.winfo_screenheight() - altura) / 2)
        self.geometry(f"{largura}x{altura}+{x}+{y}")
            
        icon_path = self.resource_path("icon.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)
        
        self.itens = itens
        self.fb_config = fb_config
        self.callback_sucesso = callback_sucesso
        self.inputs = {}
        
        self._criar_widgets()
        self._carregar_config_iniciais()
        
    def resource_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)
        
    def _criar_widgets(self):
        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        frame_left = ttk.Frame(main_pane)
        main_pane.add(frame_left, weight=6)
        
        frame_right = ttk.Frame(main_pane)
        main_pane.add(frame_right, weight=5)

        # Footer
        frame_bot = ttk.Frame(frame_left, padding="10")
        frame_bot.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Button(frame_bot, text="❌ Cancelar", command=self.destroy).pack(side=tk.LEFT)
        ttk.Button(frame_bot, text="💾 Gravar no Firebird", command=self._confirmar).pack(side=tk.RIGHT)

        # Tabela Editável
        frame_mid = ttk.LabelFrame(frame_left, text="Regras de Reforma Tributária para Inserir", padding="5")
        frame_mid.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        canvas = tk.Canvas(frame_mid)
        scrollbar = ttk.Scrollbar(frame_mid, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        headers = ["ID Regra *", "Cód. Classe *", "CST *", "% IBS", "% CBS"]
        for i, h in enumerate(headers):
            ttk.Label(scrollable_frame, text=h, font=("Segoe UI", 9, "bold")).grid(row=0, column=i, padx=5, pady=5)
            
        for row_idx, item in enumerate(self.itens, start=1):
            self.inputs[item['id']] = {}
            
            # ID Sugerido
            id_sugerido = str(item.get('c_class_trib') or '').strip().lstrip('0')
            if not id_sugerido:
                import random
                id_sugerido = str(random.randint(1000, 9999))
                
            ent_id = ttk.Entry(scrollable_frame, width=12, font=("Segoe UI", 9, "bold"))
            ent_id.insert(0, id_sugerido)
            ent_id.grid(row=row_idx, column=0, padx=5, pady=2)
            self.inputs[item['id']]['id'] = ent_id
            
            ent_class = ttk.Entry(scrollable_frame, width=15, font=("Segoe UI", 9, "bold"))
            ent_class.insert(0, str(item.get('c_class_trib') or '').strip())
            ent_class.grid(row=row_idx, column=1, padx=5, pady=2)
            self.inputs[item['id']]['class'] = ent_class
            
            ent_cst = ttk.Entry(scrollable_frame, width=8, font=("Segoe UI", 9, "bold"))
            ent_cst.insert(0, str(item.get('ibscbs_cst') or '').strip())
            ent_cst.grid(row=row_idx, column=2, padx=5, pady=2)
            self.inputs[item['id']]['cst'] = ent_cst
            
            ent_ibs = ttk.Entry(scrollable_frame, width=8)
            ent_ibs.insert(0, str(item.get('p_ibs_uf') or '0.0'))
            ent_ibs.grid(row=row_idx, column=3, padx=5, pady=2)
            self.inputs[item['id']]['ibs'] = ent_ibs
            
            ent_cbs = ttk.Entry(scrollable_frame, width=8)
            ent_cbs.insert(0, str(item.get('p_cbs') or '0.0'))
            ent_cbs.grid(row=row_idx, column=4, padx=5, pady=2)
            self.inputs[item['id']]['cbs'] = ent_cbs

        # --- LADO DIREITO (Consulta ERP) ---
        frame_right_top = ttk.Frame(frame_right, padding="5")
        frame_right_top.pack(fill=tk.X)
        
        ttk.Label(frame_right_top, text="Regras RT Existentes no ERP", font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
        ttk.Button(frame_right_top, text="🔄 Atualizar Consulta", command=self._carregar_regras_existentes).pack(side=tk.RIGHT)
        
        frame_grid_ext = ttk.Frame(frame_right)
        frame_grid_ext.pack(fill=tk.BOTH, expand=True, pady=5)

        colunas_ext = ("ID", "CÓD. CLASSE", "CST", "% IBS", "% CBS")
        self.tree_ext = ttk.Treeview(frame_grid_ext, columns=colunas_ext, show="headings")
        self._sort_directions_ext = {col: False for col in colunas_ext}
        
        larguras_ext = [80, 100, 80, 80, 80]
        for col, larg in zip(colunas_ext, larguras_ext):
            self.tree_ext.heading(col, text=col + " ↕", command=lambda c=col: self._sort_treeview_ext(c))
            self.tree_ext.column(col, width=larg, anchor=tk.CENTER)
            
        scroll_y_ext = ttk.Scrollbar(frame_grid_ext, orient=tk.VERTICAL, command=self.tree_ext.yview)
        self.tree_ext.configure(yscroll=scroll_y_ext.set)
        
        self.tree_ext.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y_ext.pack(side=tk.RIGHT, fill=tk.Y)

    def _carregar_config_iniciais(self):
        self._carregar_regras_existentes()

    def _sort_treeview_ext(self, col):
        self._sort_directions_ext[col] = not self._sort_directions_ext[col]
        reverse = self._sort_directions_ext[col]
        
        l = [(self.tree_ext.set(k, col), k) for k in self.tree_ext.get_children('')]
        
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
            self.tree_ext.move(k, '', index)
            
        for c in self._sort_directions_ext:
            if c == col:
                arrow = " ▼" if self._sort_directions_ext[c] else " ▲"
            else:
                arrow = " ↕"
            self.tree_ext.heading(c, text=c + arrow, command=lambda x=c: self._sort_treeview_ext(x))

    def _carregar_regras_existentes(self):
        for item in self.tree_ext.get_children():
            self.tree_ext.delete(item)
            
        sql = "SELECT TRT_ID, TRT_CLASS_TRIB_ID, TRT_CST, TRT_ALIQ_IBS_ESTADUAL, TRT_ALIQ_CBS FROM TABELA_RT_CONFIG_2025_2026 ORDER BY TRT_ID"
        
        try:
            with FirebirdService(self.fb_config) as fb:
                resultados = fb.query(sql)
                
            for r in resultados:
                self.tree_ext.insert("", tk.END, values=(
                    r.get('trt_id', ''),
                    r.get('trt_class_trib_id', ''),
                    r.get('trt_cst', ''),
                    f"{r.get('trt_aliq_ibs_estadual') or 0}%",
                    f"{r.get('trt_aliq_cbs') or 0}%"
                ))
                
            for col in self._sort_directions_ext:
                self.tree_ext.heading(col, text=col + " ↕")
        except Exception as e:
            pass 

    def _confirmar(self):
        regras_export = []
        for item in self.itens:
            inputs = self.inputs[item['id']]
            trt_id = inputs['id'].get().strip()
            trt_class = inputs['class'].get().strip()
            trt_cst = inputs['cst'].get().strip()
            trt_ibs = inputs['ibs'].get().strip()
            trt_cbs = inputs['cbs'].get().strip()
            
            if not trt_id or not trt_class:
                messagebox.showwarning("Aviso", f"Preencha o ID e a Classe Tributária corretamente.", parent=self)
                return
                
            try:
                ibs_val = float(trt_ibs.replace(',', '.')) if trt_ibs else 0.0
                cbs_val = float(trt_cbs.replace(',', '.')) if trt_cbs else 0.0
            except ValueError:
                messagebox.showwarning("Aviso", "Valores de IBS ou CBS inválidos.", parent=self)
                return
                
            regra = {
                'TRT_ID': trt_id,
                'TRT_CLASS_TRIB_ID': trt_class,
                'TRT_CST': trt_cst,
                'TRT_ALIQ_IBS_ESTADUAL': ibs_val,
                'TRT_ALIQ_CBS': cbs_val
            }
            regras_export.append(regra)
            
        try:
            with FirebirdService(self.fb_config) as fb:
                importer = FirebirdImporter(fb)
                res = importer.import_rt(regras_export)
                if hasattr(fb, 'commit'):
                    fb.commit()
                elif hasattr(fb, 'conn') and hasattr(fb.conn, 'commit'):
                    fb.conn.commit()
                    
            messagebox.showinfo("Sucesso", f"{res['inseridos']} regras cadastradas com sucesso!", parent=self)
            self.destroy()
            self.callback_sucesso()
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao inserir regras de RT:\n{e}", parent=self)

class DialogoRegrasRtExistentes(tk.Toplevel):
    def __init__(self, parent, fb_config):
        super().__init__(parent)
        self.title("Regras de Reforma Tributária Existentes no ERP")
        self.geometry("800x500")
        self.transient(parent)
        self.grab_set()
        
        icon_path = self.resource_path("icon.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)
            
        self.fb_config = fb_config
        self._criar_widgets()
        self._carregar_dados()
        
    def resource_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def _criar_widgets(self):
        frame_top = ttk.Frame(self, padding="10")
        frame_top.pack(side=tk.TOP, fill=tk.X)
        
        ttk.Label(frame_top, text="Regras IBS/CBS Cadastradas", font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
        ttk.Button(frame_top, text="🔄 Atualizar", command=self._carregar_dados).pack(side=tk.RIGHT)
        
        frame_grid = ttk.Frame(self, padding="10")
        frame_grid.pack(fill=tk.BOTH, expand=True)

        colunas = ("ID", "CÓD. CLASSE", "CST", "% IBS", "% CBS")
        self.tree = ttk.Treeview(frame_grid, columns=colunas, show="headings")
        self._sort_directions = {col: False for col in colunas}
        
        larguras = [80, 100, 80, 80, 80]
        for col, larg in zip(colunas, larguras):
            self.tree.heading(col, text=col + " ↕", command=lambda c=col: self._sort_treeview(c))
            self.tree.column(col, width=larg, anchor=tk.CENTER)
            
        scroll_y = ttk.Scrollbar(frame_grid, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scroll_y.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        frame_bot = ttk.Frame(self, padding="10")
        frame_bot.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Button(frame_bot, text="Fechar", command=self.destroy).pack(side=tk.RIGHT)

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

    def _carregar_dados(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        sql = "SELECT TRT_ID, TRT_CLASS_TRIB_ID, TRT_CST, TRT_ALIQ_IBS_ESTADUAL, TRT_ALIQ_CBS FROM TABELA_RT_CONFIG_2025_2026 ORDER BY TRT_ID"
        
        try:
            with FirebirdService(self.fb_config) as fb:
                resultados = fb.query(sql)
                
            for r in resultados:
                self.tree.insert("", tk.END, values=(
                    r.get('trt_id', ''),
                    r.get('trt_class_trib_id', ''),
                    r.get('trt_cst', ''),
                    f"{r.get('trt_aliq_ibs_estadual') or 0}%",
                    f"{r.get('trt_aliq_cbs') or 0}%"
                ))
                
            for col in self._sort_directions:
                self.tree.heading(col, text=col + " ↕")
                
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao buscar regras:\n{e}", parent=self)


class TelaRt(ttk.Frame):
    def __init__(self, parent, callback_voltar=None):
        super().__init__(parent, padding="10")
        self.parent = parent
        self.callback_voltar = callback_voltar
        self.pack(fill=tk.BOTH, expand=True)

        self.arquivos_selecionados = []
        self.pasta_xmls = ""
        self.dados_grid = {} 
        
        self.colunas = ("SEL", "QTD", "CÓD. CLASSE TRIB.", "CST", "DESCRIÇÃO", "RED. IBS", "RED. CBS", "REGRA", "% IBS", "% CBS", "STATUS ERP (ID)")
        self._sort_directions = {col: False for col in self.colunas}
        
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

    def _criar_widgets(self):
        lbl_title = tk.Label(self, text="REFORMA TRIBUTÁRIA (IBS/CBS)", font=("Segoe UI", 14, "bold"), fg="#F012BE")
        lbl_title.pack(anchor=tk.W, pady=(0, 10))

        frame_dir = ttk.Frame(self)
        frame_dir.pack(fill=tk.X, pady=10)
        
        self.ent_pasta = ttk.Entry(frame_dir, width=60)
        self.ent_pasta.pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_dir, text="📁 Pasta", command=self._selecionar_pasta).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_dir, text="📄 Arquivos", command=self._selecionar_arquivos).pack(side=tk.LEFT, padx=2)
        
        self.btn_analisar = ttk.Button(frame_dir, text="🔍 Analisar XMLs", command=self._iniciar_analise)
        self.btn_analisar.pack(side=tk.RIGHT, padx=5)
        
        self.btn_ver_regras = ttk.Button(frame_dir, text="👁 Ver Regras no ERP", command=self._ver_regras_existentes)
        self.btn_ver_regras.pack(side=tk.RIGHT, padx=5)

        self.lbl_status = ttk.Label(self, text="Aguardando importação...", font=("Segoe UI", 9))
        self.lbl_status.pack(anchor=tk.W)

        # Rodapé
        frame_fim = ttk.Frame(self)
        frame_fim.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
        ttk.Button(frame_fim, text="⬅ VOLTAR", command=self._fechar_tela).pack(side=tk.LEFT, padx=5)
        
        self.btn_exportar = ttk.Button(frame_fim, text="🚀 Enviar Selecionados p/ ERP", state=tk.DISABLED, command=self._preparar_exportacao)
        self.btn_exportar.pack(side=tk.RIGHT, padx=5)

        # Grade
        frame_grade = ttk.Frame(self)
        frame_grade.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=10)

        self.tree = ttk.Treeview(frame_grade, columns=self.colunas, show="headings")
        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)
        
        larguras = [40, 40, 110, 40, 250, 60, 60, 120, 50, 50, 100]
        for col, larg in zip(self.colunas, larguras):
            self.tree.heading(col, text=col + " ↕", command=lambda c=col: self._sort_treeview(c))
            self.tree.column(col, width=larg, anchor=tk.W if col == "DESCRIÇÃO" else tk.CENTER)

        self.tree.tag_configure('ENCONTRADA', background='#EAFAF1') 

        scroll_y = ttk.Scrollbar(frame_grade, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

    def _selecionar_pasta(self):
        pasta = filedialog.askdirectory()
        if pasta:
            self.ent_pasta.delete(0, tk.END); self.ent_pasta.insert(0, pasta)
            self.pasta_xmls = pasta; self.arquivos_selecionados = []

    def _selecionar_arquivos(self):
        arquivos = filedialog.askopenfilenames(filetypes=[("XML", "*.xml")])
        if arquivos:
            self.ent_pasta.delete(0, tk.END); self.ent_pasta.insert(0, f"{len(arquivos)} arquivo(s) selecionado(s)")
            self.arquivos_selecionados = list(arquivos); self.pasta_xmls = ""

    def _fechar_tela(self):
        self.destroy()
        if self.callback_voltar: self.callback_voltar()
        
    def _ver_regras_existentes(self):
        DialogoRegrasRtExistentes(self.parent, self.config_db)

    def _on_tree_click(self, event):
        if self.tree.identify_region(event.x, event.y) == "cell" and self.tree.identify_column(event.x) == "#1":
            item = self.tree.identify_row(event.y)
            valores = list(self.tree.item(item, "values"))
            valores[0] = "☑" if valores[0] == "☐" else "☐"
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
            return messagebox.showwarning("Atenção", "Selecione XMLs válidos.")
            
        self.btn_analisar.config(state=tk.DISABLED)
        self.lbl_status.config(text="Analisando XMLs e extraindo regras da Reforma Tributária...")
        for item in self.tree.get_children(): self.tree.delete(item)
        threading.Thread(target=self._pipeline_bg, daemon=True).start()

    def _pipeline_bg(self):
        try:
            itens_xml = []
            if self.arquivos_selecionados:
                for arq in self.arquivos_selecionados:
                    try: itens_xml.extend(parse_nfe(arq)['itens'])
                    except: pass
            else:
                itens_xml = parse_nfe_folder(self.pasta_xmls)

            mapa_agrupado = self._agrupar_rt(itens_xml)
            
            # Cruza com o Firebird
            regras_db = []
            try:
                with FirebirdService(self.config_db) as fb:
                    sql = "SELECT TRT_ID, TRT_CLASS_TRIB_ID, TRT_CST, TRT_ALIQ_IBS_ESTADUAL, TRT_ALIQ_CBS FROM TABELA_RT_CONFIG_2025_2026"
                    regras_db = fb.query(sql)
            except Exception:
                pass
                
            for grupo in mapa_agrupado:
                self._cruzar_regras_db(grupo, regras_db)
                
            self.parent.after(0, self._renderizar_resultados, mapa_agrupado)
        except Exception as e:
            self.parent.after(0, lambda: messagebox.showerror("Erro", str(e)))
            self.parent.after(0, lambda: self.btn_analisar.config(state=tk.NORMAL))

    def _agrupar_rt(self, itens):
        mapa = {}
        for i in itens:
            c_class_trib = str(i.get('c_class_trib') or '').strip()
            ibscbs_cst = str(i.get('ibscbs_cst') or '').strip()
            p_ibs = i.get('p_ibs_uf') or 0.0
            p_cbs = i.get('p_cbs') or 0.0
            
            # Ignora se não houver dados de IBS/CBS
            if not c_class_trib and not ibscbs_cst:
                continue
                
            k = f"{c_class_trib}|{ibscbs_cst}|{p_ibs}|{p_cbs}"
            if k not in mapa:
                mapa[k] = {
                    'id': f"rt_{len(mapa)}", 'ocorrencias': 1, 
                    'c_class_trib': c_class_trib, 'ibscbs_cst': ibscbs_cst, 
                    'p_ibs_uf': p_ibs, 'p_cbs': p_cbs,
                    'status_erp': '-'
                }
            else: 
                mapa[k]['ocorrencias'] += 1
                
        return sorted(list(mapa.values()), key=lambda x: (x['c_class_trib'], x['ibscbs_cst']))

    def _cruzar_regras_db(self, grupo, regras_db):
        xclass = str(grupo['c_class_trib']).strip().lstrip('0')
        if not xclass: xclass = '0'
        xcst = str(grupo['ibscbs_cst']).strip().lstrip('0')
        if not xcst: xcst = '0'
        xibs = float(grupo['p_ibs_uf'] or 0)
        xcbs = float(grupo['p_cbs'] or 0)
        
        matches = set()
        for r in regras_db:
            dclass = str(r.get('trt_class_trib_id') or '').strip().lstrip('0')
            if not dclass: dclass = '0'
            dcst = str(r.get('trt_cst') or '').strip().lstrip('0')
            if not dcst: dcst = '0'
            dibs = float(r.get('trt_aliq_ibs_estadual') or 0)
            dcbs = float(r.get('trt_aliq_cbs') or 0)
            
            if dclass == xclass and dcst == xcst and abs(dibs - xibs) < 0.01 and abs(dcbs - xcbs) < 0.01:
                matches.add(str(r.get('trt_id')))
                
        grupo['status_erp'] = ", ".join(sorted(list(matches))) if matches else "-"

    def _renderizar_resultados(self, mapa):
        self.dados_grid.clear()
        for r in mapa:
            c_class_pad = str(r['c_class_trib']).strip().zfill(6) if str(r['c_class_trib']).strip().isdigit() else str(r['c_class_trib']).strip()
            regra_info = REGRAS_RT_MAP.get(c_class_pad, {"descricao": "-", "red_ibs": "-", "red_cbs": "-", "regra": "-"})
            
            id_tree = self.tree.insert("", tk.END, values=(
                "☐", r['ocorrencias'], r['c_class_trib'], r['ibscbs_cst'], 
                regra_info["descricao"], regra_info["red_ibs"], regra_info["red_cbs"], regra_info["regra"],
                f"{r['p_ibs_uf']}%", f"{r['p_cbs']}%", r['status_erp']
            ), tags=('ENCONTRADA',) if r['status_erp'] != '-' else ())
            self.dados_grid[id_tree] = r
        self.btn_analisar.config(state=tk.NORMAL)
        self.btn_exportar.config(state=tk.NORMAL)
        self.lbl_status.config(text=f"Pronto. {len(mapa)} combinações únicas de IBS/CBS encontradas.")

    def _preparar_exportacao(self):
        selecionados = [self.dados_grid[i] for i in self.tree.get_children() if self.tree.set(i, "SEL") == "☑"]
        if not selecionados: return messagebox.showwarning("Aviso", "Selecione regras na tabela (coluna SEL).")
        DialogoExportarRt(self.parent, selecionados, self.config_db, lambda: self._iniciar_analise())
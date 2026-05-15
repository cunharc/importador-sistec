import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import csv
import os
import sys

from utils.xml_reader import parse_nfe_folder, parse_nfe

class TelaAuditoriaGeral(ttk.Frame):
    def __init__(self, parent, callback_voltar=None):
        super().__init__(parent, padding="10")
        self.parent = parent
        self.callback_voltar = callback_voltar
        self.pack(fill=tk.BOTH, expand=True)

        self.arquivos_selecionados = []
        self.pasta_xmls = ""
        self.itens_lidos = []
        self.linhas_agrupadas = []
        self.filtros_ativos = {'NCM': set(), 'CFOP': set(), 'UF DEST': set(), 'CST ICMS': set()}
        self._sort_directions = {}

        self._criar_widgets()

    def _criar_widgets(self):
        lbl_title = tk.Label(self, text="AUDITORIA GERAL DE TRIBUTAÇÃO (GERENCIAL)", font=("Segoe UI", 14, "bold"), fg="#2C3E50")
        lbl_title.pack(anchor=tk.W, pady=(0, 10))

        frame_dir = ttk.Frame(self)
        frame_dir.pack(fill=tk.X, pady=5)
        
        self.ent_pasta = ttk.Entry(frame_dir, width=50)
        self.ent_pasta.pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_dir, text="📁 Pasta", command=self._selecionar_pasta).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_dir, text="📄 Arquivos", command=self._selecionar_arquivos).pack(side=tk.LEFT, padx=2)
        
        self.btn_carregar = ttk.Button(frame_dir, text="📥 Carregar XMLs", command=self._carregar_xmls)
        self.btn_carregar.pack(side=tk.LEFT, padx=15)

        self.lbl_status = ttk.Label(frame_dir, text="Aguardando...", font=("Segoe UI", 9))
        self.lbl_status.pack(side=tk.LEFT, padx=10)

        # Frame de Agrupamento Dinâmico
        frame_grp = ttk.LabelFrame(self, text="Opções de Agrupamento (Selecione como deseja montar a visão)", padding="10")
        frame_grp.pack(fill=tk.X, pady=5)

        self.var_grp_prod = tk.BooleanVar(value=False)
        self.var_grp_ncm = tk.BooleanVar(value=True)
        self.var_grp_cfop = tk.BooleanVar(value=True)
        self.var_grp_uf = tk.BooleanVar(value=True)
        self.var_grp_tipo_cli = tk.BooleanVar(value=True)
        self.var_grp_icms = tk.BooleanVar(value=True)
        self.var_grp_piscof = tk.BooleanVar(value=False)
        self.var_grp_rt = tk.BooleanVar(value=False)

        ttk.Checkbutton(frame_grp, text="Produto", variable=self.var_grp_prod, command=self._processar_agrupamento).grid(row=0, column=0, sticky=tk.W, padx=10)
        ttk.Checkbutton(frame_grp, text="NCM", variable=self.var_grp_ncm, command=self._processar_agrupamento).grid(row=0, column=1, sticky=tk.W, padx=10)
        ttk.Checkbutton(frame_grp, text="CFOP", variable=self.var_grp_cfop, command=self._processar_agrupamento).grid(row=0, column=2, sticky=tk.W, padx=10)
        ttk.Checkbutton(frame_grp, text="UF Destino", variable=self.var_grp_uf, command=self._processar_agrupamento).grid(row=0, column=3, sticky=tk.W, padx=10)
        
        ttk.Checkbutton(frame_grp, text="Tipo Cliente (CT/NC/SN)", variable=self.var_grp_tipo_cli, command=self._processar_agrupamento).grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
        ttk.Checkbutton(frame_grp, text="Regras ICMS (CST, Aliq, cBenef)", variable=self.var_grp_icms, command=self._processar_agrupamento).grid(row=1, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Checkbutton(frame_grp, text="Regras PIS/COFINS", variable=self.var_grp_piscof, command=self._processar_agrupamento).grid(row=1, column=2, sticky=tk.W, padx=10, pady=5)
        ttk.Checkbutton(frame_grp, text="Reforma Tributária (IBS/CBS)", variable=self.var_grp_rt, command=self._processar_agrupamento).grid(row=1, column=3, sticky=tk.W, padx=10, pady=5)

        # Filtros Dinâmicos
        frame_filtros = ttk.LabelFrame(self, text="Filtros Específicos (Marque quais deseja ver)", padding="10")
        frame_filtros.pack(fill=tk.X, pady=5)
        
        ttk.Button(frame_filtros, text="Filtro NCM", command=lambda: self._abrir_filtro('NCM')).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_filtros, text="Filtro CFOP", command=lambda: self._abrir_filtro('CFOP')).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_filtros, text="Filtro UF", command=lambda: self._abrir_filtro('UF DEST')).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_filtros, text="Filtro CST ICMS", command=lambda: self._abrir_filtro('CST ICMS')).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_filtros, text="Limpar Filtros", command=self._limpar_filtros).pack(side=tk.LEFT, padx=15)

        # Grade
        frame_grade = ttk.Frame(self)
        frame_grade.pack(fill=tk.BOTH, expand=True, pady=5)

        self.colunas = (
            "QTD", "PRODUTO", "NCM", "CFOP", "UF DEST", "TIPO CLI",
            "CST ICMS", "% ICMS", "% RED.BC", "CBENEF",
            "CST PIS", "% PIS", "CST COF", "% COF",
            "CLASSE RT", "CST RT", "% IBS", "% CBS"
        )

        self._sort_directions = {col: False for col in self.colunas}

        self.tree = ttk.Treeview(frame_grade, columns=self.colunas, show="headings")
        
        larguras = [40, 200, 80, 50, 60, 70, 
                    70, 60, 60, 80, 
                    60, 50, 60, 50, 
                    90, 60, 50, 50]
        
        for col, larg in zip(self.colunas, larguras):
            self.tree.heading(col, text=col + " ↕", command=lambda c=col: self._sort_treeview(c))
            anchor = tk.W if col == "PRODUTO" else tk.CENTER
            self.tree.column(col, width=larg, anchor=anchor)

        scroll_y = ttk.Scrollbar(frame_grade, orient=tk.VERTICAL, command=self.tree.yview)
        scroll_x = ttk.Scrollbar(frame_grade, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscroll=scroll_y.set, xscroll=scroll_x.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)

        # Rodapé
        frame_fim = ttk.Frame(self)
        frame_fim.pack(fill=tk.X, pady=10)
        ttk.Button(frame_fim, text="⬅ VOLTAR", command=self._fechar_tela).pack(side=tk.LEFT, padx=5)
        
        self.btn_exportar = ttk.Button(frame_fim, text="📋 Exportar Visão Atual (CSV)", state=tk.DISABLED, command=self._exportar_csv)
        self.btn_exportar.pack(side=tk.RIGHT, padx=5)

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
        self.destroy()
        if self.callback_voltar: self.callback_voltar()

    def _carregar_xmls(self):
        if not self.pasta_xmls and not self.arquivos_selecionados:
            return messagebox.showwarning("Atenção", "Selecione XMLs válidos.")
            
        self.btn_carregar.config(state=tk.DISABLED)
        self.lbl_status.config(text="Lendo arquivos XML...")
        threading.Thread(target=self._ler_xmls_bg, daemon=True).start()

    def _ler_xmls_bg(self):
        try:
            self.itens_lidos = []
            if self.arquivos_selecionados:
                for arq in self.arquivos_selecionados:
                    try: self.itens_lidos.extend(parse_nfe(arq)['itens'])
                    except: pass
            else:
                self.itens_lidos = parse_nfe_folder(self.pasta_xmls)

            self.parent.after(0, self._processar_agrupamento)
        except Exception as e:
            self.parent.after(0, lambda: messagebox.showerror("Erro", str(e)))
        finally:
            self.parent.after(0, lambda: self.btn_carregar.config(state=tk.NORMAL))

    def _get_distinct(self, lista):
        s = set(str(x).strip() for x in lista if x is not None and str(x).strip() != "")
        if not s: return "-"
        if len(s) == 1: return list(s)[0]
        lst = sorted(list(s))
        if len(lst) <= 3:
            return " / ".join(lst)
        return "*VÁRIOS*"

    def _processar_agrupamento(self):
        if not self.itens_lidos:
            return

        self.lbl_status.config(text="Aplicando agrupamento...")
        
        grp_prod = self.var_grp_prod.get()
        grp_ncm = self.var_grp_ncm.get()
        grp_cfop = self.var_grp_cfop.get()
        grp_uf = self.var_grp_uf.get()
        grp_tipo_cli = self.var_grp_tipo_cli.get()
        grp_icms = self.var_grp_icms.get()
        grp_piscof = self.var_grp_piscof.get()
        grp_rt = self.var_grp_rt.get()

        mapa = {}
        for i in self.itens_lidos:
            chave = []
            if grp_prod: chave.append(str(i.get('cProd', '')))
            if grp_ncm: chave.append(str(i.get('ncm', '')))
            if grp_cfop: chave.append(str(i.get('cfop', '')))
            if grp_uf: chave.append(str(i.get('uf_dest', '')))
            if grp_tipo_cli: chave.append(str(i.get('tipo_cliente', 'CT')))
            if grp_icms:
                chave.extend([str(i.get('icms_cst', '')), str(i.get('p_icms', 0)), str(i.get('p_red_bc', 0)), str(i.get('c_benef', ''))])
            if grp_piscof:
                chave.extend([str(i.get('pis_cst', '')), str(i.get('p_pis', 0)), str(i.get('cofins_cst', '')), str(i.get('p_cofins', 0))])
            if grp_rt:
                chave.extend([str(i.get('c_class_trib', '')), str(i.get('ibscbs_cst', '')), str(i.get('p_ibs_uf', 0)), str(i.get('p_cbs', 0))])
                
            chave_tupla = tuple(chave)
            if chave_tupla not in mapa:
                mapa[chave_tupla] = []
            mapa[chave_tupla].append(i)

        linhas = []
        for grupo_itens in mapa.values():
            qtd = len(grupo_itens)
            produtos = [f"{i.get('cProd','')} - {i.get('xProd','')}" for i in grupo_itens]
            ncms = [i.get('ncm', '') for i in grupo_itens]
            cfops = [i.get('cfop', '') for i in grupo_itens]
            ufs = [i.get('uf_dest', '') for i in grupo_itens]
            tipos = [i.get('tipo_cliente', 'CT') for i in grupo_itens]
            
            icms_csts = [i.get('icms_cst', '') for i in grupo_itens]
            p_icms = [i.get('p_icms', 0) for i in grupo_itens]
            p_reds = [i.get('p_red_bc', 0) for i in grupo_itens]
            cbenefs = [i.get('c_benef', '') for i in grupo_itens]
            
            pis_csts = [str(i.get('pis_cst', '')).zfill(2) if i.get('pis_cst') else '' for i in grupo_itens]
            p_pis = [i.get('p_pis', 0) for i in grupo_itens]
            cof_csts = [str(i.get('cofins_cst', '')).zfill(2) if i.get('cofins_cst') else '' for i in grupo_itens]
            p_cof = [i.get('p_cofins', 0) for i in grupo_itens]
            
            c_class = [i.get('c_class_trib', '') for i in grupo_itens]
            cst_rt = [i.get('ibscbs_cst', '') for i in grupo_itens]
            p_ibs = [i.get('p_ibs_uf', 0) for i in grupo_itens]
            p_cbs = [i.get('p_cbs', 0) for i in grupo_itens]
            
            val = (
                qtd, self._get_distinct(produtos), self._get_distinct(ncms),
                self._get_distinct(cfops), self._get_distinct(ufs), self._get_distinct(tipos),
                self._get_distinct(icms_csts), self._get_distinct(p_icms), self._get_distinct(p_reds), self._get_distinct(cbenefs),
                self._get_distinct(pis_csts), self._get_distinct(p_pis), self._get_distinct(cof_csts), self._get_distinct(p_cof),
                self._get_distinct(c_class), self._get_distinct(cst_rt), self._get_distinct(p_ibs), self._get_distinct(p_cbs)
            )
            linhas.append(val)
            
        linhas.sort(key=lambda x: x[0], reverse=True)
        self.linhas_agrupadas = linhas
        self._limpar_filtros()

    def _limpar_filtros(self):
        for k in self.filtros_ativos:
            self.filtros_ativos[k] = set()
        self._renderizar_tabela()

    def _renderizar_tabela(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        linhas_filtradas = []
        for r in self.linhas_agrupadas:
            ncm = str(r[self.colunas.index('NCM')])
            cfop = str(r[self.colunas.index('CFOP')])
            uf = str(r[self.colunas.index('UF DEST')])
            cst_icms = str(r[self.colunas.index('CST ICMS')])

            if self.filtros_ativos.get('NCM') and ncm not in self.filtros_ativos['NCM']: continue
            if self.filtros_ativos.get('CFOP') and cfop not in self.filtros_ativos['CFOP']: continue
            if self.filtros_ativos.get('UF DEST') and uf not in self.filtros_ativos['UF DEST']: continue
            if self.filtros_ativos.get('CST ICMS') and cst_icms not in self.filtros_ativos['CST ICMS']: continue

            linhas_filtradas.append(r)

        for r in linhas_filtradas:
            self.tree.insert("", tk.END, values=r)

        for col in self.colunas:
            self.tree.heading(col, text=col + " ↕")
            self._sort_directions[col] = False

        self.lbl_status.config(text=f"Exibindo {len(linhas_filtradas)} de {len(self.linhas_agrupadas)} combinações geradas a partir de {len(self.itens_lidos)} itens.")
        self.btn_exportar.config(state=tk.NORMAL if linhas_filtradas else tk.DISABLED)

    def _abrir_filtro(self, coluna):
        if not self.linhas_agrupadas: 
            return messagebox.showwarning("Aviso", "Carregue e agrupe os dados primeiro.")
        
        idx = self.colunas.index(coluna)
        valores_unicos = sorted(list(set(str(r[idx]) for r in self.linhas_agrupadas)))
        
        top = tk.Toplevel(self)
        top.title(f"Filtrar por {coluna}")
        top.geometry("350x450")
        top.transient(self.winfo_toplevel())
        top.grab_set()

        frame_search = ttk.Frame(top)
        frame_search.pack(fill=tk.X, padx=10, pady=(10, 0))
        ttk.Label(frame_search, text="Buscar:").pack(side=tk.LEFT)
        ent_search = ttk.Entry(frame_search)
        ent_search.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        frame_list = ttk.Frame(top)
        frame_list.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        scrollbar = ttk.Scrollbar(frame_list)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        lb = tk.Listbox(frame_list, selectmode=tk.MULTIPLE, yscrollcommand=scrollbar.set)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=lb.yview)

        for val in valores_unicos:
            lb.insert(tk.END, val)
            if not self.filtros_ativos[coluna] or val in self.filtros_ativos[coluna]:
                lb.selection_set(tk.END)

        def on_search(event):
            texto = ent_search.get().lower()
            if not texto: return
            items = lb.get(0, tk.END)
            for i, val in enumerate(items):
                if texto in val.lower():
                    lb.see(i)
                    break
        ent_search.bind("<KeyRelease>", on_search)

        def aplicar():
            selecionados = [lb.get(i) for i in lb.curselection()]
            if len(selecionados) == len(valores_unicos) or not selecionados:
                self.filtros_ativos[coluna] = set()
            else:
                self.filtros_ativos[coluna] = set(selecionados)
            self._renderizar_tabela()
            top.destroy()

        def marcar_todos():
            lb.selection_set(0, tk.END)

        def desmarcar_todos():
            lb.selection_clear(0, tk.END)

        frame_btn = ttk.Frame(top)
        frame_btn.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(frame_btn, text="☑ Todos", command=marcar_todos).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_btn, text="☐ Nenhum", command=desmarcar_todos).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_btn, text="Aplicar Filtro", command=aplicar).pack(side=tk.RIGHT, padx=2)

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

    def _exportar_csv(self):
        caminho = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="Auditoria_Tributaria_Geral.csv", filetypes=[("CSV", "*.csv")])
        if not caminho: return
        try:
            with open(caminho, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(self.colunas)
                for child in self.tree.get_children():
                    writer.writerow(self.tree.item(child, "values"))
            messagebox.showinfo("Sucesso", "Exportação concluída!")
        except Exception as e:
            messagebox.showerror("Erro", str(e))
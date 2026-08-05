import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import csv
import os
import sys
import logging

from utils.xml_reader import parse_nfe_folder, parse_nfe
from utils import tema


def _csv_val(v):
    """Forca texto no Excel para numeros longos (EAN, chave NF-e, CNPJ, NCM),
    senao o Excel corta ou converte para notacao cientifica ao abrir o CSV."""
    s = '' if v is None else str(v)
    if s.isdigit() and len(s) >= 8:
        return f'="{s}"'
    return s


class DialogoDetalheItens(tk.Toplevel):
    def __init__(self, parent, itens):
        super().__init__(parent)
        self.title(f"Detalhamento de Itens ({len(itens)} registros)")
        w = min(1200, int(self.winfo_screenwidth() * 0.92))
        h = min(700, int(self.winfo_screenheight() * 0.8))
        self.geometry(f"{w}x{h}")
        self.minsize(640, 480)
        self.transient(parent)
        self.grab_set()
        
        self.itens = itens
        self._criar_widgets()
        self._carregar_dados()
        tema.centralizar(self, w, h)

    def _criar_widgets(self):
        frame_top = ttk.Frame(self, padding="5")
        frame_top.pack(fill=tk.X)
        ttk.Label(frame_top, text="Detalhamento das Notas Fiscais e Itens", font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
        ttk.Button(frame_top, text="📋 Exportar Excel (CSV)", command=self._exportar_csv).pack(side=tk.RIGHT)

        frame_grade = ttk.Frame(self, padding="5")
        frame_grade.pack(fill=tk.BOTH, expand=True)

        self.colunas = ("Nº NFE", "EMISSÃO", "CHAVE", "CNPJ/CPF DEST", "RAZÃO SOCIAL DEST", "CÓD. PROD", "PRODUTO", "EAN", "QTD", "V. UN", "V. TOTAL")
        self.tree = ttk.Treeview(frame_grade, columns=self.colunas, show="headings")

        larguras = [80, 90, 280, 120, 200, 100, 200, 110, 60, 80, 80]
        for col, larg in zip(self.colunas, larguras):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=larg, anchor=tk.W if "PRODUTO" in col or "RAZÃO" in col else tk.CENTER)

        scroll_y = ttk.Scrollbar(frame_grade, orient=tk.VERTICAL, command=self.tree.yview)
        scroll_x = ttk.Scrollbar(frame_grade, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscroll=scroll_y.set, xscroll=scroll_x.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)

    def _carregar_dados(self):
        for i in self.itens:
            nfe = str(i.get('nNF', ''))
            dh_emi = str(i.get('dhEmi', ''))
            if 'T' in dh_emi: dh_emi = dh_emi.split('T')[0]
            chave = str(i.get('chave_nfe', i.get('chNFe', '')))
            cnpj = str(i.get('dest_cnpj', i.get('emit_cnpj', '')))
            razao = str(i.get('dest_nome', i.get('emit_nome', '')))
            cprod = str(i.get('c_prod', ''))
            xprod = str(i.get('x_prod', ''))
            ean = str(i.get('c_ean', '') or '')
            qtd = str(i.get('q_com', ''))
            vun = str(i.get('v_un_com', ''))
            vtot = str(i.get('v_prod', ''))
            self.tree.insert("", tk.END, values=(nfe, dh_emi, chave, cnpj, razao, cprod, xprod, ean, qtd, vun, vtot))

    def _exportar_csv(self):
        caminho = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="Detalhamento_Itens_Produto.csv", filetypes=[("CSV", "*.csv")])
        if not caminho: return
        try:
            with open(caminho, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(self.colunas)
                for child in self.tree.get_children():
                    writer.writerow([_csv_val(v) for v in self.tree.item(child, "values")])
            messagebox.showinfo("Sucesso", "Exportação concluída!", parent=self)
        except Exception as e:
            messagebox.showerror("Erro", str(e), parent=self)


class TelaAuditoriaPorProduto(ttk.Frame):
    def __init__(self, parent, callback_voltar=None):
        super().__init__(parent, padding="10")
        self.parent = parent
        self.callback_voltar = callback_voltar
        self.pack(fill=tk.BOTH, expand=True)

        self.arquivos_selecionados = []
        self.pasta_xmls = ""
        self.itens_lidos = []
        self.linhas_agrupadas = []
        self.filtros_ativos = {'CÓD PRODUTO': set(), 'NCM': set(), 'CFOP': set(), 'CST ICMS': set()}
        self._sort_directions = {}
        self.dados_detalhe = {}

        self._criar_widgets()

    def _criar_widgets(self):
        # Header do módulo (identidade Sistecweb)
        tema.montar_header(
            self, "Auditoria por Produto",
            "Auditoria das variações de tributação que um mesmo produto sofreu nos XMLs"
        ).pack(fill=tk.X)

        # ===================== CORPO: menu lateral + conteúdo =====================
        corpo = tk.Frame(self, bg=tema.BG_BASE)
        corpo.pack(fill=tk.BOTH, expand=True)

        # -------- MENU LATERAL (padrão do main) --------
        sidebar = tema.montar_sidebar(corpo)

        # Rodapé do menu: Voltar
        rodape_sb = tk.Frame(sidebar, bg=tema.SIDEBAR_BG)
        rodape_sb.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 8))
        self.btn_voltar = tema.botao_sidebar(rodape_sb, "⎋   Voltar", self._fechar_tela)
        self.btn_voltar.pack(fill=tk.X)

        tema.titulo_sidebar(sidebar, "AÇÕES").pack(fill=tk.X, pady=(16, 4))

        self.btn_carregar = tema.botao_sidebar(sidebar, "📥   Carregar XMLs", self._carregar_xmls, cor_fg="#7EE0A0")
        self.btn_carregar.pack(fill=tk.X)

        self.btn_exportar = tema.botao_sidebar(sidebar, "📋   Exportar Visão Atual (CSV)", self._exportar_csv)
        self.btn_exportar.config(state=tk.DISABLED)
        self.btn_exportar.pack(fill=tk.X)

        # -------- CONTEÚDO --------
        content = tk.Frame(corpo, bg=tema.BG_BASE)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=16, pady=12)

        frame_dir = ttk.Frame(content)
        frame_dir.pack(fill=tk.X, pady=5)

        self.ent_pasta = ttk.Entry(frame_dir, width=50)
        self.ent_pasta.pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_dir, text="📁 Pasta", command=self._selecionar_pasta).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_dir, text="📄 Arquivos", command=self._selecionar_arquivos).pack(side=tk.LEFT, padx=2)

        self.lbl_status = ttk.Label(frame_dir, text="Aguardando...", font=("Segoe UI", 9))
        self.lbl_status.pack(side=tk.LEFT, padx=10)

        # Filtros Dinâmicos
        frame_filtros = ttk.LabelFrame(content, text="Filtros Específicos (Marque quais deseja ver)", padding="10")
        frame_filtros.pack(fill=tk.X, pady=5)

        ttk.Button(frame_filtros, text="Filtro Produto", command=lambda: self._abrir_filtro('CÓD PRODUTO')).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_filtros, text="Filtro NCM", command=lambda: self._abrir_filtro('NCM')).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_filtros, text="Filtro CFOP", command=lambda: self._abrir_filtro('CFOP')).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_filtros, text="Filtro CST ICMS", command=lambda: self._abrir_filtro('CST ICMS')).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_filtros, text="Limpar Filtros", command=self._limpar_filtros).pack(side=tk.LEFT, padx=15)

        # Grade
        frame_grade = ttk.Frame(content)
        frame_grade.pack(fill=tk.BOTH, expand=True, pady=5)

        self.colunas = (
            "QTD", "CÓD PRODUTO", "DESCRIÇÃO PRODUTO", "EAN", "NCM", "CFOP", "UF DEST", "TIPO CLI",
            "CST ICMS", "% ICMS", "% RED.BC", "CBENEF",
            "CST PIS", "% PIS", "CST COF", "% COF",
            "CLASSE RT", "CST RT", "% IBS", "% CBS"
        )

        self._sort_directions = {col: False for col in self.colunas}

        self.tree = ttk.Treeview(frame_grade, columns=self.colunas, show="headings")
        self.tree.bind("<Double-1>", self._abrir_detalhes)

        larguras = [40, 100, 200, 110, 80, 50, 60, 70,
                    70, 60, 60, 80,
                    60, 50, 60, 50,
                    90, 60, 50, 50]
        
        for col, larg in zip(self.colunas, larguras):
            self.tree.heading(col, text=col + " ↕", command=lambda c=col: self._sort_treeview(c))
            anchor = tk.W if col in ("DESCRIÇÃO PRODUTO",) else tk.CENTER
            self.tree.column(col, width=larg, anchor=anchor)

        scroll_y = ttk.Scrollbar(frame_grade, orient=tk.VERTICAL, command=self.tree.yview)
        scroll_x = ttk.Scrollbar(frame_grade, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscroll=scroll_y.set, xscroll=scroll_x.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)

    def _abrir_detalhes(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            item = self.tree.identify_row(event.y)
            if item in self.dados_detalhe:
                DialogoDetalheItens(self.winfo_toplevel(), self.dados_detalhe[item])

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
                    except Exception: logging.warning(f"Erro ao processar XML: {arq}")
            else:
                self.itens_lidos = parse_nfe_folder(self.pasta_xmls)

            self.parent.after(0, self._processar_agrupamento)
        except Exception as e:
            self.parent.after(0, lambda e=e: messagebox.showerror("Erro", str(e)))
        finally:
            self.parent.after(0, lambda: self.btn_carregar.config(state=tk.NORMAL))

    def _processar_agrupamento(self):
        if not self.itens_lidos:
            return

        self.lbl_status.config(text="Aplicando agrupamento...")

        mapa = {}
        for i in self.itens_lidos:
            chave = (
                str(i.get('c_prod', i.get('cProd', ''))),
                str(i.get('x_prod', i.get('xProd', ''))),
                str(i.get('ncm', '')),
                str(i.get('cfop', '')),
                str(i.get('uf_dest', '')),
                str(i.get('tipo_cliente', 'CT')),
                str(i.get('icms_cst', '')),
                str(i.get('p_icms', 0)),
                str(i.get('p_red_bc', 0)),
                str(i.get('c_benef', '')),
                str(i.get('pis_cst', '')),
                str(i.get('p_pis', 0)),
                str(i.get('cofins_cst', '')),
                str(i.get('p_cofins', 0)),
                str(i.get('c_class_trib', '')),
                str(i.get('ibscbs_cst', '')),
                str(i.get('p_ibs_uf', 0)),
                str(i.get('p_cbs', 0))
            )
            
            if chave not in mapa:
                mapa[chave] = []
            mapa[chave].append(i)

        linhas = []
        for chave_tupla, grupo_itens in mapa.items():
            qtd = len(grupo_itens)
            
            val = (
                qtd,
                chave_tupla[0], # CÓD PRODUTO
                chave_tupla[1], # DESCRIÇÃO PRODUTO
                self._ean_grupo(grupo_itens), # EAN
                chave_tupla[2], # NCM
                chave_tupla[3], # CFOP
                chave_tupla[4], # UF DEST
                chave_tupla[5], # TIPO CLI
                chave_tupla[6], # CST ICMS
                chave_tupla[7], # % ICMS
                chave_tupla[8], # % RED.BC
                chave_tupla[9], # CBENEF
                str(chave_tupla[10]).zfill(2) if chave_tupla[10] else '', # CST PIS
                chave_tupla[11], # % PIS
                str(chave_tupla[12]).zfill(2) if chave_tupla[12] else '', # CST COF
                chave_tupla[13], # % COF
                chave_tupla[14], # CLASSE RT
                chave_tupla[15], # CST RT
                chave_tupla[16], # % IBS
                chave_tupla[17], # % CBS
                grupo_itens
            )
            linhas.append(val)
            
        linhas.sort(key=lambda x: x[0], reverse=True)
        self.linhas_agrupadas = linhas
        self._limpar_filtros()

    def _ean_grupo(self, grupo_itens):
        """EAN(s) distintos do grupo; '-' quando todos SEM GTIN."""
        eans = set()
        for it in grupo_itens:
            e = str(it.get('c_ean') or '').strip()
            if e and e.upper() not in ('SEM GTIN', 'SEMGTIN', '0', '00000000000000'):
                eans.add(e)
        if not eans:
            return '-'
        if len(eans) == 1:
            return list(eans)[0]
        return ' / '.join(sorted(eans)) if len(eans) <= 3 else '*VÁRIOS*'

    def _limpar_filtros(self):
        for k in self.filtros_ativos:
            self.filtros_ativos[k] = set()
        self._renderizar_tabela()

    def _renderizar_tabela(self):
        self.dados_detalhe.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)

        linhas_filtradas = []
        for r in self.linhas_agrupadas:
            cod_prod = str(r[self.colunas.index('CÓD PRODUTO')])
            ncm = str(r[self.colunas.index('NCM')])
            cfop = str(r[self.colunas.index('CFOP')])
            cst_icms = str(r[self.colunas.index('CST ICMS')])

            if self.filtros_ativos.get('CÓD PRODUTO') and cod_prod not in self.filtros_ativos['CÓD PRODUTO']: continue
            if self.filtros_ativos.get('NCM') and ncm not in self.filtros_ativos['NCM']: continue
            if self.filtros_ativos.get('CFOP') and cfop not in self.filtros_ativos['CFOP']: continue
            if self.filtros_ativos.get('CST ICMS') and cst_icms not in self.filtros_ativos['CST ICMS']: continue

            linhas_filtradas.append(r)

        for r in linhas_filtradas:
            id_tree = self.tree.insert("", tk.END, values=r[:-1])
            self.dados_detalhe[id_tree] = r[-1]

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
        top.transient(self.winfo_toplevel())
        tema.centralizar(top, 350, 450)
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
        caminho = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="Auditoria_Tributaria_Por_Produto.csv", filetypes=[("CSV", "*.csv")])
        if not caminho: return
        try:
            with open(caminho, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(self.colunas)
                for child in self.tree.get_children():
                    writer.writerow([_csv_val(v) for v in self.tree.item(child, "values")])
            messagebox.showinfo("Sucesso", "Exportação concluída!")
        except Exception as e:
            messagebox.showerror("Erro", str(e))
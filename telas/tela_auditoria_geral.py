import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import csv
import os
import sys
import json
import logging
import glob

from utils.xml_reader import parse_nfe
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
        w = min(1300, int(self.winfo_screenwidth() * 0.94))
        h = min(750, int(self.winfo_screenheight() * 0.85))
        self.geometry(f"{w}x{h}")
        self.minsize(800, 500)
        self.transient(parent)
        self.grab_set()
        
        self.itens = itens
        self._criar_widgets()
        self._carregar_dados()
        tema.centralizar(self, w, h)

    def _criar_widgets(self):
        frame_top = ttk.Frame(self, padding="5")
        frame_top.pack(fill=tk.X)
        ttk.Label(frame_top, text="Detalhamento das Notas Fiscais e Itens", font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(frame_top, text="📄 Abrir XML", command=self._abrir_xml).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_top, text="📋 Ver Todos os Campos", command=self._ver_campos).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_top, text="📋 Exportar Excel (CSV)", command=self._exportar_csv).pack(side=tk.RIGHT)

        frame_grade = ttk.Frame(self, padding="5")
        frame_grade.pack(fill=tk.BOTH, expand=True)

        self.colunas = ("Nº NFE", "EMISSÃO", "CHAVE", "CNPJ/CPF DEST", "RAZÃO SOCIAL DEST", "CÓD. PROD", "PRODUTO", "EAN", "UNID", "QTD", "V. UN", "V. TOTAL", "ARQUIVO")
        self.tree = ttk.Treeview(frame_grade, columns=self.colunas, show="headings")
        self.tree.bind("<Double-1>", self._ao_duplo_clique)

        larguras = [80, 90, 220, 120, 180, 100, 200, 110, 50, 60, 80, 80, 150]
        for col, larg in zip(self.colunas, larguras):
            self.tree.heading(col, text=col)
            anchor = tk.W if col in ("PRODUTO", "RAZÃO SOCIAL DEST", "ARQUIVO") else tk.CENTER
            self.tree.column(col, width=larg, anchor=anchor)

        scroll_y = ttk.Scrollbar(frame_grade, orient=tk.VERTICAL, command=self.tree.yview)
        scroll_x = ttk.Scrollbar(frame_grade, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscroll=scroll_y.set, xscroll=scroll_x.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)

    def _item_selecionado(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Selecione um item na lista.", parent=self)
            return None
        idx = self.tree.index(sel[0])
        if idx < len(self.itens):
            return self.itens[idx]
        return None

    def _abrir_xml(self):
        item = self._item_selecionado()
        if not item:
            return
        caminho = item.get('_xml_path', '')
        if not caminho or not os.path.exists(caminho):
            messagebox.showerror("Erro", "Arquivo XML não encontrado:\n" + caminho, parent=self)
            return
        try:
            os.startfile(caminho)
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível abrir o arquivo:\n{e}", parent=self)

    def _ver_campos(self):
        item = self._item_selecionado()
        if not item:
            return
        top = tk.Toplevel(self)
        top.title("Todos os Campos do Item")
        w = min(700, int(self.winfo_screenwidth() * 0.6))
        h = min(600, int(self.winfo_screenheight() * 0.7))
        top.transient(self)
        tema.centralizar(top, w, h)
        top.grab_set()

        frame = ttk.Frame(top, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        cols = ("CAMPO", "VALOR")
        tree = ttk.Treeview(frame, columns=cols, show="headings")
        tree.heading("CAMPO", text="CAMPO")
        tree.heading("VALOR", text="VALOR")
        tree.column("CAMPO", width=250, anchor=tk.W)
        tree.column("VALOR", width=380, anchor=tk.W)

        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscroll=scroll.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        for chave, valor in sorted(item.items()):
            if chave == '_xml_path':
                continue
            tree.insert("", tk.END, values=(chave, str(valor)))

        frame_btn = ttk.Frame(top, padding="5")
        frame_btn.pack(fill=tk.X)
        ttk.Button(frame_btn, text="📄 Abrir XML", command=lambda: self._abrir_xml_especifico(item.get('_xml_path', ''))).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_btn, text="Fechar", command=top.destroy).pack(side=tk.RIGHT, padx=5)

    def _abrir_xml_especifico(self, caminho):
        if caminho and os.path.exists(caminho):
            try:
                os.startfile(caminho)
            except Exception:
                pass

    def _ao_duplo_clique(self, event):
        self._ver_campos()

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
            unid = str(i.get('u_com', ''))
            qtd = str(i.get('q_com', ''))
            vun = str(i.get('v_un_com', ''))
            vtot = str(i.get('v_prod', ''))
            arquivo = os.path.basename(i.get('_xml_path', ''))
            self.tree.insert("", tk.END, values=(nfe, dh_emi, chave, cnpj, razao, cprod, xprod, ean, unid, qtd, vun, vtot, arquivo))

    def _exportar_csv(self):
        caminho = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="Detalhamento_Itens.csv", filetypes=[("CSV", "*.csv")])
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
        self.dados_detalhe = {}
        self.ncm_descricoes = {}

        self._carregar_ncm_governo()
        self._criar_widgets()

    def _criar_widgets(self):
        # Header do módulo (identidade Sistecweb)
        tema.montar_header(
            self, "Visão Gerencial (Completa)",
            "Auditoria completa agrupando Produto, NCM, CFOP, ICMS, PIS/COFINS e RT com exportação"
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

        self.btn_exportar = tema.botao_sidebar(sidebar, "📋   Exportar Visão Atual (CSV)", self._exportar_csv, cor_fg="#7EE0A0")
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

        # Frame de Agrupamento Dinâmico
        frame_grp = ttk.LabelFrame(content, text="Opções de Agrupamento (Selecione como deseja montar a visão)", padding="10")
        frame_grp.pack(fill=tk.X, pady=5)

        self.var_grp_prod = tk.BooleanVar(self, value=False)
        self.var_grp_ncm = tk.BooleanVar(self, value=True)
        self.var_grp_cfop = tk.BooleanVar(self, value=True)
        self.var_grp_uf = tk.BooleanVar(self, value=True)
        self.var_grp_tipo_cli = tk.BooleanVar(self, value=True)
        self.var_grp_icms = tk.BooleanVar(self, value=True)
        self.var_grp_piscof = tk.BooleanVar(self, value=False)
        self.var_grp_rt = tk.BooleanVar(self, value=False)

        ttk.Checkbutton(frame_grp, text="Produto", variable=self.var_grp_prod, command=self._processar_agrupamento).grid(row=0, column=0, sticky=tk.W, padx=10)
        ttk.Checkbutton(frame_grp, text="NCM", variable=self.var_grp_ncm, command=self._processar_agrupamento).grid(row=0, column=1, sticky=tk.W, padx=10)
        ttk.Checkbutton(frame_grp, text="CFOP", variable=self.var_grp_cfop, command=self._processar_agrupamento).grid(row=0, column=2, sticky=tk.W, padx=10)
        ttk.Checkbutton(frame_grp, text="UF Destino", variable=self.var_grp_uf, command=self._processar_agrupamento).grid(row=0, column=3, sticky=tk.W, padx=10)
        
        ttk.Checkbutton(frame_grp, text="Tipo Cliente (CT/NC/SN)", variable=self.var_grp_tipo_cli, command=self._processar_agrupamento).grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
        ttk.Checkbutton(frame_grp, text="Regras ICMS (CST, Aliq, cBenef)", variable=self.var_grp_icms, command=self._processar_agrupamento).grid(row=1, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Checkbutton(frame_grp, text="Regras PIS/COFINS", variable=self.var_grp_piscof, command=self._processar_agrupamento).grid(row=1, column=2, sticky=tk.W, padx=10, pady=5)
        ttk.Checkbutton(frame_grp, text="Reforma Tributária (IBS/CBS)", variable=self.var_grp_rt, command=self._processar_agrupamento).grid(row=1, column=3, sticky=tk.W, padx=10, pady=5)

        # Filtros Dinâmicos
        frame_filtros = ttk.LabelFrame(content, text="Filtros Específicos (Marque quais deseja ver)", padding="10")
        frame_filtros.pack(fill=tk.X, pady=5)
        
        ttk.Button(frame_filtros, text="Filtro NCM", command=lambda: self._abrir_filtro('NCM')).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_filtros, text="Filtro CFOP", command=lambda: self._abrir_filtro('CFOP')).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_filtros, text="Filtro UF", command=lambda: self._abrir_filtro('UF DEST')).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_filtros, text="Filtro CST ICMS", command=lambda: self._abrir_filtro('CST ICMS')).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_filtros, text="Limpar Filtros", command=self._limpar_filtros).pack(side=tk.LEFT, padx=15)

        # Grade
        frame_grade = ttk.Frame(content)
        frame_grade.pack(fill=tk.BOTH, expand=True, pady=5)

        self.colunas = (
            "QTD", "CÓD. PROD", "DESCRIÇÃO", "EAN", "UNID", "NCM", "DESCRIÇÃO NCM", "DESCR CONCAT NCM",
            "CFOP", "UF DEST", "TIPO CLI",
            "CST ICMS", "% ICMS", "% RED.BC", "CBENEF",
            "CST PIS", "% PIS", "CST COF", "% COF",
            "CLASSE RT", "CST RT", "% IBS", "% CBS"
        )

        self._sort_directions = {col: False for col in self.colunas}

        self.tree = ttk.Treeview(frame_grade, columns=self.colunas, show="headings")
        self.tree.bind("<Double-1>", self._abrir_detalhes)

        larguras = [40, 90, 200, 110, 50, 80, 200, 200, 50, 60, 70,
                    70, 60, 60, 80,
                    60, 50, 60, 50,
                    90, 60, 50, 50]
        
        for col, larg in zip(self.colunas, larguras):
            self.tree.heading(col, text=col + " ↕", command=lambda c=col: self._sort_treeview(c))
            anchor = tk.W if col in ("DESCRIÇÃO", "DESCRIÇÃO NCM", "DESCR CONCAT NCM") else tk.CENTER
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
            pasta = os.path.normpath(pasta)
            self.ent_pasta.delete(0, tk.END); self.ent_pasta.insert(0, pasta)
            self.pasta_xmls = pasta; self.arquivos_selecionados = []

    def _selecionar_arquivos(self):
        arquivos = filedialog.askopenfilenames(filetypes=[("XML", "*.xml")])
        if arquivos:
            self.ent_pasta.delete(0, tk.END); self.ent_pasta.insert(0, f"{len(arquivos)} arquivo(s)")
            self.arquivos_selecionados = [os.path.normpath(a) for a in arquivos]; self.pasta_xmls = ""

    def _fechar_tela(self):
        self.destroy()
        if self.callback_voltar: self.callback_voltar()

    def resource_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def _carregar_ncm_governo(self):
        caminho = self.resource_path("ncm_governo.json")
        if os.path.exists(caminho):
            try:
                with open(caminho, 'r', encoding='utf-8') as f:
                    for row in json.load(f):
                        cod = str(row.get('codigo', '')).strip()
                        desc = str(row.get('descricao', '')).strip()
                        concat = str(row.get('desc_concat', '')).strip()
                        if cod and desc:
                            self.ncm_descricoes[cod] = {
                                'descricao': desc,
                                'desc_concat': concat or desc,
                            }
            except Exception as e:
                print(f"Erro ao carregar ncm_governo.json: {e}")

    def _carregar_xmls(self):
        if not self.pasta_xmls and not self.arquivos_selecionados:
            return messagebox.showwarning("Atenção", "Selecione XMLs válidos.")
            
        self.btn_carregar.config(state=tk.DISABLED)
        self.lbl_status.config(text="Lendo arquivos XML...")

        self._progress_popup = tk.Toplevel(self.winfo_toplevel())
        self._progress_popup.title("Carregando XMLs")
        w_p = min(500, int(self.winfo_screenwidth() * 0.5))
        h_p = min(150, int(self.winfo_screenheight() * 0.2))
        self._progress_popup.transient(self.winfo_toplevel())
        tema.centralizar(self._progress_popup, w_p, h_p)
        self._progress_popup.grab_set()
        self._progress_popup.protocol("WM_DELETE_WINDOW", lambda: None)

        frame = ttk.Frame(self._progress_popup, padding="15")
        frame.pack(fill=tk.BOTH, expand=True)

        self._progress_label = ttk.Label(frame, text="Iniciando leitura...")
        self._progress_label.pack(fill=tk.X, pady=(0, 10))

        self._progress_bar = ttk.Progressbar(frame, mode='determinate')
        self._progress_bar.pack(fill=tk.X)

        threading.Thread(target=self._ler_xmls_bg, daemon=True).start()

    def _atualizar_progresso(self, atual, total):
        if not hasattr(self, '_progress_bar') or not self._progress_bar:
            return
        percent = (atual / total) * 100
        self._progress_bar['value'] = percent
        self._progress_label.config(text=f"Lendo arquivo {atual} de {total} ({percent:.1f}%)")

    def _fechar_progresso(self):
        if hasattr(self, '_progress_popup') and self._progress_popup:
            try:
                self._progress_popup.destroy()
            except Exception:
                pass
            self._progress_popup = None

    def _ler_xmls_bg(self):
        try:
            self.itens_lidos = []
            if self.arquivos_selecionados:
                total = len(self.arquivos_selecionados)
                for i, arq in enumerate(self.arquivos_selecionados):
                    self.parent.after(0, self._atualizar_progresso, i + 1, total)
                    try:
                        nfe_data = parse_nfe(arq)
                        if nfe_data and nfe_data.get('itens'):
                            for item in nfe_data['itens']:
                                item['chave_nfe'] = nfe_data['chave_nfe']
                                item['_xml_path'] = arq
                                self.itens_lidos.append(item)
                    except Exception:
                        logging.warning(f"Erro ao processar XML: {arq}")
            else:
                pattern = os.path.join(self.pasta_xmls, '**', '*.xml')
                xml_files = [os.path.normpath(f) for f in glob.glob(pattern, recursive=True)]
                total = len(xml_files)
                for i, arq in enumerate(xml_files):
                    self.parent.after(0, self._atualizar_progresso, i + 1, total)
                    try:
                        nfe_data = parse_nfe(arq)
                        if nfe_data and nfe_data.get('itens'):
                            for item in nfe_data['itens']:
                                item['chave_nfe'] = nfe_data['chave_nfe']
                                item['_xml_path'] = arq
                                self.itens_lidos.append(item)
                    except Exception:
                        logging.warning(f"Erro ao processar XML: {arq}")

            self.parent.after(0, self._fechar_progresso)
            self.parent.after(0, self._processar_agrupamento)
        except Exception as e:
            self.parent.after(0, self._fechar_progresso)
            self.parent.after(0, lambda e=e: messagebox.showerror("Erro", str(e)))
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
            if grp_prod: chave.append(str(i.get('c_prod', i.get('cProd', ''))))
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
            cod_prods = [str(i.get('c_prod', i.get('cProd', ''))) for i in grupo_itens]
            desc_prods = [str(i.get('x_prod', i.get('xProd', ''))) for i in grupo_itens]
            eans = ['' if str(i.get('c_ean') or '').strip().upper() in ('SEM GTIN', 'SEMGTIN', '0', '00000000000000')
                    else str(i.get('c_ean') or '').strip() for i in grupo_itens]
            unidades = [i.get('u_com', '') for i in grupo_itens]
            ncms = [i.get('ncm', '') for i in grupo_itens]
            desc_ncms = []
            desc_concat_ncms = []
            for ncm in ncms:
                ncm_key = str(ncm).replace('.', '').replace('-', '').strip()
                info = self.ncm_descricoes.get(ncm_key)
                if info:
                    desc_ncms.append(info['descricao'])
                    desc_concat_ncms.append(info['desc_concat'])
                else:
                    desc_ncms.append("-")
                    desc_concat_ncms.append("-")
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
                qtd, self._get_distinct(cod_prods), self._get_distinct(desc_prods), self._get_distinct(eans), self._get_distinct(unidades), self._get_distinct(ncms),
                self._get_distinct(desc_ncms), self._get_distinct(desc_concat_ncms),
                self._get_distinct(cfops), self._get_distinct(ufs), self._get_distinct(tipos),
                self._get_distinct(icms_csts), self._get_distinct(p_icms), self._get_distinct(p_reds), self._get_distinct(cbenefs),
                self._get_distinct(pis_csts), self._get_distinct(p_pis), self._get_distinct(cof_csts), self._get_distinct(p_cof),
                self._get_distinct(c_class), self._get_distinct(cst_rt), self._get_distinct(p_ibs), self._get_distinct(p_cbs),
                grupo_itens
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
        self.dados_detalhe.clear()
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
        caminho = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="Auditoria_Tributaria_Geral.csv", filetypes=[("CSV", "*.csv")])
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
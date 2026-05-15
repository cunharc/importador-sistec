import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import json
import os
import sys
import csv

from utils.xml_reader import parse_nfe_folder, parse_nfe

class TelaCfop(ttk.Frame):
    def __init__(self, parent, callback_voltar=None):
        super().__init__(parent, padding="10")
        self.parent = parent
        self.callback_voltar = callback_voltar
        self.pack(fill=tk.BOTH, expand=True)

        self.arquivos_selecionados = []
        self.pasta_xmls = ""
        self.cfop_governo = {}
        
        self.colunas = ("QTD", "CFOP", "STATUS (GOVERNO)", "DESCRIÇÃO OFICIAL")
        self._sort_directions = {col: False for col in self.colunas}

        self._carregar_cfop_governo()
        self._criar_widgets()

    def resource_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def _carregar_cfop_governo(self):
        caminho_cfop = self.resource_path("cfop_governo.json")
        if os.path.exists(caminho_cfop):
            try:
                with open(caminho_cfop, 'r', encoding='utf-8') as f:
                    dados = json.load(f)
                    for row in dados:
                        cod = str(row.get('cfop') or row.get('codigo', ''))
                        if cod:
                            self.cfop_governo[cod] = row
            except Exception as e:
                print(f"Erro ao carregar cfop_governo.json: {e}")

    def _criar_widgets(self):
        lbl_title = tk.Label(self, text="ANÁLISE DE NATUREZA DE OPERAÇÃO (CFOP)", font=("Segoe UI", 14, "bold"), fg="#D35400")
        lbl_title.pack(anchor=tk.W, pady=(0, 10))

        frame_dir = ttk.Frame(self)
        frame_dir.pack(fill=tk.X, pady=10)
        
        self.ent_pasta = ttk.Entry(frame_dir, width=60)
        self.ent_pasta.pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_dir, text="📁 Pasta", command=self._selecionar_pasta).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_dir, text="📄 Arquivos", command=self._selecionar_arquivos).pack(side=tk.LEFT, padx=2)
        
        self.btn_analisar = ttk.Button(frame_dir, text="🔍 Agrupar XMLs", command=self._iniciar_analise)
        self.btn_analisar.pack(side=tk.RIGHT, padx=5)

        status_text = f"{len(self.cfop_governo)} CFOPs do Governo carregados na memória." if self.cfop_governo else "Tabela cfop_governo.json não encontrada. Validação desabilitada."
        self.lbl_status = ttk.Label(self, text=status_text, font=("Segoe UI", 9))
        self.lbl_status.pack(anchor=tk.W)

        # Grade
        frame_grade = ttk.Frame(self)
        frame_grade.pack(fill=tk.BOTH, expand=True, pady=10)

        self.tree = ttk.Treeview(frame_grade, columns=self.colunas, show="headings")
        
        larguras = [60, 80, 150, 600]
        for col, larg in zip(self.colunas, larguras):
            self.tree.heading(col, text=col + " ↕", command=lambda c=col: self._sort_treeview(c))
            anchor = tk.W if col == "DESCRIÇÃO OFICIAL" else tk.CENTER
            self.tree.column(col, width=larg, anchor=anchor)

        self.tree.tag_configure('VALIDO', background='#EAFAF1') 
        self.tree.tag_configure('INVALIDO', background='#FADBD8')

        scroll_y = ttk.Scrollbar(frame_grade, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        # Rodapé
        frame_fim = ttk.Frame(self)
        frame_fim.pack(fill=tk.X, pady=10)
        ttk.Button(frame_fim, text="⬅ VOLTAR", command=self._fechar_tela).pack(side=tk.LEFT, padx=5)
        
        self.btn_exportar = ttk.Button(frame_fim, text="📋 Exportar para Excel (CSV)", state=tk.DISABLED, command=self._exportar_csv)
        self.btn_exportar.pack(side=tk.RIGHT, padx=5)

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
        
    def _sort_treeview(self, col):
        self._sort_directions[col] = not self._sort_directions[col]
        reverse = self._sort_directions[col]
        
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        
        def valor_para_ordenar(val):
            v = str(val).strip()
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
        self.lbl_status.config(text="Agrupando CFOPs...")
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

            mapa = {}
            for i in itens_xml:
                cfop = str(i.get('cfop', '')).strip()
                if not cfop: continue
                if cfop not in mapa:
                    mapa[cfop] = {'ocorrencias': 1, 'cfop': cfop}
                else:
                    mapa[cfop]['ocorrencias'] += 1
                    
            self.parent.after(0, self._renderizar_resultados, list(mapa.values()))
        except Exception as e:
            self.parent.after(0, lambda: messagebox.showerror("Erro", str(e)))
            self.parent.after(0, lambda: self.btn_analisar.config(state=tk.NORMAL))

    def _renderizar_resultados(self, mapa):
        # Ordenar por maior ocorrência
        mapa_ordenado = sorted(mapa, key=lambda x: x['ocorrencias'], reverse=True)
        for r in mapa_ordenado:
            cfop = r['cfop']
            oficial = self.cfop_governo.get(cfop)
            desc_oficial = oficial.get('descricao', oficial.get('nome', 'CFOP NÃO ENCONTRADO')) if oficial else "CFOP NÃO ENCONTRADO"
            status = "VÁLIDO" if oficial else "INVÁLIDO"
            tag = "VALIDO" if oficial else "INVALIDO"
            self.tree.insert("", tk.END, values=(r['ocorrencias'], cfop, status, desc_oficial), tags=(tag,))
            
        self.btn_analisar.config(state=tk.NORMAL)
        self.btn_exportar.config(state=tk.NORMAL)
        self.lbl_status.config(text=f"Pronto. {len(mapa)} CFOPs únicos encontrados.")

    def _exportar_csv(self):
        caminho = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="Analise_CFOP.csv", filetypes=[("CSV", "*.csv")])
        if not caminho: return
        try:
            with open(caminho, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(["QTD", "CFOP", "STATUS (GOVERNO)", "DESCRIÇÃO OFICIAL"])
                for child in self.tree.get_children():
                    writer.writerow(self.tree.item(child, "values"))
            messagebox.showinfo("Sucesso", "Arquivo exportado com sucesso!")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao exportar:\n{e}")
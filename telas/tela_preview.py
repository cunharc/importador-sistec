import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import csv
import os
import sys

class TelaPreview(tk.Toplevel):
    def __init__(self, parent, registros, callback_importar):
        super().__init__(parent)
        self.title("Preview — Dados a serem importados")
        w = min(1100, int(self.winfo_screenwidth() * 0.92))
        h = min(700, int(self.winfo_screenheight() * 0.85))
        self.geometry(f"{w}x{h}")
        self.minsize(640, 480)
        self.transient(parent)
        self.grab_set()
        
        icon_path = self.resource_path("icon.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)

        self.registros = registros
        self.callback_importar = callback_importar

        self._criar_widgets()
        self._carregar_dados()
        
    def resource_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def _criar_widgets(self):
        top_frame = ttk.Frame(self, padding="10")
        top_frame.pack(fill=tk.X)

        ttk.Label(top_frame, text="🔍 Filtrar:").pack(side=tk.LEFT)
        self.ent_filtro = ttk.Entry(top_frame, width=30)
        self.ent_filtro.pack(side=tk.LEFT, padx=5)
        self.ent_filtro.bind("<KeyRelease>", self._filtrar_dados)

        ttk.Button(top_frame, text="📋 Exportar CSV", command=self._exportar_csv).pack(side=tk.RIGHT)

        # Treeview
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10)

        colunas = ("EMP", "FIL", "EXE", "COD", "CONTA", "DESCRIÇÃO", "NÍVEL", "RED", "IND", "NAT", "STATUS", "OBSERVAÇÃO")
        self._sort_directions = {col: False for col in colunas}
        self.tree = ttk.Treeview(tree_frame, columns=colunas, show="headings")
        
        larguras = [40, 40, 50, 50, 100, 250, 50, 50, 50, 50, 100, 250]
        for col, larg in zip(colunas, larguras):
            self.tree.heading(col, text=col + " ↕", command=lambda c=col: self._sort_tree(c))
            anchor = tk.W if col in ["CONTA", "DESCRIÇÃO", "OBSERVAÇÃO"] else tk.CENTER
            self.tree.column(col, width=larg, anchor=anchor)

        scroll_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scroll_x = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscroll=scroll_y.set, xscroll=scroll_x.set)

        self.tree.grid(row=0, column=0, sticky='nsew')
        scroll_y.grid(row=0, column=1, sticky='ns')
        scroll_x.grid(row=1, column=0, sticky='ew')
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        # Rodapé
        bottom_frame = ttk.Frame(self, padding="10")
        bottom_frame.pack(fill=tk.X)

        self.lbl_resumo = ttk.Label(bottom_frame, text="")
        self.lbl_resumo.pack(side=tk.LEFT)

        ttk.Button(bottom_frame, text="❌ CANCELAR", command=self.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="✅ CONFIRMAR E IMPORTAR", command=self._confirmar).pack(side=tk.RIGHT, padx=5)

    def _carregar_dados(self, filtro=""):
        filtro = filtro.strip().lower()
        for i in self.tree.get_children():
            self.tree.delete(i)

        analiticas = 0
        sinteticas = 0
        exibidos = 0

        for r in self.registros:
            valores = (
                r['PLANO_EMPRESA'], r['PLANO_FILIAL'], r['PLANO_EXERCICIO'], r['PLANO_CODIGO'],
                r['PLANO_CONTA'], r['PLANO_DESCRICAO'], r['PLANO_NIVEL'], 
                r['PLANO_REDUZIDO'] or "", r['PLANO_INDICE'] or "", 
                r['PLANO_COD_NATUREZA'], r['STATUS']
                , r.get('OBSERVACAO', '')
            )

            if filtro:
                texto_completo = " ".join(str(v).lower() for v in valores)
                if filtro not in texto_completo: 
                    continue

            self.tree.insert("", tk.END, values=valores)
            exibidos += 1
            
            if r['PLANO_REDUZIDO'] is not None:
                analiticas += 1
            else:
                sinteticas += 1

        self.lbl_resumo.config(text=f"Total: {len(self.registros)} registros (Exibindo {exibidos}) | Analíticas: {analiticas} | Sintéticas: {sinteticas}")

    def _filtrar_dados(self, event):
        self._carregar_dados(self.ent_filtro.get())

    def _sort_tree(self, col):
        self._sort_directions[col] = not self._sort_directions[col]
        reverse = self._sort_directions[col]

        mapping = {
            'EMP': 'PLANO_EMPRESA',
            'FIL': 'PLANO_FILIAL',
            'EXE': 'PLANO_EXERCICIO',
            'COD': 'PLANO_CODIGO',
            'CONTA': 'PLANO_CONTA',
            'DESCRIÇÃO': 'PLANO_DESCRICAO',
            'NÍVEL': 'PLANO_NIVEL',
            'RED': 'PLANO_REDUZIDO',
            'IND': 'PLANO_INDICE',
            'NAT': 'PLANO_COD_NATUREZA',
            'STATUS': 'STATUS',
            'OBSERVAÇÃO': 'OBSERVACAO'
        }

        key = mapping[col]

        def valor_para_ordenar(registro):
            valor = registro.get(key)
            if valor is None:
                return ""
            if isinstance(valor, (int, float)):
                return valor
            texto = str(valor).strip()
            return int(texto) if texto.isdigit() else texto.lower()

        self.registros.sort(key=valor_para_ordenar, reverse=reverse)
        self._atualizar_legenda_ordenacao(col)
        self._carregar_dados(self.ent_filtro.get())

    def _atualizar_legenda_ordenacao(self, coluna_ativa):
        for col in self._sort_directions:
            if col == coluna_ativa:
                arrow = " ▼" if self._sort_directions[col] else " ▲"
            else:
                arrow = " ↕"
            self.tree.heading(col, text=col + arrow, command=lambda c=col: self._sort_tree(c))

    def _exportar_csv(self):
        caminho = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
        if not caminho:
            return
            
        try:
            with open(caminho, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=self.registros[0].keys(), delimiter=';')
                writer.writeheader()
                writer.writerows(self.registros)
            messagebox.showinfo("Sucesso", "Dados exportados com sucesso!")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao exportar CSV:\n{e}")

    def _confirmar(self):
        contas_validas = [r for r in self.registros if r['STATUS'] == 'OK']
        if not contas_validas:
            messagebox.showwarning("Aviso", "Não há registros válidos ('OK') para importar.")
            return

        resposta = messagebox.askyesno("Confirmar Importação", f"Deseja realmente importar {len(contas_validas)} registros para o banco de dados?")
        if resposta:
            self.destroy()
            self.callback_importar(contas_validas)

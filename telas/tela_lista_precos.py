import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import configparser
import threading
import os
import datetime
import logging
from utils.firebird_service import FirebirdService
from utils.xml_reader import parse_nfe_folder, parse_nfe


class DropdownListbox(tk.Frame):
    """Entry + dropdown Listbox com suporte a negrito por item."""

    def __init__(self, parent, width=50, height=8, **kwargs):
        super().__init__(parent)
        self._var = tk.StringVar()
        self._items = []
        self._bold_set = set()
        self._height = height

        self.entry = ttk.Entry(self, textvariable=self._var, width=width, state="readonly")
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.entry.bind("<Button-1>", self._show_dropdown)

        self.btn = ttk.Button(self, text="\u25bc", width=3, command=self._show_dropdown)
        self.btn.pack(side=tk.RIGHT)

        self._top = tk.Toplevel(self)
        self._top.withdraw()
        self._top.overrideredirect(True)
        self._top.attributes("-topmost", True)

        self.listbox = tk.Listbox(self._top, width=width, height=height, exportselection=False,
                                  font=("Segoe UI", 9))
        self.listbox.pack(fill=tk.BOTH, expand=True)
        self.listbox.bind("<ButtonRelease-1>", self._on_select)
        self.listbox.bind("<Escape>", lambda e: self._hide_dropdown())
        self.listbox.bind("<Return>", self._on_select)
        self._top.bind("<FocusOut>", lambda e: self.after(100, self._hide_dropdown))

    def _show_dropdown(self, event=None):
        if not self._items:
            return
        self.listbox.delete(0, tk.END)
        for item in self._items:
            idx = self.listbox.size()
            self.listbox.insert(tk.END, item)
            if item in self._bold_set:
                self.listbox.itemconfig(idx, font=("Segoe UI", 9, "bold"))
            else:
                self.listbox.itemconfig(idx, font=("Segoe UI", 9))

        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        self._top.geometry(f"+{x}+{y}")
        self._top.deiconify()
        self._top.lift()
        self.listbox.focus_set()

    def _hide_dropdown(self):
        self._top.withdraw()

    def _on_select(self, event=None):
        sel = self.listbox.curselection()
        if sel:
            self._var.set(self._items[sel[0]])
        self._hide_dropdown()

    def get(self):
        return self._var.get()

    def set(self, value):
        self._var.set(value)

    def current(self, index):
        if 0 <= index < len(self._items):
            self._var.set(self._items[index])

    def set_items(self, items, bold_items=None):
        self._items = items
        self._bold_set = set(bold_items) if bold_items else set()

    def config_state(self, state):
        self.entry.config(state=state)


class TelaListaPrecos(ttk.Frame):
    def __init__(self, parent, callback_voltar=None):
        super().__init__(parent, padding="10")
        self.parent = parent
        self.callback_voltar = callback_voltar
        self.pack(fill=tk.BOTH, expand=True)

        self.arquivos_selecionados = []
        self.pasta_xmls = ""
        self.dados_analisados = []
        self.listas_existentes = []

        self.config = configparser.ConfigParser()
        self.config.read('config.ini', encoding='utf-8')
        self.config_db = {
            'host': self.config.get('FIREBIRD', 'servidor', fallback='127.0.0.1'),
            'port': self.config.get('FIREBIRD', 'porta', fallback='3050'),
            'database': self.config.get('FIREBIRD', 'caminho_banco', fallback=''),
            'user': self.config.get('FIREBIRD', 'usuario', fallback='SYSDBA'),
            'password': self.config.get('FIREBIRD', 'senha', fallback='masterkey')
        }
        
        self.empresa = self.config.get('IMPORTACAO', 'empresa', fallback='1')
        self.filial = self.config.get('IMPORTACAO', 'filial', fallback='1')

        self.colunas = ("SEL", "STATUS", "CÓD. ERP", "PRODUTO ERP", "PREÇO (R$)")
        self._sort_directions = {col: False for col in self.colunas}

        self._criar_widgets()
        self.after(500, self._carregar_listas_existentes)

    def _criar_widgets(self):
        lbl_title = tk.Label(self, text="GERAÇÃO DE LISTA DE PREÇOS DE VENDA (VIA XML)", font=("Segoe UI", 14, "bold"), fg="#E67E22")
        lbl_title.pack(anchor=tk.W, pady=(0, 10))

        # Frame de Configuração da Lista
        frame_lista = ttk.LabelFrame(self, text="Configuração da Lista de Preços", padding="10")
        frame_lista.pack(fill=tk.X, pady=5)

        self.var_modo = tk.StringVar(self, value="EXISTENTE")

        # Modo Atualizar Existente
        rb_existente = ttk.Radiobutton(frame_lista, text="Atualizar Lista Existente:", variable=self.var_modo, value="EXISTENTE", command=self._toggle_modo)
        rb_existente.grid(row=0, column=0, sticky=tk.W, padx=5)
        
        self.cb_listas = DropdownListbox(frame_lista, width=50)
        self.cb_listas.grid(row=0, column=1, columnspan=3, padx=5, sticky=tk.W)

        # Modo Nova Lista
        rb_nova = ttk.Radiobutton(frame_lista, text="Criar Nova Lista:", variable=self.var_modo, value="NOVA", command=self._toggle_modo)
        rb_nova.grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)

        ttk.Label(frame_lista, text="Código:").grid(row=1, column=1, sticky=tk.E, padx=5)
        self.ent_cod_lista = ttk.Entry(frame_lista, width=10, state=tk.DISABLED)
        self.ent_cod_lista.grid(row=1, column=2, sticky=tk.W, padx=5)

        ttk.Label(frame_lista, text="Descrição:").grid(row=1, column=3, sticky=tk.E, padx=5)
        self.ent_desc_lista = ttk.Entry(frame_lista, width=40, state=tk.DISABLED)
        self.ent_desc_lista.grid(row=1, column=4, sticky=tk.W, padx=5)

        # Seleção de Arquivos
        frame_dir = ttk.Frame(self)
        frame_dir.pack(fill=tk.X, pady=10)
        
        self.ent_pasta = ttk.Entry(frame_dir, width=60)
        self.ent_pasta.pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_dir, text="📁 Pasta", command=self._selecionar_pasta).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_dir, text="📄 Arquivos", command=self._selecionar_arquivos).pack(side=tk.LEFT, padx=2)
        
        self.btn_analisar = ttk.Button(frame_dir, text="🔍 Extrair Preços do XML", command=self._iniciar_analise)
        self.btn_analisar.pack(side=tk.RIGHT, padx=5)

        self.lbl_status = ttk.Label(self, text="Aguardando arquivos...", font=("Segoe UI", 9))
        self.lbl_status.pack(anchor=tk.W)

        # Controles da Grade
        frame_meio = ttk.Frame(self)
        frame_meio.pack(fill=tk.X, pady=5)
        ttk.Button(frame_meio, text="☑ Marcar Todos", command=self._marcar_todos).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_meio, text="☐ Desmarcar Todos", command=self._desmarcar_todos).pack(side=tk.LEFT, padx=5)
        ttk.Label(frame_meio, text="💡 DICA: Dê um duplo clique na linha do produto para editar o Preço manualmente.", foreground="#003399", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=15)

        # Grade (Treeview)
        frame_grade = ttk.Frame(self)
        frame_grade.pack(fill=tk.BOTH, expand=True, pady=5)

        self.tree = ttk.Treeview(frame_grade, columns=self.colunas, show="headings")
        
        larguras = [50, 150, 100, 350, 100]
        for col, larg in zip(self.colunas, larguras):
            self.tree.heading(col, text=col + " ↕", command=lambda c=col: self._sort_treeview(c))
            anchor = tk.W if col == "PRODUTO ERP" else tk.CENTER
            self.tree.column(col, width=larg, anchor=anchor)

        self.tree.tag_configure('OK', background='#EAFAF1')
        self.tree.tag_configure('ERRO', background='#FADBD8')

        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)
        self.tree.bind("<Double-1>", self._on_tree_double_click)

        scroll_y = ttk.Scrollbar(frame_grade, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        # Rodapé
        frame_fim = ttk.Frame(self)
        frame_fim.pack(fill=tk.X, pady=10)
        ttk.Button(frame_fim, text="⬅ VOLTAR", command=self._fechar_tela).pack(side=tk.LEFT, padx=5)
        
        self.btn_salvar = tk.Button(frame_fim, text="💾 INJETAR PREÇOS NO ERP", font=("Segoe UI", 9, "bold"), bg="#27AE60", fg="white", cursor="hand2", state=tk.DISABLED, command=self._salvar_banco)
        self.btn_salvar.pack(side=tk.RIGHT, padx=5)

    def _toggle_modo(self):
        if self.var_modo.get() == "NOVA":
            self.cb_listas.config_state(tk.DISABLED)
            self.ent_cod_lista.config(state=tk.NORMAL)
            self.ent_desc_lista.config(state=tk.NORMAL)
        else:
            self.cb_listas.config_state("readonly")
            self.ent_cod_lista.config(state=tk.DISABLED)
            self.ent_desc_lista.config(state=tk.DISABLED)

    def _carregar_listas_existentes(self):
        try:
            with FirebirdService(self.config_db) as fb:
                sql = """
                    SELECT LIS_CODIGO, LIS_DESCRICAO, LIS_DATA
                    FROM TABELA_LISTA_PRECOS
                    WHERE LIS_EMPRESA = ? AND LIS_FILIAL = ?
                    ORDER BY LIS_CODIGO, LIS_DATA DESC
                """
                listas = fb.query(sql, [int(self.empresa), int(self.filial)])
                
                self.listas_existentes = []
                self.listas_info = {}
                bold_items = []
                cod_ja_visto = set()
                for lst in listas:
                    cod = str(lst.get('lis_codigo', '')).strip()
                    desc = str(lst.get('lis_descricao', '')).strip()
                    data = lst.get('lis_data', '')
                    rotulo = f"{cod} - {desc} ({data})"
                    if rotulo not in self.listas_existentes:
                        self.listas_existentes.append(rotulo)
                    if cod not in cod_ja_visto:
                        bold_items.append(rotulo)
                        cod_ja_visto.add(cod)
                    self.listas_info[rotulo] = {'codigo': cod, 'descricao': desc, 'data': data, 'serie': '1'}
                
                self.cb_listas.set_items(self.listas_existentes, bold_items=bold_items)
                if self.listas_existentes:
                    self.cb_listas.current(0)
        except Exception as e:
            print(f"Aviso: Não foi possível carregar as listas de preços. {e}")

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

    def _on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            if column == "#1":
                item = self.tree.identify_row(event.y)
                if not item: return
                valores = list(self.tree.item(item, "values"))
                if "NÃO CADASTRADO" in valores[1]: return # Impede marcar os sem cadastro
                
                valores[0] = "☑" if valores[0] == "☐" else "☐"
                self.tree.item(item, values=valores)

    def _on_tree_double_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            item = self.tree.identify_row(event.y)
            if not item: return
            valores = list(self.tree.item(item, "values"))
            if "NÃO CADASTRADO" in valores[1]: return

            novo_preco = simpledialog.askstring("Editar Preço", f"Informe o novo preço para:\n{valores[3]}", initialvalue=valores[4])
            if novo_preco is not None:
                try:
                    preco_float = float(novo_preco.replace(',', '.'))
                    valores[4] = f"{preco_float:.2f}"
                    self.tree.item(item, values=valores)
                except ValueError:
                    messagebox.showwarning("Erro", "Valor inválido. Use apenas números e ponto.")

    def _marcar_todos(self):
        for item in self.tree.get_children():
            v = list(self.tree.item(item, "values"))
            if "NÃO CADASTRADO" not in v[1]:
                v[0] = "☑"
                self.tree.item(item, values=v)

    def _desmarcar_todos(self):
        for item in self.tree.get_children():
            v = list(self.tree.item(item, "values"))
            if "NÃO CADASTRADO" not in v[1]:
                v[0] = "☐"
                self.tree.item(item, values=v)

    def _sort_treeview(self, col):
        self._sort_directions[col] = not self._sort_directions[col]
        reverse = self._sort_directions[col]
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        def valor_para_ordenar(val):
            v = str(val).strip()
            if not v or v == '-': return -999999 if reverse else 999999
            try: return float(v.replace(',', '.'))
            except ValueError: return v.lower()
        l.sort(key=lambda t: valor_para_ordenar(t[0]), reverse=reverse)
        for index, (_, k) in enumerate(l): self.tree.move(k, '', index)
        for c in self.colunas:
            arrow = " ▼" if self._sort_directions[c] else " ▲" if c == col else " ↕"
            self.tree.heading(c, text=c + arrow, command=lambda x=c: self._sort_treeview(x))

    def _iniciar_analise(self):
        if not self.pasta_xmls and not self.arquivos_selecionados:
            return messagebox.showwarning("Atenção", "Selecione XMLs válidos.")
            
        self.btn_analisar.config(state=tk.DISABLED)
        self.btn_salvar.config(state=tk.DISABLED)
        self.lbl_status.config(text="Lendo arquivos XML... (Isso pode demorar dependendo da quantidade)")
        for item in self.tree.get_children(): self.tree.delete(item)
        threading.Thread(target=self._pipeline_bg, daemon=True).start()

    def _pipeline_bg(self):
        try:
            itens_xml = []
            if self.arquivos_selecionados:
                for arq in self.arquivos_selecionados:
                    try: itens_xml.extend(parse_nfe(arq)['itens'])
                    except Exception: logging.warning(f"Erro ao processar XML: {arq}")
            else:
                itens_xml = parse_nfe_folder(self.pasta_xmls)

            # Filtra apenas o preço mais recente/último ocorrido por cProd
            mapa_produtos_xml = {}
            for item in itens_xml:
                c_prod = str(item.get('c_prod') or item.get('cProd') or '').strip()
                if c_prod:
                    mapa_produtos_xml[c_prod] = item
                    
            lista_unicos = list(mapa_produtos_xml.values())
            
            self.parent.after(0, lambda: self.lbl_status.config(text="Cruzando itens com o ERP..."))

            # Consulta o Firebird
            produtos_erp_por_codigo = {}
            produtos_erp_por_auxiliar = {}
            try:
                with FirebirdService(self.config_db) as fb:
                    sql = "SELECT PRODUTO_CODIGO, PRODUTO_COD_AUXILIAR, PRODUTO_DESCRICAO FROM TABELA_PRODUTO WHERE PRODUTO_EMPRESA = ? AND PRODUTO_FILIAL = ?"
                    db_data = fb.query(sql, [int(self.empresa), int(self.filial)])
                    for row in db_data:
                        cod = str(row.get('produto_codigo', '')).strip()
                        cod_aux = str(row.get('produto_cod_auxiliar', '')).strip()
                        desc = str(row.get('produto_descricao', '')).strip()
                        
                        if cod:
                            produtos_erp_por_codigo[cod] = {'codigo': cod, 'descricao': desc}
                        if cod_aux:
                            produtos_erp_por_auxiliar[cod_aux] = {'codigo': cod, 'descricao': desc}
            except Exception as e:
                self.parent.after(0, lambda err=e: messagebox.showwarning("Erro DB", f"Falha ao consultar ERP:\n{err}"))

            self.dados_analisados = []
            for item in lista_unicos:
                cod_xml = str(item.get('c_prod', item.get('cProd', ''))).strip()
                
                v_preco = item.get('vUnCom') or item.get('v_un_com') or 0.0
                try:
                    preco_xml = float(v_preco)
                except ValueError:
                    preco_xml = 0.0

                if cod_xml in produtos_erp_por_auxiliar:
                    cod_erp = produtos_erp_por_auxiliar[cod_xml]['codigo']
                    desc_erp = produtos_erp_por_auxiliar[cod_xml]['descricao']
                    status = "✅ VINCULADO"
                    tag = "OK"
                    sel = "☑"
                elif cod_xml in produtos_erp_por_codigo:
                    cod_erp = produtos_erp_por_codigo[cod_xml]['codigo']
                    desc_erp = produtos_erp_por_codigo[cod_xml]['descricao']
                    status = "✅ VINCULADO"
                    tag = "OK"
                    sel = "☑"
                else:
                    cod_erp = cod_xml
                    status = "❌ NÃO CADASTRADO"
                    tag = "ERRO"
                    desc_erp = "Produto não existe no ERP (Crie-o primeiro)"
                    sel = "☐"

                self.dados_analisados.append({
                    'sel': sel,
                    'status': status,
                    'tag': tag,
                    'cod_erp': cod_erp,
                    'desc_erp': desc_erp,
                    'preco': f"{preco_xml:.2f}"
                })

            self.parent.after(0, self._renderizar_resultados)
        except Exception as e:
            self.parent.after(0, lambda err=e: messagebox.showerror("Erro", str(err)))
            self.parent.after(0, lambda: self.btn_analisar.config(state=tk.NORMAL))

    def _renderizar_resultados(self):
        chunk_size = 200
        total = len(self.dados_analisados)
        
        def render_chunk(start_idx):
            end_idx = min(start_idx + chunk_size, total)
            for i in range(start_idx, end_idx):
                item = self.dados_analisados[i]
                self.tree.insert("", tk.END, values=(
                    item['sel'], item['status'], item['cod_erp'], item['desc_erp'], item['preco']
                ), tags=(item['tag'],))
                
            if end_idx < total:
                self.lbl_status.config(text=f"Renderizando {end_idx}/{total} produtos na tabela...")
                self.parent.after(10, render_chunk, end_idx)
            else:
                self.btn_analisar.config(state=tk.NORMAL)
                if any(i['tag'] == 'OK' for i in self.dados_analisados):
                    self.btn_salvar.config(state=tk.NORMAL)
                self.lbl_status.config(text=f"Pronto. {total} produtos únicos encontrados no XML.")

        if total > 0:
            render_chunk(0)
        else:
            self.btn_analisar.config(state=tk.NORMAL)
            self.lbl_status.config(text="Pronto. Nenhum produto válido encontrado no XML.")

    def _salvar_banco(self):
        modo = self.var_modo.get()
        
        if modo == "EXISTENTE":
            selecao = self.cb_listas.get()
            if not selecao: return messagebox.showwarning("Atenção", "Selecione uma lista existente.")
            info = self.listas_info.get(selecao)
            if not info:
                return messagebox.showerror("Erro", "Lista selecionada não encontrada.")
            lis_codigo = info['codigo']
            lis_descricao = info['descricao']
            lis_data = info['data']
            lis_serie = info['serie']
        else:
            lis_codigo = self.ent_cod_lista.get().strip()
            lis_descricao = self.ent_desc_lista.get().strip().upper()
            if not lis_codigo or not lis_codigo.isdigit():
                return messagebox.showwarning("Atenção", "Informe um Código numérico válido para a Nova Lista.")
            if not lis_descricao:
                return messagebox.showwarning("Atenção", "Informe uma Descrição para a Nova Lista.")
            lis_data = datetime.date.today().isoformat()
            lis_serie = '1'

        itens_salvar = []
        for item in self.tree.get_children():
            v = self.tree.item(item, 'values')
            if v[0] == "☑" and "VINCULADO" in v[1]:
                itens_salvar.append({
                    'produto': v[2],
                    'preco': float(v[4])
                })

        if not itens_salvar:
            return messagebox.showwarning("Atenção", "Nenhum produto válido marcado para salvar.")

        if not messagebox.askyesno("Confirmar", f"Inserir/Atualizar {len(itens_salvar)} produtos na Lista de Preços {lis_codigo}?"):
            return

        def task():
            self.parent.after(0, lambda: self.lbl_status.config(text="Salvando no banco de dados..."))
            self.parent.after(0, lambda: self.btn_salvar.config(state=tk.DISABLED))
            try:
                hoje = datetime.date.today().isoformat()
                inseridos = 0
                
                with FirebirdService(self.config_db) as fb:
                    cursor = None
                    if hasattr(fb, 'conn'): cursor = fb.conn.cursor()
                    elif hasattr(fb, 'connection'): cursor = fb.connection.cursor()
                    
                    sql = """
                        UPDATE OR INSERT INTO TABELA_LISTA_PRECOS (
                            LIS_EMPRESA, LIS_FILIAL, LIS_DATA, LIS_CODIGO,
                            LIS_PRODUTO_EMPRESA, LIS_PRODUTO_FILIAL, LIS_PRODUTO,
                            LIS_DESCRICAO, LIS_PRECO, LIS_DATA_ULT_ALTERACAO
                        ) VALUES (
                            ?, ?, ?, ?,
                            ?, ?, ?,
                            ?, ?, ?
                        )                         MATCHING (LIS_EMPRESA, LIS_FILIAL, LIS_CODIGO, LIS_DATA, LIS_PRODUTO)
                    """
                    
                    for p in itens_salvar:
                        params = (
                            int(self.empresa), int(self.filial), lis_data, int(lis_codigo),
                            int(self.empresa), int(self.filial), p['produto'],
                            lis_descricao[:100], p['preco'], hoje
                        )
                        if cursor: cursor.execute(sql, params)
                        else: fb.execute(sql, params)
                        inseridos += 1
                        
                    # Força a gravação (commit) independente da estrutura da conexão na biblioteca base
                    if hasattr(fb, 'commit'):
                        fb.commit()
                    elif hasattr(fb, 'conn') and hasattr(fb.conn, 'commit'):
                        fb.conn.commit()
                    elif hasattr(fb, 'connection') and hasattr(fb.connection, 'commit'):
                        fb.connection.commit()
                    elif hasattr(fb, 'db') and hasattr(fb.db, 'commit'):
                        fb.db.commit()
                    
                self.parent.after(0, lambda: messagebox.showinfo("Sucesso", f"Lista de preços gerada com sucesso!\n{inseridos} produtos afetados."))
                self.parent.after(0, self._carregar_listas_existentes)
            except Exception as e:
                self.parent.after(0, lambda err=e: messagebox.showerror("Erro Banco", f"Falha ao salvar no banco:\n{err}"))
            finally:
                self.parent.after(0, lambda: self.lbl_status.config(text="Pronto."))
                self.parent.after(0, lambda: self.btn_salvar.config(state=tk.NORMAL))

        threading.Thread(target=task, daemon=True).start()
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import configparser
import utils.xml_reader as xml_reader
import utils.firebird_conn as fb
import re
import threading
import csv

class ToolTip(object):
    """Cria uma caixa de texto (tooltip) ao passar o mouse sobre o widget."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        self.id = None
        self.x = self.y = 0
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)

    def enter(self, event=None):
        self.schedule()

    def leave(self, event=None):
        self.unschedule()
        self.hidetip()

    def schedule(self):
        self.unschedule()
        self.id = self.widget.after(500, self.showtip)

    def unschedule(self):
        id = self.id
        self.id = None
        if id:
            self.widget.after_cancel(id)

    def showtip(self, event=None):
        x, y, cx, cy = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry("+%d+%d" % (x, y))
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                         background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                         font=("tahoma", "8", "normal"))
        label.pack(ipadx=1)

    def hidetip(self):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()

class DialogoVincularCondPagto(tk.Toplevel):
    """Modal para o usuário decidir entre criar ou vincular condições de pagamento novas."""
    def __init__(self, parent, condicoes_novas, condicoes_existentes):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("Vincular Condições de Pagamento Novas")
        self.geometry("850x600")

        self.condicoes_novas = sorted(condicoes_novas)
        self.condicoes_existentes = sorted(condicoes_existentes, key=lambda x: x[1]) # Sort by description
        self.mapeamento = {}
        self.mapeamento_final = None

        self._criar_widgets()
        self._popular_listas()

    def _criar_widgets(self):
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.rowconfigure(1, weight=3)
        main_frame.rowconfigure(2, weight=2)
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(2, weight=1)

        ttk.Label(main_frame, text="Condições Novas (do XML)", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, pady=5)
        ttk.Label(main_frame, text="Condições Existentes (no ERP)", font=("Segoe UI", 10, "bold")).grid(row=0, column=2, pady=5)

        frame_novas = ttk.Frame(main_frame)
        frame_novas.grid(row=1, column=0, sticky="nsew", padx=(0, 5))
        scroll_novas = ttk.Scrollbar(frame_novas, orient=tk.VERTICAL)
        self.list_novas = tk.Listbox(frame_novas, selectmode=tk.EXTENDED, yscrollcommand=scroll_novas.set)
        scroll_novas.config(command=self.list_novas.yview)
        scroll_novas.pack(side=tk.RIGHT, fill=tk.Y)
        self.list_novas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        frame_existentes = ttk.Frame(main_frame)
        frame_existentes.grid(row=1, column=2, sticky="nsew", padx=(5, 0))
        scroll_existentes = ttk.Scrollbar(frame_existentes, orient=tk.VERTICAL)
        self.list_existentes = tk.Listbox(frame_existentes, selectmode=tk.SINGLE, yscrollcommand=scroll_existentes.set)
        scroll_existentes.config(command=self.list_existentes.yview)
        scroll_existentes.pack(side=tk.RIGHT, fill=tk.Y)
        self.list_existentes.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        frame_botoes = ttk.Frame(main_frame)
        frame_botoes.grid(row=1, column=1, padx=10)
        ttk.Button(frame_botoes, text="Vincular →", command=self._vincular).pack(pady=5)
        ttk.Button(frame_botoes, text="Criar Nova →", command=self._marcar_para_criar).pack(pady=5)
        ttk.Button(frame_botoes, text="Ignorar (Em branco) →", command=self._marcar_para_ignorar).pack(pady=5)
        ttk.Button(frame_botoes, text="← Desfazer", command=self._desfazer).pack(pady=20)

        frame_preview = ttk.LabelFrame(main_frame, text="Mapeamento a ser Aplicado", padding=5)
        frame_preview.grid(row=2, column=0, columnspan=3, sticky="ew", pady=10)
        frame_preview.columnconfigure(0, weight=1)
        
        self.tree_preview = ttk.Treeview(frame_preview, columns=("Ação", "Vinculado a"), show="headings", height=5)
        self.tree_preview.heading("#0", text="Condição Nova (XML)")
        self.tree_preview.heading("Ação", text="Ação")
        self.tree_preview.heading("Vinculado a", text="Vinculado a (ID - Descrição)")
        self.tree_preview.column("#0", width=250)
        self.tree_preview.column("Ação", width=100, anchor=tk.CENTER)
        self.tree_preview.column("Vinculado a", width=350)
        self.tree_preview.pack(fill=tk.X, expand=True)

        frame_fim = ttk.Frame(self, padding=10)
        frame_fim.pack(fill=tk.X)
        ttk.Button(frame_fim, text="Cancelar", command=self._cancelar).pack(side=tk.LEFT)
        ttk.Button(frame_fim, text="Confirmar e Importar", command=self._confirmar, style="Accent.TButton").pack(side=tk.RIGHT)

    def _popular_listas(self):
        for item in self.condicoes_novas: self.list_novas.insert(tk.END, item)
        for cod, desc in self.condicoes_existentes: self.list_existentes.insert(tk.END, f"{cod} - {desc}")

    def _atualizar_preview(self):
        for i in self.tree_preview.get_children(): self.tree_preview.delete(i)
        for cond_nova, acao in sorted(self.mapeamento.items()):
            if acao == 'CRIAR':
                vinculado_a, acao_desc = "", "CRIAR NOVA"
            elif acao == 'IGNORAR':
                vinculado_a, acao_desc = "", "IGNORAR (EM BRANCO)"
            else:
                desc_vinculada = next((desc for cod, desc in self.condicoes_existentes if cod == acao), "N/A")
                vinculado_a, acao_desc = f"{acao} - {desc_vinculada}", "VINCULAR"
            self.tree_preview.insert("", tk.END, text=cond_nova, values=(acao_desc, vinculado_a))

    def _vincular(self):
        sel_novas_idx = self.list_novas.curselection()
        sel_existente_idx = self.list_existentes.curselection()
        if not sel_novas_idx or not sel_existente_idx: return messagebox.showwarning("Aviso", "Selecione itens em ambas as listas.", parent=self)
        cod_existente, _ = self.condicoes_existentes[sel_existente_idx[0]]
        for i in reversed(sel_novas_idx): self.mapeamento[self.list_novas.get(i)] = cod_existente; self.list_novas.delete(i)
        self._atualizar_preview()

    def _marcar_para_criar(self):
        sel_novas_idx = self.list_novas.curselection()
        if not sel_novas_idx: return messagebox.showwarning("Aviso", "Selecione uma condição para marcar para criação.", parent=self)
        for i in reversed(sel_novas_idx): self.mapeamento[self.list_novas.get(i)] = 'CRIAR'; self.list_novas.delete(i)
        self._atualizar_preview()

    def _marcar_para_ignorar(self):
        sel_novas_idx = self.list_novas.curselection()
        if not sel_novas_idx: return messagebox.showwarning("Aviso", "Selecione uma condição para ignorar.", parent=self)
        for i in reversed(sel_novas_idx): self.mapeamento[self.list_novas.get(i)] = 'IGNORAR'; self.list_novas.delete(i)
        self._atualizar_preview()

    def _desfazer(self):
        sel_preview = self.tree_preview.selection()
        if not sel_preview: return messagebox.showwarning("Aviso", "Selecione um mapeamento para desfazer.", parent=self)
        for item_id in sel_preview:
            cond_nova = self.tree_preview.item(item_id, 'text')
            if cond_nova in self.mapeamento: del self.mapeamento[cond_nova]; self.list_novas.insert(tk.END, cond_nova)
        self._atualizar_preview()

    def _confirmar(self):
        if self.list_novas.size() > 0:
            resposta = messagebox.askyesnocancel(
                "Atenção", 
                f"Ainda existem {self.list_novas.size()} condições de pagamento na lista sem mapeamento.\n\n"
                "• SIM: Para CRIAR essas condições no sistema.\n"
                "• NÃO: Para IGNORAR e deixá-las em branco no cadastro.\n"
                "• CANCELAR: Para voltar e revisar o mapeamento.", 
                parent=self
            )
            if resposta is True:
                for item in self.list_novas.get(0, tk.END): self.mapeamento[item] = 'CRIAR'
            elif resposta is False:
                for item in self.list_novas.get(0, tk.END): self.mapeamento[item] = 'IGNORAR'
            else:
                return
        self.mapeamento_final = self.mapeamento
        self.destroy()

    def _cancelar(self):
        self.mapeamento_final = None
        self.destroy()

class TelaNFe(ttk.Frame):
    def __init__(self, parent, callback_voltar=None):
        super().__init__(parent, padding="10")
        self.parent = parent
        self.callback_voltar = callback_voltar
        self.pack(fill=tk.BOTH, expand=True)
        print("✅ Instância de TelaNFe criada.")

        self.xml_files = []

        self.config = configparser.ConfigParser()
        self.config.read('config.ini', encoding='utf-8')

        self._criar_widgets()
        self._carregar_config_iniciais()

    def _criar_widgets(self):
        # Header do Módulo
        lbl_title = tk.Label(self, text="IMPORTAÇÃO DE CLIENTES/FORNECEDORES VIA XML NF-e", font=("Segoe UI", 14, "bold"), fg="#003399")
        lbl_title.pack(anchor=tk.W, pady=(0, 10))

        # Frame Configurações Iniciais
        frame_config = ttk.LabelFrame(self, text="Parâmetros Base", padding="10")
        frame_config.pack(fill=tk.X, pady=5)

        ttk.Label(frame_config, text="Empresa:").grid(row=0, column=0, padx=5)
        self.ent_empresa = ttk.Entry(frame_config, width=10)
        self.ent_empresa.grid(row=0, column=1, padx=5)

        ttk.Label(frame_config, text="Filial:").grid(row=0, column=2, padx=5)
        self.ent_filial = ttk.Entry(frame_config, width=10)
        self.ent_filial.grid(row=0, column=3, padx=5)

        # Ações Topo
        frame_top = ttk.Frame(self)
        frame_top.pack(fill=tk.X, pady=5)

        self.ent_pasta = ttk.Entry(frame_top, width=40)
        self.ent_pasta.pack(side=tk.LEFT, padx=5)
        
        self.btn_add_pasta = ttk.Button(frame_top, text="📁 Pasta", command=self._selecionar_pasta)
        self.btn_add_pasta.pack(side=tk.LEFT, padx=2)
        
        self.btn_add_xml = ttk.Button(frame_top, text="📄 Arquivos", command=self._selecionar_arquivos)
        self.btn_add_xml.pack(side=tk.LEFT, padx=2)
        
        self.btn_analisar = ttk.Button(frame_top, text="🔍 LER XMLs", command=self._adicionar_xmls)
        self.btn_analisar.pack(side=tk.LEFT, padx=5)
        
        self.btn_limpar = ttk.Button(frame_top, text="🗑 Limpar Lista", command=self._limpar_lista)
        self.btn_limpar.pack(side=tk.LEFT, padx=5)
        
        self.lbl_total = ttk.Label(frame_top, text="Total: 0 arquivo(s)", font=("Segoe UI", 10, "bold"))
        self.lbl_total.pack(side=tk.RIGHT, padx=5)

        self.progresso = ttk.Progressbar(frame_top, orient=tk.HORIZONTAL, length=150, mode='determinate')
        self.progresso.pack(side=tk.RIGHT, padx=10)

        # Grade (Treeview)
        frame_grade = ttk.Frame(self)
        frame_grade.pack(fill=tk.BOTH, expand=True, pady=10)

        colunas = ("SELECIONAR", "NF", "TIPO", "CNPJ/CPF", "RAZÃO SOCIAL", "CÓD. ANTIGO", "CONDIÇÃO PGTO", "CÓD. ERP", "STATUS")
        self.tree = ttk.Treeview(frame_grade, columns=colunas, show="headings")
        
        larguras = [80, 80, 60, 140, 250, 80, 120, 80, 160]
        for col, larg in zip(colunas, larguras):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=larg, anchor=tk.CENTER if col != "RAZÃO SOCIAL" else tk.W)

        # Configura as cores (Tags) para os status
        self.tree.tag_configure('NOVO', background='#EAFAF1') # Verde clarinho
        self.tree.tag_configure('CADASTRADO', background='#FADBD8') # Vermelho clarinho

        # Evento de clique para marcar/desmarcar a caixinha (Checkbox)
        self.tree.bind("<ButtonRelease-1>", self._toggle_checkbox)

        scroll_y = ttk.Scrollbar(frame_grade, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        # Ações Meio
        frame_mid = ttk.Frame(self)
        frame_mid.pack(fill=tk.X, pady=5)

        ttk.Button(frame_mid, text="☑ Marcar Novos", command=self._marcar_novos).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_mid, text="☐ Desmarcar Todos", command=self._desmarcar_todos).pack(side=tk.LEFT, padx=5)

        self.var_auto_criar_cond_pagto = tk.BooleanVar(self, value=True)
        self.chk_auto_criar_cond_pagto = ttk.Checkbutton(frame_mid, text="Criar Cond. Pgto. Automaticamente", variable=self.var_auto_criar_cond_pagto, onvalue=True, offvalue=False)
        self.chk_auto_criar_cond_pagto.pack(side=tk.RIGHT, padx=10)

        # Tooltip para a flag de condição de pagamento
        texto_tooltip = "Se marcado: Cria condições de pagamento inexistentes automaticamente no banco.\nSe desmarcado: Abre janela para vincular as condições do XML com as já existentes."
        ToolTip(self.chk_auto_criar_cond_pagto, texto_tooltip)

        self.btn_importar = ttk.Button(frame_mid, text="🚀 Importar Selecionados", state=tk.DISABLED, command=self._importar_selecionados)
        self.btn_importar.pack(side=tk.RIGHT, padx=5)

        # Log
        frame_log = ttk.LabelFrame(self, text="Log de Importação", padding="5")
        frame_log.pack(fill=tk.X, pady=5)
        self.txt_log = tk.Text(frame_log, height=6, state=tk.DISABLED, bg="#F9F9F9")
        self.txt_log.pack(fill=tk.BOTH, expand=True)

        # Rodapé
        frame_fim = ttk.Frame(self)
        frame_fim.pack(fill=tk.X, pady=10)

        ttk.Button(frame_fim, text="⬅ VOLTAR", command=self._fechar_tela).pack(side=tk.LEFT, padx=5)

    def _toggle_checkbox(self, event):
        """Inverte o valor do checkbox se o usuário clicar na primeira coluna."""
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            if column == "#1": # Coluna 'SELECIONAR'
                item = self.tree.identify_row(event.y)
                valores = list(self.tree.item(item, "values"))
                valores[0] = "☑" if valores[0] == "☐" else "☐"
                self.tree.item(item, values=valores)

    def _marcar_novos(self):
        """Marca todos os que estão com status NOVO."""
        for item in self.tree.get_children():
            valores = list(self.tree.item(item, "values"))
            if "NOVO" in valores[-1]:
                valores[0] = "☑"
            self.tree.item(item, values=valores)

    def _desmarcar_todos(self):
        """Desmarca todos os registros da grade."""
        for item in self.tree.get_children():
            valores = list(self.tree.item(item, "values"))
            valores[0] = "☐"
            self.tree.item(item, values=valores)

    def _aplicar_mascara_cpf_cnpj(self, documento: str) -> str:
        doc = ''.join(filter(str.isdigit, str(documento)))
        if len(doc) == 11:
            return f"{doc[:3]}.{doc[3:6]}.{doc[6:9]}-{doc[9:]}"
        elif len(doc) == 14:
            return f"{doc[:2]}.{doc[2:5]}.{doc[5:8]}/{doc[8:12]}-{doc[12:]}"
        return documento

    def _carregar_config_iniciais(self):
        # Puxa do módulo NF-e, mas se não existir, pega do que foi usado no Plano de Contas
        empresa = self.config.get('NFE', 'empresa', fallback=self.config.get('IMPORTACAO', 'empresa', fallback='1'))
        filial = self.config.get('NFE', 'filial', fallback=self.config.get('IMPORTACAO', 'filial', fallback='1'))
        self.ent_empresa.insert(0, empresa)
        self.ent_filial.insert(0, filial)

    def _salvar_config(self):
        config = configparser.ConfigParser()
        config.read('config.ini', encoding='utf-8')
        if not config.has_section('NFE'):
            config.add_section('NFE')
        config.set('NFE', 'empresa', self.ent_empresa.get())
        config.set('NFE', 'filial', self.ent_filial.get())
        with open('config.ini', 'w', encoding='utf-8') as f:
            config.write(f)
        self.config = config

    def _selecionar_pasta(self):
        pasta = filedialog.askdirectory()
        if pasta:
            self.ent_pasta.delete(0, tk.END)
            self.ent_pasta.insert(0, pasta)
            self.pasta_xmls = pasta
            self.arquivos_selecionados = []

    def _selecionar_arquivos(self):
        arquivos = filedialog.askopenfilenames(filetypes=[("Arquivos XML", "*.xml")])
        if arquivos:
            self.ent_pasta.delete(0, tk.END)
            self.ent_pasta.insert(0, f"{len(arquivos)} arquivo(s) selecionado(s)")
            self.arquivos_selecionados = list(arquivos)
            self.pasta_xmls = ""

    def _adicionar_xmls(self):
        if not hasattr(self, 'pasta_xmls'): self.pasta_xmls = ""
        if not hasattr(self, 'arquivos_selecionados'): self.arquivos_selecionados = []
            
        arquivos = []
        if self.arquivos_selecionados:
            arquivos = self.arquivos_selecionados
        elif self.pasta_xmls:
            import glob
            import os
            pattern = os.path.join(self.pasta_xmls, '**', '*.xml')
            arquivos = glob.glob(pattern, recursive=True)
            
        if not arquivos:
            messagebox.showwarning("Atenção", "Selecione uma pasta ou arquivos XML válidos.")
            return
            
        try:
            emp = int(self.ent_empresa.get())
            fil = int(self.ent_filial.get())
        except ValueError:
            messagebox.showerror("Erro", "Os campos Empresa e Filial devem ser numéricos.")
            return
        
        self._salvar_config()
        self._estado_botoes(tk.DISABLED)

        # Lê os CNPJs que já estão na grade para não duplicar
        documentos_existentes = set()
        for item in self.tree.get_children():
            doc = self.tree.item(item, "values")[3] # Índice 3 é a coluna CNPJ/CPF
            doc_limpo = re.sub(r'\D', '', doc)
            documentos_existentes.add(doc_limpo)
        
        self.progresso['value'] = 0
        self.lbl_total.config(text="Iniciando leitura...")

        # Executa o processamento pesado em background
        thread = threading.Thread(
            target=self._processar_arquivos_bg,
            args=(arquivos, emp, fil, documentos_existentes),
            daemon=True
        )
        thread.start()

    def _processar_arquivos_bg(self, arquivos, emp, fil, documentos_existentes):
        conn = None
        try:
            conn = fb.conectar()
            clientes_db = fb.buscar_clientes_existentes(conn, emp, fil)
        except Exception as e:
            self.parent.after(0, lambda: messagebox.showerror("Erro de Banco", f"Falha ao checar cadastros no Firebird:\n{e}"))
            self.parent.after(0, self._finalizar_carregamento_erro)
            return
        finally:
            if conn:
                conn.close()

        resultados = []
        erros_leitura = []
        total = len(arquivos)

        for i, arq in enumerate(arquivos):
            nome_arq = arq.split('/')[-1]
            try:
                dados_xml = xml_reader.ler_nfe(arq)
                for reg in dados_xml:
                    try:
                        doc_limpo = str(reg.get('documento') or '').strip()
                        
                        if not doc_limpo or doc_limpo in documentos_existentes:
                            continue # Ignora duplicações ou XMLs sem CNPJ/CPF
                            
                        documentos_existentes.add(doc_limpo)
                        
                        # Extrair código antigo da Razão Social (Aceita "123 - Nome" ou "123-Nome")
                        razao_limpa = str(reg.get('razao') or '').strip()
                        match = re.match(r'^(\d+)\s*[-–]\s*(.+)$', razao_limpa)
                        if match:
                            reg['cf_cod_antigo'] = match.group(1)
                            reg['razao'] = match.group(2).strip()
                        else:
                            reg['cf_cod_antigo'] = None

                        if doc_limpo in clientes_db:
                            status, check, tag = "JÁ CADASTRADO", "☐", "CADASTRADO"
                            cod_erp = clientes_db[doc_limpo]
                        else:
                            status, check, tag = "NOVO - IMPORTAR", "☑", "NOVO"
                            cod_erp = "-"
                            
                        cond_pagto_desc = reg.get('condicao_pagamento_desc', 'N/I')
                        documento_formatado = reg.get('documento_formatado')
                        if not documento_formatado:
                            documento_formatado = self._aplicar_mascara_cpf_cnpj(doc_limpo)
                            reg['documento_formatado'] = documento_formatado
                        resultados.append({
                            'check': check, 'tipo': reg.get('tipo', 'XML NF-e'), 'documento': doc_limpo,
                            'documento_formatado': documento_formatado,
                            'razao': reg.get('razao', ''), 'status': status, 'tag': tag,
                            'cod_erp': cod_erp,
                            'cond_pagto_desc': cond_pagto_desc,
                            'reg_completo': reg
                        })
                    except Exception as e_reg:
                        erros_leitura.append(f"⚠️ Aviso no cliente do arquivo {nome_arq}: {e_reg}")
            except Exception as e:
                erros_leitura.append(f"❌ Falha ao ler XML {nome_arq}: {e}")
                
            # Atualiza a barra de progresso no frontend de forma segura (a cada 15 arquivos ou no último)
            if i % 15 == 0 or i == total - 1:
                self.parent.after(0, self._atualizar_progresso, i + 1, total)

        # Devolve o resultado processado para a thread principal construir a árvore
        self.parent.after(0, self._finalizar_carregamento, arquivos, resultados, erros_leitura)

    def _atualizar_progresso(self, atual, total):
        percent = (atual / total) * 100
        self.progresso['value'] = percent
        self.lbl_total.config(text=f"Lendo: {atual}/{total} ({percent:.1f}%)")

    def _finalizar_carregamento_erro(self):
        self.lbl_total.config(text=f"Total: {len(self.xml_files)} arquivo(s)")
        self.progresso['value'] = 0
        self._estado_botoes(tk.NORMAL)

    def _finalizar_carregamento(self, novos_arquivos, resultados, erros_leitura=None):
        self.xml_files.extend(novos_arquivos)
        
        if not hasattr(self, 'dados_nfe_lidos'):
            self.dados_nfe_lidos = {}

        for res in resultados:
            doc_formatado = res.get('documento_formatado', self._aplicar_mascara_cpf_cnpj(res['documento']))
            cod_ant = res['reg_completo'].get('cf_cod_antigo') or "-"
            cond_pgto = res.get('cond_pagto_desc', 'N/I')
            item_id = self.tree.insert("", tk.END, values=(res['check'], "XML NF-e", res['tipo'], doc_formatado, res['razao'], cod_ant, cond_pgto, res.get('cod_erp', '-'), res['status']), tags=(res['tag'],))
            self.dados_nfe_lidos[item_id] = res['reg_completo']

        self.lbl_total.config(text=f"Total: {len(self.xml_files)} arquivo(s)")
        self.progresso['value'] = 0
        self._estado_botoes(tk.NORMAL)
        
        if erros_leitura:
            self.txt_log.config(state=tk.NORMAL)
            for erro in erros_leitura:
                self.txt_log.insert(tk.END, f"{erro}\n")
            self.txt_log.config(state=tk.DISABLED)
            self.txt_log.see(tk.END)

        if any(r['tag'] == 'NOVO' for r in resultados):
            self.btn_importar.config(state=tk.NORMAL)
            
    def _estado_botoes(self, estado):
        self.btn_add_xml.config(state=estado)
        self.btn_add_pasta.config(state=estado)
        self.btn_analisar.config(state=estado)
        self.btn_limpar.config(state=estado)

    def _limpar_lista(self):
        self.xml_files = []
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.lbl_total.config(text="Total: 0 arquivo(s)")

    def _fechar_tela(self):
        print("❌ Instância de TelaNFe destruída.")
        self.destroy()
        if self.callback_voltar:
            self.callback_voltar()

    def _importar_selecionados(self):
        selecionados = []
        # Filtra apenas os que estão marcados com o "☑"
        for item in self.tree.get_children():
            valores = list(self.tree.item(item, "values"))
            if valores[0] == "☑" and "NOVO" in valores[-1]:
                selecionados.append((item, valores))

        if not selecionados:
            messagebox.showwarning("Aviso", "Nenhum registro NOVO foi selecionado para importação.")
            return

        emp = int(self.ent_empresa.get())
        fil = int(self.ent_filial.get())

        try:
            conn = fb.conectar()
        except Exception as e:
            messagebox.showerror("Erro de Banco", f"Falha ao conectar no Firebird:\n{e}")
            return

        mapeamento_condicoes = {}
        condicoes_existentes_tuplas = []
        auto_criar = self.var_auto_criar_cond_pagto.get()
        
        if not auto_criar:
            condicoes_xml = set(v[6] for item, v in selecionados if v[6] != 'N/I')
            
            conn_temp = None
            try:
                conn_temp = fb.conectar()
                condicoes_existentes_tuplas = fb.listar_condicoes_pagamento(conn_temp)
                condicoes_existentes_desc = {desc.strip().upper() for _, desc in condicoes_existentes_tuplas}
                
                condicoes_novas_desc = [desc for desc in condicoes_xml if desc.strip().upper() not in condicoes_existentes_desc]
                
                if condicoes_novas_desc:
                    dialog = DialogoVincularCondPagto(self, condicoes_novas_desc, condicoes_existentes_tuplas)
                    self.wait_window(dialog)
                    
                    if dialog.mapeamento_final is not None:
                        mapeamento_condicoes = dialog.mapeamento_final
                    else:
                        messagebox.showinfo("Cancelado", "Importação cancelada pelo usuário.")
                        return
                elif condicoes_xml:
                    self.txt_log.config(state=tk.NORMAL)
                    self.txt_log.insert(tk.END, "\nℹ️ Todas as condições do XML já existem no ERP. Pulando janela de mapeamento manual.\n")
                    self.txt_log.see(tk.END)
                    self.txt_log.config(state=tk.DISABLED)
            finally:
                if conn_temp: conn_temp.close()

        self.txt_log.config(state=tk.NORMAL)
        self.txt_log.insert(tk.END, "\n" + "="*45 + "\n")
        self.txt_log.insert(tk.END, f"⚙️ Criar condições automáticas: {'SIM' if auto_criar else 'NÃO'}\n")
        self.txt_log.see(tk.END)

        try:
            codigo_atual = fb.buscar_proximo_codigo_cli_for(conn, emp, fil)
            registros_para_inserir = []
            
            for item, valores in selecionados:
                reg = self.dados_nfe_lidos[item]
                
                # Busca o código interno da cidade na TABELA_CIDADES usando o IBGE
                cid_codigo = fb.buscar_cidade_ibge(conn, reg.get('cidade_ibge', ''), emp, fil)
                if not cid_codigo:
                    self.txt_log.insert(tk.END, f"⚠️ Aviso: Cidade IBGE {reg.get('cidade_ibge')} não encontrada para {reg['razao']}. Ficará em branco.\n")
                
                cond_pagto_id = None
                desc_cond = reg.get('condicao_pagamento_desc', 'N/I')
                duplicatas = reg.get('condicao_pagamento', [])

                if desc_cond != 'N/I' and duplicatas:
                    try:
                        if not auto_criar:
                            if desc_cond in mapeamento_condicoes:
                                acao = mapeamento_condicoes.get(desc_cond)
                                if acao == 'CRIAR': cond_pagto_id = fb.buscar_ou_criar_condicao_pgto(conn, duplicatas, desc_cond); self.txt_log.insert(tk.END, f"💰 Nova condição '{desc_cond}' criada com ID {cond_pagto_id}.\n")
                                elif acao == 'IGNORAR':
                                    cond_pagto_id = None
                                    self.txt_log.insert(tk.END, f"💰 Condição '{desc_cond}' ignorada (ficará em branco).\n")
                                else: cond_pagto_id = int(acao); self.txt_log.insert(tk.END, f"💰 Condição '{desc_cond}' vinculada ao ID {cond_pagto_id}.\n")
                            else:
                                cond_pagto_id = next((cod for cod, d in condicoes_existentes_tuplas if d.strip().upper() == desc_cond.strip().upper()), None)
                                if cond_pagto_id: self.txt_log.insert(tk.END, f"💰 Condição '{desc_cond}' já existente vinculada ao ID {cond_pagto_id}.\n")
                        else:
                            cond_pagto_id = fb.buscar_ou_criar_condicao_pgto(conn, duplicatas, desc_cond)
                            if cond_pagto_id: self.txt_log.insert(tk.END, f"💰 Condição pgto '{desc_cond}' (ID {cond_pagto_id}) vinculada/criada.\n")
                    except Exception as e:
                        self.txt_log.insert(tk.END, f"⚠️ Aviso: Erro ao processar condição de pagto para {reg['razao']}: {e}\n")
                elif desc_cond == 'N/I': self.txt_log.insert(tk.END, f"ℹ️ Info: XML sem dados de duplicatas/cobrança a prazo para {reg['razao']}.\n")
                
                reg_final = reg.copy()
                reg_final['codigo_gerado'] = codigo_atual
                reg_final['cidade_ibge'] = cid_codigo
                reg_final['documento_formatado'] = reg.get('documento_formatado', reg['documento'])
                reg_final['cond_pagto_id'] = cond_pagto_id
                
                # --- BLINDAGEM EXTREMA ---
                # Se o ID ficou vazio, esvaziamos a matriz de duplicatas do registro. 
                # Isso impede FISICAMENTE que o motor de banco de dados tente criar condições ignoradas.
                if cond_pagto_id is None:
                    reg_final['condicao_pagamento'] = []
                
                registros_para_inserir.append(reg_final)
                codigo_atual += 1
                
            sucesso, inseridos, erros = fb.inserir_clientes_nfe(conn, registros_para_inserir, emp, fil)
            
            if sucesso:
                messagebox.showinfo("Sucesso", f"{inseridos} registro(s) importados com sucesso!\nErros: {erros}")
                
                for (item, valores), r in zip(selecionados, registros_para_inserir):
                    if r.get('_status_importacao') == 'OK':
                        valores[0] = "☐"
                        valores[-2] = r['codigo_gerado'] # Atualiza o CÓD. ERP gerado na tabela
                        valores[-1] = "JÁ CADASTRADO"
                        self.tree.item(item, values=valores, tags=('CADASTRADO',))
                        self.txt_log.insert(tk.END, f"✅ Importado: {r['razao']} (Cód: {r['codigo_gerado']})\n")
                    else:
                        erro_msg = r.get('_erro_importacao', 'Erro desconhecido')
                        self.txt_log.insert(tk.END, f"❌ Erro em {r['razao']}: {erro_msg}\n")
                    
                self._oferecer_log(registros_para_inserir)
        except Exception as e:
            messagebox.showerror("Erro na Importação", f"Ocorreu um erro ao gravar no banco:\n{e}")
        finally:
            self.txt_log.config(state=tk.DISABLED)
            self.txt_log.see(tk.END)
            conn.close()

    def _oferecer_log(self, registros_importados=None):
        conteudo_log = self.txt_log.get("1.0", tk.END).strip()
        if not conteudo_log:
            return
            
        resp = messagebox.askyesno("Exportar Log", "Deseja salvar um arquivo .txt com o log da importação (avisos de cidades e sucessos)?")
        if resp:
            caminho = filedialog.asksaveasfilename(defaultextension=".txt", initialfile="LOG_IMPORTACAO_NFE.txt", filetypes=[("Text Files", "*.txt")])
            if caminho:
                try:
                    with open(caminho, 'w', encoding='utf-8') as f:
                        f.write(conteudo_log)
                except Exception as e:
                    messagebox.showerror("Erro", f"Erro ao salvar o arquivo de log:\n{e}")
                    
        if registros_importados:
            resp_csv = messagebox.askyesno("Exportar Relatório", "Deseja também salvar uma planilha (CSV) com os dados detalhados dos clientes importados para conferência?")
            if resp_csv:
                caminho_csv = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="RELATORIO_CLIENTES_IMPORTADOS.csv", filetypes=[("CSV Files", "*.csv")])
                if caminho_csv:
                    try:
                        with open(caminho_csv, 'w', newline='', encoding='utf-8-sig') as f:
                            # Pega as chaves ignorando dados aninhados complexos
                            chaves = [k for k in registros_importados[0].keys() if not isinstance(registros_importados[0][k], (dict, list))]
                            writer = csv.DictWriter(f, fieldnames=chaves, delimiter=';')
                            writer.writeheader()
                            for r in registros_importados:
                                linha = {k: v for k, v in r.items() if k in chaves}
                                writer.writerow(linha)
                    except Exception as e:
                        messagebox.showerror("Erro", f"Erro ao salvar o relatório CSV:\n{e}")
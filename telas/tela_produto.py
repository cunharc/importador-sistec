import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import configparser
import threading
import os
import sys
import logging
from difflib import SequenceMatcher

from utils.xml_reader import parse_nfe_folder, parse_nfe
from utils.firebird_service import FirebirdService

# Configuração do Log de Erros
logging.basicConfig(
    filename='sistema_erros.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - [Produto Sync] - %(message)s'
)

class TelaProduto(ttk.Frame):
    def __init__(self, parent, callback_voltar=None):
        super().__init__(parent, padding="10")
        self.parent = parent
        self.callback_voltar = callback_voltar
        self.pack(fill=tk.BOTH, expand=True)

        self.arquivos_selecionados = []
        self.pasta_xmls = ""
        
        # Armazena o banco de dados e os resultados em memória
        self.produtos_erp = {} 
        self.dados_analisados = []

        # Configurações do Banco
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
        
        self.colunas = ("CÓD XML", "CÓD ERP", "DESCRIÇÃO XML", "DESCRIÇÃO ERP", "NCM XML", "NCM ERP", "STATUS MATCH")
        self._sort_directions = {col: False for col in self.colunas}
        self.var_status_filtro = tk.StringVar(value="Todos")

        self._criar_widgets()

    def _criar_widgets(self):
        # === HEADER ===
        header = tk.Frame(self, bg="#16A085", padx=15, pady=8)
        header.pack(fill=tk.X, pady=(0, 10))
        tk.Label(header, text="CADASTRO E TRIBUTAÇÃO DE PRODUTOS (XML vs ERP)",
                 font=("Segoe UI", 14, "bold"), bg="#16A085", fg="white").pack(anchor=tk.W)

        # === FILE SELECTION ===
        frame_dir = ttk.Frame(self)
        frame_dir.pack(fill=tk.X, pady=3)

        tk.Label(frame_dir, text="XMLs:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 2))
        self.ent_pasta = ttk.Entry(frame_dir, font=("Segoe UI", 9))
        self.ent_pasta.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        btn_pasta = ttk.Button(frame_dir, text="📁 Pasta", command=self._selecionar_pasta)
        btn_pasta.pack(side=tk.LEFT, padx=2)
        btn_arq = ttk.Button(frame_dir, text="📄 Arquivos", command=self._selecionar_arquivos)
        btn_arq.pack(side=tk.LEFT, padx=2)
        self.btn_analisar = tk.Button(frame_dir, text="🔍 Analisar Match",
                                       font=("Segoe UI", 9, "bold"), bg="#2980b9", fg="white",
                                       cursor="hand2", padx=10, pady=1,
                                       command=self._iniciar_analise)
        self.btn_analisar.pack(side=tk.LEFT, padx=5)

        # === STATUS BAR ===
        status_bar = ttk.Frame(self)
        status_bar.pack(fill=tk.X, pady=2)

        self.lbl_status = ttk.Label(status_bar, text="Aguardando arquivos para cruzar com o Firebird...",
                                     font=("Segoe UI", 9), foreground="#555")
        self.lbl_status.pack(side=tk.LEFT, padx=2)

        ttk.Label(status_bar, text="Código:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(15, 2))
        self.var_modo_codigo = tk.StringVar(value="xml")
        rb_xml = ttk.Radiobutton(status_bar, text="Seguir XML", variable=self.var_modo_codigo, value="xml")
        rb_xml.pack(side=tk.LEFT, padx=2)
        rb_seq = ttk.Radiobutton(status_bar, text="Sequencial", variable=self.var_modo_codigo, value="sequencial")
        rb_seq.pack(side=tk.LEFT, padx=2)

        # === DASHBOARD CARDS ===
        self.frame_cards = tk.Frame(self, pady=3)
        self.frame_cards.pack(fill=tk.X)

        self.card_vermelho = self._criar_card(
            self.frame_cards, "🔴 NÃO CADASTRADOS", "0",
            "#FFF1F0", "#CF1322", "#F5222D",
            lambda e: self._filtrar_por_card("NAO_CADASTRADO")
        )
        self.card_vermelho.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

        self.card_amarelo = self._criar_card(
            self.frame_cards, "🟡 DIVERGENTES / SUGERIDOS", "0",
            "#FFFBE6", "#D48806", "#FAAD14",
            lambda e: self._filtrar_por_card("DIVERGENTE")
        )
        self.card_amarelo.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8)

        self.card_verde = self._criar_card(
            self.frame_cards, "🟢 OK (ENCONTRADOS)", "0",
            "#F6FFED", "#389E0D", "#52C41A",
            lambda e: self._filtrar_por_card("ENCONTRADO")
        )
        self.card_verde.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))

        # === TREEVIEW ===
        frame_grade = ttk.Frame(self)
        frame_grade.pack(fill=tk.BOTH, expand=True, pady=4)

        self.tree = ttk.Treeview(frame_grade, columns=self.colunas, show="headings")

        larguras = [80, 80, 250, 250, 80, 80, 130]
        for col, larg in zip(self.colunas, larguras):
            self.tree.heading(col, text=col + " ↕", command=lambda c=col: self._sort_treeview(c))
            anchor = tk.W if "DESCRIÇÃO" in col else tk.CENTER
            self.tree.column(col, width=larg, anchor=anchor)

        self.tree.tag_configure('ENCONTRADO', background='#EAFAF1')
        self.tree.tag_configure('DIVERGENTE', background='#FEF9E7')
        self.tree.tag_configure('NAO_CADASTRADO', background='#FDEDEC')
        self.tree.tag_configure('SUGERIDO', background='#D4E6F1')

        scroll_y = ttk.Scrollbar(frame_grade, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        # === FOOTER ===
        footer = tk.Frame(self, bg="#f0f0f0", padx=10, pady=6)
        footer.pack(fill=tk.X, pady=(4, 0))

        tk.Button(footer, text="⬅ VOLTAR", command=self._fechar_tela,
                  font=("Segoe UI", 9, "bold"), bg="#95a5a6", fg="white",
                  cursor="hand2", padx=12, pady=2).pack(side=tk.LEFT)

        self.btn_ambos = tk.Button(footer, text="🔄 Cadastrar + Tributar",
                                    font=("Segoe UI", 9, "bold"), bg="#8E44AD", fg="white",
                                    cursor="hand2", state=tk.DISABLED, padx=14, pady=2,
                                    command=lambda: self._injetar_firebird(modo=3))
        self.btn_ambos.pack(side=tk.RIGHT, padx=3)

        self.btn_tributar = tk.Button(footer, text="💲 Apenas Tributar",
                                       font=("Segoe UI", 9, "bold"), bg="#E67E22", fg="white",
                                       cursor="hand2", state=tk.DISABLED, padx=14, pady=2,
                                       command=lambda: self._injetar_firebird(modo=2))
        self.btn_tributar.pack(side=tk.RIGHT, padx=3)

        self.btn_cadastrar = tk.Button(footer, text="➕ Apenas Cadastrar",
                                        font=("Segoe UI", 9, "bold"), bg="#2980B9", fg="white",
                                        cursor="hand2", state=tk.DISABLED, padx=14, pady=2,
                                        command=lambda: self._injetar_firebird(modo=1))
        self.btn_cadastrar.pack(side=tk.RIGHT, padx=3)

    def _criar_card(self, parent, titulo, valor_inicial, bg_color, border_color, text_color, command):
        card = tk.Frame(parent, bg=bg_color, highlightbackground=border_color, highlightthickness=1, padx=15, pady=10, cursor="hand2")
        lbl_titulo = tk.Label(card, text=titulo, font=("Segoe UI", 10, "bold"), bg=bg_color, fg=text_color, cursor="hand2")
        lbl_titulo.pack(anchor=tk.W)
        lbl_valor = tk.Label(card, text=valor_inicial, font=("Segoe UI", 24, "bold"), bg=bg_color, fg=text_color, cursor="hand2")
        lbl_valor.pack(anchor=tk.W, pady=(0, 0))
        card.lbl_valor = lbl_valor 
        for widget in (card, lbl_titulo, lbl_valor):
            widget.bind("<Button-1>", command)
        return card

    def _filtrar_por_card(self, status_selecionado):
        self.card_vermelho.config(highlightthickness=3 if status_selecionado == "NAO_CADASTRADO" else 1)
        self.card_amarelo.config(highlightthickness=3 if status_selecionado == "DIVERGENTE" else 1)
        self.card_verde.config(highlightthickness=3 if status_selecionado == "ENCONTRADO" else 1)
        self.var_status_filtro.set(status_selecionado)
        self._renderizar_resultados()

    def _atualizar_contadores(self):
        if not hasattr(self, 'dados_analisados'): return
        self.card_vermelho.lbl_valor.config(text=str(sum(1 for item in self.dados_analisados if item['tag'] == "NAO_CADASTRADO")))
        self.card_amarelo.lbl_valor.config(text=str(sum(1 for item in self.dados_analisados if item['tag'] in ("DIVERGENTE", "SUGERIDO"))))
        self.card_verde.lbl_valor.config(text=str(sum(1 for item in self.dados_analisados if item['tag'] == "ENCONTRADO")))

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

    def _formatar_ncm(self, ncm_str):
        n = str(ncm_str).replace('.', '').strip()
        if len(n) == 8:
            return f"{n[:4]}.{n[4:6]}.{n[6:]}"
        return ncm_str if ncm_str else "-"

    def _iniciar_analise(self):
        if not self.pasta_xmls and not self.arquivos_selecionados:
            return messagebox.showwarning("Atenção", "Selecione XMLs válidos.")
            
        self.btn_analisar.config(state=tk.DISABLED)
        self.btn_cadastrar.config(state=tk.DISABLED)
        self.btn_tributar.config(state=tk.DISABLED)
        self.btn_ambos.config(state=tk.DISABLED)
        
        self.var_status_filtro.set("Todos")
        self.card_vermelho.config(highlightthickness=1)
        self.card_amarelo.config(highlightthickness=1)
        self.card_verde.config(highlightthickness=1)
        self.lbl_status.config(text="Extraindo produtos do XML e cruzando com o Firebird...")
        
        for item in self.tree.get_children(): 
            self.tree.delete(item)
            
        threading.Thread(target=self._pipeline_bg, daemon=True).start()

    def _pipeline_bg(self):
        try:
            # 1. Extrai itens dos XMLs
            itens_xml = []
            if self.arquivos_selecionados:
                for arq in self.arquivos_selecionados:
                    try: itens_xml.extend(parse_nfe(arq)['itens'])
                    except Exception: logging.warning(f"Erro ao processar XML: {arq}")
            else:
                itens_xml = parse_nfe_folder(self.pasta_xmls)

            # Remove duplicados baseados no código do produto no XML
            mapa_produtos_xml = {str(i.get('cProd', '')).strip(): i for i in itens_xml if str(i.get('cProd', '')).strip()}
            lista_unicos_xml = list(mapa_produtos_xml.values())

            # 2. Consulta a TABELA_produto no Firebird (somente da filial logada)
            self.produtos_erp = {}
            try:
                with FirebirdService(self.config_db) as fb:
                    sql = "SELECT PRODUTO_CODIGO, PRODUTO_DESCRICAO, PRODUTO_CLASS_FISCAL, PRODUTO_UNIDADE_CV FROM TABELA_produto WHERE PRODUTO_EMPRESA = ? AND PRODUTO_FILIAL = ?"
                    db_data = fb.query(sql, [self.empresa, self.filial])
                    # Cria dicionário com a chave sendo o CÓDIGO do ERP em texto limpo
                    for row in db_data:
                        cod = str(row.get('produto_codigo', '')).strip()
                        self.produtos_erp[cod] = {
                            'descricao': str(row.get('produto_descricao', '')).strip(),
                            'ncm': str(row.get('produto_class_fiscal') or '').replace('.', '').strip(),
                            'unidade': str(row.get('produto_unidade_cv', '')).strip()
                        }
            except Exception as db_err:
                self.parent.after(0, lambda: messagebox.showwarning("Aviso Banco", f"Não foi possível consultar TABELA_produto:\n{db_err}"))
                self.produtos_erp = {}

            # 3. Faz o Match
            self.dados_analisados = []
            for xml_item in lista_unicos_xml:
                cod_xml = str(xml_item.get('cProd', '')).strip()
                desc_xml = str(xml_item.get('xProd', '')).strip()
                ncm_xml = str(xml_item.get('ncm') or '').replace('.', '').strip()
                
                # Tenta achar pelo código exato
                erp_item = self.produtos_erp.get(cod_xml)
                
                status = "❌ NÃO CADASTRADO"
                tag = "NAO_CADASTRADO"
                cod_erp, desc_erp, ncm_erp = "-", "-", "-"
                
                if erp_item:
                    cod_erp = cod_xml
                    desc_erp = erp_item['descricao']
                    ncm_erp = erp_item['ncm']
                    
                    # Verifica se diverge em NCM ou Descrição muito diferente
                    ncm_diverge = ncm_xml != ncm_erp
                    desc_ratio = SequenceMatcher(None, desc_xml.upper(), desc_erp.upper()).ratio()
                    
                    if ncm_diverge or desc_ratio < 0.6:
                        status = "⚠️ DIVERGENTE"
                        tag = "DIVERGENTE"
                    else:
                        status = "✅ ENCONTRADO"
                        tag = "ENCONTRADO"
                else:
                    # FUZZY MATCH: Se não achou pelo código, tenta achar por nome parecido
                    melhor_ratio = 0
                    melhor_cod = None
                    
                    for cod, p_erp in self.produtos_erp.items():
                        # Compara a string do XML com a do ERP (ignorando maiúsculas/minúsculas)
                        ratio = SequenceMatcher(None, desc_xml.upper(), p_erp['descricao'].upper()).ratio()
                        if ratio > melhor_ratio:
                            melhor_ratio = ratio
                            melhor_cod = cod
                            
                    # Se a semelhança for igual ou maior que 75%, sugere o vínculo!
                    if melhor_cod and melhor_ratio >= 0.75:
                        cod_erp, desc_erp, ncm_erp = melhor_cod, self.produtos_erp[melhor_cod]['descricao'], self.produtos_erp[melhor_cod]['ncm']
                        status = f"🔎 SUGERIDO ({int(melhor_ratio*100)}%)"
                        tag = "SUGERIDO"

                self.dados_analisados.append({
                    'xml': xml_item,
                    'status': status,
                    'tag': tag,
                    'cod_erp': cod_erp,
                    'desc_erp': desc_erp,
                    'ncm_erp': ncm_erp
                })

            self.parent.after(0, self._renderizar_resultados)
        except Exception as e:
            logging.error(f"Erro no pipeline de Produtos: {e}")
            self.parent.after(0, lambda e=e: messagebox.showerror("Erro", str(e)))
            self.parent.after(0, lambda: self.btn_analisar.config(state=tk.NORMAL))

    def _renderizar_resultados(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        status_filtro = getattr(self, 'var_status_filtro', tk.StringVar(value="Todos")).get()

        for item in self.dados_analisados:
            tag = item['tag']
            if status_filtro != "Todos":
                if status_filtro == "NAO_CADASTRADO" and tag != "NAO_CADASTRADO": continue
                if status_filtro == "DIVERGENTE" and tag not in ("DIVERGENTE", "SUGERIDO"): continue
                if status_filtro == "ENCONTRADO" and tag != "ENCONTRADO": continue

            xml = item['xml']
            
            ncm_xml_fmt = self._formatar_ncm(xml.get('ncm', ''))
            ncm_erp_fmt = self._formatar_ncm(item['ncm_erp'])
            
            self.tree.insert("", tk.END, values=(
                xml.get('cProd', ''),
                item['cod_erp'],
                xml.get('xProd', ''),
                item['desc_erp'],
                ncm_xml_fmt,
                ncm_erp_fmt,
                item['status']
            ), tags=(item['tag'],))
            
        self.btn_analisar.config(state=tk.NORMAL)
        
        # Habilita botões apenas se encontrou algo
        if self.dados_analisados:
            self.btn_cadastrar.config(state=tk.NORMAL)
            self.btn_tributar.config(state=tk.NORMAL)
            self.btn_ambos.config(state=tk.NORMAL)
            
        self._atualizar_contadores()
        self.lbl_status.config(text=f"Pronto. {len(self.dados_analisados)} produtos únicos analisados.")

    def _injetar_firebird(self, modo):
        """
        modo 1 = Apenas Cadastrar (Ignora tributação)
        modo 2 = Apenas Tributar (Atualiza CSTs de produtos encontrados)
        modo 3 = Ambos (Insere + Tributa)
        """
        msg = "Deseja prosseguir com a "
        if modo == 1: msg += "INSERÇÃO DE CADASTRO BÁSICO"
        elif modo == 2: msg += "ATUALIZAÇÃO DE REGRAS FISCAIS"
        elif modo == 3: msg += "INSERÇÃO COMPLETA (Cadastro + Fiscal)"
        
        msg += " no Firebird?\n\nAção não reversível!"
        
        if not messagebox.askyesno("Confirmação", msg):
            return
            
        def task():
            self.parent.after(0, lambda: self.lbl_status.config(text="Processando lote no banco de dados..."))
            try:
                processados = 0
                with FirebirdService(self.config_db) as fb:
                    cursor = fb.conn.cursor() if hasattr(fb, 'conn') else None
                    
                    modo_codigo = self.var_modo_codigo.get()
                    if modo_codigo == 'sequencial':
                        existentes_rows = fb.query(
                            "SELECT PRODUTO_CODIGO FROM TABELA_PRODUTO WHERE PRODUTO_EMPRESA = ? AND PRODUTO_FILIAL = ?",
                            [self.empresa, self.filial]
                        )
                        existentes_codigos = set(str(r.get('produto_codigo', '')) for r in existentes_rows)
                    
                    for data in self.dados_analisados:
                        xml = data['xml']
                        is_novo = data['tag'] == 'NAO_CADASTRADO'
                        ncm_salvar = self._formatar_ncm(xml.get('ncm', ''))
                        
                        if (modo in [1, 3]) and is_novo:
                            codigo_produto = xml.get('cProd', '')
                            if modo_codigo == 'sequencial':
                                codigo_produto, _ = DataTransformer.prepare_codigo_produto('', existentes_codigos, modo='sequencial')
                                existentes_codigos.add(codigo_produto)
                            
                            sql_in = """
                                INSERT INTO TABELA_produto (
                                    PRODUTO_EMPRESA, PRODUTO_FILIAL, PRODUTO_CODIGO, 
                                    PRODUTO_DESCRICAO, PRODUTO_UNIDADE_CV, PRODUTO_CLASS_FISCAL,
                                    PRODUTO_ATIVO, PRODUTO_TIPO, PRODUTO_QTDE_PECAS
                                ) VALUES (?, ?, ?, ?, ?, ?, 'S', 1, 1)
                            """
                            params_in = (
                                self.empresa, self.filial, codigo_produto,
                                xml.get('xProd','')[:200], xml.get('uCom','')[:2], ncm_salvar[:10]
                            )
                            if cursor: cursor.execute(sql_in, params_in)
                            else: fb.execute(sql_in, params_in)
                            processados += 1

                        if (modo in [2, 3]) and not is_novo:
                            # ATUALIZA EXISTENTE (Tributação Focada)
                            sql_up = """
                                UPDATE TABELA_produto SET 
                                    PRODUTO_CST_PIS = ?, PRODUTO_CST_COFINS = ?, PRODUTO_CLASS_FISCAL = ?
                                WHERE PRODUTO_EMPRESA = ? AND PRODUTO_FILIAL = ? AND PRODUTO_CODIGO = ?
                            """
                            params_up = (
                                xml.get('pis_cst',''), xml.get('cofins_cst',''), ncm_salvar[:10],
                                self.empresa, self.filial, data['cod_erp']
                            )
                            if cursor: cursor.execute(sql_up, params_up)
                            else: fb.execute(sql_up, params_up)
                            processados += 1
                    
                    if cursor: fb.conn.commit()
                
                self.parent.after(0, lambda: messagebox.showinfo("Sucesso", f"Concluído! {processados} produtos afetados no ERP."))
            except Exception as e:
                logging.error(f"Erro ao injetar produtos: {e}")
                self.parent.after(0, lambda e_msg=str(e): messagebox.showerror("Erro Banco", f"Erro no Firebird:\n{e_msg}"))
            finally:
                self.parent.after(0, lambda: self.lbl_status.config(text="Pronto."))
                
        threading.Thread(target=task, daemon=True).start()
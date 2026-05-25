import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import configparser
import threading
import os

from utils.excel_reader import obter_abas_planilha, ler_planilha_produtos
from utils.firebird_service import FirebirdService
from utils.transformer import DataTransformer
from utils.importer import FirebirdImporter

class TelaImportacaoPlanilhaProdutos(ttk.Frame):
    def __init__(self, parent, callback_voltar=None):
        super().__init__(parent, padding="10")
        self.parent = parent
        self.callback_voltar = callback_voltar
        self.pack(fill=tk.BOTH, expand=True)

        self.registros_lidos = []
        self.caminho_arquivo = ""
        self.dados_grid = {}
        
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
        # Header
        lbl_title = tk.Label(self, text="IMPORTAÇÃO DE PRODUTOS VIA PLANILHA (Excel/CSV)", font=("Segoe UI", 14, "bold"), fg="#27AE60")
        lbl_title.pack(anchor=tk.W, pady=(0, 10))

        # Frame Arquivo e Configurações Globais
        frame_top = ttk.LabelFrame(self, text="1. Seleção do Arquivo e Configuração Base", padding="10")
        frame_top.pack(fill=tk.X, pady=5)

        self.ent_arquivo = ttk.Entry(frame_top, width=60)
        self.ent_arquivo.grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        ttk.Button(frame_top, text="📁 Selecionar Arquivo", command=self._selecionar_arquivo).grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(frame_top, text="Aba:").grid(row=0, column=2, padx=5, pady=5, sticky=tk.E)
        self.cb_abas = ttk.Combobox(frame_top, width=20, state="readonly")
        self.cb_abas.grid(row=0, column=3, padx=5, pady=5)

        ttk.Label(frame_top, text="Linha Inicial (Cabeçalho ignorado):").grid(row=1, column=0, padx=5, pady=5, sticky=tk.E)
        self.ent_linha_ini = ttk.Entry(frame_top, width=10)
        self.ent_linha_ini.insert(0, "2")
        self.ent_linha_ini.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)

        ttk.Label(frame_top, text="Tipo Base do Produto:").grid(row=1, column=2, padx=5, pady=5, sticky=tk.E)
        self.cb_tipo = ttk.Combobox(frame_top, width=25, state="readonly", values=[
            "1 - Revenda", "2 - Consumo", "3 - Matéria Prima", 
            "4 - Produto Acabado", "5 - Serviços", "6 - Outros"
        ])
        self.cb_tipo.grid(row=1, column=3, padx=5, pady=5)
        self.cb_tipo.set("4 - Produto Acabado")
        self.cb_tipo.bind("<<ComboboxSelected>>", lambda e: self._atualizar_tipo_preview())

        self.var_producao = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame_top, text="Integra Produção Sistec", variable=self.var_producao).grid(row=1, column=4, padx=15)

        # Frame Mapeamento de Colunas
        frame_map = ttk.LabelFrame(self, text="2. Mapeamento de Colunas (Insira a Letra da Coluna. Ex: A, B, C... AA)", padding="10")
        frame_map.pack(fill=tk.X, pady=5)

        labels_map = [
            ("Código Antigo/Auxiliar:", "codigo_antigo", True),
            ("Descrição (Obrigatório):", "descricao", False),
            ("Grupo:", "grupo", True),
            ("Subgrupo:", "subgrupo", True),
            ("NCM:", "ncm", True),
            ("Cód. Barras (EAN):", "ean", True),
            ("Unidade (Ex: UN, KG):", "unidade", True)
        ]

        self.entradas_map = {}
        col_idx = 0
        row_idx = 0
        for lbl_texto, chave, opcional in labels_map:
            lbl = ttk.Label(frame_map, text=lbl_texto)
            lbl.grid(row=row_idx, column=col_idx, sticky=tk.E, padx=5, pady=5)
            ent = ttk.Entry(frame_map, width=5)
            ent.grid(row=row_idx, column=col_idx+1, sticky=tk.W, padx=5, pady=5)
            self.entradas_map[chave] = ent
            
            col_idx += 2
            if col_idx >= 8:
                col_idx = 0
                row_idx += 1

        # Ações e Progresso
        frame_mid = ttk.Frame(self)
        frame_mid.pack(fill=tk.X, pady=5)
        
        self.btn_analisar = ttk.Button(frame_mid, text="🔍 Carregar e Analisar Planilha", command=self._iniciar_analise)
        self.btn_analisar.pack(side=tk.LEFT, padx=5)

        ttk.Button(frame_mid, text="☑ Marcar Todos", command=self._marcar_todos).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_mid, text="☐ Desmarcar Todos", command=self._desmarcar_todos).pack(side=tk.LEFT, padx=5)
        
        self.progresso = ttk.Progressbar(frame_mid, orient=tk.HORIZONTAL, mode='determinate', length=200)
        self.progresso.pack(side=tk.RIGHT, padx=5)
        
        self.lbl_status = ttk.Label(frame_mid, text="Aguardando configuração...", font=("Segoe UI", 9))
        self.lbl_status.pack(side=tk.RIGHT, padx=15)

        # Grade Preview
        frame_grade = ttk.Frame(self)
        frame_grade.pack(fill=tk.BOTH, expand=True, pady=5)

        self.colunas = ("SEL", "STATUS", "CÓDIGO ANTIGO", "DESCRIÇÃO", "TIPO", "GRUPO", "SUBGRUPO", "NCM", "EAN", "UNID")
        self.tree = ttk.Treeview(frame_grade, columns=self.colunas, show="headings")
        
        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)
        
        larguras = [40, 100, 100, 250, 120, 120, 120, 80, 100, 60]
        for col, larg in zip(self.colunas, larguras):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=larg, anchor=tk.CENTER if col != "DESCRIÇÃO" else tk.W)

        self.tree.tag_configure('ERRO', background='#FADBD8')
        self.tree.tag_configure('OK', background='#EAFAF1')

        scroll_y = ttk.Scrollbar(frame_grade, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        # Footer
        frame_fim = ttk.Frame(self)
        frame_fim.pack(fill=tk.X, pady=10)
        ttk.Button(frame_fim, text="⬅ VOLTAR", command=self._fechar_tela).pack(side=tk.LEFT, padx=5)
        
        self.btn_importar = ttk.Button(frame_fim, text="🚀 Processar e Injetar no ERP", state=tk.DISABLED, command=self._iniciar_importacao)
        self.btn_importar.pack(side=tk.RIGHT, padx=5)

    def _selecionar_arquivo(self):
        path = filedialog.askopenfilename(filetypes=[("Arquivos Suportados", "*.xlsx *.csv"), ("Excel", "*.xlsx"), ("CSV", "*.csv")])
        if path:
            self.ent_arquivo.delete(0, tk.END)
            self.ent_arquivo.insert(0, path)
            self.caminho_arquivo = path
            
            abas = obter_abas_planilha(path)
            self.cb_abas['values'] = abas
            if abas: self.cb_abas.current(0)

    def _fechar_tela(self):
        self.destroy()
        if self.callback_voltar: self.callback_voltar()

    def _iniciar_analise(self):
        aba = self.cb_abas.get()
        try:
            linha_ini = int(self.ent_linha_ini.get())
        except ValueError:
            return messagebox.showerror("Erro", "A linha inicial deve ser um número.")
            
        if not self.caminho_arquivo or not aba:
            return messagebox.showwarning("Aviso", "Selecione o arquivo e a aba antes de continuar.")
            
        mapa_colunas = {chave: ent.get().strip() for chave, ent in self.entradas_map.items()}
        if not mapa_colunas.get('descricao'):
            return messagebox.showwarning("Aviso", "Você precisa mapear obrigatoriamente a letra da coluna 'Descrição'.")
            
        self.btn_analisar.config(state=tk.DISABLED)
        self.lbl_status.config(text="Lendo planilha...")
        self.progresso['value'] = 20
        
        threading.Thread(target=self._analisar_bg, args=(aba, mapa_colunas, linha_ini), daemon=True).start()

    def _analisar_bg(self, aba, mapa_colunas, linha_ini):
        try:
            self.registros_lidos = ler_planilha_produtos(self.caminho_arquivo, aba, mapa_colunas, linha_ini)
            self.parent.after(0, self._renderizar_preview)
        except Exception as e:
            self.parent.after(0, lambda err=e: messagebox.showerror("Erro", f"Falha na leitura da planilha:\n{err}"))
            self.parent.after(0, lambda: self.btn_analisar.config(state=tk.NORMAL))
            self.parent.after(0, lambda: self.lbl_status.config(text="Erro."))

    def _renderizar_preview(self):
        for i in self.tree.get_children(): self.tree.delete(i)
        self.dados_grid.clear()
        
        tipo_selecionado = self.cb_tipo.get()
        validos = 0
        for reg in self.registros_lidos:
            status = "OK"
            if not reg.get('descricao'): status = "ERRO (Sem Descrição)"
            else: validos += 1
            
            # Se tem grupo mas não tem subgrupo mapeado/preenchido (ou só tem espaços), auto-preenche com a descrição do grupo
            if str(reg.get('grupo', '')).strip() and not str(reg.get('subgrupo', '')).strip():
                reg['subgrupo'] = reg['grupo']
            
            reg['_status'] = status
            check = "☑" if status == "OK" else "☐"
            
            item_id = self.tree.insert("", tk.END, values=(
                check, status, reg.get('codigo_antigo', ''), reg.get('descricao', ''),
                tipo_selecionado, reg.get('grupo', ''), reg.get('subgrupo', ''), reg.get('ncm', ''),
                reg.get('ean', ''), reg.get('unidade', '')
            ), tags=('OK' if status == 'OK' else 'ERRO',))
            self.dados_grid[item_id] = reg
            
        self.lbl_status.config(text=f"Pronto. {validos} produtos válidos de {len(self.registros_lidos)} lidos.")
        self.progresso['value'] = 100
        self.btn_analisar.config(state=tk.NORMAL)
        if validos > 0: self.btn_importar.config(state=tk.NORMAL)

    def _atualizar_tipo_preview(self):
        if not self.tree.get_children(): return
        novo_tipo = self.cb_tipo.get()
        for item in self.tree.get_children():
            valores = list(self.tree.item(item, "values"))
            valores[4] = novo_tipo
            self.tree.item(item, values=valores)

    def _on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            if column == "#1":
                item_id = self.tree.identify_row(event.y)
                if not item_id: return
                valores = list(self.tree.item(item_id, 'values'))
                if "ERRO" in valores[1]: return # Impede marcar os com erro
                
                valores[0] = "☑" if valores[0] == "☐" else "☐"
                self.tree.item(item_id, values=valores)

    def _marcar_todos(self):
        for item in self.tree.get_children():
            v = list(self.tree.item(item, "values"))
            if "ERRO" not in v[1]:
                v[0] = "☑"
                self.tree.item(item, values=v)

    def _desmarcar_todos(self):
        for item in self.tree.get_children():
            v = list(self.tree.item(item, "values"))
            if "ERRO" not in v[1]:
                v[0] = "☐"
                self.tree.item(item, values=v)

    def _iniciar_importacao(self):
        selecionados = []
        for item_id in self.tree.get_children():
            valores = self.tree.item(item_id, "values")
            if valores[0] == "☑":
                selecionados.append(self.dados_grid[item_id])

        if not selecionados:
            messagebox.showwarning("Aviso", "Selecione pelo menos um produto para importar.")
            return

        resp = messagebox.askyesno("Confirmar", f"Deseja injetar os {len(selecionados)} produtos selecionados e seus grupos no Banco de Dados?\nEssa ação não pode ser desfeita.")
        if resp:
            self.btn_importar.config(state=tk.DISABLED)
            self.btn_analisar.config(state=tk.DISABLED)
            self.lbl_status.config(text="Construindo grupos e injetando produtos...")

            # Coleta os valores da interface na thread principal (evita falha silenciosa de leitura no background)
            tipo_sel = self.cb_tipo.get()
            prod_sistec = 'S' if self.var_producao.get() else 'N'
            
            threading.Thread(target=self._importacao_bg, args=(selecionados, tipo_sel, prod_sistec), daemon=True).start()

    def _importacao_bg(self, selecionados, tipo_sel, prod_sistec):
        try:
            emp = int(self.config.get('IMPORTACAO', 'empresa', fallback='1'))
            fil = int(self.config.get('IMPORTACAO', 'filial', fallback='1'))

            with FirebirdService(self.config_db) as fb:
                # Cache Grupos
                grupos_db = fb.query("SELECT GRUPO_CODIGO, GRUPO_DESCRICAO FROM TABELA_GRUPO WHERE GRUPO_EMPRESA = ? AND GRUPO_FILIAL = ?", [emp, fil])
                mapa_grupos = {str(g.get('grupo_descricao') or '').strip().upper(): int(g.get('grupo_codigo', 0)) for g in grupos_db}
                
                # Cache Subgrupos
                subgrupos_db = fb.query("SELECT SUBGRUPO_CODIGO, SUBGRUPO_DESCRICAO, SUBGRUPO_GRUPO FROM TABELA_SUBGRUPO WHERE SUBGRUPO_EMPRESA = ? AND SUBGRUPO_FILIAL = ?", [emp, fil])
                mapa_subgrupos = {f"{s.get('subgrupo_grupo')}_{str(s.get('subgrupo_descricao') or '').strip().upper()}": int(s.get('subgrupo_codigo', 0)) for s in subgrupos_db}

                # Cache Códigos Existentes (Proteção contra colisão)
                sql_codigos = "SELECT PRODUTO_CODIGO FROM TABELA_PRODUTO WHERE PRODUTO_EMPRESA = ? AND PRODUTO_FILIAL = ?"
                existentes_codigos = set(str(p['produto_codigo']) for p in fb.query(sql_codigos, [emp, fil]))

                produtos_para_inserir = []

                for item in selecionados:
                    if item.get('_status') != 'OK': continue

                    # Auto-Criação de Grupo
                    desc_grupo = str(item.get('grupo', '')).strip().upper()
                    if not desc_grupo: grupo_id = 1
                    elif desc_grupo in mapa_grupos: grupo_id = mapa_grupos[desc_grupo]
                    else:
                        res = fb.query("SELECT COALESCE(MAX(GRUPO_CODIGO), 0) + 1 AS NOVO FROM TABELA_GRUPO WHERE GRUPO_EMPRESA = ? AND GRUPO_FILIAL = ?", [emp, fil])
                        grupo_id = int(res[0]['novo'])
                        fb.execute("INSERT INTO TABELA_GRUPO (GRUPO_EMPRESA, GRUPO_FILIAL, GRUPO_CODIGO, GRUPO_DESCRICAO) VALUES (?, ?, ?, ?)", [emp, fil, grupo_id, desc_grupo[:60]])
                        mapa_grupos[desc_grupo] = grupo_id

                    # Auto-Criação de Subgrupo
                    desc_sub = str(item.get('subgrupo', '')).strip().upper()
                    if not desc_sub and desc_grupo:
                        desc_sub = desc_grupo
                        
                    if not desc_sub: subgrupo_id = 1
                    else:
                        chave_sub = f"{grupo_id}_{desc_sub}"
                        if chave_sub in mapa_subgrupos: subgrupo_id = mapa_subgrupos[chave_sub]
                        else:
                            res = fb.query("SELECT COALESCE(MAX(SUBGRUPO_CODIGO), 0) + 1 AS NOVO FROM TABELA_SUBGRUPO WHERE SUBGRUPO_EMPRESA = ? AND SUBGRUPO_FILIAL = ? AND SUBGRUPO_GRUPO = ?", [emp, fil, grupo_id])
                            subgrupo_id = int(res[0]['novo'])
                            fb.execute("INSERT INTO TABELA_SUBGRUPO (SUBGRUPO_EMPRESA, SUBGRUPO_FILIAL, SUBGRUPO_GRUPO_EMPRESA, SUBGRUPO_GRUPO_FILIAL, SUBGRUPO_GRUPO, SUBGRUPO_CODIGO, SUBGRUPO_DESCRICAO) VALUES (?, ?, ?, ?, ?, ?, ?)", [emp, fil, emp, fil, grupo_id, subgrupo_id, desc_sub[:60]])
                            mapa_subgrupos[chave_sub] = subgrupo_id

                    # Proteção da Unidade vazia
                    unidade_planilha = str(item.get('unidade', '')).strip().upper()
                    if not unidade_planilha: unidade_planilha = 'UN'

                    # Mocka objeto como se fosse XML para reuso blindado de regras do Sistec
                    xml_mock = {
                        'x_prod': item.get('descricao', ''), 'ncm': item.get('ncm', ''),
                        'c_ean': item.get('ean', ''), 'u_com': unidade_planilha
                    }

                    # Geração Segura de Código Numérico
                    cod_antigo = str(item.get('codigo_antigo', '')).strip()
                    if not cod_antigo:
                        max_num = 0
                        for code in existentes_codigos:
                            if str(code).isdigit():
                                max_num = max(max_num, int(code))
                        codigo_final = str(max_num + 1)
                        cod_aux = None
                    else:
                        codigo_final, cod_aux = DataTransformer.prepare_codigo_produto(cod_antigo, existentes_codigos)
                        
                    existentes_codigos.add(codigo_final)

                    config_prod = {'empresa': emp, 'filial': fil}
                    classificacao = {'tipo': tipo_sel, 'grupo_id': grupo_id, 'subgrupo_id': subgrupo_id, 'producao_sistec': prod_sistec}

                    novo_dict = DataTransformer.prepare_produto(xml_mock, config_prod, classificacao)
                    novo_dict['PRODUTO_CODIGO'] = codigo_final
                    novo_dict['PRODUTO_COD_AUXILIAR'] = cod_aux
                    novo_dict['_ACAO'] = 'INSERT'
                    produtos_para_inserir.append(novo_dict)

                importer = FirebirdImporter(fb)
                res_imp = importer.import_produtos(produtos_para_inserir)
                
                inseridos = res_imp.get('inseridos', 0)
                erros = res_imp.get('erros', [])
                
                msg = f"Processamento concluído!\n\n{inseridos} produtos foram cadastrados com sucesso."
                if erros:
                    msg += f"\n\nHouveram {len(erros)} erro(s) durante a importação. Veja o log para mais detalhes."
                    
                self.parent.after(0, lambda m=msg: messagebox.showinfo("Concluído", m))
                
                if erros:
                    log_erros_str = "--- LOG DE ERROS DE IMPORTACAO VIA PLANILHA ---\n\n"
                    for erro in erros:
                        detalhe = erro.get('erro', str(erro))
                        log_erros_str += f"[ERRO NO BANCO DE DADOS]:\n--> {detalhe}\n\n"
                        
                    def mostrar_log(log_str):
                        resp = messagebox.askyesno(
                            "Log de Erros", 
                            "Foram encontrados erros. Deseja salvar um arquivo de texto com os detalhes do erro para validar?", 
                            parent=self.parent
                        )
                        if resp:
                            caminho_log = filedialog.asksaveasfilename(
                                defaultextension=".txt", 
                                initialfile="LOG_ERROS_PLANILHA.txt", 
                                filetypes=[("Arquivos de Texto", "*.txt")],
                                parent=self.parent
                            )
                            if caminho_log:
                                try:
                                    with open(caminho_log, 'w', encoding='utf-8') as f:
                                        f.write(log_str)
                                    messagebox.showinfo("Log Salvo", f"Arquivo de log salvo em:\n{caminho_log}", parent=self.parent)
                                except Exception as ex:
                                    messagebox.showerror("Erro ao Salvar", f"Não foi possível salvar o log:\n{ex}", parent=self.parent)
                                    
                    self.parent.after(0, lambda l=log_erros_str: mostrar_log(l))
                    
        except Exception as e:
            self.parent.after(0, lambda err=e: messagebox.showerror("Erro de Importação", f"Ocorreu um erro estrutural:\n{err}"))
        finally:
            self.parent.after(0, lambda: self.btn_analisar.config(state=tk.NORMAL))
            self.parent.after(0, lambda: self.btn_importar.config(state=tk.NORMAL))
            self.parent.after(0, lambda: self.lbl_status.config(text="Pronto."))
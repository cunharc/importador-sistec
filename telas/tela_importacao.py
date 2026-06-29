import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import configparser
import os
import sys
from PIL import Image, ImageTk
from telas.tela_preview import TelaPreview
import utils.excel_reader as excel_reader
import utils.regras_negocio as regras_negocio
import utils.firebird_conn as fb

class TelaImportacao(ttk.Frame):
    def __init__(self, parent, callback_voltar=None):
        super().__init__(parent, padding="10")
        self.parent = parent
        self.callback_voltar = callback_voltar
        self.pack(fill=tk.BOTH, expand=True)
        print("✅ Instância de TelaImportacao criada.")

        self.registros_lidos = []
        self.cancelado = False

        self.var_limpar_banco = tk.BooleanVar(self)
        self.config = configparser.ConfigParser()
        self.config.read('config.ini', encoding='utf-8')

        self._criar_widgets()
        self._carregar_config_iniciais()

    def resource_path(self, relative_path):
        """Garante que a imagem seja encontrada ao rodar via .exe"""
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def _criar_widgets(self):
        # Header do Módulo
        lbl_title = tk.Label(self, text="IMPORTAÇÃO DE PLANO DE CONTAS VIA EXCEL", font=("Segoe UI", 14, "bold"), fg="#C8001E")
        lbl_title.pack(anchor=tk.W, pady=(0, 10))

        # Logo SISTEC
        logo_path = self.resource_path("sistec.jpg")
        if os.path.exists(logo_path):
            try:
                img = Image.open(logo_path)
                img.thumbnail((250, 100)) # Redimensiona a logo mantendo a proporção
                self.logo_img = ImageTk.PhotoImage(img)
                ttk.Label(self, image=self.logo_img).pack(pady=5)
            except Exception as e:
                print("Erro ao carregar logo:", e)

        # Frame Configurações Iniciais
        frame_config = ttk.LabelFrame(self, text="Parâmetros Base", padding="10")
        frame_config.pack(fill=tk.X, pady=5)

        ttk.Label(frame_config, text="Empresa:").grid(row=0, column=0, padx=5)
        self.ent_empresa = ttk.Entry(frame_config, width=10)
        self.ent_empresa.grid(row=0, column=1, padx=5)

        ttk.Label(frame_config, text="Filial:").grid(row=0, column=2, padx=5)
        self.ent_filial = ttk.Entry(frame_config, width=10)
        self.ent_filial.grid(row=0, column=3, padx=5)

        ttk.Label(frame_config, text="Exercício:").grid(row=0, column=4, padx=5)
        self.ent_exercicio = ttk.Entry(frame_config, width=10)
        self.ent_exercicio.grid(row=0, column=5, padx=5)

        self.chk_limpar = ttk.Checkbutton(frame_config, text="Zerar banco de dados antes de importar (Apagar plano atual)", variable=self.var_limpar_banco, command=self._limpar_tela)
        self.chk_limpar.grid(row=1, column=0, columnspan=6, sticky=tk.W, padx=5, pady=10)

        # Frame Arquivo Excel
        frame_excel = ttk.LabelFrame(self, text="Arquivo Excel", padding="10")
        frame_excel.pack(fill=tk.X, pady=5)

        ttk.Label(frame_excel, text="Arquivo Excel:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.ent_arquivo = ttk.Entry(frame_excel, width=60)
        self.ent_arquivo.grid(row=0, column=1, columnspan=3, padx=5)
        ttk.Button(frame_excel, text="📁", width=3, command=self._selecionar_arquivo).grid(row=0, column=4, padx=5)

        ttk.Label(frame_excel, text="Aba da Planilha:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.cb_abas = ttk.Combobox(frame_excel, state="readonly", width=20)
        self.cb_abas.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)

        ttk.Label(frame_excel, text="Linha Inicial:").grid(row=1, column=2, sticky=tk.E, padx=5, pady=5)
        self.ent_linha_ini = ttk.Entry(frame_excel, width=10)
        self.ent_linha_ini.grid(row=1, column=3, sticky=tk.W, padx=5, pady=5)

        ttk.Label(frame_excel, text="Coluna CONTA:").grid(row=2, column=0, sticky=tk.W, padx=5)
        self.ent_col_conta = ttk.Entry(frame_excel, width=10)
        self.ent_col_conta.grid(row=2, column=1, sticky=tk.W, padx=5)

        ttk.Label(frame_excel, text="Coluna DESCRIÇÃO:").grid(row=2, column=2, sticky=tk.E, padx=5)
        self.ent_col_desc = ttk.Entry(frame_excel, width=10)
        self.ent_col_desc.grid(row=2, column=3, sticky=tk.W, padx=5)

        ttk.Label(frame_excel, text="Nível máx sintética:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.ent_nivel_sint = ttk.Entry(frame_excel, width=10)
        self.ent_nivel_sint.grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)

        # Ações Principais
        frame_acoes = ttk.Frame(self, padding="5")
        frame_acoes.pack(fill=tk.X)

        self.btn_abrir_planilha = ttk.Button(frame_acoes, text="📂 ABRIR PLANILHA", command=self._abrir_planilha)
        self.btn_abrir_planilha.pack(side=tk.LEFT, padx=5)

        # Filtro rápido
        frame_filtro = ttk.Frame(self, padding="5")
        frame_filtro.pack(fill=tk.X)
        ttk.Label(frame_filtro, text="🔍 Filtrar:").pack(side=tk.LEFT)
        self.ent_filtro_import = ttk.Entry(frame_filtro, width=30)
        self.ent_filtro_import.pack(side=tk.LEFT, padx=5)
        self.ent_filtro_import.bind("<KeyRelease>", self._filtrar_dados)

        # Grade (Treeview preview rápido)
        frame_grade = ttk.Frame(self)
        frame_grade.pack(fill=tk.BOTH, expand=True, pady=10)

        colunas = ("CONTA", "DESCRIÇÃO", "NÍV", "RED", "NAT", "STATUS")
        self._sort_directions = {col: False for col in colunas}
        self.tree = ttk.Treeview(frame_grade, columns=colunas, show="headings", height=8)
        
        larguras = [100, 300, 50, 50, 50, 150]
        for col, larg in zip(colunas, larguras):
            self.tree.heading(col, text=col + " ↕", command=lambda c=col: self._sort_treeview(c))
            anchor = tk.W if col in ["CONTA", "DESCRIÇÃO"] else tk.CENTER
            self.tree.column(col, width=larg, anchor=anchor)

        # Configura as cores (Tags) para as linhas da grade
        self.tree.tag_configure('DUPLICADA', background='#FADBD8') # Vermelho claro (Sistec)
        self.tree.tag_configure('ERRO', background='#F5B7B1')

        scroll_y = ttk.Scrollbar(frame_grade, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        # Status e Progresso
        frame_status = ttk.Frame(self)
        frame_status.pack(fill=tk.X)

        self.lbl_status = ttk.Label(frame_status, text="Total de linhas lidas: 0 | Erros: 0")
        self.lbl_status.pack(anchor=tk.W)

        style = ttk.Style()
        style.configure("Red.Horizontal.TProgressbar", background="#E74C3C")

        self.progresso = ttk.Progressbar(frame_status, orient=tk.HORIZONTAL, length=100, mode='determinate')
        self.progresso.pack(fill=tk.X, pady=5)

        # Ações Finais
        frame_fim = ttk.Frame(self)
        frame_fim.pack(fill=tk.X, pady=10)

        self.btn_voltar = ttk.Button(frame_fim, text="⬅ VOLTAR", command=self._fechar_tela)
        self.btn_voltar.pack(side=tk.LEFT, padx=5)

        self.btn_cancelar = ttk.Button(frame_fim, text="🛑 CANCELAR", command=self._cancelar, state=tk.DISABLED)
        self.btn_cancelar.pack(side=tk.LEFT, padx=5)

        self.btn_importar = ttk.Button(frame_fim, text="🚀 IMPORTAR PARA O BANCO", command=self._iniciar_importacao, state=tk.DISABLED)
        self.btn_importar.pack(side=tk.RIGHT, padx=5)

        self.btn_preview = ttk.Button(frame_fim, text="👁 PREVIEW COMPLETO", command=self._abrir_preview, state=tk.DISABLED)
        self.btn_preview.pack(side=tk.RIGHT, padx=5)

    def _fechar_tela(self):
        print("❌ Instância de TelaImportacao destruída.")
        self.destroy()
        if self.callback_voltar:
            self.callback_voltar()

    def _carregar_config_iniciais(self):
        if self.config.has_section('IMPORTACAO'):
            self.ent_empresa.insert(0, self.config.get('IMPORTACAO', 'empresa', fallback='1'))
            self.ent_filial.insert(0, self.config.get('IMPORTACAO', 'filial', fallback='1'))
            self.ent_exercicio.insert(0, self.config.get('IMPORTACAO', 'exercicio', fallback='2026'))
            self.ent_col_conta.insert(0, self.config.get('IMPORTACAO', 'coluna_conta', fallback='A'))
            self.ent_col_desc.insert(0, self.config.get('IMPORTACAO', 'coluna_descricao', fallback='B'))
            self.ent_linha_ini.insert(0, self.config.get('IMPORTACAO', 'linha_inicial', fallback='2'))
            self.ent_nivel_sint.insert(0, self.config.get('IMPORTACAO', 'nivel_sintetico', fallback='4'))
            self.var_limpar_banco.set(self.config.getboolean('IMPORTACAO', 'limpar_banco', fallback=False))
            
            # Carrega o último arquivo Excel e a aba
            arquivo_salvo = self.config.get('IMPORTACAO', 'arquivo_excel', fallback='')
            if arquivo_salvo:
                self.ent_arquivo.insert(0, arquivo_salvo)
                if os.path.exists(arquivo_salvo):
                    try:
                        abas = excel_reader.listar_abas(arquivo_salvo)
                        self.cb_abas['values'] = abas
                        aba_salva = self.config.get('IMPORTACAO', 'aba_excel', fallback='')
                        if aba_salva in abas:
                            self.cb_abas.set(aba_salva)
                        elif abas:
                            self.cb_abas.current(0)
                    except Exception:
                        pass

    def _salvar_config(self):
        config = configparser.ConfigParser()
        config.read('config.ini', encoding='utf-8')

        if not config.has_section('IMPORTACAO'):
            config.add_section('IMPORTACAO')
        config.set('IMPORTACAO', 'empresa', self.ent_empresa.get())
        config.set('IMPORTACAO', 'filial', self.ent_filial.get())
        config.set('IMPORTACAO', 'exercicio', self.ent_exercicio.get())
        config.set('IMPORTACAO', 'coluna_conta', self.ent_col_conta.get())
        config.set('IMPORTACAO', 'coluna_descricao', self.ent_col_desc.get())
        config.set('IMPORTACAO', 'linha_inicial', self.ent_linha_ini.get())
        config.set('IMPORTACAO', 'nivel_sintetico', self.ent_nivel_sint.get())
        config.set('IMPORTACAO', 'arquivo_excel', self.ent_arquivo.get())
        config.set('IMPORTACAO', 'aba_excel', self.cb_abas.get())
        config.set('IMPORTACAO', 'limpar_banco', str(self.var_limpar_banco.get()))

        with open('config.ini', 'w', encoding='utf-8') as f:
            config.write(f)
        self.config = config

    def _selecionar_arquivo(self):
        caminho = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx")])
        if caminho:
            self.ent_arquivo.delete(0, tk.END)
            self.ent_arquivo.insert(0, caminho)
            try:
                abas = excel_reader.listar_abas(caminho)
                self.cb_abas['values'] = abas
                if abas:
                    self.cb_abas.current(0)
            except Exception as e:
                messagebox.showerror("Erro", f"Não foi possível ler as abas do arquivo:\n{e}")

    def _cancelar(self):
        self.cancelado = True

    def _abrir_planilha(self):
        arquivo = self.ent_arquivo.get()
        aba = self.cb_abas.get()
        
        if not os.path.exists(arquivo):
            messagebox.showwarning("Aviso", "Arquivo Excel não encontrado!")
            return
            
        try:
            emp = int(self.ent_empresa.get())
            fil = int(self.ent_filial.get())
            exe = int(self.ent_exercicio.get())
            linha_ini = int(self.ent_linha_ini.get())
            nivel_sint = int(self.ent_nivel_sint.get())
        except ValueError:
            messagebox.showerror("Erro", "Campos numéricos (Empresa, Filial, etc.) devem conter apenas números.")
            return

        self._salvar_config()
        self.progresso.configure(style="Horizontal.TProgressbar")
        self.progresso['value'] = 0
        self.parent.update_idletasks()

        conn = None
        try:
            conn = fb.conectar()
        except Exception as e:
            messagebox.showerror("Erro de Banco", f"Falha ao conectar no Firebird:\n{e}")
            return

        try:
            # 1. Ler Excel
            linhas = excel_reader.ler_planilha(arquivo, aba, self.ent_col_conta.get(), self.ent_col_desc.get(), linha_ini)
            
            # 2. Processar Dados do Banco
            if self.var_limpar_banco.get():
                contas_existentes = set()
                codigo_ini = 1
            else:
                contas_existentes = fb.buscar_contas_existentes(conn, emp, fil, exe)
                codigo_ini = fb.buscar_proximo_codigo(conn, emp, fil, exe)
            
            # 3. Regras de Negócio e Validações
            registros = regras_negocio.processar_planilha(linhas, emp, fil, exe, codigo_ini, nivel_sint)
            self.registros_lidos = regras_negocio.validar_registros(registros, contas_existentes)
            
            self._carregar_tree()
            self.btn_preview.config(state=tk.NORMAL)
            self.progresso['value'] = 100

        except Exception as e:
            self.progresso.configure(style="Red.Horizontal.TProgressbar")
            messagebox.showerror("Erro de Leitura", f"Ocorreu um erro ao processar:\n{e}")
        finally:
            if conn:
                conn.close()

    def _abrir_preview(self):
        TelaPreview(self.parent, self.registros_lidos, self._realizar_importacao)

    def _filtrar_dados(self, event):
        self._carregar_tree(self.ent_filtro_import.get())

    def _carregar_tree(self, filtro=""):
        filtro = filtro.strip().lower()
        for item in self.tree.get_children():
            self.tree.delete(item)

        erros = 0
        exibidos = 0
        for r in self.registros_lidos:
            valores = [
                str(r['PLANO_CONTA'] or ''),
                str(r['PLANO_DESCRICAO'] or ''),
                str(r['PLANO_NIVEL'] or ''),
                str(r['PLANO_REDUZIDO'] or ''),
                str(r['PLANO_COD_NATUREZA'] or ''),
                str(r['STATUS'] or '')
            ]
            if filtro and not any(filtro in valor.lower() for valor in valores):
                continue

            status_icon = "✅ OK" if r['STATUS'] == 'OK' else ("⚠️ DUPLICADA" if r['STATUS'] == 'DUPLICADA' else "❌ ERRO")
            if r['STATUS'] != 'OK':
                erros += 1

            self.tree.insert("", tk.END, values=(
                r['PLANO_CONTA'], r['PLANO_DESCRICAO'], r['PLANO_NIVEL'], 
                r['PLANO_REDUZIDO'] or "", r['PLANO_COD_NATUREZA'], status_icon
            ), tags=(r['STATUS'],))
            exibidos += 1

        total = len(self.registros_lidos)
        self.lbl_status.config(text=f"Total de linhas lidas: {total} | Exibindo: {exibidos} | Erros/Duplicadas: {erros}")

    def _sort_treeview(self, col):
        if not self.registros_lidos:
            return

        self._sort_directions[col] = not self._sort_directions[col]
        reverse = self._sort_directions[col]

        mapping = {
            'CONTA': 'PLANO_CONTA',
            'DESCRIÇÃO': 'PLANO_DESCRICAO',
            'NÍV': 'PLANO_NIVEL',
            'RED': 'PLANO_REDUZIDO',
            'NAT': 'PLANO_COD_NATUREZA',
            'STATUS': 'STATUS'
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

        self.registros_lidos.sort(key=valor_para_ordenar, reverse=reverse)
        self._atualizar_legenda_ordenacao(col)
        self._carregar_tree(self.ent_filtro_import.get())

    def _atualizar_legenda_ordenacao(self, coluna_ativa):
        for col in self._sort_directions:
            if col == coluna_ativa:
                arrow = " ▼" if self._sort_directions[col] else " ▲"
            else:
                arrow = " ↕"
            self.tree.heading(col, text=col + arrow, command=lambda c=col: self._sort_treeview(c))

    def _iniciar_importacao(self):
        # Acesso direto a importação pulando preview não habilitado por design (pede preview).
        # Será chamado pela TelaPreview (callback)
        pass

    def _realizar_importacao(self, registros_validos):
        self.cancelado = False
        self.btn_cancelar.config(state=tk.NORMAL)
        self.btn_preview.config(state=tk.DISABLED)
        self.btn_abrir_planilha.config(state=tk.DISABLED)
        self.progresso.configure(style="Horizontal.TProgressbar")
        self.progresso['value'] = 0
        self.parent.update_idletasks()

        emp = int(self.ent_empresa.get())
        fil = int(self.ent_filial.get())
        exe = int(self.ent_exercicio.get())

        if self.var_limpar_banco.get():
            resposta = messagebox.askyesno(
                "ATENÇÃO EXTREMA", 
                "Você marcou a opção para ZERAR o banco de dados.\n"
                f"Isso apagará TODAS as contas atuais da Empresa {emp} e Filial {fil} antes de importar as novas.\n\n"
                "Deseja realmente continuar e apagar os dados antigos?", 
                icon=messagebox.WARNING
            )
            if not resposta:
                self._restaurar_botoes()
                return

        conn = None
        try:
            conn = fb.conectar()
        except Exception as e:
            messagebox.showerror("Erro de Banco", f"Falha ao conectar no Firebird:\n{e}")
            self._restaurar_botoes()
            return

        def atualizar_prog(atual, total):
            percent = (atual / total) * 100
            self.progresso['value'] = percent
            self.lbl_status.config(text=f"Importando... {atual}/{total} ({percent:.1f}%)")
            self.parent.update_idletasks()

        def verificar_cancel():
            return self.cancelado

        try:
            if self.var_limpar_banco.get():
                fb.limpar_tabela(conn, emp, fil, exe)

            sucesso, inseridos, erros = fb.inserir_registros(conn, registros_validos, atualizar_prog, verificar_cancel)
            
            if self.cancelado:
                self.progresso.configure(style="Red.Horizontal.TProgressbar")
                messagebox.showwarning("Cancelado", "A importação foi cancelada pelo usuário. Nenhuma alteração foi salva no banco.")
            elif sucesso:
                resumo = f"{inseridos} registros importados com sucesso!\n"
                if erros > 0:
                    resumo += f"{erros} erros ao inserir."
                messagebox.showinfo("Importação Concluída", resumo)
                
                # Opcional: Salvar log export
                self._oferecer_log(registros_validos)
                
                if messagebox.askyesno("Nova Importação", "Deseja limpar a tela para importar outra planilha?"):
                    self._limpar_tela()
                
        except Exception as e:
            self.progresso.configure(style="Red.Horizontal.TProgressbar")
            messagebox.showerror("Erro", f"Erro crítico durante a importação:\n{e}")
        finally:
            if conn:
                conn.close()
            self._restaurar_botoes()

    def _oferecer_log(self, registros):
        resp = messagebox.askyesno("Exportar Log", "Deseja salvar um arquivo .txt com o log do que foi importado?")
        if resp:
            arquivo_excel = self.ent_arquivo.get()
            nome_base = os.path.basename(arquivo_excel).split('.')[0] if arquivo_excel else "PLANILHA"
            nome_sugerido = f"LOG IMPORTACAO {nome_base}.txt"
            caminho = filedialog.asksaveasfilename(defaultextension=".txt", initialfile=nome_sugerido, filetypes=[("Text Files", "*.txt")])
            if caminho:
                with open(caminho, 'w', encoding='utf-8') as f:
                    for r in registros:
                        f.write(f"CONTA: {r['PLANO_CONTA']} | DESC: {r['PLANO_DESCRICAO']} | STATUS: Importado\n")
                messagebox.showinfo("Log Salvo", f"Arquivo salvo em:\n{caminho}")
                if messagebox.askyesno("Abrir Log", "Deseja abrir o arquivo de log agora?"):
                    try:
                        os.startfile(caminho)
                    except Exception as e:
                        messagebox.showerror("Erro", f"Erro ao abrir arquivo:\n{e}")

    def _restaurar_botoes(self):
        self.btn_cancelar.config(state=tk.DISABLED)
        self.btn_preview.config(state=tk.NORMAL)
        self.btn_abrir_planilha.config(state=tk.NORMAL)

    def _limpar_tela(self):
        self.ent_arquivo.delete(0, tk.END)
        self.cb_abas.set('')
        self.cb_abas['values'] = []
        self.ent_filtro_import.delete(0, tk.END)
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.registros_lidos = []
        self.progresso.configure(style="Horizontal.TProgressbar")
        self.progresso['value'] = 0
        self.lbl_status.config(text="Total de linhas lidas: 0 | Erros: 0")
        self.btn_preview.config(state=tk.DISABLED)

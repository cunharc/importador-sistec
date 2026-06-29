import tkinter as tk
from tkinter import ttk, messagebox
import os
import configparser
import sys
from PIL import Image, ImageTk
import datetime
import getpass
import socket
from telas.tela_importacao import TelaImportacao
from telas.tela_conexao import TelaConexao
from telas.tela_nfe import TelaNFe
from telas.tela_xml_produtos import TelaXmlProdutos
from telas.tela_ncm import TelaNcm
from telas.tela_cfop import TelaCfop
from telas.tela_icms import TelaIcms
from telas.tela_rt import TelaRt
from telas.tela_lista_precos import TelaListaPrecos
from telas.tela_auditoria_geral import TelaAuditoriaGeral
from telas.tela_auditoria_por_produto import TelaAuditoriaPorProduto
from telas.tela_sobre import TelaSobre
from telas.tela_importacao_planilha_produtos import TelaImportacaoPlanilhaProdutos
from telas.tela_importacao_planilha_clientes import TelaImportacaoPlanilhaClientes
from telas.tela_importacao_planilha_receber import TelaImportacaoPlanilhaReceber
from telas.tela_importacao_planilha_pagar import TelaImportacaoPlanilhaPagar
from telas.tela_importacao_planilha_lista_precos import TelaImportacaoPlanilhaListaPrecos
from telas.tela_importacao_planilha_tributacao import TelaImportacaoPlanilhaTributacao
from busca_logs import BuscaLogsWindow
from utils.firebird_service import FirebirdService
from utils.updater import verificar_e_atualizar
from version import get_info

class TelaInicial(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg="#F0F0F0")
        self.parent = parent
        self.tela_atual = None
        self.nome_tela_atual = None
        self.pack(fill=tk.BOTH, expand=True)
        self._criar_widgets()
        
        self.parent.bind('<Escape>', self._on_escape)
        self.parent.bind('<F5>', self._on_f5)
        
        self._limpar_logs_antigos()

    def resource_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def _criar_widgets(self):
        # --- CABEÇALHO ---
        header = tk.Frame(self, bg="#FFFFFF", height=80, highlightbackground="#CCCCCC", highlightthickness=1)
        header.pack(fill=tk.X, side=tk.TOP)
        
        logo_path = self.resource_path("sistec.jpg")
        if os.path.exists(logo_path):
            try:
                img = Image.open(logo_path)
                img.thumbnail((200, 80))
                self.logo_img = ImageTk.PhotoImage(img)
                tk.Label(header, image=self.logo_img, bg="#FFFFFF").pack(side=tk.LEFT, padx=20, pady=10)
            except Exception:
                pass
                
        tk.Label(header, text="CENTRAL DE IMPLANTAÇÃO", font=("Segoe UI", 16, "bold"), bg="#FFFFFF", fg="#003399").pack(side=tk.LEFT, padx=20)
        
        # --- STATUS DA CONEXÃO NO HEADER ---
        status_frame = tk.Frame(header, bg="#FFFFFF")
        status_frame.pack(side=tk.RIGHT, padx=10)
        
        # Versão no header
        tk.Label(header, text=get_info(), font=("Segoe UI", 9), bg="#FFFFFF", fg="#666666").pack(side=tk.RIGHT, padx=5, anchor=tk.SE)
        
        # Botão Configurar Banco embalado primeiro (à direita) para nunca sumir em monitores pequenos
        btn_config_db = tk.Button(status_frame, text="⚙ Configurar Banco", font=("Segoe UI", 9), bg="#F0F0F0", fg="#1A1A1A", relief=tk.SOLID, bd=1, cursor="hand2", command=self._abrir_config_banco)
        btn_config_db.pack(side=tk.RIGHT, padx=5)

        # Combo para Empresa/Filial com tamanho reduzido para telas menores
        self.cb_filial = ttk.Combobox(status_frame, width=25, state="readonly", cursor="hand2")
        self.cb_filial.pack(side=tk.RIGHT, padx=5)
        self.cb_filial.bind("<<ComboboxSelected>>", self._salvar_filial_selecionada)
        self.filiais_data = []
        
        status_labels = tk.Frame(status_frame, bg="#FFFFFF")
        status_labels.pack(side=tk.RIGHT, padx=5)
        
        self.lbl_status_db = tk.Label(status_labels, text="Verificando...", font=("Segoe UI", 10, "bold"), bg="#FFFFFF", fg="#F39C12")
        self.lbl_status_db.pack(anchor=tk.E)
        self.lbl_path_db = tk.Label(status_labels, text="", font=("Segoe UI", 8), bg="#FFFFFF", fg="#7F8C8D")
        self.lbl_path_db.pack(anchor=tk.E)
        
        # Atualiza o status de conexão ao abrir a central
        self.after(800, self._atualizar_status)

        # --- CONTEÚDO PRINCIPAL ---
        content = tk.Frame(self, bg="#F0F0F0")
        content.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        tk.Label(content, text="Módulos Disponíveis", font=("Segoe UI", 14), bg="#F0F0F0", fg="#1A1A1A").pack(anchor=tk.W, pady=(0, 10))

        filtros_frame = tk.Frame(content, bg="#F0F0F0")
        filtros_frame.pack(fill=tk.X, pady=(0, 15))

        self.filtro_botoes = {}
        for f_texto, f_chave in [("📋 TODOS", "todos"), ("📊 EXCEL", "excel"), ("📄 XML", "xml")]:
            btn = tk.Button(filtros_frame, text=f_texto,
                            font=("Segoe UI", 10), bg="#E0E0E0", fg="#1A1A1A",
                            relief=tk.FLAT, cursor="hand2", padx=20, pady=5,
                            command=lambda f=f_chave: self._aplicar_filtro(f))
            btn.pack(side=tk.LEFT, padx=3)
            self.filtro_botoes[f_chave] = btn

        self.card_container = tk.Frame(content, bg="#F0F0F0")
        self.card_container.pack(fill=tk.BOTH, expand=True)

        self.card_frames = {}
        for categoria in ('todos', 'excel', 'xml'):
            frame_cat = self._criar_grade_filtrada(self.card_container, categoria)
            self.card_frames[categoria] = frame_cat

        self._aplicar_filtro('todos')

        # --- RODAPÉ ---
        bottom_frame = tk.Frame(self, bg="#F0F0F0")
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=20, padx=20)
        
        btn_sobre = tk.Button(bottom_frame, text="ℹ️ Sobre o Sistema", font=("Segoe UI", 10), bg="#FFFFFF", fg="#003399", relief=tk.SOLID, bd=1, cursor="hand2", padx=15, pady=5, command=self._abrir_sobre)
        btn_sobre.pack(side=tk.LEFT)

        btn_logs = tk.Button(bottom_frame, text="📄 Ver Logs de Hoje", font=("Segoe UI", 10), bg="#FFFFFF", fg="#1A1A1A", relief=tk.SOLID, bd=1, cursor="hand2", padx=15, pady=5, command=self._abrir_logs)
        btn_logs.pack(side=tk.LEFT, padx=(10, 0))

        btn_update = tk.Button(bottom_frame, text="🔄 Atualizar Sistema", font=("Segoe UI", 10, "bold"), bg="#27AE60", fg="#FFFFFF", relief=tk.SOLID, bd=1, cursor="hand2", padx=15, pady=5, command=lambda: verificar_e_atualizar(self.winfo_toplevel()))
        btn_update.pack(side=tk.LEFT, padx=(10, 0))

        btn_fechar = tk.Button(bottom_frame, text="Sair do Sistema", font=("Segoe UI", 10), bg="#FFFFFF", fg="#1A1A1A", relief=tk.SOLID, bd=1, cursor="hand2", padx=15, pady=5, command=self.parent.quit)
        btn_fechar.pack(side=tk.RIGHT)

    def _criar_grade_filtrada(self, parent, filtro):
        modulos = [
            ("Plano de Contas", "Importação estruturada do plano de contas via planilha Excel diretamente para o banco de dados Firebird.",
             "#C8001E", "_abrir_importacao", "Icone_plano.jpg", "📑", ("excel",)),
            ("Clientes/Fornec. NF-e", "Importação automática de clientes e fornecedores via leitura de arquivos XML de Notas Fiscais (NF-e 4.00).",
             "#F39C12", "_abrir_nfe", "nfe_cli.jpg", "👥", ("xml",)),
            ("Faixas de ICMS", "Construção e auditoria das regras de ICMS por estado baseado no histórico de XMLs.",
             "#8E44AD", "_abrir_icms", None, "🗺️", ("xml",)),
            ("Tributação por NCM", "Gestão de regras tributárias e alíquotas baseadas na Nomenclatura Comum do Mercosul.",
             "#2980B9", "_abrir_ncm", None, "🏷️", ("xml",)),
            ("Tributação CFOP", "Definição de naturezas de operação e regras contábeis por CFOP.",
             "#D35400", "_abrir_cfop", None, "🚚", ("xml",)),
            ("Produtos & Consolidado", "Auditoria final por produto, cruzando NCM, CFOP e ICMS para cadastro e correção.",
             "#27AE60", "_abrir_xml_produtos", "xml_produtos.jpg", "📦", ("xml",)),
            ("Reforma Tributária (RT)", "Construção e auditoria das regras de IBS e CBS baseadas nos XMLs.",
             "#F012BE", "_abrir_rt", None, "🏛️", ("xml",)),
            ("Lista de Preços XML", "Crie ou atualize Listas de Preços de Venda capturando automaticamente o valor unitário dos XMLs.",
             "#16A085", "_abrir_lista_precos", None, "💲", ("xml",)),
            ("Visão Gerencial (Completa)", "Auditoria completa agrupando Produto, NCM, CFOP, ICMS, PIS/COF e RT com exportação.",
             "#34495E", "_abrir_auditoria_geral", None, "📊", ("xml",)),
            ("Importar Produtos (Excel)", "Importação e auto-cadastro de produtos, grupos e subgrupos via planilha (XLSX/CSV).",
             "#27AE60", "_abrir_importacao_planilha_produtos", None, "📝", ("excel",)),
            ("Auditoria por Produto", "Auditoria cruzando todas as variações de tributação que um mesmo produto sofreu nos XMLs.",
             "#8E44AD", "_abrir_auditoria_produto", None, "🔎", ("xml",)),
            ("Busca em Logs ERP", "Varredura avançada e rápida em arquivos .txt de log gerados pelo ERP.",
             "#F39C12", "_abrir_busca_logs", None, "🕵️‍♂️", ()),
            ("Importar Clientes (Excel)", "Importação de clientes com mapeamento de colunas via planilha (XLSX/CSV) para cadastro no ERP.",
             "#003399", "_abrir_importacao_planilha_clientes", None, "👤", ("excel",)),
            ("Importar Contas a Receber (Excel)", "Importação de títulos e parcelas de contas a receber com mapeamento de colunas via planilha (XLSX/CSV).",
             "#E67E22", "_abrir_importacao_planilha_receber", None, "💰", ("excel",)),
            ("Importar Contas a Pagar (Excel)", "Importação de títulos e parcelas de contas a pagar com mapeamento de colunas via planilha (XLSX/CSV).",
             "#C0392B", "_abrir_importacao_planilha_pagar", None, "💳", ("excel",)),
            ("Importar Lista de Preços (Excel)", "Importação de tabela de preços com mapeamento de colunas via planilha (XLSX/CSV) e validação contra o cadastro do ERP.",
             "#E67E22", "_abrir_importacao_planilha_lista_precos", None, "📊", ("excel",)),
            ("Importar Tributação (Excel)", "Importação completa de tributação por NCM via planilha: ICMS, PIS, COFINS e Reforma Tributária com criação de faixas e regras.",
             "#F012BE", "_abrir_importacao_planilha_tributacao", None, "📋", ("excel",)),
        ]

        if filtro == 'todos':
            selecionados = modulos
        else:
            selecionados = [m for m in modulos if filtro in m[6]]

        frame = tk.Frame(parent, bg="#F0F0F0")

        if not selecionados:
            return frame

        cols = 3
        rows = (len(selecionados) + cols - 1) // cols

        for i in range(cols):
            frame.grid_columnconfigure(i, weight=1, uniform="col", minsize=280)
        for i in range(rows):
            frame.grid_rowconfigure(i, weight=1, uniform="row")

        for idx, mod in enumerate(selecionados):
            r = idx // cols
            c = idx % cols
            titulo, descricao, cor_borda, nome_comando, icone_path, icone_emoji, _ = mod
            comando = getattr(self, nome_comando)
            path = self.resource_path(icone_path) if icone_path else None
            self._criar_card_modulo(frame, r, c, titulo, descricao, cor_borda, comando, path, icone_emoji)

        return frame

    def _aplicar_filtro(self, filtro):
        for cat, frame in self.card_frames.items():
            if cat == filtro:
                frame.pack(fill=tk.BOTH, expand=True)
            else:
                frame.pack_forget()
        for cat, btn in self.filtro_botoes.items():
            if cat == filtro:
                btn.config(bg="#003399", fg="white", font=("Segoe UI", 10, "bold"))
            else:
                btn.config(bg="#E0E0E0", fg="#1A1A1A", font=("Segoe UI", 10))

    def _criar_card_modulo(self, parent, row, col, titulo, descricao, cor_borda, comando, icone_path=None, icone_emoji="📦"):
        container = tk.Frame(parent, bg="#F0F0F0")
        container.grid(row=row, column=col, sticky="nsew", padx=8, pady=8)
        
        card = tk.Frame(container, bg="#FFFFFF", highlightbackground=cor_borda, highlightthickness=2, cursor="hand2")
        card.pack(fill=tk.BOTH, expand=True, ipadx=10, ipady=10)
        card.bind("<Button-1>", lambda e: comando())
        
        elementos_hover = [card]

        # Container interno para dividir Ícone (Esquerda) e Textos (Direita)
        inner_frame = tk.Frame(card, bg="#FFFFFF", cursor="hand2")
        inner_frame.pack(fill=tk.BOTH, expand=True)
        inner_frame.bind("<Button-1>", lambda e: comando())
        elementos_hover.append(inner_frame)
        
        if icone_path and os.path.exists(icone_path):
            try:
                img = Image.open(icone_path)
                img.thumbnail((64, 64)) # Ajuste o tamanho do ícone aqui
                img_tk = ImageTk.PhotoImage(img)
                lbl_icon = tk.Label(inner_frame, image=img_tk, bg="#FFFFFF", cursor="hand2")
                lbl_icon.image = img_tk # Mantém a referência da imagem na memória
                lbl_icon.pack(side=tk.LEFT, padx=(0, 15), anchor=tk.N)
                lbl_icon.bind("<Button-1>", lambda e: comando())
                elementos_hover.append(lbl_icon)
            except Exception as e:
                print("Erro ao carregar ícone do card:", e)
                lbl_icon = tk.Label(inner_frame, text=icone_emoji, font=("Segoe UI", 40), bg="#FFFFFF", fg=cor_borda, cursor="hand2")
                lbl_icon.pack(side=tk.LEFT, padx=(0, 15), anchor=tk.N)
                lbl_icon.bind("<Button-1>", lambda e: comando())
                elementos_hover.append(lbl_icon)
        else:
            lbl_icon = tk.Label(inner_frame, text=icone_emoji, font=("Segoe UI", 40), bg="#FFFFFF", fg=cor_borda, cursor="hand2")
            lbl_icon.pack(side=tk.LEFT, padx=(0, 15), anchor=tk.N)
            lbl_icon.bind("<Button-1>", lambda e: comando())
            elementos_hover.append(lbl_icon)
                
        text_frame = tk.Frame(inner_frame, bg="#FFFFFF", cursor="hand2")
        text_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        text_frame.bind("<Button-1>", lambda e: comando())
        elementos_hover.append(text_frame)
        
        lbl_titulo = tk.Label(text_frame, text=titulo, font=("Segoe UI", 12, "bold"), bg="#FFFFFF", fg="#1A1A1A", cursor="hand2")
        lbl_titulo.pack(anchor=tk.W, pady=(0, 5))
        lbl_titulo.bind("<Button-1>", lambda e: comando())
        elementos_hover.append(lbl_titulo)
        
        lbl_desc = tk.Label(text_frame, text=descricao, font=("Segoe UI", 9), bg="#FFFFFF", fg="#1A1A1A", justify=tk.LEFT, cursor="hand2", wraplength=240)
        lbl_desc.pack(fill=tk.X, anchor=tk.W)
        lbl_desc.bind("<Button-1>", lambda e: comando())
        elementos_hover.append(lbl_desc)
        
        btn = tk.Label(text_frame, text="ACESSAR MÓDULO ➔", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg=cor_borda, cursor="hand2")
        btn.pack(anchor=tk.W, pady=(15, 0))
        btn.bind("<Button-1>", lambda e: comando())
        elementos_hover.append(btn)

        # --- CONFIGURAÇÃO DO EFEITO HOVER ---
        cor_normal = "#FFFFFF"
        cor_hover = "#F5F5F5"

        def on_enter(e):
            for el in elementos_hover:
                el.configure(bg=cor_hover)

        def on_leave(e):
            for el in elementos_hover:
                el.configure(bg=cor_normal)

        # Aplica os eventos a todos os pedacinhos do cartão
        for el in elementos_hover:
            el.bind("<Enter>", on_enter)
            el.bind("<Leave>", on_leave)
            
    def _abrir_logs(self):
        try:
            data_atual = datetime.datetime.now().strftime('%Y-%m-%d')
            nome_arquivo = f"acessos_modulos_{data_atual}.log"
            if os.path.exists(nome_arquivo):
                os.startfile(os.path.normpath(nome_arquivo)) # Abre nativamente no Bloco de Notas do Windows
            else:
                messagebox.showinfo("Logs", "Nenhum log registrado para o dia de hoje ainda.")
        except Exception as e:
            print(f"Erro ao abrir logs: {e}")

    def _registrar_log(self, modulo, acao):
        try:
            usuario = getpass.getuser()
            computador = socket.gethostname()
            data_atual = datetime.datetime.now()
            nome_arquivo = f"acessos_modulos_{data_atual.strftime('%Y-%m-%d')}.log"
            with open(nome_arquivo, "a", encoding="utf-8") as f:
                data_hora = data_atual.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{data_hora}] [{computador}\\{usuario}] {acao}: {modulo}\n")
        except Exception as e:
            print(f"Erro ao registrar log: {e}")

    def _limpar_logs_antigos(self):
        try:
            hoje = datetime.datetime.now()
            for arquivo in os.listdir("."):
                if arquivo.startswith("acessos_modulos_") and arquivo.endswith(".log"):
                    try:
                        data_str = arquivo.replace("acessos_modulos_", "").replace(".log", "")
                        data_arquivo = datetime.datetime.strptime(data_str, "%Y-%m-%d")
                        if (hoje - data_arquivo).days > 30:
                            os.remove(arquivo)
                    except ValueError:
                        pass # Ignora caso a data do arquivo não consiga ser lida
        except Exception as e:
            print(f"Erro ao limpar logs antigos: {e}")

    def _on_escape(self, event):
        # Evita acionar o "Voltar" se o usuário estiver num Pop-up ou Toplevel
        focus_widget = self.winfo_toplevel().focus_get()
        if focus_widget and focus_widget.winfo_toplevel() != self.winfo_toplevel():
            return 
            
        if self.tela_atual and hasattr(self.tela_atual, '_fechar_tela'):
            self.tela_atual._fechar_tela()

    def _on_f5(self, event=None):
        # Força a atualização do status do banco de dados/filiais e do combo
        self._atualizar_status()

    def _auto_descobrir_banco(self):
        caminho_ini = ""
        if os.path.exists(r"C:\UTILIT\SISTEC.INI"):
            caminho_ini = r"C:\UTILIT\SISTEC.INI"
        elif os.path.exists(r"C:\Sistec\launcher.ini"):
            caminho_ini = r"C:\Sistec\launcher.ini"
            
        if not caminho_ini:
            return None, None, None, None, None
            
        try:
            nome_arquivo = os.path.basename(caminho_ini).lower()
            if nome_arquivo == 'launcher.ini':
                config_l = configparser.ConfigParser(strict=False)
                try:
                    config_l.read(caminho_ini, encoding='utf-8')
                except Exception:
                    config_l.read(caminho_ini, encoding='latin-1')
                    
                if config_l.has_section('Sistec'):
                    db_str = config_l.get('Sistec', 'Database', fallback='')
                    usuario = config_l.get('Sistec', 'User_Name', fallback='sysdba')
                    senha = config_l.get('Sistec', 'Password', fallback='masterkey')
                    if db_str:
                        parts = db_str.split(':', 1)
                        if len(parts) == 2 and len(parts[0]) > 1:
                            servidor_porta = parts[0]
                            caminho_banco = parts[1]
                            if '/' in servidor_porta:
                                srv_parts = servidor_porta.split('/')
                                servidor = srv_parts[0]
                                porta = srv_parts[1]
                            else:
                                servidor = servidor_porta
                                porta = '3050'
                        else:
                            servidor = 'localhost'
                            porta = '3050'
                            caminho_banco = db_str
                        return caminho_banco, servidor, porta, usuario, senha
            else:
                with open(caminho_ini, 'r', encoding='latin-1', errors='ignore') as f:
                    dentro_bancos_local = False
                    for linha in f:
                        linha = linha.strip()
                        if "BANCOS LOCAL" in linha.upper():
                            dentro_bancos_local = True
                            continue
                        if dentro_bancos_local and linha.lower().startswith('database='):
                            db_path = linha.split('=', 1)[1].strip()
                            return db_path, "localhost", "3050", "SYSDBA", "masterkey"
        except Exception:
            pass
        return None, None, None, None, None

    def _atualizar_status(self):
        config = configparser.ConfigParser()
        try:
            config.read('config.ini', encoding='utf-8-sig')
        except Exception:
            config.read('config.ini', encoding='latin-1')
        caminho_banco = config.get('FIREBIRD', 'caminho_banco', fallback='')
        
        # AUTO-DISCOVERY SE NÃO ESTIVER CONFIGURADO
        if not caminho_banco:
            caminho_banco, servidor, porta, usuario, senha = self._auto_descobrir_banco()
            if caminho_banco:
                if not config.has_section('FIREBIRD'):
                    config.add_section('FIREBIRD')
                config.set('FIREBIRD', 'servidor', servidor)
                config.set('FIREBIRD', 'porta', porta)
                config.set('FIREBIRD', 'caminho_banco', caminho_banco)
                config.set('FIREBIRD', 'usuario', usuario)
                config.set('FIREBIRD', 'senha', senha)
                try:
                    with open('config.ini', 'w', encoding='utf-8') as f:
                        config.write(f)
                except Exception:
                    pass

        texto_banco = ""
        if caminho_banco:
            nome_arquivo = os.path.basename(caminho_banco)
            if os.path.exists(caminho_banco):
                tamanho_mb = os.path.getsize(caminho_banco) / (1024 * 1024)
                texto_banco = f"{nome_arquivo} ({tamanho_mb:.1f} MB)"
            else:
                texto_banco = nome_arquivo
                
        fbclient_ini = config.get('FIREBIRD', 'fbclient', fallback='').strip()
        fbclient_path = self.resource_path(fbclient_ini) if fbclient_ini else ''

        config_db = {
            'host': config.get('FIREBIRD', 'servidor', fallback='127.0.0.1'),
            'port': config.get('FIREBIRD', 'porta', fallback='3050'),
            'database': config.get('FIREBIRD', 'caminho_banco', fallback=''),
            'user': config.get('FIREBIRD', 'usuario', fallback='SYSDBA'),
            'password': config.get('FIREBIRD', 'senha', fallback='masterkey'),
            'fbclient': fbclient_path
        }

        try:
            with FirebirdService(config_db) as fb_conn:
                self.lbl_status_db.config(text="🟢 Conectado ao Banco", fg="#27AE60")
                self.lbl_path_db.config(text=texto_banco)
                
                sql = "SELECT F.FILIAL_EMPRESA, F.FILIAL_CODIGO, F.FILIAL_FANTASIA, F.FILIAL_UF, E.EMP_NOME FROM TABELA_FILIAL F JOIN TABELA_EMPRESA E ON F.FILIAL_EMPRESA = E.EMP_CODIGO"
                self.filiais_data = fb_conn.query(sql)
                
                combo_values = []
                selecionado_idx = 0
                emp_salva = config.get('IMPORTACAO', 'empresa', fallback='')
                fil_salva = config.get('IMPORTACAO', 'filial', fallback='')
                
                for idx, fil in enumerate(self.filiais_data):
                    emp_cod = str(fil.get('filial_empresa', ''))
                    fil_cod = str(fil.get('filial_codigo', ''))
                    fantasia = str(fil.get('filial_fantasia') or fil.get('emp_nome', ''))
                    uf = str(fil.get('filial_uf', ''))
                    desc = f"Emp: {emp_cod} | Fil: {fil_cod} - {fantasia} ({uf})"
                    combo_values.append(desc)
                    if emp_cod == emp_salva and fil_cod == fil_salva:
                        selecionado_idx = idx
                        
                self.cb_filial['values'] = combo_values
                if combo_values:
                    self.cb_filial.current(selecionado_idx)
                    self._salvar_filial_selecionada(None)
        except Exception as e:
            # Fallback: pergunta se deseja usar o banco descoberto automaticamente
            if caminho_banco:
                caminho_auto, servidor_auto, porta_auto, usuario_auto, senha_auto = self._auto_descobrir_banco()
                if caminho_auto and caminho_auto != caminho_banco:
                    resposta = messagebox.askyesno(
                        "Banco não encontrado",
                        f"O banco configurado não foi encontrado:\n{caminho_banco}\n\n"
                        f"Foi detectado um banco em:\n{caminho_auto}\n\n"
                        "Deseja usar este banco?",
                        parent=self.parent
                    )
                    if resposta:
                        try:
                            config_auto = {
                                'host': servidor_auto, 'port': porta_auto, 'database': caminho_auto,
                                'user': usuario_auto, 'password': senha_auto,
                                'fbclient': self.resource_path(config.get('FIREBIRD', 'fbclient', fallback='').strip()) or ''
                            }
                            with FirebirdService(config_auto) as _:
                                config.set('FIREBIRD', 'servidor', servidor_auto)
                                config.set('FIREBIRD', 'porta', porta_auto)
                                config.set('FIREBIRD', 'caminho_banco', caminho_auto)
                                config.set('FIREBIRD', 'usuario', usuario_auto)
                                config.set('FIREBIRD', 'senha', senha_auto)
                                with open('config.ini', 'w', encoding='utf-8') as f:
                                    config.write(f)
                                self.after(100, self._atualizar_status)
                                return
                        except Exception:
                            pass
            print("Erro na auto-conexão da Tela Inicial:", e)
            self.lbl_status_db.config(text="🔴 Não Conectado", fg="#E74C3C")
            self.lbl_path_db.config(text="")
            self.cb_filial.set('')
            self.cb_filial['values'] = []

    def _salvar_filial_selecionada(self, event):
        idx = self.cb_filial.current()
        if idx >= 0 and idx < len(self.filiais_data):
            fil = self.filiais_data[idx]
            config = configparser.ConfigParser()
            config.read('config.ini', encoding='utf-8')
            if not config.has_section('IMPORTACAO'):
                config.add_section('IMPORTACAO')
            
            config.set('IMPORTACAO', 'empresa', str(fil.get('filial_empresa', '')))
            config.set('IMPORTACAO', 'filial', str(fil.get('filial_codigo', '')))
            config.set('IMPORTACAO', 'uf', str(fil.get('filial_uf', '')))
            
            with open('config.ini', 'w', encoding='utf-8') as f:
                config.write(f)

    def _abrir_config_banco(self):
        TelaConexao(self.winfo_toplevel(), callback_status=self._atualizar_status)

    def _abrir_nfe(self):
        self.pack_forget() 
        self.winfo_toplevel().title("Clientes/Fornec. NF-e - Implantação Sistec")
        self.nome_tela_atual = "Clientes/Fornec. NF-e"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaNFe(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_xml_produtos(self):
        self.pack_forget()
        self.winfo_toplevel().title("Produtos & Consolidado - Implantação Sistec")
        self.nome_tela_atual = "Produtos & Consolidado"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaXmlProdutos(self.parent, callback_voltar=self._voltar_inicial)
        
    def _abrir_ncm(self):
        self.pack_forget()
        self.winfo_toplevel().title("Tributação por NCM - Implantação Sistec")
        self.nome_tela_atual = "Tributação por NCM"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaNcm(self.parent, callback_voltar=self._voltar_inicial)
        
    def _abrir_cfop(self):
        self.pack_forget()
        self.winfo_toplevel().title("Tributação CFOP - Implantação Sistec")
        self.nome_tela_atual = "Tributação CFOP"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaCfop(self.parent, callback_voltar=self._voltar_inicial)
        
    def _abrir_icms(self):
        self.pack_forget()
        self.winfo_toplevel().title("Faixas de ICMS - Implantação Sistec")
        self.nome_tela_atual = "Faixas de ICMS"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaIcms(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_rt(self):
        self.pack_forget()
        self.winfo_toplevel().title("Reforma Tributária (RT) - Implantação Sistec")
        self.nome_tela_atual = "Reforma Tributária (RT)"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaRt(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_lista_precos(self):
        self.pack_forget()
        self.winfo_toplevel().title("Lista de Preços XML - Implantação Sistec")
        self.nome_tela_atual = "Lista de Preços XML"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaListaPrecos(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_auditoria_geral(self):
        self.pack_forget()
        self.winfo_toplevel().title("Visão Gerencial (Completa) - Implantação Sistec")
        self.nome_tela_atual = "Visão Gerencial (Completa)"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaAuditoriaGeral(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_importacao(self):
        self.pack_forget() # Oculta a tela inicial temporariamente
        self.winfo_toplevel().title("Plano de Contas - Implantação Sistec")
        self.nome_tela_atual = "Plano de Contas"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaImportacao(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_importacao_planilha_produtos(self):
        self.pack_forget()
        self.winfo_toplevel().title("Importação de Produtos via Planilha - Implantação Sistec")
        self.nome_tela_atual = "Importação de Produtos via Planilha"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaImportacaoPlanilhaProdutos(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_importacao_planilha_clientes(self):
        self.pack_forget()
        self.winfo_toplevel().title("Importa\u00e7\u00e3o de Clientes via Planilha - Implanta\u00e7\u00e3o Sistec")
        self.nome_tela_atual = "Importa\u00e7\u00e3o de Clientes via Planilha"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaImportacaoPlanilhaClientes(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_importacao_planilha_receber(self):
        self.pack_forget()
        self.winfo_toplevel().title("Importa\u00e7\u00e3o de Contas a Receber via Planilha - Implanta\u00e7\u00e3o Sistec")
        self.nome_tela_atual = "Importa\u00e7\u00e3o de Contas a Receber via Planilha"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaImportacaoPlanilhaReceber(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_importacao_planilha_pagar(self):
        self.pack_forget()
        self.winfo_toplevel().title("Importa\u00e7\u00e3o de Contas a Pagar via Planilha - Implanta\u00e7\u00e3o Sistec")
        self.nome_tela_atual = "Importa\u00e7\u00e3o de Contas a Pagar via Planilha"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaImportacaoPlanilhaPagar(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_importacao_planilha_lista_precos(self):
        self.pack_forget()
        self.winfo_toplevel().title("Importação de Lista de Preços via Planilha - Implantação Sistec")
        self.nome_tela_atual = "Importação de Lista de Preços via Planilha"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaImportacaoPlanilhaListaPrecos(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_importacao_planilha_tributacao(self):
        self.pack_forget()
        self.winfo_toplevel().title("Importação de Tributação via Planilha - Implantação Sistec")
        self.nome_tela_atual = "Importação de Tributação via Planilha"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaImportacaoPlanilhaTributacao(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_auditoria_produto(self):
        self.pack_forget()
        self.winfo_toplevel().title("Auditoria por Produto - Implantação Sistec")
        self.nome_tela_atual = "Auditoria por Produto"
        self._registrar_log(self.nome_tela_atual, "ENTROU")
        self.tela_atual = TelaAuditoriaPorProduto(self.parent, callback_voltar=self._voltar_inicial)

    def _abrir_busca_logs(self):
        self._registrar_log("Busca de Logs ERP", "ABRIU")
        # Abre como uma janela sobreposta sem fechar a central (Toplevel nativo do módulo)
        BuscaLogsWindow(parent=self.winfo_toplevel())

    def _abrir_sobre(self):
        self._registrar_log("Sobre o Sistema", "ABRIU")
        TelaSobre(self.winfo_toplevel())

    def _voltar_inicial(self):
        if self.nome_tela_atual:
            self._registrar_log(self.nome_tela_atual, "SAIU")
            self.nome_tela_atual = None
        self.tela_atual = None # Limpa a referência para o Garbage Collector destruir a tela fechada
        self.winfo_toplevel().title("Implantação Sistec")
        self.pack(fill=tk.BOTH, expand=True) # Mostra a tela inicial de volta


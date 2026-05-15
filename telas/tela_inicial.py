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
from telas.tela_sobre import TelaSobre
from utils.firebird_service import FirebirdService
from utils.updater import verificar_e_atualizar
from version import get_info, get_modulos_prontos, get_modulos_em_ajuste

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
        
        # Versão no header
        tk.Label(header, text=get_info(), font=("Segoe UI", 9), bg="#FFFFFF", fg="#666666").pack(side=tk.RIGHT, padx=10, anchor=tk.SE)
        
        # --- STATUS DA CONEXÃO NO HEADER ---
        status_frame = tk.Frame(header, bg="#FFFFFF")
        status_frame.pack(side=tk.RIGHT, padx=20)
        
        status_labels = tk.Frame(status_frame, bg="#FFFFFF")
        status_labels.pack(side=tk.LEFT, padx=10)
        
        self.lbl_status_db = tk.Label(status_labels, text="Verificando...", font=("Segoe UI", 10, "bold"), bg="#FFFFFF", fg="#F39C12")
        self.lbl_status_db.pack(anchor=tk.E)
        self.lbl_path_db = tk.Label(status_labels, text="", font=("Segoe UI", 8), bg="#FFFFFF", fg="#7F8C8D")
        self.lbl_path_db.pack(anchor=tk.E)

        # Combo para Empresa/Filial
        self.cb_filial = ttk.Combobox(status_frame, width=45, state="readonly", cursor="hand2")
        self.cb_filial.pack(side=tk.LEFT, padx=10)
        self.cb_filial.bind("<<ComboboxSelected>>", self._salvar_filial_selecionada)
        self.filiais_data = []

        btn_config_db = tk.Button(status_frame, text="⚙ Configurar Banco", font=("Segoe UI", 9), bg="#F0F0F0", fg="#1A1A1A", relief=tk.SOLID, bd=1, cursor="hand2", command=self._abrir_config_banco)
        btn_config_db.pack(side=tk.LEFT)
        
        # Atualiza o status de conexão ao abrir a central
        self.after(800, self._atualizar_status)

        # --- CONTEÚDO PRINCIPAL ---
        content = tk.Frame(self, bg="#F0F0F0")
        content.pack(fill=tk.BOTH, expand=True, padx=40, pady=40)
        
        tk.Label(content, text="Módulos Disponíveis", font=("Segoe UI", 14), bg="#F0F0F0", fg="#1A1A1A").pack(anchor=tk.W, pady=(0, 20))
        
        # Grade de Cards
        cards_frame = tk.Frame(content, bg="#F0F0F0")
        cards_frame.pack(fill=tk.X, expand=False, pady=10)
        
        for i in range(3):
            cards_frame.grid_columnconfigure(i, weight=1, uniform="col")
        cards_frame.grid_rowconfigure(0, weight=1, uniform="row")
        cards_frame.grid_rowconfigure(1, weight=1, uniform="row")
        cards_frame.grid_rowconfigure(2, weight=1, uniform="row")
        
        # Card 1: Importar Plano de Contas
        self._criar_card_modulo(
            parent=cards_frame, row=0, col=0,
            titulo="Plano de Contas",
            descricao="Importação estruturada do plano de contas via planilha Excel diretamente para o banco de dados Firebird.",
            cor_borda="#C8001E",
            comando=self._abrir_importacao,
            icone_path=self.resource_path("Icone_plano.jpg"),
            icone_emoji="📑"
        )
        
        # Card 2: Importar Clientes de NF-e
        self._criar_card_modulo(
            parent=cards_frame, row=0, col=1,
            titulo="Clientes/Fornec. NF-e",
            descricao="Importação automática de clientes e fornecedores via leitura de arquivos XML de Notas Fiscais (NF-e 4.00).",
            cor_borda="#F39C12",
            comando=self._abrir_nfe,
            icone_path=self.resource_path("nfe_cli.jpg"),
            icone_emoji="👥"
        )

        # Card 3: Faixas de ICMS
        self._criar_card_modulo(
            parent=cards_frame, row=0, col=2,
            titulo="Faixas de ICMS",
            descricao="Construção e auditoria das regras de ICMS por estado baseado no histórico de XMLs.",
            cor_borda="#8E44AD", # Roxo para ICMS
            comando=self._abrir_icms,
            icone_path=None,
            icone_emoji="🗺️"
        )

        # Card 4: Tributação NCM
        self._criar_card_modulo(
            parent=cards_frame, row=1, col=0,
            titulo="Tributação por NCM",
            descricao="Gestão de regras tributárias e alíquotas baseadas na Nomenclatura Comum do Mercosul.",
            cor_borda="#2980B9", # Azul
            comando=self._abrir_ncm,
            icone_path=None,
            icone_emoji="🏷️"
        )

        # Card 5: Tributação CFOP
        self._criar_card_modulo(
            parent=cards_frame, row=1, col=1,
            titulo="Tributação CFOP",
            descricao="Definição de naturezas de operação e regras contábeis por CFOP.",
            cor_borda="#D35400", # Laranja avermelhado
            comando=self._abrir_cfop,
            icone_path=None,
            icone_emoji="🚚"
        )

        # Card 6: Validador XML - Produtos
        self._criar_card_modulo(
            parent=cards_frame, row=1, col=2,
            titulo="Produtos & Consolidado",
            descricao="Auditoria final por produto, cruzando NCM, CFOP e ICMS para cadastro e correção.",
            cor_borda="#27AE60", # Verde
            comando=self._abrir_xml_produtos,
            icone_path=self.resource_path("xml_produtos.jpg"),
            icone_emoji="📦"
        )

        # Card 7: Reforma Tributária
        self._criar_card_modulo(
            parent=cards_frame, row=2, col=0,
            titulo="Reforma Tributária (RT)",
            descricao="Construção e auditoria das regras de IBS e CBS baseadas nos XMLs.",
            cor_borda="#F012BE", # Fuchsia/Magenta
            comando=self._abrir_rt,
            icone_path=None,
            icone_emoji="🏛️"
        )

        # Card 8: Tabela de Preços XML
        self._criar_card_modulo(
            parent=cards_frame, row=2, col=1,
            titulo="Lista de Preços XML",
            descricao="Crie ou atualize Listas de Preços de Venda capturando automaticamente o valor unitário dos XMLs.",
            cor_borda="#16A085", # Verde mar
            comando=self._abrir_lista_precos,
            icone_path=None,
            icone_emoji="💲"
        )

        # Card 9: Auditoria Geral (Gerencial)
        self._criar_card_modulo(
            parent=cards_frame, row=2, col=2,
            titulo="Visão Gerencial (Completa)",
            descricao="Auditoria completa agrupando Produto, NCM, CFOP, ICMS, PIS/COF e RT com exportação.",
            cor_borda="#34495E", # Azul Escuro
            comando=self._abrir_auditoria_geral,
            icone_path=None,
            icone_emoji="📊"
        )

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

    def _criar_card_modulo(self, parent, row, col, titulo, descricao, cor_borda, comando, icone_path=None, icone_emoji="📦"):
        container = tk.Frame(parent, bg="#F0F0F0")
        container.grid(row=row, column=col, sticky="nsew", padx=10, pady=10)
        
        card = tk.Frame(container, bg="#FFFFFF", highlightbackground=cor_borda, highlightthickness=2, cursor="hand2")
        card.pack(fill=tk.BOTH, expand=True, ipadx=15, ipady=15)
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
                os.startfile(nome_arquivo) # Abre nativamente no Bloco de Notas do Windows
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

    def _em_desenvolvimento(self):
        from tkinter import messagebox
        messagebox.showinfo("Em Desenvolvimento", "Este módulo está sendo migrado do sistema antigo e estará disponível em breve!")
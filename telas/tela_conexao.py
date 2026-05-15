import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import configparser
import os
import sys
import fdb

class TelaConexao(tk.Toplevel):
    def __init__(self, parent, callback_status=None):
        super().__init__(parent)
        self.callback_status = callback_status
        self.title("Configuração de Conexão — Firebird")
        self.geometry("600x300")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        
        icon_path = self.resource_path("icon.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)

        self.config = configparser.ConfigParser()
        self.config.read('config.ini', encoding='utf-8')

        self._criar_widgets()
        self._carregar_dados()

    def resource_path(self, relative_path):
        if not relative_path or os.path.isabs(relative_path):
            return relative_path
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
            
        caminho_completo = os.path.join(base_path, relative_path)
        if os.path.exists(caminho_completo):
            return caminho_completo
        return relative_path

    def _criar_widgets(self):
        frame = ttk.Frame(self, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        # Servidor e Porta
        frame_serv = ttk.Frame(frame)
        frame_serv.grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=5)
        
        ttk.Label(frame_serv, text="Servidor:").pack(side=tk.LEFT)
        self.ent_servidor = ttk.Entry(frame_serv, width=20)
        self.ent_servidor.pack(side=tk.LEFT, padx=(5, 15))
        
        ttk.Label(frame_serv, text="Porta:").pack(side=tk.LEFT)
        self.ent_porta = ttk.Entry(frame_serv, width=8)
        self.ent_porta.pack(side=tk.LEFT, padx=5)

        # Caminho do banco
        ttk.Label(frame, text="Caminho do banco (.fdb):").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.ent_banco = ttk.Entry(frame, width=40)
        self.ent_banco.grid(row=1, column=1, pady=5, padx=5)
        
        frame_btn_banco = ttk.Frame(frame)
        frame_btn_banco.grid(row=1, column=2, pady=5, sticky=tk.W)
        ttk.Button(frame_btn_banco, text="📁", width=3, command=self._buscar_banco).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_btn_banco, text="Ler INI", command=self._buscar_ini).pack(side=tk.LEFT, padx=2)

        # Usuário
        ttk.Label(frame, text="Usuário:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.ent_usuario = ttk.Entry(frame, width=20)
        self.ent_usuario.grid(row=2, column=1, sticky=tk.W, pady=5, padx=5)

        # Senha
        ttk.Label(frame, text="Senha:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.ent_senha = ttk.Entry(frame, width=20, show="*")
        self.ent_senha.grid(row=3, column=1, sticky=tk.W, pady=5, padx=5)

        # Caminho fbclient.dll
        ttk.Label(frame, text="fbclient.dll (Versão):").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.cb_fbclient = ttk.Combobox(frame, width=37, values=[
            "",
            "fbclient_3.dll",
            "fbclient_4.dll",
            "fbclient_5.dll"
        ])
        self.cb_fbclient.grid(row=4, column=1, pady=5, padx=5)
        ttk.Button(frame, text="📁", width=3, command=self._buscar_fbclient).grid(row=4, column=2, pady=5)

        # Botões
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=5, column=0, columnspan=3, pady=20)
        ttk.Button(btn_frame, text="Testar Conexão", command=self._testar_conexao).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="Salvar", command=self._salvar_config).pack(side=tk.LEFT, padx=10)

    def _carregar_dados(self):
        if self.config.has_section('FIREBIRD'):
            self.ent_servidor.insert(0, self.config.get('FIREBIRD', 'servidor', fallback='localhost'))
            self.ent_porta.insert(0, self.config.get('FIREBIRD', 'porta', fallback='3050'))
            self.ent_banco.insert(0, self.config.get('FIREBIRD', 'caminho_banco', fallback=''))
            self.ent_usuario.insert(0, self.config.get('FIREBIRD', 'usuario', fallback='SYSDBA'))
            self.ent_senha.insert(0, self.config.get('FIREBIRD', 'senha', fallback='masterkey'))
            self.cb_fbclient.set(self.config.get('FIREBIRD', 'fbclient', fallback=''))
        else:
            self.ent_servidor.insert(0, 'localhost')
            self.ent_porta.insert(0, '3050')

    def _buscar_banco(self):
        caminho = filedialog.askopenfilename(filetypes=[("Banco Firebird", "*.fdb"), ("Todos os arquivos", "*.*")])
        if caminho:
            self.ent_banco.delete(0, tk.END)
            self.ent_banco.insert(0, caminho)

    def _buscar_ini(self):
        caminho_ini = ""
        
        if os.path.exists(r"C:\UTILIT\SISTEC.INI"):
            caminho_ini = r"C:\UTILIT\SISTEC.INI"
        elif os.path.exists(r"C:\Sistec\launcher.ini"):
            caminho_ini = r"C:\Sistec\launcher.ini"
        
        if not caminho_ini:
            resposta = messagebox.askyesno("INI não encontrado", "Os arquivos SISTEC.INI ou launcher.ini não foram encontrados automaticamente.\nDeseja procurá-los manualmente?", parent=self)
            if resposta:
                caminho_ini = filedialog.askopenfilename(title="Selecione o INI", filetypes=[("Arquivo INI", "*.ini"), ("Todos os arquivos", "*.*")])
                
        if not caminho_ini:
            return
            
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
                            
                        self.ent_servidor.delete(0, tk.END)
                        self.ent_servidor.insert(0, servidor)
                        self.ent_porta.delete(0, tk.END)
                        self.ent_porta.insert(0, porta)
                        self.ent_banco.delete(0, tk.END)
                        self.ent_banco.insert(0, caminho_banco)
                        self.ent_usuario.delete(0, tk.END)
                        self.ent_usuario.insert(0, usuario)
                        self.ent_senha.delete(0, tk.END)
                        self.ent_senha.insert(0, senha)
                        
                        messagebox.showinfo("Sucesso", "Configurações importadas do launcher.ini", parent=self)
                        return
                messagebox.showwarning("Aviso", "Seção [Sistec] ou Database não encontrados no launcher.ini", parent=self)
                
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
                            self.ent_banco.delete(0, tk.END)
                            self.ent_banco.insert(0, db_path)
                            self.ent_servidor.delete(0, tk.END)
                            self.ent_servidor.insert(0, "localhost")
                            self.ent_porta.delete(0, tk.END)
                            self.ent_porta.insert(0, "3050")
                            messagebox.showinfo("Sucesso", f"Caminho importado automaticamente do SISTEC.INI:\n\n{db_path}", parent=self)
                            return
                messagebox.showwarning("Aviso", "Nenhum caminho de banco ativo ('database=...') foi encontrado no arquivo.", parent=self)
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao ler o arquivo INI:\n{e}", parent=self)

    def _buscar_fbclient(self):
        caminho = filedialog.askopenfilename(filetypes=[("DLL", "*.dll"), ("Todos os arquivos", "*.*")])
        if caminho:
            self.cb_fbclient.set(caminho)

    def _mostrar_erro_detalhado(self, titulo, mensagem):
        err_win = tk.Toplevel(self)
        err_win.title(titulo)
        err_win.geometry("500x300")
        err_win.transient(self)
        err_win.grab_set()
        
        ttk.Label(err_win, text="Ocorreu um erro (Você pode copiar o texto abaixo):").pack(pady=5, anchor=tk.W, padx=10)
        txt = tk.Text(err_win, wrap=tk.WORD)
        txt.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        txt.insert(tk.END, mensagem)
        txt.configure(state=tk.DISABLED) # Deixa como leitura, mas permite selecionar e copiar
        ttk.Button(err_win, text="Fechar", command=err_win.destroy).pack(pady=10)

    def _testar_conexao(self):
        servidor = self.ent_servidor.get().strip()
        porta = self.ent_porta.get().strip()
        caminho_banco = self.ent_banco.get()
        usuario = self.ent_usuario.get()
        senha = self.ent_senha.get()
        fbclient = self.cb_fbclient.get().strip()

        if not caminho_banco:
            messagebox.showwarning("Aviso", "O caminho do banco de dados é obrigatório.", parent=self)
            return

        dsn = caminho_banco
        if servidor:
            if porta:
                dsn = f"{servidor}/{porta}:{caminho_banco}"
            else:
                dsn = f"{servidor}:{caminho_banco}"

        kwargs = {
            'dsn': dsn,
            'user': usuario,
            'password': senha,
            'charset': 'WIN1252'
        }
        if fbclient:
            kwargs['fb_library_name'] = self.resource_path(fbclient)

        try:
            conn = fdb.connect(**kwargs)
            conn.close()
            messagebox.showinfo("Sucesso", "Conexão OK!", parent=self)
            self._salvar_config_temp()
            if self.callback_status:
                self.callback_status()
            self.destroy()
        except Exception as e:
            msg_erro = str(e)
            if "usado por outro processo" in msg_erro or "used by another process" in msg_erro:
                dica = (
                    "\n\n💡 DICA DE RESOLUÇÃO:\n"
                    "O banco de dados já está sendo executado pelo servidor Firebird ou pelo sistema NEXUS.\n"
                    "Verifique se o Servidor está configurado como 'localhost'."
                )
                msg_erro += dica
            elif "unsupported on-disk structure" in msg_erro or "SQLCODE: -820" in msg_erro:
                dica = (
                    "\n\n💡 DICA DE RESOLUÇÃO (VERSÃO INCOMPATÍVEL):\n"
                    "Este erro significa que o arquivo do banco de dados é mais novo do que o Firebird instalado.\n"
                    "Tente alterar a versão do fbclient.dll na caixa de seleção para uma versão mais recente (ex: fbclient_5.dll)."
                )
                msg_erro += dica
            elif "unavailable database" in msg_erro or "SQLCODE: -904" in msg_erro:
                dica = (
                    "\n\n💡 DICA DE RESOLUÇÃO (BANCO INDISPONÍVEL):\n"
                    "1. O arquivo (.fdb) não foi encontrado no caminho especificado.\n"
                    "2. UNIDADE DE REDE (Ex: Z:\\...): O Firebird não enxerga mapeamentos de rede. Se o banco está em outro PC, coloque o IP desse PC no campo 'Servidor' e o caminho físico real de lá (Ex: C:\\Sistec\\banco.fdb).\n"
                    "3. CONEXÃO LOCAL: Se você não possui o servidor Firebird rodando, deixe os campos 'Servidor' e 'Porta' totalmente vazios."
                )
                msg_erro += dica
            self._mostrar_erro_detalhado("Erro de Conexão", f"Falha ao conectar:\n{msg_erro}")

    def _salvar_config_temp(self):
        config = configparser.ConfigParser()
        config.read('config.ini', encoding='utf-8')

        if not config.has_section('FIREBIRD'):
            config.add_section('FIREBIRD')
        config.set('FIREBIRD', 'servidor', self.ent_servidor.get().strip())
        config.set('FIREBIRD', 'porta', self.ent_porta.get().strip())
        config.set('FIREBIRD', 'caminho_banco', self.ent_banco.get())
        config.set('FIREBIRD', 'usuario', self.ent_usuario.get())
        config.set('FIREBIRD', 'senha', self.ent_senha.get())
        config.set('FIREBIRD', 'fbclient', self.cb_fbclient.get().strip())
        with open('config.ini', 'w', encoding='utf-8') as f:
            config.write(f)

    def _salvar_config(self):
        self._salvar_config_temp()
        messagebox.showinfo("Sucesso", "Configurações salvas com sucesso!", parent=self)
        if self.callback_status:
            self.callback_status()
        self.destroy()

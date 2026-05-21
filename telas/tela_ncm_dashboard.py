import tkinter as tk
from tkinter import ttk, messagebox

class TelaDashboardNCM(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        
        # Dados simulados (Mock) para demonstrar os 3 status
        self.dados_ncm = [
            # VERMELHO (Pendentes - Não existem no sistema)
            {"ncm": "1905.90.90", "descricao": "OUTROS PAES E BOLOS", "status": "PENDENTE", "motivo": "NCM Novo (Detectado em XML de Entrada)"},
            {"ncm": "2106.90.90", "descricao": "PREPARACOES ALIMENTICIAS", "status": "PENDENTE", "motivo": "NCM Novo (Detectado em XML de Entrada)"},
            {"ncm": "2202.10.00", "descricao": "AGUAS ADICIONADAS ACUCAR", "status": "PENDENTE", "motivo": "NCM Novo (Detectado em XML de Entrada)"},
            
            # AMARELO (Atenção - Faltam regras)
            {"ncm": "0201.20.20", "descricao": "QUARTOS TRASEIROS BOVINO", "status": "ATENCAO", "motivo": "Falta Alíquota de Saída (ICMS)"},
            {"ncm": "0808.10.00", "descricao": "MACAS FRESCAS", "status": "ATENCAO", "motivo": "Falta PIS/COFINS"},
            
            # VERDE (OK - Validados)
            {"ncm": "0804.40.00", "descricao": "ABACATES FRESCOS", "status": "OK", "motivo": "Tributação Completa"},
            {"ncm": "0401.20.10", "descricao": "LEITE UHT", "status": "OK", "motivo": "Tributação Completa"},
            {"ncm": "0712.90.90", "descricao": "VEGETAIS SECOS", "status": "OK", "motivo": "Tributação Completa"},
        ]
        
        self.configurar_interface()
        self.atualizar_contadores()
        self.filtrar_lista("PENDENTE") # Inicia mostrando as urgências

    def configurar_interface(self):
        # --- CABEÇALHO ---
        frame_header = tk.Frame(self, bg="white", pady=15, padx=20)
        frame_header.pack(fill=tk.X)
        
        tk.Label(frame_header, text="Dashboard de Saúde Tributária - NCMs", 
                 font=("Segoe UI", 18, "bold"), bg="white", fg="#1a1a1a").pack(anchor=tk.W)
        tk.Label(frame_header, text="Veja rapidamente os produtos que precisam da sua atenção para não travar o faturamento.", 
                 font=("Segoe UI", 10), bg="white", fg="#555555").pack(anchor=tk.W)

        # --- PAINEL DE SEMÁFORO (CARDS) ---
        frame_cards = tk.Frame(self, pady=20, padx=20)
        frame_cards.pack(fill=tk.X)
        
        # Criar os 3 cartões
        self.card_vermelho = self._criar_card(
            frame_cards, "🔴 PENDENTE DE CADASTRO", "0", 
            "#FFF1F0", "#CF1322", "#F5222D", 
            lambda e: self.filtrar_lista("PENDENTE")
        )
        self.card_vermelho.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        self.card_amarelo = self._criar_card(
            frame_cards, "🟡 ATENÇÃO (INCOMPLETO)", "0", 
            "#FFFBE6", "#D48806", "#FAAD14", 
            lambda e: self.filtrar_lista("ATENCAO")
        )
        self.card_amarelo.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)
        
        self.card_verde = self._criar_card(
            frame_cards, "🟢 TUDO CERTO", "0", 
            "#F6FFED", "#389E0D", "#52C41A", 
            lambda e: self.filtrar_lista("OK")
        )
        self.card_verde.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))

        # --- LISTA FILTRADA E AÇÕES ---
        frame_lista = tk.LabelFrame(self, text=" Detalhes dos NCMs Selecionados ", font=("Segoe UI", 10, "bold"), padx=10, pady=10)
        frame_lista.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))
        
        # Tabela (Treeview)
        colunas = ("ncm", "descricao", "motivo")
        self.tree = ttk.Treeview(frame_lista, columns=colunas, show="headings", height=8)
        self.tree.heading("ncm", text="Código NCM")
        self.tree.column("ncm", width=100, anchor=tk.CENTER)
        
        self.tree.heading("descricao", text="Descrição do Produto")
        self.tree.column("descricao", width=300)
        
        self.tree.heading("motivo", text="Motivo / Pendência")
        self.tree.column("motivo", width=250)
        
        scroll_y = ttk.Scrollbar(frame_lista, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll_y.set)
        
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Botões de Ação Dinâmicos
        self.frame_acoes = tk.Frame(frame_lista, pady=10)
        self.frame_acoes.pack(fill=tk.X)
        
        self.btn_acao_principal = ttk.Button(self.frame_acoes, text="Ação", command=self.executar_acao)
        self.btn_acao_principal.pack(side=tk.RIGHT)

    def _criar_card(self, parent, titulo, valor_inicial, bg_color, border_color, text_color, command):
        """Cria um cartão clicável (Dashboard Card)"""
        card = tk.Frame(parent, bg=bg_color, highlightbackground=border_color, highlightthickness=2, padx=15, pady=15, cursor="hand2")
        
        lbl_titulo = tk.Label(card, text=titulo, font=("Segoe UI", 10, "bold"), bg=bg_color, fg=text_color, cursor="hand2")
        lbl_titulo.pack(anchor=tk.W)
        
        lbl_valor = tk.Label(card, text=valor_inicial, font=("Segoe UI", 26, "bold"), bg=bg_color, fg=text_color, cursor="hand2")
        lbl_valor.pack(anchor=tk.W, pady=(5, 0))
        
        # Guardar referência do label de valor para atualizar depois
        card.lbl_valor = lbl_valor 
        
        # Bind de clique em tudo dentro do card
        for widget in (card, lbl_titulo, lbl_valor):
            widget.bind("<Button-1>", command)
            
        return card

    def atualizar_contadores(self):
        """Conta quantos NCMs existem em cada status e atualiza os números nos cartões"""
        pendentes = sum(1 for item in self.dados_ncm if item["status"] == "PENDENTE")
        atencao = sum(1 for item in self.dados_ncm if item["status"] == "ATENCAO")
        ok = sum(1 for item in self.dados_ncm if item["status"] == "OK")
        
        self.card_vermelho.lbl_valor.config(text=str(pendentes))
        self.card_amarelo.lbl_valor.config(text=str(atencao))
        self.card_verde.lbl_valor.config(text=str(ok))

    def filtrar_lista(self, status_selecionado):
        """Atualiza a tabela baseada no cartão clicado"""
        # Efeito visual simples de borda
        self.card_vermelho.config(highlightthickness=3 if status_selecionado == "PENDENTE" else 1)
        self.card_amarelo.config(highlightthickness=3 if status_selecionado == "ATENCAO" else 1)
        self.card_verde.config(highlightthickness=3 if status_selecionado == "OK" else 1)
        
        # Limpar tabela
        for row in self.tree.get_children():
            self.tree.delete(row)
            
        # Popular tabela
        for item in self.dados_ncm:
            if item["status"] == status_selecionado:
                self.tree.insert("", tk.END, values=(item["ncm"], item["descricao"], item["motivo"]))
                
        # Alterar o botão de ação dependendo do contexto
        self.status_atual = status_selecionado
        if status_selecionado == "PENDENTE":
            self.btn_acao_principal.config(text="✨ Iniciar Assistente (Wizard) para Cadastrar Selecionados", state=tk.NORMAL)
        elif status_selecionado == "ATENCAO":
            self.btn_acao_principal.config(text="✏️ Completar Impostos (Edição em Lote)", state=tk.NORMAL)
        else:
            self.btn_acao_principal.config(text="Nenhuma ação pendente", state=tk.DISABLED)

    def executar_acao(self):
        """Dispara a ação do botão baseado no status ativo"""
        selecao = self.tree.selection()
        if not selecao and self.status_atual != "OK":
            messagebox.showinfo("Aviso", "Por favor, selecione ao menos um NCM na lista para continuar.")
            return
            
        if self.status_atual == "PENDENTE":
            # Aqui chamaríamos a tela de Wizard em uma janela modal (Toplevel)
            messagebox.showinfo("Wizard", "Aqui abriremos uma janela 'Passo a Passo' simples, perguntando se o produto é isento, tributado, etc, para o NCM selecionado.")
        elif self.status_atual == "ATENCAO":
            # Aqui chamaríamos uma tela de edição rápida
            messagebox.showinfo("Edição", "Aqui abriremos uma janela para você preencher apenas o ICMS ou o PIS/COFINS que faltaram.")


# Código para rodar a tela de forma isolada (Standalone) e testar
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Sistec - Módulo de Tributação (Dashboard)")
    root.geometry("900x600")
    root.configure(bg="#F0F2F5")
    
    # Configurando o tema base (Clam é melhor para personalizar cores no Windows)
    style = ttk.Style()
    if "clam" in style.theme_names():
        style.theme_use("clam")
        
    style.configure("Treeview.Heading", font=('Segoe UI', 10, 'bold'))
    style.configure("Treeview", font=('Segoe UI', 10), rowheight=25)
    style.map("Treeview", background=[('selected', '#CCE8FF')], foreground=[('selected', 'black')])
    
    app = TelaDashboardNCM(root)
    app.pack(fill=tk.BOTH, expand=True)
    root.mainloop()
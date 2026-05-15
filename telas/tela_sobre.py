import tkinter as tk
from tkinter import ttk
import os
import sys
import webbrowser
from PIL import Image, ImageTk
from version import VERSAO, DATA_VERSAO

class TelaSobre(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Sobre o Sistema - Central de Implantação Sistec")
        self.geometry("800x600")
        self.minsize(800, 500)
        self.transient(parent) # Mantém a janela sempre à frente da principal
        self.grab_set()        # Desabilita cliques na janela de trás até fechar esta
        
        self._criar_widgets()

    def resource_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def _criar_widgets(self):
        # Cabeçalho
        frame_header = tk.Frame(self, bg="#FFFFFF", pady=15)
        frame_header.pack(fill=tk.X)
        
        logo_path = self.resource_path("sistec.jpg")
        if os.path.exists(logo_path):
            try:
                img = Image.open(logo_path)
                img.thumbnail((250, 100)) # Redimensiona a logo mantendo a proporção
                self.logo_img = ImageTk.PhotoImage(img)
                lbl_logo = tk.Label(frame_header, image=self.logo_img, bg="#FFFFFF")
                lbl_logo.pack(pady=(0, 10))
            except Exception as e:
                print("Erro ao carregar logo na tela sobre:", e)

        lbl_titulo = tk.Label(frame_header, text="CENTRAL DE IMPLANTAÇÃO E AUDITORIA - SISTEC", font=("Segoe UI", 16, "bold"), bg="#FFFFFF", fg="#003399")
        lbl_titulo.pack()

        lbl_versao = tk.Label(frame_header, text=f"Versão {VERSAO} (Lançamento: {DATA_VERSAO})", font=("Segoe UI", 11), bg="#FFFFFF", fg="#555555")
        lbl_versao.pack()

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X)

        # Área de Texto com Rolagem
        frame_content = tk.Frame(self)
        frame_content.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        scroll_y = ttk.Scrollbar(frame_content)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        texto = tk.Text(frame_content, wrap=tk.WORD, yscrollcommand=scroll_y.set, font=("Segoe UI", 10), bg="#F8F9F9", padx=15, pady=15, spacing3=5)
        texto.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.config(command=texto.yview)

        conteudo = """Este sistema foi projetado para atuar como um "Canivete Suíço" nas mãos de implantadores e auditores, acelerando tarefas manuais, prevenindo erros humanos e garantindo a integridade do banco de dados (Firebird) do ERP Sistec.

=== MÓDULOS E ROTINAS DISPONÍVEIS ===

1. Importação de Plano de Contas via Excel
Ferramenta vital para iniciar a contabilidade de novas empresas no ERP.
- Rotina: O usuário seleciona a planilha e aponta as colunas. O sistema varre as linhas aplicando Regras de Negócio estruturais (valida as contas sintéticas/analíticas e o tamanho do código).
- Validação e Injeção: Compara a planilha com o banco atual, sinaliza duplicidades e bloqueia erros. Oferece opção de "Zerar o Plano Atual" antes de realizar múltiplos "INSERTs" no Firebird, garantindo um plano limpo.

2. Geração de Lista de Preços de Venda via NFe (XML)
Resolve o pesadelo de atualizar preços de centenas de produtos recém-comprados.
- Rotina: Lê em lote arquivos XML de entrada, processando o último valor unitário (vUnCom) pago e extraindo o código (cProd).
- Cruzamento (Match): O sistema acessa a TABELA_PRODUTO procurando o "cProd" como Código Auxiliar. Ao encontrar correspondência, o item se torna VINCULADO com seu respectivo ID interno (Cód. ERP).
- Ação: Permite a revisão rápida do preço sugerido pelo XML na tela e dispara uma instrução "UPDATE OR INSERT" no banco, injetando o novo valor numa "TABELA_LISTA_PRECOS" (já existente ou nova).

3. Auditoria de Tributação NCM (XML vs Sistema)
Módulo cirúrgico para evitar passivos fiscais e multas na revenda.
- Rotina: Captura as alíquotas exatas de NCM, ICMS, PIS e COFINS do arquivo XML da fábrica (entrada) e compara diretamente com a TABELA_class_fiscal interna.
- Auditoria Visual: Itens em conformidade ficam limpos. NCMs não cadastrados surgem verdes. Divergências de alíquota acendem alerta laranja.
- Ação Integrada: Permite clicar num item divergente e "Copiar Impostos do XML", forçando uma atualização automática das alíquotas (UPDATE ou INSERT) no Firebird para a próxima venda.

=== PRÓXIMAS IMPLEMENTAÇÕES (ROADMAP) ===

• Parametrização Automatizada de CFOP e ICMS: Ajuste em massa das matrizes e exceções de impostos de entrada e saída.
• Adequação Reforma Tributária: Robôs de injeção focados em substituir ICMS/PIS/COFINS por CBS (Contribuição sobre Bens e Serviços) e IBS (Imposto sobre Bens e Serviços) nas tabelas do sistema em lote.

--------------------------------------------------
SISTEC - Soluções em Informática
Acesse: """
        texto.insert(tk.END, conteudo)
        
        texto.insert(tk.END, "www.sistecweb.com.br", "link")
        texto.tag_config("link", foreground="#003399", underline=True)
        texto.tag_bind("link", "<Enter>", lambda e: texto.config(cursor="hand2"))
        texto.tag_bind("link", "<Leave>", lambda e: texto.config(cursor=""))
        texto.tag_bind("link", "<Button-1>", lambda e: webbrowser.open("http://www.sistecweb.com.br"))
        
        texto.config(state=tk.DISABLED) # Bloqueia a edição, tornando modo leitura

        # Rodapé com botão Fechar
        frame_footer = tk.Frame(self, pady=10)
        frame_footer.pack(side=tk.BOTTOM, fill=tk.X)
        
        btn_fechar = ttk.Button(frame_footer, text="Fechar Janela", command=self.destroy)
        btn_fechar.pack()
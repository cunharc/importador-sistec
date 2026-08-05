import tkinter as tk
from tkinter import ttk
import os
import sys
import webbrowser
from PIL import Image, ImageTk
from version import VERSAO, DATA_VERSAO
from utils import tema


class TelaSobre(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Sobre o Sistema - Central de Implantação Sistec")
        self.configure(bg=tema.BG_BASE)
        self.minsize(760, 560)
        self.transient(parent)   # Mantém a janela sempre à frente da principal

        self._criar_widgets()
        tema.centralizar(self, 940, 720)
        self.grab_set()          # Desabilita cliques na janela de trás até fechar esta

    def resource_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def _criar_widgets(self):
        # ===================== CABEÇALHO (branco com logo) =====================
        frame_header = tk.Frame(self, bg="#FFFFFF", pady=14)
        frame_header.pack(fill=tk.X)

        logo_path = self.resource_path("sistec.jpg")
        if os.path.exists(logo_path):
            try:
                img = Image.open(logo_path)
                img.thumbnail((230, 90))
                self.logo_img = ImageTk.PhotoImage(img)
                tk.Label(frame_header, image=self.logo_img, bg="#FFFFFF").pack(pady=(0, 8))
            except Exception as e:
                print("Erro ao carregar logo na tela sobre:", e)

        tk.Label(frame_header, text="CENTRAL DE IMPLANTAÇÃO E AUDITORIA — SISTEC",
                 font=(tema.FONTE, 16, "bold"), bg="#FFFFFF", fg=tema.SISTEC_BLUE).pack()
        tk.Label(frame_header, text=f"Versão {VERSAO}  •  Lançamento {DATA_VERSAO}",
                 font=(tema.FONTE, 10), bg="#FFFFFF", fg=tema.TEXT_SECOND).pack(pady=(2, 0))

        tk.Frame(self, bg=tema.SISTEC_ORANGE, height=3).pack(fill=tk.X)

        # ===================== ÁREA DE TEXTO COM ROLAGEM =====================
        frame_content = tk.Frame(self, bg=tema.BG_BASE)
        frame_content.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        scroll_y = ttk.Scrollbar(frame_content)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        texto = tk.Text(frame_content, wrap=tk.WORD, yscrollcommand=scroll_y.set,
                        font=(tema.FONTE, 10), bg="#FFFFFF", fg=tema.TEXT,
                        relief=tk.FLAT, padx=22, pady=18, spacing1=2, spacing3=6,
                        highlightthickness=1, highlightbackground=tema.BORDER)
        texto.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.config(command=texto.yview)

        # ---- Tags de formatação ----
        texto.tag_config("intro", font=(tema.FONTE, 11), foreground=tema.TEXT_SECOND, spacing3=10)
        texto.tag_config("secao", font=(tema.FONTE, 13, "bold"), foreground=tema.SISTEC_BLUE,
                         spacing1=16, spacing3=8)
        texto.tag_config("modulo", font=(tema.FONTE, 11, "bold"), foreground=tema.SISTEC_BLUE_DARK,
                         spacing1=10, spacing3=3)
        texto.tag_config("rotulo", font=(tema.FONTE, 9, "bold"), foreground=tema.SISTEC_RED)
        texto.tag_config("corpo", font=(tema.FONTE, 10), foreground=tema.TEXT, spacing3=6)
        texto.tag_config("dica", font=(tema.FONTE, 9, "italic"), foreground=tema.TEXT_SECOND, spacing3=8)
        texto.tag_config("link", foreground=tema.SISTEC_BLUE, underline=True)

        self._montar_conteudo(texto)

        texto.config(state=tk.DISABLED)

        # ===================== RODAPÉ =====================
        frame_footer = tk.Frame(self, bg=tema.BG_BASE, pady=10)
        frame_footer.pack(side=tk.BOTTOM, fill=tk.X)
        tema.estilo_botao(frame_footer, "✔ Fechar", self.destroy, "primary").pack()

    # ------------------------------------------------------------------
    def _montar_conteudo(self, t):
        def linha(txt, tag):
            t.insert(tk.END, txt + "\n", tag)

        def modulo(titulo, categoria, faz, como):
            t.insert(tk.END, titulo + "   ", "modulo")
            t.insert(tk.END, f"[{categoria}]\n", "rotulo")
            t.insert(tk.END, "O que faz: ", "rotulo")
            t.insert(tk.END, faz + "\n", "corpo")
            t.insert(tk.END, "Como usar: ", "rotulo")
            t.insert(tk.END, como + "\n", "corpo")

        linha("Esta central é o \"canivete suíço\" do implantador e do auditor Sistec: acelera "
              "tarefas manuais, previne erro humano e garante a integridade do banco Firebird do ERP. "
              "Cada módulo é uma rotina independente — você abre, executa e volta ao menu principal. "
              "Abaixo, o que cada um faz e como operá-lo.", "intro")

        # ---- Como navegar ----
        linha("COMO NAVEGAR", "secao")
        linha("• No menu principal, os módulos aparecem como cartões. Use os filtros da lateral "
              "(Todos / Excel / XML / Outros) ou a busca no topo para localizar.", "corpo")
        linha("• Dentro de cada módulo há um menu lateral azul com as AÇÕES da tela e o botão Voltar.", "corpo")
        linha("• No topo fica o status do banco e o seletor de Empresa/Filial. Tecle F5 para "
              "reconectar/atualizar e ESC para voltar ao menu.", "corpo")
        linha("• Antes de qualquer rotina, confirme em \"Configurar Banco\" que está conectado ao "
              "banco certo e selecione a Empresa/Filial correta no topo.", "dica")

        # ---- Importação por Excel ----
        linha("IMPORTAÇÃO VIA PLANILHA (EXCEL / CSV)", "secao")

        modulo("Plano de Contas", "Excel",
               "Cria a estrutura contábil de uma empresa nova a partir de uma planilha de contas.",
               "Informe Empresa/Filial/Exercício, aponte as colunas Conta e Descrição e a linha "
               "inicial. Clique em Abrir Planilha: o sistema valida níveis sintético/analítico, "
               "sinaliza duplicidades e erros por cor. Confira no Preview e clique em Importar. "
               "Opção de zerar o plano atual antes de gravar.")

        modulo("Importar Produtos", "Excel",
               "Cadastra produtos em massa e cria automaticamente grupos e subgrupos que não existirem.",
               "Carregue a planilha, mapeie as colunas (código, descrição, NCM, preço, etc.) e "
               "analise. As linhas ficam coloridas por status (Novo/OK/Divergente/Erro). Ajuste o "
               "que precisar e clique em Processar para injetar no ERP.")

        modulo("Importar Clientes", "Excel",
               "Importa clientes e fornecedores em lote via planilha, com mapeamento de colunas.",
               "Selecione o arquivo, faça o de-para das colunas para os campos do cadastro, "
               "classifique (Cliente/Fornecedor/Outros) e processe. Erros de CNPJ/CPF ou campos "
               "obrigatórios são sinalizados antes da gravação.")

        modulo("Importar Contas a Receber", "Excel",
               "Lança títulos e parcelas de contas a receber a partir de uma planilha.",
               "Mapeie as colunas (documento, cliente, vencimento, valor, parcelas). O sistema "
               "recalcula/valida os títulos; revise a grade e processe para gravar no financeiro.")

        modulo("Importar Contas a Pagar", "Excel",
               "Lança títulos e parcelas de contas a pagar a partir de uma planilha.",
               "Mesma lógica do Contas a Receber: mapeie colunas, valide os títulos na grade e "
               "processe. Ideal para carregar o passivo inicial na implantação.")

        modulo("Importar Lista de Preços", "Excel",
               "Sobe uma tabela de preços via planilha, validando cada item contra o cadastro do ERP.",
               "Mapeie código e preço, analise (o sistema confere se o produto existe) e injete. "
               "Itens sem correspondência são destacados para correção.")

        modulo("Importar Tributação", "Excel",
               "Importa a tributação completa por NCM: ICMS, PIS, COFINS e Reforma Tributária.",
               "Aponte as colunas de NCM e alíquotas; a rotina cria faixas e regras necessárias e "
               "grava a matriz tributária. Confira o resultado na grade antes de processar.")

        # ---- Auditoria por XML ----
        linha("AUDITORIA E CADASTRO VIA XML (NF-e)", "secao")

        modulo("Clientes/Fornecedores NF-e", "XML",
               "Cadastra clientes e fornecedores lendo automaticamente os XMLs de NF-e 4.00.",
               "Aponte a pasta (ou selecione arquivos) de XMLs, leia os documentos, marque quem "
               "deseja cadastrar e importe. Também concilia condições de pagamento novas x existentes.")

        modulo("Produtos & Consolidado", "XML",
               "Auditoria final por produto cruzando NCM, CFOP e ICMS para cadastrar/corrigir itens.",
               "Carregue os XMLs, analise a consolidação por produto e processe o cadastro/correção "
               "dos itens direto no ERP.")

        modulo("Faixas de ICMS", "XML",
               "Constrói e audita as regras de ICMS por estado a partir do histórico de XMLs.",
               "Leia os XMLs, analise as faixas sugeridas, compare com o que já existe no ERP e "
               "envie as selecionadas. Use \"Ver Faixas no ERP\" para conferir o cadastro atual.")

        modulo("Tributação por NCM", "XML",
               "Gerencia regras tributárias e alíquotas por NCM, comparando XML x sistema.",
               "Analise os XMLs: NCMs não cadastrados aparecem em verde, divergências de alíquota "
               "em laranja. Selecione e sincronize para gravar as alíquotas corretas no Firebird.")

        modulo("Tributação CFOP", "XML",
               "Define naturezas de operação e regras contábeis por CFOP.",
               "Carregue os XMLs, edite/defina as regras por CFOP, salve os ajustes ou exporte em "
               "CSV. Permite criar, editar e desativar CFOPs.")

        modulo("Reforma Tributária (RT)", "XML",
               "Constrói e audita as regras de IBS e CBS a partir dos XMLs (nova tributação).",
               "Analise os XMLs, revise as regras de IBS/CBS sugeridas e envie as selecionadas ao "
               "ERP. Prepara a base para a transição da Reforma Tributária.")

        modulo("Lista de Preços XML", "XML",
               "Cria/atualiza listas de preço capturando o último valor unitário pago nos XMLs.",
               "Leia os XMLs (o sistema pega o vUnCom e casa o cProd com o código auxiliar do "
               "produto). Revise o preço sugerido e injete na lista de preços (nova ou existente).")

        modulo("Visão Gerencial (Completa)", "XML",
               "Auditoria completa agrupando Produto, NCM, CFOP, ICMS, PIS/COFINS e RT com exportação.",
               "Carregue os XMLs e navegue pela visão consolidada; filtre por NCM/CFOP/UF/CST e "
               "exporte a visão atual em CSV para análise.")

        modulo("Auditoria por Produto", "XML",
               "Mostra todas as variações de tributação que um mesmo produto sofreu nos XMLs.",
               "Carregue os XMLs e selecione um produto para ver o histórico de alíquotas e "
               "divergências entre notas — ótimo para achar cadastros inconsistentes.")

        # ---- Outros / Firebird ----
        linha("FERRAMENTAS (ACESSO DIRETO AO BANCO)", "secao")

        modulo("Duplicar / Configurar Empresa", "Outros",
               "Clona uma empresa/filial (EMPRESA, PARÂMETROS, FILIAL e CONFIG NF-e) e permite "
               "ajustar cada configuração campo a campo antes de gravar.",
               "Informe a empresa/filial de origem e o código de destino e clique em Duplicar. "
               "Depois use as abas (uma por tabela) para editar os campos como numa planilha "
               "(Enter ou duplo-clique na célula) e salve — a aba atual ou todas de uma vez.")

        modulo("Vínculo CC × Plano de Contas", "Outros",
               "Vincula os centros de custo às contas do plano (contabilização automática): "
               "CC_CONTABIL = código do plano e CC_CONTABIL_REDUZIDO = reduzido.",
               "Carregue Empresa/Filial/Exercício. A árvore de centros de custo aparece com a "
               "situação de cada analítico (vinculado/sem vínculo/divergente). Dê duplo-clique ou "
               "Enter num analítico, busque a conta do plano por termo e escolha. As alterações "
               "ficam destacadas e vão ao banco de uma vez em Salvar TODAS. Filtre por 'sem vínculo' "
               "ou 'divergentes' para ir direto ao que falta.")

        modulo("Busca em Logs ERP", "Outros",
               "Varredura rápida em arquivos .txt de log gerados pelo ERP, sem travar a máquina.",
               "Aponte a pasta de logs e digite o termo. A ferramenta abre, lê e fecha cada arquivo "
               "(baixo consumo de memória), lista as ocorrências em ordem cronológica para copiar/colar "
               "e, no duplo-clique, abre só o arquivo pedido. Filtre por módulo e ordene por coluna.")

        # ---- Manutenção ----
        linha("MANUTENÇÃO E APOIO", "secao")
        linha("• Configurar Banco: define servidor, porta, caminho do .fdb, usuário/senha e a versão "
              "do fbclient.dll. Tem \"Ler INI\" para importar do SISTEC.INI/launcher.ini e \"Testar Conexão\".", "corpo")
        linha("• Ver logs de hoje: abre o registro de acessos aos módulos do dia.", "corpo")
        linha("• Atualizar sistema: verifica e baixa novas versões automaticamente.", "corpo")
        linha("• Sobre o sistema: este manual.", "corpo")

        # ---- Rodapé de contato ----
        linha("", "corpo")
        t.insert(tk.END, "─" * 60 + "\n", "dica")
        t.insert(tk.END, "SISTEC — Soluções em Informática\n", "modulo")
        t.insert(tk.END, "Acesse: ", "corpo")
        t.insert(tk.END, "www.sistecweb.com.br", "link")

        t.tag_bind("link", "<Enter>", lambda e: t.config(cursor="hand2"))
        t.tag_bind("link", "<Leave>", lambda e: t.config(cursor=""))
        t.tag_bind("link", "<Button-1>", lambda e: webbrowser.open("http://www.sistecweb.com.br"))

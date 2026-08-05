import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import configparser
import threading
import os
import re
from utils.firebird_service import FirebirdService
from utils.xml_reader import parse_nfe_folder, parse_nfe
from utils.validator import ValidatorFiscal
from utils.report_generator import generate_audit_report
from utils.transformer import DataTransformer
from utils.importer import FirebirdImporter
from utils import tema

# Limite do INTEGER do Firebird (PRODUTO_CODIGO é LONG, 4 bytes).
COD_MAX = 2147483647

# O sistema antigo do cliente emite o cProd com DOIS códigos separados por vírgula
# ("68, 918") quando o mesmo produto tem dois cadastros lá. Gravar o texto inteiro
# deixa o produto invisível na importação das notas, porque a nota referencia só
# "68" ou só "918". Cada parte então vira um cadastro próprio e, terminadas as
# importações, inativa-se o que não foi usado.
# Só vírgula e ponto-e-vírgula: '/' e '+' aparecem DENTRO de códigos legítimos
# ('mandril1/2', 'CABO HDMI+HDMI20M') e não podem quebrar o código em dois.
_SEP_CODIGO = re.compile(r'[,;]')


def separar_codigos(c_prod):
    """Lista de códigos contidos num cProd — um só, na esmagadora maioria."""
    s = str(c_prod if c_prod is not None else '').strip()
    if not s:
        return []
    # partes já vem sem os vazios, então 'A,B' -> ['A','B'], 'A' -> ['A'],
    # 'A,' -> ['A'] e ' , ' -> [] (não devolve a vírgula como se fosse código).
    return [p.strip() for p in _SEP_CODIGO.split(s) if p.strip()]


def codigo_erp_numerico(cod_xml, existentes, modo='xml'):
    """Escolhe o PRODUTO_CODIGO, que é INTEGER no banco.

    Um cProd alfanumérico ('MCC101') ou composto ('68, 918') gravado direto ali dá
    `-303 conversion error from string` e, como o import_produtos levanta no primeiro
    erro, derruba o lote inteiro. Aqui o código do XML só é aproveitado quando é
    numérico, cabe no INTEGER e está livre; senão entra o menor número livre.

    O código do XML nunca se perde: vai para PRODUTO_COD_AUXILIAR e
    PRODUTO_COD_IMPORTACAO (VARCHAR(100)), que é por onde a importação de notas
    reencontra o produto.

    Devolve (codigo_erp, cod_xml).
    """
    limpos = {str(c).strip().lstrip('0') or '0' for c in existentes}
    numericos = sorted(int(c) for c in limpos if c.isdigit() and int(c) <= COD_MAX)
    bruto = str(cod_xml if cod_xml is not None else '').strip()

    if modo == 'sequencial':
        return str((numericos[-1] + 1) if numericos else 1), bruto

    candidato = bruto.lstrip('0')
    if candidato.isdigit() and int(candidato) <= COD_MAX and candidato not in limpos:
        return candidato, bruto

    # menor lacuna livre (mesmo critério de antes, agora sempre numérica)
    menor = 1
    for c in numericos:
        if c == menor:
            menor += 1
        elif c > menor:
            break
    return str(menor), bruto


# A barra que quebra em varias linhas vive em utils/tema.py desde que a tela de
# NCM passou a precisar dela. O alias mantem o nome usado neste arquivo.
BarraFluida = tema.BarraFluida


_rotulo = tema.rotulo_campo


class ModalPreviewProdutos(tk.Toplevel):
    def __init__(self, parent, itens, config, config_db, classificacao, grupos_db, subgrupos_db, callback_importar, modo_codigo='xml'):
        super().__init__(parent)
        self.title("Preview de Cadastro de Produtos")
        w = min(1100, int(self.winfo_screenwidth() * 0.92))
        h = min(700, int(self.winfo_screenheight() * 0.85))
        self.geometry(f"{w}x{h}")
        # minsize baixo de propósito: em 1024x768 com a barra do Windows, um piso de
        # 640x480 já obrigava a janela a nascer maior que a área útil.
        self.minsize(560, 400)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        
        self.itens = itens
        self.config = config
        self.config_db = config_db
        self.classificacao = classificacao
        self.grupos_db = grupos_db
        self.subgrupos_db = subgrupos_db
        self.callback_importar = callback_importar
        self.modo_codigo = modo_codigo
        self.produtos_para_inserir = []
        
        self._criar_widgets()
        self._preparar_dados()
        tema.centralizar(self, w, h)

    def _preparar_dados(self):
        emp = int(self.config.get('IMPORTACAO', 'empresa', fallback='1'))
        fil = int(self.config.get('IMPORTACAO', 'filial', fallback='1'))
        
        def task():
            try:
                with FirebirdService(self.config_db) as fb:
                    sql_codigos = "SELECT PRODUTO_CODIGO FROM TABELA_PRODUTO WHERE PRODUTO_EMPRESA = ? AND PRODUTO_FILIAL = ?"
                    existentes = fb.query(sql_codigos, [emp, fil])
                    existentes_codigos = set(str(p.get('produto_codigo', '')) for p in existentes)
                    
                    config_prod = {'empresa': emp, 'filial': fil}
                    
                    for r in self.itens:
                        item = r['xml']
                        acao = r.get('acao_escolhida', 'CADASTRAR NOVO')
                        erp_match = r['validacao'].erp_match or {}
                        
                        novo_dict = DataTransformer.prepare_produto(item, config_prod, self.classificacao)
                        cod_xml = str(item.get('c_prod') or '').strip()
                        novo_dict['_COD_XML'] = cod_xml
                        novo_dict['_COD_XML_ORIGINAL'] = str(item.get('c_prod_original')
                                                             or cod_xml).strip()

                        if acao == "ATUALIZAR ERP":
                            novo_dict['PRODUTO_CODIGO'] = erp_match.get('produto_codigo')
                            novo_dict['_ACAO'] = 'UPDATE'
                        else:
                            codigo_final, cod_aux = codigo_erp_numerico(
                                cod_xml, existentes_codigos, self.modo_codigo)
                            novo_dict['PRODUTO_CODIGO'] = codigo_final
                            novo_dict['PRODUTO_COD_AUXILIAR'] = cod_aux[:100] or None
                            # A importação de notas procura o produto por
                            # COD_IMPORTACAO antes do auxiliar; sem gravar aqui, o
                            # produto cadastrado nesta tela não é reencontrado lá.
                            novo_dict['PRODUTO_COD_IMPORTACAO'] = cod_aux[:100] or None
                            novo_dict['_ACAO'] = 'INSERT'
                            existentes_codigos.add(codigo_final)

                        self.produtos_para_inserir.append(novo_dict)
                        
                self.after(0, self._renderizar_dados)
            except Exception as e:
                self.after(0, lambda e=e: messagebox.showerror("Erro", f"Erro ao preparar dados:\n{e}", parent=self))
                self.after(0, self.destroy)
                
        threading.Thread(target=task, daemon=True).start()

    def _criar_widgets(self):
        self.lbl_titulo = ttk.Label(self, text="Carregando produtos para visualização...", font=("Segoe UI", 12, "bold"))
        self.lbl_titulo.pack(anchor=tk.W, padx=10, pady=10)
        
        barra = BarraFluida(self, "Editar Grupo/Subgrupo do(s) Produto(s) Selecionado(s)")
        barra.pack(fill=tk.X, padx=10, pady=5)

        cx = barra.grupo()
        ttk.Label(cx, text="Grupo:").pack(side=tk.LEFT, padx=(0, 4))
        self.cb_grupo = ttk.Combobox(cx, width=26, state="readonly")
        self.cb_grupo.pack(side=tk.LEFT)
        self.cb_grupo.bind("<<ComboboxSelected>>", self._on_grupo_selecionado)

        cx = barra.grupo()
        ttk.Label(cx, text="Subgrupo:").pack(side=tk.LEFT, padx=(0, 4))
        self.cb_subgrupo = ttk.Combobox(cx, width=26, state="readonly")
        self.cb_subgrupo.pack(side=tk.LEFT)

        cx = barra.grupo()
        ttk.Button(cx, text="Aplicar Seleção",
                   command=self._aplicar_grupo_subgrupo).pack(side=tk.LEFT)
        barra.montar()

        valores_grupo = [f"{g.get('grupo_codigo')} - {g.get('grupo_descricao', '')}" for g in self.grupos_db]
        self.cb_grupo['values'] = valores_grupo

        frame_grid = ttk.Frame(self)
        frame_grid.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        frame_grid.rowconfigure(0, weight=1)
        frame_grid.columnconfigure(0, weight=1)

        # CÓD. XML fica ao lado do CÓDIGO ERP porque é a correspondência que o
        # usuário precisa ver: o código do ERP é gerado, o do XML é o que veio na nota.
        colunas = ("AÇÃO", "CÓDIGO ERP", "CÓD. XML", "DESCRIÇÃO", "NCM", "C. BARRAS",
                   "CEST", "UNID", "GRUPO", "SUBGRUPO")
        self.tree = ttk.Treeview(frame_grid, columns=colunas, show="headings", selectmode="extended")

        larguras = [90, 90, 110, 230, 80, 100, 70, 50, 110, 110]
        for col, larg in zip(colunas, larguras):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=larg, minwidth=45, stretch=(col == "DESCRIÇÃO"),
                             anchor=tk.CENTER if col != "DESCRIÇÃO" else tk.W)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        scroll_y = ttk.Scrollbar(frame_grid, orient=tk.VERTICAL, command=self.tree.yview)
        # Sem o scroll horizontal, numa tela estreita as colunas finais (GRUPO,
        # SUBGRUPO) ficam inalcançáveis.
        scroll_x = ttk.Scrollbar(frame_grid, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscroll=scroll_y.set, xscroll=scroll_x.set)
        self.tree.grid(row=0, column=0, sticky=tk.NSEW)
        scroll_y.grid(row=0, column=1, sticky=tk.NS)
        scroll_x.grid(row=1, column=0, sticky=tk.EW)

        frame_bot = ttk.Frame(self, padding="10")
        frame_bot.pack(fill=tk.X, side=tk.BOTTOM)
        
        ttk.Button(frame_bot, text="❌ CANCELAR", command=self.destroy).pack(side=tk.LEFT, padx=5)
        self.btn_confirmar = ttk.Button(frame_bot, text="✅ CONFIRMAR E CADASTRAR", command=self._confirmar, state=tk.DISABLED)
        self.btn_confirmar.pack(side=tk.RIGHT, padx=5)
        
    def _renderizar_dados(self):
        for item in self.tree.get_children(): self.tree.delete(item)
        compostos = sum(1 for p in self.produtos_para_inserir
                        if p.get('_COD_XML_ORIGINAL') != p.get('_COD_XML'))
        titulo = f"Produtos que serão processados ({len(self.produtos_para_inserir)} itens)"
        if compostos:
            titulo += (f" — {compostos} vêm de código composto e serão cadastrados "
                       f"em duplicidade proposital")
        self.lbl_titulo.config(text=titulo + ":")
        for idx, p in enumerate(self.produtos_para_inserir):
            acao_str = "📝 ATUALIZAR" if p.get('_ACAO') == 'UPDATE' else "✨ NOVO"

            grupo_nome = self._get_nome_grupo(p.get('PRODUTO_GRUPO'))
            subgrupo_nome = self._get_nome_subgrupo(p.get('PRODUTO_GRUPO'), p.get('PRODUTO_SUBGRUPO'))

            cod_xml = p.get('_COD_XML', '')
            if p.get('_COD_XML_ORIGINAL') and p['_COD_XML_ORIGINAL'] != cod_xml:
                cod_xml = f"{cod_xml}  ⧉"   # veio de um código composto

            self.tree.insert("", tk.END, iid=str(idx), values=(
                acao_str,
                p.get('PRODUTO_CODIGO', ''),
                cod_xml,
                p.get('PRODUTO_DESCRICAO', ''),
                p.get('PRODUTO_CLASS_FISCAL', ''),
                p.get('PRODUTO_CBARRA', ''),
                p.get('PRODUTO_CEST', ''),
                p.get('PRODUTO_UNIDADE_CV', ''),
                grupo_nome,
                subgrupo_nome
            ))
        self.btn_confirmar.config(state=tk.NORMAL)
            
    def _get_nome_grupo(self, grupo_id):
        for g in self.grupos_db:
            if str(g.get('grupo_codigo', '')) == str(grupo_id):
                return f"{g.get('grupo_codigo')} - {g.get('grupo_descricao', '')}"
        return str(grupo_id) if grupo_id else ""

    def _get_nome_subgrupo(self, grupo_id, subgrupo_id):
        for s in self.subgrupos_db:
            if str(s.get('subgrupo_grupo', '')) == str(grupo_id) and str(s.get('subgrupo_codigo', '')) == str(subgrupo_id):
                return f"{s.get('subgrupo_codigo')} - {s.get('subgrupo_descricao', '')}"
        return str(subgrupo_id) if subgrupo_id else ""

    def _on_grupo_selecionado(self, event):
        sel = self.cb_grupo.get()
        if not sel: return
        
        grupo_cod = sel.split('-')[0].strip()
        subgrupos_filtrados = [
            f"{s.get('subgrupo_codigo')} - {s.get('subgrupo_descricao', '')}" 
            for s in self.subgrupos_db if str(s.get('subgrupo_grupo', '')) == grupo_cod
        ]
        self.cb_subgrupo['values'] = subgrupos_filtrados
        self.cb_subgrupo.set('')
        if subgrupos_filtrados:
            self.cb_subgrupo.current(0)

    def _on_tree_select(self, event):
        sel = self.tree.selection()
        if not sel: return
        idx = int(sel[0])
        p = self.produtos_para_inserir[idx]
        
        grupo_nome = self._get_nome_grupo(p.get('PRODUTO_GRUPO'))
        if grupo_nome in self.cb_grupo['values']:
            self.cb_grupo.set(grupo_nome)
            self._on_grupo_selecionado(None)
            subgrupo_nome = self._get_nome_subgrupo(p.get('PRODUTO_GRUPO'), p.get('PRODUTO_SUBGRUPO'))
            if subgrupo_nome in self.cb_subgrupo['values']:
                self.cb_subgrupo.set(subgrupo_nome)
            else:
                self.cb_subgrupo.set('')
        else:
            self.cb_grupo.set('')
            self.cb_subgrupo.set('')

    def _aplicar_grupo_subgrupo(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Selecione um ou mais produtos na lista para aplicar a alteração.", parent=self)
            return
            
        grupo_str = self.cb_grupo.get()
        subgrupo_str = self.cb_subgrupo.get()
        
        grupo_id = grupo_str.split('-')[0].strip() if grupo_str else '1'
        subgrupo_id = subgrupo_str.split('-')[0].strip() if subgrupo_str else '1'
        
        for item_id in sel:
            idx = int(item_id)
            p = self.produtos_para_inserir[idx]
            p['PRODUTO_GRUPO'] = grupo_id
            p['PRODUTO_SUBGRUPO'] = subgrupo_id
            
            valores = list(self.tree.item(item_id, 'values'))
            valores[8] = grupo_str      # GRUPO e SUBGRUPO são as duas últimas
            valores[9] = subgrupo_str
            self.tree.item(item_id, values=valores)
            
        messagebox.showinfo("Sucesso", "Classificação aplicada aos produtos selecionados.", parent=self)

    def _confirmar(self):
        self.callback_importar(self.produtos_para_inserir)
        self.destroy()

class TelaXmlProdutos(ttk.Frame):
    def __init__(self, parent, callback_voltar=None):
        super().__init__(parent, padding="10")
        self.parent = parent
        self.callback_voltar = callback_voltar
        self.pack(fill=tk.BOTH, expand=True)
        print("✅ Instância de TelaXmlProdutos criada.")

        self.resultados_validacao = []
        self.pasta_xmls = ""
        self.arquivos_selecionados = []
        self.dados_grid = {}
        self.grupos_db = []
        self.subgrupos_db = []
        
        self.colunas = ("SEL", "AÇÃO", "CÓD. XML", "CÓD. ERP", "PRODUTO XML", "PRODUTO ERP", "NCM XML", "NCM ERP", "DIVERGÊNCIAS")
        self._sort_directions = {col: False for col in self.colunas}

        self.config = configparser.ConfigParser()
        self.config.read('config.ini', encoding='utf-8')

        self._criar_widgets()
        self._carregar_config_iniciais()
        self.after(500, self._carregar_grupos_db) # Carrega os grupos 0.5s após abrir a tela

    def _criar_widgets(self):
        # === HEADER (identidade Sistecweb) ===
        tema.montar_header(
            self, "Produtos & Consolidado",
            "Auditoria final por produto cruzando NCM, CFOP e ICMS para cadastro e correção"
        ).pack(fill=tk.X)

        # ===================== CORPO: menu lateral + conteúdo =====================
        corpo = tk.Frame(self, bg=tema.BG_BASE)
        corpo.pack(fill=tk.BOTH, expand=True)

        # -------- MENU LATERAL (padrão do main) --------
        # Em console de servidor (1024px ou menos) 210px de menu são 20% da largura
        # útil; encolher o menu devolve espaço para a grade, que é o que interessa.
        largura_sb = 210 if self.winfo_screenwidth() >= 1300 else 168
        sidebar = tema.montar_sidebar(corpo, largura=largura_sb)

        # Rodapé do menu: Voltar
        rodape_sb = tk.Frame(sidebar, bg=tema.SIDEBAR_BG)
        rodape_sb.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 8))
        self.btn_voltar = tema.botao_sidebar(rodape_sb, "⎋   Voltar", self._fechar_tela)
        self.btn_voltar.pack(fill=tk.X)

        tema.titulo_sidebar(sidebar, "AÇÕES").pack(fill=tk.X, pady=(16, 4))

        self.btn_analisar = tema.botao_sidebar(sidebar, "🔍   Analisar XMLs", self._iniciar_analise)
        self.btn_analisar.pack(fill=tk.X)

        self.btn_importar = tema.botao_sidebar(sidebar, "🚀   Processar Produtos", self._iniciar_importacao, cor_fg="#7EE0A0")
        self.btn_importar.config(state=tk.DISABLED)
        self.btn_importar.pack(fill=tk.X)

        self.btn_relatorio = tema.botao_sidebar(sidebar, "📊   Gerar CSV", self._gerar_relatorio)
        self.btn_relatorio.config(state=tk.DISABLED)
        self.btn_relatorio.pack(fill=tk.X)

        # -------- CONTEÚDO --------
        content = tk.Frame(corpo, bg=tema.BG_BASE)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=16, pady=12)

        # === TOP BAR: Config compacta (quebra em linhas em tela estreita) ===
        top_bar = BarraFluida(content, "Configuração")
        top_bar.pack(fill=tk.X, pady=2)

        cx = top_bar.grupo()
        _rotulo(cx, "Empresa:").pack(side=tk.LEFT, padx=(0, 3))
        self.ent_empresa = ttk.Entry(cx, width=6, font=("Segoe UI", 9))
        self.ent_empresa.pack(side=tk.LEFT)

        cx = top_bar.grupo()
        _rotulo(cx, "Filial:").pack(side=tk.LEFT, padx=(0, 3))
        self.ent_filial = ttk.Entry(cx, width=6, font=("Segoe UI", 9))
        self.ent_filial.pack(side=tk.LEFT)

        cx = top_bar.grupo()
        _rotulo(cx, "UF:").pack(side=tk.LEFT, padx=(0, 3))
        self.ent_uf = ttk.Entry(cx, width=4, font=("Segoe UI", 9))
        self.ent_uf.pack(side=tk.LEFT)
        self.ent_uf.insert(0, "SP")

        cx = top_bar.grupo()
        _rotulo(cx, "Código:").pack(side=tk.LEFT, padx=(0, 3))
        self.var_modo_codigo = tk.StringVar(value="xml")
        ttk.Radiobutton(cx, text="Seguir XML", variable=self.var_modo_codigo,
                        value="xml").pack(side=tk.LEFT)
        ttk.Radiobutton(cx, text="Sequencial", variable=self.var_modo_codigo,
                        value="sequencial").pack(side=tk.LEFT, padx=(4, 0))
        top_bar.montar()

        # === FILE SELECTION ===
        frame_dir = ttk.Frame(content)
        frame_dir.pack(fill=tk.X, pady=4)

        tk.Label(frame_dir, text="XMLs:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 2))
        self.ent_pasta = ttk.Entry(frame_dir, font=("Segoe UI", 9))
        self.ent_pasta.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        btn_pasta = ttk.Button(frame_dir, text="📁 Pasta", command=self._selecionar_pasta)
        btn_pasta.pack(side=tk.LEFT, padx=2)
        btn_arq = ttk.Button(frame_dir, text="📄 Arquivos", command=self._selecionar_arquivos)
        btn_arq.pack(side=tk.LEFT, padx=2)

        # === PROGRESS ===
        self.progresso = ttk.Progressbar(content, orient=tk.HORIZONTAL, mode='determinate')
        self.progresso.pack(fill=tk.X, pady=3)
        self.lbl_status = ttk.Label(content, text="Aguardando arquivos...", font=("Segoe UI", 9), foreground="#555")
        self.lbl_status.pack(anchor=tk.W, padx=2)

        # === CLASSIFICATION BAR (quebra em linhas em tela estreita) ===
        class_bar = BarraFluida(content, "Classificação em Lote")
        class_bar.pack(fill=tk.X, pady=4)

        cx = class_bar.grupo()
        _rotulo(cx, "Tipo:").pack(side=tk.LEFT, padx=(0, 3))
        self.cb_tipo = ttk.Combobox(cx, width=17, state="readonly", font=("Segoe UI", 9), values=[
            "1 - Revenda", "2 - Consumo", "3 - Matéria Prima",
            "4 - Produto Acabado", "5 - Serviços", "6 - Outros"
        ])
        self.cb_tipo.pack(side=tk.LEFT)
        self.cb_tipo.set("4 - Produto Acabado")

        cx = class_bar.grupo()
        _rotulo(cx, "Grupo:").pack(side=tk.LEFT, padx=(0, 3))
        self.cb_grupo = ttk.Combobox(cx, width=18, state="readonly", font=("Segoe UI", 9))
        self.cb_grupo.pack(side=tk.LEFT)
        self.cb_grupo.bind("<<ComboboxSelected>>", self._on_grupo_selecionado)

        cx = class_bar.grupo()
        _rotulo(cx, "Subgrupo:").pack(side=tk.LEFT, padx=(0, 3))
        self.cb_subgrupo = ttk.Combobox(cx, width=18, state="readonly", font=("Segoe UI", 9))
        self.cb_subgrupo.pack(side=tk.LEFT)
        ttk.Button(cx, text="🔄", width=3,
                   command=self._carregar_grupos_db).pack(side=tk.LEFT, padx=(4, 0))

        cx = class_bar.grupo()
        self.var_producao_sistec = tk.BooleanVar(value=False)
        ttk.Checkbutton(cx, text="Produção Sistec",
                        variable=self.var_producao_sistec).pack(side=tk.LEFT)

        cx = class_bar.grupo()
        ttk.Button(cx, text="☑ Marcar Novos", command=self._marcar_novos).pack(side=tk.LEFT)
        ttk.Button(cx, text="☐ Desmarcar",
                   command=self._desmarcar_todos).pack(side=tk.LEFT, padx=(4, 0))
        class_bar.montar()

        # === TREEVIEW ===
        frame_grade = ttk.Frame(content)
        frame_grade.pack(fill=tk.BOTH, expand=True, pady=6)
        frame_grade.rowconfigure(0, weight=1)
        frame_grade.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(frame_grade, columns=self.colunas, show="headings")

        larguras = [36, 110, 95, 75, 190, 190, 80, 80, 230]
        for col, larg in zip(self.colunas, larguras):
            self.tree.heading(col, text=col + " ↕", command=lambda c=col: self._sort_treeview(c))
            anchor = tk.W if col in ["PRODUTO XML", "PRODUTO ERP", "DIVERGÊNCIAS"] else tk.CENTER
            # stretch só na última: com as outras fixas o scroll horizontal funciona
            # e nada é comprimido até ficar ilegível em tela estreita.
            self.tree.column(col, width=larg, minwidth=36,
                             stretch=(col == "DIVERGÊNCIAS"), anchor=anchor)

        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)

        self.tree.tag_configure('VALIDADO', background='#EAFAF1')
        self.tree.tag_configure('DIVERGENTE', background='#FEF9E7')
        self.tree.tag_configure('NAO_ENCONTRADO', background='#FADBD8')

        scroll_y = ttk.Scrollbar(frame_grade, orient=tk.VERTICAL, command=self.tree.yview)
        # A grade soma ~1.100px de colunas. Numa tela de 1024 as últimas ficavam
        # fora do alcance, sem scroll horizontal e sem nenhuma indicação disso.
        scroll_x = ttk.Scrollbar(frame_grade, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscroll=scroll_y.set, xscroll=scroll_x.set)
        self.tree.grid(row=0, column=0, sticky=tk.NSEW)
        scroll_y.grid(row=0, column=1, sticky=tk.NS)
        scroll_x.grid(row=1, column=0, sticky=tk.EW)

    def _carregar_config_iniciais(self):
        self.config.read('config.ini', encoding='utf-8')
        empresa = self.config.get('IMPORTACAO', 'empresa', fallback='1')
        filial = self.config.get('IMPORTACAO', 'filial', fallback='1')
        uf = self.config.get('IMPORTACAO', 'uf', fallback='SP')
        
        self.ent_empresa.config(state=tk.NORMAL)
        self.ent_empresa.delete(0, tk.END)
        self.ent_empresa.insert(0, empresa)
        self.ent_empresa.config(state='readonly')
        
        self.ent_filial.config(state=tk.NORMAL)
        self.ent_filial.delete(0, tk.END)
        self.ent_filial.insert(0, filial)
        self.ent_filial.config(state='readonly')
        
        self.ent_uf.config(state=tk.NORMAL)
        self.ent_uf.delete(0, tk.END)
        self.ent_uf.insert(0, uf)
        self.ent_uf.config(state='readonly')

    def _carregar_grupos_db(self):
        """Busca Grupos e Subgrupos do Firebird"""
        config_db = {
            'host': self.config.get('FIREBIRD', 'servidor', fallback='127.0.0.1'),
            'port': self.config.get('FIREBIRD', 'porta', fallback='3050'),
            'database': self.config.get('FIREBIRD', 'caminho_banco', fallback=''),
            'user': self.config.get('FIREBIRD', 'usuario', fallback='SYSDBA'),
            'password': self.config.get('FIREBIRD', 'senha', fallback='masterkey'),
            'fbclient': self.config.get('FIREBIRD', 'fbclient', fallback='')
        }
        emp = int(self.ent_empresa.get() or 1)
        fil = int(self.ent_filial.get() or 1)
        
        try:
            with FirebirdService(config_db) as fb:
                # Query de Grupos
                self.grupos_db = fb.query("SELECT GRUPO_CODIGO, GRUPO_DESCRICAO FROM TABELA_GRUPO WHERE GRUPO_EMPRESA = ? AND GRUPO_FILIAL = ?", [emp, fil])
                
                # Query de Subgrupos
                self.subgrupos_db = fb.query("SELECT SUBGRUPO_CODIGO, SUBGRUPO_DESCRICAO, SUBGRUPO_GRUPO FROM TABELA_SUBGRUPO WHERE SUBGRUPO_EMPRESA = ? AND SUBGRUPO_FILIAL = ?", [emp, fil])
                
            # Popula Combobox de Grupo
            valores_grupo = [f"{g.get('grupo_codigo')} - {g.get('grupo_descricao', '')}" for g in self.grupos_db]
            self.cb_grupo['values'] = valores_grupo
            if valores_grupo:
                self.cb_grupo.current(0)
                self._on_grupo_selecionado(None) # Força popular os subgrupos
        except Exception as e:
            print(f"Aviso: Não foi possível carregar grupos do ERP. O banco pode estar vazio ou a estrutura é diferente. {e}")

    def _on_grupo_selecionado(self, event):
        sel = self.cb_grupo.get()
        if not sel: return
        
        grupo_cod = sel.split('-')[0].strip()
        subgrupos_filtrados = [
            f"{s.get('subgrupo_codigo')} - {s.get('subgrupo_descricao', '')}" 
            for s in self.subgrupos_db if str(s.get('subgrupo_grupo', '')) == grupo_cod
        ]
        self.cb_subgrupo['values'] = subgrupos_filtrados
        self.cb_subgrupo.set('')
        if subgrupos_filtrados:
            self.cb_subgrupo.current(0)

    def _selecionar_pasta(self):
        pasta = filedialog.askdirectory(title="Selecione a pasta com os XMLs de NF-e")
        if pasta:
            self.ent_pasta.delete(0, tk.END)
            self.ent_pasta.insert(0, pasta)
            self.pasta_xmls = pasta
            self.arquivos_selecionados = []

    def _selecionar_arquivos(self):
        arquivos = filedialog.askopenfilenames(title="Selecione os arquivos XML de NF-e", filetypes=[("XML", "*.xml")])
        if arquivos:
            self.ent_pasta.delete(0, tk.END)
            self.ent_pasta.insert(0, f"{len(arquivos)} arquivo(s) selecionado(s)")
            self.arquivos_selecionados = list(arquivos)
            self.pasta_xmls = ""

    def _fechar_tela(self):
        self.destroy()
        if self.callback_voltar:
            self.callback_voltar()

    def _on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            item_id = self.tree.identify_row(event.y)
            if not item_id: return
            
            valores = list(self.tree.item(item_id, 'values'))
            if valores[0] == '-': return
            
            if column == "#1": # Coluna SEL
                valores[0] = '☑' if valores[0] == '☐' else '☐'
                if valores[0] == '☐':
                    valores[1] = 'IGNORAR'
                else:
                    if valores[3] != '-':
                        valores[1] = 'ATUALIZAR ERP'
                    else:
                        valores[1] = 'CADASTRAR NOVO'
                self.tree.item(item_id, values=valores)
                
            elif column == "#2": # Coluna AÇÃO
                if valores[3] != '-': # Tem CÓD. ERP
                    acoes = ["ATUALIZAR ERP", "IGNORAR", "CADASTRAR NOVO"]
                else:
                    acoes = ["CADASTRAR NOVO", "IGNORAR"]
                
                try:
                    idx = acoes.index(valores[1])
                    valores[1] = acoes[(idx + 1) % len(acoes)]
                except ValueError:
                    valores[1] = acoes[0]
                    
                if valores[1] != "IGNORAR":
                    valores[0] = '☑'
                else:
                    valores[0] = '☐'
                    
                self.tree.item(item_id, values=valores)

    def _marcar_novos(self):
        for item in self.tree.get_children():
            valores = list(self.tree.item(item, "values"))
            if valores[0] != '-':
                if valores[3] == '-': # Não tem código ERP
                    valores[0] = "☑"
                    valores[1] = "CADASTRAR NOVO"
                    self.tree.item(item, values=valores)

    def _desmarcar_todos(self):
        for item in self.tree.get_children():
            valores = list(self.tree.item(item, "values"))
            if valores[0] != '-':
                valores[0] = "☐"
                valores[1] = "IGNORAR"
                self.tree.item(item, values=valores)

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

    def _iniciar_analise(self):
        if not self.pasta_xmls and not self.arquivos_selecionados:
            messagebox.showwarning("Atenção", "Selecione uma pasta ou arquivos XML válidos.")
            return
            
        self.btn_analisar.config(state=tk.DISABLED)
        self.btn_relatorio.config(state=tk.DISABLED)
        self.progresso['value'] = 0
        self.lbl_status.config(text="Lendo arquivos XML e carregando dados do ERP...")
        
        # Limpa a grid
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        self.resultados_validacao = []

        # Inicia Thread (O famoso Main Pipeline / Orquestrador)
        threading.Thread(target=self._pipeline_auditoria_bg, daemon=True).start()

    def _pipeline_auditoria_bg(self):
        """Este é o PIPELINE (Comando 07) rodando em background conectado na Interface."""
        try:
            emp = self.ent_empresa.get()
            fil = self.ent_filial.get()
            uf_dest = self.ent_uf.get()
            
            # 1. Conectar e buscar dados do ERP usando FirebirdService
            # (Lembrar que o FirebirdService usa chaves em letras minúsculas por padrão)
            config_db = {
                'host': self.config.get('FIREBIRD', 'servidor', fallback='127.0.0.1'),
                'port': self.config.get('FIREBIRD', 'porta', fallback='3050'),
                'database': self.config.get('FIREBIRD', 'caminho_banco', fallback=''),
                'user': self.config.get('FIREBIRD', 'usuario', fallback='SYSDBA'),
                'password': self.config.get('FIREBIRD', 'senha', fallback='masterkey'),
                'fbclient': self.config.get('FIREBIRD', 'fbclient', fallback='')
            }
            
            with FirebirdService(config_db) as fb:
                # Busca Produtos
                sql_produtos = "SELECT PRODUTO_CODIGO, PRODUTO_COD_AUXILIAR, PRODUTO_DESCRICAO, PRODUTO_CLASS_FISCAL, PRODUTO_CBARRA, PRODUTO_ICMS, PRODUTO_UNIDADE_CV FROM TABELA_PRODUTO WHERE PRODUTO_EMPRESA = ? AND PRODUTO_FILIAL = ?"
                erp_produtos = fb.query(sql_produtos, [emp, fil])
                
                # Limpar espaços em branco à direita (comuns em colunas CHAR do Firebird) para evitar falsas divergências
                for p in erp_produtos:
                    for k, v in p.items():
                        if isinstance(v, str):
                            p[k] = v.strip()
                            
                # Busca Regras ICMS
                sql_icms = "SELECT AICMS_FAIXA, AICMS_ESTADO, AICMS_SITUACAO_CONT, AICMS_ALIQUOTA_CONT, AICMS_REDUCAO_CONT, AICMS_CBENEF_CONT, AICMS_SITUACAO_NCONT, AICMS_ALIQUOTA_NCONT, AICMS_REDUCAO_NCONT, AICMS_CBENEF_NCONT, AICMS_DATA FROM TABELA_ALIQUOTA_ICMS WHERE AICMS_EMPRESA = ? AND AICMS_FILIAL = ?"
                regras_icms = fb.query(sql_icms, [emp, fil])
                
                for r in regras_icms:
                    for k, v in r.items():
                        if isinstance(v, str):
                            r[k] = v.strip()
                
                # Busca CFOPs
                sql_cfops = "SELECT NAT_CODIGO FROM TABELA_NAT_OPERACAO_SAIDA WHERE NAT_EMPRESA = ? AND NAT_FILIAL = ?"
                cfops_erp = fb.query(sql_cfops, [emp, fil])
                
            # 2. Ler todos os itens dos XMLs
            self.parent.after(0, lambda: self.lbl_status.config(text="Analisando notas fiscais (Parsing XML)..."))
            
            if self.arquivos_selecionados:
                itens_xml = []
                total_arqs = len(self.arquivos_selecionados)
                for i_arq, arq in enumerate(self.arquivos_selecionados):
                    try:
                        nfe_data = parse_nfe(arq)
                        for item in nfe_data['itens']:
                            item['chave_nfe'] = nfe_data['chave_nfe']
                            item['inf_cpl'] = nfe_data['inf_cpl']
                            itens_xml.append(item)
                    except Exception as e:
                        print(f"Erro ao ler {arq}: {e}")
                    percent = ((i_arq + 1) / total_arqs) * 50
                    self.parent.after(0, self._atualizar_progresso, percent, f"Lendo XMLs {i_arq+1}/{total_arqs}...")
            else:
                itens_xml = parse_nfe_folder(self.pasta_xmls, callback_progresso=self._progresso_xml)
            
            if not itens_xml:
                self.parent.after(0, lambda: messagebox.showinfo("Aviso", "Nenhum produto/item encontrado nos arquivos XML válidos."))
                self.parent.after(0, self._finalizar_pipeline)
                return
                
            # Remover itens duplicados pelo código do produto
            mapa_produtos_xml = {}
            for item in itens_xml:
                ncm_raw = str(item.get('ncm') or item.get('NCM') or '').replace('.', '').strip()
                if len(ncm_raw) == 8:
                    ncm_fmt = f"{ncm_raw[:4]}.{ncm_raw[4:6]}.{ncm_raw[6:]}"
                    item['ncm'] = ncm_fmt
                    if 'NCM' in item:
                        item['NCM'] = ncm_fmt
                    
                c_prod = str(item.get('c_prod') or item.get('cProd') or '').strip()
                if not c_prod:
                    continue
                # Código composto ("68, 918") vira uma linha por código: cada um
                # precisa do seu cadastro, porque a nota vai referenciar um OU outro.
                partes = separar_codigos(c_prod)
                for parte in partes:
                    if parte in mapa_produtos_xml:
                        continue
                    novo = dict(item)
                    novo['c_prod'] = parte
                    novo['cProd'] = parte
                    novo['c_prod_original'] = c_prod
                    novo['irmaos_codigo'] = [p for p in partes if p != parte]
                    mapa_produtos_xml[parte] = novo

            lista_unicos_xml = list(mapa_produtos_xml.values())
                
            # 3. Instanciar o Validador
            validador = ValidatorFiscal(erp_produtos, regras_icms, [], cfops_erp, [])
            
            total = len(lista_unicos_xml)
            for i, item in enumerate(lista_unicos_xml):
                # 4. Valida cada item
                result = validador.validate(item, uf_dest)
                
                self.resultados_validacao.append({
                    'xml': item,
                    'validacao': result
                })
                
                # Atualiza interface a cada lote (50% a 100% da barra)
                if i % 50 == 0 or i == total - 1:
                    percent = 50 + ((i + 1) / total) * 50
                    self.parent.after(0, self._atualizar_progresso, percent, f"Validando {i+1}/{total} itens fiscais...")
            
            # Conclui
            self.parent.after(0, self._renderizar_resultados)
            
        except Exception as e:
            self.parent.after(0, lambda e=e: messagebox.showerror("Erro de Processamento", f"Falha ao executar auditoria:\n{e}"))
            self.parent.after(0, self._finalizar_pipeline)

    def _progresso_xml(self, atual, total):
        percent = (atual / total) * 50
        self.parent.after(0, self._atualizar_progresso, percent, f"Lendo XMLs {atual}/{total}...")

    def _atualizar_progresso(self, valor, texto):
        try:
            if not self.winfo_exists():
                return
            self.progresso['value'] = valor
            self.lbl_status.config(text=texto)
        except tk.TclError:
            pass

    def _renderizar_resultados(self):
        # Selo deste render. A grade e preenchida em blocos com after(), entao um
        # render antigo pode continuar inserindo DEPOIS que outro limpou a tela —
        # a grade acumula duas analises e os totais somam tudo. O selo faz os
        # blocos do render antigo pararem.
        self._render_seq = getattr(self, '_render_seq', 0) + 1
        meu_seq = self._render_seq

        # Callback agendado em 2º plano: se o usuário já trocou de tela, aborta.
        if not self.winfo_exists():
            return
        self.dados_grid.clear()
        self.lbl_status.config(text="Renderizando resultados na tabela...")
        self.btn_analisar.config(state=tk.DISABLED)
        
        chunk_size = 200
        total = len(self.resultados_validacao)
        
        def render_chunk(start_idx):
            if meu_seq != self._render_seq:
                return  # um render mais novo assumiu a grade
            end_idx = min(start_idx + chunk_size, total)
            for i in range(start_idx, end_idx):
                r = self.resultados_validacao[i]
                xml = r['xml']
                val = r['validacao']
                erp = val.erp_match or {}
                
                # Prepara visualização
                status = val.status
                divs = " | ".join(val.divergencias) if val.divergencias else "OK"
                
                acao = "IGNORAR"
                if status == 'NAO_ENCONTRADO':
                    divs = "Produto não existe no ERP"
                    sel = "☑"
                    acao = "CADASTRAR NOVO"
                elif status == 'DIVERGENTE':
                    sel = "☐"
                    acao = "ATUALIZAR ERP"
                else:
                    sel = "☐"
                    acao = "IGNORAR"

                # Aviso do código composto: o usuário precisa saber que este
                # cadastro tem um gêmeo e que um dos dois será inativado no fim.
                irmaos = xml.get('irmaos_codigo') or []
                if irmaos:
                    aviso = (f"código composto \"{xml.get('c_prod_original')}\" — "
                             f"cadastrar também {', '.join(irmaos)} e inativar o "
                             f"que não for usado")
                    divs = aviso if divs == 'OK' else f"{aviso} | {divs}"

                item_id = self.tree.insert("", tk.END, values=(
                    sel,
                    acao,
                    xml.get('c_prod', ''),
                    erp.get('produto_codigo', '-'),
                    xml.get('x_prod', ''),
                    erp.get('produto_descricao', '-'),
                    xml.get('ncm', ''),
                    erp.get('produto_class_fiscal', '-'),
                    divs
                ), tags=(status,))
                
                self.dados_grid[item_id] = r
                
            if end_idx < total:
                self.progresso['value'] = (end_idx / total) * 100
                self.lbl_status.config(text=f"Renderizando {end_idx}/{total} itens na tabela...")
                self.parent.after(10, render_chunk, end_idx)
            else:
                self.btn_relatorio.config(state=tk.NORMAL)
                
                if total > 0:
                    self.btn_importar.config(state=tk.NORMAL)
                    
                self._finalizar_pipeline()
                messagebox.showinfo("Concluído", "Auditoria de produtos finalizada com sucesso!")

        # Inicia a renderização em pedaços para não travar a tela
        if total > 0:
            render_chunk(0)
        else:
            self._finalizar_pipeline()

    def _finalizar_pipeline(self):
        self.btn_analisar.config(state=tk.NORMAL)
        texto = f"Pronto. {len(self.resultados_validacao)} itens analisados."
        compostos = sum(1 for r in self.resultados_validacao
                        if r['xml'].get('irmaos_codigo'))
        if compostos:
            originais = {r['xml'].get('c_prod_original')
                         for r in self.resultados_validacao if r['xml'].get('irmaos_codigo')}
            texto += (f"  ⧉ {len(originais)} código(s) composto(s) no XML geraram "
                      f"{compostos} cadastros — inative os não usados no fim.")
        self.lbl_status.config(text=texto)

    def _gerar_relatorio(self):
        caminho = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="Auditoria_Fiscal_Produtos.csv", filetypes=[("CSV", "*.csv")])
        if caminho:
            try:
                generate_audit_report(self.resultados_validacao, caminho)
                messagebox.showinfo("Relatório Salvo", f"Auditoria exportada para:\n{caminho}")
            except Exception as e:
                messagebox.showerror("Erro", f"Falha ao salvar CSV:\n{e}")

    def _iniciar_importacao(self):
        selecionados = []
        for item_id in self.tree.get_children():
            valores = self.tree.item(item_id, "values")
            if valores[0] == "☑":
                dados = self.dados_grid[item_id]
                dados['acao_escolhida'] = valores[1]
                selecionados.append(dados)
                
        if not selecionados:
            messagebox.showwarning("Aviso", "Selecione pelo menos um produto para processar (marcados com ☑).")
            return
            
        # Extrai os IDs da Classificação escolhida
        tipo_selecionado = self.cb_tipo.get()
        grupo_selecionado = self.cb_grupo.get()
        subgrupo_selecionado = self.cb_subgrupo.get()
        
        grupo_id = 1
        subgrupo_id = 1
        if grupo_selecionado:
            grupo_id = int(grupo_selecionado.split('-')[0].strip())
        if subgrupo_selecionado:
            subgrupo_id = int(subgrupo_selecionado.split('-')[0].strip())
            
        classificacao = {
            'tipo': tipo_selecionado,
            'grupo_id': grupo_id,
            'subgrupo_id': subgrupo_id,
            'producao_sistec': 'S' if self.var_producao_sistec.get() else None
        }
        
        config_db = {
            'host': self.config.get('FIREBIRD', 'servidor', fallback='127.0.0.1'),
            'port': self.config.get('FIREBIRD', 'porta', fallback='3050'),
            'database': self.config.get('FIREBIRD', 'caminho_banco', fallback=''),
            'user': self.config.get('FIREBIRD', 'usuario', fallback='SYSDBA'),
            'password': self.config.get('FIREBIRD', 'senha', fallback='masterkey'),
            'fbclient': self.config.get('FIREBIRD', 'fbclient', fallback='')
        }
        
        ModalPreviewProdutos(self.parent, selecionados, self.config, config_db, classificacao, self.grupos_db, self.subgrupos_db, self._executar_importacao, modo_codigo=self.var_modo_codigo.get())

    def _executar_importacao(self, produtos_para_inserir):
        self.btn_importar.config(state=tk.DISABLED)
        self.btn_relatorio.config(state=tk.DISABLED)
        self.btn_analisar.config(state=tk.DISABLED)
        self.lbl_status.config(text="Processando produtos...")
        
        threading.Thread(target=self._importar_produtos_bg, args=(produtos_para_inserir,), daemon=True).start()

    def _importar_produtos_bg(self, produtos_para_inserir):
        try:
            emp = int(self.ent_empresa.get())
            fil = int(self.ent_filial.get())
            
            config_db = {
                'host': self.config.get('FIREBIRD', 'servidor', fallback='127.0.0.1'),
                'port': self.config.get('FIREBIRD', 'porta', fallback='3050'),
                'database': self.config.get('FIREBIRD', 'caminho_banco', fallback=''),
                'user': self.config.get('FIREBIRD', 'usuario', fallback='SYSDBA'),
                'password': self.config.get('FIREBIRD', 'senha', fallback='masterkey'),
                'fbclient': self.config.get('FIREBIRD', 'fbclient', fallback='')
            }
            
            with FirebirdService(config_db) as fb:
                cursor = fb.conn.cursor() if hasattr(fb, 'conn') else None
                
                inserts = [p for p in produtos_para_inserir if p.get('_ACAO') == 'INSERT']
                updates = [p for p in produtos_para_inserir if p.get('_ACAO') == 'UPDATE']
                total_geral = len(inserts) + len(updates)
                concluidos = 0

                def _progresso_insert(atual, total):
                    pct = (atual / total) * (len(inserts) / total_geral * 100) if total_geral > 0 else 0
                    self.parent.after(0, self._atualizar_progresso, pct, f"Inserindo {atual}/{total} novos produtos...")

                importer = FirebirdImporter(fb)
                res_imp = importer.import_produtos(inserts, progress_callback=_progresso_insert) if inserts else {'inseridos': 0, 'erros': []}
                concluidos += len(inserts)
                
                inseridos = res_imp.get('inseridos', 0)
                erros = res_imp.get('erros', [])
                
                atualizados = 0
                total_updates = len(updates)
                for i_up, p in enumerate(updates):
                    try:
                        sql_up = "UPDATE TABELA_PRODUTO SET PRODUTO_DESCRICAO = ?, PRODUTO_CLASS_FISCAL = ?, PRODUTO_CBARRA = ?, PRODUTO_CEST = ?, PRODUTO_UNIDADE_CV = ?, PRODUTO_PRODUCAO_SISTEC = ? WHERE PRODUTO_EMPRESA = ? AND PRODUTO_FILIAL = ? AND PRODUTO_CODIGO = ?"
                        params_up = [p.get('PRODUTO_DESCRICAO', '')[:200], p.get('PRODUTO_CLASS_FISCAL', '')[:8], p.get('PRODUTO_CBARRA', '')[:14], p.get('PRODUTO_CEST', '')[:7], p.get('PRODUTO_UNIDADE_CV', '')[:2], p.get('PRODUTO_PRODUCAO_SISTEC'), emp, fil, p.get('PRODUTO_CODIGO')]
                        if cursor: cursor.execute(sql_up, params_up)
                        else: fb.execute(sql_up, params_up)
                        
                        # Inserir também a unidade na TABELA_PRODUTO_UNIDADE
                        unidade_cod = p.get('_UNIDADE_CODIGO', 2)
                        sql_unid = """
                            UPDATE OR INSERT INTO TABELA_PRODUTO_UNIDADE 
                            (TPU_PROD_EMPRESA, TPU_PROD_FILIAL, TPU_PRODUTO, TPU_COD_UNIDADE, TPU_UNIDADE_PADRAO)
                            VALUES (?, ?, ?, ?, 'S')
                            MATCHING (TPU_PROD_EMPRESA, TPU_PROD_FILIAL, TPU_PRODUTO, TPU_COD_UNIDADE)
                        """
                        if cursor: cursor.execute(sql_unid, [emp, fil, p.get('PRODUTO_CODIGO'), unidade_cod])
                        else: fb.execute(sql_unid, [emp, fil, p.get('PRODUTO_CODIGO'), unidade_cod])

                        # Codigo de barras (EAN) na tabela de barras (tela geral)
                        cbarra_up = str(p.get('PRODUTO_CBARRA') or '').strip()
                        cod_prod_up = str(p.get('PRODUTO_CODIGO') or '').strip()
                        if cbarra_up and cod_prod_up.isdigit():
                            sql_cb = ("UPDATE OR INSERT INTO TABELA_PRODUTO_CBARRA "
                                      "(PCB_EMPRESA, PCB_FILIAL, PCB_PRODUTO, PCB_CBARRA, PCB_QTDE_PACK) "
                                      "VALUES (?, ?, ?, ?, 1) "
                                      "MATCHING (PCB_EMPRESA, PCB_FILIAL, PCB_PRODUTO, PCB_CBARRA)")
                            if cursor: cursor.execute(sql_cb, [emp, fil, int(cod_prod_up), cbarra_up[:128]])
                            else: fb.execute(sql_cb, [emp, fil, int(cod_prod_up), cbarra_up[:128]])

                        atualizados += 1
                    except Exception as e_up:
                        erros.append({'produto': p, 'detalhe': f"Erro no UPDATE: {e_up}"})
                    
                    concluidos += 1
                    pct = (concluidos / total_geral) * 100 if total_geral > 0 else 0
                    self.parent.after(0, self._atualizar_progresso, pct, f"Atualizando {i_up+1}/{total_updates} produtos...")
                        
                if cursor: fb.conn.commit()
                
            msg = f"Processamento finalizado!\n\n{inseridos} novos produtos cadastrados.\n{atualizados} produtos atualizados no ERP."
            
            if erros:
                msg += f"\n\nOcorreram {len(erros)} erro(s) durante a importação."
                
            self.parent.after(0, lambda m=msg: messagebox.showinfo("Importação Concluída", m))
            
            if erros:
                log_erros_str = "--- LOG DE ERROS NO PROCESSAMENTO DE PRODUTOS ---\n\n"
                for erro in erros:
                    if 'produto' in erro:
                        cod_prod = erro.get('produto', {}).get('PRODUTO_CODIGO', 'N/A')
                        desc_prod = erro.get('produto', {}).get('PRODUTO_DESCRICAO', 'N/A')
                        acao_prod = erro.get('produto', {}).get('_ACAO', 'N/A')
                        detalhe_erro = erro.get('detalhe', str(erro))
                        log_erros_str += f"[{acao_prod}] Produto Cód: {cod_prod} ({desc_prod})\n--> Erro: {detalhe_erro}\n\n"
                    else:
                        detalhe_erro = erro.get('erro', str(erro))
                        log_erros_str += f"[INSERT] Erro no Banco de Dados:\n--> {detalhe_erro}\n\n"

                resp = messagebox.askyesno(
                    "Log de Erros", 
                    "Foram encontrados erros durante o processamento. Deseja salvar um arquivo de log com os detalhes?", 
                    parent=self.parent
                )
                if resp:
                    caminho_log = filedialog.asksaveasfilename(
                        defaultextension=".txt", 
                        initialfile="LOG_ERROS_PRODUTOS.txt", 
                        filetypes=[("Arquivos de Texto", "*.txt")],
                        parent=self.parent
                    )
                    if caminho_log:
                        try:
                            with open(caminho_log, 'w', encoding='utf-8') as f:
                                f.write(log_erros_str)
                            messagebox.showinfo("Log Salvo", f"Arquivo de log salvo em:\n{caminho_log}", parent=self.parent)
                            if messagebox.askyesno("Abrir Log", "Deseja abrir o arquivo de log agora?", parent=self.parent):
                                try:
                                    os.startfile(caminho_log)
                                except Exception as e:
                                    messagebox.showerror("Erro", f"Erro ao abrir arquivo:\n{e}", parent=self.parent)
                        except Exception as e:
                            messagebox.showerror("Erro ao Salvar", f"Não foi possível salvar o log:\n{e}", parent=self.parent)

            # Atualiza e recarrega a auditoria instantaneamente
            self.parent.after(0, self._iniciar_analise)
            
        except Exception as e:
            self.parent.after(0, lambda err=e: messagebox.showerror("Erro no Processamento", f"Falha ao cadastrar/atualizar produtos:\n{err}"))
        finally:
            self.parent.after(0, lambda: self.btn_importar.config(state=tk.NORMAL))
            self.parent.after(0, lambda: self.btn_relatorio.config(state=tk.NORMAL))
            self.parent.after(0, lambda: self.btn_analisar.config(state=tk.NORMAL))
            self.parent.after(0, self._atualizar_progresso, 100, "Pronto.")
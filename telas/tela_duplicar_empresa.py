import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import configparser
import os
import sys

from utils.firebird_service import FirebirdService
from utils import tema

# Definicao das tabelas envolvidas na duplicacao/configuracao de uma empresa.
# 'pk' = lista de (coluna_no_banco, chave_logica) onde chave_logica aponta
# para 'emp', 'fil' ou 'exerc' informados pelo usuario.
TABELAS = [
    {'aba': 'EMPRESA',       'tabela': 'TABELA_EMPRESA',       'pk': [('EMP_CODIGO', 'emp'), ('EMP_EXERCICIO', 'exerc')]},
    {'aba': 'EMPRESA_PARAM', 'tabela': 'TABELA_EMPRESA_PARAM', 'pk': [('EP_EMPRESA', 'emp')]},
    {'aba': 'FILIAL',        'tabela': 'TABELA_FILIAL',        'pk': [('FILIAL_EMPRESA', 'emp'), ('FILIAL_CODIGO', 'fil')]},
    {'aba': 'FILIAL_PARAM',  'tabela': 'TABELA_FILIAL_PARAM',  'pk': [('FP_EMPRESA', 'emp'), ('FP_FILIAL', 'fil')]},
    {'aba': 'CONFIG_NFE',    'tabela': 'TABELA_CONFIG_NFE',    'pk': [('CNFE_EMPRESA', 'emp'), ('CNFE_FILIAL', 'fil')]},
]

# Codigos de tipo de campo do Firebird (RDB$FIELD_TYPE)
TIPOS_INT = (7, 8, 16)          # SMALLINT, INTEGER, BIGINT (NUMERIC/DECIMAL usam estes + scale)
TIPOS_FLOAT = (10, 27)          # FLOAT, DOUBLE PRECISION
TIPO_BLOB = 261

# Presets de área para o "Ajuste em Lote": palavra-chave (substring, maiúsculas)
# usada para filtrar os nomes de coluna das tabelas de parâmetros/config.
PRESETS_LOTE = {
    "Todos os campos": [],
    "Notas de Saída": ["SAIDA", "VENDA", "DANFE", "NFCE", "NFE", "MDFE", "DACTE", "CTE",
                       "MOD_NOTA", "SERIE_NF", "LER_SERIE", "ULANCTO_NF", "DEV_VENDA",
                       "DEVOL_VENDA", "FRETE_DEST"],
    "Notas de Entrada": ["ENTRADA", "_ENT", "COMPRA", "DEVOL_COMPRA", "DEV_COMPRA",
                         "NF_ENT", "RECEBIMENTO", "CONFIRMA_RECEB"],
    "Pedidos": ["PED", "ORC", "CONFAT", "COTACAO", "REQUISICAO", "ROMANEIO"],
    "Títulos a Receber": ["_REC", "CONREC", "CLIENTE", "CTA_CLIENTE", "V_REC", "P_REC",
                          "PERDA_REC", "ABATIMENTO_REC", "JUROS_REC", "DESC_REC"],
    "Títulos a Pagar": ["_PAG", "CONPAG", "FORNEC", "IRRF", "INSS", "FUNRURAL", "SENAR",
                        "JUROS_PAG", "DESC_PAG", "COMIS_PAG", "DESP_PAG"],
    "Contas Contábeis": ["CTA_", "CONTA", "PLANO", "HIST_"],
    "Centros de Custo": ["_CC", "CC_", "CENT_C", "CENTRO"],
    "CFOP": ["CFOP"],
    "Séries / Numeração": ["SERIE", "UNRO", "_NUM", "SEQ", "NRO_", "ULANC"],
    "Referências de Empresa/Filial (1→91)": [],  # tratado por sufixo _EMPRESA/_FILIAL
}


def _q(col):
    """Coloca aspas duplas no identificador (nomes como 'EP_TAB-CC' exigem)."""
    return '"' + col.replace('"', '') + '"'


class TelaDuplicarEmpresa(ttk.Frame):
    def __init__(self, parent, callback_voltar=None):
        super().__init__(parent, padding="10")
        self.parent = parent
        self.callback_voltar = callback_voltar
        self.pack(fill=tk.BOTH, expand=True)

        self.config = configparser.ConfigParser()
        try:
            self.config.read('config.ini', encoding='utf-8')
        except Exception:
            self.config.read('config.ini', encoding='latin-1')

        self.config_db = {
            'host': self.config.get('FIREBIRD', 'servidor', fallback='127.0.0.1'),
            'port': self.config.get('FIREBIRD', 'porta', fallback='3050'),
            'database': self.config.get('FIREBIRD', 'caminho_banco', fallback=''),
            'user': self.config.get('FIREBIRD', 'usuario', fallback='SYSDBA'),
            'password': self.config.get('FIREBIRD', 'senha', fallback='masterkey'),
            'fbclient': self._resource_path(self.config.get('FIREBIRD', 'fbclient', fallback='').strip())
                        if self.config.get('FIREBIRD', 'fbclient', fallback='').strip() else ''
        }

        # Estado por aba: metadados, valores originais, widgets
        self.meta_cache = {}       # tabela -> lista de dicts de metadados
        self.trees = {}            # aba -> Treeview
        self.filtros = {}          # aba -> Entry de filtro
        self.ordem = {}            # aba -> lista de nomes de campo na ordem
        self.orig = {}             # aba -> {campo: valor_original_str}
        self.pk_cols = {}          # aba -> set de colunas PK
        self.blob_cols = {}        # aba -> set de colunas BLOB
        self.lbl_abas = {}         # aba -> Label de status da aba
        self.sort_state = {}       # aba -> (coluna, reverse) da ordenação atual
        self.alvo_carregado = None # (emp, fil, exerc) atualmente nas abas

        self.filiais_data = []
        self._criar_widgets()
        self._carregar_lista_filiais()

    # ------------------------------------------------------------------ utils
    def _resource_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def _fechar_tela(self):
        self.destroy()
        if self.callback_voltar:
            self.callback_voltar()

    # --------------------------------------------------------------- interface
    def _criar_widgets(self):
        # Header do módulo (identidade Sistecweb)
        tema.montar_header(
            self, "Duplicar / Configurar Empresa",
            "Clona empresa/filial e permite ajustar cada configuração campo a campo antes de gravar"
        ).pack(fill=tk.X)

        # ===================== CORPO: menu lateral + conteúdo =====================
        corpo = tk.Frame(self, bg=tema.BG_BASE)
        corpo.pack(fill=tk.BOTH, expand=True)

        # -------- MENU LATERAL (padrão do main) --------
        sidebar = tema.montar_sidebar(corpo)

        rodape_sb = tk.Frame(sidebar, bg=tema.SIDEBAR_BG)
        rodape_sb.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 8))
        self.btn_voltar = tema.botao_sidebar(rodape_sb, "⎋   Voltar", self._fechar_tela)
        self.btn_voltar.pack(fill=tk.X)

        tema.titulo_sidebar(sidebar, "AÇÕES").pack(fill=tk.X, pady=(16, 4))

        self.btn_duplicar = tema.botao_sidebar(sidebar, "⧉   Duplicar Empresa", self._duplicar, cor_fg="#7EE0A0")
        self.btn_duplicar.pack(fill=tk.X)

        self.btn_carregar = tema.botao_sidebar(sidebar, "📥   Carregar nas Abas", self._carregar_config)
        self.btn_carregar.pack(fill=tk.X)

        self.btn_salvar_tudo = tema.botao_sidebar(sidebar, "💾   Salvar TODAS as Abas", self._salvar_tudo, cor_fg="#7EE0A0")
        self.btn_salvar_tudo.pack(fill=tk.X)

        self.btn_salvar_aba = tema.botao_sidebar(sidebar, "💾   Salvar Aba Atual", self._salvar_aba_atual)
        self.btn_salvar_aba.pack(fill=tk.X)

        # -------- CONTEÚDO --------
        content = tk.Frame(corpo, bg=tema.BG_BASE)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=16, pady=12)

        # === ETAPA 1: DUPLICACAO ===
        dup = ttk.LabelFrame(content, text="1. Duplicar (copia todas as tabelas trocando apenas as chaves)", padding="8")
        dup.pack(fill=tk.X, pady=4)

        tk.Label(dup, text="Origem:", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, padx=(4, 2), pady=4, sticky=tk.E)
        self.cb_origem = ttk.Combobox(dup, width=48, state="readonly", font=("Segoe UI", 9))
        self.cb_origem.grid(row=0, column=1, columnspan=3, padx=2, pady=4, sticky=tk.W)
        self.cb_origem.bind("<<ComboboxSelected>>", self._on_origem_sel)

        tk.Label(dup, text="Exercício origem:", font=("Segoe UI", 9, "bold")).grid(row=0, column=4, padx=(10, 2), pady=4, sticky=tk.E)
        self.ent_exerc_orig = ttk.Entry(dup, width=8, font=("Segoe UI", 9))
        self.ent_exerc_orig.grid(row=0, column=5, padx=2, pady=4, sticky=tk.W)

        tk.Label(dup, text="Nova Empresa:", font=("Segoe UI", 9, "bold")).grid(row=1, column=0, padx=(4, 2), pady=4, sticky=tk.E)
        self.ent_dest_emp = ttk.Entry(dup, width=8, font=("Segoe UI", 9))
        self.ent_dest_emp.grid(row=1, column=1, padx=2, pady=4, sticky=tk.W)

        tk.Label(dup, text="Nova Filial:", font=("Segoe UI", 9, "bold")).grid(row=1, column=2, padx=(10, 2), pady=4, sticky=tk.E)
        self.ent_dest_fil = ttk.Entry(dup, width=8, font=("Segoe UI", 9))
        self.ent_dest_fil.grid(row=1, column=3, padx=2, pady=4, sticky=tk.W)

        tk.Label(dup, text="Novo Exercício:", font=("Segoe UI", 9, "bold")).grid(row=1, column=4, padx=(10, 2), pady=4, sticky=tk.E)
        self.ent_dest_exerc = ttk.Entry(dup, width=8, font=("Segoe UI", 9))
        self.ent_dest_exerc.grid(row=1, column=5, padx=2, pady=4, sticky=tk.W)

        # === ETAPA 2: CONFIGURACAO ===
        cfg = ttk.LabelFrame(content, text="2. Configurar (edite os campos e grave — defina o que vai junto e o que vai separado)", padding="8")
        cfg.pack(fill=tk.BOTH, expand=True, pady=4)

        carreg = ttk.Frame(cfg)
        carreg.pack(fill=tk.X, pady=(0, 6))
        tk.Label(carreg, text="Empresa:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(4, 2))
        self.ent_cfg_emp = ttk.Entry(carreg, width=8, font=("Segoe UI", 9))
        self.ent_cfg_emp.pack(side=tk.LEFT, padx=2)
        tk.Label(carreg, text="Filial:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(10, 2))
        self.ent_cfg_fil = ttk.Entry(carreg, width=8, font=("Segoe UI", 9))
        self.ent_cfg_fil.pack(side=tk.LEFT, padx=2)
        tk.Label(carreg, text="Exercício:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(10, 2))
        self.ent_cfg_exerc = ttk.Entry(carreg, width=8, font=("Segoe UI", 9))
        self.ent_cfg_exerc.pack(side=tk.LEFT, padx=2)
        tk.Label(carreg, text="Duplo-clique no valor para editar. Chaves e campos BLOB são bloqueados.",
                 font=("Segoe UI", 8, "italic"), fg="#7F8C8D").pack(side=tk.LEFT, padx=12)

        self.notebook = ttk.Notebook(cfg)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        style = ttk.Style()
        try:
            style.configure("Dup.Treeview", rowheight=22)
        except Exception:
            pass

        for tbl in TABELAS:
            aba = tbl['aba']
            frame = ttk.Frame(self.notebook, padding="4")
            self.notebook.add(frame, text=aba)

            topo = ttk.Frame(frame)
            topo.pack(fill=tk.X, pady=(0, 4))
            tk.Label(topo, text="🔎 Filtrar campo:", font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT, padx=(2, 2))
            ent_filtro = ttk.Entry(topo, width=30, font=("Segoe UI", 9))
            ent_filtro.pack(side=tk.LEFT, padx=2)
            ent_filtro.bind("<KeyRelease>", lambda e, a=aba: self._filtrar(a))
            self.filtros[aba] = ent_filtro
            lbl_status = tk.Label(topo, text="(nenhum registro carregado)", font=("Segoe UI", 8, "italic"), fg="#7F8C8D")
            lbl_status.pack(side=tk.LEFT, padx=12)
            self.lbl_abas[aba] = lbl_status

            grid_frame = ttk.Frame(frame)
            grid_frame.pack(fill=tk.BOTH, expand=True)

            tree = ttk.Treeview(grid_frame, columns=("campo", "valor"), show="headings",
                                 style="Dup.Treeview", selectmode="browse")
            tree.heading("campo", text="CAMPO", command=lambda a=aba: self._ordenar(a, "campo"))
            tree.heading("valor", text="VALOR", command=lambda a=aba: self._ordenar(a, "valor"))
            tree.column("campo", width=330, anchor=tk.W)
            tree.column("valor", width=520, anchor=tk.W)
            tree.tag_configure("pk", background="#F2D7D5")
            tree.tag_configure("blob", background="#EAECEE")
            tree.tag_configure("changed", background="#D5F5E3")

            vsb = ttk.Scrollbar(grid_frame, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=vsb.set)
            tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            vsb.pack(side=tk.RIGHT, fill=tk.Y)
            tree.bind("<Double-1>", lambda e, a=aba: self._editar_celula(e, a))
            tree.bind("<Return>", lambda e, a=aba: self._editar_por_teclado(a))
            self.trees[aba] = tree

        # nova aba: ajuste em lote (NF-e / pedidos / títulos / referências)
        self._criar_aba_lote()

    # ---------------------------------------------------------- carga de dados
    def _carregar_lista_filiais(self):
        try:
            with FirebirdService(self.config_db) as fb:
                sql = ("SELECT F.FILIAL_EMPRESA, F.FILIAL_CODIGO, F.FILIAL_FANTASIA, F.FILIAL_UF, "
                       "E.EMP_NOME, E.EMP_EXERCICIO "
                       "FROM TABELA_FILIAL F JOIN TABELA_EMPRESA E ON F.FILIAL_EMPRESA = E.EMP_CODIGO "
                       "ORDER BY F.FILIAL_EMPRESA, F.FILIAL_CODIGO")
                self.filiais_data = fb.query(sql)
        except Exception as e:
            messagebox.showerror("Erro de conexão",
                                 f"Não foi possível ler as empresas/filiais:\n{e}", parent=self.parent)
            self.filiais_data = []
            return

        valores = []
        for f in self.filiais_data:
            emp = f.get('filial_empresa')
            fil = f.get('filial_codigo')
            nome = str(f.get('filial_fantasia') or f.get('emp_nome', ''))
            uf = str(f.get('filial_uf', '') or '')
            valores.append(f"Emp {emp} | Fil {fil} - {nome} ({uf})")
        self.cb_origem['values'] = valores

    def _on_origem_sel(self, event=None):
        idx = self.cb_origem.current()
        if idx < 0 or idx >= len(self.filiais_data):
            return
        f = self.filiais_data[idx]
        exerc = f.get('emp_exercicio')
        self.ent_exerc_orig.delete(0, tk.END)
        self.ent_exerc_orig.insert(0, str(exerc) if exerc is not None else '')
        # pre-preenche exercicio destino com o mesmo da origem
        if not self.ent_dest_exerc.get().strip():
            self.ent_dest_exerc.insert(0, str(exerc) if exerc is not None else '')

    def _get_meta(self, fb, tabela):
        """Retorna metadados das colunas (nome, tipo, scale, blob, computed), em cache."""
        if tabela in self.meta_cache:
            return self.meta_cache[tabela]
        sql = ("SELECT rf.RDB$FIELD_NAME, f.RDB$FIELD_TYPE, f.RDB$FIELD_SCALE, f.RDB$COMPUTED_BLR "
               "FROM RDB$RELATION_FIELDS rf "
               "JOIN RDB$FIELDS f ON rf.RDB$FIELD_SOURCE = f.RDB$FIELD_NAME "
               "WHERE rf.RDB$RELATION_NAME = ? "
               "ORDER BY rf.RDB$FIELD_POSITION")
        rows = fb.query(sql, [tabela])
        meta = []
        for r in rows:
            nome = str(r.get('rdb$field_name', '')).strip()
            tipo = r.get('rdb$field_type')
            scale = r.get('rdb$field_scale') or 0
            computed = r.get('rdb$computed_blr') is not None
            meta.append({
                'nome': nome,
                'tipo': tipo,
                'scale': scale,
                'blob': tipo == TIPO_BLOB,
                'computed': computed,
            })
        self.meta_cache[tabela] = meta
        return meta

    # ----------------------------------------------------------- duplicacao
    def _ler_destino_dup(self):
        try:
            orig_emp = int(self.filiais_data[self.cb_origem.current()].get('filial_empresa'))
            orig_fil = int(self.filiais_data[self.cb_origem.current()].get('filial_codigo'))
        except Exception:
            raise ValueError("Selecione a empresa/filial de ORIGEM.")
        try:
            orig_exerc = int(self.ent_exerc_orig.get().strip())
        except Exception:
            raise ValueError("Exercício de origem inválido.")
        try:
            dest_emp = int(self.ent_dest_emp.get().strip())
            dest_fil = int(self.ent_dest_fil.get().strip())
            dest_exerc = int(self.ent_dest_exerc.get().strip())
        except Exception:
            raise ValueError("Preencha Nova Empresa, Nova Filial e Novo Exercício com números.")
        orig = {'emp': orig_emp, 'fil': orig_fil, 'exerc': orig_exerc}
        dest = {'emp': dest_emp, 'fil': dest_fil, 'exerc': dest_exerc}
        return orig, dest

    def _duplicar(self):
        try:
            orig, dest = self._ler_destino_dup()
        except ValueError as e:
            messagebox.showwarning("Atenção", str(e), parent=self.parent)
            return

        if orig['emp'] == dest['emp'] and orig['fil'] == dest['fil']:
            messagebox.showwarning("Atenção", "A empresa/filial de destino é igual à de origem.", parent=self.parent)
            return

        if not messagebox.askyesno(
                "Confirmar duplicação",
                f"Copiar de  Emp {orig['emp']} / Fil {orig['fil']} / Exerc {orig['exerc']}\n"
                f"para       Emp {dest['emp']} / Fil {dest['fil']} / Exerc {dest['exerc']} ?\n\n"
                "Serão copiadas: EMPRESA, EMPRESA_PARAM, FILIAL, FILIAL_PARAM, CONFIG_NFE.\n"
                "Tabelas que já existirem no destino serão puladas.",
                parent=self.parent):
            return

        inseridas, puladas, erros = [], [], []
        try:
            with FirebirdService(self.config_db) as fb:
                def _op(cur):
                    for tbl in TABELAS:
                        nome_tbl = tbl['tabela']
                        meta = self._get_meta(fb, nome_tbl)
                        cols = [m['nome'] for m in meta if not m['computed']]
                        pk_cols = [c for c, _ in tbl['pk']]

                        # valores de origem e destino para as chaves
                        orig_pk_vals = [orig[key] for _, key in tbl['pk']]
                        dest_por_col = {c: dest[key] for c, key in tbl['pk']}

                        where = " AND ".join(f"{_q(c)} = ?" for c, _ in tbl['pk'])

                        # origem existe?
                        r_o = fb.query(f"SELECT COUNT(*) AS N FROM {nome_tbl} WHERE {where}", orig_pk_vals)
                        if not r_o or (r_o[0].get('n') or 0) == 0:
                            puladas.append(f"{tbl['aba']} (origem não existe)")
                            continue

                        # destino já existe?
                        dest_pk_vals = [dest[key] for _, key in tbl['pk']]
                        r_d = fb.query(f"SELECT COUNT(*) AS N FROM {nome_tbl} WHERE {where}", dest_pk_vals)
                        if r_d and (r_d[0].get('n') or 0) > 0:
                            puladas.append(f"{tbl['aba']} (destino já existe)")
                            continue

                        # monta INSERT ... SELECT trocando as PKs por parâmetros
                        select_terms, params = [], []
                        for c in cols:
                            if c in dest_por_col:
                                select_terms.append("?")
                                params.append(dest_por_col[c])
                            else:
                                select_terms.append(_q(c))
                        params.extend(orig_pk_vals)  # para o WHERE

                        sql = (f"INSERT INTO {nome_tbl} ({', '.join(_q(c) for c in cols)}) "
                               f"SELECT {', '.join(select_terms)} FROM {nome_tbl} WHERE {where}")
                        cur.execute(sql, params)
                        inseridas.append(tbl['aba'])
                    return True
                fb.transaction(_op)
        except Exception as e:
            messagebox.showerror("Erro na duplicação",
                                 f"Nada foi gravado (rollback).\n\n{e}", parent=self.parent)
            return

        msg = "Duplicação concluída.\n\n"
        if inseridas:
            msg += "Copiadas: " + ", ".join(inseridas) + "\n"
        if puladas:
            msg += "Puladas: " + ", ".join(puladas) + "\n"
        messagebox.showinfo("Duplicar Empresa", msg, parent=self.parent)

        # ja aponta a etapa de configuracao para o destino e carrega
        self.ent_cfg_emp.delete(0, tk.END); self.ent_cfg_emp.insert(0, str(dest['emp']))
        self.ent_cfg_fil.delete(0, tk.END); self.ent_cfg_fil.insert(0, str(dest['fil']))
        self.ent_cfg_exerc.delete(0, tk.END); self.ent_cfg_exerc.insert(0, str(dest['exerc']))
        self._carregar_lista_filiais()
        self._carregar_config()

    # ----------------------------------------------------------- configuracao
    def _ler_alvo_cfg(self):
        try:
            emp = int(self.ent_cfg_emp.get().strip())
            fil = int(self.ent_cfg_fil.get().strip())
            exerc = int(self.ent_cfg_exerc.get().strip())
        except Exception:
            raise ValueError("Informe Empresa, Filial e Exercício (números) para carregar.")
        return {'emp': emp, 'fil': fil, 'exerc': exerc}

    def _carregar_config(self):
        try:
            alvo = self._ler_alvo_cfg()
        except ValueError as e:
            messagebox.showwarning("Atenção", str(e), parent=self.parent)
            return

        try:
            with FirebirdService(self.config_db) as fb:
                for tbl in TABELAS:
                    aba = tbl['aba']
                    meta = self._get_meta(fb, tbl['tabela'])
                    where = " AND ".join(f"{_q(c)} = ?" for c, _ in tbl['pk'])
                    params = [alvo[key] for _, key in tbl['pk']]
                    rows = fb.query(f"SELECT * FROM {tbl['tabela']} WHERE {where}", params)
                    self._popular_aba(aba, tbl, meta, rows[0] if rows else None)
        except Exception as e:
            messagebox.showerror("Erro ao carregar", str(e), parent=self.parent)
            return

        self.alvo_carregado = alvo

    def _popular_aba(self, aba, tbl, meta, row):
        tree = self.trees[aba]
        tree.delete(*tree.get_children())
        self.ordem[aba] = []
        self.orig[aba] = {}
        self.pk_cols[aba] = {c for c, _ in tbl['pk']}
        self.blob_cols[aba] = {m['nome'] for m in meta if m['blob']}
        self.filtros[aba].delete(0, tk.END)

        if row is None:
            self.lbl_abas[aba].config(text="⚠ registro NÃO encontrado para esta empresa/filial", fg="#C80000")
            return

        for m in meta:
            if m['computed']:
                continue
            nome = m['nome']
            valor_db = row.get(nome.lower())
            is_pk = nome in self.pk_cols[aba]
            is_blob = m['blob']

            if is_blob:
                display = "[BLOB - não editável]"
            else:
                display = '' if valor_db is None else str(valor_db)
                self.orig[aba][nome] = display  # guarda original só de editáveis

            tags = ()
            if is_pk:
                tags = ("pk",)
            elif is_blob:
                tags = ("blob",)
            tree.insert("", tk.END, iid=nome, values=(nome, display), tags=tags)
            self.ordem[aba].append(nome)

        self.lbl_abas[aba].config(
            text=f"✔ {len(self.ordem[aba])} campos carregados", fg="#16A34A")

        # ordena alfabeticamente por CAMPO automaticamente ao carregar
        self.sort_state.pop(aba, None)
        self._ordenar(aba, "campo")

        # seleciona e foca o 1º campo (navegação por setas + Enter já funciona)
        if self.ordem[aba]:
            primeiro = self.ordem[aba][0]
            tree.selection_set(primeiro)
            tree.focus(primeiro)

    def _ordenar(self, aba, col):
        """Ordena a grade pela coluna clicada (alterna asc/desc)."""
        tree = self.trees.get(aba)
        if not tree or not self.ordem.get(aba):
            return
        prev_col, prev_rev = self.sort_state.get(aba, (None, False))
        reverse = (prev_col == col) and (not prev_rev)

        # reanexa tudo antes de reordenar (itens filtrados podem estar destacados)
        for i, nome in enumerate(self.ordem[aba]):
            tree.reattach(nome, '', i)

        def chave(nome):
            if col == "campo":
                return nome.upper()
            return str(tree.set(nome, "valor")).upper()

        itens = sorted(self.ordem[aba], key=chave, reverse=reverse)
        for i, nome in enumerate(itens):
            tree.move(nome, "", i)
        self.ordem[aba] = itens
        self.sort_state[aba] = (col, reverse)

        seta = " ▼" if reverse else " ▲"
        tree.heading("campo", text="CAMPO" + (seta if col == "campo" else ""))
        tree.heading("valor", text="VALOR" + (seta if col == "valor" else ""))

        # reaplica o filtro vigente (se houver)
        self._filtrar(aba)

    def _filtrar(self, aba):
        tree = self.trees.get(aba)
        if not tree or aba not in self.ordem:
            return
        txt = self.filtros[aba].get().strip().upper()
        # reanexa tudo na ordem, depois remove o que nao casa
        for i, nome in enumerate(self.ordem[aba]):
            tree.reattach(nome, '', i)
        if txt:
            for nome in self.ordem[aba]:
                valor = str(tree.set(nome, 'valor')).upper()
                if txt not in nome.upper() and txt not in valor:
                    tree.detach(nome)

    def _editar_celula(self, event, aba):
        """Duplo-clique na coluna VALOR abre o editor."""
        tree = self.trees[aba]
        if tree.identify_region(event.x, event.y) != 'cell':
            return
        if tree.identify_column(event.x) != '#2':  # só a coluna VALOR
            return
        self._abrir_editor(aba, tree.identify_row(event.y))

    def _editar_por_teclado(self, aba):
        """Enter edita o campo focado (navegação pelas setas ↑/↓ + Enter)."""
        tree = self.trees[aba]
        self._abrir_editor(aba, tree.focus())
        return "break"

    def _abrir_editor(self, aba, nome):
        tree = self.trees[aba]
        if not nome:
            return
        if nome in self.pk_cols.get(aba, set()):
            messagebox.showinfo("Campo bloqueado", "Este é um campo-chave e não pode ser alterado por aqui.", parent=self.parent)
            return
        if nome in self.blob_cols.get(aba, set()):
            messagebox.showinfo("Campo bloqueado", "Campo BLOB não é editável nesta tela.", parent=self.parent)
            return

        tree.see(nome)
        bbox = tree.bbox(nome, "#2")
        if not bbox:
            return
        x, y, w, h = bbox
        valor_atual = tree.set(nome, "valor")
        entry = ttk.Entry(tree)
        entry.place(x=x, y=y, width=w, height=h)
        entry.insert(0, valor_atual)
        entry.focus_set()
        entry.select_range(0, tk.END)

        estado = {"fechado": False}

        def _voltar_foco():
            tree.focus_set()
            tree.focus(nome)
            tree.selection_set(nome)

        def salvar(e=None):
            if estado["fechado"]:
                return "break"
            estado["fechado"] = True
            novo = entry.get()
            tree.set(nome, "valor", novo)
            if novo != self.orig[aba].get(nome, ""):
                tree.item(nome, tags=("changed",))
            else:
                tree.item(nome, tags=())
            entry.destroy()
            _voltar_foco()
            return "break"  # evita reabrir o editor pela tecla Enter da grade

        def cancelar(e=None):
            if estado["fechado"]:
                return "break"
            estado["fechado"] = True
            entry.destroy()
            _voltar_foco()
            return "break"

        entry.bind("<Return>", salvar)
        entry.bind("<FocusOut>", salvar)
        entry.bind("<Escape>", cancelar)

    # -------------------------------------------------------------- gravacao
    def _converter(self, valor_str, meta_campo):
        s = valor_str.strip()
        if s == '':
            return None
        tipo = meta_campo['tipo']
        scale = meta_campo['scale'] or 0
        try:
            if tipo in TIPOS_INT:
                if scale < 0:
                    return float(s.replace(',', '.'))
                return int(s)
            if tipo in TIPOS_FLOAT:
                return float(s.replace(',', '.'))
        except ValueError:
            raise ValueError(f"valor '{s}' não é numérico")
        return s  # texto / data / hora / timestamp

    def _coletar_alteracoes(self, aba, tbl):
        """Retorna (sql, params) do UPDATE da aba, ou None se nada mudou."""
        if aba not in self.orig or not self.orig[aba]:
            return None
        tree = self.trees[aba]
        meta_por_nome = {m['nome']: m for m in self.meta_cache.get(tbl['tabela'], [])}

        sets, params, mudados = [], [], []
        for nome, orig_val in self.orig[aba].items():
            atual = tree.set(nome, 'valor')
            if atual == orig_val:
                continue
            meta_campo = meta_por_nome.get(nome)
            if not meta_campo:
                continue
            valor = self._converter(atual, meta_campo)
            sets.append(f"{_q(nome)} = ?")
            params.append(valor)
            mudados.append(nome)

        if not sets:
            return None

        where = " AND ".join(f"{_q(c)} = ?" for c, _ in tbl['pk'])
        for _, key in tbl['pk']:
            params.append(self.alvo_carregado[key])
        sql = f"UPDATE {tbl['tabela']} SET {', '.join(sets)} WHERE {where}"
        return sql, params, mudados

    def _salvar_aba_atual(self):
        idx = self.notebook.index(self.notebook.select())
        if idx >= len(TABELAS):
            messagebox.showinfo("Ajuste em Lote",
                                "Nesta aba use o botão '💾 Salvar em Lote'.", parent=self.parent)
            return
        self._salvar([TABELAS[idx]])

    def _salvar_tudo(self):
        self._salvar(TABELAS)

    def _salvar(self, tabelas):
        if not self.alvo_carregado:
            messagebox.showwarning("Atenção", "Carregue um registro nas abas antes de salvar.", parent=self.parent)
            return

        planos = []
        try:
            for tbl in tabelas:
                res = self._coletar_alteracoes(tbl['aba'], tbl)
                if res:
                    planos.append((tbl, res))
        except ValueError as e:
            messagebox.showerror("Valor inválido", str(e), parent=self.parent)
            return

        if not planos:
            messagebox.showinfo("Salvar", "Nenhuma alteração para gravar.", parent=self.parent)
            return

        resumo = "\n".join(f"• {tbl['aba']}: {len(res[2])} campo(s)" for tbl, res in planos)
        if not messagebox.askyesno("Confirmar gravação",
                                   f"Gravar as alterações abaixo?\n\n{resumo}", parent=self.parent):
            return

        try:
            with FirebirdService(self.config_db) as fb:
                def _op(cur):
                    for _tbl, (sql, params, _m) in planos:
                        cur.execute(sql, params)
                    return True
                fb.transaction(_op)
        except Exception as e:
            messagebox.showerror("Erro ao gravar", f"Nada foi gravado (rollback).\n\n{e}", parent=self.parent)
            return

        # atualiza originais e limpa marcacao de alterado
        for tbl, (_sql, _params, mudados) in planos:
            aba = tbl['aba']
            tree = self.trees[aba]
            for nome in mudados:
                self.orig[aba][nome] = tree.set(nome, 'valor')
                tree.item(nome, tags=())
        messagebox.showinfo("Salvar", "Alterações gravadas com sucesso.", parent=self.parent)

    # ==================================================================
    #                         AJUSTE EM LOTE
    # ==================================================================
    def _criar_aba_lote(self):
        # estado
        self._lote_orig = {}          # nome -> valor original (alvo) str
        self._lote_ref = {}           # nome -> valor da empresa referência str
        self._lote_pending = {}       # nome -> novo valor str
        self._lote_cols = []          # nomes candidatos (sem PK/BLOB/computed)
        self._lote_meta_by_name = {}  # nome -> meta
        self._lote_tbl = None
        self._lote_alvo = None

        frame = ttk.Frame(self.notebook, padding="6")
        self.notebook.add(frame, text="⚙ Ajuste em Lote")

        l1 = ttk.LabelFrame(frame, text="Alvo (empresa a configurar)  ×  Referência (de onde comparar)", padding=6)
        l1.pack(fill=tk.X)
        tk.Label(l1, text="Empresa alvo:", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky=tk.E, padx=(4, 2), pady=3)
        self.lote_emp = ttk.Entry(l1, width=7); self.lote_emp.grid(row=0, column=1, sticky=tk.W, padx=2)
        tk.Label(l1, text="Filial:", font=("Segoe UI", 9, "bold")).grid(row=0, column=2, sticky=tk.E, padx=(10, 2))
        self.lote_fil = ttk.Entry(l1, width=7); self.lote_fil.grid(row=0, column=3, sticky=tk.W, padx=2)
        tk.Label(l1, text="Exercício:", font=("Segoe UI", 9, "bold")).grid(row=0, column=4, sticky=tk.E, padx=(10, 2))
        self.lote_exe = ttk.Entry(l1, width=8); self.lote_exe.grid(row=0, column=5, sticky=tk.W, padx=2)

        tk.Label(l1, text="Empresa ref.:", font=("Segoe UI", 9, "bold")).grid(row=1, column=0, sticky=tk.E, padx=(4, 2), pady=3)
        self.lote_ref_emp = ttk.Entry(l1, width=7); self.lote_ref_emp.grid(row=1, column=1, sticky=tk.W, padx=2)
        tk.Label(l1, text="Filial ref.:", font=("Segoe UI", 9, "bold")).grid(row=1, column=2, sticky=tk.E, padx=(10, 2))
        self.lote_ref_fil = ttk.Entry(l1, width=7); self.lote_ref_fil.grid(row=1, column=3, sticky=tk.W, padx=2)
        tk.Label(l1, text="Tabela:", font=("Segoe UI", 9, "bold")).grid(row=1, column=4, sticky=tk.E, padx=(10, 2))
        self.lote_cb_tabela = ttk.Combobox(l1, width=16, state="readonly",
                                           values=["EMPRESA", "EMPRESA_PARAM", "FILIAL", "FILIAL_PARAM", "CONFIG_NFE"])
        self.lote_cb_tabela.current(3)  # FILIAL_PARAM (a maior) por padrão
        self.lote_cb_tabela.grid(row=1, column=5, sticky=tk.W, padx=2)
        tema.estilo_botao(l1, "📥 Carregar", self._lote_carregar, "primary").grid(row=0, column=6, rowspan=2, padx=10)

        self.lote_emp.insert(0, self.config.get('IMPORTACAO', 'empresa', fallback='1'))
        self.lote_fil.insert(0, self.config.get('IMPORTACAO', 'filial', fallback='1'))
        self.lote_exe.insert(0, self.config.get('IMPORTACAO', 'exercicio', fallback='2026'))
        self.lote_ref_emp.insert(0, '1'); self.lote_ref_fil.insert(0, '1')

        l2 = ttk.Frame(frame); l2.pack(fill=tk.X, pady=(6, 4))
        tk.Label(l2, text="Área:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(2, 2))
        self.lote_cb_area = ttk.Combobox(l2, width=34, state="readonly", values=list(PRESETS_LOTE.keys()))
        self.lote_cb_area.current(0)
        self.lote_cb_area.pack(side=tk.LEFT, padx=2)
        self.lote_cb_area.bind("<<ComboboxSelected>>", lambda e: self._lote_render())
        tk.Label(l2, text="🔎 Buscar campo:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(12, 2))
        self.lote_busca = ttk.Entry(l2, width=24); self.lote_busca.pack(side=tk.LEFT, padx=2)
        self.lote_busca.bind("<KeyRelease>", lambda e: self._lote_render())

        gf = ttk.Frame(frame); gf.pack(fill=tk.BOTH, expand=True)
        cols = ("campo", "valor", "valorref", "situacao")
        self.lote_tree = ttk.Treeview(gf, columns=cols, show="headings", style="Dup.Treeview", selectmode="extended")
        self.lote_tree.heading("campo", text="CAMPO")
        self.lote_tree.heading("valor", text="VALOR (ALVO)")
        self.lote_tree.heading("valorref", text="VALOR (REFERÊNCIA)")
        self.lote_tree.heading("situacao", text="SITUAÇÃO")
        self.lote_tree.column("campo", width=300, anchor=tk.W)
        self.lote_tree.column("valor", width=220, anchor=tk.W)
        self.lote_tree.column("valorref", width=220, anchor=tk.W)
        self.lote_tree.column("situacao", width=120, anchor=tk.CENTER)
        self.lote_tree.tag_configure("lote_changed", background=tema.BLUE_CONTAINER)
        self.lote_tree.tag_configure("lote_difere", background=tema.WARNING_CT)
        self.lote_tree.tag_configure("lote_igual", background="white")
        vsb = ttk.Scrollbar(gf, orient="vertical", command=self.lote_tree.yview)
        self.lote_tree.configure(yscrollcommand=vsb.set)
        self.lote_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.lote_tree.bind("<Double-1>", self._lote_editar)
        self.lote_tree.bind("<Return>", lambda e: self._lote_editar_teclado())

        ac = ttk.Frame(frame); ac.pack(fill=tk.X, pady=(6, 0))
        tema.estilo_botao(ac, "✏ Aplicar valor aos selecionados", self._lote_aplicar_valor, "primary").pack(side=tk.LEFT, padx=2)
        tema.estilo_botao(ac, "⧉ Copiar Referência → Alvo", self._lote_copiar_ref, "ghost").pack(side=tk.LEFT, padx=2)
        tema.estilo_botao(ac, "🔁 Trocar valor (de→para)…", self._lote_trocar, "ghost").pack(side=tk.LEFT, padx=2)
        tema.estilo_botao(ac, "💾 Salvar em Lote", self._lote_salvar, "success").pack(side=tk.RIGHT, padx=2)
        self.lote_status = tk.Label(frame, text="Carregue uma tabela para começar.", fg="#7F8C8D",
                                    font=("Segoe UI", 8, "italic"), anchor="w")
        self.lote_status.pack(fill=tk.X, pady=(4, 0))

    def _lote_tbl_por_aba(self, aba):
        for t in TABELAS:
            if t['aba'] == aba:
                return t
        return None

    def _lote_carregar(self):
        try:
            alvo = {'emp': int(self.lote_emp.get()), 'fil': int(self.lote_fil.get()), 'exerc': int(self.lote_exe.get())}
            ref = {'emp': int(self.lote_ref_emp.get()), 'fil': int(self.lote_ref_fil.get()), 'exerc': int(self.lote_exe.get())}
        except ValueError:
            messagebox.showwarning("Atenção", "Empresa/Filial/Exercício devem ser números.", parent=self.parent)
            return
        tbl = self._lote_tbl_por_aba(self.lote_cb_tabela.get())
        if not tbl:
            return
        if self._lote_pending and not messagebox.askyesno(
                "Recarregar", f"Há {len(self._lote_pending)} alteração(ões) não salva(s). Descartar?", parent=self.parent):
            return
        try:
            with FirebirdService(self.config_db) as fb:
                meta = self._get_meta(fb, tbl['tabela'])
                cols = [m['nome'] for m in meta if not m['computed'] and not m['blob']]
                sel = ", ".join(_q(c) for c in cols)
                where = " AND ".join(f"{_q(c)} = ?" for c, _ in tbl['pk'])
                ra = fb.query(f"SELECT {sel} FROM {tbl['tabela']} WHERE {where}", [alvo[k] for _, k in tbl['pk']])
                rr = fb.query(f"SELECT {sel} FROM {tbl['tabela']} WHERE {where}", [ref[k] for _, k in tbl['pk']])
        except Exception as e:
            messagebox.showerror("Erro ao carregar", str(e), parent=self.parent)
            return
        if not ra:
            messagebox.showwarning("Atenção", f"Registro ALVO não encontrado em {tbl['tabela']}.", parent=self.parent)
            return

        row_a = ra[0]; row_r = rr[0] if rr else {}
        pk_set = {c for c, _ in tbl['pk']}
        self._lote_tbl = tbl; self._lote_alvo = alvo
        self._lote_pending = {}; self._lote_orig = {}; self._lote_ref = {}; self._lote_cols = []
        self._lote_meta_by_name = {m['nome']: m for m in meta}
        for m in meta:
            nome = m['nome']
            if m['computed'] or m['blob'] or nome in pk_set:
                continue
            va = row_a.get(nome.lower()); vr = row_r.get(nome.lower())
            self._lote_orig[nome] = '' if va is None else str(va)
            self._lote_ref[nome] = '' if vr is None else str(vr)
            self._lote_cols.append(nome)
        if not row_r:
            self.lote_status.config(text="⚠ empresa de referência não encontrada — coluna referência ficará vazia.")
        self._lote_render()

    def _lote_match(self, nome, area, termo):
        up = nome.upper()
        if termo and termo not in up:
            return False
        if area == "Todos os campos":
            return True
        if area.startswith("Referências"):
            return up.endswith("_EMPRESA") or up.endswith("_FILIAL")
        return any(kw in up for kw in PRESETS_LOTE.get(area, []))

    def _lote_render(self):
        if not hasattr(self, 'lote_tree'):
            return
        self.lote_tree.delete(*self.lote_tree.get_children())
        area = self.lote_cb_area.get()
        termo = self.lote_busca.get().strip().upper()
        n_tot = n_dif = 0
        for nome in self._lote_cols:
            if not self._lote_match(nome, area, termo):
                continue
            cur = self._lote_pending.get(nome, self._lote_orig.get(nome, ''))
            ref = self._lote_ref.get(nome, '')
            if nome in self._lote_pending and self._lote_pending[nome] != self._lote_orig.get(nome, ''):
                sit, tag = "✎ alterado", "lote_changed"
            elif cur != ref:
                sit, tag = "≠ difere", "lote_difere"; n_dif += 1
            else:
                sit, tag = "= igual", "lote_igual"
            self.lote_tree.insert("", tk.END, iid=nome, values=(nome, cur, ref, sit), tags=(tag,))
            n_tot += 1
        self.lote_status.config(
            text=f"{n_tot} campo(s) exibido(s)   •   ≠ diferem da referência: {n_dif}   •   "
                 f"✎ alterações pendentes: {len(self._lote_pending)}")

    def _lote_set_pending(self, nome, novo):
        if novo == self._lote_orig.get(nome, ''):
            self._lote_pending.pop(nome, None)
        else:
            self._lote_pending[nome] = novo

    def _lote_editar(self, event):
        if self.lote_tree.identify_region(event.x, event.y) != 'cell':
            return
        if self.lote_tree.identify_column(event.x) != '#2':  # só coluna VALOR (ALVO)
            return
        self._lote_abrir_editor(self.lote_tree.identify_row(event.y))

    def _lote_editar_teclado(self):
        self._lote_abrir_editor(self.lote_tree.focus())
        return "break"

    def _lote_abrir_editor(self, nome):
        if not nome:
            return
        tree = self.lote_tree
        tree.see(nome)
        bbox = tree.bbox(nome, "#2")
        if not bbox:
            return
        x, y, w, h = bbox
        entry = ttk.Entry(tree)
        entry.place(x=x, y=y, width=w, height=h)
        entry.insert(0, tree.set(nome, "valor"))
        entry.focus_set(); entry.select_range(0, tk.END)
        estado = {"f": False}

        def salvar(e=None):
            if estado["f"]:
                return "break"
            estado["f"] = True
            self._lote_set_pending(nome, entry.get())
            entry.destroy()
            self._lote_render()
            tree.selection_set(nome); tree.focus(nome)
            return "break"

        def cancelar(e=None):
            if estado["f"]:
                return "break"
            estado["f"] = True
            entry.destroy()
            return "break"

        entry.bind("<Return>", salvar)
        entry.bind("<FocusOut>", salvar)
        entry.bind("<Escape>", cancelar)

    def _lote_aplicar_valor(self):
        sel = list(self.lote_tree.selection())
        if not sel:
            messagebox.showinfo("Aplicar valor", "Selecione um ou mais campos (Ctrl/Shift).", parent=self.parent)
            return
        val = simpledialog.askstring("Aplicar valor", f"Valor a aplicar em {len(sel)} campo(s):", parent=self.parent)
        if val is None:
            return
        for nome in sel:
            self._lote_set_pending(nome, val)
        self._lote_render()

    def _lote_copiar_ref(self):
        sel = list(self.lote_tree.selection())
        if not sel:
            messagebox.showinfo("Copiar referência", "Selecione um ou mais campos (Ctrl/Shift).", parent=self.parent)
            return
        for nome in sel:
            self._lote_set_pending(nome, self._lote_ref.get(nome, ''))
        self._lote_render()

    def _lote_trocar(self):
        vis = self.lote_tree.get_children()
        if not vis:
            messagebox.showinfo("Trocar valor", "Nada visível para trocar. Carregue e filtre primeiro.", parent=self.parent)
            return
        de = simpledialog.askstring("Trocar valor",
                                    "Trocar os campos VISÍVEIS cujo valor atual seja exatamente:",
                                    parent=self.parent)
        if de is None:
            return
        para = simpledialog.askstring("Trocar valor", f"Substituir '{de}' por:", parent=self.parent)
        if para is None:
            return
        n = 0
        for nome in vis:
            cur = self._lote_pending.get(nome, self._lote_orig.get(nome, ''))
            if cur == de:
                self._lote_set_pending(nome, para)
                n += 1
        self._lote_render()
        messagebox.showinfo("Trocar valor",
                            f"{n} campo(s) marcados para trocar de '{de}' → '{para}'.\n"
                            "Revise (ficam azuis) e clique em '💾 Salvar em Lote'.", parent=self.parent)

    def _lote_salvar(self):
        if not self._lote_tbl or not self._lote_alvo:
            messagebox.showinfo("Salvar em Lote", "Carregue uma tabela primeiro.", parent=self.parent)
            return
        changed = {n: v for n, v in self._lote_pending.items() if v != self._lote_orig.get(n, '')}
        if not changed:
            messagebox.showinfo("Salvar em Lote", "Nenhuma alteração pendente.", parent=self.parent)
            return
        try:
            sets, params = [], []
            for nome, val in changed.items():
                sets.append(f"{_q(nome)} = ?")
                params.append(self._converter(val, self._lote_meta_by_name.get(nome)))
        except ValueError as e:
            messagebox.showerror("Valor inválido", str(e), parent=self.parent)
            return
        tbl = self._lote_tbl
        where = " AND ".join(f"{_q(c)} = ?" for c, _ in tbl['pk'])
        for _, k in tbl['pk']:
            params.append(self._lote_alvo[k])
        if not messagebox.askyesno(
                "Confirmar gravação",
                f"Gravar {len(changed)} campo(s) em {tbl['tabela']}\n"
                f"(Emp {self._lote_alvo['emp']} / Fil {self._lote_alvo['fil']})?", parent=self.parent):
            return
        sql = f"UPDATE {tbl['tabela']} SET {', '.join(sets)} WHERE {where}"
        try:
            with FirebirdService(self.config_db) as fb:
                fb.execute(sql, params)
        except Exception as e:
            messagebox.showerror("Erro ao gravar", f"Nada foi gravado.\n\n{e}", parent=self.parent)
            return
        for nome, val in changed.items():
            self._lote_orig[nome] = val
            self._lote_pending.pop(nome, None)
        self._lote_render()
        messagebox.showinfo("Salvar em Lote", f"{len(changed)} campo(s) gravado(s) com sucesso.", parent=self.parent)

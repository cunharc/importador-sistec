# -*- coding: utf-8 -*-
"""
Vínculo Centro de Custos  <->  Plano de Contas.

Mostra a árvore de Centros de Custo (TABELA_CC) com o vínculo contábil de cada
analítico e permite vincular/corrigir em massa, estilo planilha:
    CC_CONTABIL           = PLANO_CODIGO
    CC_CONTABIL_REDUZIDO  = PLANO_REDUZIDO

Fluxo: dê duplo-clique (ou Enter) num centro de custo analítico -> abre a busca
do plano -> digite o termo/Enter -> escolha a conta. As alterações ficam
destacadas e só vão ao banco quando você clica em "Salvar TODAS" (em lote).
"""

import tkinter as tk
from tkinter import ttk, messagebox
import configparser
import os
import sys

from utils.firebird_service import FirebirdService
from utils import tema


def _norm(v):
    """Normaliza código/reduzido para comparação: None/''/espaços -> None;
    numérico -> string do inteiro; senão string sem espaços."""
    if v is None:
        return None
    s = str(v).strip()
    if s == "":
        return None
    try:
        return str(int(float(s)))
    except (ValueError, TypeError):
        return s


class TelaVinculoCC(ttk.Frame):
    def __init__(self, parent, callback_voltar=None):
        super().__init__(parent, padding="0")
        self.parent = parent
        self.callback_voltar = callback_voltar
        self.pack(fill=tk.BOTH, expand=True)

        self.config = configparser.ConfigParser()
        try:
            self.config.read('config.ini', encoding='utf-8')
        except Exception:
            self.config.read('config.ini', encoding='latin-1')

        fbcli = self.config.get('FIREBIRD', 'fbclient', fallback='').strip()
        self.config_db = {
            'host': self.config.get('FIREBIRD', 'servidor', fallback='127.0.0.1'),
            'port': self.config.get('FIREBIRD', 'porta', fallback='3050'),
            'database': self.config.get('FIREBIRD', 'caminho_banco', fallback=''),
            'user': self.config.get('FIREBIRD', 'usuario', fallback='SYSDBA'),
            'password': self.config.get('FIREBIRD', 'senha', fallback='masterkey'),
            'fbclient': self._resource_path(fbcli) if fbcli else ''
        }

        # Estado
        self.ccs = []                 # lista de dicts dos centros de custo
        self.cc_by_code = {}          # norm(codigo) -> row
        self.plano = []               # lista de dicts do plano
        self.plano_by_codigo = {}     # norm(PLANO_CODIGO) -> row
        self.plano_analiticos = []    # rows do plano com reduzido (vinculáveis)
        self.pending = {}             # norm(cc_codigo) -> {'contabil':.., 'reduzido':..}
        self.iid_to_code = {}         # iid do tree -> norm(codigo)

        self._criar_widgets()
        self.after(120, self._carregar)

    # ------------------------------------------------------------------ utils
    def _resource_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def _fechar_tela(self):
        if self.pending and not messagebox.askyesno(
                "Alterações pendentes",
                f"Há {len(self.pending)} vínculo(s) alterado(s) e não salvo(s).\n"
                "Deseja sair mesmo assim e descartar?"):
            return
        self.destroy()
        if self.callback_voltar:
            self.callback_voltar()

    def _servico(self):
        if not self.config_db['database']:
            raise RuntimeError("Banco de dados não configurado. Use 'Configurar Banco' na tela inicial.")
        return FirebirdService(self.config_db)

    # --------------------------------------------------------------- interface
    def _criar_widgets(self):
        tema.montar_header(
            self, "Vínculo Centro de Custos × Plano de Contas",
            "Vincule cada centro de custo analítico à sua conta contábil (contábil = código do plano)"
        ).pack(fill=tk.X)

        corpo = tk.Frame(self, bg=tema.BG_BASE)
        corpo.pack(fill=tk.BOTH, expand=True)

        # -------- MENU LATERAL --------
        sidebar = tema.montar_sidebar(corpo)
        rodape_sb = tk.Frame(sidebar, bg=tema.SIDEBAR_BG)
        rodape_sb.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 8))
        self.btn_voltar = tema.botao_sidebar(rodape_sb, "⎋   Voltar", self._fechar_tela)
        self.btn_voltar.pack(fill=tk.X)

        tema.titulo_sidebar(sidebar, "AÇÕES").pack(fill=tk.X, pady=(16, 4))
        self.btn_salvar = tema.botao_sidebar(sidebar, "💾   Salvar TODAS", self._salvar, cor_fg="#7EE0A0")
        self.btn_salvar.pack(fill=tk.X)
        self.btn_recarregar = tema.botao_sidebar(sidebar, "🔄   Recarregar", self._carregar)
        self.btn_recarregar.pack(fill=tk.X)
        self.btn_vincular = tema.botao_sidebar(sidebar, "🔗   Vincular selecionados", self._editar_selecionado)
        self.btn_vincular.pack(fill=tk.X)
        self.btn_limpar = tema.botao_sidebar(sidebar, "🧹   Limpar vínculo", self._limpar_selecionado, cor_fg="#FF9B9B")
        self.btn_limpar.pack(fill=tk.X)

        tk.Label(sidebar, text="Dica: segure Ctrl ou Shift\npara marcar vários e vincular\ntodos à mesma conta.",
                 bg=tema.SIDEBAR_BG, fg=tema.SIDEBAR_FG_MUTED, justify=tk.LEFT,
                 font=(tema.FONTE, 8), anchor="w", padx=18).pack(fill=tk.X, pady=(14, 0))

        # -------- CONTEÚDO --------
        content = tk.Frame(corpo, bg=tema.BG_BASE)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=16, pady=12)

        # Barra: empresa/filial/exercício
        barra = ttk.LabelFrame(content, text="Origem", padding="8")
        barra.pack(fill=tk.X)
        ttk.Label(barra, text="Empresa:").pack(side=tk.LEFT)
        self.ent_emp = ttk.Entry(barra, width=6)
        self.ent_emp.pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(barra, text="Filial:").pack(side=tk.LEFT)
        self.ent_fil = ttk.Entry(barra, width=6)
        self.ent_fil.pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(barra, text="Exercício:").pack(side=tk.LEFT)
        self.ent_exe = ttk.Entry(barra, width=8)
        self.ent_exe.pack(side=tk.LEFT, padx=(4, 12))
        self.ent_emp.insert(0, self.config.get('IMPORTACAO', 'empresa', fallback='1'))
        self.ent_fil.insert(0, self.config.get('IMPORTACAO', 'filial', fallback='1'))
        self.ent_exe.insert(0, self.config.get('IMPORTACAO', 'exercicio', fallback='2026'))
        tema.estilo_botao(barra, "📥 Carregar", self._carregar, "primary").pack(side=tk.LEFT, padx=6)

        # Barra: filtro + status
        filtro = tk.Frame(content, bg=tema.BG_BASE)
        filtro.pack(fill=tk.X, pady=(10, 4))
        tk.Label(filtro, text="🔎", bg=tema.BG_BASE).pack(side=tk.LEFT)
        self.ent_filtro = ttk.Entry(filtro, width=28)
        self.ent_filtro.pack(side=tk.LEFT, padx=(4, 14))
        self.ent_filtro.bind("<KeyRelease>", lambda e: self._render())

        self.var_status = tk.StringVar(value="todos")
        for txt, val in [("Todos", "todos"), ("Sem vínculo", "vazio"), ("Divergentes", "divergente")]:
            ttk.Radiobutton(filtro, text=txt, value=val, variable=self.var_status,
                            command=self._render).pack(side=tk.LEFT, padx=4)

        self.var_ocultar_desativados = tk.BooleanVar(value=True)
        ttk.Checkbutton(filtro, text="Ocultar desativados", variable=self.var_ocultar_desativados,
                        command=self._render).pack(side=tk.LEFT, padx=(14, 0))

        # Grade (árvore) de centros de custo
        frame_grade = tk.Frame(content, bg=tema.BG_BASE)
        frame_grade.pack(fill=tk.BOTH, expand=True)

        cols = ("reduzido", "contabil", "conta", "status")
        self.tree = ttk.Treeview(frame_grade, columns=cols, show="tree headings", height=18,
                                 selectmode="extended")
        self.tree.heading("#0", text="Centro de Custo")
        self.tree.heading("reduzido", text="Reduzido")
        self.tree.heading("contabil", text="Cód. Contábil")
        self.tree.heading("conta", text="Conta Contábil Vinculada")
        self.tree.heading("status", text="Situação")
        self.tree.column("#0", width=340, stretch=False)
        self.tree.column("reduzido", width=80, anchor=tk.CENTER, stretch=False)
        self.tree.column("contabil", width=90, anchor=tk.CENTER, stretch=False)
        self.tree.column("conta", width=320)
        self.tree.column("status", width=130, anchor=tk.CENTER, stretch=False)

        self.tree.tag_configure("grupo", background=tema.SURFACE, font=(tema.FONTE, 9, "bold"))
        self.tree.tag_configure("ok", background="white")
        self.tree.tag_configure("vazio", background=tema.WARNING_CT)
        self.tree.tag_configure("divergente", background=tema.ERROR_CT)
        self.tree.tag_configure("pendente", background=tema.BLUE_CONTAINER)

        scr = ttk.Scrollbar(frame_grade, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scr.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scr.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<Double-1>", self._on_double)
        self.tree.bind("<Return>", lambda e: self._editar_selecionado())
        self.tree.bind("<Delete>", lambda e: self._limpar_selecionado())

        # Rodapé de status
        self.lbl_status = tk.Label(content, text="Pronto.", bg=tema.BG_BASE, fg=tema.TEXT_SECOND,
                                   anchor="w", font=(tema.FONTE, 9))
        self.lbl_status.pack(fill=tk.X, pady=(6, 0))

    # ------------------------------------------------------------------ dados
    def _carregar(self):
        try:
            emp = int(self.ent_emp.get())
            fil = int(self.ent_fil.get())
            exe = int(self.ent_exe.get())
        except ValueError:
            messagebox.showerror("Erro", "Empresa, Filial e Exercício devem ser números.")
            return

        if self.pending and not messagebox.askyesno(
                "Recarregar", f"Há {len(self.pending)} alteração(ões) não salva(s). Recarregar e descartar?"):
            return

        self.emp, self.fil, self.exe = emp, fil, exe
        self.pending.clear()
        self.lbl_status.config(text="Carregando do banco...")
        self.update_idletasks()

        try:
            with self._servico() as fb:
                self.ccs = fb.query(
                    "SELECT CC_CODIGO, CC_DESCRICAO, CC_MOVIMENTO, CC_GRAU, CC_CC, "
                    "CC_CONTABIL, CC_CONTABIL_REDUZIDO, CC_DESATIVADO "
                    "FROM TABELA_CC WHERE CC_EMPRESA=? AND CC_FILIAL=? ORDER BY CC_CODIGO",
                    [emp, fil])
                self.plano = fb.query(
                    "SELECT PLANO_CODIGO, PLANO_REDUZIDO, PLANO_CONTA, PLANO_DESCRICAO, PLANO_NIVEL "
                    "FROM TABELA_PLANO WHERE PLANO_EMPRESA=? AND PLANO_FILIAL=? AND PLANO_EXERCICIO=? "
                    "ORDER BY PLANO_CONTA",
                    [emp, fil, exe])
        except Exception as e:
            self.lbl_status.config(text="Falha ao carregar.")
            messagebox.showerror("Erro de Banco", f"Não foi possível carregar os dados:\n{e}")
            return

        # Índices
        self.cc_by_code = {_norm(r['cc_codigo']): r for r in self.ccs}
        self.plano_by_codigo = {_norm(r['plano_codigo']): r for r in self.plano}
        self.plano_analiticos = [r for r in self.plano if _norm(r.get('plano_reduzido')) is not None]

        self._render()

    # ------------------------------------------------------------- lógica vínculo
    def _efetivo(self, row):
        """Retorna (contabil, reduzido) considerando alterações pendentes."""
        code = _norm(row['cc_codigo'])
        if code in self.pending:
            p = self.pending[code]
            return p['contabil'], p['reduzido']
        return row.get('cc_contabil'), row.get('cc_contabil_reduzido')

    def _situacao(self, row):
        """('ok'|'vazio'|'divergente', texto_conta, texto_reduzido)."""
        contabil, reduzido = self._efetivo(row)
        ncont = _norm(contabil)
        if ncont is None:
            return "vazio", "", ""
        prow = self.plano_by_codigo.get(ncont)
        if prow:
            return "ok", str(prow.get('plano_descricao') or ""), str(_norm(reduzido) or _norm(prow.get('plano_reduzido')) or "")
        return "divergente", f"(conta {contabil} não encontrada no plano)", str(_norm(reduzido) or "")

    def _is_analitico(self, row):
        return str(row.get('cc_movimento') or "").strip().upper() == "S"

    def _sincroniza_pending(self, code, row):
        """Se o pending virou igual ao original, remove-o de pending."""
        if code not in self.pending:
            return
        p = self.pending[code]
        if (_norm(p['contabil']), _norm(p['reduzido'])) == \
           (_norm(row.get('cc_contabil')), _norm(row.get('cc_contabil_reduzido'))):
            del self.pending[code]

    # ------------------------------------------------------------------ render
    def _render(self):
        self.tree.delete(*self.tree.get_children())
        self.iid_to_code.clear()

        filtro = self.ent_filtro.get().strip().lower()
        status_filtro = self.var_status.get()
        ocultar_desat = self.var_ocultar_desativados.get()

        modo_plano = status_filtro == "todos" and not filtro
        # modo_plano = árvore completa; senão, lista plana só de analíticos que casam

        def desativado(row):
            return str(row.get('cc_desativado') or "").strip().upper() == "S"

        if modo_plano:
            self._render_arvore(ocultar_desat)
        else:
            self._render_plano(filtro, status_filtro, ocultar_desat, desativado)

        self._atualizar_contadores()

    def _linha_valores(self, row):
        sit, conta_txt, red_txt = self._situacao(row)
        code = _norm(row['cc_codigo'])
        analitico = self._is_analitico(row)
        if not analitico:
            return ("", "", "", ""), "grupo"
        contabil, _red = self._efetivo(row)
        contabil_txt = "" if _norm(contabil) is None else str(_norm(contabil))
        icone = {"ok": "✔ vinculado", "vazio": "● sem vínculo", "divergente": "⚠ divergente"}[sit]
        pend = code in self.pending
        tag = "pendente" if pend else sit
        if pend:
            icone = "✎ " + icone
        return (red_txt, contabil_txt, conta_txt, icone), tag

    def _render_arvore(self, ocultar_desat):
        # Monta filhos por pai (CC_CC)
        filhos = {}
        raizes = []
        codes = set(self.cc_by_code.keys())
        for r in self.ccs:
            if ocultar_desat and str(r.get('cc_desativado') or "").strip().upper() == "S":
                continue
            code = _norm(r['cc_codigo'])
            pai = _norm(r.get('cc_cc'))
            if pai is None or pai == code or pai not in codes:
                raizes.append(r)
            else:
                filhos.setdefault(pai, []).append(r)

        def inserir(row, parent_iid):
            code = _norm(row['cc_codigo'])
            texto = f"{row['cc_codigo']}  {row.get('cc_descricao') or ''}"
            valores, tag = self._linha_valores(row)
            iid = self.tree.insert(parent_iid, tk.END, text=texto, values=valores, tags=(tag,), open=True)
            self.iid_to_code[iid] = code
            for ch in filhos.get(code, []):
                inserir(ch, iid)

        for r in raizes:
            inserir(r, "")

    def _render_plano(self, filtro, status_filtro, ocultar_desat, desativado):
        for r in self.ccs:
            if not self._is_analitico(r):
                continue
            if ocultar_desat and desativado(r):
                continue
            sit, _c, _rd = self._situacao(r)
            if status_filtro in ("vazio", "divergente") and sit != status_filtro:
                continue
            if filtro:
                alvo = f"{r['cc_codigo']} {r.get('cc_descricao') or ''}".lower()
                if filtro not in alvo:
                    continue
            texto = f"{r['cc_codigo']}  {r.get('cc_descricao') or ''}"
            valores, tag = self._linha_valores(r)
            iid = self.tree.insert("", tk.END, text=texto, values=valores, tags=(tag,))
            self.iid_to_code[iid] = _norm(r['cc_codigo'])

    def _atualizar_contadores(self):
        total = viculados = vazios = diverg = 0
        for r in self.ccs:
            if not self._is_analitico(r):
                continue
            total += 1
            sit, _c, _rd = self._situacao(r)
            if sit == "ok":
                viculados += 1
            elif sit == "vazio":
                vazios += 1
            else:
                diverg += 1
        self.lbl_status.config(
            text=f"Analíticos: {total}   •   ✔ vinculados: {viculados}   •   "
                 f"● sem vínculo: {vazios}   •   ⚠ divergentes: {diverg}   •   "
                 f"✎ alterações pendentes: {len(self.pending)}")

    def _atualizar_linha(self, iid):
        code = self.iid_to_code.get(iid)
        row = self.cc_by_code.get(code)
        if not row:
            return
        valores, tag = self._linha_valores(row)
        self.tree.item(iid, values=valores, tags=(tag,))
        self._atualizar_contadores()

    # ------------------------------------------------------------------ edição
    def _alvos_selecionados(self):
        """Lista de (iid, row) apenas dos analíticos entre os itens selecionados."""
        alvos = []
        for iid in self.tree.selection():
            row = self.cc_by_code.get(self.iid_to_code.get(iid))
            if row and self._is_analitico(row):
                alvos.append((iid, row))
        return alvos

    def _on_double(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        code = self.iid_to_code.get(iid)
        row = self.cc_by_code.get(code)
        if row and self._is_analitico(row):
            # Duplo-clique atua só na linha clicada (seleção individual)
            self._abrir_picker([(iid, row)])
            return "break"
        # não-analítico: deixa o comportamento padrão (expandir/recolher)

    def _editar_selecionado(self):
        alvos = self._alvos_selecionados()
        if not alvos:
            messagebox.showinfo(
                "Vínculo", "Selecione um ou mais centros de custo analíticos (de movimento).\n"
                           "Dica: segure Ctrl ou Shift para marcar vários.")
            return
        self._abrir_picker(alvos)

    def _limpar_selecionado(self):
        alvos = self._alvos_selecionados()
        if not alvos:
            return
        for iid, row in alvos:
            code = _norm(row['cc_codigo'])
            self.pending[code] = {'contabil': None, 'reduzido': None}
            self._sincroniza_pending(code, row)
            self._atualizar_linha(iid)

    def _aplicar_vinculo(self, alvos, plano_row):
        """Aplica o mesmo vínculo a todos os alvos (lista de (iid, row))."""
        for iid, row in alvos:
            code = _norm(row['cc_codigo'])
            self.pending[code] = {
                'contabil': plano_row.get('plano_codigo'),
                'reduzido': plano_row.get('plano_reduzido'),
            }
            self._sincroniza_pending(code, row)
            self._atualizar_linha(iid)
        # se foi um único alvo, avança para a próxima linha (fluxo rápido)
        if len(alvos) == 1:
            prox = self.tree.next(alvos[0][0])
            if prox:
                self.tree.selection_set(prox)
                self.tree.focus(prox)
                self.tree.see(prox)

    # ------------------------------------------------------------------ picker
    def _abrir_picker(self, alvos):
        if not alvos:
            return
        if not self.plano_analiticos:
            messagebox.showwarning("Plano vazio", "Nenhuma conta analítica do plano foi carregada para este exercício.")
            return
        # linha de referência (a primeira) para pré-seleção do vínculo atual
        ref_iid, ref_row = alvos[0]

        if len(alvos) == 1:
            subtitulo = f"CC {ref_row['cc_codigo']} — {ref_row.get('cc_descricao') or ''}"
        else:
            subtitulo = f"{len(alvos)} centros de custo selecionados serão vinculados à mesma conta"

        top = tk.Toplevel(self)
        top.title("Selecionar Conta do Plano")
        top.configure(bg=tema.BG_BASE)
        top.transient(self.winfo_toplevel())

        tema.montar_header(top, "Vincular Conta Contábil", subtitulo).pack(fill=tk.X)

        corpo = tk.Frame(top, bg=tema.BG_BASE, padx=12, pady=10)
        corpo.pack(fill=tk.BOTH, expand=True)

        linha = tk.Frame(corpo, bg=tema.BG_BASE)
        linha.pack(fill=tk.X)
        tk.Label(linha, text="Digite a conta e Enter p/ vincular  ·  Espaço p/ buscar:", bg=tema.BG_BASE).pack(side=tk.LEFT)
        ent = ttk.Entry(linha, width=40)
        ent.pack(side=tk.LEFT, padx=6, fill=tk.X, expand=True)

        grade = tk.Frame(corpo, bg=tema.BG_BASE)
        grade.pack(fill=tk.BOTH, expand=True, pady=(8, 8))
        cols = ("reduzido", "conta", "descricao")
        lst = ttk.Treeview(grade, columns=cols, show="headings", height=14)
        lst.heading("reduzido", text="Reduzido")
        lst.heading("conta", text="Conta")
        lst.heading("descricao", text="Descrição")
        lst.column("reduzido", width=80, anchor=tk.CENTER, stretch=False)
        lst.column("conta", width=150, stretch=False)
        lst.column("descricao", width=360)
        scr = ttk.Scrollbar(grade, orient=tk.VERTICAL, command=lst.yview)
        lst.configure(yscroll=scr.set)
        lst.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scr.pack(side=tk.RIGHT, fill=tk.Y)

        pl_iid = {}

        def popular(termo=""):
            lst.delete(*lst.get_children())
            pl_iid.clear()
            termo = termo.strip().lower()
            atual_cont = _norm(self._efetivo(ref_row)[0])
            sel_iid = None
            for pr in self.plano_analiticos:
                red = str(_norm(pr.get('plano_reduzido')) or "")
                conta = str(pr.get('plano_conta') or "")
                desc = str(pr.get('plano_descricao') or "")
                if termo and termo not in red.lower() and termo not in conta.lower() and termo not in desc.lower():
                    continue
                i = lst.insert("", tk.END, values=(red, conta, desc))
                pl_iid[i] = pr
                if sel_iid is None and _norm(pr.get('plano_codigo')) == atual_cont:
                    sel_iid = i
            if sel_iid:
                lst.selection_set(sel_iid)
                lst.see(sel_iid)

        def _match_exato(termo):
            """Resolve o texto digitado numa conta do plano, priorizando o REDUZIDO."""
            t = str(termo or "").strip()
            if not t:
                return None
            tn = _norm(t)
            tl = t.lower()
            # 1) Prioridade: REDUZIDO (é o que o usuário costuma digitar)
            if tn is not None:
                for pr in self.plano_analiticos:
                    if tn == _norm(pr.get('plano_reduzido')):
                        return pr
            # 2) Fallback: código contábil ou a conta formatada
            for pr in self.plano_analiticos:
                cod = _norm(pr.get('plano_codigo'))
                conta = str(pr.get('plano_conta') or "").strip()
                if (tn is not None and tn == cod) or (conta and tl == conta.lower()):
                    return pr
            return None

        def confirmar(_e=None):
            # 1) Digitou o código/reduzido/conta exato? Vincula direto (sem precisar clicar na lista)
            pr = _match_exato(ent.get())
            if pr:
                self._aplicar_vinculo(alvos, pr)
                top.destroy()
                return
            # 2) Senão, usa a seleção da lista (ou o 1º filtrado)
            sel = lst.selection()
            if not sel:
                filhos = lst.get_children()
                if not filhos:
                    messagebox.showwarning("Conta não encontrada",
                        f"Nenhuma conta corresponde a “{ent.get().strip()}”.\n"
                        "Digite o código/reduzido exato ou escolha uma na lista.", parent=top)
                    return
                sel = (filhos[0],)
            pr = pl_iid.get(sel[0])
            if pr:
                self._aplicar_vinculo(alvos, pr)
                top.destroy()

        def limpar():
            for a_iid, a_row in alvos:
                a_code = _norm(a_row['cc_codigo'])
                self.pending[a_code] = {'contabil': None, 'reduzido': None}
                self._sincroniza_pending(a_code, a_row)
                self._atualizar_linha(a_iid)
            top.destroy()

        # Espaço = dispara a busca (filtra a lista); Enter = pega o que foi digitado e vincula.
        ent.bind("<KeyRelease-space>", lambda e: popular(ent.get()))
        ent.bind("<Return>", confirmar)
        ent.bind("<Down>", lambda e: (lst.focus_set(),
                                      lst.selection_set(lst.get_children()[0]) if lst.get_children() else None))
        lst.bind("<Double-1>", confirmar)
        lst.bind("<Return>", confirmar)
        top.bind("<Escape>", lambda e: top.destroy())

        botoes = tk.Frame(corpo, bg=tema.BG_BASE)
        botoes.pack(fill=tk.X)
        tema.estilo_botao(botoes, "🔗 Vincular", confirmar, "success").pack(side=tk.LEFT)
        tema.estilo_botao(botoes, "🧹 Limpar vínculo", limpar, "accent").pack(side=tk.LEFT, padx=6)
        tema.estilo_botao(botoes, "Cancelar", top.destroy, "neutro").pack(side=tk.RIGHT)

        popular()
        tema.centralizar(top, 720, 560)
        top.grab_set()
        ent.focus_set()

    # ------------------------------------------------------------------ salvar
    def _salvar(self):
        if not self.pending:
            messagebox.showinfo("Salvar", "Nenhuma alteração pendente para salvar.")
            return
        n = len(self.pending)
        if not messagebox.askyesno("Confirmar gravação",
                                   f"Gravar {n} vínculo(s) alterado(s) no banco?"):
            return

        emp, fil, exe = self.emp, self.fil, self.exe
        itens = list(self.pending.items())

        def trabalho(cur):
            for code, p in itens:
                row = self.cc_by_code.get(code)
                cc_codigo = row['cc_codigo']
                if _norm(p['contabil']) is None:
                    cur.execute(
                        "UPDATE TABELA_CC SET CC_CONTABIL=NULL, CC_CONTABIL_REDUZIDO=NULL "
                        "WHERE CC_EMPRESA=? AND CC_FILIAL=? AND CC_CODIGO=?",
                        [emp, fil, cc_codigo])
                else:
                    cur.execute(
                        "UPDATE TABELA_CC SET CC_CONTABIL=?, CC_CONTABIL_REDUZIDO=?, "
                        "CC_CONTABIL_EMPRESA=?, CC_CONTABIL_FILIAL=?, CC_CONTABIL_EXERCICIO=? "
                        "WHERE CC_EMPRESA=? AND CC_FILIAL=? AND CC_CODIGO=?",
                        [int(_norm(p['contabil'])), int(_norm(p['reduzido'])) if _norm(p['reduzido']) is not None else None,
                         emp, fil, exe, emp, fil, cc_codigo])

        self.lbl_status.config(text="Gravando...")
        self.update_idletasks()
        try:
            with self._servico() as fb:
                fb.transaction(trabalho)
        except Exception as e:
            messagebox.showerror("Erro ao gravar", f"Falha na gravação (nada foi alterado):\n{e}")
            self.lbl_status.config(text="Falha ao gravar.")
            return

        # Aplica no cache local e limpa pendências
        for code, p in itens:
            row = self.cc_by_code.get(code)
            if row:
                row['cc_contabil'] = _norm(p['contabil'])
                row['cc_contabil_reduzido'] = _norm(p['reduzido'])
        self.pending.clear()
        self._render()
        messagebox.showinfo("Sucesso", f"{n} vínculo(s) gravado(s) com sucesso!")

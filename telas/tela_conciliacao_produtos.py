# -*- coding: utf-8 -*-
"""Conciliação Planilha × ERP (produtos).

Tela separada da importação: não grava nada, só põe lado a lado o que está na
planilha e o que está no cadastro do ERP, para conferir antes de importar.
A base é a planilha (uma linha por linha da planilha), com a opção de mostrar
também os produtos do ERP que a planilha não trouxe.
"""
import csv
import re
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from utils.firebird_service import FirebirdService
from utils import tema


class TelaConciliacaoProdutos(tk.Toplevel):
    # Sequência pedida: ERP, Excel, Importação, Auxiliar, Descrição ERP, Descrição Excel.
    COLUNAS = ("CÓDIGO ERP", "CÓDIGO EXCEL", "CÓDIGO IMPORTAÇÃO", "CÓDIGO AUXILIAR",
               "DESCRIÇÃO ERP", "DESCRIÇÃO EXCEL", "CASOU POR", "SITUAÇÃO")
    LARGURAS = (90, 110, 130, 130, 260, 260, 150, 190)
    ALINHA_ESQ = {"DESCRIÇÃO ERP", "DESCRIÇÃO EXCEL", "CASOU POR", "SITUAÇÃO"}

    FILTROS = ("TODOS", "CASADOS", "SÓ NA PLANILHA", "SÓ NO ERP",
               "DESCRIÇÃO DIFERENTE")

    def __init__(self, parent, config_db, registros, emp=1, fil=1):
        super().__init__(parent)
        self.title("Conciliação Planilha × ERP — Produtos")
        self.config_db = config_db
        self.registros = registros or []
        self.emp, self.fil = emp, fil
        self.linhas = []          # todas as linhas conciliadas
        self._ordem = (None, False)

        self.transient(parent)
        tema.centralizar(self, 1400, 720)
        self._criar_widgets()
        self._iniciar_carga()

    # ------------------------------------------------------------------ UI
    def _criar_widgets(self):
        tema.montar_header(
            self, "Conciliação Planilha × ERP",
            "Compara a planilha com o cadastro de produtos do ERP. Nada é gravado aqui."
        ).pack(fill=tk.X)

        barra = ttk.Frame(self, padding=(10, 6))
        barra.pack(fill=tk.X)

        tk.Label(barra, text="Filtro:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        self.cb_filtro = ttk.Combobox(barra, values=self.FILTROS, state="readonly",
                                      width=20, font=("Segoe UI", 9))
        self.cb_filtro.set("TODOS")
        self.cb_filtro.pack(side=tk.LEFT, padx=(4, 12))
        self.cb_filtro.bind("<<ComboboxSelected>>", lambda e: self._render())

        tk.Label(barra, text="Buscar:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        self.ent_busca = ttk.Entry(barra, width=26, font=("Segoe UI", 9))
        self.ent_busca.pack(side=tk.LEFT, padx=(4, 4))
        self.ent_busca.bind("<Return>", lambda e: self._render())
        ttk.Button(barra, text="🔍", width=3, command=self._render).pack(side=tk.LEFT)

        self.var_erp_sobrando = tk.BooleanVar(self, value=False)
        ttk.Checkbutton(barra, text="Mostrar produtos do ERP fora da planilha",
                        variable=self.var_erp_sobrando,
                        command=self._render).pack(side=tk.LEFT, padx=12)

        ttk.Button(barra, text="⬇ Exportar CSV",
                   command=self._exportar).pack(side=tk.RIGHT, padx=3)
        ttk.Button(barra, text="🔄 Recarregar do ERP",
                   command=self._iniciar_carga).pack(side=tk.RIGHT, padx=3)

        # contadores
        self.lbl_resumo = tk.Label(self, text="Lendo o ERP...", anchor=tk.W,
                                   font=("Segoe UI", 9), fg=tema.TEXT_SECOND,
                                   bg=tema.BG_BASE, padx=12)
        self.lbl_resumo.pack(fill=tk.X)

        moldura = ttk.Frame(self, padding=(10, 4))
        moldura.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(moldura, columns=self.COLUNAS, show="headings")
        for col, larg in zip(self.COLUNAS, self.LARGURAS):
            self.tree.heading(col, text=col,
                              command=lambda c=col: self._ordenar(c))
            self.tree.column(col, width=larg,
                             anchor=tk.W if col in self.ALINHA_ESQ else tk.CENTER)

        self.tree.tag_configure('CASOU', background=tema.SUCCESS_CT)
        self.tree.tag_configure('DIVERGE', background=tema.WARNING_CT)
        self.tree.tag_configure('SO_PLANILHA', background=tema.INFO_CT)
        self.tree.tag_configure('SO_ERP', background=tema.SURFACE)
        self.tree.tag_configure('AMBIGUO', background=tema.ERROR_CT)

        sy = ttk.Scrollbar(moldura, orient=tk.VERTICAL, command=self.tree.yview)
        sx = ttk.Scrollbar(moldura, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscroll=sy.set, xscroll=sx.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        moldura.rowconfigure(0, weight=1)
        moldura.columnconfigure(0, weight=1)

        rodape = ttk.Frame(self, padding=(10, 6))
        rodape.pack(fill=tk.X)
        self.lbl_status = tk.Label(rodape, text="", font=("Segoe UI", 9), fg="#555")
        self.lbl_status.pack(side=tk.LEFT)
        ttk.Button(rodape, text="Fechar", command=self.destroy).pack(side=tk.RIGHT)

    # -------------------------------------------------------------- chaves
    @staticmethod
    def _norm_cod(valor):
        """Código comparável: sem espaço, maiúsculo, sem .0 do Excel."""
        v = str(valor or '').strip().upper()
        if re.match(r'^\d+[.,]0+$', v):
            v = re.split(r'[.,]', v)[0]
        return v

    @staticmethod
    def _norm_desc(valor):
        """Descrição comparável: só letras e números (ignora espaço e pontuação)."""
        return re.sub(r'[^0-9A-ZÀ-Ú]', '', str(valor or '').upper())

    # --------------------------------------------------------------- carga
    def _iniciar_carga(self):
        self.lbl_resumo.config(text="Lendo o cadastro de produtos do ERP...")
        threading.Thread(target=self._carga_bg, daemon=True).start()

    def _carga_bg(self):
        try:
            with FirebirdService(self.config_db) as fb:
                rows = fb.query(
                    "SELECT PRODUTO_CODIGO, PRODUTO_DESCRICAO, PRODUTO_COD_IMPORTACAO, "
                    "PRODUTO_COD_AUXILIAR, PRODUTO_ATIVO FROM TABELA_PRODUTO "
                    "WHERE PRODUTO_EMPRESA = ? AND PRODUTO_FILIAL = ?",
                    [self.emp, self.fil])
        except Exception as e:
            return self.after(0, lambda err=e: (
                messagebox.showerror("Erro DB", f"Falha ao ler o ERP:\n{err}", parent=self),
                self.lbl_resumo.config(text="Falha ao ler o ERP.")))

        produtos = [{
            'codigo': self._norm_cod(r.get('produto_codigo')),
            'descricao': str(r.get('produto_descricao') or '').strip(),
            'importacao': str(r.get('produto_cod_importacao') or '').strip(),
            'auxiliar': str(r.get('produto_cod_auxiliar') or '').strip(),
            'ativo': str(r.get('produto_ativo') or '').strip().upper(),
        } for r in rows]

        linhas = self._conciliar(produtos, self.registros)
        self.after(0, lambda: self._pos_carga(linhas, len(produtos)))

    @classmethod
    def _conciliar(cls, produtos, registros):
        """Uma linha por linha da planilha + as sobras do ERP no fim.

        Casa por código do ERP, código de importação, código auxiliar e, por
        último, descrição. Guarda por que casou — o motivo é o que permite
        confiar (ou não) no vínculo.
        """
        por_codigo, por_importacao, por_auxiliar, por_desc = {}, {}, {}, {}
        for p in produtos:
            if p['codigo']:
                por_codigo.setdefault(p['codigo'], []).append(p)
            if p['importacao']:
                por_importacao.setdefault(cls._norm_cod(p['importacao']), []).append(p)
            if p['auxiliar']:
                por_auxiliar.setdefault(cls._norm_cod(p['auxiliar']), []).append(p)
            if p['descricao']:
                por_desc.setdefault(cls._norm_desc(p['descricao']), []).append(p)

        linhas, usados = [], set()
        for reg in registros:
            cod_atual = cls._norm_cod(reg.get('codigo_atual'))
            cod_antigo = cls._norm_cod(reg.get('codigo_antigo'))
            desc_plan = str(reg.get('descricao') or '').strip()
            cod_excel = cod_atual or cod_antigo

            achados, motivo = [], ''
            for chave, indice, rotulo in (
                (cod_atual, por_codigo, 'código do ERP'),
                (cod_antigo, por_codigo, 'código do ERP'),
                (cod_antigo, por_importacao, 'código de importação'),
                (cod_atual, por_importacao, 'código de importação'),
                (cod_antigo, por_auxiliar, 'código auxiliar'),
                (cod_atual, por_auxiliar, 'código auxiliar'),
            ):
                if chave and chave in indice:
                    achados, motivo = indice[chave], rotulo
                    break
            if not achados and desc_plan:
                chave_desc = cls._norm_desc(desc_plan)
                if chave_desc in por_desc:
                    achados, motivo = por_desc[chave_desc], 'descrição'

            if not achados:
                linhas.append({
                    'codigo_erp': '', 'codigo_excel': cod_excel,
                    'importacao': '', 'auxiliar': '',
                    'desc_erp': '', 'desc_excel': desc_plan,
                    'casou': '—', 'situacao': 'SÓ NA PLANILHA (será cadastrado)',
                    'tag': 'SO_PLANILHA',
                })
                continue

            p = achados[0]
            usados.add(p['codigo'])
            ambiguo = len(achados) > 1
            igual = cls._norm_desc(p['descricao']) == cls._norm_desc(desc_plan)
            if ambiguo:
                outros = ', '.join(q['codigo'] for q in achados[1:6])
                situacao = f"AMBÍGUO: também casa com {outros}"
                tag = 'AMBIGUO'
            elif not igual:
                situacao = 'DESCRIÇÃO DIFERENTE'
                tag = 'DIVERGE'
            else:
                situacao = 'CASOU'
                tag = 'CASOU'
            if p['ativo'] == 'N':
                situacao += ' • INATIVO no ERP'

            linhas.append({
                'codigo_erp': p['codigo'], 'codigo_excel': cod_excel,
                'importacao': p['importacao'], 'auxiliar': p['auxiliar'],
                'desc_erp': p['descricao'], 'desc_excel': desc_plan,
                'casou': motivo, 'situacao': situacao, 'tag': tag,
            })

        # Duas linhas da planilha apontando para o mesmo produto do ERP: é o
        # caso que gera atualização em cima de atualização, e não aparecia.
        quantas = {}
        for l in linhas:
            if l['codigo_erp']:
                quantas[l['codigo_erp']] = quantas.get(l['codigo_erp'], 0) + 1
        for l in linhas:
            n = quantas.get(l['codigo_erp'], 0)
            if n > 1:
                l['situacao'] += f" • {n} linhas da planilha apontam para este produto"
                if l['tag'] == 'CASOU':
                    l['tag'] = 'DIVERGE'

        # sobras do ERP (só aparecem se o usuário pedir)
        for p in produtos:
            if p['codigo'] in usados:
                continue
            linhas.append({
                'codigo_erp': p['codigo'], 'codigo_excel': '',
                'importacao': p['importacao'], 'auxiliar': p['auxiliar'],
                'desc_erp': p['descricao'], 'desc_excel': '',
                'casou': '—',
                'situacao': 'SÓ NO ERP' + (' • INATIVO' if p['ativo'] == 'N' else ''),
                'tag': 'SO_ERP', '_sobra_erp': True,
            })
        return linhas

    def _pos_carga(self, linhas, qtd_erp):
        self.linhas = linhas
        self._qtd_erp = qtd_erp
        self._render()

    # ------------------------------------------------------------- render
    def _visiveis(self):
        filtro = self.cb_filtro.get()
        busca = self._norm_desc(self.ent_busca.get()) if self.ent_busca.get().strip() else ''
        busca_cod = self._norm_cod(self.ent_busca.get())
        mostra_sobra = self.var_erp_sobrando.get()

        fora = []
        for l in self.linhas:
            if l.get('_sobra_erp') and not (mostra_sobra or filtro == 'SÓ NO ERP'):
                continue
            if filtro == 'CASADOS' and l['tag'] not in ('CASOU', 'DIVERGE', 'AMBIGUO'):
                continue
            if filtro == 'SÓ NA PLANILHA' and l['tag'] != 'SO_PLANILHA':
                continue
            if filtro == 'SÓ NO ERP' and l['tag'] != 'SO_ERP':
                continue
            if filtro == 'DESCRIÇÃO DIFERENTE' and l['tag'] != 'DIVERGE':
                continue
            if busca:
                alvo = self._norm_desc(l['desc_erp'] + l['desc_excel'])
                codigos = ' '.join((l['codigo_erp'], l['codigo_excel'],
                                    l['importacao'], l['auxiliar'])).upper()
                if busca not in alvo and busca_cod not in codigos:
                    continue
            fora.append(l)
        return fora

    def _valores(self, l):
        return (l['codigo_erp'], l['codigo_excel'], l['importacao'], l['auxiliar'],
                l['desc_erp'], l['desc_excel'], l['casou'], l['situacao'])

    def _render(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        linhas = self._visiveis()
        col, invertido = self._ordem
        if col:
            idx = self.COLUNAS.index(col)
            linhas = sorted(linhas, key=lambda l: self._chave_ordem(self._valores(l)[idx]),
                            reverse=invertido)
        for l in linhas:
            self.tree.insert("", tk.END, values=self._valores(l), tags=(l['tag'],))

        conta = {}
        for l in self.linhas:
            conta[l['tag']] = conta.get(l['tag'], 0) + 1
        self.lbl_resumo.config(text=(
            f"Planilha: {len(self.registros)} linha(s)  •  ERP: {getattr(self, '_qtd_erp', 0)} produto(s)"
            f"   |   ✔ casaram: {conta.get('CASOU', 0)}"
            f"   •  descrição diferente: {conta.get('DIVERGE', 0)}"
            f"   •  ambíguos: {conta.get('AMBIGUO', 0)}"
            f"   •  só na planilha: {conta.get('SO_PLANILHA', 0)}"
            f"   •  só no ERP: {conta.get('SO_ERP', 0)}"))
        self.lbl_status.config(text=f"Exibindo {len(linhas)} linha(s)")

    @staticmethod
    def _chave_ordem(valor):
        """Ordena número como número e texto como texto (vazio no fim)."""
        v = str(valor or '').strip()
        if not v:
            return (2, 0.0, '')
        try:
            return (0, float(v.replace(',', '.')), '')
        except ValueError:
            return (1, 0.0, v.upper())

    def _ordenar(self, col):
        atual, invertido = self._ordem
        self._ordem = (col, not invertido if atual == col else False)
        for c in self.COLUNAS:
            seta = ''
            if c == self._ordem[0]:
                seta = ' ▼' if self._ordem[1] else ' ▲'
            self.tree.heading(c, text=c + seta)
        self._render()

    def _exportar(self):
        linhas = self._visiveis()
        if not linhas:
            return messagebox.showinfo("Conciliação", "Nada para exportar.", parent=self)
        caminho = filedialog.asksaveasfilename(
            parent=self, defaultextension=".csv", initialfile="CONCILIACAO_PRODUTOS.csv",
            filetypes=[("CSV", "*.csv")])
        if not caminho:
            return
        try:
            with open(caminho, 'w', newline='', encoding='utf-8-sig') as f:
                w = csv.writer(f, delimiter=';')
                w.writerow(self.COLUNAS)
                for l in linhas:
                    w.writerow(self._valores(l))
        except Exception as e:
            return messagebox.showerror("Erro", f"Não foi possível salvar:\n{e}", parent=self)
        messagebox.showinfo("Conciliação", f"{len(linhas)} linha(s) exportada(s) para:\n{caminho}",
                            parent=self)

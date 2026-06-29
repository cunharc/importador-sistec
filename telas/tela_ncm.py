import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import configparser
import threading
import json
import os
import sys
import csv
import logging

from utils.xml_reader import parse_nfe_folder, parse_nfe
from utils.firebird_service import FirebirdService

logging.basicConfig(
    filename='sistema_erros.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - [NCM Sync] - %(message)s'
)

class DialogoPreviewNCM(tk.Toplevel):
    def __init__(self, parent, registros, callback_confirmar, faixas_icms=None, regras_rt=None, config_db=None, empresa='1', filial='1'):
        super().__init__(parent)
        self.title("Revisão de NCMs antes de Salvar no ERP")
        w = min(1100, int(self.winfo_screenwidth() * 0.92))
        h = min(750, int(self.winfo_screenheight() * 0.85))
        self.geometry(f"{w}x{h}")
        self.minsize(640, 480)
        self.transient(parent)
        self.grab_set()

        self.registros = registros
        self.callback_confirmar = callback_confirmar
        self.faixas_icms = faixas_icms or {}
        self.regras_rt = regras_rt or []
        self.config_db = config_db or {}
        self.empresa = empresa
        self.filial = filial
        self.item_selecionado = None
        self._ncm_atual = None

        self._build_opcoes_faixas()
        self._criar_widgets()
        self._carregar_dados()

    def _build_opcoes_faixas(self):
        self.opcoes_faixa_icms = []
        self.icms_faixa_map = {}
        icms_set = set()
        for estado, faixas in self.faixas_icms.items():
            for r in faixas:
                faixa_num = str(r.get('aicms_faixa', '')).strip()
                if not faixa_num:
                    continue
                cst = r.get('_cst_cont', '000')
                alq = r.get('_alq_cont', 0)
                opt = f"{faixa_num} - {estado} - CST {cst} - {alq}%"
                icms_set.add(opt)
        for opt in sorted(icms_set):
            self.opcoes_faixa_icms.append(opt)
            self.icms_faixa_map[opt] = opt.split(' - ')[0]

        self.opcoes_faixa_reforma = []
        self.reforma_faixa_map = {}
        for r in self.regras_rt:
            rid = str(r.get('id', '')).strip()
            rclass = str(r.get('class', '0')).strip()
            rcst = str(r.get('cst', '0')).strip()
            ribs = r.get('ibs', 0)
            rcbs = r.get('cbs', 0)
            opt = f"{rid} - Class {rclass} - CST {rcst} - IBS {ribs}% - CBS {rcbs}%"
            self.opcoes_faixa_reforma.append(opt)
            self.reforma_faixa_map[opt] = rid

    def _criar_widgets(self):
        lbl_title = tk.Label(self, text="Revise e ajuste os dados extraídos do XML antes de gravar no ERP:", font=("Segoe UI", 12, "bold"))
        lbl_title.pack(anchor=tk.W, padx=10, pady=10)

        frame_grid = ttk.Frame(self)
        frame_grid.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.colunas = ("NCM", "STATUS", "DESCRIÇÃO", "FAIXA ICMS", "FAIXA REFORMA", "CST PIS", "PIS %", "CST COF", "COFINS %")
        self.tree = ttk.Treeview(frame_grid, columns=self.colunas, show="headings", selectmode="browse")

        larguras = [80, 80, 300, 80, 80, 60, 60, 60, 60]
        for col, larg in zip(self.colunas, larguras):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=larg, anchor=tk.CENTER if col != "DESCRIÇÃO" else tk.W)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        scroll_y = ttk.Scrollbar(frame_grid, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        # Frame de Edição Manual
        frame_edicao = ttk.LabelFrame(self, text="Editar NCM Selecionado", padding="10")
        frame_edicao.pack(fill=tk.X, padx=10, pady=10)

        self.var_desc = tk.StringVar(self)
        self.var_faixa = tk.StringVar(self)
        self.var_faixa_reforma = tk.StringVar(self)
        self.var_cst_pis = tk.StringVar(self)
        self.var_pis = tk.StringVar(self)
        self.var_cst_cof = tk.StringVar(self)
        self.var_cof = tk.StringVar(self)
        self.var_st_saida = tk.StringVar(self)
        self.var_st_compra = tk.StringVar(self)

        ttk.Label(frame_edicao, text="Descrição:").grid(row=0, column=0, sticky=tk.W, padx=5)
        ttk.Entry(frame_edicao, textvariable=self.var_desc, width=50).grid(row=0, column=1, columnspan=3, sticky=tk.W, padx=5, pady=2)

        ttk.Label(frame_edicao, text="Faixa ICMS:").grid(row=1, column=0, sticky=tk.W, padx=5)
        self.cmb_faixa_icms = ttk.Combobox(frame_edicao, textvariable=self.var_faixa, values=self.opcoes_faixa_icms, width=40, state='normal')
        self.cmb_faixa_icms.grid(row=1, column=1, columnspan=2, sticky=tk.W, padx=5, pady=2)

        ttk.Label(frame_edicao, text="CST PIS:").grid(row=1, column=3, sticky=tk.E, padx=5)
        ttk.Entry(frame_edicao, textvariable=self.var_cst_pis, width=8).grid(row=1, column=4, sticky=tk.W, padx=5, pady=2)

        ttk.Label(frame_edicao, text="PIS %:").grid(row=1, column=5, sticky=tk.E, padx=5)
        ttk.Entry(frame_edicao, textvariable=self.var_pis, width=8).grid(row=1, column=6, sticky=tk.W, padx=5, pady=2)

        ttk.Label(frame_edicao, text="Faixa Reforma:").grid(row=2, column=0, sticky=tk.W, padx=5)
        self.cmb_faixa_reforma = ttk.Combobox(frame_edicao, textvariable=self.var_faixa_reforma, values=self.opcoes_faixa_reforma, width=50, state='normal')
        self.cmb_faixa_reforma.grid(row=2, column=1, columnspan=2, sticky=tk.W, padx=5, pady=2)

        ttk.Label(frame_edicao, text="CST COF:").grid(row=2, column=3, sticky=tk.E, padx=5)
        ttk.Entry(frame_edicao, textvariable=self.var_cst_cof, width=8).grid(row=2, column=4, sticky=tk.W, padx=5, pady=2)

        ttk.Label(frame_edicao, text="COFINS %:").grid(row=2, column=5, sticky=tk.E, padx=5)
        ttk.Entry(frame_edicao, textvariable=self.var_cof, width=8).grid(row=2, column=6, sticky=tk.W, padx=5, pady=2)

        ttk.Label(frame_edicao, text="ST Saída:").grid(row=3, column=0, sticky=tk.W, padx=5)
        self.cmb_st_saida = ttk.Combobox(frame_edicao, textvariable=self.var_st_saida, values=['N', 'S'], width=6, state='readonly')
        self.cmb_st_saida.grid(row=3, column=1, sticky=tk.W, padx=5, pady=2)
        self.var_st_saida.set('N')
        self.var_st_saida.trace_add('write', self._on_st_change)

        ttk.Label(frame_edicao, text="ST Compra:").grid(row=3, column=2, sticky=tk.W, padx=5)
        self.cmb_st_compra = ttk.Combobox(frame_edicao, textvariable=self.var_st_compra, values=['N', 'S'], width=6, state='readonly')
        self.cmb_st_compra.grid(row=3, column=3, sticky=tk.W, padx=5, pady=2)
        self.var_st_compra.set('N')
        self.var_st_compra.trace_add('write', self._on_st_change)

        self.btn_config_st = ttk.Button(frame_edicao, text="⚙ Configurar ST", command=self._abrir_iva_st, state=tk.DISABLED)
        self.btn_config_st.grid(row=3, column=4, padx=10)

        ttk.Button(frame_edicao, text="✔️ Aplicar Alteração na Linha", command=self._aplicar_edicao).grid(row=0, column=7, rowspan=4, padx=20)

        frame_bot = ttk.Frame(self, padding="10")
        frame_bot.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(frame_bot, text="❌ Cancelar", command=self.destroy).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_bot, text="💾 Confirmar e Salvar no ERP", command=self._confirmar).pack(side=tk.RIGHT, padx=5)

    def _carregar_dados(self):
        for i, reg in enumerate(self.registros):
            faixa_icms_display = reg.get('faixa_sugerida', '')
            faixa_reforma_display = reg.get('reforma_faixa_sugerida', '')

            # Match ICMS suggestion to a formatted option
            if faixa_icms_display and faixa_icms_display in self.icms_faixa_map:
                pass
            elif faixa_icms_display:
                for opt in self.opcoes_faixa_icms:
                    if opt.startswith(str(faixa_icms_display)):
                        faixa_icms_display = opt
                        break
                else:
                    faixa_icms_display = str(faixa_icms_display) if faixa_icms_display else '-'

            # Match Reforma suggestion to a formatted option
            if faixa_reforma_display and faixa_reforma_display in self.reforma_faixa_map:
                pass
            elif faixa_reforma_display and faixa_reforma_display != '-':
                for opt in self.opcoes_faixa_reforma:
                    if opt.startswith(str(faixa_reforma_display)):
                        faixa_reforma_display = opt
                        break
                else:
                    faixa_reforma_display = str(faixa_reforma_display) if faixa_reforma_display else '-'
            else:
                faixa_reforma_display = '-'

            reg['faixa_sugerida'] = faixa_icms_display
            reg['reforma_faixa_sugerida'] = faixa_reforma_display

            self.tree.insert("", tk.END, iid=str(i), values=(
                reg['ncm'], reg['status'], reg['descricao'], faixa_icms_display, faixa_reforma_display,
                reg['cst_pis'], reg['pis_sugerido'], reg['cst_cofins'], reg['cofins_sugerido']
            ))

    def _on_select(self, event):
        sel = self.tree.selection()
        if not sel: return
        self.item_selecionado = sel[0]
        idx = int(self.item_selecionado)
        reg = self.registros[idx]
        ncm = reg['ncm']
        self._ncm_atual = ncm

        self.var_desc.set(reg['descricao'])
        self.var_faixa.set(reg['faixa_sugerida'] if reg['faixa_sugerida'] else '')
        self.var_faixa_reforma.set(reg.get('reforma_faixa_sugerida', ''))
        self.var_cst_pis.set(reg['cst_pis'])
        self.var_pis.set(str(reg['pis_sugerido']).replace('.', ','))
        self.var_cst_cof.set(reg['cst_cofins'])
        self.var_cof.set(str(reg['cofins_sugerido']).replace('.', ','))

        st_saida = reg.get('cfis_subst_tributaria', '')
        st_compra = reg.get('cfis_st_compra', '')
        if not st_saida or st_saida not in ('S', 'N'):
            st_saida = self._buscar_st_erp(ncm, 'CFIS_SUBST_TRIBUTARIA')
        if not st_compra or st_compra not in ('S', 'N'):
            st_compra = self._buscar_st_erp(ncm, 'CFIS_ST_COMPRA')
        self.var_st_saida.set(st_saida if st_saida in ('S', 'N') else 'N')
        self.var_st_compra.set(st_compra if st_compra in ('S', 'N') else 'N')

    def _buscar_st_erp(self, ncm, campo):
        if not self.config_db or not ncm:
            return 'N'
        try:
            with FirebirdService(self.config_db) as fb:
                cursor = fb.conn.cursor()
                cursor.execute(f"SELECT {campo} FROM TABELA_class_fiscal WHERE CFIS_CODIGO=? AND CFIS_EMPRESA=? AND CFIS_FILIAL=?",
                               (ncm, self.empresa, self.filial))
                row = cursor.fetchone()
                if row and row[0] in ('S', 'N'):
                    return row[0]
        except Exception:
            pass
        return 'N'

    def _on_st_change(self, *args):
        if self.var_st_saida.get() == 'S' or self.var_st_compra.get() == 'S':
            self.btn_config_st.config(state=tk.NORMAL)
        else:
            self.btn_config_st.config(state=tk.DISABLED)

    def _abrir_iva_st(self):
        ncm = self._ncm_atual
        if not ncm:
            return messagebox.showwarning("Aviso", "Selecione um NCM primeiro.", parent=self)
        DialogoIvaSt(self, ncm, self.empresa, self.filial, self.config_db)

    def _aplicar_edicao(self):
        if not self.item_selecionado: return
        idx = int(self.item_selecionado)

        # Extract raw faixa number from formatted combobox value
        faixa_icms_val = self.var_faixa.get()
        raw_faixa = self.icms_faixa_map.get(faixa_icms_val, faixa_icms_val)

        faixa_reforma_val = self.var_faixa_reforma.get()
        raw_reforma = self.reforma_faixa_map.get(faixa_reforma_val, faixa_reforma_val)

        self.registros[idx]['descricao'] = self.var_desc.get()
        self.registros[idx]['faixa_sugerida'] = raw_faixa
        self.registros[idx]['reforma_faixa_sugerida'] = raw_reforma
        try:
            pis_val = float(self.var_pis.get().replace(',', '.'))
        except ValueError:
            pis_val = 0.0
        try:
            cof_val = float(self.var_cof.get().replace(',', '.'))
        except ValueError:
            cof_val = 0.0

        self.registros[idx]['cst_pis'] = self.var_cst_pis.get()
        self.registros[idx]['pis_sugerido'] = pis_val
        self.registros[idx]['cst_cofins'] = self.var_cst_cof.get()
        self.registros[idx]['cofins_sugerido'] = cof_val
        self.registros[idx]['cfis_subst_tributaria'] = self.var_st_saida.get()
        self.registros[idx]['cfis_st_compra'] = self.var_st_compra.get()

        self.tree.item(self.item_selecionado, values=(
            self.registros[idx]['ncm'],
            self.registros[idx]['status'],
            self.registros[idx]['descricao'],
            faixa_icms_val,
            faixa_reforma_val,
            self.registros[idx]['cst_pis'],
            str(pis_val).replace('.', ','),
            self.registros[idx]['cst_cofins'],
            str(cof_val).replace('.', ',')
        ))

    def _confirmar(self):
        # Convert all formatted faixa values to raw before returning
        for reg in self.registros:
            faixa = reg.get('faixa_sugerida', '')
            if faixa in self.icms_faixa_map:
                reg['faixa_sugerida'] = self.icms_faixa_map[faixa]
            ref = reg.get('reforma_faixa_sugerida', '')
            if ref in self.reforma_faixa_map:
                reg['reforma_faixa_sugerida'] = self.reforma_faixa_map[ref]
        self.callback_confirmar(self.registros)
        self.destroy()


class DialogoIvaSt(tk.Toplevel):
    def __init__(self, parent, ncm, empresa, filial, config_db):
        super().__init__(parent)
        self.title(f"Configuração ST - NCM {ncm}")
        w = min(900, int(self.winfo_screenwidth() * 0.85))
        h = min(650, int(self.winfo_screenheight() * 0.8))
        self.geometry(f"{w}x{h}")
        self.minsize(640, 480)
        self.transient(parent)
        self.grab_set()

        self.ncm = ncm
        self.empresa = empresa
        self.filial = filial
        self.config_db = config_db
        self.registros = []
        self._item_editando = None

        self._criar_widgets()
        self._carregar_dados()

    def _criar_widgets(self):
        ttk.Label(self, text=f"ST para NCM: {self.ncm}", font=("Segoe UI", 12, "bold")).pack(anchor=tk.W, padx=10, pady=10)

        frame_grid = ttk.Frame(self)
        frame_grid.pack(fill=tk.BOTH, expand=True, padx=10)

        colunas = ("UF", "DATA", "IVA%", "ALIQ ICMS INT%", "RED ICMS INT%", "FCP", "RED ICMS PRÓPRIO%", "REAJ", "OBS")
        self.tree = ttk.Treeview(frame_grid, columns=colunas, show="headings", selectmode="browse")
        largs = [50, 90, 70, 100, 100, 50, 120, 50, 150]
        for col, larg in zip(colunas, largs):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=larg, anchor=tk.CENTER if col != "OBS" else tk.W)

        scroll_y = ttk.Scrollbar(frame_grid, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        frame_btn = ttk.Frame(self, padding=10)
        frame_btn.pack(fill=tk.X)
        ttk.Button(frame_btn, text="➕ Novo", command=self._novo).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_btn, text="✏️ Editar", command=self._editar).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_btn, text="🗑️ Excluir", command=self._excluir).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_btn, text="Fechar", command=self.destroy).pack(side=tk.RIGHT, padx=5)

        frame_form = ttk.LabelFrame(self, text="Dados ST", padding=10)
        frame_form.pack(fill=tk.X, padx=10, pady=5)

        self.var_uf = tk.StringVar(self)
        self.var_data = tk.StringVar(self)
        self.var_iva = tk.StringVar(self)
        self.var_aliq_int = tk.StringVar(self)
        self.var_red_int = tk.StringVar(self)
        self.var_fcp = tk.StringVar(self)
        self.var_red_proprio = tk.StringVar(self)
        self.var_reaj = tk.StringVar(self)
        self.var_obs = tk.StringVar(self)

        row = 0
        ttk.Label(frame_form, text="UF:").grid(row=row, column=0, sticky=tk.W, padx=5)
        ttk.Entry(frame_form, textvariable=self.var_uf, width=6).grid(row=row, column=1, sticky=tk.W, padx=5)
        ttk.Label(frame_form, text="Data:").grid(row=row, column=2, sticky=tk.W, padx=5)
        ttk.Entry(frame_form, textvariable=self.var_data, width=12).grid(row=row, column=3, sticky=tk.W, padx=5)
        ttk.Label(frame_form, text="IVA%:").grid(row=row, column=4, sticky=tk.W, padx=5)
        ttk.Entry(frame_form, textvariable=self.var_iva, width=8).grid(row=row, column=5, sticky=tk.W, padx=5)
        ttk.Label(frame_form, text="Aliq ICMS Int%:").grid(row=row, column=6, sticky=tk.W, padx=5)
        ttk.Entry(frame_form, textvariable=self.var_aliq_int, width=8).grid(row=row, column=7, sticky=tk.W, padx=5)

        row = 1
        ttk.Label(frame_form, text="Red ICMS Int%:").grid(row=row, column=0, sticky=tk.W, padx=5)
        ttk.Entry(frame_form, textvariable=self.var_red_int, width=8).grid(row=row, column=1, sticky=tk.W, padx=5)
        ttk.Label(frame_form, text="FCP:").grid(row=row, column=2, sticky=tk.W, padx=5)
        self.cmb_fcp = ttk.Combobox(frame_form, textvariable=self.var_fcp, values=['N', 'S'], width=6, state='readonly')
        self.cmb_fcp.grid(row=row, column=3, sticky=tk.W, padx=5)
        self.var_fcp.set('N')
        ttk.Label(frame_form, text="Red ICMS Próprio%:").grid(row=row, column=4, sticky=tk.W, padx=5)
        ttk.Entry(frame_form, textvariable=self.var_red_proprio, width=8).grid(row=row, column=5, sticky=tk.W, padx=5)
        ttk.Label(frame_form, text="Reajustado:").grid(row=row, column=6, sticky=tk.W, padx=5)
        self.cmb_reaj = ttk.Combobox(frame_form, textvariable=self.var_reaj, values=['N', 'S'], width=6, state='readonly')
        self.cmb_reaj.grid(row=row, column=7, sticky=tk.W, padx=5)
        self.var_reaj.set('N')

        row = 2
        ttk.Label(frame_form, text="Obs:").grid(row=row, column=0, sticky=tk.W, padx=5)
        ttk.Entry(frame_form, textvariable=self.var_obs, width=50).grid(row=row, column=1, columnspan=5, sticky=tk.W, padx=5)
        ttk.Button(frame_form, text="💾 Salvar", command=self._salvar_registro).grid(row=row, column=6, columnspan=2, padx=10)

    def _carregar_dados(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.registros.clear()
        try:
            with FirebirdService(self.config_db) as fb:
                cursor = fb.conn.cursor()
                cursor.execute("""
                    SELECT ST_UF, ST_DATA, ST_IVA, ST_ALIQUOTA_ICMS_INT, ST_REDUICAO_ICMS_INT,
                           ST_ST_FCB, ST_REDUCAO_ICMS_PROPRIO, ST_REAJUSTADO, ST_OBS
                    FROM TABELA_CLASSIF_FISCAL_IVA_ST
                    WHERE ST_CLASSIF_FISCAL=? AND ST_EMPRESA=? AND ST_FILIAL=?
                    ORDER BY ST_UF, ST_DATA
                """, (self.ncm, self.empresa, self.filial))
                for row in cursor.fetchall():
                    self.registros.append(dict(zip(
                        ('uf', 'data', 'iva', 'aliq_int', 'red_int', 'fcp', 'red_proprio', 'reaj', 'obs'),
                        [str(v) if v is not None else '' for v in row]
                    )))
                    self.tree.insert("", tk.END, values=row)
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao carregar ST: {e}", parent=self)

    def _on_select(self, event):
        sel = self.tree.selection()
        if not sel:
            self._limpar_form()
            return
        idx = int(self.tree.index(sel[0]))
        self._item_editando = idx
        r = self.registros[idx]
        self.var_uf.set(r['uf'])
        self.var_data.set(r['data'])
        self.var_iva.set(r['iva'])
        self.var_aliq_int.set(r['aliq_int'])
        self.var_red_int.set(r['red_int'])
        self.var_fcp.set(r['fcp'] if r['fcp'] in ('S', 'N') else 'N')
        self.var_red_proprio.set(r['red_proprio'])
        self.var_reaj.set(r['reaj'] if r['reaj'] in ('S', 'N') else 'N')
        self.var_obs.set(r['obs'])

    def _limpar_form(self):
        self._item_editando = None
        self.var_uf.set('')
        self.var_data.set('')
        self.var_iva.set('')
        self.var_aliq_int.set('')
        self.var_red_int.set('')
        self.var_fcp.set('N')
        self.var_red_proprio.set('')
        self.var_reaj.set('N')
        self.var_obs.set('')

    def _salvar_registro(self):
        uf = self.var_uf.get().strip().upper()
        data = self.var_data.get().strip()
        if not uf or not data:
            return messagebox.showwarning("Validação", "UF e Data são obrigatórios.", parent=self)

        iva = self._float_ou_null(self.var_iva.get())
        aliq_int = self._float_ou_null(self.var_aliq_int.get())
        red_int = self._float_ou_null(self.var_red_int.get())
        red_proprio = self._float_ou_null(self.var_red_proprio.get())
        fcp = self.var_fcp.get() if self.var_fcp.get() in ('S', 'N') else 'N'
        reaj = self.var_reaj.get() if self.var_reaj.get() in ('S', 'N') else 'N'
        obs = self.var_obs.get().strip() or None

        try:
            with FirebirdService(self.config_db) as fb:
                cursor = fb.conn.cursor()
                cursor.execute("""
                    UPDATE OR INSERT INTO TABELA_CLASSIF_FISCAL_IVA_ST
                    (ST_CLASSIF_FISCAL, ST_EMPRESA, ST_FILIAL, ST_UF, ST_DATA,
                     ST_IVA, ST_ALIQUOTA_ICMS_INT, ST_REDUICAO_ICMS_INT,
                     ST_ST_FCB, ST_REDUCAO_ICMS_PROPRIO, ST_REAJUSTADO, ST_OBS)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    MATCHING (ST_CLASSIF_FISCAL, ST_EMPRESA, ST_FILIAL, ST_UF, ST_DATA)
                """, (self.ncm, self.empresa, self.filial, uf, data,
                      iva, aliq_int, red_int, fcp, red_proprio, reaj, obs))
                fb.conn.commit()
            self._carregar_dados()
            self._limpar_form()
            messagebox.showinfo("Sucesso", "Registro ST salvo!", parent=self)
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao salvar ST: {e}", parent=self)

    def _novo(self):
        self._limpar_form()

    def _editar(self):
        if self._item_editando is None:
            messagebox.showwarning("Aviso", "Selecione um registro na lista.", parent=self)
            return
        r = self.registros[self._item_editando]
        self.var_uf.set(r['uf'])
        self.var_data.set(r['data'])
        self.var_iva.set(r['iva'])
        self.var_aliq_int.set(r['aliq_int'])
        self.var_red_int.set(r['red_int'])
        self.var_fcp.set(r['fcp'] if r['fcp'] in ('S', 'N') else 'N')
        self.var_red_proprio.set(r['red_proprio'])
        self.var_reaj.set(r['reaj'] if r['reaj'] in ('S', 'N') else 'N')
        self.var_obs.set(r['obs'])

    def _excluir(self):
        sel = self.tree.selection()
        if not sel:
            return messagebox.showwarning("Aviso", "Selecione um registro na lista.", parent=self)
        idx = int(self.tree.index(sel[0]))
        r = self.registros[idx]
        if not messagebox.askyesno("Confirmar", f"Excluir ST para UF {r['uf']} data {r['data']}?", parent=self):
            return
        try:
            with FirebirdService(self.config_db) as fb:
                cursor = fb.conn.cursor()
                cursor.execute("""
                    DELETE FROM TABELA_CLASSIF_FISCAL_IVA_ST
                    WHERE ST_CLASSIF_FISCAL=? AND ST_EMPRESA=? AND ST_FILIAL=? AND ST_UF=? AND ST_DATA=?
                """, (self.ncm, self.empresa, self.filial, r['uf'], r['data']))
                fb.conn.commit()
            self._carregar_dados()
            self._limpar_form()
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao excluir: {e}", parent=self)

    @staticmethod
    def _float_ou_null(val):
        if val is None or not str(val).strip():
            return None
        try:
            return float(str(val).replace(',', '.'))
        except ValueError:
            return None


class TelaNcm(ttk.Frame):
    def __init__(self, parent, callback_voltar=None):
        super().__init__(parent, padding="10")
        self.parent = parent
        self.callback_voltar = callback_voltar
        self.pack(fill=tk.BOTH, expand=True)

        self.arquivos_selecionados = []
        self.pasta_xmls = ""
        self.dados_sistema = {}
        self.faixas_icms = {}
        self.dados_agrupados = []
        self.dados_grid = {}
        self.valores_tree = []
        self.selecionados_lote = []
        self.cancel_event = threading.Event()
        self.edit_mode_enabled = True
        self.analysis_thread = None
        self.config = configparser.ConfigParser()
        self.config.read('config.ini', encoding='utf-8')
        self.config_db = {
            'host': self.config.get('FIREBIRD', 'servidor', fallback='127.0.0.1'),
            'port': self.config.get('FIREBIRD', 'porta', fallback='3050'),
            'database': self.config.get('FIREBIRD', 'caminho_banco', fallback=''),
            'user': self.config.get('FIREBIRD', 'usuario', fallback='SYSDBA'),
            'password': self.config.get('FIREBIRD', 'senha', fallback='masterkey'),
            'fbclient': self.config.get('FIREBIRD', 'fbclient', fallback='')
        }

        self._criar_widgets()

    def resource_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def _criar_widgets(self):
        lbl_title = tk.Label(self, text="ANÁLISE DE TRIBUTAÇÃO POR NCM", font=("Segoe UI", 14, "bold"), fg="#2980B9")
        lbl_title.pack(anchor=tk.W, pady=(0, 10))

        frame_escopo = ttk.LabelFrame(self, text="Escopo da Análise", padding="10")
        frame_escopo.pack(fill=tk.X, pady=5)

        self.var_escopo = tk.StringVar(self, value="FILIAL_ATUAL")

        rb_filial = ttk.Radiobutton(frame_escopo, text="Apenas Filial Atual", variable=self.var_escopo, value="FILIAL_ATUAL", command=self._on_escopo_change)
        rb_filial.pack(side=tk.LEFT, padx=10)

        rb_unificado = ttk.Radiobutton(frame_escopo, text="Unificar Todas as Filiais da Empresa", variable=self.var_escopo, value="UNIFICADO", command=self._on_escopo_change)
        rb_unificado.pack(side=tk.LEFT, padx=10)

        frame_dir = ttk.Frame(self)
        frame_dir.pack(fill=tk.X, pady=10)
        
        self.ent_pasta = ttk.Entry(frame_dir, width=60)
        self.ent_pasta.pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_dir, text="📁 Pasta", command=self._selecionar_pasta).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_dir, text="📄 Arquivos", command=self._selecionar_arquivos).pack(side=tk.LEFT, padx=2)
        
        self.btn_analisar = ttk.Button(frame_dir, text="🔍 Analisar NCMs", command=self._iniciar_analise)
        self.btn_analisar.pack(side=tk.RIGHT, padx=5)

        self.btn_cancelar = ttk.Button(frame_dir, text="✖ Cancelar", command=self._cancelar_analise, state=tk.DISABLED)
        self.btn_cancelar.pack(side=tk.RIGHT, padx=5)

        self.btn_sincronizar = tk.Button(
            frame_dir, text="🔄 Sincronizar NCMs Gov.", 
            font=("Segoe UI", 9, "bold"), bg="#8E44AD", fg="#FFFFFF", 
            cursor="hand2", padx=10, command=self._sincronizar_ncm_erp
        )
        self.btn_sincronizar.pack(side=tk.RIGHT, padx=5)

        self.progresso = ttk.Progressbar(frame_dir, orient=tk.HORIZONTAL, mode='determinate', length=200)
        self.progresso.pack(side=tk.RIGHT, padx=10)

        # Dashboard Cards
        self.frame_cards = tk.Frame(self, pady=5)
        self.frame_cards.pack(fill=tk.X)
        
        self.card_vermelho = self._criar_card(
            self.frame_cards, "🔴 NOVOS (PENDENTES)", "0", 
            "#FFF1F0", "#CF1322", "#F5222D", 
            lambda e: self._filtrar_por_card("NOVO")
        )
        self.card_vermelho.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        self.card_amarelo = self._criar_card(
            self.frame_cards, "🟡 DIVERGENTES (ATENÇÃO)", "0", 
            "#FFFBE6", "#D48806", "#FAAD14", 
            lambda e: self._filtrar_por_card("DIFERENTE")
        )
        self.card_amarelo.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)
        
        self.card_verde = self._criar_card(
            self.frame_cards, "🟢 VALIDADOS (OK)", "0", 
            "#F6FFED", "#389E0D", "#52C41A", 
            lambda e: self._filtrar_por_card("OK")
        )
        self.card_verde.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))

        frame_filtro = ttk.Frame(self)
        frame_filtro.pack(fill=tk.X, pady=(5, 10))

        self.var_filtro = tk.StringVar(self)
        self.var_filtro_ncm = tk.StringVar(self)
        self.var_filtro_uf = tk.StringVar(self)
        self.var_filtro_cfop = tk.StringVar(self)
        self.var_status_filtro = tk.StringVar(self, value="Todos")

        ttk.Label(frame_filtro, text="Buscar:").pack(side=tk.LEFT, padx=(0, 5))
        self.ent_filtro = ttk.Entry(frame_filtro, textvariable=self.var_filtro, width=20)
        self.ent_filtro.pack(side=tk.LEFT, padx=(0, 5))
        self.ent_filtro.bind('<KeyRelease>', lambda event: self._filtrar_treeview())

        ttk.Label(frame_filtro, text="NCM:").pack(side=tk.LEFT, padx=(10, 5))
        self.ent_filtro_ncm = ttk.Entry(frame_filtro, textvariable=self.var_filtro_ncm, width=12)
        self.ent_filtro_ncm.pack(side=tk.LEFT, padx=(0, 5))
        self.ent_filtro_ncm.bind('<KeyRelease>', lambda event: self._filtrar_treeview())

        ttk.Label(frame_filtro, text="UF:").pack(side=tk.LEFT, padx=(10, 5))
        self.ent_filtro_uf = ttk.Entry(frame_filtro, textvariable=self.var_filtro_uf, width=6)
        self.ent_filtro_uf.pack(side=tk.LEFT, padx=(0, 5))
        self.ent_filtro_uf.bind('<KeyRelease>', lambda event: self._filtrar_treeview())

        ttk.Label(frame_filtro, text="CFOP:").pack(side=tk.LEFT, padx=(10, 5))
        self.ent_filtro_cfop = ttk.Entry(frame_filtro, textvariable=self.var_filtro_cfop, width=8)
        self.ent_filtro_cfop.pack(side=tk.LEFT, padx=(0, 5))
        self.ent_filtro_cfop.bind('<KeyRelease>', lambda event: self._filtrar_treeview())

        ttk.Label(frame_filtro, text="Status:").pack(side=tk.LEFT, padx=(10, 5))
        self.cmb_status_filtro = ttk.Combobox(frame_filtro, textvariable=self.var_status_filtro, values=["Todos", "NOVO", "DIFERENTE", "OK"], state="readonly", width=10)
        self.cmb_status_filtro.pack(side=tk.LEFT, padx=(0, 5))
        self.cmb_status_filtro.bind('<<ComboboxSelected>>', lambda event: self._filtrar_treeview())

        ttk.Button(frame_filtro, text="Limpar filtro", command=self._limpar_filtro).pack(side=tk.LEFT, padx=(10, 0))

        self.lbl_status = ttk.Label(self, text="Aguardando arquivos...", font=("Segoe UI", 9))
        self.lbl_status.pack(anchor=tk.W, padx=10)

        frame_grade = ttk.Frame(self)
        frame_grade.pack(fill=tk.BOTH, expand=True, pady=5)

        colunas = ("SEL", "QTD", "NCM", "STATUS", "DESCRIÇÃO", "UF", "CFOP", "TIPO", 
                   "CST ICMS", "ICMS%", "RED.BC%", "FCP%", "MVA ST%", "ICMS ST%",
                   "CBENEF", "C.CRED", "P.CRED",
                   "CST PIS", "PIS%", "PIS% ERP",
                   "CST COF", "COF%", "COF% ERP",
                   "C. CLASSE RT", "CST RT", "IBS%", "CBS%",
                   "FAIXA ICMS", "FAIXA ERP", "REGRA RT ERP")

        self._sort_directions = {col: False for col in colunas}
        self.tree = ttk.Treeview(frame_grade, columns=colunas, show="headings", height=10)
        
        larguras = [40, 40, 80, 80, 200, 40, 50, 45,
                    70, 60, 60, 50, 60, 70,
                    80, 70, 60,
                    60, 60, 60,
                    60, 60, 60,
                    90, 60, 50, 50,
                    80, 80, 90]
        
        for col, larg in zip(colunas, larguras):
            self.tree.heading(col, text=col + " ↕", command=lambda c=col: self._sort_treeview(c))
            anchor = tk.W if col in ("DESCRIÇÃO",) else tk.CENTER
            self.tree.column(col, width=larg, anchor=anchor)

        self.tree.tag_configure('NOVO', background='#EAFAF1', foreground='#1E8449') 
        self.tree.tag_configure('DIFERENTE', background='#FEF9E7', foreground='#D35400')
        self.tree.tag_configure('MULTIPLOS', background='#FDEDEC', foreground='#C0392B')
        self.tree.tag_configure('OK', background='#FFFFFF', foreground='black')

        scroll_y = ttk.Scrollbar(frame_grade, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.tree.bind("<Button-1>", self._on_tree_click)

        frame_botoes = ttk.Frame(self)
        frame_botoes.pack(fill=tk.X, pady=5)
        
        ttk.Button(frame_botoes, text="☑ Selecionar Todos", command=self._selecionar_todos).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_botoes, text="☐ Desmarcar Todos", command=self._desmarcar_todos).pack(side=tk.LEFT, padx=2)
        
        self.btn_sinc_lote = tk.Button(
            frame_botoes, text="✨ Iniciar Assistente (Sincronizar Selecionados)", font=("Segoe UI", 10, "bold"),
            bg="#27AE60", fg="#FFFFFF", cursor="hand2", state=tk.DISABLED, command=self._sincronizar_lote, padx=10, pady=5
        )
        self.btn_sinc_lote.pack(side=tk.RIGHT, padx=5)

        frame_fim = ttk.Frame(self)
        frame_fim.pack(fill=tk.X, pady=10)
        ttk.Button(frame_fim, text="⬅ VOLTAR", command=self._fechar_tela).pack(side=tk.LEFT, padx=5)
        
        self.btn_exportar = ttk.Button(frame_fim, text="📋 Exportar CSV", state=tk.DISABLED, command=self._exportar_csv)
        self.btn_exportar.pack(side=tk.RIGHT, padx=5)

    def _criar_card(self, parent, titulo, valor_inicial, bg_color, border_color, text_color, command):
        card = tk.Frame(parent, bg=bg_color, highlightbackground=border_color, highlightthickness=1, padx=15, pady=10, cursor="hand2")
        lbl_titulo = tk.Label(card, text=titulo, font=("Segoe UI", 10, "bold"), bg=bg_color, fg=text_color, cursor="hand2")
        lbl_titulo.pack(anchor=tk.W)
        lbl_valor = tk.Label(card, text=valor_inicial, font=("Segoe UI", 24, "bold"), bg=bg_color, fg=text_color, cursor="hand2")
        lbl_valor.pack(anchor=tk.W, pady=(0, 0))
        card.lbl_valor = lbl_valor 
        for widget in (card, lbl_titulo, lbl_valor):
            widget.bind("<Button-1>", command)
        return card

    def _filtrar_por_card(self, status_selecionado):
        self.card_vermelho.config(highlightthickness=3 if status_selecionado == "NOVO" else 1)
        self.card_amarelo.config(highlightthickness=3 if status_selecionado == "DIFERENTE" else 1)
        self.card_verde.config(highlightthickness=3 if status_selecionado == "OK" else 1)
        
        self.var_status_filtro.set(status_selecionado)
        self._filtrar_treeview()

    def _atualizar_contadores(self):
        if not hasattr(self, 'valores_tree'): return
        novos = sum(1 for v, tag, g in self.valores_tree if v[3].startswith("NOVO"))
        diferentes = sum(1 for v, tag, g in self.valores_tree if v[3].startswith("DIFERENTE"))
        ok = sum(1 for v, tag, g in self.valores_tree if v[3] == "OK")
        
        if hasattr(self, 'card_vermelho'):
            self.card_vermelho.lbl_valor.config(text=str(novos))
            self.card_amarelo.lbl_valor.config(text=str(diferentes))
            self.card_verde.lbl_valor.config(text=str(ok))

    def _atualizar_progresso(self, valor, texto):
        if hasattr(self, 'progresso'):
            self.progresso['value'] = valor
        self.lbl_status.config(text=texto)

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
            
        for c in self._sort_directions:
            if c == col:
                arrow = " ▼" if self._sort_directions[c] else " ▲"
            else:
                arrow = " ↕"
            self.tree.heading(c, text=c + arrow, command=lambda x=c: self._sort_treeview(x))

    def _formatar_cst(self, valor):
        if not valor: return ''
        return str(valor).zfill(2)

    def _on_escopo_change(self):
        if self.var_escopo.get() == "UNIFICADO":
            self.edit_mode_enabled = False
            self.btn_sinc_lote.config(state=tk.DISABLED)
            messagebox.showinfo("Modo Unificado", "No modo unificado, a visualização é consolidada para toda a empresa.\n\nA edição e sincronização de NCMs são desabilitadas.", parent=self)
        else:
            self.edit_mode_enabled = True
            self._atualizar_selecionados()

    def _get_distinct_from_list(self, lista_de_dicionarios, chave):
        s = set(str(d.get(chave, '')).strip() for d in lista_de_dicionarios if d.get(chave) is not None and str(d.get(chave, '')).strip() != "")
        if not s: return "-"
        if len(s) == 1: return list(s)[0]
        try:
            lst = sorted(list(s), key=float)
        except ValueError:
            lst = sorted(list(s))
        return " / ".join(map(str, lst)) if len(lst) <= 3 else "*VÁRIOS*"

    def _extrair_float(self, valor_str):
        import re
        v = str(valor_str).replace('%', '').strip()
        try:
            return float(v)
        except ValueError:
            m = re.search(r'\d+(\.\d+)?', v)
            return float(m.group()) if m else 0.0

    def _extrair_cst(self, valor_str):
        v = str(valor_str).split(' / ')[0].replace('*VÁRIOS*', '00').strip()
        return self._formatar_cst(v)[:2] if v and v != '-' else ''

    def _selecionar_pasta(self):
        pasta = filedialog.askdirectory()
        if pasta:
            self.ent_pasta.delete(0, tk.END); self.ent_pasta.insert(0, pasta)
            self.pasta_xmls = pasta; self.arquivos_selecionados = []

    def _selecionar_arquivos(self):
        arquivos = filedialog.askopenfilenames(filetypes=[("XML", "*.xml")])
        if arquivos:
            self.ent_pasta.delete(0, tk.END); self.ent_pasta.insert(0, f"{len(arquivos)} arquivo(s)")
            self.arquivos_selecionados = list(arquivos); self.pasta_xmls = ""

    def _fechar_tela(self):
        if self.winfo_manager():
            self.pack_forget()
        # Se o usuário voltar de tela com uma leitura rolando, mata o thread interno
        if hasattr(self, 'cancel_event'):
            self.cancel_event.set()
        self.destroy()
        if self.callback_voltar: 
            self.callback_voltar()

    def _carregar_faixas_icms(self, escopo="FILIAL_ATUAL"):
        empresa = self.config.get('IMPORTACAO', 'empresa', fallback='1')
        filial = self.config.get('IMPORTACAO', 'filial', fallback='1')

        try:
            with FirebirdService(self.config_db) as fb:
                sql = """SELECT t1.AICMS_FAIXA, t1.AICMS_ESTADO, t1.AICMS_ALIQUOTA_CONT, t1.AICMS_REDUCAO_CONT,
                         t1.AICMS_SITUACAO_CONT, t1.AICMS_CBENEF_CONT, t1.AICMS_ALIQUOTA_NCONT, t1.AICMS_REDUCAO_NCONT,
                         t1.AICMS_SITUACAO_NCONT, t1.AICMS_CBENEF_NCONT, t1.AICMS_ALIQUOTA_SIMP_NAC, t1.AICMS_REDUCAO_SIMP_NAC,
                         t1.AICMS_SITUACAO_SIMP_NAC,
                         t1.AICMS_CBENEF_SIMP_NAC, t3.CBE_C_CREDPRESUMIDO, t3.CBE_P_CREDPRESUMIDO
                         FROM TABELA_ALIQUOTA_ICMS t1
                         LEFT JOIN TABELA_ALIQUOTA_ICMS_CBENEF t2 ON 
                             t1.AICMS_EMPRESA = t2.TACB_AICMS_EMPRESA AND 
                             t1.AICMS_FILIAL = t2.TACB_AICMS_FILIAL AND 
                             t1.AICMS_DATA = t2.TACB_AICMS_DATA AND 
                             t1.AICMS_FAIXA = t2.TACB_AICMS_FAIXA AND 
                             t1.AICMS_ESTADO = t2.TACB_AICMS_ESTADO
                         LEFT JOIN TABELA_CBENEF t3 ON t2.TACB_CBE_ID = t3.CBE_ID"""
                raw_faixas = fb.query(sql, [])
                
                params = []
                where_clauses = []
                if escopo == "FILIAL_ATUAL":
                    where_clauses.append("t1.AICMS_EMPRESA = ? AND t1.AICMS_FILIAL = ?")
                    params.extend([empresa, filial])
                else: # UNIFICADO
                    where_clauses.append("t1.AICMS_EMPRESA = ?")
                    params.append(empresa)
                
                sql += " WHERE " + " AND ".join(where_clauses)
                raw_faixas = fb.query(sql, params)
                
                self.faixas_icms = {}
                for r in raw_faixas:
                    est = str(r.get('aicms_estado') or '').strip().upper()
                    if est not in self.faixas_icms:
                        self.faixas_icms[est] = []
                    
                    r['_cst_cont'] = str(r.get('aicms_situacao_cont') or '').replace('.','').lstrip('0').zfill(3)
                    r['_cbenef_cont'] = str(r.get('aicms_cbenef_cont') or '').strip().upper()
                    r['_alq_cont'] = float(r.get('aicms_aliquota_cont') or 0)
                    r['_red_cont'] = float(r.get('aicms_reducao_cont') or 0)
                    
                    r['_cst_ncont'] = str(r.get('aicms_situacao_ncont') or '').replace('.','').lstrip('0').zfill(3)
                    r['_cbenef_ncont'] = str(r.get('aicms_cbenef_ncont') or '').strip().upper()
                    r['_alq_ncont'] = float(r.get('aicms_aliquota_ncont') or 0)
                    r['_red_ncont'] = float(r.get('aicms_reducao_ncont') or 0)
                    
                    r['_cst_sn'] = str(r.get('aicms_situacao_simp_nac') or '').replace('.','').lstrip('0').zfill(3)
                    r['_cbenef_sn'] = str(r.get('aicms_cbenef_simp_nac') or '').strip().upper()
                    r['_alq_sn'] = float(r.get('aicms_aliquota_simp_nac') or 0)
                    r['_red_sn'] = float(r.get('aicms_reducao_simp_nac') or 0)
                    
                    r['_dccred'] = str(r.get('cbe_c_credpresumido') or '').strip().upper()
                    r['_dpcred'] = float(r.get('cbe_p_credpresumido') or 0)
                    
                    self.faixas_icms[est].append(r)
        except Exception as e:
            logging.error(f"Erro ao carregar faixas ICMS: {e}")
            self.faixas_icms = {}

    def _buscar_faixa_para_ncm(self, grupo):
        """Busca faixa no banco baseada em cbenef + gcred + UF + CST."""
        uf_dest = str(grupo.get('uf_dest') or '').strip().upper()
        faixas_estado = self.faixas_icms.get(uf_dest, [])
        if not faixas_estado: return None
        
        ncm = grupo.get('ncm', '')
        cbenef = str(grupo.get('c_benef') or '').strip().upper()
        c_cred = str(grupo.get('c_cred') or '').strip().upper()
        p_cred = float(grupo.get('p_cred') or 0)
        tipo_cli = grupo.get('tipo_cliente', 'CT')
        icms_cst = str(grupo.get('icms_cst') or '').replace('.','').lstrip('0').zfill(3)
        p_icms = float(grupo.get('p_icms') or 0)
        p_red = float(grupo.get('p_red_bc') or 0)
        
        faixas_encontradas = set()
        
        for r in faixas_estado:
            if tipo_cli == 'NC':
                dcst, dcbenef, daliquota = r['_cst_ncont'], r['_cbenef_ncont'], r['_alq_ncont']
            elif tipo_cli == 'SN':
                dcst, dcbenef, daliquota = r['_cst_sn'], r['_cbenef_sn'], r['_alq_ncont']
            else:
                dcst, dcbenef, daliquota = r['_cst_cont'], r['_cbenef_cont'], r['_alq_cont']
            
            dccred, dpcred = r['_dccred'], r['_dpcred']
            
            cbenef_match = cbenef and cbenef in [dcbenef] if dcbenef else False
            gcred_match = c_cred and c_cred == dccred and abs(p_cred - dpcred) < 0.01
            
            if (dcst == icms_cst and abs(daliquota - p_icms) < 0.01 and 
                (cbenef_match or gcred_match or (not cbenef and not c_cred))):
                faixas_encontradas.add(str(r.get('aicms_faixa')))
        
        if faixas_encontradas:
            return sorted(list(faixas_encontradas), key=lambda x: int(x) if x.isdigit() else x)[0]
        return None

    def _buscar_regra_rt(self, grupo):
        xclass = str(grupo.get('c_class_trib', '')).strip().lstrip('0')
        if not xclass: xclass = '0'
        xcst = str(grupo.get('ibscbs_cst', '')).strip().lstrip('0')
        if not xcst: xcst = '0'
        xibs = float(grupo.get('p_ibs_uf') or 0)
        xcbs = float(grupo.get('p_cbs') or 0)
        
        matches = set()
        for r in getattr(self, 'regras_rt', []):
            if r['class'] == xclass and r['cst'] == xcst and abs(r['ibs'] - xibs) < 0.01 and abs(r['cbs'] - xcbs) < 0.01:
                matches.add(r['id'])
                
        return ", ".join(sorted(list(matches))) if matches else "-"

    def _on_tree_click(self, event):
        if not self.edit_mode_enabled:
            return

        """Permite marcar/desmarcar itens clicando na coluna SEL."""
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            if column == "#1":  # Coluna SEL
                item_id = self.tree.identify_row(event.y)
                if item_id:
                    valores = list(self.tree.item(item_id, 'values'))
                    valores[0] = '☐' if valores[0] == '☑' else '☑'
                    self.tree.item(item_id, values=valores)
                    self._atualizar_selecionados()
                    return "break"  # Impede seleção da linha

    def _atualizar_selecionados(self):
        """Atualiza a lista de itens selecionados."""
        if not self.edit_mode_enabled:
            self.btn_sinc_lote.config(state=tk.DISABLED)
            return

        self.selecionados_lote = [item for item in self.tree.get_children() 
                                  if self.tree.item(item, 'values')[0] == '☑']
        if len(self.selecionados_lote) >= 1:
            self.btn_sinc_lote.config(state=tk.NORMAL)
        else:
            self.btn_sinc_lote.config(state=tk.DISABLED)

    def _selecionar_todos(self):
        for item in self.tree.get_children():
            valores = list(self.tree.item(item, 'values'))
            valores[0] = '☑'
            self.tree.item(item, values=valores)
        self._atualizar_selecionados()

    def _desmarcar_todos(self):
        for item in self.tree.get_children():
            valores = list(self.tree.item(item, 'values'))
            valores[0] = '☐'
            self.tree.item(item, values=valores)
        self._atualizar_selecionados()

    def _iniciar_analise(self):
        if not self.pasta_xmls and not self.arquivos_selecionados:
            return messagebox.showwarning("Atenção", "Selecione XMLs.")
            
        self.btn_analisar.config(state=tk.DISABLED)
        self.btn_cancelar.config(state=tk.NORMAL)
        self.lbl_status.config(text="Agrupando NCMs e buscando faixas no banco...")
        self._toggle_edit_mode(enabled=False)
        for item in self.tree.get_children(): self.tree.delete(item)
        self.selecionados_lote = []
        self.btn_sinc_lote.config(state=tk.DISABLED)
        self.cancel_event.clear()
        escopo = self.var_escopo.get()
        self._carregar_faixas_icms(escopo)
        self.analysis_thread = threading.Thread(target=self._pipeline_bg, args=(escopo,), daemon=True)
        self.analysis_thread.start()

    def _cancelar_analise(self):
        self.cancel_event.set()
        self.btn_cancelar.config(state=tk.DISABLED)
        self.lbl_status.config(text="Cancelando análise... Aguarde.")

    def _finalizar_cancelamento(self):
        self.btn_analisar.config(state=tk.NORMAL)
        self.btn_cancelar.config(state=tk.DISABLED)
        self._atualizar_progresso(0, "Análise cancelada.")

    def _toggle_edit_mode(self, enabled):
        state = tk.NORMAL if enabled and self.edit_mode_enabled else tk.DISABLED
        self.btn_sinc_lote.config(state=state)
        if not enabled:
            self.btn_sinc_lote.config(state=tk.DISABLED)

    def _pipeline_bg(self, escopo="FILIAL_ATUAL"):
        try:
            self.parent.after(0, lambda: self._atualizar_progresso(5, "Lendo arquivos XML..."))
            itens_xml = []
            if self.arquivos_selecionados:
                for arq in self.arquivos_selecionados:
                    if self.cancel_event.is_set():
                        self.parent.after(0, self._finalizar_cancelamento)
                        return
                    try: itens_xml.extend(parse_nfe(arq)['itens'])
                    except Exception: logging.warning(f"Erro ao processar XML: {arq}")
            else:
                itens_xml = parse_nfe_folder(self.pasta_xmls)

            if self.cancel_event.is_set():
                self.parent.after(0, self._finalizar_cancelamento)
                return

            self.parent.after(0, self._atualizar_progresso, 30, "Agrupando itens por NCM...")
            self.dados_agrupados = self._agrupar_ncm(itens_xml)
            
            if self.cancel_event.is_set():
                self.parent.after(0, self._finalizar_cancelamento)
                return

            self.parent.after(0, self._atualizar_progresso, 35, "Consultando tabelas no Firebird...")
            empresa = self.config.get('IMPORTACAO', 'empresa', fallback='1')
            filial = self.config.get('IMPORTACAO', 'filial', fallback='1')
            try:
                with FirebirdService(self.config_db) as fb:
                    sql = """SELECT CFIS_CODIGO, CFIS_DESCRICAO, CFIS_ICMS_VENDA, CFIS_PIS, CFIS_COFINS, CFIS_CST_PIS, CFIS_CST_COFINS FROM TABELA_class_fiscal"""
                    params = [empresa]
                    if escopo == "FILIAL_ATUAL":
                        sql += " WHERE CFIS_EMPRESA = ? AND CFIS_FILIAL = ?"
                        params.append(filial)
                    else: # UNIFICADO
                        sql += " WHERE CFIS_EMPRESA = ?"
                    
                    ncm_db = fb.query(sql, params)

                    if escopo == "FILIAL_ATUAL":
                        self.dados_sistema = {str(row['cfis_codigo']).replace('.', '').strip(): row for row in ncm_db}
                    else: # UNIFICADO
                        self.dados_sistema = {}
                        for row in ncm_db:
                            ncm_key = str(row['cfis_codigo']).replace('.', '').strip()
                            if not self.dados_sistema.get(ncm_key): self.dados_sistema[ncm_key] = []
                            self.dados_sistema[ncm_key].append(row)
                    
                    try:
                        sql_gov = "SELECT NCM_CODIGO, NCM_DESCRICAO FROM TABELA_NCM"
                        gov_db = fb.query(sql_gov, [])
                        self.ncm_governo = {str(row['ncm_codigo']).replace('.', '').strip(): str(row.get('ncm_descricao', '')) for row in gov_db}
                    except Exception:
                        self.ncm_governo = {}
                        
                    try:
                        sql_rt = "SELECT TRT_ID, TRT_CLASS_TRIB_ID, TRT_CST, TRT_ALIQ_IBS_ESTADUAL, TRT_ALIQ_CBS FROM TABELA_RT_CONFIG_2025_2026"
                        raw_rt = fb.query(sql_rt, [])
                        self.regras_rt = []
                        for r in raw_rt:
                            self.regras_rt.append({
                                'id': str(r.get('trt_id')),
                                'class': str(r.get('trt_class_trib_id') or '').strip().lstrip('0') or '0',
                                'cst': str(r.get('trt_cst') or '').strip().lstrip('0') or '0',
                                'ibs': float(r.get('trt_aliq_ibs_estadual') or 0),
                                'cbs': float(r.get('trt_aliq_cbs') or 0)
                            })
                    except Exception:
                        self.regras_rt = []
            except Exception as db_err:
                self.dados_sistema = {}
                self.ncm_governo = {}

            if self.cancel_event.is_set():
                self.parent.after(0, self._finalizar_cancelamento)
                return

            total_grupos = len(self.dados_agrupados)
            valores_tree = []
            
            for idx, grupo in enumerate(self.dados_agrupados):
                if self.cancel_event.is_set():
                    self.parent.after(0, self._finalizar_cancelamento)
                    return

                ncm = grupo['ncm']
                sys_item = self.dados_sistema.get(ncm)
                
                if escopo == "FILIAL_ATUAL":
                    sys_item = self.dados_sistema.get(ncm)
                    faixa_erp = sys_item.get('cfis_icms_venda', '-') if sys_item else '-'
                    pis_erp = sys_item.get('cfis_pis', '-') if sys_item else '-'
                    cofins_erp = sys_item.get('cfis_cofins', '-') if sys_item else '-'
                    desc_sys = sys_item.get('cfis_descricao') if sys_item else None
                else: # UNIFICADO
                    sys_items = self.dados_sistema.get(ncm)
                    if sys_items:
                        faixa_erp = self._get_distinct_from_list(sys_items, 'cfis_icms_venda')
                        pis_erp = self._get_distinct_from_list(sys_items, 'cfis_pis')
                        cofins_erp = self._get_distinct_from_list(sys_items, 'cfis_cofins')
                        desc_sys = self._get_distinct_from_list(sys_items, 'cfis_descricao')
                    else:
                        faixa_erp, pis_erp, cofins_erp, desc_sys = '-', '-', '-', None
                
                faixas_encontradas = set()
                regras_rt_encontradas = set()
                for item_original in grupo['itens_originais']:
                    faixa = self._buscar_faixa_para_ncm(item_original)
                    if faixa: faixas_encontradas.add(faixa)
                    
                    regra = self._buscar_regra_rt(item_original)
                    if regra and regra != '-': regras_rt_encontradas.add(regra)
                
                faixa_xml = ", ".join(sorted(list(faixas_encontradas))) if faixas_encontradas else "-"
                regra_rt = ", ".join(sorted(list(regras_rt_encontradas))) if regras_rt_encontradas else "-"
                
                is_multiple = False
                if len(faixas_encontradas) > 1: is_multiple = True
                if '*' in str(grupo['pis_alq']) or ' / ' in str(grupo['pis_alq']): is_multiple = True
                if '*' in str(grupo['cofins_alq']) or ' / ' in str(grupo['cofins_alq']): is_multiple = True

                is_novo = (escopo == "FILIAL_ATUAL" and not sys_item) or (escopo == "UNIFICADO" and not sys_items)

                if is_novo:
                    if is_multiple:
                        status, tag = "NOVO (MÚLTIPLOS)", "MULTIPLOS"
                    else:
                        status, tag = "NOVO", "NOVO"
                else:
                    status, tag = "OK", "OK"
                    is_different = False
                    if str(faixa_xml) != str(faixa_erp) and str(faixa_xml) != '-': is_different = True
                    
                    if not is_different and str(grupo['pis_alq']) not in ('-', '*VÁRIOS*') and str(pis_erp) != '-' and str(grupo['pis_alq']) != str(pis_erp):
                        is_different = True
                    if not is_different and str(grupo['cofins_alq']) not in ('-', '*VÁRIOS*') and str(cofins_erp) != '-' and str(grupo['cofins_alq']) != str(cofins_erp):
                        is_different = True

                    if is_multiple:
                        status, tag = "DIFERENTE (MÚLTIPLOS)", "MULTIPLOS"
                    elif is_different:
                        status, tag = "DIFERENTE", "DIFERENTE"
                    else:
                        status, tag = "OK", "OK"
                
                desc_oficial = getattr(self, 'ncm_governo', {}).get(ncm)
                desc_exibicao = desc_oficial if desc_oficial else (desc_sys if desc_sys else grupo['descricao'])
                
                valores = (
                    '☐', grupo['ocorrencias'], ncm, status, desc_exibicao,
                    grupo['uf_dest'], grupo['cfop'], grupo['tipo_cliente'],
                    grupo['icms_cst'], f"{grupo['p_icms']}%", f"{grupo['p_red_bc']}%", f"{grupo['p_fcp']}%", f"{grupo['p_mvast']}%", f"{grupo['p_icmsst']}%",
                    grupo['c_benef'] or '-', grupo['c_cred'] or '-', f"{grupo['p_cred']}%" if grupo['p_cred'] else '-',
                    self._formatar_cst(grupo['pis_cst']), f"{grupo['pis_alq']}%", 
                    pis_erp if pis_erp else '-',
                    self._formatar_cst(grupo['cofins_cst']), f"{grupo['cofins_alq']}%",
                    cofins_erp if cofins_erp else '-',
                    grupo['c_class_trib'] or '-', grupo['ibscbs_cst'] or '-', f"{grupo['p_ibs_uf']}%", f"{grupo['p_cbs']}%",
                    faixa_xml or '-', faixa_erp, regra_rt
                )
                valores_tree.append((valores, tag, grupo))
                
                if idx % max(1, total_grupos // 20) == 0:
                    self.parent.after(0, self._atualizar_progresso, 40 + (idx / max(1, total_grupos)) * 55, f"Cruzando NCMs: {idx}/{total_grupos}")

            self.parent.after(0, self._atualizar_progresso, 95, "Renderizando Tabela Visual...")
            self.parent.after(0, lambda v=valores_tree: self._renderizar_resultados(v))
        except Exception as e:
            self.parent.after(0, lambda e=e: messagebox.showerror("Erro", str(e)))
            self.parent.after(0, lambda: self.btn_analisar.config(state=tk.NORMAL))

    def _get_tax_key(self, item):
        """Gera chave única de tributação para sub-agrupamento (ICMS + PIS + COFINS + CFOP)."""
        icms_cst = str(item.get('icms_cst', '')).strip() or '00'
        p_icms = str(item.get('p_icms', '0')).strip()
        p_red_bc = str(item.get('p_red_bc', '0')).strip()
        c_benef = str(item.get('c_benef', '')).strip()
        pis_cst = str(item.get('pis_cst', '')).strip() or '00'
        p_pis = str(item.get('p_pis', '0')).strip()
        cofins_cst = str(item.get('cofins_cst', '')).strip() or '00'
        p_cofins = str(item.get('p_cofins', '0')).strip()
        cfop = str(item.get('cfop', '')).strip() or '0000'
        return f"{icms_cst}|{p_icms}|{p_red_bc}|{c_benef}|{pis_cst}|{p_pis}|{cofins_cst}|{p_cofins}|{cfop}"

    def _agrupar_ncm(self, itens):
        mapa = {}
        for i in itens:
            ncm_xml = str(i.get('ncm', '')).replace('.', '').strip()
            if not ncm_xml: continue
            
            if ncm_xml not in mapa:
                mapa[ncm_xml] = []
            mapa[ncm_xml].append(i)

        dados_agrupados = []
        for ncm, itens_grupo in mapa.items():
            sub_map = {}
            for item in itens_grupo:
                tax_key = self._get_tax_key(item)
                if tax_key not in sub_map:
                    sub_map[tax_key] = []
                sub_map[tax_key].append(item)

            for tax_key, sub_itens in sub_map.items():
                def get_distinct_gcred(itens, chave):
                    valores = set()
                    for item in itens:
                        gcreds = item.get('cred_presumidos', [])
                        if gcreds:
                            valores.add(str(gcreds[0].get(chave, '')))
                    if not valores: return "-"
                    if len(valores) == 1: return list(valores)[0]
                    return "*VÁRIOS*"

                grupo = {
                    'ncm': ncm,
                    'descricao': self._get_distinct_from_list(sub_itens, 'x_prod'),
                    'uf_dest': self._get_distinct_from_list(sub_itens, 'uf_dest'),
                    'cfop': self._get_distinct_from_list(sub_itens, 'cfop'),
                    'tipo_cliente': self._get_distinct_from_list(sub_itens, 'tipo_cliente'),
                    'ocorrencias': len(sub_itens),
                    'c_benef': self._get_distinct_from_list(sub_itens, 'c_benef'),
                    'c_cred': get_distinct_gcred(sub_itens, 'c_cred'),
                    'p_cred': get_distinct_gcred(sub_itens, 'p_cred'),
                    'icms_cst': self._get_distinct_from_list(sub_itens, 'icms_cst'),
                    'p_icms': self._get_distinct_from_list(sub_itens, 'p_icms'),
                    'p_red_bc': self._get_distinct_from_list(sub_itens, 'p_red_bc'),
                    'p_fcp': self._get_distinct_from_list(sub_itens, 'p_fcp'),
                    'p_icmsst': self._get_distinct_from_list(sub_itens, 'p_icmsst'),
                    'p_mvast': self._get_distinct_from_list(sub_itens, 'p_mvast'),
                    'pis_cst': self._get_distinct_from_list(sub_itens, 'pis_cst'),
                    'pis_alq': self._get_distinct_from_list(sub_itens, 'p_pis'),
                    'cofins_cst': self._get_distinct_from_list(sub_itens, 'cofins_cst'),
                    'cofins_alq': self._get_distinct_from_list(sub_itens, 'p_cofins'),
                    'c_class_trib': self._get_distinct_from_list(sub_itens, 'c_class_trib'),
                    'ibscbs_cst': self._get_distinct_from_list(sub_itens, 'ibscbs_cst'),
                    'p_ibs_uf': self._get_distinct_from_list(sub_itens, 'p_ibs_uf'),
                    'p_cbs': self._get_distinct_from_list(sub_itens, 'p_cbs'),
                    'itens_originais': sub_itens
                }
                dados_agrupados.append(grupo)
        return dados_agrupados

    def _renderizar_resultados(self, valores_tree):
        self.valores_tree = valores_tree
        self.filtered_tree = valores_tree[:]
        self.btn_analisar.config(state=tk.NORMAL)
        self.btn_cancelar.config(state=tk.DISABLED)
        self.btn_exportar.config(state=tk.NORMAL)
        self._atualizar_progresso(100, f"Renderizando tabela...")
        self._atualizar_contadores()
        self._filtrar_treeview()

    def _filtrar_treeview(self):
        filtro = self.var_filtro.get().strip().lower()
        filtro_ncm = self.var_filtro_ncm.get().strip().lower()
        filtro_uf = self.var_filtro_uf.get().strip().lower()
        filtro_cfop = self.var_filtro_cfop.get().strip().lower()
        status = self.var_status_filtro.get()
        if not hasattr(self, 'valores_tree') or not self.valores_tree:
            return

        filtrados = []
        for valores, tag, grupo in self.valores_tree:
            status_item = valores[3]
            if status != "Todos":
                if status == "NOVO" and "NOVO" not in status_item: continue
                if status == "DIFERENTE" and "DIFERENTE" not in status_item: continue
                if status == "OK" and status_item != "OK": continue

            if filtro:
                texto_procura = filtro
                valores_busca = (
                    valores[2], valores[4], valores[5], valores[6], valores[7], valores[3]
                )
                if not any(texto_procura in str(v).lower() for v in valores_busca):
                    continue

            if filtro_ncm and filtro_ncm not in str(valores[2]).lower():
                continue

            if filtro_uf and filtro_uf not in str(valores[5]).lower():
                continue

            if filtro_cfop and filtro_cfop not in str(valores[6]).lower():
                continue

            filtrados.append((valores, tag, grupo))

        self.filtered_tree = filtrados
        
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.dados_grid.clear()

        for vals, tg, grp in self.filtered_tree:
            item_id = self.tree.insert("", tk.END, values=vals, tags=(tg,))
            self.dados_grid[item_id] = grp

        self.lbl_status.config(text=f"Pronto. {len(self.filtered_tree)} resultados exibidos.")

    def _limpar_filtro(self):
        self.var_filtro.set("")
        self.var_filtro_ncm.set("")
        self.var_filtro_uf.set("")
        self.var_filtro_cfop.set("")
        self.var_status_filtro.set("Todos")
        self.filtered_tree = self.valores_tree[:]
        self._filtrar_treeview()

    def _sincronizar_ncm_erp(self):
        caminho_json = filedialog.askopenfilename(title="JSON do Governo", filetypes=[("JSON", "*.json")])
        if not caminho_json: return

        try:
            with open(caminho_json, 'r', encoding='utf-8') as f:
                dados_json = json.load(f)
        except Exception as e:
            return messagebox.showerror("Erro", f"Ler JSON: {e}")

        lista_ncm = dados_json.get("Nomenclaturas", dados_json)
        ncms_para_inserir = []
        for item in lista_ncm:
            codigo = str(item.get("Codigo", "")).replace(".", "").strip()
            descricao = str(item.get("Descricao", "")).strip()
            descricao = descricao.encode('cp1252', errors='ignore').decode('cp1252')
            if len(codigo) == 8:
                ncms_para_inserir.append((codigo, descricao[:200]))

        if not ncms_para_inserir:
            return messagebox.showwarning("Aviso", "Nenhum NCM de 8 dígitos.")

        if not messagebox.askyesno("Confirmação", f"Inserir {len(ncms_para_inserir)} NCMs na TABELA_NCM?"):
            return

        def task():
            self.parent.after(0, lambda: self.btn_sincronizar.config(state=tk.DISABLED, text="Enviando..."))
            try:
                inseridos = 0
                with FirebirdService(self.config_db) as fb:
                    cursor = fb.conn.cursor() if hasattr(fb, 'conn') else None
                    for cod, desc in ncms_para_inserir:
                        sql = """MERGE INTO TABELA_NCM T USING 
                                 (SELECT CAST(? AS VARCHAR(10)) AS NCM_CODIGO, CAST(? AS VARCHAR(250)) FROM RDB$DATABASE) S 
                                 ON T.NCM_CODIGO = S.NCM_CODIGO WHEN NOT MATCHED THEN INSERT VALUES (S.NCM_CODIGO, S.NCM_DESCRICAO)"""
                        try:
                            if cursor: cursor.execute(sql, (cod, desc))
                            else: fb.execute(sql, (cod, desc))
                            inseridos += 1
                        except Exception: logging.warning(f"Erro ao sincronizar NCM {cod}: {desc}")
                    if cursor: fb.conn.commit()
                self.parent.after(0, lambda: messagebox.showinfo("Sucesso", f"{inseridos} NCMs inseridos!"))
            except Exception as e:
                self.parent.after(0, lambda e=e: messagebox.showerror("Erro", str(e)))
            finally:
                self.parent.after(0, lambda: self.btn_sincronizar.config(state=tk.NORMAL, text="🔄 Sincronizar NCMs p/ ERP"))

        threading.Thread(target=task, daemon=True).start()

    def _exportar_csv(self):
        caminho = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="NCM_Analise.csv")
        if not caminho: return
        try:
            with open(caminho, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f, delimiter=';')
                
                colunas = ("QTD", "NCM", "STATUS", "DESCRIÇÃO", "UF", "CFOP", "TIPO", 
                           "CST ICMS", "ICMS%", "RED.BC%", "FCP%", "MVA ST%", "ICMS ST%",
                           "CBENEF", "C.CRED", "P.CRED",
                           "CST PIS", "PIS%", "PIS% ERP",
                           "CST COF", "COF%", "COF% ERP",
                           "C. CLASSE RT", "CST RT", "IBS%", "CBS%",
                    "FAIXA ICMS", "FAIXA ERP", "REGRA RT ERP")

                writer.writerow(colunas)
                for child in self.tree.get_children():
                    v = self.tree.item(child, "values")
                    writer.writerow(v[1:]) # Pula a coluna SEL
            messagebox.showinfo("Sucesso", "CSV exportado!")
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def _sincronizar_lote(self):
        selecionados = [item for item in self.tree.get_children() if self.tree.item(item, 'values')[0] == '☑']
        if not selecionados:
            return messagebox.showwarning("Aviso", "Nenhum item selecionado para sincronizar.")

        registros_para_salvar = []
        ignorados_multiplos = 0
        
        for item_id in selecionados:
            grupo = self.dados_grid.get(item_id)
            valores = self.tree.item(item_id, 'values')
            status = valores[3]

            if "MÚLTIPLOS" in status:
                ignorados_multiplos += 1
                continue

            ncm_limpo = grupo['ncm']
            faixa = valores[27] if valores[27] != '-' else ''
            pis = self._extrair_float(valores[18])
            cofins = self._extrair_float(valores[21])
            cst_pis = self._extrair_cst(grupo.get('pis_cst', ''))
            cst_cofins = self._extrair_cst(grupo.get('cofins_cst', ''))
            reforma_faixa = valores[29] if len(valores) > 29 and valores[29] != '-' else ''
            
            desc_oficial = getattr(self, 'ncm_governo', {}).get(ncm_limpo, grupo['descricao'])
            
            registros_para_salvar.append({
                'ncm': ncm_limpo,
                'status': status,
                'descricao': desc_oficial[:200],
                'faixa_sugerida': faixa,
                'pis_sugerido': pis,
                'cofins_sugerido': cofins,
                'cst_pis': cst_pis,
                'cst_cofins': cst_cofins,
                'reforma_faixa_sugerida': reforma_faixa,
                'c_class_trib': grupo.get('c_class_trib', ''),
                'ibscbs_cst': grupo.get('ibscbs_cst', ''),
                'p_ibs_uf': grupo.get('p_ibs_uf', 0),
                'p_cbs': grupo.get('p_cbs', 0),
                'cfis_subst_tributaria': 'S' if (grupo.get('p_icmsst') or 0) > 0 else 'N',
                'cfis_st_compra': 'S' if (grupo.get('p_icmsst') or 0) > 0 else 'N',
            })

        if not registros_para_salvar:
            msg = "Nenhum item válido selecionado."
            if ignorados_multiplos > 0:
                msg += f"\n\n⚠️ {ignorados_multiplos} NCM(s) com múltiplas variações foram ignorados. Edite-os individualmente!"
            return messagebox.showinfo("Aviso", msg)

        if ignorados_multiplos > 0:
            messagebox.showwarning("Aviso Múltiplos", f"{ignorados_multiplos} NCM(s) com múltiplas variações foram ignorados. Edite-os individualmente.")

        # Abre o Modal para revisão e edição manual
        empresa = self.config.get('IMPORTACAO', 'empresa', fallback='1')
        filial = self.config.get('IMPORTACAO', 'filial', fallback='1')

        DialogoPreviewNCM(
            self.winfo_toplevel(), registros_para_salvar,
            self._iniciar_sincronizacao_thread,
            faixas_icms=self.faixas_icms,
            regras_rt=self.regras_rt,
            config_db=self.config_db,
            empresa=empresa,
            filial=filial
        )

    def _iniciar_sincronizacao_thread(self, registros):
        self.btn_sinc_lote.config(state=tk.DISABLED, text="Sincronizando...")
        self.btn_analisar.config(state=tk.DISABLED)

        threading.Thread(target=self._executar_sincronizacao_bg, args=(registros,), daemon=True).start()

    def _executar_sincronizacao_bg(self, registros):
        empresa = self.config.get('IMPORTACAO', 'empresa', fallback='1')
        filial = self.config.get('IMPORTACAO', 'filial', fallback='1')
        
        sucesso_ins = 0
        sucesso_upd = 0
        erros = []

        try:
            with FirebirdService(self.config_db) as fb:
                cursor = fb.conn.cursor()
                for reg in registros:
                    try:
                        ncm_limpo = reg['ncm']
                        ncm_fmt = f"{ncm_limpo[:4]}.{ncm_limpo[4:6]}.{ncm_limpo[6:]}" if len(ncm_limpo) == 8 else ncm_limpo
                        
                        desc_oficial = reg['descricao']

                        faixa = reg['faixa_sugerida']
                        if faixa == '*VÁRIOS*' or ' / ' in str(faixa):
                            faixa = str(faixa).split(' / ')[0].replace('*VÁRIOS*', '').strip() or None
                        elif not faixa:
                            faixa = None

                        pis_alq = self._extrair_float(str(reg['pis_sugerido']).replace(',', '.'))
                        cofins_alq = self._extrair_float(str(reg['cofins_sugerido']).replace(',', '.'))
                        cst_pis = self._extrair_cst(str(reg['cst_pis']))
                        cst_cofins = self._extrair_cst(str(reg['cst_cofins']))

                        st_saida = reg.get('cfis_subst_tributaria', 'N')
                        st_compra = reg.get('cfis_st_compra', 'N')
                        if st_saida not in ('S', 'N'): st_saida = 'N'
                        if st_compra not in ('S', 'N'): st_compra = 'N'

                        if 'NOVO' in reg['status']:
                            sql_in = """INSERT INTO TABELA_class_fiscal 
                                        (CFIS_EMPRESA, CFIS_FILIAL, CFIS_CODIGO, CFIS_DESCRICAO, CFIS_ICMS_VENDA, 
                                         CFIS_PIS, CFIS_COFINS, CFIS_CST_PIS, CFIS_CST_COFINS, CFIS_IPI, CFIS_CST_IPI,
                                         CFIS_SUBST_TRIBUTARIA, CFIS_ST_COMPRA) 
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, '53', ?, ?)"""
                            params = (empresa, filial, ncm_fmt, desc_oficial, faixa, pis_alq, cofins_alq, cst_pis, cst_cofins, st_saida, st_compra)
                            cursor.execute(sql_in, params)
                            sucesso_ins += 1
                        else:
                            sql_up = """UPDATE TABELA_class_fiscal SET 
                                            CFIS_DESCRICAO = ?, CFIS_ICMS_VENDA = ?, CFIS_PIS = ?, CFIS_COFINS = ?, 
                                            CFIS_CST_PIS = ?, CFIS_CST_COFINS = ?,
                                            CFIS_SUBST_TRIBUTARIA = ?, CFIS_ST_COMPRA = ?
                                        WHERE CFIS_EMPRESA = ? AND CFIS_FILIAL = ? AND CFIS_CODIGO = ?"""
                            params = (desc_oficial, faixa, pis_alq, cofins_alq, cst_pis, cst_cofins, st_saida, st_compra, empresa, filial, ncm_fmt)
                            cursor.execute(sql_up, params)
                            sucesso_upd += 1
                    except Exception as e:
                        erros.append(f"NCM {ncm_fmt}: {e}")

                fb.conn.commit()
            
            msg_final = f"Sincronização concluída!\n\n• {sucesso_ins} NCMs inseridos.\n• {sucesso_upd} NCMs atualizados."
            if erros:
                msg_final += f"\n• {len(erros)} erros."
                if messagebox.askyesno("Erros na Sincronização", f"{msg_final}\n\nDeseja salvar um log com os detalhes dos erros?"):
                    caminho_log = filedialog.asksaveasfilename(defaultextension=".txt", initialfile="log_erros_ncm.txt")
                    if caminho_log:
                        with open(caminho_log, 'w', encoding='utf-8') as f:
                            f.write('\n'.join(erros))

            self.parent.after(0, lambda: messagebox.showinfo("Sucesso", msg_final))
            self.parent.after(0, self._iniciar_analise)

        except Exception as e:
            self.parent.after(0, lambda e=e: messagebox.showerror("Erro Crítico", f"Falha na sincronização com o banco:\n{e}"))
        finally:
            self.parent.after(0, lambda: self.btn_sinc_lote.config(state=tk.NORMAL, text="🚀 Sincronizar Selecionados"))
            self.parent.after(0, lambda: self.btn_analisar.config(state=tk.NORMAL))

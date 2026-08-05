import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import configparser
import threading
import json
import os
import re
import sys
import csv
import logging

from utils.xml_reader import parse_nfe_folder, parse_nfe
from utils.firebird_service import FirebirdService
from utils import tema

logging.basicConfig(
    filename='sistema_erros.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - [NCM Sync] - %(message)s'
)

# ------------------------------------------------------------------ ORGANIZAÇÃO
# Como os NCMs-pai são ordenados na grade. A ordenação é aplicada na renderização
# (e não movendo linhas depois), então sobrevive a filtrar, limpar filtro e
# reanalisar — clicar no cabeçalho de uma coluna reordenava e a próxima digitada
# no filtro devolvia tudo para a ordem de leitura dos XMLs.
ORDEM_PENDENTES = "Pendentes primeiro"
ORDEM_NCM = "NCM (menor → maior)"
ORDEM_NCM_DESC = "NCM (maior → menor)"
ORDEM_USO = "Mais usados nas notas"
ORDEM_REGRAS = "Mais regras diferentes"
ORDEM_DESCRICAO = "Descrição (A → Z)"
ORDENS = [ORDEM_PENDENTES, ORDEM_NCM, ORDEM_NCM_DESC,
          ORDEM_USO, ORDEM_REGRAS, ORDEM_DESCRICAO]

PESO_STATUS = {'NOVO': 0, 'DIFERENTE': 1, 'OK': 2}


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
        tema.centralizar(self, w, h)

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
        # No ERP o CFIS_CODIGO é gravado COM pontos (ex.: '0102.29.90'); formata antes de consultar
        ncm_str = str(ncm).replace('.', '')
        ncm_fmt = f"{ncm_str[:4]}.{ncm_str[4:6]}.{ncm_str[6:]}" if len(ncm_str) == 8 and ncm_str.isdigit() else ncm
        try:
            with FirebirdService(self.config_db) as fb:
                cursor = fb.conn.cursor()
                cursor.execute(f"SELECT {campo} FROM TABELA_class_fiscal WHERE CFIS_CODIGO=? AND CFIS_EMPRESA=? AND CFIS_FILIAL=?",
                               (ncm_fmt, self.empresa, self.filial))
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
        tema.centralizar(self, w, h)

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


class DialogoConfirmacaoAntesDepois(tk.Toplevel):
    """Mostra, NCM a NCM, como o cadastro está no ERP e como vai ficar após gravar.

    Permite validar antes de aplicar, exportar as variações NÃO eleitas (roteiro
    para tratar em produto/CFOP) e, opcionalmente, abrir o editor fino.
    """
    def __init__(self, parent, registros, nao_usadas, callback_gravar,
                 combos_icms=None, combos_rt=None, callback_editar=None):
        super().__init__(parent)
        self.title("Conferência: como está × como vai ficar")
        w = min(1080, int(self.winfo_screenwidth() * 0.9))
        h = min(720, int(self.winfo_screenheight() * 0.88))
        self.geometry(f"{w}x{h}")
        self.minsize(720, 480)
        self.transient(parent)
        self.grab_set()

        self.registros = registros
        self.nao_usadas = nao_usadas or []
        self.combos_icms = combos_icms or []
        self.combos_rt = combos_rt or []
        self.callback_gravar = callback_gravar
        self.callback_editar = callback_editar
        self._entries_faixa = {}   # key -> Entry (número da faixa)
        self._entries_rt = {}      # key -> Entry (TRT_ID)

        self._criar_widgets()
        self._carregar()
        tema.centralizar(self, w, h)

    @staticmethod
    def _norm(v):
        s = str(v if v is not None else '').strip()
        return '' if s in ('-', 'None', '*VÁRIOS*') else s

    def _fmt(self, antes, depois, novo):
        a, d = self._norm(antes), self._norm(depois)
        if novo:
            return d or '-'
        if a == d:
            return a or '-'
        return f"{a or '-'} → {d or '-'}"

    def _criar_widgets(self):
        tk.Label(self, text="Revise cada NCM antes de gravar. Linhas em destaque mudam de valor.",
                 font=("Segoe UI", 12, "bold")).pack(anchor=tk.W, padx=10, pady=10)

        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        cols = ("NCM", "FAIXA ICMS", "RT", "PIS (CST/%)", "COFINS (CST/%)", "IPI (CST/%)", "SITUAÇÃO")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings")
        larg = [95, 150, 110, 150, 160, 130, 90]
        for c, l in zip(cols, larg):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=l, anchor=tk.CENTER if c != "NCM" else tk.W)

        self.tree.tag_configure('novo', background='#EAFAF1', foreground='#16A34A')
        self.tree.tag_configure('altera', background='#FEF9E7', foreground='#B45309')
        self.tree.tag_configure('igual', background='#FFFFFF', foreground='#475569')

        sy = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=sy.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sy.pack(side=tk.RIGHT, fill=tk.Y)

        self.lbl_resumo = ttk.Label(self, text="", font=("Segoe UI", 9), foreground="#555")
        self.lbl_resumo.pack(anchor=tk.W, padx=12, pady=(4, 0))

        # Seções do que será CRIADO (faixas ICMS / regras RT), com número editável
        self._perfis_faixa = {}   # key -> {'CT':BooleanVar,'NC':BooleanVar,'SN':BooleanVar}
        if self.combos_icms:
            lf = ttk.LabelFrame(self, text="🆕 Faixas de ICMS a criar (marque os perfis e confira o número)", padding=8)
            lf.pack(fill=tk.X, padx=10, pady=(6, 0))
            hdr = ["Nº Faixa *", "UF", "CST", "% ICMS", "% Red.", "CBENEF", "CT", "NC", "SN", "Qtd"]
            for i, h in enumerate(hdr):
                ttk.Label(lf, text=h, font=("Segoe UI", 8, "bold")).grid(row=0, column=i, padx=5, pady=2)
            for r, c in enumerate(self.combos_icms, start=1):
                ent = ttk.Entry(lf, width=8, font=("Segoe UI", 9, "bold"))
                ent.insert(0, str(c.get('sugerido', '')))
                ent.grid(row=r, column=0, padx=5, pady=1)
                self._entries_faixa[c['key']] = ent
                ttk.Label(lf, text=c['uf']).grid(row=r, column=1, padx=5)
                ttk.Label(lf, text=c['cst']).grid(row=r, column=2, padx=5)
                ttk.Label(lf, text=f"{c['aliquota']}%").grid(row=r, column=3, padx=5)
                ttk.Label(lf, text=f"{c['reducao']}%").grid(row=r, column=4, padx=5)
                ttk.Label(lf, text=c.get('cbenef') or '-').grid(row=r, column=5, padx=5)
                perfis = {}
                for j, t in enumerate(('CT', 'NC', 'SN')):
                    var = tk.BooleanVar(value=(t in c.get('tipos', set())))
                    ttk.Checkbutton(lf, variable=var).grid(row=r, column=6 + j, padx=5)
                    perfis[t] = var
                self._perfis_faixa[c['key']] = perfis
                ttk.Label(lf, text=str(c['qtd'])).grid(row=r, column=9, padx=5)

        if self.combos_rt:
            lf = ttk.LabelFrame(self, text="🆕 Regras de Reforma (RT) a criar (confira/edite o ID)", padding=8)
            lf.pack(fill=tk.X, padx=10, pady=(6, 0))
            hdr = ["ID RT *", "Classe Trib", "CST", "% IBS", "% CBS", "Qtd NCMs"]
            for i, h in enumerate(hdr):
                ttk.Label(lf, text=h, font=("Segoe UI", 8, "bold")).grid(row=0, column=i, padx=6, pady=2)
            for r, c in enumerate(self.combos_rt, start=1):
                ent = ttk.Entry(lf, width=8, font=("Segoe UI", 9, "bold"))
                ent.insert(0, str(c.get('sugerido', '')))
                ent.grid(row=r, column=0, padx=6, pady=1)
                self._entries_rt[c['key']] = ent
                ttk.Label(lf, text=c['class']).grid(row=r, column=1, padx=6)
                ttk.Label(lf, text=c['cst']).grid(row=r, column=2, padx=6)
                ttk.Label(lf, text=f"{c['ibs']}%").grid(row=r, column=3, padx=6)
                ttk.Label(lf, text=f"{c['cbs']}%").grid(row=r, column=4, padx=6)
                ttk.Label(lf, text=str(c['qtd'])).grid(row=r, column=5, padx=6)

        bot = ttk.Frame(self, padding=10)
        bot.pack(fill=tk.X, side=tk.BOTTOM)

        txt_exp = f"📤 Exportar regras não usadas ({len(self.nao_usadas)})"
        self.btn_export = ttk.Button(bot, text=txt_exp, command=self._exportar_nao_usadas)
        self.btn_export.pack(side=tk.LEFT)
        if not self.nao_usadas:
            self.btn_export.config(state=tk.DISABLED)

        ttk.Button(bot, text="💾 Gravar no ERP", command=self._gravar).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bot, text="❌ Cancelar", command=self.destroy).pack(side=tk.RIGHT, padx=5)
        if self.callback_editar:
            ttk.Button(bot, text="✏️ Editar detalhes…", command=self._editar).pack(side=tk.RIGHT, padx=5)

    def _carregar(self):
        novos = altera = igual = 0
        for reg in self.registros:
            antes = reg.get('_antes', {})
            novo = not antes.get('existe')

            faixa = self._fmt(antes.get('faixa'), reg.get('faixa_sugerida'), novo)
            rt = self._fmt(antes.get('rt'), reg.get('reforma_faixa_sugerida'), novo)
            pis = self._fmt(f"{self._norm(antes.get('cst_pis'))}/{self._norm(antes.get('pis'))}",
                            f"{self._norm(reg.get('cst_pis'))}/{self._norm(reg.get('pis_sugerido'))}", novo)
            cof = self._fmt(f"{self._norm(antes.get('cst_cofins'))}/{self._norm(antes.get('cofins'))}",
                            f"{self._norm(reg.get('cst_cofins'))}/{self._norm(reg.get('cofins_sugerido'))}", novo)
            ipi = self._fmt(f"{self._norm(antes.get('cst_ipi'))}/{self._norm(antes.get('ipi'))}",
                            f"{self._norm(reg.get('ipi_cst'))}/{self._norm(reg.get('ipi_alq'))}", novo)

            if novo:
                situacao, tag = "NOVO", "novo"
                novos += 1
            elif any('→' in x for x in (faixa, rt, pis, cof, ipi)):
                situacao, tag = "ALTERA", "altera"
                altera += 1
            else:
                situacao, tag = "IGUAL", "igual"
                igual += 1

            self.tree.insert("", tk.END, values=(reg['ncm'], faixa, rt, pis, cof, ipi, situacao), tags=(tag,))

        self.lbl_resumo.config(
            text=f"{len(self.registros)} NCM(s):  {novos} novo(s)  ·  {altera} alteração(ões)  ·  {igual} sem mudança."
        )

    def _exportar_nao_usadas(self):
        if not self.nao_usadas:
            return
        caminho = filedialog.asksaveasfilename(
            defaultextension=".csv", initialfile="regras_nao_usadas.csv",
            filetypes=[("CSV", "*.csv")], parent=self)
        if not caminho:
            return
        try:
            with open(caminho, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow((
                    "NCM", "QTD", "UF", "CFOP", "TIPO", "CST ICMS", "ICMS%", "RED.BC%",
                    "CBENEF", "FAIXA XML", "CST PIS", "PIS%", "CST COF", "COF%", "REGRA RT",
                    "PRÓXIMO PASSO"))
                for r in self.nao_usadas:
                    writer.writerow((
                        r['ncm'], r['ocorrencias'], r['uf'], r['cfop'], r['tipo'],
                        r['icms_cst'], r['p_icms'], r['p_red_bc'], r['c_benef'], r['faixa'],
                        r['pis_cst'], r['pis'], r['cofins_cst'], r['cofins'], r['regra_rt'],
                        "Tratar via PRODUTO ou CFOP"))
            messagebox.showinfo("Exportado", f"Arquivo salvo em:\n{caminho}", parent=self)
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao exportar:\n{e}", parent=self)

    def _editar(self):
        if self.callback_editar:
            self.destroy()
            self.callback_editar(self.registros)

    def _validar_numeros(self, entries, combos, label):
        """Lê os Entry de número, valida (inteiro, único) e devolve {key: numero}. (RT)"""
        vistos = set()
        mapa = {}
        for c in combos:
            val = entries[c['key']].get().strip()
            if not val.isdigit() or int(val) <= 0:
                messagebox.showwarning("Número inválido",
                    f"{label}: número inválido na linha Classe {c.get('class', '')} CST {c['cst']}.",
                    parent=self)
                return None
            if val in vistos:
                messagebox.showwarning("Número repetido",
                    f"{label}: o número {val} está repetido. Cada um precisa ser único.", parent=self)
                return None
            vistos.add(val)
            mapa[c['key']] = val
        return mapa

    def _montar_faixa_map(self):
        """Valida as faixas ICMS a criar permitindo o MESMO número em perfis diferentes.

        Só bloqueia se o mesmo (número, UF, perfil) for reivindicado por duas regras
        diferentes — aí seria sobreposição de verdade.
        """
        faixa_map = {}
        ocupacao = {}   # (numero, uf, perfil) -> (cst, aliq, red, cbenef)
        for c in self.combos_icms:
            val = self._entries_faixa[c['key']].get().strip()
            if not val.isdigit() or int(val) <= 0:
                messagebox.showwarning("Número inválido",
                    f"Faixa ICMS: número inválido para {c['uf']} CST {c['cst']}.", parent=self)
                return None
            perfis = {t: v.get() for t, v in self._perfis_faixa[c['key']].items()}
            if not any(perfis.values()):
                messagebox.showwarning("Perfil obrigatório",
                    f"Faixa {val} ({c['uf']} CST {c['cst']}): marque ao menos um perfil (CT, NC ou SN).",
                    parent=self)
                return None
            assinatura = (c['cst'], c['aliquota'], c['reducao'], c.get('cbenef') or '')
            for t, on in perfis.items():
                if not on:
                    continue
                slot = (val, c['uf'], t)
                if slot in ocupacao and ocupacao[slot] != assinatura:
                    messagebox.showwarning("Conflito de perfil",
                        f"A faixa {val} / {c['uf']} / perfil {t} está sendo pedida por DUAS regras "
                        "diferentes ao mesmo tempo.\n\nUse números de faixa diferentes, ou deixe cada "
                        "regra num perfil distinto (ex.: uma no CT, outra no NC).", parent=self)
                    return None
                ocupacao[slot] = assinatura
            faixa_map[c['key']] = {'faixa': val, 'uf': c['uf'], 'cst': c['cst'],
                                   'aliquota': c['aliquota'], 'reducao': c['reducao'],
                                   'cbenef': c.get('cbenef') or '', 'perfis': perfis}
        return faixa_map

    def _gravar(self):
        # Valida e monta os mapas do que será criado
        faixa_map, rt_map = {}, {}
        if self.combos_icms:
            faixa_map = self._montar_faixa_map()
            if faixa_map is None:
                return
        if self.combos_rt:
            nums = self._validar_numeros(self._entries_rt, self.combos_rt, "Regra RT")
            if nums is None:
                return
            for c in self.combos_rt:
                rt_map[c['key']] = {'id': nums[c['key']], 'class': c['class'], 'cst': c['cst'],
                                    'ibs': c['ibs'], 'cbs': c['cbs']}

        extras = []
        if faixa_map:
            linhas = {(v['faixa'], v['uf']) for v in faixa_map.values()}
            extras.append(f"{len(linhas)} faixa(s) ICMS")
        if rt_map:
            extras.append(f"{len(rt_map)} regra(s) RT")
        msg = f"Gravar {len(self.registros)} NCM(s) no ERP?"
        if extras:
            msg += "\n\nSerão criadas: " + " e ".join(extras) + "."
        if not messagebox.askyesno("Confirmar", msg, parent=self):
            return
        self.callback_gravar(self.registros, faixa_map, rt_map)
        self.destroy()


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
        # Header do módulo (identidade Sistecweb)
        tema.montar_header(
            self, "Tributação por NCM",
            "Gestão de regras tributárias e alíquotas por Nomenclatura Comum do Mercosul"
        ).pack(fill=tk.X)

        # ===================== CORPO: menu lateral + conteúdo =====================
        corpo = tk.Frame(self, bg=tema.BG_BASE)
        corpo.pack(fill=tk.BOTH, expand=True)

        # -------- MENU LATERAL (padrão do main) --------
        sidebar = tema.montar_sidebar(corpo, largura=tema.largura_sidebar(self))

        # Rodapé do menu: Voltar
        rodape_sb = tk.Frame(sidebar, bg=tema.SIDEBAR_BG)
        rodape_sb.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 8))
        self.btn_voltar = tema.botao_sidebar(rodape_sb, "⎋   Voltar", self._fechar_tela)
        self.btn_voltar.pack(fill=tk.X)

        tema.titulo_sidebar(sidebar, "AÇÕES").pack(fill=tk.X, pady=(16, 4))

        self.btn_analisar = tema.botao_sidebar(sidebar, "🔍   Analisar NCMs", self._iniciar_analise, cor_fg="#7EE0A0")
        self.btn_analisar.pack(fill=tk.X)

        self.btn_cancelar = tema.botao_sidebar(sidebar, "✖   Cancelar", self._cancelar_analise, cor_fg="#FF9B9B")
        self.btn_cancelar.config(state=tk.DISABLED)
        self.btn_cancelar.pack(fill=tk.X)

        self.btn_sincronizar = tema.botao_sidebar(sidebar, "🔄   Sincronizar NCMs Gov.", self._sincronizar_ncm_erp)
        self.btn_sincronizar.pack(fill=tk.X)

        self.btn_sinc_lote = tema.botao_sidebar(sidebar, "✨   Sincronizar Selecionados", self._sincronizar_lote, cor_fg="#7EE0A0")
        self.btn_sinc_lote.config(state=tk.DISABLED)
        self.btn_sinc_lote.pack(fill=tk.X)

        self.btn_exportar = tema.botao_sidebar(sidebar, "📋   Exportar CSV", self._exportar_csv)
        self.btn_exportar.config(state=tk.DISABLED)
        self.btn_exportar.pack(fill=tk.X)

        # -------- CONTEÚDO --------
        content = tk.Frame(corpo, bg=tema.BG_BASE)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=16, pady=12)

        # Escopo + arquivos + progresso numa barra que quebra em 2-3 linhas quando a
        # largura não dá. Antes eram três faixas empilhadas de altura fixa que, num
        # console de 1024x768, comiam a área da grade e ainda cortavam o botão da
        # direita.
        barra_escopo = tema.BarraFluida(content, "Escopo e arquivos")
        barra_escopo.pack(fill=tk.X, pady=(2, 4))

        self.var_escopo = tk.StringVar(self, value="FILIAL_ATUAL")
        g = barra_escopo.grupo()
        ttk.Radiobutton(g, text="Apenas filial atual", variable=self.var_escopo,
                        value="FILIAL_ATUAL", command=self._on_escopo_change).pack(side=tk.LEFT)
        ttk.Radiobutton(g, text="Unificar filiais da empresa", variable=self.var_escopo,
                        value="UNIFICADO", command=self._on_escopo_change).pack(side=tk.LEFT, padx=(8, 0))

        g = barra_escopo.grupo()
        tema.rotulo_campo(g, "XMLs:").pack(side=tk.LEFT, padx=(0, 4))
        self.ent_pasta = ttk.Entry(g, width=42)
        self.ent_pasta.pack(side=tk.LEFT)
        ttk.Button(g, text="📁 Pasta", command=self._selecionar_pasta).pack(side=tk.LEFT, padx=3)
        ttk.Button(g, text="📄 Arquivos", command=self._selecionar_arquivos).pack(side=tk.LEFT)

        g = barra_escopo.grupo()
        self.progresso = ttk.Progressbar(g, orient=tk.HORIZONTAL, mode='determinate', length=180)
        self.progresso.pack(side=tk.LEFT)
        barra_escopo.montar()

        # Dashboard Cards
        self.frame_cards = tk.Frame(content, bg=tema.BG_BASE, pady=2)
        self.frame_cards.pack(fill=tk.X)
        self._cards = []
        
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

        barra_filtro = tema.BarraFluida(content, "Filtrar e organizar")
        barra_filtro.pack(fill=tk.X, pady=(0, 4))

        self.var_filtro = tk.StringVar(self)
        self.var_filtro_ncm = tk.StringVar(self)
        self.var_filtro_uf = tk.StringVar(self)
        self.var_filtro_cfop = tk.StringVar(self)
        self.var_status_filtro = tk.StringVar(self, value="Todos")
        self.var_ordem = tk.StringVar(self, value=self._ordem_salva())
        self.var_so_multiplas = tk.BooleanVar(self, value=False)

        for rot, var, larg, attr in (("Buscar:", self.var_filtro, 18, 'ent_filtro'),
                                     ("NCM:", self.var_filtro_ncm, 11, 'ent_filtro_ncm'),
                                     ("UF:", self.var_filtro_uf, 5, 'ent_filtro_uf'),
                                     ("CFOP:", self.var_filtro_cfop, 7, 'ent_filtro_cfop')):
            g = barra_filtro.grupo()
            tema.rotulo_campo(g, rot).pack(side=tk.LEFT, padx=(0, 4))
            ent = ttk.Entry(g, textvariable=var, width=larg)
            ent.pack(side=tk.LEFT)
            ent.bind('<KeyRelease>', lambda event: self._filtrar_treeview())
            setattr(self, attr, ent)

        g = barra_filtro.grupo()
        tema.rotulo_campo(g, "Status:").pack(side=tk.LEFT, padx=(0, 4))
        self.cmb_status_filtro = ttk.Combobox(
            g, textvariable=self.var_status_filtro,
            values=["Todos", "NOVO", "DIFERENTE", "OK"], state="readonly", width=10)
        self.cmb_status_filtro.pack(side=tk.LEFT)
        self.cmb_status_filtro.bind('<<ComboboxSelected>>', lambda event: self._filtrar_treeview())

        # Ordem dos NCMs na grade — o pedido de "poder organizar os NCMs".
        g = barra_filtro.grupo()
        tema.rotulo_campo(g, "Ordenar por:").pack(side=tk.LEFT, padx=(0, 4))
        self.cmb_ordem = ttk.Combobox(g, textvariable=self.var_ordem, values=ORDENS,
                                      state="readonly", width=22)
        self.cmb_ordem.pack(side=tk.LEFT)
        self.cmb_ordem.bind('<<ComboboxSelected>>', lambda event: self._on_ordem_mudou())

        g = barra_filtro.grupo()
        chk = ttk.Checkbutton(g, text="Só NCM com mais de uma regra",
                              variable=self.var_so_multiplas,
                              command=self._filtrar_treeview)
        chk.pack(side=tk.LEFT)

        g = barra_filtro.grupo()
        ttk.Button(g, text="⊞ Expandir", width=11,
                   command=lambda: self._abrir_todos(True)).pack(side=tk.LEFT, padx=(0, 3))
        ttk.Button(g, text="⊟ Recolher", width=11,
                   command=lambda: self._abrir_todos(False)).pack(side=tk.LEFT, padx=(0, 3))
        ttk.Button(g, text="✕ Limpar filtro", command=self._limpar_filtro).pack(side=tk.LEFT)
        barra_filtro.montar()

        self.lbl_status = ttk.Label(content, text="Aguardando arquivos...", font=("Segoe UI", 9))
        self.lbl_status.pack(anchor=tk.W, pady=(2, 0))

        frame_grade = ttk.Frame(content)
        frame_grade.pack(fill=tk.BOTH, expand=True, pady=(4, 2))

        colunas = ("SEL", "USAR", "STATUS", "QTD", "UF", "CFOP", "TIPO",
                   "CST ICMS", "ICMS%", "RED.BC%", "FCP%", "MVA ST%", "ICMS ST%",
                   "CBENEF", "C.CRED", "P.CRED",
                   "CST PIS", "PIS%", "CST COF", "COF%",
                   "C.CLASSE RT", "CST RT", "IBS%", "CBS%",
                   "FAIXA XML", "FAIXA ERP", "RT ERP")

        self._sort_directions = {col: False for col in colunas}
        # show="tree headings": a coluna #0 (árvore) exibe o NCM-pai e ganha o [+] para
        # expandir as regras-filhas que vieram no XML.
        self.tree = ttk.Treeview(frame_grade, columns=colunas, show="tree headings", height=12)

        self.tree.heading("#0", text="NCM  /  REGRA (XML)")
        # 280px numa tela de 1024 é 27% da largura só para a primeira coluna
        self.tree.column("#0", width=280 if self.winfo_screenwidth() >= 1300 else 200,
                         minwidth=140, anchor=tk.W, stretch=False)

        larguras = [34, 44, 90, 45, 36, 46, 42,
                    60, 55, 55, 45, 55, 60,
                    70, 60, 55,
                    55, 50, 55, 50,
                    80, 55, 45, 45,
                    75, 75, 70]

        for col, larg in zip(colunas, larguras):
            self.tree.heading(col, text=col + " ↕", command=lambda c=col: self._sort_treeview(c))
            self.tree.column(col, width=larg, anchor=tk.CENTER, stretch=False)

        # Cores por status do NCM-pai
        self.tree.tag_configure('NOVO', background='#EAFAF1', foreground='#16A34A')
        self.tree.tag_configure('DIFERENTE', background='#FEF9E7', foreground='#D35400')
        self.tree.tag_configure('OK', background='#FFFFFF', foreground='black')
        # Linhas-filhas (variações)
        self.tree.tag_configure('variacao', background='#FBFCFE', foreground='#334155')
        self.tree.tag_configure('eleita', background='#E7F1FF', foreground='#0B4DA2')

        # grid em vez de pack: com pack, a barra horizontal atravessava por baixo da
        # vertical e o canto ficava sobreposto. As 27 colunas somam ~1.800px, então a
        # barra horizontal não é opcional — é a única forma de chegar em RT ERP.
        scroll_y = ttk.Scrollbar(frame_grade, orient=tk.VERTICAL, command=self.tree.yview)
        scroll_x = ttk.Scrollbar(frame_grade, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscroll=scroll_y.set, xscroll=scroll_x.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        frame_grade.grid_rowconfigure(0, weight=1)
        frame_grade.grid_columnconfigure(0, weight=1)

        self.tree.bind("<Button-1>", self._on_tree_click)

        frame_botoes = ttk.Frame(content)
        frame_botoes.pack(fill=tk.X, pady=5)

        ttk.Button(frame_botoes, text="☑ Selecionar Todos", command=self._selecionar_todos).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_botoes, text="☐ Desmarcar Todos", command=self._desmarcar_todos).pack(side=tk.LEFT, padx=2)

        # o formato dos cards acompanha a altura da janela
        self.bind("<Configure>", self._ajustar_cards)
        self.after(60, self._ajustar_cards)

    def _criar_card(self, parent, titulo, valor_inicial, bg_color, border_color, text_color, command):
        """Card clicável de contagem. O formato é decidido em `_ajustar_cards`."""
        card = tk.Frame(parent, bg=bg_color, highlightbackground=border_color,
                        highlightthickness=1, padx=12, pady=6, cursor="hand2")
        lbl_titulo = tk.Label(card, text=titulo, font=("Segoe UI", 9, "bold"),
                              bg=bg_color, fg=text_color, cursor="hand2")
        lbl_valor = tk.Label(card, text=valor_inicial, font=("Segoe UI", 22, "bold"),
                             bg=bg_color, fg=text_color, cursor="hand2")
        card.lbl_valor = lbl_valor
        card.lbl_titulo = lbl_titulo
        for widget in (card, lbl_titulo, lbl_valor):
            widget.bind("<Button-1>", command)
        self._cards.append(card)
        return card

    def _ajustar_cards(self, event=None):
        """Compacta os cards quando a altura disponível é pequena.

        O número em corpo 22 com o título acima dá um card de ~85px; três deles mais as
        duas barras não deixavam espaço para a grade. Em janela baixa o título vai para
        o lado do número e o card cai para ~40px — duas linhas de grade a mais.

        A decisão é pela altura da JANELA, não do monitor: quem tem tela grande mas
        trabalha com a janela pela metade tinha o mesmo problema, e olhar
        `winfo_screenheight()` não via isso.
        """
        compacto = self.winfo_height() < 780
        if compacto == getattr(self, '_cards_compactos', None):
            return
        self._cards_compactos = compacto
        for card in getattr(self, '_cards', []):
            card.lbl_titulo.pack_forget()
            card.lbl_valor.pack_forget()
            card.config(pady=3 if compacto else 6)
            card.lbl_valor.config(font=("Segoe UI", 16 if compacto else 22, "bold"))
            if compacto:
                card.lbl_valor.pack(side=tk.LEFT)
                card.lbl_titulo.pack(side=tk.LEFT, padx=(8, 0))
            else:
                card.lbl_titulo.pack(anchor=tk.W)
                card.lbl_valor.pack(anchor=tk.W)

    def _filtrar_por_card(self, status_selecionado):
        self.card_vermelho.config(highlightthickness=3 if status_selecionado == "NOVO" else 1)
        self.card_amarelo.config(highlightthickness=3 if status_selecionado == "DIFERENTE" else 1)
        self.card_verde.config(highlightthickness=3 if status_selecionado == "OK" else 1)
        
        self.var_status_filtro.set(status_selecionado)
        self._filtrar_treeview()

    # ------------------------------------------------------ ORGANIZAR OS NCMs
    def _ordem_salva(self):
        """Ordem guardada no config.ini, ou 'Pendentes primeiro'.

        O padrão é pendentes primeiro porque é o que se vem fazer nesta tela: os NOVOS
        e DIVERGENTES são o trabalho; os OK são só confirmação.
        """
        salva = self.config.get('TRIBUTACAO_NCM', 'ordenacao', fallback=ORDEM_PENDENTES)
        return salva if salva in ORDENS else ORDEM_PENDENTES

    def _on_ordem_mudou(self):
        if not self.config.has_section('TRIBUTACAO_NCM'):
            self.config.add_section('TRIBUTACAO_NCM')
        self.config.set('TRIBUTACAO_NCM', 'ordenacao', self.var_ordem.get())
        try:
            with open('config.ini', 'w', encoding='utf-8') as f:
                self.config.write(f)
        except Exception:
            pass          # não poder gravar a preferência não impede de ordenar
        self._filtrar_treeview()

    @staticmethod
    def _ncm_num(node):
        """O NCM como número, para '0201.10.00' e '02011000' ordenarem juntos."""
        d = re.sub(r'\D', '', str(node.get('ncm') or ''))
        return int(d) if d else 0

    @staticmethod
    def _total_ocorrencias(node):
        return sum(int(v.get('ocorrencias') or 0) for v in node.get('variacoes', []))

    def _ordenar_nodes(self, nodes):
        """Aplica a ordem escolhida no combo. O NCM sempre entra como desempate,
        para a grade não trocar de ordem entre duas renderizações iguais."""
        modo = self.var_ordem.get()
        if modo == ORDEM_NCM:
            return sorted(nodes, key=self._ncm_num)
        if modo == ORDEM_NCM_DESC:
            return sorted(nodes, key=self._ncm_num, reverse=True)
        if modo == ORDEM_USO:
            return sorted(nodes, key=lambda n: (-self._total_ocorrencias(n), self._ncm_num(n)))
        if modo == ORDEM_REGRAS:
            return sorted(nodes, key=lambda n: (-len(n.get('variacoes', [])),
                                                -self._total_ocorrencias(n), self._ncm_num(n)))
        if modo == ORDEM_DESCRICAO:
            return sorted(nodes, key=lambda n: (str(n.get('descricao') or '').strip().lower(),
                                                self._ncm_num(n)))
        # ORDEM_PENDENTES: NOVO, depois DIFERENTE, depois OK; dentro de cada bloco,
        # o mais usado nas notas primeiro — é a fila de trabalho.
        return sorted(nodes, key=lambda n: (PESO_STATUS.get(n.get('status'), 3),
                                            -self._total_ocorrencias(n), self._ncm_num(n)))

    def _abrir_todos(self, abrir=True):
        """Expande ou recolhe todos os NCMs de uma vez."""
        for iid in self.tree.get_children(''):
            self.tree.item(iid, open=bool(abrir))

    def _atualizar_contadores(self):
        nodes = getattr(self, 'ncm_nodes', [])
        novos = sum(1 for n in nodes if n['status'] == "NOVO")
        diferentes = sum(1 for n in nodes if n['status'] == "DIFERENTE")
        ok = sum(1 for n in nodes if n['status'] == "OK")

        if hasattr(self, 'card_vermelho'):
            self.card_vermelho.lbl_valor.config(text=str(novos))
            self.card_amarelo.lbl_valor.config(text=str(diferentes))
            self.card_verde.lbl_valor.config(text=str(ok))

    def _atualizar_progresso(self, valor, texto):
        if hasattr(self, 'progresso'):
            self.progresso['value'] = valor
        self.lbl_status.config(text=texto)

    def _sort_treeview(self, col):
        """Ordena apenas as linhas-pai (NCM); as filhas seguem o pai automaticamente."""
        self._sort_directions[col] = not self._sort_directions[col]
        reverse = self._sort_directions[col]

        pais = [k for k in self.tree.get_children('') if k in getattr(self, 'item_node', {})]

        def valor_para_ordenar(pai_id):
            v = str(self.tree.set(pai_id, col)).replace('%', '').replace('→', '').strip()
            if not v or v == '-':
                return (2, 0.0, '')
            try:
                return (0, float(v.replace(',', '.')), '')
            except ValueError:
                return (1, 0.0, v.lower())

        pais.sort(key=valor_para_ordenar, reverse=reverse)

        for index, pai_id in enumerate(pais):
            self.tree.move(pai_id, '', index)

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

    def _rt_id(self, valor):
        """Extrai o ID inteiro da regra de Reforma Tributária (TRT_ID) ou None."""
        s = str(valor or '').strip()
        if not s or s in ('-', '*VÁRIOS*'):
            return None
        s = s.split(',')[0].split(' / ')[0].split(' - ')[0].strip()
        try:
            return int(s)
        except ValueError:
            return None

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
                dcst, dcbenef, daliquota = r['_cst_sn'], r['_cbenef_sn'], r['_alq_sn']
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

    def _status_do_ncm(self, node):
        """Status do NCM comparando a regra ELEITA com o que já está no ERP."""
        if not node['existe']:
            return "NOVO"
        eleita = node['variacoes'][node['escolhido_idx']]
        faixa_xml = eleita.get('faixa_xml')
        if faixa_xml and str(faixa_xml) != str(node['faixa_erp']):
            return "DIFERENTE"
        pis_xml = str(eleita.get('pis_alq'))
        if pis_xml not in ('-', '*VÁRIOS*') and str(node['pis_erp']) not in ('-', '') \
                and pis_xml != str(node['pis_erp']):
            return "DIFERENTE"
        cof_xml = str(eleita.get('cofins_alq'))
        if cof_xml not in ('-', '*VÁRIOS*') and str(node['cofins_erp']) not in ('-', '') \
                and cof_xml != str(node['cofins_erp']):
            return "DIFERENTE"
        return "OK"

    def _on_tree_click(self, event):
        if not self.edit_mode_enabled:
            return

        region = self.tree.identify_region(event.x, event.y)
        if region not in ("cell", "tree"):
            return
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return
        column = self.tree.identify_column(event.x)  # '#0' = árvore; '#1' = SEL; '#2' = USAR

        # Linha-PAI (NCM): coluna SEL marca/desmarca o NCM para gravação
        if item_id in getattr(self, 'item_node', {}):
            node = self.item_node[item_id]
            if column == "#1":  # SEL
                node['selecionado'] = not node['selecionado']
                self.tree.set(item_id, "SEL", '☑' if node['selecionado'] else '☐')
                self._atualizar_selecionados()
                return "break"
            return

        # Linha-FILHA (variação): clicar em USAR ou no rótulo elege a regra do NCM
        if item_id in getattr(self, 'item_var', {}):
            node, i = self.item_var[item_id]
            if column in ("#0", "#2"):
                self._eleger_variacao(node, i)
                return "break"
            return

    def _eleger_variacao(self, node, i):
        """Elege a variação i como a regra que vai para o NCM (estilo rádio)."""
        if node.get('escolhido_idx') == i:
            return
        node['escolhido_idx'] = i
        for j, fid in enumerate(node.get('child_iids', [])):
            self.tree.set(fid, "USAR", '●' if j == i else '○')
            self.tree.item(fid, tags=('eleita' if j == i else 'variacao',))
        node['status'] = self._status_do_ncm(node)
        pai = node.get('iid')
        if pai:
            tag_pai = node['status'] if node['status'] in ('NOVO', 'DIFERENTE', 'OK') else 'OK'
            self.tree.item(pai, values=self._valores_pai(node), tags=(tag_pai,))
        self._atualizar_contadores()

    def _atualizar_selecionados(self):
        """Habilita a sincronização quando há pelo menos um NCM marcado."""
        if not self.edit_mode_enabled:
            self.btn_sinc_lote.config(state=tk.DISABLED)
            return
        n = sum(1 for node in getattr(self, 'ncm_nodes', []) if node.get('selecionado'))
        self.selecionados_lote = n
        self.btn_sinc_lote.config(state=tk.NORMAL if n >= 1 else tk.DISABLED)

    def _selecionar_todos(self):
        for pai_id, node in getattr(self, 'item_node', {}).items():
            node['selecionado'] = True
            self.tree.set(pai_id, "SEL", '☑')
        self._atualizar_selecionados()

    def _desmarcar_todos(self):
        for pai_id, node in getattr(self, 'item_node', {}).items():
            node['selecionado'] = False
            self.tree.set(pai_id, "SEL", '☐')
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
                    sql = """SELECT CFIS_CODIGO, CFIS_DESCRICAO, CFIS_ICMS_VENDA, CFIS_PIS, CFIS_COFINS, CFIS_CST_PIS, CFIS_CST_COFINS, CFIS_RT_2025_2026, CFIS_IPI, CFIS_CST_IPI FROM TABELA_class_fiscal"""
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

            # Agrupa as variações (regras-filhas) por NCM para montar a árvore
            por_ncm = {}
            ordem_ncm = []
            for grupo in self.dados_agrupados:
                ncm = grupo['ncm']
                if ncm not in por_ncm:
                    por_ncm[ncm] = []
                    ordem_ncm.append(ncm)
                por_ncm[ncm].append(grupo)

            total_ncms = len(ordem_ncm)
            ncm_nodes = []

            for idx, ncm in enumerate(ordem_ncm):
                if self.cancel_event.is_set():
                    self.parent.after(0, self._finalizar_cancelamento)
                    return

                variacoes = por_ncm[ncm]

                # Dados atuais do ERP (o "como está")
                if escopo == "FILIAL_ATUAL":
                    sys_item = self.dados_sistema.get(ncm)
                    faixa_erp = (sys_item.get('cfis_icms_venda') or '-') if sys_item else '-'
                    pis_erp = (sys_item.get('cfis_pis') if sys_item else None)
                    pis_erp = '-' if pis_erp is None else pis_erp
                    cofins_erp = (sys_item.get('cfis_cofins') if sys_item else None)
                    cofins_erp = '-' if cofins_erp is None else cofins_erp
                    cst_pis_erp = (sys_item.get('cfis_cst_pis') or '') if sys_item else ''
                    cst_cofins_erp = (sys_item.get('cfis_cst_cofins') or '') if sys_item else ''
                    rt_erp = (sys_item.get('cfis_rt_2025_2026') or '-') if sys_item else '-'
                    ipi_erp = (sys_item.get('cfis_ipi') if sys_item else None)
                    ipi_erp = '-' if ipi_erp is None else ipi_erp
                    cst_ipi_erp = (sys_item.get('cfis_cst_ipi') or '') if sys_item else ''
                    desc_sys = sys_item.get('cfis_descricao') if sys_item else None
                    existe = bool(sys_item)
                else:  # UNIFICADO
                    sys_items = self.dados_sistema.get(ncm)
                    if sys_items:
                        faixa_erp = self._get_distinct_from_list(sys_items, 'cfis_icms_venda')
                        pis_erp = self._get_distinct_from_list(sys_items, 'cfis_pis')
                        cofins_erp = self._get_distinct_from_list(sys_items, 'cfis_cofins')
                        cst_pis_erp = self._get_distinct_from_list(sys_items, 'cfis_cst_pis')
                        cst_cofins_erp = self._get_distinct_from_list(sys_items, 'cfis_cst_cofins')
                        rt_erp = self._get_distinct_from_list(sys_items, 'cfis_rt_2025_2026')
                        ipi_erp = self._get_distinct_from_list(sys_items, 'cfis_ipi')
                        cst_ipi_erp = self._get_distinct_from_list(sys_items, 'cfis_cst_ipi')
                        desc_sys = self._get_distinct_from_list(sys_items, 'cfis_descricao')
                    else:
                        faixa_erp = pis_erp = cofins_erp = rt_erp = ipi_erp = '-'
                        cst_pis_erp = cst_cofins_erp = cst_ipi_erp = ''
                        desc_sys = None
                    existe = bool(sys_items)

                # Enriquecer cada variação com a faixa/RT que ela casa no ERP.
                # Usa os itens CRUS do XML (float ok); o dict do grupo tem '-'/'*VÁRIOS*'.
                for v in variacoes:
                    faixas = set()
                    rts = set()
                    for it in v['itens_originais']:
                        fx = self._buscar_faixa_para_ncm(it)
                        if fx:
                            faixas.add(str(fx))
                        rt = self._buscar_regra_rt(it)
                        if rt and rt != '-':
                            rts.add(rt)
                    v['faixa_xml'] = sorted(faixas, key=lambda x: int(x) if x.isdigit() else x)[0] if faixas else None
                    v['regra_rt'] = ", ".join(sorted(rts)) if rts else '-'

                # Eleição padrão = variação com mais ocorrências (predominante)
                escolhido_idx = max(range(len(variacoes)),
                                    key=lambda i: variacoes[i]['ocorrencias'])

                desc_oficial = getattr(self, 'ncm_governo', {}).get(ncm)
                desc_exib = desc_oficial or desc_sys or variacoes[0]['descricao']

                node = {
                    'ncm': ncm,
                    'descricao': desc_exib,
                    'existe': existe,
                    'variacoes': variacoes,
                    'escolhido_idx': escolhido_idx,
                    'faixa_erp': faixa_erp,
                    'pis_erp': pis_erp,
                    'cofins_erp': cofins_erp,
                    'cst_pis_erp': cst_pis_erp,
                    'cst_cofins_erp': cst_cofins_erp,
                    'rt_erp': rt_erp,
                    'ipi_erp': ipi_erp,
                    'cst_ipi_erp': cst_ipi_erp,
                    'selecionado': False,
                }
                node['status'] = self._status_do_ncm(node)
                ncm_nodes.append(node)

                if idx % max(1, total_ncms // 20 or 1) == 0:
                    self.parent.after(0, self._atualizar_progresso,
                                      40 + (idx / max(1, total_ncms)) * 55,
                                      f"Cruzando NCMs: {idx}/{total_ncms}")

            self.parent.after(0, self._atualizar_progresso, 95, "Renderizando Tabela Visual...")
            self.parent.after(0, lambda n=ncm_nodes: self._renderizar_resultados(n))
        except Exception as e:
            self.parent.after(0, lambda e=e: messagebox.showerror("Erro", str(e)))
            self.parent.after(0, lambda: self.btn_analisar.config(state=tk.NORMAL))

    def _get_tax_key(self, item):
        """Gera chave única de tributação para sub-agrupamento.

        Inclui UF + tipo de cliente porque são determinantes da faixa de ICMS;
        assim cada 'regra-filha' vira uma combinação limpa que casa com UMA faixa.
        """
        uf = str(item.get('uf_dest', '')).strip().upper() or '--'
        tipo = str(item.get('tipo_cliente', '')).strip().upper() or 'CT'
        icms_cst = str(item.get('icms_cst', '')).strip() or '00'
        p_icms = str(item.get('p_icms', '0')).strip()
        p_red_bc = str(item.get('p_red_bc', '0')).strip()
        c_benef = str(item.get('c_benef', '')).strip()
        pis_cst = str(item.get('pis_cst', '')).strip() or '00'
        p_pis = str(item.get('p_pis', '0')).strip()
        cofins_cst = str(item.get('cofins_cst', '')).strip() or '00'
        p_cofins = str(item.get('p_cofins', '0')).strip()
        cfop = str(item.get('cfop', '')).strip() or '0000'
        return f"{uf}|{tipo}|{icms_cst}|{p_icms}|{p_red_bc}|{c_benef}|{pis_cst}|{p_pis}|{cofins_cst}|{p_cofins}|{cfop}"

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
                    'ipi_cst': self._get_distinct_from_list(sub_itens, 'ipi_cst'),
                    'ipi_alq': self._get_distinct_from_list(sub_itens, 'p_ipi'),
                    'c_class_trib': self._get_distinct_from_list(sub_itens, 'c_class_trib'),
                    'ibscbs_cst': self._get_distinct_from_list(sub_itens, 'ibscbs_cst'),
                    'p_ibs_uf': self._get_distinct_from_list(sub_itens, 'p_ibs_uf'),
                    'p_cbs': self._get_distinct_from_list(sub_itens, 'p_cbs'),
                    'itens_originais': sub_itens
                }
                dados_agrupados.append(grupo)
        return dados_agrupados

    def _renderizar_resultados(self, ncm_nodes):
        self.ncm_nodes = ncm_nodes
        self.btn_analisar.config(state=tk.NORMAL)
        self.btn_cancelar.config(state=tk.DISABLED)
        self.btn_exportar.config(state=tk.NORMAL)
        self._atualizar_progresso(100, "Renderizando tabela...")
        self._atualizar_contadores()
        self._filtrar_treeview()

    @staticmethod
    def _pct(valor):
        s = str(valor)
        if s in ('', '-', '*VÁRIOS*', 'None'):
            return s if s in ('-', '*VÁRIOS*') else '-'
        return f"{s}%"

    def _valores_pai(self, node):
        eleita = node['variacoes'][node['escolhido_idx']]
        faixa_eleita = eleita.get('faixa_xml') or '-'
        n = len(node['variacoes'])
        total = sum(int(v['ocorrencias']) for v in node['variacoes'])
        sel = '☑' if node.get('selecionado') else '☐'
        usar = f"{n} reg" if n != 1 else "1 reg"
        return (
            sel, usar, node['status'], total,
            '', '', '',
            '', '', '', '', '', '',
            '', '', '',
            '', '', '', '',
            '', '', '', '',
            f"→ {faixa_eleita}", node['faixa_erp'], node['rt_erp'],
        )

    def _valores_filho(self, node, i):
        v = node['variacoes'][i]
        usar = '●' if i == node['escolhido_idx'] else '○'
        return (
            '', usar, '', v['ocorrencias'],
            v['uf_dest'], v['cfop'], v['tipo_cliente'],
            v['icms_cst'], self._pct(v['p_icms']), self._pct(v['p_red_bc']),
            self._pct(v['p_fcp']), self._pct(v['p_mvast']), self._pct(v['p_icmsst']),
            v['c_benef'] or '-', v['c_cred'] or '-', self._pct(v['p_cred']),
            self._formatar_cst(v['pis_cst']), self._pct(v['pis_alq']),
            self._formatar_cst(v['cofins_cst']), self._pct(v['cofins_alq']),
            v['c_class_trib'] or '-', v['ibscbs_cst'] or '-',
            self._pct(v['p_ibs_uf']), self._pct(v['p_cbs']),
            v.get('faixa_xml') or '-', '', v.get('regra_rt') or '-',
        )

    def _filtrar_treeview(self):
        if not hasattr(self, 'ncm_nodes'):
            return
        filtro = self.var_filtro.get().strip().lower()
        filtro_ncm = self.var_filtro_ncm.get().strip().lower()
        filtro_uf = self.var_filtro_uf.get().strip().lower()
        filtro_cfop = self.var_filtro_cfop.get().strip().lower()
        status = self.var_status_filtro.get()

        self.tree.delete(*self.tree.get_children())
        self.item_node = {}
        self.item_var = {}

        exibidos = 0
        # a ordem é aplicada aqui, na renderização, para não se perder ao filtrar
        for node in self._ordenar_nodes(self.ncm_nodes):
            if status != "Todos" and node['status'] != status:
                continue
            if filtro_ncm and filtro_ncm not in str(node['ncm']).lower():
                continue
            variacoes = node['variacoes']
            # NCM com uma regra só não tem conflito para resolver; poder esconder
            # esses deixa na tela apenas o que precisa de decisão
            if self.var_so_multiplas.get() and len(variacoes) < 2:
                continue
            if filtro_uf and not any(filtro_uf in str(v['uf_dest']).lower() for v in variacoes):
                continue
            if filtro_cfop and not any(filtro_cfop in str(v['cfop']).lower() for v in variacoes):
                continue
            if filtro:
                alvo = [str(node['ncm']), str(node['descricao'])]
                for v in variacoes:
                    alvo += [str(v['uf_dest']), str(v['cfop']), str(v['tipo_cliente'])]
                if not any(filtro in t.lower() for t in alvo):
                    continue

            tag_pai = node['status'] if node['status'] in ('NOVO', 'DIFERENTE', 'OK') else 'OK'
            texto_pai = f"{node['ncm']}   ·   {node['descricao']}"
            pai_id = self.tree.insert("", tk.END, text=texto_pai,
                                      values=self._valores_pai(node), tags=(tag_pai,), open=False)
            self.item_node[pai_id] = node
            node['iid'] = pai_id
            node['child_iids'] = []
            for i, v in enumerate(variacoes):
                tag_f = 'eleita' if i == node['escolhido_idx'] else 'variacao'
                texto_f = f"    {v['descricao']}  —  {v['uf_dest']}/{v['tipo_cliente']}"
                fid = self.tree.insert(pai_id, tk.END, text=texto_f,
                                       values=self._valores_filho(node, i), tags=(tag_f,))
                self.item_var[fid] = (node, i)
                node['child_iids'].append(fid)
            exibidos += 1

        total = len(self.ncm_nodes)
        sufixo = "" if exibidos == total else f" de {total}"
        self.lbl_status.config(
            text=f"Pronto. {exibidos} NCM(s) exibidos{sufixo} · ordem: {self.var_ordem.get()}")

    def _limpar_filtro(self):
        self.var_filtro.set("")
        self.var_filtro_ncm.set("")
        self.var_filtro_uf.set("")
        self.var_filtro_cfop.set("")
        self.var_status_filtro.set("Todos")
        self.var_so_multiplas.set(False)
        # a ordem NÃO é filtro: limpar filtro não desfaz a organização escolhida
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
                                 (SELECT CAST(? AS VARCHAR(10)) AS NCM_CODIGO, CAST(? AS VARCHAR(250)) AS NCM_DESCRICAO FROM RDB$DATABASE) S
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
                writer.writerow((
                    "NCM", "DESCRIÇÃO", "STATUS", "ELEITA", "QTD", "UF", "CFOP", "TIPO",
                    "CST ICMS", "ICMS%", "RED.BC%", "FCP%", "MVA ST%", "ICMS ST%",
                    "CBENEF", "C.CRED", "P.CRED",
                    "CST PIS", "PIS%", "CST COF", "COF%",
                    "C.CLASSE RT", "CST RT", "IBS%", "CBS%",
                    "FAIXA XML", "REGRA RT", "FAIXA ERP (atual)", "RT ERP (atual)"))
                for node in getattr(self, 'ncm_nodes', []):
                    for i, v in enumerate(node['variacoes']):
                        writer.writerow((
                            node['ncm'], node['descricao'], node['status'],
                            'SIM' if i == node['escolhido_idx'] else '',
                            v['ocorrencias'], v['uf_dest'], v['cfop'], v['tipo_cliente'],
                            v['icms_cst'], v['p_icms'], v['p_red_bc'], v['p_fcp'], v['p_mvast'], v['p_icmsst'],
                            v['c_benef'], v['c_cred'], v['p_cred'],
                            v['pis_cst'], v['pis_alq'], v['cofins_cst'], v['cofins_alq'],
                            v['c_class_trib'], v['ibscbs_cst'], v['p_ibs_uf'], v['p_cbs'],
                            v.get('faixa_xml') or '', v.get('regra_rt') or '',
                            node['faixa_erp'], node['rt_erp'],
                        ))
            messagebox.showinfo("Sucesso", "CSV exportado!")
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def _sincronizar_lote(self):
        selecionados = [node for node in getattr(self, 'ncm_nodes', []) if node.get('selecionado')]
        if not selecionados:
            return messagebox.showwarning("Aviso", "Marque ao menos um NCM (coluna SEL) para sincronizar.")

        registros_para_salvar = []
        nao_usadas = []
        combos_icms = {}   # faixas ICMS a criar (dedupe por UF/CST/alíquota/redução)
        combos_rt = {}     # regras RT a criar (dedupe por classe/CST/IBS/CBS)

        for node in selecionados:
            eleita = node['variacoes'][node['escolhido_idx']]
            ncm_limpo = node['ncm']

            faixa = eleita.get('faixa_xml') or ''
            pis = self._extrair_float(eleita.get('pis_alq'))
            cofins = self._extrair_float(eleita.get('cofins_alq'))
            cst_pis = self._extrair_cst(eleita.get('pis_cst', ''))
            cst_cofins = self._extrair_cst(eleita.get('cofins_cst', ''))
            reforma_faixa = eleita.get('regra_rt') if eleita.get('regra_rt') not in (None, '-') else ''

            # IPI: usa o que veio no XML; se não veio, fallback CST 53 / alíquota 0
            ipi_cst = self._extrair_cst(eleita.get('ipi_cst', '')) or '53'
            ipi_alq = self._extrair_float(eleita.get('ipi_alq'))

            reg = {
                'ncm': ncm_limpo,
                'status': 'NOVO' if not node['existe'] else 'OK',
                'descricao': str(node['descricao'])[:200],
                'faixa_sugerida': faixa,
                'pis_sugerido': pis,
                'cofins_sugerido': cofins,
                'cst_pis': cst_pis,
                'cst_cofins': cst_cofins,
                'ipi_cst': ipi_cst,
                'ipi_alq': ipi_alq,
                'reforma_faixa_sugerida': reforma_faixa,
                'cfis_subst_tributaria': 'S' if self._extrair_float(eleita.get('p_icmsst')) > 0 else 'N',
                'cfis_st_compra': 'S' if self._extrair_float(eleita.get('p_icmsst')) > 0 else 'N',
                # Estado atual no ERP ("como está") para a tela de conferência
                '_antes': {
                    'existe': node['existe'],
                    'faixa': node['faixa_erp'], 'rt': node['rt_erp'],
                    'pis': node['pis_erp'], 'cst_pis': node['cst_pis_erp'],
                    'cofins': node['cofins_erp'], 'cst_cofins': node['cst_cofins_erp'],
                    'ipi': node['ipi_erp'], 'cst_ipi': node['cst_ipi_erp'],
                },
            }

            # Faixa ICMS a CRIAR: regra eleita não casou nenhuma faixa mas tem ICMS
            icms_cst_raw = str(eleita.get('icms_cst', '')).strip()
            if not faixa and icms_cst_raw and icms_cst_raw not in ('-', '*VÁRIOS*'):
                uf = str(eleita.get('uf_dest', '')).strip().upper()
                cst3 = icms_cst_raw.replace('.', '').lstrip('0').zfill(3)
                aliq = self._extrair_float(eleita.get('p_icms'))
                red = self._extrair_float(eleita.get('p_red_bc'))
                cbenef = str(eleita.get('c_benef', '') or '').strip().upper()
                tipo = str(eleita.get('tipo_cliente', 'CT') or 'CT').strip().upper()
                if tipo not in ('CT', 'NC', 'SN'):
                    tipo = 'CT'
                # CBENEF faz parte da regra → entra na chave (faixas com benefício são distintas)
                ck = f"{uf}|{cst3}|{round(aliq, 2)}|{round(red, 2)}|{cbenef}"
                if ck not in combos_icms:
                    combos_icms[ck] = {'key': ck, 'uf': uf, 'cst': cst3, 'aliquota': aliq,
                                       'reducao': red, 'cbenef': cbenef, 'tipos': set(), 'qtd': 0}
                combos_icms[ck]['qtd'] += 1
                combos_icms[ck]['tipos'].add(tipo)
                reg['_icms_criar_key'] = ck

            # Regra RT a CRIAR: regra eleita não casou nenhuma RT mas tem dados de reforma
            classe = str(eleita.get('c_class_trib', '')).strip()
            if not reforma_faixa and classe and classe not in ('-', '*VÁRIOS*', '0'):
                cst_rt = str(eleita.get('ibscbs_cst', '')).strip()
                ibs = self._extrair_float(eleita.get('p_ibs_uf'))
                cbs = self._extrair_float(eleita.get('p_cbs'))
                rk = f"{classe}|{cst_rt}|{round(ibs, 4)}|{round(cbs, 4)}"
                if rk not in combos_rt:
                    combos_rt[rk] = {'key': rk, 'class': classe, 'cst': cst_rt,
                                     'ibs': ibs, 'cbs': cbs, 'qtd': 0}
                combos_rt[rk]['qtd'] += 1
                reg['_rt_criar_key'] = rk

            registros_para_salvar.append(reg)

            # Variações NÃO eleitas → roteiro para tratar depois em produto/CFOP
            for i, v in enumerate(node['variacoes']):
                if i == node['escolhido_idx']:
                    continue
                nao_usadas.append({
                    'ncm': ncm_limpo, 'uf': v['uf_dest'], 'cfop': v['cfop'],
                    'tipo': v['tipo_cliente'], 'icms_cst': v['icms_cst'],
                    'p_icms': v['p_icms'], 'p_red_bc': v['p_red_bc'],
                    'c_benef': v['c_benef'], 'faixa': v.get('faixa_xml') or '',
                    'pis_cst': v['pis_cst'], 'pis': v['pis_alq'],
                    'cofins_cst': v['cofins_cst'], 'cofins': v['cofins_alq'],
                    'regra_rt': v.get('regra_rt') or '', 'ocorrencias': v['ocorrencias'],
                })

        # Números sugeridos (próximo livre) para o que será criado
        prox_faixa, prox_rt = self._proximos_numeros()
        for i, info in enumerate(combos_icms.values()):
            info['sugerido'] = prox_faixa + i
        for i, info in enumerate(combos_rt.values()):
            info['sugerido'] = prox_rt + i

        DialogoConfirmacaoAntesDepois(
            self.winfo_toplevel(), registros_para_salvar, nao_usadas,
            self._iniciar_sincronizacao_thread,
            combos_icms=list(combos_icms.values()),
            combos_rt=list(combos_rt.values()),
            callback_editar=self._abrir_edicao_fina
        )

    def _proximos_numeros(self):
        """Consulta o próximo número livre de faixa ICMS e de regra RT."""
        empresa = self.config.get('IMPORTACAO', 'empresa', fallback='1')
        filial = self.config.get('IMPORTACAO', 'filial', fallback='1')
        prox_faixa, prox_rt = 1, 1
        try:
            with FirebirdService(self.config_db) as fb:
                r = fb.query(
                    "SELECT COALESCE(MAX(CAST(AICMS_FAIXA AS INTEGER)), 0) + 1 AS N "
                    "FROM TABELA_ALIQUOTA_ICMS WHERE AICMS_EMPRESA = ? AND AICMS_FILIAL = ?",
                    [empresa, filial])
                prox_faixa = int(r[0]['n']) if r else 1
                r2 = fb.query(
                    "SELECT COALESCE(MAX(CAST(TRT_ID AS INTEGER)), 0) + 1 AS N "
                    "FROM TABELA_RT_CONFIG_2025_2026")
                prox_rt = int(r2[0]['n']) if r2 else 1
        except Exception as e:
            logging.error(f"Erro ao consultar próximos números de faixa/RT: {e}")
        return prox_faixa, prox_rt

    def _abrir_edicao_fina(self, registros):
        """Abre o editor fino (PIS/COFINS/ST) reaproveitando o DialogoPreviewNCM."""
        empresa = self.config.get('IMPORTACAO', 'empresa', fallback='1')
        filial = self.config.get('IMPORTACAO', 'filial', fallback='1')
        DialogoPreviewNCM(
            self.winfo_toplevel(), registros,
            self._iniciar_sincronizacao_thread,
            faixas_icms=self.faixas_icms,
            regras_rt=self.regras_rt,
            config_db=self.config_db,
            empresa=empresa,
            filial=filial
        )

    def _iniciar_sincronizacao_thread(self, registros, faixa_map=None, rt_map=None):
        self.btn_sinc_lote.config(state=tk.DISABLED, text="Sincronizando...")
        self.btn_analisar.config(state=tk.DISABLED)

        threading.Thread(target=self._executar_sincronizacao_bg,
                         args=(registros, faixa_map or {}, rt_map or {}), daemon=True).start()

    def _executar_sincronizacao_bg(self, registros, faixa_map=None, rt_map=None):
        faixa_map = faixa_map or {}
        rt_map = rt_map or {}
        empresa = self.config.get('IMPORTACAO', 'empresa', fallback='1')
        filial = self.config.get('IMPORTACAO', 'filial', fallback='1')

        sucesso_ins = 0
        sucesso_upd = 0
        criados_icms = 0
        criados_rt = 0
        erros = []

        try:
            with FirebirdService(self.config_db) as fb:
                cursor = fb.conn.cursor()

                # 1) Cria as faixas de ICMS novas (uma por combinação, gravando CT/NC/SN)
                faixas_criadas = {}
                data_vig = "01/01/2025"
                sufixos = {'CT': 'CONT', 'NC': 'NCONT', 'SN': 'SIMP_NAC'}
                # Grava por PERFIL usando UPDATE OR INSERT: escrever um perfil não apaga
                # os outros perfis já gravados na mesma faixa/estado (mescla na linha).
                rows_faixa = set()
                for key, info in faixa_map.items():
                    try:
                        cbenef = info.get('cbenef') or None
                        perfis = info.get('perfis', {'CT': True, 'NC': True, 'SN': True})
                        cols = ["AICMS_EMPRESA", "AICMS_FILIAL", "AICMS_DATA", "AICMS_FAIXA",
                                "AICMS_ESTADO", "AICMS_COMPRA_VENDA"]
                        vals = [empresa, filial, data_vig, info['faixa'], info['uf'], 'V']
                        for t in ('CT', 'NC', 'SN'):
                            if not perfis.get(t):
                                continue  # perfil não marcado → não mexe nessa coluna
                            s = sufixos[t]
                            cols += [f"AICMS_SITUACAO_{s}", f"AICMS_ALIQUOTA_{s}",
                                     f"AICMS_REDUCAO_{s}", f"AICMS_CBENEF_{s}"]
                            vals += [info['cst'], info['aliquota'], info['reducao'], cbenef]
                        ph = ", ".join("?" for _ in vals)
                        sql = (f"UPDATE OR INSERT INTO TABELA_ALIQUOTA_ICMS ({', '.join(cols)}) "
                               f"VALUES ({ph}) "
                               "MATCHING (AICMS_EMPRESA, AICMS_FILIAL, AICMS_DATA, AICMS_FAIXA, AICMS_ESTADO)")
                        cursor.execute(sql, vals)
                        faixas_criadas[key] = str(info['faixa'])
                        rows_faixa.add((str(info['faixa']), info['uf']))
                    except Exception as e:
                        erros.append(f"Faixa ICMS {info.get('faixa')} ({info.get('uf')} CST {info.get('cst')}): {e}")
                criados_icms = len(rows_faixa)

                # 2) Cria as regras de RT novas
                rts_criadas = {}
                for key, info in rt_map.items():
                    try:
                        cursor.execute(
                            """INSERT INTO TABELA_RT_CONFIG_2025_2026
                               (TRT_ID, TRT_CLASS_TRIB_ID, TRT_CST, TRT_ALIQ_IBS_ESTADUAL, TRT_ALIQ_CBS)
                               VALUES (?, ?, ?, ?, ?)""",
                            [info['id'], info['class'], info['cst'], info['ibs'], info['cbs']])
                        rts_criadas[key] = str(info['id'])
                        criados_rt += 1
                    except Exception as e:
                        erros.append(f"Regra RT {info.get('id')} (Classe {info.get('class')} CST {info.get('cst')}): {e}")

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
                        # Se essa regra pediu faixa nova, usa a que acabou de ser criada
                        if faixa is None:
                            ck = reg.get('_icms_criar_key')
                            if ck and ck in faixas_criadas:
                                faixa = faixas_criadas[ck]

                        pis_alq = self._extrair_float(str(reg['pis_sugerido']).replace(',', '.'))
                        cofins_alq = self._extrair_float(str(reg['cofins_sugerido']).replace(',', '.'))
                        cst_pis = self._extrair_cst(str(reg['cst_pis']))
                        cst_cofins = self._extrair_cst(str(reg['cst_cofins']))

                        st_saida = reg.get('cfis_subst_tributaria', 'N')
                        st_compra = reg.get('cfis_st_compra', 'N')
                        if st_saida not in ('S', 'N'): st_saida = 'N'
                        if st_compra not in ('S', 'N'): st_compra = 'N'

                        rt_id = self._rt_id(reg.get('reforma_faixa_sugerida'))
                        # Se essa regra pediu RT nova, usa a que acabou de ser criada
                        if rt_id is None:
                            rk = reg.get('_rt_criar_key')
                            if rk and rk in rts_criadas:
                                rt_id = self._rt_id(rts_criadas[rk])

                        # IPI vindo do XML; fallback CST 53 / alíquota 0
                        cst_ipi = self._extrair_cst(str(reg.get('ipi_cst', ''))) or '53'
                        ipi_alq = self._extrair_float(reg.get('ipi_alq', 0))

                        if 'NOVO' in reg['status']:
                            sql_in = """INSERT INTO TABELA_class_fiscal
                                        (CFIS_EMPRESA, CFIS_FILIAL, CFIS_CODIGO, CFIS_DESCRICAO, CFIS_ICMS_VENDA,
                                         CFIS_PIS, CFIS_COFINS, CFIS_CST_PIS, CFIS_CST_COFINS, CFIS_IPI, CFIS_CST_IPI,
                                         CFIS_SUBST_TRIBUTARIA, CFIS_ST_COMPRA, CFIS_RT_2025_2026)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
                            params = (empresa, filial, ncm_fmt, desc_oficial, faixa, pis_alq, cofins_alq, cst_pis, cst_cofins, ipi_alq, cst_ipi, st_saida, st_compra, rt_id)
                            cursor.execute(sql_in, params)
                            sucesso_ins += 1
                        else:
                            campos_up = ["CFIS_DESCRICAO = ?", "CFIS_PIS = ?", "CFIS_COFINS = ?",
                                         "CFIS_CST_PIS = ?", "CFIS_CST_COFINS = ?", "CFIS_IPI = ?", "CFIS_CST_IPI = ?",
                                         "CFIS_SUBST_TRIBUTARIA = ?", "CFIS_ST_COMPRA = ?"]
                            params = [desc_oficial, pis_alq, cofins_alq, cst_pis, cst_cofins, ipi_alq, cst_ipi, st_saida, st_compra]
                            # só grava a faixa ICMS quando a regra eleita achou uma (não apaga a existente)
                            if faixa is not None:
                                campos_up.insert(1, "CFIS_ICMS_VENDA = ?")
                                params.insert(1, faixa)
                            # só grava a faixa RT se o usuário escolheu uma (evita apagar vínculo existente)
                            if rt_id is not None:
                                campos_up.append("CFIS_RT_2025_2026 = ?")
                                params.append(rt_id)
                            sql_up = ("UPDATE TABELA_class_fiscal SET " + ", ".join(campos_up) +
                                      " WHERE CFIS_EMPRESA = ? AND CFIS_FILIAL = ? AND CFIS_CODIGO = ?")
                            params += [empresa, filial, ncm_fmt]
                            cursor.execute(sql_up, params)
                            sucesso_upd += 1
                    except Exception as e:
                        erros.append(f"NCM {ncm_fmt}: {e}")

                fb.conn.commit()
            
            msg_final = (f"Sincronização concluída!\n\n• {sucesso_ins} NCMs inseridos.\n"
                         f"• {sucesso_upd} NCMs atualizados.\n"
                         f"• {criados_icms} faixas ICMS criadas.\n• {criados_rt} regras RT criadas.")
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

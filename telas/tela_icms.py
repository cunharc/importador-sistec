import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import configparser
import threading
from datetime import date
from collections import defaultdict
import os
import sys

from utils.firebird_service import FirebirdService
from utils.xml_reader import parse_nfe_folder, parse_nfe
from utils.importer import FirebirdImporter

class DialogoExportarIcms(tk.Toplevel):
    """Modal flutuante para definir as faixas de ICMS a serem cadastradas."""
    def __init__(self, parent, itens, fb_config, callback_sucesso):
        super().__init__(parent)
        self.title("Definir Faixas de ICMS para Exportação (ERP)")
        self.transient(parent)
        self.grab_set()
        
        # Define o tamanho para 95% da largura e 85% da altura da tela (evitando cobrir a barra de tarefas)
        largura = int(self.winfo_screenwidth() * 0.95)
        altura = int(self.winfo_screenheight() * 0.85)
        x = int((self.winfo_screenwidth() - largura) / 2)
        y = int((self.winfo_screenheight() - altura) / 2)
        self.geometry(f"{largura}x{altura}+{x}+{y}")
            
        icon_path = self.resource_path("icon.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)
        
        self.itens = itens
        self.fb_config = fb_config
        self.callback_sucesso = callback_sucesso
        self.inputs_faixa = {}
        self.inputs_cv = {}
        
        self._criar_widgets()
        self._carregar_config_iniciais()
        
    def resource_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)
        
    def _criar_widgets(self):
        # Painel Divisor (Esquerda: Formulário / Direita: Consulta ERP)
        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        frame_left = ttk.Frame(main_pane)
        main_pane.add(frame_left, weight=6)
        
        frame_right = ttk.Frame(main_pane)
        main_pane.add(frame_right, weight=5)

        # Header Configs
        frame_top = ttk.Frame(frame_left, padding="10")
        frame_top.pack(fill=tk.X)
        
        ttk.Label(frame_top, text="Empresa de Destino:").pack(side=tk.LEFT, padx=5)
        self.ent_empresa = ttk.Entry(frame_top, width=8)
        self.ent_empresa.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(frame_top, text="Filial de Destino:").pack(side=tk.LEFT, padx=5)
        self.ent_filial = ttk.Entry(frame_top, width=8)
        self.ent_filial.pack(side=tk.LEFT, padx=5)
        
        # Checkboxes de Tipos CF
        frame_chk = ttk.LabelFrame(frame_top, text="Gravar regras para quais Tipos de Cliente?", padding="5")
        frame_chk.pack(side=tk.RIGHT, padx=10)
        self.var_ct = tk.BooleanVar(self, value=True)
        self.var_nc = tk.BooleanVar(self, value=True)
        self.var_sn = tk.BooleanVar(self, value=True)
        ttk.Checkbutton(frame_chk, text="Contribuinte (CT)", variable=self.var_ct).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(frame_chk, text="Não Contrib. (NC)", variable=self.var_nc).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(frame_chk, text="Simples Nac. (SN)", variable=self.var_sn).pack(side=tk.LEFT, padx=5)

        # Footer (Empacotado primeiro no BOTTOM para não ser esmagado pela tabela)
        frame_bot = ttk.Frame(frame_left, padding="10")
        frame_bot.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Button(frame_bot, text="❌ Cancelar", command=self.destroy).pack(side=tk.LEFT)
        ttk.Button(frame_bot, text="💾 Gravar no Firebird", command=self._confirmar).pack(side=tk.RIGHT)

        # Tabela Editável
        frame_mid = ttk.LabelFrame(frame_left, text="Itens Selecionados para Inserir", padding="5")
        frame_mid.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        canvas = tk.Canvas(frame_mid)
        scrollbar = ttk.Scrollbar(frame_mid, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Cabeçalhos
        headers = ["Nº Faixa *", "C/V *", "CFOP", "TIPO CLI", "CST", "% ICMS", "% Red", "% FCP", "UF Orig", "UF Dest", "cBenef", "Cód Cred", "% Cred", "% MVA", "% ST"]
        for i, h in enumerate(headers):
            ttk.Label(scrollable_frame, text=h, font=("Segoe UI", 9, "bold")).grid(row=0, column=i, padx=5, pady=5)
            
        for row_idx, item in enumerate(self.itens, start=1):
            ent_faixa = ttk.Entry(scrollable_frame, width=8, font=("Segoe UI", 9, "bold"))
            ent_faixa.grid(row=row_idx, column=0, padx=5, pady=2)
            self.inputs_faixa[item['id']] = ent_faixa
            
            cb_cv = ttk.Combobox(scrollable_frame, values=["C", "V"], width=4, state="readonly", font=("Segoe UI", 9, "bold"))
            if str(item['cfop']).startswith(('5','6','7')):
                cb_cv.set("V")
            elif str(item['cfop']).startswith(('1','2','3')):
                cb_cv.set("C")
            cb_cv.grid(row=row_idx, column=1, padx=5, pady=2)
            self.inputs_cv[item['id']] = cb_cv
            
            ttk.Label(scrollable_frame, text=item['cfop']).grid(row=row_idx, column=2, padx=5)
            ttk.Label(scrollable_frame, text=item.get('tipo_cliente', 'NC')).grid(row=row_idx, column=3, padx=5)
            ttk.Label(scrollable_frame, text=item['icms_cst']).grid(row=row_idx, column=4, padx=5)
            ttk.Label(scrollable_frame, text=f"{item['p_icms']}%").grid(row=row_idx, column=5, padx=5)
            ttk.Label(scrollable_frame, text=f"{item['p_red_bc']}%").grid(row=row_idx, column=6, padx=5)
            ttk.Label(scrollable_frame, text=f"{item['p_fcp']}%").grid(row=row_idx, column=7, padx=5)
            ttk.Label(scrollable_frame, text=item['uf_emit']).grid(row=row_idx, column=8, padx=5)
            ttk.Label(scrollable_frame, text=item['uf_dest']).grid(row=row_idx, column=9, padx=5)
            ttk.Label(scrollable_frame, text=item['c_benef'] or '-').grid(row=row_idx, column=10, padx=5)
            ttk.Label(scrollable_frame, text=item['c_cred'] or '-').grid(row=row_idx, column=11, padx=5)
            ttk.Label(scrollable_frame, text=f"{item['p_cred']}%" if item['p_cred'] else '-').grid(row=row_idx, column=12, padx=5)
            ttk.Label(scrollable_frame, text=f"{item['p_mvast']}%" if item['p_mvast'] else '-').grid(row=row_idx, column=13, padx=5)
            ttk.Label(scrollable_frame, text=f"{item['p_icmsst']}%" if item['p_icmsst'] else '-').grid(row=row_idx, column=14, padx=5)

        # --- LADO DIREITO (Consulta ERP) ---
        frame_right_top = ttk.Frame(frame_right, padding="5")
        frame_right_top.pack(fill=tk.X)
        
        ttk.Label(frame_right_top, text="Faixas Existentes no ERP", font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
        ttk.Button(frame_right_top, text="🔄 Atualizar Consulta", command=self._carregar_faixas_existentes).pack(side=tk.RIGHT)
        
        self.cb_filtro_uf = ttk.Combobox(frame_right_top, width=6, state="readonly")
        self.cb_filtro_uf.pack(side=tk.RIGHT, padx=5)
        self.cb_filtro_uf.bind("<<ComboboxSelected>>", lambda e: self._carregar_faixas_existentes())
        ttk.Label(frame_right_top, text="Filtrar UF:").pack(side=tk.RIGHT)
        
        frame_grid_ext = ttk.Frame(frame_right)
        frame_grid_ext.pack(fill=tk.BOTH, expand=True, pady=5)

        colunas_ext = ("FAIXA", "UF", "C/V", "CST", "% ICMS", "% RED.", "CBENEF", "CÓD. CRED", "% CRED", "TIPOS CF")
        self.tree_ext = ttk.Treeview(frame_grid_ext, columns=colunas_ext, show="headings")
        self._sort_directions_ext = {col: False for col in colunas_ext}
        
        larguras_ext = [50, 40, 40, 50, 60, 60, 80, 80, 60, 100]
        for col, larg in zip(colunas_ext, larguras_ext):
            self.tree_ext.heading(col, text=col + " ↕", command=lambda c=col: self._sort_treeview_ext(c))
            self.tree_ext.column(col, width=larg, anchor=tk.CENTER)
            
        scroll_y_ext = ttk.Scrollbar(frame_grid_ext, orient=tk.VERTICAL, command=self.tree_ext.yview)
        self.tree_ext.configure(yscroll=scroll_y_ext.set)
        
        self.tree_ext.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y_ext.pack(side=tk.RIGHT, fill=tk.Y)

    def _carregar_config_iniciais(self):
        config = configparser.ConfigParser()
        config.read('config.ini', encoding='utf-8')
        empresa = config.get('IMPORTACAO', 'empresa', fallback='1')
        filial = config.get('IMPORTACAO', 'filial', fallback='1')
        
        self.ent_empresa.insert(0, empresa)
        self.ent_empresa.config(state='readonly')
        
        self.ent_filial.insert(0, filial)
        self.ent_filial.config(state='readonly')
        
        # Sugestão de Tipos de Cliente para Gravação
        tipos = set(item.get('tipo_cliente', 'CT') for item in self.itens)
        if 'CT' in tipos and 'NC' not in tipos:
            self.var_ct.set(True)
            self.var_sn.set(True)
            self.var_nc.set(False)
        elif 'NC' in tipos and 'CT' not in tipos:
            self.var_ct.set(False)
            self.var_sn.set(False)
            self.var_nc.set(True)
        else:
            self.var_ct.set(True)
            self.var_sn.set(True)
            self.var_nc.set(True)
            
        # Configurar opções de UF no filtro baseadas no ERP
        self.cb_filtro_uf['values'] = ["TODAS"]
        self.cb_filtro_uf.current(0)
        self._atualizar_filtro_ufs()
        
        # Carregar as faixas na Treeview direita
        self._carregar_faixas_existentes()

    def _atualizar_filtro_ufs(self):
        emp = self.ent_empresa.get().strip()
        fil = self.ent_filial.get().strip()
        if not emp or not fil:
            return
            
        sql = "SELECT DISTINCT AICMS_ESTADO FROM TABELA_ALIQUOTA_ICMS WHERE AICMS_EMPRESA = ? AND AICMS_FILIAL = ?"
        try:
            with FirebirdService(self.fb_config) as fb:
                res = fb.query(sql, [emp, fil])
                ufs = sorted(list(set(r.get('aicms_estado', '').strip() for r in res if r.get('aicms_estado'))))
                if ufs:
                    self.cb_filtro_uf['values'] = ["TODAS"] + ufs
        except Exception:
            pass

    def _sort_treeview_ext(self, col):
        self._sort_directions_ext[col] = not self._sort_directions_ext[col]
        reverse = self._sort_directions_ext[col]
        
        l = [(self.tree_ext.set(k, col), k) for k in self.tree_ext.get_children('')]
        
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
            self.tree_ext.move(k, '', index)
            
        for c in self._sort_directions_ext:
            if c == col:
                arrow = " ▼" if self._sort_directions_ext[c] else " ▲"
            else:
                arrow = " ↕"
            self.tree_ext.heading(c, text=c + arrow, command=lambda x=c: self._sort_treeview_ext(x))

    def _carregar_faixas_existentes(self):
        emp = self.ent_empresa.get().strip()
        fil = self.ent_filial.get().strip()
        uf_filtro = self.cb_filtro_uf.get()
        
        for item in self.tree_ext.get_children():
            self.tree_ext.delete(item)
            
        if not emp or not fil:
            return
            
        sql = """
            SELECT 
                tai.AICMS_FAIXA, tai.AICMS_ESTADO, tai.AICMS_COMPRA_VENDA,
                tai.AICMS_SITUACAO_CONT, tai.AICMS_ALIQUOTA_CONT, tai.AICMS_REDUCAO_CONT, tai.AICMS_CBENEF_CONT,
                tai.AICMS_SITUACAO_NCONT, tai.AICMS_ALIQUOTA_NCONT, tai.AICMS_REDUCAO_NCONT, tai.AICMS_CBENEF_NCONT,
                tai.AICMS_SITUACAO_SIMP_NAC, tai.AICMS_ALIQUOTA_SIMP_NAC, tai.AICMS_REDUCAO_SIMP_NAC, tai.AICMS_CBENEF_SIMP_NAC,
                tc.CBE_C_CREDPRESUMIDO, tc.CBE_P_CREDPRESUMIDO,
                LIST(taic.TACB_TIPO_CF, ', ') as TIPOS_CF
            FROM TABELA_ALIQUOTA_ICMS tai
            LEFT JOIN TABELA_ALIQUOTA_ICMS_CBENEF taic ON 
                tai.AICMS_EMPRESA = taic.TACB_AICMS_EMPRESA AND 
                tai.AICMS_FILIAL = taic.TACB_AICMS_FILIAL AND 
                tai.AICMS_DATA = taic.TACB_AICMS_DATA AND 
                tai.AICMS_FAIXA = taic.TACB_AICMS_FAIXA AND 
                tai.AICMS_ESTADO = taic.TACB_AICMS_ESTADO
            LEFT JOIN TABELA_CBENEF tc ON taic.TACB_CBE_ID = tc.CBE_ID
            WHERE tai.AICMS_EMPRESA = ? AND tai.AICMS_FILIAL = ?
        """
        params = [emp, fil]
        if uf_filtro != "TODAS":
            sql += " AND tai.AICMS_ESTADO = ?"
            params.append(uf_filtro)
            
        sql += """
            GROUP BY 
                tai.AICMS_FAIXA, tai.AICMS_ESTADO, tai.AICMS_COMPRA_VENDA,
                tai.AICMS_SITUACAO_CONT, tai.AICMS_ALIQUOTA_CONT, tai.AICMS_REDUCAO_CONT, tai.AICMS_CBENEF_CONT,
                tai.AICMS_SITUACAO_NCONT, tai.AICMS_ALIQUOTA_NCONT, tai.AICMS_REDUCAO_NCONT, tai.AICMS_CBENEF_NCONT,
                tai.AICMS_SITUACAO_SIMP_NAC, tai.AICMS_ALIQUOTA_SIMP_NAC, tai.AICMS_REDUCAO_SIMP_NAC, tai.AICMS_CBENEF_SIMP_NAC,
                tc.CBE_C_CREDPRESUMIDO, tc.CBE_P_CREDPRESUMIDO
            ORDER BY tai.AICMS_FAIXA DESC, tai.AICMS_ESTADO
        """
        
        try:
            with FirebirdService(self.fb_config) as fb:
                resultados = fb.query(sql, params)
                
            for r in resultados:
                tipos = []
                if r.get('aicms_situacao_cont'): tipos.append('CT')
                if r.get('aicms_situacao_ncont'): tipos.append('NC')
                if r.get('aicms_situacao_simp_nac'): tipos.append('SN')
                
                self.tree_ext.insert("", tk.END, values=(
                    r.get('aicms_faixa', ''),
                    r.get('aicms_estado', ''),
                    r.get('aicms_compra_venda', ''),
                    r.get('aicms_situacao_cont', ''),
                    f"{r.get('aicms_aliquota_cont') or 0}%",
                    f"{r.get('aicms_reducao_cont') or 0}%",
                    r.get('aicms_cbenef_cont', ''),
                    r.get('cbe_c_credpresumido', ''),
                    f"{r.get('cbe_p_credpresumido')}%" if r.get('cbe_p_credpresumido') else "",
                    ", ".join(tipos) if tipos else "-"
                ))
                
            # Reseta os ícones de ordenação para o padrão ao recarregar a lista
            for col in self._sort_directions_ext:
                self.tree_ext.heading(col, text=col + " ↕")
        except Exception as e:
            pass # Evita exibir pop-ups que irritem o usuário caso a tabela de visualização esteja com alguma conversão errada

    def _confirmar(self):
        emp = self.ent_empresa.get().strip()
        fil = self.ent_filial.get().strip()
        
        if not emp or not fil:
            messagebox.showwarning("Aviso", "Preencha Empresa e Filial de destino.", parent=self)
            return
            
        data_vigencia = date.today().isoformat()
        
        # Busca a última data cadastrada no ERP para evitar a inativação das regras anteriores
        try:
            with FirebirdService(self.fb_config) as fb:
                sql_data = "SELECT MAX(AICMS_DATA) AS MAX_DATA FROM TABELA_ALIQUOTA_ICMS WHERE AICMS_EMPRESA = ? AND AICMS_FILIAL = ?"
                res_data = fb.query(sql_data, [emp, fil])
                if res_data and res_data[0].get('max_data'):
                    dt = res_data[0]['max_data']
                    data_vigencia = dt.isoformat()[:10] if hasattr(dt, 'isoformat') else str(dt)[:10]
        except Exception as e:
            print(f"Aviso ao buscar última data de ICMS: {e}")
            
        regras_export = []
        
        tipos_cf = []
        if self.var_ct.get(): tipos_cf.append('CT')
        if self.var_nc.get(): tipos_cf.append('NC')
        if self.var_sn.get(): tipos_cf.append('SN')

        for item in self.itens:
            faixa = self.inputs_faixa[item['id']].get().strip()
            if not faixa:
                messagebox.showwarning("Aviso", f"Preencha a Faixa para o CFOP {item['cfop']}.", parent=self)
                return
                
            compra_venda = self.inputs_cv[item['id']].get().strip()
            if not compra_venda:
                messagebox.showwarning("Aviso", f"Selecione C/V para o CFOP {item['cfop']}.", parent=self)
                return
                
            cst_limpo = str(item['icms_cst']).replace('.', '').lstrip('0').zfill(3)
            
            aliquota = item['p_icms'] if item['p_icms'] else None
            reducao = item['p_red_bc'] if item['p_red_bc'] else None
            cbenef = item['c_benef'] or None
            c_cred = item['c_cred'] or None
            p_cred = item['p_cred'] if item['p_cred'] else None
            
            regra = {
                'AICMS_EMPRESA': emp, 'AICMS_FILIAL': fil, 'AICMS_DATA': data_vigencia,
                'AICMS_FAIXA': faixa, 'AICMS_ESTADO': item['uf_dest'], 'AICMS_COMPRA_VENDA': compra_venda,
                'CBE_C_CREDPRESUMIDO': c_cred, 'CBE_P_CREDPRESUMIDO': p_cred, 'tipos_cf': tipos_cf
            }
            
            if self.var_ct.get():
                regra['AICMS_ALIQUOTA_CONT'] = aliquota
                regra['AICMS_REDUCAO_CONT'] = reducao
                regra['AICMS_SITUACAO_CONT'] = cst_limpo
                regra['AICMS_CBENEF_CONT'] = cbenef
                
            if self.var_nc.get():
                regra['AICMS_ALIQUOTA_NCONT'] = aliquota
                regra['AICMS_REDUCAO_NCONT'] = reducao
                regra['AICMS_SITUACAO_NCONT'] = cst_limpo
                regra['AICMS_CBENEF_NCONT'] = cbenef
                
            if self.var_sn.get():
                regra['AICMS_ALIQUOTA_SIMP_NAC'] = aliquota
                regra['AICMS_REDUCAO_SIMP_NAC'] = reducao
                regra['AICMS_SITUACAO_SIMP_NAC'] = cst_limpo
                regra['AICMS_CBENEF_SIMP_NAC'] = cbenef
                
            regras_export.append(regra)
            
        try:
            with FirebirdService(self.fb_config) as fb:
                importer = FirebirdImporter(fb)
                res = importer.import_icms(regras_export)
                
                # Força o commit da transação para persistir a gravação no banco de dados
                if hasattr(fb, 'commit'):
                    fb.commit()
                elif hasattr(fb, 'conn') and hasattr(fb.conn, 'commit'):
                    fb.conn.commit()
                elif hasattr(fb, 'connection') and hasattr(fb.connection, 'commit'):
                    fb.connection.commit()
                elif hasattr(fb, 'db') and hasattr(fb.db, 'commit'):
                    fb.db.commit()
                    
            messagebox.showinfo("Sucesso", f"{res['inseridos']} faixas cadastradas com sucesso!", parent=self)
            self.destroy()
            self.callback_sucesso()
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao inserir regras:\n{e}", parent=self)

class DialogoDetalhesFaixa(tk.Toplevel):
    """Modal que exibe os detalhes de faixas de ICMS consultando o ERP."""
    def __init__(self, parent, faixas_str, uf_dest, fb_config):
        super().__init__(parent)
        self.title(f"Detalhes das Faixas de ICMS - ERP (UF: {uf_dest})")
        self.geometry("950x400")
        self.transient(parent)
        self.grab_set()
        
        self.faixas = [f.strip() for f in str(faixas_str).split(',') if f.strip() and f.strip() != '-']
        self.uf_dest = uf_dest
        self.fb_config = fb_config
        
        self._criar_widgets()
        self._carregar_dados()

    def _criar_widgets(self):
        frame_bot = ttk.Frame(self, padding="10")
        frame_bot.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Button(frame_bot, text="Fechar", command=self.destroy).pack(side=tk.RIGHT)

        frame_main = ttk.Frame(self, padding="10")
        frame_main.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        ttk.Label(frame_main, text=f"Analisando Faixa(s): {', '.join(self.faixas)} | Destino: {self.uf_dest}", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W, pady=(0, 10))

        colunas = ("FAIXA", "DATA VIG.", "ESTADO", "C/V", "CST", "% ICMS", "% RED.", "CBENEF", "CÓD. CRED", "% CRED", "TIPOS CF")
        self.tree = ttk.Treeview(frame_main, columns=colunas, show="headings")
        
        larguras = [50, 80, 50, 40, 50, 60, 60, 80, 80, 60, 120]
        for col, larg in zip(colunas, larguras):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=larg, anchor=tk.CENTER)
            
        scroll_y = ttk.Scrollbar(frame_main, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scroll_y.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

    def _carregar_dados(self):
        if not self.faixas:
            return
            
        faixas_param = ", ".join("?" for _ in self.faixas)
        sql = f"""
            SELECT 
                tai.AICMS_FAIXA, tai.AICMS_DATA, tai.AICMS_ESTADO, tai.AICMS_COMPRA_VENDA,
                tai.AICMS_SITUACAO_CONT, tai.AICMS_ALIQUOTA_CONT, tai.AICMS_REDUCAO_CONT, tai.AICMS_CBENEF_CONT,
                tai.AICMS_SITUACAO_NCONT, tai.AICMS_ALIQUOTA_NCONT, tai.AICMS_REDUCAO_NCONT, tai.AICMS_CBENEF_NCONT,
                tai.AICMS_SITUACAO_SIMP_NAC, tai.AICMS_ALIQUOTA_SIMP_NAC, tai.AICMS_REDUCAO_SIMP_NAC, tai.AICMS_CBENEF_SIMP_NAC,
                tc.CBE_C_CREDPRESUMIDO, tc.CBE_P_CREDPRESUMIDO,
                LIST(taic.TACB_TIPO_CF, ', ') as TIPOS_CF
            FROM TABELA_ALIQUOTA_ICMS tai
            LEFT JOIN TABELA_ALIQUOTA_ICMS_CBENEF taic ON 
                tai.AICMS_EMPRESA = taic.TACB_AICMS_EMPRESA AND 
                tai.AICMS_FILIAL = taic.TACB_AICMS_FILIAL AND 
                tai.AICMS_DATA = taic.TACB_AICMS_DATA AND 
                tai.AICMS_FAIXA = taic.TACB_AICMS_FAIXA AND 
                tai.AICMS_ESTADO = taic.TACB_AICMS_ESTADO
            LEFT JOIN TABELA_CBENEF tc ON taic.TACB_CBE_ID = tc.CBE_ID
            WHERE tai.AICMS_FAIXA IN ({faixas_param}) AND tai.AICMS_ESTADO = ?
            GROUP BY 
                tai.AICMS_FAIXA, tai.AICMS_DATA, tai.AICMS_ESTADO, tai.AICMS_COMPRA_VENDA,
                tai.AICMS_SITUACAO_CONT, tai.AICMS_ALIQUOTA_CONT, tai.AICMS_REDUCAO_CONT, tai.AICMS_CBENEF_CONT,
                tai.AICMS_SITUACAO_NCONT, tai.AICMS_ALIQUOTA_NCONT, tai.AICMS_REDUCAO_NCONT, tai.AICMS_CBENEF_NCONT,
                tai.AICMS_SITUACAO_SIMP_NAC, tai.AICMS_ALIQUOTA_SIMP_NAC, tai.AICMS_REDUCAO_SIMP_NAC, tai.AICMS_CBENEF_SIMP_NAC,
                tc.CBE_C_CREDPRESUMIDO, tc.CBE_P_CREDPRESUMIDO
            ORDER BY tai.AICMS_FAIXA, tai.AICMS_DATA DESC
        """
        
        params = self.faixas + [self.uf_dest]
        
        try:
            with FirebirdService(self.fb_config) as fb:
                resultados = fb.query(sql, params)
                
            for r in resultados:
                tipos = []
                if r.get('aicms_situacao_cont'): tipos.append('CT')
                if r.get('aicms_situacao_ncont'): tipos.append('NC')
                if r.get('aicms_situacao_simp_nac'): tipos.append('SN')
                
                self.tree.insert("", tk.END, values=(
                    r.get('aicms_faixa', ''),
                    r.get('aicms_data', ''),
                    r.get('aicms_estado', ''),
                    r.get('aicms_compra_venda', ''),
                    r.get('aicms_situacao_cont', ''),
                    f"{r.get('aicms_aliquota_cont') or 0}%",
                    f"{r.get('aicms_reducao_cont') or 0}%",
                    r.get('aicms_cbenef_cont', ''),
                    r.get('cbe_c_credpresumido', ''),
                    f"{r.get('cbe_p_credpresumido')}%" if r.get('cbe_p_credpresumido') else "",
                    ", ".join(tipos) if tipos else "-"
                ))
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao buscar detalhes:\n{e}", parent=self)

class DialogoFaixasExistentes(tk.Toplevel):
    """Modal que exibe as faixas de ICMS já cadastradas no ERP para a Empresa/Filial configuradas."""
    def __init__(self, parent, fb_config):
        super().__init__(parent)
        self.title("Faixas de ICMS Existentes no ERP")
        self.geometry("950x500")
        self.transient(parent)
        self.grab_set()
        
        icon_path = self.resource_path("icon.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)
            
        config = configparser.ConfigParser()
        config.read('config.ini', encoding='utf-8')
        self.emp = config.get('IMPORTACAO', 'empresa', fallback='1')
        self.fil = config.get('IMPORTACAO', 'filial', fallback='1')
        self.fb_config = fb_config
        
        self._criar_widgets()
        self._carregar_dados()
        
    def resource_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def _criar_widgets(self):
        frame_top = ttk.Frame(self, padding="10")
        frame_top.pack(side=tk.TOP, fill=tk.X)
        
        ttk.Label(frame_top, text=f"Faixas de ICMS (Empresa {self.emp} / Filial {self.fil})", font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
        
        ttk.Button(frame_top, text="🔄 Atualizar", command=self._carregar_dados).pack(side=tk.RIGHT)
        
        self.cb_filtro_uf = ttk.Combobox(frame_top, width=6, state="readonly")
        self.cb_filtro_uf.pack(side=tk.RIGHT, padx=5)
        self.cb_filtro_uf.bind("<<ComboboxSelected>>", lambda e: self._carregar_dados())
        ttk.Label(frame_top, text="Filtrar UF:").pack(side=tk.RIGHT)
        
        frame_grid = ttk.Frame(self, padding="10")
        frame_grid.pack(fill=tk.BOTH, expand=True)

        colunas = ("FAIXA", "UF", "C/V", "CST", "% ICMS", "% RED.", "CBENEF", "CÓD. CRED", "% CRED", "TIPOS CF")
        self.tree = ttk.Treeview(frame_grid, columns=colunas, show="headings")
        self._sort_directions = {col: False for col in colunas}
        
        larguras = [50, 40, 40, 50, 60, 60, 80, 80, 60, 100]
        for col, larg in zip(colunas, larguras):
            self.tree.heading(col, text=col + " ↕", command=lambda c=col: self._sort_treeview(c))
            self.tree.column(col, width=larg, anchor=tk.CENTER)
            
        scroll_y = ttk.Scrollbar(frame_grid, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scroll_y.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        frame_bot = ttk.Frame(self, padding="10")
        frame_bot.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Button(frame_bot, text="Fechar", command=self.destroy).pack(side=tk.RIGHT)
        
        self._atualizar_filtro_ufs()

    def _atualizar_filtro_ufs(self):
        sql = "SELECT DISTINCT AICMS_ESTADO FROM TABELA_ALIQUOTA_ICMS WHERE AICMS_EMPRESA = ? AND AICMS_FILIAL = ?"
        self.cb_filtro_uf['values'] = ["TODAS"]
        self.cb_filtro_uf.current(0)
        try:
            with FirebirdService(self.fb_config) as fb:
                res = fb.query(sql, [self.emp, self.fil])
                ufs = sorted(list(set(r.get('aicms_estado', '').strip() for r in res if r.get('aicms_estado'))))
                if ufs:
                    self.cb_filtro_uf['values'] = ["TODAS"] + ufs
        except Exception:
            pass

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

    def _carregar_dados(self):
        uf_filtro = self.cb_filtro_uf.get()
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        sql = '''
            SELECT 
                tai.AICMS_FAIXA, tai.AICMS_ESTADO, tai.AICMS_COMPRA_VENDA,
                tai.AICMS_SITUACAO_CONT, tai.AICMS_ALIQUOTA_CONT, tai.AICMS_REDUCAO_CONT, tai.AICMS_CBENEF_CONT,
                tai.AICMS_SITUACAO_NCONT, tai.AICMS_ALIQUOTA_NCONT, tai.AICMS_REDUCAO_NCONT, tai.AICMS_CBENEF_NCONT,
                tai.AICMS_SITUACAO_SIMP_NAC, tai.AICMS_ALIQUOTA_SIMP_NAC, tai.AICMS_REDUCAO_SIMP_NAC, tai.AICMS_CBENEF_SIMP_NAC,
                tc.CBE_C_CREDPRESUMIDO, tc.CBE_P_CREDPRESUMIDO,
                LIST(taic.TACB_TIPO_CF, ', ') as TIPOS_CF
            FROM TABELA_ALIQUOTA_ICMS tai
            LEFT JOIN TABELA_ALIQUOTA_ICMS_CBENEF taic ON 
                tai.AICMS_EMPRESA = taic.TACB_AICMS_EMPRESA AND 
                tai.AICMS_FILIAL = taic.TACB_AICMS_FILIAL AND 
                tai.AICMS_DATA = taic.TACB_AICMS_DATA AND 
                tai.AICMS_FAIXA = taic.TACB_AICMS_FAIXA AND 
                tai.AICMS_ESTADO = taic.TACB_AICMS_ESTADO
            LEFT JOIN TABELA_CBENEF tc ON taic.TACB_CBE_ID = tc.CBE_ID
            WHERE tai.AICMS_EMPRESA = ? AND tai.AICMS_FILIAL = ?
        '''
        params = [self.emp, self.fil]
        if uf_filtro != "TODAS":
            sql += " AND tai.AICMS_ESTADO = ?"
            params.append(uf_filtro)
            
        sql += '''
            GROUP BY 
                tai.AICMS_FAIXA, tai.AICMS_ESTADO, tai.AICMS_COMPRA_VENDA,
                tai.AICMS_SITUACAO_CONT, tai.AICMS_ALIQUOTA_CONT, tai.AICMS_REDUCAO_CONT, tai.AICMS_CBENEF_CONT,
                tai.AICMS_SITUACAO_NCONT, tai.AICMS_ALIQUOTA_NCONT, tai.AICMS_REDUCAO_NCONT, tai.AICMS_CBENEF_NCONT,
                tai.AICMS_SITUACAO_SIMP_NAC, tai.AICMS_ALIQUOTA_SIMP_NAC, tai.AICMS_REDUCAO_SIMP_NAC, tai.AICMS_CBENEF_SIMP_NAC,
                tc.CBE_C_CREDPRESUMIDO, tc.CBE_P_CREDPRESUMIDO
            ORDER BY tai.AICMS_FAIXA DESC, tai.AICMS_ESTADO
        '''
        
        try:
            with FirebirdService(self.fb_config) as fb:
                resultados = fb.query(sql, params)
                
            for r in resultados:
                tipos = []
                if r.get('aicms_situacao_cont'): tipos.append('CT')
                if r.get('aicms_situacao_ncont'): tipos.append('NC')
                if r.get('aicms_situacao_simp_nac'): tipos.append('SN')
                
                self.tree.insert("", tk.END, values=(
                    r.get('aicms_faixa', ''),
                    r.get('aicms_estado', ''),
                    r.get('aicms_compra_venda', ''),
                    r.get('aicms_situacao_cont', ''),
                    f"{r.get('aicms_aliquota_cont') or 0}%",
                    f"{r.get('aicms_reducao_cont') or 0}%",
                    r.get('aicms_cbenef_cont', ''),
                    r.get('cbe_c_credpresumido', ''),
                    f"{r.get('cbe_p_credpresumido')}%" if r.get('cbe_p_credpresumido') else "",
                    ", ".join(tipos) if tipos else "-"
                ))
                
            for col in self._sort_directions:
                self.tree.heading(col, text=col + " ↕")
                
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao buscar faixas:\n{e}", parent=self)

class TelaIcms(ttk.Frame):
    def __init__(self, parent, callback_voltar=None):
        super().__init__(parent, padding="10")
        self.parent = parent
        self.callback_voltar = callback_voltar
        self.pack(fill=tk.BOTH, expand=True)

        self.arquivos_selecionados = []
        self.pasta_xmls = ""
        self.dados_grid = {} 
        
        self.colunas = ("SEL", "QTD", "UF ORIG", "UF DEST", "CFOP", "TIPO CLI", "FAIXA ERP", "CST", "% ICMS", "% RED.BC", "% FCP", "CBENEF", "CÓD.CRED", "% CRED", "% MVA", "% ICMS ST")
        self._sort_directions = {col: False for col in self.colunas}
        
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

    def _criar_widgets(self):
        lbl_title = tk.Label(self, text="MATRIZ DE FAIXAS DE ICMS (UF x UF)", font=("Segoe UI", 14, "bold"), fg="#8E44AD")
        lbl_title.pack(anchor=tk.W, pady=(0, 10))

        frame_dir = ttk.Frame(self)
        frame_dir.pack(fill=tk.X, pady=10)
        
        self.ent_pasta = ttk.Entry(frame_dir, width=60)
        self.ent_pasta.pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_dir, text="📁 Pasta", command=self._selecionar_pasta).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_dir, text="📄 Arquivos", command=self._selecionar_arquivos).pack(side=tk.LEFT, padx=2)
        
        self.btn_analisar = ttk.Button(frame_dir, text="🔍 Analisar XMLs", command=self._iniciar_analise)
        self.btn_analisar.pack(side=tk.RIGHT, padx=5)
        
        self.btn_ver_faixas = ttk.Button(frame_dir, text="👁 Ver Faixas no ERP", command=self._ver_faixas_existentes)
        self.btn_ver_faixas.pack(side=tk.RIGHT, padx=5)

        self.lbl_status = ttk.Label(self, text="Aguardando importação...", font=("Segoe UI", 9))
        self.lbl_status.pack(anchor=tk.W)

        # Rodapé (Empacotado primeiro no BOTTOM para garantir que fique visível e não cortado pela barra de tarefas)
        frame_fim = ttk.Frame(self)
        frame_fim.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
        ttk.Button(frame_fim, text="⬅ VOLTAR", command=self._fechar_tela).pack(side=tk.LEFT, padx=5)
        
        self.btn_exportar = ttk.Button(frame_fim, text="🚀 Enviar Selecionados p/ ERP", state=tk.DISABLED, command=self._preparar_exportacao)
        self.btn_exportar.pack(side=tk.RIGHT, padx=5)

        # Grade
        frame_grade = ttk.Frame(self)
        frame_grade.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=10)

        self.tree = ttk.Treeview(frame_grade, columns=self.colunas, show="headings")
        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        
        larguras = [40, 40, 60, 60, 50, 60, 80, 50, 60, 70, 60, 80, 80, 60, 60, 80]
        for col, larg in zip(self.colunas, larguras):
            self.tree.heading(col, text=col + " ↕", command=lambda c=col: self._sort_treeview(c))
            self.tree.column(col, width=larg, anchor=tk.CENTER)

        self.tree.tag_configure('ENCONTRADA', background='#EAFAF1') 

        scroll_y = ttk.Scrollbar(frame_grade, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

    def _selecionar_pasta(self):
        pasta = filedialog.askdirectory()
        if pasta:
            self.ent_pasta.delete(0, tk.END); self.ent_pasta.insert(0, pasta)
            self.pasta_xmls = pasta; self.arquivos_selecionados = []

    def _selecionar_arquivos(self):
        arquivos = filedialog.askopenfilenames(filetypes=[("XML", "*.xml")])
        if arquivos:
            self.ent_pasta.delete(0, tk.END); self.ent_pasta.insert(0, f"{len(arquivos)} arquivo(s) selecionado(s)")
            self.arquivos_selecionados = list(arquivos); self.pasta_xmls = ""

    def _fechar_tela(self):
        self.destroy()
        if self.callback_voltar: self.callback_voltar()
        
    def _ver_faixas_existentes(self):
        DialogoFaixasExistentes(self.parent, self.config_db)

    def _on_tree_click(self, event):
        if self.tree.identify_region(event.x, event.y) == "cell" and self.tree.identify_column(event.x) == "#1":
            item = self.tree.identify_row(event.y)
            valores = list(self.tree.item(item, "values"))
            valores[0] = "☑" if valores[0] == "☐" else "☐"
            self.tree.item(item, values=valores)
            
    def _on_tree_double_click(self, event):
        if self.tree.identify_region(event.x, event.y) == "cell":
            item = self.tree.identify_row(event.y)
            if item:
                valores = self.tree.item(item, "values")
                faixas_str = str(valores[6])
                uf_dest = str(valores[3])
                if faixas_str and faixas_str != '-':
                    DialogoDetalhesFaixa(self.parent, faixas_str, uf_dest, self.config_db)

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
            return messagebox.showwarning("Atenção", "Selecione XMLs válidos.")
            
        self.btn_analisar.config(state=tk.DISABLED)
        self.lbl_status.config(text="Analisando XMLs e extraindo faixas...")
        for item in self.tree.get_children(): self.tree.delete(item)
        threading.Thread(target=self._pipeline_bg, daemon=True).start()

    def _pipeline_bg(self):
        try:
            itens_xml = []
            if self.arquivos_selecionados:
                for arq in self.arquivos_selecionados:
                    try: itens_xml.extend(parse_nfe(arq)['itens'])
                    except: pass
            else:
                itens_xml = parse_nfe_folder(self.pasta_xmls)

            mapa_agrupado = self._agrupar_icms(itens_xml)
            
            # Cruza com o Firebird
            with FirebirdService(self.config_db) as fb:
                sql = """SELECT t1.AICMS_FAIXA, t1.AICMS_ESTADO, t1.AICMS_ALIQUOTA_CONT, t1.AICMS_REDUCAO_CONT, t1.AICMS_SITUACAO_CONT, t1.AICMS_CBENEF_CONT, t1.AICMS_ALIQUOTA_NCONT, t1.AICMS_REDUCAO_NCONT, t1.AICMS_SITUACAO_NCONT, t1.AICMS_CBENEF_NCONT, t1.AICMS_ALIQUOTA_SIMP_NAC, t1.AICMS_REDUCAO_SIMP_NAC, t1.AICMS_SITUACAO_SIMP_NAC, t1.AICMS_CBENEF_SIMP_NAC, t3.CBE_C_CREDPRESUMIDO, t3.CBE_P_CREDPRESUMIDO FROM TABELA_ALIQUOTA_ICMS t1 LEFT JOIN TABELA_ALIQUOTA_ICMS_CBENEF t2 ON t1.AICMS_EMPRESA = t2.TACB_AICMS_EMPRESA AND t1.AICMS_FILIAL = t2.TACB_AICMS_FILIAL AND t1.AICMS_DATA = t2.TACB_AICMS_DATA AND t1.AICMS_FAIXA = t2.TACB_AICMS_FAIXA AND t1.AICMS_ESTADO = t2.TACB_AICMS_ESTADO LEFT JOIN TABELA_CBENEF t3 ON t2.TACB_CBE_ID = t3.CBE_ID"""
                regras_db = fb.query(sql)
                
            for grupo in mapa_agrupado:
                self._cruzar_regras_db(grupo, regras_db)
                
            self.parent.after(0, self._renderizar_resultados, mapa_agrupado)
        except Exception as e:
            self.parent.after(0, lambda: messagebox.showerror("Erro", str(e)))
            self.parent.after(0, lambda: self.btn_analisar.config(state=tk.NORMAL))

    def _agrupar_icms(self, itens):
        mapa = {}
        for i in itens:
            g = i.get('cred_presumidos', [])
            k = f"{i.get('uf_emit','N/I')}|{i.get('uf_dest','EX')}|{i.get('cfop','')}|{i.get('tipo_cliente','CT')}|{i.get('icms_cst','')}|{i.get('p_icms') or 0}|{i.get('p_red_bc') or 0}|{i.get('p_fcp') or 0}|{i.get('c_benef','')}|{g[0].get('c_cred','') if g else ''}|{g[0].get('p_cred',0) if g else 0}|{i.get('p_mvast') or 0}|{i.get('p_icmsst') or 0}"
            if k not in mapa:
                mapa[k] = {
                    'id': f"icms_{len(mapa)}", 'ocorrencias': 1, 
                    'uf_emit': i.get('uf_emit','N/I'), 'uf_dest': i.get('uf_dest','EX'), 
                    'cfop': i.get('cfop',''), 'tipo_cliente': i.get('tipo_cliente', 'CT'),
                    'icms_cst': i.get('icms_cst',''), 
                    'p_icms': i.get('p_icms') or 0, 'p_fcp': i.get('p_fcp') or 0, 
                    'p_red_bc': i.get('p_red_bc') or 0, 'c_benef': i.get('c_benef',''), 
                    'c_cred': g[0].get('c_cred','') if g else '', 'p_cred': g[0].get('p_cred',0) if g else 0,
                    'p_mvast': i.get('p_mvast') or 0, 'p_icmsst': i.get('p_icmsst') or 0,
                    'faixas_erp': '-'
                }
            else: 
                mapa[k]['ocorrencias'] += 1
                
        return sorted(list(mapa.values()), key=lambda x: (x['cfop'], x['icms_cst'], x['uf_dest']))

    def _cruzar_regras_db(self, grupo, regras_db):
        xcst = str(grupo['icms_cst']).replace('.','').lstrip('0').zfill(3)
        xcbenef = str(grupo['c_benef'] or '').strip().upper()
        xccred = str(grupo['c_cred'] or '').strip().upper()
        xpcred = float(grupo['p_cred'] or 0)
        tipo_cli = grupo.get('tipo_cliente', 'CT')
        
        faixas = set()
        for r in regras_db:
            if tipo_cli == 'NC':
                dcst = str(r.get('aicms_situacao_ncont') or '').replace('.','').lstrip('0').zfill(3)
                dcbenef = str(r.get('aicms_cbenef_ncont') or '').strip().upper()
                daliquota = float(r.get('aicms_aliquota_ncont') or 0)
                dreducao = float(r.get('aicms_reducao_ncont') or 0)
            elif tipo_cli == 'SN':
                dcst = str(r.get('aicms_situacao_simp_nac') or '').replace('.','').lstrip('0').zfill(3)
                dcbenef = str(r.get('aicms_cbenef_simp_nac') or '').strip().upper()
                daliquota = float(r.get('aicms_aliquota_simp_nac') or 0)
                dreducao = float(r.get('aicms_reducao_simp_nac') or 0)
            else:
                dcst = str(r.get('aicms_situacao_cont') or '').replace('.','').lstrip('0').zfill(3)
                dcbenef = str(r.get('aicms_cbenef_cont') or '').strip().upper()
                daliquota = float(r.get('aicms_aliquota_cont') or 0)
                dreducao = float(r.get('aicms_reducao_cont') or 0)

            dccred = str(r.get('cbe_c_credpresumido') or '').strip().upper()
            dpcred = float(r.get('cbe_p_credpresumido') or 0)
            
            if (dcst == xcst and abs(daliquota - float(grupo['p_icms'])) < 0.01 and 
                abs(dreducao - float(grupo['p_red_bc'])) < 0.01 and 
                str(r.get('aicms_estado') or '').strip().upper() == str(grupo['uf_dest']).strip().upper() and
                dcbenef == xcbenef and dccred == xccred and abs(dpcred - xpcred) < 0.01):
                faixas.add(str(r.get('aicms_faixa')))
                
        grupo['faixas_erp'] = ", ".join(sorted(list(faixas), key=lambda x: int(x) if x.isdigit() else x)) if faixas else "-"

    def _renderizar_resultados(self, mapa):
        self.dados_grid.clear()
        for r in mapa:
            id_tree = self.tree.insert("", tk.END, values=(
                "☐", r['ocorrencias'], r['uf_emit'], r['uf_dest'], r['cfop'], r['tipo_cliente'], r['faixas_erp'], 
                r['icms_cst'], f"{r['p_icms']}%", f"{r['p_red_bc']}%", f"{r['p_fcp']}%", 
                r['c_benef'], r['c_cred'], f"{r['p_cred']}%", f"{r['p_mvast']}%", f"{r['p_icmsst']}%"
            ), tags=('ENCONTRADA',) if r['faixas_erp'] != '-' else ())
            self.dados_grid[id_tree] = r
        self.btn_analisar.config(state=tk.NORMAL)
        self.btn_exportar.config(state=tk.NORMAL)
        self.lbl_status.config(text=f"Pronto. {len(mapa)} combinações únicas de ICMS encontradas.")

    def _preparar_exportacao(self):
        selecionados = [self.dados_grid[i] for i in self.tree.get_children() if self.tree.set(i, "SEL") == "☑"]
        if not selecionados: return messagebox.showwarning("Aviso", "Selecione regras na tabela (coluna SEL).")
        DialogoExportarIcms(self.parent, selecionados, self.config_db, lambda: self._iniciar_analise())
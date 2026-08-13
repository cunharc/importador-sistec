# -*- coding: utf-8 -*-
"""Importação de Transportadoras (Excel/CSV) para a TABELA_TRANSPORTADORA.

O que foi validado no banco antes de escrever esta tela:
  - PK = (TRANS_EMPRESA, TRANS_FILIAL, TRANS_CODIGO), as três INTEGER NOT NULL.
    Todas as outras 77 colunas aceitam NULL, então a importação pode ser enxuta.
  - **Não existe generator** para o código (nenhum GEN_*TRANS* serve) e **não há
    trigger BEFORE INSERT**: o código tem de vir da planilha ou ser calculado
    como MAX+1 por empresa/filial. Nada é preenchido pelo banco.
  - Sem CHECK constraint na tabela e sem validação de domínio nas colunas.
  - FKs que saem: TABELA_FILIAL (empresa/filial), TABELA_CIDADE
    (emp/fil/código) e TABELA_ENTREGADOR — esta última fica NULL (a tabela de
    entregadores está vazia na base).
  - 24 tabelas apontam para cá (PEDIDO, ROMANEIO, ORDEM_CARREGAMENTO, VEICULO,
    NF_ENTRADA_TRANS, TICKET_BALANCA, MDFE...), além de CF_TRANSPORTADORA no
    cadastro de clientes: código errado aqui contamina tudo isso.
"""
import configparser
import csv
import os
import re
import threading
import tkinter as tk
import unicodedata
from tkinter import ttk, filedialog, messagebox

from utils.excel_reader import obter_abas_planilha, ler_planilha_produtos
from utils.firebird_service import FirebirdService
from utils import tema


class TelaImportacaoPlanilhaTransportadora(ttk.Frame):
    """Uma linha da planilha = uma transportadora."""

    # (chave, rótulo no mapeamento, coluna no banco, tamanho máximo)
    # A ordem é a que aparece na tela.
    CAMPOS = [
        ('codigo',      'Código no ERP',   'TRANS_CODIGO',          None),
        ('descricao',   'Razão Social *',  'TRANS_DESCRICAO',       50),
        ('cnpj',        'CNPJ/CPF',        'TRANS_CGC_CPF',         20),
        ('ie',          'IE / RG',         'TRANS_IE_RG',           20),
        ('endereco',    'Endereço',        'TRANS_ENDERECO',        50),
        ('numero',      'Número',          'TRANS_NUMERO',          None),
        ('complemento', 'Complemento',     'TRANS_COMPLEMENTO',     100),
        ('bairro',      'Bairro',          'TRANS_BAIRRO',          50),
        ('cep',         'CEP',             'TRANS_CEP',             10),
        ('cidade',      'Cidade',          'TRANS_CIDADE_DESC',     100),
        ('uf',          'UF',              'TRANS_UF',              2),
        ('ibge',        'Cód. IBGE',       None,                    None),
        ('fone',        'Telefone',        'TRANS_FONE',            20),
        ('celular',     'Celular',         'TRANS_CELULAR',         20),
        ('contato',     'Contato',         'TRANS_CONTATO',         50),
        ('email',       'E-mail',          'TRANS_EMAIL',           50),
        ('email_nfe',   'E-mail NF-e',     'TRANS_EMAIL_NFE',       50),
        ('placa',       'Placa',           'TRANS_PLACA',           10),
        ('placa_uf',    'UF da Placa',     'TRANS_PLACA_UF',        2),
        ('rntrc',       'RNTRC / ANTT',    'TRANS_RNTRC',           20),
        ('comissao',    '% Comissão',      'TRANS_PER_COMISSAO',    None),
        ('obs',         'Observação',      'TRANS_OBS',             300),
        ('cod_antigo',  'Cód. Antigo',     'TRANS_CODIGO_IMPORTACAO', 20),
    ]
    OBRIGATORIOS = ('descricao',)

    COLUNAS = ("SEL", "AÇÃO", "STATUS", "CÓD. ERP", "RAZÃO SOCIAL", "CNPJ/CPF",
               "CIDADE (RESOLVIDA)", "UF", "FONE", "PLACA", "RNTRC", "CÓD. ANTIGO")

    def __init__(self, parent, callback_voltar=None):
        super().__init__(parent, padding="10")
        self.parent = parent
        self.callback_voltar = callback_voltar
        self.pack(fill=tk.BOTH, expand=True)

        self.caminho_arquivo = ""
        self.registros_lidos = []
        self.dados_analisados = []
        self.dados_grid = {}

        self.config = configparser.ConfigParser()
        self.config.read('config.ini', encoding='utf-8')
        self.config_db = {
            'host': self.config.get('FIREBIRD', 'servidor', fallback='127.0.0.1'),
            'port': self.config.get('FIREBIRD', 'porta', fallback='3050'),
            'database': self.config.get('FIREBIRD', 'caminho_banco', fallback=''),
            'user': self.config.get('FIREBIRD', 'usuario', fallback='SYSDBA'),
            'password': self.config.get('FIREBIRD', 'senha', fallback='masterkey'),
            'fbclient': self.config.get('FIREBIRD', 'fbclient', fallback=''),
        }

        self._criar_widgets()
        self._carregar_config()

    # =============================================================== UI
    def _criar_widgets(self):
        tema.montar_header(
            self, "Importar Transportadoras (Excel)",
            "Cadastro de transportadoras na TABELA_TRANSPORTADORA via planilha (XLSX/CSV)"
        ).pack(fill=tk.X)

        corpo = tk.Frame(self, bg=tema.BG_BASE)
        corpo.pack(fill=tk.BOTH, expand=True)

        sidebar = tema.montar_sidebar(corpo)
        rodape_sb = tk.Frame(sidebar, bg=tema.SIDEBAR_BG)
        rodape_sb.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 8))
        tema.botao_sidebar(rodape_sb, "⎋   Voltar", self._fechar).pack(fill=tk.X)

        tema.titulo_sidebar(sidebar, "AÇÕES").pack(fill=tk.X, pady=(16, 4))
        self.btn_analisar = tema.botao_sidebar(sidebar, "🔍   Carregar e Analisar Planilha",
                                               self._iniciar_analise)
        self.btn_analisar.pack(fill=tk.X)
        self.btn_importar = tema.botao_sidebar(sidebar, "🚀   Gravar no ERP",
                                               self._iniciar_importacao, cor_fg="#7EE0A0")
        self.btn_importar.config(state=tk.DISABLED)
        self.btn_importar.pack(fill=tk.X)
        self.btn_exportar = tema.botao_sidebar(sidebar, "⬇   Exportar Conferência (CSV)",
                                               self._exportar_csv)
        self.btn_exportar.config(state=tk.DISABLED)
        self.btn_exportar.pack(fill=tk.X)

        content = tk.Frame(corpo, bg=tema.BG_BASE)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=16, pady=12)

        # ---- arquivo
        linha = ttk.Frame(content)
        linha.pack(fill=tk.X, pady=2)
        tk.Label(linha, text="Arquivo:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 2))
        self.ent_arquivo = ttk.Entry(linha, font=("Segoe UI", 9))
        self.ent_arquivo.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        ttk.Button(linha, text="📁 Selecionar", command=self._selecionar_arquivo).pack(side=tk.LEFT, padx=2)
        tk.Label(linha, text="Aba:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(10, 2))
        self.cb_abas = ttk.Combobox(linha, width=16, state="readonly", font=("Segoe UI", 9))
        self.cb_abas.pack(side=tk.LEFT, padx=2)
        tk.Label(linha, text="Linha Inicial:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(10, 2))
        self.ent_linha_ini = ttk.Entry(linha, width=6, font=("Segoe UI", 9))
        self.ent_linha_ini.insert(0, "2")
        self.ent_linha_ini.pack(side=tk.LEFT, padx=2)

        # ---- opções
        opc = ttk.Frame(content)
        opc.pack(fill=tk.X, pady=2)
        tk.Label(opc, text="Código:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 2))
        self.var_modo_codigo = tk.StringVar(value="sequencial")
        ttk.Radiobutton(opc, text="Sequencial (MAX+1)", variable=self.var_modo_codigo,
                        value="sequencial").pack(side=tk.LEFT, padx=2)
        ttk.Radiobutton(opc, text="Seguir planilha", variable=self.var_modo_codigo,
                        value="planilha").pack(side=tk.LEFT, padx=2)
        tk.Label(opc, text="(não há generator para transportadora neste ERP)",
                 font=("Segoe UI", 8, "italic"), fg="#666").pack(side=tk.LEFT, padx=6)

        ttk.Separator(opc, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=2)
        self.var_copiar_cod = tk.BooleanVar(self, value=True)
        ttk.Checkbutton(opc, text="Cód. antigo → Cód. Importação",
                        variable=self.var_copiar_cod).pack(side=tk.LEFT, padx=4)

        # ---- campos que o "Atualizar" grava
        frame_upd = ttk.LabelFrame(
            content, padding="6",
            text="Transportadora já cadastrada → 'Atualizar' grava só os campos marcados")
        frame_upd.pack(fill=tk.X, pady=2)
        self.vars_update = {}
        padrao_marcado = {'endereco', 'bairro', 'cep', 'cidade', 'fone', 'celular',
                          'email', 'email_nfe', 'placa', 'rntrc', 'ie'}
        for chave, rotulo, coluna, _t in self.CAMPOS:
            if chave in ('codigo', 'ibge') or coluna is None:
                continue
            var = tk.BooleanVar(self, value=chave in padrao_marcado)
            self.vars_update[chave] = var
            ttk.Checkbutton(frame_upd, text=rotulo.replace(' *', ''),
                            variable=var).pack(side=tk.LEFT, padx=4)

        # ---- mapeamento
        self.frame_map = ttk.LabelFrame(
            content, padding="8",
            text="Mapeamento de Colunas (letra: A, B, C...)  •  obrigatório: Razão Social  •  "
                 "Cidade aceita nome, e o Cód. IBGE resolve sem depender do nome")
        self.frame_map.pack(fill=tk.X, pady=4)

        self.entradas_map = {}
        self._map_widgets = []
        for chave, rotulo, _col, _tam in self.CAMPOS:
            lbl = tk.Label(self.frame_map, text=rotulo + ":", font=("Segoe UI", 8, "bold"))
            ent = ttk.Entry(self.frame_map, width=5, font=("Segoe UI", 9))
            self.entradas_map[chave] = ent
            self._map_widgets.append((lbl, ent))
        self._map_por_linha = 0
        self._reorganizar_mapa(6)
        self.frame_map.bind("<Configure>", self._on_map_resize)

        # ---- ações da grade
        acoes = ttk.Frame(content)
        acoes.pack(fill=tk.X, pady=4)
        ttk.Button(acoes, text="☑ Marcar Todos", command=self._marcar_todos).pack(side=tk.LEFT, padx=3)
        ttk.Button(acoes, text="☐ Desmarcar", command=self._desmarcar_todos).pack(side=tk.LEFT, padx=3)
        ttk.Button(acoes, text="🔄 Marcar Já Cadastradas p/ Atualizar",
                   command=self._marcar_atualizar).pack(side=tk.LEFT, padx=3)
        tk.Label(acoes, text="Clique em SEL ou AÇÃO para alterar a linha",
                 font=("Segoe UI", 8, "italic"), fg="#666").pack(side=tk.LEFT, padx=10)
        self.progresso = ttk.Progressbar(acoes, orient=tk.HORIZONTAL, mode='determinate', length=120)
        self.progresso.pack(side=tk.LEFT, padx=8)
        self.lbl_status = ttk.Label(acoes, text="Aguardando configuração...",
                                    font=("Segoe UI", 9), foreground="#555")
        self.lbl_status.pack(side=tk.LEFT, padx=2)

        # ---- grade
        moldura = ttk.Frame(content)
        moldura.pack(fill=tk.BOTH, expand=True, pady=4)
        self.tree = ttk.Treeview(moldura, columns=self.COLUNAS, show="headings")
        self._ci = {c: i for i, c in enumerate(self.COLUNAS)}
        larguras = (40, 90, 230, 80, 240, 130, 200, 40, 120, 90, 110, 100)
        esquerda = {"STATUS", "RAZÃO SOCIAL", "CIDADE (RESOLVIDA)"}
        for col, larg in zip(self.COLUNAS, larguras):
            self.tree.heading(col, text=col, command=lambda c=col: self._ordenar(c))
            self.tree.column(col, width=larg, anchor=tk.W if col in esquerda else tk.CENTER)
        self.tree.bind("<ButtonRelease-1>", self._on_click)
        self.tree.tag_configure('NOVO', background=tema.INFO_CT)
        self.tree.tag_configure('OK', background=tema.SUCCESS_CT)
        self.tree.tag_configure('AVISO', background=tema.WARNING_CT)
        self.tree.tag_configure('ERRO', background=tema.ERROR_CT)
        sy = ttk.Scrollbar(moldura, orient=tk.VERTICAL, command=self.tree.yview)
        sx = ttk.Scrollbar(moldura, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscroll=sy.set, xscroll=sx.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        moldura.rowconfigure(0, weight=1)
        moldura.columnconfigure(0, weight=1)

        filtro = ttk.Frame(content)
        filtro.pack(fill=tk.X, pady=(2, 4))
        tk.Label(filtro, text="Filtrar Status:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 5))
        self.cb_filtro = ttk.Combobox(filtro, state="readonly", width=20, font=("Segoe UI", 9),
                                      values=["TODOS", "NOVO", "JÁ CADASTRADO", "AVISO", "ERRO"])
        self.cb_filtro.set("TODOS")
        self.cb_filtro.pack(side=tk.LEFT, padx=2)
        self.cb_filtro.bind("<<ComboboxSelected>>", lambda e: self._render())
        self.lbl_info = tk.Label(filtro, text="", font=("Segoe UI", 8), fg="#555")
        self.lbl_info.pack(side=tk.LEFT, padx=10)

    def _reorganizar_mapa(self, por_linha):
        por_linha = max(1, int(por_linha))
        if por_linha == self._map_por_linha:
            return
        self._map_por_linha = por_linha
        for i, (lbl, ent) in enumerate(self._map_widgets):
            lbl.grid(row=i // por_linha, column=(i % por_linha) * 2,
                     padx=(5, 1), pady=3, sticky=tk.E)
            ent.grid(row=i // por_linha, column=(i % por_linha) * 2 + 1,
                     padx=(0, 8), pady=3, sticky=tk.W)

    def _on_map_resize(self, event):
        self._reorganizar_mapa(max(1, min(len(self._map_widgets), event.width // 150)))

    def _fechar(self):
        self.destroy()
        if self.callback_voltar:
            self.callback_voltar()

    def _selecionar_arquivo(self):
        path = filedialog.askopenfilename(
            filetypes=[("Arquivos Suportados", "*.xlsx *.csv"), ("Excel", "*.xlsx"), ("CSV", "*.csv")])
        if not path:
            return
        self.ent_arquivo.delete(0, tk.END)
        self.ent_arquivo.insert(0, path)
        self.caminho_arquivo = path
        abas = obter_abas_planilha(path)
        self.cb_abas['values'] = abas
        if abas:
            self.cb_abas.current(0)

    # ============================================================ config
    SECAO = 'IMPORTACAO_TRANSPORTADORA'

    def _salvar_config(self):
        if not self.config.has_section(self.SECAO):
            self.config.add_section(self.SECAO)
        s = self.config[self.SECAO]
        s['ultimo_arquivo'] = self.caminho_arquivo
        s['ultima_aba'] = self.cb_abas.get()
        s['linha_inicial'] = self.ent_linha_ini.get()
        s['modo_codigo'] = self.var_modo_codigo.get()
        s['copiar_cod'] = 'S' if self.var_copiar_cod.get() else 'N'
        for chave, ent in self.entradas_map.items():
            s[f'mapa_{chave}'] = ent.get().strip()
        for chave, var in self.vars_update.items():
            s[f'upd_{chave}'] = 'S' if var.get() else 'N'
        with open('config.ini', 'w', encoding='utf-8') as f:
            self.config.write(f)

    def _carregar_config(self):
        if not self.config.has_section(self.SECAO):
            return
        s = self.config[self.SECAO]
        arquivo = s.get('ultimo_arquivo', '')
        if arquivo:
            self.ent_arquivo.delete(0, tk.END)
            self.ent_arquivo.insert(0, arquivo)
            self.caminho_arquivo = arquivo
            try:
                abas = obter_abas_planilha(arquivo)
                self.cb_abas['values'] = abas
                aba = s.get('ultima_aba', '')
                if aba and aba in abas:
                    self.cb_abas.set(aba)
                elif abas:
                    self.cb_abas.current(0)
            except Exception:
                pass
        self.ent_linha_ini.delete(0, tk.END)
        self.ent_linha_ini.insert(0, s.get('linha_inicial', '2'))
        self.var_modo_codigo.set(s.get('modo_codigo', 'sequencial'))
        self.var_copiar_cod.set(s.get('copiar_cod', 'S') == 'S')
        for chave, ent in self.entradas_map.items():
            v = s.get(f'mapa_{chave}', '')
            if v:
                ent.delete(0, tk.END)
                ent.insert(0, v)
        for chave, var in self.vars_update.items():
            v = s.get(f'upd_{chave}', '')
            if v:
                var.set(v == 'S')

    # ========================================================= helpers
    @staticmethod
    def _sem_acento(texto):
        return ''.join(c for c in unicodedata.normalize('NFKD', str(texto or ''))
                       if not unicodedata.combining(c))

    @classmethod
    def _norm_nome(cls, valor):
        """Nome comparável: sem acento, só letras e números."""
        return re.sub(r'[^0-9A-Z]', '', cls._sem_acento(valor).upper())

    @staticmethod
    def _so_digitos(valor):
        v = str(valor or '').strip()
        # Excel entrega CNPJ numérico como 12345678000199.0
        if re.match(r'^\d+[.,]0+$', v):
            v = re.split(r'[.,]', v)[0]
        return re.sub(r'\D', '', v)

    @staticmethod
    def _texto(valor, tam=None):
        v = str(valor or '').strip()
        if re.match(r'^\d+[.,]0+$', v):      # número que virou texto no Excel
            v = re.split(r'[.,]', v)[0]
        v = ' '.join(v.split())
        return v[:tam] if tam else v

    @staticmethod
    def _inteiro(valor):
        d = re.sub(r'\D', '', str(valor or ''))
        return int(d) if d and len(d) <= 9 else None

    @staticmethod
    def _decimal(valor):
        v = str(valor or '').strip().replace('%', '').replace(' ', '')
        if not v:
            return None
        if ',' in v and '.' in v:
            v = v.replace('.', '').replace(',', '.')
        elif ',' in v:
            v = v.replace(',', '.')
        try:
            return float(v)
        except ValueError:
            return None

    @staticmethod
    def _uf(valor):
        v = re.sub(r'[^A-Za-z]', '', str(valor or '')).upper()
        return v[:2] if len(v) >= 2 else ''

    @classmethod
    def _doc_valido(cls, digitos):
        """CPF (11) ou CNPJ (14) com dígito verificador correto.
        Documento errado na transportadora reprova a NF-e na SEFAZ, então a
        conferência acontece aqui e não depois."""
        d = digitos
        if len(d) == 11:
            if d == d[0] * 11:
                return False
            for corte in (9, 10):
                soma = sum(int(d[i]) * (corte + 1 - i) for i in range(corte))
                dv = (soma * 10) % 11 % 10
                if dv != int(d[corte]):
                    return False
            return True
        if len(d) == 14:
            if d == d[0] * 14:
                return False
            pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
            pesos2 = [6] + pesos1
            for pesos, corte in ((pesos1, 12), (pesos2, 13)):
                soma = sum(int(d[i]) * pesos[i] for i in range(corte))
                resto = soma % 11
                dv = 0 if resto < 2 else 11 - resto
                if dv != int(d[corte]):
                    return False
            return True
        return False

    # ========================================================= análise
    def _iniciar_analise(self):
        aba = self.cb_abas.get()
        if not self.caminho_arquivo or not aba:
            return messagebox.showwarning("Aviso", "Selecione o arquivo e a aba da planilha.")
        mapa = {c: e.get().strip() for c, e in self.entradas_map.items()}
        faltando = [r for c, r, _col, _t in self.CAMPOS
                    if c in self.OBRIGATORIOS and not mapa.get(c)]
        if faltando:
            return messagebox.showwarning(
                "Aviso", "Mapeie a letra da coluna obrigatória: " + ', '.join(faltando))
        try:
            linha_ini = int(self.ent_linha_ini.get())
        except ValueError:
            return messagebox.showerror("Erro", "A linha inicial deve ser um número.")

        self._salvar_config()
        self.btn_analisar.config(state=tk.DISABLED)
        self.lbl_status.config(text="Lendo planilha...")
        self.progresso['value'] = 15
        threading.Thread(target=self._analisar_bg, args=(aba, mapa, linha_ini),
                         daemon=True).start()

    def _analisar_bg(self, aba, mapa, linha_ini):
        try:
            self.registros_lidos = ler_planilha_produtos(self.caminho_arquivo, aba, mapa, linha_ini)
            if not self.registros_lidos:
                self.parent.after(0, lambda: messagebox.showwarning(
                    "Aviso", "Nenhum registro encontrado na planilha."))
                self.parent.after(0, lambda: self.btn_analisar.config(state=tk.NORMAL))
                return

            self.parent.after(0, lambda n=len(self.registros_lidos): self.lbl_status.config(
                text=f"{n} linhas lidas. Consultando o ERP..."))
            self.parent.after(0, lambda: self.progresso.config(value=35))

            emp = int(self.config.get('IMPORTACAO', 'empresa', fallback='1'))
            fil = int(self.config.get('IMPORTACAO', 'filial', fallback='1'))

            with FirebirdService(self.config_db) as fb:
                existentes, por_doc, por_nome, max_cod = self._carregar_transportadoras(fb, emp, fil)
                cid_ibge, cid_nome_uf, cid_nome = self._carregar_cidades(fb, emp, fil)

            self.parent.after(0, lambda: self.lbl_status.config(text="Conferindo linha por linha..."))
            self.parent.after(0, lambda: self.progresso.config(value=60))

            modo = self.var_modo_codigo.get()
            self.dados_analisados = []
            cods_planilha = {}
            docs_planilha = {}
            prox = max_cod + 1

            for idx, reg in enumerate(self.registros_lidos):
                linha_excel = linha_ini + idx
                item = self._analisar_linha(reg, linha_excel, emp, fil, modo, existentes,
                                            por_doc, por_nome, cid_ibge, cid_nome_uf,
                                            cid_nome, cods_planilha, docs_planilha)
                if item['acao'] in ('Importar',) and item['codigo'] is None:
                    item['codigo'] = prox
                    prox += 1
                if item['codigo'] is not None and item['tag'] != 'ERRO':
                    cods_planilha[item['codigo']] = linha_excel
                self.dados_analisados.append(item)

            self.parent.after(0, self._render)
        except Exception as e:
            self.parent.after(0, lambda err=e: messagebox.showerror(
                "Erro", f"Falha na análise:\n{err}"))
            self.parent.after(0, lambda: self.btn_analisar.config(state=tk.NORMAL))

    @staticmethod
    def _carregar_transportadoras(fb, emp, fil):
        """O que já existe no ERP, indexado por documento e por nome."""
        existentes, por_doc, por_nome = {}, {}, {}
        max_cod = 0
        for r in fb.query(
            "SELECT TRANS_CODIGO, TRANS_DESCRICAO, TRANS_CGC_CPF, TRANS_CODIGO_IMPORTACAO "
            "FROM TABELA_TRANSPORTADORA WHERE TRANS_EMPRESA = ? AND TRANS_FILIAL = ?",
            [emp, fil]
        ):
            cod = int(r['trans_codigo'])
            info = {'codigo': cod,
                    'descricao': str(r['trans_descricao'] or '').strip(),
                    'cnpj': str(r['trans_cgc_cpf'] or '').strip(),
                    'cod_importacao': str(r['trans_codigo_importacao'] or '').strip()}
            existentes[cod] = info
            max_cod = max(max_cod, cod)
            doc = re.sub(r'\D', '', info['cnpj'])
            if doc:
                por_doc.setdefault(doc, info)
            nome = TelaImportacaoPlanilhaTransportadora._norm_nome(info['descricao'])
            if nome:
                por_nome.setdefault(nome, info)
        return existentes, por_doc, por_nome, max_cod

    @classmethod
    def _carregar_cidades(cls, fb, emp, fil):
        """Índices de cidade: por IBGE, por (nome, UF) e por nome.

        A FK aponta para TABELA_CIDADE(emp, fil, código) e o código é INTERNO
        (9 dígitos = IBGE × 100 + sufixo), diferente do IBGE (7). O IBGE da
        planilha precisa ser traduzido — gravar o IBGE direto no TRANS_CIDADE
        quebra a FK (só 2 das 10.073 cidades têm código de 7 dígitos, resquício
        de importação antiga).

        Um mesmo IBGE tem várias linhas: a **sede** do município e os distritos
        (São Paulo = 355030800, e VILA MARIANA, LAJEADO... com sufixos maiores).
        A sede é a linha de MENOR código de 9 dígitos daquele IBGE — regra
        conferida contra a TABELA_CIDADES_IBGE: acerta o nome do município em
        5.563 dos 5.564 (a única divergência é grafia: MOGI/MOJI MIRIM).
        """
        linhas = []
        por_ibge_todas = {}
        for r in fb.query(
            "SELECT CID_CODIGO, CID_DESCRICAO, CID_UF, CID_CODIGO_IBGE FROM TABELA_CIDADE "
            "WHERE CID_EMPRESA = ? AND CID_FILIAL = ?", [emp, fil]
        ):
            cod = int(r['cid_codigo'])
            desc = str(r['cid_descricao'] or '').strip()
            uf = str(r['cid_uf'] or '').strip().upper()
            ibge = re.sub(r'\D', '', str(r['cid_codigo_ibge'] or ''))
            linhas.append((cod, desc, uf, ibge))
            if ibge:
                por_ibge_todas.setdefault(ibge, []).append(cod)

        # sede de cada IBGE = menor código de 9 dígitos (ignora os de 7)
        sedes = set()
        por_ibge = {}
        for ibge, codigos in por_ibge_todas.items():
            candidatos = [c for c in codigos if len(str(c)) == 9] or codigos
            sedes.add(min(candidatos))

        por_nome_uf, por_nome = {}, {}
        for cod, desc, uf, ibge in linhas:
            eh_sede = cod in sedes
            if ibge and eh_sede:
                por_ibge[ibge] = (cod, desc, uf)
            nome = cls._norm_nome(desc)
            if nome:
                info = (cod, desc, uf, eh_sede)
                por_nome_uf.setdefault((nome, uf), []).append(info)
                por_nome.setdefault(nome, []).append(info)
        return por_ibge, por_nome_uf, por_nome

    def _analisar_linha(self, reg, linha_excel, emp, fil, modo, existentes, por_doc,
                        por_nome, cid_ibge, cid_nome_uf, cid_nome, cods_planilha,
                        docs_planilha):
        v = lambda ch: reg.get(ch, '')
        descricao = self._texto(v('descricao'), 50)
        descricao_bruta = self._texto(v('descricao'))
        doc = self._so_digitos(v('cnpj'))
        uf = self._uf(v('uf'))
        avisos = []

        item = {
            'linha': linha_excel, 'descricao': descricao, 'cnpj': doc, 'uf': uf,
            'codigo': None, 'cidade_cod': None, 'cidade_label': '',
            'reg': reg, 'match': None,
        }

        if not descricao:
            item.update(status="ERRO (Sem Razão Social)", tag="ERRO", sel="☐", acao="—")
            return item
        if len(descricao_bruta) > 50:
            avisos.append(f"razão social cortada em 50 ('{descricao_bruta[:20]}...')")

        # ---- documento
        if doc and not self._doc_valido(doc):
            item.update(status=f"ERRO (CNPJ/CPF inválido: {doc})", tag="ERRO", sel="☐", acao="—")
            return item
        if doc and doc in docs_planilha:
            item.update(status=f"ERRO (CNPJ repetido na planilha — linha {docs_planilha[doc]})",
                        tag="ERRO", sel="☐", acao="—")
            return item
        if doc:
            docs_planilha[doc] = linha_excel

        # ---- cidade
        item['cidade_cod'], item['cidade_label'], aviso_cid = self._resolver_cidade(
            v('ibge'), v('cidade'), uf, cid_ibge, cid_nome_uf, cid_nome)
        if aviso_cid:
            avisos.append(aviso_cid)

        # ---- já existe?
        achado = None
        casou_por = ''
        if doc and doc in por_doc:
            achado, casou_por = por_doc[doc], 'CNPJ'
        elif not doc:
            nome = self._norm_nome(descricao)
            if nome in por_nome:
                achado, casou_por = por_nome[nome], 'razão social'
        item['match'] = achado
        item['casou_por'] = casou_por

        # ---- código
        cod_plan = self._inteiro(v('codigo'))
        if achado:
            item['codigo'] = achado['codigo']
            item.update(status=f"JÁ CADASTRADO (cód. {achado['codigo']}, por {casou_por})",
                        tag="OK", sel="☐", acao="Ignorar")
            if self._norm_nome(achado['descricao']) != self._norm_nome(descricao):
                item['status'] = (f"JÁ CADASTRADO (cód. {achado['codigo']}) — no ERP: "
                                  f"'{achado['descricao'][:28]}'")
                item['tag'] = "AVISO"
            return item

        if modo == 'planilha':
            if cod_plan is None:
                item.update(status="ERRO (Código não informado na planilha)", tag="ERRO",
                            sel="☐", acao="—")
                return item
            if cod_plan in existentes:
                ocupa = existentes[cod_plan]['descricao'][:26]
                item.update(status=f"ERRO (Código {cod_plan} já é de '{ocupa}')",
                            tag="ERRO", sel="☐", acao="—")
                return item
            if cod_plan in cods_planilha:
                item.update(status=f"ERRO (Código {cod_plan} repetido na planilha — "
                                   f"linha {cods_planilha[cod_plan]})",
                            tag="ERRO", sel="☐", acao="—")
                return item
            item['codigo'] = cod_plan
        elif cod_plan is not None and cod_plan not in existentes and cod_plan not in cods_planilha:
            # planilha trouxe código e ele está livre: respeita
            item['codigo'] = cod_plan

        if avisos:
            item.update(status="NOVO ⚠ " + "; ".join(avisos)[:120], tag="AVISO")
        else:
            item.update(status="NOVO", tag="NOVO")
        item.update(sel="☑", acao="Importar")
        return item

    @classmethod
    def _resolver_cidade(cls, ibge, cidade, uf, cid_ibge, cid_nome_uf, cid_nome):
        """(código da cidade, rótulo, aviso). IBGE primeiro; depois nome+UF; depois nome.

        Entre homônimos prefere a **sede** do município: 183 pares (nome, UF) se
        repetem no cadastro porque distrito e sede têm o mesmo nome em casos como
        SAO JOSE/CE. Sobrando mais de uma sede, não escolhe — avisa.
        """
        d_ibge = re.sub(r'\D', '', str(ibge or ''))
        if d_ibge:
            if d_ibge in cid_ibge:
                cod, desc, u = cid_ibge[d_ibge]
                return cod, f"{cod} - {desc}/{u}", ''
            return None, '', f"IBGE {d_ibge} não existe no cadastro de cidades"

        nome = cls._norm_nome(cidade)
        if not nome:
            return None, '', ''

        def escolher(candidatos, aviso_uf=''):
            sedes = [c for c in candidatos if c[3]]
            lista = sedes or candidatos
            if len(lista) == 1:
                cod, desc, u, _s = lista[0]
                return cod, f"{cod} - {desc}/{u}", aviso_uf
            codigos = ', '.join(str(c[0]) for c in lista[:4])
            return None, '', (f"cidade '{cls._texto(cidade)}' tem {len(lista)} cadastros "
                              f"({codigos}) — informe o Cód. IBGE para decidir")

        if uf and (nome, uf) in cid_nome_uf:
            return escolher(cid_nome_uf[(nome, uf)])

        candidatos = cid_nome.get(nome, [])
        if not candidatos:
            return None, '', f"cidade '{cls._texto(cidade)}' não encontrada"
        ufs = {c[2] for c in candidatos}
        if uf and uf not in ufs:
            return None, '', (f"cidade '{cls._texto(cidade)}' não existe em {uf} "
                              f"(só em {', '.join(sorted(ufs))})")
        if len(ufs) > 1:
            return None, '', (f"cidade '{cls._texto(cidade)}' existe em mais de um estado "
                              f"({', '.join(sorted(ufs))}) — informe a UF ou o IBGE")
        aviso = '' if not uf else ''
        return escolher(candidatos, aviso)

    # ========================================================== grade
    def _valores(self, item):
        return (item.get('sel', '☐'), item.get('acao', '—'), item['status'],
                item['codigo'] if item['codigo'] is not None else '',
                item['descricao'], item['cnpj'], item['cidade_label'], item['uf'],
                self._texto(item['reg'].get('fone', ''), 20),
                self._texto(item['reg'].get('placa', ''), 10),
                self._texto(item['reg'].get('rntrc', ''), 20),
                self._texto(item['reg'].get('cod_antigo', ''), 20))

    def _render(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        self.dados_grid.clear()

        filtro = self.cb_filtro.get()
        tags = {"NOVO": {"NOVO"}, "JÁ CADASTRADO": {"OK"}, "AVISO": {"AVISO"},
                "ERRO": {"ERRO"}}.get(filtro)
        mostrados = 0
        for item in self.dados_analisados:
            if tags is not None and item['tag'] not in tags:
                continue
            iid = self.tree.insert("", tk.END, values=self._valores(item), tags=(item['tag'],))
            self.dados_grid[iid] = item
            mostrados += 1

        conta = {}
        for it in self.dados_analisados:
            conta[it['tag']] = conta.get(it['tag'], 0) + 1
        total = len(self.dados_analisados)
        novos = conta.get('NOVO', 0) + conta.get('AVISO', 0)
        self.btn_analisar.config(state=tk.NORMAL)
        self.btn_exportar.config(state=tk.NORMAL if total else tk.DISABLED)
        if any(self._ciclo(it['status']) for it in self.dados_analisados):
            self.btn_importar.config(state=tk.NORMAL)
        self.progresso['value'] = 100
        self.lbl_status.config(
            text=f"Pronto. {novos} nova(s), {conta.get('OK', 0)} já cadastrada(s), "
                 f"{conta.get('ERRO', 0)} com erro, de {total} linhas.")
        self.lbl_info.config(text=f"Exibindo {mostrados} de {total} registros")

    @staticmethod
    def _ciclo(status):
        if "ERRO" in status:
            return []
        if status.startswith("NOVO"):
            return ["Importar", "Ignorar"]
        if "JÁ CADASTRADO" in status:
            return ["Atualizar", "Ignorar"]
        return []

    def _on_click(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        col = self.tree.identify_column(event.x)
        iid = self.tree.identify_row(event.y)
        if not iid or col not in ("#1", "#2"):
            return
        item = self.dados_grid.get(iid)
        if not item:
            return
        ciclo = self._ciclo(item['status'])
        if not ciclo:
            return
        if col == "#1":
            if item.get('sel') == "☑":
                item['sel'], item['acao'] = "☐", "Ignorar"
            else:
                item['sel'], item['acao'] = "☑", ciclo[0]
        else:
            try:
                prox = ciclo[(ciclo.index(item['acao']) + 1) % len(ciclo)]
            except ValueError:
                prox = ciclo[0]
            item['acao'] = prox
            item['sel'] = "☐" if prox == "Ignorar" else "☑"
        self.tree.item(iid, values=self._valores(item))

    def _marcar_todos(self):
        for iid, item in self.dados_grid.items():
            if "JÁ CADASTRADO" in item['status']:
                continue
            ciclo = self._ciclo(item['status'])
            if ciclo:
                item['sel'], item['acao'] = "☑", ciclo[0]
                self.tree.item(iid, values=self._valores(item))

    def _desmarcar_todos(self):
        for iid, item in self.dados_grid.items():
            if item.get('sel') == "☑":
                item['sel'], item['acao'] = "☐", "Ignorar"
                self.tree.item(iid, values=self._valores(item))

    def _marcar_atualizar(self):
        n = 0
        for iid, item in self.dados_grid.items():
            if "Atualizar" not in self._ciclo(item['status']):
                continue
            item['sel'], item['acao'] = "☑", "Atualizar"
            self.tree.item(iid, values=self._valores(item))
            n += 1
        campos = [r.replace(' *', '') for c, r, _col, _t in self.CAMPOS
                  if c in self.vars_update and self.vars_update[c].get()]
        self.lbl_status.config(
            text=f"{n} linha(s) para Atualizar "
                 f"({', '.join(campos) if campos else 'NENHUM campo marcado!'})")

    def _ordenar(self, col):
        atual, inv = getattr(self, '_ordem', (None, False))
        inv = not inv if atual == col else False
        self._ordem = (col, inv)
        idx = self._ci[col]

        def chave(iid):
            v = str(self.tree.item(iid, 'values')[idx] or '').strip()
            if not v:
                return (2, 0.0, '')
            try:
                return (0, float(v.replace(',', '.')), '')
            except ValueError:
                return (1, 0.0, v.upper())

        for pos, iid in enumerate(sorted(self.tree.get_children(), key=chave, reverse=inv)):
            self.tree.move(iid, '', pos)
        for c in self.COLUNAS:
            seta = (' ▼' if inv else ' ▲') if c == col else ''
            self.tree.heading(c, text=c + seta)

    def _exportar_csv(self):
        if not self.dados_analisados:
            return messagebox.showinfo("Aviso", "Nada para exportar.")
        caminho = filedialog.asksaveasfilename(
            defaultextension=".csv", initialfile="CONFERENCIA_TRANSPORTADORAS.csv",
            filetypes=[("CSV", "*.csv")])
        if not caminho:
            return
        try:
            with open(caminho, 'w', newline='', encoding='utf-8-sig') as f:
                w = csv.writer(f, delimiter=';')
                w.writerow(("LINHA",) + self.COLUNAS)
                for it in self.dados_analisados:
                    w.writerow((it['linha'],) + self._valores(it))
        except Exception as e:
            return messagebox.showerror("Erro", f"Não foi possível salvar:\n{e}")
        messagebox.showinfo("Exportado", f"Arquivo salvo em:\n{caminho}")

    # ======================================================= importação
    def _iniciar_importacao(self):
        selecionados = [it for it in self.dados_grid.values() if it.get('sel') == "☑"]
        if not selecionados:
            return messagebox.showwarning("Aviso", "Selecione pelo menos uma linha.")
        n_upd = sum(1 for it in selecionados if it['acao'] == 'Atualizar')
        n_ins = len(selecionados) - n_upd
        campos = [r.replace(' *', '') for c, r, _col, _t in self.CAMPOS
                  if c in self.vars_update and self.vars_update[c].get()]
        if n_upd and not campos:
            return messagebox.showwarning(
                "Aviso", f"{n_upd} linha(s) estão como 'Atualizar', mas nenhum campo está "
                         f"marcado na faixa de atualização.")
        partes = []
        if n_ins:
            partes.append(f"cadastrar {n_ins} transportadora(s)")
        if n_upd:
            partes.append(f"atualizar {n_upd} existente(s) — só {', '.join(campos)}")
        if not messagebox.askyesno("Confirmar", "Deseja " + " e ".join(partes) +
                                   " no banco de dados?\nEssa ação não pode ser desfeita."):
            return

        self._salvar_config()
        self.btn_importar.config(state=tk.DISABLED)
        self.btn_analisar.config(state=tk.DISABLED)
        self.lbl_status.config(text="Gravando no ERP...")
        campos_upd = {c for c in self.vars_update if self.vars_update[c].get()}
        threading.Thread(target=self._importacao_bg, args=(selecionados, campos_upd),
                         daemon=True).start()

    def _valores_gravacao(self, item, emp, fil):
        """Colunas do INSERT/UPDATE a partir da linha da planilha.

        Só entra o que a planilha realmente trouxe — coluna não mapeada ou
        célula vazia fica de fora, para não apagar o que já existe no ERP nem
        gravar string vazia onde o cadastro espera NULL.
        """
        reg = item['reg']
        dados = {}
        for chave, _rotulo, coluna, tam in self.CAMPOS:
            if coluna is None or chave in ('codigo', 'cidade'):
                continue
            bruto = reg.get(chave, '')
            if bruto is None or str(bruto).strip() == '':
                continue
            if chave == 'cnpj':
                valor = item['cnpj']
            elif chave in ('uf', 'placa_uf'):
                valor = self._uf(bruto)
            elif chave == 'numero':
                valor = self._inteiro(bruto)
            elif chave == 'comissao':
                valor = self._decimal(bruto)
            elif chave == 'cep':
                valor = self._so_digitos(bruto)[:10] or None
            elif chave == 'cod_antigo':
                valor = self._texto(bruto, tam)
            else:
                valor = self._texto(bruto, tam)
            if valor in ('', None):
                continue
            dados[coluna] = valor

        # cidade: o nome vai para TRANS_CIDADE_DESC, o código resolvido para a FK
        nome_cidade = self._texto(reg.get('cidade', ''), 100)
        if nome_cidade:
            dados['TRANS_CIDADE_DESC'] = nome_cidade
            dados['TRANS_CIDADE_IMPORTACAO'] = nome_cidade[:50]
        if item.get('cidade_cod') is not None:
            dados['TRANS_CIDADE_EMPRESA'] = emp
            dados['TRANS_CIDADE_FILIAL'] = fil
            dados['TRANS_CIDADE'] = item['cidade_cod']
        if dados.get('TRANS_UF'):
            dados['TRANS_UF_IMPORTACAO'] = dados['TRANS_UF']

        cod_antigo = self._texto(reg.get('cod_antigo', ''), 20)
        if self.var_copiar_cod.get() and cod_antigo:
            dados['TRANS_CODIGO_IMPORTACAO'] = cod_antigo
            dados['TRANS_COD_IMPORTA'] = cod_antigo
        return dados

    def _importacao_bg(self, selecionados, campos_upd):
        log = []
        inseridos = atualizados = erros = 0
        sem_campo = 0
        try:
            emp = int(self.config.get('IMPORTACAO', 'empresa', fallback='1'))
            fil = int(self.config.get('IMPORTACAO', 'filial', fallback='1'))
            colunas_upd = set()
            for chave, _r, coluna, _t in self.CAMPOS:
                if chave in campos_upd and coluna:
                    colunas_upd.add(coluna)
            if 'cidade' in campos_upd:
                colunas_upd.update({'TRANS_CIDADE', 'TRANS_CIDADE_EMPRESA',
                                    'TRANS_CIDADE_FILIAL', 'TRANS_CIDADE_DESC',
                                    'TRANS_CIDADE_IMPORTACAO'})

            with FirebirdService(self.config_db) as fb:
                # Revalida o MAX aqui: entre a análise e a gravação alguém pode
                # ter cadastrado transportadora pela tela do ERP.
                r = fb.query("SELECT COALESCE(MAX(TRANS_CODIGO), 0) AS M FROM "
                             "TABELA_TRANSPORTADORA WHERE TRANS_EMPRESA = ? AND TRANS_FILIAL = ?",
                             [emp, fil])
                prox = int(r[0]['m']) + 1
                ocupados = set()
                for row in fb.query("SELECT TRANS_CODIGO FROM TABELA_TRANSPORTADORA "
                                    "WHERE TRANS_EMPRESA = ? AND TRANS_FILIAL = ?", [emp, fil]):
                    ocupados.add(int(row['trans_codigo']))

                total = len(selecionados)
                for i, item in enumerate(selecionados):
                    if i % 25 == 0:
                        self.parent.after(0, lambda d=i, t=total: self.lbl_status.config(
                            text=f"Gravando {d + 1}/{t}..."))
                    nome = item['descricao']
                    try:
                        dados = self._valores_gravacao(item, emp, fil)
                        if item['acao'] == 'Atualizar':
                            cod = item['codigo']
                            upd = {k: v for k, v in dados.items() if k in colunas_upd}
                            if not upd:
                                sem_campo += 1
                                log.append(f"⏭ {nome}: nada a atualizar (os campos marcados "
                                           f"estão vazios na planilha)")
                                continue
                            sets = ", ".join(f"{c} = ?" for c in upd)
                            fb.execute(
                                f"UPDATE TABELA_TRANSPORTADORA SET {sets} WHERE TRANS_EMPRESA = ? "
                                f"AND TRANS_FILIAL = ? AND TRANS_CODIGO = ?",
                                list(upd.values()) + [emp, fil, cod])
                            atualizados += 1
                            log.append(f"↻ {cod} {nome}: atualizado ({', '.join(sorted(upd))})")
                            continue

                        cod = item['codigo']
                        if cod is None or cod in ocupados:
                            while prox in ocupados:
                                prox += 1
                            cod = prox
                        ocupados.add(cod)
                        dados['TRANS_EMPRESA'] = emp
                        dados['TRANS_FILIAL'] = fil
                        dados['TRANS_CODIGO'] = cod
                        cols = ", ".join(dados)
                        ph = ", ".join("?" * len(dados))
                        fb.execute(f"INSERT INTO TABELA_TRANSPORTADORA ({cols}) VALUES ({ph})",
                                   list(dados.values()))
                        inseridos += 1
                        item['codigo'] = cod
                        cid = item['cidade_label'] or 'sem cidade'
                        log.append(f"✔ {cod} {nome} — {cid}")
                    except Exception as e:
                        erros += 1
                        log.append(f"❌ {nome}: {e}")

            msg = f"Processamento concluído!\n\n{inseridos} transportadora(s) cadastradas."
            if atualizados:
                msg += f"\n{atualizados} atualizada(s)."
            if sem_campo:
                msg += f"\n{sem_campo} sem nada a atualizar (campos marcados vazios na planilha)."
            if erros:
                msg += f"\n{erros} erro(s) — veja o log."
            resumo = [
                "--- LOG DE IMPORTACAO DE TRANSPORTADORAS ---", "",
                f"  cadastradas : {inseridos}",
                f"  atualizadas : {atualizados}",
                f"  sem alterar : {sem_campo}",
                f"  erros       : {erros}", "",
            ]
            self.parent.after(0, lambda m=msg: messagebox.showinfo("Concluído", m))
            self.parent.after(0, lambda t="\n".join(resumo + log): self._oferecer_log(t))
        except Exception as e:
            self.parent.after(0, lambda err=e: messagebox.showerror(
                "Erro de Importação", f"Ocorreu um erro estrutural:\n{err}"))
        finally:
            self.parent.after(0, self._pos_importacao)

    def _pos_importacao(self):
        self.btn_importar.config(state=tk.NORMAL)
        if self.caminho_arquivo and self.cb_abas.get():
            self._iniciar_analise()   # reanalisa: o que entrou vira JÁ CADASTRADO
        else:
            self.btn_analisar.config(state=tk.NORMAL)
            self.lbl_status.config(text="Pronto.")

    def _oferecer_log(self, texto):
        if not messagebox.askyesno("Log", "Deseja salvar o log desta importação?"):
            return
        caminho = filedialog.asksaveasfilename(
            defaultextension=".txt", initialfile="LOG_TRANSPORTADORAS.txt",
            filetypes=[("Arquivos de Texto", "*.txt")])
        if not caminho:
            return
        try:
            with open(caminho, 'w', encoding='utf-8') as f:
                f.write(texto)
        except Exception as e:
            return messagebox.showerror("Erro", f"Não foi possível salvar:\n{e}")
        if messagebox.askyesno("Abrir", "Log salvo. Deseja abrir agora?"):
            try:
                os.startfile(caminho)
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao abrir:\n{e}")

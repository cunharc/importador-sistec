import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import re
import threading
import queue
import datetime
import json
import sys
from pathlib import Path

MODULOS_FIXOS = [
    "Abate - Pesagem", "Arvore de Privilegios", "Baixa Etiqueta",
    "Baixa Titulo Classe", "Baixa por Nro de Documento",
    "Cadastro D.I.A Pedido Compra Animal", "Cadastro Limite Pesos Cliente",
    "Cadastro Lote", "Cadastro Modelo de Chassi",
    "Cadastro Motivo Devolucao Nota Fiscal", "Cadastro Motivo Morte Animal",
    "Cadastro Nota Fiscal Produtor", "Cadastro Ordem de Desossa Produto Acabado",
    "Cadastro Pedido", "Cadastro Pedido Animal - Item",
    "Cadastro Pedido Animal - Peso Morto", "Cadastro Pedido Animal - Peso Vivo",
    "Cadastro Pedido Compra de Animal", "Cadastro Unidade Produto",
    "Cadastro Vacina", "Cadastro de Adiantamento", "Cadastro de Animal",
    "Cadastro de Bens", "Cadastro de Centro de Custos",
    "Cadastro de Clientes-Fornecedores", "Cadastro de Compradores",
    "Cadastro de Computadores", "Cadastro de Contas",
    "Cadastro de Curral Confinamento", "Cadastro de Dieta",
    "Cadastro de Etiquetas", "Cadastro de Filial",
    "Cadastro de GTA Pedido de Compra", "Cadastro de Grupos",
    "Cadastro de Locais de Estoque", "Cadastro de Local Confinamento",
    "Cadastro de Meta Vendedor", "Cadastro de Motoristas",
    "Cadastro de Movimento", "Cadastro de Notas de Entrada",
    "Cadastro de Ordem de Carregamento", "Cadastro de Pedidos",
    "Cadastro de Plano de Contas", "Cadastro de Produto",
    "Cadastro de Produtos", "Cadastro de Produtos Gerado via Classe",
    "Cadastro de Saldos Anteriores", "Cadastro de Solicitantes",
    "Cadastro de Subgrupos", "Cadastro de Tipo de Lancamento",
    "Cadastro de Tipo de Produto", "Cadastro de Transportadoras",
    "Cadastro de Vendedores-Representantes", "Calculo Saldo Conta",
    "Cancelamento de Nota Fiscal", "Cancelamento de Pedidos",
    "Cancelar Nota Fiscal de Entrada", "Compensar Cheques Manual",
    "Complemento da Filial", "Consulta de CNPJ", "Encerrar Movimento",
    "Entrada da Desossa", "ManifestaNFE - Recupera NF",
    "Montagem de Ordem de Carregamento", "Movimento Concor Classe",
    "Movimento Concor Classe - Centro de Custo", "Movimento Estoque Manual",
    "Movimento de Estoque", "Notas Fiscais de Entrada de Ajustes do ICMS",
    "PDA", "Paramametros da Filial - SPED ReInf",
    "Parametros da Filial - Compras", "Parametros da Filial - Conpag",
    "Parametros da filial - Conrec", "Parametros de Pedidos de Varejo",
    "Pedido de Venda - Varejo", "Pedido de Venda Gerado via Classe",
    "Pesagem de Desossa", "Recalcula Impostos - PIS-COFINS",
    "Recalculo do Estoque", "Recebimento Animal", "Recebimento de Mercadoria",
]

# Configuração para salvar a última pasta buscada
CONFIG_FILE = "config_busca_logs.json"

def carregar_config():
    """Carrega as preferências locais do usuário (última pasta selecionada)."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def salvar_config(config):
    """Salva as preferências locais do usuário no JSON."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f)
    except Exception as e:
        print(f"Erro ao salvar config_busca_logs.json: {e}")

def detectar_modulo(filename: str) -> str:
    """Extrai o nome do módulo/tela a partir do nome do arquivo de log."""
    if not filename:
        return ""
    name_only = os.path.basename(filename).replace('.txt', '')
    name_clean = re.sub(r' \d{2}-\d{2}-\d{2}.*', '', name_only)
    name_clean = re.sub(r'_\d{2}-\d{2}-\d{2}_.*', '', name_clean)
    return name_clean.strip()


def analisar_campos_acesso(campos_alterados: list) -> str:
    """
    Analisa campos ACESSO_* para determinar o significado semântico.
    Retorna uma descrição legível do que aconteceu.
    """
    acessos = {}
    for c, v1, v2 in campos_alterados:
        if c.startswith('ACESSO_'):
            acessos[c] = (v1, v2)

    aceito = acessos.get('ACESSO_ACEITO', ('', ''))
    incluir = acessos.get('ACESSO_INCLUIR', ('', ''))
    alterar = acessos.get('ACESSO_ALTERAR', ('', ''))
    excluir = acessos.get('ACESSO_EXCLUIR', ('', ''))

    aceito_granted = aceito[0] == 'N' and aceito[1] == 'S'
    incluir_granted = incluir[0] == 'N' and incluir[1] == 'S'
    alterar_granted = alterar[0] == 'N' and alterar[1] == 'S'
    excluir_granted = excluir[0] == 'N' and excluir[1] == 'S'

    if aceito_granted and incluir_granted and alterar_granted and excluir_granted:
        return "ACESSO TOTAL CONCEDIDO (ACESSO_ACEITO/INCLUIR/ALTERAR/EXCLUIR: N → S)"
    if aceito_granted and incluir_granted and alterar_granted:
        return "ACESSO PARCIAL CONCEDIDO (ACEITO+INCLUIR+ALTERAR: N → S)"
    if aceito_granted:
        return "ACESSO BÁSICO CONCEDIDO (ACESSO_ACEITO: N → S)"

    return ""


def analisar_semantica_modulo(dados: dict, modulo: str) -> dict:
    """
    Enriquece os dados com interpretação semântica baseada no módulo
    e nos campos alterados/inseridos.
    """
    dados['significado'] = ""
    dados['campos_chave'] = []
    dados['campos_ruido'] = []

    # Lista de campos conhecidos como ruído (nunca mostram mudança real)
    campos_ruido_conhecidos = [
        'ACESSO_EXTRA1', 'ACESSO_EXTRA2', 'ACESSO_EXTRA3', 'ACESSO_EXTRA4',
        'ACESSO_EXTRA5', 'ACESSO_EXTRA6', 'ACESSO_EXTRA7', 'ACESSO_EXTRA8',
        'ACESSO_EXTRA9', 'ACESSO_EXTRA10', 'ACESSO_EXTRA11', 'ACESSO_EXTRA12',
        'ACESSO_EXTRA13', 'ACESSO_EXTRA14', 'ACESSO_EXTRA15', 'ACESSO_EXTRA16',
        'ACESSO_EXTRA17', 'ACESSO_EXTRA18', 'ACESSO_EXTRA19', 'ACESSO_EXTRA20',
        'ACESSO_EXTRA21', 'ACESSO_EXTRA22', 'ACESSO_EXTRA23', 'ACESSO_EXTRA24',
        'ACESSO_EXTRA25', 'ACESSO_EXTRA26', 'ACESSO_EXTRA27', 'ACESSO_EXTRA28',
        'ACESSO_EXTRA29', 'ACESSO_EXTRA30',
        'ACESSO_EMITIR', 'ACESSO_REEMITIR',
        'ACESSO_PERFIL',
    ]

    if 'PRIVILÉGIO' in modulo.upper() or 'PRIVILEGIO' in modulo.upper() or 'ARVORE' in modulo.upper():
        # Análise semântica para Árvore de Privilégios
        significado = analisar_campos_acesso(dados['campos_alterados'])
        if significado:
            dados['significado'] = significado

        # Marcar campos ACESSO_* como campos-chave
        for c, v1, v2 in dados['campos_alterados']:
            if c.startswith('ACESSO_') and c not in campos_ruido_conhecidos:
                dados['campos_chave'].append((c, v1, v2))

        for c, v in dados['campos_inseridos']:
            if c.startswith('ACESSO_USUARIO') or c.startswith('ACESSO_MENU') or c.startswith('ACESSO_NIVEL') or c.startswith('ACESSO_SISTEMA'):
                dados['campos_chave'].append((c, v))

    elif 'BAIXA ETIQUETA' in modulo.upper():
        # Análise semântica para Baixa Etiqueta
        for c, v1, v2 in dados['campos_alterados']:
            if c == 'CBE_STATUS':
                if not v1 and v2 == 'F':
                    dados['significado'] = "CBE FINALIZADO (CBE_STATUS: vazio → F)"
                elif v1 == 'A' and v2 == 'F':
                    dados['significado'] = "CBE FINALIZADO (CBE_STATUS: A → F)"
                elif v1 == 'F' and v2 == 'A':
                    dados['significado'] = "CBE REVERTIDO PARA ATIVO (CBE_STATUS: F → A)"
                elif v1 and v2:
                    dados['significado'] = f"CBE_STATUS ALTERADO: {v1} → {v2}"
        for c, v1, v2 in dados['campos_alterados']:
            if c in ('CBE_ID', 'CBE_STATUS', 'CBE_MOTIVO', 'CBE_DATA'):
                dados['campos_chave'].append((c, v1, v2))
        for c, v in dados['campos_inseridos']:
            if c in ('CBE_ID', 'BEE_ID', 'BEE_CBE_ID', 'PRODUTO_DESCRICAO', 'BEE_PRODUTO',
                      'BEE_QTDE', 'BEE_PESO', 'CBE_STATUS', 'CBE_MOTIVO'):
                dados['campos_chave'].append((c, v))

    elif 'CLASSIFICAÇÕES FISCAIS' in modulo.upper() or 'NCM' in modulo.upper():
        for c, v1, v2 in dados['campos_alterados']:
            if c in ('CFIS_DIRB', 'CFIS_CODIGO', 'CFIS_DESCRICAO', 'CFIS_ICMS_VENDA',
                      'CFIS_ICMS_COMPRA', 'CFIS_CEST', 'CFIS_NCM'):
                dados['campos_chave'].append((c, v1, v2))
                if c == 'CFIS_DIRB' and not v1 and v2:
                    dados['significado'] = f"DIRB ATRIBUÍDO: {v2}"
        for c, v in dados['campos_inseridos']:
            if c in ('CFIS_CODIGO', 'CFIS_DESCRICAO'):
                dados['campos_chave'].append((c, v))

    elif 'CLIENTES' in modulo.upper() or 'FORNECEDORES' in modulo.upper():
        for c, v1, v2 in dados['campos_alterados']:
            if c in ('CF_CODIGO', 'CF_RAZAO', 'CF_FANTASIA', 'CF_CPF_CGC',
                      'CF_RG_IE', 'CF_ATIVO', 'CF_CLIENTE', 'CF_FORNECEDOR',
                      'CF_ENDERECO', 'CF_EMAIL', 'CF_FONE1', 'CF_COND_PAGTO',
                      'CF_ICMS', 'CF_TIPO_INSCR'):
                dados['campos_chave'].append((c, v1, v2))
                if c == 'CF_RG_IE' and not v1 and v2:
                    dados['significado'] = f"IE REGISTRADA: {v2}"
                if c == 'CF_ATIVO' and v1 != v2:
                    dados['significado'] = f"Ativo: {v1} → {v2}"
        for c, v in dados['campos_inseridos']:
            if c in ('CF_CODIGO', 'CF_RAZAO', 'CF_FANTASIA', 'CF_CPF_CGC'):
                dados['campos_chave'].append((c, v))

    else:
        # Semântica genérica: detectar CBE_STATUS em qualquer módulo
        for c, v1, v2 in dados['campos_alterados']:
            if c == 'CBE_STATUS':
                if not v1 and v2 == 'F':
                    dados['significado'] = "CBE FINALIZADO (CBE_STATUS: vazio → F)"
                elif v1 == 'A' and v2 == 'F':
                    dados['significado'] = "CBE FINALIZADO (CBE_STATUS: A → F)"
                elif v1 == 'F' and v2 == 'A':
                    dados['significado'] = "CBE REVERTIDO PARA ATIVO (CBE_STATUS: F → A)"
                elif not v1 and v2:
                    dados['significado'] = f"CBE_STATUS ATRIBUÍDO: → {v2}"
                elif v2 == 'F':
                    dados['significado'] = f"CBE_STATUS ALTERADO PARA F: {v1} → F"
                dados['campos_chave'].append((c, v1, v2))
            if c == 'CBE_ID':
                dados['campos_chave'].append((c, v1, v2))

        # Detectar quaisquer ACESSO_* mesmo sem módulo identificado
        aceito_sig = analisar_campos_acesso(dados['campos_alterados'])
        if aceito_sig:
            dados['significado'] = aceito_sig
            for c, v1, v2 in dados['campos_alterados']:
                if c.startswith('ACESSO_') and c not in campos_ruido_conhecidos:
                    dados['campos_chave'].append((c, v1, v2))

    return dados


def filtrar_ruido(dados: dict) -> dict:
    """
    Remove campos que não tiveram mudança real (ruído).
    Em blocos de ALTERAÇÃO, campos que aparecem sem '---------->'
    são apenas repetição do estado atual - não são inserções reais.
    """
    if dados['tipo_operacao'] == 'ALTERAÇÃO':
        # Em alterações, 'campos_inseridos' são na verdade campos exibidos
        # que não mudaram. Devemos filtrar apenas os que podem ser úteis.
        # Mantemos apenas campos-chave conhecidos como úteis mesmo sem alteração
        uteis_sem_mudanca = {'ACESSO_USUARIO', 'ACESSO_MENU', 'ACESSO_NIVEL',
                              'ACESSO_SISTEMA', 'CBE_ID', 'CF_CODIGO',
                              'CFIS_CODIGO', 'CFIS_DESCRICAO',
                              'NAT_CODIGO', 'NAT_DESCRICAO_ABR'}
        if dados['campos_inseridos']:
            filtrados = [(c, v) for c, v in dados['campos_inseridos']
                         if c in uteis_sem_mudanca]
            dados['campos_inseridos'] = filtrados

    return dados


def parse_bloco(bloco_texto: str, filename: str = "") -> dict:
    """
    Analisa um bloco cru de texto do log separado e extrai suas propriedades
    (Data, Hora, Usuário, Computador, Tipo, Tela e Campos alterados/inseridos).
    Inclui análise semântica e filtragem de ruído.
    """
    # Filtra as linhas vazias e as que são puramente separadores '=========='
    linhas = [linha for linha in bloco_texto.split('\n') if linha.strip() and not linha.startswith('===')]
    if not linhas:
        return None

    dados = {
        'data': '',
        'hora': '',
        'usuario': '',
        'computador': '',
        'tipo_operacao': 'OPERAÇÃO',
        'tela': '',
        'campos_alterados': [],
        'campos_inseridos': [],
        'termo_encontrado_em': [],
        'bloco_raw': bloco_texto,
        'significado': '',
        'campos_chave': [],
        'campos_ruido': [],
    }

    modulo = detectar_modulo(filename)

    # 1. PARSER DO CABEÇALHO (Busca Data, Hora, Usuário, Computador e Tipo)
    for i, linha in enumerate(linhas[:6]):
        if 'Data' in linha or 'Hora' in linha:
            m_data = re.search(r'Data\s*:\s*(\d{2}/\d{2}/\d{4})', linha)
            if m_data: dados['data'] = m_data.group(1)
            m_hora = re.search(r'Hora\s*:\s*(\d{2}:\d{2}(?::\d{2})?)', linha)
            if m_hora: dados['hora'] = m_hora.group(1)
        
        if 'Usuário' in linha or 'Usu?rio' in linha:
            m_usu = re.search(r'Usu.rio\s*:\s*(\S+)', linha)
            if m_usu: dados['usuario'] = m_usu.group(1)
            m_comp = re.search(r'Computador\s*:\s*(\S+)', linha)
            if m_comp: dados['computador'] = m_comp.group(1)

        if 'Tipo de Alteração' in linha or 'Tipo de Altera' in linha:
            m_tipo = re.search(r'Tipo de Altera.*:\s*(.*)', linha)
            if m_tipo:
                t = m_tipo.group(1).strip().upper()
                if 'ALTERA' in t: dados['tipo_operacao'] = 'ALTERAÇÃO'
                elif 'INSER' in t: dados['tipo_operacao'] = 'INSERÇÃO'
                elif 'EXCLUS' in t: dados['tipo_operacao'] = 'EXCLUSÃO'
                elif not t: dados['tipo_operacao'] = 'OPERAÇÃO'
                else: dados['tipo_operacao'] = t

    # 2. DETERMINAR A TELA/MÓDULO DO BLOCO
    if 'Data' not in linhas[0] and 'Usuário' not in linhas[0] and 'Usu?rio' not in linhas[0]:
        dados['tela'] = linhas[0].strip()
    else:
        for i, linha in enumerate(linhas):
            if 'Tipo de Altera' in linha and i + 1 < len(linhas):
                next_line = linhas[i+1].strip()
                if ':' not in next_line and '----' not in next_line:
                    dados['tela'] = next_line
                    break

    if not dados['tela'] and modulo:
        dados['tela'] = modulo

    if not dados['tela']:
        dados['tela'] = "Operação Desconhecida"

    # 3. EXTRAÇÃO DOS CAMPOS
    for linha in linhas:
        linha_strip = linha.strip()
        if ':' not in linha_strip:
            continue
        
        if any(linha_strip.startswith(x) for x in ['Data', 'Usuário', 'Usu?rio', 'Tipo de Altera']):
            continue

        parts = linha_strip.split(':', 1)
        if len(parts) == 2:
            campo = parts[0].strip()
            valor_raw = parts[1].strip()

            if '---------->' in valor_raw:
                val_parts = valor_raw.split('---------->')
                val_antigo = val_parts[0].strip()
                val_novo = val_parts[1].strip()
                dados['campos_alterados'].append((campo, val_antigo, val_novo))
            else:
                dados['campos_inseridos'].append((campo, valor_raw))

    # 4. ANÁLISE SEMÂNTICA
    dados = analisar_semantica_modulo(dados, modulo)

    # 5. FILTRAGEM DE RUÍDO
    dados = filtrar_ruido(dados)

    # 6. INFERIR TIPO DE OPERAÇÃO VIA SUBTÍTULO/CAMPOS
    if 'ESTORNO' in dados['tela'].upper() or any('ESTORNO' in c.upper() or 'ESTORNO' in v.upper() for c, v in dados['campos_inseridos']) or any('ESTORNO' in c.upper() or 'ESTORNO' in v1.upper() or 'ESTORNO' in v2.upper() for c, v1, v2 in dados['campos_alterados']):
        dados['tipo_operacao'] = 'ESTORNO'
        
    if 'CANCELAMENTO' in dados['tela'].upper() or any('CANCELAMENTO' in c.upper() or 'CANCELAMENTO' in v.upper() for c, v in dados['campos_inseridos']) or any('CANCELAMENTO' in c.upper() or 'CANCELAMENTO' in v1.upper() or 'CANCELAMENTO' in v2.upper() for c, v1, v2 in dados['campos_alterados']):
        dados['tipo_operacao'] = 'CANCELAMENTO'

    return dados

def parse_log_file(filepath: str, termo: str, case_insensitive: bool) -> list:
    """Abre um arquivo, lê o bloco e tenta encontrar correspondências do termo passado."""
    blocos_encontrados = []
    
    try:
        # Logs do ERP Sistec têm encoding Latin-1. Errors replace previne falhas com lixo.
        with open(filepath, 'r', encoding='latin-1', errors='replace') as f:
            conteudo = f.read()
    except Exception as e:
        print(f"Erro ao ler {filepath}: {e}")
        return []

    # Quebra o arquivo em blocos separados pelas linhas '=' (80 ou mais caracteres de = geralmente)
    blocos_raw = re.split(r'=+', conteudo)
    termo_busca = termo.lower() if case_insensitive else termo

    for bloco_raw in blocos_raw:
        if not bloco_raw.strip():
            continue
            
        texto_busca = bloco_raw.lower() if case_insensitive else bloco_raw
        if termo_busca in texto_busca:
            dados = parse_bloco(bloco_raw, str(filepath))
            if dados:
                dados['bloco_raw'] = bloco_raw
                
                # Mapeia onde o termo foi encontrado para facilitar o Highlight na Interface
                for c, v1, v2 in dados['campos_alterados']:
                    v_str = f"{c} {v1} {v2}"
                    if termo_busca in (v_str.lower() if case_insensitive else v_str):
                        dados['termo_encontrado_em'].append(c)
                        
                for c, v in dados['campos_inseridos']:
                    v_str = f"{c} {v}"
                    if termo_busca in (v_str.lower() if case_insensitive else v_str):
                        dados['termo_encontrado_em'].append(c)
                
                if not dados['termo_encontrado_em']:
                    dados['termo_encontrado_em'].append("Corpo do Bloco / Cabeçalho")

                blocos_encontrados.append(dados)
                
    return blocos_encontrados

def buscar_em_pasta(pasta: str, termo: str, subpastas: bool, case_insensitive: bool, q: queue.Queue):
    """Função background que faz o crawling nas pastas sem travar a interface."""
    resultados = {}
    total_arquivos = 0
    
    try:
        p = Path(pasta)
        pattern = "**/*.*" if subpastas else "*.*"
        exts = {'.txt', '.log'}
        arquivos = [f for f in p.glob(pattern) if f.suffix.lower() in exts]
        total_arquivos = len(arquivos)
        
        for i, filepath in enumerate(arquivos):
            blocos = parse_log_file(str(filepath), termo, case_insensitive)
            if blocos:
                mtime = os.path.getmtime(filepath)
                data_arquivo = datetime.datetime.fromtimestamp(mtime).strftime('%d/%m/%Y %H:%M')
                resultados[str(filepath)] = {
                    'nome': filepath.name,
                    'data_arquivo': data_arquivo,
                    'blocos': blocos,
                    'filepath': str(filepath)
                }
            
            # Evita sobrecarga da interface enfileirando progresso a cada 10 arquivos
            if i % 10 == 0 or i == total_arquivos - 1:
                q.put({'tipo': 'progresso', 'atual': i + 1, 'total': total_arquivos})
                
    except Exception as e:
        q.put({'tipo': 'erro', 'msg': str(e)})

    q.put({'tipo': 'fim', 'resultados': resultados})

def exportar_resultados(resultados, filepath):
    """Exporta o resultado do parser resumido para um TXT legível."""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            for r in resultados.values():
                f.write(f"Arquivo: {r['nome']} (Data: {r['data_arquivo']}) - {len(r['blocos'])} ocorrência(s)\n")
                f.write("=" * 80 + "\n\n")
                
                for b in r['blocos']:
                    f.write(f"Operação : {b['tipo_operacao']} | {b['tela']}\n")
                    f.write(f"Data/Hora: {b['data']} às {b['hora']}\n")
                    f.write(f"Usuário  : {b['usuario']} | Computador: {b['computador']}\n")
                    f.write("-" * 50 + "\n")
                    
                    if b['campos_alterados']:
                        f.write("Campos Alterados:\n")
                        for c, v1, v2 in b['campos_alterados']:
                            f.write(f"  {c}: {v1} -> {v2}\n")
                    
                    if b['campos_inseridos']:
                        f.write("Outros Campos:\n")
                        for c, v in b['campos_inseridos'][:15]: # Limite de 15 para não poluir
                            f.write(f"  {c}: {v}\n")
                            
                    f.write("\n")
                f.write("\n")
        return True
    except Exception as e:
        print(e)
        return False

class BuscaLogsWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Busca Avançada em Logs do Sistema")
        self.geometry("900x700")
        self.minsize(800, 600)
        
        self._maximized = False
        self._normal_geometry = "900x700"
        
        self.resultados = {}
        self.fila_busca = queue.Queue()
        self.thread_busca = None
        self.config_app = carregar_config()
        self._sort_column = None
        self._sort_reverse = False
        self._col_headers = {
            "Modulo": "Módulo/Tela",
            "Nome do Arquivo": "Nome do Arquivo",
            "Data do Arquivo": "Data do Arquivo",
            "Ocorrências": "Qtd. Ocorrências",
        }
        self._filtro_modulo = ""
        self._resultados_raw = {}
        
        # Configurar ícone do projeto caso exista
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        icon_path = os.path.join(base_path, "icon.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        self._criar_widgets()
        
        # --- FIX: FORÇAR JANELA PARA A FRENTE ---
        # Deve ser executado APÓS criar os widgets, senão a tela congela vazia
        if parent:
            self.transient(parent)
            
        self.update_idletasks() # Força o Windows a desenhar os botões e campos
        self.attributes('-topmost', True) # Puxa para a frente absoluto
        self.lift()
        self.focus_force()
        self.grab_set() # Bloqueia a janela de trás
        self.after(200, lambda: self.attributes('-topmost', False))

    def _criar_widgets(self):
        # --- PAINEL DE PARÂMETROS ---
        frame_busca = ttk.LabelFrame(self, text="Parâmetros de Busca", padding=10)
        frame_busca.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(frame_busca, text="Pasta raiz:").grid(row=0, column=0, sticky=tk.E, padx=5, pady=5)
        self.ent_pasta = ttk.Entry(frame_busca, width=60)
        self.ent_pasta.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
        self.ent_pasta.insert(0, self.config_app.get('ultima_pasta', ''))
        
        ttk.Button(frame_busca, text="Selecionar 📁", command=self._selecionar_pasta).grid(row=0, column=2, padx=5, pady=5)
        
        ttk.Label(frame_busca, text="Termo / Valor:").grid(row=1, column=0, sticky=tk.E, padx=5, pady=5)
        self.ent_termo = ttk.Entry(frame_busca, width=60)
        self.ent_termo.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=5)
        self.ent_termo.bind("<Return>", lambda e: self._iniciar_busca())
        
        frame_botoes = ttk.Frame(frame_busca)
        frame_botoes.grid(row=1, column=2, padx=5, pady=5, sticky=tk.W)
        ttk.Button(frame_botoes, text="🔍 Buscar", command=self._iniciar_busca).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_botoes, text="🧹 Limpar", command=self._limpar_resultados).pack(side=tk.LEFT, padx=2)
        
        frame_chk = ttk.Frame(frame_busca)
        frame_chk.grid(row=2, column=1, sticky=tk.W, padx=5)
        
        self.var_subpastas = tk.BooleanVar(value=True)
        self.var_case = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame_chk, text="Incluir subpastas", variable=self.var_subpastas).pack(side=tk.LEFT, padx=(0, 15))
        ttk.Checkbutton(frame_chk, text="Ignorar maiúsculas/minúsculas (Case-insensitive)", variable=self.var_case).pack(side=tk.LEFT)
        
        frame_busca.columnconfigure(1, weight=1)
        
        # --- FILTRO POR MÓDULO ---
        frame_modulo = ttk.Frame(frame_busca)
        frame_modulo.grid(row=3, column=0, columnspan=3, sticky=tk.EW, padx=5, pady=(0, 5))
        
        ttk.Label(frame_modulo, text="Filtrar por módulo:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.var_modulo = tk.StringVar()
        self.cb_modulo = ttk.Combobox(frame_modulo, textvariable=self.var_modulo, width=40, state="readonly")
        self.cb_modulo['values'] = ["Todos os módulos"] + MODULOS_FIXOS
        self.var_modulo.set("Todos os módulos")
        self.cb_modulo.pack(side=tk.LEFT, padx=(0, 5))
        self.cb_modulo.bind("<<ComboboxSelected>>", self._on_modulo_selected)
        ttk.Button(frame_modulo, text="Múltiplos...", command=self._abrir_popup_modulos).pack(side=tk.LEFT, padx=2)
        
        # --- PAINEL DE PROGRESSO ---
        frame_progresso = ttk.LabelFrame(self, text="Progresso da Busca", padding=5)
        frame_progresso.pack(fill=tk.X, padx=10, pady=(0, 0))
        
        self.lbl_progresso = ttk.Label(frame_progresso, text="Aguardando...")
        self.lbl_progresso.pack(anchor=tk.W, padx=5)
        
        self.progresso = ttk.Progressbar(frame_progresso, mode='determinate')
        self.progresso.pack(fill=tk.X, padx=5, pady=(0, 5))
        
        # --- TOPO (maximize/minimize) ---
        self.frame_topo = ttk.Frame(self)
        self.frame_topo.pack(fill=tk.X, padx=10, pady=(5, 0))
        self.btn_maximizar = ttk.Button(self.frame_topo, text="⛶ Maximizar", command=self._toggle_maximizar)
        self.btn_maximizar.pack(side=tk.LEFT)
        self.bind("<F11>", lambda e: self._toggle_maximizar())
        
        # --- DIVISOR CENTRAL ---
        pane = ttk.PanedWindow(self, orient=tk.VERTICAL)
        pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 1. LISTA DE ARQUIVOS
        frame_lista = ttk.LabelFrame(pane, text="Arquivos Encontrados (Ctrl+click para selecionar múltiplos, Clique p/ detalhes, Duplo-clique p/ abrir)", padding=5)
        pane.add(frame_lista, weight=1)
        
        colunas = ("Modulo", "Nome do Arquivo", "Data do Arquivo", "Ocorrências")
        self.tree = ttk.Treeview(frame_lista, columns=colunas, show="headings", selectmode="extended")
        self.tree.heading("Modulo", text="Módulo/Tela", command=lambda: self._ordenar_por_coluna("Modulo"))
        self.tree.column("Modulo", width=150, anchor=tk.W, minwidth=80, stretch=True)
        self.tree.heading("Nome do Arquivo", text="Nome do Arquivo", command=lambda: self._ordenar_por_coluna("Nome do Arquivo"))
        self.tree.column("Nome do Arquivo", width=300, anchor=tk.W, minwidth=150, stretch=True)
        self.tree.heading("Data do Arquivo", text="Data do Arquivo", command=lambda: self._ordenar_por_coluna("Data do Arquivo"))
        self.tree.column("Data do Arquivo", width=120, anchor=tk.CENTER, minwidth=80, stretch=True)
        self.tree.heading("Ocorrências", text="Qtd. Ocorrências", command=lambda: self._ordenar_por_coluna("Ocorrências"))
        self.tree.column("Ocorrências", width=100, anchor=tk.CENTER, minwidth=60, stretch=True)
        
        scroll_tree_y = ttk.Scrollbar(frame_lista, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll_tree_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_tree_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        
        # Atalho Ctrl+C na tabela copia os detalhes para a área de transferência
        self.tree.bind("<Control-c>", lambda e: self._copiar_detalhes())
        self.tree.bind("<Control-C>", lambda e: self._copiar_detalhes())
        
        self.tree.bind("<Button-3>", self._on_tree_right_click)
        
        # 2. DETALHES DO LOG
        frame_detalhes = ttk.LabelFrame(pane, text="Detalhes e Valores das Ocorrências", padding=5)
        pane.add(frame_detalhes, weight=2)
        
        # Container superior para os botões de ação
        frame_acoes_detalhes = ttk.Frame(frame_detalhes)
        frame_acoes_detalhes.pack(fill=tk.X, padx=2, pady=2)
        
        self.btn_salvar_copia = ttk.Button(frame_acoes_detalhes, text="💾 Salvar cópia do arquivo", command=self._salvar_copia_arquivo, state=tk.DISABLED)
        self.btn_salvar_copia.pack(side=tk.LEFT)
        
        self.btn_copiar = ttk.Button(frame_acoes_detalhes, text="📋 Copiar Detalhes", command=self._copiar_detalhes, state=tk.DISABLED)
        self.btn_copiar.pack(side=tk.RIGHT)
        
        self.txt_detalhes = tk.Text(frame_detalhes, wrap=tk.WORD, font=("Consolas", 10), state=tk.DISABLED, bg="#F9F9F9")
        scroll_txt_y = ttk.Scrollbar(frame_detalhes, orient=tk.VERTICAL, command=self.txt_detalhes.yview)
        self.txt_detalhes.configure(yscrollcommand=scroll_txt_y.set)
        self.txt_detalhes.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_txt_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        self._configurar_tags_texto()
        
        # Bind resize event para responsividade
        self.bind("<Configure>", self._on_resize)
        
        # --- RODAPÉ ---
        frame_status = ttk.Frame(self, padding=5)
        frame_status.pack(fill=tk.X, padx=10, pady=5)
        
        self.btn_exportar = ttk.Button(frame_status, text="Exportar Resultados .txt", command=self._exportar, state=tk.DISABLED)
        self.btn_exportar.pack(side=tk.LEFT)
        
        self.lbl_status = ttk.Label(frame_status, text="Aguardando...")
        self.lbl_status.pack(side=tk.RIGHT)

    def _configurar_tags_texto(self):
        self.txt_detalhes.tag_configure("header", foreground="#2C3E50", font=("Consolas", 10, "bold"))
        self.txt_detalhes.tag_configure("info", foreground="#555555")
        self.txt_detalhes.tag_configure("campo", foreground="#34495E", font=("Consolas", 10, "bold"))
        self.txt_detalhes.tag_configure("val_antigo", foreground="#C0392B") 
        self.txt_detalhes.tag_configure("val_novo", foreground="#27AE60", font=("Consolas", 10, "bold")) 
        self.txt_detalhes.tag_configure("highlight", background="#F1C40F", foreground="black") 
        self.txt_detalhes.tag_configure("bg_exclusao", background="#FDEDEC", font=("Consolas", 10, "bold"), foreground="#C0392B")
        self.txt_detalhes.tag_configure("bg_insercao", background="#EAFAF1", font=("Consolas", 10, "bold"), foreground="#27AE60")
        self.txt_detalhes.tag_configure("separador", foreground="#BDC3C7")
        self.txt_detalhes.tag_configure("semantico", foreground="#8E44AD", font=("Consolas", 10, "bold"))

    def _toggle_maximizar(self):
        if self._maximized:
            self.state("normal")
            self.geometry(self._normal_geometry)
            self.btn_maximizar.config(text="⛶ Maximizar")
            self._maximized = False
        else:
            self._normal_geometry = self.geometry()
            self.state("zoomed")
            self.btn_maximizar.config(text="❐ Restaurar")
            self._maximized = True

    def _on_resize(self, event):
        if event.widget == self:
            w = self.winfo_width()
            # Ajusta dinamicamente o Entry de busca
            self.ent_pasta.configure(width=max(30, int(w / 14)))
            self.ent_termo.configure(width=max(30, int(w / 14)))

    def _selecionar_pasta(self):
        pasta = filedialog.askdirectory(initialdir=self.ent_pasta.get())
        if pasta:
            self.ent_pasta.delete(0, tk.END)
            self.ent_pasta.insert(0, pasta)
            self.config_app['ultima_pasta'] = pasta
            salvar_config(self.config_app)

    def _iniciar_busca(self):
        self._resultados_raw = {}
        self._filtro_modulos = []
        self.var_modulo.set("Todos os módulos")
        pasta = self.ent_pasta.get().strip()
        termo = self.ent_termo.get().strip()
        
        if not pasta or not os.path.exists(pasta):
            return messagebox.showwarning("Aviso", "A pasta selecionada é inválida ou não existe.")
        if not termo:
            return messagebox.showwarning("Aviso", "Digite um termo para buscar (Ex: um ID de pedido, NCM, ou erro).")
            
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        self.txt_detalhes.config(state=tk.NORMAL)
        self.txt_detalhes.delete(1.0, tk.END)
        self.txt_detalhes.config(state=tk.DISABLED)
        
        self.resultados = {}
        self._sort_column = None
        self._sort_reverse = False
        for cid, base in self._col_headers.items():
            self.tree.heading(cid, text=base)
        self.btn_exportar.config(state=tk.DISABLED)
        self.progresso['value'] = 0
        self.lbl_progresso.config(text="Aguardando...")
        self.config(cursor="wait")
        
        subpastas = self.var_subpastas.get()
        case_insensitive = self.var_case.get()
        
        self.thread_busca = threading.Thread(
            target=buscar_em_pasta, 
            args=(pasta, termo, subpastas, case_insensitive, self.fila_busca), 
            daemon=True
        )
        self.thread_busca.start()
        self.after(100, self._checar_fila)

    def _checar_fila(self):
        try:
            while not self.fila_busca.empty():
                msg = self.fila_busca.get_nowait()
                
                if msg['tipo'] == 'progresso':
                    total = msg['total']
                    atual = msg['atual']
                    pct = (atual / total * 100) if total > 0 else 0
                    self.progresso['maximum'] = total
                    self.progresso['value'] = atual
                    self.lbl_progresso.config(text=f"Lendo arquivos... {atual} de {total} ({pct:.0f}%)")
                    self.lbl_status.config(text=f"Processando arquivos... {atual} de {total}")
                    
                elif msg['tipo'] == 'erro':
                    print(f"Erro na thread de busca: {msg['msg']}")
                    
                elif msg['tipo'] == 'fim':
                    self.config(cursor="")
                    self._resultados_raw = msg['resultados']
                    self._popular_modulos_filtro(self._resultados_raw)
                    self._aplicar_filtro_modulo()
                    self.progresso['value'] = 0
                    return
        except queue.Empty:
            pass
            
        if self.thread_busca and self.thread_busca.is_alive():
            self.after(100, self._checar_fila)
        else:
            self.config(cursor="")

    def _limpar_resultados(self):
        """Limpa as grids e variáveis da busca atual."""
        self.ent_termo.delete(0, tk.END)
        self.resultados = {}
        self._resultados_raw = {}
        self._filtro_modulos = []
        self._sort_column = None
        self._sort_reverse = False
        self.cb_modulo['values'] = ["Todos os módulos"] + MODULOS_FIXOS
        self.var_modulo.set("Todos os módulos")
        for cid, base in self._col_headers.items():
            self.tree.heading(cid, text=base)
        self.btn_exportar.config(state=tk.DISABLED)
        self.btn_copiar.config(state=tk.DISABLED)

    def _exibir_resultados(self):
        total_arquivos = len(self.resultados)
        total_ocorrencias = sum(len(r['blocos']) for r in self.resultados.values())
        self._preencher_tree(self.resultados)
        self.lbl_status.config(text=f"Concluído: {total_arquivos} arquivo(s) com {total_ocorrencias} ocorrência(s).")
        if self.resultados:
            self.btn_exportar.config(state=tk.NORMAL)

    def _modulos_por_arquivo(self, r):
        mods = set()
        for b in r['blocos']:
            tela = b.get('tela', '').strip()
            if tela:
                mods.add(tela)
        return ", ".join(sorted(mods))

    def _preencher_tree(self, resultados):
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        items = []
        for fp, r in resultados.items():
            mods_str = self._modulos_por_arquivo(r)
            ocorr = len(r['blocos'])
            items.append((mods_str, r['nome'], r['data_arquivo'], ocorr, fp))
        
        if self._sort_column:
            col_idx = {"Modulo": 0, "Nome do Arquivo": 1, "Data do Arquivo": 2, "Ocorrências": 3}
            idx = col_idx[self._sort_column]
            
            def sort_key(item):
                val = item[idx]
                if self._sort_column == "Ocorrências":
                    return val
                if self._sort_column == "Data do Arquivo":
                    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S"):
                        try:
                            return datetime.datetime.strptime(str(val), fmt)
                        except (ValueError, TypeError):
                            pass
                    return datetime.datetime.min
                return str(val).lower()
            
            items.sort(key=sort_key, reverse=self._sort_reverse)
        
        for mods_str, nome, data_arquivo, ocorr, fp in items:
            self.tree.insert("", tk.END, values=(mods_str, nome, data_arquivo, ocorr), tags=(fp,))

    def _ordenar_por_coluna(self, col):
        if self._sort_column == col:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = col
            self._sort_reverse = False
        
        for cid, base in self._col_headers.items():
            arrow = " ▼" if (cid == col and self._sort_reverse) else " ▲" if cid == col else ""
            self.tree.heading(cid, text=base + arrow)
        
        self._preencher_tree(self.resultados)

    def _sort_key_bloco(self, bloco):
        data = bloco.get('data', '')
        hora = bloco.get('hora', '')
        if data and hora:
            for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
                try:
                    return datetime.datetime.strptime(f"{data} {hora}", fmt)
                except ValueError:
                    continue
        return datetime.datetime.min

    def _on_tree_select(self, event):
        sel = self.tree.selection()
        if not sel:
            self.txt_detalhes.config(state=tk.NORMAL)
            self.txt_detalhes.delete(1.0, tk.END)
            self.txt_detalhes.config(state=tk.DISABLED)
            self.btn_copiar.config(state=tk.DISABLED)
            self.btn_salvar_copia.config(state=tk.DISABLED)
            return

        todos_blocos = []
        nomes_arquivos = set()
        tem_arquivo_existente = False

        for item in sel:
            filepath = self.tree.item(item, "tags")[0]
            if filepath in self.resultados:
                r = self.resultados[filepath]
                for b in r['blocos']:
                    bloco = dict(b)
                    bloco['_nome_arquivo'] = r['nome']
                    todos_blocos.append(bloco)
                nomes_arquivos.add(r['nome'])
                if os.path.exists(filepath):
                    tem_arquivo_existente = True

        if not todos_blocos:
            self.txt_detalhes.config(state=tk.NORMAL)
            self.txt_detalhes.delete(1.0, tk.END)
            self.txt_detalhes.insert(tk.END, "Nenhum bloco encontrado para a seleção atual.\n", "info")
            self.txt_detalhes.config(state=tk.DISABLED)
            self.btn_copiar.config(state=tk.DISABLED)
            self.btn_salvar_copia.config(state=tk.DISABLED)
            return

        todos_blocos.sort(key=self._sort_key_bloco)

        if len(sel) == 1:
            fp = self.tree.item(sel[0], "tags")[0]
            self._ultimo_filepath_selecionado = fp
        else:
            self._ultimo_filepath_selecionado = None

        merged = {
            'nome': " | ".join(sorted(nomes_arquivos)),
            'blocos': todos_blocos,
            'multi_arquivo': len(sel) > 1
        }
        self._mostrar_detalhes(merged)

        if tem_arquivo_existente and len(sel) == 1:
            self.btn_salvar_copia.config(state=tk.NORMAL)
        else:
            self.btn_salvar_copia.config(state=tk.DISABLED)

    def _get_selected_filepath(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return self.tree.item(sel[0], "tags")[0]

    def _on_tree_right_click(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            filepath = self._get_selected_filepath()
            if filepath and os.path.exists(filepath):
                menu = tk.Menu(self, tearoff=0)
                menu.add_command(label="📂 Abrir arquivo original", command=lambda: self._abrir_arquivo(filepath))
                menu.add_command(label="💾 Salvar cópia do arquivo...", command=lambda: self._salvar_copia(filepath))
                menu.tk_popup(event.x_root, event.y_root)

    def _on_tree_double_click(self, event):
        sel = self.tree.selection()
        if not sel: return
        
        filepath = self.tree.item(sel[0], "tags")[0]
        
        if filepath in self.resultados and os.path.exists(filepath):
            try:
                os.startfile(filepath)
            except Exception as e:
                messagebox.showerror("Erro", f"Não foi possível abrir o arquivo:\n{e}")

    def _abrir_arquivo(self, filepath):
        try:
            os.startfile(filepath)
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível abrir o arquivo:\n{e}")

    def _salvar_copia(self, filepath):
        import shutil
        destino = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=os.path.basename(filepath),
            filetypes=[("Arquivo de Texto", "*.txt"), ("Arquivo de Log", "*.log"), ("Todos os arquivos", "*.*")]
        )
        if destino:
            try:
                shutil.copy2(filepath, destino)
                messagebox.showinfo("Sucesso", f"Cópia salva em:\n{destino}", parent=self)
            except Exception as e:
                messagebox.showerror("Erro", f"Não foi possível copiar o arquivo:\n{e}", parent=self)

    def _salvar_copia_arquivo(self):
        filepath = self._ultimo_filepath_selecionado if hasattr(self, '_ultimo_filepath_selecionado') else None
        if filepath and os.path.exists(filepath):
            self._salvar_copia(filepath)

    def _mostrar_detalhes(self, resultado):
        self.txt_detalhes.config(state=tk.NORMAL)
        self.txt_detalhes.delete(1.0, tk.END)
        
        termo = self.ent_termo.get()
        case_ins = self.var_case.get()
        termo_busca = termo.lower() if case_ins else termo
        
        blocos = resultado['blocos']
        ocorrencias = len(blocos)
        datas = [f"{b['data']} {b['hora']}".strip() for b in blocos if b.get('data') or b.get('hora')]
        data_min = min(datas) if datas else ''
        data_max = max(datas) if datas else ''
        periodo = f"{data_min} — {data_max}" if data_min != data_max else data_min
        
        if resultado.get('multi_arquivo'):
            self.txt_detalhes.insert(tk.END, f"📂 Múltiplos Arquivos Selecionados\n", "header")
        self.txt_detalhes.insert(tk.END, f"📄 Arquivo(s): {resultado['nome']}\n", "header")
        if periodo:
            self.txt_detalhes.insert(tk.END, f"📅 Período nos logs: {periodo}\n", "info")
        self.txt_detalhes.insert(tk.END, f"🔎 Ocorrências: {ocorrencias}\n", "header")
        self.txt_detalhes.insert(tk.END, "━" * 60 + "\n\n", "separador")
        
        for bloco in blocos:
            tipo = bloco['tipo_operacao']
            bg_tag = ""
            if tipo in ["EXCLUSÃO", "CANCELAMENTO", "ESTORNO"]: bg_tag = "bg_exclusao"
            elif tipo == "INSERÇÃO": bg_tag = "bg_insercao"
            
            nome_arq = bloco.get('_nome_arquivo', '')
            if nome_arq:
                self.txt_detalhes.insert(tk.END, f"📄 Fonte: {nome_arq}\n", "info")
            
            self.txt_detalhes.insert(tk.END, f"🔧 Operação : ", "info")
            self.txt_detalhes.insert(tk.END, f"{tipo}\n", bg_tag if bg_tag else "header")
                
            self.txt_detalhes.insert(tk.END, f"📅 Data/Hora: {bloco['data']} às {bloco['hora']}\n", "info")
            self.txt_detalhes.insert(tk.END, f"👤 Usuário  : {bloco['usuario']}\n", "info")
            self.txt_detalhes.insert(tk.END, f"🖥️  Computador: {bloco['computador']}\n", "info")
            self.txt_detalhes.insert(tk.END, f"📋 Tela/Módulo: {bloco['tela']}\n", "info")
            
            significado = bloco.get('significado', '')
            if significado:
                self.txt_detalhes.insert(tk.END, f"💡 {significado}\n", "semantico")
            
            self.txt_detalhes.insert(tk.END, "\n", "info")
            
            # Mostrar campos-chave primeiro (mais relevantes)
            campos_chave = bloco.get('campos_chave', [])
            if campos_chave:
                self.txt_detalhes.insert(tk.END, "📌 O que mudou de fato:\n", "header")
                for item in campos_chave:
                    if len(item) == 3:
                        c, v1, v2 = item
                        self._insert_highlighted(f"  • {c}: ", "campo", termo, case_ins)
                        self._insert_highlighted(f"{v1} ", "val_antigo", termo, case_ins)
                        self.txt_detalhes.insert(tk.END, " ──►  ", "info")
                        self._insert_highlighted(f"{v2}\n", "val_novo", termo, case_ins)
                    else:
                        c, v = item
                        self._insert_highlighted(f"  • {c}: ", "campo", termo, case_ins)
                        self._insert_highlighted(f"{v}\n", "val_novo", termo, case_ins)
                self.txt_detalhes.insert(tk.END, "\n", "info")
            
            # Mostrar campos alterados adicionais (não-chave)
            campos_alterados_extra = [(c, v1, v2) for c, v1, v2 in bloco['campos_alterados']
                                      if (c, v1, v2) not in campos_chave]
            if campos_alterados_extra:
                self.txt_detalhes.insert(tk.END, "Demais alterações:\n", "info")
                count_alt = 0
                for c, v1, v2 in campos_alterados_extra:
                    if count_alt >= 10:
                        self.txt_detalhes.insert(tk.END, f"  • ... e {len(campos_alterados_extra) - count_alt} campo(s) oculto(s) ...\n", "info")
                        break
                    self._insert_highlighted(f"  • {c}: ", "campo", termo, case_ins)
                    self._insert_highlighted(f"{v1} ", "val_antigo", termo, case_ins)
                    self.txt_detalhes.insert(tk.END, " ──►  ", "info")
                    self._insert_highlighted(f"{v2}\n", "val_novo", termo, case_ins)
                    count_alt += 1
            
            if bloco['campos_inseridos']:
                self.txt_detalhes.insert(tk.END, "Valores Registrados:\n", "info")
                count = 0
                for c, v in bloco['campos_inseridos']:
                    if count >= 10:
                        self.txt_detalhes.insert(tk.END, f"  • ... e {len(bloco['campos_inseridos']) - count} campo(s) oculto(s) ...\n", "info")
                        break
                    v_str = f"{c} {v}"
                    if termo_busca in (v_str.lower() if case_ins else v_str) or tipo == "INSERÇÃO":
                        self._insert_highlighted(f"  • {c}: ", "campo", termo, case_ins)
                        self._insert_highlighted(f"{v}\n", "info" if (c, v) not in campos_chave else "val_novo", termo, case_ins)
                        count += 1
                        
            self.txt_detalhes.insert(tk.END, "\n" + "─" * 40 + "\n\n", "separador")
            
        self.txt_detalhes.config(state=tk.DISABLED)
        self.btn_copiar.config(state=tk.NORMAL)

    def _copiar_detalhes(self):
        texto = self.txt_detalhes.get(1.0, tk.END).strip()
        if texto:
            self.clipboard_clear()
            self.clipboard_append(texto)
            messagebox.showinfo("Copiado", "Conteúdo do log copiado para a área de transferência!", parent=self)

    def _insert_highlighted(self, text, base_tag, term, case_insensitive):
        if not term:
            self.txt_detalhes.insert(tk.END, text, base_tag)
            return
            
        flags = re.IGNORECASE if case_insensitive else 0
        last_idx = 0
        
        for match in re.finditer(re.escape(term), text, flags):
            start, end = match.span()
            if start > last_idx:
                self.txt_detalhes.insert(tk.END, text[last_idx:start], base_tag)
            self.txt_detalhes.insert(tk.END, text[start:end], ("highlight", base_tag))
            last_idx = end
            
        if last_idx < len(text):
            self.txt_detalhes.insert(tk.END, text[last_idx:], base_tag)

    def _exportar(self):
        if not self.resultados:
            return
            
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        sugestao = f"Resultados_Busca_Logs_{timestamp}.txt"
        
        filepath = filedialog.asksaveasfilename(defaultextension=".txt", initialfile=sugestao, filetypes=[("Arquivo de Texto", "*.txt")])
        if filepath:
            if exportar_resultados(self.resultados, filepath):
                messagebox.showinfo("Sucesso", "Resultados exportados com sucesso.")
            else:
                messagebox.showerror("Erro", "Erro ao exportar os resultados.")

    # ---- Filtro por módulo ----
    def _popular_modulos_filtro(self, resultados):
        modulos = set(MODULOS_FIXOS)
        for r in resultados.values():
            for b in r['blocos']:
                tela = b.get('tela', '').strip()
                if tela and tela not in ("Operação Desconhecida", "Operação", ""):
                    modulos.add(tela)
        self._modulos_disponiveis = sorted(modulos)
        self.cb_modulo['values'] = ["Todos os módulos"] + self._modulos_disponiveis
        if len(self._filtro_modulos) == 1 and self._filtro_modulos[0] in modulos:
            self.var_modulo.set(self._filtro_modulos[0])
        elif len(self._filtro_modulos) > 1:
            self.var_modulo.set(f"Múltiplos ({len(self._filtro_modulos)})")
        else:
            self._filtro_modulos = []
            self.var_modulo.set("Todos os módulos")

    def _on_modulo_selected(self, event=None):
        val = self.var_modulo.get()
        self._filtro_modulos = [] if val == "Todos os módulos" else [val]
        self._aplicar_filtro_modulo()

    def _abrir_popup_modulos(self):
        if not hasattr(self, '_modulos_disponiveis') or not self._modulos_disponiveis:
            messagebox.showinfo("Aviso", "Faça uma busca primeiro para carregar os módulos disponíveis.", parent=self)
            return
        win = tk.Toplevel(self)
        win.title("Selecionar Módulos")
        win.geometry("450x500")
        win.transient(self)
        win.grab_set()

        ttk.Label(win, text="Selecione os módulos desejados:", font=("", 10, "bold")).pack(anchor=tk.W, padx=10, pady=10)

        outer = ttk.Frame(win)
        outer.pack(fill=tk.BOTH, expand=True, padx=10)

        canvas = tk.Canvas(outer, highlightthickness=0, bg="#FFFFFF")
        scrollbar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        scrollable = ttk.Frame(canvas)

        scrollable.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)

        vars_modulos = {}
        for mod in self._modulos_disponiveis:
            var = tk.BooleanVar(value=mod in self._filtro_modulos)
            ttk.Checkbutton(scrollable, text=mod, variable=var).pack(anchor=tk.W, padx=15, pady=2)
            vars_modulos[mod] = var

        def aplicar():
            self._filtro_modulos = sorted(m for m, v in vars_modulos.items() if v.get())
            if len(self._filtro_modulos) == 1:
                self.var_modulo.set(self._filtro_modulos[0])
            elif self._filtro_modulos:
                self.var_modulo.set(f"Múltiplos ({len(self._filtro_modulos)})")
            else:
                self.var_modulo.set("Todos os módulos")
            self._aplicar_filtro_modulo()
            win.destroy()

        btn_frame = ttk.Frame(win, padding=10)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="Aplicar", command=aplicar).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancelar", command=win.destroy).pack(side=tk.RIGHT, padx=5)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _aplicar_filtro_modulo(self):
        if not self._resultados_raw:
            return
        if not self._filtro_modulos:
            self.resultados = self._resultados_raw
        else:
            filtrados = {}
            for fp, r in self._resultados_raw.items():
                blocos_filtrados = [b for b in r['blocos'] if b.get('tela', '').strip() in self._filtro_modulos]
                if blocos_filtrados:
                    r_filtrado = dict(r)
                    r_filtrado['blocos'] = blocos_filtrados
                    filtrados[fp] = r_filtrado
            self.resultados = filtrados
        self._exibir_resultados()


if __name__ == '__main__':
    root = tk.Tk()
    root.withdraw() # Esconde a principal para exibir só o Toplevel
    app = BuscaLogsWindow(root)
    root.mainloop()
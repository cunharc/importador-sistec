import os
import re
import json
import threading
from pathlib import Path
from collections import OrderedDict

CONFIG_MODULOS = "config_modulos_log.json"
PASTA_PADRAO_LOG = r"D:\Rafael Cunha\log"

def _extrair_telas_do_arquivo(filepath: str) -> set:
    """Extrai nomes de telas/módulos de um arquivo de log."""
    telas = set()
    try:
        with open(filepath, 'r', encoding='latin-1', errors='replace') as f:
            conteudo = f.read()
    except Exception:
        return telas

    blocos = re.split(r'=+', conteudo)
    for bloco_raw in blocos:
        linhas = [l for l in bloco_raw.split('\n') if l.strip() and not l.startswith('===')]
        if not linhas:
            continue

        tela = ""
        if 'Data' not in linhas[0] and 'Usuário' not in linhas[0] and 'Usu?rio' not in linhas[0]:
            tela = linhas[0].strip()
        else:
            for i, linha in enumerate(linhas):
                if 'Tipo de Altera' in linha and i + 1 < len(linhas):
                    next_line = linhas[i+1].strip()
                    if ':' not in next_line and '----' not in next_line:
                        tela = next_line
                        break

        if tela and tela not in ("Operação Desconhecida", "Operação", ""):
            telas.add(tela)
    return telas

def scan_modulos(pasta: str = None) -> OrderedDict:
    """Varre a pasta de logs e retorna OrderedDict {tela: count}."""
    if not pasta:
        pasta = PASTA_PADRAO_LOG
    if not os.path.isdir(pasta):
        return OrderedDict()

    modulos = OrderedDict()
    p = Path(pasta)
    exts = {'.txt', '.log'}
    for f in p.glob("**/*.*"):
        if f.suffix.lower() in exts:
            telas = _extrair_telas_do_arquivo(str(f))
            for t in telas:
                modulos[t] = modulos.get(t, 0) + 1
    return OrderedDict(sorted(modulos.items(), key=lambda x: (-x[1], x[0])))

def carregar_modulos() -> list:
    """Carrega a lista de módulos conhecidos do JSON."""
    if os.path.exists(CONFIG_MODULOS):
        try:
            with open(CONFIG_MODULOS, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return []

def salvar_modulos(modulos: list):
    """Salva a lista de módulos conhecidos no JSON."""
    try:
        with open(CONFIG_MODULOS, 'w', encoding='utf-8') as f:
            json.dump(modulos, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def merge_modulos(existentes: list, novos: OrderedDict) -> list:
    """Mescla módulos descobertos com a lista existente."""
    existentes_set = set(existentes)
    for tela in novos:
        if tela not in existentes_set:
            existentes.append(tela)
            existentes_set.add(tela)
    return sorted(existentes)

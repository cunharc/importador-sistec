# -*- coding: utf-8 -*-
"""Controle de versão do sistema."""

VERSAO = "3.1.2"
DATA_VERSAO = "02/06/2026"

MODULOS = {
    "Plano de Contas": {
        "status": "pronto",
        "descricao": "Importação de plano de contas"
    },
    "NCM": {
        "status": "ajustes",
        "descricao": "Classificação fiscal de NCMs"
    },
    "CFOP": {
        "status": "pronto",
        "descricao": "Parametrização de CFOPs"
    },
    "ICMS": {
        "status": "pronto",
        "descricao": "Matriz de faixas ICMS"
    },
    "Importação XML": {
        "status": "ajustes",
        "descricao": "Importação genérica de XML"
    },
    "Produtos": {
        "status": "ajustes",
        "descricao": "Cadastro de produtos"
    },
    "Reforma Tributária": {
        "status": "ajustes",
        "descricao": "CBS/IBS substituição"
    },
    "Busca de Logs": {
        "status": "pronto",
        "descricao": "Pesquisa avançada em arquivos de log ERP"
    }
}

def get_info():
    """Retorna informações da versão."""
    return f"Importador Sistec v{VERSAO} ({DATA_VERSAO})"

def get_modulos_prontos():
    """Retorna lista de módulos prontos."""
    return [k for k, v in MODULOS.items() if v["status"] == "pronto"]

def get_modulos_em_ajuste():
    """Retorna lista de módulos em ajuste."""
    return [k for k, v in MODULOS.items() if v["status"] == "ajustes"]

def marcar_modulo_pronto(nome):
    """Marca um módulo como pronto."""
    if nome in MODULOS:
        MODULOS[nome]["status"] = "pronto"
        return True
    return False

if __name__ == "__main__":
    print(get_info())
    print("\nModulos prontos:")
    for m in get_modulos_prontos():
        print(f"  [OK] {m}")
    print("\nModulos em ajuste:")
    for m in get_modulos_em_ajuste():
        print(f"  [--] {m}")

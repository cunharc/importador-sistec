# -*- coding: utf-8 -*-
"""Controle de versão do sistema."""

VERSAO = "4.18"
DATA_VERSAO = "11/08/2026"

MODULOS = {
    "Notas Fiscais (XML)": {
        "status": "pronto",
        "descricao": "Importa notas de emissao propria (entrada e saida) dos XMLs, validando cliente, natureza de operacao e produto"
    },
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
    },
    "Importação Clientes Planilha": {
        "status": "pronto",
        "descricao": "Importação de clientes via planilha Excel/CSV"
    },
    "Clientes NF-e": {
        "status": "pronto",
        "descricao": "Importação de clientes e fornecedores via XML NF-e"
    },
    "Importação Produtos Planilha": {
        "status": "pronto",
        "descricao": "Importação de produtos via planilha Excel/CSV"
    },
    "Importação Receber": {
        "status": "pronto",
        "descricao": "Importação de contas a receber via planilha"
    },
    "Importação Pagar": {
        "status": "pronto",
        "descricao": "Importação de contas a pagar via planilha"
    },
    "Importação Lista Preços": {
        "status": "ajustes",
        "descricao": "Importação de lista de preços via planilha"
    },
    "Lista de Preços XML": {
        "status": "ajustes",
        "descricao": "Criação de lista de preços a partir de XMLs NF-e"
    },
    "Importação Tributação": {
        "status": "ajustes",
        "descricao": "Importação de tributação NCM via planilha com criação de faixas ICMS e regras RT"
    },
    "Auditoria Geral": {
        "status": "pronto",
        "descricao": "Auditoria tributária gerencial NF-e"
    },
    "Auditoria por Produto": {
        "status": "pronto",
        "descricao": "Auditoria tributária por produto"
    },
    "Duplicar/Configurar Empresa": {
        "status": "pronto",
        "descricao": "Clona empresa/filial (EMPRESA, PARAM, FILIAL, CONFIG NF-e), edita campo a campo e ajusta configs em lote (NF-e/pedidos/títulos) comparando com uma empresa de referência"
    },
    "Vínculo CC x Plano de Contas": {
        "status": "pronto",
        "descricao": "Vincula centros de custo às contas do plano (contabilização automática) em massa, com árvore de CC e busca do plano"
    },
    "Importação Estoque de Produção": {
        "status": "ajustes",
        "descricao": "Importa estoque de Produto Acabado por etiquetas via planilha, gerando Ordem de Desossa de inventário, itens PA e as pesagens"
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

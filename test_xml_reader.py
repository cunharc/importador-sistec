import pytest
import os
from utils.xml_reader import parse_nfe, ler_nfe

CAMINHO_XML = "NFe_exemplo.xml"

def test_parse_nfe_returns_dict():
    resultado = parse_nfe(CAMINHO_XML)
    assert isinstance(resultado, dict)
    assert 'chave_nfe' in resultado
    assert 'itens' in resultado

def test_parse_nfe_chave():
    resultado = parse_nfe(CAMINHO_XML)
    assert resultado['chave_nfe'] == '35200600012345000188550010000000011000000010'

def test_parse_nfe_itens():
    resultado = parse_nfe(CAMINHO_XML)
    assert len(resultado['itens']) == 1

def test_parse_nfe_item_data():
    resultado = parse_nfe(CAMINHO_XML)
    item = resultado['itens'][0]
    assert item['c_prod'] == '1001'
    assert item['x_prod'] == 'PRODUTO EXEMPLO DE TESTE'
    assert item['ncm'] == '22021000'
    assert item['cfop'] == '5101'
    assert item['u_com'] == 'UN'
    assert item['q_com'] == 10.0
    assert item['v_un_com'] == 25.5

def test_parse_nfe_icms():
    resultado = parse_nfe(CAMINHO_XML)
    item = resultado['itens'][0]
    assert item['icms_cst'] == '00'
    assert item['p_icms'] == 12.0

def test_parse_nfe_pis_cofins():
    resultado = parse_nfe(CAMINHO_XML)
    item = resultado['itens'][0]
    assert item['pis_cst'] == '08'
    assert item['cofins_cst'] == '08'

def test_parse_nfe_emitente():
    resultado = parse_nfe(CAMINHO_XML)
    item = resultado['itens'][0]
    assert item['emit_cnpj'] == '00012345000188'
    assert item['emit_nome'] == 'EMPRESA FORNECEDORA LTDA'

def test_parse_nfe_destinatario():
    resultado = parse_nfe(CAMINHO_XML)
    item = resultado['itens'][0]
    assert item['dest_cnpj'] == '00098765000199'
    assert item['dest_nome'] == 'EMPRESA CLIENTE LTDA'

def test_parse_nfe_ufs():
    resultado = parse_nfe(CAMINHO_XML)
    item = resultado['itens'][0]
    assert item['uf_dest'] == 'MG'
    assert item['tipo_cliente'] == 'CT'

def test_parse_nfe_inf_cpl():
    resultado = parse_nfe(CAMINHO_XML)
    assert 'TESTE DE IMPORTACAO' in resultado['inf_cpl']

def test_ler_nfe_emitente():
    registros = ler_nfe(CAMINHO_XML)
    emitentes = [r for r in registros if r['tipo'] == 'Fornecedor']
    assert len(emitentes) == 1
    assert emitentes[0]['documento'] == '00012345000188'
    assert emitentes[0]['razao'] == 'EMPRESA FORNECEDORA LTDA'

def test_ler_nfe_destinatario():
    registros = ler_nfe(CAMINHO_XML)
    clientes = [r for r in registros if r['tipo'] == 'Cliente']
    assert len(clientes) == 1
    assert clientes[0]['documento'] == '00098765000199'
    assert clientes[0]['razao'] == 'EMPRESA CLIENTE LTDA'

def test_ler_nfe_enderecos():
    registros = ler_nfe(CAMINHO_XML)
    fornecedor = [r for r in registros if r['tipo'] == 'Fornecedor'][0]
    assert fornecedor['endereco'] == 'RUA DAS INDUSTRIAS'
    assert fornecedor['uf'] == 'SP'

def test_ler_nfe_condicao_pagamento():
    registros = ler_nfe(CAMINHO_XML)
    cliente = [r for r in registros if r['tipo'] == 'Cliente'][0]
    assert len(cliente['condicao_pagamento']) > 0
    assert cliente['condicao_pagamento_desc'] is not None

import pytest
from utils.transformer import DataTransformer

def test_prepare_codigo_produto_existente():
    existentes = {'1', '2', '100', '101'}
    cod, aux = DataTransformer.prepare_codigo_produto('100', existentes)
    assert cod == '102' # Pega o maior numérico e soma 1
    assert aux == '100'

def test_prepare_codigo_produto_nao_existente():
    existentes = {'1', '2'}
    cod, aux = DataTransformer.prepare_codigo_produto('ALFA50', existentes)
    assert cod == 'ALFA50'
    assert aux == 'ALFA50'

def test_prepare_produto_cest_valido():
    xml_item = {'x_prod': 'PRODUTO TESTE', 'cest': '07.124.00'}
    res = DataTransformer.prepare_produto(xml_item, {}, {})
    assert res['PRODUTO_CEST'] == '0712400'

def test_prepare_produto_cest_vazio():
    xml_item = {'x_prod': 'PRODUTO TESTE', 'cest': ''}
    res = DataTransformer.prepare_produto(xml_item, {}, {})
    assert res['PRODUTO_CEST'] is None

def test_prepare_produto_cbarra_invalido():
    xml_item = {'x_prod': 'TESTE', 'c_ean': 'SEM GTIN'}
    res = DataTransformer.prepare_produto(xml_item, {}, {})
    assert res['PRODUTO_CBARRA'] is None
    
    xml_item = {'x_prod': 'TESTE', 'c_ean': '00000000000000'}
    res2 = DataTransformer.prepare_produto(xml_item, {}, {})
    assert res2['PRODUTO_CBARRA'] is None

def test_prepare_produto_truncar_descricao():
    desc_longa = "A" * 60
    xml_item = {'x_prod': desc_longa}
    res = DataTransformer.prepare_produto(xml_item, {}, {})
    assert len(res['PRODUTO_DESCRICAO']) == 50
    assert len(res['PRODUTO_DESCRICAO2']) == 10

def test_clean_float_virgula():
    assert DataTransformer.clean_float('12,50') == 12.5

def test_clean_float_ponto():
    assert DataTransformer.clean_float('12.50') == 12.5

def test_clean_float_invalido():
    assert DataTransformer.clean_float(None) is None
    assert DataTransformer.clean_float('') is None
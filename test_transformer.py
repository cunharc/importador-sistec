import pytest
from utils.transformer import DataTransformer

def test_prepare_codigo_produto_existente():
    existentes = {'1', '2', '100', '101'}
    cod, aux = DataTransformer.prepare_codigo_produto('100', existentes)
    assert cod == '3' # Gap-filling: menor lacuna disponível
    assert aux == '100'

def test_prepare_codigo_produto_nao_existente():
    existentes = {'1', '2'}
    cod, aux = DataTransformer.prepare_codigo_produto('ALFA50', existentes)
    assert cod == 'ALFA50'
    assert aux == 'ALFA50'

def test_prepare_codigo_produto_sequencial():
    existentes = {'1', '2', '5', '100'}
    cod, aux = DataTransformer.prepare_codigo_produto('', existentes, modo='sequencial')
    assert cod == '101'
    assert aux is None

def test_prepare_codigo_produto_sequencial_vazio():
    cod, aux = DataTransformer.prepare_codigo_produto('', set(), modo='sequencial')
    assert cod == '1'
    assert aux is None

def test_prepare_codigo_produto_sequencial_zeros():
    existentes = {'001', '002', '005'}
    cod, aux = DataTransformer.prepare_codigo_produto('', existentes, modo='sequencial')
    assert cod == '6'
    assert aux is None

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
    assert len(res['PRODUTO_DESCRICAO']) == 60

def test_clean_float_virgula():
    assert DataTransformer.clean_float('12,50') == 12.5

def test_clean_float_ponto():
    assert DataTransformer.clean_float('12.50') == 12.5

def test_clean_float_invalido():
    assert DataTransformer.clean_float(None) is None
    assert DataTransformer.clean_float('') is None
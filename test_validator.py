import pytest
from utils.validator import ValidatorFiscal

@pytest.fixture
def validator_mock():
    erp_produtos = [
        {
            'produto_codigo': '1',
            'produto_descricao': 'PRODUTO A',
            'produto_class_fiscal': '12345678',
            'produto_icms': 1,
            'produto_cbarra': '7891011121314'
        }
    ]
    regras_icms = [
        {'aicms_faixa': 1, 'aicms_estado': 'SP', 'aicms_situacao_cont': '000', 'aicms_aliquota_cont': 18.0, 'aicms_data': '2025-01-01'}
    ]
    return ValidatorFiscal(erp_produtos, regras_icms, [], [], [])

def test_validar_produto_nao_encontrado(validator_mock):
    xml_item = {'x_prod': 'XYZ DESCONHECIDO', 'ncm': '00000000'}
    res = validator_mock.validate(xml_item, 'SP')
    assert res.status == 'NAO_ENCONTRADO'

def test_validar_produto_gtin_match(validator_mock):
    xml_item = {'x_prod': 'NOVO NOME', 'c_ean': '7891011121314', 'ncm': '12345678'}
    res = validator_mock.validate(xml_item, 'SP')
    assert res.erp_match is not None
    assert res.score >= 100
    assert res.auto_approve is True

def test_validar_divergencia_ncm(validator_mock):
    xml_item = {'x_prod': 'PRODUTO A', 'ncm': '87654321'} # Descrição exata garante match, NCM errado
    res = validator_mock.validate(xml_item, 'SP')
    assert res.status == 'DIVERGENTE'
    assert any('NCM divergente' in d for d in res.divergencias)

def test_validar_divergencia_ncm_tamanho(validator_mock):
    xml_item = {'x_prod': 'PRODUTO A', 'ncm': '1234.56.78'} # Tem pontuação
    res = validator_mock.validate(xml_item, 'SP')
    assert any('inválido' in d.lower() for d in res.divergencias)

def test_validar_icms_tolerancia_ok(validator_mock):
    # Alíquota no banco é 18.0. XML vem com 18.001
    xml_item = {
        'x_prod': 'PRODUTO A', 'ncm': '12345678', 'c_ean': '7891011121314',
        'icms_cst': '000', 'p_icms': 18.001
    }
    res = validator_mock.validate(xml_item, 'SP')
    assert not any('% ICMS divergente' in d for d in res.divergencias)

def test_validar_icms_divergente(validator_mock):
    # Alíquota no banco é 18.0. XML vem com 17.0
    xml_item = {
        'x_prod': 'PRODUTO A', 'ncm': '12345678', 'c_ean': '7891011121314',
        'icms_cst': '000', 'p_icms': 17.0
    }
    res = validator_mock.validate(xml_item, 'SP')
    assert res.status == 'DIVERGENTE'
    assert any('% ICMS divergente' in d for d in res.divergencias)
import pytest
from utils.xml_reader import parse_nfe

CAMINHO_XML = "NFe_exemplo.xml"


def _agrupar_cfops_por_base(itens_xml):
    mapa = {}
    for i in itens_xml:
        cfop = str(i.get('cfop', '')).strip()
        if not cfop:
            continue
        base = cfop[:4] if len(cfop) >= 4 else cfop
        if base not in mapa:
            mapa[base] = {'cfop': base, 'ocorrencias': 1}
        else:
            mapa[base]['ocorrencias'] += 1
    return sorted(mapa.values(), key=lambda x: x['ocorrencias'], reverse=True)


def test_cfop_analysis_groups_by_base():
    nfe = parse_nfe(CAMINHO_XML)
    itens = nfe.get('itens', [])
    assert len(itens) == 1
    assert itens[0]['cfop'] == '5101'

    resultado = _agrupar_cfops_por_base(itens)
    assert len(resultado) == 1
    assert resultado[0]['cfop'] == '5101'
    assert resultado[0]['ocorrencias'] == 1


def test_cfop_analysis_truncates_6digit_to_base():
    itens_fake = [
        {'cfop': '510101'},
        {'cfop': '510102'},
        {'cfop': '510201'},
    ]
    resultado = _agrupar_cfops_por_base(itens_fake)
    assert len(resultado) == 2
    m = {r['cfop']: r['ocorrencias'] for r in resultado}
    assert m['5101'] == 2
    assert m['5102'] == 1


def test_cfop_analysis_multiple_same_base():
    itens_fake = [
        {'cfop': '5101'},
        {'cfop': '5102'},
        {'cfop': '5101'},
    ]
    resultado = _agrupar_cfops_por_base(itens_fake)
    assert len(resultado) == 2
    m = {r['cfop']: r['ocorrencias'] for r in resultado}
    assert m['5101'] == 2
    assert m['5102'] == 1


def test_cfop_analysis_skips_empty():
    itens_fake = [
        {'cfop': ''},
        {'cfop': '   '},
        {'cfop': '5101'},
        {},
    ]
    resultado = _agrupar_cfops_por_base(itens_fake)
    assert len(resultado) == 1
    assert resultado[0]['cfop'] == '5101'

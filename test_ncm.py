import pytest
import tkinter as tk
from telas.tela_ncm import TelaNcm
from utils.xml_reader import parse_nfe

CAMINHO_XML = "NFe_exemplo.xml"


@pytest.fixture(scope="module")
def tela_ncm(root):
    tela = TelaNcm(root)
    yield tela


class TestGetTaxKey:
    def test_same_icms_different_pis_cst(self, tela_ncm):
        item1 = {'icms_cst': '00', 'p_icms': '12', 'p_red_bc': '0', 'c_benef': '',
                 'pis_cst': '01', 'p_pis': '1.65', 'cofins_cst': '01', 'p_cofins': '7.6'}
        item2 = {'icms_cst': '00', 'p_icms': '12', 'p_red_bc': '0', 'c_benef': '',
                 'pis_cst': '08', 'p_pis': '0', 'cofins_cst': '08', 'p_cofins': '0'}
        assert tela_ncm._get_tax_key(item1) != tela_ncm._get_tax_key(item2)

    def test_same_icms_different_pis_alq(self, tela_ncm):
        item1 = {'icms_cst': '00', 'p_icms': '12', 'p_red_bc': '0', 'c_benef': '',
                 'pis_cst': '01', 'p_pis': '1.65', 'cofins_cst': '01', 'p_cofins': '7.6'}
        item2 = {'icms_cst': '00', 'p_icms': '12', 'p_red_bc': '0', 'c_benef': '',
                 'pis_cst': '01', 'p_pis': '2.0', 'cofins_cst': '01', 'p_cofins': '7.6'}
        assert tela_ncm._get_tax_key(item1) != tela_ncm._get_tax_key(item2)

    def test_same_icms_different_cofins_cst(self, tela_ncm):
        item1 = {'icms_cst': '00', 'p_icms': '12', 'p_red_bc': '0', 'c_benef': '',
                 'pis_cst': '01', 'p_pis': '1.65', 'cofins_cst': '01', 'p_cofins': '7.6'}
        item2 = {'icms_cst': '00', 'p_icms': '12', 'p_red_bc': '0', 'c_benef': '',
                 'pis_cst': '01', 'p_pis': '1.65', 'cofins_cst': '02', 'p_cofins': '7.6'}
        assert tela_ncm._get_tax_key(item1) != tela_ncm._get_tax_key(item2)

    def test_same_icms_different_cofins_alq(self, tela_ncm):
        item1 = {'icms_cst': '00', 'p_icms': '12', 'p_red_bc': '0', 'c_benef': '',
                 'pis_cst': '01', 'p_pis': '1.65', 'cofins_cst': '01', 'p_cofins': '7.6'}
        item2 = {'icms_cst': '00', 'p_icms': '12', 'p_red_bc': '0', 'c_benef': '',
                 'pis_cst': '01', 'p_pis': '1.65', 'cofins_cst': '01', 'p_cofins': '8.0'}
        assert tela_ncm._get_tax_key(item1) != tela_ncm._get_tax_key(item2)

    def test_same_all(self, tela_ncm):
        item1 = {'icms_cst': '00', 'p_icms': '12', 'p_red_bc': '0', 'c_benef': '',
                 'pis_cst': '08', 'p_pis': '0', 'cofins_cst': '08', 'p_cofins': '0'}
        item2 = {'icms_cst': '00', 'p_icms': '12', 'p_red_bc': '0', 'c_benef': '',
                 'pis_cst': '08', 'p_pis': '0', 'cofins_cst': '08', 'p_cofins': '0'}
        assert tela_ncm._get_tax_key(item1) == tela_ncm._get_tax_key(item2)

    def test_missing_values_defaults(self, tela_ncm):
        item = {}
        key = tela_ncm._get_tax_key(item)
        assert key == "00|0|0||00|0|00|0|0000"

    def test_with_cbenef(self, tela_ncm):
        item = {'icms_cst': '40', 'p_icms': '0', 'p_red_bc': '0', 'c_benef': '123456',
                'pis_cst': '08', 'p_pis': '0', 'cofins_cst': '08', 'p_cofins': '0'}
        key = tela_ncm._get_tax_key(item)
        assert "123456" in key

    def test_different_cfop_different_key(self, tela_ncm):
        item1 = {'icms_cst': '00', 'p_icms': '12', 'p_red_bc': '0', 'c_benef': '',
                 'pis_cst': '08', 'p_pis': '0', 'cofins_cst': '08', 'p_cofins': '0',
                 'cfop': '5101'}
        item2 = {'icms_cst': '00', 'p_icms': '12', 'p_red_bc': '0', 'c_benef': '',
                 'pis_cst': '08', 'p_pis': '0', 'cofins_cst': '08', 'p_cofins': '0',
                 'cfop': '5102'}
        assert tela_ncm._get_tax_key(item1) != tela_ncm._get_tax_key(item2)

    def test_same_cfop_same_key(self, tela_ncm):
        item1 = {'icms_cst': '00', 'p_icms': '12', 'p_red_bc': '0', 'c_benef': '',
                 'pis_cst': '08', 'p_pis': '0', 'cofins_cst': '08', 'p_cofins': '0',
                 'cfop': '5101'}
        item2 = {'icms_cst': '00', 'p_icms': '12', 'p_red_bc': '0', 'c_benef': '',
                 'pis_cst': '08', 'p_pis': '0', 'cofins_cst': '08', 'p_cofins': '0',
                 'cfop': '5101'}
        assert tela_ncm._get_tax_key(item1) == tela_ncm._get_tax_key(item2)


class TestAgruparNcm:
    def test_same_ncm_same_tax_key_single_group(self, tela_ncm):
        itens = [
            {'ncm': '22021000', 'x_prod': 'Refri A', 'uf_dest': 'MG', 'cfop': '5101',
             'tipo_cliente': 'CT', 'icms_cst': '00', 'p_icms': '12', 'p_red_bc': '0',
             'p_fcp': '0', 'p_icmsst': '0', 'p_mvast': '0', 'c_benef': '',
             'pis_cst': '08', 'p_pis': '0', 'cofins_cst': '08', 'p_cofins': '0',
             'cred_presumidos': [],
             'c_class_trib': '', 'ibscbs_cst': '', 'p_ibs_uf': '0', 'p_cbs': '0'},
            {'ncm': '22021000', 'x_prod': 'Refri B', 'uf_dest': 'MG', 'cfop': '5101',
             'tipo_cliente': 'CT', 'icms_cst': '00', 'p_icms': '12', 'p_red_bc': '0',
             'p_fcp': '0', 'p_icmsst': '0', 'p_mvast': '0', 'c_benef': '',
             'pis_cst': '08', 'p_pis': '0', 'cofins_cst': '08', 'p_cofins': '0',
             'cred_presumidos': [],
             'c_class_trib': '', 'ibscbs_cst': '', 'p_ibs_uf': '0', 'p_cbs': '0'},
        ]
        grupos = tela_ncm._agrupar_ncm(itens)
        assert len(grupos) == 1
        assert grupos[0]['ocorrencias'] == 2
        assert grupos[0]['ncm'] == '22021000'

    def test_same_ncm_different_pis_separate_groups(self, tela_ncm):
        itens = [
            {'ncm': '22021000', 'x_prod': 'Refri Normal', 'uf_dest': 'MG', 'cfop': '5101',
             'tipo_cliente': 'CT', 'icms_cst': '00', 'p_icms': '12', 'p_red_bc': '0',
             'p_fcp': '0', 'p_icmsst': '0', 'p_mvast': '0', 'c_benef': '',
             'pis_cst': '01', 'p_pis': '1.65', 'cofins_cst': '01', 'p_cofins': '7.6',
             'cred_presumidos': [],
             'c_class_trib': '', 'ibscbs_cst': '', 'p_ibs_uf': '0', 'p_cbs': '0'},
            {'ncm': '22021000', 'x_prod': 'Refri Diferente', 'uf_dest': 'MG', 'cfop': '5101',
             'tipo_cliente': 'CT', 'icms_cst': '00', 'p_icms': '12', 'p_red_bc': '0',
             'p_fcp': '0', 'p_icmsst': '0', 'p_mvast': '0', 'c_benef': '',
             'pis_cst': '08', 'p_pis': '0', 'cofins_cst': '08', 'p_cofins': '0',
             'cred_presumidos': [],
             'c_class_trib': '', 'ibscbs_cst': '', 'p_ibs_uf': '0', 'p_cbs': '0'},
        ]
        grupos = tela_ncm._agrupar_ncm(itens)
        assert len(grupos) == 2
        assert grupos[0]['ncm'] == '22021000'
        assert grupos[1]['ncm'] == '22021000'
        assert grupos[0]['ocorrencias'] == 1
        assert grupos[1]['ocorrencias'] == 1
        assert grupos[0]['pis_alq'] != grupos[1]['pis_alq']

    def test_same_ncm_different_cofins_separate_groups(self, tela_ncm):
        itens = [
            {'ncm': '22021000', 'x_prod': 'Prod A', 'uf_dest': 'MG', 'cfop': '5101',
             'tipo_cliente': 'CT', 'icms_cst': '00', 'p_icms': '12', 'p_red_bc': '0',
             'p_fcp': '0', 'p_icmsst': '0', 'p_mvast': '0', 'c_benef': '',
             'pis_cst': '01', 'p_pis': '1.65', 'cofins_cst': '01', 'p_cofins': '7.6',
             'cred_presumidos': [],
             'c_class_trib': '', 'ibscbs_cst': '', 'p_ibs_uf': '0', 'p_cbs': '0'},
            {'ncm': '22021000', 'x_prod': 'Prod B', 'uf_dest': 'MG', 'cfop': '5101',
             'tipo_cliente': 'CT', 'icms_cst': '00', 'p_icms': '12', 'p_red_bc': '0',
             'p_fcp': '0', 'p_icmsst': '0', 'p_mvast': '0', 'c_benef': '',
             'pis_cst': '01', 'p_pis': '1.65', 'cofins_cst': '01', 'p_cofins': '3.0',
             'cred_presumidos': [],
             'c_class_trib': '', 'ibscbs_cst': '', 'p_ibs_uf': '0', 'p_cbs': '0'},
        ]
        grupos = tela_ncm._agrupar_ncm(itens)
        assert len(grupos) == 2

    def test_same_ncm_different_cfop_separate_groups(self, tela_ncm):
        itens = [
            {'ncm': '22021000', 'x_prod': 'Venda', 'uf_dest': 'MG', 'cfop': '5101',
             'tipo_cliente': 'CT', 'icms_cst': '00', 'p_icms': '12', 'p_red_bc': '0',
             'p_fcp': '0', 'p_icmsst': '0', 'p_mvast': '0', 'c_benef': '',
             'pis_cst': '08', 'p_pis': '0', 'cofins_cst': '08', 'p_cofins': '0',
             'cred_presumidos': [],
             'c_class_trib': '', 'ibscbs_cst': '', 'p_ibs_uf': '0', 'p_cbs': '0'},
            {'ncm': '22021000', 'x_prod': 'Devolucao', 'uf_dest': 'MG', 'cfop': '5201',
             'tipo_cliente': 'CT', 'icms_cst': '00', 'p_icms': '12', 'p_red_bc': '0',
             'p_fcp': '0', 'p_icmsst': '0', 'p_mvast': '0', 'c_benef': '',
             'pis_cst': '08', 'p_pis': '0', 'cofins_cst': '08', 'p_cofins': '0',
             'cred_presumidos': [],
             'c_class_trib': '', 'ibscbs_cst': '', 'p_ibs_uf': '0', 'p_cbs': '0'},
        ]
        grupos = tela_ncm._agrupar_ncm(itens)
        assert len(grupos) == 2
        assert {g['cfop'] for g in grupos} == {'5101', '5201'}

    def test_different_ncms_separate_groups(self, tela_ncm):
        itens = [
            {'ncm': '22021000', 'x_prod': 'Refri', 'uf_dest': 'MG', 'cfop': '5101',
             'tipo_cliente': 'CT', 'icms_cst': '00', 'p_icms': '18', 'p_red_bc': '0',
             'p_fcp': '0', 'p_icmsst': '0', 'p_mvast': '0', 'c_benef': '',
             'pis_cst': '08', 'p_pis': '0', 'cofins_cst': '08', 'p_cofins': '0',
             'cred_presumidos': [],
             'c_class_trib': '', 'ibscbs_cst': '', 'p_ibs_uf': '0', 'p_cbs': '0'},
            {'ncm': '39241000', 'x_prod': 'Utensilio', 'uf_dest': 'MG', 'cfop': '5101',
             'tipo_cliente': 'CT', 'icms_cst': '00', 'p_icms': '12', 'p_red_bc': '0',
             'p_fcp': '0', 'p_icmsst': '0', 'p_mvast': '0', 'c_benef': '',
             'pis_cst': '08', 'p_pis': '0', 'cofins_cst': '08', 'p_cofins': '0',
             'cred_presumidos': [],
             'c_class_trib': '', 'ibscbs_cst': '', 'p_ibs_uf': '0', 'p_cbs': '0'},
        ]
        grupos = tela_ncm._agrupar_ncm(itens)
        assert len(grupos) == 2
        ncms = {g['ncm'] for g in grupos}
        assert ncms == {'22021000', '39241000'}

    def test_empty_input(self, tela_ncm):
        grupos = tela_ncm._agrupar_ncm([])
        assert grupos == []

    def test_skip_missing_ncm(self, tela_ncm):
        itens = [
            {'x_prod': 'Sem NCM', 'uf_dest': 'MG', 'cfop': '5101',
             'tipo_cliente': 'CT', 'icms_cst': '00', 'p_icms': '12', 'p_red_bc': '0',
             'p_fcp': '0', 'p_icmsst': '0', 'p_mvast': '0', 'c_benef': '',
             'pis_cst': '08', 'p_pis': '0', 'cofins_cst': '08', 'p_cofins': '0',
             'cred_presumidos': [],
             'c_class_trib': '', 'ibscbs_cst': '', 'p_ibs_uf': '0', 'p_cbs': '0'},
        ]
        grupos = tela_ncm._agrupar_ncm(itens)
        assert grupos == []

    def test_group_with_cred_presumidos(self, tela_ncm):
        itens = [
            {'ncm': '22021000', 'x_prod': 'Prod A', 'uf_dest': 'MG', 'cfop': '5101',
             'tipo_cliente': 'CT', 'icms_cst': '00', 'p_icms': '12', 'p_red_bc': '0',
             'p_fcp': '0', 'p_icmsst': '0', 'p_mvast': '0', 'c_benef': '',
             'pis_cst': '08', 'p_pis': '0', 'cofins_cst': '08', 'p_cofins': '0',
             'cred_presumidos': [{'c_cred': '123', 'p_cred': 5.0, 'v_cred': 10.0}],
             'c_class_trib': '', 'ibscbs_cst': '', 'p_ibs_uf': '0', 'p_cbs': '0'},
            {'ncm': '22021000', 'x_prod': 'Prod B', 'uf_dest': 'MG', 'cfop': '5101',
             'tipo_cliente': 'CT', 'icms_cst': '00', 'p_icms': '12', 'p_red_bc': '0',
             'p_fcp': '0', 'p_icmsst': '0', 'p_mvast': '0', 'c_benef': '',
             'pis_cst': '08', 'p_pis': '0', 'cofins_cst': '08', 'p_cofins': '0',
             'cred_presumidos': [{'c_cred': '123', 'p_cred': 5.0, 'v_cred': 10.0}],
             'c_class_trib': '', 'ibscbs_cst': '', 'p_ibs_uf': '0', 'p_cbs': '0'},
        ]
        grupos = tela_ncm._agrupar_ncm(itens)
        assert len(grupos) == 1
        assert grupos[0]['ocorrencias'] == 2

    def test_from_real_xml(self, tela_ncm):
        resultado = parse_nfe(CAMINHO_XML)
        itens = resultado['itens']
        assert len(itens) == 1
        grupos = tela_ncm._agrupar_ncm(itens)
        assert len(grupos) == 1
        grupo = grupos[0]
        assert grupo['ncm'] == '22021000'
        assert grupo['ocorrencias'] == 1
        assert grupo['cfop'] == '5101'
        assert grupo['uf_dest'] == 'MG'
        assert grupo['tipo_cliente'] == 'CT'
        assert grupo['pis_cst'] == '08'
        assert grupo['cofins_cst'] == '08'

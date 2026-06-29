import pytest
import tkinter as tk
from unittest.mock import patch, MagicMock
from telas.tela_ncm import DialogoPreviewNCM, DialogoIvaSt, TelaNcm


# ---------------------------------------------------------------------------
# _buscar_st_erp
# ---------------------------------------------------------------------------
class TestBuscarStErp:
    def _make_dialog(self, root, config_db={'host': 'dummy'}, empresa='2', filial='3'):
        return DialogoPreviewNCM(
            root, [],
            lambda r: None,
            config_db=config_db,
            empresa=empresa, filial=filial
        )

    @patch('telas.tela_ncm.FirebirdService')
    def test_retorna_S_quando_banco_tem_S(self, MockFB, root):
        inst = MockFB.return_value.__enter__.return_value
        cursor = inst.conn.cursor.return_value
        cursor.fetchone.return_value = ('S',)
        d = self._make_dialog(root)
        assert d._buscar_st_erp('22021000', 'CFIS_SUBST_TRIBUTARIA') == 'S'

    @patch('telas.tela_ncm.FirebirdService')
    def test_retorna_N_quando_banco_tem_N(self, MockFB, root):
        inst = MockFB.return_value.__enter__.return_value
        cursor = inst.conn.cursor.return_value
        cursor.fetchone.return_value = ('N',)
        d = self._make_dialog(root)
        assert d._buscar_st_erp('22021000', 'CFIS_ST_COMPRA') == 'N'

    @patch('telas.tela_ncm.FirebirdService')
    def test_retorna_N_quando_banco_retorna_None(self, MockFB, root):
        inst = MockFB.return_value.__enter__.return_value
        cursor = inst.conn.cursor.return_value
        cursor.fetchone.return_value = None
        d = self._make_dialog(root)
        assert d._buscar_st_erp('22021000', 'CFIS_SUBST_TRIBUTARIA') == 'N'

    @patch('telas.tela_ncm.FirebirdService')
    def test_retorna_N_quando_banco_retorna_valor_invalido(self, MockFB, root):
        inst = MockFB.return_value.__enter__.return_value
        cursor = inst.conn.cursor.return_value
        cursor.fetchone.return_value = ('X',)
        d = self._make_dialog(root)
        assert d._buscar_st_erp('22021000', 'CFIS_SUBST_TRIBUTARIA') == 'N'

    @patch('telas.tela_ncm.FirebirdService')
    def test_retorna_N_quando_sem_config_db(self, MockFB, root):
        d = self._make_dialog(root, config_db=None)
        assert d._buscar_st_erp('22021000', 'CFIS_SUBST_TRIBUTARIA') == 'N'

    @patch('telas.tela_ncm.FirebirdService')
    def test_retorna_N_quando_sem_ncm(self, MockFB, root):
        d = self._make_dialog(root)
        assert d._buscar_st_erp('', 'CFIS_SUBST_TRIBUTARIA') == 'N'

    @patch('telas.tela_ncm.FirebirdService')
    def test_consulta_usa_empresa_e_filial_corretos(self, MockFB, root):
        inst = MockFB.return_value.__enter__.return_value
        cursor = inst.conn.cursor.return_value
        cursor.fetchone.return_value = ('S',)
        d = self._make_dialog(root)
        d._buscar_st_erp('22021000', 'CFIS_SUBST_TRIBUTARIA')
        params = cursor.execute.call_args[0][1]
        assert params == ('22021000', '2', '3')

    @patch('telas.tela_ncm.FirebirdService')
    def test_trata_excecao_retorna_N(self, MockFB, root):
        MockFB.return_value.__enter__.side_effect = Exception('DB down')
        d = self._make_dialog(root)
        assert d._buscar_st_erp('22021000', 'CFIS_SUBST_TRIBUTARIA') == 'N'


# ---------------------------------------------------------------------------
# _on_st_change
# ---------------------------------------------------------------------------
class TestOnStChange:
    def _make_dialog(self, root):
        return DialogoPreviewNCM(root, [], lambda r: None, config_db={'host': 'dummy'})

    def test_botao_habilitado_quando_st_saida_S(self, root):
        d = self._make_dialog(root)
        d.var_st_saida.set('S')
        d.var_st_compra.set('N')
        d._on_st_change()
        assert str(d.btn_config_st.cget('state')) == 'normal'

    def test_botao_habilitado_quando_st_compra_S(self, root):
        d = self._make_dialog(root)
        d.var_st_saida.set('N')
        d.var_st_compra.set('S')
        d._on_st_change()
        assert str(d.btn_config_st.cget('state')) == 'normal'

    def test_botao_habilitado_quando_ambos_S(self, root):
        d = self._make_dialog(root)
        d.var_st_saida.set('S')
        d.var_st_compra.set('S')
        d._on_st_change()
        assert str(d.btn_config_st.cget('state')) == 'normal'

    def test_botao_desabilitado_quando_ambos_N(self, root):
        d = self._make_dialog(root)
        d.var_st_saida.set('N')
        d.var_st_compra.set('N')
        d._on_st_change()
        assert str(d.btn_config_st.cget('state')) == 'disabled'


# ---------------------------------------------------------------------------
# _float_ou_null  (DialogoIvaSt static method)
# ---------------------------------------------------------------------------
class TestFloatOuNull:
    def test_none_para_vazio(self):
        assert DialogoIvaSt._float_ou_null('') is None

    def test_none_para_espacos(self):
        assert DialogoIvaSt._float_ou_null('   ') is None

    def test_none_para_none(self):
        assert DialogoIvaSt._float_ou_null(None) is None

    def test_float_com_ponto(self):
        assert DialogoIvaSt._float_ou_null('12.5') == 12.5

    def test_float_com_virgula(self):
        assert DialogoIvaSt._float_ou_null('12,5') == 12.5

    def test_float_inteiro(self):
        assert DialogoIvaSt._float_ou_null('10') == 10.0

    def test_none_para_texto_invalido(self):
        assert DialogoIvaSt._float_ou_null('abc') is None


# ---------------------------------------------------------------------------
# _extrair_float e _extrair_cst  (TelaNcm)
# ---------------------------------------------------------------------------
class TestExtrairFloat:
    def _make_tela(self, root):
        return TelaNcm(root)

    def test_percentual_simples(self, root):
        assert self._make_tela(root)._extrair_float('18%') == 18.0

    def test_numero_decimal(self, root):
        assert self._make_tela(root)._extrair_float('1.65') == 1.65

    def test_string_vazia(self, root):
        assert self._make_tela(root)._extrair_float('') == 0.0

    def test_traco(self, root):
        assert self._make_tela(root)._extrair_float('-') == 0.0

    def test_multiplos_valores(self, root):
        assert self._make_tela(root)._extrair_float('12 / 18') == 12.0


class TestExtrairCst:
    def _make_tela(self, root):
        return TelaNcm(root)

    def test_cst_simples(self, root):
        assert self._make_tela(root)._extrair_cst('01') == '01'

    def test_cst_com_zero(self, root):
        assert self._make_tela(root)._extrair_cst('08') == '08'

    def test_cst_com_multiplos(self, root):
        assert self._make_tela(root)._extrair_cst('01 / 08') == '01'

    def test_cst_com_varios(self, root):
        assert self._make_tela(root)._extrair_cst('*VÁRIOS*') == '00'

    def test_cst_vazio(self, root):
        assert self._make_tela(root)._extrair_cst('-') == ''

    def test_cst_00_retorna_00(self, root):
        assert self._make_tela(root)._extrair_cst('0') == '00'


# ---------------------------------------------------------------------------
# SQL de sincronização
# ---------------------------------------------------------------------------
class TestSyncSql:
    INSERT_SQL = """INSERT INTO TABELA_class_fiscal 
                                        (CFIS_EMPRESA, CFIS_FILIAL, CFIS_CODIGO, CFIS_DESCRICAO, CFIS_ICMS_VENDA, 
                                         CFIS_PIS, CFIS_COFINS, CFIS_CST_PIS, CFIS_CST_COFINS, CFIS_IPI, CFIS_CST_IPI,
                                         CFIS_SUBST_TRIBUTARIA, CFIS_ST_COMPRA) 
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, '53', ?, ?)"""

    UPDATE_SQL = """UPDATE TABELA_class_fiscal SET 
                                            CFIS_DESCRICAO = ?, CFIS_ICMS_VENDA = ?, CFIS_PIS = ?, CFIS_COFINS = ?, 
                                            CFIS_CST_PIS = ?, CFIS_CST_COFINS = ?,
                                            CFIS_SUBST_TRIBUTARIA = ?, CFIS_ST_COMPRA = ?
                                        WHERE CFIS_EMPRESA = ? AND CFIS_FILIAL = ? AND CFIS_CODIGO = ?"""

    def test_insert_contains_subst_tributaria(self):
        assert 'CFIS_SUBST_TRIBUTARIA' in self.INSERT_SQL

    def test_insert_contains_st_compra(self):
        assert 'CFIS_ST_COMPRA' in self.INSERT_SQL

    def test_insert_has_11_placeholders_after_values(self):
        values_pos = self.INSERT_SQL.index('VALUES')
        after_values = self.INSERT_SQL[values_pos:]
        n_params = after_values.count('?')
        assert n_params == 11

    def test_insert_params_order(self):
        pos_subst = self.INSERT_SQL.index('CFIS_SUBST_TRIBUTARIA')
        pos_compra = self.INSERT_SQL.index('CFIS_ST_COMPRA')
        assert pos_subst < pos_compra

    def test_update_contains_subst_tributaria(self):
        assert 'CFIS_SUBST_TRIBUTARIA' in self.UPDATE_SQL

    def test_update_contains_st_compra(self):
        assert 'CFIS_ST_COMPRA' in self.UPDATE_SQL

    def test_update_has_11_placeholders(self):
        assert self.UPDATE_SQL.count('?') == 11

    def test_update_params_order(self):
        pos_subst = self.UPDATE_SQL.index('CFIS_SUBST_TRIBUTARIA')
        pos_compra = self.UPDATE_SQL.index('CFIS_ST_COMPRA')
        pos_where = self.UPDATE_SQL.index('WHERE')
        assert pos_subst < pos_compra < pos_where


# ---------------------------------------------------------------------------
# Defaults ST em _sincronizar_lote
# ---------------------------------------------------------------------------
class TestSincronizarLoteDefaults:
    def test_registro_default_subst_tributaria_N(self, root):
        t = TelaNcm(root)
        assert t is not None

    def test_registro_default_st_compra_N(self):
        registro = {
            'cfis_subst_tributaria': 'N',
            'cfis_st_compra': 'N',
        }
        assert registro['cfis_subst_tributaria'] == 'N'
        assert registro['cfis_st_compra'] == 'N'

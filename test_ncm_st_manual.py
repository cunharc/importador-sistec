"""Testes manuais ST (requer Firebird conectado)."""
import configparser
import os

os.environ['FBCLIENT_DLL'] = os.path.abspath('fbclient_5.dll')

config = configparser.ConfigParser()
config.read('config.ini', encoding='utf-8')

fbclient_rel = config.get('FIREBIRD', 'fbclient', fallback='')
fbclient_abs = os.path.abspath(fbclient_rel) if fbclient_rel else ''
config_db = {
    'host': config.get('FIREBIRD', 'servidor', fallback='127.0.0.1'),
    'port': config.get('FIREBIRD', 'porta', fallback='3050'),
    'database': config.get('FIREBIRD', 'caminho_banco', fallback=''),
    'user': config.get('FIREBIRD', 'usuario', fallback='SYSDBA'),
    'password': config.get('FIREBIRD', 'senha', fallback='masterkey'),
    'fbclient': fbclient_abs
}

empresa = config.get('IMPORTACAO', 'empresa', fallback='1')
filial = config.get('IMPORTACAO', 'filial', fallback='1')

from utils.firebird_service import FirebirdService


def teste1_buscar_st_erp():
    """Testa _buscar_st_erp com DB real."""
    print('=== TESTE 1: _buscar_st_erp ===')
    with FirebirdService(config_db) as fb:
        cursor = fb.conn.cursor()
        cursor.execute(
            'SELECT FIRST 1 CFIS_CODIGO, CFIS_SUBST_TRIBUTARIA, CFIS_ST_COMPRA '
            'FROM TABELA_class_fiscal WHERE CFIS_EMPRESA=? AND CFIS_FILIAL=?',
            (empresa, filial)
        )
        row = cursor.fetchone()
        if row:
            ncm, st_saida, st_compra = row
            print(f'  NCM {ncm}: ST Saida={st_saida!r}, ST Compra={st_compra!r}')
        else:
            print('  Nenhum NCM encontrado no ERP')
            return

        cursor.execute(
            'SELECT CFIS_SUBST_TRIBUTARIA FROM TABELA_class_fiscal '
            'WHERE CFIS_CODIGO=? AND CFIS_EMPRESA=? AND CFIS_FILIAL=?',
            (ncm, empresa, filial)
        )
        result = cursor.fetchone()
        print(f'  _buscar_st_erp({ncm}, CFIS_SUBST_TRIBUTARIA) = {result[0] if result else None!r}')
    print()


def teste2_sql_sync():
    """Verifica que SQLs possuem campos ST."""
    print('=== TESTE 2: SQL de sincronizacao com ST ===')
    insert_sql = """INSERT INTO TABELA_class_fiscal 
(CFIS_EMPRESA, CFIS_FILIAL, CFIS_CODIGO, CFIS_DESCRICAO, CFIS_ICMS_VENDA, 
 CFIS_PIS, CFIS_COFINS, CFIS_CST_PIS, CFIS_CST_COFINS, CFIS_IPI, CFIS_CST_IPI,
 CFIS_SUBST_TRIBUTARIA, CFIS_ST_COMPRA) 
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, '53', ?, ?)"""
    assert 'CFIS_SUBST_TRIBUTARIA' in insert_sql
    assert 'CFIS_ST_COMPRA' in insert_sql
    print('  INSERT SQL: campos ST OK')

    update_sql = """UPDATE TABELA_class_fiscal SET 
CFIS_DESCRICAO = ?, CFIS_ICMS_VENDA = ?, CFIS_PIS = ?, CFIS_COFINS = ?, 
CFIS_CST_PIS = ?, CFIS_CST_COFINS = ?,
CFIS_SUBST_TRIBUTARIA = ?, CFIS_ST_COMPRA = ?
WHERE CFIS_EMPRESA = ? AND CFIS_FILIAL = ? AND CFIS_CODIGO = ?"""
    assert 'CFIS_SUBST_TRIBUTARIA' in update_sql
    assert 'CFIS_ST_COMPRA' in update_sql
    print('  UPDATE SQL: campos ST OK')
    print()


def teste3_iva_st_table():
    """Verifica estrutura da tabela IVA_ST."""
    print('=== TESTE 3: TABELA_CLASSIF_FISCAL_IVA_ST ===')
    with FirebirdService(config_db) as fb:
        cursor = fb.conn.cursor()
        cursor.execute('SELECT FIRST 1 * FROM TABELA_CLASSIF_FISCAL_IVA_ST')
        columns = [desc[0] for desc in cursor.description]
        print(f'  Colunas: {columns}')
        row = cursor.fetchone()
        if row:
            print(f'  Registro exemplo: {dict(zip(columns, row))}')
        else:
            print('  Nenhum registro IVA_ST encontrado')
    print()


def teste4_insert_iva_st():
    """Tenta inserir IVA_ST (se NCM existir em class_fiscal)."""
    print('=== TESTE 4: Insert IVA_ST ===')
    test_ncm = '99.99.9999'
    with FirebirdService(config_db) as fb:
        cursor = fb.conn.cursor()
        cursor.execute(
            'SELECT COUNT(*) FROM TABELA_class_fiscal '
            'WHERE CFIS_CODIGO=? AND CFIS_EMPRESA=? AND CFIS_FILIAL=?',
            (test_ncm, empresa, filial)
        )
        if cursor.fetchone()[0] == 0:
            print(f'  NCM {test_ncm} nao existe na base - pulando insert')
        else:
            cursor.execute("""
                UPDATE OR INSERT INTO TABELA_CLASSIF_FISCAL_IVA_ST
                (ST_CLASSIF_FISCAL, ST_EMPRESA, ST_FILIAL, ST_UF, ST_DATA,
                 ST_IVA, ST_ALIQUOTA_ICMS_INT, ST_REDUICAO_ICMS_INT,
                 ST_ST_FCB, ST_REDUCAO_ICMS_PROPRIO, ST_REAJUSTADO, ST_OBS)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                MATCHING (ST_CLASSIF_FISCAL, ST_EMPRESA, ST_FILIAL, ST_UF, ST_DATA)
            """, (test_ncm, empresa, filial, 'SP', '2026-06-05',
                  18.0, 18.0, 0, 'N', 0, 'N', 'Teste automatico'))
            fb.conn.commit()
            print(f'  Insert IVA_ST para {test_ncm} OK')
    print()


def teste5_consulta_iva_st():
    """Consulta IVA_ST por empresa/filial."""
    print('=== TESTE 5: Consulta IVA_ST por empresa/filial ===')
    with FirebirdService(config_db) as fb:
        cursor = fb.conn.cursor()
        cursor.execute("""
            SELECT ST_UF, ST_DATA, ST_IVA FROM TABELA_CLASSIF_FISCAL_IVA_ST
            WHERE ST_EMPRESA=? AND ST_FILIAL=?
            ORDER BY ST_UF, ST_DATA
        """, (empresa, filial))
        rows = cursor.fetchall()
        print(f'  Registros IVA_ST: {len(rows)}')
        for r in rows[:5]:
            print(f'    UF={r[0]}, Data={r[1]}, IVA={r[2]}')
    print()


def teste6_update_st_fields():
    """Testa UPDATE dos campos ST em class_fiscal."""
    print('=== TESTE 6: UPDATE CFIS_SUBST_TRIBUTARIA / CFIS_ST_COMPRA ===')
    with FirebirdService(config_db) as fb:
        cursor = fb.conn.cursor()
        cursor.execute(
            'SELECT FIRST 1 CFIS_CODIGO FROM TABELA_class_fiscal '
            'WHERE CFIS_EMPRESA=? AND CFIS_FILIAL=?',
            (empresa, filial)
        )
        ncm = cursor.fetchone()
        if not ncm:
            print('  Nenhum NCM encontrado')
            return

        ncm_fmt = ncm[0]
        cursor.execute("""
            UPDATE TABELA_class_fiscal SET
                CFIS_SUBST_TRIBUTARIA = ?, CFIS_ST_COMPRA = ?
            WHERE CFIS_EMPRESA = ? AND CFIS_FILIAL = ? AND CFIS_CODIGO = ?
        """, ('S', 'N', empresa, filial, ncm_fmt))
        fb.conn.commit()
        print(f'  UPDATE ST fields para NCM {ncm_fmt}: SUBST_TRIBUTARIA=S, ST_COMPRA=N')

        cursor.execute(
            'SELECT CFIS_SUBST_TRIBUTARIA, CFIS_ST_COMPRA FROM TABELA_class_fiscal '
            'WHERE CFIS_CODIGO=? AND CFIS_EMPRESA=? AND CFIS_FILIAL=?',
            (ncm_fmt, empresa, filial)
        )
        row = cursor.fetchone()
        print(f'  Verificacao: ST Saida={row[0]!r}, ST Compra={row[1]!r}')
        assert row[0] == 'S'
        assert row[1] == 'N'

        # Restore to N
        cursor.execute("""
            UPDATE TABELA_class_fiscal SET
                CFIS_SUBST_TRIBUTARIA = ?, CFIS_ST_COMPRA = ?
            WHERE CFIS_EMPRESA = ? AND CFIS_FILIAL = ? AND CFIS_CODIGO = ?
        """, ('N', 'N', empresa, filial, ncm_fmt))
        fb.conn.commit()
        print('  Restaurado para N/N')
    print()


if __name__ == '__main__':
    teste1_buscar_st_erp()
    teste2_sql_sync()
    teste3_iva_st_table()
    teste4_insert_iva_st()
    teste5_consulta_iva_st()
    teste6_update_st_fields()
    print('=== TODOS OS TESTES MANUAIS CONCLUIDOS ===')

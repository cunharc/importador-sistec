# -*- coding: utf-8 -*-
"""Centro de custo e conta contábil dos títulos, num só lugar.

Três telas gravam título (notas por XML, Contas a Receber por planilha e Contas a
Pagar por planilha) e as três precisam do mesmo rateio. O SQL vive aqui para não
existirem três versões que divergem na primeira correção.

Convenções do ERP levantadas no banco:
  - centro de custo é `TABELA_CC`, e só os de `CC_MOVIMENTO='S'` aceitam lançamento
  - conta contábil é `TABELA_PLANO` por exercício; `PLANO_REDUZIDO` alimenta
    `TCONT_CONTABIL_REDUZIDO`. Não confundir com `TABELA_CONTA`, que é a conta de
    *classificação* apontada por `CC_CONTA`
  - o rateio é sempre de 100% no valor do título
"""
from utils.firebird_service import FirebirdService

ROTULO_SEM_CC = "(nenhum)"
ROTULO_SEM_CONTA = "(nenhuma)"


def carregar_opcoes(config_db, emp, fil, ao_falhar=None):
    """Lê centros de custo e contas contábeis do ERP.

    Devolve (rotulos_cc, rotulos_conta, exercicio, reduzidos), onde os rótulos já
    vêm com o placeholder de "nenhum" na primeira posição e `reduzidos` mapeia
    PLANO_CODIGO -> PLANO_REDUZIDO.

    `ao_falhar(mensagem)` é chamado quando a leitura falha. Sem ele, uma falha de
    conexão devolvia listas vazias e a tela mostrava só "(nenhum)" — indistinguível
    de um ERP sem centro de custo cadastrado. Quem chama tem de poder avisar.
    """
    ccs = contas = []
    exercicio = None
    try:
        with FirebirdService(config_db) as fb:
            ccs = fb.query(
                "SELECT CC_CODIGO C, CC_DESCRICAO D FROM TABELA_CC "
                "WHERE CC_EMPRESA = ? AND CC_FILIAL = ? AND CC_MOVIMENTO = 'S' "
                "  AND COALESCE(CC_DESATIVADO, 'N') = 'N' ORDER BY CC_DESCRICAO",
                [emp, fil])
            ex = fb.query("SELECT MAX(PLANO_EXERCICIO) E FROM TABELA_PLANO "
                          "WHERE PLANO_EMPRESA = ? AND PLANO_FILIAL = ?", [emp, fil])
            exercicio = ex[0]['e'] if ex and ex[0]['e'] else None
            if exercicio:
                contas = fb.query(
                    "SELECT DISTINCT PLANO_CODIGO C, PLANO_CONTA CT, PLANO_REDUZIDO R, "
                    "       PLANO_DESCRICAO D FROM TABELA_PLANO "
                    "WHERE PLANO_EMPRESA = ? AND PLANO_FILIAL = ? AND PLANO_EXERCICIO = ? "
                    "  AND PLANO_REDUZIDO IS NOT NULL ORDER BY PLANO_CONTA",
                    [emp, fil, exercicio])
    except Exception as e:
        if ao_falhar:
            ao_falhar(str(e))
    rot_cc = [ROTULO_SEM_CC] + [f"{r['c']} - {r['d']}" for r in ccs]
    rot_ct = [ROTULO_SEM_CONTA] + [f"{r['c']} - {r['ct']} {r['d']}" for r in contas]
    reduzidos = {int(r['c']): r['r'] for r in contas}
    return rot_cc, rot_ct, exercicio, reduzidos


def codigo_do_rotulo(texto):
    """Código numérico de um rótulo '12 - DESCRIÇÃO'; None para vazio/placeholder."""
    txt = (texto or '').strip()
    if not txt or txt.startswith('('):
        return None
    try:
        return int(txt.split('-')[0].strip())
    except (ValueError, IndexError):
        return None


def rateio_receber(cur, emp, fil, cod, serie, cliente, emissao, valor,
                   cc=None, conta=None, exercicio=None, reduzidos=None):
    """Rateio do título no Contas a Receber. No-op quando cc e conta são None."""
    if cc:
        cur.execute("""
            INSERT INTO TABELA_TITULO_CC_REC (
                TCC_EMPRESA, TCC_FILIAL, TCC_CODIGO, TCC_SERIE, TCC_LANCAMENTO,
                TCC_CLIENTE_EMPRESA, TCC_CLIENTE_FILIAL, TCC_CLIENTE,
                TCC_CC_EMPRESA, TCC_CC_FILIAL, TCC_CC,
                TCC_PORCENTAGEM, TCC_VALOR
            ) VALUES (?,?,?,?,1, ?,?,?, ?,?,?, 100, ?)
        """, [emp, fil, cod, serie, emp, fil, cliente, emp, fil, cc,
              float(valor or 0.0)])
    if conta and exercicio:
        cur.execute("""
            INSERT INTO TABELA_TITULO_CONTABIL_REC (
                TCONT_EMPRESA, TCONT_FILIAL, TCONT_CODIGO, TCONT_SERIE, TCONT_LANCAMENTO,
                TCONT_CLIENTE_EMPRESA, TCONT_CLIENTE_FILIAL, TCONT_CLIENTE,
                TCONT_CONTABIL_EMPRESA, TCONT_CONTABIL_FILIAL, TCONT_CONTABIL_EXERCICIO,
                TCONT_CONTABIL, TCONT_CONTABIL_REDUZIDO,
                TCONT_VALOR, TCONT_PORCENTAGEM,
                TCONT_HISTORICO_EMPRESA, TCONT_HISTORICO_FILIAL, TCONT_EMISSAO
            ) VALUES (?,?,?,?,1, ?,?,?, ?,?,?, ?,?, ?,100, ?,?,?)
        """, [emp, fil, cod, serie, emp, fil, cliente,
              emp, fil, exercicio, conta, (reduzidos or {}).get(conta),
              float(valor or 0.0), emp, fil, emissao])


def rateio_pagar(cur, emp, fil, cod, serie, fornecedor, emissao, valor,
                 cc=None, conta=None, exercicio=None, reduzidos=None):
    """Rateio do título no Contas a Pagar. No-op quando cc e conta são None."""
    if cc:
        cur.execute("""
            INSERT INTO TABELA_TITULO_CC (
                TCC_EMPRESA, TCC_FILIAL, TCC_TITULO,
                TCC_FORNECEDOR_EMPRESA, TCC_FORNECEDOR_FILIAL, TCC_FORNECEDOR,
                TCC_CC_EMPRESA, TCC_CC_FILIAL, TCC_CC,
                TCC_LANCAMENTO, TCC_SERIE, TCC_EMISSAO,
                TCC_PORCENTAGEM, TCC_VALOR
            ) VALUES (?,?,?, ?,?,?, ?,?,?, 1,?,?, 100, ?)
        """, [emp, fil, cod, emp, fil, fornecedor, emp, fil, cc,
              serie, emissao, float(valor or 0.0)])
    if conta and exercicio:
        cur.execute("""
            INSERT INTO TABELA_TITULO_CONTABIL (
                TCONT_EMPRESA, TCONT_FILIAL, TCONT_TITULO, TCONT_SERIE, TCONT_LANCAMENTO,
                TCONT_FORNECEDOR_EMPRESA, TCONT_FORNECEDOR_FILIAL, TCONT_FORNECEDOR,
                TCONT_CONTABIL_EMPRESA, TCONT_CONTABIL_FILIAL, TCONT_CONTABIL_EXERCICIO,
                TCONT_CONTABIL, TCONT_CONTABIL_REDUZIDO, TCONT_EMISSAO,
                TCONT_PORCENTAGEM, TCONT_VALOR,
                TCONT_HISTORICO_EMPRESA, TCONT_HISTORICO_FILIAL
            ) VALUES (?,?,?,?,1, ?,?,?, ?,?,?, ?,?,?, 100,?, ?,?)
        """, [emp, fil, cod, serie, emp, fil, fornecedor,
              emp, fil, exercicio, conta, (reduzidos or {}).get(conta),
              emissao, float(valor or 0.0), emp, fil])

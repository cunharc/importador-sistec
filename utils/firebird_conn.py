import locale
if not hasattr(locale, 'resetlocale'):
    locale.resetlocale = lambda: locale.setlocale(locale.LC_ALL, "")

import fdb
import configparser
import os
import re
import sys

def carregar_config():
    config = configparser.ConfigParser()
    if os.path.exists('config.ini'):
        config.read('config.ini', encoding='utf-8')
    return config

def resource_path(relative_path):
    """Garante que a DLL seja encontrada ao rodar via .exe (PyInstaller)"""
    if not relative_path or os.path.isabs(relative_path):
        return relative_path
        
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
        
    caminho_completo = os.path.join(base_path, relative_path)
    if os.path.exists(caminho_completo):
        return caminho_completo
    return relative_path

def conectar():
    config = carregar_config()
    servidor = config.get('FIREBIRD', 'servidor', fallback='localhost')
    porta = config.get('FIREBIRD', 'porta', fallback='3050')
    caminho_banco = config.get('FIREBIRD', 'caminho_banco', fallback='')
    usuario = config.get('FIREBIRD', 'usuario', fallback='SYSDBA')
    senha = config.get('FIREBIRD', 'senha', fallback='masterkey')
    fbclient = config.get('FIREBIRD', 'fbclient', fallback='')
    
    dsn = caminho_banco
    if servidor:
        if porta:
            dsn = f"{servidor}/{porta}:{caminho_banco}"
        else:
            dsn = f"{servidor}:{caminho_banco}"

    kwargs = {
        'dsn': dsn,
        'user': usuario,
        'password': senha,
        'charset': 'WIN1252'
    }
    if fbclient:
        kwargs['fb_library_name'] = resource_path(fbclient)
    
    return fdb.connect(**kwargs)

def testar_conexao_simples():
    """Retorna True se conectar com sucesso, False caso contrário."""
    try:
        conn = conectar()
        conn.close()
        return True
    except Exception:
        return False

def buscar_contas_existentes(conn, empresa, filial, exercicio):
    """Busca todas as contas já cadastradas para validar duplicatas de forma otimizada."""
    cur = conn.cursor()
    cur.execute(
        "SELECT PLANO_CONTA FROM TABELA_PLANO "
        "WHERE PLANO_EMPRESA = ? AND PLANO_FILIAL = ? AND PLANO_EXERCICIO = ?",
        (empresa, filial, exercicio)
    )
    return set(row[0].strip() for row in cur.fetchall() if row[0])

def buscar_proximo_codigo(conn, empresa, filial, exercicio):
    cur = conn.cursor()
    cur.execute(
        "SELECT COALESCE(MAX(PLANO_CODIGO), 0) FROM TABELA_PLANO "
        "WHERE PLANO_EMPRESA = ? AND PLANO_FILIAL = ? AND PLANO_EXERCICIO = ?",
        (empresa, filial, exercicio)
    )
    resultado = cur.fetchone()
    return (resultado[0] or 0) + 1

def limpar_tabela(conn, empresa, filial, exercicio):
    """Remove todos os registros para a empresa, filial e exercício especificados."""
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM TABELA_PLANO WHERE PLANO_EMPRESA = ? AND PLANO_FILIAL = ? AND PLANO_EXERCICIO = ?",
        (empresa, filial, exercicio)
    )

def inserir_registros(conn, registros: list, callback_progresso=None, checar_cancelamento=None):
    """
    Insere os registros no banco.
    Retorna (sucesso_bool, qtd_inserida, erros)
    """
    cur = conn.cursor()
    sql = """
        INSERT INTO TABELA_PLANO (
            PLANO_EMPRESA, PLANO_FILIAL, PLANO_EXERCICIO, PLANO_CODIGO,
            PLANO_CONTA, PLANO_REDUZIDO, PLANO_INDICE, PLANO_NIVEL,
            PLANO_DESCRICAO, PLANO_SALDOANTERIOR, PLANO_DEBITO,
            PLANO_CREDITO, PLANO_SALDOATUAL, PLANO_MES_INI,
            PLANO_ATIVO, PLANO_COD_NATUREZA, PLANO_COD_EXTERNO,
            PLANO_CONTA_EXERCICIO_ANT, PLANO_CONTA_IMPORT
        ) VALUES (
            ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, 0, 0,
            0, 0, 1,
            'S', ?, ?,
            ?, ?
        )
    """
    total = len(registros)
    inseridos = 0
    erros = 0
    
    try:
        for i, reg in enumerate(registros):
            if checar_cancelamento and checar_cancelamento():
                conn.rollback()
                return False, inseridos, erros
            
            if reg.get('STATUS') == 'OK':
                try:
                    cur.execute(sql, (
                        reg['PLANO_EMPRESA'], reg['PLANO_FILIAL'], reg['PLANO_EXERCICIO'],
                        reg['PLANO_CODIGO'], reg['PLANO_CONTA'], reg['PLANO_REDUZIDO'],
                        reg['PLANO_INDICE'], reg['PLANO_NIVEL'], reg['PLANO_DESCRICAO'],
                        reg['PLANO_COD_NATUREZA'], reg['PLANO_COD_EXTERNO'],
                        reg['PLANO_CONTA_EXERCICIO_ANT'], reg['PLANO_CONTA_IMPORT']
                    ))
                    inseridos += 1
                except Exception as e:
                    erros += 1
                    print(f"Erro ao inserir conta {reg['PLANO_CONTA']}: {e}")
                    
            if callback_progresso:
                callback_progresso(i + 1, total)
                
        conn.commit()
        return True, inseridos, erros
    except Exception as e:
        conn.rollback()
        raise e


# =============================================================================
# FUNÇÕES DO MÓDULO NF-E (CLIENTES E FORNECEDORES)
# =============================================================================

def buscar_cidade_ibge(conn, codigo_ibge, empresa, filial, nome_cidade='', cep='', uf=''):
    """Busca o código da cidade. Se não encontrar, auto-cadastra na TABELA_CIDADE."""
    if not codigo_ibge:
        return None
    cur = conn.cursor()
    
    # 1. Tenta buscar na TABELA_CIDADES_IBGE pelo CIDADE_CODIGO
    try:
        cur.execute(
            "SELECT CIDADE_CODIGO FROM TABELA_CIDADES_IBGE "
            "WHERE CIDIBGE_CODIGO = ?",
            (codigo_ibge,)
        )
        row = cur.fetchone()
        if row: return row[0]
    except Exception:
        pass
        
    # 2. Tenta buscar na TABELA_CIDADES_IBGE pelo CIDIBGE_CIDADE
    try:
        cur.execute(
            "SELECT CIDIBGE_CIDADE FROM TABELA_CIDADES_IBGE "
            "WHERE CIDIBGE_CODIGO = ?",
            (codigo_ibge,)
        )
        row = cur.fetchone()
        if row: return row[0]
    except Exception:
        pass

    # 3. Busca na TABELA_CIDADE (Novo schema informado)
    try:
        cur.execute(
            "SELECT CID_CODIGO FROM TABELA_CIDADE "
            "WHERE CID_CODIGO_IBGE = ? AND CID_EMPRESA = ? AND CID_FILIAL = ?",
            (codigo_ibge, empresa, filial)
        )
        row = cur.fetchone()
        if row: return row[0]
    except Exception:
        pass
        
    # 4. Tenta buscar pelo próprio código na TABELA_CIDADE
    try:
        cur.execute(
            "SELECT CID_CODIGO FROM TABELA_CIDADE "
            "WHERE CID_CODIGO = ? AND CID_EMPRESA = ? AND CID_FILIAL = ?",
            (codigo_ibge, empresa, filial)
        )
        row = cur.fetchone()
        if row: return row[0]
    except Exception:
        pass

    # 5. Fallback para a TABELA_CIDADES (Schema antigo)
    try:
        cur.execute(
            "SELECT CIDADE_CODIGO FROM TABELA_CIDADES "
            "WHERE CIDADE_IBGE = ? AND CIDADE_EMPRESA = ? AND CIDADE_FILIAL = ?",
            (codigo_ibge, empresa, filial)
        )
        row = cur.fetchone()
        if row: return row[0]
    except Exception:
        pass

    # --- 6. SE NÃO ACHOU EM LUGAR NENHUM -> CADASTRA A NOVA CIDADE ---
    try:
        sql_insert = """
            INSERT INTO TABELA_CIDADE (
                CID_EMPRESA, CID_FILIAL, CID_CODIGO, CID_DESCRICAO, 
                CID_CEP, CID_UF, CID_VENDEDOR_EMPRESA, CID_VENDEDOR_FILIAL, 
                CID_CODIGO_IBGE, CID_PAIS, CID_TABELA_ISS_EMP, CID_TABELA_ISS_FIL, 
                CIDADE_LISTA_PRECO_EMP, CIDADE_LISTA_PRECO_FIL
            ) VALUES (
                ?, ?, ?, ?, 
                ?, ?, ?, ?, 
                ?, 1058, ?, ?, 
                ?, ?
            )
        """
        descricao = nome_cidade[:60].upper() if nome_cidade else f"IBGE {codigo_ibge}"
        cur.execute(sql_insert, (
            empresa, filial, codigo_ibge, descricao,
            cep, uf, empresa, filial,
            codigo_ibge, empresa, filial,
            empresa, filial
        ))
        conn.commit() # Salva a cidade imediatamente no banco
        return codigo_ibge
    except Exception as e:
        print(f"Erro ao auto-cadastrar a cidade {codigo_ibge}: {e}")
        conn.rollback()
        return None

def buscar_clientes_existentes(conn, empresa, filial):
    """Retorna um dict mapeando todos os CPF/CNPJ (apenas números) já cadastrados para o seu respectivo CF_CODIGO."""
    cur = conn.cursor()
    cur.execute(
        "SELECT CF_CPF_CGC, CF_CODIGO FROM TABELA_CLI_FOR WHERE CF_EMPRESA = ? AND CF_FILIAL = ?",
        (empresa, filial)
    )
    # Retorna um dicionário {cnpj_apenas_numeros: cf_codigo}
    return {re.sub(r'\D', '', str(row[0])): row[1] for row in cur.fetchall() if row[0]}

def buscar_proximo_codigo_cli_for(conn, empresa, filial):
    """Gera o próximo CF_CODIGO sequencial."""
    cur = conn.cursor()
    cur.execute(
        "SELECT COALESCE(MAX(CF_CODIGO), 0) + 1 FROM TABELA_CLI_FOR "
        "WHERE CF_EMPRESA = ? AND CF_FILIAL = ?",
        (empresa, filial)
    )
    return cur.fetchone()[0]

def buscar_ou_criar_condicao_pgto(conn, duplicatas, tipo_pagamento=None):
    """
    Busca cond. pagto pelo descritivo exato. Se não existir, cria nova com parcelas.
    
    Regras:
    - Se duplicatas vazias ou só dia 0: A VISTA
    - Se duplicatas com dias únicos: "DIA1/DIA2/DIA3 DIAS"
    - Se duplicatas com dias repetidos: agrupa por dia e soma percentuais
    """
    if not duplicatas:
        return None
    
    dias_unicos = sorted(set(d['dias'] for d in duplicatas))
    
    if len(dias_unicos) == 1 and dias_unicos[0] == 0:
        descricao = "A VISTA"
    else:
        assinatura_dias = "/".join(str(d) for d in dias_unicos)
        descricao = f"{assinatura_dias} DIAS"

    cur = conn.cursor()
    try:
        cur.execute("SELECT CONDPGTO_CODIGO FROM TABELA_CONDICAOPGTO WHERE TRIM(UPPER(CONDPDTO_DESCRICAO)) = ?", (descricao.upper(),))
        row = cur.fetchone()
        if row:
            return row[0]
        
        # Se não encontrou e não há dados para criar, retorna nulo
        if not duplicatas:
            return None

        cur.execute("SELECT COALESCE(MAX(CONDPGTO_CODIGO), 0) + 1 FROM TABELA_CONDICAOPGTO")
        novo_codigo = cur.fetchone()[0]
        
        cur.execute(
            "INSERT INTO TABELA_CONDICAOPGTO (CONDPGTO_CODIGO, CONDPDTO_DESCRICAO, CONDPGTO_CONDICAO) VALUES (?, ?, ?)",
            (novo_codigo, descricao, 'DDL')
        )
        
        # Agrupa parcelas por dia para lidar com casos como "30/30/30"
        parcelas_por_dia = {}
        total_percentual = 0
        for dup in duplicatas:
            dia = dup['dias']
            pct = dup.get('percentual', 0)
            if dia in parcelas_por_dia:
                parcelas_por_dia[dia] += pct
            else:
                parcelas_por_dia[dia] = pct
            total_percentual += pct

        # Se os percentuais não somarem ~100, recalcula de forma igualitária
        recalcular = abs(total_percentual - 100) > 1
        
        dias_unicos = sorted(parcelas_por_dia.keys())
        num_parcelas = len(dias_unicos)

        for i, dia in enumerate(dias_unicos):
            percentual_final = (100.0 / num_parcelas) if recalcular else parcelas_por_dia[dia]
            cur.execute(
                "INSERT INTO TABELA_CONDPGTO_PARCELAS (CONDPARC_CODIGO, CONDPARC_PARCELA, CONDPARC_PERCENTUAL, CONDPARC_DIAS) VALUES (?, ?, ?, ?)",
                (novo_codigo, i + 1, round(percentual_final, 2), dia)
            )
        
        conn.commit()
        return novo_codigo
    except Exception as e:
        conn.rollback()
        raise Exception(f"Erro no BD ao criar condição: {e}")
        
def listar_condicoes_pagamento(conn):
    """Lista todas as condições de pagamento cadastradas."""
    cur = conn.cursor()
    try:
        cur.execute("SELECT CONDPGTO_CODIGO, CONDPDTO_DESCRICAO FROM TABELA_CONDICAOPGTO ORDER BY CONDPDTO_DESCRICAO")
        # .strip() para remover espaços em branco que possam existir no banco
        return [(row[0], row[1].strip()) for row in cur.fetchall()]
    except Exception:
        return []

def inserir_clientes_nfe(conn, registros, empresa, filial, callback_progresso=None, checar_cancelamento=None):
    """Insere os clientes/fornecedores no banco aplicando todas as regras."""
    cur = conn.cursor()
    
    sql = """
        INSERT INTO TABELA_CLI_FOR (
            CF_EMPRESA, CF_FILIAL, CF_CODIGO, CF_DATA, CF_DATA_ALT,
            CF_CPF_CGC, CF_RAZAO, CF_FANTASIA,
            CF_ATIVO, CF_TIPO_INSCR, CF_CLIENTE, CF_FORNECEDOR,
            CF_RG_IE, CF_ICMS, CF_ATIVIDADE,
                CF_ENDERECO, CF_NRO_END, CF_BAIRRO, CF_CIDADE, CF_CEP,
                CF_ENDERECO2, CF_NRO_END2, CF_BAIRRO2, CF_CIDADE2, CF_CEP2,
                CF_ENDERECO3, CF_BAIRRO3, CF_CIDADE3, CF_CEP3,
                CF_ENDERECO4, CF_BAIRRO4, CF_CIDADE4, CF_CEP4,
            CF_CIDADE_EMPRESA, CF_CIDADE_FILIAL,
            CF_REPRESENTANTE_EMP, CF_REPRESENTANTE_FILIAL,
            CF_FONE1, CF_FONE2, CF_FAX,
            CF_EMAIL,
            CF_EMAIL_NFE, CF_COND_PGTO_VENDA, CF_COND_PGTO_COMPRA,
            CF_COD_ANTIGO
        ) VALUES (
            ?, ?, ?, CURRENT_DATE, CURRENT_DATE,
            ?, ?, ?,
            'S', ?, ?, ?,
            ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
            ?, ?,
            ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?,
            ?
        )
    """
    
    total = len(registros)
    inseridos = 0
    erros = 0
    
    try:
        for i, reg in enumerate(registros):
            if checar_cancelamento and checar_cancelamento():
                conn.rollback()
                return False, inseridos, erros
            
            end = reg.get('endereco', '')
            nro = reg.get('nro_end', '')
            bairro = reg.get('bairro', '')
            cid = reg.get('cidade_ibge', '')
            cep = reg.get('cep', '')
            
            cgc_unformatted = ''.join(filter(str.isdigit, reg.get('documento', '') or ''))
            cgc = reg.get('documento_formatado') or reg.get('documento', '')
            
            razao = str(reg.get('razao', ''))[:60]
            fantasia = str(reg.get('fantasia', ''))[:60]
            
            tipo_inscr = 1 if len(cgc_unformatted) == 11 else 2
            
            cliente = 'S' if reg.get('tipo', '') == 'Cliente' else 'N'
            fornecedor = 'S' if reg.get('tipo', '') == 'Fornecedor' else 'N'
            
            ie_bruta = str(reg.get('ie', '')).strip().upper()
            if not ie_bruta or ie_bruta == 'ISENTO':
                rg_ie = 'ISENTO'
                cf_icms = 2
            else:
                rg_ie = ie_bruta[:20]
                cf_icms = 1
                
            cf_atividade = 1
            
            fone1 = str(reg.get('fone1', ''))[:15]
            fone2 = str(reg.get('fone2', ''))[:15]
            fax = str(reg.get('fax', ''))[:15]
            email = str(reg.get('email', ''))[:60]
            cod_antigo = reg.get('cf_cod_antigo')

            # Usa a condicao de pagamento já processada pela tela, ou busca/cria se não processada
            if 'cond_pagto_id' in reg:
                cond_pgto = reg['cond_pagto_id']
            else:
                cond_pgto = buscar_ou_criar_condicao_pgto(conn, reg.get('condicao_pagamento', []), reg.get('condicao_pagamento_desc'))
            
            # Gera o próximo ID do cliente
            cf_codigo = buscar_proximo_codigo_cli_for(conn, empresa, filial)
            
            valores = (
                empresa, filial, cf_codigo,
                cgc, razao, fantasia,
                tipo_inscr, cliente, fornecedor,
                rg_ie, cf_icms, cf_atividade,
                end, nro, bairro, cid, cep,
                end, nro, bairro, cid, cep,
                end, bairro, cid, cep,
                end, bairro, cid, cep,
                empresa, filial,
                empresa, filial,
                fone1, fone2, fax,
                email, 'S',
                cond_pgto, cond_pgto,
                cod_antigo
            )
            
            try:
                cur.execute(sql, valores)
                inseridos += 1
                reg['_status_importacao'] = 'OK'
            except Exception as e:
                erros += 1
                print(f"Erro ao inserir cliente/fornecedor {razao}: {str(e)}")
                reg['_status_importacao'] = 'ERRO'
                reg['_erro_importacao'] = str(e)
                
            if callback_progresso:
                callback_progresso(i + 1, total)
                
        conn.commit()
        return True, inseridos, erros
    except Exception as e:
        conn.rollback()
        raise e
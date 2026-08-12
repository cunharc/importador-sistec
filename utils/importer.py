import locale
if not hasattr(locale, 'resetlocale'):
    locale.resetlocale = lambda: locale.setlocale(locale.LC_ALL, "")

from typing import List, Dict, Any
import fdb
from utils.firebird_service import FirebirdService
from utils.logger import get_logger

_log = get_logger('importer')

class FirebirdImporter:
    """
    Classe responsável por persistir os dados validados e transformados
    no banco de dados Firebird utilizando transações seguras.
    """
    def __init__(self, fb_service: FirebirdService):
        self.fb_service = fb_service

    def _sanitize_valores(self, valores: List[Any]) -> List[Any]:
        for idx, val in enumerate(valores):
            # Identifica um timestamp ISO (ex: 2023-10-25T08:47:44.000Z)
            if isinstance(val, str) and len(val) >= 19 and val[10] == 'T' and val[4] == '-' and val[7] == '-':
                # Converte para padrão puro Firebird TIMESTAMP (2023-10-25 08:47:44.000)
                val = val.replace('T', ' ').replace('Z', '')
                idx_plus = val.find('+', 19)
                if idx_plus != -1:
                    val = val[:idx_plus]
                idx_minus = val.find('-', 19)
                if idx_minus != -1:
                    val = val[:idx_minus]
                valores[idx] = val
        return valores

    def import_produtos(self, produtos: List[Dict[str, Any]], progress_callback=None) -> Dict[str, Any]:
        """
        Insere um lote de novos produtos na TABELA_PRODUTO.
        Remove automaticamente chaves internas (prefixo '_') que não são colunas do banco.
        progress_callback: callable(atual, total) opcional para reportar progresso.
        """
        if not produtos:
            return {'inseridos': 0, 'erros': []}
            
        def _callback(cur: fdb.Cursor):
            inseridos = 0
            total = len(produtos)
            for i, prod in enumerate(produtos):
                try:
                    prod_limpo = {k: v for k, v in prod.items() if not k.startswith('_')}
                    colunas = list(prod_limpo.keys())
                    valores = list(prod_limpo.values())
                    valores = self._sanitize_valores(valores)
                    placeholders = ",".join(["?"] * len(colunas))
                    
                    sql = f"INSERT INTO TABELA_PRODUTO ({','.join(colunas)}) VALUES ({placeholders})"
                    cur.execute(sql, valores)
                    inseridos += 1
                    
                    # Salva a unidade padrão na tabela de unidades
                    cod_unidade = prod.get('_UNIDADE_CODIGO', 2)
                    codigo_produto = prod.get('PRODUTO_CODIGO')
                    if codigo_produto:
                        sql_unid = """
                            UPDATE OR INSERT INTO TABELA_PRODUTO_UNIDADE 
                            (TPU_PROD_EMPRESA, TPU_PROD_FILIAL, TPU_PRODUTO, TPU_COD_UNIDADE, TPU_UNIDADE_PADRAO)
                            VALUES (?, ?, ?, ?, 'S')
                            MATCHING (TPU_PROD_EMPRESA, TPU_PROD_FILIAL, TPU_PRODUTO, TPU_COD_UNIDADE)
                        """
                        cur.execute(sql_unid, [prod.get('PRODUTO_EMPRESA', 1), prod.get('PRODUTO_FILIAL', 1), codigo_produto, cod_unidade])

                        # Salva o codigo de barras (EAN) na tabela de barras;
                        # senao a tela geral de produtos nao exibe o EAN.
                        cbarra = str(prod.get('PRODUTO_CBARRA') or '').strip()
                        if cbarra and str(codigo_produto).strip().isdigit():
                            cur.execute(
                                "UPDATE OR INSERT INTO TABELA_PRODUTO_CBARRA "
                                "(PCB_EMPRESA, PCB_FILIAL, PCB_PRODUTO, PCB_CBARRA, PCB_QTDE_PACK) "
                                "VALUES (?, ?, ?, ?, 1) "
                                "MATCHING (PCB_EMPRESA, PCB_FILIAL, PCB_PRODUTO, PCB_CBARRA)",
                                [prod.get('PRODUTO_EMPRESA', 1), prod.get('PRODUTO_FILIAL', 1), int(codigo_produto), cbarra[:128]]
                            )

                    if progress_callback and (i % 25 == 0 or i == total - 1):
                        progress_callback(i + 1, total)
                except Exception as e:
                    # Interrompe o processo e aciona o ROLLBACK da transação
                    raise Exception(f"Erro ao inserir produto '{prod.get('PRODUTO_DESCRICAO', 'N/A')}': {str(e)}")
                    
            return {'inseridos': inseridos, 'erros': []}
            
        try:
            return self.fb_service.transaction(_callback)
        except Exception as e:
            return {'inseridos': 0, 'erros': [{'erro': str(e)}]}

    def update_produtos(self, produtos: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Atualiza dados de produtos já existentes na TABELA_PRODUTO.
        Exige que o campo 'PRODUTO_CODIGO' esteja presente no dicionário.
        """
        if not produtos:
            return {'atualizados': 0, 'erros': []}
            
        def _callback(cur: fdb.Cursor):
            atualizados = 0
            for i, prod in enumerate(produtos):
                try:
                    # Extrai o código para usar no WHERE e remove do dict do SET
                    # Chaves internas (prefixo '_') nao sao colunas: se entrarem
                    # no SET o UPDATE morre com -206 (coluna desconhecida).
                    prod_copy = {k: v for k, v in prod.items() if not k.startswith('_')}
                    codigo = prod_copy.pop('PRODUTO_CODIGO', None)
                    if not codigo:
                        raise ValueError("Chave 'PRODUTO_CODIGO' não fornecida para atualização.")
                        
                    colunas = list(prod_copy.keys())
                    valores = list(prod_copy.values())
                    valores = self._sanitize_valores(valores)
                    
                    set_clause = ", ".join([f"{col} = ?" for col in colunas])
                    sql = f"UPDATE TABELA_PRODUTO SET {set_clause} WHERE PRODUTO_CODIGO = ?"
                    
                    valores.append(codigo)
                    cur.execute(sql, valores)

                    # Codigo de barras (EAN) na tabela de barras (tela geral)
                    cbarra = str(prod.get('PRODUTO_CBARRA') or '').strip()
                    if cbarra and str(codigo).strip().isdigit():
                        cur.execute(
                            "UPDATE OR INSERT INTO TABELA_PRODUTO_CBARRA "
                            "(PCB_EMPRESA, PCB_FILIAL, PCB_PRODUTO, PCB_CBARRA, PCB_QTDE_PACK) "
                            "VALUES (?, ?, ?, ?, 1) "
                            "MATCHING (PCB_EMPRESA, PCB_FILIAL, PCB_PRODUTO, PCB_CBARRA)",
                            [prod.get('PRODUTO_EMPRESA', 1), prod.get('PRODUTO_FILIAL', 1), int(codigo), cbarra[:128]]
                        )
                    atualizados += 1
                    
                    if atualizados % 100 == 0:
                        _log.info(f"Progresso: {atualizados}/{len(produtos)} produtos atualizados...")
                except Exception as e:
                    raise Exception(f"Erro ao atualizar produto código '{codigo}': {str(e)}")
                    
            return {'atualizados': atualizados, 'erros': []}
            
        try:
            return self.fb_service.transaction(_callback)
        except Exception as e:
            return {'atualizados': 0, 'erros': [{'erro': str(e)}]}

    def import_icms(self, regras: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Importa regras de ICMS fazendo UPSERT e lidando com dados retroativos e benefícios fiscais.
        """
        if not regras:
            return {'inseridos': 0, 'erros': []}
            
        def _callback(cur: fdb.Cursor):
            faixas_atualizadas = set()
            processados = 0
            
            for i, r in enumerate(regras):
                try:
                    # 1. Update de data retroativa (executado apenas uma vez por faixa)
                    chave_faixa = (r.get('AICMS_EMPRESA'), r.get('AICMS_FILIAL'), r.get('AICMS_FAIXA'))
                    if chave_faixa not in faixas_atualizadas:
                        cur.execute(
                            "UPDATE TABELA_ALIQUOTA_ICMS SET AICMS_DATA = ? WHERE AICMS_EMPRESA = ? AND AICMS_FILIAL = ? AND AICMS_FAIXA = ?",
                            (r.get('AICMS_DATA'), *chave_faixa)
                        )
                        faixas_atualizadas.add(chave_faixa)
                        
                    # Filtra apenas colunas pertinentes à tabela de alíquotas
                    dict_icms = {k: v for k, v in r.items() if k.upper().startswith('AICMS_')}
                    colunas = list(dict_icms.keys())
                    valores = list(dict_icms.values())
                    placeholders = ",".join(["?"] * len(colunas))
                    
                    # 2. UPDATE OR INSERT na tabela de ICMS
                    sql_upsert = f"UPDATE OR INSERT INTO TABELA_ALIQUOTA_ICMS ({','.join(colunas)}) VALUES ({placeholders}) MATCHING (AICMS_EMPRESA, AICMS_FILIAL, AICMS_DATA, AICMS_FAIXA, AICMS_ESTADO)"
                    cur.execute(sql_upsert, valores)
                    
                    # 3. Regra de Benefício Fiscal (TABELA_CBENEF)
                    c_cred = r.get('CBE_C_CREDPRESUMIDO')
                    p_cred = r.get('CBE_P_CREDPRESUMIDO')
                    
                    if c_cred or p_cred:
                        cur.execute("SELECT CBE_ID FROM TABELA_CBENEF WHERE CBE_C_CREDPRESUMIDO = ? AND CBE_P_CREDPRESUMIDO = ?", (c_cred, p_cred))
                        row = cur.fetchone()
                        if not row:
                            cur.execute("SELECT COALESCE(MAX(CBE_ID), 0) + 1 FROM TABELA_CBENEF")
                            novo_cbe_id = cur.fetchone()[0]
                            cur.execute("INSERT INTO TABELA_CBENEF (CBE_ID, CBE_C_CREDPRESUMIDO, CBE_P_CREDPRESUMIDO) VALUES (?, ?, ?)", (novo_cbe_id, c_cred, p_cred))
                        else:
                            novo_cbe_id = row[0]
                            
                        tipos_cf = r.get('TACB_TIPO_CF') or r.get('tipos_cf', [])
                        if not isinstance(tipos_cf, list):
                            tipos_cf = [tipos_cf]
                            
                        for tipo in tipos_cf:
                            try:
                                cur.execute(
                                    "UPDATE OR INSERT INTO TABELA_ALIQUOTA_ICMS_CBENEF "
                                    "(TACB_AICMS_EMPRESA, TACB_AICMS_FILIAL, TACB_AICMS_DATA, "
                                    "TACB_AICMS_FAIXA, TACB_AICMS_ESTADO, TACB_CBE_ID, TACB_TIPO_CF) "
                                    "VALUES (?, ?, ?, ?, ?, ?, ?) "
                                    "MATCHING (TACB_AICMS_EMPRESA, TACB_AICMS_FILIAL, TACB_AICMS_DATA, "
                                    "TACB_AICMS_FAIXA, TACB_AICMS_ESTADO, TACB_TIPO_CF)",
                                    (r.get('AICMS_EMPRESA'), r.get('AICMS_FILIAL'), r.get('AICMS_DATA'),
                                     r.get('AICMS_FAIXA'), r.get('AICMS_ESTADO'), novo_cbe_id, tipo)
                                )
                            except Exception as e_up:
                                if 'violation of primary or unique key' in str(e_up).lower():
                                    try:
                                        cur.execute(
                                            "INSERT INTO TABELA_ALIQUOTA_ICMS_CBENEF (TACB_AICMS_EMPRESA, TACB_AICMS_FILIAL, TACB_AICMS_DATA, TACB_AICMS_FAIXA, TACB_AICMS_ESTADO, TACB_CBE_ID, TACB_TIPO_CF) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                            (r.get('AICMS_EMPRESA'), r.get('AICMS_FILIAL'), r.get('AICMS_DATA'), r.get('AICMS_FAIXA'), r.get('AICMS_ESTADO'), novo_cbe_id, tipo)
                                        )
                                    except Exception as e_in:
                                        if 'violation of primary or unique key' not in str(e_in).lower():
                                            raise e_in
                                else:
                                    raise e_up
                            
                    processados += 1
                    if processados % 100 == 0:
                        _log.info(f"Progresso: {processados}/{len(regras)} regras ICMS importadas...")
                        
                except Exception as e:
                    raise Exception(f"Erro na regra ICMS {r.get('AICMS_FAIXA')} - Estado {r.get('AICMS_ESTADO')}: {str(e)}")
                    
            return {'inseridos': processados, 'erros': []}
            
        try:
            return self.fb_service.transaction(_callback)
        except Exception as e:
            return {'inseridos': 0, 'erros': [{'erro': str(e)}]}

    def import_cfops(self, cfops: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Importa a natureza de operação de saída (CFOPs) usando UPSERT.
        """
        def _callback(cur: fdb.Cursor):
            processados = 0
            for r in cfops:
                try:
                    # Garante as regras fixas exigidas pela modelagem
                    r.update({'NAT_DESATIVADO': 'N', 'NAT_REMESSA': 'N', 'NAT_ST': 'S', 'NAT_PIS': 'S', 'NAT_COFINS': 'S'})
                    if 'NAT_DESCRICAO_ABR' in r and r['NAT_DESCRICAO_ABR']:
                        r['NAT_DESCRICAO_ABR'] = str(r['NAT_DESCRICAO_ABR'])[:30]
                    if 'NAT_DESCRICAO_COMP' in r and r['NAT_DESCRICAO_COMP']:
                        r['NAT_DESCRICAO_COMP'] = str(r['NAT_DESCRICAO_COMP'])[:50]
                        
                    colunas = list(r.keys())
                    valores = list(r.values())
                    placeholders = ",".join(["?"] * len(colunas))
                    
                    sql = f"UPDATE OR INSERT INTO TABELA_NAT_OPERACAO_SAIDA ({','.join(colunas)}) VALUES ({placeholders}) MATCHING (NAT_EMPRESA, NAT_FILIAL, NAT_CODIGO)"
                    cur.execute(sql, valores)
                    processados += 1
                except Exception as e:
                    raise Exception(f"Erro no CFOP '{r.get('NAT_CODIGO', 'N/A')}': {str(e)}")
            return {'inseridos': processados, 'erros': []}
            
        try:
            return self.fb_service.transaction(_callback)
        except Exception as e:
            return {'inseridos': 0, 'erros': [{'erro': str(e)}]}

    def import_rt(self, regras_rt: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Importa configurações da Reforma Tributária (IBS/CBS) 2025/2026.
        """
        if not regras_rt:
            return {'inseridos': 0, 'erros': []}
            
        def _callback(cur: fdb.Cursor):
            processados = 0
            for r in regras_rt:
                try:
                    trt_id = r.get('TRT_ID')
                    class_trib = r.get('TRT_CLASS_TRIB_ID') if 'TRT_CLASS_TRIB_ID' in r else r.get('TRT_CLAS_TRIB_ID')
                    cst = r.get('TRT_CST')
                    aliq_ibs = r.get('TRT_ALIQ_IBS_ESTADUAL')
                    aliq_cbs = r.get('TRT_ALIQ_CBS')
                    
                    sql = "UPDATE OR INSERT INTO TABELA_RT_CONFIG_2025_2026 (TRT_ID, TRT_CLASS_TRIB_ID, TRT_CST, TRT_ALIQ_IBS_ESTADUAL, TRT_ALIQ_CBS) VALUES (?, ?, ?, ?, ?) MATCHING (TRT_ID)"
                    cur.execute(sql, (trt_id, class_trib, cst, aliq_ibs, aliq_cbs))
                    processados += 1
                except Exception as e:
                    raise Exception(f"Erro na regra RT ID '{r.get('TRT_ID', 'N/A')}': {str(e)}")
            return {'inseridos': processados, 'erros': []}
            
        try:
            return self.fb_service.transaction(_callback)
        except Exception as e:
            return {'inseridos': 0, 'erros': [{'erro': str(e)}]}
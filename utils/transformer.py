from datetime import datetime, date
import re
from typing import Dict, Any, Tuple, Set, Optional

class DataTransformer:
    """
    Utilitário para transformar e higienizar os dados do XML 
    antes que eles sejam inseridos ou atualizados no Firebird.
    """
    @staticmethod
    def clean_float(value: Any) -> Optional[float]:
        """Converte strings com vírgula para float de forma segura."""
        if value is None or str(value).strip() == '':
            return None
        if isinstance(value, float):
            return value
        if isinstance(value, int):
            return float(value)
        s = str(value).strip().replace(',', '.')
        try:
            return float(s)
        except ValueError:
            return None

    @staticmethod
    def get_codigo_unidade(unidade_str: str) -> int:
        unidade_str = str(unidade_str).strip().upper()
        unidades_map = {
            "%": 43, "%0": 105, ",6": 44, ".": 92, "00": 78, "01": 55, "03": 86, "06": 87,
            "1": 18, "10": 62, "13": 68, "18": 42, "1K": 57, "2": 19, "20": 71, "3": 34,
            "30": 66, "8L": 48, "AM": 75, "AP": 99, "BA": 58, "BB": 24, "BD": 33, "BG": 100,
            "BI": 67, "BL": 40, "BP": 73, "BR": 16, "CA": 32, "CD": 83, "CE": 11, "CJ": 39,
            "CM": 70, "CN": 35, "CR": 98, "CT": 41, "CX": 12, "CH": 85, "DE": 17, "DI": 51,
            "DP": 52, "DS": 69, "DT": 81, "DZ": 29, "EB": 89, "EE": 82, "EM": 25, "EN": 102,
            "ES": 104, "EV": 76, "FC": 65, "FD": 26, "FL": 79, "FR": 59, "GA": 53, "GL": 20,
            "JG": 23, "JO": 45, "KG": 1, "KI": 84, "KL": 46, "KM": 14, "KT": 74, "KW": 38,
            "L": 4, "LA": 49, "LI": 56, "LT": 3, "M": 15, "M2": 21, "M3": 28, "MA": 97,
            "MI": 94, "ML": 6, "MM": 80, "MP": 36, "MQ": 37, "MT": 8, "MU": 112, "OC": 77,
            "PA": 60, "PC": 5, "PD": 22, "PE": 13, "PO": 50, "PP": 72, "PR": 30, "PT": 27,
            "PÇ": 47, "RL": 31, "RO": 63, "SC": 9, "SE": 103, "SG": 101, "SR": 93, "SV": 113,
            "TB": 64, "TL": 107, "TN": 61, "TO": 10, "TU": 54, "UD": 7, "UN": 2, "VD": 88,
            "XX": 90, "QT": 91
        }
        return unidades_map.get(unidade_str, 2)

    @staticmethod
    def prepare_codigo_produto(c_prod: str, existing_codes: Set[str], modo: str = 'xml') -> Tuple[str, str]:
        """
        Gera o código do produto de acordo com o modo selecionado.
        
        modo='xml' (padrão): Usa o código do XML. Se já existir, preenche a 
                             menor lacuna disponível (gap-filling).
        modo='sequencial': Ignora o código do XML e gera o próximo número 
                           sequencial disponível.
        
        Retorna a tupla (PRODUTO_CODIGO, PRODUTO_COD_AUXILIAR).
        """
        if modo == 'sequencial':
            max_num = 0
            for code in existing_codes:
                clean = code.lstrip('0') or '0'
                if clean.isdigit():
                    max_num = max(max_num, int(clean))
            codigo_final = str(max_num + 1)
            return (codigo_final, None)

        c_prod_str = str(c_prod).strip()
        c_prod_clean = c_prod_str.lstrip('0') or '0'

        existing_clean = {c.lstrip('0') or '0' for c in existing_codes}

        if c_prod_clean in existing_clean:
            codigos_numericos = sorted(
                int(c) for c in existing_clean if c.isdigit()
            )
            menor = 1
            for c in codigos_numericos:
                if c == menor:
                    menor += 1
                elif c > menor:
                    break
            return (str(menor), c_prod_str)
        else:
            return (c_prod_str, c_prod_str)

    @staticmethod
    def prepare_produto(xml_item: Dict[str, Any], config: Dict[str, Any], grupos: Dict[str, Any]) -> Dict[str, Any]:
        """Prepara o dicionário de campos preenchidos para o INSERT do novo produto."""
        desc = str(xml_item.get('x_prod') or '').upper()
        desc_1 = desc[:100] # Limite padrão de descrição

        ncm = re.sub(r'\D', '', str(xml_item.get('ncm') or ''))
        ncm_fmt = f"{ncm[:4]}.{ncm[4:6]}.{ncm[6:]}" if len(ncm) == 8 else ncm

        c_barra = str(xml_item.get('c_ean') or str(xml_item.get('c_barra') or '')).strip()
        if c_barra.upper() in ('SEM GTIN', 'SEMGTIN', '0', '', '00000000000000'):
            c_barra = None

        unidade = str(xml_item.get('u_com') or '').strip().upper()[:6]
        
        emp = config.get('empresa', 1)
        fil = config.get('filial', 1)
        ano = date.today().year
        hoje_data = date.today().isoformat()
        hoje_hora = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.000Z")
        
        tipo_str = str(grupos.get('tipo', '4'))
        tipo_id = int(tipo_str.split('-')[0].strip()) if '-' in tipo_str else 4
        
        # Regra do SPED baseada no Tipo
        sped_map = {1: '00', 2: '07', 3: '01', 4: '04', 5: '09', 6: '10'}
        tipo_sped = sped_map.get(tipo_id, '04')
        
        grupo_id = grupos.get('grupo_id') or 1
        subgrupo_id = grupos.get('subgrupo_id') or 1
        producao_sistec = grupos.get('producao_sistec')

        novo_produto = {
            'PRODUTO_EMPRESA': emp,
            'PRODUTO_FILIAL': fil,
            'PRODUTO_TIPO': tipo_id,
            'PRODUTO_TIPO_PRODUTO_SPED': tipo_sped,
            'PRODUTO_SUBGRUPO_EMPRESA': emp,
            'PRODUTO_SUBGRUPO_FILIAL': fil,
            'PRODUTO_SUBGRUPO': subgrupo_id,
            'PRODUTO_GRUPO_EMPRESA': emp,
            'PRODUTO_GRUPO_FILIAL': fil,
            'PRODUTO_GRUPO': grupo_id,
            'PRODUTO_ATIVO': 'S',
            'PRODUTO_MARCA_EMPRESA': emp,
            'PRODUTO_MARCA_FILIAL': fil,
            'PRODUTO_MARCA': None,
            'PRODUTO_DESCRICAO': desc_1,
            'PRODUTO_DESCRICAO2': desc_1,
            'PRODUTO_CONTROLE_QTDE': 'N',
            'PRODUTO_LESTOQUE_EMPRESA': emp,
            'PRODUTO_LESTOQUE_FILIAL': fil,
            'PRODUTO_LESTOQUE': None,
            'PRODUTO_UNIDADE_CV': unidade,
            'PRODUTO_CONTEUDO_EMB': 1.0,
            'PRODUTO_MULTIPLO': 1.0,
            'PRODUTO_UNIDADE_EST': unidade,
            'PRODUTO_ESTOQUE_MIN': None,
            'PRODUTO_ESTOQUE_MAX': None,
            'PRODUTO_PESO': 0.0,
            'PRODUTO_REG_MIN_AGR_SAUDE': None,
            'PRODUTO_SUBST_TRIBUTARIA': 'S' if (xml_item.get('p_icmsst') or 0) > 0 else 'N',
            'PRODUTO_CLASS_FISCAL': ncm_fmt,
            'PRODUTO_PERC_SUBST_TRIBUTARIA': None,
            'PRODUTO_ICMS': 0,
            'PRODUTO_GARANTIA': None,
            'PRODUTO_IPI': None,
            'PRODUTO_ONU': None,
            'PRODUTO_CLASSE_RISCO': None,
            'PRODUTO_NUM_RISCO': None,
            'PRODUTO_LCLASS_FISCAL': None,
            'PRODUTO_PIS': 'N',
            'PRODUTO_COFINS': 'N',
            'PRODUTO_CONTABIL_EMPRESA': emp,
            'PRODUTO_CONTABIL_FILIAL': fil,
            'PRODUTO_CONTABIL_EXERCICIO': ano,
            'PRODUTO_CONTABIL': None,
            'PRODUTO_CONTABIL_REDUZIDO': None,
            'PRODUTO_CC_EMPRESA': emp,
            'PRODUTO_CC_FILIAL': fil,
            'PRODUTO_CC': None,
            'PRODUTO_CERTIFICADO': 'N',
            'PRODUTO_UN_EXP': unidade,
            'PRODUTO_CBARRA': c_barra,
            'PRODUTO_DATA': hoje_data,
            'PRODUTO_DATA_ALT': hoje_data,
            'PRODUTO_GERA_CONTABIL': 'P',
            'PRODUTO_ORIGEM': '0',
            'PRODUTO_SIMILARIDADE_EMP': emp,
            'PRODUTO_SIMILARIDADE_FIL': fil,
            'PRODUTO_ULT_GRAVACAO': hoje_hora,
            'PRODUTO_CLASS_FISCAL_EMP': emp,
            'PRODUTO_CLASS_FISCAL_FIL': fil,
            'PRODUTO_QTDE_PECAS': 1,
            'PRODUTO_CF_EMPRESA': emp,
            'PRODUTO_CF_FILIAL': fil,
            'PRODUTO_PRODUCAO_SISTEC': producao_sistec,
            'PRODUTO_HIST_CONTABIL_EMP': emp,
            'PRODUTO_HIST_CONTABIL_FIL': fil,
            'PRODUTO_CLASS_EMPRESA': 0,
            'PRODUTO_CLASS_FILIAL': 0,
            '_UNIDADE_CODIGO': DataTransformer.get_codigo_unidade(unidade)
        }
        
        return novo_produto

    @staticmethod
    def prepare_tributacao_update(xml_item: Dict[str, Any], erp_match: Dict[str, Any], update_trib: bool) -> Dict[str, Any]:
        """Retorna o dicionário de campos para o SET do comando UPDATE do produto."""
        desc = str(xml_item.get('x_prod') or '').upper()[:50]
        unidade = str(xml_item.get('u_com') or '').strip().upper()[:6]
        
        update_data = {
            'PRODUTO_DESCRICAO': desc,
            'PRODUTO_CLASS_FISCAL': re.sub(r'\D', '', str(xml_item.get('ncm') or '')),
            'PRODUTO_UNIDADE_CV': unidade,
            'PRODUTO_UNIDADE_EST': unidade,
            'PRODUTO_UN_EXP': unidade,
            'PRODUTO_CONTEUDO_EMB': 1.0,
            'PRODUTO_MULTIPLO': 1.0,
            'PRODUTO_DATA_ALT': date.today()
        }
        
        if update_trib:
            pass # Aqui pode plugar a atualização de PRODUTO_ICMS e PIS/COFINS de forma dinâmica, caso a UI permita sobreposição.
        return update_data
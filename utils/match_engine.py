import unicodedata
import re
from functools import lru_cache
from typing import List, Dict, Any, Optional, Tuple

@lru_cache(maxsize=4096)
def norm_str(s: str) -> str:
    """Normaliza strings de descrição para comparação avançada."""
    s = str(s or '')
    s = s.replace('&QUOT;', '"').replace('&AMP;', '&').replace('&LT;', '<').replace('&GT;', '>')
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn') # Remove acentos
    s = re.sub(r'["\'\']+', '', s)
    s = re.sub(r'\s+', ' ', s).strip().upper()
    return s

def build_product_index(erp_produtos: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Cria dicionários para acesso O(1) rápido aos produtos ERP."""
    indice = {
        'by_gtin': {},
        'by_ncm': {}
    }
    for prod in erp_produtos:
        gtin = str(prod.get('produto_cbarra') or '').strip().upper()
        if gtin and gtin not in ('SEM GTIN', 'SEMGTIN', '0', ''):
            # Evita sobrescrever se houver GTINs duplicados (fica com o primeiro)
            if gtin not in indice['by_gtin']:
                indice['by_gtin'][gtin] = prod
                
        ncm = str(prod.get('produto_class_fiscal') or '').strip()
        ncm_limpo = re.sub(r'\D', '', ncm)
        if ncm_limpo:
            # Mantém uma lista de produtos por NCM, já que NCM não é exclusivo
            if ncm_limpo not in indice['by_ncm']:
                indice['by_ncm'][ncm_limpo] = []
            indice['by_ncm'][ncm_limpo].append(prod)
            
    return indice

def find_by_code(code: str, erp_produtos: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Busca um produto pelo seu código exato (PRODUTO_CODIGO ou PRODUTO_COD_AUXILIAR)."""
    code_str = str(code).strip()
    for prod in erp_produtos:
        if str(prod.get('produto_codigo') or '').strip() == code_str:
            return prod
        if str(prod.get('produto_cod_auxiliar') or '').strip() == code_str:
            return prod
    return None

def get_best_match(xml_item: Dict[str, Any], erp_produtos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Busca o melhor correspondente do produto XML dentro da lista do ERP, 
    replicando as regras de heurística originais.
    """
    xml_gtin = str(xml_item.get('c_ean') or '').strip().upper()
    xml_ncm = re.sub(r'\D', '', str(xml_item.get('ncm') or ''))
    xml_desc = norm_str(xml_item.get('x_prod', ''))
    xml_desc_prefix = xml_desc[:8] if len(xml_desc) >= 8 else xml_desc

    best_match = None
    best_score = 0

    for erp in erp_produtos:
        score = 0
        erp_gtin = str(erp.get('produto_cbarra') or '').strip().upper()
        erp_ncm = re.sub(r'\D', '', str(erp.get('produto_class_fiscal') or ''))
        erp_desc = norm_str(erp.get('produto_descricao', '') + ' ' + (erp.get('produto_descricao2') or ''))

        if xml_gtin and erp_gtin and xml_gtin == erp_gtin and xml_gtin not in ('SEM GTIN', 'SEMGTIN', '0'):
            score += 100
        if xml_ncm and erp_ncm and xml_ncm == erp_ncm:
            score += 10
        if xml_desc and erp_desc and xml_desc == erp_desc:
            score += 20
        if xml_desc_prefix and len(xml_desc_prefix) >= 8 and xml_desc_prefix in erp_desc:
            score += 5

        if score > best_score:
            best_score = score
            best_match = erp
            if score >= 100:  # Optimization: já atingiu aprovação máxima
                break

    return {
        'match': best_match,
        'score': best_score,
        'auto_approve': best_score >= 100
    }
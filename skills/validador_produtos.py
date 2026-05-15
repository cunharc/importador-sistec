from typing import List, Dict, Any
from utils.xml_reader import parse_nfe_folder, parse_nfe

class ValidadorProdutosSkill:
    """
    A mais complexa das Skills. Faz o cruzamento de todas as malhas fiscais (ICMS, NCM, CFOP)
    por nível de Produto (EAN/Código). Usado para consolidação da Tabela de Produtos antes da importação.
    """

    def __init__(self):
        pass

    def validar_e_agrupar_produtos(self, arquivos: List[str] = None, pasta: str = None) -> List[Dict[str, Any]]:
        itens_xml = []
        if arquivos:
            for arq in arquivos:
                try:
                    res = parse_nfe(arq)
                    if res and 'itens' in res:
                        itens_xml.extend(res['itens'])
                except Exception:
                    pass
        elif pasta:
            itens_xml = parse_nfe_folder(pasta)

        mapa_produtos = {}
        for i in itens_xml:
            tag_identificacao = f"{i.get('c_prod')}|{i.get('ean')}|{i.get('descricao')}"
            
            if tag_identificacao not in mapa_produtos:
                mapa_produtos[tag_identificacao] = {
                    'c_prod': i.get('c_prod'),
                    'ean': i.get('ean'),
                    'descricao': i.get('descricao'),
                    'ncm': i.get('ncm'),
                    'cfop': i.get('cfop'),
                    'cst': i.get('icms_cst'),
                    'ocorrencias': 1
                }
            else:
                mapa_produtos[tag_identificacao]['ocorrencias'] += 1

        return sorted(list(mapa_produtos.values()), key=lambda x: x['ocorrencias'], reverse=True)

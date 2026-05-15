from typing import List, Dict, Any
from utils.xml_reader import parse_nfe_folder, parse_nfe

class ReformaTributariaSkill:
    """
    Skill de Inteligência Tributária (IBS/CBS). Processa os CSTs da transição
    de reforma tributária baseados em arquivos fiscais da versão moderna das NFes.
    """

    def __init__(self):
        pass

    def agrupar_regras_ibs_cbs(self, arquivos: List[str] = None, pasta: str = None) -> List[Dict[str, Any]]:
        """
        Busca e unifica a dupla IBS e CBS contida no detalhamento dos itens nos XMLs.
        """
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

        mapa = {}
        for i in itens_xml:
            c_class_trib = str(i.get('c_class_trib') or '').strip()
            ibscbs_cst = str(i.get('ibscbs_cst') or '').strip()
            p_ibs = i.get('p_ibs_uf') or 0.0
            p_cbs = i.get('p_cbs') or 0.0

            if not c_class_trib and not ibscbs_cst:
                continue

            assinatura = f"{c_class_trib}|{ibscbs_cst}|{p_ibs}|{p_cbs}"
            if assinatura not in mapa:
                mapa[assinatura] = {
                    'id': f"rt_{len(mapa)}",
                    'ocorrencias': 1,
                    'c_class_trib': c_class_trib,
                    'ibscbs_cst': ibscbs_cst,
                    'p_ibs_uf': p_ibs,
                    'p_cbs': p_cbs,
                    'status_erp': '-'
                }
            else:
                mapa[assinatura]['ocorrencias'] += 1

        return sorted(list(mapa.values()), key=lambda x: (x['c_class_trib'], x['ibscbs_cst']))

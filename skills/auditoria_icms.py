from typing import List, Dict, Any, Tuple
from utils.xml_reader import parse_nfe_folder, parse_nfe

class AuditoriaIcmsSkill:
    """
    Skill responsável por processar arquivos XML de NF-e e agrupar as tributações de ICMS
    para montagem da matriz de regras no ERP (TABELA_ALIQUOTA_ICMS).
    """

    def __init__(self):
        pass

    def agrupar_xml_icms(self, arquivos: List[str] = None, pasta: str = None) -> List[Dict[str, Any]]:
        """
        Lê e extrai itens de XMLs, montando as assinaturas únicas de ICMS por UF.
        :param arquivos: Lista de caminhos para arquivos .xml.
        :param pasta: Caminho de um diretório contendo .xml.
        :return: Lista de dicionários agrupados por regra de ICMS.
        """
        itens_xml = []
        if arquivos:
            for arq in arquivos:
                try:
                    resultado = parse_nfe(arq)
                    if resultado and 'itens' in resultado:
                        itens_xml.extend(resultado['itens'])
                except Exception as e:
                    print(f"Erro na leitura do xml {arq}: {e}")
        elif pasta:
            itens_xml = parse_nfe_folder(pasta)

        mapa_icms = {}
        for i in itens_xml:
            # Assinatura única de identificação da regra de ICMS
            assinatura = (
                str(i.get('uf_emit', '')).strip(),
                str(i.get('uf_dest', '')).strip(),
                str(i.get('cfop', '')).strip(),
                str(i.get('icms_cst', '')).strip(),
                float(i.get('p_icms') or 0.0),
                float(i.get('p_red_bc') or 0.0),
                str(i.get('c_benef', '')).strip(),
                str(i.get('tipo_cliente', 'NC')).strip()
            )

            if assinatura not in mapa_icms:
                mapa_icms[assinatura] = {
                    'id': f"icms_{len(mapa_icms)}",
                    'ocorrencias': 1,
                    'uf_emit': assinatura[0],
                    'uf_dest': assinatura[1],
                    'cfop': assinatura[2],
                    'icms_cst': assinatura[3],
                    'p_icms': assinatura[4],
                    'p_red_bc': assinatura[5],
                    'c_benef': assinatura[6],
                    'tipo_cliente': assinatura[7],
                    'p_fcp': float(i.get('p_fcp') or 0.0),
                    'c_cred': str(i.get('c_cred', '')).strip(),
                    'p_cred': float(i.get('p_cred') or 0.0),
                    'p_mvast': float(i.get('p_mvast') or 0.0),
                    'p_icmsst': float(i.get('p_icmsst') or 0.0),
                    'faixas_erp': '-'
                }
            else:
                mapa_icms[assinatura]['ocorrencias'] += 1

        # Ordenar por maior ocorrência e UF
        lista_final = sorted(list(mapa_icms.values()), key=lambda x: (x['ocorrencias'], x['uf_dest']), reverse=True)
        return lista_final

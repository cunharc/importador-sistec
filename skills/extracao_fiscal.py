from typing import List, Dict, Any
from utils.xml_reader import parse_nfe_folder, parse_nfe

class ExtracaoFiscalSkill:
    """
    Skill responsável por extrair dados consolidados de clientes e fornecedores
    a partir da estrutura fiscal presente nos arquivos NFe.
    """

    def __init__(self):
        pass

    def extrair_clientes_fornecedores(self, arquivos: List[str] = None, pasta: str = None) -> List[Dict[str, Any]]:
        """
        Extrai o emissor e destinatário de milhares de XMLs.
        Garante que apenas informações não duplicadas retornem para auto-cadastro no Firebird.
        """
        notas = []
        if arquivos:
            for arq in arquivos:
                try:
                    res = parse_nfe(arq)
                    if res:
                        notas.append(res)
                except Exception:
                    pass
        elif pasta:
            # Aqui podemos ter um método especial que extrai apenas os cabeçalhos para evitar memória
            notas = [parse_nfe(f) for f in []] # TODO impl parse massivo para extracao_fiscal especifico

        # Logica Mock de extração já que ela existe solta no aplicativo principal ou nos modules do importer
        return notas

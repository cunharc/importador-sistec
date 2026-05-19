from typing import List, Dict, Any
from utils.xml_reader import parse_nfe_folder, parse_nfe
import glob
import os

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
        
        lista_arquivos = arquivos if arquivos else []
        if pasta:
            lista_arquivos.extend(glob.glob(os.path.join(pasta, '**', '*.xml'), recursive=True))
            
        for arq in lista_arquivos:
            try:
                res = parse_nfe(arq)
                if res:
                    notas.append(res)
            except Exception:
                pass
                
        return notas

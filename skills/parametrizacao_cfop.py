import json
import os
from typing import List, Dict, Any

from utils.xml_reader import parse_nfe_folder, parse_nfe

class ParametrizacaoCfopSkill:
    """
    Skill responsável pela análise das Naturezas de Operação (CFOP).
    Cruza as operações contidas em notas fiscais contra as bases oficiais do Governo.
    """

    def __init__(self, caminho_base_governo: str = None):
        self.cfop_governo = {}
        if caminho_base_governo:
            self.carregar_base_governo(caminho_base_governo)

    def carregar_base_governo(self, filepath: str):
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    dados = json.load(f)
                    for row in dados:
                        cod = str(row.get('cfop') or row.get('codigo', ''))
                        if cod:
                            self.cfop_governo[cod] = row
            except Exception as e:
                print(f"Aviso: Erro ao carregar dicionário de CFOP: {e}")

    def extrair_cfop(self, arquivos: List[str] = None, pasta: str = None) -> List[Dict[str, Any]]:
        """
        Agrupa todas as ocorrências de CFOPs dos XMLs para exibição.
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
            cfop = str(i.get('cfop', '')).strip()
            if not cfop:
                continue
            if cfop not in mapa:
                mapa[cfop] = {'ocorrencias': 1, 'cfop': cfop}
            else:
                mapa[cfop]['ocorrencias'] += 1

        for data in mapa.values():
            oficial = self.cfop_governo.get(data['cfop'])
            if oficial:
                data['descricao_oficial'] = oficial.get('descricao', oficial.get('nome', ''))
                data['validez'] = True
            else:
                data['descricao_oficial'] = "CFOP NÃO ENCONTRADO NA BASE OFICIAL"
                data['validez'] = False

        return sorted(list(mapa.values()), key=lambda x: x['ocorrencias'], reverse=True)

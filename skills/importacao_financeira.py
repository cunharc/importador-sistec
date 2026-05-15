from typing import List, Dict, Any

class ImportacaoFinanceiraSkill:
    """
    Skill utilizada para normalização, formatação e importação do Plano de Contas.
    Faz a leitura dos planilhamentos (.xlsx) fornecidos pelo time de contabilidade.
    """

    def __init__(self):
        pass

    def processar_planilha_contas(self, caminho_excel: str) -> List[Dict[str, Any]]:
        """
        Processamento do layout cru do Excel para o formato que deve ser importado
        para a tabela TABELA_PLANO.
        """
        # Integração com o utils.excel_reader na camada de negócio
        from utils.excel_reader import processar_excel
        registros, duplicatas = processar_excel(caminho_excel)
        return registros

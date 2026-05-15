from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string

def listar_abas(caminho_arquivo: str) -> list:
    wb = load_workbook(caminho_arquivo, read_only=True, data_only=True)
    abas = wb.sheetnames
    wb.close()
    return abas

def ler_planilha(caminho_arquivo: str, aba: str, coluna_conta: str, 
                 coluna_descricao: str, linha_inicial: int) -> list:
    """
    Retorna lista de dicts: [{'conta': '1.1.1.01', 'descricao': 'CAIXA'}, ...]
    """
    wb = load_workbook(caminho_arquivo, read_only=True, data_only=True)
    ws = wb[aba]
    
    col_conta_idx = column_index_from_string(coluna_conta)
    col_desc_idx = column_index_from_string(coluna_descricao)
    
    registros = []
    for row in ws.iter_rows(min_row=linha_inicial, values_only=True):
        if len(row) < max(col_conta_idx, col_desc_idx):
            continue
            
        conta = row[col_conta_idx - 1]
        descricao = row[col_desc_idx - 1]
        
        if conta is None or str(conta).strip() == '':
            continue
            
        registros.append({
            'conta': str(conta).strip(),
            'descricao': str(descricao).strip() if descricao else ''
        })
    
    wb.close()
    return registros

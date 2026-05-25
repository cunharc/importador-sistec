from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string
import csv
import os

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

def obter_abas_planilha(caminho_arquivo: str) -> list:
    """Lê as abas de forma segura suportando XLSX e CSV."""
    if str(caminho_arquivo).lower().endswith('.csv'):
        return ['CSV (Aba Única)']
    try:
        wb = load_workbook(caminho_arquivo, read_only=True, data_only=True)
        abas = wb.sheetnames
        wb.close()
        return abas
    except Exception:
        return []

def ler_planilha_produtos(caminho_arquivo: str, aba: str, mapa_colunas: dict, linha_inicial: int) -> list:
    """Lê CSVs ou Excel com base num dicionário de letras de colunas: {'descricao': 'C', 'grupo': 'D'}"""
    registros = []
    
    if caminho_arquivo.lower().endswith('.csv'):
        with open(caminho_arquivo, 'r', encoding='utf-8-sig', errors='ignore') as f:
            reader = csv.reader(f, delimiter=';')
            for i, row in enumerate(reader, start=1):
                if i < linha_inicial: continue
                if not row: continue
                reg = {}
                for chave, letra in mapa_colunas.items():
                    if not letra:
                        reg[chave] = ''
                        continue
                    # Converte Letra da Coluna para Índice Numérico
                    idx = 0
                    for char in letra.strip().upper():
                        idx = idx * 26 + (ord(char) - ord('A')) + 1
                    idx -= 1
                    reg[chave] = str(row[idx]).strip() if idx < len(row) else ''
                if any(reg.values()): registros.append(reg)
    else:
        wb = load_workbook(caminho_arquivo, read_only=True, data_only=True)
        ws = wb[aba] if aba in wb.sheetnames else wb.active
        for i, row in enumerate(ws.iter_rows(values_only=True), start=1):
            if i < linha_inicial: continue
            reg = {}
            for chave, letra in mapa_colunas.items():
                if not letra:
                    reg[chave] = ''
                    continue
                idx = column_index_from_string(letra.strip().upper()) - 1
                val = row[idx] if idx < len(row) else ''
                reg[chave] = str(val).strip() if val is not None else ''
            if any(reg.values()): registros.append(reg)
        wb.close()
    return registros

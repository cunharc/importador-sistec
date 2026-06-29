import json
import os
import sys

try:
    import openpyxl
except ImportError:
    print("A biblioteca 'openpyxl' não foi encontrada.")
    print("Por favor, instale executando: pip install openpyxl")
    sys.exit(1)


COLUNAS_ESPERADAS = {
    'CODIGO': ['Código', 'CODIGO', 'codigo', 'NCM', 'ncm'],
    'DESCRICAO': ['Descrição', 'DESCRIÇÃO', 'Descricao', 'descricao', 'DESCRICAO'],
    'DESCRICAO_CONCAT': ['Descrição Concatenada', 'DESCRIÇÃO CONCATENADA', 'Descricao Concatenada', 'descricao concatenada', 'DESCRICAO CONCATENADA'],
}


def encontrar_coluna(linha_cabecalho, nomes_possiveis):
    for i, val in enumerate(linha_cabecalho):
        if val and str(val).strip() in nomes_possiveis:
            return i
    return None


def ler_planilha_ncm(caminho_xlsx, aba=None):
    wb = openpyxl.load_workbook(caminho_xlsx, data_only=True)

    if aba:
        ws = wb[aba]
    else:
        ws = wb.active

    linhas = list(ws.iter_rows(values_only=True))
    if not linhas:
        print("Planilha vazia!")
        return []

    # Procura a linha de cabeçalho (que contém "Código" ou "codigo")
    def _find_header_row_index(rows):
        for idx, row in enumerate(rows):
            if any(cell and str(cell).strip() in COLUNAS_ESPERADAS['CODIGO'] for cell in row):
                return idx
        return None
    linha_cabecalho_idx = _find_header_row_index(linhas)
    if linha_cabecalho_idx is None:
        print("Linha de cabeçalho não encontrada (esperava 'Código' em alguma célula).")
        print("Primeiras linhas da planilha:")
        for i, row in enumerate(linhas[:6]):
            print(f"  Linha {i+1}: {[str(c or '') for c in row]}")
        return []

    cabecalho = [str(c or '').strip() for c in linhas[linha_cabecalho_idx]]

    col_codigo = encontrar_coluna(cabecalho, COLUNAS_ESPERADAS['CODIGO'])
    col_descricao = encontrar_coluna(cabecalho, COLUNAS_ESPERADAS['DESCRICAO'])
    col_desc_concat = encontrar_coluna(cabecalho, COLUNAS_ESPERADAS['DESCRICAO_CONCAT'])

    if col_codigo is None:
        print(f"Coluna 'Código' não encontrada no cabeçalho: {cabecalho}")
        return []
    if col_descricao is None:
        print(f"Coluna 'Descrição' não encontrada no cabeçalho: {cabecalho}")
        return []

    dados = []
    for row in linhas[linha_cabecalho_idx + 1:]:
        codigo = str(row[col_codigo] or '').strip()
        descricao = str(row[col_descricao] or '').strip()
        desc_concat = str(row[col_desc_concat] or '').strip() if col_desc_concat is not None else ''

        if not codigo:
            continue

        codigo_limpo = codigo.replace('.', '').replace('-', '').replace('/', '').strip()

        if len(codigo_limpo) != 8 or not codigo_limpo.isdigit():
            continue

        item = {
            'codigo': codigo_limpo,
            'descricao': descricao,
        }
        if desc_concat:
            item['desc_concat'] = desc_concat
        dados.append(item)

    return dados


def main():
    if len(sys.argv) < 2:
        print("Uso: python import_ncm_planilha.py <caminho_da_planilha.xlsx> [aba]")
        print("Exemplo: python import_ncm_planilha.py Tabela_NCM.xlsx")
        print("         python import_ncm_planilha.py Tabela_NCM.xlsx Planilha1")
        sys.exit(1)

    caminho = sys.argv[1]
    aba = sys.argv[2] if len(sys.argv) > 2 else None

    if not os.path.exists(caminho):
        print(f"Arquivo não encontrado: {caminho}")
        sys.exit(1)

    print(f"Lendo planilha: {caminho}")
    if aba:
        print(f"Aba: {aba}")

    dados = ler_planilha_ncm(caminho, aba)

    if not dados:
        print("Nenhum NCM válido encontrado na planilha.")
        print("Verifique se as colunas 'Código' e 'Descrição' existem no cabeçalho.")
        sys.exit(1)

    saida = 'ncm_governo.json'
    with open(saida, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

    print(f"\n{len(dados)} NCMs exportados para {saida}")
    print("Pronto! Agora inclua este JSON no compilador e na tela de Visão Gerencial.")


if __name__ == '__main__':
    main()

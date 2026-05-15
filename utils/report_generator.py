import csv
import os
from typing import List, Dict, Any

def generate_audit_report(resultados: List[Dict[str, Any]], output_path: str) -> str:
    """Gera um relatório CSV de auditoria da importação/validação."""
    colunas = [
        'CHAVE_NFE', 'C_PROD_XML', 'X_PROD_XML', 'NCM_XML', 'CFOP', 'UF_DEST',
        'ICMS_CST', 'P_ICMS', 'P_RED_BC', 'C_BENEF', 'PIS_CST', 'COFINS_CST',
        'C_CLASS_TRIB', 'IBSCBS_CST', 'P_IBS_UF', 'P_CBS',
        'STATUS', 'SCORE_MATCH', 'AUTO_APPROVE',
        'ERP_CODIGO', 'ERP_DESCRICAO', 'ERP_NCM', 'ERP_UNIDADE',
        'DIVERGENCIAS'
    ]

    totais = {'TOTAL': len(resultados), 'VALIDADO': 0, 'DIVERGENTE': 0, 'NAO_ENCONTRADO': 0}

    # Garante que o diretório de saída exista antes de salvar o arquivo
    if os.path.dirname(output_path):
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(colunas)

        for r in resultados:
            xml = r.get('xml', {})
            val = r.get('validacao')
            if not val: 
                continue
            
            erp = val.erp_match or {}
            status = val.status
            
            if status in totais:
                totais[status] += 1

            writer.writerow([
                xml.get('chave_nfe', ''),
                xml.get('c_prod', ''),
                xml.get('x_prod', ''),
                xml.get('ncm', ''),
                xml.get('cfop', ''),
                xml.get('uf_dest', ''),
                xml.get('icms_cst', ''),
                str(xml.get('p_icms', '')).replace('.', ','),
                str(xml.get('p_red_bc', '')).replace('.', ','),
                xml.get('c_benef', ''),
                xml.get('pis_cst', ''),
                xml.get('cofins_cst', ''),
                xml.get('c_class_trib', ''),
                xml.get('ibscbs_cst', ''),
                str(xml.get('p_ibs_uf', '')).replace('.', ','),
                str(xml.get('p_cbs', '')).replace('.', ','),
                status,
                val.score,
                'SIM' if val.auto_approve else 'NAO',
                erp.get('produto_codigo', ''),
                erp.get('produto_descricao', ''),
                erp.get('produto_class_fiscal', ''),
                erp.get('produto_unidade_cv', ''),
                " | ".join(val.divergencias)
            ])
            
        # Linhas de resumo no rodapé
        writer.writerow([])
        writer.writerow(['RESUMO GERAL'])
        writer.writerow(['TOTAL PROCESSADO', totais['TOTAL']])
        writer.writerow(['VALIDADOS', totais['VALIDADO']])
        writer.writerow(['DIVERGENTES', totais['DIVERGENTE']])
        writer.writerow(['NAO ENCONTRADOS', totais['NAO_ENCONTRADO']])

    return output_path

def generate_summary_report(resultados: List[Dict[str, Any]]) -> str:
    """Gera um resumo em texto formatado para exibição no terminal."""
    totais = {'VALIDADO': 0, 'DIVERGENTE': 0, 'NAO_ENCONTRADO': 0}
    for r in resultados:
        if r.get('validacao'):
            status = r['validacao'].status
            totais[status] = totais.get(status, 0) + 1
            
    return (
        "========================================\n"
        "      RESUMO DA VALIDAÇÃO FISCAL        \n"
        "========================================\n"
        f" Total Processado:  {len(resultados)}\n"
        f" Validados (Match): {totais.get('VALIDADO', 0)}\n"
        f" Divergentes:       {totais.get('DIVERGENTE', 0)}\n"
        f" Não Encontrados:   {totais.get('NAO_ENCONTRADO', 0)}\n"
        "========================================"
    )

def export_novos_produtos(resultados: List[Dict[str, Any]], output_path: str) -> str:
    """Exporta os produtos não encontrados com colunas vazias para preenchimento manual (Revisão)."""
    colunas = [
        'C_PROD_XML', 'X_PROD_XML', 'NCM_XML', 'CEAN_XML', 'UNIDADE_XML',
        'GRUPO', 'SUBGRUPO', 'FAIXA_ICMS', 'FAIXA_RT'
    ]
    
    novos = [r for r in resultados if r.get('validacao') and r['validacao'].status == 'NAO_ENCONTRADO']
    
    # Garante que o diretório de saída exista antes de salvar o arquivo
    if os.path.dirname(output_path):
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(colunas)
        
        for r in novos:
            xml = r.get('xml', {})
            writer.writerow([
                xml.get('c_prod', ''),
                xml.get('x_prod', ''),
                xml.get('ncm', ''),
                xml.get('c_ean', ''),
                xml.get('u_com', ''),
                '', # GRUPO
                '', # SUBGRUPO
                '', # FAIXA_ICMS
                ''  # FAIXA_RT
            ])
            
    return output_path

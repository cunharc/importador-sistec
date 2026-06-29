import argparse
import logging
import csv
import sys
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from utils.firebird_service import FirebirdService
from utils.xml_reader import parse_nfe_folder
from utils.match_engine import get_best_match
from utils.validator import ValidatorFiscal
from utils.transformer import DataTransformer
from utils.importer import FirebirdImporter

def setup_logging(level):
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def load_erp_data(fb: FirebirdService, emp: int, fil: int):
    logging.info("Carregando dados do ERP em paralelo...")
    data = {}
    
    def fetch_produtos():
        return fb.query("SELECT * FROM TABELA_PRODUTO WHERE PRODUTO_EMPRESA=? AND PRODUTO_FILIAL=?", [emp, fil])
        
    def fetch_icms():
        return fb.query("SELECT * FROM TABELA_ALIQUOTA_ICMS WHERE AICMS_EMPRESA=? AND AICMS_FILIAL=?", [emp, fil])
        
    def fetch_cfops():
        return fb.query("SELECT NAT_CODIGO FROM TABELA_NAT_OPERACAO_SAIDA WHERE NAT_EMPRESA=? AND NAT_FILIAL=?", [emp, fil])
        
    def fetch_rt():
        try:
            return fb.query("SELECT * FROM TABELA_RT_CONFIG_2025_2026")
        except Exception:
            return [] # Ignora se a tabela não existir ainda

    with ThreadPoolExecutor(max_workers=4) as executor:
        fut_prod = executor.submit(fetch_produtos)
        fut_icms = executor.submit(fetch_icms)
        fut_cfops = executor.submit(fetch_cfops)
        fut_rt = executor.submit(fetch_rt)
        
        data['produtos'] = fut_prod.result()
        data['regras_icms'] = fut_icms.result()
        data['cfops'] = fut_cfops.result()
        data['regras_rt'] = fut_rt.result()
        data['classes_trib'] = [] # Mock, se necessário
        
    logging.info(f"Dados carregados: {len(data['produtos'])} produtos, {len(data['regras_icms'])} regras ICMS.")
    return data

def gerar_relatorio_csv(resultados, filepath):
    if not resultados:
        return
    colunas = [
        'chave_nfe', 'c_prod', 'x_prod', 'ncm', 'cfop', 
        'icms_cst', 'pis_cst', 'cofins_cst', 'status', 'score',
        'divergencias', 'erp_codigo', 'erp_descricao'
    ]
    
    with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow([c.upper() for c in colunas])
        for r in resultados:
            xml = r['xml']
            val = r['validacao']
            erp = val.erp_match or {}
            
            writer.writerow([
                xml.get('chave_nfe', ''),
                xml.get('c_prod', ''),
                xml.get('x_prod', ''),
                xml.get('ncm', ''),
                xml.get('cfop', ''),
                xml.get('icms_cst', ''),
                xml.get('pis_cst', ''),
                xml.get('cofins_cst', ''),
                val.status,
                val.score,
                " | ".join(val.divergencias),
                erp.get('produto_codigo', ''),
                erp.get('produto_descricao', '')
            ])
    logging.info(f"Relatório gerado: {filepath}")

def main():
    parser = argparse.ArgumentParser(description="Orquestrador de Importação de XML NF-e")
    parser.add_argument('--xml-dir', required=True, help="Diretório com os arquivos XML")
    parser.add_argument('--db-path', required=True, help="Caminho do banco Firebird")
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=3050)
    parser.add_argument('--user', default='SYSDBA')
    parser.add_argument('--passw', default='masterkey')
    parser.add_argument('--empresa', type=int, default=1)
    parser.add_argument('--filial', type=int, default=1)
    parser.add_argument('--mode', choices=['validar', 'importar-produtos', 'tudo'], default='validar')
    parser.add_argument('--log-level', default='INFO')
    parser.add_argument('--dry-run', action='store_true', help="Não comita transações no banco")
    
    args = parser.parse_args()
    setup_logging(args.log_level)
    
    config_fb = {
        'host': args.host, 'port': args.port, 'database': args.db_path,
        'user': args.user, 'password': args.passw
    }
    
    logging.info(f"Iniciando modo: {args.mode.upper()} {'(DRY RUN)' if args.dry_run else ''}")
    
    try:
        with FirebirdService(config_fb) as fb:
            erp_data = load_erp_data(fb, args.empresa, args.filial)
            
            validator = ValidatorFiscal(
                erp_data['produtos'], erp_data['regras_icms'], 
                erp_data['regras_rt'], erp_data['cfops'], erp_data['classes_trib']
            )
            
            logging.info(f"Lendo XMLs de: {args.xml_dir}")
            itens_xml = parse_nfe_folder(args.xml_dir)
            logging.info(f"Total de itens extraídos: {len(itens_xml)}")
            
            resultados = []
            novos_produtos = []
            existentes_codigos = set([str(p.get('produto_codigo', '')) for p in erp_data['produtos']])
            
            for item in itens_xml:
                uf_dest = item.get('uf_dest', 'SP')
                val_result = validator.validate(item, uf_dest)
                
                resultados.append({'xml': item, 'validacao': val_result})
                
                if val_result.status == 'NAO_ENCONTRADO' and args.mode in ['importar-produtos', 'tudo']:
                    config_prod = {'empresa': args.empresa, 'filial': args.filial}
                    novo_dict = DataTransformer.prepare_produto(item, config_prod, {})
                    codigo_final, cod_aux = DataTransformer.prepare_codigo_produto(item.get('c_prod', ''), existentes_codigos)
                    novo_dict['PRODUTO_CODIGO'] = codigo_final
                    novo_dict['PRODUTO_COD_AUXILIAR'] = cod_aux
                    existentes_codigos.add(codigo_final)
                    novos_produtos.append(novo_dict)

            agrupamento = {'VALIDADO': 0, 'DIVERGENTE': 0, 'NAO_ENCONTRADO': 0}
            for r in resultados:
                agrupamento[r['validacao'].status] += 1
                
            logging.info(f"Resumo da Validação:")
            logging.info(f" - Validados (Match perfeito): {agrupamento['VALIDADO']}")
            logging.info(f" - Divergentes (Match com avisos): {agrupamento['DIVERGENTE']}")
            logging.info(f" - Não Encontrados (Novos): {agrupamento['NAO_ENCONTRADO']}")
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            gerar_relatorio_csv(resultados, f"relatorio_auditoria_{timestamp}.csv")
            
            if novos_produtos and not args.dry_run:
                logging.info(f"Iniciando importação de {len(novos_produtos)} novos produtos...")
                importer = FirebirdImporter(fb)
                res_imp = importer.import_produtos(novos_produtos)
                logging.info(f"Produtos inseridos: {res_imp['inseridos']}. Erros: {len(res_imp['erros'])}")
            elif novos_produtos and args.dry_run:
                logging.info("DRY RUN: Importação pulada.")
                
    except KeyboardInterrupt:
        logging.warning("Processo cancelado pelo usuário (Ctrl+C).")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Erro fatal: {e}")
        sys.exit(1)
        
    logging.info("Processo concluído.")

if __name__ == '__main__':
    main()
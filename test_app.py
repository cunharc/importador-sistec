import os
import locale
import configparser

# Patch para compatibilidade com Python 3.13+
if not hasattr(locale, 'resetlocale'):
    locale.resetlocale = lambda: locale.setlocale(locale.LC_ALL, "")

from utils.firebird_service import FirebirdService
from utils.xml_reader import ler_nfe, parse_nfe
from utils.validator import ValidatorFiscal
from utils.report_generator import generate_summary_report

def carregar_config():
    config = configparser.ConfigParser()
    config.read('config.ini', encoding='utf-8')
    return config

def main():
    print("=== INICIANDO TESTE DO SISTEMA ===")
    config = carregar_config()
    
    # 1. TESTAR CONEXÃO COM O BANCO DE DADOS
    print("\n1. Testando conexão com Firebird...")
    fb_config = dict(config['FIREBIRD']) if 'FIREBIRD' in config else {}
    try:
        fb_service = FirebirdService(fb_config)
        fb_service.connect()
        print("   -> Conexão estabelecida com sucesso!")
    except Exception as e:
        print(f"   -> ERRO DE CONEXÃO: {e}")
        return

    # 2. TESTAR LEITURA DE XML
    print("\n2. Testando leitura de XML...")
    caminho_xml = "NFe_exemplo.xml" # COLOQUE UM XML VÁLIDO NESTA PASTA PARA TESTAR
    
    if not os.path.exists(caminho_xml):
        print(f"   -> Arquivo XML não encontrado: {caminho_xml}")
        print("   -> Adicione um XML real para testar a extração.")
        return

    dados_nfe = parse_nfe(caminho_xml)
    itens = dados_nfe.get('itens', [])
    print(f"   -> Produtos encontrados na NFe: {len(itens)}")
    
    if not itens:
        return

    # 3. TESTAR VALIDADOR
    print("\n3. Testando o ValidatorFiscal...")
    
    erp_produtos_mock = [
        {
            'produto_codigo': '1001', 
            'produto_cbarra': itens[0].get('c_ean', '123'), 
            'produto_class_fiscal': itens[0].get('ncm', '123'),
            'produto_descricao': itens[0].get('x_prod', 'PRODUTO TESTE'),
            'produto_unidade_cv': itens[0].get('u_com', 'UN')
        }
    ]
    
    validator = ValidatorFiscal(erp_produtos=erp_produtos_mock, regras_icms=[], regras_rt=[], cfops_erp=[], classes_trib=[])
    resultados_auditoria = []
    
    for item in itens:
        validacao = validator.validate(item, uf_dest='SP')
        resultados_auditoria.append({'xml': item, 'validacao': validacao})
        print(f"   -> Item '{item.get('x_prod')[:20]}...' -> Status: {validacao.status} (Score: {validacao.score})")

    # 4. TESTAR RELATÓRIO
    print("\n4. Testando Geração de Resumo...")
    print(generate_summary_report(resultados_auditoria))
    
    fb_service.detach()

if __name__ == "__main__":
    main()
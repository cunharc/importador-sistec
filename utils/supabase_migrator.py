import os
import json
import argparse
from typing import Dict, Any

try:
    from supabase import create_client, Client
except ImportError:
    print("A biblioteca 'supabase' não foi encontrada.")
    print("Por favor, instale executando: pip install supabase")
    Client = Any

def get_supabase_client(url: str, key: str) -> Client:
    """Cria e retorna o cliente do Supabase."""
    return create_client(url, key)

def export_historico_xml(supabase_url: str, supabase_key: str, output_dir: str) -> int:
    """
    Exporta a tabela historico_xml em páginas de 1000 registros,
    salvando múltiplos arquivos JSON para não sobrecarregar a memória.
    """
    supabase = get_supabase_client(supabase_url, supabase_key)
    page_size = 1000
    start = 0
    total_exported = 0
    page_num = 1
    
    os.makedirs(output_dir, exist_ok=True)
    print("\nIniciando exportação de historico_xml...")
    
    while True:
        response = supabase.table('historico_xml').select('*').range(start, start + page_size - 1).execute()
        data = response.data
        
        if not data:
            break
            
        file_path = os.path.join(output_dir, f'historico_xml_page_{page_num}.json')
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        total_exported += len(data)
        start += page_size
        print(f"Página {page_num} salva. Total parcial: {total_exported} registros.")
        page_num += 1
        
        if len(data) < page_size:
            break
            
    return total_exported

def export_ncm_governo(supabase_url: str, supabase_key: str, output_dir: str) -> int:
    """
    Exporta a tabela ncm_governo e salva em um único arquivo JSON unificado.
    """
    supabase = get_supabase_client(supabase_url, supabase_key)
    page_size = 1000
    start = 0
    all_data = []
    
    os.makedirs(output_dir, exist_ok=True)
    print("\nIniciando exportação de ncm_governo...")
    
    while True:
        response = supabase.table('ncm_governo').select('*').range(start, start + page_size - 1).execute()
        data = response.data
        
        if not data:
            break
            
        all_data.extend(data)
        start += page_size
        print(f"Buscando NCMs... {len(all_data)} encontrados até agora.")
        
        if len(data) < page_size:
            break
            
    file_path = os.path.join(output_dir, 'ncm_governo.json')
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
        
    return len(all_data)

def export_cfop_governo(supabase_url: str, supabase_key: str, output_dir: str) -> int:
    """
    Exporta a tabela cfop_governo e salva em um único arquivo JSON unificado.
    """
    supabase = get_supabase_client(supabase_url, supabase_key)
    page_size = 1000
    start = 0
    all_data = []
    
    os.makedirs(output_dir, exist_ok=True)
    print("\nIniciando exportação de cfop_governo...")
    
    while True:
        response = supabase.table('cfop_governo').select('*').range(start, start + page_size - 1).execute()
        data = response.data
        
        if not data:
            break
            
        all_data.extend(data)
        start += page_size
        print(f"Buscando CFOPs... {len(all_data)} encontrados até agora.")
        
        if len(data) < page_size:
            break
            
    file_path = os.path.join(output_dir, 'cfop_governo.json')
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
        
    return len(all_data)

def import_ncm_from_json(json_path: str) -> Dict[str, Dict[str, Any]]:
    """Carrega o JSON de NCM em memória indexado para busca O(1)."""
    if not os.path.exists(json_path):
        return {}
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return {str(row.get('codigo', '')): row for row in data if row.get('codigo')}

def import_cfop_from_json(json_path: str) -> Dict[str, Dict[str, Any]]:
    """Carrega o JSON de CFOP em memória indexado para busca O(1)."""
    if not os.path.exists(json_path):
        return {}
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return {str(row.get('cfop') or row.get('codigo', '')): row for row in data if (row.get('cfop') or row.get('codigo'))}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Script para migração one-shot do Supabase para JSON local.")
    parser.add_argument('--url', required=True, help="URL da sua instância Supabase")
    parser.add_argument('--key', required=True, help="Chave pública (anon-key) do Supabase")
    parser.add_argument('--output-dir', required=True, help="Pasta de destino para os arquivos JSON")
    args = parser.parse_args()
    
    total_cfop = export_cfop_governo(args.url, args.key, args.output_dir)
    total_ncm = export_ncm_governo(args.url, args.key, args.output_dir)
    total_hist = export_historico_xml(args.url, args.key, args.output_dir)
    
    print(f"\n=== RESUMO DA MIGRAÇÃO ===")
    print(f"CFOPs Exportados:     {total_cfop}")
    print(f"NCMs Exportados:      {total_ncm}")
    print(f"Históricos em Páginas:{total_hist}")
    print(f"==========================")
    print(f"Migração concluída com sucesso! Os arquivos estão em: {os.path.abspath(args.output_dir)}")
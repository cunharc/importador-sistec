import unicodedata

def remover_acentos(texto: str) -> str:
    if not texto:
        return ""
    # Normaliza a string separando os caracteres base dos acentos
    texto_normalizado = unicodedata.normalize('NFD', str(texto))
    return texto_normalizado.encode('ascii', 'ignore').decode('utf-8')

def limpar_codigo_conta(codigo_conta: str) -> str:
    if not codigo_conta:
        return codigo_conta
    partes = str(codigo_conta).strip().split('.')
    # Remove de trás para frente os segmentos que contêm apenas zeros (ex: 1.0.00 -> 1)
    while len(partes) > 1 and partes[-1].replace('0', '') == '':
        partes.pop()
    return '.'.join(partes)

def calcular_nivel(codigo_conta: str) -> int:
    return codigo_conta.strip().count('.') + 1

def calcular_reduzido(codigo_conta: str, nivel_maximo_sintetico: int):
    nivel = calcular_nivel(codigo_conta)
    if nivel > nivel_maximo_sintetico:
        ultimo_segmento = codigo_conta.strip().split('.')[-1]
        try:
            return int(ultimo_segmento)
        except ValueError:
            return None
    return None

def calcular_natureza(codigo_conta: str) -> int:
    primeiro = codigo_conta.strip()[0]
    if primeiro == '1':
        return 1
    elif primeiro == '2':
        return 2
    elif primeiro in ('3', '4'):
        return 4
    elif primeiro in ('5', '6'):
        return 5
    else:
        return 0

def processar_planilha(linhas_excel: list, empresa: int, filial: int,
                        exercicio: int, codigo_inicial: int,
                        nivel_maximo_sintetico: int = 4) -> list:
    """Transforma as linhas lidas do Excel em registros prontos para o banco."""
    registros = []
    codigo_atual = codigo_inicial
    
    for linha in linhas_excel:
        conta = linha['conta']
        descricao = linha['descricao']
        
        # Remove acentos e caracteres especiais da descrição (ex: ÇÃO -> CAO)
        descricao = remover_acentos(descricao)

        # Aplica a limpeza dos zeros à direita na conta
        conta = limpar_codigo_conta(conta)
        
        # Garantir que o 4º nível tenha sempre 2 dígitos (ex: 1.1.1.1 -> 1.1.1.01)
        partes = conta.split('.')
        if len(partes) >= 4:
            partes[3] = partes[3].zfill(2)
            conta = '.'.join(partes)
        
        nivel = calcular_nivel(conta)
        reduzido = calcular_reduzido(conta, nivel_maximo_sintetico)
        natureza = calcular_natureza(conta)
        
        registro = {
            'PLANO_EMPRESA': empresa,
            'PLANO_FILIAL': filial,
            'PLANO_EXERCICIO': exercicio,
            'PLANO_CODIGO': codigo_atual,
            'PLANO_CONTA': conta,
            'PLANO_REDUZIDO': reduzido,
            'PLANO_INDICE': reduzido,
            'PLANO_NIVEL': nivel,
            'PLANO_DESCRICAO': descricao[:60],
            'PLANO_ATIVO': 'S',
            'PLANO_COD_NATUREZA': natureza,
            'PLANO_COD_EXTERNO': conta,
            'PLANO_CONTA_EXERCICIO_ANT': conta,
            'PLANO_CONTA_IMPORT': conta,
            'STATUS': 'OK',
            'OBSERVACAO': ''
        }
        
        registros.append(registro)
        codigo_atual += 1
    
    # --- NOVO TRATAMENTO PARA REDUZIDOS: SEQUENCIAL PURO ---
    sequencial_reduzido = 1
    
    for reg in registros:
        if reg.get('PLANO_REDUZIDO') is not None:
            novo_reduzido = sequencial_reduzido
            
            reg['PLANO_REDUZIDO'] = novo_reduzido
            reg['PLANO_INDICE'] = novo_reduzido
            
            # Atualiza a estrutura da conta analítica para bater com o reduzido final
            conta_original = reg['PLANO_CONTA']
            partes = conta_original.split('.')
            
            # Substitui o final pelo reduzido formatado (sem zeros à esquerda)
            partes[-1] = str(novo_reduzido)
            nova_conta = '.'.join(partes)
            
            if nova_conta != conta_original:
                reg['PLANO_CONTA'] = nova_conta
                
                obs_atual = reg.get('OBSERVACAO', '')
                if obs_atual:
                    reg['OBSERVACAO'] = f"{obs_atual} Conta ajustada de {conta_original} para {nova_conta}."
                else:
                    reg['OBSERVACAO'] = f"Conta ajustada de {conta_original} para {nova_conta} (Reduzido sequencial)."
            
            sequencial_reduzido += 1

    return registros

def validar_registros(registros: list, contas_existentes: set) -> list:
    """Valida os registros e marca status: OK, DUPLICADA, ERRO."""
    for reg in registros:
        if reg['PLANO_CONTA'] in contas_existentes:
            reg['STATUS'] = 'DUPLICADA'
            reg['OBSERVACAO'] = 'Conta já existe no banco'
        elif not reg['PLANO_CONTA']:
            reg['STATUS'] = 'ERRO'
            reg['OBSERVACAO'] = 'Código de conta vazio'
        elif not reg['PLANO_DESCRICAO']:
            reg['STATUS'] = 'ERRO'
            reg['OBSERVACAO'] = 'Descrição vazia'
    return registros

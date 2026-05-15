# Skill: Classificação e Validação de NCM

## Contexto do Projeto
Sistema de importação/tributação para ERP Firebird (Sistec). Trabalha com XMLs de NFe.

## Regras de Negócio para NCM (Atualizado 2026-04-15)

### 1. COLUNAS DA GRADE DE NCM (tela_ncm.py)
```
SEL, QTD, NCM, STATUS, DESCRIÇÃO, UF, CFOP, TIPO,
CBENEF, COD.CRED, PCT.CRED,
CST ICMS, ICMS% XML, RED.BC%, FCP%,
CST PIS, PIS% XML, PIS% ERP,
CST COF, COF% XML, COF% ERP,
FAIXA ICMS, FAIXA ERP
```

### 2. CAMPOS DOBANCO (TABELA_class_fiscal)

#### OBRIGATÓRIOS:
- CFIS_EMPRESA
- CFIS_FILIAL
- CFIS_CODIGO (NCM formatado: XXXX.XX.XX)
- CFIS_DESCRICAO

#### OPCIONAIS (pode ficar no PRODUTO):
- CFIS_ICMS_VENDA (Faixa ICMS)
- CFIS_PIS (% PIS)
- CFIS_COFINS (% COFINS)
- CFIS_CST_PIS
- CFIS_CST_COFINS

### 3. DADOS DO XML (xml_reader.py)
```python
grupo = {
    'ncm': '12345678',
    'descricao': 'PRODUTO...',
    'uf_dest': 'SP',
    'cfop': '5102',
    'tipo_cliente': 'CT',
    'c_benef': 'SEM_GF',
    'c_cred': '123',
    'p_cred': 7.0,
    'icms_cst': '00',
    'p_icms': 18.0,
    'pis_cst': '01',
    'pis_alq': 1.65,
    'cofins_cst': '01',
    'cofins_alq': 7.6,
}
```

### 4. LÓGICA DE BUSCA DE FAIXA
```python
def _buscar_faixa_para_ncm(grupo):
    # Busca em TABELA_ALIQUOTA_ICMS usando:
    # - UF destino
    # - cBenef (CONT/NCONT/SIMP_NAC)
    # - gCred (código + %)
    # - CST ICMS
    # - % ICMS
    # Retorna código da faixa ou None
```

### 5. TABELAS ENVOLVIDAS
- `TABELA_ALIQUOTA_ICMS` - Faixas de ICMS
- `TABELA_ALIQUOTA_ICMS_CBENEF` - Relacionamento faixas x cbenef
- `TABELA_CBENEF` - Cadastro de benefícios fiscais
- `TABELA_class_fiscal` - Classificação fiscal de NCMs
- `TABELA_NCM` - Cadastro de NCMs do governo

## Funcionalidades

### Grade Principal
- Mostra NCM + todos os dados fiscais
- Coluna "FAIXA ICMS" = sugestão baseada no banco
- Coluna "FAIXA ERP" = valor atual no banco
- Status: NOVO / DIFERENTE / OK

### Editor em Lote
- Selecionar múltiplos NCMs
- Ver todos os dados (XML + ERP)
- Copiar Faixa ERP/XML → NOVO
- Copiar PIS/COFINS ERP → NOVO
- Editar Faixa, PIS, COFINS
- Salvar mesmo sem tributação (só classificação)

### Regras de Salvamento
- Sempre salva: Empresa, Filial, Código, Descrição
- Opcional: Faixa ICMS, PIS, COFINS
- Tributação pode ficar no PRODUTO se preferir

## Histórico

### 2026-04-15 - Revisão com Rafael
1. xml_reader.py extrai c_cred e p_cred
2. Grade mostra cBenef, gCred, PIS/COFINS completos
3. Lógica de busca de faixa igual à tela ICMS
4. CST formatado para 2 dígitos
5. Clique na coluna SEL funciona
6. "Editar em Lote" com 1+ itens
7. Campos obrigatórios: só empresa, filial, código, descrição
8. Tributação opcional (pode ficar no PRODUTO)

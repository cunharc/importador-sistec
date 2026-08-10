# DOCUMENTAÇÃO: Fluxo de Dados do NCM

## 1. CAMPOS EXTRAÍDOS DO XML (xml_reader.py)

```python
item_xml = {
    # Identificação do produto
    'ncm': '12345678',              # NCM do produto
    'x_prod': 'Nome do Produto',    # Descrição
    
    # Operação
    'cfop': '5102',                 # CFOP
    'uf_emit': 'SP',               # UF Emitente
    'uf_dest': 'SP',               # UF Destino
    'tipo_cliente': 'CT',          # CT=Contribuinte, NC=Não Contribuinte
    
    # === REFORMA TRIBUTÁRIA (para buscar FAIXA) ===
    'c_benef': 'SEM_GF',           # Código Benefício Fiscal (no prod)
    'c_cred': '123',               # Código Crédito Presumido (no gCred)
    'p_cred': 7.0,                 # % Crédito Presumido (no gCred)
    'v_cred': 100.00,             # Valor Crédito Presumido
    'cred_presumidos': [           # Lista de todos os gCred
        {'c_cred': '123', 'p_cred': 7.0, 'v_cred': 100.00}
    ],
    
    # === ICMS ===
    'icms_cst': '000',             # CST ICMS com 3 dígitos: orig + CST (CSOSN vai como está)
    'p_icms': 18.0,                # % ICMS
    'p_red_bc': 0.0,              # % Redução Base de Cálculo
    'p_fcp': 0.0,                 # % FCP
    'p_mvast': 0.0,               # % MVA ST
    'p_icmsst': 0.0,              # % ICMS ST
    
    # === PIS ===
    'pis_cst': '01',               # CST PIS
    'p_pis': 1.65,                # % PIS
    
    # === COFINS ===
    'cofins_cst': '01',           # CST COFINS
    'p_cofins': 7.6,              # % COFINS
}
```

## 2. COLUNAS DA GRADE PRINCIPAL (tela_ncm.py)

```
| SEL | QTD | NCM      | STATUS  | DESCRIÇÃO | UF | CFOP | TIPO | CBENEF | COD.CRED | PCT.CRED | CST ICMS | ICMS% | RED.BC% | FCP% | CST PIS | PIS% XML | PIS% ERP | CST COF | COF% XML | COF% ERP | FAIXA ICMS | FAIXA ERP |
```

### CBENEF, COD.CRED, PCT.CRED são usados APENAS para buscar a FAIXA ICMS - NÃO são salvos no NCM.

## 3. TABELA_CLASS_FISCAL (Banco de Dados)

```sql
TABELA_class_fiscal
├── CFIS_EMPRESA         -- OBRIGATÓRIO
├── CFIS_FILIAL          -- OBRIGATÓRIO
├── CFIS_CODIGO          -- OBRIGATÓRIO (NCM formatado: 1234.56.78)
├── CFIS_DESCRICAO       -- OBRIGATÓRIO (descrição do NCM)
├── CFIS_ICMS_VENDA      -- OPCIONAL (Faixa ICMS - pode ficar no PRODUTO)
├── CFIS_PIS             -- OPCIONAL (% PIS - pode ficar no PRODUTO)
├── CFIS_COFINS          -- OPCIONAL (% COFINS - pode ficar no PRODUTO)
├── CFIS_CST_PIS         -- OPCIONAL (CST PIS)
├── CFIS_CST_COFINS      -- OPCIONAL (CST COFINS)
├── CFIS_IPI             -- OPCIONAL
└── CFIS_CST_IPI         -- OPCIONAL
```

## 4. REGRAS DE SALVAMENTO

### Obrigatórios:
- CFIS_EMPRESA
- CFIS_FILIAL
- CFIS_CODIGO (NCM)
- CFIS_DESCRICAO

### Opcionais (pode ficar no PRODUTO):
- CFIS_ICMS_VENDA (Faixa ICMS)
- CFIS_PIS (% PIS)
- CFIS_COFINS (% COFINS)
- CFIS_CST_PIS
- CFIS_CST_COFINS

## 5. LÓGICA DE BUSCA DE FAIXA ICMS

```
XML Item                          TABELA_ALIQUOTA_ICMS
─────────────────────────────────────────────────────
uf_dest                          → AICMS_ESTADO
tipo_cliente (CT/NC)             → AICMS_SITUACAO_CONT/NCONT
icms_cst                         → AICMS_SITUACAO_CONT/NCONT
p_icms                           → AICMS_ALIQUOTA_CONT/NCONT
c_benef                          → AICMS_CBENEF_CONT/NCONT/SIMP_NAC
c_cred + p_cred                 → TABELA_CBENEF (via junção)
                                    CBE_C_CREDPRESUMIDO + CBE_P_CREDPRESUMIDO
─────────────────────────────────────────────────────
Resultado: AICMS_FAIXA (código da faixa)
```

## 6. QUANDO USAR NCM vs PRODUTO

### Salvar no NCM (TABELA_class_fiscal):
- Classificação fiscal padrão do produto
- Faixa ICMS padrão para todas as vendas
- PIS/COFINS padrão quando não varia por produto

### Salvar no PRODUTO (TABELA_produto):
- Tributação específica daquele produto
- Variação por CFOP ou UF
- Quando o mesmo NCM tem tributação diferente por produto

## 7. FLUXO ATUALIZADO

```
1. Lê XML → extrai dados do produto
2. Agrupa por NCM + UF + CFOP + tipo cliente
3. Busca FAIXA ICMS no banco usando cbenef + gcred
4. Mostra na grade: NCM, CBENEF, GCRED, ICMS, PIS, COFINS, FAIXA
5. Usuário edita via modal (opcional)
6. Salva no banco:
   - Se NCM novo: INSERT com campos obrigatórios + opcionais
   - Se NCM existe: UPDATE campos alterados
```

## 8. EDITOR EM LOTE (Modal)

O modal permite:
- Ver todos os dados do XML e do ERP
- Copiar Faixa ERP → NOVO
- Copiar Faixa XML → NOVO
- Copiar PIS/COFINS ERP → NOVO
- Editar Faixa, PIS, COFINS manualmente
- Salvar mesmo sem tributação (só classificação)

### Confirmação mostra:
```
Salvar 5 NCM(s)?

TABELA: TABELA_class_fiscal
OBRIGATÓRIOS: Empresa, Filial, Código, Descrição
OPCIONAIS: Faixa ICMS, PIS, COFINS

• 12345678 - Produto A      | Faixa=5, PIS=1.65
• 98765432 - Produto B      (só classificação)
• 55555555 - Produto C      | Faixa=3

Tributação opcional = pode ficar no PRODUTO, não precisa no NCM.
```

# VERSÃO DO SISTEMA

```
┌─────────────────────────────────────────────────────────────┐
│                   IMPORTADOR SISTEC                        │
│                      VERSÃO 4.1                            │
│                   Data: 29/06/2026                         │
└─────────────────────────────────────────────────────────────┘
```

## MÓDULOS POR VERSÃO

### ✅ VERSÃO 4.1 - RELEASE ATUAL (29/06/2026)
| Módulo                     | Status    | Descrição                                    |
|----------------------------|-----------|----------------------------------------------|
| Plano de Contas            | ✅ PRONTO | Importação de plano de contas                |
| NCM                        | 🔧 AJUSTES| Classificação fiscal de NCMs                 |
| Clientes NF-e              | ✅ PRONTO | Importação de clientes/fornecedores via XML NF-e |
| CFOP                       | ✅ PRONTO | Parametrização de CFOPs                      |
| ICMS                       | ✅ PRONTO | Matriz de faixas ICMS                        |
| Importação XML             | 🔧 AJUSTES| Importação genérica de XML                   |
| Produtos                   | 🔧 AJUSTES| Cadastro de produtos via XML/planilha        |
| Reforma Tributária         | 🔧 AJUSTES| CBS/IBS substituição                         |
| Busca de Logs              | ✅ PRONTO | Busca avançada em logs ERP                   |
| Importação Clientes        | ✅ PRONTO | Importação de clientes via planilha          |
| Importação Receber/Pagar   | ✅ PRONTO | Importação de contas a receber/pagar        |
| Importação Lista Preços    | 🔧 AJUSTES| Importação de lista de preços via planilha   |
| Importação Tributação      | 🔧 AJUSTES| Importação de tributação NCM via planilha (ICMS, PIS, COFINS, RT) |
| Lista de Preços XML        | ✅ PRONTO | Criação de lista de preços a partir de XMLs NF-e |
| Auditoria por Produto      | ✅ PRONTO | Auditoria tributária por produto             |
| Auditoria Geral            | ✅ PRONTO | Auditoria tributária gerencial NF-e          |

### 📋 HISTÓRICO DE VERSÕES

#### VERSÃO 4.1 (29/06/2026)
- **Nova funcionalidade:** Importação de Tributação via Planilha — importação completa de NCM, ICMS, PIS, COFINS e Reforma Tributária com criação automática de faixas ICMS e regras RT no ERP
- **Atualização:** version.py com todos os módulos do sistema documentados (18 módulos)
- **Documentação:** VERSION.md sincronizado com version.py

#### VERSÃO 4.0 (22/06/2026)
- **Nova funcionalidade:** Recalcular Títulos — botão em "Contas a Receber" que recalcula TIT_TOTAL pela soma das parcelas sem apagar dados
- **Nova funcionalidade:** Abrir XML da NF-e — diálogo de detalhes na Auditoria Geral agora mostra coluna ARQUIVO com o nome do XML, botão "Abrir XML" (abre no visualizador padrão) e "Ver Todos os Campos" (todos os pares chave:valor do XML)
- **Nova funcionalidade:** Opção "Salvar e Abrir" — todas as telas com exportação de log em .txt agora perguntam se deseja abrir o arquivo após salvar
- **Melhoria:** Coluna "Produto" na Auditoria Geral agora agrupa e exibe corretamente a descrição do produto
- **Melhoria:** Menu principal reorganizado com filtro por cards (TODOS/EXCEL/XML)
- **Correção:** Importação de recebíveis agora atualiza cabeçalho TIT_TOTAL quando o título já existe
- **Correção:** Caminhos de arquivo normalizados (os.path.normpath) para evitar falhas com barras mistas em rede UNC
- **Documentação:** SKILL.md criado com documentação completa de todas as 20 telas, utilitários e tabelas Firebird
- **Compatibilidade:** Suporte a caminhos de rede (//sistec-files/...)

#### VERSÃO 3.3 (05/06/2026)
- Importação de planilha de contas a receber e a pagar
- Mapeamento flexível de colunas do Excel
- Validação de títulos duplicados
- Tela de importação de lista de preços por planilha
- Tela de importação de produtos por planilha (com validação de erros)

#### VERSÃO 3.2.1 (04/06/2026)
- Filtro por módulo/tela na Busca de Logs (combobox + seleção múltipla)
- Lista fixa de módulos Sistec pré-carregada no filtro
- Descoberta automática de módulos novos durante a busca
- Correção: filtro de módulo reseta ao iniciar nova busca
- Título da janela principal exibe versão

#### VERSÃO 3.2.0 (02/06/2026)
- Sincronização de versão com release v3.2.0

#### VERSÃO 3.0.0 (29/05/2026)
- Versão inicial do sistema de importação
- Módulos: Plano de Contas, CFOP, ICMS
- Busca de Logs básica
- Atualizador automático via GitHub

## COMO ATUALIZAR A VERSÃO

Para criar uma nova versão, edite este arquivo e:
1. Mude a versão no topo
2. Mova os módulos de "🔧 AJUSTES" para "✅ PRONTO"
3. Adicione data da release
4. Commite com tag (se usar git)

## ARQUIVOS DA VERSÃO

O sistema pode gerar um `VERSION.txt` para incluir no executável.

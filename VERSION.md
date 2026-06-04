# VERSÃO DO SISTEMA

```
┌─────────────────────────────────────────────────────────────┐
│                   IMPORTADOR SISTEC                        │
│                      VERSÃO 3.2.1                           │
│                   Data: 04/06/2026                         │
└─────────────────────────────────────────────────────────────┘
```

## MÓDULOS POR VERSÃO

### ✅ VERSÃO 3.2.1 - RELEASE ATUAL (04/06/2026)
| Módulo              | Status    | Descrição                         |
|---------------------|-----------|-----------------------------------|
| Plano de Contas     | ✅ PRONTO | Importação de plano de contas     |
| NCM                 | 🔧 AJUSTES| Classificação fiscal de NCMs      |
| CFOP                | ✅ PRONTO | Parametrização de CFOPs           |
| ICMS                | ✅ PRONTO | Matriz de faixas ICMS             |
| Importação XML      | 🔧 AJUSTES| Importação genérica de XML        |
| Produtos            | 🔧 AJUSTES| Cadastro de produtos              |
| Reforma Tributária   | 🔧 AJUSTES| CBS/IBS substituição              |
| Busca de Logs       | ✅ PRONTO | Busca avançada em logs ERP        |

### 📋 HISTÓRICO DE VERSÕES

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

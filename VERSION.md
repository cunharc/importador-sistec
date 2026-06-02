# VERSÃO DO SISTEMA

```
┌─────────────────────────────────────────────────────────────┐
│                   IMPORTADOR SISTEC                        │
│                      VERSÃO 3.1.1                           │
│                   Data: 02/06/2026                         │
└─────────────────────────────────────────────────────────────┘
```

## MÓDULOS POR VERSÃO

### ✅ VERSÃO 3.1.1 - RELEASE ATUAL (02/06/2026)
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

#### VERSÃO 3.1.1 (02/06/2026)
- Busca de Logs: Maximizar/restaurar tela, layout responsivo
- Busca de Logs: Análise semântica inteligente (ACESSO_*, CBE_STATUS, DIRB)
- Busca de Logs: Filtragem de ruído e exibição de campos-chave
- Busca de Logs: Salvar cópia do arquivo original

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

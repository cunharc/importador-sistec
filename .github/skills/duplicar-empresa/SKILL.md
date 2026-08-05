---
name: duplicar-empresa
user-invocable: true
description: '**REFERÊNCIA DE MÓDULO** — Documenta a tela "Duplicar / Configurar Empresa" (telas/tela_duplicar_empresa.py). USE FOR: entender, dar manutenção ou estender a rotina que clona uma empresa/filial do ERP Sistec (EMPRESA, EMPRESA_PARAM, FILIAL, FILIAL_PARAM, CONFIG_NFE) e edita as configurações campo a campo antes de gravar no Firebird. Consulte antes de mexer nessa tela, na duplicação de empresas, ou nas tabelas de configuração de empresa/filial. DO NOT USE FOR: importações por planilha/XML ou auditorias (outros módulos).'
---

# Módulo: Duplicar / Configurar Empresa

## O que faz
Clona uma empresa/filial existente do ERP Sistec e permite ajustar cada configuração
(campo a campo) antes de gravar. Resolve o cenário de implantação em que se cria uma
empresa nova (ex: empresa 91) como cópia de outra (ex: empresa 1), decidindo **o que vai
junto** (config compartilhada, aponta para a empresa origem) e **o que vai separado**
(config própria, aponta para a empresa nova).

## Arquivos
- `telas/tela_duplicar_empresa.py` — a tela (classe `TelaDuplicarEmpresa`).
- `telas/tela_inicial.py` — registro do card (`_abrir_duplicar_empresa`, import, entrada na
  lista `modulos` com categoria `()` → só aparece no filtro TODOS).
- `docs/DUPLICAR_EMPRESA.md` — manual operacional (passo a passo para o implantador).

## Tabelas envolvidas e chaves (constante `TABELAS`)
| Aba / Tabela            | Chave primária (col → chave lógica)                    | Nível    |
|-------------------------|--------------------------------------------------------|----------|
| TABELA_EMPRESA          | EMP_CODIGO→emp, EMP_EXERCICIO→exerc                    | empresa  |
| TABELA_EMPRESA_PARAM    | EP_EMPRESA→emp                                         | empresa  |
| TABELA_FILIAL           | FILIAL_EMPRESA→emp, FILIAL_CODIGO→fil                 | filial   |
| TABELA_FILIAL_PARAM     | FP_EMPRESA→emp, FP_FILIAL→fil                         | filial   |
| TABELA_CONFIG_NFE       | CNFE_EMPRESA→emp, CNFE_FILIAL→fil                     | filial   |

Contagem real de colunas (FABENE, jul/2026): EMPRESA=34, EMPRESA_PARAM=165, FILIAL=507,
FILIAL_PARAM=1243, CONFIG_NFE=123 (esta tem o BLOB `CNFE_CERT_ARQUIVO`).

## Como usar (resumo)
1. **Etapa 1 — Duplicar:** escolhe origem no combo (exercício auto-preenche), informa Nova
   Empresa / Nova Filial / Novo Exercício → botão **⧉ Duplicar**. Copia as 5 tabelas em uma
   transação; tabela que já existir no destino é **pulada** (não sobrescreve). Ao fim, já
   carrega o destino nas abas.
2. **Etapa 2 — Configurar:** notebook com 1 aba por tabela, grade **campo | valor** com
   busca. Duplo-clique no valor edita inline. Alterado = verde; chave = vermelho (travado);
   BLOB = cinza (travado). **💾 Salvar aba atual** ou **💾 Salvar TODAS as abas** grava só os
   campos alterados, em transação, com confirmação por tabela.

Caso "adicionar filial a empresa existente": duplicar de novo pra mesma empresa mudando só a
filial — EMPRESA/EMPRESA_PARAM aparecem como "destino já existe" e são puladas; só cria
FILIAL/FILIAL_PARAM/CONFIG_NFE da nova filial.

## Decisões técnicas (NÃO QUEBRAR)
- **Duplicação via `INSERT ... SELECT` no próprio banco**, trocando só as colunas-chave por
  parâmetros. Copia tipos e BLOBs nativamente (sem round-trip em Python).
- **Colunas lidas do catálogo** (`RDB$RELATION_FIELDS`/`RDB$FIELDS`) em tempo de execução e
  cacheadas em `self.meta_cache` — nada de campos hardcoded. Colunas **computed**
  (`RDB$COMPUTED_BLR IS NOT NULL`) são excluídas do INSERT (não é possível inserir nelas).
- **TODO identificador vai com aspas duplas** via helper `_q()`. Motivo: existe a coluna
  `EP_TAB-CC` (com hífen) em TABELA_EMPRESA_PARAM; sem aspas o Firebird lê como subtração e
  quebra. Se for gerar SQL com nome de coluna, use `_q(col)`.
- **BLOB** (tipo 261): mostrado como `[BLOB - não editável]`, travado na edição, mas
  **copiado** na duplicação (está em `cols`, só não é editável na grade).
- **Ordem de inserção** respeita FK: EMPRESA → EMPRESA_PARAM → FILIAL → FILIAL_PARAM →
  CONFIG_NFE. Tudo numa transação (`fb.transaction`) — falha = rollback total.
- **Conversão de tipos ao salvar** (`_converter`): vazio→NULL; tipos 7/8/16 → int (scale<0 →
  float); 10/27 → float; resto (char/varchar/date/time/timestamp) → string. Datas devem ser
  editadas em ISO (`YYYY-MM-DD`).
- Comparação de alteração é por string (valor exibido vs original guardado em `self.orig`);
  só campos que mudaram entram no UPDATE.

## Como estender
- **Adicionar outra tabela** à duplicação/edição: inclua um dict em `TABELAS` com `aba`,
  `tabela` e `pk` (lista de `(coluna, chave_lógica)` onde a chave é `emp`/`fil`/`exerc`). A
  aba, a grade, a duplicação e o salvamento passam a funcionar automaticamente.
- **Novo nível de chave** além de emp/fil/exerc: adicionar o campo na UI, no dict `orig`/
  `dest`/`alvo` e mapear na `pk`.

## Armadilhas conhecidas
- `config.ini` precisa apontar para o banco certo (a tela usa o `[FIREBIRD]` corrente).
- Não editar campos de data/timestamp sem usar formato ISO.
- Filtro da grade usa detach/reattach (não repopula) — preserva valores editados não salvos.

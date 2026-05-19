# 🧠 RESUMO TÉCNICO E ARQUITETURA DE MÓDULOS

Este documento consolida todas as implementações, regras de negócio e lógicas arquiteturais aplicadas na **Central de Implantação e Auditoria Sistec**.

---

## 1. Hub Central e Sistema Core (`main.py` e `tela_inicial.py`)
* **Auto-Discovery do Banco de Dados:** O sistema varre automaticamente caminhos padrão (`C:\UTILIT\SISTEC.INI` e `launcher.ini`) para descobrir o IP, caminho do `.FDB`, usuário e senha, auto-configurando o `config.ini` de forma silenciosa.
* **Gestão de Memória:** Implementada técnica de `self.tela_atual` com `.destroy()`. Ao voltar para a tela inicial, a tela anterior é limpa do Garbage Collector do Python, impedindo vazamento de RAM (memory leak) ao abrir telas com Treeviews pesadas.
* **Rastreabilidade (Logs Diários):** Eventos de entrada, saída e clique são monitorados. Gera arquivos particionados por dia (`acessos_modulos_YYYY-MM-DD.log`) capturando `socket` (Nome da Máquina) e `getpass` (Usuário do Windows). Possui rotina autolimpante que varre e deleta logs com mais de 30 dias na inicialização.
* **Atalhos e Acessibilidade:** 
  - `<F5>` Atualiza a conexão com o banco e recarrega combos.
  - `<Esc>` Aciona a rotina inteligente de "Voltar" (bloqueada caso seja um popup/toplevel).

## 2. Atualização Automática via Nuvem (`utils/updater.py`)
* **Comunicação com a API do GitHub:** O módulo requisita a rota `/releases/latest` usando `urllib`.
* **Lógica Regex de Tag:** Extrai a versão puramente numérica de qualquer release (Ex: `centralsistec-v2.1` -> `2.1`) para comparar com a constante em `version.py`.
* **Patching sem perda de dados:** Baixa o `.zip` compilado na pasta temporária do Windows (`tempfile`). Gera e executa um `atualizar.bat` que "mata" a aplicação atual em Python, faz o `xcopy` do conteúdo extraído e reinicia o executável. Isso **não apaga** arquivos dinâmicos (logs e `.ini`), mantendo a estabilidade.

## 3. Importação de Plano de Contas (`tela_importacao.py`)
* **Validação Estrutural Contábil:** Analisa linhas da planilha Excel definindo o Nível Sintético/Analítico e validando máscaras.
* **Segurança na Injeção (Firebird):** Apresenta grade de *Preview* multi-colorida (Sinalizando linhas DUPLICADAS ou com ERRO). Possui trava de segurança e validação visual de "Zerar Banco de Dados".
* **Comunicação com BD em Bloco:** Rotina transacional que injeta registros processados progressivamente utilizando `fb.inserir_registros`, protegida por `try-finally` para evitar bancos trancados.

## 4. Auditoria de Lista de Preços (`tela_lista_precos.py`)
* **Leitura Híbrida de XML:** Carrega NFe em lote varrendo `cProd` e `vUnCom`. 
* **Matching Engine Interno:** Cruza os códigos lidos contra a `TABELA_PRODUTO` do ERP (procurando no Código Interno ou no Código Auxiliar).
* **Data Grid Inteligente:** Permite a modificação manual de preços sugeridos (com duplo-clique) antes de salvar.
* **UPSERT:** Dispara comando nativo do Firebird `UPDATE OR INSERT INTO TABELA_LISTA_PRECOS` através do `MATCHING (LIS_EMPRESA, LIS_FILIAL, LIS_CODIGO, LIS_PRODUTO)`, atualizando preços e inativando falhas.

## 5. Adequação da Reforma Tributária (`tela_rt.py`)
* **Dicionário em Memória (`REGRAS_RT_MAP`):** Aplicação de tabela oficial mapeando a `ClassTrib` com os percentuais de Isenção, Tributação Integral, Redução de Alíquota ou Redução Mista.
* **Tratamento de Padding:** Uso de `zfill(6)` dinâmico para garantir o formato exigido pelo validador.
* **Dual Grid View:** Lado esquerdo com as regras lidas do XML e imputação rápida (auto-sugerindo Random IDs quando necessário). Lado direito apresentando a `TABELA_RT_CONFIG_2025_2026` puxada do ERP, com sistema comparativo em tempo real para status ERP de atualização.

## 6. Auditoria Geral Gerencial (`tela_auditoria_geral.py`)
* **Agrupamento Dinâmico em Tempo de Execução:** Algoritmo que transforma XMLs baseados nos checkbuttons (Produto, NCM, CFOP, UF Dest, ICMS, etc.). Ele gera combinações únicas formatando chaves tuplas dinâmicas (`tuple(chave)`).
* **População Distinta (`_get_distinct`):** Em colunas unidas, agrupa dados por Set, imprimindo valores concatenados (Ex: "123 / 124") ou a flag `*VÁRIOS*` caso excedam 3 variantes, simplificando a interface visual.
* **Filtros Multi-Selection:** Modal Toplevel customizado contendo barra de busca e `Listbox` de seleção múltipla, alterando os registros visíveis em memória.
* **Exportação CSV:** Converte o `Treeview` renderizado ativamente em um CSV estruturado em `utf-8-sig` (garantindo perfeita abertura no Excel).

---

*Documentação criada/atualizada em: Maio de 2026.*
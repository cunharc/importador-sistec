# Central de Implantação Sistecweb — Resumo do Sistema

## O que é

Ferramenta de **implantação e auditoria** de ERP (banco **Firebird**). Ela lê **XMLs de NF-e/NFC-e** e **planilhas Excel/CSV** para **cadastrar, tributar e auditar** dados diretamente no ERP do cliente — reduzindo digitação manual na virada/implantação.

Duas grandes fontes de dados:
- **XML** — o sistema lê as notas (NF-e modelo 55 e NFC-e modelo 65) e monta/audita cadastros e tributação a partir do que a empresa já emitiu/recebeu.
- **Excel/CSV** — importações com **mapeamento de colunas** (você diz qual letra de coluna é cada campo).

O menu inicial ("Central de Implantação") organiza os módulos em três categorias: **XML**, **Excel** e **Outros**, com busca e cards.

---

## Módulos baseados em XML

Leem os XMLs de uma pasta/arquivos e cruzam com o ERP.

| Tela | O que faz |
|------|-----------|
| **Clientes/Fornecedores NF-e** | Importa clientes e fornecedores automaticamente a partir da leitura dos XMLs de NF-e 4.00. |
| **Faixas de ICMS** | Constrói e audita as **faixas de ICMS por estado** a partir do histórico de XMLs e grava no ERP. Cada faixa tem os perfis **CT (contribuinte), NC (não-contribuinte) e SN (Simples Nacional)** — dá para definir o perfil **linha a linha** e juntar várias regras numa mesma faixa (uma no CT, outra no NC, etc.). Uma faixa é sempre **Compra OU Venda**. |
| **Tributação por NCM** | Agrupa os NCMs encontrados nos XMLs e mostra, em formato **mestre-detalhe** (NCM-pai + regras que vieram no XML), todas as variações de tributação. Você **elege** qual regra vira o padrão do NCM (rádio), e o sistema grava faixa de ICMS, Reforma (RT), PIS, COFINS e IPI na classificação fiscal. **Cria faixa de ICMS e regra RT** quando ainda não existem, com tela de conferência **antes → depois** e exportação das regras não usadas. |
| **Tributação CFOP** | Define as **naturezas de operação** e regras contábeis por CFOP. |
| **Reforma Tributária (RT)** | Constrói e audita as regras de **IBS e CBS** a partir dos XMLs. |
| **Produtos & Consolidado** | Auditoria final por produto, cruzando **NCM, CFOP e ICMS**, para cadastro e correção dos produtos no ERP. |
| **Lista de Preços XML** | Cria ou atualiza **listas de preço de venda** capturando o valor unitário direto dos XMLs. |
| **Auditoria por Produto** | Mostra todas as **variações de tributação** que um mesmo produto sofreu ao longo dos XMLs (útil para achar divergências). |
| **Visão Gerencial (Completa)** | Auditoria consolidada agrupando **Produto + NCM + CFOP + ICMS + PIS/COFINS + RT**, com exportação. |

---

## Módulos baseados em Excel/CSV

Importam planilhas com **mapeamento de colunas** (você informa a letra da coluna de cada campo) e **validam contra o ERP** antes de gravar.

| Tela | O que faz |
|------|-----------|
| **Plano de Contas** | Importação estruturada do **plano de contas** via Excel para o Firebird. |
| **Importar Produtos (Excel)** | Auto-cadastro de **produtos, grupos e subgrupos**. Permite mapear código antigo e **código atual**, tipo de produto, NCM, unidade, etc. Regras de código: usa o **código atual** informado, ou mantém o antigo, ou gera **sequencial**. Flag para levar o **código antigo** ao Auxiliar e ao Cód. Importação. Após importar, a tela **recarrega** sozinha. |
| **Importar Clientes (Excel)** | Importação de clientes com mapeamento de colunas. |
| **Importar Contas a Receber (Excel)** | Importação de **títulos e parcelas** de contas a receber. |
| **Importar Contas a Pagar (Excel)** | Importação de **títulos e parcelas** de contas a pagar. |
| **Importar Lista de Preços (Excel)** | Importação de tabela de preços com validação contra o cadastro do ERP. |
| **Importar Tributação (Excel)** | Importação completa de tributação por NCM via planilha: **ICMS, PIS, COFINS e Reforma Tributária**, criando faixas e regras quando necessário. |

---

## Ferramentas / Outros

| Tela | O que faz |
|------|-----------|
| **Busca em Logs ERP** | Varredura rápida e avançada nos arquivos `.txt` de log gerados pelo ERP (filtros por módulo, ordenação, etc.). |
| **Duplicar / Configurar Empresa** | Clona uma empresa/filial existente (EMPRESA, PARAM, FILIAL, config de NF-e) e permite **ajustar cada configuração campo a campo** antes de gravar. |
| **Vínculo Centro de Custos × Plano de Contas** | Vincula os **centros de custo analíticos** às contas do plano (contabilização automática) em massa, estilo planilha. Árvore de CC + busca do plano; dá para **digitar o código/reduzido da conta e vincular direto**. |

---

## Telas de apoio

| Tela | O que faz |
|------|-----------|
| **Configuração de Conexão** | Parâmetros de acesso ao Firebird: servidor, porta, caminho do banco (.fdb), usuário, senha e a versão do **fbclient.dll**. Botão "Testar Conexão". |
| **Central de Implantação (menu inicial)** | Tela principal: cards dos módulos por categoria, busca, status da conexão, acesso a logs e "Sobre". |
| **Sobre** | Informações e versão do sistema. |
| **Pré-visualização / Injeção de Produto** | Telas internas usadas pelos fluxos de produto para revisar os dados extraídos e gravar/atualizar no ERP. |

---

## Fluxo típico de implantação

1. **Configurar Conexão** com o Firebird do cliente.
2. **Duplicar/Configurar Empresa** (quando é uma nova empresa/filial).
3. Cadastros base por **Excel** (Plano de Contas, Produtos, Clientes) ou por **XML** (Clientes/Fornecedores, Produtos).
4. **Tributação** a partir dos XMLs (Faixas de ICMS, NCM, CFOP, Reforma) ou pela planilha de Tributação.
5. **Contas a Pagar/Receber** e **Listas de Preço**.
6. **Vínculo CC × Plano de Contas** e **Auditorias** (por Produto e Visão Gerencial) para conferência final.

> **Observação:** todas as leituras de XML consideram **NF-e (55) e NFC-e (65)** juntas, sem filtro por modelo.

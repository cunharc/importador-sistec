# Registro da Rotina: Importação de Lista de Preços via XML

## 1. Objetivo
Automatizar a criação e atualização das Listas de Preços de Venda (`TABELA_LISTA_PRECOS`) a partir dos arquivos XML de Notas Fiscais, cruzando os itens do XML com os produtos já cadastrados no ERP.

## 2. Fluxo de Operação

### Etapa 1: Captura e Leitura dos XMLs
- O usuário seleciona uma pasta ou um conjunto de arquivos XML.
- O sistema varre os arquivos e extrai a tag de código do produto (`cProd`), descrição (`xProd`) e o valor unitário (`vUnCom`).
- Em caso de produtos repetidos nos XMLs (mesmo `cProd`), o sistema mantém apenas a última ocorrência para garantir o preço mais recente.

### Etapa 2: Cruzamento com o ERP (Match)
- O sistema consulta a `TABELA_PRODUTO` no Firebird filtrando por Empresa e Filial.
- É feita uma tentativa de correspondência (Match) do código do XML (`cProd`) em duas frentes:
  1. **Código Auxiliar (`PRODUTO_COD_AUXILIAR`)**: Geralmente onde o código original do fornecedor é armazenado.
  2. **Código Interno (`PRODUTO_CODIGO`)**: Código gerado pelo próprio ERP.
- **Vínculo**: Se encontrado em qualquer uma das chaves, o sistema resgata o Código Interno Verdadeiro para usar na tabela de preços.
- **Falha**: Se não encontrado, o produto é marcado como "NÃO CADASTRADO" e bloqueado para importação (já que não há um ID válido no ERP para vinculá-lo).

### Etapa 3: Interface e Edição (UI)
- Os dados são carregados em uma grade visual. Para grandes volumes, o carregamento é feito em "lotes" (chunks) de 200 em 200 itens para não congelar o aplicativo.
- O usuário pode visualizar o status (VINCULADO ou NÃO CADASTRADO), o preço extraído e a descrição.
- **Edição Manual**: Através de um duplo clique na linha, é possível editar manualmente o preço que será importado, garantindo flexibilidade caso o preço do XML não seja o preço final de venda desejado.

### Etapa 4: Configuração da Lista
O usuário define o destino dos dados na interface:
- **Atualizar Lista Existente**: O sistema consulta as listas atuais (`LIS_CODIGO` e `LIS_DESCRICAO`) para o usuário escolher uma do menu suspenso.
- **Criar Nova Lista**: O usuário informa manualmente um ID numérico e uma descrição para criar uma lista do zero.

### Etapa 5: Injeção no Banco de Dados (Firebird)
- A injeção ocorre apenas para os produtos marcados com "☑" e que possuem o status "VINCULADO".
- A instrução SQL utilizada é o `UPDATE OR INSERT ... MATCHING (LIS_EMPRESA, LIS_FILIAL, LIS_CODIGO, LIS_PRODUTO)`.
  - Isso garante que se o produto já existir na mesma lista, seu preço seja apenas **atualizado**. Se não existir, ele será **inserido**.
- Os campos atualizados com o valor do XML são: `LIS_PRECO` e `LIS_VR_BRUTO`.
- A data de criação/alteração (`LIS_DATA` e `LIS_DATA_ULT_ALTERACAO`) recebe automaticamente a data do dia da execução do processo.

## 3. Prevenções contra Falhas
- **Tratamento de Exceções Silenciosas**: Campos de preço vazios ou nulos (`vUnCom`) no XML são convertidos para `0.0` em vez de quebrar a rotina.
- **Filtro de Inserção**: É impossível inserir um produto na lista de preços sem que ele exista previamente na tabela principal de produtos.
- **Congelamento da UI**: A renderização dividida via `parent.after()` garante que a thread principal do Tkinter não bloqueie a janela ao processar milhares de itens.
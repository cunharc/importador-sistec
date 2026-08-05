# Rotina: Duplicar / Configurar Empresa

> Módulo da Central de Implantação Sistec para **clonar uma empresa/filial** do ERP e
> **ajustar as configurações** antes de gravar no Firebird.
> Tela: `telas/tela_duplicar_empresa.py` · Card roxo ⧉ (filtro **TODOS**).

---

## 1. Para que serve

Na implantação, muitas vezes é preciso criar uma empresa nova que é quase idêntica a uma
existente — mesma estrutura, mesmos parâmetros — mudando apenas **quais configurações são
compartilhadas e quais são próprias**.

Exemplo real: no frigorífico Central do Agro existe a **Empresa 1 / Filial 1** com todos os
seus configs e dados. Precisa-se criar a **Empresa 91**, que é um clone da 1, mas com parte
dos configs apontando para ela mesma (91) e parte continuando a apontar para a 1.

As tabelas de filial têm dezenas de campos `CONFIG_XXX_EMPRESA` / `CONFIG_XXX_FILIAL` que
definem **de qual empresa/filial cada área puxa a configuração**. É exatamente isso que a
Etapa 2 permite ajustar.

---

## 2. Tabelas que a rotina copia

| Tabela                 | O que guarda                          | Nº de campos* |
|------------------------|---------------------------------------|:-------------:|
| TABELA_EMPRESA         | Cadastro da empresa                    | 34            |
| TABELA_EMPRESA_PARAM   | Parâmetros gerais da empresa           | 165           |
| TABELA_FILIAL          | Cadastro da filial + apontadores CONFIG| 507           |
| TABELA_FILIAL_PARAM    | Parâmetros operacionais/fiscais da filial | 1.243      |
| TABELA_CONFIG_NFE      | Configuração de NF-e (inclui certificado digital) | 123 |

\* Contagem observada no banco FABENE em jul/2026 (a tela lê as colunas do banco em tempo
real, então acompanha mudanças de estrutura).

---

## 3. Passo a passo

### Etapa 1 — Duplicar

1. Confirme que o `config.ini` aponta para o **banco correto** (indicador de conexão na tela
   inicial).
2. Abra o módulo **Duplicar / Configurar Empresa**.
3. Em **Origem**, escolha a empresa/filial que servirá de modelo. O **Exercício origem**
   preenche automaticamente.
4. Preencha **Nova Empresa**, **Nova Filial** e **Novo Exercício** (números).
5. Clique **⧉ Duplicar Empresa** e confirme.
   - As 5 tabelas são copiadas em **uma única transação**.
   - Qualquer tabela que **já exista no destino** é **pulada** (a rotina nunca sobrescreve).
   - Se algo falhar, faz **rollback total** — nada é gravado pela metade.
6. A tela mostra o que foi copiado e o que foi pulado, e já carrega o destino nas abas.

### Etapa 2 — Configurar (o "vai junto / vai separado")

1. Em **Empresa / Filial / Exercício** (seção 2), confirme o registro (já vem preenchido com
   o destino após duplicar) e clique **📥 Carregar nas abas** se precisar recarregar.
2. Cada aba (EMPRESA, EMPRESA_PARAM, FILIAL, FILIAL_PARAM, CONFIG_NFE) mostra os campos em
   grade **CAMPO | VALOR**.
3. Use **🔎 Filtrar campo** para achar rápido (ex: digite `CONFIG_TITULO`, `CFOP`, `SERIE`).
4. **Duplo-clique no valor** para editar. Enter confirma, Esc cancela.
   - Campo **alterado** fica **verde**.
   - Campo **chave** fica **vermelho** e é **bloqueado** (não dá pra alterar por aqui).
   - Campo **BLOB** (ex: certificado) fica **cinza** e bloqueado.
5. Defina o compartilhamento. Exemplos práticos (baseados na empresa 21 do FABENE):
   - **Vai junto** (compartilha com a empresa origem): `CONFIG_CLIENTE_EMPRESA = 1`,
     `CONFIG_PRODUTO_EMPRESA = 1`, `CONFIG_GRUPO_EMPRESA = 1`.
   - **Vai separado** (próprio da nova empresa): `CONFIG_TITULO_EMPRESA = 91`,
     `CONFIG_PEDIDO_EMPRESA = 91`, `CONFIG_MOVIMENTO_EMPRESA = 91`,
     `CONFIG_NF_SAIDA_EMPRESA = 91`, `CONFIG_ICMS_EMPRESA = 91`.
6. Clique **💾 Salvar aba atual** ou **💾 Salvar TODAS as abas**.
   - Grava **apenas os campos alterados**, em transação, com confirmação mostrando quantos
     campos por tabela.

---

## 4. Casos comuns

- **Nova empresa completa:** duplica empresa+filial de uma vez (as 5 tabelas entram).
- **Nova filial em empresa existente:** duplique de novo para a **mesma empresa**, mudando só
  a **filial**. EMPRESA e EMPRESA_PARAM aparecerão como "destino já existe" (puladas) e só
  serão criadas FILIAL, FILIAL_PARAM e CONFIG_NFE da nova filial.
- **Só reconfigurar** (sem duplicar): informe Empresa/Filial/Exercício na seção 2 e
  **📥 Carregar nas abas** — dá pra editar qualquer empresa/filial já existente.

---

## 5. Cuidados

- **Datas/horas:** se for editar um campo de data, use o formato ISO `AAAA-MM-DD`
  (ex: `2026-07-07`). Campos de data em branco viram NULL.
- **Certificado digital (CONFIG_NFE):** é copiado na duplicação, mas não é editável pela
  grade (é um BLOB). Para trocar certificado, use o próprio ERP.
- **Vazio = NULL:** deixar um valor em branco grava NULL naquele campo.
- **Rollback:** tanto a duplicação quanto o salvamento são atômicos — se der erro, nada é
  gravado.

---

## 6. Notas técnicas (para manutenção)

- Duplicação feita com `INSERT ... SELECT` no próprio banco, trocando só as colunas-chave —
  preserva tipos e BLOBs.
- Colunas lidas do catálogo do Firebird em tempo de execução (nada hardcoded); colunas
  *computed* são ignoradas na cópia.
- **Todos os identificadores são escritos com aspas duplas** porque existe a coluna
  `EP_TAB-CC` (com hífen) em `TABELA_EMPRESA_PARAM`.
- Detalhes de arquitetura e como estender: ver o skill `.github/skills/duplicar-empresa/`.

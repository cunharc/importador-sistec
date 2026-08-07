# VERSÃO DO SISTEMA

```
┌─────────────────────────────────────────────────────────────┐
│                   IMPORTADOR SISTEC                         │
│                      VERSÃO 4.11                            │
│                   Data: 07/08/2026                          │
└─────────────────────────────────────────────────────────────┘
```

## MÓDULOS POR VERSÃO

### ✅ VERSÃO 4.11 - RELEASE ATUAL (07/08/2026)

| Módulo                     | Status    | Descrição                                    |
|----------------------------|-----------|----------------------------------------------|
| Importação Notas Fiscais   | ✅ PRONTO | 🐞 **A gravação reescolhia o CFOP e ignorava o que foi marcado na tela.** A fase 2 escolhia certo a variação que atende (`510102`, fluxo de caixa `N`), mas na hora de gravar o código jogava essa escolha fora e refazia a busca pegando **a primeira variação que começasse com o CFOP** — a `510101`, que gera financeiro. Resultado: importação marcada como **SEM financeiro** entrava amarrada a uma natureza **COM** financeiro. Agora a variação escolhida na análise é a que vai para a nota (cabeçalho, itens e linha de ICMS), e sem escolha a nota falha pedindo reanálise em vez de improvisar |
| Importação Notas Fiscais   | ✅ PRONTO | 🐞 **A nota entrava e o ERP recusava imprimir o DANFE.** Sem gerar financeiro, o cabeçalho declarava `NFS_QTDE_PARCELAS = <n>` e **nenhuma parcela era gravada**; o ERP compara a soma das parcelas com o total da nota, achava zero contra o total e barrava a impressão (*"valor das parcelas diferente do valor total da nota"*). Sem fluxo de caixa marcado a nota agora declara **zero parcela**, como manda a regra. E **com** financeiro a soma passa a fechar exatamente com o `NFS_VALOR_TOTAL_NOTA` que o trigger `TR_NF_SAIDA_TOTAL` recalcula — as duplicatas do XML somam o `vNF` da DANFE, que difere desse total quando há **ICMS desonerado**; a diferença vai para a última parcela e fica registrada no log (arredondamento de centavo x diferença grande, avisados de forma diferente), e o título no Receber/Pagar usa os mesmos valores para não divergir da nota |
| Importação Notas Fiscais   | ✅ PRONTO | **Nota numa filial, cadastros em outra.** Quem mantém cliente, produto e natureza numa filial só e faz as demais olharem para lá por configuração do ERP não conseguia importar: procurar na filial da nota não achava nada. Entraram os campos **Cadastros (cliente / produto / natureza) na Empresa / Filial**, com aviso quando diferem da nota (em branco, seguem a da nota). Cada coluna vai no par empresa/filial que a **chave estrangeira dela** aponta — conferido em `RDB$REF_CONSTRAINTS`, não adivinhado: `NFS_EMPRESA/FILIAL` e `TIT_EMPRESA/FILIAL` na filial da nota; `NFS_CLIENTE_*`, `NFS_NAT_OPERACAO_*`, `NFP_PRODUTO_*`, `NFP_NAT_OP_*`, `NFP_LE_*`, `NFS_CIDADE_*`, `NFS_LC_*`, `NFS_VENDEDOR_*`, `NFCC_CC_*` e os equivalentes do título na filial dos cadastros; `NFP_ESTOQUE_*` (sem FK) fica na filial do movimento. Vale para as combos de vendedor / local de cobrança / centro de custo / conta e para os três botões de cadastrar |
| Importação Notas Fiscais   | ✅ PRONTO | **Produto inativo importa, só avisa.** A nota é histórico: o produto que ela usou foi aquele mesmo, e o cliente pode tê-lo inativado depois — bloquear seria reescrever o passado. Importar já funcionava, o que faltava era o aviso; o status virou `OK (produto inativo no ERP — nota antiga)` em linha âmbar, e os contadores de pendência deixaram de tratar aviso como erro (tratavam, e isso viraria bloqueio silencioso). Continuam bloqueando só `NÃO ENCONTRADO` e `AMBÍGUO` — inclusive dois **inativos** com o mesmo código, onde não há critério para escolher |
| Auditoria (Geral e por Produto) | ✅ PRONTO | **Colunas `% MVA ST` e `% ICMS ST`** nas duas visões de produto, saindo do `pMVAST` / `pICMSST` do XML e posicionadas no bloco de ICMS (entre `% RED.BC` e `CBENEF`). Sem ST a célula fica **vazia** em vez de `0.0`, para as linhas com substituição saltarem à vista, e as duas entraram na chave de agrupamento: o mesmo produto vendido com MVA 40,55 e depois 71,78 aparece em **duas linhas**, que é a divergência que uma auditoria existe para achar. A exportação CSV leva as colunas novas |
| Clientes NF-e (XML)        | ✅ PRONTO | **Tela adaptável.** Em 1024x700 a barra de ações tinha 6 controles numa linha só e o `Aplicar aos ☑` com o checkbox de condição de pagamento **saíam pela direita**, sem rolagem e sem pista de que existiam; a grade, com 9 colunas somando 1.140px, **não tinha barra horizontal** e as quatro últimas eram inalcançáveis. Agora as barras de filtro e de ações usam a `BarraFluida` (quebram em 2 linhas em janela estreita, voltam a 1 em 1366px+), a grade foi para `grid` com as **duas** barras de rolagem, e o log encolhe para 2–3 linhas em janela baixa. O rodapé é empacotado antes da grade, então quem cede espaço é a grade e não o log; e o menu lateral passou a **caber o maior rótulo** (`Importar Selecionados` pedia 211px num menu de 210) |
| Arquitetura                | ✅ PRONTO | 🐞 **`BarraFluida` quebrava em linhas que caberiam.** Ela dimensionava todas as colunas pelo **grupo mais largo**, quando no `grid` do Tk cada coluna assume a largura do *seu* maior ocupante; com um controle largo e cinco estreitos a conta superestimava e a barra vinha em 2 linhas até em monitor de 1920. Agora soma coluna a coluna. Afeta as telas de Produtos por XML, NCM e Clientes NF-e |
| Publicação (só para o autor) | ✅ PRONTO | 🐞 **Dois scripts morriam no `print`, não no trabalho** (console do Windows em cp1252, e as mensagens têm `✔` / `✅`). O `publicar.py --versao` quebrava **depois** de escrever o `version.py`, deixando a versão nova no arquivo e o `VERSION.md` na antiga; o `compilar.py` quebrava **depois** de o `.exe` estar pronto, e o `publicar.py` — que confere o código de saída — anunciava *"a compilação falhou"* com o executável já compilado ao lado. Os dois passaram a forçar a saída em UTF-8 |

### ✅ VERSÃO 4.10 (06/08/2026)

| Módulo                     | Status    | Descrição                                    |
|----------------------------|-----------|----------------------------------------------|
| Importação Notas Fiscais   | ✅ PRONTO | **Natureza de operação que já existe é imutável.** `NAT_CODIGO` é o CFOP + 2 dígitos de variação (o CFOP 5101 aparece como `510101`, `510102`...), cada variação com as suas flags. A regra passou a ser: **existe variação que atenda exatamente** fluxo de caixa / contabilidade / estoque? **usa ela**. Não existe? **cadastra uma variação nova** (`510103`), e a grade lista as existentes com as flags de cada uma para você ver o porquê. O próximo sufixo é lido do banco no momento do cadastro, não da análise — entre analisar e cadastrar alguém pode ter criado uma variação no ERP |
| Importação Notas Fiscais   | ✅ PRONTO | 🐞 **A importação alterava natureza de operação existente.** O botão *⤓ Aplicar às naturezas desta análise* dava `UPDATE` em `NAT_FLUXO_CAIXA` / `NAT_CONTABILIDADE`, e o cadastro usava `UPDATE OR INSERT`: pedir fluxo de caixa `N` numa natureza que estava em `S` **reescrevia a natureza compartilhada**, mudando o comportamento de todas as notas que já tinham passado por ela e das outras rotinas do ERP. O botão foi **removido** e o cadastro virou `INSERT` puro |
| Importação Notas Fiscais   | ✅ PRONTO | 🐞 **Produto inativo concorria e criava ambiguidade falsa.** O CORACAO de `cProd` 3345 existe duas vezes no ERP (10381 ativo, 20000 **inativo**) e a fase 3 mostrava *AMBÍGUO (2 produtos)*, obrigando a resolver algo que já estava resolvido: inativar o gêmeo é justamente como se diz qual não usar. Agora **inativo não concorre** — só há ambiguidade quando sobra mais de um **ativo**, e nesse caso a grade mostra **quais** são os códigos em conflito em vez de só contar. Quando o gêmeo é descartado, a linha diz `OK (gêmeo inativo ignorado: 20000)`. Produto que só existe inativo continua sendo encontrado — melhor que mandar cadastrar uma terceira via do mesmo item |

### ✅ VERSÃO 4.9 (05/08/2026)

| Módulo                     | Status    | Descrição                                    |
|----------------------------|-----------|----------------------------------------------|
| Importação Clientes (planilha e XML) | ✅ PRONTO | **Cliente e fornecedor no mesmo cadastro.** As três colunas do ERP (`CF_CLIENTE`, `CF_FORNECEDOR`, `CF_OUTROS`) sempre foram independentes — quem impunha a exclusividade eram as telas, e isso obrigava a cadastrar duas vezes quem compra e vende. Agora **CLI e FOR convivem** (só `OUTROS` continua exclusivo, porque significa "nem um nem outro"): na planilha, clicando nas colunas ou pelo botão **👥🏭 Cliente + Fornecedor**; no XML de clientes, clicando na coluna **TIPO** (alterna entre os quatro tipos) ou pelo combo **Aplicar aos ☑**. A regra virou `utils/tipo_cadastro.py`, um lugar só para as três telas |
| Clientes NF-e (XML)        | ✅ PRONTO | 🐞 O `CF_OUTROS` **não existia** no INSERT desta tela: quem não era cliente nem fornecedor entrava com as três colunas em branco. Agora entra `Outros` de verdade |
| Atualização automática     | ✅ PRONTO | **O sistema avisa, o usuário decide.** Ao abrir, uma consulta em segundo plano (2,5s depois, para não parecer travado) verifica a Release mais recente do GitHub; havendo versão nova, aparece um **aviso discreto no menu** — nada é baixado, nada interrompe. Clicando, abre a janela com **o que mudou** (as notas da Release) e três saídas: *Atualizar agora*, *Depois* e *Não avisar desta versão* (guardada em `[ATUALIZACAO] versao_ignorada`, e a versão seguinte volta a avisar). Sem internet o sistema abre normal, sem reclamar |
| Atualização automática     | ✅ PRONTO | 🐞 Três defeitos que impediam a atualização de funcionar: `comparar_versoes` comparava **texto**, então a **4.10 era considerada menor que a 4.9**; o download pegava `assets[0]` **cegamente**, e um `.txt` de notas anexado por engano na Release quebrava a atualização de todos; e o `.bat` copiava um caminho fixo, então zip com o .exe numa subpasta caía na tela de "FALHA NA ATUALIZACAO" sem dizer o motivo — agora o executável é localizado em Python **antes** de gerar o `.bat`, com mensagem clara quando não está lá |
| Publicação (só para o autor) | ✅ PRONTO | **`publicar.py`**: um comando compila, empacota o `.exe` num zip com ele **na raiz** (que é onde o updater procura), cria a tag `vX.Y`, envia, cria a Release no GitHub com as notas **extraídas do `VERSION.md`**, sobe o zip e por fim **consulta a API como o cliente consulta**, confirmando que um sistema em versão anterior vai receber o aviso. Sem token, vai até a tag e diz exatamente o que falta |
| Clientes / Fornecedores (planilha, XML, Receber, Pagar) | ✅ PRONTO | 🐞 **Célula com mais de um valor rejeitava a nota.** Quem monta a planilha junta valores numa célula só (`rafael@x.com.br,rafael@x.com.br`, `(47) 3333-3333 / 99999-9999`, dois CNPJs) e o estrago era silencioso: o e-mail duplo ia inteiro para `CF_EMAIL_NFE` e a **SEFAZ rejeita a nota**; o telefone virava 22 dígitos cortados em 15 (um número que não existe); o CPF/CNPJ virava 28 dígitos, nascia inválido e nunca mais casava com nada — inclusive furando a checagem de documento único, que deixava o mesmo cliente entrar duas vezes. Agora `utils/multivalor.py` escolhe **um** valor por campo, com separadores por tipo (`/` separa telefone mas faz parte do CNPJ) e sem contar repetição como descarte. Na grade a linha fica **âmbar**, há o filtro **⚠ MAIS DE UM VALOR**, o rodapé conta quantas são e o log de importação registra o que foi descartado, linha por linha. Aplicado também na leitura do XML (`<email>`), na importação de clientes por NF-e, na fase 1 das notas e na busca de cliente/fornecedor do Receber e do Pagar |
| Tributação por NCM         | ✅ PRONTO | **Organizar os NCMs**: combo **Ordenar por** com 6 ordens — *Pendentes primeiro* (o padrão: NOVO, depois DIVERGENTE, depois OK, e dentro de cada bloco o mais usado nas notas à frente), NCM ↑/↓, mais usados, mais regras diferentes, descrição A–Z. A ordem é aplicada **na renderização**, então sobrevive a filtrar, limpar filtro e reanalisar (clicar no cabeçalho reordenava e a próxima letra digitada no filtro devolvia tudo à ordem de leitura dos XMLs). Mais **⊞ Expandir / ⊟ Recolher todos**, o filtro **"Só NCM com mais de uma regra"** (deixa na tela só o que precisa de decisão) e a preferência de ordem guardada no `config.ini` |
| Tributação por NCM         | ✅ PRONTO | **Tela proporcional**: as três faixas empilhadas de altura fixa (escopo, arquivos, filtros) viraram **duas barras que quebram em 2–3 linhas** conforme a largura; os cards de contagem **encolhem pela altura da janela** (título ao lado do número, corpo 16 em vez de 22) e a grade ganhou 8 → 13 linhas visíveis em 1024x700 / 1366x768; a barra de scroll horizontal foi para `grid` (com `pack` ela passava por baixo da vertical) e as 27 colunas finalmente têm como ser alcançadas; menu lateral em 168px e coluna do NCM em 200px em telas < 1300px |
| Arquitetura                | ✅ PRONTO | A `BarraFluida` (barra que quebra em várias linhas) saiu da tela de produtos por XML para **`utils/tema.py`** — a de NCM foi a terceira a precisar dela, e duas cópias não sobreviveriam à primeira correção |
| Importação Notas Fiscais   | ✅ PRONTO | 🐞 **Contraparte das duas pontas saía com uma flag só.** Na fase 1, o papel era decidido pela **primeira** nota encontrada com aquele CNPJ — quem é destinatário de uma saída *e* emitente de uma entrada era cadastrado só como cliente (ou só como fornecedor) e tinha de ser corrigido à mão no ERP. Agora o automático varre **todas** as notas e cadastra como cliente **e** fornecedor. O combo **Cadastrar como** permite forçar um tipo fixo para o lote inteiro |

### ✅ VERSÃO 4.8 (04/08/2026)

| Módulo                     | Status    | Descrição                                    |
|----------------------------|-----------|----------------------------------------------|
| Importação Receber / Pagar  | ✅ PRONTO | **Centro de custo e conta contábil na importação por planilha** — combos nas duas telas, rateio de 100% no valor do título, gravado na mesma transação do título e só em título NOVO (título que já existia no ERP não é da importação e não leva o rateio dela). Guardado no `config.ini` por seção |
| Importação Notas Fiscais    | ✅ PRONTO | 🐞 **Descarte silencioso**: notas de terceiros eram ignoradas com um motivo genérico, 356 vezes seguidas, sem dizer que eram **notas recebidas de fornecedor** (a empresa é o destinatário). Agora a análise abre a radiografia da pasta — emitente por emitente, com contagem e papel — e **bloqueia com erro** quando nenhuma nota foi emitida pelo CNPJ informado (banco de uma empresa com pasta de outra) |
| Arquitetura                 | ✅ PRONTO | O SQL do rateio contábil saiu de dentro da tela de NF-e para **`utils/rateio_contabil.py`**, usado pelas três telas que gravam título. Havia uma cópia; agora não há nenhuma divergindo |
| Importação Notas Fiscais   | ✅ PRONTO | **Fluxo de caixa da natureza escolhido por rodada** — é ele, não a importação, que decide se a nota gera financeiro no ERP: com `NAT_FLUXO_CAIXA='S'` o faturamento (CONFAT) cria o título ao passar pela nota, mesmo que a importação não tenha criado nada. Para o cliente cujo financeiro já veio por planilha, as naturezas entram com `N`; para os outros, com `S`. Desmarcar "Gerar financeiro" desmarca o fluxo de caixa junto, e o botão **⤓ Aplicar às naturezas desta análise** vira as que já existem (só as da análise, não a tabela inteira). A confirmação da importação avisa se sobrou alguma natureza com fluxo `S` numa rodada sem financeiro |
| Importação Notas Fiscais   | ✅ PRONTO | 🐞 O botão **↻** só recarregava o CNPJ da filial: cadastrar um vendedor no ERP com a tela aberta e clicar nele não trazia nada. Agora relê também local de cobrança, vendedor, centro de custo e conta contábil, preservando o que estava selecionado |
| Importação Notas Fiscais   | ✅ PRONTO | 🐞 **Item de nota ia para o produto errado** — 1.221 dos 3.540 itens do FABENE. `_chaves_produto` gera uma forma degradada "só os dígitos" e `_resolver_produto` testava **todas** as formas contra `PRODUTO_CODIGO` antes de olhar `COD_IMPORTACAO`: `MDC131` virava `131` e casava com o produto de código 131. Agora a chave vem antes do campo no laço — acerto exato vence acerto degradado. 64 dos 157 produtos não se achavam a si mesmos; agora, zero |
| Importação Notas Fiscais   | ✅ PRONTO | **Escopo da importação**: `Só saídas` / `Só entradas` / `Saídas + Entradas`. Saída e entrada têm classificação contábil e centro de custo diferentes, então cada uma é gravada na sua passada. O par centro de custo + conta contábil é **guardado por escopo** no `config.ini`, e o escopo é aplicado tanto na marcação da grade quanto na gravação (nota do outro tipo marcada à mão é descartada) |
| Produtos & Consolidado     | ✅ PRONTO | 🐞 **Cadastro quebrava com código não numérico**: `PRODUTO_CODIGO` é INTEGER e recebia o `cProd` do XML como texto (`MCC101`, `68, 918`) → `-303 conversion error`, e como o lote é tudo-ou-nada derrubava a importação inteira. Eram **406 dos 819** códigos dos XMLs do cliente. O código do ERP agora é sempre numérico e o do XML vai para `PRODUTO_COD_AUXILIAR` **e `PRODUTO_COD_IMPORTACAO`** (era só o auxiliar — sem a de importação a nota não reencontrava o produto) |
| Produtos & Consolidado     | ✅ PRONTO | **Código composto vira dois cadastros**: o sistema antigo emite `cProd` com dois códigos (`68, 918`) quando o produto tem dois cadastros lá. Cada parte passa a ser uma linha na grade e um cadastro próprio, marcado com ⧉ e com aviso na coluna DIVERGÊNCIAS — depois das importações, inativa-se o que não foi usado. Só `,` e `;` separam: `/` e `+` fazem parte de códigos legítimos (`mandril1/2`, `CABO HDMI+HDMI20M`) |
| Produtos & Consolidado     | ✅ PRONTO | **Tela cabe em console de servidor**: as barras Configuração e Classificação quebram em 2–3 linhas conforme a largura (1 linha em 1920, 3 em 1024), a grade ganhou **scroll horizontal** (somava 1.100px de colunas sem nenhuma forma de alcançar as últimas), o menu lateral encolhe para 168px em telas < 1300px e o modal de preview ganhou scroll horizontal, coluna **CÓD. XML** e `minsize` menor |

### ✅ VERSÃO 4.7 (03/08/2026)

Validação do módulo de NF-e contra **1.946 XMLs reais** (base FABENE): 1.545 saídas
e 9 entradas de emissão própria importadas, 356 notas de terceiros ignoradas.

| Módulo                     | Status    | Descrição                                    |
|----------------------------|-----------|----------------------------------------------|
| Importação Notas Fiscais   | ✅ PRONTO | **CNPJ da empresa agora vem de `TABELA_FILIAL`** pela empresa/filial escolhida (editável, botão ↻); o banco tem a palavra final sobre o `config.ini` — CNPJ salvo de outra base marcaria tudo como terceiros |
| Importação Notas Fiscais   | ✅ PRONTO | **DANFE não emitia** (`O valor 2.0 não é válido`): `NFS_QTDE_VOLUME` é `VARCHAR(10)` e recebia float, gravando o texto `"2.0"`. Passa a gravar inteiro puro, como o ERP |
| Importação Notas Fiscais   | ✅ PRONTO | **Entrada aparecia como INCOMPLETA**: faltava `NFE_EMITIDO='S'` (no ERP acompanha `NFE_TIPO_EMISSAO='P'`) + `NFE_SITD_CODIGO='00'`, endereço/cidade do fornecedor, dados adicionais e protocolo |
| Importação Notas Fiscais   | ✅ PRONTO | **Cadastro da contraparte não funcionava** (`-413`): `CF_ICMS` é INTEGER com FK em `TABELA_ICMS` (1=contribuinte, 2=não) e recebia `'S'`; `CF_TIPO_INSCR` usava o `indIEDest` do XML (1/9) em vez do tipo do documento (1=CPF, 2=CNPJ, 99=outros — **não existe 9**) |
| Importação Notas Fiscais   | ✅ PRONTO | **Local de cobrança e vendedor** com combo na tela (um para todas as notas), gravados na nota, na parcela e no título; o `CF_REPRESENTANTE` do cliente tem prioridade sobre o padrão |
| Importação Notas Fiscais   | ✅ PRONTO | **CST de PIS/COFINS/IPI** do XML passaram a ser gravados (`NFP_CTS_PIS/COFINS/IPI`) — vinham no arquivo e eram descartados |
| Importação Notas Fiscais   | ✅ PRONTO | 45 colunas do item de saída e 17 do de entrada entram **zeradas em vez de nulas** (lista levantada no FRIGOMASTER): NULL em campo numérico quebra a validação da DANFE |
| Importação Notas Fiscais   | ✅ PRONTO | Aviso quando o total do ERP não bate com a DANFE: `NFS_VALOR_TOTAL_NOTA` é **derivada** por `TR_NF_SAIDA_TOTAL` e a fórmula não tem termo para **ICMS desonerado** (CFOP 6109/Zona Franca) — itens e financeiro seguem corretos |
| Importação Notas Fiscais   | ✅ PRONTO | **Centro de custo e conta contábil** selecionáveis (opcionais): gravados na nota de saída (`NF_SAIDA_CC`), na de entrada (`NF_ENTRADA_CC`) e nos títulos (`TITULO_CC_REC`/`TITULO_CONTABIL_REC` e `TITULO_CC`/`TITULO_CONTABIL`), rateio de 100% no valor da nota |
| Importação Notas Fiscais   | ✅ PRONTO | **Fechar a tela durante a leitura não gera mais erro**: as threads escrevem via `_ui()`, que desiste se a tela foi destruída (`TclError: invalid command name`), e empresa/filial passaram a ser lidos na thread da UI. A grade de notas ganhou o **token de geração** que as outras 9 telas já tinham |

### VERSÃO 4.6 (01/08/2026)
| Módulo                     | Status    | Descrição                                    |
|----------------------------|-----------|----------------------------------------------|
| Importação Notas Fiscais   | 🔧 AJUSTES| **NOVO** — Traz notas de emissão própria (entrada e saída) dos XMLs. Valida em 4 fases: cliente/fornecedor, natureza de operação (com fluxo de caixa e contábil), produto (por código/auxiliar/importação) e a nota. Grava cabeçalho, itens, ICMS, observação, parcelas e o título no Receber/Pagar. **Não movimenta estoque** e não duplica título já existente |
| Importação Contas a Pagar  | ✅ PRONTO | Correção do `-530`: a chave do título passou a incluir a **série** (título na série `1` fazia o cabeçalho da série `IMP` ser pulado) + guarda de `rowcount` no UPDATE do cabeçalho |
| Importação Produtos        | ✅ PRONTO | A análise bloqueia "Código Atual" repetido na planilha ou já usado no ERP, antes do `-803` derrubar o lote inteiro |
| Importação Clientes        | ✅ PRONTO | Correção: o vendedor era criado mas **não vinculado** — `CF_REPRESENTANTE` entrou no INSERT; `VEND_NOME` truncado em 50 |
| Importação Estoque Produção| ✅ PRONTO | Colunas PRODUÇÃO / VENCIMENTO / DIAS VAL. na grade e na exportação |

### VERSÃO 4.5 (31/07/2026)
| Módulo                     | Status    | Descrição                                    |
|----------------------------|-----------|----------------------------------------------|
| Importação Estoque Produção| 🔧 AJUSTES| **NOVO** — Estoque de PA por etiquetas: gera CONFRI_ORDEM_DESOSSA (1 ordem de inventário), CONFRI_ORDEM_DESOSSA_PA (1 item por produto) e CONFRI_ORDEM_DESOSSA_PA_PESAGEM (1 por etiqueta), com validação de produto/etiqueta duplicada e commit em lote |

### VERSÃO 4.4 (30/07/2026)
| Módulo                     | Status    | Descrição                                    |
|----------------------------|-----------|----------------------------------------------|
| Importação Clientes        | ✅ PRONTO | Limite de crédito, Ativo, código mapeável com reserva/remanejamento, dedup por documento e desempenho |
| Importação Receber         | ✅ PRONTO | Situação por coluna Status, "a receber" auto-calculado, número do documento só dígitos |
| Importação Lista Preços    | ✅ PRONTO | Casamento por código de importação + descrição lado a lado |
| Identidade visual          | ✅ PRONTO | Logo oficial na interface e ícone (janela/.exe) |

### VERSÃO 4.3 (09/07/2026)
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
| Duplicar/Configurar Empresa| ✅ PRONTO | Clona empresa/filial, edita campo a campo e ajusta configs em lote |
| Vínculo CC × Plano de Contas| ✅ PRONTO | Vincula centros de custo às contas do plano em massa |

### 📋 HISTÓRICO DE VERSÕES

#### VERSÃO 4.4 (30/07/2026)
- **Importação de Clientes (Excel) — reformulação:**
  - Novos mapeamentos: **Limite de Crédito** (grava em `CF_LIMITE_CREDITO` e em `HISTORICO_LIMITE_CREDITO`; NULL quando sem valor), **Ativo** (`CF_ATIVO`: ATIVO/S/1 → `S`, INATIVO/N/0 → `N`) e **Código (CF_CODIGO)**.
  - **Código mapeável com reserva/remanejamento (2 passadas):** mantém o código antigo quando livre; os que colidem com códigos já existentes são encaixados no menor número livre, sem cascata. A grade mostra `mantém`, `antigo→novo` (remanejado) ou `(auto)`.
  - **Documento único:** CPF/CNPJ repetido (na planilha ou já no ERP) é pulado e reportado (`DOC. REPETIDO`/`JÁ CADASTRADO`).
  - **Correção de erro FK -530** (`CF_TIPO_INSCR` = 0) para registros sem documento (ex.: CONSUMIDOR → tipo 99).
  - **Desempenho:** cidades e vendedores em cache (fim das varreduras por linha na `TABELA_CIDADES_IBGE`) + progresso `X/Y`.
  - **Mapeamento responsivo** e **resumo** de importação com contagem por motivo.
- **Importação de Contas a Receber (Excel):**
  - **Situação pela coluna Status** (quando mapeada): Cancelado vem do texto; senão mantém a regra por valores.
  - **"Valor a Receber" auto-calculado** (= Conta − Recebido) quando não mapeado — corrige Saldo em Aberto e o "Cancelado" falso; os valores do preview passam a ser os mesmos gravados.
  - **Número do documento só com dígitos** (ex.: `R00099` → `99`), evitando erro de conversão em `TIT_CODIGO`.
- **Importação de Lista de Preços (Excel):** casamento por **código de importação** (prioridade código → importação → auxiliar → cód. barras → descrição) com **descrição planilha × sistema lado a lado**.
- **Identidade visual:** logo oficial (com o escrito) na splash e na topbar; ícone (janela e `.exe`) a partir da logo ícone-só.

#### VERSÃO 4.3 (09/07/2026)
- **Novo módulo — Vínculo CC × Plano de Contas:** vincula os centros de custo às contas do plano (contabilização automática: `CC_CONTABIL` = `PLANO_CODIGO`, `CC_CONTABIL_REDUZIDO` = `PLANO_REDUZIDO`). Mostra a **árvore de centros de custo** (hierarquia por `CC_CC`) com a situação de cada analítico (✔ vinculado / ● sem vínculo / ⚠ divergente), busca do plano por termo, **seleção múltipla** (Ctrl/Shift) para vincular vários à mesma conta, filtros (sem vínculo / divergentes), limpar vínculo e **gravação em lote** (transação). Registrado no menu (categoria Outros) e no manual (Sobre).
- **Nova rotina — Ajuste em Lote (dentro de Duplicar/Configurar Empresa):** editor de parâmetros com **comparação lado a lado** entre a empresa alvo e uma empresa de referência, para `EMPRESA_PARAM`, `FILIAL_PARAM` (1243 campos) e `CONFIG_NFE`. **Filtros por área** (Notas de Saída/Entrada, Pedidos, Títulos a Pagar/Receber, Contas Contábeis, Centros de Custo, CFOP, Séries/Numeração, Referências de Empresa/Filial) + busca. Edição individual e **em lote**: aplicar valor aos selecionados, copiar da referência e **trocar valor de→para** (ex.: `1 → 91` nos campos que apontam empresa). Alterações destacadas e gravadas em lote numa transação.
- **Identidade visual — telas de módulo:** todas as telas de módulo migradas para o layout com **menu lateral navy** (padrão da tela inicial): ações no menu (Analisar/Importar/Processar/Exportar/Salvar/Cancelar/Voltar), cabeçalho unificado e cores semânticas nas grades — preservando 100% da lógica/processos.
- **Pop-ups centralizados:** todas as janelas (Configuração de Conexão, Sobre, Preview, diálogos de NF-e/ICMS/NCM/RT/Auditorias, Busca em Logs, aviso do atualizador) passam a abrir **centralizadas** via novo helper `tema.centralizar()`.
- **Tela Sobre → Manual do sistema:** reescrita como manual simplificado com "O que faz / Como usar" de cada módulo, agrupado por área, com janela centralizada e identidade da marca.
- **Menu principal:** categoria "Firebird" renomeada para **"Outros"** (agrupa Duplicar Empresa, Vínculo CC e Busca em Logs); alinhamento e espaçamento do menu lateral refinados (coluna fixa de ícone, ícones alinhados à esquerda).
- **Conexão de Banco:** tela centralizada, com cabeçalho da marca e botões "Testar Conexão"/"Salvar" no novo estilo.

#### VERSÃO 4.2 (07/07/2026)
- **Identidade visual:** Sistema inteiro rebrandado com a identidade **Sistecweb** — paleta oficial (navy `#14146E`, vermelho `#C80000`, laranja IA `#FF6A14`), superfícies e cores semânticas, aplicada globalmente via novo módulo `utils/tema.py` (`aplicar_tema()` reestiliza grades/Treeview, abas/Notebook, botões, campos e scrollbars de todas as telas). Cabeçalhos de módulo unificados no navy da marca; splash e título na nova identidade.
- **Nova funcionalidade:** Módulo **Duplicar / Configurar Empresa** — clona uma empresa/filial existente (TABELA_EMPRESA, EMPRESA_PARAM, FILIAL, FILIAL_PARAM, CONFIG_NFE) trocando apenas as chaves, e permite editar cada campo em grade (campo|valor com busca) para definir o que vai compartilhado e o que vai separado antes de gravar. Duplicação e gravação atômicas (rollback em erro). Documentação em `docs/DUPLICAR_EMPRESA.md` e skill `.github/skills/duplicar-empresa/`.
- **Melhoria:** Exportações CSV das auditorias (Geral e por Produto, grade + detalhamento) agora forçam **campos numéricos longos como texto** (`="valor"`) — EAN, chave NF-e, CNPJ e NCM com zero à esquerda não são mais cortados nem viram notação científica ao abrir no Excel.
- **Nova funcionalidade:** Importação de Produtos via Planilha passa a ler a coluna **Tipo** no mapeamento (PRODUTO_TIPO por linha; se não mapeado/vazio usa o Tipo da tela).
- **Melhoria:** Importação de EAN (código de barras) do XML e da planilha grava também em `TABELA_PRODUTO_CBARRA`, fazendo o EAN aparecer na tela de produtos e na tela de produtos geral.
- **Melhoria:** Auditoria Geral com colunas de Unidade de medida e Código/Descrição separados; EAN incluído nas exportações das auditorias por produto.
- **Correção:** Importação de produtos por XML — unidade de medida truncada para 2 caracteres (`PRODUTO_UNIDADE_CV/EST/UN_EXP` são VARCHAR(2)); unidades de 3+ letras (ex: "UND") não causam mais erro "parameter too long".

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

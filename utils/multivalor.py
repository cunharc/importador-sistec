# -*- coding: utf-8 -*-
"""Célula com mais de um valor: escolhe um e diz o que descartou.

Quem monta a planilha de clientes junta valores numa célula só:

    rafael@rafael.com.br,rafael@rafael.com.br
    (47) 3333-3333 / 99999-9999
    11.111.111/0001-11; 22.222.222/0001-22

O ERP tem um campo para cada coisa, e o estrago é maior do que "ficou feio":

  - **e-mail** com dois endereços vai inteiro para `CF_EMAIL` / `CF_EMAIL_NFE` e a
    **SEFAZ rejeita a nota** — o XML aceita um endereço, não uma lista.
  - **telefone** passava por `re.sub(r'\\D', '')`, virava 22 dígitos e era cortado
    em 15: um número que não existe.
  - **CPF/CNPJ** virava 28 dígitos, então o cadastro nascia com documento inválido
    e nunca mais casava com nada.

Cada função devolve `(escolhido, descartados)`. Os descartados existem para o log:
descartar em silêncio é o que faz o problema voltar na próxima planilha.

Os separadores são por tipo, de propósito. `/` separa telefones ("3333-3333 /
99999-9999") mas faz parte do CNPJ ("0001-11") — um separador único para tudo
quebraria um dos dois.
"""
import re

_SEP_LISTA = re.compile(r'[,;\n\r\t]+')          # vale para todos
_SEP_FONE = re.compile(r'[,;/|\n\r\t]+|\s+e\s+')  # telefone também usa / e " e "


def _partes(texto, regex):
    return [p.strip() for p in regex.split(str(texto or '')) if p.strip()]


def _resultado(candidatos, todas):
    """Primeiro candidato + tudo que sobrou (sem repetir o escolhido)."""
    if not candidatos:
        return '', []
    escolhido = candidatos[0]
    descartados = [p for p in todas if p != escolhido]
    return escolhido, descartados


def um_email(texto):
    """Um e-mail só. Separa por vírgula, ponto-e-vírgula e espaço.

    Repetição não conta como descarte: `a@x.com,a@x.com` (o caso que apareceu) tem
    um e-mail só escrito duas vezes, e avisar disso seria ruído.
    """
    brutos = []
    for parte in _partes(texto, _SEP_LISTA):
        brutos.extend(p for p in parte.split() if p)
    # sem @ não é e-mail; se nenhum tiver @, devolve o texto como veio para não
    # apagar em silêncio o que o usuário digitou
    validos = [p for p in brutos if '@' in p]
    if not validos:
        return (brutos[0] if len(brutos) == 1 else ' '.join(brutos)), []
    unicos = []
    for e in validos:
        if e.lower() not in [u.lower() for u in unicos]:
            unicos.append(e)
    return unicos[0], unicos[1:]


def um_fone(texto):
    """Um telefone só, em dígitos. Aceita `,` `;` `/` `|` e " e " como separador."""
    partes = [re.sub(r'\D', '', p) for p in _partes(texto, _SEP_FONE)]
    partes = [p for p in partes if p]
    unicos = list(dict.fromkeys(partes))
    # com 8 dígitos ou mais é telefone; abaixo disso costuma ser ramal ou sujeira,
    # mas ainda assim serve se for tudo que existe
    completos = [p for p in unicos if len(p) >= 8]
    return _resultado(completos or unicos, unicos)


def um_documento(texto):
    """Um CPF/CNPJ só, em dígitos.

    Além dos separadores, trata o caso sem separador nenhum: 22 dígitos são dois
    CPFs colados e 28 são dois CNPJs — aí o primeiro documento é a primeira metade.
    Fora desses tamanhos exatos não há como adivinhar onde um acaba, então o valor
    passa inteiro e a tela mostra o documento inválido, que é honesto.
    """
    partes = [re.sub(r'\D', '', p) for p in _partes(texto, _SEP_LISTA)]
    partes = [p for p in partes if p]
    if len(partes) == 1 and len(partes[0]) in (22, 28):
        metade = len(partes[0]) // 2
        partes = [partes[0][:metade], partes[0][metade:]]
    unicos = list(dict.fromkeys(partes))
    validos = [p for p in unicos if len(p) in (11, 14)]
    return _resultado(validos or unicos, unicos)


def um_valor(texto, limite=None):
    """Um valor de texto só (IE, código, o que for). Separa por `,` `;` e quebra
    de linha — nunca por `/`, que aparece dentro de inscrições e de códigos."""
    unicos = list(dict.fromkeys(_partes(texto, _SEP_LISTA)))
    escolhido, descartados = _resultado(unicos, unicos)
    if limite:
        escolhido = escolhido[:limite]
    return escolhido, descartados


# Campos aos quais a limpeza se aplica, com a função de cada um. A ordem é a que
# aparece no aviso mostrado ao usuário.
CAMPOS = (
    ('documento', 'CPF/CNPJ', um_documento),
    ('ie', 'IE', um_valor),
    ('fone1', 'Fone 1', um_fone),
    ('fone2', 'Fone 2', um_fone),
    ('email', 'E-mail', um_email),
    ('email_nfe', 'E-mail NF-e', um_email),
)


def limpar_registro(reg):
    """Aplica a limpeza nos campos de `CAMPOS` de um dicionário de cliente.

    Devolve a lista de avisos (`'E-mail: ficou a@x.com; descartado b@y.com'`) e
    grava os valores escolhidos em `reg['<campo>_unico']` — sem sobrescrever o
    original, para o que o usuário digitou continuar visível na conferência.
    """
    avisos = []
    for chave, rotulo, func in CAMPOS:
        if chave not in reg:
            continue
        escolhido, descartados = func(reg.get(chave))
        reg[f'{chave}_unico'] = escolhido
        if descartados:
            avisos.append(f"{rotulo}: ficou '{escolhido}'; "
                          f"descartado(s) {', '.join(descartados)}")
    return avisos

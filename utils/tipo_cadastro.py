# -*- coding: utf-8 -*-
"""Tipo do cadastro em TABELA_CLI_FOR: cliente, fornecedor, outros.

As três colunas do ERP (`CF_CLIENTE`, `CF_FORNECEDOR`, `CF_OUTROS`) são
independentes — o banco sempre aceitou o mesmo cadastro ser cliente E fornecedor.
Quem impunha a exclusividade eram as telas de importação, e isso obrigava a
cadastrar duas vezes quem compra e vende.

A única exclusividade que faz sentido é `outros`: ele significa justamente
"não é cliente nem fornecedor", então não convive com os outros dois.
"""

CLIENTE = 'Cliente'
FORNECEDOR = 'Fornecedor'
CLIENTE_FORNECEDOR = 'Cliente e Fornecedor'
OUTROS = 'Outros'

# Ordem usada pelo clique que alterna o tipo na grade e pelos combos.
TIPOS = [CLIENTE, FORNECEDOR, CLIENTE_FORNECEDOR, OUTROS]

_FLAGS = {
    CLIENTE:            {'cliente': True,  'fornecedor': False, 'outros': False},
    FORNECEDOR:         {'cliente': False, 'fornecedor': True,  'outros': False},
    CLIENTE_FORNECEDOR: {'cliente': True,  'fornecedor': True,  'outros': False},
    OUTROS:             {'cliente': False, 'fornecedor': False, 'outros': True},
}


def flags(rotulo):
    """Dicionário {cliente, fornecedor, outros} para um dos rótulos de `TIPOS`.

    Rótulo desconhecido cai em `OUTROS` — é o único destino que não afirma nada
    de errado sobre o cadastro.
    """
    return dict(_FLAGS.get(str(rotulo or '').strip(), _FLAGS[OUTROS]))


def sn(rotulo):
    """Tripla ('S'/'N', 'S'/'N', 'S'/'N') pronta para o INSERT, na ordem
    CF_CLIENTE, CF_FORNECEDOR, CF_OUTROS."""
    f = flags(rotulo)
    return ('S' if f['cliente'] else 'N',
            'S' if f['fornecedor'] else 'N',
            'S' if f['outros'] else 'N')


def rotulo(cliente=False, fornecedor=False, outros=False):
    """Caminho inverso: das flags para o rótulo."""
    if cliente and fornecedor:
        return CLIENTE_FORNECEDOR
    if cliente:
        return CLIENTE
    if fornecedor:
        return FORNECEDOR
    return OUTROS


def proximo(rotulo_atual):
    """Rótulo seguinte no ciclo, para o clique na coluna TIPO da grade."""
    try:
        i = TIPOS.index(str(rotulo_atual or '').strip())
    except ValueError:
        i = -1
    return TIPOS[(i + 1) % len(TIPOS)]

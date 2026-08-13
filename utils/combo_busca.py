# -*- coding: utf-8 -*-
"""Combobox em que se digita para filtrar, em vez de rolar a lista.

Centro de custo e conta contábil têm centenas de opções (o plano de contas do
cliente tem 249 no exercício), e `state="readonly"` obriga a rolar tudo. Aqui o
campo aceita digitação: o texto filtra as opções por pedaços, sem depender de
acento nem da ordem das palavras — "receita revenda" acha
"130 - 3.1.1.01.77 RECEITA DE REVENDA DE MERCADORIAS".

Uso:
    combo = ttk.Combobox(pai, width=34)
    combo_busca.tornar_pesquisavel(combo)
    combo_busca.definir_valores(combo, ["(nenhuma)", "130 - ...", ...])

Ao sair do campo (ou com Enter) o texto é resolvido para uma opção da lista;
não resolvendo, volta o último valor válido — assim nunca sobra no campo um
texto que não corresponde a cadastro nenhum.
"""
import re
import tkinter as tk
import unicodedata

_ESTADO = '_combo_busca'


def _norm(texto):
    """Sem acento, maiúsculo, espaços colapsados."""
    t = ''.join(c for c in unicodedata.normalize('NFKD', str(texto or ''))
                if not unicodedata.combining(c))
    return ' '.join(t.upper().split())


def filtrar(valores, texto):
    """Opções que contêm TODOS os pedaços do texto (em qualquer ordem).

    Função pura para poder ser testada sem tela.
    """
    termos = [t for t in _norm(texto).split(' ') if t]
    if not termos:
        return list(valores)
    return [v for v in valores if all(t in _norm(v) for t in termos)]


def resolver(valores, texto):
    """Melhor opção para o texto digitado, ou None.

    Ordem: igual → começa com → único que contém todos os pedaços. Mais de um
    candidato "contém" não resolve — devolve None para o campo voltar ao valor
    anterior em vez de escolher no lugar do usuário.
    """
    alvo = _norm(texto)
    if not alvo:
        return None
    for v in valores:
        if _norm(v) == alvo:
            return v
    comeca = [v for v in valores if _norm(v).startswith(alvo)]
    if len(comeca) == 1:
        return comeca[0]
    # o código na frente do rótulo ("130 - ...") é o que o usuário costuma digitar
    if re.fullmatch(r'\d+', alvo):
        por_codigo = [v for v in valores if _norm(v).split(' ')[0] == alvo]
        if len(por_codigo) == 1:
            return por_codigo[0]
    contem = filtrar(valores, texto)
    return contem[0] if len(contem) == 1 else None


def definir_valores(combo, valores, manter=None):
    """Troca a lista mestre do combo (e o que aparece na tela).

    `manter` é o texto a deixar selecionado; se ele não estiver na lista, o
    campo fica vazio em vez de mostrar opção inexistente.
    """
    valores = list(valores or [])
    st = getattr(combo, _ESTADO, None)
    if st is None:
        st = {}
        setattr(combo, _ESTADO, st)
    st['todos'] = valores
    combo['values'] = valores
    if manter is not None:
        combo.set(manter if manter in valores else '')
    st['ultimo'] = combo.get()


def _restaurar(combo):
    st = getattr(combo, _ESTADO, {})
    combo['values'] = st.get('todos', [])


def tornar_pesquisavel(combo, ao_escolher=None):
    """Liga a digitação com filtro neste Combobox.

    Mantém `combo['values']` como a lista visível (filtrada) e guarda a lista
    completa à parte. `ao_escolher(valor)` é chamado quando o texto é resolvido.
    """
    st = getattr(combo, _ESTADO, None)
    if st is None:
        st = {}
        setattr(combo, _ESTADO, st)
    st.setdefault('todos', list(combo['values']))
    st.setdefault('ultimo', combo.get())
    combo.config(state='normal')

    IGNORAR = {'Up', 'Down', 'Left', 'Right', 'Home', 'End', 'Tab',
               'Shift_L', 'Shift_R', 'Control_L', 'Control_R', 'Alt_L', 'Alt_R',
               'Prior', 'Next'}

    def ao_digitar(event):
        if event.keysym in IGNORAR:
            return
        if event.keysym == 'Escape':
            combo.set(st.get('ultimo', ''))
            _restaurar(combo)
            return
        if event.keysym == 'Return':
            confirmar()
            return
        texto = combo.get()
        combo['values'] = filtrar(st.get('todos', []), texto) or st.get('todos', [])

    def confirmar(event=None):
        texto = combo.get()
        if not texto.strip():
            # campo apagado: mantém vazio só se a lista tiver um "(nenhum...)"
            vazio = next((v for v in st.get('todos', []) if v.startswith('(')), '')
            combo.set(vazio)
        else:
            achado = resolver(st.get('todos', []), texto)
            combo.set(achado if achado else st.get('ultimo', ''))
        _restaurar(combo)
        st['ultimo'] = combo.get()
        if ao_escolher:
            ao_escolher(combo.get())

    def ao_selecionar(event):
        _restaurar(combo)
        st['ultimo'] = combo.get()
        if ao_escolher:
            ao_escolher(combo.get())

    combo.bind('<KeyRelease>', ao_digitar, add='+')
    # Enter tem binding próprio: o KeyRelease dele pode não chegar quando o
    # foco muda no mesmo instante (é o que acontece ao teclar Enter e Tab).
    combo.bind('<Return>', confirmar, add='+')
    combo.bind('<KP_Enter>', confirmar, add='+')
    combo.bind('<FocusOut>', confirmar, add='+')
    combo.bind('<<ComboboxSelected>>', ao_selecionar, add='+')
    # ↓ (comportamento nativo do ttk) abre a lista já filtrada
    return combo

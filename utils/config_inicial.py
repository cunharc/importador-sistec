# -*- coding: utf-8 -*-
"""Garante que existe um config.ini para o sistema ler.

O `config.ini` de verdade não vai para o repositório: ele guarda o caminho do banco do
cliente, caminhos de rede internos, CNPJ e o último arquivo aberto em cada tela. O que
vai é o `config.ini.exemplo`, com as mesmas chaves e nenhum desses valores.

Sem isso, um clone novo abriria o sistema com todas as telas em branco e o banco
apontando para lugar nenhum, sem dizer por quê. Aqui o arquivo é criado a partir do
modelo na primeira execução, e a tela de conexão já mostra o que falta preencher.
"""
import os
import shutil

NOME = 'config.ini'
MODELO = 'config.ini.exemplo'


def garantir_config(base=None):
    """Cria o config.ini a partir do modelo quando ele não existe.

    Devolve (caminho, criado_agora). Nunca sobrescreve um config.ini existente —
    perder as preferências de quem já usa o sistema seria pior que o problema.
    """
    base = base or os.getcwd()
    destino = os.path.join(base, NOME)
    if os.path.isfile(destino):
        return destino, False

    modelo = os.path.join(base, MODELO)
    if not os.path.isfile(modelo):
        # sem modelo não há o que copiar; as telas caem nos seus próprios fallbacks
        return destino, False

    try:
        shutil.copy2(modelo, destino)
        return destino, True
    except Exception:
        return destino, False

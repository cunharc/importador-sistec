# -*- coding: utf-8 -*-
"""
Leitor da NOTA INTEIRA a partir do XML da NF-e.

Por que existe: o `utils/xml_reader.py` resolve muito bem duas necessidades
pontuais — `ler_nfe()` devolve emitente/destinatário (para cadastrar
cliente/fornecedor) e `parse_nfe()` devolve uma lista ACHATADA de itens (para
cadastrar produto/CFOP). Nenhum dos dois devolve a nota como documento: perde-se
o cabeçalho, os totais, o transporte e as duplicatas.

Este módulo NÃO reimplementa parsing: reusa os helpers já testados do
`xml_reader` (`_load_xml`, `_get`, `_get_float`, `_parse_det`,
`_extrair_dados_pagamento`, `_formatar_cnpj_cpf`, `_formatar_fone`,
`_mapear_tipo_inscr`, `_extrair_endereco_completo`) e só monta a estrutura
completa que o módulo de importação de notas precisa.
"""
import os
import re
import glob
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from utils.xml_reader import (
    _load_xml, _get, _get_float, _parse_det, _extrair_dados_pagamento,
    _formatar_cnpj_cpf, _formatar_fone, _mapear_tipo_inscr,
    _extrair_endereco_completo,
)

_log = logging.getLogger(__name__)

NS = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}


def so_digitos(valor: Any) -> str:
    """Mantém apenas dígitos — usado para comparar CNPJ/CPF de formas diferentes."""
    return re.sub(r'\D', '', str(valor or ''))


# --------------------------------------------- situação do documento fiscal
# Códigos da TABELA_SIT_DOCUM_FISCAL do ERP (são os do SPED, registro C100):
SITD_REGULAR = '00'
SITD_CANCELADO = '02'
SITD_DENEGADA = '04'
SITD_COMPLEMENTAR = '06'

# cStat do protocolo de autorização que significam DENEGADA: o documento nunca
# valeu, e é isso que a escrituração precisa saber.
CSTAT_DENEGADA = {'110', '301', '302', '303'}
# cStat de cancelamento homologado (layout antigo, no retCancNFe)
CSTAT_CANCELADA = {'101', '151', '135', '155'}
# eventos de cancelamento (o layout atual: evento separado, arquivo separado)
EVENTOS_CANCELAMENTO = {'110111', '110112'}
# cStat que confirmam o registro do evento
CSTAT_EVENTO_OK = {'135', '155'}


def ler_evento(xml_path: str) -> Optional[Dict[str, Any]]:
    """Lê um XML que NÃO é nota: evento (cancelamento, CC-e) ou cancelamento antigo.

    O cancelamento não está no XML da nota — ele é um documento à parte, na mesma
    pasta (`...-procEventoNFe.xml`, `...-can.xml`). Sem ler esses arquivos, uma
    nota cancelada entra no ERP como documento REGULAR, e a escrituração sai
    errada com valor que não existe mais.

    Devolve {'chave', 'tp_evento', 'cstat', 'cancelamento', 'data', 'motivo',
    'protocolo'} ou None. A data e a justificativa vêm do próprio evento porque o
    ERP tem campo para as duas (NFS_DATA_CANCELA / NFS_MOTIVO_CANCELA) e é por
    elas que ele trata a nota como cancelada.
    """
    try:
        root, inf_nfe, _ns = _load_xml(xml_path)
    except Exception:
        return None
    if root is None or inf_nfe is not None:
        return None          # é nota, não evento

    def _valor(tag):
        for el in root.iter():
            if re.sub(r'\{.*\}', '', el.tag) == tag and (el.text or '').strip():
                return (el.text or '').strip()
        return ''

    chave = so_digitos(_valor('chNFe'))
    if not chave:
        return None
    tp_evento = _valor('tpEvento')
    cstat = _valor('cStat')
    raiz = re.sub(r'\{.*\}', '', root.tag).lower()
    # Cancelamento pode chegar de três formas: evento 110111/110112 registrado,
    # o retCancNFe do layout antigo, ou um arquivo cujo próprio nome/raiz é de
    # cancelamento com o cStat de homologação.
    cancelamento = bool(
        (tp_evento in EVENTOS_CANCELAMENTO and (not cstat or cstat in CSTAT_EVENTO_OK))
        or ('canc' in raiz and cstat in CSTAT_CANCELADA)
        or (not tp_evento and cstat in ('101', '151'))
    )
    # dhRegEvento é o registro na SEFAZ (o que vale); dhEvento é o pedido. No
    # layout antigo (retCancNFe) o carimbo vem em dhRecbto.
    data = (_data(_valor('dhRegEvento')) or _data(_valor('dhEvento'))
            or _data(_valor('dhRecbto')))
    motivo = _valor('xJust') or _valor('xEvento') or _valor('xMotivo')
    return {'chave': chave, 'tp_evento': tp_evento, 'cstat': cstat,
            'cancelamento': cancelamento, 'arquivo': xml_path,
            'data': data, 'motivo': motivo, 'protocolo': _valor('nProt')}


def situacao_documento(nota: Dict[str, Any], cancelados=None) -> str:
    """Código da TABELA_SIT_DOCUM_FISCAL para esta nota.

    Ordem de precedência: DENEGADA vence tudo (o documento nunca existiu),
    depois CANCELADO, depois COMPLEMENTAR (`finNFe=2`); o resto é REGULAR.
    Os códigos "extemporâneo" (01/03/07) dependem de quando foi escriturado,
    coisa que o XML não diz, então não são deduzidos aqui.
    """
    if str(nota.get('cstat') or '').strip() in CSTAT_DENEGADA:
        return SITD_DENEGADA
    if nota.get('cancelada') or (cancelados and nota.get('chave') in cancelados):
        return SITD_CANCELADO
    if int(nota.get('finalidade') or 1) == 2:
        return SITD_COMPLEMENTAR
    return SITD_REGULAR


def _busca(pai, caminho: str):
    """`find` tolerante a XML com e sem namespace (o ERP recebe os dois)."""
    if pai is None:
        return None
    tags = caminho.split('/')
    atual = pai
    for tag in tags:
        if atual is None:
            return None
        prox = atual.find(f'nfe:{tag}', NS)
        if prox is None:
            prox = atual.find(tag)
        atual = prox
    return atual


def _busca_todos(pai, tag: str):
    if pai is None:
        return []
    achados = pai.findall(f'nfe:{tag}', NS)
    if not achados:
        achados = pai.findall(tag)
    return achados


def _data(texto: Optional[str]):
    """`dhEmi` (2026-07-21T13:46:15-03:00) ou `dEmi` (2026-07-21) -> date."""
    if not texto:
        return None
    try:
        return datetime.fromisoformat(str(texto)[:19]).date()
    except Exception:
        pass
    try:
        return datetime.strptime(str(texto)[:10], '%Y-%m-%d').date()
    except Exception:
        return None


def _hora(texto: Optional[str]):
    if not texto or 'T' not in str(texto):
        return None
    try:
        return datetime.fromisoformat(str(texto)[:19]).time()
    except Exception:
        return None


def _dados_parte(no, rotulo: str) -> Dict[str, Any]:
    """Emitente ou destinatário, no mesmo formato que a tela de clientes consome."""
    if no is None:
        return {}
    doc = _get(no, 'CNPJ') or _get(no, 'CPF') or ''
    ender = _busca(no, 'enderEmit') or _busca(no, 'enderDest')
    end = _extrair_endereco_completo(ender, NS) if ender is not None else {}
    ie = _get(no, 'IE') or ''
    ind_ie = _get(no, 'indIEDest') or ('1' if rotulo == 'emit' else '9')
    return {
        'documento': so_digitos(doc),
        'documento_formatado': _formatar_cnpj_cpf(doc),
        'razao': (_get(no, 'xNome') or '').strip(),
        'fantasia': (_get(no, 'xFant') or _get(no, 'xNome') or '').strip(),
        'ie': ie if ie.upper() not in ('', 'ISENTO') else 'ISENTO',
        'ind_ie': ind_ie,
        'tipo_inscr': _mapear_tipo_inscr(ind_ie, ie),
        'endereco': end.get('endereco', ''),
        'nro_end': end.get('nro', ''),
        'complemento': end.get('complemento', ''),
        'bairro': end.get('bairro', ''),
        'cidade_ibge': end.get('cidade_ibge', ''),
        'cidade_nome': end.get('cidade_nome', ''),
        'uf': end.get('uf', ''),
        'cep': so_digitos(end.get('cep', '')),
        'fone1': _formatar_fone(end.get('fone', '')),
        'suframa': _get(no, 'ISUF') or '',
    }


def _totais(inf_nfe) -> Dict[str, float]:
    t = _busca(inf_nfe, 'total/ICMSTot')
    campos = ('vBC', 'vICMS', 'vICMSDeson', 'vFCP', 'vBCST', 'vST', 'vFCPST',
              'vProd', 'vFrete', 'vSeg', 'vDesc', 'vII', 'vIPI', 'vPIS',
              'vCOFINS', 'vOutro', 'vNF')
    tot = {c: _get_float(t, c) for c in campos} if t is not None else {c: 0.0 for c in campos}
    # peso vem do transporte, não do total
    pb = pl = 0.0
    for vol in _busca_todos(_busca(inf_nfe, 'transp'), 'vol'):
        pb += _get_float(vol, 'pesoB')
        pl += _get_float(vol, 'pesoL')
    tot['pesoB'] = pb
    tot['pesoL'] = pl
    qtde_vol = 0.0
    for vol in _busca_todos(_busca(inf_nfe, 'transp'), 'vol'):
        qtde_vol += _get_float(vol, 'qVol')
    tot['qVol'] = qtde_vol
    return tot


def _transporte(inf_nfe) -> Dict[str, Any]:
    transp = _busca(inf_nfe, 'transp')
    if transp is None:
        return {'mod_frete': 9, 'transportadora': {}, 'placa': '', 'placa_uf': '', 'volumes': []}
    tr = _busca(transp, 'transporta')
    veic = _busca(transp, 'veicTransp') or _busca(transp, 'reboque')
    try:
        mod_frete = int(_get(transp, 'modFrete') or 9)
    except (TypeError, ValueError):
        mod_frete = 9
    transportadora = {}
    if tr is not None:
        doc = _get(tr, 'CNPJ') or _get(tr, 'CPF') or ''
        transportadora = {
            'documento': so_digitos(doc),
            'documento_formatado': _formatar_cnpj_cpf(doc),
            'razao': (_get(tr, 'xNome') or '').strip(),
            'ie': (_get(tr, 'IE') or '').strip(),
            'endereco': (_get(tr, 'xEnder') or '').strip(),
            'cidade_nome': (_get(tr, 'xMun') or '').strip(),
            'uf': (_get(tr, 'UF') or '').strip(),
        }
    volumes = []
    for vol in _busca_todos(transp, 'vol'):
        volumes.append({
            'qtde': _get_float(vol, 'qVol'),
            'especie': (_get(vol, 'esp') or '').strip(),
            'marca': (_get(vol, 'marca') or '').strip(),
            'peso_liq': _get_float(vol, 'pesoL'),
            'peso_bruto': _get_float(vol, 'pesoB'),
        })
    return {
        'mod_frete': mod_frete,
        'transportadora': transportadora,
        'placa': (_get(veic, 'placa') or '').strip() if veic is not None else '',
        'placa_uf': (_get(veic, 'UF') or '').strip() if veic is not None else '',
        'volumes': volumes,
    }


def _impostos_item(det) -> Dict[str, float]:
    """Valores (não alíquotas) que o `_parse_det` não devolve mas as tabelas de NF pedem."""
    imp = _busca(det, 'imposto')
    out = {'v_bc_icms': 0.0, 'v_icms': 0.0, 'v_bc_st': 0.0, 'v_st': 0.0,
           'v_icms_deson': 0.0, 'v_fcp': 0.0, 'v_ipi': 0.0, 'v_bc_ipi': 0.0,
           'v_bc_pis': 0.0, 'v_bc_cofins': 0.0}
    if imp is None:
        return out
    icms = _busca(imp, 'ICMS')
    if icms is not None and len(icms) > 0:
        n = icms[0]
        out['v_bc_icms'] = _get_float(n, 'vBC')
        out['v_icms'] = _get_float(n, 'vICMS')
        out['v_bc_st'] = _get_float(n, 'vBCST')
        out['v_st'] = _get_float(n, 'vICMSST')
        out['v_icms_deson'] = _get_float(n, 'vICMSDeson')
        out['v_fcp'] = _get_float(n, 'vFCP')
    ipi = _busca(imp, 'IPI')
    if ipi is not None and len(ipi) > 0:
        n = _busca(ipi, 'IPITrib') or ipi[-1]
        out['v_ipi'] = _get_float(n, 'vIPI')
        out['v_bc_ipi'] = _get_float(n, 'vBC')
    pis = _busca(imp, 'PIS')
    if pis is not None and len(pis) > 0:
        out['v_bc_pis'] = _get_float(pis[0], 'vBC')
    cof = _busca(imp, 'COFINS')
    if cof is not None and len(cof) > 0:
        out['v_bc_cofins'] = _get_float(cof[0], 'vBC')
    return out


def ler_nota_completa(xml_path: str, cnpj_empresa: str = '') -> Optional[Dict[str, Any]]:
    """
    Lê um XML de NF-e e devolve a nota como documento completo.

    `cnpj_empresa` define `emissao_propria`: verdadeiro quando o CNPJ do
    <emit> é o da empresa (só dígitos). Sem ele, `emissao_propria` fica None
    (indefinido) e quem chama decide.
    """
    try:
        root, inf_nfe, ns = _load_xml(xml_path)
    except Exception as e:
        _log.warning(f"Falha ao abrir {xml_path}: {e}")
        return None
    if inf_nfe is None:
        return None

    chave = (inf_nfe.get('Id') or '')
    if chave.startswith('NFe'):
        chave = chave[3:]
    chave = so_digitos(chave)

    ide = _busca(inf_nfe, 'ide')
    dh_emi_txt = _get(ide, 'dhEmi') or _get(ide, 'dEmi')
    dh_said_txt = _get(ide, 'dhSaiEnt') or _get(ide, 'dSaiEnt')
    data_emissao = _data(dh_emi_txt)
    hora_emissao = _hora(dh_emi_txt)

    def _int(v, padrao=0):
        try:
            return int(str(v).strip())
        except (TypeError, ValueError):
            return padrao

    emit = _dados_parte(_busca(inf_nfe, 'emit'), 'emit')
    dest = _dados_parte(_busca(inf_nfe, 'dest'), 'dest')

    tot = _totais(inf_nfe)
    pag = _extrair_dados_pagamento(
        inf_nfe, NS,
        datetime.combine(data_emissao, datetime.min.time()) if data_emissao else None,
        tot.get('vNF', 0.0))

    itens = []
    for det in _busca_todos(inf_nfe, 'det'):
        item = _parse_det(det)
        item['n_item'] = _int(det.get('nItem'), len(itens) + 1)
        item.update(_impostos_item(det))
        # valores acessórios rateados por item
        prod = _busca(det, 'prod')
        item['v_frete'] = _get_float(prod, 'vFrete')
        item['v_seg'] = _get_float(prod, 'vSeg')
        item['v_desc'] = _get_float(prod, 'vDesc')
        item['v_outro'] = _get_float(prod, 'vOutro')
        item['q_trib'] = _get_float(prod, 'qTrib')
        item['u_trib'] = (_get(prod, 'uTrib') or '').strip()
        item['x_ped'] = (_get(prod, 'xPed') or '').strip()
        itens.append(item)

    inf_adic = _busca(inf_nfe, 'infAdic')
    prot = _busca(root, 'protNFe/infProt') if root is not None else None

    doc_emit = emit.get('documento', '')
    propria = None
    if cnpj_empresa:
        propria = (doc_emit == so_digitos(cnpj_empresa))

    tp_nf = _int(_get(ide, 'tpNF'), 1)

    return {
        'arquivo': xml_path,
        'chave': chave,
        'nro_nf': _int(_get(ide, 'nNF')),
        'serie': (_get(ide, 'serie') or '1').strip(),
        'modelo': (_get(ide, 'mod') or '55').strip(),
        'tp_nf': tp_nf,                      # 0 = entrada, 1 = saida
        'nat_op': (_get(ide, 'natOp') or '').strip(),
        'finalidade': _int(_get(ide, 'finNFe'), 1),
        'data_emissao': data_emissao,
        'hora_emissao': hora_emissao,
        'data_saida': _data(dh_said_txt) or data_emissao,
        'mun_fato_gerador': (_get(ide, 'cMunFG') or '').strip(),
        'emit': emit,
        'dest': dest,
        'totais': tot,
        'transporte': _transporte(inf_nfe),
        'itens': itens,
        'parcelas': pag.get('duplicatas', []),
        'fatura': pag.get('fatura'),
        'pagamentos': pag.get('pagamentos', []),
        'ind_pag': pag.get('ind_pag'),
        'inf_cpl': (_get(inf_adic, 'infCpl') or '') if inf_adic is not None else '',
        'inf_ad_fisco': (_get(inf_adic, 'infAdFisco') or '') if inf_adic is not None else '',
        'protocolo': (_get(prot, 'nProt') or '') if prot is not None else '',
        # cStat do protocolo: 100/150 autorizada, 110/301/302/303 DENEGADA
        'cstat': (_get(prot, 'cStat') or '') if prot is not None else '',
        'motivo_status': (_get(prot, 'xMotivo') or '') if prot is not None else '',
        'emissao_propria': propria,
        # a contraparte da nota: nas saidas e o destinatario, nas entradas o emitente
        'contraparte': dest if tp_nf == 1 else emit,
        'cfops': sorted({str(i.get('cfop') or '').strip()
                         for i in itens if str(i.get('cfop') or '').strip()}),
    }


def ler_pasta_notas(pasta: str, cnpj_empresa: str = '',
                    callback_progresso=None) -> List[Dict[str, Any]]:
    """Lê todos os XMLs da pasta (recursivo) e devolve uma nota por arquivo.

    Notas com a mesma chave aparecem uma única vez (a primeira lida) — é comum
    o mesmo XML estar em duas pastas.
    """
    arquivos = sorted(glob.glob(os.path.join(pasta, '**', '*.xml'), recursive=True))
    total = len(arquivos)
    notas: List[Dict[str, Any]] = []
    vistas = set()
    # chave -> dados do cancelamento homologado ({'data', 'motivo', 'protocolo'}).
    # É dicionário e não conjunto porque o ERP grava a DATA e a JUSTIFICATIVA do
    # cancelamento, e é por elas (NFS_DATA_CANCELA) que ele reconhece a nota como
    # cancelada em livro fiscal, relatórios e telas.
    cancelados = {}
    for i, arq in enumerate(arquivos):
        if callback_progresso:
            callback_progresso(i + 1, total)
        try:
            nota = ler_nota_completa(arq, cnpj_empresa)
        except Exception as e:
            _log.warning(f"Erro ao ler {arq}: {e}")
            continue
        if not nota:
            # não é nota: pode ser o evento de cancelamento dela
            evento = ler_evento(arq)
            if evento and evento['cancelamento']:
                # a mesma nota pode ter o pedido e o registro do cancelamento em
                # arquivos separados: fica o que tiver data.
                atual = cancelados.get(evento['chave'])
                if not atual or (not atual.get('data') and evento.get('data')):
                    cancelados[evento['chave']] = {
                        'data': evento.get('data'), 'motivo': evento.get('motivo'),
                        'protocolo': evento.get('protocolo')}
            continue
        chave = nota.get('chave') or f"SEM-CHAVE::{arq}"
        if chave in vistas:
            continue
        vistas.add(chave)
        notas.append(nota)

    # A situação só pode ser decidida com a pasta INTEIRA lida: o evento de
    # cancelamento costuma vir depois da nota na ordem dos arquivos.
    for nota in notas:
        if nota.get('chave') in cancelados:
            nota['cancelada'] = True
            nota['cancelamento'] = cancelados[nota['chave']]
        nota['sit_documento'] = situacao_documento(nota, cancelados)
    return notas

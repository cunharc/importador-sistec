import xml.etree.ElementTree as ET
import os
import glob
import configparser
from typing import List, Dict, Any, Optional
from datetime import datetime
from utils.logger import get_logger
from utils import multivalor

_log = get_logger('xml_reader')


def pct_st(v):
    """Percentual de ST (pMVAST / pICMSST) para exibição: vazio quando não há.

    MVA e ICMS ST só existem em operação com substituição tributária. Mostrar
    '0.0' em todas as outras enche a coluna de ruído e esconde justamente as
    linhas que interessam; em branco, as que têm ST saltam à vista.
    """
    try:
        n = float(str(v).replace(',', '.'))
    except (TypeError, ValueError):
        return ''
    return '' if n == 0 else f"{n:g}"


def _get(element: ET.Element, tag: str) -> Optional[str]:
    """Tenta buscar a tag com e sem o namespace padrão da NF-e."""
    if element is None:
        return None
    
    # Tenta com namespace
    ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
    res = element.find(f'nfe:{tag}', ns)
    if res is not None:
        return res.text
        
    # Tenta sem namespace
    res = element.find(tag)
    if res is not None:
        return res.text
        
    # Busca iterativa para ignorar prefixos de namespace se houver outros
    for child in element:
        if child.tag.endswith(f'}}{tag}') or child.tag == tag:
            return child.text
            
    return None

def _get_float(element: ET.Element, tag: str) -> float:
    """Busca a tag e converte para float de forma segura."""
    val = _get(element, tag)
    if val:
        try:
            return float(val)
        except ValueError:
            return 0.0
    return 0.0

def _parse_det(det_element: ET.Element) -> Dict[str, Any]:
    """Extrai as informações de produto e tributação do bloco <det>."""
    ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
    prod = det_element.find('nfe:prod', ns)
    if prod is None:
        prod = det_element.find('.//prod') or det_element # Fallback

    item = {
        'c_prod': _get(prod, 'cProd'),
        'x_prod': _get(prod, 'xProd'),
        'c_ean': _get(prod, 'cEAN'),
        'c_barra': _get(prod, 'cBarra'),
        'ncm': _get(prod, 'NCM'),
        'cfop': _get(prod, 'CFOP'),
        'u_com': _get(prod, 'uCom'),
        'q_com': _get_float(prod, 'qCom'),
        'v_un_com': _get_float(prod, 'vUnCom'),
        'v_prod': _get_float(prod, 'vProd'),
        'c_benef': _get(prod, 'cBenef') or '',
    }

    imposto = det_element.find('nfe:imposto', ns) or det_element.find('.//imposto')
    if imposto is not None:
        # ICMS
        icms = imposto.find('nfe:ICMS', ns) or imposto.find('.//ICMS')
        if icms is not None and len(icms) > 0:
            icms_node = icms[0] # ICMS00, ICMS10, ICMS40, ICMS_SN101, etc.
            cst = _get(icms_node, 'CST')
            csosn = _get(icms_node, 'CSOSN')
            item['icms_cst'] = cst if cst else csosn
            item['p_icms'] = _get_float(icms_node, 'pICMS')
            item['p_red_bc'] = _get_float(icms_node, 'pRedBC')
            item['p_fcp'] = _get_float(icms_node, 'pFCP')
            item['mot_des_icms'] = _get(icms_node, 'motDesICMS')
            item['p_mvast'] = _get_float(icms_node, 'pMVAST')
            item['p_icmsst'] = _get_float(icms_node, 'pICMSST')

        # PIS
        pis = imposto.find('nfe:PIS', ns) or imposto.find('.//PIS')
        if pis is not None and len(pis) > 0:
            item['pis_cst'] = _get(pis[0], 'CST')
            item['p_pis'] = _get_float(pis[0], 'pPIS')
            item['v_pis'] = _get_float(pis[0], 'vPIS')

        # COFINS
        cofins = imposto.find('nfe:COFINS', ns) or imposto.find('.//COFINS')
        if cofins is not None and len(cofins) > 0:
            item['cofins_cst'] = _get(cofins[0], 'CST')
            item['p_cofins'] = _get_float(cofins[0], 'pCOFINS')
            item['v_cofins'] = _get_float(cofins[0], 'vCOFINS')

        # IPI
        ipi = imposto.find('nfe:IPI', ns) or imposto.find('.//IPI')
        if ipi is not None:
            ipi_node = ipi.find('nfe:IPITrib', ns) or ipi.find('nfe:IPINT', ns) or (len(ipi) > 0 and ipi[-1])
            if ipi_node is not None:
                item['ipi_cst'] = _get(ipi_node, 'CST')
                # Alíquota só existe no IPITrib; no IPINT (não tributado, ex.: CST 53) fica 0.
                item['p_ipi'] = _get_float(ipi_node, 'pIPI')

        # Créditos presumidos
        cred_presumidos = []
        for gcred in det_element.findall('.//nfe:gCred', ns) or det_element.findall('.//gCred'):
            cred_presumidos.append({
                'c_cred': _get(gcred, 'cCredPresumido'),
                'p_cred': _get_float(gcred, 'pCredPresumido'),
                'v_cred': _get_float(gcred, 'vCredPresumido')
            })
        item['cred_presumidos'] = cred_presumidos
        
        # Também extrai os valores individuais (primeiro gCred encontrado)
        if cred_presumidos:
            item['c_cred'] = cred_presumidos[0]['c_cred']
            item['p_cred'] = cred_presumidos[0]['p_cred']
            item['v_cred'] = cred_presumidos[0]['v_cred']
        else:
            item['c_cred'] = ''
            item['p_cred'] = 0.0
            item['v_cred'] = 0.0

        # IBSCBS (Reforma Tributária 2025/2026)
        ibscbs = None
        for child in imposto.iter():
            if child.tag.endswith('}IBSCBS') or child.tag == 'IBSCBS':
                ibscbs = child
                break
                
        def _get_rec(node, tag):
            if node is None: return None
            for c in node.iter():
                if c.tag.endswith(f'}}{tag}') or c.tag == tag:
                    return c.text
            return None
            
        def _safe_float(val):
            if val:
                try: return float(val)
                except ValueError: pass
            return 0.0

        if ibscbs is not None:
            item['ibscbs_cst'] = _get_rec(ibscbs, 'CST') or ''
            item['c_class_trib'] = _get_rec(ibscbs, 'cClassTrib') or ''
            item['p_ibs_uf'] = _safe_float(_get_rec(ibscbs, 'pAliqIBSUF') or _get_rec(ibscbs, 'pIBSUF') or _get_rec(ibscbs, 'pIBS'))
            item['p_cbs'] = _safe_float(_get_rec(ibscbs, 'pAliqCBS') or _get_rec(ibscbs, 'pCBS'))
            item['v_ibs'] = _safe_float(_get_rec(ibscbs, 'vIBSUF') or _get_rec(ibscbs, 'vIBS'))
            item['v_cbs'] = _safe_float(_get_rec(ibscbs, 'vCBS'))
        else:
            # Fallback (Garante a leitura se as tags IBS e CBS vierem em blocos separados fora do padrão)
            ibs_node, cbs_node = None, None
            for child in imposto.iter():
                if child.tag.endswith('}IBS') or child.tag == 'IBS': ibs_node = child
                if child.tag.endswith('}CBS') or child.tag == 'CBS': cbs_node = child
            if ibs_node is not None or cbs_node is not None:
                item['ibscbs_cst'] = _get_rec(ibs_node, 'CST') or _get_rec(cbs_node, 'CST') or ''
                item['c_class_trib'] = _get_rec(ibs_node, 'cClassTrib') or _get_rec(cbs_node, 'cClassTrib') or ''
                item['p_ibs_uf'] = _safe_float(_get_rec(ibs_node, 'pAliqIBSUF') or _get_rec(ibs_node, 'pIBSUF') or _get_rec(ibs_node, 'pIBS'))
                item['p_cbs'] = _safe_float(_get_rec(cbs_node, 'pAliqCBS') or _get_rec(cbs_node, 'pCBS'))
            
    return item

TPAG_DESCRIPTIONS = {
    '01': 'DINHEIRO',
    '02': 'CHEQUE',
    '03': 'CARTAO CREDITO',
    '04': 'CARTAO DEBITO',
    '05': 'CREDITO LOJA',
    '06': 'VALE ALIMENTACAO',
    '07': 'VALE REFEICAO',
    '08': 'VALE PRESENTE',
    '09': 'VALE COMBUSTIVEL',
    '10': 'BOLETO BANCARIO',
    '11': 'DEPOSITO BANCARIO',
    '12': 'PIX',
    '13': 'TRANSFERENCIA',
    '14': 'PROGRAMAS FIDELIDADE',
    '15': 'BOLETO CSR',
    '16': 'PIX QRCODE',
    '17': 'CREDITO INTERNO',
    '18': 'USB',
    '19': 'CARTAO MERCANTE',
    '20': 'GRATIS',
    '21': 'OUTROS',
    '90': 'SEM PAGAMENTO',
    '99': 'OUTROS',
}

def _formatar_cnpj_cpf(documento: str) -> str:
    """Formata CNPJ ou CPF com máscara."""
    doc = ''.join(filter(str.isdigit, str(documento)))
    if len(doc) == 14:
        return f"{doc[:2]}.{doc[2:5]}.{doc[5:8]}/{doc[8:12]}-{doc[12:]}"
    elif len(doc) == 11:
        return f"{doc[:3]}.{doc[3:6]}.{doc[6:9]}-{doc[9:]}"
    return documento

def _formatar_fone(fone: str) -> str:
    """Formata telefone com máscara."""
    if not fone:
        return ''
    nums = ''.join(filter(str.isdigit, str(fone)))
    if len(nums) >= 10:
        if len(nums) == 10:
            return f"({nums[:2]}) {nums[2:6]}-{nums[6:]}"
        elif len(nums) == 11:
            return f"({nums[:2]}) {nums[2:7]}-{nums[7:]}"
        elif len(nums) > 11:
            return f"({nums[:2]}) {nums[2:len(nums)-4]}-{nums[-4:]}"
    return fone

def _mapear_tipo_inscr(ind_iedest: str, ie: str) -> int:
    """Mapeia indIEDest para CF_TIPO_INSCR (1=Contribuinte, 9=Não Contribuinte, 2=Isento)."""
    if ind_iedest == '9':
        return 9
    elif ind_iedest in ('1', '2'):
        return 1
    elif ie and ie.upper() not in ('', 'ISENTO'):
        return 1
    return 9

def _extrair_endereco_completo(ender, ns):
    """Extrai todos os campos de endereço do XML."""
    if ender is None:
        return {
            'endereco': '', 'nro': '', 'complemento': '', 'bairro': '',
            'cidade_ibge': '', 'cidade_nome': '', 'uf': '', 'cep': '', 'fone': ''
        }
    
    return {
        'endereco': _get(ender, 'xLgr') or '',
        'nro': _get(ender, 'nro') or '',
        'complemento': _get(ender, 'xCpl') or '',
        'bairro': _get(ender, 'xBairro') or '',
        'cidade_ibge': _get(ender, 'cMun') or '',
        'cidade_nome': _get(ender, 'xMun') or '',
        'uf': _get(ender, 'UF') or '',
        'cep': _get(ender, 'CEP') or '',
        'fone': _get(ender, 'fone') or ''
    }

def _extrair_dados_pagamento(inf_nfe, ns, dt_emi, v_nf):
    """Extrai todos os dados de pagamento do XML: cobr (fatura/duplicatas) e pag (meios de pagamento)."""
    dados_pagamento = {
        'fatura': None,
        'duplicatas': [],
        'pagamentos': [],
        'ind_pag': None,
        'tipo_pagamento': None,
        'condicao_pagamento': [],
        'descricao_condicao': None
    }
    
    cobr = inf_nfe.find('nfe:cobr', ns) or inf_nfe.find('cobr')
    if cobr is not None:
        fat = cobr.find('nfe:fat', ns) or cobr.find('fat')
        if fat is not None:
            dados_pagamento['fatura'] = {
                'n_fat': _get(fat, 'nFat') or '',
                'v_orig': _get_float(fat, 'vOrig'),
                'v_desc': _get_float(fat, 'vDesc'),
                'v_liq': _get_float(fat, 'vLiq')
            }
        
        for dup in cobr.findall('.//nfe:dup', ns) or cobr.findall('.//dup'):
            n_dup = _get(dup, 'nDup') or ''
            d_venc = _get(dup, 'dVenc')
            v_dup = _get_float(dup, 'vDup')
            
            dias = 0
            if d_venc and dt_emi:
                try:
                    dt_venc = datetime.strptime(d_venc, '%Y-%m-%d')
                    dias = (dt_venc - dt_emi).days
                    if dias < 0:
                        dias = 0
                except Exception:
                    pass
            
            pct = 0
            if v_nf > 0 and v_dup > 0:
                pct = (v_dup / v_nf) * 100
            
            dados_pagamento['duplicatas'].append({
                'n_dup': n_dup,
                'dias': dias,
                'percentual': round(pct, 2),
                'd_venc': d_venc,
                'v_dup': v_dup
            })
    
    ide = inf_nfe.find('nfe:ide', ns) or inf_nfe.find('ide')
    if ide is not None:
        dados_pagamento['ind_pag'] = _get(ide, 'indPag')
    
    pag = inf_nfe.find('nfe:pag', ns) or inf_nfe.find('pag')
    if pag is not None:
        for det_pag in pag.findall('nfe:detPag', ns) or pag.findall('detPag'):
            t_pag = _get(det_pag, 'tPag') or ''
            v_pag = _get_float(det_pag, 'vPag')
            c_pag = _get(det_pag, 'cPaymentMethod') or ''
            
            desc_tpag = TPAG_DESCRIPTIONS.get(t_pag, f'COD_{t_pag}')
            
            tpag_det = {
                't_pag': t_pag,
                'descricao': desc_tpag,
                'v_pag': v_pag
            }
            
            if t_pag in ('03', '04'):
                tpag_det['c_npj'] = _get(det_pag, 'CNPJ') or ''
                tpag_det['t_band'] = _get(det_pag, 'tBand') or ''
                tpag_det['c_aut'] = _get(det_pag, 'cAut') or ''
            
            dados_pagamento['pagamentos'].append(tpag_det)
            dados_pagamento['tipo_pagamento'] = desc_tpag
    
    v_troco = 0
    if pag is not None:
        v_troco = _get_float(pag, 'vTroco')
    dados_pagamento['v_troco'] = v_troco
    
    if dados_pagamento['duplicatas']:
        dias_list = sorted(set(d['dias'] for d in dados_pagamento['duplicatas']))
        dados_pagamento['condicao_pagamento'] = [
            {'dias': d, 'percentual': 100.0 / len(dados_pagamento['duplicatas'])}
            for d in dias_list
        ]
        dados_pagamento['descricao_condicao'] = '/'.join(str(d) for d in dias_list) + ' DIAS'
    elif dados_pagamento['pagamentos']:
        dados_pagamento['condicao_pagamento'] = [{'dias': 0, 'percentual': 100.0}]
        dados_pagamento['descricao_condicao'] = 'A VISTA'
    else:
        dados_pagamento['condicao_pagamento'] = [{'dias': 0, 'percentual': 100.0}]
        dados_pagamento['descricao_condicao'] = 'N/I'
    
    return dados_pagamento

def _load_xml(xml_path: str):
    """Carrega e parseia um XML de NF-e, retornando (root, inf_nfe, ns)."""
    try:
        with open(xml_path, 'r', encoding='utf-8') as f:
            xml_content = f.read()
    except UnicodeDecodeError:
        with open(xml_path, 'r', encoding='iso-8859-1') as f:
            xml_content = f.read()

    xml_content = xml_content[xml_content.find('<'):]
    try:
        root = ET.fromstring(xml_content)
    except Exception:
        return None, None, None

    ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
    inf_nfe = root.find('.//nfe:infNFe', ns) or root.find('.//infNFe')
    return root, inf_nfe, ns

def ler_nfe(xml_path: str) -> List[Dict[str, Any]]:
    """Lê um XML de NF-e e extrai os dados do Emitente e Destinatário para importação de Clientes/Fornecedores."""
    root, inf_nfe, ns = _load_xml(xml_path)
    if inf_nfe is None:
        return []

    registros = []
    
    dh_emi = _get(inf_nfe.find('nfe:ide', ns) or inf_nfe.find('ide'), 'dhEmi')
    dt_emi = None
    if dh_emi:
        try:
            dt_emi = datetime.fromisoformat(dh_emi[:19])
        except Exception:
            pass

    v_nf = _get_float(inf_nfe.find('.//nfe:vNF', ns) or inf_nfe.find('.//vNF'), 'vNF')
    
    dados_pagamento = _extrair_dados_pagamento(inf_nfe, ns, dt_emi, v_nf)

    # Emitente
    emit = inf_nfe.find('nfe:emit', ns) or inf_nfe.find('emit')
    if emit is not None:
        cnpj = _get(emit, 'CNPJ') or _get(emit, 'CPF')
        if cnpj:
            ender_emit = emit.find('nfe:enderEmit', ns) or emit.find('enderEmit')
            end_data = _extrair_endereco_completo(ender_emit, ns)
            ie_emit = _get(emit, 'IE') or ''
            ind_iedest = _get(emit, 'indIEDest') or '1'
            
            reg = {
                'tipo': 'Fornecedor',
                'documento': cnpj,
                'documento_formatado': _formatar_cnpj_cpf(cnpj),
                'razao': _get(emit, 'xNome') or '',
                'fantasia': _get(emit, 'xFant') or _get(emit, 'xNome') or '',
                'ie': ie_emit if ie_emit.upper() not in ('', 'ISENTO') else 'ISENTO',
                'tipo_inscr': _mapear_tipo_inscr(ind_iedest, ie_emit),
                'endereco': end_data['endereco'],
                'nro_end': end_data['nro'] if end_data['nro'] and end_data['nro'] not in ('SN', 'S/N') else '',
                'complemento': end_data['complemento'],
                'bairro': end_data['bairro'],
                'cidade_ibge': end_data['cidade_ibge'],
                'cidade_nome': end_data['cidade_nome'],
                'uf': end_data['uf'],
                'cep': end_data['cep'],
                'fone1': _formatar_fone(end_data['fone']),
                'fone2': '',
                'fax': '',
                'email': '',
                'condicao_pagamento': [],
                'condicao_pagamento_desc': 'N/I',
                'dados_pagamento': dados_pagamento
            }
            registros.append(reg)

    # Destinatário
    dest = inf_nfe.find('nfe:dest', ns) or inf_nfe.find('dest')
    if dest is not None:
        cnpj = _get(dest, 'CNPJ') or _get(dest, 'CPF')
        if cnpj:
            ender_dest = dest.find('nfe:enderDest', ns) or dest.find('enderDest')
            end_data = _extrair_endereco_completo(ender_dest, ns)
            ie_dest = _get(dest, 'IE') or ''
            ind_iedest = _get(dest, 'indIEDest') or '9'
            # a tag <email> do XML também vem com dois endereços separados por
            # vírgula em nota emitida por sistema que não valida o campo
            email = multivalor.um_email(_get(dest, 'email'))[0]
            
            reg = {
                'tipo': 'Cliente',
                'documento': cnpj,
                'documento_formatado': _formatar_cnpj_cpf(cnpj),
                'razao': _get(dest, 'xNome') or '',
                'fantasia': _get(dest, 'xNome') or '',
                'ie': ie_dest if ie_dest.upper() not in ('', 'ISENTO') else 'ISENTO',
                'tipo_inscr': _mapear_tipo_inscr(ind_iedest, ie_dest),
                'endereco': end_data['endereco'],
                'nro_end': end_data['nro'] if end_data['nro'] and end_data['nro'] not in ('SN', 'S/N') else '',
                'complemento': end_data['complemento'],
                'bairro': end_data['bairro'],
                'cidade_ibge': end_data['cidade_ibge'],
                'cidade_nome': end_data['cidade_nome'],
                'uf': end_data['uf'],
                'cep': end_data['cep'],
                'fone1': _formatar_fone(end_data['fone']),
                'fone2': '',
                'fax': '',
                'email': email or '',
                'condicao_pagamento': dados_pagamento['condicao_pagamento'],
                'condicao_pagamento_desc': dados_pagamento['descricao_condicao'],
                'dados_pagamento': dados_pagamento
            }
            registros.append(reg)

    return registros

def parse_nfe(xml_path: str) -> Dict[str, Any]:
    """Lê e processa um arquivo XML de NF-e, retornando chave, info complementar e itens."""
    root, inf_nfe, ns = _load_xml(xml_path)
    if inf_nfe is None:
        return {'chave_nfe': '', 'inf_cpl': '', 'itens': []}
        
    chave_nfe = inf_nfe.get('Id', '')
    if chave_nfe.startswith('NFe'):
        chave_nfe = chave_nfe[3:]
        
    inf_adic = inf_nfe.find('nfe:infAdic', ns) or inf_nfe.find('infAdic')
    inf_cpl = _get(inf_adic, 'infCpl') if inf_adic is not None else ""
    
    # Extração do Tipo de Cliente (CT, NC) baseado na Inscrição Estadual
    dest = inf_nfe.find('.//nfe:dest', ns) or inf_nfe.find('.//dest')
    ind_iedest = _get(dest, 'indIEDest') if dest is not None else '9'
    tipo_cliente = 'CT' if ind_iedest in ('1', '2') else 'NC'
    
    # Extração de UFs (Origem e Destino)
    config = configparser.ConfigParser()
    config.read('config.ini', encoding='utf-8')
    uf_emit = config.get('IMPORTACAO', 'uf', fallback='N/I')

    # UF do emitente vinda do próprio XML (para o fallback interno da NFC-e)
    ender_emit = inf_nfe.find('.//nfe:enderEmit', ns) or inf_nfe.find('.//enderEmit')
    uf_emit_xml = _get(ender_emit, 'UF') if ender_emit is not None else None

    ender_dest = inf_nfe.find('.//nfe:enderDest', ns) or inf_nfe.find('.//enderDest')
    uf_dest = _get(ender_dest, 'UF') if ender_dest is not None else None
    if not uf_dest:
        # NFC-e / venda a consumidor não traz enderDest → operação interna:
        # assume a UF do emitente (do XML; senão a configurada).
        uf_dest = uf_emit_xml or (uf_emit if uf_emit != 'N/I' else 'EX')

    ide = inf_nfe.find('.//nfe:ide', ns) or inf_nfe.find('.//ide')
    nnf = _get(ide, 'nNF') if ide is not None else ''
    dhemi = _get(ide, 'dhEmi') if ide is not None else ''

    emit = inf_nfe.find('.//nfe:emit', ns) or inf_nfe.find('.//emit')
    emit_cnpj = _get(emit, 'CNPJ') or _get(emit, 'CPF') if emit is not None else ''
    emit_nome = _get(emit, 'xNome') if emit is not None else ''

    dest_cnpj = _get(dest, 'CNPJ') or _get(dest, 'CPF') if dest is not None else ''
    dest_nome = _get(dest, 'xNome') if dest is not None else ''

    itens = []
    for det in inf_nfe.findall('nfe:det', ns) or inf_nfe.findall('det'):
        item_data = _parse_det(det)
        item_data['uf_emit'] = uf_emit
        item_data['uf_dest'] = uf_dest
        item_data['tipo_cliente'] = tipo_cliente
        
        item_data['nNF'] = nnf
        item_data['dhEmi'] = dhemi
        item_data['emit_cnpj'] = emit_cnpj
        item_data['emit_nome'] = emit_nome
        item_data['dest_cnpj'] = dest_cnpj
        item_data['dest_nome'] = dest_nome
        
        itens.append(item_data)
        
    return {
        'chave_nfe': chave_nfe,
        'inf_cpl': inf_cpl,
        'itens': itens
    }

def parse_nfe_folder(folder_path: str, callback_progresso=None) -> List[Dict[str, Any]]:
    """Itera sobre todos os XMLs de uma pasta e retorna uma lista linear (achatada) de itens."""
    todos_itens = []
    pattern = os.path.join(folder_path, '**', '*.xml')
    xml_files = glob.glob(pattern, recursive=True)
    total = len(xml_files)
    for i, xml_file in enumerate(xml_files):
        if callback_progresso:
            callback_progresso(i + 1, total)
        try:
            nfe_data = parse_nfe(xml_file)
            if nfe_data and nfe_data.get('itens'):
                for item in nfe_data['itens']:
                    item['chave_nfe'] = nfe_data['chave_nfe']
                    item['inf_cpl'] = nfe_data['inf_cpl']
                    todos_itens.append(item)
        except Exception as e:
            _log.warning(f"Erro ao processar o arquivo {xml_file}: {e}")
            
    return todos_itens
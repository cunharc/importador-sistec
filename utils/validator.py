import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from utils.match_engine import norm_str, get_best_match

@dataclass
class ValidationResult:
    """Resultado da validação de um item do XML contra o ERP."""
    erp_match: Optional[Dict[str, Any]] = None
    score: int = 0
    auto_approve: bool = False
    divergencias: List[str] = field(default_factory=list)
    status: str = 'NAO_ENCONTRADO'

class ValidatorFiscal:
    """
    Motor de regras de auditoria fiscal e cadastral.
    Compara os dados lidos do XML com as tabelas de domínio do ERP.
    """
    def __init__(self, erp_produtos: List[Dict], regras_icms: List[Dict], 
                 regras_rt: List[Dict], cfops_erp: List[Dict], classes_trib: List[Dict]):
        self.erp_produtos = erp_produtos
        self.regras_icms = regras_icms
        self.regras_rt = regras_rt
        self.cfops_erp = {str(c.get('nat_codigo', '')).strip(): c for c in cfops_erp}
        self.classes_trib = classes_trib

    def validate(self, xml_item: Dict[str, Any], uf_dest: str) -> ValidationResult:
        match_info = get_best_match(xml_item, self.erp_produtos)
        erp_match = match_info['match']
        
        result = ValidationResult(
            erp_match=erp_match,
            score=match_info['score'],
            auto_approve=match_info['auto_approve'],
            divergencias=[]
        )

        if not erp_match:
            result.status = 'NAO_ENCONTRADO'
            return result
            
        divs = []
        divs.extend(self._check_ncm(xml_item, erp_match))
        divs.extend(self._check_descricao(xml_item, erp_match))
        divs.extend(self._check_unidade(xml_item, erp_match))
        divs.extend(self._check_icms(xml_item, erp_match, uf_dest))
        divs.extend(self._check_pis_cofins(xml_item, erp_match))
        divs.extend(self._check_origem(xml_item, erp_match))
        divs.extend(self._check_cfop(xml_item))
        divs.extend(self._check_rt(xml_item, erp_match))
        
        result.divergencias.extend(divs)
        result.status = 'DIVERGENTE' if result.divergencias else 'VALIDADO'
        
        return result

    def _check_ncm(self, xml_item: Dict, erp_match: Dict) -> List[str]:
        divs = []
        ncm_xml = str(xml_item.get('ncm') or '').strip()
        ncm_erp = str(erp_match.get('produto_class_fiscal') or '').strip()
        
        if not re.match(r'^[0-9]{8}$', ncm_xml):
            divs.append(f"NCM XML inválido (deve conter 8 dígitos): '{ncm_xml}'")
            
        if ncm_xml and ncm_erp and ncm_xml != ncm_erp:
            divs.append(f"NCM divergente: XML={ncm_xml} | ERP={ncm_erp}")
            
        return divs

    def _check_descricao(self, xml_item: Dict, erp_match: Dict) -> List[str]:
        desc_xml = norm_str(xml_item.get('x_prod', ''))
        desc_erp = norm_str(erp_match.get('produto_descricao', '') + ' ' + (erp_match.get('produto_descricao2') or ''))
        
        if desc_xml != desc_erp:
            return [f"Descrição divergente: XML='{desc_xml[:20]}...' | ERP='{desc_erp[:20]}...'"]
        return []

    def _check_unidade(self, xml_item: Dict, erp_match: Dict) -> List[str]:
        un_xml = str(xml_item.get('u_com') or '').strip().upper()
        un_erp = str(erp_match.get('produto_unidade_cv') or '').strip().upper()
        if un_xml and un_erp and un_xml != un_erp:
            return [f"Unidade divergente: XML={un_xml} | ERP={un_erp}"]
        return []

    def _check_icms(self, xml_item: Dict, erp_match: Dict, uf_dest: str) -> List[str]:
        if not uf_dest or not str(uf_dest).strip():
            return ["UF de destino não informada para validação de ICMS."]
            
        divs = []
        faixa_id = erp_match.get('produto_icms')
        if faixa_id is None:
            return ["Produto sem Faixa de ICMS (PRODUTO_ICMS) informada no cadastro."]
            
        # Filtra a regra da faixa correspondente ao estado destino (com a data mais recente)
        regras_filtradas = [r for r in self.regras_icms if r.get('aicms_faixa') == faixa_id and str(r.get('aicms_estado', '')).upper() == uf_dest.upper()]
        if not regras_filtradas:
            return [f"Regra de ICMS não encontrada para a faixa {faixa_id} e estado {uf_dest}."]
            
        # Assume que a lista já vem ordenada por data decrescente do BD, ou ordenamos aqui
        regra = sorted(regras_filtradas, key=lambda x: x.get('aicms_data') or '', reverse=True)[0]
        
        tipo_cliente = xml_item.get('tipo_cliente', 'CT')
        if tipo_cliente == 'NC':
            erp_cst = str(regra.get('aicms_situacao_ncont') or '').strip()
            erp_aliq = float(regra.get('aicms_aliquota_ncont') or 0.0)
            erp_red = float(regra.get('aicms_reducao_ncont') or 0.0)
            erp_cbenef = str(regra.get('aicms_cbenef_ncont') or '').strip()
        else:
            erp_cst = str(regra.get('aicms_situacao_cont') or '').strip()
            erp_aliq = float(regra.get('aicms_aliquota_cont') or 0.0)
            erp_red = float(regra.get('aicms_reducao_cont') or 0.0)
            erp_cbenef = str(regra.get('aicms_cbenef_cont') or '').strip()

        xml_cst = str(xml_item.get('icms_cst') or '').strip()
        if xml_cst.lstrip('0') != erp_cst.lstrip('0'):
            divs.append(f"CST ICMS divergente ({tipo_cliente}): XML={xml_cst} | ERP={erp_cst}")
            
        if abs((xml_item.get('p_icms') or 0.0) - erp_aliq) > 0.01:
            divs.append(f"% ICMS divergente ({tipo_cliente}): XML={xml_item.get('p_icms')} | ERP={erp_aliq}")
            
        if abs((xml_item.get('p_red_bc') or 0.0) - erp_red) > 0.01:
            divs.append(f"% Redução BC divergente ({tipo_cliente}): XML={xml_item.get('p_red_bc')} | ERP={erp_red}")
            
        xml_cbenef = str(xml_item.get('c_benef') or '').strip()
        if xml_cbenef and erp_cbenef and xml_cbenef != erp_cbenef:
            divs.append(f"cBenef divergente ({tipo_cliente}): XML={xml_cbenef} | ERP={erp_cbenef}")
            
        return divs

    def _check_pis_cofins(self, xml_item: Dict, erp_match: Dict) -> List[str]:
        divs = []
        if xml_item.get('pis_cst') and str(xml_item['pis_cst']).lstrip('0') != str(erp_match.get('produto_cst_pis') or '').lstrip('0'):
            divs.append(f"CST PIS divergente: XML={xml_item['pis_cst']} | ERP={erp_match.get('produto_cst_pis')}")
            
        if xml_item.get('cofins_cst') and str(xml_item['cofins_cst']).lstrip('0') != str(erp_match.get('produto_cst_cofins') or '').lstrip('0'):
            divs.append(f"CST COFINS divergente: XML={xml_item['cofins_cst']} | ERP={erp_match.get('produto_cst_cofins')}")
            
        return divs

    def _check_cfop(self, xml_item: Dict) -> List[str]:
        cfop = str(xml_item.get('cfop') or '').strip()
        if cfop and cfop not in self.cfops_erp:
            return [f"CFOP da nota não cadastrado no ERP: {cfop}"]
        return []

    def _check_rt(self, xml_item: Dict, erp_match: Dict) -> List[str]:
        xml_class = str(xml_item.get('c_class_trib') or '').strip().lstrip('0') or '0'
        xml_cst = str(xml_item.get('ibscbs_cst') or '').strip().lstrip('0') or '0'
        
        if xml_class == '0' and xml_cst == '0':
            return []
            
        divs = []
        match_found = False
        
        for regra in self.regras_rt:
            db_class = str(regra.get('trt_class_trib_id') or regra.get('trt_clas_trib_id') or '').lstrip('0') or '0'
            db_cst = str(regra.get('trt_cst') or '').lstrip('0') or '0'
            
            if db_class == xml_class and db_cst == xml_cst:
                match_found = True
                
                db_ibs = float(regra.get('trt_aliq_ibs_estadual') or 0)
                xml_ibs = float(xml_item.get('p_ibs_uf') or 0)
                if abs(db_ibs - xml_ibs) > 0.01:
                    divs.append(f"% IBS divergente: XML={xml_ibs} | ERP={db_ibs}")
                    
                db_cbs = float(regra.get('trt_aliq_cbs') or 0)
                xml_cbs = float(xml_item.get('p_cbs') or 0)
                if abs(db_cbs - xml_cbs) > 0.01:
                    divs.append(f"% CBS divergente: XML={xml_cbs} | ERP={db_cbs}")
                
                return divs
                
        if not match_found:
            divs.append(f"Regra RT não encontrada para cClassTrib={xml_class} CST={xml_cst}")
            
        return divs

    def _check_origem(self, xml_item: Dict, erp_match: Dict) -> List[str]:
        origem = erp_match.get('produto_origem')
        cst = str(xml_item.get('icms_cst') or '').strip()
        if origem == 0 and cst == '101':
            return ["Inconsistência de Origem: Produto nacional (Origem=0) utilizando CST de importado ('101')"]
        return []
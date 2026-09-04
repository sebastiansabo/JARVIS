"""Tiered supplier resolution: CUI -> Nr.Reg -> Ref.No -> alias -> name -> fuzzy."""
from dataclasses import dataclass

from core.suppliers.normalize import normalize_cui, normalize_nr_reg


@dataclass(frozen=True)
class Resolution:
    supplier_id: int | None
    confidence: str  # 'high' | 'medium' | 'low' | 'none'
    method: str


class SupplierResolver:
    def __init__(self, lookup):
        self.lookup = lookup

    def resolve(self, name=None, cui=None, nr_reg=None, ref_no=None) -> Resolution:
        ncui = normalize_cui(cui)
        if ncui:
            sid = self.lookup.find_by_cui_normalized(ncui)
            if sid:
                return Resolution(sid, 'high', 'cui')
        nreg = normalize_nr_reg(nr_reg)
        if nreg:
            sid = self.lookup.find_by_nr_reg_normalized(nreg)
            if sid:
                return Resolution(sid, 'high', 'nr_reg')
        if ref_no:
            sid = self.lookup.find_by_ref_no(ref_no)
            if sid:
                return Resolution(sid, 'high', 'ref_no')
        sid = self.lookup.find_by_alias(name=name, cui_normalized=ncui)
        if sid:
            return Resolution(sid, 'high', 'alias')
        if name:
            sid = self.lookup.find_by_name_exact(name)
            if sid:
                return Resolution(sid, 'medium', 'name_exact')
            match = self.lookup.find_by_fuzzy_name(name)
            if match:
                return Resolution(match[0], 'low', 'fuzzy')
        return Resolution(None, 'none', 'none')

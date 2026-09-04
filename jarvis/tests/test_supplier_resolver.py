from core.suppliers.resolver import SupplierResolver, Resolution


class FakeLookup:
    def __init__(self, by_cui=None, by_nr=None, by_ref=None, by_alias=None, by_name=None, fuzzy=None):
        self._cui, self._nr, self._ref = by_cui or {}, by_nr or {}, by_ref or {}
        self._alias, self._name, self._fuzzy = by_alias or {}, by_name or {}, fuzzy
    def find_by_cui_normalized(self, cui): return self._cui.get(cui)
    def find_by_nr_reg_normalized(self, nr): return self._nr.get(nr)
    def find_by_ref_no(self, ref): return self._ref.get(ref)
    def find_by_alias(self, name, cui_normalized):
        return self._alias.get(cui_normalized) or self._alias.get((name or '').lower())
    def find_by_name_exact(self, name): return self._name.get((name or '').lower())
    def find_by_fuzzy_name(self, name): return self._fuzzy


def test_cui_tier_wins_even_when_name_differs():
    # Porsche case: master row 42 keyed by CUI; invoice spells the name differently
    r = SupplierResolver(FakeLookup(by_cui={'9997007': 42})).resolve(
        name='Porsche Romania s.r.l.', cui='RO9997007')
    assert r == Resolution(42, 'high', 'cui')

def test_falls_through_to_nr_reg_then_ref_no():
    assert SupplierResolver(FakeLookup(by_nr={'J40/1/2020': 7})).resolve(nr_reg='j40 / 1 / 2020') == Resolution(7, 'high', 'nr_reg')
    assert SupplierResolver(FakeLookup(by_ref={'EXT-1': 9})).resolve(ref_no='EXT-1') == Resolution(9, 'high', 'ref_no')

def test_name_exact_is_medium_and_fuzzy_is_low():
    assert SupplierResolver(FakeLookup(by_name={'acme srl': 3})).resolve(name='ACME SRL') == Resolution(3, 'medium', 'name_exact')
    assert SupplierResolver(FakeLookup(fuzzy=(5, 0.82))).resolve(name='acme s.r.l') == Resolution(5, 'low', 'fuzzy')

def test_no_hit_is_none():
    assert SupplierResolver(FakeLookup()).resolve(name='Unknown', cui='RO1') == Resolution(None, 'none', 'none')

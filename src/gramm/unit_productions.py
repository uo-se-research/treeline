"""Factor unit productions.
Example:
    A ::= B C ;
    B ::= X ;
    X :: 'b';
    C ::= 'c';

should become:
    A ::= 'b' 'c' ;
"""

from gramm import grammar

from typing import Set

import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

class UnitProductions(grammar.TransformBase):
    """After transformation, Assuming we have already consolidated all productions for
    each non-terminal, there should be no productions with a single _Literal or _Symbol
    on the right-hand side.
    """
    def __init__(self, g: grammar.Grammar):
        self.gram = g
        self.unit_symbols: Set[grammar._Symbol] = set()

    def is_unit(self, item: grammar.RHSItem) -> bool:
        log.debug(f"Checking RHS item {item} of type {type(item)}")
        if not isinstance(item, grammar._Symbol):
            log.debug("Not a symbol")
            return False
        log.debug(f"=> {item.expansions}")
        if isinstance(item.expansions, grammar._Symbol):
            return True
        if isinstance(item.expansions, grammar._Literal):
            return True

    def apply(self, item: grammar.RHSItem) -> grammar.RHSItem:
        """Replace symbols that expand into a single symbol (unit productions)"""
        # It's a _Symbol, so it has an 'expansions' member
        while self.is_unit(item):
            self.unit_symbols.add(item)
            item = item.expansions
        return item

    def teardown(self, g: grammar.Grammar):
        """Prune orphan symbols"""
        # Cannot remove start symbol!
        self.unit_symbols.discard(g.start)
        symbols = list(g.symbols.keys())
        for name in symbols:
            if g.symbols[name] in self.unit_symbols:
                del g.symbols[name]
        g._calc_min_tokens()
        g._calc_pot_tokens()

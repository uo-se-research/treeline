"""Transform grammar so that each _Choice node has
exactly two alternatives.
"""

import grammar
from grammar import _Choice, RHSItem
from typing import List

class Binary_Choices(grammar.TransformBase):
    """After transformation, each _Choice node will
    have two alternatives.
    """
    def __init__(self, g: grammar.Grammar):
        self.gram = g

    def divide(self, items: List[RHSItem]) -> RHSItem:
        assert len(items) > 0
        # Special cases for 1, 2 items
        if len(items) == 1:
            return items[0]
        if len(items) == 2:
            choice = self.gram.choice()
            choice.append(items[0])
            choice.append(items[1])
        # 3 or more nodes: Recursive subdivision
        parent = self.gram.choice()
        div = len(items) // 2
        parent.append(self.divide(items[:div]))
        parent.append(self.divide(items[div:]))
        return parent


    def apply(self, item: grammar.RHSItem) -> grammar.RHSItem:
        """Postorder visit"""
        # Only _Choice nodes are affected
        if not isinstance(item, grammar._Choice):
            return item
        # Also we don't need to split choices of two items
        assert isinstance(item, grammar._Choice)
        if len(item.items) == 2:
            return item
        assert len(item.items) > 2
        divided = self.divide(item.items)
        return divided


    def teardown(self, g: grammar.Grammar):
        """We have introduced new nodes, so we need
        to recalculate min tokens.
        FIXME: Increasingly min tokens looks like it shouldn't
               be part of initial grammar creation.
        """
        g._calc_min_tokens()

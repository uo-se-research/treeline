"""Group large choices of character literals into categories"""

from gramm import grammar
from enum import Enum, auto
from typing import List

import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

# How big does a choice need to be to make it worthwhile to split?
CHARCLASS_TRIGGER_THRESHOLD = 5  # Must be at least 3

class CharCategory(Enum):
    """The values associated with these categories are
    functions that classify the strings. They are ordered
    from more specific to less specific.
    """
    digit = [str.isdigit]
    lower = [str.islower]
    upper = [str.isupper]
    space = [str.isspace]
    ascii_alnum = [lambda s: s.isascii() and s.isalnum()]
    control = [lambda s: s.isascii() and not s.isprintable()]
    ascii_other = [str.isascii]
    unicode_letter = [str.isalpha]
    unicode_other = [lambda s: True]
    # Implementation note:  functions as Enum values
    # do not work in Python 3.  This is an undocumented
    # bug:  Python turns function values into methods instead
    # of Enum entries.  That is why I need to make each
    # category a list.

def categorize(s: str) -> CharCategory:
    assert isinstance(s, str)
    for cat in CharCategory:
        log.debug(f"Checking {s} against {cat}")
        if cat.value[0](s):
            return cat
    assert False, "No category matched!"


class CharClasses(grammar.TransformBase):
    """Where we have a single Choice node with many character Literals,
    break the character literals into categories such as alpha, numeric, national,
    control, etc.
    """
    def __init__(self, g: grammar.Grammar):
        self.gram = g

    def divide(self, items: List[grammar._Literal]) -> grammar.RHSItem:
        parent = self.gram.choice()  # New parent node for choosing a group
        items.sort(key=lambda i: i.text)
        # We assume categories are mostly in contiguous
        # ranges of character codes, and we proceed to
        # break up the categories by runs of same
        # category.
        subgroup = self.gram.choice()
        parent.append(subgroup)
        category = categorize(items[0].text)
        for item in items:
            item_cat = categorize(item.text)
            if item_cat != category:
                subgroup = self.gram.choice()
                parent.append(subgroup)
                category = item_cat
            subgroup.append(item)
        if len(parent.items) == 1:
            # They were all in the same category!
            return subgroup
        return parent

    def is_eligible(self, item: grammar.RHSItem) -> bool:
        """A node is eligible for breaking into character classes if it
        is a Choice node with at least CHARCLASS_TRIGGER_THRESHOLD alternatives,
        each of which is a literal consisting of a single character.
        """
        if not isinstance(item, grammar._Choice):
            return False
        if len(item.items) < CHARCLASS_TRIGGER_THRESHOLD:
            return False
        for choice in item.items:
            if not isinstance(choice, grammar._Literal):
                return False
            # class _Literal objects have a 'text' field; the ones we
            # care about are single unicode characters
            if len(choice.text) > 1:
                return False
        return True


    def apply(self, item: grammar.RHSItem) -> grammar.RHSItem:
        """Postorder visit"""
        # Only _Choice nodes are affected
        if not self.is_eligible(item):
            return item
        divided = self.divide(item.items)
        return divided


    def teardown(self, g: grammar.Grammar):
        """We have introduced new nodes, so we need
        to recalculate min tokens.
        FIXME: Increasingly min tokens looks like it shouldn't
               be part of initial grammar creation.
        """
        g._calc_min_tokens()
        g._calc_pot_tokens()

"""Glue together parsing and random sentence generation"""

from gramm.llparse import *
from gramm.generator import *
from gramm.char_classes import  CharClasses
from gramm.unit_productions import UnitProductions
from gramm.grammar import FactorEmpty
from gramm.biased_choice import Bias

import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

# f = open("data/ebnf_optional.gram")
# f = open("data/ebnf_plus.gram")
# f = open("data/nested_groups.gram")
# f = open("data/sqlite_pruned.txt")
f = open("data/flex.gram")
# f = open("data/ebnf_charclass.gram")
# f = open("data/gram-calc-multi-line-2020-06-04_22-59.gram.txt")
gram = parse(f, len_based_size=True)
gram.finalize()

xform = UnitProductions(gram)
xform.transform_all_rhs(gram)

xform = CharClasses(gram)
xform.transform_all_rhs(gram)

xform = FactorEmpty(gram)
xform.transform_all_rhs(gram)

# log.debug(f"Grammar is {gram}")
#
# print("*** Grammar (repr): ***")
# for name in gram.symbols:
#     sym = gram.symbols[name]
#     print(f"{sym} ::= {repr(sym.expansions)}")
# print("*** *** ***")
# print("*** Grammar (str) ***")
# print(gram.dump())
# print("*** Generated sentences ***")
# budget = max(5, 2 * gram.start.min_tokens())
bias_base = Bias()
for i in range(100):
    bias = bias_base.fork()
    txt = random_sentence(gram, budget=60, min_length=30, bias=bias)
    if len(txt) > 50:
        bias.reward()
    elif len(txt) < 40:
        bias.penalize()
    print(f"\nGenerated:\n{txt}")
# print("Bias table: ")
# print(dump_bias(bias_base, gram))
# print("Bias should be up there^")

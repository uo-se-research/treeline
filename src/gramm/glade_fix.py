"""Transformations designed specifically for grammars produced
by Glade, to make them more suitable for TreeLine.
- Add a single non-terminal EMPTY and remove other empty strings
- Unroll unit productions, which add useless depth to derivations
- Break big disjunction of character literals into groups that are
  often treated similarly, e.g., digits
"""

from gramm.llparse import *
from gramm.char_classes import CharClasses
from gramm.unit_productions import UnitProductions
from gramm.grammar import FactorEmpty

import argparse
import sys

import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


def cli():
    """Command line interface for grammar fixups"""
    parser = argparse.ArgumentParser("Transform grammar (esp. Glade grammars)")
    parser.add_argument("original", type=argparse.FileType('r'),
                        nargs="?", default=sys.stdin,
                        help="Original BNF grammar file")
    parser.add_argument("transformed", type=argparse.FileType('w'),
                        nargs="?", default=sys.stdout,
                        help="Transformed BNF grammar file")
    args = parser.parse_args()
    return args


def main():
    args = cli()
    grammar = parse(args.original)
    grammar.finalize()
    logging.debug("Parsed original grammar")

    logging.debug("Unrolling unit productions")
    xform = UnitProductions(grammar)
    xform.transform_all_rhs(grammar)

    logging.debug("Dividing character constants into groups")
    xform = CharClasses(grammar)
    xform.transform_all_rhs(grammar)

    logging.debug("Factoring empty productions")
    xform = FactorEmpty(grammar)
    xform.transform_all_rhs(grammar)

    print(grammar.dump(), file=args.transformed)


if __name__ == "__main__":
    main()

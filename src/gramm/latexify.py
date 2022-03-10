"""Mark up a grammar for printing with latex.sty"""

from gramm.llparse import *
from gramm.char_classes import  CharClasses
from gramm.unit_productions import UnitProductions
from gramm.grammar import FactorEmpty

import argparse
import sys

import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

def cli() -> object:
    """Command line interface"""
    parser = argparse.ArgumentParser("Convert pygramm grammar for LaTeX processing")
    parser.add_argument("infile", nargs="?", default=sys.stdin,
                        type=argparse.FileType("r"),
                        help="pygramm grammar file to read")
    parser.add_argument("outfile", nargs="?", default=sys.stdout,
                        type=argparse.FileType("w"),
                        help="LaTeX file to write")
    parser.add_argument("--factor_units", action="store_true",
                        help="Factor unit productions")
    parser.add_argument("--char_classes",  action="store_true",
                        help="Form character classes")
    parser.add_argument("--factor_empty",action="store_true",
                        help="Factor empty rhs to a single non-terminal")
    args = parser.parse_args()
    return args


def main():
    args = cli()
    f = args.infile
    gram = parse(f)
    gram.finalize()
    if args.factor_units:
        xform = UnitProductions(gram)
        xform.transform_all_rhs(gram)
    if args.factor_empty:
        xform = FactorEmpty(gram)
        xform.transform_all_rhs(gram)
    if args.char_classes:
        xform = CharClasses(gram)
        xform.transform_all_rhs(gram)
    print(gram.latex(), file=args.outfile)

if __name__ == "__main__":
    main()

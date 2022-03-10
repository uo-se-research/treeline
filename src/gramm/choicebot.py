"""Interactive sentence generation:
User prompted for each choice.
"""

import argparse

from gramm.llparse import *
from gramm.generator import Gen_State
from gramm.grammar import Grammar, FactorEmpty


def cli() -> object:
    """Command line interface,
    returns an object with an attribute for each
    command line argument.
    """
    parser = argparse.ArgumentParser("Interactive sentence generator")
    parser.add_argument("grammar", type=argparse.FileType("r"),
                        help="Path to file containing BNF grammar definition"
                        )
    parser.add_argument("budget", type=int,
                        default=50,
                        help="Maximum length string to generate, default 50")
    parser.add_argument("--esc", dest="escapes",
                        default=False,
                        action="store_const", const=True,
                        help="Expand unicode escapes in grammar")
    return parser.parse_args()


def choose_from(choices: list) -> int:
    """Obtain an integer choice from user.
    Returned int should be index of choice.
    """
    while True:
        try:
            for i in range(len(choices)):
                print(f"({i}) {choices[i]}  requires {choices[i].min_tokens()}")
            choice = int(input("Your choice: "))
            if choice in range(len(choices)):
                return choices[choice]
        except Exception:
            pass
        print("Bad choice. Try again.")


def generate_sentence(g: Grammar, budget: int,
                      escapes=False):
    """A generator of random sentences with external control"""
    state = Gen_State(g, budget)
    while state.has_more():
        print(f"=> {state} margin/budget {state.margin}/{state.budget}")
        if state.is_terminal():
            state.shift()
        else:
            choices = state.choices()
            if len(choices) > 1:
                choice = choose_from(choices)
            else:
                choice = choices[0]
            state.expand(choice)
    if escapes:
        state.text = state.text.encode().decode('unicode-escape')
    print(f"Final: \n{state.text}")


def main():
    args = cli()
    gram = parse(args.grammar)
    transform = FactorEmpty(gram)
    transform.transform_all_rhs(gram)
    budget = args.budget
    generate_sentence(gram, budget, args.escapes)


if __name__ == "__main__":
    main()

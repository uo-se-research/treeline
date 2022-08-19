"""Mutation of derivation trees styled after Nautilus (roughly).
Two kinds of mutation at a non-terminal symbol in the derivation tree:
   (a)  Generate a random substitute subtree
   (b)  Splice a previously seen tree
"""
import context
import mutation.gen_tree  as gen_tree
import mutation.chunk_store as chunk_store

import random
from typing import Optional

import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

SEEN = chunk_store.Chunkstore()


def mutant(tree: gen_tree.DTreeNode,  budget: int) -> Optional[gen_tree.DTreeNode]:
    """A copy with one choice replaced by a fresh expansion,
    staying within budget.
    No guarantee of getting something different!
    FIXME:  Ensure uniqueness with store of already generated strings (or hashes)
    """
    # Tactic:  Compare the length of the whole sentence to
    #    the budget.  This gives a margin, which can be
    #    added to the length of the subtree we are replacing.
    mutated = tree.copy()
    # How much can a mutated subtree exceed its
    # minimum requirement?
    margin = budget - len(tree)
    assert margin >= 0
    mutable_node: gen_tree.DTreeNode = random.choice(mutated.mutation_points())
    assert mutable_node is not None
    mutable_node.expand(len(mutable_node) + margin)
    return mutated


def hybrid(tree: gen_tree.DTreeNode, budget: int) -> Optional[gen_tree.DTreeNode]:
    """A copy with one choice replaced by a spliced
    subtree to form a new tree.  Guaranteed not to return the
    same tree, but could produce a previously seen tree.
    """
    assert isinstance(tree, gen_tree.DTreeNode)
    # Tactic:  Compare the length of the whole sentence to
    #    the budget.  This gives a margin, which can be
    #    added to the length of the subtree we are replacing.
    mutated = tree.copy()
    # How much can a mutated subtree exceed its
    # minimum requirement?
    margin = budget - len(tree)
    assert margin >= 0
    choices = mutated.mutation_points()
    splice_point: gen_tree = random.choice(choices)
    assert isinstance(splice_point, gen_tree.DTreeNode)
    assert splice_point is not None
    # Splicing at root would just be substituting another (sub)tree that
    # has already been seen, so we prefer any other node.
    if len(choices) > 1 and splice_point == mutated:
        for again in range(3):
            splice_point: gen_tree = random.choice(choices)
            if splice_point != mutated:
                break
    if splice_point == mutated:
        # Will still occasionally happen by bad luck
        log.debug(f"No mutable nodes except root in {mutated}\n ( {repr(mutated)} )")
        return None
    # Head is ok, but the children need to be replaced
    substitute = SEEN.get_sub(splice_point, len(splice_point) + margin)
    if substitute is None:
        log.info(f"No compatible substitutes for '{splice_point}'")
        log.info(f"Because: {SEEN.why_not(splice_point, len(splice_point) + margin)}\n")
        return None
    assert isinstance(substitute, gen_tree.DTreeNode)
    splice_point.children = substitute.children
    return mutated


def stash(t: gen_tree.DTreeNode):
    """Save all subtrees that could be used in splicing"""
    for m in t.mutation_points():
        SEEN.put(m)


def cli() -> object:
    """Command line argument is path to grammar file"""
    import argparse
    parser = argparse.ArgumentParser("Mutating and splicing derivation trees")
    parser.add_argument("grammar", type=argparse.FileType("r"))
    parser.add_argument("--limit", type=int, default=60,
                        help="Upper bound on generated sentence length")
    parser.add_argument("--tokens", help="Limit by token count",
                        action="store_true")
    return parser.parse_args()


def demo():
    from gramm.llparse import parse
    # from gramm.char_classes import CharClasses
    # from gramm.unit_productions import UnitProductions
    args = cli()
    limit = args.limit
    f = args.grammar
    gram = parse(f, len_based_size=True)
    gram.finalize()
    print(f"LL grammar: \n{gram.dump()}")

    # xform = UnitProductions(gram)
    # xform.transform_all(gram)

    # xform = CharClasses(gram)
    # xform.transform_all(gram)

    trees = []
    for fresh_trees in range(5):
        t = gen_tree.derive(gram, budget=limit)
        trees.append(t)
        log.debug(f"Fresh tree: {repr(t)}")
        print(f"Fresh tree: '{t}'")
        for m in t.mutation_points():
            SEEN.put(m)

        # print("Mutants:")
        for _ in range(3):
            mut = mutant(t, budget=limit)
            log.debug(f"Mutant tree: \n{repr(mut)}")
            print(f"Mutant: {mut}")
            trees.append(mut)
            stash(mut)


    print("The following chunks have been recorded")
    print(SEEN)

    print("\nSplices:")
    for t in trees:
        print(f"\nHybridizing {t}")
        for _ in range(3):
            mut = hybrid(t, budget=limit)
            # assert mut is not None
            print(f"'{t}' =>\n'{mut}'")


if __name__ == "__main__":
    demo()

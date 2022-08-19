"""A collection of previously generated subtrees, indexed by non-terminal symbol.
Based (roughly) on the chunkstore of Nautilus grammar-based mutation tester.
"""

# We really want to do this exactly once, by importing a single path adjustment module (?)
# import sys, os
# this_folder = os.path.abspath(os.path.join(os.path.dirname(__file__)))
# sys.path.insert(0, os.path.abspath(this_folder))

import context

import gramm.grammar as grammar
import mutation.gen_tree as gen_tree
import random
from typing import Optional

import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

class Chunk:
    """Record of a previously generated subtree, with attributes we can
    use to select or reject it when we are splicing into another tree.
    Attributes are public.
    """
    def __init__(self, t: gen_tree.DTreeNode, text: str):
        assert isinstance(t, gen_tree.DTreeNode)
        self.node = t
        self.length = len(text)
        log.debug(f"Indexing {t.head} => '{t}'  ({text})")
        self.sig = hash(text)

    def __str__(self) -> str:
        return str(self.node)


class Chunkstore:
    """A collection of gen_tree.DTreeNode objects, indexed by their head symbol.
    These are subtrees that we could splice into another derivation tree.
    The basic idea, although not all details of the implementation, is taken from
    the Nautilus grammar-based mutation testing system (which is written in Rust and
    integrated with AFL++).
    """
    def __init__(self):
        self.chunks: dict[grammar._Symbol, list[Chunk]] = dict()
        self.seen_chunks: dict[grammar._Symbol, set[int]] = dict()

    def __str__(self):
        """Printable as an indented list"""
        lines = []
        lines.append("Chunk store:")
        for (nt, chunks) in self.chunks.items():
            lines.append(f"\t{nt}:")
            for chunk in chunks:
                lines.append(f"\t\t'{chunk.node}' ({chunk.length})")
        return '\n'.join(lines)

    def put(self, t: gen_tree.DTreeNode):
        hd = t.head
        if hd not in self.chunks:
            self.chunks[hd] = []
            self.seen_chunks[hd] = set()
        text = str(t)
        sig = hash(text)
        if sig in self.seen_chunks[hd]:
            return   ## We might consider incrementing weight
        self.seen_chunks[hd].add(sig)
        self.chunks[hd].append(Chunk(t, text))


    def get_sub(self, t: gen_tree.DTreeNode, max_len: int) -> Optional[gen_tree.DTreeNode]:
        """Fetch a potential and distinct substitute to be spliced in place of t,
        subject to a length constraint.  May return None if a good substitute
        cannot be found quickly.
        """
        if t.head not in self.chunks:
            return  None # Failed, never seen this symbol before
        sig = hash(str(t))
        candidates = []
        for sub in self.chunks[t.head]:
            if sub.length <= max_len and sub.sig != sig:
                candidates.append(sub)
        if not candidates:
            return None
        # Bias toward longer choices?   We are getting too many small trees.
        return random.choice(candidates).node

    def why_not(self, t: gen_tree.DTreeNode, max_len: int) -> str:
        """Diagnostic on why we were not able to find a suitable
        substitute for t.  Basically a copy of get_sub with explanation of
        each place it can hit a dead end.
        """
        if t.head not in self.chunks:
            return  f"There are no chunks indexed by {t.head}"
        sig = hash(str(t))
        excuses: list(str) = []
        for sub in self.chunks[t.head]:
            if sub.length > max_len:
                excuses.append(f"Too long: '{sub.node}' ({sub.length})")
            elif sub.sig == sig:
                excuses.append(f"Duplicates existing subtree: '{sub}'")
            else:
                return "What?  '{sub}' should have worked!"
            return "\n".join(excuses)



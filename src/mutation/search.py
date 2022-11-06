"""Mutation search"""
from typing import Optional, List
import pathlib
import time
import math
import enum

from mutation.weighted_choice import Scorable, Sampler
import mutation.mutator  as mutator
import mutation.gen_tree as gen_tree
import gramm.grammar
from mutation.dup_checker import History
import mutation.const_config as conf
from targetAppConnect import InputHandler


import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

SEP = ":"   # For Linux.  In MacOS you may need another character (or maybe not)

global_node_count = 0
def get_serial() -> int:
    """Returns the next serial number"""
    global global_node_count
    global_node_count += 1
    return global_node_count

def percent(portion: int, total: int) -> int:
    """Fraction as a percentage, rounded"""
    frac = portion / total
    return round(100 * frac)

# Experiment:  Candidate scores subclass Scorable to be
#    compatible with weighted_choice.Sampler
class Candidate(Scorable):
    """Sometimes called a "seed", a candidate is a derivation tree (representing an input)
    along with bookkeeping information for selecting among candidates.
    """
    def __init__(self, tree: gen_tree.DTreeNode,
                 parent: Optional["Candidate"] = None,
                 cost: int=0, reasons: str = ""):
        self.root = tree
        self.parent = parent
        self.children = []
        if self.parent:
            self.parent.add_child(self)
        self.cost = cost
        self.reasons = reasons
        self.serial = get_serial()  # Just an identifier for nodes
        # How frequently is this node good? (Score similar to UCT)
        self.count_selections = 1   # Floor 1 so we don't divide by zero
        self.count_successful = 1   # How many times has it generated a good mutant child?
        # Un-propagated versions for pseudo-child
        # (MCTS variant for extremely bushy trees in which generating all children at once
        # is not feasible.)  We consider the node to have a copy of itself as a child, so that
        # additional children can be created occasionally.
        self.count_selections_direct = 1
        self.count_successful_direct = 1

    def add_child(self, child: "Candidate"):
        self.children.append(child)

    def select(self) -> gen_tree.DTreeNode:
        """Get derivation tree and note that it has been selected"""
        self.count_selections += 1
        return self.root

    def succeed(self):
        """Note that this node was successful (updating score).
        Propagate in MCTS style. Each trial should either add to
        successes or failures.
        """
        # Non-propagating
        self.count_successful_direct += 1
        self.count_selections_direct += 1
        # Propagating
        self.propagate_success()


    def propagate_success(self):
        self.count_successful += 1
        self.count_selections += 1
        if self.parent:
            self.parent.propagate_success()

    def fail(self):
        """Note that this node was not successful (updating score).
        Propagate in MCTS style. Each trial should either add to
        successes or failures.
        """
        # Non-propagating
        self.count_selections_direct += 1
        # Propagating
        self.propagate_failure()

    def propagate_failure(self):
        self.count_selections += 1
        if self.parent:
            self.parent.propagate_failure()

    def score(self) -> float:
        """Based on UCT for MCTS, but internal nodes are also treated as
        frontier nodes since our very bushy tree precludes fully expanding
        a node in the "expand" step of MCTS.
        """
        exploit = self.count_successful / self.count_selections
        if self.parent is None:
            return exploit
        # Since we are working bottom up, the exploration component doesn't
        # influence which children will be considered, but this node itself
        # may spawn new children (including children that were not previously possible
        # because of content of chunkstore).
        parent_explored = math.log(self.parent.count_selections)
        explore = math.sqrt(parent_explored / self.count_selections_direct)
        return exploit + conf.C * explore

    def __str__(self):
        if self.parent:
            pedigree = f" <= {self.parent.count_selections} '{self.parent.root}'"
        else:
            pedigree = f" (root)"
        return (f"[{self.score():3.2}: {self.reasons} c={self.cost:4_} "
                f"{self.count_successful_direct}/{self.count_selections_direct}"
                f"{self.count_successful}/{self.count_selections}] '{self.root}'")

    def pedigree(self) -> str:
        """Full ancestry of an item"""
        if not self.parent:
            return "\n(root)"
        return f"@{self.serial} {str(self)} \n  <=  {self.parent.pedigree()}"


# Scoring factors
#    Classic UCT (also classic fuzz genetic search):  1/0, anything good or not
#    Fecundity:  Can I generate fresh inputs from this node (or from its descendants)?
#    Coverage:  Easiest, probably lowest weight positive factor
#    New max on edge: Higher weight than coverage
#    New max cost:  Highest, can we boost it farther?
#    So let's propagate a weighted score instead of a simple count. Maybe keep fecundity
#       separate for now, keep only on frontier nodes.


# Default exploration strategy is to simply iterate through the frontier.
class SimpleFrontier:
    def __init__(self):
        self.elements: list[Candidate] = []  # The whole frontier

    def __len__(self) -> int:
        return len(self.elements)

    def __str__(self):
        return "\n".join([str(c) for c in self.elements])

    def __iter__(self):
        """Iterate through the frontier.  The simplest strategy just
        iterates through the whole list in order.
        """
        return self.elements.__iter__()

    def append(self, element: Candidate):
        self.elements.append(element)


# Experiment:  Use weighted sampling based on Monte Carlo with exploration/exploitation
#   balance (variant of MCTS) in place of iteration through frontier.  We'll make it
#   look like a simple iteration, but under the hood it will prioritize nodes with
#   higher scores, including freshly generated nodes.
#
class WeightedFrontier:
    """Variant of genetic search with weighted sampling"""

    def __init__(self):
        self.elements: list[Candidate] = []  # The whole frontier
        self.fresh: list[Candidate] = []  # append puts them here, iterator pops them
        # Note that iterator has its own local lists that overlap these

    def __len__(self) -> int:
        return len(self.elements)

    def __str__(self):
        return "\n".join([str(c) for c in self.elements])

    def first_scores(self, elements: List[Candidate], n: int = 10) -> List[float]:
        """Diagnostic info on score ranges"""
        return [e.score() for e in elements[:n]]

    def __iter__(self):
        """Here is where we sneak in the weighted choice disguised as a
        simple list iteration.
        """
        # Experiment: Focus much more on hottest elements
        log.debug(f"First element scores: {self.first_scores(self.elements)}")
        eligible = sorted(self.elements, key=lambda e: 0.0 - e.score())[:conf.HOT_BUF_SIZE]
        log.debug(f"Selected first element scores: {self.first_scores(eligible)}")
        sampler = Sampler(eligible)
        draw_limit = len(eligible)
        draw_count = 0  # bumped for draws from selector only
        while draw_count < draw_limit:
            if self.fresh:
                yield self.fresh.pop()
            else:
                draw_count += 1
                yield sampler.draw()

    def append(self, element: Candidate):
        self.elements.append(element)
        self.fresh.append(element)


class Search:
    """A genetic search in the space of sentences generated by a
     context-free grammar, mutating and splicing derivation trees
     (following the key ideas of Nautilus, but not imitating it in
     all details.)
     """

    def __init__(self, gram: gramm.grammar.Grammar, logdir: pathlib.Path,
                 input_handler: InputHandler, frontier=SimpleFrontier):
        # Configuration choices (tune these empirically)
        self.n_seeds = 100  # Start with how many randomly generated sentences?
        # Resources for the search
        self.gram = gram
        self.logdir = logdir
        self.input_handler = input_handler
        self.mutator = mutator.Mutator()
        if not self.input_handler.is_connected():
            print(f"ERROR: No connection to input handler")
            exit(1)
        self.stale = History()
        # self.frontier = Frontier()   # Trees on the frontier, to be mutated
        self.frontier = frontier()
        # Characterize the search frontier
        self.max_cost = 0  # Used for determining "has new cost"
        self.max_hot = 0  # Used for determining "has new max"
        #  Stats about this search (especially for tuning configuration parameters)
        self.count_kept = 0  # Mutants that we place onto the frontier; also used to label them
        self.count_hnb = 0  # How many times did we see new coverage (by AFL bucketed criterion)
        self.count_hnm = 0  # How many times did we see a max on an edge (AFL modification)
        self.count_hnc = 0  # How many times did we see a new max total cost (AFL modification)
        self.count_attempts = 0  # Attempts to create a mutant
        self.count_splices = 0  # How many times did we create a valid splice
        self.count_mutants = 0  # Total mutants created by any means (includes splices)
        self.count_stale = 0  # Number of duplicate mutants created by any means
        self.count_valid = 0  # Valid, non-stale mutants generated by any method
        self.count_splice_progress = 0  # How many spliced mutants resulted in progress
        self.count_expand_progress = 0  # How many newly expanded mutants resulted in progress

    def summarize(self, length_limit: int, time_limit_ms: int):
        """Print summary stats.  Used in finding good settings for default
        configuration of search.  (Later we might auto-tune, but that will be slow,
        and we want to have some initial notion of what reasonable ranges might be.)
        """
        summary = self.report()
        print(summary)
        summary_path = self.logdir.joinpath("summary.txt")
        with open(summary_path, "w") as f:
            print(summary, file=f)

    def report(self) -> str:
        """
        Write a complete report to string. Can be used for slack or prints.
        """
        summary = "\n".join([str(e) for e in self.frontier])
        summary += "\n====\nPedigree of top 5 by cost\n"
        by_cost = sorted(self.frontier.elements, key=lambda e: 0 - e.cost)
        for i in range(min(5, len(by_cost))):
            summary += by_cost[i].pedigree()
            summary += "\n====\n"
        summary += f"""
            *** Summary of search ***

            Results logged to {self.logdir}
            {len(self.frontier)} nodes on search frontier
            {self.max_cost:_} highest execution cost encountered
            {self.count_hnb} ({percent(self.count_hnb, self.count_valid)}%) occurrences new coverage (AFL bucketed criterion)
            {self.count_hnm} ({percent(self.count_hnm, self.count_valid)}%) occurrences new max count on an edge (AFL mod in TreeLine and PerfFuzz)
            {self.count_hnc} ({percent(self.count_hnc, self.count_valid)}%) occurrences new max of edges executed (measure of execution cost)
            ---
            {self.count_attempts} attempts to generate a mutant
            {self.count_splices} mutants generated by splicing
            {self.count_mutants - self.count_splices} mutants generated by randomly expanding a node
            {self.count_mutants} mutants generated by splicing OR randomly expanding a node
            {self.count_stale} ({percent(self.count_stale, self.count_mutants)}%)stale mutants (duplicated previously generated string)
            {self.count_valid} ({percent(self.count_valid, self.count_mutants)}%) valid (not duplicate) mutants submitted for execution
            ---
            {self.count_splice_progress} times splicing a subtree gave progress
            {self.count_expand_progress} times regenerating a subtree gave progress
            ---

            """
        return summary

    def seed(self, n_seeds: int = 10):
        while len(self.frontier) < n_seeds:
            t = gen_tree.derive(self.gram)
            txt = str(t)
            if self.stale.is_dup(txt):
                log.debug(f"Seeding, duplicated '{txt}'")
            else:
                log.debug(f"Fresh seed '{txt}'")
                self.frontier.append(Candidate(t))
                self.mutator.stash(t)

    def search(self, length_limit: int, time_limit_ms: int):
        """One complete round of search"""
        # Classic mutation search:  Repeat cycling through examples on the frontier,
        # generating new mutants from them.  Any mutant that is new and achieves some
        # progress is added to the frontier.
        #
        search_started_ms = time.time_ns() // 1_000_000
        self.seed()
        while True:  # Until time limit
            found_good = False
            for candidate in self.frontier:
                basis = candidate.select()  # from DTreeNode to derivation
                # OK to iterate while expanding frontier per Python docs
                if (time.time_ns() // 1_000_000) - search_started_ms > time_limit_ms:
                    # Time has expired
                    return
                self.count_attempts += 1
                mutant = self.mutator.hybrid(basis, length_limit)
                if mutant is None:
                    is_a_splice = False
                    log.debug(f"Failed to hybridize '{basis}', try mutating instead")
                    mutant = self.mutator.mutant(basis, length_limit)
                else:
                    self.count_splices += 1
                    is_a_splice = True

                if mutant is None:
                    log.debug(f"Failed to mutate '{basis}'")
                    continue
                else:
                    self.count_mutants += 1

                if self.stale.is_dup(str(mutant)):
                    log.debug(f"Mutant '{mutant}' is stale")
                    self.count_stale += 1
                    continue
                self.count_valid += 1
                log.debug(f"Generated valid mutant to test: '{mutant}'")
                self.stale.record(str(mutant))

                tot_cost, new_bytes, new_max, hot_spot = self.input_handler.run_input(str(mutant))
                log.debug(f"cost: {tot_cost}  new_bytes: {new_bytes} new_max: {new_max}  hot_spot: {hot_spot}")
                ##
                # Any reason to record this mutant at all?
                if not (tot_cost > self.max_cost
                        or hot_spot > self.max_hot
                        or new_max or new_bytes):
                    candidate.fail()
                    continue
                # We will keep this for some reason.  We need to log
                # it.
                found_good = True
                self.count_kept += 1
                candidate.succeed()  # This was a good candidate!
                suffix = ""
                if tot_cost > self.max_cost:
                    log.info(f"New total cost {tot_cost} for '{mutant}")
                    self.max_cost = tot_cost
                    self.count_hnc += 1
                    suffix += "+cost"
                elif hot_spot > self.max_hot:
                    log.info(f"New hot spot {hot_spot} for '{mutant}'")
                    self.max_hot = hot_spot
                    self.count_hnm += 1
                    suffix += "+max"
                elif new_max or new_bytes:
                    log.info(f"New coverage or edge max for '{mutant}'")
                    self.count_hnb += 1
                    suffix += "+cov"
                self.frontier.append(Candidate(mutant, parent=candidate, cost=tot_cost, reasons=suffix))

                found_time_ms = time.time_ns() // 1_000_000
                elapsed_time_ms = found_time_ms - search_started_ms
                label = (f"id{SEP}{self.count_kept:08}-cost{SEP}{tot_cost:010}-exec{SEP}{self.count_valid:08}"
                         + f"-crtime{SEP}{found_time_ms}-dur{SEP}{elapsed_time_ms}{suffix}")
                result_path = self.logdir.joinpath(label)
                with open(result_path, "w") as saved_input:
                    print(str(mutant), file=saved_input)

                # Concurrent with iteration, so we may mutate the mutant
                # before finishing this scan of the frontier!
                self.mutator.stash(mutant)
                if is_a_splice:
                    self.count_splice_progress += 1
                else:
                    self.count_expand_progress += 1

            if not found_good:
                log.info(f"Complete cycle without generating a good mutant")




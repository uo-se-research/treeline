"""Grammar fuzzing with mutant search to find performance issues.

The approach is based on Nautilus:
    - We maintain derivation trees, not (just) strings generated by the grammar.
    - A "chunk store" keeps subtrees previously generated.  (We store all and only
    subtrees that have either achieved new coverage or a greater individual edge count
    after warming up with some random trees).
    - A tree may be mutated by "splicing" a previously generated subtree at any non-terminal
    symbol.

Some differences from Nautilus, because we are looking for performance issues:
    - A "good" sentence may be one that executes some control flow edge more than has been
    previously observed (even if the edge is not being executed for the first time or a new
    bucket of counts a la AFL).  Nautilus looks for new coverage and does not judge an edge
    execution count of 313 to be significant if we have already seen an edge execution count of 311.
    (In this we follow PerfFuzz.)
    - We limit the length of generated sentences.  Finding new edge counts because the input is longer
    is not interesting when looking for performance is
    - For the same reason, we do not attempt to minimize inputs, as most coverage-based fuzzers do.
    - We do not apply string mutations like Havoc.  "Almost correct" input may be very useful for finding
    security bugs, but for performance problems we want to generate (to the extent practical) correct inputs.

Other differences and possible differences from Nautilus:
    - The input grammars are more restrictive.  Nautilus supports Python scripts in place of CFG constructs.
    We support standard context-free grammars (though specified in an extended BNF).
    - When we cannot find a suitable splice, we result to generating a new random subtree
    - We have not carefully studied Natilus's tactics for managing the "interesting" trees,
    and have probably not replicated it precisely.  Our approach is based more on AFL,
    which simply iterates through all previously found "good" trees.
"""
import io

import context

# For logging results:
import datetime
import time
import pathlib
import os

import mutation.mutator  as mutator
import mutation.gen_tree as gen_tree
import gramm.llparse
from gramm.char_classes import CharClasses
from gramm.unit_productions import UnitProductions
from mutation.dup_checker import History

# from mutation.fake_runner import InputHandler  # STUB
from targetAppConnect import InputHandler    # REAL

import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

import argparse

SEP = ":"   # For Linux.  In MacOS you may need another character (or maybe not)


class Search:
    """A genetic search in the space of sentences generated by a
     context-free grammar, mutating and splicing derivation trees
     (following the key ideas of Nautilus, but not imitating it in
     all details.)
     """

    def __init__(self, gram: gramm.grammar.Grammar, logdir: pathlib.Path):
        # Configuration choices (tune these empirically)
        self.n_seeds = 100  # Start with how many randomly generated sentences?
        # Resources for the search
        self.gram = gram
        self.logdir = logdir
        self.input_handler = InputHandler()
        self.mutator = mutator.Mutator()
        if not self.input_handler.is_connected():
            print(f"ERROR: No connection to input handler")
            exit(1)
        self.stale = History()
        self.frontier: list[mutation.gen_tree.DTreeNode] = []   # Trees on the frontier, to be mutated
        # Characterize the search frontier
        self.max_cost = 0    # Used for determining "has new cost"
        self.max_hot = 0     # Used for determining "has new max"
        #  Stats about this search (especially for tuning configuration parameters)
        self.count_kept = 0  # Mutants that we place onto the frontier; also used to label them
        self.count_hnb = 0   # How many times did we see new coverage (by AFL bucketed criterion)
        self.count_hnm = 0   # How many times did we see a max on an edge (AFL modification)
        self.count_hnc = 0   # How many times did we see a new max total cost (AFL modification)
        self.count_attempts = 0  # Attempts to create a mutant
        self.count_splices = 0  # How many times did we create a valid splice
        self.count_mutants = 0  # Total mutants created by any means (includes splices)
        self.count_stale = 0   # Number of duplicate mutants created by any means
        self.count_valid = 0   # Valid, non-stale mutants generated by any method
        self.count_splice_progress = 0 # How many spliced mutants resulted in progress
        self.count_expand_progress = 0  # How many newly expanded mutants resulted in progress


    def summarize(self):
        """Print summary stats.  Used in finding good settings for default
        configuration of search.  (Later we might auto-tune, but that will be slow,
        and we want to have some initial notion of what reasonable ranges might be.)
        """
        print("*** Summary of search ***")
        print(f"Results logged to {self.logdir}")
        print(f"{len(self.frontier)} nodes on search frontier")
        print(f"{self.max_cost} highest execution cost encountered")
        print(f"{self.count_hnb} occurrences new coverage (AFL bucketed criterion)")
        print(f"{self.count_hnm} occurrences new max count on an edge (AFL mod in TreeLine and PerfFuzz)")
        print(f"{self.count_hnc} occurrences new max of edges executed (measure of execution cost)")
        print("---")
        print(f"{self.count_attempts} attempts to generate a mutant")
        print(f"{self.count_splices} mutants generated by splicing")
        print(f"{self.count_mutants - self.count_splices} mutants generated by randomly expanding a node")
        print(f"{self.count_mutants} mutants generated by splicing OR randomly expanding a node")
        print(f"{self.count_stale} stale mutants (duplicated previously generated string)")
        print(f"{self.count_valid} valid (not duplicate) mutants submitted for execution")
        print("---")
        print(f"{self.count_splice_progress} times splicing a subtree gave progress")
        print(f"{self.count_expand_progress} times regenerating a subtree gave progress")

    def seed(self, n_seeds: int = 10):
        while len(self.frontier) < n_seeds:
            t = gen_tree.derive(self.gram)
            txt = str(t)
            if self.stale.is_dup(txt):
                log.debug(f"Seeding, duplicated '{txt}'")
            else:
                log.debug(f"Fresh seed '{txt}'")
                self.frontier.append(t)
                self.mutator.stash(t)

    def search(self, length_limit: int, time_limit_ms: int):
        """One complete round of search"""
        # Classic mutation search:  Repeat cycling through examples on the frontier,
        # generating new mutants from them.  Any mutant that is new and achieves some
        # progress is added to the frontier.
        #
        search_started_ms = time.time_ns() // 1_000_000
        self.seed()
        while True:   # FIXME: Should this be "while (True)" for a time-limited run?
            found_good = False
            for basis in self.frontier:
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
                if self.test_mutant(str(mutant), search_started_ms):
                    found_good = True
                    self.frontier.append(mutant)
                    # Concurrent with iteration, so we may mutate the mutant
                    # before finishing this scan of the frontier!
                    self.mutator.stash(mutant)
                    if is_a_splice:
                        self.count_splice_progress += 1
                    else:
                        self.count_expand_progress += 1

                if not found_good:
                    log.debug(f"Complete cycle without generating a good mutant")


    def test_mutant(self, mut: str, start_time: int) -> bool:
        """Tests a valid mutant,
        True if it is good (new coverage, new max, etc)
        side effect writes record of good mutant to output
        FIXME:  Make this fit the format that TreeLine uses
        """
        tot_cost, new_bytes, new_max, hot_spot = self.input_handler.run_input(mut)
        log.info(f"cost: {tot_cost}  new_bytes: {new_bytes} new_max: {new_max}  hot_spot: {hot_spot}")
        ##
        # Any reason to record this mutant at all?
        if not(tot_cost > self.max_cost
                or hot_spot > self.max_hot
                or new_max or new_bytes):
            return False
        # We will keep this for some reason.  We need to log
        # it.
        self.count_kept += 1
        suffix = ""
        if tot_cost > self.max_cost:
            log.debug(f"New total cost {tot_cost} for '{mut}")
            self.max_cost = tot_cost
            self.count_hnc += 1
            suffix += "+cost"
        elif hot_spot > self.max_hot:
            log.debug(f"New hot spot {hot_spot} for '{mut}'")
            self.max_hot = hot_spot
            self.count_hnm += 1
            suffix += "+max"
        elif new_max or new_bytes:
            log.debug(f"New coverage or edge max for '{mut}'")
            self.count_hnb += 1
            suffix += "+max"

        found_time_ms = time.time_ns() // 1_000_000
        elapsed_time_ms = found_time_ms - start_time
        label = (f"id{SEP}{self.count_kept:08}-cost{SEP}{tot_cost:010}-exec{SEP}{self.count_valid:08}"
            + f"-crtime{SEP}{found_time_ms}-dur{SEP}{elapsed_time_ms}{suffix}")
        result_path = self.logdir.joinpath(label)
        with open(result_path, "w") as saved_input:
            print(mut, file=saved_input)
        return True

       # FIXME:  Main program should pass directory named by MCTS conventions,
        #   app:APPNAME-desc:nautilike-gram:GRAMNAME
        #   and here we should save each generated input to a file that looks like
        # id:000001,cost:0000069485,hs:0000004068,hnb:2,exec:1,len:006,tu:006,crtime:1651191586707,dur:5+cov+max+cost
        # but we don't need all the keys, just
        # 		Must Have keys:
        # 		id: is the input id relative to the saved inputs.
        # 		exec: is the input id relative to all the executed inputs.
        # 		crtime: creation time which is an integer of milliseconds since the epoch. Can be found using this simple statement time.time_ns() // 1_000_000.
        # 		dur: The duration of finding this input since the beginning of the search process in milliseconds. Using the same statement from crtime above to save the time at which the search process started (call it start ), then dur is (time.time_ns() // 1_000_000) - start.

def ready_grammar(f) -> gramm.grammar.Grammar:
    gram = gramm.llparse.parse(f, len_based_size=True)
    gram.finalize()
    xform = UnitProductions(gram)
    xform.transform_all_rhs(gram)
    xform = CharClasses(gram)
    xform.transform_all_rhs(gram)
    return gram

def cli() -> object:
    """Command line interface, including information for logging"""
    parser = argparse.ArgumentParser(description="Mutating and splicing derivation trees")
    parser.add_argument("app", type=str,
                        help="Application name, e.g., graphviz")
    parser.add_argument("grammar", type=str,
                        help="Path to grammar file")
    parser.add_argument("directory", type=str,
                        help="Root directory for experiment results")
    parser.add_argument("--length", type=int, default=60,
                        help="Upper bound on generated sentence length")
    parser.add_argument("--seconds", type=int, default=60 * 60,
                        help="Timeout in seconds, default 3600 (60 minutes)")
    parser.add_argument("--tokens", help="Limit by token count",
                        action="store_true")
    return parser.parse_args()


def create_result_directory(root: str, app: str, gram_name: str) -> pathlib.Path:
    """root should be a path to an existing writeable directory.
    Returns path to a writeable "list" subdirectory within a labeled subdirectory within root.
    May throw exception if directories cannot be created!
    """
    now = datetime.datetime.now()
    ident = f"app{SEP}{app}-gram{SEP}{gram_name}-crtime{SEP}{int(time.time())}"
    exp_path = pathlib.Path(root).joinpath(ident)
    os.mkdir(exp_path)
    list_path = exp_path.joinpath("list")
    list_dir = os.mkdir(list_path)
    log.info(f"Logging to {list_dir}")
    return list_path


def main():
    args = cli()
    length_limit: int = args.length
    gram_path = pathlib.Path(args.grammar)
    gram_name = gram_path.name
    gram = ready_grammar(open(args.grammar, "r"))
    timeout_ms = args.seconds * 1000
    logdir = create_result_directory(args.directory, args.app, gram_name)
    search = Search(gram, logdir)
    search.search(length_limit, timeout_ms)
    search.summarize()


if __name__ == "__main__":
    main()





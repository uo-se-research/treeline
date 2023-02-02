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
    and have probably not replicated it precisely.  Our breadth-first search is based
    more on AFL, which simply iterates through all previously found "good" trees.
    (However we winnow similarly to Nautilus, periodically discarding inputs whose virtue
    has been superseded, e.g., they were initially retained for reasons of coverage but since
    then other retained inputs cover the same behavior.)
"""

import datetime
import time
import pathlib
import os

import grammfuzz_configure

import gramm.llparse
import mutation.search
from gramm.char_classes import CharClasses
from gramm.unit_productions import UnitProductions
# import mutation.search_config as search_config
import mutation.search as search

from targetAppConnect import InputHandler    # REAL

import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.WARN)

import slack

import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

import argparse

SEP = ":"   # For Linux.  In MacOS you may need another character (or maybe not)

def ready_grammar(f) -> gramm.grammar.Grammar:
    gram = gramm.llparse.parse(f, len_based_size=True)
    gram.finalize()
    xform = UnitProductions(gram)
    xform.transform_all_rhs(gram)
    xform = CharClasses(gram)
    xform.transform_all_rhs(gram)
    return gram



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


def slack_message(m: str):
    slack.post_message_to_slack(f"{m}")


def slack_command(c: str):
    slack.post_message_to_slack(f"```\n{c}\n```")


def main():
    settings = grammfuzz_configure.configure()
    mutation.search.init(settings)
    length_limit: int = settings["length"]
    gram_path = pathlib.Path(settings["gram_file"])
    gram_name = settings["gram_name"]
    app_name = settings["app_name"]
    gram = ready_grammar(open(gram_path, "r"))
    seconds = int(settings["seconds"])
    timeout_ms = seconds * 1000
    number_of_exper = int(settings["runs"])
    report_to_slack = bool(settings["slack"])
    search_strategy = settings["FRONTIER"]
    log.info(f"Experiment {seconds} seconds with {settings['search']}")
    for run_id in range(1, number_of_exper+1):
        logdir = create_result_directory(settings['directory'],
                                         app_name, gram_name)
        if report_to_slack:
            slack_message(f"New mutant run #{run_id} out of {number_of_exper}.")
            slack_message(f"Configs: length=`{length_limit}`, gram_path=`{gram_path}`, gram_name=`{gram_name}`, "
                          f"duration(s)=`{settings['seconds']}`, logdir=`{settings['']}`, "
                          f"tokens=`{settings['tokens']}`, frontier=`{settings.string_val('FRONTIER')}`")
        searcher = search.Search(gram, logdir,
                                 InputHandler(settings['FUZZ_SERVER'],
                                              settings['FUZZ_PORT']),
                                 frontier=settings['FRONTIER']
                                 )
        searcher.search(length_limit, timeout_ms)
        searcher.summarize(length_limit, timeout_ms)
        if report_to_slack:
            slack_message(f"Run #{run_id} finished!")
            slack_command(searcher.brief_report())
        record_path = logdir.parent.joinpath("report.txt")
        record = open(record_path, 'w')
        print(searcher.full_report(), file=record)
        record.close()
        settings_path = logdir.parent.joinpath("settings.yaml")
        settings_record = open(settings_path, 'w')
        print(settings.dump_yaml(), file=settings_record)
        settings_record.close()





if __name__ == "__main__":
    main()





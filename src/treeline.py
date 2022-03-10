__author__ = "Ziyad Alsaeed"
__email__ = "zalsaeed@cs.uoregon.edu"
__status__ = "Testing"

import os
import csv
import argparse
import logging
from datetime import datetime

from gramm.llparse import *
from gramm.grammar import FactorEmpty
from mcts.monte_carlo_tree_search import MonteCarloTreeSearch


if __name__ == "__main__":

    current_time = datetime.now().strftime('%Y%m%d-%H%M%S')
    log_dir = os.path.join(os.path.dirname(__file__), os.pardir, 'logs/')

    # define arguments
    parser = argparse.ArgumentParser(description="Command line utility for MCTS.")
    parser.add_argument("gram_file", type=str, help="The grammar file which can only be of type txt, gram, or any text "
                                                    "based file.")
    parser.add_argument("-desc", type=str, default="", help="A task description to identify the run logs if needed.")
    parser.add_argument("-i", action="store_true", help="Run an experiment based on specified number of iterations "
                                                        "instead of time")
    parser.add_argument("-iters", type=int, default=100_000, help="The number of iterations to run in a search "
                                                                  "assuming it is an iteration based.")
    parser.add_argument("-time", type=int, default=1, help="The duration for the search. Assuming it is a time based "
                                                           "job (default).")
    parser.add_argument("-b", type=int, default=60, help="The allowed budget for an input (aka target app max input "
                                                         "size).")
    parser.add_argument("-c", type=int, default=1.5, help="The constant value for UCT formula.")
    parser.add_argument("-e", type=int, default=20, help="The number of visit to a node before we expand it.")
    parser.add_argument("-lock", action='store_true', help="Lock nodes if they get fully explored.")
    parser.add_argument("-sim", action='store_true', help="Turn on simulation at the end.")
    parser.add_argument("-tree", action='store_true', help="Print tree at the end of the search.")
    parser.add_argument("-log_level", type=str, default="INFO",
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help="Set the logging level for root logger")
    parser.add_argument("-log_to_file", action='store_true', help="Log to file instead of stdout?")
    parser.add_argument("-r", action='store_true', help="A flag to add result from this experiment to the report file.")

    # get arguments
    args = parser.parse_args()

    log_level = {"DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARNING": logging.WARNING, "ERROR": logging.ERROR,
                 "CRITICAL": logging.CRITICAL}

    if args.log_level not in log_level:
        raise ValueError(f"Logging level must be one of Python's logger levels {log_level}. Got {args.log_level}")

    # set up logger
    for handler in logging.root.handlers[:]:  # make sure all handlers are removed
        logging.root.removeHandler(handler)
    logging.root.setLevel(log_level[args.log_level])
    logging_format = logging.Formatter('%(asctime)s: %(levelname)s [%(name)s:%(funcName)s:%(lineno)d] - %(message)s')
    if args.log_to_file:
        h = logging.FileHandler(f'{log_dir}MCTS-{os.path.basename(args.gram_file)}-{current_time}.log')
        h.setFormatter(logging_format)
        logging.root.addHandler(h)
    else:
        h = logging.StreamHandler()
        h.setFormatter(logging_format)
        logging.root.addHandler(h)

    # validate gram file
    if not args.gram_file.rpartition('.')[-1] == 'txt':
        raise ValueError(f"Grammar file must be of type .txt. Got {args.gram_file}")

    # build grammar
    gram = parse(open(args.gram_file, 'r'))
    xform = FactorEmpty(gram)
    xform.transform_all_rhs(gram)

    MonteCarloTreeSearch.change_globals("C", args.c)
    MonteCarloTreeSearch.change_globals("E", args.e)

    # build mcts obj and run a search
    mcst = MonteCarloTreeSearch(gram, budget=args.b)
    mcst.warm_up()
    mcst.search(num_iter=args.iter)

    # if true, run a simulation of the best path
    if not args.no_sim:
        mcst.simulate()

    if args.tree:  # if asked to print the tree
        tree_file = open(f"{log_dir}Tree-{os.path.basename(args.gram_file)}-{current_time}-iter:{args.iter}.log", "w")
        tree_file.write(mcst.get_tree())
        tree_file.close()

    # prepping the output file name and gram file
    gram_file_full_name = os.path.basename(args.gram_file)
    file_name_prefix = gram_file_full_name.split('.')[0]
    target_app_name = file_name_prefix.split('-')[1]

    # getting dict report and adding high-level info (e.g. date, gram file).
    report = mcst.get_report()
    report['date/time'] = str(current_time)
    report['grammar file'] = str(gram_file_full_name)

    # logging high-level info for this experiment in the target app file
    if args.r:
        report_file = f"{log_dir}experiments-info-{target_app_name}.csv"
        if os.path.exists(report_file):
            with open(report_file, "a") as e_file:
                writer = csv.writer(e_file)
                values = [*report.values()]
                writer.writerow(values)
        else:
            with open(report_file, "a") as e_file:
                writer = csv.writer(e_file)
                header = [*report.keys()]
                writer.writerow(header)  # header (should only be written once)
                values = [*report.values()]
                writer.writerow(values)

    for k, v in report.items():
        print(f"{k}: {v}")



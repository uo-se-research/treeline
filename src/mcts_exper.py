import os
import csv
import platform
import psutil
from itertools import product
from datetime import datetime

import graphviz

import slack
import helpers as helper
from pygramm.llparse import *
from pygramm.grammar import FactorEmpty
import mcts.mcts_globals as mg  # MCTS globals
from mcts.mcts import MonteCarloTreeSearch

if __name__ == "__main__":

    # dirname(dirname(file)) gives you the parent dir
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs/')
    current_time = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')

    # args
    # WF
    gram_file = [
        "../target_apps/word-frequency/grammars/gram-wf-simple.txt",
        "../target_apps/word-frequency/grammars/wf-arvada.gram",
    ]

    # libxml2
    # gram_file =[
    #     "../target_apps/libxml2/grammars/gram-libxml2-free-typing.txt",
    #     "../target_apps/libxml2/grammars/libxml-arvada.gram",
    # ]

    # graphviz
    # gram_file = [
    #     "../target_apps/graphviz/grammars/parser-based.txt",
    #     "../target_apps/graphviz/grammars/graphviz-arvada.gram",
    # ]

    # flex
    # gram_file = [
    #     "../target_apps/flex/grammars/flex.gram",
    #     "../target_apps/flex/grammars/flex-limited.gram",
    #     "../target_apps/flex/grammars/flex-arvada.gram",
    # ]

    # lunaSVG
    # gram_file = [
    #     "../target_apps/lunasvg/grammars/svg.gram",
    #     "../target_apps/lunasvg/grammars/svg-limited.gram",
    #     "../target_apps/lunasvg/grammars/lunasvg-arvada.gram",
    # ]

    app_name = "wf"  # graphviz, wf, dc, libxml2, quicksort, insertion_sort, sqlite
    expr_desc = "icse"  # DO NOT USE "-" to separate words
    number_of_repetitions = 1  # how many times should we repeat a given experiment configuration?
    save_tree_as_binary = False  # save the  tree as a binary in a .tree file in case we want to load it again
    write_tree_to_file_as_text = False  # print the tree as text to txt file?
    generate_tree_vis = False  # generate a tree vis as PDF?
    log_to_file = True  # should we log to file or stream
    report_to_slack = False  # only official runs should report to slack

    # combination of parameter to run
    mutable_param = dict(
        c=[1.5],  # exploration
        e=[20],  # visits before expansion
        budget=[60],  # budget allowed for an input
        is_time_based=[True],  # are running based on time or iterations?
        time_cap_in_h=[1],  # if based on time, how long in hours are we allowed to run?
        num_iter=[50],  # if based on iterations, what is the number of search iteration planned?
        reward_type=['quantile'],  # 'prc', 'smoothed', 'log', 'binary', 'quantile'
        grams=gram_file,
        algorithm=['lcc'],  # 'mcts', 'leaf-pruning-mcts', 'root-pruning-mcts', 'coverage-based-mcts', 'lcc', 'lcc-conv'
        use_locking=[True],
        use_bias=[True],
        max_reward=[100],
        tail_len=[25000],
        max_cutting_threshold=[0.9],  # or 0.5
        threshold_decay_rate=[0.00005]  # Max=0.5, Decay=0.00001 was good for WF
    )

    # set up logger
    for handler in logging.root.handlers[:]:  # make sure all handlers are removed
        logging.root.removeHandler(handler)
    # in some cases the logging level will change to DEBUG based on what happens in search, but in general this is the
    # logging level we want
    logging_level = logging.WARNING
    logging.root.setLevel(logging_level)
    logging_format = logging.Formatter('%(asctime)s: %(levelname)s [%(name)s:%(funcName)s:%(lineno)d] - %(message)s')

    # collecting system info
    available_mem = psutil.virtual_memory().total / 1_073_741_824
    cpu_cores = psutil.cpu_count()
    hosting_os = platform.platform()

    params = [v for v in mutable_param.values()]

    number_of_experiments = sum(1 for e in product(*params))  # count number of comp
    comp = 0
    print(f"We have {number_of_experiments} experiment configuration to run!")
    for c, e, budget, is_time_based, time_cap_in_h, num_iter, reward_type, gram_used, alg,\
            locking, bias, max_reward, tail_len, max_cutting_threshold, threshold_decay_rate in product(*params):
        comp += 1
        gram_base_file_name = os.path.basename(gram_used)
        for r in range(number_of_repetitions):
            date = datetime.now().date().strftime("%m/%d/%Y")
            time = datetime.now().time().strftime("%H:%M:%S")
            print("====================================================")
            exper_info = f"Experiment Info:\n ```\ngram={gram_base_file_name}, algorithm={alg}, c={c}, e={e}, " \
                         f"locking={locking}, bias={bias}, budget={budget}, reward-type={reward_type}, " \
                         f"reward-max={max_reward}, " \
                         f"tail-len={tail_len}, max-cutting-threshold={max_cutting_threshold}," \
                         f"threshold-decay-rate={threshold_decay_rate:f}, time-based?={is_time_based}, " \
                         f"time-cap-h={time_cap_in_h} iter={num_iter}\n```"
            run_seq = f"This is combination {comp} of {number_of_experiments}. And this is run {r+1} of "\
                      f"{number_of_repetitions}."
            print(exper_info)
            print(run_seq)
            print("====================================================")
            if report_to_slack:
                slack.post_message_to_slack(f"New Experiment [date: {date}, time: {time}]")
                slack.post_message_to_slack(run_seq)
                slack.post_message_to_slack(exper_info)

            # updating MCTS globals for all
            mg.C = c
            mg.E = e

            expr_desc_with_id = "" if expr_desc == "" else f"desc:{expr_desc}-"  # if one is given prep for file name
            duration_info = f"time_based(h={time_cap_in_h})" if is_time_based else f"iter_based(iter={num_iter})"
            bias_ind = 'T' if bias else "F"
            locking_ind = 'T' if locking else "F"
            expr_identifier = f"app:{app_name}-{expr_desc_with_id}alg:{alg}-" \
                              f"gram:{gram_base_file_name.replace('-', '_')}-c:{mg.C}-e:{mg.E}-" \
                              f"BDG:{budget}-rType:{reward_type}-rMax:{max_reward}-bias:{bias_ind}-" \
                              f"tail:{tail_len}-unqMax:{max_cutting_threshold}-unqGrwRate:{threshold_decay_rate:f}-" \
                              f"lock:{locking_ind}-DUR:{duration_info}-" \
                              f"date:{date.replace('/', '')}-time:{time.replace(':','')}"
            output_dir = f"{log_dir}{expr_identifier}/"
            os.makedirs(output_dir)

            # make sure all handlers are removed
            for handler in logging.root.handlers[:]:
                logging.root.removeHandler(handler)

            if log_to_file:
                # File logging:
                h = logging.FileHandler(f'{output_dir}traces.log')
                h.setFormatter(logging_format)
                logging.root.addHandler(h)
            else:
                # Stream logging:
                h = logging.StreamHandler()
                h.setFormatter(logging_format)
                logging.root.addHandler(h)

            # build grammar
            gram = parse(open(gram_used, 'r'), len_based_size=True)
            xform = FactorEmpty(gram)
            xform.transform_all_rhs(gram)

            # print gram info after parsing and adjusting costs
            with open(f"{output_dir}gram-with-cost.txt", "w") as file:
                file.write(gram.dump())

            mcts = MonteCarloTreeSearch(gram=gram,
                                        output_dir=output_dir,
                                        expr_id=expr_identifier,
                                        budget=budget,
                                        reward_type=reward_type,
                                        use_locking=locking,
                                        use_bias=bias,
                                        tail_len=tail_len,
                                        max_threshold=max_cutting_threshold,
                                        threshold_decay=threshold_decay_rate)

            if not mcts.dry_run():  # skip any experiment we cannot warmup for within allowed time.
                continue

            # use the specified algorithm to do the search
            if alg == 'lcc':
                mcts.treeline(is_time_based, time_cap_h=time_cap_in_h, num_iter=num_iter)
            elif alg == 'random':
                mcts.random_search(is_time_based, time_cap_h=time_cap_in_h, num_iter=num_iter)
            else:
                raise RuntimeError(f"Unknown algorithm {alg}")

            # run a simulation of the best path
            # mcts.simulate()

            # save the tree as binary
            if save_tree_as_binary:
                print("Saving tree as binary ...")
                mcts.save_tree()

            # print the tree to file
            if write_tree_to_file_as_text:
                print("Saving tree as text ...")
                with open(f"{output_dir}Tree.txt", "w") as tree_file:
                    tree_file.write(mcts.get_tree())

            if generate_tree_vis:
                print("Rendering the tree based on dot file ...")
                g = graphviz.Source(helper.tree_to_dot(mcts.root))
                g.render(filename=f"{output_dir}TreeVis", format="pdf", cleanup=True)

            # getting dict report and adding high-level info (e.g. date, gram file, etc).
            report = mcts.get_report()
            report['Period: Run date-time'] = str(date) + "-" + str(time)
            report['Config: grammar file'] = str(gram_base_file_name)
            report['Env: available mem'] = str(available_mem)
            report['Env: cpu cores'] = str(cpu_cores)
            report['Env: os'] = str(hosting_os)
            report['Config: Target App'] = app_name   # TODO: can we get this from the runner itsefl?
            report['Config: Expr Description'] = expr_desc  # TODO: do we need it?
            report['Config: Search Algorithm'] = alg

            # logging high-level info for this experiment in the target app file
            print("Logging high-level info of this target app ...")
            print(f"Max cost observed: {report['Results: Max Observed Cost']}")
            report_file = f"{log_dir}experiments-info-{app_name}.csv"
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

            # write final stats to file
            print("Write high-level stats to file ...")
            with open(f"{output_dir}config-and-stats-report.txt", "w") as report_file:
                stats_summery = helper.beautify_final_report(report)
                report_file.write(stats_summery)

            if report_to_slack:
                slack.post_message_to_slack(f"Experiment Ended (it started at {date}, {time}). "
                                            f"Here are some stats:\n\n```\n{stats_summery}\n```\n")

            mcts.close_connection()

            # make sure the logging level is set-back to INFO for the next run
            logging.root.setLevel(logging_level)

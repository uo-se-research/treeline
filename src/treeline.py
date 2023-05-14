__author__ = "Ziyad Alsaeed"
__email__ = "zalsaeed@cs.uoregon.edu"
__status__ = "Testing"

import os
import csv
import platform
import argparse
from itertools import product
from datetime import datetime

import psutil
import graphviz

import slack
import helpers as helper
import configuration_loader
import mcts.mcts_globals as mg  # MCTS globals
from pygramm.llparse import *
from pygramm.grammar import FactorEmpty
from mcts.mcts import MonteCarloTreeSearch


if __name__ == "__main__":

    current_time = datetime.now().strftime('%Y%m%d-%H%M%S')

    # define arguments
    parser = argparse.ArgumentParser(description="Command line utility for MCTS.")
    parser.add_argument("-settings", type=str, default="defaults.yaml", help="The file for search main settings.")
    parser.add_argument("-o", "--output", type=str, default="/tmp/treeline", help="The output directory where all "
                                                                                  "inputs will be saved.")
    parser.add_argument("--slack", action='store_true', help="Report run to slack (require channel integration).")

    # get arguments
    args = parser.parse_args()

    config_file = os.path.abspath(args.settings)

    # Get global settings from yaml file.
    settings = configuration_loader.Settings()
    settings.read_yaml(open(config_file))

    log_level = {"DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARNING": logging.WARNING, "ERROR": logging.ERROR,
                 "CRITICAL": logging.CRITICAL}

    if settings["log_level"] not in log_level:
        raise ValueError(f"Logging level must be one of Python's logger levels {log_level}. Got {args.log_level}")

    # set up logger
    for handler in logging.root.handlers[:]:  # make sure all handlers are removed
        logging.root.removeHandler(handler)
    logging.root.setLevel(log_level[settings["log_level"]])
    logging_format = logging.Formatter('%(asctime)s: %(levelname)s [%(name)s:%(funcName)s:%(lineno)d] - %(message)s')

    # the run settings that are permutable
    mutable_param = dict(
        c=settings["c"],  # exploration
        e=settings["e"],  # visits before expansion
        budget=settings["budget"],  # budget allowed for an input
        is_time_based=settings["is_time_based"],  # are running based on time or iterations?
        time_cap_in_h=settings["time"],  # if based on time, how long in hours are we allowed to run?
        num_iter=settings["total_iter"],  # if based on iterations, what is the number of search iteration planned?
        reward_type=settings['reward_type'],  # the reward strategy
        grams=settings["gram_file"],
        algorithm=settings["algorithm"],  # The search algorithm to use
        use_locking=settings["lock"],
        use_bias=settings["use_bias"],
        max_reward=settings["max_reward"],
        tail_len=settings["tail_len"],
        max_cutting_threshold=settings["max_cutting_threshold"],
        threshold_decay_rate=settings["threshold_decay_rate"]
    )

    immutable_params = dict(  # Collect run info
        app_name=settings["app_name"],  # TODO: We should get this from the app run command
        expr_desc=settings["desc"].__str__().replace("-", ""),  # "-" Are not allowed
        number_of_repetitions=settings["number_of_repetitions"],
        save_tree_as_binary=settings["save_tree_as_binary"],
        write_tree_to_file_as_text=settings["write_tree_to_file_as_text"],
        generate_tree_vis=settings["generate_tree_vis"],
        sim=settings['sim'],
        tree=settings['tree'],
        report=settings['report'],
        log_to_file=settings["log_to_file"],
    )

    # collecting system info
    available_mem = psutil.virtual_memory().total / 1_073_741_824
    cpu_cores = psutil.cpu_count()
    hosting_os = platform.platform()

    params = [v for v in mutable_param.values()]

    number_of_experiments = sum(1 for e in product(*params))  # count number of comb
    combination_id = 0
    print(f"There are {number_of_experiments} experiment(s) configuration to run!")

    root_output_dir = os.path.abspath(args.output)
    print(f"Saving result to '{root_output_dir}'")

    for c, e, budget, is_time_based, time_cap_in_s, num_iter, reward_type, gram_used, alg,\
            locking, bias, max_reward, tail_len, max_cutting_threshold, threshold_decay_rate in product(*params):
        combination_id += 1
        time_cap_in_h = time_cap_in_s / 3600
        gram_base_file_name = os.path.basename(gram_used)
        for r in range(immutable_params["number_of_repetitions"]):
            date = datetime.now().date().strftime("%m/%d/%Y")
            time = datetime.now().time().strftime("%H:%M:%S")
            print("====================================================")
            exper_info = f"Experiment Info:\n ```\ngram={gram_base_file_name}, algorithm={alg}, c={c}, e={e}, " \
                         f"locking={locking}, bias={bias}, budget={budget}, reward-type={reward_type}, " \
                         f"reward-max={max_reward}, " \
                         f"tail-len={tail_len}, max-cutting-threshold={max_cutting_threshold}," \
                         f"threshold-decay-rate={threshold_decay_rate:f}, time-based?={is_time_based}, " \
                         f"time-cap-h={time_cap_in_h} iter={num_iter}\n```"
            run_seq = f"This is combination {combination_id} of {number_of_experiments}. And this is run {r+1} of "\
                      f"{immutable_params['number_of_repetitions']}."
            print(exper_info)
            print(run_seq)
            print("====================================================")
            if args.slack:
                slack.post_message_to_slack(f"New Experiment [date: {date}, time: {time}]")
                slack.post_message_to_slack(run_seq)
                slack.post_message_to_slack(exper_info)

            # updating MCTS globals for all
            mg.C = c
            mg.E = e

            # if one is given prep for file name
            expr_desc_with_id = "" if immutable_params['expr_desc'] == "" else f"desc:{immutable_params['expr_desc']}-"
            duration_info = f"time_based(h={time_cap_in_h})" if is_time_based else f"iter_based(iter={num_iter})"
            bias_ind = 'T' if bias else "F"
            locking_ind = 'T' if locking else "F"
            expr_identifier = f"app:{immutable_params['app_name']}-{expr_desc_with_id}alg:{alg}-" \
                              f"gram:{gram_base_file_name.replace('-', '_')}-c:{mg.C}-e:{mg.E}-" \
                              f"BDG:{budget}-rType:{reward_type}-rMax:{max_reward}-bias:{bias_ind}-" \
                              f"tail:{tail_len}-unqMax:{max_cutting_threshold}-unqGrwRate:{threshold_decay_rate:f}-" \
                              f"lock:{locking_ind}-DUR:{duration_info}-" \
                              f"date:{date.replace('/', '')}-time:{time.replace(':','')}"
            output_dir = os.path.join(root_output_dir, expr_identifier)
            os.makedirs(output_dir)

            # make sure all handlers are removed
            for handler in logging.root.handlers[:]:
                logging.root.removeHandler(handler)

            if immutable_params['log_to_file']:
                # File logging:
                h = logging.FileHandler(f'{output_dir}/traces.log')
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
            if alg == 'treeline':
                mcts.treeline(is_time_based, time_cap_h=time_cap_in_h, num_iter=num_iter)
            elif alg == 'random':
                mcts.random_search(is_time_based, time_cap_h=time_cap_in_h, num_iter=num_iter)
            else:
                raise RuntimeError(f"Unknown algorithm {alg}")

            # run a simulation of the best path
            if immutable_params['sim']:
                mcts.simulate()

            # save the tree as binary
            if immutable_params['save_tree_as_binary']:
                print("Saving tree as binary ...")
                mcts.save_tree()

            # print the tree to file
            if immutable_params['write_tree_to_file_as_text']:
                print("Saving tree as text ...")
                with open(f"{output_dir}Tree.txt", "w") as tree_file:
                    tree_file.write(mcts.get_tree())

            if immutable_params['generate_tree_vis']:
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
            report['Config: Target App'] = immutable_params['app_name']
            report['Config: Expr Description'] = immutable_params['expr_desc']
            report['Config: Search Algorithm'] = alg

            # logging high-level info for this experiment in the target app file
            print("Logging high-level info of this target app ...")
            print(f"Max cost observed: {report['Results: Max Observed Cost']}")
            report_file = f"{root_output_dir}/experiments-info-{immutable_params['app_name']}.csv"
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

            # merge the configurations The server options (not in use yet) | immutable option | mutable options based
            # on this run.
            exper_configurations = dict(FUZZ_SERVER="localhost", FUZZ_PORT=2300) | immutable_params | dict(
                log_level=settings['log_level'],
                c=[c],  # exploration
                e=[e],  # visits before expansion
                budget=[budget],  # budget allowed for an input
                is_time_based=[is_time_based],  # are running based on time or iterations?
                time_cap_in_h=[time_cap_in_s],  # if based on time, how long in hours are we allowed to run?
                num_iter=[num_iter],  # if based on iterations, what is the number of search iteration planned?
                reward_type=[reward_type],  # the reward strategy
                grams=[gram_used],
                algorithm=alg,  # The search algorithm to use
                use_locking=[locking],
                use_bias=[bias],
                max_reward=[max_reward],
                tail_len=[tail_len],
                max_cutting_threshold=[max_cutting_threshold],
                threshold_decay_rate=[threshold_decay_rate],
            )

            # save configurations to file for re-run
            configuration_loader.Settings.dump_yaml_from_dict(exper_configurations, f"{output_dir}/configurations.yaml")

            if args.slack:
                slack.post_message_to_slack(f"Experiment Ended (it started at {date}, {time}). "
                                            f"Here are some stats:\n\n```\n{stats_summery}\n```\n")

            mcts.close_connection()

            # make sure the logging level is set-back to whatever the user chose for the next run
            # FIXME, where did we change the log level to need this?
            logging.root.setLevel(log_level[settings["log_level"]])

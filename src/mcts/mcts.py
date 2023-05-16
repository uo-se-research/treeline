__author__ = "Ziyad Alsaeed"
__email__ = "zalsaeed@cs.uoregon.edu"
__status__ = "Testing"

import os
import gc
import time
import random
import pickle as cpickle
import datetime
import collections
from typing import Tuple
from itertools import count

import numpy as np
import psutil
from tdigest import TDigest

import helpers as helper
from pygramm.llparse import *
from pygramm.grammar import Grammar
import mcts.mcts_globals as mg  # MCTS globals
from mcts.mctsnode import MCTSNode


class MonteCarloTreeSearch:
    """Monte Carlo tree searcher.

    :param gram: The grammar used to search for expensive input in the target application.
    :param output_dir: The directory where all the inputs generated and logs should be saved
    :param expr_id: A unique identifier for the experiment that should help the user find this run.
    :param budget: The allowed maximum budget regardless of how the budget is defined.
    :param reward_type: The reward function to be used in this search.
    :param use_locking: If True, any node that is exhausted will be locked from future visits
        (i.e., as if it doesn't exist anymore).
    :param use_bias: If True, the rollouts will use the bias function instead of completely random search.
    :param cost_reward_scaling: The initial cost reward scaling.
    :param tail_len: A tail size used to check for tree stabilization (reset or not) and uniqueness
    :param max_threshold: Used to establish an epsilon strategy for tree dropping threshold.
    :param threshold_decay: Used to establish an epsilon strategy for tree dropping threshold.
    """

    def __init__(self, gram: Grammar, output_dir: str, expr_id: str, budget: int, reward_type: str,
                 use_locking: bool = False, use_bias: bool = False, cost_reward_scaling: int = 1,
                 tail_len: int = 5000, max_threshold: float = 0.5, threshold_decay: float = 0.0001):
        """
        The initializer of the TreeLine  and BiasOnly algorithms.
        """
        self.log = logging.getLogger(self.__class__.__name__)

        self.output_dir = output_dir
        self.expr_id = expr_id
        self.use_locking = use_locking
        self.use_bias = use_bias
        self.cost_reward_scaling = cost_reward_scaling
        self.gram = gram
        self.allowed_budget = budget
        self.reward_type = reward_type
        self.root = MCTSNode(budget=self.allowed_budget, text="", stack=[self.gram.start], tokens=0,
                             use_locking=use_locking)
        self.root.start_connection()  # TODO: do we have to establish connection while the MCTSnode does it?
        self.current = self.root

        # reward adjustment variables
        self.digest = TDigest()
        self.len_weight = 0.1  # the length base weight within a reward.
        self.len_buffer = collections.deque(maxlen=100)  # inputs observed lengths buffer.
        self.is_raw_len_based_reward = False  # whether we should use the raw len value within the reward or not.
        self.decided_to_always_go_with_full_input_len = False  # necessary to force first tree dropping.
        self.weight_len_increase_skip_counter = 0  # a counter to track how many times we reach the len weight ceiling.

        # tree reset tracking and reporting variables
        self.exec_since_last_reset = 0
        self.reset_counter = 1
        self.tail_len = tail_len  # a tail size used to check for tree stabilization (reset or not) and uniqueness
        self.max_threshold = max_threshold
        self.threshold_decay = threshold_decay

        # statistical and tracking variables.
        self.count_of_anomalous_runs = 0
        self.max_observed_cost = 0
        self.min_observed_cost = 0
        self.max_observed_hotspot = 0

        # collect initial information for the final report.
        self.report_dict = collections.defaultdict(str)
        self.report_dict['Globals: E (# of visits before expansion)'] = str(mg.E)
        self.report_dict['Globals: C (exploration variable)'] = str(mg.C)
        self.report_dict['Globals: Extensive Data Tracking?'] = str(mg.extensive_data_tracking)
        self.report_dict['Config: Cost Reward Scaling Value'] = str(self.cost_reward_scaling)
        self.report_dict['Config: Budget'] = str(self.allowed_budget)
        self.report_dict['Config: Uniqueness tail size'] = str(self.tail_len)
        self.report_dict['Config: Lock Fully Observed Nodes?'] = str(self.use_locking)
        self.report_dict['Config: Use Bias?'] = str(self.use_bias)
        self.report_dict['Config: Tree-Dropping Max Threshold'] = str(max_threshold)
        self.report_dict['Config: Tree-Dropping Decay Rate'] = str(threshold_decay)
        self.report_dict['Config: Grammar name'] = str(gram.gram_name)
        self.report_dict['Stats: # total rollouts'] = str(0)
        self.report_dict['Stats: # total expansions'] = str(0)
        self.report_dict['Stats: # total edges'] = str(0)

    def dry_run(self) -> bool:
        """The root must have an empty string as text. Usually an empty string is the minimalist cost value possible.
        We use it to define the min_cost of the target app that would help adjust the tail length. Also, we use it to
        distinguish anomalous runs. Moreover, this method help us check if we can run the target app or not.

        :return: True if we ran the app successfully and collected the base data, or False otherwise.
        """
        found_input, ac, _, _, _, _ = self.root.dummy_run()
        self.min_observed_cost = ac

        # anything below 80% of the min cost is an anomalous run
        mg.TARGET_APP_MIN_POSSIBLE_COST = self.min_observed_cost

        return True

    def treeline(self, is_time_based: bool, time_cap_h=1, num_iter=100):
        """
        The main method to run (train) the algorithm. An iteration is a derivation that starts from the root node. Any
        derivation would end at a terminal. However, the reach of the terminal could be based on the tree observed UCB1
        values or random (rollout).

        :param is_time_based: A boolean to make the run based on either time cap (True) or num of iteration (False).
        :param num_iter: The maximum number of derivations (target app runs) that are allowed.
        :param time_cap_h: The maximum time allowed for a run in hours.
        """

        buffer_dir = f"{self.output_dir}buffer/"  # dir to track cov and max inputs
        os.makedirs(buffer_dir)

        # tracking variables
        rollouts = 0
        expansions = 0
        edges = 0
        input_id = 0
        execution_costs = []

        """
        The progress_report is dictionary to track as much numerical information as possible with each step. This will
        only be used if the global variable for data tracking (extensive_data_tracking) is set to True. The information
        stored in the dictionary will be written to disc at the end of the run. The flag extensive_data_tracking should
        only be set to True if you're interested in extensively analysing how the algorithm is progressing during the
        search process at each step. Otherwise, it should be disabled for performance.
        """
        progress_report = collections.defaultdict(list)

        # TreeLine related variables
        hot_nodes: List[MCTSNode] = []  # hot_nodes of all hnb, hnm, or hnc non-terminal nodes.
        top_n_hot_nodes: List[MCTSNode] = []  # top n nodes from hot_nodes given their UCT value at some point
        hot_node_prop_threshold = 0.5  # the probability of selecting a node from the hot_nodes vs. using the root node

        print()  # make a space for the progress bar (info).
        expr_max_time = datetime.timedelta(hours=time_cap_h)  # maximum possible time in case of time-based runs
        start = time.time_ns() // 1_000_000  # get time in milliseconds from epoch to label inputs.
        expr_start_time = datetime.datetime.now()  # expr start time in case of time-based run.

        # ready to search for expensive input
        for i in count(1):  # this will loop forever. We check for break condition at the end based on duration base.

            self.current = self.root  # let make sure we have a node to do a search

            # update the top n hot-nodes every 500 iterations.
            if i % 500 == 0:
                top_n_hot_nodes = list(helper.top_n(hot_nodes, n=10, key=lambda n: n.get_ucb1()))

            # with some probability larger than the hot-node threshold,
            # either keep the root node or select the best node from top n hot_nodes
            if random.random() > hot_node_prop_threshold:
                if top_n_hot_nodes:
                    self.current = max(top_n_hot_nodes, key=lambda n: n.get_ucb1())

            # get uniqueness and prep for check to drop the tree if ready
            uniqueness_percentage = 1.0 if self.exec_since_last_reset < self.tail_len \
                else helper.find_prc_uniq_values(execution_costs[-self.tail_len:])

            refresh_threshold = 1 - helper.get_exploration_rate(self.exec_since_last_reset, self.threshold_decay, 1,
                                                                1-self.max_threshold)

            # progress bar (info) prints (different for time vs. iter based).
            helper.progress_bar(is_time_based=is_time_based, start_time=expr_start_time, iter_counter=i,
                                num_rollouts=rollouts, num_expansions=expansions, num_edges=edges,
                                num_hot_nodes=len(hot_nodes), max_reward=self.cost_reward_scaling,
                                refresh_threshold=refresh_threshold, uniqueness_per=uniqueness_percentage,
                                tail_len=self.tail_len, len_reward_weight=self.len_weight, total_allowed_iter=num_iter)

            self.log.debug(f"Iter: {i}")

            # OK, now we have some node and would like to travers the tree based on the UCB1 value.
            while not self.current.is_leaf():  # a leaf node is either a terminal node or a non-expanded node yet.
                best_child = self._select()
                self.current = best_child

            # if all nodes are expanded, and we reach a terminal node, ask for app execution to get the cost
            if self.current.is_terminal():
                final_input, ac, hnb, hnm, hs, is_anomalous = self.current.run()
                tokens_used = self.current.tokens_used

                # update the bias if we are using it.
                # TODO: The terminal node is a special case, but can we update the bias only in one place?
                if self.use_bias:
                    if ac > self.max_observed_cost or hnb or hnm:
                        self.current.bias.reward()
                    else:
                        self.current.bias.penalize()

                # we never want to visit this node again if possible
                if self.use_locking and not is_anomalous:
                    self.current.locked = True

            # the node is not terminal, but it is not expandable yet (new).
            elif self.current.is_new():
                final_input, ac, hnb, hnm, hs, is_anomalous, tokens_used = self.rollout()  # do a rollout from current
                rollouts += 1

            else:  # the node is not terminal and not new, expand it then do a rollout from one of its children.
                edges += self.expand()
                expansions += 1
                self.current = self.current.get_children()[0]  # set first child as current as all of them are new
                final_input, ac, hnb, hnm, hs, is_anomalous, tokens_used = self.rollout()

            # Now evaluate the run we did. If there is a cov increase then mark the node accordingly regardless if the
            # run is anomalous or not. We cannot do this at the node itself as doesn't have visibility of the overall
            # cost.
            if hnb:  # not 0 (we don't care either 1 or 2)
                self.current.set_hnb(hnb)
            if hnm:
                self.current.set_hnm(hnm)
            hnh = self.has_new_hotspot(hs)  # calling it updates the known max hs in treeline side.
            if hnh:
                self.current.set_hotspot(hs)
            hnc = self.has_new_cost(ac)  # calling it updates the known max cost in treeline side

            # shall we add the current node to hot_nodes?
            if not self.current.is_terminal():  # no value of adding terminals to hot-nodes
                if (hnb or hnm or hnc) and self.current not in hot_nodes:
                    hot_nodes.append(self.current)

            # if the run is anomalous, make a note but don't back-propagate any info based on wrong run!
            if is_anomalous:
                self.count_of_anomalous_runs += 1  # make sure we track this incident
            else:
                self.exec_since_last_reset += 1
                # first back-propagate from current node given the reward.
                reward = self._get_reward(cost=ac, input_len=tokens_used)
                self._backpropagate(reward)

                # log the run info for debugging with high priority to hnc as we want to always see it
                log_message = f"hnb:{hnb}, hnm:{int(hnm)}, hnc:{int(hnc)}, hnh:{int(hnh)}, hs:{hs:010d}, "\
                              f"cost:{ac:010d}, reward:{reward:02f}, len:{len(bytes(final_input, 'utf-8'))}," \
                              f" anomalous:{int(is_anomalous)}, input:{final_input.encode()}"
                if hnc:
                    self.log.warning(log_message)  # not actually a warning, but this will make it standout
                else:
                    self.log.info(log_message)

                end = time.time_ns() // 1_000_000  # get time in milliseconds from epoch. Tracking input generation time
                elapsed_time = end - start

                # append the cost for uniqueness check
                execution_costs.append(ac)

                # track the run info in dict for detailed analysis if desired.
                if mg.extensive_data_tracking:
                    # collect this iter information
                    temp_progress_data = {'execution_cost': ac, 'iter': i, 'duration': elapsed_time,
                                          'rollouts': rollouts, 'expansions': expansions, 'edges': edges,
                                          'reward': reward, 'hnb': hnb, 'hnm': int(hnm), 'hs': hs,
                                          'hot_nodes': len(hot_nodes), 'tokens_used': tokens_used,
                                          'refresh_threshold': refresh_threshold,
                                          'uniqueness_percentage': uniqueness_percentage, 'tail_len': self.tail_len,
                                          'len_weight': self.len_weight}
                    # append it to each corresponding key in the progress report
                    for key, value in temp_progress_data.items():
                        progress_report[key].append(value)

            # main tracker: save inputs if interesting (we don't save all inputs).
            if hnb or hnm or hnc:
                cur_ms = time.time_ns() // 1_000_000
                input_id += 1
                helper.save_input(generated_input=final_input, hnb=bool(hnb), hnm=hnm, hnc=hnc, hs=hs, ac=ac,
                                  tokens_used=tokens_used, output_dir=buffer_dir, input_id=input_id, exec_count=i,
                                  cur_ms=cur_ms, dur=cur_ms-start)

            # Tree-Dropping-Case-1: evaluate if the current tree should be dropped based on stabilization
            if self.exec_since_last_reset >= self.tail_len:  # did we give it enough runs according to the tail?
                if self.has_stabilized(uniqueness_percentage):  # did it stabilize?

                    # track progress for general experiment stats that is printed at the end.
                    self.save_tree_info_to_report(rollouts=rollouts, expansions=expansions, edges=edges,
                                                  num_hot_nodes=len(hot_nodes), reset_counter=self.reset_counter,
                                                  number_of_executions=self.exec_since_last_reset)

                    hot_nodes.clear()  # clear the lcc hot_nodes
                    rollouts = expansions = edges = 0  # resetting tree ops tracking variables
                    execution_costs = []
                    self._reset()  # now we can drop the tree and start a new one.

            # Tree-Dropping-Case-2: evaluate if the current tree should be dropped based on a drastic change on the
            # reward function. This should only happen (if any) once in for each run.
            if self.decided_to_always_go_with_full_input_len:
                self.decided_to_always_go_with_full_input_len = False

                # track progress for general experiment stats that is printed at the end.
                self.save_tree_info_to_report(rollouts=rollouts, expansions=expansions, edges=edges,
                                              num_hot_nodes=len(hot_nodes), reset_counter=self.reset_counter,
                                              number_of_executions=self.exec_since_last_reset)

                hot_nodes.clear()  # clear the lcc hot_nodes
                rollouts = expansions = edges = 0  # resetting tree ops tracking variables
                execution_costs = []
                self._reset()  # now we can drop the tree and start a new one.

            # checking if we should break the loop based on duration base configuration
            if is_time_based:
                if datetime.datetime.now() - expr_start_time > expr_max_time:
                    print("\nDone searching based on time!")
                    break
            else:
                if i >= num_iter:
                    print("\nDone searching based on # of iterations!")
                    break

        # make sure we reset the root to the gram original root at the end of the search.
        self.current = self.root

        end = time.time_ns() // 1_000_000  # get time in milliseconds from epoch.
        elapsed_time = end - start
        print(f"Elapsed time: {elapsed_time / 60_000} minutes")

        # final addition to the general report
        self.report_dict['Period: Run duration(ms)'] = str(elapsed_time)
        self.report_dict['Period: Run duration(s)'] = str(elapsed_time/1_000)
        self.report_dict['Period: Run duration(m)'] = str(elapsed_time/60_000)
        self.report_dict['Period: Run duration(h)'] = str(elapsed_time/3_600_000)
        self.report_dict['Duration-Config: Is Duration based on Time?'] = str(is_time_based)
        self.report_dict['Duration-Config: Time allowed in hours'] = str(time_cap_h)
        self.report_dict['Duration-Config: # of iterations'] = str(num_iter)
        self.report_dict['Results: Max Observed Cost'] = "{:,}".format(self.max_observed_cost)
        self.report_dict['Results: Max Observed Hotspot'] = "{:,}".format(self.max_observed_hotspot)
        self.report_dict['Dynamics: final Uniqueness Tail Len'] = str(self.tail_len)
        self.report_dict['Dynamics: final Cost Reward Scaling Value'] = str(self.cost_reward_scaling)
        self.report_dict['Dynamics: Target App Min Possible Cost'] = str(mg.TARGET_APP_MIN_POSSIBLE_COST)
        self.save_tree_info_to_report(rollouts=rollouts, expansions=expansions, edges=edges,
                                      num_hot_nodes=len(hot_nodes), reset_counter=self.reset_counter,
                                      number_of_executions=self.exec_since_last_reset)

        # save the bias table for reference (regardless if it is used or not)
        with open(f"{self.output_dir}bias.txt", "w") as bias_file:
            bias_file.write(self.root.bias.__str__())

        # write the last known tree to file TODO: should we write all trees (before dropping them)?
        if mg.extensive_data_tracking:
            self.write_tree_to_file_as_dot()

        # if we collected the progress data, write it to file with full experiment information for reference.
        if mg.extensive_data_tracking:
            helper.write_dict_to_csv(data=progress_report, output_dir=self.output_dir,
                                     file_name=f"progress-report",
                                     comments=f"grammar: {self.gram.gram_name}, budget: {self.allowed_budget}, "
                                              f"total-iter: {num_iter}, c: {mg.C}, e: {mg.E}, "
                                              f"duration(ms): {elapsed_time}, "
                                              f"total rollouts: {int(self.report_dict['Stats: # total rollouts'])}, "
                                              f"total expansions: "
                                              f"{int(self.report_dict['Stats: # total expansions'])}, "
                                              f"total edges: {int(self.report_dict['Stats: # total edges'])}, "
                                              f"total anomalous runs: {self.count_of_anomalous_runs}, "
                                              f"Starting node threshold: {hot_node_prop_threshold}")

    def random_search(self, is_time_based: bool, time_cap_h=1, num_iter=100):
        """
        The main method to run (train) the algorithm. An iteration is a derivation that starts from the root node. Any
        derivation would end at a terminal. However, the reach of the terminal could be based on the tree observed UCB1
        values or random (rollout).

        :param is_time_based: A boolean to make the run based on either time cap (True) or num of iteration (False).
        :param num_iter: The number of derivations we would like to do from root to terminal.
        :param time_cap_h: The maximum time allowed for a run in hours.
        """
        # dir to track cov and max inputs:
        buffer_dir = f"{self.output_dir}buffer/"
        os.makedirs(buffer_dir)

        # tracking variables
        rollouts = 0
        input_id = 0

        """
         The progress_report is dictionary to track as much numerical information as possible with each step. This will
         only be used if the global variable for data tracking (extensive_data_tracking) is set to True. The information
         stored in the dictionary will be written to disc at the end of the run. The flag extensive_data_tracking should
         only be set to True if you're interested in extensively analysing how the algorithm is progressing during the
         search process at each step. Otherwise, it should be disabled for performance.
         """
        progress_report = collections.defaultdict(list)

        print()  # make a space for the progress bar (info).
        expr_max_time = datetime.timedelta(hours=time_cap_h)  # maximum possible time in case of time-based runs
        start = time.time_ns() // 1_000_000  # get time in milliseconds from epoch to label inputs.
        expr_start_time = datetime.datetime.now()  # expr start time in case of time-based run.

        # ready to search for expensive input
        for i in count(1):  # this will loop forever. We check for break condition at the end based on duration base.

            self.current = self.root  # always start from the root

            # progress bar (info) prints (different for time vs. iter based). Should be in its own function!
            helper.progress_bar(is_time_based=is_time_based, start_time=expr_start_time, iter_counter=i,
                                num_rollouts=rollouts, max_reward=self.cost_reward_scaling,
                                len_reward_weight=self.len_weight, total_allowed_iter=num_iter)

            self.log.debug(f"Iter: {i}")

            # The current node = the root node, we do random search (no UCT eval just random rollout).
            final_input, ac, hnb, hnm, hs, is_anomalous, tokens_used = self.rollout()  # do a rollout from current
            rollouts += 1

            # Did we encounter a new hotspot or cost?
            hnh = self.has_new_hotspot(hs)  # calling it updates the known max hs
            hnc = self.has_new_cost(ac)  # calling has_new_cost(x) updates the known max cost

            self.exec_since_last_reset += 1

            # log the run info for debugging with high priority to hnc as we want to always see it
            log_message = f"hnb:{hnb}, hnm:{int(hnm)}, hnc:{int(hnc)}, hnh:{int(hnh)}, hs:{hs:010d}, cost:{ac:010d}, " \
                          f"len:{len(bytes(final_input, 'utf-8'))}, anomalous:{int(is_anomalous)}, " \
                          f"input:{final_input.encode()}"

            if hnc:
                self.log.warning(log_message)  # not actually a warning, but this will make it standout
            else:
                self.log.info(log_message)

            end = time.time_ns() // 1_000_000  # get time in milliseconds from epoch. Tracking input generation time
            elapsed_time = end - start

            # track the run info in dict for detailed analysis if desired.
            if mg.extensive_data_tracking:
                # collect this iter information
                temp_progress_data = {'execution_cost': ac, 'iter': i, 'duration': elapsed_time,
                                      'rollouts': rollouts, 'hnb': hnb, 'hnm': int(hnm), 'hs': hs,
                                      'tokens_used': tokens_used, 'tail_len': self.tail_len,
                                      'len_weight': self.len_weight}
                # append it to each corresponding key in the progress report
                for key, value in temp_progress_data.items():
                    progress_report[key].append(value)

            # main tracker: save inputs if interesting (we don't save all inputs).
            if hnb or hnm or hnc:
                cur_ms = time.time_ns() // 1_000_000
                input_id += 1
                helper.save_input(generated_input=final_input, hnb=bool(hnb), hnm=hnm, hnc=hnc, hs=hs, ac=ac,
                                  tokens_used=tokens_used, output_dir=buffer_dir, input_id=input_id, exec_count=i,
                                  cur_ms=cur_ms, dur=cur_ms-start)

            # checking if we should break the loop based on duration base configuration
            if is_time_based:
                if datetime.datetime.now() - expr_start_time > expr_max_time:
                    print("\nDone searching based on time!")
                    break
            else:
                if i >= num_iter:
                    print("\nDone searching based on # of iterations!")
                    break

        # make sure we reset the root to the gram original root at the end of the search.
        self.current = self.root

        end = time.time_ns() // 1_000_000  # get time in milliseconds from epoch.
        elapsed_time = end - start
        print(f"Elapsed time: {elapsed_time / 60_000} minutes")

        # track reportable values before exiting
        self.report_dict['Period: duration(ms)'] = str(elapsed_time)
        self.report_dict['Period: duration(s)'] = str(elapsed_time/1_000)
        self.report_dict['Period: duration(m)'] = str(elapsed_time/60_000)
        self.report_dict['Period: duration(h)'] = str(elapsed_time/3_600_000)
        self.report_dict['Duration-Config: Is Duration based on Time?'] = str(is_time_based)
        self.report_dict['Duration-Config: Time allowed in hours'] = str(time_cap_h)
        self.report_dict['Duration-Config: # of iterations'] = str(num_iter)
        self.report_dict['Results: max cost'] = "{:,}".format(self.max_observed_cost)
        self.report_dict['Results: max hotspot'] = "{:,}".format(self.max_observed_hotspot)
        self.report_dict['Dynamics: final tail len'] = str(self.tail_len)
        self.report_dict['Dynamics: final Cost Reward Scaling Value'] = str(self.cost_reward_scaling)
        self.save_tree_info_to_report(rollouts=rollouts, expansions=0, edges=0, num_hot_nodes=0,
                                      reset_counter=self.reset_counter, number_of_executions=self.exec_since_last_reset)

        # save the bias table for reference (regardless if it is used or not)
        with open(f"{self.output_dir}bias.txt", "w") as bias_file:
            bias_file.write(self.root.bias.__str__())

        # Write the last known tree to file
        if mg.extensive_data_tracking:
            self.write_tree_to_file_as_dot()

        # if we collected the progress data, write it to file with full experiment information for reference.
        if mg.extensive_data_tracking:
            helper.write_dict_to_csv(progress_report, self.output_dir, f"progress-report-{self.expr_id}",
                                     comments=f"grammar: {self.gram.gram_name}, budget: {self.allowed_budget}, "
                                              f"total-iter: {num_iter}, c: {mg.C}, e: {mg.E}, "
                                              f"duration(ms): {elapsed_time}, "
                                              f"total rollouts: {int(self.report_dict['Stats: # total rollouts'])}, "
                                              f"total expansions: "
                                              f"{int(self.report_dict['Stats: # total expansions'])}, "
                                              f"total edges: {int(self.report_dict['Stats: # total edges'])}, "
                                              f"total anomalous runs: {self.count_of_anomalous_runs}")

    def _reset(self):
        """
        Dropping the tree and creating a fresh one based on the grammar and other permanent parameters.
        """
        print(f"\nResetting the env (#{self.reset_counter}) ...")
        # ask how much memory used
        if mg.extensive_data_tracking:
            self.log.warning(f"Resetting tree | memory used: {psutil.virtual_memory().percent}% ...")

        # LOG: export the tree we have to dot before dropping it.
        if mg.extensive_data_tracking:
            self.write_tree_to_file_as_dot()

        # To carry the bias between trees
        bias_temp = self.root.bias

        # delete all traces of the tree
        del self.root
        del self.current
        self.log.warning(f"Deleted all tree nodes | memory used: {psutil.virtual_memory().percent}% ...")

        # garbage collect as a safety check
        gc.collect()
        self.log.warning(f"Did explicit gc | memory used: {psutil.virtual_memory().percent}% ...")

        # finally re-populate the tree root given the grammar.
        self.root = MCTSNode(budget=self.allowed_budget, text="", stack=[self.gram.start], tokens=0,
                             use_locking=self.use_locking, bias=bias_temp)
        self.original_root = self.root  # necessary for the root pruning only
        self.current = self.root
        if mg.extensive_data_tracking:
            self.log.warning("Done resetting!")

        if not self.is_raw_len_based_reward and self.reset_counter == 1:
            print(f"The length reward weight is set to: {self.len_weight}")
        # self.exec_count_since_last_increase = 0
        self.exec_since_last_reset = 0
        self.reset_counter += 1

    def adjust_cost_reward_scaling(self):
        """
        The cost reward scaling has to be changed depending on the target application size. For micro applications the
        edge count between and empty input and the most expensive input can be in few hundreds if not less. While in
        macro to large application a modest input can have a significant difference in edge count compared to trivial
        empty input. Therefore, in the case of micro application web blow up the cost by multiplying it by 100 to allow
        our algorithm to distinguish between extreme and normal cases while we use the cost as is if the edge hits
        difference is large enough by itself.
        """
        diff = self.max_observed_cost - self.min_observed_cost
        if diff/self.min_observed_cost > 1.0:
            self.cost_reward_scaling = 1
        else:
            self.cost_reward_scaling = 100

    def adjust_tail_len(self):
        """
        A function that adjusts the tail length based on a newly observed max or min. This should only be called when
        the max/min is adjusted.
        """
        new_range = self.max_observed_cost - self.min_observed_cost
        idx = np.digitize(new_range, bins=mg.buckets)
        self.tail_len = mg.tails[idx]

    def has_new_cost(self, cost: int) -> bool:
        """
        Check with the cost passed is a new maximum cost or not and adjust all the tracking variables accordingly
        if it demonstrates a new maximum.

        :param cost: The new cost to evaluate.
        :return: True if the cost passed is a new maximum and False otherwise.
        """
        if cost > self.max_observed_cost:
            self.max_observed_cost = cost

            # Adjusting the tail len because we changed the known max cost.
            self.adjust_tail_len()

            # we got a new max. Is the reward scaling still good for the new range?
            self.adjust_cost_reward_scaling()

            return True
        else:
            # self.exec_count_since_last_increase += 1
            return False

    def has_new_hotspot(self, hotspot) -> bool:
        """
        Check with the hotspot value passed is a new maximum or not and adjust all the tracking variables accordingly
        if it demonstrates a new maximum.
        :param hotspot: The value observed for the hotspot.
        :return: True if the hotspot passed is a new maximum and False otherwise.
        """
        if hotspot > self.max_observed_hotspot:
            self.max_observed_hotspot = hotspot
            return True
        else:
            return False

    def _select(self) -> MCTSNode:
        """
        Choose the best successor of current node (choose a move). Can't be called on a terminal or unexpanded nodes.

        :return: The best child node of the current node.
        """
        if self.current.is_terminal():
            raise RuntimeError(f"Trying to select a a child node from the terminal node {self.current}")

        if not self.current.get_children():
            raise RuntimeError(f"The current node {self.current} has no populated children to select from.")

        return max(self.current.get_children(), key=lambda node: node.get_ucb1())

    def rollout(self, warmup=False) -> Tuple[str, int, int, bool, int, bool, int]:
        """
        Expand the tree from the current node until you reach terminal node either randomly or using the bias.

        :return: Run information of the generated input (text, ac, hnb, hnm, hs, is_anomalous, tokens_used).
        """
        s_i = self.current
        while not s_i.is_terminal():
            if mg.extensive_data_tracking:
                self.log.debug(f"Node: {s_i}")
            s_j = s_i.select_random_child(using_bias=self.use_bias)
            s_i = s_j
            if mg.extensive_data_tracking:
                self.log.debug(f"Token-Count: {s_i.tokens_used}")
                self.log.debug("-----------------------------------------------------------")
        if mg.extensive_data_tracking:
            self.log.debug(f"Final (s_i): {s_i}")
            self.log.debug("===========================================================")

        if (self.allowed_budget - s_i.tokens_used) != s_i.budget:
            # at a terminal state, the difference between allowed budget and number of used terminal tokens
            # MUST equal the remaining budget
            raise RuntimeError(f"Wrong budget use! Allowed-Budget={self.allowed_budget}, Tokens-Used={s_i.tokens_used},"
                               f"Terminal-State-Remaining-Budget={s_i.budget}. Node: {s_i}")

        text, ac, hnb, hnm, hs, is_anomalous = s_i.run(warmup=warmup)

        # update the bias if we are using it
        if self.use_bias:
            if ac > self.max_observed_cost or hnb or hnm:
                s_i.bias.reward()
            else:
                s_i.bias.penalize()

        return text, ac, hnb, hnm, hs, is_anomalous, s_i.tokens_used

    def expand(self) -> int:
        """
        Populate the children of the current node.

        :return: The number of valid children populated.
        """
        if not self.current.is_terminal():
            self.current.populate_children()
        else:
            raise RuntimeError(f"This is an un-expandable node {self.current}")

        return self.current.get_num_of_children()

    def _backpropagate(self, reward: float):
        """
        Send the reward back up to the ancestors of the current. The back-propagation updates both the reward found
        from the execution and the count of visits. The count is implicits here (taken care of by the update function).

        :param reward: The reward observed at the current node (rolling out to terminal or itself being a terminal).
        """
        self.current.update(reward)  # make sure we update the current first
        s = self.current
        while s.has_a_parent():
            s_parent = s.parent
            s_parent.update(reward)
            s = s_parent

    def _get_reward(self, cost: int, input_len: int) -> float:
        """
        Get the reward based on the len and cost of the input generated. The len weight changes within the first
        established tree. Moreover, if thr adjust_len_weight determines that we should use the actual len value, then
        the weight is disregarded.

        :param cost: The execution cost of the input.
        :param input_len: The input len regardless of base used (bytes, chars, or tokens)
        :return: The reward of the input based on the reward formula at the time of calling this method as well as the
        other hyper-parameters values.
        """

        if self.reset_counter <= 1:  # we only adjust the reward function on the first tree
            self.adjust_len_weight(input_len)

        # using tdigest as found here https://github.com/CamDavidsonPilon/tdigest
        cost_reward = self.digest.cdf(cost)  # we get the reward before we update the quantile
        self.digest.update(cost)

        if self.is_raw_len_based_reward:
            return cost_reward + input_len
        else:
            len_reward = helper.scale_to_range(input_len, self.allowed_budget, 0, 0, 1)
            return (cost_reward * (1 - self.len_weight) * self.cost_reward_scaling) + len_reward * self.len_weight

    def adjust_len_weight(self, input_len: int):
        """
        A method to adjust the length weight according to our formula. In a nutshell, the weight is decreased or
        increased by 0.0001 depending on whether 50% of the observed inputs are within the top 20% of the budget
        allowance.
        """
        change_factor = .0001
        self.len_buffer.append(input_len)
        if not self.is_raw_len_based_reward:  # and if we settle for raw, that's it, never going back
            if len(self.len_buffer) == self.len_buffer.maxlen:  # only when we have enough samples
                top_20_prc = int(0.8 * self.allowed_budget)
                if helper.get_prc_of_value_above_threshold(list(self.len_buffer), top_20_prc) < .5:
                    if self.len_weight < 0.9:  # hitting the max
                        self.len_weight += change_factor
                    else:
                        self.weight_len_increase_skip_counter += 1
                    if self.weight_len_increase_skip_counter > self.len_buffer.maxlen * 5:  # extreme case
                        self.is_raw_len_based_reward = True
                        self.decided_to_always_go_with_full_input_len = True
                        self.len_weight = float("inf")
                else:
                    if self.len_weight > 0.1:
                        self.len_weight -= change_factor

    def save_tree(self):
        """
        Save the current tree to file.
        """
        with open(f"{self.output_dir}/{self.expr_id}.tree", "wb") as file_:
            cpickle.dump(self.original_root, file_)

    def load_tree(self, file_name: str):
        """
        Load tree from file.
        :param file_name: The tree file name.
        """
        if not os.path.isfile(file_name):
            raise RuntimeError(f"The string given {file_name} is not a file!")
        if not file_name.endswith(".tree"):
            raise RuntimeError(f"The file must be of type tree")
        with open(file_name, "rb") as input_file:
            self.root = cpickle.load(input_file)
        self.root = self.original_root

    def write_tree_to_file_as_dot(self):
        """
        Write tree to file in dot language for post-search visualization.
        """
        tree_dir = f"{self.output_dir}trees/"
        if not os.path.exists(tree_dir):
            os.makedirs(tree_dir)
        with open(f"{tree_dir}{self.reset_counter:02d}-TreeVis.dot", "w") as tree_file:
            tree_file.write(helper.tree_to_dot(self.root))

    def print_tree(self):
        """
        From the root node, print the tree found thus far.
        """
        print(helper.tree_state(self.root))

    def get_tree(self) -> str:
        """
        From the root node, return the tree found thus far.
        :return: A tree as a string.
        """
        return helper.tree_state(self.root)

    def simulate(self):
        """
        Given the learned policy, do a simulation of the current learned best path from the root node. If no complete
        path is learned the derivation process will continue randomly until it reaches a terminal node.
        """
        print("========================================================================================")
        print("Running a simulation from the root node to some terminal based on the learned best path:")
        print("----------------------------------------------------------------------------------------")
        self.current = self.root

        # for reporting only
        deepness = 0
        reached_terminal = True

        # keep selecting children based on UCB1 as long as we didn't reach the end (terminal) and the node has children.
        while not self.current.is_terminal() and self.current.get_children():
            print(f"{self.current}")
            best_child = self._select()
            self.current = best_child
            deepness += 1

        # if we didn't reach a terminal, then the algorithm didn't have time to expand the grammar for at least one
        # branch and called it "best". Thus, continue with random selections from here till a terminal node.
        if not self.current.is_terminal():
            reached_terminal = False
            print(f"The algorithm didn't have enough time to expand to a known best path path, randomly rolling out"
                  f"from here: {self.current.get_signature()}")
            final_input, ac, _, _, _, is_anomalous, tokens_used = self.rollout(warmup=True)
            print(f"Input {final_input}, tokens-used={tokens_used}, len={len(final_input)}, target-app-edge-count: {ac}"
                  f", reward: {self._get_reward(ac, tokens_used)} and is this considered anomalous? {is_anomalous}")
        else:
            print(f"{self.current}")
            final_input, ac, _, _, _, is_anomalous = self.current.run(warmup=True)
            tokens_used = self.current.tokens_used
            print(f"Input {final_input}, tokens-used={self.current.tokens_used}, len={len(final_input)}, "
                  f"target-app-edge-count: {ac}, "
                  f"reward: {self._get_reward(ac, tokens_used)} and is this considered anomalous? {is_anomalous}")
        print("========================================================================================")

        if is_anomalous:
            self.count_of_anomalous_runs += 1

        print(f'maximum depth reached: {deepness}')
        print(f'reached terminal? {reached_terminal}')
        print(f'the final input found: {final_input.encode()}')
        print(f'the input length: {len(final_input)}')
        print(f'input cost: {ac}')
        print(f'reward {self._get_reward(ac, tokens_used)}')

    def save_tree_info_to_report(self, rollouts, expansions, edges, num_hot_nodes, reset_counter, number_of_executions):
        """Save midway information to the report dictionary. This happens when we are about to drop a tree.

        :param rollouts: The number of rollouts occurred for the given tree.
        :param expansions: The number of expansions occurred for thr given tree.
        :param edges: The number of edges created within the given tree.
        :param num_hot_nodes: The number of hot-nodes identified within the given tree.
        :param reset_counter: How many times we dropped tree (or the tree ID).
        :param number_of_executions: The number of executions made while searching within the tree.
        """
        self.report_dict['Stats: # total rollouts'] = str(int(self.report_dict['Stats: # total rollouts']) + rollouts)
        self.report_dict['Stats: # total expansions'] = str(int(self.report_dict['Stats: # total expansions']) +
                                                            expansions)
        self.report_dict['Stats: # total edges'] = str(int(self.report_dict['Stats: # total edges']) + edges)
        self.report_dict[f'Stats: Tree #{reset_counter}'] = f"rollouts={rollouts}, expansions={expansions}, " \
                                                            f"edges={edges}, hot_nodes_size={num_hot_nodes}, " \
                                                            f"#-of-iter={number_of_executions}"

    def get_report(self) -> dict:
        """

        :return:
        """
        # make sure we get the latest info about anomalous runs before returning the report.
        self.report_dict['Stats: Anomalous - Observed Anomalous Value?'] = str(self.count_of_anomalous_runs > 0)
        self.report_dict['Stats: Anomalous - # of Anomalous Value'] = str(self.count_of_anomalous_runs)

        return self.report_dict

    def close_connection(self):
        """
        Close the connection to the AFL runner.
        """
        self.root.close_connection()

    def has_stabilized(self, uniqueness_prc: float) -> bool:
        """Evaluate whether the tree has stabilized based on the number of execution  made using the tree and the
        uniqueness percentage value.

        :param uniqueness_prc: The uniqueness percentage (e.g., 0.5 is 50%).
        :return: True if it stabilized or False otherwise.
        """
        # TODO: This can be a staticmethod.
        return True if uniqueness_prc < (1 - helper.get_exploration_rate(self.exec_since_last_reset,
                                                                         self.threshold_decay,
                                                                         1,
                                                                         1-self.max_threshold)) else False

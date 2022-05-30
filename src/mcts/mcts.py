__author__ = "Ziyad Alsaeed"
__email__ = "zalsaeed@cs.uoregon.edu"
__status__ = "Testing"

import os
import gc
import sys
import time
import random
import _pickle as cpickle
import datetime
import collections
from typing import Tuple, Dict
from itertools import count

import numpy as np
import psutil
from tdigest import TDigest

import mcts.mcts_globals as mg  # MCTS globals
from mcts.mctsnode import MCTSNode
from gramm.llparse import *
from gramm.grammar import Grammar
from epsilonStrategy import EpsilonGreedyStrategy
from utilities import Utility


class MonteCarloTreeSearch:
    """
    Monte Carlo tree searcher.
    """

    def __init__(self, gram: Grammar, output_dir: str, expr_id: str, budget: int, reward_type: str,
                 hundredth_upper_bound: int, use_locking: bool = False, use_bias: bool = False, max_reward: int = 1,
                 tail_len: int = 5000, max_threshold: float = 0.5, threshold_decay: float = 0.0001):
        """
        The initializer of the TreeLine algorithm and the BiasOnly algorithm.

        @param gram: The grammar used to search for expensive input in the target application.
        @param output_dir: The directory where all the inputs generated and logs should be saved
        @param expr_id: A unique identifier for the experiment that should help the user find this run.
        @param budget: The allowed maximum budget regardless of how the budget is defined.
        @param reward_type: The reward function to be used in this search.
        @param hundredth_upper_bound:
        @param use_locking: If True, any node that is exhausted will be locked from future visits
            (i.e., as if it doesn't exist anymore).
        @param use_bias: If True, the rollouts will use the bias function instead of completely random search.
        @param max_reward:
        @param tail_len:
        @param max_threshold:
        @param threshold_decay:
        """
        self.log = logging.getLogger(self.__class__.__name__)

        self.digest = TDigest()
        self.output_dir = output_dir
        self.expr_id = expr_id
        self.use_locking = use_locking
        self.use_bias = use_bias
        self.max_reward = max_reward  # TODO: this must be removed as it multiplies the cost reward by 100. A careful observation should be made once it changed.
        self.gram = gram
        self.allowed_budget = budget
        self.reward_type = reward_type
        self.hundredth_upper_bound = hundredth_upper_bound
        # self.hundredth_upper_bound = 100  TODO: delete
        self.root = MCTSNode(budget=self.allowed_budget, text="", stack=[self.gram.start], tokens=0,
                             use_locking=use_locking)
        self.original_root = self.root  # necessary for the root pruning only
        self.original_root.start_connection()
        self.current = self.root  # fixme: either this or self.original_root. It is confusion to have the two.

        # statistical and tracking variables.
        self.average_cost = 0.0  # the average cost that will be found based on the warmup phase
        self.len_buffer = collections.deque(maxlen=100)
        self.len_w = 0.0
        self.skipped = 0
        self.raw_len_based_reward = False
        self.decided_to_always_go_with_full_input_len = False
        self.weight_total_observation = 0.0

        self.count_of_anomalous_runs = 0
        self.prune_count = 0

        self.max_observed_cost = 0
        self.min_observed_cost = 0
        self.exec_count_since_last_increase = 0
        self.observed_new_cost_at_least_once = False
        self.max_observed_hotspot = 0
        self.exec_since_last_reset = 0

        self.reset_counter = 1
        self.tail_len = tail_len
        self.epsilon = EpsilonGreedyStrategy(1, 1-max_threshold, threshold_decay)

        self.report_dict = collections.defaultdict(str)
        self.report_dict['Config: E (# of visits before expansion)'] = str(mg.E)
        self.report_dict['Config: C (exploration variable)'] = str(mg.C)
        self.report_dict['Config: Max Reward'] = str(self.max_reward)
        self.report_dict['Config: budget'] = str(self.allowed_budget)
        self.report_dict['Config: reward function'] = reward_type
        self.report_dict['Config: uniqueness tail size'] = str(self.tail_len)
        self.report_dict['Config: initial hundredth_upper_bound'] = str(self.hundredth_upper_bound)
        self.report_dict['Config: Lock fully observed nodes?'] = str(self.use_locking)
        self.report_dict['Config: Use Bias?'] = str(self.use_bias)
        self.report_dict['Config: Tail-Len'] = str(self.tail_len)
        self.report_dict['Config: Tree-Dropping-Max-Threshold'] = str(max_threshold)
        self.report_dict['Config: Tree-Dropping-Decay-Rate'] = str(threshold_decay)
        self.report_dict['Progress: # total rollouts'] = str(0)
        self.report_dict['Progress: # total expansions'] = str(0)
        self.report_dict['Progress: # total edges'] = str(0)

    def write_tree_to_file_as_dot(self):
        """
        Write tree to file in dot language for post-search visualization.
        """
        tree_dir = f"{self.output_dir}trees/"
        if not os.path.exists(tree_dir):
            os.makedirs(tree_dir)
        with open(f"{tree_dir}{self.reset_counter:02d}-TreeVis.dot", "w") as tree_file:
            tree_file.write(Utility.tree_to_dot(self.root))

    def save_tree(self):
        """
        Save the current tree to file.
        """
        # TODO: Can be added to util.
        with open(f"{self.output_dir}/{self.expr_id}.tree", "wb") as file_:
            cpickle.dump(self.original_root, file_)

    def load_tree(self, file_name: str):
        """
        Load tree from file.
        @param file_name: The tree file name.
        """
        # TODO: Can be added to util.
        if not os.path.isfile(file_name):
            raise RuntimeError(f"The string given {file_name} is not a file!")
        if not file_name.endswith(".tree"):
            raise RuntimeError(f"The file must be of type tree")
        with open(file_name, "rb") as input_file:
            self.original_root = cpickle.load(input_file)
        self.root = self.original_root

    def adjust_tail_len(self):
        """
        A function that adjusts the tail length based on a newly observed max or min. This should only be called when
        the max/min is adjusted.
        """
        new_range = self.max_observed_cost - self.min_observed_cost
        idx = np.digitize(new_range, bins=mg.buckets)
        self.tail_len = mg.tails[idx]

    def adjust_max_reward(self):
        """

        @return:
        """
        # TODO: delete the whole method
        diff = self.max_observed_cost - self.min_observed_cost
        if diff/self.min_observed_cost > 1.0:
            self.max_reward = 1
        else:
            self.max_reward = 100

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
        del self.original_root
        del self.current
        if mg.extensive_data_tracking:
            self.log.warning(f"Deleted all tree nodes | memory used: {psutil.virtual_memory().percent}% ...")

        # garbage collect as a safety check
        gc.collect()
        if mg.extensive_data_tracking:
            self.log.warning(f"Did explicit gc | memory used: {psutil.virtual_memory().percent}% ...")

        # finally re-populate the tree root given the grammar.
        self.root = MCTSNode(budget=self.allowed_budget, text="", stack=[self.gram.start], tokens=0,
                             use_locking=self.use_locking, bias=bias_temp)
        self.original_root = self.root  # necessary for the root pruning only
        self.current = self.root
        if mg.extensive_data_tracking:
            self.log.warning("Done resetting!")

        if not self.raw_len_based_reward and self.reset_counter == 1:
            self.len_w = round(self.weight_total_observation/self.exec_since_last_reset, 4)
            print(f"The length reward weight is set to: {self.len_w}")
        self.exec_count_since_last_increase = 0
        self.exec_since_last_reset = 0
        self.reset_counter += 1

    def has_new_cost(self, cost: int) -> bool:
        """
        Check with the cost passed is a new maximum cost or not and adjust all the tracking variables accordingly
        if it demonstrates a new maximum.

        @param cost: The new cost to evaluate.
        @return: True if the cost passed is a new maximum and False otherwise.
        """
        if cost > self.max_observed_cost:
            self.max_observed_cost = cost

            # Adjusting the tail len because we changed the known max cost.
            self.adjust_tail_len()

            # we got a new max. Is the reward scaling still good for the new range?
            self.adjust_max_reward()

            # these two variables can be used to help decide when we should drop the tree
            self.exec_count_since_last_increase = 0
            self.observed_new_cost_at_least_once = True

            # if not quantile reward, adjust the upper bound.  TODO: this is not necessary anymore.
            if self.reward_type != 'quantile':
                diff = cost - self.min_observed_cost
                prc = diff/self.min_observed_cost * 100
                if prc == 0:
                    prc += 0.00000001
                # maybe use cost*0.01 for max?
                self.hundredth_upper_bound = Utility.find_hundredth_upper_bound(prc, 100, 0, 0, 1)

            return True
        else:
            self.exec_count_since_last_increase += 1
            return False

    def has_new_hotspot(self, hotspot) -> bool:
        """
        Check with the hotspot value passed is a new maximum or not and adjust all the tracking variables accordingly
        if it demonstrates a new maximum.
        @param hotspot: The value observed for the hotspot.
        @return: True if the hotspot passed is a new maximum and False otherwise.
        """
        if hotspot > self.max_observed_hotspot:
            self.max_observed_hotspot = hotspot
            return True
        else:
            return False

    def warm_up(self) -> bool:
        """

        @return:
        """

        # TODO: remove this method. We don't need it anymore with quantiles as rewards. Maybe we only need it to
        #  validate the grammar and the app work.
        unique_random_input = {}
        n = 20
        start_time = datetime.datetime.now()
        max_time = datetime.timedelta(minutes=3)

        # run until you get n unique inputs with their costs
        while len(unique_random_input.keys()) < n:
            found_input, ac, _, _, _, is_anomalous, _ = self.rollout(warmup=True)

            # we didn't define what an anomalous input is for this app yet. But by default any edge count of an
            # application below the default value (50) is in our experience an anomalous run.
            if is_anomalous:
                continue

            if found_input not in unique_random_input:
                unique_random_input[found_input] = ac

            time_elapsed = datetime.datetime.now() - start_time
            if time_elapsed > max_time:
                self.log.warning(f"Could not find {n} unique inputs within maximum allowed time ({max_time})")
                return False

        warmup_file = open(f"{self.output_dir}warmup.txt", "w")
        warmup_file.write(f'Warmup phase for {n} unique inputs (mcts.mcts_globals.TARGET_APP_MIN_POSSIBLE_COST='
                          f'{mg.TARGET_APP_MIN_POSSIBLE_COST})\n')
        # find the average cost
        total_costs = 0
        max_cost = 0
        for k, v in unique_random_input.items():
            warmup_file.write(f'input "{k}": cost {v}\n')
            total_costs += v
            if v > max_cost:
                max_cost = v
            if self.reward_type == 'quantile':
                self.digest.update(v)
        self.average_cost = total_costs/n
        diff = max_cost - self.average_cost
        prc = diff / self.average_cost * 100
        self.hundredth_upper_bound = Utility.find_hundredth_upper_bound(prc, 100, 0, 0, 30)  # max_cost*0.1

        """
        The root must have an empty string as text. usually an empty string the minimalist value possible. We use it 
        to define the min_cost of the target app that would help adjust the tail.
        """
        found_input, ac, _, _, _, _ = self.root.dummy_run()
        self.min_observed_cost = ac

        # anything below 80% of the average cost is an anomalous run
        mg.TARGET_APP_MIN_POSSIBLE_COST = int(self.average_cost * 0.2)

        warmup_file.write(f'New mcts.mcts_globals.TARGET_APP_MIN_POSSIBLE_COST={mg.TARGET_APP_MIN_POSSIBLE_COST}.')
        warmup_file.write(f'The average cost found={self.average_cost} and the new anomalous values bar='
                          f'{mg.TARGET_APP_MIN_POSSIBLE_COST}')
        warmup_file.write(f'The self.hundredth_upper_bound found is: {self.hundredth_upper_bound}')
        warmup_file.close()
        return True

    def treeline(self, is_time_based: bool, time_cap_h=1, num_iter=100):
        """
        The main method to run (train) the algorithm. An iteration is a derivation that starts from the root node. Any
        derivation would end at a terminal. However, the reach of the terminal could be based on the tree observed UCB1
        values or random (rollout).

        @param is_time_based: A boolean to make the run based on either time cap (True) or num of iteration (False).
        @param num_iter: The maximum number of derivations (target app runs) that are allowed.
        @param time_cap_h: The maximum time allowed for a run in hours.
        """

        buffer_dir = f"{self.output_dir}hot_nodes/"  # dir to track cov and max inputs
        os.makedirs(buffer_dir)

        # tracking variables
        rollouts = 0
        expansions = 0
        edges = 0
        input_id = 1
        progress_report = collections.defaultdict(list)

        # TreeLine related variables
        hot_nodes: List[MCTSNode] = []  # hot_nodes of all hnb, hnm, or hnc non-terminal nodes.
        top_n_hot_nodes: List[MCTSNode] = []  # top n nodes from hot_nodes given their UCT value at some point
        hot_node_prop_threshold = 0.5  # the probability of selecting a node from the hot_nodes vs. using the root node

        # [hot_nodes-plot] tracking hot_nodes only, this is expensive. TODO: remove the tracking.
        # it doesn't hurt ti creat an empty dict, thus we don't use the flag mg.extensive_data_tracking
        track_costs: Dict[int, int] = collections.defaultdict()
        track_ucb = collections.defaultdict(list)

        print()  # make a space for the progress bar (info).
        expr_max_time = datetime.timedelta(hours=time_cap_h)  # maximum possible time in case of time-based runs
        start = time.time_ns() // 1_000_000  # get time in milliseconds from epoch to label inputs.
        expr_start_time = datetime.datetime.now()  # expr start time in case of time-based run.
        for i in count(1):  # this will loop forever. We check for break condition at the end based on duration base.

            self.current = self.root  # let make sure we have a node to do a search

            # update the top n nodes every 500 iterations.
            if i % 500 == 0:
                top_n_hot_nodes = list(Utility.top_n(hot_nodes, n=10, key=lambda n: n.get_ucb1()))

            # with some random value, either keep the root node or select the best node from top n hot_nodes
            if random.random() > hot_node_prop_threshold:
                if top_n_hot_nodes:
                    self.current = max(top_n_hot_nodes, key=lambda n: n.get_ucb1())

            # [hot_nodes-plot] tracking hot_nodes nodes only, this is expensive. TODO: remove
            if mg.extensive_data_tracking:
                # log the uct value for each node in the hot_nodes.
                for node in hot_nodes:
                    cost = track_costs[id(node)]  # the cost for which this node was added to hot_nodes (used in key)
                    track_ucb[f"{node.get_signature()}-{cost}"].append(node.get_ucb1())

            # LOG: logging uniqueness and prep for check to drop the tree
            uniqueness_percentage = 1.0 if self.exec_since_last_reset < self.tail_len \
                else Utility.find_prc_uniq_values(progress_report['execution_cost'][-self.tail_len:])

            # progress bar (info) prints (different for time vs. iter based).
            Utility.progress_bar(is_time_based=is_time_based, start_time=expr_start_time, iter_counter=i,
                                 num_rollouts=rollouts, num_expansions=expansions, num_edges=edges,
                                 num_hot_nodes=len(hot_nodes), max_reward=self.max_reward,
                                 refresh_threshold=1 - self.epsilon.get_exploration_rate(self.exec_since_last_reset),
                                 uniqueness_per=uniqueness_percentage, tail_len=self.tail_len,
                                 len_reward_weight=self.len_w, total_allowed_iter=num_iter)

            if mg.extensive_data_tracking:
                self.log.debug(f"Iter: {i}")

            # OK, now we have some node and would like to travers the tree based on the UCB1 value.
            while not self.current.is_leaf():  # a leaf node is either a terminal node or a non-expanded node yet.
                best_child = self._select()
                self.current = best_child

            # if all nodes are expanded, and we reach a terminal node, get cost
            if self.current.is_terminal():
                final_input, ac, hnb, hnm, hs, is_anomalous = self.current.run()
                tokens_used = self.current.tokens_used

                # update the bias if we are using it. TODO: why are we updating the bias here but not in the rollout
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
            # run is anomalous or not.
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
                if hnb or hnm or hnc:
                    if self.current not in hot_nodes:
                        hot_nodes.append(self.current)
                        if mg.extensive_data_tracking:
                            # [hot_nodes-plot] A new node added to hot_nodes, we must track the cost for which it was
                            # added. TODO: remove as this is expensive
                            track_costs[id(self.current)] = ac

            # if the run is anomalous, make a note but don't back-propagate any info based on wrong run!
            if is_anomalous:
                self.count_of_anomalous_runs += 1  # make sure we track this incident
            else:
                self.exec_since_last_reset += 1
                # first back-propagate from current given the reward.
                # TODO: We have two different calls because of the binary rewards. This should be removed if it
                #  doesn't prove to be any good.
                if hnb or hnm or hnc:
                    reward = self._get_reward(ac, tokens_used, self.reward_type, self.hundredth_upper_bound, 1)
                    self._backpropagate(reward)
                else:
                    reward = self._get_reward(ac, tokens_used, self.reward_type, self.hundredth_upper_bound, 0)
                    self._backpropagate(reward)

                # LOG: log the run info for debugging with high priority as we want to see hnc regardless og log level
                if mg.extensive_data_tracking:
                    if hnc:
                        self.log.warning(f"hnb:{hnb}, hnm:{int(hnm)}, hnc:{int(hnc)}, hnh:{int(hnh)}, hs:{hs:010d}, "
                                         f"cost:{ac:010d}, reward:{reward:02f}, len:{len(bytes(final_input, 'utf-8'))},"
                                         f" anomalous:{int(is_anomalous)}, input:{final_input.encode()}")
                    else:
                        self.log.info(f"hnb:{hnb}, hnm:{int(hnm)}, hnc:{int(hnc)}, hnh:{int(hnh)}, hs:{hs:010d}, "
                                      f"cost:{ac:010d}, reward:{reward:02f}, len:{len(bytes(final_input, 'utf-8'))}, "
                                      f"anomalous:{int(is_anomalous)}, input:{final_input.encode()}")

                # LOG: track the run info in dict for detailed plots
                end = time.time_ns() // 1_000_000  # get time in milliseconds from epoch. Tracking input generation time
                elapsed_time = end - start
                progress_report["execution_cost"].append(ac)  # the progress is needed for drop eval
                if mg.extensive_data_tracking:
                    progress_report["iter"].append(i)
                    progress_report["duration"].append(elapsed_time)
                    progress_report["rollouts"].append(rollouts)
                    progress_report["expansions"].append(expansions)
                    progress_report["edges"].append(edges)
                    progress_report["reward"].append(reward)
                    progress_report["hnb"].append(hnb)
                    progress_report["hnm"].append(int(hnm))
                    progress_report["hs"].append(hs)
                    progress_report["hot_nodes"].append(len(hot_nodes))
                    progress_report["derivation_len"].append(tokens_used)
                    progress_report["refresh_threshold"].append(
                        1-self.epsilon.get_exploration_rate(self.exec_since_last_reset))
                    progress_report['hundredth_upper_bound'].append(self.hundredth_upper_bound)
                    progress_report['average_cost'].append(self.average_cost)
                    progress_report['uniqueness_percentage'].append(uniqueness_percentage)
                    progress_report['tail_len'].append(self.tail_len)
                    progress_report['len_weight'].append(self.len_w)

            # main tracker: save inputs if interesting
            if hnb or hnm or hnc:
                postfix = ""
                if hnb:  # not 0 (we don't care either 1 or 2)
                    postfix += "+cov"
                if hnm:
                    postfix += "+max"
                if hnc:
                    postfix += "+cost"
                cur_ms = time.time_ns() // 1_000_000
                # TODO: change the len tracking to be based on the len given by the user (e.g., char, or byte).
                with open(f"{buffer_dir}id:{input_id:06d},cost:{ac:010d},hs:{hs:010d},hnb:{hnb},exec:{i},"
                          f"len:{len(bytes(final_input, 'utf-8')):03d},tu:{tokens_used:03d},crtime:{cur_ms},"
                          f"dur:{cur_ms-start}{postfix}", "wb") as cov_file:
                    cov_file.write(final_input.encode())
                input_id += 1

            # now evaluate if the current tree should be dropped
            if self.exec_since_last_reset >= self.tail_len:  # did we give it enough runs according to the tail?
                if self.has_stabilized(uniqueness_percentage):  # did it stabilize?

                    # track progress for experiment stats
                    # TODO: change how we track the info to be more concise.
                    self.report_dict['Progress: # total rollouts'] = \
                        str(int(self.report_dict['Progress: # total rollouts']) + rollouts)
                    self.report_dict['Progress: # total expansions'] = \
                        str(int(self.report_dict['Progress: # total expansions']) + expansions)
                    self.report_dict['Progress: # total edges'] = \
                        str(int(self.report_dict['Progress: # total edges']) + edges)
                    self.report_dict[f'Progress: Tree #{self.reset_counter}'] = f"rollouts={rollouts}, " \
                                                                                f"expansions={expansions}, " \
                                                                                f"edges={edges}, " \
                                                                                f"hot_nodes-size={len(hot_nodes)}, " \
                                                                                f"#-of-iter=" \
                                                                                f"{self.exec_since_last_reset}"

                    hot_nodes.clear()  # clear the lcc hot_nodes
                    rollouts = expansions = edges = 0  # resetting tree ops tracking variables
                    self.observed_new_cost_at_least_once = False  # resetting the key for the reset decision
                    self._reset()  # now we can drop the tree and start a new one.

            # if the tree reward function is drastically changed drop, no question
            if self.decided_to_always_go_with_full_input_len:
                self.decided_to_always_go_with_full_input_len = False
                # track progress for experiment stats
                self.report_dict['Progress: # total rollouts'] = \
                    str(int(self.report_dict['Progress: # total rollouts']) + rollouts)
                self.report_dict['Progress: # total expansions'] = \
                    str(int(self.report_dict['Progress: # total expansions']) + expansions)
                self.report_dict['Progress: # total edges'] = \
                    str(int(self.report_dict['Progress: # total edges']) + edges)
                self.report_dict[f'Progress: Tree #{self.reset_counter}'] = f"rollouts={rollouts}, " \
                                                                            f"expansions={expansions}, " \
                                                                            f"edges={edges}, " \
                                                                            f"hot_nodes-size={len(hot_nodes)}, " \
                                                                            f"#-of-iter=" \
                                                                            f"{self.exec_since_last_reset}"

                hot_nodes.clear()  # clear the lcc hot_nodes
                rollouts = expansions = edges = 0  # resetting tree ops tracking variables
                self.observed_new_cost_at_least_once = False  # resetting the key for the reset decision
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

        # track reportable values before exiting
        self.report_dict['Time: duration(ms)'] = str(elapsed_time)
        self.report_dict['Time: duration(s)'] = str(elapsed_time/1_000)
        self.report_dict['Time: duration(m)'] = str(elapsed_time/60_000)
        self.report_dict['Time: duration(h)'] = str(elapsed_time/3_600_000)
        self.report_dict['Duration-Config: Is Duration based on Time?'] = str(is_time_based)
        self.report_dict['Duration-Config: Time allowed in hours'] = str(time_cap_h)
        self.report_dict['Duration-Config: # of iterations'] = str(num_iter)
        self.report_dict['Results: max cost'] = str(self.max_observed_cost)
        self.report_dict['Results: max hotspot'] = str(self.max_observed_hotspot)
        self.report_dict['Progress: final tail len'] = str(self.tail_len)
        self.report_dict['Progress: # total rollouts'] = \
            str(int(self.report_dict['Progress: # total rollouts']) + rollouts)
        self.report_dict['Progress: % of rollout/iter(s)'] = \
            str(int(self.report_dict['Progress: # total rollouts'])/num_iter)
        self.report_dict['Progress: # total expansions'] = \
            str(int(self.report_dict['Progress: # total expansions']) + expansions)
        self.report_dict['Progress: % expansions/iter(s)'] = \
            str(int(self.report_dict['Progress: # total expansions'])/num_iter)
        self.report_dict['Progress: # total edges'] = str(int(self.report_dict['Progress: # total edges']) + edges)
        self.report_dict[f'Progress: Tree #{self.reset_counter}'] = f"rollouts={rollouts}, " \
                                                                    f"expansions={expansions}, " \
                                                                    f"edges={edges}, " \
                                                                    f"hot_nodes-size={len(hot_nodes)}, " \
                                                                    f"#-of-iter={self.exec_since_last_reset}"

        # whether we use it or not, print the bias table
        with open(f"{self.output_dir}bias.txt", "w") as bias_file:
            bias_file.write(self.root.bias.__str__())

        # Write the last known tree to file
        if mg.extensive_data_tracking:
            self.write_tree_to_file_as_dot()

        # LOG: write progress report to file
        if mg.extensive_data_tracking:
            Utility.write_dict_to_csv(progress_report, self.output_dir, f"Progress-report-{self.expr_id}",
                                      comments=f"grammar: {self.gram.gram_name}, budget: {self.allowed_budget}, "
                                               f"total-iter: {num_iter}, c: {mg.C}, e: {mg.E}, "
                                               f"duration(ms): {elapsed_time}, "
                                               f"total rollouts: "
                                               f"{int(self.report_dict['Progress: # total rollouts'])}, "
                                               f"total expansions: "
                                               f"{int(self.report_dict['Progress: # total expansions'])}, "
                                               f"total edges: {int(self.report_dict['Progress: # total edges'])}, "
                                               f"total anomalous runs: {self.count_of_anomalous_runs}, "
                                               f"Starting node threshold: {hot_node_prop_threshold}")

        # [hot_nodes-plot] for reporting the hot_nodes ucb(s) only. TODO: remove once done. This is expensive.
        if mg.extensive_data_tracking:
            max_tracked_len = 0
            for k, v in track_ucb.items():
                if len(v) > max_tracked_len:
                    max_tracked_len = len(v)

            for k, v in track_ucb.items():
                if len(v) < max_tracked_len:
                    track_ucb[k] = [None]*(max_tracked_len-len(v)) + v
                elif len(v) > max_tracked_len:
                    raise RuntimeError("We got a wrong max!")

            Utility.write_dict_to_csv(track_ucb, self.output_dir, f"Buffer-Status-{self.expr_id}")

    def random_search(self, time_based: bool, time_cap_h=1, num_iter=100):
        """
        The main method to run (train) the algorithm. An iteration is a derivation that starts from the root node. Any
        derivation would end at a terminal. However, the reach of the terminal could be based on the tree observed UCB1
        values or random (rollout).

        @param time_based: A boolean to make the run based on either time cap (True) or num of iteration (False).
        @param num_iter: The number of derivations we would like to do from root to terminal.
        @param time_cap_h: The maximum time allowed for a run in hours.
        """
        # dir to track cov and max inputs:
        buffer_dir = f"{self.output_dir}buffer/"
        os.makedirs(buffer_dir)

        # tracking variables
        rollouts = 0
        input_id = 1
        progress_report = collections.defaultdict(list)

        print()  # make a space for the progress bar (info).
        expr_max_time = datetime.timedelta(hours=time_cap_h)  # maximum possible time in case of time-based runs
        start = time.time_ns() // 1_000_000  # get time in milliseconds from epoch to label inputs.
        expr_start_time = datetime.datetime.now()  # expr start time in case of time-based run.
        for i in count(1):  # this will loop forever. We check for break condition at the end based on duration base.

            self.current = self.root  # let make sure we have a node to do a search

            # progress bar (info) prints (different for time vs. iter based). Should be in its own function!
            sys.stdout.write('\r')
            if time_based:
                sys.stdout.write("Duration(m)= %.5f, iter #%.1f, rollouts=%.1f, "
                                 "rMax=%.1f, refresh-threshold=%.5f, len(tail)=%.3f, "
                                 "rw=%.1f" %
                                 ((datetime.datetime.now() - expr_start_time).seconds/60,
                                  i,
                                  rollouts,
                                  self.max_reward,
                                  1 - self.epsilon.get_exploration_rate(self.exec_since_last_reset),
                                  self.tail_len,
                                  self.len_w
                                  )
                                 )
            else:
                sys.stdout.write("[%-50s] %.2f%%, iter #%.1f, rollouts=%.1f, "
                                 "rMax=%.1f, refresh-threshold=%.5f, len(tail)=%.1f, rw=%.3f" %
                                 ('=' * int(50 * i / (num_iter - 1)),
                                  100 * i / (num_iter - 1),
                                  i,
                                  rollouts,
                                  self.max_reward,
                                  1-self.epsilon.get_exploration_rate(self.exec_since_last_reset),
                                  self.tail_len,
                                  self.len_w
                                  )
                                 )
            sys.stdout.flush()

            if mg.extensive_data_tracking:
                self.log.debug(f"Iter: {i}")

            # The current node = the root node, we do random search (no UCT eval just random rollout).

            final_input, ac, hnb, hnm, hs, is_anomalous, tokens_used = self.rollout()  # do a rollout from current
            rollouts += 1

            # Did we encounter a new hotspot or cost?
            hnh = self.has_new_hotspot(hs)  # calling it updates the known max hs
            hnc = self.has_new_cost(ac)  # calling has_new_cost(x) updates the known max cost

            self.exec_since_last_reset += 1

            # LOG: log the run info for debugging with high priority as we want to see hnc regardless of log level
            if mg.extensive_data_tracking:
                if hnc:
                    self.log.warning(f"hnb:{hnb}, hnm:{int(hnm)}, hnc:{int(hnc)}, hnh:{int(hnh)}, hs:{hs:010d}, "
                                     f"cost:{ac:010d}, len:{len(bytes(final_input, 'utf-8'))},"
                                     f" anomalous:{int(is_anomalous)}, input:{final_input.encode()}")
                else:
                    self.log.info(f"hnb:{hnb}, hnm:{int(hnm)}, hnc:{int(hnc)}, hnh:{int(hnh)}, hs:{hs:010d}, "
                                  f"cost:{ac:010d}, len:{len(bytes(final_input, 'utf-8'))}, "
                                  f"anomalous:{int(is_anomalous)}, input:{final_input.encode()}")

            # LOG: track the run info in dict for detailed plots
            end = time.time_ns() // 1_000_000  # get time in milliseconds from epoch. Tracking input generation time
            elapsed_time = end - start
            progress_report["execution_cost"].append(ac)  # the progress is needed for drop eval
            if mg.extensive_data_tracking:
                progress_report["iter"].append(i)
                progress_report["duration"].append(elapsed_time)
                progress_report["rollouts"].append(rollouts)
                progress_report["hnb"].append(hnb)
                progress_report["hnm"].append(int(hnm))
                progress_report["hs"].append(hs)
                progress_report["derivation_len"].append(tokens_used)
                progress_report["refresh_threshold"].append(
                    1-self.epsilon.get_exploration_rate(self.exec_since_last_reset))
                progress_report['hundredth_upper_bound'].append(self.hundredth_upper_bound)
                progress_report['average_cost'].append(self.average_cost)
                progress_report['tail_len'].append(self.tail_len)
                progress_report['len_weight'].append(self.len_w)

            # main tracker: save inputs if interesting
            if hnb or hnm or hnc:
                postfix = ""
                if hnb:  # not 0 (we don't care either 1 or 2)
                    postfix += "+cov"
                if hnm:
                    postfix += "+max"
                if hnc:
                    postfix += "+cost"
                cur_ms = time.time_ns() // 1_000_000
                with open(f"{buffer_dir}id:{input_id:06d},cost:{ac:010d},hs:{hs:010d},hnb:{hnb},exec:{i},"
                          f"len:{len(bytes(final_input, 'utf-8')):03d},tu:{tokens_used:03d},crtime:{cur_ms},"
                          f"dur:{cur_ms-start}{postfix}", "wb") as cov_file:
                    cov_file.write(final_input.encode())
                input_id += 1

            # checking if we should break the loop based on duration base configuration
            if time_based:
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
        self.report_dict['Time: duration(ms)'] = str(elapsed_time)
        self.report_dict['Time: duration(s)'] = str(elapsed_time/1_000)
        self.report_dict['Time: duration(m)'] = str(elapsed_time/60_000)
        self.report_dict['Time: duration(h)'] = str(elapsed_time/3_600_000)
        self.report_dict['Duration-Config: Is Duration based on Time?'] = str(time_based)
        self.report_dict['Duration-Config: Time allowed in hours'] = str(time_cap_h)
        self.report_dict['Duration-Config: # of iterations'] = str(num_iter)
        self.report_dict['Results: max cost'] = str(self.max_observed_cost)
        self.report_dict['Results: max hotspot'] = str(self.max_observed_hotspot)
        self.report_dict['Progress: final tail len'] = str(self.tail_len)
        self.report_dict['Progress: # total rollouts'] = \
            str(int(self.report_dict['Progress: # total rollouts']) + rollouts)
        self.report_dict['Progress: % of rollout/iter(s)'] = \
            str(int(self.report_dict['Progress: # total rollouts'])/num_iter)
        self.report_dict['Progress: % expansions/iter(s)'] = \
            str(int(self.report_dict['Progress: # total expansions'])/num_iter)
        self.report_dict[f'Progress: Tree #{self.reset_counter}'] = f"rollouts={rollouts}, " \
                                                                    f"#-of-iter={self.exec_since_last_reset}"

        # whether we use it or not, print the bias table
        with open(f"{self.output_dir}bias.txt", "w") as bias_file:
            bias_file.write(self.root.bias.__str__())

        # Write the last known tree to file
        if mg.extensive_data_tracking:
            self.write_tree_to_file_as_dot()

        # LOG: write progress report to file
        if mg.extensive_data_tracking:
            Utility.write_dict_to_csv(progress_report, self.output_dir, f"Progress-report-{self.expr_id}",
                                      comments=f"grammar: {self.gram.gram_name}, budget: {self.allowed_budget}, "
                                               f"total-iter: {num_iter}, c: {mg.C}, e: {mg.E}, "
                                               f"duration(ms): {elapsed_time}, "
                                               f"total rollouts: "
                                               f"{int(self.report_dict['Progress: # total rollouts'])}, "
                                               f"total expansions: "
                                               f"{int(self.report_dict['Progress: # total expansions'])}, "
                                               f"total edges: {int(self.report_dict['Progress: # total edges'])}, "
                                               f"total anomalous runs: {self.count_of_anomalous_runs}")

    def _select(self) -> MCTSNode:
        """
        Choose the best successor of current node (choose a move). Can't be called on a terminal or unexpanded nodes.

        @return: The best child node of the current node.
        """
        if self.current.is_terminal():
            raise RuntimeError(f"Trying to select a a child node from the terminal node {self.current}")

        if not self.current.get_children():
            raise RuntimeError(f"The current node {self.current} has no populated children to select from.")

        return max(self.current.get_children(), key=lambda node: node.get_ucb1())

    def rollout(self, warmup=False) -> Tuple[str, int, int, bool, int, bool, int]:
        """
        Expand the tree from the current node until you reach terminal node either randomly or using the bias.

        @return: Run information of the generated input (text, ac, hnb, hnm, hs, is_anomalous, tokens_used).
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

        @return: The number of valid children populated.
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

        @param reward: The reward observed at the current node (rolling out to terminal or itself being a terminal).
        """
        self.current.update(reward)  # make sure we update the current first
        s = self.current
        while s.has_a_parent():
            s_parent = s.parent
            s_parent.update(reward)
            s = s_parent

    def _get_reward(self, cost: int, input_len: int, reward_type: str, hundredth_upper_bound: float,
                    binary_val: int) -> float:
        """
        Get the reward based on the len and cost of the input generated. The len weight changes within the first
        established tree. Moreover, if thr adjust_len_weight determines that we should use the actual len value, then
        the weight is disregarded.

        @param cost: The execution cost of the input.
        @param input_len: The input len regardless of base used (bytes, chars, or tokens)
        @return: The reward of the input based on the reward formula at the time of calling this method as well as the
        other hyper-parameters values.
        """

        if self.reset_counter <= 1:  # we only adjust the reward function on the first tree
            self.adjust_len_weight(input_len)

        # using tdigest as found here https://github.com/CamDavidsonPilon/tdigest
        cost_reward = self.digest.cdf(cost)  # we get the reward before we update the quantile
        self.digest.update(cost)

        if self.raw_len_based_reward:
            return cost_reward + input_len
        else:
            len_reward = Utility.scale_to_range(input_len, self.allowed_budget, 0, 0, 1)
            return (cost_reward * (1-self.len_w) * self.max_reward) + len_reward * self.len_w

    def adjust_len_weight(self, input_len: int):
        """
        AA method to adjust the length weight according to our formula. In a nutshell, the weight is decreased or
        increased by 0.0001 depending on whether 50% of the observed inputs are within the top 20% of the budget
        allowance.
        """
        self.len_buffer.append(input_len)
        if not self.raw_len_based_reward:  # and if we settle for raw, that's it, never going back
            if len(self.len_buffer) == self.len_buffer.maxlen:
                top_20_prc = int(0.8 * self.allowed_budget)
                if Utility.get_prc_of_value_above_threshold(list(self.len_buffer), top_20_prc) < .5:
                    if self.len_w < 0.9:  # hitting the max
                        self.len_w += .0001
                    else:
                        self.skipped += 1
                    if self.skipped > self.len_buffer.maxlen * 5:
                        self.raw_len_based_reward = True
                        self.decided_to_always_go_with_full_input_len = True
                        self.len_w = float("inf")
                else:
                    if self.len_w > 0.1:
                        self.len_w -= .0001
                self.weight_total_observation += self.len_w

    def print_tree(self):
        """
        From the root node, print the tree found thus far.
        """
        print(Utility.tree_state(self.root))

    def get_tree(self) -> str:
        """
        From the root node, return the tree found thus far.
        @return: A tree as a string.
        """
        return Utility.tree_state(self.root)

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
        # branch. Thus, continue with random selections from here till a terminal node.
        if not self.current.is_terminal():
            reached_terminal = False
            self.log.warning("The algorithm didn't have enough time to expand at least a complete single path, rolling "
                             "out from here!")
            logging.root.setLevel(logging.DEBUG)  # force set to DEBUG to see how the derivation ends.
            final_input, ac, _, _, _, is_anomalous, tokens_used = self.rollout(warmup=True)
            print(f"Input {final_input}, tokens-used={tokens_used}, len={len(final_input)}, target-app-edge-count: {ac}"
                  f", reward: {self._get_reward(ac, tokens_used, self.reward_type, self.hundredth_upper_bound, 0)} and "
                  f"this is considered anomalous? {is_anomalous}")
        else:
            print(f"{self.current}")
            final_input, ac, _, _, _, is_anomalous = self.current.run(warmup=True)
            tokens_used = self.current.tokens_used
            print(f"Input {final_input}, tokens-used={self.current.tokens_used}, len={len(final_input)}, "
                  f"target-app-edge-count: {ac}, "
                  f"reward: {self._get_reward(ac, tokens_used, self.reward_type,self.hundredth_upper_bound, 0)} and "
                  f"this is considered anomalous? {is_anomalous}")
        print("========================================================================================")

        if is_anomalous:
            self.count_of_anomalous_runs += 1

        # track reportable values before exiting. TODO: we don't need these. If anything they should be a method call.
        self.report_dict['final max depth'] = str(deepness)
        self.report_dict['reached terminal?'] = str(reached_terminal)
        self.report_dict['final input'] = str(final_input.encode())
        self.report_dict['input len'] = str(len(final_input))
        self.report_dict['target app input based edge count'] = str(ac)
        self.report_dict['final reward'] = str(self._get_reward(ac, tokens_used, self.reward_type,
                                                                self.hundredth_upper_bound, 0))

    def get_report(self) -> dict:
        """

        @return:
        """
        # make sure we get the latest info about anomalous runs before returning the report.
        self.report_dict['Progress: anam - observed anomalous value?'] = str(self.count_of_anomalous_runs > 0)
        self.report_dict['Progress: anam - # of anomalous value'] = str(self.count_of_anomalous_runs)

        return self.report_dict

    def close_connection(self):
        """
        Close the connection to the AFL runner.
        """
        self.original_root.close_connection()

    def has_stabilized(self, uniqueness_prc: float) -> bool:
        """
        Evaluate whether the tree has stabilized based on the number of execution  made using the tree and the
        uniqueness percentage value.
        @param uniqueness_prc: The uniqueness percentage (e.g., 0.5 is 50%).
        @return: True if it stabilized and False otherwise.
        """
        # TODO: This can be a staticmethod.
        return True if uniqueness_prc < (1 - self.epsilon.get_exploration_rate(self.exec_since_last_reset)) else False

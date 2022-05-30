__author__ = "Ziyad Alsaeed"
__email__ = "zalsaeed@cs.uoregon.edu"
__status__ = "Testing"

import os
import re
import sys
import datetime
import subprocess
from typing import List, Iterable, Callable

import pandas as pd
import numpy as np
from sympy.solvers import solve
from sympy import Symbol
from sympy import Eq

from gramm.grammar import RHSItem
from mcts.mctsnode import MCTSNode


class Utility:

    @staticmethod
    def progress_bar(is_time_based: bool, start_time: datetime, iter_counter: int, num_rollouts: int,
                     num_expansions: int, num_edges: int, num_hot_nodes: int, max_reward: float,
                     refresh_threshold: float, uniqueness_per: float, tail_len: int, len_reward_weight: float,
                     total_allowed_iter: int):
        """
        A method to show the progress bar of the run based on it whether being based on time or number of iter.

        @param is_time_based:
        @param start_time:
        @param iter_counter:
        @param num_rollouts:
        @param num_expansions:
        @param num_edges:
        @param num_hot_nodes:
        @param max_reward:
        @param refresh_threshold:
        @param uniqueness_per:
        @param tail_len:
        @param len_reward_weight:
        @param total_allowed_iter:
        """
        sys.stdout.write('\r')
        if is_time_based:
            sys.stdout.write("Duration(m)= %.5f, iter #%.1f, rollouts=%.1f, expansions=%.1f, edges=%.1f, "
                             "hot-nodes=%.1f, rMax=%.1f, refresh-threshold=%.5f, uniquenessPRC=%.5f, "
                             "len(tail)=%.3f, rw=%.1f" %
                             ((datetime.datetime.now() - start_time).seconds / 60,
                              iter_counter,
                              num_rollouts,
                              num_expansions,
                              num_edges,
                              num_hot_nodes,
                              max_reward,
                              refresh_threshold,
                              uniqueness_per,
                              tail_len,
                              len_reward_weight
                              )
                             )
        else:
            sys.stdout.write("[%-50s] %.2f%%, iter #%.1f, rollouts=%.1f, expansions=%.1f, edges=%.1f, "
                             "hot-nodes=%.1f, rMax=%.1f, refresh-threshold=%.5f, uniquenessPRC=%.5f, "
                             "len(tail)=%.1f, rw=%.3f" %
                             ('=' * int(50 * iter_counter / (total_allowed_iter - 1)),
                              100 * iter_counter / (total_allowed_iter - 1),
                              iter_counter,
                              num_rollouts,
                              num_expansions,
                              num_edges,
                              num_hot_nodes,
                              max_reward,
                              refresh_threshold,
                              uniqueness_per,
                              tail_len,
                              len_reward_weight
                              )
                             )
        sys.stdout.flush()

    @staticmethod
    def scale_to_range(x_value, x_max, x_min, range_a, range_b) -> float:
        """
        Given a value x in a known range (min-max), squish it between a new defined range a and b.

        @param x_value: tha value to scale.
        @param x_max: the maximum value in the range from where x is given.
        @param x_min: the minimum value in the range from where x is given.
        @param range_a: the minimum value of the new scale.
        @param range_b: the maximum value of the new scale.
        @return: A value scaled within the new range a and b.
        """
        return (range_b - range_a) * (x_value - x_min) / (x_max - x_min) + range_a

    @staticmethod
    def find_hundredth_upper_bound(x, max_x, min_x, range_a, max_smoothed_value) -> float:
        if max_x == min_x:
            raise RuntimeError(f"max_x == min_x")
        if min_x == x:
            raise RuntimeError(f"min_x == x")

        b = Symbol('b')
        b = solve(Eq((b - range_a) * (x - min_x) / (max_x - min_x) + range_a, max_smoothed_value), b)

        if b[0] > 100:
            b[0] = 100

        return b[0]

    @staticmethod
    def write_dict_to_csv(data: dict, output_dir: str, file_name: str, comments: str = None):
        """
        A method that takes a dictionary and uses  its keys as headers for a CSV file.

        @param data: The data passed as a dictionary.
        @param output_dir: full directory to which the output file should be saved.
        @param file_name: The desired name for the generated file.
        @param comments: Whether to add a comment to the CSV file header or not.
        """
        project_root = f"{output_dir}{file_name}.csv"

        with open(project_root, "w") as e_file:
            if comments is not None:
                e_file.write("# " + comments + "\n")
            pd.DataFrame(data).to_csv(e_file, index=False)

    @staticmethod
    def is_confident(values: List[float], k: float = 0.8) -> bool:
        """
        After normalization, compares all the values in a list to the max value. If all values (other than the max)
        are below threshold compared to normalized max, then we are confident. Otherwise, we are not.

        @param values: The list of values
        @param k: The confidence threshold.
        @return: Whether all values are below k compared to the max or not.
        """
        if not values:
            raise RuntimeError("The list is empty!")

        max_val = max(values)
        min_val = min(values)
        values.remove(max(values))  # remove the max from the list as we don't want to compare with self

        if not values:  # there was only one value in the list, thus we must be confident.
            return True

        # fixme: should we really return in this case?
        if max_val == max(values):  # the highest two values are the same, return fast
            return False

        confident = True
        for v in values:
            if (1.0 - Utility.normalize(v, max_val, min_val)) < k:  # the value 1.0 is the max value when normalized
                confident = False
        return confident

    @staticmethod
    def normalize(val, max_val, min_val):
        """
        Min-Max normalization (https://en.wikipedia.org/wiki/Feature_scaling#Rescaling_(min-max_normalization)).

        @param val: Value to be normalized.
        @param max_val: The maximum possible value in the dataset.
        @param min_val: The minimum possible value in the dataset.
        @return: A normalized value between 0 and 1.
        """
        if (max_val - min_val) == 0:
            return 0.0
        else:
            return (val - min_val) / (max_val - min_val)

    @staticmethod
    def prep_expr_for_showmax(root_path: str, expr_dir: List[str]):
        """
        For each expr directory copy all the input using a pattern we defined that would guarantee fixed naming length
        in both the dir names and the inputs names without losing essential information about the input
        (e.g. timestamp(mtime), exec, id).

        PerfFuzz inputs naming samples:
        id:004322,src:004072,op:havoc,rep:4,exec:00005455595,+max
        id:003935,src:003637+000498,op:splice,rep:4,exec:00004626249,+max
        id:002391,src:002000+002009,op:splice,rep:8,exec:00001751333,+cov,+max

        PerfRL naming samples:
        id:000091,cost:0000016880,hs:0000008440,hnb:0,exec:00000000150,len:010,tu:010+max
        id:000054,cost:0000017920,hs:0000008960,hnb:0,exec:00000000015,len:010,tu:010+cost+max

        Target naming patter for each input:
        id:{6-digit},exec:{11-digits}

        Also each dir of each experiment must be named as expt:{4-digit}. This information of the experiment itself that
        used to be saved in the name, should be saved in a file named "expr-info.txt". Users of this method will use
        that file to retrieve the experiment information.

        @param root_path:
        @param expr_dir:
        """
        # TODO: read name given the new method for names
        if root_path.endswith('/'):  # remove the last backslash
            root_path = root_path[:-1]
        expr_id = 1
        for expr in sorted(expr_dir):
            inputs_dir = 'queue' if os.path.exists(root_path + f'/{expr}' + '/queue') else 'buffer'
            technique = 'tool:PerfFuzz' if inputs_dir == 'queue' else 'tool:PerfRL'

            # create a dir for this expr and a nested dir for inputs at the same time
            try:
                os.makedirs(f"{root_path}/expr:{expr_id:04d}/inputs")
                print(f"Directory: '{root_path}/expr:{expr_id:04d}/inputs' created")
            except FileExistsError:
                print(f"Directory: '{root_path}/expr:{expr_id:04d}/inputs' already exists!")

            # save expr info to file "expr-info.txt":
            with open(f"{root_path}/expr:{expr_id:04d}/expr-info.txt", "w") as expr_info:
                expr_info.write(f'{technique}-{expr}')

            # get names of all files in queue/buffer
            inputs = [f.name for f in os.scandir(root_path + f'/{expr}' + f'/{inputs_dir}') if f.is_file()]

            # loop saved inputs to copy each one to the new destination given the same parts of the name we care about
            for file_name in inputs:

                input_id = None
                input_exec = None
                input_crtime = None
                input_dur = None

                # remove postfix (e.g., +max, +cov, or +cost)
                base_name = file_name
                base_name = Utility.remove_suffix(base_name)

                # break by indicators and their values
                if base_name.endswith(','):
                    base_name = base_name[:-1]
                indicators = base_name.split(',')

                # checking if we should skip an input because it is an orig
                skip_this_input = False
                for indicator in indicators:  # e.g. id:****, exec:****, ... etc
                    broken_indicator = indicator.split(':')
                    if len(broken_indicator) == 2:
                        indicator_id, indicator_val = broken_indicator
                        if indicator_id in ['orig']:
                            skip_this_input = True

                if skip_this_input:
                    continue

                for indicator in indicators:  # e.g. id:****, exec:****, ... etc
                    broken_indicator = indicator.split(':')
                    if len(broken_indicator) == 2:
                        indicator_id, indicator_val = broken_indicator
                        if indicator_id == 'id':
                            input_id = int(indicator_val)
                        if indicator_id == 'exec':
                            input_exec = int(indicator_val)
                        if indicator_id == 'crtime':
                            input_crtime = int(indicator_val)
                        if indicator_id == 'dur':
                            input_dur = int(indicator_val)
                if input_id is None:
                    raise RuntimeError(f'Failed passing the id of the input{file_name} in '
                                       f'{root_path}/{expr}/{inputs_dir}')

                if input_crtime is None or input_dur is None or input_exec is None:
                    raise RuntimeError(f'Accepting new experiments only! {file_name} in '
                                       f'{root_path}/{expr}/{inputs_dir} did not have exec, crtime, or dur')

                # the flag -p is to preserve the file mtime timestamp
                subprocess.run(['cp', '-p', f'{root_path}/{expr}/{inputs_dir}/{file_name}',
                                f'{root_path}/expr:{expr_id:04d}/inputs/id:{input_id:06d},exec:{input_exec:011d},'
                                f'crtime:{input_crtime},dur:{input_dur:010d}'])
            expr_id += 1

    @staticmethod
    def remove_suffix(file_name: str, possible_suffixes=('+max', '+cov', '+cost')) -> str:
        """
        Helper function to remove the suffixes added to the input files names.
        @param file_name: The file name with the undesired suffix.
        @param possible_suffixes: The suffixes that we might encounter and would like  to remove.
        @return: The same file name without any of the suffixes given.
        """
        while file_name.endswith(possible_suffixes):
            for suffix in possible_suffixes:
                if file_name.endswith(suffix):
                    file_name = file_name[:-len(suffix)]
        return file_name

    @staticmethod
    def get_expr_dirs(root_dir: str) -> list:
        """
        Helper function to collect the experiments directories for post-processing.

        @param root_dir: The main directory where all the experiments are collected.
        @return: A list of all the valid experiments directories.
        """

        # collect  all sub-dir names in a list (if any)
        sub_dir = [f.name for f in os.scandir(root_dir) if f.is_dir()]

        expr_dir = []  # expr sub-dir only

        for dir_name in sub_dir:
            if str(dir_name).startswith("expr:"):
                expr_dir.append(dir_name)

        if not expr_dir:
            raise RuntimeError(f'No "expr:" directories in the root dir {root_dir}')
        return sorted(expr_dir)

    @staticmethod
    def top_n(items: Iterable, n: int = 10, key: Callable = None) -> Iterable:
        """
        Get the top (max) n elements in an iterable.

        @param items: The set of items to evaluate.
        @param n: The number of items to return.
        @param key: A key criteria to evaluate.
        @return: An iterable of len n or less sorted based on the key if given.
        """
        iter_len = sum(1 for _ in items)
        if n >= iter_len:
            return items
        
        if key is None:
            var = sorted(items)[-n:]
        else:
            var = sorted(items, key=key)[-n:]
        return var

    @staticmethod
    def get_prc_of_value_above_threshold(data: List[int], k: int) -> float:
        """
        Given a list of data points, find the percentage of values above or equal to a given threshold
        from the list. For example, if the list is [1,2,3,4,5] and k=3, then the return value is 0.6 (i.e., 60%).

        @param data: List of data points
        @param k: Threshold to compare against.
        @return: Percentage of instances larger or equal to `k` from `data`.
        """
        if data:
            x = sum(i >= k for i in data)  # num of values larger than or equal to k
            return x / len(data)
        else:
            return 0.0

    @staticmethod
    def find_prc_of_val_greater_than(data: List[int], k: int) -> float:
        if data:
            x = sum(i >= k for i in data)  # num of values larger than or equal to k
            return x/len(data)
        else:
            return 0.0

    @staticmethod
    def find_prc_uniq_values(data: List[int]) -> float:
        """
        A function to calculate the percentage of duplicate value in a list. For example, if data=[1,1,1,2] then the
        return value will be 0.5 (or 50%). That is out of the four element only 50% are unique.

        @param data: A list of numbers.
        @return:  The percentage of unique value to the number of element in the list.
        """
        if data:
            return len(np.unique(data)) / len(data)
        else:
            return 0.0  # special case

    @staticmethod
    def tree_state(node: MCTSNode) -> str:
        """
        Tree printing helper method.

        @param node: The root node from which we would like to start the printing process.
        """
        indent = "    "
        tree = ''
        tree += f"{node.level*indent}{node}\n"
        for child in node.get_children():
            tree += Utility.tree_state(child)
        return tree

    @staticmethod
    def tree_to_dot(node: MCTSNode) -> str:
        """
        Generate a tree written in a dot language for post-print rendering. The method works for the target applications
        we tried. However, there is no guarantee that it would work for all target applications as the depending on the
        applications' language it can interfere with the dot code.

        @param node: The root node from which we would print the tree.
        @return: The dot file as a string.
        """
        # open the graph and add high-level attributes
        dot_rep = "digraph {\n"
        dot_rep += "\tnode [shape=record, colorscheme=rdylbu11];\n"

        # add graph nodes based on tree (body)
        dot_rep += Utility.node_to_struct(node, True)

        # add the legend and close the whole graph
        dot_rep += "\tsubgraph cluster_key {\n"
        dot_rep += "\t\trank=sink;\n"
        dot_rep += "\t\tstyle = filled;\n"
        dot_rep += "\t\tcolor=lightgrey;\n"
        dot_rep += "\t\tlabel=\"Legend\";\n"
        dot_rep += "\t\tdetails [label=\"{Generated input\\n'' means empty|len(input)= length \\nof generated input|" \
                   "# used tokens = total terminal token \\nused to generated the shown input \\nwhich must never " \
                   "exceed the budget}|" \
                   "SYMBOL\\nunder evaluation|" \
                   "{AB= Allowed Budget|PB= Passed Budget|len(s)= Stack Size}|" \
                   "STACK|" \
                   "{V= Total Costs (sum) based on \\nany descendant of this node|N= No. of Visits|UCB= UCB value to " \
                   "reach \\nthis node from parent}" \
                   "}\"];\n"
        dot_rep += "\t\tbest_intermediate [label=\"Intermediate Node in Best Path\"; style=filled; fillcolor=8]\n"
        dot_rep += "\t\tbest_leaf [label=\"Leaf Node in Best Path\"; style=filled; fillcolor=7]\n"
        dot_rep += "\t\tbest_terminal [label=\"Terminal Node in Best Path\"; style=filled; fontcolor=white; " \
                   "fillcolor=9]\n"
        dot_rep += "\t\tintermediate [label=\"Intermediate Node\"; style=filled; fillcolor=4]\n"
        dot_rep += "\t\tleaf [label=\"Leaf Node\"; style=filled; fillcolor=5]\n"
        dot_rep += "\t\tterminal [label=\"Terminal Node\"; style=filled; fillcolor=3]\n"
        dot_rep += "\t}\n"
        dot_rep += "}\n"

        return dot_rep

    @staticmethod
    def node_to_struct(node: MCTSNode, is_best: bool) -> str:

        if node.locked:
            dot_struct = f"\tstruct{id(node)} [style=filled; fontcolor=white; fillcolor=black; label=\""
        elif is_best:  # blue background
            if node.is_terminal():
                dot_struct = f"\tstruct{id(node)} [style=filled; fontcolor=white; fillcolor=9; label=\""
            elif node.is_leaf():
                dot_struct = f"\tstruct{id(node)} [style=filled; fillcolor=7; label=\""
            else:
                dot_struct = f"\tstruct{id(node)} [style=filled; fillcolor=8; label=\""
        else:  # gold background
            if node.is_terminal():
                dot_struct = f"\tstruct{id(node)} [style=filled; fillcolor=3; label=\""
            elif node.is_leaf():
                dot_struct = f"\tstruct{id(node)} [style=filled; fillcolor=5; label=\""
            else:
                dot_struct = f"\tstruct{id(node)} [style=filled; fillcolor=4; label=\""

        # input and len of input
        # escape all characters except the ones specified below, because they could be graphviz chars.
        dot_struct += "{'" + re.sub("([^a-zA-Z0-9])", r"\\\1", node.text) + "'| "
        dot_struct += f" len(input): {len(node.text)}|# used tokens: {node.tokens_used}"
        dot_struct += "}|"

        # symbol in hand
        if isinstance(node.symbol, RHSItem):
            # escape all characters except the ones specified below
            dot_struct += re.sub("([^a-zA-Z0-9])", r"\\\1", node.symbol.__str__()) + "|"
        else:
            dot_struct += f"{node.symbol}|"

        # budget and stack information
        dot_struct += "{"
        dot_struct += f"AB: {node.allowed_budget}|PB:{node.budget}|len(s):{len(node.stack)}"
        dot_struct += "}|"

        # stack content
        reversed_stack = node.stack[::-1]
        dot_struct += "{"
        if reversed_stack:
            for item in reversed_stack:
                # escape all characters except the ones specified below
                dot_struct += re.sub("([^a-zA-Z0-9])", r"\\\1", item.__str__()) + "|"
            dot_struct = dot_struct[:-1]  # removing the last char "|" in the string.
        else:
            dot_struct += f"EMPTY\\nSTACK"
        dot_struct += "}|"

        # MCTS information (V, N, UCB)
        dot_struct += "{"
        dot_struct += f"V: {node.get_total_cost()}|N: {node.get_visits()}| UCB1: {node.get_ucb1()}"
        dot_struct += "}\"];\n"

        if node.get_children() and is_best:  # if it has children, and it is in the best path, then get the max child
            max_child = max(node.get_children(), key=lambda n: n.get_ucb1())
            max_ucb = max_child.get_ucb1()  # get the best child ucb1 value for coloring
        else:
            max_ucb = -1.0

        for child in node.get_children():
            if child.get_ucb1() == max_ucb:
                dot_struct += Utility.node_to_struct(child, True)
            else:
                dot_struct += Utility.node_to_struct(child, False)
            dot_struct += f"\tstruct{id(node)} -> struct{id(child)} "
            c = Utility.scale_to_range(child.level, 181, 0, 1, 2)
            if child.get_ucb1() == float("inf") or child.get_ucb1() == float("-inf"):
                dot_struct += f"[taillabel=\"C={round(c, 2)}, UCB={round(child.get_ucb1(), 4)}, " \
                              f"level={child.level}\"; penwidth={0.5}];\n"
            else:
                dot_struct += f"[taillabel=\"C={round(c, 2)}, UCB={round(child.get_ucb1(), 4)}, " \
                              f"level={child.level}\"; penwidth={round(child.get_ucb1(), 4)}];\n"
        return dot_struct

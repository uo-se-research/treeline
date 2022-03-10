__author__ = "Ziyad Alsaeed"
__email__ = "zalsaeed@cs.uoregon.edu"
__status__ = "Testing"

import os
import csv
import datetime
import subprocess
from pathlib import Path
from typing import List, Iterable, Callable

# import torch
import pandas as pd
from sympy.solvers import solve
from sympy import Symbol
from sympy import Eq

from targetAppConnect import InputHandler


class Utility:

    @staticmethod
    def scale_to_range(x, max_x, min_x, range_a, range_b) -> float:
        """

        :param x: tha value to scale.
        :param max_x: the maximum value in the range from where x is given.
        :param min_x: the minimum value in the range from where x is given.
        :param range_a: the minimum value of the new scale.
        :param range_b: the maximum value of the new scale.
        :return: A value scaled within the new range a and b.
        """
        return (range_b - range_a) * (x - min_x) / (max_x - min_x) + range_a

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

        :param values: the list of values
        :param k: the confidence threshold.
        :return: whether all values are below k compared to the max or not.
        """
        if not values:
            raise RuntimeError("The list is empty!")

        max_val = max(values)
        min_val = min(values)
        values.remove(max(values))  # remove the max from the list as we don't want to compare with self

        if not values:  # there was only one value in the list, thus we must be confident.
            return True

        if max_val == max(values):  # the highest two values are the same, return fast
            return False

        confident = True
        for v in values:
            if (1.0 - Utility.normalize(v, max_val, min_val)) < k:  # the value 1.0 is the max value when normalized
                confident = False
        return confident

    @staticmethod
    def normalize(val, max_val, min_val):
        if (max_val - min_val) == 0:
            return 0.0
        else:
            return (val - min_val) / (max_val - min_val)

    @staticmethod
    def convert_durations_to_timedelta(durations: List[str]):
        # TODO: delete as this is not used anymore
        timedelta_durations = []
        for duration in durations:
            time_obj = datetime.datetime.strptime(duration, "%H:%M:%S")
            timedelta_durations.append(datetime.time(hour=time_obj.hour,
                                                     minute=time_obj.minute,
                                                     second=time_obj.second))
        return timedelta_durations

    @staticmethod
    def run_inputs_and_write_to_csv(dirname: str):

        if not os.path.isdir(dirname):
            raise RuntimeError(f"{dirname} is not a directory")

        # get the file sorted by their modification time
        files = sorted(Path(dirname).iterdir(), key=os.path.getmtime)

        # make sure there are files in the dir.
        if not files:
            raise RuntimeError(f"There no files in {dirname}")

        input_handler = InputHandler()
        if not input_handler.is_connected():
            print(f"No connection to input handler")

        start_time = int(files[0].stat().st_mtime * 1000)  # first file m-time on ms
        with open(f'{dirname}/costs.csv', "w") as e_file:
            writer = csv.writer(e_file)
            writer.writerow(['time_millisecond', 'total_exec_costs'])  # header

            for f in files:
                # get the files timestamp relative to the first file on list.
                # file timestamp should be in milliseconds in accordance to PerfFuzz's timestamp
                time_millisecond = int(f.stat().st_mtime * 1000) - start_time

                with open(f, "rb") as tc:
                    test_case = tc.read()
                # print(test_case)
                # print(test_case.decode("utf-8"))

                cost, _, _, _ = input_handler.run_input(test_case, "wup")
                # print(cost)
                writer.writerow([time_millisecond, cost])

    @staticmethod
    def get_expr_description(file_name: str) -> tuple:
        """
        Given a file name for one of the experiment. This will do the necessary massaging to the name (old or new) to
        return a name that is as unique to this experiment as possible without the data and time difference.

        The necessity of this is to find files that match in terms of experiment settings and group them together.
        Also, since this is a lot of work already. We take advantage of this and return an indicator to tell us if this
        is a file for PerfFuzz or for one of our techniques.
        :param file_name: the whole file name (e.g. "name.csv")
        :return: a tuple of the base name and whether this is a perffuzz run or not (name, bool:True if for PerfFuzz).
        """
        if not file_name.endswith('.csv'):
            raise RuntimeError(f"Can only process CSV files. Got {file_name}")

        if file_name.startswith("PerfFuzz") or file_name.startswith("tool:PerfFuzz"):
            if file_name.startswith('PerfFuzz'):  # old format
                # Patter sample: "PerfFuzz-libxml2-60-may-11-02"
                app_name = file_name.split('-')[:-3]  # split name by "-", and drop last 3 indicators (month, day, id).
                expr_desc = []
                ids = ['tool', 'app', 'budget']
                for idx, val in enumerate(app_name):
                    expr_desc.append(f"{val}:{ids[idx]}")
                return "-".join(expr_desc), True  # rejoin with the same delimiter
            else:
                # Pattern sample "tool:PerfFuzz-app:libxml2-budget:60-month:may-day:11-id:01"
                app_name = file_name.split('-')[:-3]  # split name by "-", and drop last 3 indicators (month, day, id).
                return "-".join(app_name), True  # rejoin with the same delimiter
        elif file_name.startswith('Progress-report') or file_name.startswith('PerfRL'):
            # we have two possibilities here, "Progress-report" without indicator-ids or "Progress-report-app:..."
            # which has the indicator ids and easy to parse.

            # Pattern Sample: "Progress-report-libxml2(DroppingIdleTreesAfterUnique,Fixed20Threshold,
            # AllSpecialChar)-lcc-gram-libxml2-free-typing.txt-c=1.5-e=20-lockingTrue-budget=60-reward-
            # type=smoothed-SUB=1-iter=80000-05262021-092828.csv"
            app_name = file_name.split('-')
            if app_name[0] == 'PerfRL':
                app_name = "-".join(app_name[1:-2])  # throw the first part and last two stings broken by delimiter
            else:
                app_name = "-".join(app_name[2:-2])  # throw the first and last two stings broken by delimiter

            if app_name.startswith('app:'):
                return app_name, False
            else:
                app_name = app_name.split('-')
                has_description = False
                if '(' in app_name[0] and ')' in app_name[0]:  # then this must have a description
                    has_description = True

                expr_desc = []
                if has_description:
                    app_name_and_desc = app_name[0].split('(')
                    expr_desc.append(f'tool:PerfRL')
                    expr_desc.append(f"app:{app_name_and_desc[0]}")
                    expr_desc.append(f"desc:{app_name_and_desc[1][:-1]}")
                    app_name.pop(0)  # we already parsed this, remove it
                else:
                    expr_desc.append(f'tool:PerfRL')
                    expr_desc.append(f"app:{app_name.pop(0)}")

                ids = ['alg', 'gram', 'c', 'e', 'locking', 'budget', 'RewardType', 'SUB', 'iter']

                matching_parts = []
                while app_name:
                    part = app_name.pop(0)
                    if part == 'gram':
                        while app_name:  # inner loop to collect  gram file name
                            gram_part = app_name.pop(0)
                            if gram_part.endswith('.txt'):
                                part += f'_{gram_part}'
                                break
                            else:
                                part += f'_{gram_part}'
                    if part == 'reward':
                        part += app_name.pop(0)
                    matching_parts.append(part)

                for idx, val in enumerate(ids):
                    info = matching_parts[idx].split('=')
                    if len(info) > 1:
                        info = info[1]
                    else:
                        info = "".join(info)
                    expr_desc.append(f"{val}:{info}")

                return "-".join(expr_desc), False
        else:
            # this is the new pattern. Parts are split by "-" and each part is split by ":"
            # you only need to drop the file extension ".csv" then collect things easily
            app_name = file_name[:-4]  # copy name and drop the ".csv"
            app_name = app_name.split('-')
            app_name = app_name[:-2]  # dropping the last two parts (date and time)
            return "-".join(app_name), False
        # else:
        #     # Then we don't know what this file is, this must be a csv file passed by mistake
        #     raise RuntimeError(f'Unknown file pattern {file_name}')

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

        :param root_path:
        :param expr_dir:
        :return:
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
    def remove_suffix(file_name: str, possible_suffixes=('+max', '+cov', '+cost')):
        while file_name.endswith(possible_suffixes):
            for suffix in possible_suffixes:
                if file_name.endswith(suffix):
                    file_name = file_name[:-len(suffix)]
        return file_name

    @staticmethod
    def get_expr_dirs(root_dir: str) -> list:
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
        iter_len = sum(1 for _ in items)
        if n >= iter_len:
            return items
        
        if key is None:
            var = sorted(items)[-n:]
        else:
            var = sorted(items, key=key)[-n:]
        return var

    @staticmethod
    def show_max_cost_of_csv_files(path: str):
        if not os.path.isdir(path):
            raise RuntimeError(f"Path given is not a dir! PATH={path}")
        files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]

        l_sum = 0
        for file in sorted(files):
            if file.startswith("."):
                continue
            df = pd.read_csv(f"{path}/{file}", comment="#")
            l_max = df.cost.max()
            l_sum += l_max
            print(f"File {file}")
            print(f"Max= {Utility.human_format(l_max)} ({l_max})")
        avg = l_sum/len(files)
        print(f"Average maximum cost is {Utility.human_format(avg)} ({avg})")

    @staticmethod
    def human_format(num):
        """
        As found in https://stackoverflow.com/a/45846841/3504748
        :param num: the number we are formatting.
        :return:
        """
        num = float('{:.3g}'.format(num))
        magnitude = 0
        while abs(num) >= 1000:
            magnitude += 1
            num /= 1000.0
        return '{}{}'.format('{:f}'.format(num).rstrip('0').rstrip('.'), ['', 'K', 'M', 'B', 'T'][magnitude])

    @staticmethod
    def get_tool_name_from_expr_file(exper_file: str) -> str:
        indicators = exper_file.split('-')
        if not indicators[0].startswith("tool:"):
            raise RuntimeError(f"A tool name is not given in file: {exper_file}")

        _, tool_name = indicators[0].split(":")
        if tool_name in ["PerfRL", "PerfMCTS"]:
            tool_name = "TreeLine"
        return tool_name

    @staticmethod
    def incident_prc_of_value_threshold(data: List[int], k: int) -> float:
        """
        Given a list of data points. This method finds the percentage of values above or equal to a given threshold
        from the list.

        :param data: List of data points
        :param k: threshold to compare against.
        :return: percentage of instances larger or equal to k from data.
        """
        if data:
            x = sum(i >= k for i in data)  # num of values larger than or equal to k
            return x / len(data)
        else:
            return 0.0

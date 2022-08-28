__author__ = "Ziyad Alsaeed"
__email__ = "zalsaeed@cs.uoregon.edu"
__status__ = "Testing"

import os
import shutil
import subprocess
from collections import defaultdict
import warnings


class AppRunner:

    def __init__(self, target_app_bin: str):
        """

        :param target_app_bin: the path or name (if it is in env PATH) of binary file.
        """
        if len(target_app_bin.split(" ")) > 1:
            target_app_bin_list = target_app_bin.split(" ")
            self.target_app_bin = target_app_bin_list.pop(0)  # the first element must be the bin
            self.target_flags = []
            for flag in target_app_bin_list:
                self.target_flags.append(flag)
        else:
            self.target_app_bin = target_app_bin
            self.target_flags = []
        if shutil.which(self.target_app_bin) is None:  # if the path to binary can't be resolved, throw an error!
            raise RuntimeError(f"The binary given {self.target_app_bin} does not exist!")
        self.timeout_flag = '-t 10000'

    def run_showmax(self, path_to_input: str) -> tuple:
        """
        Given a file, this method runs the target app using the input file and return the path length, the hotspot,
        and the coverage count of the input based on target app.
        :param path_to_input: input file.
        :return: A tuple of three integers (path_len, hotspot, coverage).
        """
        if not os.path.isfile(path_to_input):
            raise RuntimeError(f"The path given {path_to_input} is not for a file!")

        return self.run_showmax_path_len(path_to_input), self.run_showmax_hotspot(
            path_to_input), self.run_showmax_coverage(path_to_input)

    def run_showmax_path_len(self, path_to_input: str) -> int:
        if not os.path.isfile(path_to_input):
            raise RuntimeError(f"The path given {path_to_input} is not for a file!")
        command = subprocess.run(['afl-showmax', self.timeout_flag, self.target_app_bin] + self.target_flags +
                                 [path_to_input], capture_output=True)

        if command.returncode == 0:  # success, then capture output.
            return int(command.stdout)
        else:
            warnings.warn(f"Command failed with message: {command.stderr}, cod: {command.returncode}. "
                          f"On file: {path_to_input}")
            return int(command.stdout)

    def run_showmax_hotspot(self, path_to_input: str) -> int:
        if not os.path.isfile(path_to_input):
            raise RuntimeError(f"The path given {path_to_input} is not for a file!")
        command = subprocess.run(['afl-showmax', '-x', self.timeout_flag, self.target_app_bin] + self.target_flags +
                                 [path_to_input], capture_output=True)

        if command.returncode == 0:  # success, then capture output.
            return int(command.stdout)
        else:
            warnings.warn(f"Command failed with message: {command.stderr}. On file: {path_to_input}")
            return int(command.stdout)

    def run_showmax_coverage(self, path_to_input: str) -> int:
        return len(self.run_showmax_perf_map(path_to_input))

    def run_showmax_perf_map(self, path_to_input: str) -> dict:
        if not os.path.isfile(path_to_input):
            raise RuntimeError(f"The path given {path_to_input} is not for a file!")
        command = subprocess.run(['afl-showmax', '-a', self.timeout_flag, self.target_app_bin] + self.target_flags +
                                 [path_to_input], capture_output=True)

        # if command.returncode == 0:  # success, then capture output.
        perf_map = defaultdict(int)
        stdout = command.stdout.decode('ascii').split('\n')
        stdout = stdout[:-1]  # splitting on newline produce an empty pocket at the end. We delete it.
        for pocket in stdout:
            p = pocket.split(' ')
            if len(p) != 2:
                raise RuntimeError(f"Received an anomalous data {p} of len={len(p)} from stdout.")
            perf_map[int(p[0])] = int(p[1])
        # return perf_map
        if command.returncode == 0:
            return perf_map
        else:
            warnings.warn(f"Command failed with message: {command.stderr}. On file: {path_to_input}")
            return perf_map

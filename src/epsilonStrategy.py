__author__ = "Ziyad Alsaeed"
__email__ = "zalsaeed@cs.uoregon.edu"
__status__ = "Testing"

import math


class EpsilonGreedyStrategy:
    def __init__(self, max_exploration_rate: float, min_exploration_rate: float, decay_rate: float):
        """
        Constructor!

        :param max_exploration_rate: the max possible probability of exploration at the beginning of learning
        (epsilon=max_exploration_rate)
        :param min_exploration_rate: the min possible probability of exploration at the throughout the learning process
        :param decay_rate: the decay rate of exploration as we step through the environment we are learning. In other
        words, the speed in which we transition from exploration to exploitation.
        """
        self.max_exploration_rate = max_exploration_rate
        self.min_exploration_rate = min_exploration_rate
        self.decay_rate = decay_rate

    def get_exploration_rate(self, current_episode: int) -> float:
        """
        A simple method that calculate the exploration rate based on how advance we are in the envrionment (how many
        steps we took) and the other constraints given by the user at the beginning of the experiment.

        :param current_episode: A count of the steps the agent took so far.
        :return: a decimal representing the exploration rate.
        """
        return self.min_exploration_rate + (self.max_exploration_rate - self.min_exploration_rate) \
            * math.exp(-1. * current_episode * self.decay_rate)

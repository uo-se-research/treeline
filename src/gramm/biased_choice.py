"""A substitute for random.choice that (choose from a list) with learnable bias.
Keeps a side table of weights which can be incremented (rewarded) or decremented (penalized)
and biases future choices toward those biases.
"""
import random
from typing import List

import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

# Tuning constants
#
# The weight that all items start at.  Must be in open interval
# 0.0 .. 1.0.  I can't think of a reason that this would change.
DEFAULT_WEIGHT = 0.5
#
# Default learning rates.  Move current weight what fraction of the way from its
# current value toward 1.0 (if reward) or 0.0 (if penalty).  Small values will learn
# slowly, large values will oscillate.  If rewards are rare, we might want a penalty
# delta that is smaller than the reward delta.
REWARD_DELTA = 0.5
PENALTY_DELTA = 0.05
#
# If we have a bigram xa, and we also have a weight for a regardless of
# prior, how much of the weight value should depend on the bigram weight?
# Since we see individual items more often than we see bigrams, this should
# probably not be 1.0.
BIGRAM_PRIORITY = 0.99

class _BiasCore:
    """Core shared state of the biased chooser.  When a chooser is
    forked, we keep a reference to this part (i.e., it is shared
    among all Bias objects forked from an initial Bias object).
    """

    def __init__(self,
                 default_weight=DEFAULT_WEIGHT,
                 reward_delta=REWARD_DELTA,
                 penalty_delta=PENALTY_DELTA,
                 bigram_priority = BIGRAM_PRIORITY):
        assert 0.0 < default_weight < 1.0, "default weights must be in open interval 0.0..1.0"
        self.default_weight = default_weight
        assert 0.0 < reward_delta < 1.0
        self.reward_delta = reward_delta
        assert 0.0 < penalty_delta < 1.0
        self.penalty_delta = penalty_delta
        self.bigram_priority = bigram_priority
        self.weights = {}
        self.bigram_weights = {}

    def __str__(self) -> str:
        """String representation is likely to be large, so we will
        format it into several lines.
        """
        lines = []
        lines.append("Individual choice weights:")
        for choice in sorted(self.weights.keys(), key=str):
            lines.append(f"   {choice}:\t{self.weights[choice]}")
        lines.append("")
        lines.append("Bigram weights:")
        for choice in sorted(self.bigram_weights.keys(), key=str):
            prior, item = choice
            lines.append(f"   {prior} => {item}:\t{self.bigram_weights[choice]}")
        return "\n".join(lines)

    def choose(self, choices: List[object], prior=None):
        """Make a biased choice among choices."""
        if not choices:
            return None
        sum_weight = sum(self.weight(item, prior) for item in choices)
        r = random.random()  # In open interval 0.0 .. 1.0
        log.debug(f"Rolled {r:1.3}")
        bound = 0.0  # Sum of adjusted weights so far
        for item in choices:
            weight = self.weight(item, prior)
            portion = weight / sum_weight
            bound += portion
            log.debug(f"{item} weight {weight:0.3}({portion:0.3}), new bound {bound:0.3}")
            if r <= bound:
                log.debug(f"Chose {item}")
                return item
        # Infinitessimal possibility of roundoff error
        log.debug("None of the above; but return {choices[-1]}")
        return choices[-1]

    def weight(self, item: object, prior=None) -> float:
        """Current weight of an item, initialized if needed."""
        bigram = (prior, item)
        if item not in self.weights:
            self.weights[item] = self.default_weight
        item_weight = self.weights[item]
        if bigram not in self.bigram_weights:
            # Haven't seen it in this context; depend on its
            # overall weight from all contexts in which we've seen it.
            # log.debug(f"First sighting of {bigram}")
            return item_weight
        bi_weight = self.bigram_weights[bigram]
        log.debug(f"Combining weights {item_weight} with bigram weight {bi_weight}")
        return self.bigram_priority * bi_weight + (1 - self.bigram_priority) * item_weight


    def reward(self, item: object, prior: object=None):
        """Choose this one / this pair more often"""
        old_weight = self.weight(item)
        new_weight = old_weight + self.reward_delta * (1.0 - old_weight)
        self.weights[item] = new_weight
        if not prior:
            # No bigram
            return
        # Record a weight for the bigram
        bigram = (prior, item)
        if bigram in self.bigram_weights:
            old_weight = self.bigram_weights[bigram]
        else:
            old_weight = self.default_weight
        new_weight = old_weight + self.reward_delta * (1.0 - old_weight)
        self.bigram_weights[bigram] = new_weight

    def penalize(self, item: object=None, prior: object=None):
        """Choose this one / these less often"""
        old_weight = self.weight(item)
        new_weight = old_weight - self.penalty_delta * old_weight
        self.weights[item] = new_weight
        if not prior:
            return
        bigram = (prior, item)
        if bigram in self.bigram_weights:
            old_weight = self.bigram_weights[bigram]
        else:
            old_weight = self.default_weight
        new_weight = old_weight - self.penalty_delta * old_weight
        self.bigram_weights[bigram] = new_weight


class Bias:
    """Provides a 'choice' method like random.choice but weighted.
    Choices must be hashable.
    """
    def __init__(self,
                default_weight = DEFAULT_WEIGHT,
                reward_delta = REWARD_DELTA,
                penalty_delta = PENALTY_DELTA,
                bigram_priority = BIGRAM_PRIORITY,
                forked=False):
        if not forked:
            self.core = _BiasCore(default_weight,  reward_delta, penalty_delta, bigram_priority)
            self.history = []

    def fork(self) -> 'Bias':
        forked = Bias(forked=True)
        forked.core = self.core
        forked.history = self.history.copy()
        return forked

    def choose(self, choices: List[object]):
        """Make a biased choice among choices."""
        if len(self.history) > 0:
            prior = self.history[-1]
        else:
            prior = None
        choice = self.core.choose(choices, prior)
        self.history.append(choice)
        return choice

    def reward(self):
        """These were good choices; make them more often"""
        prior = None
        for item in self.history:
            self.core.reward(item, prior=prior)
            prior = item

    def penalize(self):
        """These were not good choices; avoid them"""
        prior = None
        for item in self.history:
            self.core.penalize(item, prior=prior)
            prior = item

    def __str__(self) -> str:
        return str(self.core)




def main():
    """Smoke test, biases letter choice toward end of alphabet.
    We should see random words tend toward later letters after
    a few hundred iterations.
    """
    letters = list("abcdefghijklmnopqrstuvwxyz")
    # letters = list("akemix")   # Simpler problem for debugging
    root_chooser = Bias()
    for epoch in range(100):
        epoch_score = 0
        for trial in range(100):
            chooser = root_chooser.fork()
            word_letters = []
            if epoch > 999 and trial == 999:  # Enable by putting epoch bound lower
                log.setLevel(logging.DEBUG)
                log.debug("*** EPOCH ***")
            for pos in range(5):   ### Length of word, critical parameter
                xl = chooser.choose(letters)
                word_letters.append(xl)
            log.setLevel(logging.INFO)
            word = "".join(word_letters)
            if can_pronounce(word):
                epoch_score += 1
                chooser.reward()
            else:
                chooser.penalize()
        print(f"{word}  / This epoch score {epoch_score}")
    # print(root_chooser.core.weights)
    # bigram_weights = list(root_chooser.core.bigram_weights.items())
    # print(sorted(bigram_weights))
    print("Weights at conclusion:")
    print(chooser.core)

def can_pronounce(word: str) -> bool:
    """Simple relation to learn:  We'll say a word can be
    pronounced if it alternates consonants with vowels.
    """
    consonants = set("bcdfghjklmnpqrstvwxyz")
    vowels = set("aeiouy")
    # State machine:
    transitions = [
        [1, 2], # 0/consonant -> state 1, 0/vowel -> state 2
        [-1, 2], # 1/consonant -> FAIL, 1/vowel -> state 2
        [1, -1]   # 2/consonant -> 1, 2/vowel -> FAIL
    ]
    state = 0
    for letter in word:
        if letter in consonants:
            state = transitions[state][0]
        elif letter in vowels:
            state = transitions[state][1]
        if state < 0:
            return False
    return True


if __name__ == "__main__":
    main()




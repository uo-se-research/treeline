"""Basic configuration constants, lower level than search_conf.py,
and imported into search.py directly as well as mutant_search.py indirectly.
"""

# C = 1.4   # ratio of exploration to exploitation factors in UCT
C = 3.0

HOT_BUF_SIZE = 300 # 50   # Was 300

# Winnowing is discarding inputs that have not proved
# useful, in particular inputs that were retained because of
# new coverage but which are no longer unique in achieving that
# coverage (i.e., superseded by other inputs discovered later)

WINNOW_TRIGGER_SIZE = 1000   # Initially 1000, fairly conservative to avoid overshoot
WINNOW_TRIGGER_GROW = 1.25   # Lower bound on how much frontier must grow before next winnow


# Weighting factors for "wins", instead of 1/0
#
WEIGHT_NEWCOV = 1.0
WEIGHT_NEWMAX = 5.0
WEIGHT_NEWCOST = 10.0
WEIGHT_QUANTILE = 3.0 # In the top quantile

# What is "nearly top cost"?
# We'll start with top 5th percentile
QUANTILE = 0.05



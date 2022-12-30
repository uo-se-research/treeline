"""Basic configuration constants, lower level than search_conf.py,
and imported into search.py directly as well as mutant_search.py indirectly.
"""

# C = 1.4   # ratio of exploration to exploitation factors in UCT
C = 3.0

HOT_BUF_SIZE = 300
HOT_BUF_MIN = 100
HOT_BUF_MAX = 1000
HOT_BUF_FRAC = 0.5

# Weighting factors for "wins", instead of 1/0
#
WEIGHT_NEWCOV = 1.0
WEIGHT_NEWMAX = 5.0
WEIGHT_NEWCOST = 10.0
WEIGHT_QUANTILE = 3.0 # In the top quantile

# What is "nearly top cost"?
# We'll start with top 5th percentile
QUANTILE = 0.05




"""Global variables for Treeline"""

C = 2
"""The value of C within UCB formula that determines the exploration probability (higher C == more exploration).
"""


E = 10
"""A threshold used to determine how many minimum visits are required before a node can be expanded. Higher value means
less memory stress.
"""

TARGET_APP_MIN_POSSIBLE_COST = 50
"""A threshold we use to callout anomalous runs. This will be updated after the warmup phase. But in our experience we
never see anything valid below 50.
"""


extensive_data_tracking = True
"""A global variable to turn on/off the data tracking for the non-essential pieces of progress monitoring. For
reportable runs we want to track minimal data.
"""

buckets = [500, 1000, 100000, 1000000, 1000000000]  # ranges of costs
tails = [200000, 100000, 50000, 25000, 5000, 2500]  # possible tails
"""Creating a mapping between ranges of cost and tail. These arrays are used in the main algorithm to adjust the tail size
each time we observe a new max cost.

+----------------------------+-------------+
| cost range                 |  tail size  |
+============================+=============+
| 0 - 499                    | 200,000     |
+----------------------------+-------------+
| 500 - 999                  | 100,000     |
+----------------------------+-------------+
| 1,000 - 99,999             | 50,000      |
+----------------------------+-------------+
| 100,000 - 999,999          | 25,000      |
+----------------------------+-------------+
| 1,000,000 - 999,999,999    | 5,000       |
+----------------------------+-------------+
| 1,000,000,000 - infinity   | 2,500       | 
+----------------------------+-------------+

:Usage example:
.. code-block:: python

    for i in [0, 499, 500, 999, 1000, 99999, 100000, 999999, 1000000, 999999999, 1000000000]:
        idx = np.digitize(i, bins=buckets)
        print(f"range: {i} has index={idx} which translate to tail={tails[idx]}")

:The results would be:
.. code-block::

    range: 0 has index=0 which translate to tail=200000
    range: 499 has index=0 which translate to tail=200000
    range: 500 has index=1 which translate to tail=100000
    range: 999 has index=1 which translate to tail=100000
    range: 1000 has index=2 which translate to tail=50000
    range: 99999 has index=2 which translate to tail=50000
    range: 100000 has index=3 which translate to tail=25000
    range: 999999 has index=3 which translate to tail=25000
    range: 1000000 has index=4 which translate to tail=10000
    range: 999999999 has index=4 which translate to tail=10000
    range: 1000000000 has index=5 which translate to tail=5000
"""

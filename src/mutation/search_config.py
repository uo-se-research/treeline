"""Search configuration parameters.  This is the
"high level" configuration, where we can include strategies
that must have visibility into search.py to pick components
(and which is therefore not imported into search.py),
as incorporates the lower level configuration which is
imported into search.py.
"""

# Low level stuff seen by search.py
from mutation.const_config import *


# Things that are seen only by the higher-level
# strategy driver.
import mutation.search

# Allow remote connection
# FUZZ_SERVER = "localhost"
FUZZ_SERVER = "localhost"
FUZZ_PORT = 2300

# Selection strategy class
# FRONTIER = mutation.search.SimpleFrontier
FRONTIER = mutation.search.WeightedFrontier



def init():
    """Later we might use a configuration file or
    otherwise allow these parameters to be tested and tuned.
    """
    pass


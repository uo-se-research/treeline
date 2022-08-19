"""Path hack:  Add parent directory to search path.  Do this just once, and
import "context" into each module so that they can refer to modules in this
directory as mutation.mod and to sibling modules as pygramm.mod
"""

import sys, os
this_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.abspath(this_folder))



"""
Configuration file for Pygramm.
"""

HUGE = 999_999   # Larger than any sentence we will generate
# LEN_BASED_SIZE means we measure and budget the size of a
# generated string based on its length *in bytes*.
LEN_BASED_SIZE = False  # use the len(text) in _Literal as the their size (True) or consider each _Literal=1 (False)?
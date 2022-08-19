# README: Grammar mutation for performance bugs

At this time we know of no grammar-based mutational fuzzers 
aimed at finding performance bugs.  There are good text mutation 
fuzzers for performance bugs (PerfFuzz) and good grammar-based
mutational fuzzers (Nautilus), but modifying either to combine their 
attributes is not straightforward.  

## Nautilus

We looked in particular at Nautilus, because in addition to being a 
very good fuzzer for its intended domain, it had enough in common 
with TreeLine to seem an apt basis for comparison between tree 
search (Monte Carlo or otherwise) and grammar-based mutation.

However, the implementation of Nautilus is in rust, and its 
integration with an AFL++ back end (vs AFL code base for PerfFuzz 
and TreeLine) is a shared memory area.  Thus it is very tightly 
coupled to the in-memory data structure of the coverage structure 
that AFL++ builds (which is probably compatible with AFL, but we 
aren't sure).  TreeLine uses additional memory structures, adopted 
from PerfFuzz.  In particular, while AFL (and AFL++, presumably) 
buckets edge counts in a way that treats 301 and 311 as the same count
(i.e., an execution that touches an edge 311 times is not 
necessarily "new coverage" if the edge has previously been touched 
301 times), PerfFuzz and TreeLine keep total counts for each edge so 
that touching an edge more times than it has been touched before 
(even if in the same bucket) can be treated as progress toward 
finding expensive runs or hot spots. 

We were not confident of correctly modifying Nautilus to use the 
additional information produced by our modified AFL back-end.  In 
addition, Nautilus has other optimizations and operations (including 
some textual mutation with "havoc"), and a rust application with a 
shared memory interface was not an "apples to apples" comparison 
with a Python application communicating over sockets.  This led us 
to borrow and reimplement key ideas from Nautilus in Python. 

## Our mutator

Following Nautilus, our mutator can "splice" a previously generated 
subtree at any non-terminal in the grammar. These previously 
generated subtrees are kept in the "chunk_store", following the 
chunkstore structure in Nautilus.  Like Nautilus, we record 
previously generated trees (actually just hashes of the strings they 
generate) so we don't waste time testing the same string over and over.

Key differences include 
- No bells and whistles.  No havoc.  There are only three ways to 
  get a new string: 
  - Splice a previously generated subtree into the current tree
  - Replace any subtree at a non-terminal with a randomly generated 
    subtree
  - Generate a new random tree from the root (really a special case 
    of the second approach)
- Length control:  This is critical for performance fuzzing, and not 
  for finding other kinds of bugs.  We never generate a string that 
  is longer than a fixed limit, which can be in characters or in 
  tokens.  But we also do not minimize inputs as Nautilus and AFL 
  do: We want strings that are pretty close to the limit. 




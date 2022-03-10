# The logic of phrase generation budgets

When we generate a sentence or phrase 
from a sequence of grammar symbols, 
we want to do so within a given budget. 
The budget could be in characters or in 
number of tokens; the only difference 
would be in how we count literals.  Here
we will consider a budget in number 
of tokens. 

## Minimum budgets 

We want to associate with each sequence 
of symbols a *minimum* number of tokens
it must generate.  We can define 
*minbud(s)* recursively:

* *minbud(L) == 1* if L is a literal
* *minbud(A|B) == min(minbud(A), minbud()B)*
* *minbud(S) == sum(minbud(E) for E in S)* if S
  is a sequence.  Note in particular that this 
  gives a budget of 0 for an empty sequence. 
* *minbud(A`*`) == 0* because A could be 
  repeated zero times.  Note this is equivalent to 
  treating A`*` as (AA`*`|/* empty */).
* If A is a non-terminal symbol, then 
  minbud(A) is min(minbud(P) for A -> P)
 
Because a grammar can be recursive, the last
rule could trigger an infinite recursive loop
if we coded it directly.  This can be 
avoided by iterating to a fixed point. 
We begin by assigning each non-terminal a 
very large initial estimate, then repeatedly 
evaluate the last rule without recursion. 
When the estimated minimum budgets for 
each non-terminal symbol do not change, 
the fixed point has been reached, 
and the estimate will be the 
actual minimum budget for each non-terminal. 

# Budgets while generating

We maintain a budget while generating
text from the grammar.  At each step in 
generation, we have a string of 
tokens that has been generated, which 
 we will call the prefix, and a
string of grammar symbols that remain
to be processed, which we will call
the suffix. We want to remain "in budget", 
meaning that the length of the prefix plus 
the minimum budget for the suffix is at 
most the the budget for the sentence. 

Initially we can calculate a *margin* as 
the difference between the total budget 
and the minimum budget for the start symbol.
We are within budget if the *margin* is 
non-negative.  
It is this *margin* that we will adjust 
as generation proceeds. 

Suppose we are expanding a symbol *A*, 
with a minimum budget of *b*, and we 
currently hold a *margin* of *m*.  We may
choose any expansion of *A* with a 
minimum budget at most *m + b*. If we 
choose an expansion with minimum budget *t*
such that *b < t <= m+b*, then we have a 
*remaining margin* of *m - (t - b)*. 

We can see this adjustment in `generator.py`: 

```python
     def expand(self, expansion: grammar.RHSItem):
        sym = self.suffix.pop()
        log.debug(f"{sym} -> {expansion}")
        self.suffix.append(expansion)
        # Budget adjustment. Did we use some of the margin?
        spent = expansion.min_tokens() - sym.min_tokens()
        self.margin -= spent
```

# pygramm : Grammar processing in Python

Experiments in processing BNF with Python. 
Work in progress. 

## Why? 

While Ply provides a semi-yaccalike, it has some 
characteristics that bother me.  First, it prioritizes
lexical processing by the length of the pattern, 
not the length of the token ... in violation of the 
"maximum munch" rule.  Second, it tries to do everything
at run time. 

Also I want to experiment with generation of 
sentences as well as parsing, and with LL as well 
as LR parsing. 

## Work in progress

### Done
* Parse BNF (`llparse.py`) and create an internal form. 
  The BNF form is extended with Kleene *, but a grammar
  in pure BNF without Kleene is also fine.  
* Internal structure (`grammar.py`) represents the BNF 
  structure directly.  The Grammar object contains a list
  of symbols, each of which has a single `expansion` 
  (which could be a sequence or a choice).  The following two
  grammars will produce precisely the same internal form:
  ```
  S ::= "a";
  S ::= "b";
  ```
  and 
  ```
  S ::= "a" | "b";
  ```
* A phrase generator (`generator.py`), together with some
  grammar analysis in `grammar.py`, can produce sentences
  within a given length limit (the _budget_) with or without
  direction.  See `choicebot.py` for an example of how
  grammar choices can be controlled. 
  
### To Do

* Distinguish lexical from CFG productions even for 
  sentence generation because we will want different tactics for 
  tokens than for RHS.  In CFG we budget for length of sentence. 
  In lexical productions we should choose between new and previously 
  used tokens.  Currently the BNF goes all the way to string
  constants, always.  The works for the kinds of grammars that 
  [Glade](https://github.com/kuhy/glade) learns, but it is
  not really ideal for generating useful program inputs. 
* Related to the prior point:  Infer a good boundary between
  CFG and lexical structure.  In conventional grammar processing, 
  a developer makes this distinction.  For grammar learners
  like Glade, though, the distinction is not trivial to recognize. 
* Add classic grammar analyses, starting with analyses for LL(1)
  grammars (first, follow), then checking for conflicts, and 
  likewise for LALR(1) and/or LR(1).
* Add simple transformations, such as left-factoring for LL(1).

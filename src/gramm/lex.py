"""
Lexical structure of BNF

I want BNF to look fairly standard, but I will
distinguish parts in BNF from lexical productions.

Initial cut might look like this:

# BNF part
Expr ::= Term { plus Expr };
Term ::= Factor { times Factor };
Factor ::= number | ident;

# Lexical part --- definitions are raw Python regexps
number = "[0-9]+" ;
ident = "[a-zA-Z][a-zA-Z0-9_]*" ;

Note on escaped characters:  I don't want to categorize here which
strings should undergo decoding and which should not, so that is
handled in the parser.

"""
import io
from typing import Sequence

# We use regular expressions (re) for the patterns that
# match lexemes
import re

# An Enum is a special kind of class used to enumerate
# a finite set of values.
from enum import Enum

import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


# To the extent possible, we would like to describe
# the lexical structure by some tables that are easily
# edited, rather than details of the procedural code.
# We will make a pattern for each distinct token. These
# are 'raw' strings to make it easier to 'escape' some
# characters that are special in regular expressions.
#
# Conventions:
#   UPPER = token
#   error = error  (name is exactly "error")
#   ignore = comment or whitespace (name is exactly "ignore")
#
#   Order matters:  e.g., INT must precede MINUS so that -5
#   is read as one negative integer, not MINUS followed by INT.
#   Keywords like IF must precede general patterns like VAR.
#   error should be the last pattern.
#
class TokenCat(Enum):
    # Note that these patterns MUST NOT include
    # capturing groups.  Use ?: to disable capturing
    ignore = r"\s+|#.*|/\*.*?\*/"   # Whitespace and comments
    IDENT = r"<?[a-zA-Z_][a-zA-Z_0-9]*>?"
    LBRACE = r"\{"  # Not currently used
    RBRACE = r"\}"
    # STRING = r'["](?:[^"]|(?:[\\]["]))*["]'
    STRING = r'["](?:[^\\"]|(?:[\\].))*["]'
    CHAR = r"'[^']+'"
    TERMINATOR = r';'
    # EBNF groups: disjunction, repetition
    DISJUNCT = r'\|'
    KLEENE = r'\*'
    LPAREN = r'\('
    RPAREN = r'\)'
    OPTIONAL = r'\?'     # EBNF shorthand: (x y)?  == ((x y)|/*empty*/)
    KLEENEPLUS = r"\+"   # EBNF shorthand x+ == xx*
    # Merges: [symbol, symbol, ...]
    # Also character classes [a-zA-Z]
    CHARCLASS = r"\[(?:\\\]|[^\]])*\]"
    LBRACK = r"\["
    RBRACK = r"\]"
    COMMA = ","
    # Relations
    BNFMERGE = r":::"
    BNFPROD = r"::=|:"  # Added yacc/antlr style productions
    # LEXPROD = r":="
    # Error processing
    error = "."           # catch-all for errors
    END = "---SHOULD NOT MATCH---"  # Not really a pattern


def all_token_re() -> str:
    """Create a regular expression that matches ALL of the tokens in TokenCat.
    Pattern will look like
     r"(?:\+)|(?:\*)|...|(?:[0-9]+)"
    i.e., each token pattern P will be enclosed in the non-capturing
    group (?:P) and all the groups will be combined as alternatives
    with | .
    """
    anything = "|".join([f"(?:{cat.value})" for cat in TokenCat])
    log.debug(f"Pattern '{anything}' should match anything")
    # log.debug(f"substring to 54 '{anything[:54]}'")
    # log.debug(f"substring 54.. '{anything[54:]}'")
    return anything


TOKENS_PAT = re.compile(all_token_re())


def debug_matches(s: str):
    """Debugging: What would match for each of the
    patterns in TokenCat?
    """
    print(f"**** Debug matches on {s} *****")
    for cat in TokenCat:
        pat = cat.value
        matches = re.match(pat, s)
        if matches:
            print(f"'{pat}' matches {matches.group(0)}")
        else:
            print(f"'{pat}' does not match")
    print("**** ****")


class LexicalError(Exception):
    """Raised when we can't extract tokens from the input"""
    pass


class Token(object):
    """One token from the input stream"""

    def __init__(self, value: any, kind: TokenCat):
        self.value = value
        self.kind = kind

    def __repr__(self) -> str:
        return f"Token('{self.value}', {self.kind})"

    def __str__(self) -> str:
        return repr(self)


END = Token("End of Input", TokenCat.END)


class TokenStream(object):
    """
    Provides the tokens within a stream one-by-one.
    Example usage:
       f = open("my_input_file")
       stream = TokenStream(f)
       while stream.has_more():
           token = stream.take()     # Removes token from front of stream
           lookahead = stream.peek() # Returns token without removing it
           # Do something with the token
    """

    def __init__(self, f: io.TextIOBase):
        self.file = f
        self.line_num = 0  # Public variable
        self.tokens = []
        self._check_fill()
        log.debug("Tokens: {}".format(self.tokens))

    def __str__(self) -> str:
        return "[{}]".format("|".join(self.tokens))

    def _check_fill(self):
        while len(self.tokens) == 0:
            # We could read more than one line before hitting
            # a token, but the loop will be broken if we
            # hit end of file
            line = self.file.readline()
            self.line_num += 1
            log.debug(f"Check fill reading line: '{line}'")
            if len(line) == 0:
                # End of file, leave zero tokens in buffer
                break
            try:
                self.tokens = self.lex(line.strip())
            except LexicalError as e:
                msg = f"Line {self.line_num}: {e}"
                raise LexicalError(msg)
            log.debug("Refilled, tokens: {}".format(self.tokens))
            # Note this might also leave zero tokens in buffer,
            # but in that case outer while loop will attempt
            # to refill it until we either get some tokens
            # or hit end of file

    def has_more(self) -> bool:
        """True if there are more tokens in the stream"""
        self._check_fill()
        return len(self.tokens) > 0

    def peek(self) -> Token:
        """Examine next token without consuming it. """
        self._check_fill()
        if len(self.tokens) > 0:
            token = self.tokens[0]
        else:
            token = END
        return token

    def take(self) -> Token:
        """Consume next token"""
        self._check_fill()
        if len(self.tokens) > 0:
            token = self.tokens.pop(0)
        else:
            token = END
        return token

    def pushback(self, token: Token):
        """Place a token back in the stream;
        used when we need extra lookahead.
        """
        self.tokens.insert(0, token)


    def lex(self, s: str) -> Sequence[Token]:
        """Break string into a list of Token objects.
        NOTE TOKENS_PAT must NOT include matching groups!
        """
        log.debug(f"Running big regular expression on '{s}'")
        words = TOKENS_PAT.findall(s)
        log.debug(f"Findall returned {words}")
        tokens = []
        for word in words:
            token = self.classify(word)
            if token.kind == TokenCat.ignore:
                log.debug(f"Skipping {token}")
                continue
            tokens.append(token)
        return tokens

    def classify(self, word: str) -> Token:
        """Convert a textual token into a Token object
        with a value and category.
        """
        log.debug(f"Classifying token '{word}")
        for kind in TokenCat:
            log.debug(f"Checking '{word}' for token class '{kind}'")
            pattern = kind.value
            if re.fullmatch(pattern, word):
                log.debug(f"Classified as {kind}")
                if kind.name == "error":
                    raise LexicalError(f"Unrecognized character '{word}'"
                                       f" in line {self.line_num}")
                return Token(word, kind)
        raise LexicalError(f"Unrecognized token '{word}'")


###
if __name__ == "__main__":
    # Simple smoke test
    sample = "<Alt_4520936952> ::= <Rep_4520937232>"
    debug_matches(sample)
    text = io.StringIO(sample)
    tokens = TokenStream(text)
    while tokens.has_more():
        print(f"Token: {tokens.take()}")
        input("Press enter to continue")

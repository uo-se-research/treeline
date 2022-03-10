# An XML grammar slightly adapted from
# https://github.com/antlr/grammars-v4/tree/master/xml
#
# Modifications:
#    - parser and lexer parts combined
#    - no negated regex; no .* for "everything",
#      so we will generate some sample random text
#    - lacking "modes" (like lex "states"), we
#      will add some recursive structure to the lexer
#

# ###############################
# Parser part, from XMLParser.g4
# ###############################

document    :   prolog? misc* element misc*;

prolog      :   XMLDeclOpen attribute* SPECIAL_CLOSE ;

content     :   chardata?
                ((element | reference | CDATA | PI | COMMENT) chardata?)* ;

element     :   '<' Name attribute* '>' content '<' '/' Name '>'
            |   '<' Name attribute* '/>'
            ;

reference   :   EntityRef | CharRef ;

attribute   :   Name '=' STRING ; # Our STRING is AttValue in spec

# ``All text that is not markup constitutes the character data of
#  the document.''
#
chardata    :   TEXT | SEA_WS ;

misc        :   COMMENT | PI | SEA_WS ;

# ##############################
# Lexer part, from XMLLexer.g4
# ##############################

# // Default "mode": Everything OUTSIDE of a tag
COMMENT     :   '<!--' TEXT* '-->' ;
CDATA       :   '<![CDATA[' TEXT* ']]>' ;
# /** Scarf all DTD stuff, Entity Declarations like <!ENTITY ...>,
# *  and Notation Declarations <!NOTATION ...>
# */
DTD         :   '<!' TEXT* '>'         ;#   -> skip ;
EntityRef   :   '&' Name ';' ;
CharRef     :   '&#' DIGIT+ ';'
            |   '&#x' HEXDIGIT+ ';'
            ;
SEA_WS      :   (' '|'\t'|'\r'? '\n')+ ;

# OPEN        :   '<'                     -> pushMode(INSIDE) ;
OPEN        :   '<'   ;
# XMLDeclOpen :   '<?xml' S               -> pushMode(INSIDE) ;
XMLDeclOpen :   '<?xml' S  ;

# SPECIAL_OPEN:   '<?' Name   ;#             -> more, pushMode(PROC_INSTR) ;

# TEXT        :   ~[<&]+ ;        // match any 16 bit char other than < and &
TEXT : 'a' | 'b' | 'c' | 'd' | 'e' ;

# // ----------------- Everything INSIDE of a tag ---------------------
# mode INSIDE;

CLOSE       :   '>'           ;#         -> popMode ;
SPECIAL_CLOSE:  '?>'          ;#         -> popMode ; // close <?xml...?>
SLASH_CLOSE :   '/>'          ;#          -> popMode ;
SLASH       :   '/' ;
EQUALS      :   '=' ;
#STRING      :   '"' ~[<"]* '"'
#          |   '\'' ~[<']* '\''
#            ;
# A much more restrictive set of strings
STRING : '"' ("a" | "b" | "c")* '"' ;

Name        :   NameStartChar NameChar* ;
#S           :   [ \t\r\n]               -> skip ;
S : " " | "\t" | "\r" | "\n" ;

HEXDIGIT    :   [a-fA-F0-9] ;

DIGIT       :   [0-9] ;

NameChar    :   NameStartChar
            |   '-' | '_' | '.' | DIGIT
            |   '\u00B7'
            |   [\u0300..\u036F]

            # |   '\u203F'..'\u2040'
            |   '\u203F' | '\u2040'
            ;

NameStartChar
            :   "a" | "b" | "c" | "d"
            |   '\u2070'| '\u218F'
            |   '\u2C00' | '\u2FEF'
            |   '\u3001' | '\uD7FF'
            |   '\uF900' | '\uFDCF'
            |   '\uFDF0' | '\uFFFD'
            ;

# // ----------------- Handle <? ... ?> ---------------------

PI          :   '?>'       ;#             -> popMode ; // close <?...?>
IGNORE      :   'i' |          ;#            -> more ;


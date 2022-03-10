""""Biased_choice specifically for grammars;
Mainly adds a nicer diagnostic table dump.
"""

from gramm.biased_choice import Bias
from gramm.grammar import Grammar, _Choice

def dump_bias(bias: Bias, gram: Grammar) -> str:
    """Bias table annotation of grammar"""
    # Convert {(context, symbol) -> weight}
    # to { symbol -> [(context, weight), (context, weight) ...]}
    lines = []
    choices_in_context = {}
    for ((context, choice), weight) in bias.core.bigram_weights.items():
        # print(f"{context}/{choice}:{weight}")
        if choice not in choices_in_context:
            choices_in_context[choice] = []
        choices_in_context[choice].append((context, weight))
    # Now produce a table with choices for each grammar production
    # with a top-level choice.  (Note it may be desirable to normalize
    # grammars that have choices nested within other RHS elements.)
    for (sym_name, symbol) in gram.symbols.items():
        lines.append("")
        expansions = symbol.expansions
        if not isinstance(expansions, _Choice):
            lines.append(f"{sym_name} ::= {symbol.expansions}")
            continue
        # Choice of productions.  Show weight of each.
        for choice in expansions.items:
            lines.append(f"{sym_name} ::= {choice}")
            if choice not in bias.core.weights:
                lines.append(f" (never selected)")
                continue
            weight_alone = bias.core.weights[choice]
            lines.append(f" -- Without context: {weight_alone:.3f}")
            if choice not in choices_in_context:
                continue
            for (context, weight) in choices_in_context[choice]:
                lines.append(f" -- {weight:.3f} after {context}")
    return "\n".join(lines)






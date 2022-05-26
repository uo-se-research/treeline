__author__ = "Ziyad Alsaeed"
__email__ = "zalsaeed@cs.uoregon.edu"
__status__ = "Testing"

import math
import random
from typing import Tuple

import mcts.mcts_globals as mg  # MCTS globals
from gramm.llparse import *
from gramm.grammar import _Symbol, _Choice, _Seq, _Literal
from gramm.biased_choice import Bias
from targetAppConnect import InputHandler

input_handler = InputHandler()
if not input_handler.is_connected():
    logging.warning(f"No connection to input handler")


class MCTSNode:

    def __init__(self, budget, text: str, stack: List[RHSItem], tokens, parent: "MCTSNode" = None,
                 use_locking: bool = False, bias: Bias = None):
        """
        The object of the search tree. The initialization of each new node will fall into three possible cases.
        1. An empty stack: in which it would lead to a terminal node. In such case we don't want to pop from an empty
            stack, and we need to ensure that the symbol=None, so we can determine this node as terminal (in MCTS def.).
        2. Non-terminal at top of stack: this is the simplest case where we just pop that element and use it as the
            symbol. Any Non-terminal must have some options (even if a single option) only in such cases we want to
            create MCTSNodes.
        3. Terminal node at top of stack: This is possible when the parent of this node had a choice that contains a
            sequence of terminals, or a mix of both terminals and non-terminal (e.g. <A> ::= 'a' <B> 'c' | 'a' 'b' 'c').
            When we encounter a terminal at the top of the stack, we want to make sure we adjust the values of used
            tokens and the generated text properly. Then throw the terminal element. Terminals (_Literal) are
            choice-less elements, we do not want to create MCTSNode for them as it is a waste of resources (both in
            terms of space and time).

        @param budget: The budget allowed based on the defined input length (e.g., num of char, tokens or bytes).
        @param text: The literals generated to the so far (i.e., to the left of the current “cursor”).
        @param stack: Tokens need to be resolved as given by the choice from the parent node.
        @param tokens: The number of tokens used as of parent node.
        @param parent: This node's parent.
        @param use_locking: If True: any node that is exhausted will be locked from future visits
            (i.e., as if it doesn't exist anymore).
        @parma bias: A reference to the bias object regardless if we use bias or not.
        """
        self.log = logging.getLogger(self.__class__.__name__)

        self._v = 0.0  # total costs
        self._n = 0  # num of visits
        self.locked = False

        self._hnb = 0  # has new bits (coverage)? 0: no, 1: there was a change to some pocket, 2: newly touched pocket
        self._hnm = False  # has new max? was there any increase to some pocket (no matter how large it is)?
        self._hs = 0  # what was the max known hit to some edge from this node?

        self._children: List[MCTSNode] = []

        self.budget = budget  # the allowed budget from this given node
        self.tokens_used = tokens  # track used tokens to validate budget use per node (token is not # of chars)
        self.use_locking = use_locking

        # Initializing the node based on the three cases described above.
        if stack:
            symbol = stack.pop()
            while isinstance(symbol, _Literal) or isinstance(symbol, _Seq):
                if isinstance(symbol, _Literal):
                    self.tokens_used += symbol.min_tokens()
                    text += symbol.text
                    if stack:
                        symbol = stack.pop()
                    else:
                        symbol = None
                elif isinstance(symbol, _Seq):
                    for el in reversed(symbol.items):
                        stack.append(el)
                    symbol = stack.pop()

            self.symbol = symbol  # LIFO order (stack)!
        else:
            self.symbol = None
        self.stack = stack

        if parent is None:  # special case of root node
            self.parent = None
            self.level = 0
            self.text = ""
            self.budget = self.budget - self.symbol.min_tokens()
            if bias is None:
                self.bias = Bias()
            else:
                self.bias = bias
        else:
            self.parent = parent
            self.level = parent.level + 1
            self.text = text
            self.bias = self.parent.bias.fork()

        self.allowed_budget = 0
        if self.symbol is None:  # this is a terminal
            self.allowed_budget = self.budget
        else:
            self.allowed_budget = self.budget + self.symbol.min_tokens()  # either parent or any other node

    def update(self, new_cost):
        """
        Update this node given an observed cost based on it or based on a descendant from it.
        @param new_cost: the cost observed.
        """
        self._v += new_cost
        self._n += 1

        # also check if we should lock it based on its children
        if self.use_locking:
            if self._children:
                should_lock_it = True
                for child in self._children:
                    if not child.locked:
                        should_lock_it = False
                self.locked = should_lock_it

    def populate_children(self):
        """
        Create all valid children from this node and add them to its list of children.
        """
        assert not self.is_terminal()
        gram_children = self._get_gram_valid_children()  # get all options (empty=None, otherwise list of choices)

        for child in gram_children:
            self._children.append(self._populate_child_node(child))

    def _get_gram_valid_children(self) -> List[RHSItem]:
        """
        Provides a list of Valid choices from this node given the allows budget.

        @return: List[RHSItem] of valid children (e.g. [_Symbol('<word>'), _Symbol('<char>')]).
        """
        if isinstance(self.symbol, _Symbol):
            if isinstance(self.symbol.choices(self.allowed_budget)[0], _Choice):
                """
                There are multiple options we don't consider "_Choice" as a state in our tree node, thus we skip it.
                In pygramm, a _Choice is simply the expansions possible. If more then one expansion are possible from a
                _Symbol, then they will be wrapped in a type _Choice. Otherwise, it will be a the choice itself.
                """
                list_of_one_elem_choice = self.symbol.choices(self.allowed_budget)
                return list_of_one_elem_choice[0].choices(self.allowed_budget)
            else:
                # only one possible options
                return self.symbol.choices(self.allowed_budget)
        else:
            return self.symbol.choices(self.allowed_budget)

    def _populate_child_node(self, child: RHSItem) -> "MCTSNode":
        """
        Given a valid grammar node option (child) create the MCTSNode appropriately then return it.

        Note that this method does NOT add a child to this current node. It only populates a child that can be added
        to its children (in a case where we expand it) or just creating one for random expansion (in a case
        of a rollout).

        @param child: A child is a valid grammar option (action) from this node.
        @return: A new MCTSNode with the appropriate options (budget, token, text, etc) adjusted.
        """

        if isinstance(child, _Literal):
            new_stack = self.stack.copy()  # no change on stack
            spent = child.min_tokens() - self.symbol.min_tokens()
            new_budget = self.budget - spent
            # new_budget = self.budget  # no change on budget
            new_text = self.text + child.text  # update the text
            new_tokens_used = self.tokens_used + child.min_tokens()  # update used tokens
        elif isinstance(child, _Symbol) and child.name == "EMPTY":
            new_stack = self.stack.copy()  # no change on stack
            new_budget = self.budget  # no change on budget
            new_text = self.text  # no change on text
            new_tokens_used = self.tokens_used  # no change on used tokens
        elif isinstance(child, _Seq):
            new_stack = self.stack.copy()  # update stack
            for el in reversed(child.items):
                new_stack.append(el)
            spent = child.min_tokens() - self.symbol.min_tokens()
            new_budget = self.budget - spent
            # new_budget = self.budget - child.min_tokens()  # update budget
            new_text = self.text  # no change on text
            new_tokens_used = self.tokens_used  # no change on used tokens
        else:  # this must be some non-terminal symbol
            new_stack = self.stack.copy()  # update stack
            new_stack.append(child)
            spent = child.min_tokens() - self.symbol.min_tokens()
            new_budget = self.budget - spent
            # new_budget = s_i.budget - choice.min_tokens()  # update budget
            new_text = self.text  # no change on text
            new_tokens_used = self.tokens_used  # no change on used tokens

        return MCTSNode(budget=new_budget, text=new_text, stack=new_stack, tokens=new_tokens_used, parent=self,
                        use_locking=self.use_locking)

    def select_random_child(self, using_bias=False) -> "MCTSNode":
        """
        From the valid children of this node, select one randomly and return it as an MCTSNode.

        @return: a random valid child as MCTSNode
        """
        choices = self._get_gram_valid_children()  # get all options
        if using_bias:
            choice = self.bias.choose(choices)  # bias-based selection
        else:
            choice = random.choice(choices)  # randomly select one

        # self.log.debug("Choices:")
        # for idx, c, in enumerate(choices):
        #     self.log.debug(f"\t{idx + 1}: {c}")
        # self.log.debug(f"Chosen: {choice}")

        return self._populate_child_node(choice)

    def get_ucb1(self) -> float:
        """
        Upper Confidence Bounds or UCB1 for this node. If root the value will be 0. If a node is locked then the UCB
        value will be negative infinity so that it doesn't get selected ever.

        @return: float value of representing the UCB of this node.
        """
        if self.parent is None:  # i.e., if this is the root
            return 0.0
        else:
            if self._n == 0:
                return float("inf")  # maximize unseen children
            if self.locked:
                return float("-inf")  # minimize fully explored children

            """
            Note on UCB1 formula.
            There are some variations of the UCB1 formula based on resources. I'm not sure yet which is the best. 
            However, there is a clear difference between each one. For example, the first formula favors initially 
            observed expensive paths and doesn't do much exploration. We need to do more research to know which
            formula is better for our case. For now the formula below does just fine.
            """

            # as found in https://en.wikipedia.org/wiki/Monte_Carlo_tree_search
            return self._v / self._n + mg.C * math.sqrt(math.log(self.parent._n) / self._n)

    def run(self, warmup: bool = False) -> Tuple[str, int, int, bool, int, bool]:
        """
        A method to run the app given the input from this node. This must only be called on terminal nodes. It returns
        all the possible information it can collect from a run. It is up to the method that call this one to decide on
        what information to pass to the requester of a run.

        @param warmup: what should be the run type. A warmup run, which is the less often one should always send the
        signal 'wup' to avoid missing the max_count on AFL side. Any three characters '***' would lead to a run that
        update max_count (if there was one) on AFL side.
        @return: A tuple of (input:str, total-execution-cost:int, hnb:int, hnm:bool, hs:int, anomalous_run:bool).
        hnb (coverage) is either 0 (no change), 1 (an edge has new change in hit count), or 2 (an edge got hit for the
        first time). hnm is True iff there was an increase on the hit for some edge given the past observations. And
        hs is the number of edge hit for the edge that got hit the most.
        """
        run_type = 'nml'
        if warmup:
            run_type = 'wup'
        if self.is_terminal():
            if input_handler.is_connected():
                """
                Based on our experience, AFL could sometimes return a zero cost run. Such run is considered a glitch
                for us. Therefore, as long as the cost is abnormal, we will keep running the app given the input here.  
                """
                anomalous_run = False
                actual_cost, hnb, hnm, hs = input_handler.run_input(self.text, run_type=run_type)

                if actual_cost < mg.TARGET_APP_MIN_POSSIBLE_COST:
                    anomalous_run = True
                    self.log.warning(f"Run with warmup={warmup}, execution-cost={actual_cost}, input={self.text} "
                                     f"is abnormal!")

                return self.text, actual_cost, hnb, hnm, hs, anomalous_run
            else:
                raise RuntimeError("No connection to Target App Runner!")
        else:
            raise RuntimeError(f"Called on a non-terminal node {self}!")

    def dummy_run(self) -> Tuple[str, int, int, bool, int, bool]:
        """
        A none official app runner that can only be used on the root node. This dummy runner is only useful in
        establishing some basics about the application possible call graph cost.
        @return: Same tuple of the official runs (see the "run" method for detailed information).
        """
        run_type = 'wup'
        if self.parent is not None:
            raise RuntimeError("This is only accessible from the root node")
        else:
            anomalous_run = False
            actual_cost, hnb, hnm, hs = input_handler.run_input(self.text, run_type=run_type)

            if actual_cost < mg.TARGET_APP_MIN_POSSIBLE_COST:
                anomalous_run = True
                self.log.warning(f"Run with warmup={run_type}, execution-cost={actual_cost}, input={self.text} "
                                 f"is abnormal!")

            return self.text, actual_cost, hnb, hnm, hs, anomalous_run

    def get_visits(self) -> int:
        """
        The number of visits to this node so far.
        @return: The number of visits.
        """
        return self._n

    def get_total_cost(self) -> float:
        """
        The accumulative cost seen so for from this node.
        @return: duh
        """
        return self._v

    def get_allowed_budget(self) -> int:
        """
        The allowed budget from this node given the context to that lead to this current state.
        @return:
        """
        return self.allowed_budget

    def __str__(self):
        """
        A node print consists of six pieces of information.
            1. <input>: The input generated thus far. The right-most char being the latest char added.
            2. <symbol>: The grammar symbol under evaluation now.
            3. <allowed-budget>: The allowed budget at this node.
            4. <budget>: The budget passed to this node from its parent.
            5. <stack>: The derivation stack at this point. The left-most element is the top of the stack.
            6. <node-mcts-info>: The cost, visits, and UCB1 information.

        This information is arranged as the following:
        '<input>'-(<symbol> | <allowed-budget>/<budget>)-<stack> [<node-mcts-info>]
        """
        # left most element is the one to be evaluated next (preserve consistency with derivations intuition)
        reversed_stack = self.stack[::-1]

        return f"'{self.text.encode('utf-8')}'-({self.symbol} | {self.allowed_budget}/" \
               f"{self.budget})-{reversed_stack} [V: {self._v}, N: {self._n}, UCB1: {self.get_ucb1()}]"

    def get_signature(self) -> str:
        """
        Create a signature of this node given the text generated so far, its symbol, and what symbols are still in
        the stack.
        @return: The node signature as string "<text>-<symbol>-[<stack>]"
        """
        reversed_stack = self.stack[::-1]
        simplified_stack = ""
        for node in reversed_stack:
            simplified_stack += str(node)
        return f"{self.text.encode('utf_8')}-{self.symbol}-[{simplified_stack}]"

    def get_children(self) -> List["MCTSNode"]:
        """
        Get all the populated children.
        @return: A list of the populated children.
        """
        return self._children

    def get_num_of_children(self) -> int:
        """
        The number of populated children. These must always be either 0 (not populated yet) or equal to all the valid
        children as we populate children at once.
        @return: duh
        """
        return len(self._children)

    def is_new(self) -> bool:
        """
        A node is new if it was visited less than then the expansion threshold (E).
        @return: bool of whether it is new or not.
        """
        return self._n < mg.E

    def is_terminal(self) -> bool:
        """
        Unlike terminal gram symbols, a terminal MCTSNode is also the last terminal symbol in the stack. Otherwise, it
        is only a terminal symbol that has one possible action.
        @return: True (if stack is empty and symbol is None), and False otherwise.
        """
        return not self.stack and self.symbol is None

    def is_leaf(self) -> bool:
        """
        A leaf is a node that has no children yet. A leaf node is not necessarily a terminal node!

        @return: True if it has no children, False otherwise.
        """
        return not self._children

    def is_coverage_increased(self) -> bool:
        """
        If the input from this new or any of its descendants demonstrate a run that the edge has-new-bits or has-new-max
        then return True.
        @return: Return true if this node uncovered new bits or new max.
        """
        return self._hnb or self._hnm

    def get_hnb(self) -> int:
        """
        Get the value of has-new-bits (hnb or coverage).
        @return: Coverage is either 0 (no change), 1 (an edge has new change in hit count), or 2 (an edge got hit for
        the first time).
        """
        return self._hnb

    def set_hnb(self, hnb: int):
        """
        Set the value of has-new-bits (hnb or coverage)
        @param hnb: Coverage is either 0 (no change), 1 (an edge has new change in hit count), or 2 (an edge got hit
        for the first time).
        """
        self._hnb = hnb

    def get_hnm(self) -> bool:
        """
        Get the value of has-new-max (hnm).
        @return: hnm is True iff there was an increase on the hit for some edge given the past observations.
        """
        return self._hnm

    def set_hnm(self, hnm: bool):
        """
        Get the value of has-new-max (hnm).
        @param hnm: has-new-max is True iff there was an increase on the hit for some edge given the past observations.
        """
        self._hnm = hnm

    def get_hotspot(self) -> int:
        """
        Get the value of hotspot (hs).
        @return: hs is the number of edge hit for the edge that got hit the most.
        """
        return self._hs

    def set_hotspot(self, hs: int):
        """
        Set the value of hotspot (hs).
        @param hs: hotspot is the number of edge hit for the edge that got hit the most.
        """
        self._hs = hs

    def has_a_parent(self):
        """
        Whether this is a root node or not.

        @return: True if root, false otherwise.
        """
        return self.parent is not None

    def start_connection(self):
        input_handler.open_connection()

    def close_connection(self):
        input_handler.close_connection()

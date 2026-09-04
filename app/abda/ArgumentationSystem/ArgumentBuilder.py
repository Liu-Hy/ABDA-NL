from itertools import product

from ArgumentationSystem.Argument import Argument
from KnowledgeBase.DefeasibleRule import DefeasibleRule
from ArgumentationSystem.Attack import Attack
from Configuration import Configuration


# Deterministic work limits for the public demo. Request-rate limits do not
# protect a worker from one structurally valid scenario whose derivations grow
# combinatorially. These ceilings leave ample room above every bundled example
# while keeping argument construction, attack discovery, serialization, and UI
# rendering bounded.
MAX_BUILD_ITERATIONS = 100
MAX_ARGUMENTS = 250
MAX_PREMISE_MATCH_INSPECTIONS = 250_000
MAX_CANDIDATE_COMBINATIONS = 2_500
MAX_ARGUMENT_REPRESENTATION_CHARS = 20_000
MAX_ATTACK_INSPECTIONS = 500_000
MAX_ATTACKS = 10_000


class ArgumentConstructionError(Exception):
    """Raised when argument construction cannot produce a usable framework."""


class ArgumentComplexityError(ArgumentConstructionError):
    """Raised when a scenario exceeds a deterministic public-service limit."""


class _ArgumentBuildBudget:
    def __init__(self):
        self.premise_match_inspections = 0
        self.candidate_combinations = 0

    def inspect_premise_match(self):
        self.premise_match_inspections += 1
        if self.premise_match_inspections > MAX_PREMISE_MATCH_INSPECTIONS:
            raise ArgumentComplexityError(
                "scenario exceeds the safe premise-matching limit of "
                f"{MAX_PREMISE_MATCH_INSPECTIONS} checks; simplify the rule set"
            )

    def reserve_candidates(self, count):
        self.candidate_combinations += count
        if self.candidate_combinations > MAX_CANDIDATE_COMBINATIONS:
            raise ArgumentComplexityError(
                "scenario exceeds the safe candidate-combination limit of "
                f"{MAX_CANDIDATE_COMBINATIONS}; reduce alternative derivations"
            )


class _AttackBuildBudget:
    def __init__(self):
        self.inspections = 0

    def inspect_subargument(self):
        self.inspections += 1
        if self.inspections > MAX_ATTACK_INSPECTIONS:
            raise ArgumentComplexityError(
                "scenario exceeds the safe attack-analysis limit of "
                f"{MAX_ATTACK_INSPECTIONS} subargument checks; simplify the "
                "argument graph"
            )


def _would_create_cycle(rule, combo):
    """True iff ``rule`` already appears as the top rule of some argument in
    any sub-argument's transitive Sub set.

    Implements the well-formedness constraint from Caminada et al. (2015),
    Definition 7, footnote 6: a rule may reappear across different branches
    of a derivation but never twice on the same root-to-leaf path. Applying
    ``rule`` on top of ``combo`` would place ``rule`` at the new root; if
    any sub-argument in ``combo`` has ``rule`` somewhere in its subtree,
    the resulting argument would violate the constraint -- and admitting
    it would also let the fixpoint diverge on self-referential chains.
    """
    for sub_arg in combo:
        for s in sub_arg.Sub:
            if s.TopRule is rule:
                return True
    return False


def _projected_flattened_length(rule, build_from_arguments):
    """Compute Argument.Flattened length without allocating the string."""
    output_length = 2 + len(str(rule.RightSide))
    rule_id = getattr(rule, "_scenario_id", None) or getattr(rule, "Name", None) or ""
    if rule_id:
        output_length += len(str(rule_id)) + 2

    arguments_by_conclusion = {}
    for argument in build_from_arguments:
        arguments_by_conclusion.setdefault(argument.Conclusion, argument)

    wrapped_subargument_lengths = []
    for condition in rule.LeftSide:
        matching = arguments_by_conclusion[condition]
        wrapped_subargument_lengths.append(len(matching.Flattened) + 2)

    if len(wrapped_subargument_lengths) == 1:
        return output_length + wrapped_subargument_lengths[0]
    return (
        output_length
        + sum(wrapped_subargument_lengths)
        + len(wrapped_subargument_lengths) - 1
        + 2
    )


def get_applicable_argument_tuples(rule, arguments, budget=None):
    """Yield every valid tuple of sub-arguments that satisfies ``rule``'s
    premises.

    For each condition in ``rule.LeftSide`` (in order), collect every
    candidate sub-argument whose conclusion matches, then yield the
    Cartesian product filtered by the well-formedness constraint from
    Caminada et al. (2015), Definition 7 footnote 6 (no rule repeats on
    a single root-to-leaf path). Returns ``None`` when any premise has no
    candidate (the rule cannot fire at all).

    Replaces an earlier greedy selection that picked the first matching
    sub-argument per premise from an unordered set and under-enumerated
    arguments for rules with uneven premise-candidate counts -- introducing
    Python-hash-seed nondeterminism in the resulting AF.
    """
    candidate_lists = []
    for condition in rule.LeftSide:
        candidates = []
        for argument in arguments:
            if budget is not None:
                budget.inspect_premise_match()
            if argument.Conclusion == condition:
                candidates.append(argument)
        if not candidates:
            return None
        candidate_lists.append(candidates)
    if budget is not None:
        candidate_count = 1
        for candidates in candidate_lists:
            candidate_count *= len(candidates)
        budget.reserve_candidates(candidate_count)

    def valid_tuples():
        for combo in product(*candidate_lists):
            if not _would_create_cycle(rule, combo):
                yield combo

    return valid_tuples()


def build_arguments(rules):
    arguments = set()
    budget = _ArgumentBuildBudget()
    # Bodyless rules -> ground arguments (facts / assumptions).
    for rule in set(filter(lambda r: not r.LeftSide, rules)):
        argument = Argument(rule)
        if argument not in arguments and len(arguments) >= MAX_ARGUMENTS:
            raise ArgumentComplexityError(
                f"scenario exceeds the safe limit of {MAX_ARGUMENTS} arguments; "
                "reduce rules or alternative derivations"
            )
        arguments.add(argument)

    # Fixpoint: re-enumerate every rule until no new arguments appear.
    old_size = -1
    iterations = 0
    while old_size != len(arguments):
        iterations += 1
        if iterations > MAX_BUILD_ITERATIONS:
            raise ArgumentConstructionError(
                f"argument construction did not converge after "
                f"{MAX_BUILD_ITERATIONS} iterations ({len(arguments)} arguments "
                "built so far); likely a self-referential rule chain"
            )
        old_size = len(arguments)
        for rule in rules:
            if not rule.LeftSide:
                continue
            tuples = get_applicable_argument_tuples(rule, arguments, budget)
            if tuples is None:
                continue
            for combo in tuples:
                build_from_arguments = set(combo)
                flattened_length = _projected_flattened_length(
                    rule, build_from_arguments
                )
                if flattened_length > MAX_ARGUMENT_REPRESENTATION_CHARS:
                    raise ArgumentComplexityError(
                        "scenario exceeds the safe argument-derivation size of "
                        f"{MAX_ARGUMENT_REPRESENTATION_CHARS} characters; simplify "
                        "deep or highly branching rules"
                    )
                argument = Argument(rule, build_from_arguments)
                if argument not in arguments and len(arguments) >= MAX_ARGUMENTS:
                    raise ArgumentComplexityError(
                        f"scenario exceeds the safe limit of {MAX_ARGUMENTS} "
                        "arguments; reduce rules or alternative derivations"
                    )
                arguments.add(argument)
    return arguments


def build_attacks(arguments):
    arguments = tuple(arguments)
    if len(arguments) > MAX_ARGUMENTS:
        raise ArgumentComplexityError(
            f"scenario exceeds the safe limit of {MAX_ARGUMENTS} arguments; "
            "reduce rules or alternative derivations"
        )
    attacks = set()
    budget = _AttackBuildBudget()
    for a in arguments:
        for b in arguments:
            if does_attacks(a, b, budget):
                if len(attacks) >= MAX_ATTACKS:
                    raise ArgumentComplexityError(
                        f"scenario exceeds the safe limit of {MAX_ATTACKS} attacks; "
                        "simplify the argument graph"
                    )
                attacks.add(Attack(a, b))
    return attacks


def does_attacks(a, b, budget=None):
    # Undercutting?
    for b1 in b.Sub:
        if budget is not None:
            budget.inspect_subargument()
        if isinstance(b1.TopRule, DefeasibleRule) and is_negation(b1.TopRule.Name, a.Conclusion):
            if Configuration.Verbose:
                print(str(a) + " undercuts " + str(b) + " on " + str(b1.TopRule.Name))
            return True
    # Rebutting?
    for b1 in b.Sub:
        if budget is not None:
            budget.inspect_subargument()
        if  is_negation(a.Conclusion, b1.Conclusion) and not a < b1:
            if Configuration.Verbose:
                print(str(a) + " rebuts " + str(b) + " on " + str(b1))
            return True
    return False


def is_negation(a, b):
    return a == "-" + b or b == "-" + a

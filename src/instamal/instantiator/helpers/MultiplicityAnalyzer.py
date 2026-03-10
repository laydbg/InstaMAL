from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from antlr4 import Token
from maltoolbox.language import LanguageGraph
from maltoolbox.language.language_graph_assoc import LanguageGraphAssociation

from instamal.instantiator.helpers import SpecVisitor, SpecParser
from instamal.instantiator.helpers.distributions import (
    distribution_bounds_functions,
    distribution_expected_functions,
)

INF = math.inf


# ── Data structures ──────────────────────────────────────────────────────────


@dataclass
class CardinalityBound:
    """Min/max number of assets in a set."""

    min: int
    max: float  # float to accommodate INF

    def __post_init__(self):
        if self.min is None:
            self.min = 0
        if self.max is None:
            self.max = INF


@dataclass
class FieldAccumulator:
    """
    Accumulated connection bounds for one (asset_type, fieldname) pair,
    across all connection rules that write to that field.

    min_connections: sum of guaranteed minimums from rules with weight==1.0.
                     Rules with weight < 1.0 conservatively contribute 0.
    max_connections: sum of possible maximums across all rules.
    source_tokens:   representative tokens from the spec for error reporting.
    """

    min_connections: float = 0
    max_connections: float = 0
    source_tokens: List[Token] = field(default_factory=list)


@dataclass
class MultiplicityViolation:
    line: int
    column: int
    description: str


@dataclass
class RuleContribution:
    """The contribution of a single connection rule to a field's degree
    distribution, expressed as a Binomial(n, p) approximation."""

    n: float  # E[right_set_size] (or left_set_size for reverse)
    p: float  # RGG connection probability for this rule's weight


@dataclass
class FieldEstimate:
    """Accumulated probabilistic estimates for one (asset_type, fieldname)
    pair across all contributing connection rules."""

    rule_contributions: List[RuleContribution] = field(default_factory=list)
    source_tokens: List[Token] = field(default_factory=list)


@dataclass
class MultiplicityWarning:
    line: int
    column: int
    asset_type: str
    fieldname: str
    mult_min: int
    mult_max: float
    per_asset_probability: float
    n_assets_expected: float
    global_probability: float
    threshold: float

    def __str__(self) -> str:
        mult_max_str = "∞" if self.mult_max == INF else str(int(self.mult_max))
        return (
            f"  line {self.line}, col {self.column}: "
            f"Association field '{self.fieldname}' on '{self.asset_type}' "
            f"(multiplicity {self.mult_min}..{mult_max_str}): "
            f"P(single asset satisfied) ≈ {self.per_asset_probability:.2%}, "
            f"with ~{self.n_assets_expected:.1f} assets "
            f"P(all satisfied) ≈ {self.global_probability:.2%} "
            f"(threshold: {self.threshold:.0%})"
        )


# ── Analyzers ─────────────────────────────────────────────────────────────────


class StaticMultiplicityAnalyzer(SpecVisitor):
    """
    Performs a static multiplicity check over a parsed Spec for any guaranteed
    violations.
    """

    def __init__(self, lang_graph: LanguageGraph) -> None:
        self._lang_graph: LanguageGraph = lang_graph

        # Key: (left_asset_type, right_fieldname, right_asset_type)
        self._assoc_map: Dict[Tuple[str, str, str], LanguageGraphAssociation] = {}
        for assoc in lang_graph.associations:
            lname = assoc.left_field.asset.name
            rname = assoc.right_field.asset.name
            self._assoc_map[(lname, assoc.right_field.fieldname, rname)] = assoc
            self._assoc_map[(rname, assoc.left_field.fieldname, lname)] = assoc

        self._field_assoc_map: Dict[Tuple[str, str], LanguageGraphAssociation] = {}
        for (at, fn, _), assoc in self._assoc_map.items():
            self._field_assoc_map[(at, fn)] = assoc

        self._cardinality_bounds: Dict[str, CardinalityBound] = {}
        self._types: Dict[str, str] = {}
        self._subsystems: Dict[str, SpecParser.SubsystemContext] = {}

        # Stack of (prefix, local_bounds, local_types) for nested subsystems
        self._subsystem_stack: List[
            Tuple[str, Dict[str, CardinalityBound], Dict[str, str]]
        ] = []

        # (asset_type, fieldname) -> FieldAccumulator
        self._field_accumulators: Dict[Tuple[str, str], FieldAccumulator] = {}

        self._violations: List[MultiplicityViolation] = []

    # ── Public entry point ────────────────────────────────────────────────

    def analyze(self, spec_ctx: SpecParser.SpecContext) -> List[MultiplicityViolation]:
        """Run the static multiplicity analysis and return all violations."""
        self._cardinality_bounds = {}
        self._types = {}
        self._subsystems = {}
        self._subsystem_stack = []
        self._field_accumulators = {}
        self._violations = []

        self.visit(spec_ctx)
        self._check_accumulators()
        return self._violations

    # ── Helpers ───────────────────────────────────────────────────────────

    def _current_prefix(self) -> str:
        return self._subsystem_stack[-1][0] if self._subsystem_stack else ""

    def _current_bounds(self) -> Dict[str, CardinalityBound]:
        return (
            self._subsystem_stack[-1][1]
            if self._subsystem_stack
            else self._cardinality_bounds
        )

    def _current_types(self) -> Dict[str, str]:
        return self._subsystem_stack[-1][2] if self._subsystem_stack else self._types

    def _scoped(self, raw_id: str) -> str:
        prefix = self._current_prefix()
        return f"{prefix}.{raw_id}" if prefix else raw_id

    def _resolve_variable(
        self, var_id: str
    ) -> Tuple[Optional[CardinalityBound], Optional[str]]:
        """Resolve a (possibly prefixed) variable to its bounds and type."""
        bounds = self._current_bounds()
        types = self._current_types()
        return bounds.get(var_id), types.get(var_id)

    def _accumulate(
        self,
        asset_type: str,
        fieldname: str,
        min_conn: float,
        max_conn: float,
        token: Token,
    ) -> None:
        key = (asset_type, fieldname)
        if key not in self._field_accumulators:
            self._field_accumulators[key] = FieldAccumulator()
        acc = self._field_accumulators[key]
        acc.min_connections += min_conn
        acc.max_connections += max_conn
        acc.source_tokens.append(token)

    # ── Expression bound evaluator ────────────────────────────────────────

    def _expr_bounds(self, ctx: SpecParser.ExprContext) -> Tuple[float, float]:
        """Return (min, max) for an expression without sampling."""
        leading_sign = ctx.sign() is not None
        lo, hi = self._term_bounds(ctx.term(0))
        if leading_sign:
            sign = -1 if ctx.sign().MINUS() is not None else 1
            lo, hi = lo * sign, hi * sign
            if sign < 0:
                lo, hi = hi, lo

        for i in range(1, len(ctx.term())):
            op = ctx.getChild(2 * i - (not leading_sign)).getText()
            tlo, thi = self._term_bounds(ctx.term(i))
            if op == "+":
                lo += tlo
                hi += thi
            elif op == "-":
                lo -= thi
                hi -= tlo

        return lo, hi

    def _term_bounds(self, ctx: SpecParser.TermContext) -> Tuple[float, float]:
        lo, hi = self._fact_bounds(ctx.fact(0))
        for i in range(1, len(ctx.fact())):
            op = ctx.getChild(2 * i - 1).getText()
            flo, fhi = self._fact_bounds(ctx.fact(i))
            if op == "*":
                products = [lo * flo, lo * fhi, hi * flo, hi * fhi]
                lo, hi = min(products), max(products)
            elif op == "/":
                # Avoid division by zero conservatively
                if flo == 0:
                    flo = 1e-9
                if fhi == 0:
                    fhi = 1e-9
                quotients = [lo / flo, lo / fhi, hi / flo, hi / fhi]
                lo, hi = min(quotients), max(quotients)
        return lo, hi

    def _fact_bounds(self, ctx: SpecParser.FactContext) -> Tuple[float, float]:
        if ctx.POWER():
            blo, bhi = self._prim_bounds(ctx.prim(0))
            elo, ehi = self._prim_bounds(ctx.prim(1))
            combos = [blo**elo, blo**ehi, bhi**elo, bhi**ehi]
            return min(combos), max(combos)
        return self._prim_bounds(ctx.prim(0))

    def _prim_bounds(self, ctx: SpecParser.PrimContext) -> Tuple[float, float]:
        if ctx.number():
            v = self._number_value(ctx.number())
            return v, v
        elif ctx.LPAREN():
            return self._expr_bounds(ctx.expr())
        elif ctx.distributionSample():
            return self._distribution_bounds(ctx.distributionSample())
        return 0.0, INF

    def _distribution_bounds(
        self, ctx: SpecParser.DistributionSampleContext
    ) -> Tuple[float, float]:
        func_name = ctx.ID().getText()
        params = [self._expr_bounds(e) for e in ctx.parameters().expr()]
        # Use midpoint of each param range as the argument to bounds function.
        # This is arguably conservative: distribution_bounds_functions are
        # defined to return the widest possible support given fixed parameters.
        mid_params = [(lo + hi) / 2 for lo, hi in params]
        if func_name in distribution_bounds_functions:
            return distribution_bounds_functions[func_name](*mid_params)
        return 0.0, INF

    def _number_value(self, ctx: SpecParser.NumberContext) -> float:
        if ctx.INT() is not None:
            return float(ctx.INT().getText())
        return float(ctx.FLOAT().getText())

    # ── Visitor overrides ─────────────────────────────────────────────────

    def visitSubsystem(self, ctx: SpecParser.SubsystemContext):
        self._subsystems[ctx.ID().getText()] = ctx
        return None

    def visitLet(self, ctx: SpecParser.LetContext):
        raw_id: str = ctx.variable().getText()
        scoped_id = self._scoped(raw_id)

        asset_instantiation = ctx.assetSet().assetInstantiation()

        if asset_instantiation:
            type_name: str = asset_instantiation.ID().getText()

            if type_name in self._subsystems:
                # Subsystem instantiation, determine how many copies.
                num_lo, num_hi = 1, 1
                if asset_instantiation.expr():
                    num_lo, num_hi = self._expr_bounds(asset_instantiation.expr())
                num_lo = max(0, math.floor(num_lo))
                num_hi = math.floor(num_hi) if num_hi != INF else INF

                # Visit the subsystem body once to collect internal structure,
                # then merge upward multiplied by the instance count.
                sub_ctx = self._subsystems[type_name]
                self._subsystem_stack.append((scoped_id, {}, {}))
                self.visitChildren(sub_ctx)
                _, inner_bounds, inner_types = self._subsystem_stack.pop()

                target_bounds = self._current_bounds()
                target_types = self._current_types()

                for k, cb in inner_bounds.items():
                    # Multiply internal cardinality by number of subsystem copies
                    merged_lo = cb.min * num_lo
                    merged_hi = (
                        cb.max * num_hi if num_hi != INF and cb.max != INF else INF
                    )
                    target_bounds[k] = CardinalityBound(
                        math.floor(merged_lo),
                        math.floor(merged_hi) if merged_hi != INF else INF,
                    )
                    target_types[k] = inner_types.get(k)
                return None
            # else: plain asset instantiation, fall through to handler below

        # Plain asset set (instantiation or variable reference)
        cb, asset_type = self._visit_asset_set_bounds(ctx.assetSet())
        self._current_bounds()[scoped_id] = cb
        self._current_types()[scoped_id] = asset_type
        return None

    def _visit_asset_set_bounds(
        self, ctx: SpecParser.AssetSetContext
    ) -> Tuple[CardinalityBound, Optional[str]]:
        if ctx.assetInstantiation():
            return self._visit_asset_instantiation_bounds(ctx.assetInstantiation())

        elif ctx.variable():
            var_id = self._scoped(ctx.variable().getText())
            cb, t = self._resolve_variable(var_id)
            if cb is None:
                # Fallback to maximal uncertainty on unknown variable
                return CardinalityBound(0, INF), None
            return cb, t

        elif ctx.subsystemSetAccess():
            # e.g. networks.hosts — resolve via the stored bounds
            ids = [tok.getText() for tok in ctx.subsystemSetAccess().ID()]
            prefix = self._current_prefix()
            # Build the full dotted key as the instantiator would
            full_key = ".".join([f"{prefix}.{ids[0]}" if prefix else ids[0]] + ids[1:])
            cb = self._current_bounds().get(full_key)
            t = self._current_types().get(full_key)
            if cb is None:
                return CardinalityBound(0, INF), t
            return cb, t

        return CardinalityBound(0, INF), None

    def _visit_asset_instantiation_bounds(
        self, ctx: SpecParser.AssetInstantiationContext
    ) -> Tuple[CardinalityBound, str]:
        asset_type: str = ctx.ID().getText()
        lo, hi = 1.0, 1.0
        if ctx.expr():
            lo, hi = self._expr_bounds(ctx.expr())
        lo = max(0, math.floor(lo))
        hi = math.floor(hi) if hi != INF else INF
        return CardinalityBound(lo, hi), asset_type

    def visitConnect(self, ctx: SpecParser.ConnectContext):
        if ctx.connectionRule():
            for rule_ctx in ctx.connectionRule():
                self._process_connection_rule(rule_ctx)

    def _process_connection_rule(self, ctx: SpecParser.ConnectionRuleContext) -> None:
        weight: float = float(ctx.number().getText())
        is_certain = weight == 1.0

        left_cb, left_type = self._visit_asset_set_bounds(ctx.assetSet(0))
        fieldname: str = ctx.associationFieldname().ID().getText()
        right_cb, right_type = self._visit_asset_set_bounds(ctx.assetSet(1))

        if left_type is None or right_type is None:
            return

        # Defensive coercion in case bounds resolution returned None fields
        left_min = left_cb.min if left_cb.min is not None else 0
        left_max = left_cb.max if left_cb.max is not None else INF
        right_min = right_cb.min if right_cb.min is not None else 0
        right_max = right_cb.max if right_cb.max is not None else INF

        # For each individual left asset, how many right assets could it connect to?
        # RGG connects each pair with some probability; a single left asset could
        # connect to anywhere in [0, right_set_size] right assets.
        # With weight==1.0, at least right_cb.min are guaranteed reachable
        # (entire unit square is covered). With weight<1.0, minimum is 0.
        per_asset_min = right_min if is_certain else 0
        per_asset_max = right_max

        token = ctx.associationFieldname().ID().getSymbol()

        self._accumulate(left_type, fieldname, per_asset_min, per_asset_max, token)

        # Handle reverse association case
        assoc = self._assoc_map.get((left_type, fieldname, right_type))
        if assoc is not None:
            if assoc.right_field.fieldname == fieldname:
                reverse_fieldname = assoc.left_field.fieldname
                reverse_asset_type = right_type
            else:
                reverse_fieldname = assoc.right_field.fieldname
                reverse_asset_type = left_type

            rev_per_asset_min = left_min if is_certain else 0
            rev_per_asset_max = left_max
            self._accumulate(
                reverse_asset_type,
                reverse_fieldname,
                rev_per_asset_min,
                rev_per_asset_max,
                token,
            )

    # ── Final multiplicity check ──────────────────────────────────────────

    def _check_accumulators(self) -> None:
        for (asset_type, fieldname), acc in self._field_accumulators.items():
            if acc.min_connections is None or acc.max_connections is None:
                continue

            assoc = self._find_assoc_for_field(asset_type, fieldname)
            if assoc is None:
                continue

            # Determine which field carries the multiplicity constraint for
            # asset_type's side, i.e. the field whose fieldname matches.
            if assoc.right_field.fieldname == fieldname:
                mult_field = assoc.right_field
            else:
                mult_field = assoc.left_field

            mult_min: int = mult_field.minimum if mult_field.minimum is not None else 0
            mult_max: float = INF if mult_field.maximum is None else mult_field.maximum

            token = acc.source_tokens[0] if acc.source_tokens else None
            line = token.line if token else 0
            col = token.column if token else 0

            if mult_max != INF and acc.min_connections > mult_max:
                self._violations.append(
                    MultiplicityViolation(
                        line=line,
                        column=col,
                        description=(
                            f"Association field '{fieldname}' on asset '{asset_type}' "
                            f"has multiplicity max={int(mult_max)}, but the specification "
                            f"guarantees at least {int(acc.min_connections)} connections. "
                            f"Reduce the size of the connected asset sets or lower the "
                            f"connection weight."
                        ),
                    )
                )

            if mult_min > 0 and acc.max_connections < mult_min:
                self._violations.append(
                    MultiplicityViolation(
                        line=line,
                        column=col,
                        description=(
                            f"Association field '{fieldname}' on asset '{asset_type}' "
                            f"has multiplicity min={mult_min}, but the specification "
                            f"can produce at most {int(acc.max_connections)} connections. "
                            f"Increase the size of the connected asset sets or add "
                            f"additional connection rules."
                        ),
                    )
                )

    def _find_assoc_for_field(
        self, asset_type: str, fieldname: str
    ) -> Optional[LanguageGraphAssociation]:
        """Find the association in the language graph for a given asset type
        and field name."""
        return self._field_assoc_map.get((asset_type, fieldname))


class ProbabilisticMultiplicityAnalyzer(SpecVisitor):
    """
    Estimates the probability that a generated model instance satisfies all
    association multiplicity constraints, using:
      - Expected asset counts derived from distribution expected values
      - RGG degree distribution approximated as Poisson-Binomial
      - Per-asset and global satisfaction probabilities
    """

    def __init__(self, lang_graph: LanguageGraph, threshold: float = 0.9) -> None:
        self._lang_graph = lang_graph
        self._threshold = threshold

        self._assoc_map: Dict[Tuple[str, str, str], LanguageGraphAssociation] = {}
        for assoc in lang_graph.associations:
            lname = assoc.left_field.asset.name
            rname = assoc.right_field.asset.name
            self._assoc_map[(lname, assoc.right_field.fieldname, rname)] = assoc
            self._assoc_map[(rname, assoc.left_field.fieldname, lname)] = assoc

        self._field_assoc_map: Dict[Tuple[str, str], LanguageGraphAssociation] = {}
        for (at, fn, _), assoc in self._assoc_map.items():
            self._field_assoc_map[(at, fn)] = assoc

        self._expected_counts: Dict[str, float] = {}
        self._types: Dict[str, str] = {}
        self._subsystems: Dict[str, SpecParser.SubsystemContext] = {}
        self._subsystem_stack: List[Tuple[str, Dict[str, float], Dict[str, str]]] = []
        self._field_estimates: Dict[Tuple[str, str], FieldEstimate] = {}

    # ── Public entry point ────────────────────────────────────────────────────

    def analyze(self, spec_ctx: SpecParser.SpecContext) -> List[MultiplicityWarning]:
        self._expected_counts = {}
        self._types = {}
        self._subsystems = {}
        self._subsystem_stack = []
        self._field_estimates = {}

        self.visit(spec_ctx)
        return self._compute_warnings()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _current_prefix(self) -> str:
        return self._subsystem_stack[-1][0] if self._subsystem_stack else ""

    def _current_counts(self) -> Dict[str, float]:
        return (
            self._subsystem_stack[-1][1]
            if self._subsystem_stack
            else self._expected_counts
        )

    def _current_types(self) -> Dict[str, str]:
        return self._subsystem_stack[-1][2] if self._subsystem_stack else self._types

    def _scoped(self, raw_id: str) -> str:
        prefix = self._current_prefix()
        return f"{prefix}.{raw_id}" if prefix else raw_id

    def _accumulate(
        self,
        asset_type: str,
        fieldname: str,
        n: float,
        p: float,
        token: Token,
    ) -> None:
        key = (asset_type, fieldname)
        if key not in self._field_estimates:
            self._field_estimates[key] = FieldEstimate()
        est = self._field_estimates[key]
        est.rule_contributions.append(RuleContribution(n=n, p=p))
        est.source_tokens.append(token)

    # ── RGG connection probability ────────────────────────────────────────────

    def _rgg_connection_probability(self, weight: float) -> float:
        """Approximate P(two uniform random points in unit square are within
        r = weight * sqrt(2) of each other).

        Uses the closed-form area-intersection formula for a disk of radius r
        clipped to the unit square, averaged over all point positions.
        For r >= sqrt(2) the entire square is covered so p = 1.
        """
        r = weight * math.sqrt(2)
        if r >= math.sqrt(2):
            return 1.0
        if r <= 0:
            return 0.0
        # Expected fraction of unit square within distance r of a uniform point:
        # p = pi*r^2 - (8/3)*r^3 + (1/2)*r^4  (boundary correction approximation)
        p = math.pi * r**2 - (8 / 3) * r**3 + 0.5 * r**4
        return max(0.0, min(1.0, p))

    # ── Poisson-Binomial degree PMF ───────────────────────────────────────────

    def _poisson_binomial_pmf(
        self, contributions: List[RuleContribution], max_k: int
    ) -> List[float]:
        """Compute the PMF of the sum of independent Binomial(n_i, p_i)
        random variables up to max_k, using the convolution approach.

        Each Binomial(n, p) is itself a sum of n Bernoulli(p) trials, so we
        treat the full degree as a Poisson-Binomial over all individual trials.
        """
        # Collect all individual Bernoulli probabilities
        bernoullis: List[float] = []
        for contrib in contributions:
            n_int = round(contrib.n)
            for _ in range(n_int):
                bernoullis.append(contrib.p)

        # dp[k] = P(sum == k) via convolution
        dp = [0.0] * (max_k + 2)
        dp[0] = 1.0
        for p in bernoullis:
            # Iterate backwards to avoid using updated values
            for k in range(min(len(dp) - 1, len(bernoullis)), 0, -1):
                dp[k] = dp[k] * (1 - p) + dp[k - 1] * p
            dp[0] *= 1 - p

        return dp[: max_k + 1]

    # ── Expected value expression evaluator ──────────────────────────────────

    def _expr_expected(self, ctx: SpecParser.ExprContext) -> float:
        leading_sign = ctx.sign() is not None
        result = self._term_expected(ctx.term(0))
        if leading_sign:
            sign = -1 if ctx.sign().MINUS() is not None else 1
            result *= sign

        for i in range(1, len(ctx.term())):
            op = ctx.getChild(2 * i - (not leading_sign)).getText()
            term_val = self._term_expected(ctx.term(i))
            if op == "+":
                result += term_val
            elif op == "-":
                result -= term_val
        return result

    def _term_expected(self, ctx: SpecParser.TermContext) -> float:
        result = self._fact_expected(ctx.fact(0))
        for i in range(1, len(ctx.fact())):
            op = ctx.getChild(2 * i - 1).getText()
            val = self._fact_expected(ctx.fact(i))
            if op == "*":
                result *= val
            elif op == "/":
                result /= val if val != 0 else 1e-9
        return result

    def _fact_expected(self, ctx: SpecParser.FactContext) -> float:
        if ctx.POWER():
            base = self._prim_expected(ctx.prim(0))
            exp = self._prim_expected(ctx.prim(1))
            return base**exp
        return self._prim_expected(ctx.prim(0))

    def _prim_expected(self, ctx: SpecParser.PrimContext) -> float:
        if ctx.number():
            return self._number_value(ctx.number())
        elif ctx.LPAREN():
            return self._expr_expected(ctx.expr())
        elif ctx.distributionSample():
            return self._distribution_expected(ctx.distributionSample())
        return 1.0

    def _distribution_expected(
        self, ctx: SpecParser.DistributionSampleContext
    ) -> float:
        func_name = ctx.ID().getText()
        params = [self._expr_expected(e) for e in ctx.parameters().expr()]
        if func_name in distribution_expected_functions:
            return distribution_expected_functions[func_name](*params)
        return 1.0

    def _number_value(self, ctx: SpecParser.NumberContext) -> float:
        if ctx.INT() is not None:
            return float(ctx.INT().getText())
        return float(ctx.FLOAT().getText())

    # ── Asset set expected count resolver ─────────────────────────────────────

    def _visit_asset_set_expected(
        self, ctx: SpecParser.AssetSetContext
    ) -> Tuple[float, Optional[str]]:
        if ctx.assetInstantiation():
            return self._visit_asset_instantiation_expected(ctx.assetInstantiation())
        elif ctx.variable():
            var_id = self._scoped(ctx.variable().getText())
            count = self._current_counts().get(var_id, 1.0)
            t = self._current_types().get(var_id)
            return count, t
        elif ctx.subsystemSetAccess():
            ids = [tok.getText() for tok in ctx.subsystemSetAccess().ID()]
            prefix = self._current_prefix()
            full_key = ".".join([f"{prefix}.{ids[0]}" if prefix else ids[0]] + ids[1:])
            count = self._current_counts().get(full_key, 1.0)
            t = self._current_types().get(full_key)
            return count, t
        return 1.0, None

    def _visit_asset_instantiation_expected(
        self, ctx: SpecParser.AssetInstantiationContext
    ) -> Tuple[float, str]:
        asset_type: str = ctx.ID().getText()
        count = 1.0
        if ctx.expr():
            count = self._expr_expected(ctx.expr())
        return max(0.0, count), asset_type

    # ── Visitor overrides ─────────────────────────────────────────────────────

    def visitSpec(self, ctx: SpecParser.SpecContext):
        return self.visitChildren(ctx)

    def visitSubsystem(self, ctx: SpecParser.SubsystemContext):
        self._subsystems[ctx.ID().getText()] = ctx
        return None

    def visitLet(self, ctx: SpecParser.LetContext):
        raw_id = ctx.variable().getText()
        scoped_id = self._scoped(raw_id)

        asset_instantiation = ctx.assetSet().assetInstantiation()

        if asset_instantiation:
            type_name = asset_instantiation.ID().getText()

            if type_name in self._subsystems:
                num_expected = 1.0
                if asset_instantiation.expr():
                    num_expected = self._expr_expected(asset_instantiation.expr())

                sub_ctx = self._subsystems[type_name]
                self._subsystem_stack.append((scoped_id, {}, {}))
                self.visitChildren(sub_ctx)
                _, inner_counts, inner_types = self._subsystem_stack.pop()

                target_counts = self._current_counts()
                target_types = self._current_types()

                for k, inner_count in inner_counts.items():
                    target_counts[k] = inner_count * num_expected
                    target_types[k] = inner_types.get(k)
                return None

        # Plain asset set
        count, asset_type = self._visit_asset_set_expected(ctx.assetSet())
        self._current_counts()[scoped_id] = count
        self._current_types()[scoped_id] = asset_type
        return None

    def visitConnect(self, ctx: SpecParser.ConnectContext):
        if ctx.connectionRule():
            for rule_ctx in ctx.connectionRule():
                self._process_connection_rule(rule_ctx)

    def _process_connection_rule(self, ctx: SpecParser.ConnectionRuleContext) -> None:
        weight = float(ctx.number().getText())
        p = self._rgg_connection_probability(weight)

        left_count, left_type = self._visit_asset_set_expected(ctx.assetSet(0))
        fieldname = ctx.associationFieldname().ID().getText()
        right_count, right_type = self._visit_asset_set_expected(ctx.assetSet(1))

        if left_type is None or right_type is None:
            return

        token = ctx.associationFieldname().ID().getSymbol()

        # Each left asset can connect to E[right_count] right assets
        self._accumulate(left_type, fieldname, right_count, p, token)

        # Reverse direction
        assoc = self._assoc_map.get((left_type, fieldname, right_type))
        if assoc is not None:
            if assoc.right_field.fieldname == fieldname:
                reverse_fieldname = assoc.left_field.fieldname
                reverse_asset_type = right_type
            else:
                reverse_fieldname = assoc.right_field.fieldname
                reverse_asset_type = left_type

            self._accumulate(
                reverse_asset_type, reverse_fieldname, left_count, p, token
            )

    # ── Warning computation ───────────────────────────────────────────────────

    def _compute_warnings(self) -> List[MultiplicityWarning]:
        warnings = []
        for (asset_type, fieldname), est in self._field_estimates.items():
            assoc = self._field_assoc_map.get((asset_type, fieldname))
            if assoc is None:
                continue

            if assoc.right_field.fieldname == fieldname:
                mult_field = assoc.right_field
            else:
                mult_field = assoc.left_field

            mult_min = mult_field.minimum if mult_field.minimum is not None else 0
            mult_max = INF if mult_field.maximum is None else mult_field.maximum

            # Max degree to consider in PMF (cap for performance)
            max_k = int(
                min(
                    sum(round(c.n) for c in est.rule_contributions) + 1,
                    1000,
                )
            )

            pmf = self._poisson_binomial_pmf(est.rule_contributions, max_k)

            # P(mult_min <= degree <= mult_max)
            lo = mult_min
            hi = min(int(mult_max), max_k) if mult_max != INF else max_k
            per_asset_p = sum(pmf[lo : hi + 1])

            # E[N] for this asset type. Look up from expected counts
            n_expected = self._get_expected_asset_count(asset_type)

            # Conservative global probability: per_asset_p ^ n_expected
            global_p = per_asset_p**n_expected if n_expected > 0 else 1.0

            if global_p < self._threshold:
                token = est.source_tokens[0] if est.source_tokens else None
                warnings.append(
                    MultiplicityWarning(
                        line=token.line if token else 0,
                        column=token.column if token else 0,
                        asset_type=asset_type,
                        fieldname=fieldname,
                        mult_min=mult_min,
                        mult_max=mult_max,
                        per_asset_probability=per_asset_p,
                        n_assets_expected=n_expected,
                        global_probability=global_p,
                        threshold=self._threshold,
                    )
                )

        return warnings

    def _get_expected_asset_count(self, asset_type: str) -> float:
        """Sum expected counts across all variables of the given asset type."""
        total = 0.0
        for var_id, t in self._types.items():
            if t == asset_type:
                total += self._expected_counts.get(var_id, 0.0)
        return total

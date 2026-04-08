from __future__ import annotations

import inspect
import math
from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Tuple

from antlr4 import Token
from maltoolbox.language import LanguageGraph
from maltoolbox.language.language_graph_assoc import LanguageGraphAssociation

from instamal.language import SpecVisitor, SpecParser
from instamal.distributions import (
    distribution_bounds_functions,
    distribution_expected_functions,
)

INF = math.inf


# Data structures


@dataclass
class SemanticError:
    line: int
    column: int
    description: str


@dataclass
class CardinalityBound:
    """Inclusive [min, max] count of assets in a set.

    max may be INF to represent an unbounded upper end.
    """

    min: float = 0
    max: float = INF


@dataclass
class MultiplicityViolation:
    line: int
    column: int
    description: str


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
        mult_max_str = '∞' if self.mult_max == INF else str(int(self.mult_max))
        return (
            f'  line {self.line}, col {self.column}: '
            f"Association field '{self.fieldname}' on '{self.asset_type}' "
            f'(multiplicity {self.mult_min}..{mult_max_str}): '
            f'P(single asset satisfied) ≈ {self.per_asset_probability:.2%}, '
            f'with ~{self.n_assets_expected:.1f} assets '
            f'P(all satisfied) ≈ {self.global_probability:.2%} '
            f'(threshold: {self.threshold:.0%})'
        )


@dataclass
class FieldAccumulator:
    """
    Accumulated connection bounds for one (asset_type, fieldname) pair,
    across all connection rules that write to that field.

    min_connections: sum of guaranteed minimums (from weight==1.0 rules,
                     using the lower bound of each right-set size).
                     Rules with weight < 1.0 conservatively contribute 0.
    max_connections: sum of possible maximums (upper bound of each right-set
                     size) across all rules regardless of weight.
    source_tokens:   representative tokens from the spec for error reporting.
    """

    min_connections: float = 0
    max_connections: float = 0
    source_tokens: List[Token] = field(default_factory=list)


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


# Shared multiplicity analyzer base


class MultiplicityAnalyzer(SpecVisitor):
    """
    Shared infrastructure for static and probabilistic multiplicity analysis.

    Both subclasses traverse the same subsystem/let/connect structure and look
    up associations from the language graph. They differ in how they evaluate
    expressions and accumulate connection counts:

    - StaticMultiplicityAnalyzer propagates (lo, hi) bound pairs and works
      with CardinalityBound throughout, so it can precisely determine whether
      a violation is guaranteed regardless of random outcomes.

    - ProbabilisticMultiplicityAnalyzer propagates expected values (single
      floats) and uses a Poisson-Binomial model to estimate acceptance
      probability.

    The base class provides the shared association maps, stack helpers,
    the number helper, and the visitConnect / _process_connection_rule
    skeleton. Subclasses override _eval_expr (used for the base class
    visitParam and visitLet paths) and _accumulate_bounds (called from
    _process_connection_rule with explicit lo/hi pairs).

    Note on the two-scalar design: _process_connection_rule always calls
    _accumulate_bounds(asset_type, fieldname, lo, hi, weight, token) where
    lo and hi are the lower and upper bounds of the opposite-side asset set
    size. The static analyzer uses both; the probabilistic analyzer uses
    only the expected value (which it passes as both lo and hi, since it
    does not distinguish bounds).
    """

    def __init__(self, lang_graph: LanguageGraph) -> None:
        self._lang_graph = lang_graph

        self._assoc_map: Dict[Tuple[str, str, str], LanguageGraphAssociation] = {}
        self._field_assoc_map: Dict[Tuple[str, str], LanguageGraphAssociation] = {}
        for assoc in lang_graph.associations:
            lname = assoc.left_field.asset.name
            rname = assoc.right_field.asset.name
            self._assoc_map[(lname, assoc.right_field.fieldname, rname)] = assoc
            self._assoc_map[(rname, assoc.left_field.fieldname, lname)] = assoc
        for (at, fn, _), assoc in self._assoc_map.items():
            self._field_assoc_map[(at, fn)] = assoc

        # Initialized at the start of each analyze() call.
        # _scalar_map holds the single-scalar representation of each param
        # (upper bound for static, expected value for probabilistic).
        self._scalar_map: Dict[str, float] = {}
        self._subsystems: Dict[str, SpecParser.SubsystemContext] = {}

        # Stack frames: (prefix, local_scalars, local_types)
        self._subsystem_stack: List[Tuple[str, Dict[str, float], Dict[str, str]]] = []

        # Top-level variable maps (used when stack is empty)
        self._variable_scalars: Dict[str, float] = {}
        self._variable_types: Dict[str, str] = {}

    # Stack helpers

    def _current_prefix(self) -> str:
        return self._subsystem_stack[-1][0] if self._subsystem_stack else ''

    def _current_scalars(self) -> Dict[str, float]:
        return (
            self._subsystem_stack[-1][1]
            if self._subsystem_stack
            else self._variable_scalars
        )

    def _current_types(self) -> Dict[str, str]:
        return (
            self._subsystem_stack[-1][2]
            if self._subsystem_stack
            else self._variable_types
        )

    def _scoped(self, raw_id: str) -> str:
        prefix = self._current_prefix()
        return f'{prefix}.{raw_id}' if prefix else raw_id

    # Shared number helper

    def _number_value(self, ctx: SpecParser.NumberContext) -> float:
        if ctx.INT() is not None:
            return float(ctx.INT().getText())
        return float(ctx.FLOAT().getText())

    # Abstract interface for subclasses

    @abstractmethod
    def _eval_expr(self, ctx: SpecParser.ExprContext) -> float:
        """Evaluate an expression to a single scalar.

        For the static analyzer this returns the upper bound; for the
        probabilistic analyzer this returns the expected value. Used by the
        base class visitParam and visitLet to populate _scalar_map and
        _variable_scalars.
        """
        ...

    @abstractmethod
    def _accumulate_bounds(
        self,
        asset_type: str,
        fieldname: str,
        lo: float,
        hi: float,
        weight: float,
        token: Token,
    ) -> None:
        """Record one connection rule's contribution to a field accumulator.

        lo and hi are the lower and upper bounds of the opposite-side asset
        set size for this rule. The static analyzer uses both; the
        probabilistic analyzer treats lo as its expected value (and ignores hi
        since it already received the expected value in both positions).
        """
        ...

    # Shared visitor overrides

    def visitSubsystem(self, ctx: SpecParser.SubsystemContext):
        self._subsystems[ctx.ID().getText()] = ctx
        return None

    def visitParam(self, ctx: SpecParser.ParamContext) -> None:
        param_name: str = ctx.ID().getText()
        self._scalar_map[param_name] = self._eval_expr(ctx.expr())

    def visitLet(self, ctx: SpecParser.LetContext):
        raw_id: str = ctx.variable().getText()
        scoped_id = self._scoped(raw_id)

        asset_instantiation = ctx.assetSet().assetInstantiation()

        if asset_instantiation:
            type_name: str = asset_instantiation.ID().getText()

            if type_name in self._subsystems:
                num = 1.0
                if asset_instantiation.assetInstantiationParameters():
                    num = max(
                        0.0,
                        self._eval_expr(
                            asset_instantiation.assetInstantiationParameters().expr()
                        ),
                    )

                sub_ctx = self._subsystems[type_name]
                self._subsystem_stack.append((scoped_id, {}, {}))
                self.visitChildren(sub_ctx)
                _, inner_scalars, inner_types = self._subsystem_stack.pop()

                target_scalars = self._current_scalars()
                target_types = self._current_types()
                for k, v in inner_scalars.items():
                    target_scalars[k] = v * num
                    target_types[k] = inner_types.get(k)
                return None

        scalar, asset_type = self._visit_asset_set(ctx.assetSet())
        self._current_scalars()[scoped_id] = scalar
        self._current_types()[scoped_id] = asset_type
        return None

    def _visit_asset_set(
        self, ctx: SpecParser.AssetSetContext
    ) -> Tuple[float, Optional[str]]:
        if ctx.assetInstantiation():
            return self._visit_asset_instantiation(ctx.assetInstantiation())
        elif ctx.namedAssetSet():
            return self._visit_named_asset_set(ctx.namedAssetSet())
        return 1.0, None

    def _visit_named_asset_set(
        self, ctx: SpecParser.NamedAssetSetContext
    ) -> Tuple[float, Optional[str]]:
        if ctx.variable():
            var_id = self._scoped(ctx.variable().getText())
            scalar = self._current_scalars().get(var_id, 1.0)
            t = self._current_types().get(var_id)
            return scalar, t
        elif ctx.subsystemSetAccess():
            ids = [tok.getText() for tok in ctx.subsystemSetAccess().ID()]
            prefix = self._current_prefix()
            full_key = '.'.join([f'{prefix}.{ids[0]}' if prefix else ids[0]] + ids[1:])
            scalar = self._current_scalars().get(full_key, 1.0)
            t = self._current_types().get(full_key)
            return scalar, t
        return 1.0, None

    def _visit_asset_instantiation(
        self, ctx: SpecParser.AssetInstantiationContext
    ) -> Tuple[float, str]:
        asset_type: str = ctx.ID().getText()
        scalar = 1.0
        if ctx.assetInstantiationParameters():
            scalar = max(
                0.0, self._eval_expr(ctx.assetInstantiationParameters().expr())
            )
        return scalar, asset_type

    def visitConnect(self, ctx: SpecParser.ConnectContext):
        if ctx.connectionRule():
            for rule_ctx in ctx.connectionRule():
                self._process_connection_rule(rule_ctx)

    def _process_connection_rule(self, ctx: SpecParser.ConnectionRuleContext) -> None:
        """Process one connection rule, calling _accumulate_bounds with the
        lo/hi pair of the opposite-side set for both forward and reverse
        directions.

        Subclasses that need full bound-pair semantics (StaticMultiplicityAnalyzer)
        override this method entirely so that they can call their own
        _visit_asset_set_bounds instead of the scalar-only _visit_asset_set.
        """
        weight: float = float(ctx.number().getText())

        left_scalar, left_type = self._visit_asset_set(ctx.assetSet(0))
        fieldname: str = ctx.associationFieldname().ID().getText()
        right_scalar, right_type = self._visit_asset_set(ctx.assetSet(1))

        if left_type is None or right_type is None:
            return

        token = ctx.associationFieldname().ID().getSymbol()
        # Pass scalar as both lo and hi; subclasses that need distinct bounds
        # override this method rather than _accumulate_bounds.
        self._accumulate_bounds(
            left_type, fieldname, right_scalar, right_scalar, weight, token
        )

        assoc = self._assoc_map.get((left_type, fieldname, right_type))
        if assoc is not None:
            if assoc.right_field.fieldname == fieldname:
                reverse_fieldname = assoc.left_field.fieldname
                reverse_asset_type = right_type
            else:
                reverse_fieldname = assoc.right_field.fieldname
                reverse_asset_type = left_type

            self._accumulate_bounds(
                reverse_asset_type,
                reverse_fieldname,
                left_scalar,
                left_scalar,
                weight,
                token,
            )

    def _find_assoc_for_field(
        self, asset_type: str, fieldname: str
    ) -> Optional[LanguageGraphAssociation]:
        return self._field_assoc_map.get((asset_type, fieldname))


# Static multiplicity analyzer


class StaticMultiplicityAnalyzer(MultiplicityAnalyzer):
    """
    Performs a static multiplicity check over a parsed spec for any guaranteed
    violations, using conservative bound propagation rather than sampling.

    Precision design:

    The static analyzer tracks every asset set size as a CardinalityBound
    (lo, hi) pair rather than as a single scalar. This is essential for
    correctness. Consider a distribution Uniform(2, 6) used as a right-set
    size against a field with mult_max=3:

    - With a single scalar (the upper bound, 6), both min_connections and
      max_connections would be set to 6, causing a spurious guaranteed-minimum
      violation even though the distribution can produce values within bounds.

    - With bound propagation, lo=2 and hi=6. The max_connections accumulator
      receives hi=6, correctly flagging that the set *can* exceed the limit.
      The min_connections accumulator receives lo=2 only when weight==1.0
      (since only certain rules guarantee a minimum), correctly identifying
      that at least 2 connections are guaranteed — which is within the limit,
      so no over-connection violation is raised. A separate check on max vs
      mult_min handles the under-connection direction symmetrically.

    To support this, StaticMultiplicityAnalyzer maintains its own parallel
    data structures:

    - _param_bounds: Dict[str, CardinalityBound] — lo/hi bounds for each
      param, populated in visitParam.
    - _variable_bounds: Dict[str, CardinalityBound] — lo/hi bounds for each
      let variable and subsystem member, populated in visitLet and during
      subsystem merging.

    It overrides visitParam, visitLet, and _process_connection_rule entirely,
    so that these paths always work with CardinalityBound rather than scalars.
    The base class _visit_asset_set / _eval_expr / visitParam / visitLet are
    still called via super() for the scalar-map side effects needed by the
    base class subsystem stack logic, but the static analyzer's own
    accumulation logic uses _visit_asset_set_bounds and _expr_bounds
    exclusively.
    """

    def __init__(self, lang_graph: LanguageGraph) -> None:
        super().__init__(lang_graph)
        self._param_bounds: Dict[str, CardinalityBound] = {}
        self._variable_bounds: Dict[str, CardinalityBound] = {}
        # Stack frames for bounds: mirrors _subsystem_stack but holds bounds
        self._bounds_stack: List[Dict[str, CardinalityBound]] = []
        # (asset_type, fieldname) -> FieldAccumulator
        self._field_accumulators: Dict[Tuple[str, str], FieldAccumulator] = {}

    # Public entry point

    def analyze(self, spec_ctx: SpecParser.SpecContext) -> None:
        """
        Run the static multiplicity analysis.

        Raises:
            Exception: if any guaranteed multiplicity violations are found,
                with a message listing all violations.
        """
        self._scalar_map = {}
        self._param_bounds = {}
        self._variable_bounds = {}
        self._bounds_stack = []
        self._subsystems = {}
        self._subsystem_stack = []
        self._variable_scalars = {}
        self._variable_types = {}
        self._field_accumulators = {}

        self.visit(spec_ctx)
        violations = self._collect_violations()

        if violations:
            messages = '\n'.join(
                f'  line {v.line}, col {v.column}: {v.description}' for v in violations
            )
            raise Exception(f'Multiplicity violation(s) detected:\n{messages}')

    # Bounds stack helpers

    def _current_bounds(self) -> Dict[str, CardinalityBound]:
        return self._bounds_stack[-1] if self._bounds_stack else self._variable_bounds

    # Expression bound evaluator

    def _eval_expr(self, ctx: SpecParser.ExprContext) -> float:
        """Return the upper bound of the expression.

        Used by the base class visitLet/visitParam scalar-map paths, which
        the static analyzer calls via super() only for their side effects on
        the subsystem stack. The static analyzer's own accumulation uses
        _expr_bounds directly.
        """
        _, hi = self._expr_bounds(ctx)
        return hi if hi != INF else INF

    def _expr_bounds(self, ctx: SpecParser.ExprContext) -> Tuple[float, float]:
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
            if op == '+':
                lo += tlo
                hi += thi
            elif op == '-':
                lo -= thi
                hi -= tlo
        return lo, hi

    def _term_bounds(self, ctx: SpecParser.TermContext) -> Tuple[float, float]:
        lo, hi = self._fact_bounds(ctx.fact(0))
        for i in range(1, len(ctx.fact())):
            op = ctx.getChild(2 * i - 1).getText()
            flo, fhi = self._fact_bounds(ctx.fact(i))
            if op == '*':
                products = [lo * flo, lo * fhi, hi * flo, hi * fhi]
                lo, hi = min(products), max(products)
            elif op == '/':
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
        elif ctx.ID():
            name = ctx.ID().getText()
            cb = self._param_bounds.get(name)
            if cb is not None:
                return float(cb.min), float(cb.max)
        return 0.0, INF

    def _distribution_bounds(
        self, ctx: SpecParser.DistributionSampleContext
    ) -> Tuple[float, float]:
        func_name = ctx.ID().getText()
        params = [self._expr_bounds(e) for e in ctx.parameters().expr()]
        mid_params = [(lo + hi) / 2 for lo, hi in params]
        if func_name in distribution_bounds_functions:
            return distribution_bounds_functions[func_name](*mid_params)
        return 0.0, INF

    # Asset set bounds resolver

    def _visit_asset_set_bounds(
        self, ctx: SpecParser.AssetSetContext
    ) -> Tuple[CardinalityBound, Optional[str]]:
        """Resolve an asset set to its (lo, hi) CardinalityBound and type."""
        if ctx.assetInstantiation():
            return self._visit_asset_instantiation_bounds(ctx.assetInstantiation())
        elif ctx.namedAssetSet():
            return self._visit_named_asset_set_bounds(ctx.namedAssetSet())
        return CardinalityBound(0, INF), None

    def _visit_named_asset_set_bounds(
        self, ctx: SpecParser.NamedAssetSetContext
    ) -> Tuple[CardinalityBound, Optional[str]]:
        if ctx.variable():
            var_id = self._scoped(ctx.variable().getText())
            cb = self._current_bounds().get(var_id)
            t = self._current_types().get(var_id)
            if cb is None:
                return CardinalityBound(0, INF), t
            return cb, t
        elif ctx.subsystemSetAccess():
            ids = [tok.getText() for tok in ctx.subsystemSetAccess().ID()]
            prefix = self._current_prefix()
            full_key = '.'.join([f'{prefix}.{ids[0]}' if prefix else ids[0]] + ids[1:])
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
        if ctx.assetInstantiationParameters():
            lo, hi = self._expr_bounds(ctx.assetInstantiationParameters().expr())
        else:
            lo, hi = 1.0, 1.0
        lo = max(0.0, lo)
        return CardinalityBound(lo, hi), asset_type

    # Param and let visitor overrides

    def visitParam(self, ctx: SpecParser.ParamContext) -> None:
        param_name: str = ctx.ID().getText()
        lo, hi = self._expr_bounds(ctx.expr())
        lo_int = math.floor(max(0.0, lo))
        hi_val = math.floor(hi) if hi != INF else INF
        self._param_bounds[param_name] = CardinalityBound(min=lo_int, max=hi_val)
        # Keep scalar_map in sync for the base class subsystem logic
        self._scalar_map[param_name] = hi_val

    def visitLet(self, ctx: SpecParser.LetContext):
        raw_id: str = ctx.variable().getText()
        scoped_id = self._scoped(raw_id)

        asset_instantiation = ctx.assetSet().assetInstantiation()

        if asset_instantiation:
            type_name: str = asset_instantiation.ID().getText()

            if type_name in self._subsystems:
                # Determine how many copies of the subsystem are instantiated.
                if asset_instantiation.assetInstantiationParameters():
                    num_lo, num_hi = self._expr_bounds(
                        asset_instantiation.assetInstantiationParameters().expr()
                    )
                    num_lo = max(0.0, num_lo)
                else:
                    num_lo, num_hi = 1.0, 1.0

                # Push a fresh frame onto both the base class scalar stack and
                # the bounds stack, visit the subsystem body, then merge upward.
                sub_ctx = self._subsystems[type_name]
                self._subsystem_stack.append((scoped_id, {}, {}))
                self._bounds_stack.append({})
                self.visitChildren(sub_ctx)
                _, inner_scalars, inner_types = self._subsystem_stack.pop()
                inner_bounds = self._bounds_stack.pop()

                target_scalars = self._current_scalars()
                target_types = self._current_types()
                target_bounds = self._current_bounds()

                for k, v in inner_scalars.items():
                    target_scalars[k] = v * num_hi
                    target_types[k] = inner_types.get(k)

                for k, cb in inner_bounds.items():
                    merged_lo = cb.min * num_lo
                    merged_hi = (
                        cb.max * num_hi if cb.max != INF and num_hi != INF else INF
                    )
                    target_bounds[k] = CardinalityBound(merged_lo, merged_hi)

                return None

        cb, asset_type = self._visit_asset_set_bounds(ctx.assetSet())
        self._current_bounds()[scoped_id] = cb
        # Keep scalar-side in sync using the upper bound
        self._current_scalars()[scoped_id] = cb.max if cb.max != INF else INF
        self._current_types()[scoped_id] = asset_type
        return None

    # Connection rule override

    def _process_connection_rule(self, ctx: SpecParser.ConnectionRuleContext) -> None:
        """Override the base class to use CardinalityBound pairs throughout."""
        weight: float = float(ctx.number().getText())

        left_cb, left_type = self._visit_asset_set_bounds(ctx.assetSet(0))
        fieldname: str = ctx.associationFieldname().ID().getText()
        right_cb, right_type = self._visit_asset_set_bounds(ctx.assetSet(1))

        if left_type is None or right_type is None:
            return

        token = ctx.associationFieldname().ID().getSymbol()
        self._accumulate_bounds(
            left_type,
            fieldname,
            right_cb.min,
            right_cb.max,
            weight,
            token,
        )

        assoc = self._assoc_map.get((left_type, fieldname, right_type))
        if assoc is not None:
            if assoc.right_field.fieldname == fieldname:
                reverse_fieldname = assoc.left_field.fieldname
                reverse_asset_type = right_type
            else:
                reverse_fieldname = assoc.right_field.fieldname
                reverse_asset_type = left_type

            self._accumulate_bounds(
                reverse_asset_type,
                reverse_fieldname,
                left_cb.min,
                left_cb.max,
                weight,
                token,
            )

    # Accumulation

    def _accumulate_bounds(
        self,
        asset_type: str,
        fieldname: str,
        lo: float,
        hi: float,
        weight: float,
        token: Token,
    ) -> None:
        """Accumulate one connection rule's contribution.

        lo and hi are the lower and upper bounds of the opposite-side asset
        set size.

        - max_connections accumulates hi regardless of weight, because even a
          weight < 1.0 rule could in principle connect all eligible pairs.
        - min_connections accumulates lo only when weight == 1.0, because only
          a certain rule guarantees that every pair within range is connected.
          A weight < 1.0 rule conservatively contributes 0 to the minimum.
        """
        is_certain = weight == 1.0
        per_asset_min = lo if is_certain else 0.0
        per_asset_max = hi

        key = (asset_type, fieldname)
        if key not in self._field_accumulators:
            self._field_accumulators[key] = FieldAccumulator()
        acc = self._field_accumulators[key]
        acc.min_connections += per_asset_min
        acc.max_connections += per_asset_max
        acc.source_tokens.append(token)

    # Violation check

    def _collect_violations(self) -> List[MultiplicityViolation]:
        violations = []
        for (asset_type, fieldname), acc in self._field_accumulators.items():
            assoc = self._find_assoc_for_field(asset_type, fieldname)
            if assoc is None:
                continue

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
                violations.append(
                    MultiplicityViolation(
                        line=line,
                        column=col,
                        description=(
                            f"Association field '{fieldname}' on asset "
                            f"'{asset_type}' has multiplicity "
                            f'max={int(mult_max)}, but the specification '
                            f'guarantees at least '
                            f'{int(acc.min_connections)} connections. '
                            f'Reduce the size of the connected asset sets '
                            f'or lower the connection weight.'
                        ),
                    )
                )

            if mult_min > 0 and acc.max_connections < mult_min:
                violations.append(
                    MultiplicityViolation(
                        line=line,
                        column=col,
                        description=(
                            f"Association field '{fieldname}' on asset "
                            f"'{asset_type}' has multiplicity "
                            f'min={mult_min}, but the specification '
                            f'can produce at most '
                            f'{int(acc.max_connections)} connections. '
                            f'Increase the size of the connected asset sets '
                            f'or add additional connection rules.'
                        ),
                    )
                )
        return violations


# Probabilistic multiplicity analyzer


class ProbabilisticMultiplicityAnalyzer(MultiplicityAnalyzer):
    """
    Estimates the probability that a generated model instance satisfies all
    association multiplicity constraints, using:
      - Expected asset counts derived from distribution expected values
      - RGG degree distribution approximated as Poisson-Binomial
      - Per-asset and global satisfaction probabilities
    """

    def __init__(self, lang_graph: LanguageGraph, threshold: float = 0.9) -> None:
        super().__init__(lang_graph)
        self._threshold = threshold
        self._field_estimates: Dict[Tuple[str, str], FieldEstimate] = {}

    # Public entry point

    def analyze(self, spec_ctx: SpecParser.SpecContext) -> List[MultiplicityWarning]:
        """
        Run the probabilistic multiplicity analysis.

        Returns:
            A list of MultiplicityWarning for fields whose global acceptance
            probability falls below the configured threshold.
        """
        self._scalar_map = {}
        self._subsystems = {}
        self._subsystem_stack = []
        self._variable_scalars = {}
        self._variable_types = {}
        self._field_estimates = {}

        self.visit(spec_ctx)
        return self._compute_warnings()

    # Expression expected-value evaluator

    def _eval_expr(self, ctx: SpecParser.ExprContext) -> float:
        leading_sign = ctx.sign() is not None
        result = self._eval_term(ctx.term(0))
        if leading_sign:
            sign = -1 if ctx.sign().MINUS() is not None else 1
            result *= sign

        for i in range(1, len(ctx.term())):
            op = ctx.getChild(2 * i - (not leading_sign)).getText()
            term_val = self._eval_term(ctx.term(i))
            if op == '+':
                result += term_val
            elif op == '-':
                result -= term_val
        return result

    def _eval_term(self, ctx: SpecParser.TermContext) -> float:
        result = self._eval_fact(ctx.fact(0))
        for i in range(1, len(ctx.fact())):
            op = ctx.getChild(2 * i - 1).getText()
            val = self._eval_fact(ctx.fact(i))
            if op == '*':
                result *= val
            elif op == '/':
                result /= val if val != 0 else 1e-9
        return result

    def _eval_fact(self, ctx: SpecParser.FactContext) -> float:
        if ctx.POWER():
            base = self._eval_prim(ctx.prim(0))
            exp = self._eval_prim(ctx.prim(1))
            return base**exp
        return self._eval_prim(ctx.prim(0))

    def _eval_prim(self, ctx: SpecParser.PrimContext) -> float:
        if ctx.number():
            return self._number_value(ctx.number())
        elif ctx.LPAREN():
            return self._eval_expr(ctx.expr())
        elif ctx.distributionSample():
            return self._eval_distribution(ctx.distributionSample())
        elif ctx.ID():
            return self._scalar_map.get(ctx.ID().getText(), 1.0)
        return 1.0

    def _eval_distribution(self, ctx: SpecParser.DistributionSampleContext) -> float:
        func_name = ctx.ID().getText()
        params = [self._eval_expr(e) for e in ctx.parameters().expr()]
        if func_name in distribution_expected_functions:
            return distribution_expected_functions[func_name](*params)
        return 1.0

    # RGG connection probability

    def _rgg_connection_probability(self, weight: float) -> float:
        """Approximate P(two uniform random points in the unit square are
        within r = weight * sqrt(2) of each other).

        Uses the closed-form area-intersection formula for a disk of radius r
        clipped to the unit square, averaged over all point positions.
        For r >= sqrt(2) the entire square is covered so p = 1.
        """
        r = weight * math.sqrt(2)
        if r >= math.sqrt(2):
            return 1.0
        if r <= 0:
            return 0.0
        p = math.pi * r**2 - (8 / 3) * r**3 + 0.5 * r**4
        return max(0.0, min(1.0, p))

    # Poisson-Binomial degree PMF

    def _poisson_binomial_pmf(
        self, contributions: List[RuleContribution], max_k: int
    ) -> List[float]:
        """Compute the PMF of the sum of independent Binomial(n_i, p_i)
        random variables up to max_k, using the convolution approach.

        Each Binomial(n, p) is itself a sum of n Bernoulli(p) trials, so we
        treat the full degree as a Poisson-Binomial over all individual trials.
        """
        bernoullis: List[float] = []
        for contrib in contributions:
            n_int = round(contrib.n)
            for _ in range(n_int):
                bernoullis.append(contrib.p)

        dp = [0.0] * (max_k + 2)
        dp[0] = 1.0
        for p in bernoullis:
            for k in range(min(len(dp) - 1, len(bernoullis)), 0, -1):
                dp[k] = dp[k] * (1 - p) + dp[k - 1] * p
            dp[0] *= 1 - p

        return dp[: max_k + 1]

    # Accumulation

    def _accumulate_bounds(
        self,
        asset_type: str,
        fieldname: str,
        lo: float,
        hi: float,  # noqa: ARG002 — unused; probabilistic analyzer uses lo only
        weight: float,
        token: Token,
    ) -> None:
        """Record one connection rule's contribution.

        The probabilistic analyzer only needs the expected value, which the
        base class _process_connection_rule passes as lo (with lo == hi ==
        expected_value).
        """
        p = self._rgg_connection_probability(weight)
        key = (asset_type, fieldname)
        if key not in self._field_estimates:
            self._field_estimates[key] = FieldEstimate()
        est = self._field_estimates[key]
        est.rule_contributions.append(RuleContribution(n=lo, p=p))
        est.source_tokens.append(token)

    # Warning computation

    def _compute_warnings(self) -> List[MultiplicityWarning]:
        warnings = []
        for (asset_type, fieldname), est in self._field_estimates.items():
            assoc = self._find_assoc_for_field(asset_type, fieldname)
            if assoc is None:
                continue

            if assoc.right_field.fieldname == fieldname:
                mult_field = assoc.right_field
            else:
                mult_field = assoc.left_field

            mult_min = mult_field.minimum if mult_field.minimum is not None else 0
            mult_max = INF if mult_field.maximum is None else mult_field.maximum

            max_k = int(
                min(
                    sum(round(c.n) for c in est.rule_contributions) + 1,
                    1000,
                )
            )

            pmf = self._poisson_binomial_pmf(est.rule_contributions, max_k)

            lo = mult_min
            hi = min(int(mult_max), max_k) if mult_max != INF else max_k
            per_asset_p = sum(pmf[lo : hi + 1])

            n_expected = self._get_expected_asset_count(asset_type)
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
        for var_id, t in self._variable_types.items():
            if t == asset_type:
                total += self._variable_scalars.get(var_id, 0.0)
        return total


# Semantic analyzer


def _build_distribution_arities() -> Dict[str, int]:
    """Return a mapping from distribution name to expected parameter count,
    derived from the signatures of the bounds functions."""
    return {
        name: len(inspect.signature(fn).parameters)
        for name, fn in distribution_bounds_functions.items()
    }


_DISTRIBUTION_ARITIES: Dict[str, int] = _build_distribution_arities()


class SemanticAnalyzer(SpecVisitor):
    """
    Performs semantic analysis of a spec language file.

    Raises an Exception immediately upon finding the first error, so every
    visitor method is guaranteed to run in a valid state and none of them
    need to guard against a previously recorded error.

    Checks performed:

    - All asset type names used in let declarations and inline instantiations
      must exist in the DSL language assets.
    - All param, variable and subsystem names must be unique across all three
      namespaces.
    - All distributionSample function names must be known, with the correct
      number of arguments.
    - All subsystemSetAccess paths must be valid given the subsystems and
      variables declared so far.
    - All variables must resolve to exactly one concrete MAL asset type .
    - All connection rule weights must be in [0, 1].
    - All connection rules must correspond to a valid association in the DSL.
    - prune arguments must each resolve to a concrete asset type.
    - All defenseControl names in an assetInstantiation must be valid defenses
      of that asset type, and no defense may be set more than once in the same
      instantiation.
    """

    def __init__(self, lang_graph: LanguageGraph) -> None:
        self._lang_info = (
            f'{lang_graph.metadata["id"]}, {lang_graph.metadata["version"]}'
        )
        self._lang_assets: Set[str] = set(lang_graph.assets.keys())
        self._lang_associations: Set[Tuple[str, str, str]] = set()
        for asset in lang_graph.assets.values():
            for fieldname, assoc in asset.associations.items():
                target_asset = assoc.get_field(fieldname).asset
                for sub_asset in target_asset.sub_assets:
                    self._lang_associations.add((asset.name, fieldname, sub_asset.name))

        self._asset_defenses: Dict[str, Set[str]] = {}
        for asset_name, asset in lang_graph.assets.items():
            defenses: Set[str] = set()
            for step_name, step in asset.attack_steps.items():
                if step.type == 'defense':
                    defenses.add(step_name)
            self._asset_defenses[asset_name] = defenses

        self._params: Set[str] = set()

        self._subsystems: Set[str] = set()
        self._subsystem_defs: Dict[str, Dict[str, str]] = {}

        self._variable_types: Dict[str, str] = {}

        self._current_subsystem_name: Optional[str] = None
        self._current_subsystem_members: Optional[Dict[str, str]] = None
        self._current_variable: str = ''

    # Public entry point

    def analyze(self, spec_ctx: SpecParser.SpecContext) -> None:
        """Analyze the spec for semantic errors.

        Raises:
            Exception: on the first semantic error found, with line/col info.
        """
        self._params = set()
        self._subsystems = set()
        self._subsystem_defs = {}
        self._variable_types = {}
        self._current_subsystem_name = None
        self._current_variable = ''

        # First pass: register all subsystem definitions so that forward
        # references from let declarations to subsystem types are valid.
        for child in spec_ctx.getChildren():
            if isinstance(child, SpecParser.SubsystemContext):
                self._register_subsystem(child)

        # Second pass: visit params, lets, connects and prune in order.
        self.visit(spec_ctx)

    # Error reporting

    def _fail(self, line: int, col: int, message: str) -> None:
        raise Exception(f'Semantic error on line {line}, col {col}: {message}')

    def _fail_token(self, token, message: str) -> None:
        self._fail(token.line, token.column, message)

    # Name uniqueness

    def _all_declared_names(self) -> Set[str]:
        return self._params | set(self._variable_types) | set(self._subsystems)

    def _assert_name_available(self, token) -> None:
        name = token.getText() if hasattr(token, 'getText') else token
        symbol = token.getSymbol() if hasattr(token, 'getSymbol') else token
        if name in self._all_declared_names():
            self._fail_token(
                symbol,
                f"Name '{name}' has already been declared.",
            )

    # Subsystem definition registration (first pass)

    def _register_subsystem(self, ctx: SpecParser.SubsystemContext) -> None:
        """Collect a subsystem's member types without executing any checks
        that depend on the order of top-level declarations. Full validation
        happens when the subsystem is visited in the second pass."""
        name = ctx.ID().getText()
        members: Dict[str, str] = {}

        saved = self._current_subsystem_members
        self._current_subsystem_members = members

        for child in ctx.getChildren():
            if isinstance(child, SpecParser.LetContext):
                member_name = child.variable().ID().getText()
                asset_set = child.assetSet()
                if asset_set.assetInstantiation():
                    type_name = asset_set.assetInstantiation().ID().getText()
                    members[member_name] = type_name
                elif asset_set.namedAssetSet():
                    text = asset_set.namedAssetSet().getText()
                    if asset_set.namedAssetSet().variable():
                        ref_name = asset_set.namedAssetSet().variable().ID().getText()
                        members[member_name] = members.get(ref_name, ref_name)
                    else:
                        members[member_name] = text

        self._current_subsystem_members = saved
        self._subsystem_defs[name] = members

    # Helpers

    def _resolve_named_asset_set(self, ctx: SpecParser.NamedAssetSetContext) -> str:
        """Resolve a namedAssetSet to its concrete asset type string.

        Raises on any resolution failure.
        """
        if ctx.variable():
            return self._resolve_variable(ctx.variable())
        else:
            return self._resolve_subsystem_set_access(ctx.subsystemSetAccess())

    def _resolve_variable(self, ctx: SpecParser.VariableContext) -> str:
        """Resolve a plain variable reference to its asset type.

        The variable must be declared and must map to a concrete MAL asset
        type (not a subsystem name).
        """
        name = ctx.ID().getText()
        symbol = ctx.ID().getSymbol()

        types = (
            self._current_subsystem_members
            if self._current_subsystem_members is not None
            else self._variable_types
        )

        if name not in types:
            self._fail_token(symbol, f"Variable '{name}' has not been declared.")

        resolved = types[name]
        if resolved not in self._lang_assets:
            self._fail_token(
                symbol,
                f"'{name}' refers to a subsystem, not an asset set. "
                f'Use dot-access to refer to a member instead '
                f'(e.g. {name}.variableName).',
            )
        return resolved

    def _resolve_subsystem_set_access(
        self, ctx: SpecParser.SubsystemSetAccessContext
    ) -> str:
        """Resolve a dot-access path to the asset type of its final segment.

        Each intermediate segment must name a subsystem instantiation whose
        definition is known; the final segment must be a member of that
        subsystem that resolves to a concrete MAL asset type.

        The first segment is looked up in the current scope (subsystem members
        when inside a subsystem body, top-level variables otherwise), since
        dot-access paths can start from a variable declared in either scope.
        """
        ids = [tok for tok in ctx.ID()]
        first_name = ids[0].getText()

        current_scope = (
            self._current_subsystem_members
            if self._current_subsystem_members is not None
            else self._variable_types
        )

        if first_name not in current_scope:
            self._fail_token(
                ids[0].getSymbol(),
                f"Variable '{first_name}' has not been declared.",
            )

        current_type = current_scope[first_name]

        for tok in ids[1:]:
            field = tok.getText()
            if current_type not in self._subsystem_defs:
                self._fail_token(
                    tok.getSymbol(),
                    f"'{current_type}' is not a subsystem and has no member '{field}'.",
                )
            members = self._subsystem_defs[current_type]
            if field not in members:
                self._fail_token(
                    tok.getSymbol(),
                    f"Subsystem '{current_type}' has no member '{field}'.",
                )
            current_type = members[field]

        if current_type not in self._lang_assets:
            last_tok = ids[-1]
            self._fail_token(
                last_tok.getSymbol(),
                f"'{ctx.getText()}' resolves to subsystem '{current_type}', "
                f'not an asset set. Continue the dot-access to a member.',
            )

        return current_type

    # Visitor overrides

    def visitParam(self, ctx: SpecParser.ParamContext) -> None:
        name_tok = ctx.ID()
        name = name_tok.getText()

        if name in self._lang_assets:
            self._fail_token(
                name_tok.getSymbol(),
                f"Cannot use asset type name '{name}' as a param name.",
            )
        self._assert_name_available(name_tok)

        self.visitChildren(ctx)

        self._params.add(name)

    def visitSubsystem(self, ctx: SpecParser.SubsystemContext) -> None:
        name_tok = ctx.ID()
        name = name_tok.getText()

        if name in self._lang_assets:
            self._fail_token(
                name_tok.getSymbol(),
                f"Cannot use asset type name '{name}' as a subsystem name.",
            )
        if name in self._all_declared_names():
            self._fail_token(
                name_tok.getSymbol(),
                f"Name '{name}' has already been declared.",
            )

        self._subsystems.add(name)

        # Visit body in subsystem scope.
        saved_members = self._current_subsystem_members
        saved_name = self._current_subsystem_name
        self._current_subsystem_members = {}
        self._current_subsystem_name = name
        self.visitChildren(ctx)

        # Record member types.
        self._subsystem_defs[name] = self._current_subsystem_members
        self._current_subsystem_members = saved_members
        self._current_subsystem_name = saved_name

    def visitLet(self, ctx: SpecParser.LetContext) -> None:
        name_tok = ctx.variable().ID()
        variable_name = name_tok.getText()

        if variable_name in self._lang_assets:
            self._fail_token(
                name_tok.getSymbol(),
                f"Cannot use asset type name '{variable_name}' as a variable name.",
            )
        if variable_name in self._all_declared_names():
            self._fail_token(
                name_tok.getSymbol(),
                f"Name '{variable_name}' has already been declared.",
            )

        self._current_variable = variable_name
        asset_type = self._visit_asset_set_for_type(ctx.assetSet())

        if self._current_subsystem_members is not None:
            self._current_subsystem_members[variable_name] = asset_type
        else:
            self._variable_types[variable_name] = asset_type

    def _visit_asset_set_for_type(self, ctx: SpecParser.AssetSetContext) -> str:
        """Validate an assetSet and return its concrete asset type."""
        if ctx.assetInstantiation():
            return self._visit_asset_instantiation_for_type(ctx.assetInstantiation())
        elif ctx.namedAssetSet():
            return self._resolve_named_asset_set(ctx.namedAssetSet())
        raise RuntimeError('Unexpected assetSet node.')

    def _visit_asset_instantiation_for_type(
        self, ctx: SpecParser.AssetInstantiationContext
    ) -> str:
        """Validate an asset instantiation and return its asset type."""
        type_tok = ctx.ID()
        type_name = type_tok.getText()

        if type_name in self._subsystem_defs:
            if type_name == self._current_subsystem_name:
                self._fail_token(
                    type_tok.getSymbol(),
                    f"Subsystem '{type_name}' cannot instantiate itself recursively.",
                )
            if (
                ctx.assetInstantiationParameters()
                and ctx.assetInstantiationParameters().defenseControl()
            ):
                first_dc = ctx.assetInstantiationParameters().defenseControl(0)
                self._fail_token(
                    first_dc.ID().getSymbol(),
                    f'Defense controls cannot be applied to a subsystem '
                    f"instantiation of '{type_name}'.",
                )
            members = self._subsystem_defs[type_name]
            scope = (
                self._current_subsystem_members
                if self._current_subsystem_members is not None
                else self._variable_types
            )
            for member_name, member_type in members.items():
                scope[f'{self._current_variable}.{member_name}'] = member_type

            aip = ctx.assetInstantiationParameters()
            if aip and aip.expr():
                self.visitExpr(aip.expr())
            return type_name

        if type_name not in self._lang_assets:
            self._fail_token(
                type_tok.getSymbol(),
                f"Asset type '{type_name}' does not exist in {self._lang_info}.",
            )

        aip = ctx.assetInstantiationParameters()
        if aip and aip.expr():
            self.visitExpr(aip.expr())

        if aip and aip.defenseControl():
            valid_defenses = self._asset_defenses.get(type_name, set())
            seen: Set[str] = set()
            for dc in aip.defenseControl():
                defense_tok = dc.ID()
                defense_name = defense_tok.getText()
                if defense_name not in valid_defenses:
                    self._fail_token(
                        defense_tok.getSymbol(),
                        f"'{defense_name}' is not a defense of asset type "
                        f"'{type_name}'. Valid defenses: "
                        f'{", ".join(sorted(valid_defenses)) or "(none)"}.',
                    )
                if defense_name in seen:
                    self._fail_token(
                        defense_tok.getSymbol(),
                        f"Defense '{defense_name}' is set more than once in "
                        f"this instantiation of '{type_name}'.",
                    )
                seen.add(defense_name)
                self.visitExpr(dc.expr())

        return type_name

    def visitDistributionSample(
        self, ctx: SpecParser.DistributionSampleContext
    ) -> None:
        func_tok = ctx.ID()
        func_name = func_tok.getText()

        if func_name not in _DISTRIBUTION_ARITIES:
            self._fail_token(
                func_tok.getSymbol(),
                f"Unknown distribution function '{func_name}'. "
                f'Supported distributions: '
                f'{", ".join(sorted(_DISTRIBUTION_ARITIES))}.',
            )

        expected = _DISTRIBUTION_ARITIES[func_name]
        actual = len(ctx.parameters().expr())
        if actual != expected:
            self._fail_token(
                func_tok.getSymbol(),
                f"Distribution '{func_name}' expects {expected} argument(s), "
                f'got {actual}.',
            )

        self.visitChildren(ctx)

    def visitPrim(self, ctx: SpecParser.PrimContext) -> None:
        if ctx.ID():
            name = ctx.ID().getText()
            if name not in self._params:
                if name == self._current_variable:
                    self._fail_token(
                        ctx.ID().getSymbol(),
                        f"Param '{name}' cannot reference itself.",
                    )
                else:
                    self._fail_token(
                        ctx.ID().getSymbol(),
                        f"'{name}' has not been declared as a param.",
                    )
        self.visitChildren(ctx)

    def visitConnectionRule(self, ctx: SpecParser.ConnectionRuleContext) -> None:
        weight = float(ctx.number().getText())
        if not 0.0 <= weight <= 1.0:
            num_tok = ctx.number().getStart()
            self._fail_token(
                num_tok,
                f'Connection rule weight must be in [0, 1], got {weight}.',
            )

        left_type = self._resolve_named_asset_set_from_asset_set(ctx.assetSet(0))
        fieldname = ctx.associationFieldname().ID().getText()
        right_type = self._resolve_named_asset_set_from_asset_set(ctx.assetSet(1))

        if (left_type, fieldname, right_type) not in self._lang_associations:
            self._fail_token(
                ctx.associationFieldname().ID().getSymbol(),
                f"Association with fieldname '{fieldname}' from '{left_type}' "
                f"to '{right_type}' does not exist in {self._lang_info}.",
            )

    def _resolve_named_asset_set_from_asset_set(
        self, ctx: SpecParser.AssetSetContext
    ) -> str:
        """Resolve an assetSet used in a connection rule.

        Connection rules may only reference named asset sets (variables or
        subsystem set accesses) or inline instantiations.
        """
        if ctx.namedAssetSet():
            return self._resolve_named_asset_set(ctx.namedAssetSet())
        elif ctx.assetInstantiation():
            return self._visit_asset_instantiation_for_type(ctx.assetInstantiation())
        raise RuntimeError('Unexpected assetSet node in connection rule.')

    def visitPrune(self, ctx: SpecParser.PruneContext) -> None:
        if ctx.pruneParameters() is None:
            return

        for named_set_ctx in ctx.pruneParameters().namedAssetSet():
            self._resolve_named_asset_set(named_set_ctx)

from __future__ import annotations

import itertools as it
import logging
import math
import os
import random

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from antlr4 import CommonTokenStream, FileStream
from maltoolbox.language import LanguageGraph
from maltoolbox.model import Model

from instamal.distributions import distribution_functions
from instamal.language import SpecLexer, SpecParser, SpecVisitor
from instamal.instantiation.spec_analysis import (
    SemanticAnalyzer,
    StaticMultiplicityAnalyzer,
    ProbabilisticMultiplicityAnalyzer,
)

logger = logging.getLogger(__name__)


@dataclass
class SubsystemContext:
    prefix: str
    asset_sets: Dict[str, Set[str]] = field(default_factory=dict)


@dataclass
class ConnectionRule:
    weight: float
    left_set: Set[str]
    right_fieldname: str
    right_set: Set[str]


class ModelInstantiator(SpecVisitor):
    def __init__(
        self, spec_path: str, lang_path: str, interactive: bool = True
    ) -> None:
        input_stream = FileStream(spec_path)
        lang_graph = LanguageGraph().load_from_file(lang_path)

        lexer = SpecLexer(input_stream)
        stream = CommonTokenStream(lexer)
        parser = SpecParser(stream)

        spec_ctx = parser.spec()

        # Semantic analysis, raises on the first error found
        SemanticAnalyzer(lang_graph).analyze(spec_ctx)

        # Static multiplicity check, raises if any guaranteed violations exist
        StaticMultiplicityAnalyzer(lang_graph).analyze(spec_ctx)

        # Probabilistic multiplicity check, returns warnings, does not raise
        warnings = ProbabilisticMultiplicityAnalyzer(lang_graph, threshold=0.9).analyze(
            spec_ctx
        )
        if warnings:
            logger.warning('Probabilistic multiplicity warnings:')
            for w in warnings:
                logger.warning(str(w))
            if interactive:
                answer = input('Proceed with instantiation? [y/N]: ').strip().lower()
                if answer != 'y':
                    raise Exception(
                        'Instantiation aborted by user due to multiplicity warnings.'
                    )

        self._model: Model = None
        self._lang_graph: LanguageGraph = lang_graph
        self._spec_ctx: SpecParser.SpecContext = spec_ctx
        self._asset_sets: Dict[str, Set[str]] = {}
        self._types: Dict[str, str] = {}
        self._type_count: Dict[str, int] = {}
        self._subsystems: Dict[str, SpecParser.SubsystemContext] = {}
        self._subsystem_stack: List[SubsystemContext] = []
        self._param_values: Dict[str, float] = {}
        self._param_exprs: Dict[str, SpecParser.ExprContext] = {}

    def instantiate(
        self, outDirPath: str, n: int = 1, modelPrefix: str = 'model_'
    ) -> None:
        """Instantiate exactly n valid models and save them to the specified directory.

        Retries on failure, consistent with rejection sampling from the MAL model
        distribution. If the acceptance rate drops below 1 in 100 attempts a
        warning is logged, but instantiation continues until n models are produced.
        """
        assert n > 0

        os.makedirs(outDirPath, exist_ok=True)

        warn_threshold = 100
        warned = False
        successful = 0
        attempts = 0

        while successful < n:
            attempts += 1
            modelName = f'{modelPrefix}{successful}'
            try:
                model = self._instantiate_single_model(modelName)
                model.save_to_file(f'{outDirPath}/{modelName}.yml')
                successful += 1
                warned = False
            except Exception as e:
                tb = e.__traceback__
                while tb.tb_next is not None:
                    tb = tb.tb_next
                origin = tb.tb_frame.f_code.co_filename
                if os.path.abspath(origin) == os.path.abspath(__file__):
                    raise
                else:
                    logger.debug(
                        f'Retrying after failed attempt {attempts} '
                        f'({successful}/{n} succeeded so far): {e}'
                    )

            if (
                not warned
                and attempts - successful >= warn_threshold
                and successful < n
            ):
                acceptance_rate = successful / attempts if attempts > 0 else 0
                logger.warning(
                    f'Low acceptance rate: {successful} valid model(s) produced in '
                    f'{attempts} attempt(s) ({acceptance_rate:.1%}). The specification '
                    f'may be too constrained for efficient rejection sampling. '
                    f'Press Ctrl+C to abort.'
                )
                warned = True

        logger.info(f'Successfully instantiated {n} models in {attempts} attempt(s).')

    def _instantiate_single_model(self, name: str) -> Model:
        """Instantiate a new model internally and return it."""
        self._model = Model(name, self._lang_graph)
        self._asset_sets = {}
        self._types = {}
        self._type_count = {}
        self._subsystems = {}
        self._subsystem_stack = []
        self._param_values = {}
        self._param_exprs = {}
        self.visit(self._spec_ctx)
        return self._model

    def _generate_asset_id(self, name_prefix: str) -> str:
        """Generate a unique asset ID given a name prefix."""
        if name_prefix not in self._type_count:
            self._type_count[name_prefix] = 1
        else:
            self._type_count[name_prefix] += 1
        return f'{name_prefix}:{self._type_count[name_prefix]}'

    def _random_connect(self, rules: List[ConnectionRule]) -> None:
        """Connect assets using the heterogeneous random geometric graph algorithm."""
        assets: Set[str] = set()
        for r in rules:
            assets.update(r.left_set)
            assets.update(r.right_set)

        pos: Dict[str, Tuple[float, float]] = {
            asset: (random.random(), random.random()) for asset in assets
        }

        def rule_match(a_l: str, a_r: str, r: ConnectionRule) -> bool:
            return a_l in r.left_set and a_r in r.right_set and a_l != a_r

        def dist(a1: str, a2: str) -> float:
            return math.dist(pos[a1], pos[a2])

        sqrt_2 = math.sqrt(2)
        for asset_l, asset_r in it.permutations(assets, 2):
            for rule in rules:
                assert 0 <= rule.weight <= 1
                if (
                    rule_match(asset_l, asset_r, rule)
                    and dist(asset_l, asset_r) < rule.weight * sqrt_2
                ):
                    model_asset_l = self._model.get_asset_by_name(asset_l)
                    model_asset_r = self._model.get_asset_by_name(asset_r)
                    model_asset_l.add_associated_assets(
                        rule.right_fieldname, {model_asset_r}
                    )

    def _current_prefix(self) -> str:
        return self._subsystem_stack[-1].prefix if self._subsystem_stack else ''

    # Expression evaluators

    def _eval_expr(self, ctx: SpecParser.ExprContext) -> float:
        leading_sign = ctx.sign() is not None
        result = self._eval_term(ctx.term(0))
        if leading_sign:
            result *= -1 if ctx.sign().MINUS() is not None else 1

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
                result /= val
        return result

    def _eval_fact(self, ctx: SpecParser.FactContext) -> float:
        if ctx.POWER():
            return self._eval_prim(ctx.prim(0)) ** self._eval_prim(ctx.prim(1))
        return self._eval_prim(ctx.prim(0))

    def _eval_prim(self, ctx: SpecParser.PrimContext) -> float:
        if ctx.number():
            return self._eval_number(ctx.number())
        elif ctx.LPAREN():
            return self._eval_expr(ctx.expr())
        elif ctx.distributionSample():
            return self._eval_distribution_sample(ctx.distributionSample())
        elif ctx.ID():
            name = ctx.ID().getText()
            if name in self._param_values:
                return self._param_values[name]
            if name in self._param_exprs:
                return self._eval_expr(self._param_exprs[name])
            raise ValueError(f"Undeclared param '{name}' referenced at runtime.")
        raise ValueError('Unexpected prim node.')

    def _eval_distribution_sample(
        self, ctx: SpecParser.DistributionSampleContext
    ) -> float:
        func_name = ctx.ID().getText()
        params = [self._eval_expr(e) for e in ctx.parameters().expr()]
        if func_name in distribution_functions:
            return distribution_functions[func_name](*params)
        raise ValueError(f'Unknown distribution function: {func_name}')

    def _eval_number(self, ctx: SpecParser.NumberContext) -> float:
        if ctx.INT() is not None:
            return int(ctx.INT().getText())
        return float(ctx.FLOAT().getText())

    def _eval_asset_set(
        self, ctx: SpecParser.AssetSetContext, name_prefix: Optional[str] = None
    ) -> Tuple[Set[str], Optional[str]]:
        if ctx.assetInstantiation():
            return self._eval_asset_instantiation(ctx.assetInstantiation(), name_prefix)
        elif ctx.variable() or ctx.subsystemSetAccess():
            variable_id = ctx.getText()
            if self._subsystem_stack:
                full_id = f'{self._current_prefix()}.{variable_id}'
                return (
                    self._subsystem_stack[-1].asset_sets.get(full_id, set()),
                    self._types.get(full_id),
                )
            return (
                self._asset_sets.get(variable_id, set()),
                self._types.get(variable_id),
            )
        raise RuntimeError('Unexpected node in _eval_asset_set.')

    def _eval_asset_instantiation(
        self,
        ctx: SpecParser.AssetInstantiationContext,
        name_prefix: Optional[str] = None,
    ) -> Tuple[Set[str], str]:
        asset_type = ctx.ID().getText()
        num_assets = 1
        if ctx.expr():
            num_assets = math.floor(self._eval_expr(ctx.expr()))

        # If no name prefix was provided this is an inline instantiation
        prefix = name_prefix if name_prefix is not None else f'_{asset_type}'

        assets: Set[str] = set()
        for _ in range(num_assets):
            asset_id = self._generate_asset_id(prefix)
            assets.add(asset_id)
            self._model.add_asset(asset_type=asset_type, name=asset_id)

        for aid in assets:
            self._types[aid] = asset_type

        return assets, asset_type

    # Visitor overrides

    def visitParam(self, ctx: SpecParser.ParamContext) -> None:
        param_name = ctx.ID().getText()
        if ctx.ASSIGN():
            self._param_values[param_name] = self._eval_expr(ctx.expr())
        else:
            self._param_exprs[param_name] = ctx.expr()

    def visitSubsystem(self, ctx: SpecParser.SubsystemContext) -> None:
        self._subsystems[ctx.ID().getText()] = ctx

    def visitLet(self, ctx: SpecParser.LetContext) -> None:
        raw_variable_id = ctx.variable().getText()
        prefix = self._current_prefix()
        variable_id = f'{prefix}.{raw_variable_id}' if prefix else raw_variable_id

        asset_instantiation = ctx.assetSet().assetInstantiation()
        if asset_instantiation:
            type_name = asset_instantiation.ID().getText()
            if type_name in self._subsystems:
                num_subsystems = 1
                if asset_instantiation.expr():
                    num_subsystems = math.floor(
                        self._eval_expr(asset_instantiation.expr())
                    )

                for _ in range(num_subsystems):
                    self._subsystem_stack.append(SubsystemContext(prefix=variable_id))
                    self.visitChildren(self._subsystems[type_name])
                    frame = self._subsystem_stack.pop()

                    target = (
                        self._subsystem_stack[-1].asset_sets
                        if self._subsystem_stack
                        else self._asset_sets
                    )
                    for k, v in frame.asset_sets.items():
                        if k not in target:
                            target[k] = set()
                        target[k].update(v)
                return

        asset_set, asset_type = self._eval_asset_set(
            ctx.assetSet(), name_prefix=variable_id
        )

        if self._subsystem_stack:
            self._subsystem_stack[-1].asset_sets[variable_id] = asset_set
        else:
            self._asset_sets[variable_id] = asset_set
        self._types[variable_id] = asset_type

    def visitConnect(self, ctx: SpecParser.ConnectContext) -> None:
        if not ctx.connectionRule():
            return

        rules: List[ConnectionRule] = []
        for rule_ctx in ctx.connectionRule():
            weight = float(rule_ctx.number().getText())
            if not 0 <= weight <= 1:
                raise ValueError(
                    f'Connection rule weight must be in [0,1], got {weight}.'
                )
            left_set = self._eval_asset_set(rule_ctx.assetSet(0))[0]
            right_fieldname = rule_ctx.associationFieldname().ID().getText()
            right_set = self._eval_asset_set(rule_ctx.assetSet(1))[0]
            rules.append(ConnectionRule(weight, left_set, right_fieldname, right_set))

        self._random_connect(rules)

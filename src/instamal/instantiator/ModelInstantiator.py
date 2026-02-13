import math
import itertools as it
import os
import random
from typing import Dict, List, Optional, Set, Tuple

from antlr4 import *
from maltoolbox.language import LanguageGraph
from maltoolbox.model import Model

from instamal.instantiator.helpers import *


distribution_functions = {
    "Bernoulli": bernoulli,
    "Binomial": binomial,
    "Exponential": exponential,
    "Gamma": gamma,
    "LogNormal": lognormal,
    "Pareto": pareto,
    "TruncatedNormal": truncated_normal,
    "Uniform": uniform,
}


class SubsystemContext:
    def __init__(self, prefix: str, asset_sets: Dict[str, str]):
        self.prefix: str = prefix
        self.asset_sets: Dict[str, str] = asset_sets


class ConnectionRule:
    def __init__(
        self,
        weight: float,
        left_set: Set[str],
        right_fieldname: str,
        right_set: Set[str],
    ):
        self.weight: float = weight
        self.left_set: Set[str] = left_set
        self.right_fieldname: str = right_fieldname
        self.right_set: Set[str] = right_set


class ModelInstantiator(SpecVisitor):
    def __init__(self, spec_path: str, lang_path: str) -> None:
        input_stream = FileStream(spec_path)
        lang_graph = LanguageGraph().load_from_file(lang_path)

        lexer = SpecLexer(input_stream)
        stream = CommonTokenStream(lexer)
        parser = SpecParser(stream)

        spec_ctx = parser.spec()

        analyzer: SpecAnalyzer = SpecAnalyzer(lang_graph)
        error: Optional[AnalyzerError] = analyzer.analyze(spec_ctx)
        if error is not None:
            raise Exception(f"Semantic error on line {error.line}, col {error.column}: {error.description}")

        self._model: Model = None
        self._lang_graph: LanguageGraph = lang_graph
        self._spec_ctx: SpecParser.SpecContext = spec_ctx
        self._asset_sets: Dict[str, Set[str]] = {}
        self._types: Dict[str, str] = {}
        self._type_count: Dict[str, int] = {}
        self._subsystems: Dict[str, SpecParser.SubsystemContext] = {}
        self._subsystem_stack: List[SubsystemContext] = []

    def instantiate(
        self, outDirPath: str, n: int = 1, modelPrefix: str = "model_"
    ) -> None:
        """Instaniate and save n models to the specified directory."""
        assert n > 0

        os.makedirs(outDirPath, exist_ok=True)

        model: Model
        for i in range(n):
            modelName = f"{modelPrefix}{i}"
            model = self._instantiate_single_model(modelName)
            model.save_to_file(f"{outDirPath}/{modelName}.yml")

    def _instantiate_single_model(self, name: str) -> Model:
        """Instanciate a new model internally and return it."""
        self._model = Model(name, self._lang_graph)
        self._asset_sets = {}
        self._types = {}
        self._type_count = {}
        self._subsystems = {}
        self._subsystem_stack = []

        self.visit(self._spec_ctx)
        return self._model

    def _generate_asset_id(self, asset_type: str) -> str:
        """Generate a unique asset ID given an asset type."""
        if not asset_type in self._type_count:
            self._type_count[asset_type] = 1
        else:
            self._type_count[asset_type] += 1
        return f"{asset_type}:{self._type_count[asset_type]}"

    def _random_connect(self, rules: Set[ConnectionRule]) -> None:
        """Using the heterogeneous random geometric graph algorithm, connect all assets specified in the rules according to the rules."""
        assets: Set[str] = set()
        for r in rules:
            assets.update(r.left_set)
            assets.update(r.right_set)

        pos: Dict[str, Tuple[float, float]] = {}
        for asset in assets:
            pos[asset] = (random.random(), random.random())

        def ruleMatch(a_l: str, a_r: str, r: ConnectionRule) -> bool:
            return a_l in r.left_set and a_r in r.right_set and not a_l == a_r

        def dist(a1: str, a2: str) -> float:
            p1: Tuple[float, float] = pos[a1]
            p2: Tuple[float, float] = pos[a2]
            return math.dist(p1, p2)

        sqrt_2 = math.sqrt(2)
        for asset_l, asset_r in it.permutations(assets, 2):
            for rule in rules:
                assert 0 <= rule.weight and rule.weight <= 1
                r = rule.weight * sqrt_2
                if ruleMatch(asset_l, asset_r, rule) and dist(asset_l, asset_r) < r:
                    model_asset_l = self._model.get_asset_by_name(asset_l)
                    model_asset_r = self._model.get_asset_by_name(asset_r)
                    model_asset_l.add_associated_assets(
                        rule.right_fieldname, set([model_asset_r])
                    )
    
    def _current_prefix(self) -> str:
        if not self._subsystem_stack:
            return ""
        return self._subsystem_stack[-1].prefix

    def visitExpr(self, ctx: SpecParser.ExprContext) -> float:
        result: float = 0
        leadingSign = ctx.sign() is not None

        first_term = self.visit(ctx.term(0))
        if leadingSign:
            first_term *= self.visit(ctx.sign())
        result += first_term

        for i in range(1, len(ctx.term())):
            operator = ctx.getChild(2 * i - (not leadingSign)).getText()
            next_term = self.visit(ctx.term(i))

            if operator == "+":
                result += next_term
            elif operator == "-":
                result -= next_term

        return result

    def visitSign(self, ctx) -> int:
        return -1 if ctx.MINUS() is not None else 1

    def visitTerm(self, ctx: SpecParser.TermContext) -> float:
        first_fact = self.visit(ctx.fact(0))
        result = first_fact

        for i in range(1, len(ctx.fact())):
            operator = ctx.getChild(2 * i - 1).getText()
            fact_value = self.visit(ctx.fact(i))
            if operator == "*":
                result *= fact_value
            elif operator == "/":
                result /= fact_value

        return result

    def visitFact(self, ctx: SpecParser.FactContext) -> float:
        if ctx.POWER():
            base = self.visit(ctx.prim(0))
            exponent = self.visit(ctx.prim(1))
            return base**exponent

        return self.visit(ctx.prim(0))

    def visitPrim(self, ctx: SpecParser.PrimContext) -> float:
        if ctx.number():
            return self.visit(ctx.number())
        elif ctx.LPAREN():
            return self.visit(ctx.expr())
        elif ctx.distributionSample():
            return self.visit(ctx.distributionSample())

    def visitDistributionSample(
        self, ctx: SpecParser.DistributionSampleContext
    ) -> float:
        func_name = ctx.ID().getText()
        parameters = self.visit(ctx.parameters())

        if func_name in distribution_functions:
            return distribution_functions[func_name](*parameters)
        else:
            raise ValueError(f"Unknown distribution function: {func_name}")

    def visitParameters(self, ctx: SpecParser.ParametersContext) -> List[float]:
        return [self.visit(expr) for expr in ctx.expr()]

    def visitNumber(self, ctx: SpecParser.NumberContext) -> int | float:
        if ctx.INT() is not None:
            return int(ctx.INT().getText())
        else:
            return float(ctx.FLOAT().getText())

    def visitSubsystem(self, ctx: SpecParser.SubsystemContext):
        self._subsystems[ctx.ID().getText()] = ctx
        return None

    def visitLet(self, ctx: SpecParser.LetContext):
        raw_variable_id: str = ctx.variable().getText()

        prefix = self._current_prefix()
        variable_id = f"{prefix}.{raw_variable_id}" if prefix else raw_variable_id

        asset_instantiation: SpecParser.AssetInstantiationContext = ctx.assetSet().assetInstantiation()
        if asset_instantiation:
            type: str = asset_instantiation.ID().getText()
            if type in self._subsystems:
                full_prefix = variable_id

                num_subsystems = 1
                if asset_instantiation.expr():
                    num_subsystems = math.floor(self.visitExpr(asset_instantiation.expr()))

                for _ in range(num_subsystems):
                    self._subsystem_stack.append(SubsystemContext(full_prefix, {}))

                    self.visitChildren(self._subsystems[type])

                    frame = self._subsystem_stack.pop()

                    # Merge asset sets upward
                    if self._subsystem_stack:
                        # Nested case
                        for k, v in frame.asset_sets.items():
                            if k not in self._subsystem_stack[-1].asset_sets:
                                self._subsystem_stack[-1].asset_sets[k] = set()
                            self._subsystem_stack[-1].asset_sets[k].update(v)
                    else:
                        # Top-level subsystem instantiation
                        for k, v in frame.asset_sets.items():
                            if k not in self._asset_sets:
                                self._asset_sets[k] = set()
                            self._asset_sets[k].update(v)
                return None


        asset_info: Tuple[Set[str], str] = self.visit(ctx.assetSet())
        asset_set: Set[str] = asset_info[0]
        asset_type: str = asset_info[1]

        if self._subsystem_stack:
            self._subsystem_stack[-1].asset_sets[variable_id] = asset_set
        else:
            self._asset_sets[variable_id] = asset_set
        self._types[variable_id] = asset_type

        return None
            

    def visitAssetSet(self, ctx: SpecParser.AssetSetContext) -> Tuple[Set[str], str]:
        if ctx.assetInstantiation():
            return self.visit(ctx.assetInstantiation())
        elif ctx.variable() or ctx.subsystemSetAccess():
            variable_id: str = ctx.getText()
            if self._subsystem_stack:
                prefix = self._current_prefix()
                full_id = f"{prefix}.{variable_id}"
                return self._subsystem_stack[-1].asset_sets[full_id], self._types[full_id]
            else:
                return self._asset_sets[variable_id], self._types[variable_id]
        else:
            raise RuntimeError(
                "Something bad happened in ModelInstantiator.visitAssetSet"
            )

    def visitAssetInstantiation(
        self, ctx: SpecParser.AssetInstantiationContext
    ) -> Tuple[Set[str], str]:
        asset_type: str = ctx.ID().getText()

        num_assets: int = 1
        if ctx.expr():
            num_assets = math.floor(self.visit(ctx.expr()))

        assets: Set[str] = set()
        for _ in range(num_assets):
            asset_id: str = self._generate_asset_id(asset_type)
            assets.add(asset_id)
            self._model.add_asset(asset_type=asset_type, name=asset_id)

        for id in assets:
            self._types[id] = asset_type

        return assets, asset_type

    def visitConnect(self, ctx: SpecParser.ConnectContext):
        if ctx.connectionRule():
            rules: Set[ConnectionRule] = set()
            for i in range(len(ctx.connectionRule())):
                rules.add(self.visit(ctx.connectionRule(i)))
            self._random_connect(rules)

    def visitConnectionRule(self, ctx: SpecParser.ConnectionRuleContext):
        weight: float = float(ctx.number().getText())
        if weight < 0 or weight > 1:
            raise ValueError(
                f"Connection rule weight must be in range [0,1], got {weight}."
            )
        left_set: Set[str] = self.visit(ctx.assetSet(0))[0]
        right_fieldname: str = self.visit(ctx.associationFieldname())
        right_set: Set[str] = self.visit(ctx.assetSet(1))[0]

        return ConnectionRule(weight, left_set, right_fieldname, right_set)

    def visitAssociationFieldname(self, ctx: SpecParser.AssociationFieldnameContext):
        return ctx.ID().getText()
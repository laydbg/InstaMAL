from typing import Dict, Optional, Set, Tuple

from antlr4 import *
from maltoolbox.language import LanguageGraph

from instamal.instantiator.helpers import SpecVisitor, SpecParser


class AnalyzerError:
    def __init__(self, line: int, column: int, description: str):
        self.line: int = line
        self.column: int = column
        self.description: str = description


class SpecAnalyzer(SpecVisitor):
    """Perform semantic analysis of a Spec language file. Stops after first
    error encountered."""

    def __init__(self, lang_graph: LanguageGraph):
        self._error: Optional[AnalyzerError] = None
        self._lang_info: str = (
            f"{lang_graph.metadata['id']}, {lang_graph.metadata['version']}"
        )
        self._lang_assets: Set[str] = {asset for asset in lang_graph.assets.keys()}
        self._lang_associations: Set[Tuple[str, str, str]] = set()
        for asset in lang_graph.assets.values():
            for fieldname, assoc in asset.associations.items():
                target_asset = assoc.get_field(fieldname).asset
                for sub_asset in target_asset.sub_assets:
                    self._lang_associations.add((asset.name, fieldname, sub_asset.name))

        self._variable_types: Dict[str, str] = {}
        self._defined_subsystems: Dict[str, Dict[str, str]] = {}
        self._in_subsystem_context: bool = False
        self._subsystem_variable_types: Dict[str, str] = {}
        self._current_variable: str = ""
        self._declared_params: Set[str] = set()
        self._current_param: Optional[str] = None
        self._spec_ctx: SpecParser.SpecContext = None

    def analyze(self, spec_ctx: SpecParser.SpecContext) -> Optional[AnalyzerError]:
        """Analyze the spec and return the first semantic error found, or None."""
        self._variable_types = {}
        self._defined_subsystems = {}
        self._in_subsystem_context = False
        self._subsystem_variable_types = {}
        self._current_variable = ""
        self._declared_params = set()
        self._current_param = None
        self._spec_ctx = spec_ctx
        self.visit(spec_ctx)
        return self._error

    def _report_error(self, symbol: Token, description: str) -> None:
        if self._error is None:
            self._error = AnalyzerError(symbol.line, symbol.column, description)

    def _all_declared_names(self) -> Set[str]:
        """Return all names currently in use across params, variables, and
        subsystems, for conflict checking."""
        return (
            self._declared_params
            | set(self._variable_types.keys())
            | set(self._defined_subsystems.keys())
        )

    def _resolve_subsystem_access(
        self, ctx: SpecParser.SubsystemSetAccessContext
    ) -> Optional[str]:
        if self._error is not None:
            return None

        ids = [id_token.getText() for id_token in ctx.ID()]
        types = (
            self._variable_types
            if not self._in_subsystem_context
            else self._subsystem_variable_types
        )

        first = ids[0]
        if first not in types:
            self._report_error(
                ctx.ID(0).getSymbol(),
                f"Variable name '{first}' has not been declared.",
            )
            return None

        current_type = types[first]
        for i, field in enumerate(ids[1:], start=1):
            if current_type not in self._defined_subsystems:
                self._report_error(
                    ctx.ID(i).getSymbol(),
                    f"Asset '{current_type}' has no members (not a subsystem).",
                )
                return None

            subsystem_fields = self._defined_subsystems[current_type]
            if field not in subsystem_fields:
                self._report_error(
                    ctx.ID(i).getSymbol(),
                    f"Subsystem '{current_type}' has no member '{field}'.",
                )
                return None

            current_type = subsystem_fields[field]
        return current_type

    def visitParam(self, ctx: SpecParser.ParamContext):
        if self._error is not None:
            return None

        paramName: str = ctx.ID().getText()

        if paramName in self._lang_assets:
            self._report_error(
                ctx.ID().getSymbol(),
                f"Cannot use asset name '{paramName}' as param name.",
            )
            return None

        if paramName in self._all_declared_names():
            self._report_error(
                ctx.ID().getSymbol(),
                f"Name '{paramName}' has already been declared.",
            )
            return None

        # Visit the expression with _current_param set so that visitPrim can
        # detect self-references and forward references.
        self._current_param = paramName
        self.visitChildren(ctx)
        self._current_param = None

        self._declared_params.add(paramName)
        return None

    def visitPrim(self, ctx: SpecParser.PrimContext):
        if self._error is not None:
            return None

        if ctx.ID():
            name: str = ctx.ID().getText()

            if name not in self._declared_params:
                if name == self._current_param:
                    self._report_error(
                        ctx.ID().getSymbol(),
                        f"Param '{name}' cannot reference itself.",
                    )
                else:
                    self._report_error(
                        ctx.ID().getSymbol(),
                        f"'{name}' has not been declared as a param.",
                    )
                return None

        return self.visitChildren(ctx)

    def visitSubsystem(self, ctx: SpecParser.SubsystemContext):
        if self._error is not None:
            return None

        subsystemName: str = ctx.ID().getText()
        if subsystemName in self._lang_assets:
            self._report_error(
                ctx.ID().getSymbol(),
                f"Cannot use asset name '{subsystemName}' as subset name.",
            )
            return None
        if subsystemName in self._all_declared_names():
            self._report_error(
                ctx.ID().getSymbol(),
                f"Name '{subsystemName}' has already been declared.",
            )
            return None

        self._in_subsystem_context = True
        self.visitChildren(ctx)
        self._in_subsystem_context = False

        self._defined_subsystems[subsystemName] = self._subsystem_variable_types
        self._subsystem_variable_types = {}
        return None

    def visitLet(self, ctx: SpecParser.LetContext):
        if self._error is not None:
            return None

        variableName: str = ctx.variable().ID().getText()
        if variableName in self._lang_assets:
            self._report_error(
                ctx.variable().ID().getSymbol(),
                f"Cannot use asset name '{variableName}' as variable name.",
            )
            return None
        if variableName in self._all_declared_names():
            self._report_error(
                ctx.variable().ID().getSymbol(),
                f"Name '{variableName}' has already been declared.",
            )
            return None

        setType: str = self.visitAssetSet(ctx.assetSet())
        if not self._in_subsystem_context:
            self._variable_types[variableName] = setType
        else:
            self._subsystem_variable_types[variableName] = setType

        self._current_variable = variableName
        return self.visitChildren(ctx)

    def visitAssetSet(self, ctx: SpecParser.AssetSetContext) -> str:
        if self._error is not None:
            return None

        if ctx.variable():
            variableName: str = ctx.variable().ID().getText()
            types: Dict[str, str] = (
                self._variable_types
                if not self._in_subsystem_context
                else self._subsystem_variable_types
            )
            if variableName not in types:
                self._report_error(
                    ctx.variable().ID().getSymbol(),
                    f"Variable name '{variableName}' has not been declared yet.",
                )
                return None
            return types[variableName]
        elif ctx.assetInstantiation():
            self.visitAssetInstantiation(ctx.assetInstantiation())
            return ctx.assetInstantiation().ID().getText()
        elif ctx.subsystemSetAccess():
            return self._resolve_subsystem_access(ctx.subsystemSetAccess())
        else:
            raise RuntimeError("Unexpected error in SpecAnalyzer.visitAssetSet.")

    def visitAssetInstantiation(self, ctx: SpecParser.AssetInstantiationContext):
        if self._error is not None:
            return None

        assetType: str = ctx.ID().getText()
        if assetType not in self._lang_assets:
            if assetType in self._defined_subsystems:
                variableName: str = self._current_variable
                for set, type in self._defined_subsystems[assetType].items():
                    self._variable_types[f"{variableName}.{set}"] = type
            else:
                self._report_error(
                    ctx.ID().getSymbol(),
                    f"Asset '{assetType}' does not exist in {self._lang_info}",
                )
                return None
        return self.visitChildren(ctx)

    def visitConnectionRule(self, ctx: SpecParser.ConnectionRuleContext):
        if self._error is not None:
            return None

        left_type: str = self.visitAssetSet(ctx.assetSet(0))
        right_fieldname: str = ctx.associationFieldname().ID().getText()
        right_type: str = self.visitAssetSet(ctx.assetSet(1))

        if (left_type, right_fieldname, right_type) not in self._lang_associations:
            self._report_error(
                ctx.associationFieldname().ID().getSymbol(),
                f"The association with fieldname '{right_fieldname}' from asset "
                f"'{left_type}' to '{right_type}' does not exist in {self._lang_info}.",
            )
            return None
        return self.visitChildren(ctx)

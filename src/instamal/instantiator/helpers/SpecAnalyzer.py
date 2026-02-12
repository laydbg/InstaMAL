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
    """Perform semantic analysis of a Spec language file."""

    def __init__(self, lang_graph: LanguageGraph):
        self._error: Optional[AnalyzerError] = None
        self._lang_info: str = (
            f"{lang_graph.metadata['id']}, {lang_graph.metadata['version']}"
        )
        self._lang_assets: Set[str] = {asset for asset in lang_graph.assets.keys()}
        self._lang_associations: Set[Tuple[str, str, str]] = {
            (
                assoc.left_field.asset.name,
                assoc.right_field.fieldname,
                assoc.right_field.asset.name,
            )
            for assoc in lang_graph.associations
        }
        self._lang_associations.update(
            {
                (
                    assoc.right_field.asset.name,
                    assoc.left_field.fieldname,
                    assoc.left_field.asset.name,
                )
                for assoc in lang_graph.associations
            }
        )
        self._variable_types: Dict[str, str] = {}
        self._spec_ctx: SpecParser.SpecContext = None

    def analyze(self, spec_ctx: SpecParser.SpecContext) -> Optional[AnalyzerError]:
        """Analyze the specified system domain specification and return the first semantical error found or None in the case of no errors."""
        self._variable_types = {}
        self._spec_ctx = spec_ctx
        self.visit(spec_ctx)
        return self._error

    def _report_error(self, symbol: Token, description: str) -> None:
        if self._error is None:
            self._error = AnalyzerError(symbol.line, symbol.column, description)

    def visit(self, tree):
        if self._error is not None:
            return None
        return super().visit(tree)

    def visitLet(self, ctx: SpecParser.LetContext):
        variableName: str = ctx.variable().ID().getText()
        if variableName in self._lang_assets:
            self._report_error(
                ctx.variable().ID().getSymbol(),
                f"Cannot use asset name '{variableName}' as variable name.",
            )
            return None

        assetType: str = self.visit(ctx.assetSet())
        self._variable_types[variableName] = assetType

        return self.visitChildren(ctx)

    def visitAssetSet(self, ctx: SpecParser.AssetSetContext) -> str:
        if ctx.variable():
            variableName: str = ctx.variable().getText()
            if variableName not in self._variable_types:
                self._report_error(
                    ctx.variable().ID().getSymbol(),
                    f"Variable name '{variableName}' has not been declared yet.",
                )
                return None
            return self._variable_types[ctx.variable().ID().getText()]
        elif ctx.assetInstantiation():
            self.visit(ctx.assetInstantiation())
            return ctx.assetInstantiation().ID().getText()
        else:
            raise RuntimeError("Unexpexted error in SpecAnalyzer.visitAssetSet.")

    def visitAssetInstantiation(self, ctx: SpecParser.AssetInstantiationContext):
        assetType: str = ctx.ID().getText()
        if assetType not in self._lang_assets:
            self._report_error(
                ctx.ID().getSymbol(),
                f"Asset '{assetType}' does not exist in {self._lang_info}",
            )
            return None
        return self.visitChildren(ctx)

    def visitConnectionRule(self, ctx: SpecParser.ConnectionRuleContext):
        left_type: str = self.visit(ctx.assetSet(0))
        right_fieldname: str = ctx.associationFieldname().ID().getText()
        right_type: str = self.visit(ctx.assetSet(1))

        if not (left_type, right_fieldname, right_type) in self._lang_associations:
            self._report_error(
                ctx.associationFieldname().ID().getSymbol(),
                f"The association with fieldname '{right_fieldname}' from asset '{left_type}' to '{right_type}' does not exist in {self._lang_info}.",
            )
            return None

        return self.visitChildren(ctx)

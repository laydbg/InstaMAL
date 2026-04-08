# Generated from Spec.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .spec_parser import SpecParser
else:
    from spec_parser import SpecParser

# This class defines a complete generic visitor for a parse tree produced by SpecParser.

class SpecVisitor(ParseTreeVisitor):

    # Visit a parse tree produced by SpecParser#spec.
    def visitSpec(self, ctx:SpecParser.SpecContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SpecParser#param.
    def visitParam(self, ctx:SpecParser.ParamContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SpecParser#number.
    def visitNumber(self, ctx:SpecParser.NumberContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SpecParser#expr.
    def visitExpr(self, ctx:SpecParser.ExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SpecParser#sign.
    def visitSign(self, ctx:SpecParser.SignContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SpecParser#term.
    def visitTerm(self, ctx:SpecParser.TermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SpecParser#fact.
    def visitFact(self, ctx:SpecParser.FactContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SpecParser#prim.
    def visitPrim(self, ctx:SpecParser.PrimContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SpecParser#distributionSample.
    def visitDistributionSample(self, ctx:SpecParser.DistributionSampleContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SpecParser#parameters.
    def visitParameters(self, ctx:SpecParser.ParametersContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SpecParser#subsystem.
    def visitSubsystem(self, ctx:SpecParser.SubsystemContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SpecParser#subsystemSetAccess.
    def visitSubsystemSetAccess(self, ctx:SpecParser.SubsystemSetAccessContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SpecParser#let.
    def visitLet(self, ctx:SpecParser.LetContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SpecParser#variable.
    def visitVariable(self, ctx:SpecParser.VariableContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SpecParser#assetSet.
    def visitAssetSet(self, ctx:SpecParser.AssetSetContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SpecParser#namedAssetSet.
    def visitNamedAssetSet(self, ctx:SpecParser.NamedAssetSetContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SpecParser#assetInstantiation.
    def visitAssetInstantiation(self, ctx:SpecParser.AssetInstantiationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SpecParser#assetInstantiationParameters.
    def visitAssetInstantiationParameters(self, ctx:SpecParser.AssetInstantiationParametersContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SpecParser#defenseControl.
    def visitDefenseControl(self, ctx:SpecParser.DefenseControlContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SpecParser#connect.
    def visitConnect(self, ctx:SpecParser.ConnectContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SpecParser#connectionRule.
    def visitConnectionRule(self, ctx:SpecParser.ConnectionRuleContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SpecParser#associationFieldname.
    def visitAssociationFieldname(self, ctx:SpecParser.AssociationFieldnameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SpecParser#prune.
    def visitPrune(self, ctx:SpecParser.PruneContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SpecParser#pruneParameters.
    def visitPruneParameters(self, ctx:SpecParser.PruneParametersContext):
        return self.visitChildren(ctx)



del SpecParser
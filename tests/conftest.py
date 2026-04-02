"""
Shared fixtures and helpers for the InstaMal test suite.
"""

import os
import tempfile
from pathlib import Path
from typing import List

import pytest
from antlr4 import CommonTokenStream, FileStream
from maltoolbox.language import LanguageGraph

from instamal import ModelInstantiator
from instamal.instantiation.spec_analysis import (
    ProbabilisticMultiplicityAnalyzer,
    MultiplicityWarning,
)
from instamal.language import SpecLexer, SpecParser


TESTDATA_DIR = Path(__file__).resolve().parent / 'testdata'

TRAININGLANG_PATH = str(TESTDATA_DIR / 'org.mal-lang.trainingLang-1.0.0.mar')
MULTIPLICITYLANG_PATH = str(TESTDATA_DIR / 'multiplicityLang.mal')
INHERITANCELANG_PATH = str(TESTDATA_DIR / 'inheritanceLang.mal')


# Language path fixtures


@pytest.fixture(scope='session')
def trainingLang_path():
    return TRAININGLANG_PATH


@pytest.fixture(scope='session')
def multiplicityLang_path():
    return MULTIPLICITYLANG_PATH


@pytest.fixture(scope='session')
def inheritanceLang_path():
    return INHERITANCELANG_PATH


# Instantiation fixture


@pytest.fixture(scope='function')
def instantiate():
    """
    Return a helper that writes a spec string to a temp file and runs
    ModelInstantiator against the given language source.

    Usage::

        instantiate(spec, lang_path)
        instantiate(spec, lang_path, n=5)
    """

    def _instantiate(spec: str, lang_src: str, n: int = 1) -> None:
        tmp_spec_path = None
        try:
            with tempfile.NamedTemporaryFile(
                delete=False, mode='w', encoding='utf-8'
            ) as f:
                f.write(spec)
                tmp_spec_path = f.name

            with tempfile.TemporaryDirectory() as tmp_dir:
                instantiator = ModelInstantiator(
                    tmp_spec_path, lang_src, interactive=False
                )
                instantiator.instantiate(tmp_dir, n)
        finally:
            if tmp_spec_path is not None:
                os.remove(tmp_spec_path)

    return _instantiate


# Probabilistic analysis helper


def run_probabilistic_analysis(
    spec: str, lang_path: str, threshold: float = 0.9
) -> List[MultiplicityWarning]:
    """
    Run only the probabilistic multiplicity analyzer on a spec string and
    return the list of warnings. Bypasses semantic and static analysis so
    that tests can target the probabilistic analyzer in isolation.
    """
    lang_graph = LanguageGraph.load_from_file(lang_path)
    tmp_spec_path = None
    try:
        with tempfile.NamedTemporaryFile(
            delete=False, mode='w', encoding='utf-8', suffix='.spec'
        ) as f:
            f.write(spec)
            tmp_spec_path = f.name

        input_stream = FileStream(tmp_spec_path)
        lexer = SpecLexer(input_stream)
        stream = CommonTokenStream(lexer)
        parser = SpecParser(stream)
        spec_ctx = parser.spec()

        analyzer = ProbabilisticMultiplicityAnalyzer(lang_graph, threshold=threshold)
        return analyzer.analyze(spec_ctx)
    finally:
        if tmp_spec_path is not None:
            os.remove(tmp_spec_path)


def warnings_for(
    warnings: List[MultiplicityWarning], asset_type: str, fieldname: str
) -> List[MultiplicityWarning]:
    """Filter a warnings list to a specific (asset_type, fieldname) pair."""
    return [
        w for w in warnings if w.asset_type == asset_type and w.fieldname == fieldname
    ]

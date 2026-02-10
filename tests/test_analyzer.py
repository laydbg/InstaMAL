from typing import Optional
import pytest

from antlr4 import InputStream, CommonTokenStream
from maltoolbox.language import LanguageGraph
from pathlib import Path

from instamal.instantiator.helpers import (
    SpecLexer,
    SpecParser,
    AnalyzerError,
    SpecAnalyzer,
)


TRAININGLANG_PATH = (
    f"{Path(__file__).resolve().parent}/org.mal-lang.trainingLang-1.0.0.mar"
)


@pytest.fixture(scope="function")
def analyze():
    def _analyze(spec: str, lang_src: str) -> Optional[AnalyzerError]:
        lexer = SpecLexer(InputStream(spec))
        tokens = CommonTokenStream(lexer)
        parser = SpecParser(tokens)
        tree = parser.spec()

        lang_graph: LanguageGraph = LanguageGraph.load_from_file(lang_src)

        analyzer = SpecAnalyzer(lang_graph)
        return analyzer.analyze(tree)

    return _analyze


def test_error_on_variable_not_declared(analyze):
    spec: str = """
        let networks = Network(2);

        connect {
            1.0: networks --> [toNetworks] netwrks; // <-
        }
        """
    e = analyze(spec, TRAININGLANG_PATH)
    assert e is not None


def test_error_on_invalid_asset(analyze):
    spec: str = """
        let users = Useer(); // <-
        """
    e = analyze(spec, TRAININGLANG_PATH)
    assert e is not None


def test_error_on_invalid_association(analyze):
    spec: str = """
        let hosts = Host(10);
        let users = User(TruncatedNormal(15, 4));

        connect {
            0.5: users --> [someNonexistantAssoc] hosts; // <-
        }
        """
    e = analyze(spec, TRAININGLANG_PATH)
    assert e is not None


def test_error_on_asset_as_variable_name(analyze):
    spec: str = """
        let Data = Network(2); // <-
        """
    e = analyze(spec, TRAININGLANG_PATH)
    assert e is not None


# def test_error_on_(analyze):
#     spec: str = """
#         let networks = Network(2);
#         let hosts = Host(10);
#         let users = User(TruncatedNormal(15, 4));
#         let data = Data(8+Uniform(7-9, 2*2));
#
#         connect {
#             1.0: networks --> [toNetworks] networks;
#             0.5: hosts --> [networks] networks;
#             0.5: users --> [hosts] hosts;
#             0.7: data --> [hosts] hosts;
#         }
#         """
#     assert analyze(spec, TRAININGLANG_PATH) is not None

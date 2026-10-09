"""
Tests for the `ligase` command line: model selection, parsing, helpers.
No network or model calls.
"""

import pytest

from ligase import cli

MODEL_ENV = [
    "GLIMMER_30B_BACKEND",
    "GLIMMER_30B_MODEL",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "LIGASE_BASE_URL",
    "LIGASE_MODEL",
]


@pytest.fixture
def clean_env(monkeypatch):
    for name in MODEL_ENV:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_auto_prefers_private_host(clean_env):
    clean_env.setenv("GLIMMER_30B_BACKEND", "http://host:1/v1")
    clean_env.setenv("OPENAI_API_KEY", "sk-test")
    cfg = cli.resolve_model("auto")
    assert cfg["name"] == "glimmer"
    assert cfg["base_url"] == "http://host:1/v1"


def test_auto_falls_back_to_openai(clean_env):
    clean_env.setenv("OPENAI_API_KEY", "sk-test")
    assert cli.resolve_model("auto")["name"] == "openai"


def test_placeholder_key_counts_as_unset(clean_env):
    clean_env.setenv("OPENAI_API_KEY", "your_openai_api_key_here")
    with pytest.raises(cli.ConfigError, match="No model configured"):
        cli.resolve_model("auto")


def test_luna_is_alias_for_openai(clean_env):
    clean_env.setenv("OPENAI_API_KEY", "sk-test")
    assert cli.resolve_model("luna")["name"] == "openai"


def test_missing_endpoint_names_the_variable(clean_env):
    with pytest.raises(cli.ConfigError, match="GLIMMER_30B_BACKEND"):
        cli.resolve_model("glimmer")


def test_custom_requires_model_name(clean_env):
    clean_env.setenv("LIGASE_BASE_URL", "http://localhost:8000/v1")
    with pytest.raises(cli.ConfigError, match="LIGASE_MODEL"):
        cli.resolve_model("custom")


def test_escape_inline_stars_keeps_allele_names():
    assert cli.escape_inline_stars("APOE*4 and APOE*3") == "APOE\\*4 and APOE\\*3"
    assert cli.escape_inline_stars("**bold** and * bullet") == "**bold** and * bullet"


def test_parser_commands():
    parser = cli.build_parser()
    args = parser.parse_args(["run", "What is TP53?", "--ad", "--max-iterations", "4"])
    assert (args.cmd, args.question, args.ad, args.max_iterations) == ("run", "What is TP53?", True, 4)
    assert parser.parse_args(["example", "apoe4"]).name == "apoe4"
    assert parser.parse_args([]).cmd is None  # bare `ligase` opens the prompt


def test_examples_are_complete():
    for ex in cli.EXAMPLES.values():
        assert ex["question"] and ex["title"] and ex["max_iterations"] > 0


def test_examples_command_needs_no_model(clean_env, capsys):
    assert cli.main(["examples"]) == 0
    assert "apoe4" in capsys.readouterr().out

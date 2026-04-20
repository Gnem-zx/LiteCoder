"""Tests for core modules: config, context, session, imports."""

import os
import pathlib
import tempfile

from litecoder import Agent, LLM, Config, ALL_TOOLS, __version__
from litecoder.context import ContextManager, estimate_tokens
from litecoder.cli import _resolve_session_save_id
from litecoder.session import save_session, load_session, list_sessions
from litecoder.rules import add_rule, load_rules, delete_rule, clear_rules, render_rules_prompt
from litecoder.tools import get_tool


def test_version():
    assert __version__ == "0.2.0"


def test_public_api_exports():
    """Users should be able to import key classes from the top-level package."""
    assert Agent is not None
    assert LLM is not None
    assert Config is not None
    assert len(ALL_TOOLS) == 8


def test_config_from_env():
    os.environ["CORECODER_MODEL"] = "test-model"
    c = Config.from_env()
    assert c.model == "test-model"
    del os.environ["CORECODER_MODEL"]


def test_config_defaults():
    # temporarily clear relevant env vars
    saved = {}
    for k in [
        "LITECODER_MODEL",
        "CORECODER_MODEL",
        "LITECODER_MAX_TOKENS",
        "CORECODER_MAX_TOKENS",
        "LITECODER_TEMPERATURE",
        "CORECODER_TEMPERATURE",
    ]:
        if k in os.environ:
            saved[k] = os.environ.pop(k)

    c = Config.from_env()
    assert c.model == "gpt-4o"
    assert c.max_tokens == 4096
    assert c.temperature == 0.0

    os.environ.update(saved)


# --- Context ---

def test_estimate_tokens():
    msgs = [{"role": "user", "content": "hello world"}]
    t = estimate_tokens(msgs)
    assert t > 0
    assert t < 100


def test_context_snip():
    ctx = ContextManager(max_tokens=3000)
    msgs = [
        {"role": "tool", "tool_call_id": "t1", "content": "x\n" * 1000},
    ]
    before = estimate_tokens(msgs)
    ctx._snip_tool_outputs(msgs)
    after = estimate_tokens(msgs)
    assert after < before


def test_context_externalize_huge_tool_output():
    huge = "line\n" * 5000  # > 12000 chars, should be externalized to local file

    with tempfile.TemporaryDirectory() as tmp:
        old_workdir = os.environ.get("LITECODER_WORKDIR")
        os.environ["LITECODER_WORKDIR"] = tmp
        try:
            ctx = ContextManager(max_tokens=3000)
            msgs = [
                {"role": "tool", "tool_call_id": "t_huge", "content": huge},
            ]
            changed = ctx._snip_tool_outputs(msgs)
            assert changed is True

            replaced = msgs[0]["content"]
            assert "[tool output externalized]" in replaced
            assert "Full output saved to:" in replaced

            path_line = [ln for ln in replaced.splitlines() if ln.startswith("Full output saved to:")][0]
            saved_path = path_line.split(":", 1)[1].strip()
            full_path = pathlib.Path(saved_path)
            if not full_path.is_absolute():
                full_path = pathlib.Path(tmp) / full_path

            assert full_path.exists()
            assert full_path.read_text(encoding="utf-8") == huge
        finally:
            if old_workdir is None:
                os.environ.pop("LITECODER_WORKDIR", None)
            else:
                os.environ["LITECODER_WORKDIR"] = old_workdir


def test_context_compress():
    ctx = ContextManager(max_tokens=2000)
    msgs = []
    for i in range(20):
        msgs.append({"role": "user", "content": f"msg {i} " + "a" * 200})
        msgs.append({"role": "tool", "tool_call_id": f"t{i}", "content": "b" * 2000})
    before = estimate_tokens(msgs)
    ctx.maybe_compress(msgs, None)
    after = estimate_tokens(msgs)
    assert after < before
    assert len(msgs) < 40  # should be compressed


# --- Session ---

def test_session_save_load():
    msgs = [{"role": "user", "content": "test message"}]
    with tempfile.TemporaryDirectory() as tmp:
        sid = save_session(msgs, "test-model", "pytest_test_session", workdir=tmp)
        assert sid == "pytest_test_session"
        loaded = load_session("pytest_test_session", workdir=tmp)
        assert loaded is not None
        assert loaded[0] == msgs
        assert loaded[1] == "test-model"
        # cleanup
        pathlib.Path(tmp).joinpath(".litecoder/sessions/pytest_test_session.json").unlink()


def test_session_not_found():
    with tempfile.TemporaryDirectory() as tmp:
        assert load_session("nonexistent_session_id", workdir=tmp) is None


def test_list_sessions():
    with tempfile.TemporaryDirectory() as tmp:
        sessions = list_sessions(workdir=tmp)
        assert isinstance(sessions, list)


def test_resolve_session_save_id_priority():
    assert _resolve_session_save_id("current_sid", None) == "current_sid"
    assert _resolve_session_save_id("current_sid", "explicit_sid") == "explicit_sid"
    assert _resolve_session_save_id(None, None) is None


def test_rules_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        add_rule(tmp, "Always write tests for bug fixes")
        add_rule(tmp, "Prefer minimal changes")
        rules = load_rules(tmp)
        assert len(rules) == 2
        assert "Always write tests" in rules[0]

        ok, left = delete_rule(tmp, 1)
        assert ok is True
        assert len(left) == 1

        prompt_rules = render_rules_prompt(tmp)
        assert "1." in prompt_rules

        clear_rules(tmp)
        assert load_rules(tmp) == []




# --- Cost estimation ---

def test_cost_estimation_known_model():
    from litecoder.llm import LLM
    llm = LLM.__new__(LLM)
    llm.model = "gpt-5.4"
    llm.total_prompt_tokens = 1_000_000
    llm.total_completion_tokens = 500_000
    cost = llm.estimated_cost
    assert cost is not None
    assert cost == 2.5 + 7.5  # $2.5/M in + $15/M out * 0.5M

def test_cost_estimation_unknown_model():
    from litecoder.llm import LLM
    llm = LLM.__new__(LLM)
    llm.model = "some-custom-model"
    llm.total_prompt_tokens = 1000
    llm.total_completion_tokens = 500
    assert llm.estimated_cost is None


# --- Changed files tracking ---

def test_edit_tracks_changed_files():
    from litecoder.tools.edit import _changed_files
    _changed_files.clear()
    edit = get_tool("edit_file")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("aaa\nbbb\n")
        f.flush()
        edit.execute(file_path=f.name, old_string="aaa", new_string="zzz")
        assert any(f.name in p for p in _changed_files)
        os.unlink(f.name)
    _changed_files.clear()


def test_write_tracks_changed_files():
    from litecoder.tools.edit import _changed_files
    _changed_files.clear()
    write = get_tool("write_file")
    path = tempfile.mktemp(suffix=".txt")
    write.execute(file_path=path, content="tracked\n")
    assert any("tracked" not in p and path.split("/")[-1] in p for p in _changed_files) or len(_changed_files) > 0
    os.unlink(path)
    _changed_files.clear()

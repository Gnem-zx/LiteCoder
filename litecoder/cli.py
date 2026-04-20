"""LiteCoder CLI entry.

Responsibilities:
1) interactive REPL mode
2) argument/env override management
3) session resume/save/list
4) bilingual terminal text (EN/ZH)
5) first-run setup and local metadata under .litecoder/
"""

import sys
import os
import argparse
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.application import Application
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.key_binding import KeyBindings

from .agent import Agent
from .llm import LLM
from .config import Config
from .session import save_session, load_session, list_sessions
from .i18n import normalize_lang, tr
from . import __version__

console = Console()


_CUSTOM = "__custom__"


def _parse_args():
    """Parse CLI arguments."""
    p = argparse.ArgumentParser(
        prog="litecoder",
        description="Minimal AI coding agent. Works with any OpenAI-compatible LLM.",
    )
    p.add_argument("-m", "--model", help="Model name (default: $LITECODER_MODEL or $CORECODER_MODEL)")
    p.add_argument("--base-url", help="API base URL (default: $OPENAI_BASE_URL / $LITECODER_BASE_URL)")
    p.add_argument("--api-key", help="API key (default: $OPENAI_API_KEY / $LITECODER_API_KEY)")
    p.add_argument("--lang", choices=["en", "zh"], help="CLI language: en or zh (default: en)")
    p.add_argument("-C", "--workdir", help="Working directory (default: current directory)")
    p.add_argument("-r", "--resume", metavar="ID", help="Resume a saved session")
    p.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    return p.parse_args()


def _resolve_workdir(raw: str | None) -> Path:
    path = Path(raw).expanduser().resolve() if raw else Path.cwd().resolve()
    if not path.exists() or not path.is_dir():
        raise ValueError(str(path))
    return path


def _litecoder_dir(workdir: Path) -> Path:
    return workdir / ".litecoder"


def _env_path(workdir: Path) -> Path:
    return workdir / ".env"


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _needs_first_setup(workdir: Path) -> bool:
    env = _parse_env_file(_env_path(workdir))
    has_model = bool(env.get("LITECODER_MODEL") or env.get("CORECODER_MODEL"))
    has_base = bool(env.get("LITECODER_BASE_URL") or env.get("OPENAI_BASE_URL") or env.get("CORECODER_BASE_URL"))
    has_lang = bool(
        env.get("LITECODER_LANG")
        or env.get("LITECODER_LANGUAGE")
        or env.get("CORECODER_LANG")
        or env.get("CORECODER_LANGUAGE")
        or env.get("LANGUAGE")
    )
    has_key = bool(
        env.get("LITECODER_API_KEY")
        or env.get("CORECODER_API_KEY")
        or env.get("OPENAI_API_KEY")
        or env.get("DEEPSEEK_API_KEY")
    )
    return not (has_model and has_base and has_lang and has_key)


def _env_quote(value: str) -> str:
    if not value:
        return ""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    if any(ch.isspace() for ch in value) or "#" in value:
        return f'"{escaped}"'
    return escaped


def _upsert_env(workdir: Path, updates: dict[str, str]):
    env_file = _env_path(workdir)
    original_lines = []
    if env_file.exists():
        original_lines = env_file.read_text(encoding="utf-8", errors="ignore").splitlines()

    new_lines: list[str] = []
    applied_keys: set[str] = set()

    for line in original_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue

        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            new_lines.append(f"{key}={_env_quote(updates[key])}")
            applied_keys.add(key)
        else:
            new_lines.append(line)

    if not new_lines:
        new_lines.append("# LiteCoder initialization")

    if new_lines and new_lines[-1].strip():
        new_lines.append("")

    for key, value in updates.items():
        if key not in applied_keys:
            new_lines.append(f"{key}={_env_quote(value)}")

    env_file.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")


def _mask_secret(secret: str, keep: int = 4) -> str:
    if not secret:
        return ""
    if len(secret) <= keep:
        return "*" * len(secret)
    return "*" * (len(secret) - keep) + secret[-keep:]


def _choice_dialog(lang: str, title_key: str, options: list[tuple[str, str]], default: str) -> str:
    current_index = 0
    for i, (value, _) in enumerate(options):
        if value == default:
            current_index = i
            break

    def _render():
        fragments = [
            ("class:title", f"{tr(lang, 'setup_title')}\n"),
            ("class:desc", f"{tr(lang, title_key)}\n"),
            ("class:desc", f"{tr(lang, 'setup_choice_hint')}\n\n"),
        ]
        for idx, (_, label) in enumerate(options):
            prefix = ">" if idx == current_index else " "
            style = "class:selected" if idx == current_index else "class:item"
            fragments.append((style, f"{prefix} {label}\n"))
        return fragments

    kb = KeyBindings()

    @kb.add("up")
    def _up(event):
        nonlocal current_index
        current_index = (current_index - 1) % len(options)
        event.app.invalidate()

    @kb.add("down")
    def _down(event):
        nonlocal current_index
        current_index = (current_index + 1) % len(options)
        event.app.invalidate()

    @kb.add("enter")
    def _enter(event):
        event.app.exit(result=options[current_index][0])

    @kb.add("c-c")
    def _cancel(event):
        event.app.exit(result=options[current_index][0])

    app = Application(
        layout=Layout(Window(content=FormattedTextControl(_render), always_hide_cursor=True)),
        key_bindings=kb,
        full_screen=False,
    )
    selected = app.run()
    return selected if selected is not None else options[current_index][0]


def _custom_input(lang: str, prompt_key: str, fallback: str, is_password: bool = False) -> str:
    prompt_text = f"{tr(lang, prompt_key)} "
    default_value = "" if is_password else fallback
    value = pt_prompt(prompt_text, default=default_value, is_password=is_password).strip()
    if not value:
        return fallback
    return value


def _common_workdirs(seed: Path, lang: str) -> list[tuple[str, str]]:
    home = Path.home().resolve()
    items = [
        (str(seed), tr(lang, "workdir_current", path=str(seed))),
        (str(seed.parent), tr(lang, "workdir_parent", path=str(seed.parent))),
        (str(home), tr(lang, "workdir_home", path=str(home))),
        (str(home / "Documents"), tr(lang, "workdir_docs", path=str(home / "Documents"))),
        (str(home / "Desktop"), tr(lang, "workdir_desktop", path=str(home / "Desktop"))),
    ]

    seen: set[str] = set()
    options: list[tuple[str, str]] = []
    for value, label in items:
        if value in seen:
            continue
        seen.add(value)
        options.append((value, label))

    options.append((_CUSTOM, tr(lang, "setup_custom_label")))
    return options


def _common_api_keys(default_key: str, lang: str) -> list[tuple[str, str]]:
    options: list[tuple[str, str]] = []
    if default_key:
        options.append((default_key, tr(lang, "api_key_from_env", masked=_mask_secret(default_key))))
    options.append(("ollama", tr(lang, "api_key_ollama")))
    options.append((_CUSTOM, tr(lang, "setup_custom_label")))
    return options


def _first_setup_wizard(initial_workdir: Path, defaults: Config, preferred_lang: str) -> tuple[Path, str, str, str, str]:
    lang = normalize_lang(preferred_lang)
    console.print(f"\n{tr(lang, 'setup_title')}")
    console.print(tr(lang, "setup_intro"))
    console.print()

    # 1) workdir
    workdir_default = str(initial_workdir)
    workdir_choice = _choice_dialog(lang, "setup_choose_workdir", _common_workdirs(initial_workdir, lang), workdir_default)
    if workdir_choice == _CUSTOM:
        workdir_choice = _custom_input(lang, "setup_custom_workdir", workdir_default)
    selected_workdir = Path(workdir_choice).expanduser().resolve()
    selected_workdir.mkdir(parents=True, exist_ok=True)

    # 2) url
    base_default = defaults.base_url or "https://api.openai.com/v1"
    url_choices = [
        ("https://api.openai.com/v1", tr(lang, "url_openai")),
        ("https://api.deepseek.com", tr(lang, "url_deepseek")),
        ("https://dashscope.aliyuncs.com/compatible-mode/v1", tr(lang, "url_dashscope")),
        ("https://api.moonshot.ai/v1", tr(lang, "url_moonshot")),
        ("http://localhost:11434/v1", tr(lang, "url_ollama")),
        (_CUSTOM, tr(lang, "setup_custom_label")),
    ]
    url_choice = _choice_dialog(lang, "setup_choose_url", url_choices, base_default)
    if url_choice == _CUSTOM:
        url_choice = _custom_input(lang, "setup_custom_url", base_default)

    # 3) model
    model_default = defaults.model or "gpt-4o"
    model_choices = [
        ("gpt-4o", "gpt-4o"),
        ("gpt-5.4", "gpt-5.4"),
        ("deepseek-chat", "deepseek-chat"),
        ("qwen-max", "qwen-max"),
        ("kimi-k2.5", "kimi-k2.5"),
        ("qwen2.5-coder", "qwen2.5-coder"),
        (_CUSTOM, tr(lang, "setup_custom_label")),
    ]
    model_choice = _choice_dialog(lang, "setup_choose_model", model_choices, model_default)
    if model_choice == _CUSTOM:
        model_choice = _custom_input(lang, "setup_custom_model", model_default)

    # 4) language,只能选英文或中文
    lang_default = normalize_lang(defaults.language or lang)
    lang_choices = [
        ("en", tr(lang, "lang_en")),
        ("zh", tr(lang, "lang_zh"))
    ]
    final_lang = _choice_dialog(lang, "setup_choose_language", lang_choices, lang_default)

    # 5) api key
    key_default = defaults.api_key or ""
    key_choice = _choice_dialog(
        final_lang,
        "setup_choose_apikey",
        _common_api_keys(key_default, final_lang),
        key_default if key_default else "ollama",
    )
    if key_choice == _CUSTOM:
        key_choice = _custom_input(final_lang, "setup_custom_apikey", "", is_password=True)

    # Ensure API key is not empty after setup.
    while not key_choice:
        key_choice = _custom_input(final_lang, "setup_custom_apikey", "", is_password=True)

    # 保存选择到 .env 文件，方便后续自动加载和 CLI 参数覆盖。
    _upsert_env(
        selected_workdir,
        {
            "LITECODER_WORKDIR": str(selected_workdir),
            "LITECODER_BASE_URL": url_choice,
            "LITECODER_MODEL": model_choice, 
            "LITECODER_LANG": final_lang,
            "LITECODER_API_KEY": key_choice,
        },
    )
    console.print(tr(final_lang, "setup_done"))
    return selected_workdir, model_choice, url_choice, final_lang, key_choice


def main():
    """Main CLI entry."""
    args = _parse_args()

    try:
        bootstrap_workdir = _resolve_workdir(args.workdir)
    except ValueError as e:
        console.print(tr("en", "invalid_workdir", path=str(e)))
        sys.exit(1)

    bootstrap_config = Config.from_env(start_dir=bootstrap_workdir)
    bootstrap_lang = normalize_lang(args.lang or bootstrap_config.language)

    if _needs_first_setup(bootstrap_workdir):
        workdir, _, _, _, _ = _first_setup_wizard(bootstrap_workdir, bootstrap_config, bootstrap_lang)
    else:
        workdir = bootstrap_workdir

    # Align cwd with selected workspace so tools and .env resolve consistently.
    os.chdir(workdir)
    _litecoder_dir(workdir).mkdir(parents=True, exist_ok=True)

    # Load env first, then CLI overrides.
    config = Config.from_env(start_dir=workdir)

    if args.model:
        config.model = args.model
    if args.base_url:
        config.base_url = args.base_url
    if args.api_key:
        config.api_key = args.api_key
    if args.lang:
        config.language = normalize_lang(args.lang)

    lang = normalize_lang(config.language)

    if not config.api_key:
        console.print(tr(lang, "missing_api_key"))
        console.print(tr(lang, "missing_api_key_help"))
        sys.exit(1)

    llm = LLM(
        model=config.model,
        api_key=config.api_key,
        base_url=config.base_url,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )

    agent = Agent(llm=llm, max_context_tokens=config.max_context_tokens)

    if args.resume:
        loaded = load_session(args.resume, workdir=workdir)
        if loaded:
            agent.messages, loaded_model = loaded
            if not args.model:
                agent.llm.model = loaded_model
                config.model = loaded_model
            console.print(tr(lang, "resumed_session", sid=args.resume, model=agent.llm.model))
        else:
            console.print(tr(lang, "resume_not_found", sid=args.resume))
            sys.exit(1)

    _repl(agent, config, workdir)


def _command_completer() -> WordCompleter:
    """关键字补全器，提升用户输入体验。"""
    words = [
        "/help",
        "/reset",
        "/model",
        "/tokens",
        "/compact",
        "/diff",
        "/save",
        "/sessions",
        "quit",
        "exit",
        "gpt-4o",
        "gpt-5.4",
        "deepseek-chat",
        "qwen-max",
        "kimi-k2.5",
    ]
    return WordCompleter(words, ignore_case=True)


def _repl(agent: Agent, config: Config, workdir: Path):
    """Interactive REPL loop."""
    lang = normalize_lang(config.language)
    base_info = f"  Base: [dim]{config.base_url}[/dim]" if config.base_url else ""
    console.print(Panel(
        tr(
            lang,
            "banner",
            version=__version__,
            model=config.model,
            base=base_info,
            workdir=str(workdir),
        ),
        border_style="blue",
    ))

    # Keep history local to the selected workspace.
    hist_path = _litecoder_dir(workdir) / "history"
    history = FileHistory(str(hist_path))

    kb = KeyBindings()

    @kb.add("enter")
    def _submit(event):
        event.current_buffer.validate_and_handle()

    @kb.add("escape", "enter")
    def _newline(event):
        event.current_buffer.insert_text("\n")

    completer = _command_completer()

    while True:
        lang = normalize_lang(config.language)
        try:
            user_input = pt_prompt(
                tr(lang, "user_prompt"),
                history=history,
                multiline=True,
                key_bindings=kb,
                prompt_continuation="...  ",
                completer=completer,
                complete_while_typing=True,
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print(f"\n{tr(lang, 'bye')}")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "/quit", "/exit"):
            break
        if user_input == "/help":
            _show_help(lang)
            continue
        if user_input == "/reset": # 重置对话历史，但不清除系统信息，方便快速切换话题或调试。
            agent.reset()
            console.print(tr(lang, "conversation_reset"))
            continue
        if user_input == "/tokens":
            p = agent.llm.total_prompt_tokens
            c = agent.llm.total_completion_tokens
            line = tr(lang, "tokens", prompt=p, completion=c, total=p + c)
            cost = agent.llm.estimated_cost
            if cost is not None:
                line += f"  (~${cost:.4f})"
            console.print(line)
            continue
        if user_input == "/model" or user_input.startswith("/model "): 
            new_model = user_input[7:].strip() if user_input.startswith("/model ") else ""
            if new_model:
                agent.llm.model = new_model
                config.model = new_model
                _upsert_env(workdir, {"LITECODER_MODEL": new_model})
                console.print(tr(lang, "switched_model", model=new_model))
            else:
                console.print(tr(lang, "current_model", model=config.model))
            continue
        if user_input == "/compact":
            from .context import estimate_tokens

            before = estimate_tokens(agent.messages)
            compressed = agent.context.maybe_compress(agent.messages, agent.llm)
            after = estimate_tokens(agent.messages)
            if compressed:
                console.print(tr(lang, "compressed", before=before, after=after, messages=len(agent.messages)))
            else:
                console.print(tr(lang, "nothing_to_compress", before=before, messages=len(agent.messages)))
            continue
        if user_input == "/save": 
            sid = save_session(agent.messages, config.model, workdir=workdir)
            console.print(tr(lang, "session_saved", sid=sid))
            console.print(tr(lang, "resume_hint", workdir=str(workdir), sid=sid))
            continue
        if user_input == "/diff": 
            from .tools.edit import _changed_files

            if not _changed_files:
                console.print(tr(lang, "no_files_modified"))
            else:
                console.print(tr(lang, "files_modified", count=len(_changed_files)))
                for f in sorted(_changed_files):
                    console.print(f"  [cyan]{f}[/cyan]")
            continue
        if user_input == "/sessions": # 列出已保存的会话，方便用户查看和恢复之前的对话历史。
            sessions = list_sessions(workdir=workdir)
            if not sessions:
                console.print(tr(lang, "no_saved_sessions"))
            else:
                for s in sessions:
                    console.print(f"  [cyan]{s['id']}[/cyan] ({s['model']}, {s['saved_at']}) {s['preview']}")
            continue

        streamed: list[str] = []

        def on_token(tok):
            streamed.append(tok)
            print(tok, end="", flush=True)

        def on_tool(name, kwargs):
            console.print(f"\n[dim]> {name}({_brief(kwargs)})[/dim]")

        try:
            response = agent.chat(user_input, on_token=on_token, on_tool=on_tool)
            if streamed:
                print()
            else:
                console.print(Markdown(response))
        except KeyboardInterrupt:
            console.print(f"\n{tr(lang, 'interrupted')}")
        except Exception as e:
            console.print(f"\n{tr(lang, 'error', error=e)}")


def _show_help(lang: str):
    """Show built-in commands and input shortcuts."""
    console.print(Panel(
        tr(lang, "help_body"),
        title=tr(lang, "help_title"),
        border_style="dim",
    ))


def _brief(kwargs: dict, maxlen: int = 80) -> str:
    """Convert tool kwargs to a compact single-line preview."""
    s = ", ".join(f"{k}={repr(v)[:40]}" for k, v in kwargs.items())
    return s[:maxlen] + ("..." if len(s) > maxlen else "")

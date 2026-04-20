"""Persistent system rules management.

Rules are stored under <workdir>/.litecoder/rules.txt and injected into every
system prompt. This gives users a stable, local policy layer.
"""

from pathlib import Path


def _litecoder_dir(workdir: str | Path) -> Path:
    return Path(workdir).expanduser().resolve() / ".litecoder"


def _rules_path(workdir: str | Path) -> Path:
    return _litecoder_dir(workdir) / "rules.txt"


def load_rules(workdir: str | Path) -> list[str]:
    """Load all persisted rules (one rule per line)."""
    path = _rules_path(workdir)
    if not path.exists():
        return []

    rules: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        rules.append(line)
    return rules


def save_rules(workdir: str | Path, rules: list[str]) -> None:
    """Persist rules as UTF-8 text, one rule per line."""
    path = _rules_path(workdir)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(r.strip() for r in rules if r.strip())
    path.write_text((content + "\n") if content else "", encoding="utf-8")


def add_rule(workdir: str | Path, rule: str) -> list[str]:
    """Append a rule and return the updated rule list."""
    rules = load_rules(workdir)
    value = rule.strip()
    if value:
        rules.append(value)
    save_rules(workdir, rules)
    return rules


def delete_rule(workdir: str | Path, index_1based: int) -> tuple[bool, list[str]]:
    """Delete a rule by 1-based index."""
    rules = load_rules(workdir)
    idx = index_1based - 1
    if idx < 0 or idx >= len(rules):
        return False, rules
    rules.pop(idx)
    save_rules(workdir, rules)
    return True, rules


def clear_rules(workdir: str | Path) -> None:
    """Clear all persisted rules."""
    save_rules(workdir, [])


def render_rules_prompt(workdir: str | Path) -> str:
    """Render rules to a prompt-friendly numbered list."""
    rules = load_rules(workdir)
    if not rules:
        return ""
    lines = [f"{i + 1}. {r}" for i, r in enumerate(rules)]
    return "\n".join(lines)

"""Session persistence - save and resume conversations.

Claude Code maintains session state via QueryEngine (1295 lines).
CoreCoder distills this to: JSON dump of messages + model config.
"""

import json
import time
from pathlib import Path


def _read_json_text_with_fallback(path: Path) -> str:
    """Read JSON text with UTF-8 first, then GBK for backward compatibility."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="gbk")
        except UnicodeDecodeError:
            return path.read_text(encoding="utf-8", errors="replace")


def _sessions_dir(workdir: str | Path | None = None) -> Path:
    """Resolve session directory under <workdir>/.litecoder/sessions."""
    base = Path(workdir).expanduser().resolve() if workdir else Path.cwd().resolve()
    return base / ".litecoder" / "sessions"


def save_session(
    messages: list[dict],
    model: str,
    session_id: str | None = None,
    workdir: str | Path | None = None,
) -> str:
    """Save conversation to disk. Returns the session ID."""
    sessions_dir = _sessions_dir(workdir)
    sessions_dir.mkdir(parents=True, exist_ok=True)

    if not session_id:
        session_id = f"session_{int(time.time())}"

    data = {
        "id": session_id,
        "model": model,
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "messages": messages,
    }

    path = sessions_dir / f"{session_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return session_id


def load_session(session_id: str, workdir: str | Path | None = None) -> tuple[list[dict], str] | None:
    """Load a saved session. Returns (messages, model) or None."""
    path = _sessions_dir(workdir) / f"{session_id}.json"
    if not path.exists():
        return None

    data = json.loads(_read_json_text_with_fallback(path))
    return data["messages"], data["model"]


def list_sessions(workdir: str | Path | None = None) -> list[dict]:
    """List available sessions, newest first."""
    sessions_dir = _sessions_dir(workdir)
    if not sessions_dir.exists():
        return []

    sessions = []
    for f in sorted(sessions_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(_read_json_text_with_fallback(f))
            # grab first user message as preview
            preview = ""
            for m in data.get("messages", []):
                if m.get("role") == "user" and m.get("content"):
                    preview = m["content"][:80]
                    break
            sessions.append({
                "id": data.get("id", f.stem),
                "model": data.get("model", "?"),
                "saved_at": data.get("saved_at", "?"),
                "preview": preview,
            })
        except (json.JSONDecodeError, KeyError):
            continue

    return sessions[:20]  # cap at 20

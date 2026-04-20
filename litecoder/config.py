"""Configuration - env vars and defaults."""

import os
from dataclasses import dataclass
from pathlib import Path

from .i18n import normalize_lang


def _load_dotenv(start_dir: str | Path | None = None):
    """Load .env from working dir, walking up to home dir. No-op if python-dotenv missing."""
    try:
        from dotenv import load_dotenv
        # search working dir first, then parent dirs up to ~
        root = Path(start_dir).expanduser().resolve() if start_dir else Path.cwd()
        env_path = root / ".env"
        if not env_path.exists():
            cur = root
            home = Path.home().resolve()
            while cur != cur.parent:
                candidate = cur / ".env"
                if candidate.exists():
                    env_path = candidate
                    break
                if cur == home:
                    break
                cur = cur.parent

        if env_path.exists():
            load_dotenv(env_path, override=False)
    except ImportError:
        pass  # python-dotenv not installed, silently skip


@dataclass
class Config:
    model: str = "gpt-4o"
    api_key: str = ""
    base_url: str | None = None
    language: str = "en"
    max_tokens: int = 8000
    temperature: float = 0.0
    max_context_tokens: int = 128_000

    @classmethod
    def from_env(cls, start_dir: str | Path | None = None) -> "Config":
        # load .env if present (won't override existing env vars)
        _load_dotenv(start_dir)
        # pick up common env vars automatically
        api_key = (
            os.getenv("LITECODER_API_KEY")
            or ""
        )

        model = (
            os.getenv("LITECODER_MODEL")
            or "gpt-4o"
        )

        base_url = (
            os.getenv("LITECODER_BASE_URL")
        )

        language = normalize_lang(
            os.getenv("LITECODER_LANG")
        )

        return cls(
            model=model,
            api_key=api_key,
            base_url=base_url,
            language=language,
            max_tokens=int(os.getenv("LITECODER_MAX_TOKENS" , "8000") ),
            temperature=float(os.getenv("LITECODER_TEMPERATURE" , "0")),
            max_context_tokens=int(os.getenv("LITECODER_MAX_CONTEXT" , "128000")),
        )

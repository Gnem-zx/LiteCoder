"""CoreCoder - Minimal AI coding agent inspired by Claude Code's architecture."""

__version__ = "0.1.0"

from litecoder.agent import Agent
from litecoder.llm import LLM
from litecoder.config import Config
from litecoder.tools import ALL_TOOLS

__all__ = ["Agent", "LLM", "Config", "ALL_TOOLS", "__version__"]

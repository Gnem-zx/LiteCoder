# LiteCoder

[English](README.md) | [中文](README_zh.md)

> This project is a simplified implementation created by the author after studying Claude Code source architecture on an open-source project. The goal is to keep the high-value agent capabilities while removing heavy engineering overhead, so the codebase is easier to read, modify, and extend.

LiteCoder is a lightweight terminal AI coding assistant. It combines common agent coding workflows (read files, edit files, run commands, and save sessions) into a practical local CLI tool.

## What This Project Does

- Provides an interactive REPL for continuous coding conversations.
- Includes built-in tools: `read_file`, `edit_file`, `write_file`, `bash`, `glob`, `grep`, and `agent`.
- Supports session persistence: save, restore, and switch sessions under `.litecoder/`.
- Uses context compression to control token growth in long chats.
- Supports persistent rules via `/rule`, automatically injected into system prompts.
- Supports Chinese and English interface modes.

## Installation and Quick Start

### 1) Install

With `uv` (recommended):

```bash
uv pip install -e .
```

Or with pip:

```bash
pip install -e .
```

### 2) Configure model environment

Create a `.env` in your workspace (example):

```env
LITECODER_API_KEY=sk-xxxx
LITECODER_BASE_URL=https://api.openai.com/v1
LITECODER_MODEL=gpt-4o
LITECODER_LANG=en
```

### 3) Run

```bash
litecoder
```

On first launch, LiteCoder guides you through basic setup and stores config in your workspace.

## Commands

```text
/help                 Show help
/model [name]         Show/switch model
/tokens               Show token usage
/compact              Manually compact context
/diff                 Show changed files in current session
/save                 Save current session
/sessions             List saved sessions
/session ...          Session ops (list/new/switch/save/current)
/rule ...             Rule ops (list/add/del/clear)
/reset                Clear current chat history
quit                  Exit
```

## Examples

### Example 1: Fix code

```text
You > Read src/main.py, fix import errors, and apply the smallest safe patch.
```

LiteCoder will call tools as needed (for example `read_file` and `edit_file`) and return the result.

### Example 2: Save and switch sessions

```text
/save
/sessions
/session switch session_1710000000
```

### Example 3: Add persistent rules

```text
/rule add Read target files before editing.
/rule add Prefer minimal safe changes in final responses.
```

These rules are automatically applied in later conversations.

## Project Structure (Simplified)

```text
litecoder/
  cli.py         REPL entry and command handling
  agent.py       Agent loop and tool orchestration
  llm.py         LLM client and streaming
  context.py     Context compression
  session.py     Session persistence
  prompt.py      System prompt assembly
  tools/         Tool implementations
```

## Acknowledgements

Special thanks to the original author [Yufeng He](https://github.com/he-yufeng) and the CoreCoder open-source work and architecture analysis that inspired this project.


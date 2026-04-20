"""Internationalization helpers for LiteCoder CLI."""

I18N = {
    "en": {
        "invalid_workdir": "[red]Invalid workdir: {path}[/red]",
        "missing_api_key": "[red bold]No API key found.[/]",
        "missing_api_key_help": (
            "Set one of: LITECODER_API_KEY, CORECODER_API_KEY, OPENAI_API_KEY, or DEEPSEEK_API_KEY\n"
            "You can put these values in .env under your workdir.\n"
            "\nExamples:\n"
            "  OPENAI_API_KEY=sk-...\n"
            "  OPENAI_API_KEY=sk-... OPENAI_BASE_URL=https://api.deepseek.com\n"
            "  OPENAI_API_KEY=ollama OPENAI_BASE_URL=http://localhost:11434/v1 LITECODER_MODEL=qwen2.5-coder"
        ),
        "resumed_session": "[green]Resumed session: {sid} (model: {model})[/green]",
        "resume_not_found": "[red]Session '{sid}' not found.[/red]",
        "banner": (
            "[bold]LiteCoder[/bold] v{version}\n"
            "Model: [cyan]{model}[/cyan]{base}\n"
            "Workdir: [dim]{workdir}[/dim]\n"
            "Type [bold]/help[/bold] for commands, [bold]Tab[/bold] to complete, "
            "[bold]Ctrl+C[/bold] to cancel, [bold]quit[/bold] to exit."
        ),
        "bye": "Bye!",
        "conversation_reset": "[yellow]Conversation reset.[/yellow]",
        "tokens": "Tokens: [cyan]{prompt}[/cyan] prompt + [cyan]{completion}[/cyan] completion = [bold]{total}[/bold] total",
        "switched_model": "Switched to [cyan]{model}[/cyan]",
        "current_model": "Current model: [cyan]{model}[/cyan]",
        "compressed": "[green]Compressed: {before} -> {after} tokens ({messages} messages)[/green]",
        "nothing_to_compress": "[dim]Nothing to compress ({before} tokens, {messages} messages)[/dim]",
        "session_saved": "[green]Session saved: {sid}[/green]",
        "resume_hint": "Resume with: litecoder -C {workdir} -r {sid}",
        "no_files_modified": "[dim]No files modified this session.[/dim]",
        "files_modified": "[bold]Files modified this session ({count}):[/bold]",
        "no_saved_sessions": "[dim]No saved sessions.[/dim]",
        "interrupted": "[yellow]Interrupted.[/yellow]",
        "error": "[red]Error: {error}[/red]",
        "setup_title": "LiteCoder First Run",
        "setup_intro": "Select 5 options in order: workdir, base URL, model, language, API key.",
        "setup_done": "[green]Initial setup completed and written to .env[/green]",
        "setup_choose_workdir": "Choose working directory",
        "setup_choose_url": "Choose API base URL",
        "setup_choose_model": "Choose model",
        "setup_choose_language": "Choose language",
        "setup_choose_apikey": "Choose API key",
        "setup_choice_hint": "Use Up/Down keys to choose and Enter to confirm.",
        "setup_custom_workdir": "Enter custom working directory path:",
        "setup_custom_url": "Enter custom API base URL:",
        "setup_custom_model": "Enter custom model name:",
        "setup_custom_language": "Enter custom language code (en/zh):",
        "setup_custom_apikey": "Enter API key:",
        "setup_custom_label": "Custom...",
        "api_key_from_env": "Use key from environment: {masked}",
        "api_key_ollama": "Ollama local key: ollama",
        "workdir_current": "Current directory: {path}",
        "workdir_parent": "Parent directory: {path}",
        "workdir_home": "Home directory: {path}",
        "workdir_docs": "Documents: {path}",
        "workdir_desktop": "Desktop: {path}",
        "url_openai": "OpenAI: https://api.openai.com/v1",
        "url_deepseek": "DeepSeek: https://api.deepseek.com",
        "url_dashscope": "DashScope: https://dashscope.aliyuncs.com/compatible-mode/v1",
        "url_moonshot": "Moonshot: https://api.moonshot.ai/v1",
        "url_ollama": "Ollama local: http://localhost:11434/v1",
        "lang_en": "English (en)",
        "lang_zh": "Chinese (zh)",
        "user_prompt": "You > ",
        "help_title": "LiteCoder Help",
        "help_body": (
            "[bold]Commands:[/bold]\n"
            "  /help          Show this help\n"
            "  /reset         Clear conversation history\n"
            "  /model         Show current model\n"
            "  /model <name>  Switch model mid-conversation\n"
            "  /tokens        Show token usage\n"
            "  /compact       Compress conversation context\n"
            "  /diff          Show files modified this session\n"
            "  /save          Save session to disk\n"
            "  /sessions      List saved sessions\n"
            "  quit           Exit LiteCoder\n"
            "\n"
            "[bold]Input:[/bold]\n"
            "  Enter          Submit message\n"
            "  Esc+Enter      Insert newline (for pasting code)\n"
            "  Tab            Complete commands"
        ),
    },
    "zh": {
        "invalid_workdir": "[red]工作目录无效: {path}[/red]",
        "missing_api_key": "[red bold]未找到 API Key。[/]",
        "missing_api_key_help": (
            "请设置以下任一变量: LITECODER_API_KEY、CORECODER_API_KEY、OPENAI_API_KEY、DEEPSEEK_API_KEY\n"
            "也可以把这些值写到工作目录下的 .env 文件中。\n"
            "\n示例:\n"
            "  OPENAI_API_KEY=sk-...\n"
            "  OPENAI_API_KEY=sk-... OPENAI_BASE_URL=https://api.deepseek.com\n"
            "  OPENAI_API_KEY=ollama OPENAI_BASE_URL=http://localhost:11434/v1 LITECODER_MODEL=qwen2.5-coder"
        ),
        "resumed_session": "[green]已恢复会话: {sid} (模型: {model})[/green]",
        "resume_not_found": "[red]未找到会话 '{sid}'。[/red]",
        "banner": (
            "[bold]LiteCoder[/bold] v{version}\n"
            "模型: [cyan]{model}[/cyan]{base}\n"
            "工作目录: [dim]{workdir}[/dim]\n"
            "输入 [bold]/help[/bold] 查看命令，[bold]Tab[/bold] 补全，[bold]Ctrl+C[/bold] 中断，[bold]quit[/bold] 退出。"
        ),
        "bye": "再见！",
        "conversation_reset": "[yellow]会话已重置。[/yellow]",
        "tokens": "Token 用量: [cyan]{prompt}[/cyan] 输入 + [cyan]{completion}[/cyan] 输出 = [bold]{total}[/bold] 总计",
        "switched_model": "已切换到 [cyan]{model}[/cyan]",
        "current_model": "当前模型: [cyan]{model}[/cyan]",
        "compressed": "[green]已压缩: {before} -> {after} tokens ({messages} 条消息)[/green]",
        "nothing_to_compress": "[dim]无需压缩 ({before} tokens, {messages} 条消息)[/dim]",
        "session_saved": "[green]会话已保存: {sid}[/green]",
        "resume_hint": "恢复命令: litecoder -C {workdir} -r {sid}",
        "no_files_modified": "[dim]本次会话尚未修改文件。[/dim]",
        "files_modified": "[bold]本次会话修改的文件 ({count}):[/bold]",
        "no_saved_sessions": "[dim]暂无已保存会话。[/dim]",
        "interrupted": "[yellow]已中断。[/yellow]",
        "error": "[red]错误: {error}[/red]",
        "setup_title": "LiteCoder 首次设置",
        "setup_intro": "请依次配置 5 个选项：工作目录、Base URL、模型、语言、API Key。",
        "setup_done": "[green]首次设置完成，已写入 .env 文件[/green]",
        "setup_choose_workdir": "选择工作目录",
        "setup_choose_url": "选择 API Base URL",
        "setup_choose_model": "选择模型",
        "setup_choose_language": "选择语言",
        "setup_choose_apikey": "选择 API Key",
        "setup_choice_hint": "使用方向键上下选择，回车确认。",
        "setup_custom_workdir": "输入自定义工作目录路径：",
        "setup_custom_url": "输入自定义 API Base URL：",
        "setup_custom_model": "输入自定义模型名称：",
        "setup_custom_language": "输入自定义语言代码（en/zh）：",
        "setup_custom_apikey": "输入 API Key：",
        "setup_custom_label": "自定义...",
        "api_key_from_env": "使用环境变量中的 Key: {masked}",
        "api_key_ollama": "本地 Ollama Key: ollama",
        "workdir_current": "当前目录: {path}",
        "workdir_parent": "上级目录: {path}",
        "workdir_home": "用户主目录: {path}",
        "workdir_docs": "文档目录: {path}",
        "workdir_desktop": "桌面目录: {path}",
        "url_openai": "OpenAI: https://api.openai.com/v1",
        "url_deepseek": "DeepSeek: https://api.deepseek.com",
        "url_dashscope": "DashScope: https://dashscope.aliyuncs.com/compatible-mode/v1",
        "url_moonshot": "Moonshot: https://api.moonshot.ai/v1",
        "url_ollama": "本地 Ollama: http://localhost:11434/v1",
        "lang_en": "英文 (en)",
        "lang_zh": "中文 (zh)",
        "user_prompt": "你 > ",
        "help_title": "LiteCoder 帮助",
        "help_body": (
            "[bold]命令:[/bold]\n"
            "  /help          显示帮助\n"
            "  /reset         清空对话历史\n"
            "  /model         查看当前模型\n"
            "  /model <name>  运行中切换模型\n"
            "  /tokens        查看 token 用量\n"
            "  /compact       压缩上下文\n"
            "  /diff          查看本次会话修改文件\n"
            "  /save          保存会话到磁盘\n"
            "  /sessions      列出已保存会话\n"
            "  quit           退出 LiteCoder\n"
            "\n"
            "[bold]输入:[/bold]\n"
            "  Enter          提交消息\n"
            "  Esc+Enter      插入换行（粘贴代码）\n"
            "  Tab            命令补全"
        ),
    },
}


def normalize_lang(value: str | None) -> str:
    """Normalize language code to `en` or `zh`."""
    if not value:
        return "en"
    v = value.strip().lower().replace("_", "-")
    if v.startswith("zh"):
        return "zh"
    return "en"


def tr(lang: str, key: str, **kwargs) -> str:
    """Translate key with fallback to English."""
    catalog = I18N.get(lang, I18N["en"])
    template = catalog.get(key, I18N["en"].get(key, key))
    return template.format(**kwargs)

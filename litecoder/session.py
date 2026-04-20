"""会话持久化模块：保存、加载、列出历史会话。

本模块的职责很聚焦：
1) 将当前对话消息与模型信息写入磁盘（JSON）。
2) 根据会话 ID 读取并恢复历史会话。
3) 列出可恢复的会话并给出预览信息。

设计要点：
- 存储位置固定在 <workdir>/.litecoder/sessions。
- 写入统一使用 UTF-8，避免 Windows 默认编码导致乱码。
- 读取时兼容 UTF-8 / GBK，便于平滑读取历史旧文件。
"""

import json
import time
from pathlib import Path


def _read_json_text_with_fallback(path: Path) -> str:
    """以“UTF-8 优先、GBK 兜底”的方式读取 JSON 文本。

    兼容策略：
    1) 先按 UTF-8 读取（当前标准写入编码）。
    2) 若解码失败，再尝试 GBK（兼容历史文件）。
    3) 若仍失败，则以 UTF-8 + replace 方式尽量读出内容，避免直接崩溃。
    """
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="gbk")
        except UnicodeDecodeError:
            return path.read_text(encoding="utf-8", errors="replace")


def _sessions_dir(workdir: str | Path | None = None) -> Path:
    """解析会话目录路径：<workdir>/.litecoder/sessions。

    参数说明：
    - workdir: 业务工作目录。若为空则使用当前进程工作目录。

    返回值：
    - 仅返回路径对象，不负责创建目录。
    """
    # 统一把输入路径展开并转为绝对路径，避免相对路径歧义。
    base = Path(workdir).expanduser().resolve() if workdir else Path.cwd().resolve()
    return base / ".litecoder" / "sessions"


def save_session(
    messages: list[dict],
    model: str,
    session_id: str | None = None,
    workdir: str | Path | None = None,
) -> str:
    """保存当前会话到磁盘，并返回会话 ID。

    参数说明：
    - messages: 对话消息列表（user/assistant/tool 等）。
    - model: 当前会话使用的模型名。
    - session_id: 可选，若为空则自动生成时间戳 ID。
    - workdir: 工作目录，决定会话落盘位置。
    """
    # 获取会话目录并确保存在。
    sessions_dir = _sessions_dir(workdir)
    sessions_dir.mkdir(parents=True, exist_ok=True)

    # 未指定 ID 时，使用秒级时间戳生成默认会话 ID。
    if not session_id:
        session_id = f"session_{int(time.time())}"

    # 会话文件数据结构：基础元信息 + 消息正文。
    data = {
        "id": session_id,
        "model": model,
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "messages": messages,
    }

    # 统一按 UTF-8 写入，ensure_ascii=False 以保留中文可读性。
    path = sessions_dir / f"{session_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return session_id


def load_session(session_id: str, workdir: str | Path | None = None) -> tuple[list[dict], str] | None:
    """加载指定会话。

    返回：
    - 成功时返回 (messages, model)
    - 找不到会话文件时返回 None
    """
    path = _sessions_dir(workdir) / f"{session_id}.json"
    if not path.exists():
        return None

    # 读取并反序列化 JSON，兼容 UTF-8 / GBK 历史文件。
    data = json.loads(_read_json_text_with_fallback(path))
    return data["messages"], data["model"]


def list_sessions(workdir: str | Path | None = None) -> list[dict]:
    """列出可用会话（按文件名倒序，通常越新越靠前）。

    返回列表中的每个元素包含：
    - id: 会话 ID
    - model: 使用模型
    - saved_at: 保存时间
    - preview: 首条用户消息预览（最多 80 字符）
    """
    sessions_dir = _sessions_dir(workdir)
    if not sessions_dir.exists():
        return []

    sessions = []
    # reverse=True：按文件名倒序遍历，便于优先展示新会话。
    for f in sorted(sessions_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(_read_json_text_with_fallback(f))
            # 抽取首条 user 消息作为预览，帮助用户快速识别会话内容。
            preview = ""
            for m in data.get("messages", []):
                if m.get("role") == "user" and m.get("content"):
                    preview = m["content"][:80]
                    break
            sessions.append({
                # 若字段缺失则提供兜底值，避免展示层报错。
                "id": data.get("id", f.stem),
                "model": data.get("model", "?"),
                "saved_at": data.get("saved_at", "?"),
                "preview": preview,
            })
        except (json.JSONDecodeError, KeyError):
            # 跳过损坏/不完整文件，避免单个坏文件影响整体列表。
            continue

    # 返回上限 20 条，避免会话过多导致输出过长。
    return sessions[:20]

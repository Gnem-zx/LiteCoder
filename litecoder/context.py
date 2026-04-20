"""多层上下文压缩模块。

背景：
- 对话式编码 Agent 在多轮工具调用后，历史消息会快速膨胀。
- 若不压缩，容易触发上下文窗口上限，导致模型调用失败或成本升高。

本模块实现 3 层压缩策略（按轻到重逐级触发）：
1) tool_snip：裁剪冗长工具输出（保留头尾关键信息）。
2) summarize：用 LLM（或降级规则）总结旧消息，仅保留最近消息原文。
3) hard_collapse：紧急压缩，仅保留摘要 + 最近少量消息。
"""

from __future__ import annotations
import hashlib
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .llm import LLM


def _approx_tokens(text: str) -> int:
    """粗略估算文本 token 数。

    这里使用经验系数：大约每 3 个字符折算 1 个 token。
    该估算不追求精确，主要用于“是否需要压缩”的阈值判断。
    """
    return len(text) // 3


def estimate_tokens(messages: list[dict]) -> int:
    """估算消息列表总 token 数（近似值）。

    计入项：
    - message.content
    - message.tool_calls（转字符串后估算）
    """
    total = 0
    for m in messages:
        if m.get("content"):
            total += _approx_tokens(m["content"])
        if m.get("tool_calls"):
            total += _approx_tokens(str(m["tool_calls"]))
    return total


def _resolve_workdir() -> Path:
    """解析工具输出使用的工作目录。

    解析顺序：
    1) 优先使用初始化阶段写入/加载到环境变量的 LITECODER_WORKDIR。
    2) 兼容旧变量 CORECODER_WORKDIR。
    3) 若都不存在，则回退到当前进程工作目录。
    """
    raw = os.getenv("LITECODER_WORKDIR") 
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.cwd().resolve()


class ContextManager:
    def __init__(self, max_tokens: int = 128_000):
        """初始化上下文压缩管理器。

        参数：
        - max_tokens: 目标上下文预算上限。

        触发阈值：
        - 50%：开始裁剪工具输出
        - 70%：开始总结旧消息
        - 90%：进入硬压缩
        """
        self.max_tokens = max_tokens
        # 第一层压缩阈值：超过该长度就会尝试裁剪（预览保留）。
        self._tool_snip_chars = 1500
        # 超大输出阈值：超过该长度会把完整输出落盘，并在上下文中保留引用路径。
        self._tool_externalize_chars = 12_000
        # 工具输出目录优先使用 .env 配置的工作目录，而不是运行时 cwd。
        self._workdir = _resolve_workdir()
        self._tool_output_dir = self._workdir / ".litecoder" / "tool_outputs"
        # 各层触发阈值（按 max_tokens 比例计算）。
        self._snip_at = int(max_tokens * 0.50)    # 50% -> snip tool outputs
        self._summarize_at = int(max_tokens * 0.70)  # 70% -> LLM summarize
        self._collapse_at = int(max_tokens * 0.90)   # 90% -> hard collapse

    def maybe_compress(self, messages: list[dict], llm: LLM | None = None) -> bool:
        """按需执行压缩，返回是否发生过压缩。

        执行顺序：
        1) 先尝试轻量裁剪（tool_snip）
        2) 再尝试摘要压缩（summarize）
        3) 最后才是硬压缩（hard_collapse）

        这样可以在尽量保留信息的前提下控制上下文长度。
        """
        current = estimate_tokens(messages)
        compressed = False

        # 第 1 层：裁剪冗长工具输出。
        if current > self._snip_at:
            if self._snip_tool_outputs(messages):
                compressed = True
                current = estimate_tokens(messages)

        # 第 2 层：总结旧消息，仅保留最近消息原文。
        if current > self._summarize_at and len(messages) > 10:
            if self._summarize_old(messages, llm, keep_recent=8):
                compressed = True
                current = estimate_tokens(messages)

        # 第 3 层：紧急硬压缩（兜底方案）。
        if current > self._collapse_at and len(messages) > 4:
            self._hard_collapse(messages, llm)
            compressed = True

        return compressed

    def _snip_tool_outputs(self, messages: list[dict]) -> bool:
        """第 1 层压缩：裁剪超长工具输出。

        规则：
        - 仅处理 role == "tool" 的消息。
        - content 长度超过 1500 时触发第一层压缩。
        - 若 content 超过 12000（超大输出），会先把完整结果写入本地文件，
          然后上下文只保留头尾预览 + 完整文件路径引用。
        - 其余超长输出仅保留预览，避免上下文持续膨胀。

        返回：
        - True：至少有一条消息被改写。
        - False：未发生改写。
        """
        changed = False
        for m in messages:
            if m.get("role") != "tool":
                continue
            content = m.get("content", "")
            if not content or len(content) <= self._tool_snip_chars:
                continue
            # 已经是“落盘引用”格式则跳过，避免重复写文件。
            if self._is_externalized_pointer(content):
                continue
            
            # 构建输出预览：优先按行头尾保留，否则按字符头尾保留。
            preview = self._build_preview(content)

            # 超大工具输出：完整结果落盘，并在上下文中保留“引用指针”。
            if len(content) >= self._tool_externalize_chars:
                output_path = self._persist_tool_output(content)
                m["content"] = (
                    "[tool output externalized]\n"
                    f"{preview}\n"
                    f"... (full output externalized: {len(content)} chars) ...\n"
                    f"Full output saved to: {output_path}"
                )
                changed = True
                continue

            # 普通超长输出：仅做预览裁剪。
            if preview != content:
                m["content"] = (
                    f"{preview}\n"
                    f"... ({len(content)} chars, snipped to save context) ..."
                )
                changed = True
        return changed

    @staticmethod
    def _is_externalized_pointer(content: str) -> bool:
        """判断消息是否已被替换为“落盘引用”格式。"""
        return content.startswith("[tool output externalized]") and "Full output saved to:" in content

    @staticmethod
    def _build_preview(content: str) -> str:
        """构建工具输出预览：优先按行头尾保留，否则按字符头尾保留。"""
        lines = content.splitlines()
        if len(lines) > 6:
            return (
                "\n".join(lines[:3])
                + f"\n... ({len(lines)} lines previewed: head/tail kept) ...\n"
                + "\n".join(lines[-3:])
            )

        # 行数较少但单行/短行很长时，按字符头尾裁剪。
        if len(content) > 800:
            return (
                content[:400]
                + "\n... (preview truncated: middle omitted) ...\n"
                + content[-400:]
            )

        return content

    def _persist_tool_output(self, content: str) -> str:
        """把完整工具输出写入本地文件，并返回可展示路径。"""
        self._tool_output_dir.mkdir(parents=True, exist_ok=True)

        digest = hashlib.sha1(content.encode("utf-8", errors="ignore")).hexdigest()[:12]
        ts = int(time.time() * 1000)
        out_path = self._tool_output_dir / f"tool_output_{ts}_{digest}.log"
        out_path.write_text(content, encoding="utf-8")

        # 返回相对 workdir 的路径，便于跨 cwd 场景稳定定位。
        return str(out_path.relative_to(self._workdir))

    def _summarize_old(self, messages: list[dict], llm: LLM | None,
                       keep_recent: int = 8) -> bool:
        """第 2 层压缩：总结旧消息，保留最近消息原文。

        参数：
        - keep_recent: 原样保留的末尾消息条数。

        实现思路：
        - 将旧消息汇总成摘要（优先 LLM，总结失败时走规则提取）。
        - 以“摘要 user 消息 + ack assistant 消息”替换旧历史。
        - 再拼回最近 keep_recent 条消息。
        """
        if len(messages) <= keep_recent:
            return False

        # old: 被总结压缩的历史；tail: 保留原文的近期消息。
        old = messages[:-keep_recent]
        tail = messages[-keep_recent:]

        summary = self._get_summary(old, llm)

        # 用摘要替换旧历史，降低上下文体积。
        messages.clear()
        messages.append({
            "role": "user",
            "content": f"[Context compressed - conversation summary]\n{summary}",
        })
        messages.append({
            "role": "assistant",
            "content": "Got it, I have the context from our earlier conversation.",
        })
        messages.extend(tail)
        return True

    def _hard_collapse(self, messages: list[dict], llm: LLM | None):
        """第 3 层压缩：紧急硬压缩。

        该策略会更激进地减少历史：
        - 仅保留最后 4 条消息（不足时保留 2 条）。
        - 其余历史全部折叠为一个摘要。
        """
        # 在极限场景下只保留很短的近期窗口。
        tail = messages[-4:] if len(messages) > 4 else messages[-2:]
        summary = self._get_summary(messages[:-len(tail)], llm)

        # 重建消息历史：摘要 + 恢复提示 + 近期原文。
        messages.clear()
        messages.append({
            "role": "user",
            "content": f"[Hard context reset]\n{summary}",
        })
        messages.append({
            "role": "assistant",
            "content": "Context restored. Continuing from where we left off.",
        })
        messages.extend(tail)

    def _get_summary(self, messages: list[dict], llm: LLM | None) -> str:
        """生成摘要：优先 LLM，失败时降级为规则提取。"""
        flat = self._flatten(messages)

        if llm:
            try:
                # 使用较短的专项摘要提示词，强调“保留关键信息、丢弃冗余细节”。
                resp = llm.chat(
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Compress this conversation into a brief summary. "
                                "Preserve: file paths edited, key decisions made, "
                                "errors encountered, current task state. "
                                "Drop: verbose command output, code listings, "
                                "redundant back-and-forth."
                            ),
                        },
                        # 限制输入长度，避免摘要过程本身再次撑爆上下文。
                        {"role": "user", "content": flat[:15000]},
                    ],
                )
                return resp.content
            except Exception:
                # 摘要调用失败时，回退到本地规则提取，保证流程不断。
                pass

        # 兜底：无需 LLM 的规则抽取。
        return self._extract_key_info(messages)

    @staticmethod
    def _flatten(messages: list[dict]) -> str:
        """把消息列表压平为文本，供摘要阶段使用。"""
        parts = []
        for m in messages:
            role = m.get("role", "?")
            text = m.get("content", "") or ""
            if text:
                # 每条消息最多取前 400 字符，降低摘要输入体积。
                parts.append(f"[{role}] {text[:400]}")
        return "\n".join(parts)

    @staticmethod
    def _extract_key_info(messages: list[dict]) -> str:
        """规则兜底摘要：提取文件路径与错误线索。

        当 LLM 不可用或摘要调用失败时使用。
        """
        import re

        # files_seen: 收集疑似文件路径；errors: 收集错误线索。
        files_seen = set()
        errors = []
        decisions = []

        for m in messages:
            text = m.get("content", "") or ""
            # 提取形如 foo/bar.py、src/main.ts 这类路径片段。
            for match in re.finditer(r'[\w./\-]+\.\w{1,5}', text):
                files_seen.add(match.group())
            # 提取包含 error/Error 的行作为故障线索。
            for line in text.splitlines():
                if 'error' in line.lower() or 'Error' in line:
                    errors.append(line.strip()[:150])

        parts = []
        if files_seen:
            parts.append(f"Files touched: {', '.join(sorted(files_seen)[:20])}")
        if errors:
            parts.append(f"Errors seen: {'; '.join(errors[:5])}")
        # 无可提取信息时返回固定占位文本，保证调用方总能得到字符串。
        return "\n".join(parts) or "(no extractable context)"

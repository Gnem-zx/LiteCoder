"""LLM 提供层：对 OpenAI 兼容接口做一层轻量封装。

设计目标：
1) 屏蔽不同厂商在接入层的小差异，统一通过 openai SDK 调用。
2) 支持流式输出，边接收边回调 token。
3) 支持工具调用（tool calls）增量拼接与解析。
4) 记录 token 用量并估算费用。

由于 DeepSeek、Qwen、Kimi、Ollama 等均提供 OpenAI 兼容 API，
这里通过切换 base_url 与 api_key 即可对接不同服务商。
"""

import json
import time
from dataclasses import dataclass, field

from openai import OpenAI, APIError, RateLimitError, APITimeoutError, APIConnectionError


@dataclass
class ToolCall:
    """一次工具调用的结构化表示。"""

    # 模型返回的 tool_call id（用于与 tool 结果消息对齐）
    id: str
    # 工具名称，对应工具注册表中的 name
    name: str
    # 工具参数（已解析为 dict）
    arguments: dict


@dataclass
class LLMResponse:
    """单轮 LLM 调用的统一返回结构。"""

    # 普通文本内容；若本轮主要是工具调用，这里可能为空字符串
    content: str = ""
    # 模型请求执行的工具调用列表
    tool_calls: list[ToolCall] = field(default_factory=list)
    # 本轮输入 token（prompt tokens）
    prompt_tokens: int = 0
    # 本轮输出 token（completion tokens）
    completion_tokens: int = 0

    @property
    def message(self) -> dict:
        """转换为 OpenAI 消息格式，用于追加到对话历史。

        返回的结构可以直接拼进 messages，供下一轮模型调用使用。
        """
        msg: dict = {"role": "assistant", "content": self.content or None}
        if self.tool_calls:
            # 按 OpenAI tool_calls 协议编码函数调用信息。
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments),
                    },
                }
                for tc in self.tool_calls
            ]
        return msg


# pricing per million tokens: (input, output)
# sources: 
#   openai.com/api/pricing, 
#   api-docs.deepseek.com, 
#   platform.claude.com,
#   platform.moonshot.ai, 
#   alibabacloud.com/help/en/model-studio
_PRICING = {
    # OpenAI - current flagships
    "gpt-5.4": (2.5, 15),
    "gpt-5.4-mini": (0.75, 4.5),
    "gpt-5.4-nano": (0.2, 1.25),
    "o4-mini": (1.1, 4.4),
    # OpenAI - previous gen (still widely used)
    "gpt-4.1": (2, 8),
    "gpt-4.1-mini": (0.4, 1.6),
    "gpt-4.1-nano": (0.1, 0.4),
    "gpt-4o": (2.5, 10),
    "gpt-4o-mini": (0.15, 0.6),
    # DeepSeek
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
    # Anthropic Claude
    "claude-opus-4-6": (5, 25),
    "claude-sonnet-4-6": (3, 15),
    "claude-haiku-4-5": (1, 5),
    # Alibaba Qwen
    "qwen3-max": (0.78, 3.9),
    "qwen3-plus": (0.26, 0.78),
    "qwen-max": (0.78, 3.9),
    # Moonshot Kimi
    "kimi-k2.5": (0.6, 3),
}


class LLM:
    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str | None = None,
        **kwargs,
    ):
        """初始化 LLM 客户端。

        参数说明：
        - model: 默认使用的模型名。
        - api_key: 调用接口使用的凭证。
        - base_url: OpenAI 兼容服务端地址，None 表示官方默认地址。
        - kwargs: 透传给 chat.completions.create 的额外参数，常见如
          temperature、max_tokens 等。
        """
        # 当前会话默认模型。
        self.model = model
        # 底层 SDK 客户端。
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        # 保存可透传的调用参数。
        self.extra = kwargs  # temperature, max_tokens, etc.
        # 累计 token 统计（用于 /tokens 展示与费用估算）。
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    @property
    def estimated_cost(self) -> float | None:
        """估算累计费用（USD）。

        说明：
        - 若当前模型不在 _PRICING 表中，返回 None。
        - 费用按“累计输入 + 累计输出”计算。
        """
        pricing = _PRICING.get(self.model)
        if not pricing:
            return None
        input_rate, output_rate = pricing
        return (
            self.total_prompt_tokens * input_rate / 1_000_000
            + self.total_completion_tokens * output_rate / 1_000_000
        )

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        on_token=None,
    ) -> LLMResponse:
        """发送消息并以流式方式接收响应，同时处理工具调用。

        流程概述：
        1) 组装请求参数（模型、messages、stream 等）。
        2) 优先尝试开启 stream_options.include_usage 获取 token 用量。
           若服务商不支持该扩展参数，则自动移除后重试。
        3) 遍历流式 chunk：
           - 增量拼接文本内容
           - 增量拼接 tool_calls 的 arguments JSON 片段
           - 读取最终 usage 统计
        4) 将工具参数 JSON 解析为 dict，返回统一的 LLMResponse。
        """
        # 请求基础参数：固定开启 stream，以便边生成边展示。
        params: dict = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            **self.extra,
        }
        if tools:
            # 仅在有工具定义时传 tools 字段，避免无意义参数。
            params["tools"] = tools

        # stream_options 是 OpenAI 扩展字段，部分兼容服务商可能不支持。
        # 这里采用“先尝试、失败后降级”的方式，保证兼容性。
        try:
            params["stream_options"] = {"include_usage": True}
            stream = self._call_with_retry(params)
        except Exception:
            params.pop("stream_options", None)
            stream = self._call_with_retry(params)

        # 累积文本片段，最终 join 成完整 assistant 文本。
        content_parts: list[str] = []
        # 工具调用增量缓存：index -> {id, name, args(JSON字符串片段)}
        # 流式场景下，tool call 参数可能被拆成多个 chunk 下发。
        tc_map: dict[int, dict] = {}
        # 本轮 token 用量（若服务端返回 usage）。
        prompt_tok = 0
        completion_tok = 0

        for chunk in stream:
            # usage 通常出现在最后几个 chunk；有值时持续覆盖即可。
            if chunk.usage:
                prompt_tok = chunk.usage.prompt_tokens
                completion_tok = chunk.usage.completion_tokens

            # 某些 chunk 只携带 usage 或控制信息，没有 choices。
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            # 增量拼接文本，并通过 on_token 回调实时输出。
            if delta.content:
                content_parts.append(delta.content)
                if on_token:
                    on_token(delta.content)

            # 增量拼接工具调用：id/name/arguments 都可能分片到达。
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tc_map:
                        tc_map[idx] = {"id": "", "name": "", "args": ""}
                    if tc_delta.id:
                        tc_map[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tc_map[idx]["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            tc_map[idx]["args"] += tc_delta.function.arguments

        # 解析累计的工具调用参数（JSON 字符串 -> dict）。
        parsed: list[ToolCall] = []
        for idx in sorted(tc_map):
            raw = tc_map[idx]
            try:
                args = json.loads(raw["args"])
            except (json.JSONDecodeError, KeyError):
                # 参数异常时兜底为空 dict，避免整个流程中断。
                args = {}
            parsed.append(ToolCall(id=raw["id"], name=raw["name"], arguments=args))

        # 更新累计 token 统计。
        self.total_prompt_tokens += prompt_tok
        self.total_completion_tokens += completion_tok

        # 返回统一结果对象，上层可直接写入消息历史并继续循环。
        return LLMResponse(
            content="".join(content_parts),
            tool_calls=parsed,
            prompt_tokens=prompt_tok,
            completion_tokens=completion_tok,
        )

    def _call_with_retry(self, params: dict, max_retries: int = 3):
        """对瞬时错误进行指数退避重试。

        重试策略：
        - RateLimit / Timeout / Connection 错误：最多重试 max_retries 次。
        - APIError：仅对 5xx 重试，4xx 直接抛出。
        """
        for attempt in range(max_retries):
            try:
                return self.client.chat.completions.create(**params)
            except (RateLimitError, APITimeoutError, APIConnectionError) as e:
                # 这类错误通常是临时性问题，可通过退避重试恢复。
                if attempt == max_retries - 1:
                    raise
                wait = 2 ** attempt
                time.sleep(wait)
            except APIError as e:
                # 5xx 服务端错误可重试；4xx 客户端错误通常需要修参，不重试。
                if e.status_code and e.status_code >= 500 and attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    raise

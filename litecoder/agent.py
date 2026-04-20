"""Core agent loop（核心 Agent 循环）。

该模块是 LiteCoder 的执行中枢，核心流程如下：

    用户输入 -> 调用 LLM（携带工具定义） -> 模型是否请求工具？
                                        -> 是：执行工具并回填结果，再进入下一轮
                                        -> 否：直接返回文本回复，结束本次 chat

这个循环会持续运行，直到模型不再发起 tool calls，表示任务已完成。
"""

import concurrent.futures
from .llm import LLM
from .tools import ALL_TOOLS, get_tool
from .tools.base import Tool
from .prompt import system_prompt
from .context import ContextManager


class Agent:
    def __init__(
        self,
        llm: LLM,
        tools: list[Tool] | None = None,
        max_context_tokens: int = 128_000,
        max_rounds: int = 50,
    ):
        """初始化 Agent。

        参数说明：
        - llm: LLM 客户端实例，负责与模型通信。
        - tools: 可用工具列表；若不传，默认使用 ALL_TOOLS。
        - max_context_tokens: 上下文管理器允许的最大 token 预算。
        - max_rounds: 单次 chat 里最多允许多少轮“模型->工具->模型”循环。
        """
        # 模型客户端，后续每一轮都会通过它发起对话请求。
        self.llm = llm
        # 本 Agent 可调用的工具集合。
        self.tools = tools if tools is not None else ALL_TOOLS
        # 会话消息历史（不含系统提示词，系统提示词由 _full_messages 动态拼接）。
        self.messages: list[dict] = []
        # 上下文压缩管理器，用于控制历史消息体积。
        self.context = ContextManager(max_tokens=max_context_tokens)
        # 防止异常情况下无限循环。
        self.max_rounds = max_rounds
        # 可动态注入的系统提示词扩展（持久规则 / 已安装技能）。
        self._persistent_rules = ""

        # 为支持父代理上下文的工具注入 parent 引用（如 agent ）。
        for t in self.tools:
            if hasattr(t, "_parent_agent"):
                t._parent_agent = self

    def _full_messages(self) -> list[dict]:
        """拼接完整消息列表（系统提示词 + 历史消息）。"""

        base_system = system_prompt(
            self.tools,
            persistent_rules=self._persistent_rules
        )
        return [{"role": "system", "content": base_system}] + self.messages

    def configure_prompt_extensions(self, persistent_rules: str = ""):
        """配置可持久注入系统提示词的扩展内容。"""
        self._persistent_rules = persistent_rules or ""
        





    def switch_session(self, messages: list[dict], model: str | None = None):
        """切换到指定会话内容，并按需更新当前模型。"""
        self.messages = list(messages)
        if model:
            self.llm.model = model

    def _tool_schemas(self) -> list[dict]:
        """导出工具 schema，供 LLM 的 function/tool calling 使用。"""
        return [t.schema() for t in self.tools]

    def chat(self, user_input: str, on_token=None, on_tool=None, on_dangerous=None) -> str:
        """处理一条用户消息，必要时触发多轮工具调用。

        整体行为：
        1) 先把用户输入写入历史。
        2) 按需做一次上下文压缩，避免消息过长。
        3) 进入最多 max_rounds 轮循环：
           - 调用模型
           - 若无工具调用：返回模型文本
           - 若有工具调用：执行工具并把结果追加到历史，再进入下一轮

        回调说明：
        - on_token: 流式文本 token 回调，用于终端实时输出。
        - on_tool: 工具执行前回调，用于输出“正在调用哪个工具”。
        """
        # 记录当前用户输入，作为后续模型推理的最新上下文。
        self.messages.append({"role": "user", "content": user_input})
        # 每轮开始前先尝试压缩，减少超长上下文导致的失败概率与成本。
        self.context.maybe_compress(self.messages, self.llm)

        # 主循环：一次 chat 内允许多轮“模型决策 + 工具执行”。
        for _ in range(self.max_rounds):
            # 让模型基于当前完整上下文进行下一步决策（回复文本或请求工具）。
            resp = self.llm.chat(
                messages=self._full_messages(),
                tools=self._tool_schemas(),
                on_token=on_token,
            )

            # 没有工具调用：表示模型已完成本轮任务，直接返回文本答案。
            if not resp.tool_calls:
                self.messages.append(resp.message)
                return resp.content

            # 有工具调用：先记录 assistant 的 tool_calls 消息，保证历史链路完整。
            self.messages.append(resp.message)

            if len(resp.tool_calls) == 1:
                # 单工具调用：直接串行执行，逻辑更简单，开销更低。
                tc = resp.tool_calls[0]
                if on_tool:
                    on_tool(tc.name, tc.arguments)
                result = self._exec_tool(tc, on_dangerous=on_dangerous)
                # 将工具执行结果写回历史，供下一轮模型继续推理。
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
            else:
                # 多工具调用：并行执行，加速整体响应。
                results = self._exec_tools_parallel(resp.tool_calls, on_tool, on_dangerous=on_dangerous)
                for tc, result in zip(resp.tool_calls, results):
                    # 保持“每个 tool_call 对应一个 tool 消息”的结构。
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })

            # 工具输出可能很长，再次压缩以控制后续轮次的上下文体积。
            self.context.maybe_compress(self.messages, self.llm)

        # 达到最大轮次仍未结束，返回保护性提示，避免无限循环。
        return "(reached maximum tool-call rounds)"

    def _exec_tool(self, tc, on_dangerous=None) -> str:
        """执行单个工具调用，并将结果统一转成字符串返回。"""
        # 根据工具名查找具体工具实例。
        tool = get_tool(tc.name)
        if tool is None:
            return f"Error: unknown tool '{tc.name}'"

        # bash 高危命令执行前确认：未确认则拒绝执行。
        if tc.name == "bash":
            from .tools.bash import is_dangerous_command

            cmd = str(tc.arguments.get("command", ""))
            reason = is_dangerous_command(cmd)
            if reason:
                approved = False
                if on_dangerous:
                    try:
                        approved = bool(on_dangerous(cmd, reason))
                    except Exception:
                        approved = False

                if not approved:
                    return f"Rejected dangerous command: {reason}\nCommand: {cmd}"

                args = dict(tc.arguments)
                args["approved"] = True
                try:
                    return tool.execute(**args)
                except TypeError as e:
                    return f"Error: bad arguments for {tc.name}: {e}"
                except Exception as e:
                    return f"Error executing {tc.name}: {e}"

        try:
            # 将模型给出的参数解包后传给工具执行。
            return tool.execute(**tc.arguments)
        except TypeError as e:
            # 参数不匹配通常是模型构参问题，返回清晰错误供模型自我修正。
            return f"Error: bad arguments for {tc.name}: {e}"
        except Exception as e:
            # 捕获工具内部异常，避免整个 Agent 流程中断。
            return f"Error executing {tc.name}: {e}"

    def _exec_tools_parallel(self, tool_calls, on_tool=None, on_dangerous=None) -> list[str]:
        """使用线程池并行执行多个工具调用。

        说明：
        - 这里是“同一轮内多工具并发”，不是流式边生成边执行。
        - 结果顺序与 tool_calls 顺序保持一致，便于后续逐条回填。
        """
        # 先触发工具回调，便于 UI 侧展示将要执行的工具列表。
        for tc in tool_calls:
            if on_tool:
                on_tool(tc.name, tc.arguments)

        # 需要用户确认时避免在线程中触发交互，改为串行执行。
        if on_dangerous:
            from .tools.bash import is_dangerous_command

            has_dangerous_bash = any(
                tc.name == "bash" and is_dangerous_command(str(tc.arguments.get("command", "")))
                for tc in tool_calls
            )
            if has_dangerous_bash:
                return [self._exec_tool(tc, on_dangerous=on_dangerous) for tc in tool_calls]

        # 线程池并行执行，适合 I/O 密集型工具（读写文件、子进程调用等）。
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(self._exec_tool, tc, None) for tc in tool_calls]
            # 按提交顺序取结果，保证与输入工具调用一一对应。
            return [f.result() for f in futures]

    def reset(self):
        """清空会话历史（仅消息历史，不重建 Agent 配置）。"""
        self.messages.clear()

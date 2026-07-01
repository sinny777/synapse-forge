"""
tool_router.common.llm_adapters
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

LiteLLM-backed LangChain ChatModel adapter.

Provides :class:`LiteLLMChatOpenAI`, a ``ChatOpenAI`` subclass that routes
LLM calls through LiteLLM so that local (Ollama/Granite) and cloud models
(OpenAI, Anthropic, WatsonX, …) can all be used interchangeably within
LangGraph agents.
"""

import json
import logging
from typing import AsyncGenerator

from langchain_openai import ChatOpenAI
from litellm import completion, acompletion

logger = logging.getLogger(__name__)


class LiteLLMChatOpenAI(ChatOpenAI):
    litellm_model: str

    def _to_litellm_messages(self, messages):
        from langchain_core.messages import SystemMessage, AIMessage, HumanMessage, ToolMessage
        litellm_messages = []
        for m in messages:
            if isinstance(m, SystemMessage) or (hasattr(m, "type") and m.type == "system"):
                litellm_messages.append({"role": "system", "content": m.content})
            elif isinstance(m, HumanMessage) or (hasattr(m, "type") and m.type == "human"):
                litellm_messages.append({"role": "user", "content": m.content})
            elif isinstance(m, ToolMessage) or (hasattr(m, "type") and m.type == "tool"):
                # Use the standard tool-role message for all models.
                # The old "is_local" workaround (converting tool results to user messages)
                # was written assuming local models don't support function calling, but
                # Granite 4.1:8b and similar models do — and the text-based workaround
                # breaks the tool-call/result correlation, causing the model to re-call
                # tools with empty arguments on the next turn.
                # WatsonX still needs the text workaround as it doesn't support tool role.
                is_watsonx = "watsonx/" in self.litellm_model.lower()
                if is_watsonx:
                    tool_name = getattr(m, "name", "tool") or "tool"
                    litellm_messages.append({
                        "role": "user",
                        "content": f"[Tool Result - {tool_name}]\n{m.content}"
                    })
                else:
                    litellm_messages.append({
                        "role": "tool",
                        "content": m.content,
                        "tool_call_id": getattr(m, "tool_call_id", None) or getattr(m, "id", None)
                    })
            elif isinstance(m, AIMessage) or (hasattr(m, "type") and m.type in ("assistant", "ai")):
                content = m.content or ""
                # WatsonX doesn't support native tool_calls in the message format,
                # so we inline a text representation into the assistant content instead.
                is_watsonx = "watsonx/" in self.litellm_model.lower()
                if is_watsonx and hasattr(m, "tool_calls") and m.tool_calls:
                    tool_calls_text = []
                    for tc in m.tool_calls:
                        tool_calls_text.append(f"Tool Call: {tc.get('name')}({json.dumps(tc.get('args'))})")
                    content = (content + "\n\n" + "\n".join(tool_calls_text)).strip() if content else "\n".join(tool_calls_text)

                msg_dict = {"role": "assistant", "content": content}
                if not is_watsonx and hasattr(m, "tool_calls") and m.tool_calls:
                    msg_dict["tool_calls"] = [
                        {
                            "id": tc.get("id"),
                            "type": "function",
                            "function": {
                                "name": tc.get("name"),
                                "arguments": json.dumps(tc.get("args")),
                            }
                        }
                        for tc in m.tool_calls
                    ]
                litellm_messages.append(msg_dict)
            else:
                role = getattr(m, "role", "user")
                litellm_messages.append({"role": role, "content": m.content})
        logger.info(f"[_to_litellm_messages] Serialized messages:\n{json.dumps(litellm_messages, indent=2)}")
        return litellm_messages

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        litellm_messages = self._to_litellm_messages(messages)
        tools = kwargs.pop("tools", None) or kwargs.pop("functions", None)
        extra_args = {}
        if tools:
            litellm_tools = []
            for t in tools:
                if isinstance(t, dict):
                    litellm_tools.append(t)
                else:
                    try:
                        from langchain_core.utils.function_calling import convert_to_openai_tool
                        litellm_tools.append(convert_to_openai_tool(t))
                    except Exception as e:
                        logger.warning(f"Failed to convert tool {getattr(t, 'name', 'unknown')} using convert_to_openai_tool: {e}")
                        if hasattr(t, "name"):
                            litellm_tools.append({
                                "type": "function",
                                "function": {
                                    "name": t.name,
                                    "description": t.description or "",
                                    "parameters": t.args if hasattr(t, "args") else {}
                                }
                            })
            if litellm_tools:
                extra_args["tools"] = litellm_tools

        res = completion(
            model=self.litellm_model,
            messages=litellm_messages,
            temperature=self.temperature or 0.0,
            max_tokens=self.max_tokens,
            **{**extra_args, **kwargs}
        )
        choice_message = res.choices[0].message
        content = choice_message.content or ""

        tool_calls = []
        if hasattr(choice_message, "tool_calls") and choice_message.tool_calls:
            for tc in choice_message.tool_calls:
                tc_name = getattr(getattr(tc, "function", None), "name", None)
                tc_args_str = getattr(getattr(tc, "function", None), "arguments", "{}")
                try:
                    tc_args = json.loads(tc_args_str) if tc_args_str else {}
                except Exception:
                    tc_args = {}
                tc_id = getattr(tc, "id", None)
                if tc_name:
                    tool_calls.append({
                        "name": tc_name,
                        "args": tc_args,
                        "id": tc_id,
                        "type": "tool_call"
                    })
        from langchain_core.outputs import ChatResult, ChatGeneration
        from langchain_core.messages import AIMessage
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content, tool_calls=tool_calls))])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        litellm_messages = self._to_litellm_messages(messages)
        tools = kwargs.pop("tools", None) or kwargs.pop("functions", None)
        extra_args = {}
        if tools:
            litellm_tools = []
            for t in tools:
                if isinstance(t, dict):
                    litellm_tools.append(t)
                else:
                    try:
                        from langchain_core.utils.function_calling import convert_to_openai_tool
                        litellm_tools.append(convert_to_openai_tool(t))
                    except Exception as e:
                        logger.warning(f"Failed to convert tool {getattr(t, 'name', 'unknown')} using convert_to_openai_tool: {e}")
                        if hasattr(t, "name"):
                            litellm_tools.append({
                                "type": "function",
                                "function": {
                                    "name": t.name,
                                    "description": t.description or "",
                                    "parameters": t.args if hasattr(t, "args") else {}
                                }
                            })
            if litellm_tools:
                extra_args["tools"] = litellm_tools

        res = await acompletion(
            model=self.litellm_model,
            messages=litellm_messages,
            temperature=self.temperature or 0.0,
            max_tokens=self.max_tokens,
            **{**extra_args, **kwargs}
        )
        choice_message = res.choices[0].message
        content = choice_message.content or ""

        tool_calls = []
        if hasattr(choice_message, "tool_calls") and choice_message.tool_calls:
            for tc in choice_message.tool_calls:
                tc_name = getattr(getattr(tc, "function", None), "name", None)
                tc_args_str = getattr(getattr(tc, "function", None), "arguments", "{}")
                try:
                    tc_args = json.loads(tc_args_str) if tc_args_str else {}
                except Exception:
                    tc_args = {}
                tc_id = getattr(tc, "id", None)
                if tc_name:
                    tool_calls.append({
                        "name": tc_name,
                        "args": tc_args,
                        "id": tc_id,
                        "type": "tool_call"
                    })
        from langchain_core.outputs import ChatResult, ChatGeneration
        from langchain_core.messages import AIMessage
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content, tool_calls=tool_calls))])

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        litellm_messages = self._to_litellm_messages(messages)
        tools = kwargs.pop("tools", None) or kwargs.pop("functions", None)
        extra_args = {}
        if tools:
            litellm_tools = []
            for t in tools:
                if isinstance(t, dict):
                    litellm_tools.append(t)
                else:
                    try:
                        from langchain_core.utils.function_calling import convert_to_openai_tool
                        litellm_tools.append(convert_to_openai_tool(t))
                    except Exception as e:
                        logger.warning(f"Failed to convert tool {getattr(t, 'name', 'unknown')} using convert_to_openai_tool: {e}")
                        if hasattr(t, "name"):
                            litellm_tools.append({
                                "type": "function",
                                "function": {
                                    "name": t.name,
                                    "description": t.description or "",
                                    "parameters": t.args if hasattr(t, "args") else {}
                                }
                            })
            if litellm_tools:
                extra_args["tools"] = litellm_tools

        response = await acompletion(
            model=self.litellm_model,
            messages=litellm_messages,
            temperature=self.temperature or 0.0,
            max_tokens=self.max_tokens,
            stream=True,
            **{**extra_args, **kwargs}
        )
        from langchain_core.messages import AIMessageChunk
        from langchain_core.outputs import ChatGenerationChunk
        async for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            content_delta = getattr(delta, "content", None) or ""

            tool_call_chunks = []
            if hasattr(delta, "tool_calls") and delta.tool_calls:
                for tc in delta.tool_calls:
                    tc_index = getattr(tc, "index", 0)
                    tc_id = getattr(tc, "id", None)
                    tc_func = getattr(tc, "function", None)
                    tc_name = getattr(tc_func, "name", None) if tc_func else None
                    tc_args = getattr(tc_func, "arguments", None) if tc_func else None

                    tool_call_chunks.append({
                        "name": tc_name,
                        "args": tc_args,
                        "id": tc_id,
                        "index": tc_index,
                        "type": "tool_call_chunk"
                    })

            if content_delta or tool_call_chunks:
                yield ChatGenerationChunk(
                    message=AIMessageChunk(
                        content=content_delta,
                        tool_call_chunks=tool_call_chunks
                    )
                )

from __future__ import annotations

import json
from typing import AsyncGenerator, Callable

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_chroma import Chroma


def _to_jsonable(value):
    """Coerce values (including LangChain message/tool objects) to JSON-serializable."""
    try:
        json.dumps(value)
        return value
    except TypeError:
        # Common LangChain objects may have `content` attribute
        content = getattr(value, "content", None)
        if content is not None:
            return content
        # Fallback to string
        return str(value)


class AgentRunner:
    """Wraps a LangGraph ReAct agent and exposes a streaming event generator."""

    def __init__(
        self,
        retriever_fn: Callable[[str], str],
        model: str = "gpt-4o-mini",
        temperature: float = 0.0,
    ):
        # Lazy import to avoid import errors if langgraph is not installed at analysis time
        from langgraph.prebuilt import create_react_agent

        self.llm = ChatOpenAI(model=model, temperature=temperature, streaming=True)

        @tool("retrieve")
        def retrieve(query: str) -> str:
            """
            Search the knowledge base and return relevant context snippets for the given query.
            """
            return retriever_fn(query)

        self.agent = create_react_agent(self.llm, tools=[retrieve])

    async def stream(self, message: str) -> AsyncGenerator[bytes, None]:
        """Yield NDJSON event lines for real-time UI updates."""
        async for event in self.agent.astream_events(
            {"messages": [HumanMessage(content=message)]},
            version="v1",
        ):
            etype = event.get("event")
            if etype == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                token = getattr(chunk, "content", "") or ""
                if token:
                    yield (json.dumps({"type": "token", "content": token}) + "\n").encode()
            elif etype == "on_tool_start":
                name = event.get("name") or event.get("data", {}).get("name")
                input_raw = event.get("data", {}).get("input")
                input_ = _to_jsonable(input_raw)
                yield (
                    json.dumps({"type": "tool_start", "name": name, "input": input_}) + "\n"
                ).encode()
            elif etype == "on_tool_end":
                name = event.get("name") or event.get("data", {}).get("name")
                output_raw = event.get("data", {}).get("output")
                output = _to_jsonable(output_raw)
                yield (
                    json.dumps({"type": "tool_end", "name": name, "output": output}) + "\n"
                ).encode()
            elif etype == "on_chain_end":
                # Include the final text if present
                data = event.get("data", {})
                output = data.get("output", {})
                final_text = None
                if isinstance(output, dict):
                    msg = output.get("messages") or []
                    if msg:
                        final_text = getattr(msg[-1], "content", None)
                if final_text:
                    yield (json.dumps({"type": "final", "content": final_text}) + "\n").encode()


def build_retriever(index_path: str):
    """Builds a simple top-1 retriever function returning a text blob."""
    embeddings = OpenAIEmbeddings()
    vectorstore = Chroma(persist_directory=index_path, embedding_function=embeddings)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

    def _run(query: str) -> str:
        try:
            # Use invoke per LangChain v0.3 deprecation notice
            docs = retriever.invoke(query)
            return "\n\n".join(d.page_content for d in docs if getattr(d, "page_content", ""))
        except Exception:
            return ""

    return _run

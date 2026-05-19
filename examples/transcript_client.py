"""End-to-end smoke test: launches `subconscious-mcp` as a subprocess and
drives it through a real MCP stdio session. Prints a readable transcript.

Usage:
    python examples/transcript_client.py
"""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _pretty(label: str, payload) -> None:
    print(f"\n>>> {label}")
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump()
    print(json.dumps(payload, indent=2, default=str))


async def _content_to_dict(result):
    """call_tool() returns content blocks; we want the structured/text payload."""
    if getattr(result, "structuredContent", None):
        return result.structuredContent
    if result.content:
        block = result.content[0]
        if hasattr(block, "text"):
            try:
                return json.loads(block.text)
            except json.JSONDecodeError:
                return {"raw": block.text}
    return {}


async def main() -> int:
    params = StdioServerParameters(command="subconscious-mcp", args=[])

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            _pretty("initialize", {"server": init.serverInfo.name, "version": init.serverInfo.version})

            tools = await session.list_tools()
            _pretty("list_tools", [t.name for t in tools.tools])

            # 1. recall a task we've never stored -> miss
            miss = await session.call_tool(
                "recall",
                arguments={
                    "task": "How do I deploy a Next.js app to Vercel?",
                    "threshold": 0.85,
                },
            )
            _pretty("recall (cold) ->", await _content_to_dict(miss))

            # 2. remember the answer
            remembered = await session.call_tool(
                "remember",
                arguments={
                    "task": "How do I deploy a Next.js app to Vercel?",
                    "answer": "Run `vercel --prod` after `vercel login`.",
                    "tags": ["vercel", "deploy"],
                },
            )
            remembered_dict = await _content_to_dict(remembered)
            _pretty("remember ->", remembered_dict)
            entry_id = remembered_dict["entry_id"]

            # 3. recall the same task (exact) -> hit
            hit = await session.call_tool(
                "recall",
                arguments={
                    "task": "How do I deploy a Next.js app to Vercel?",
                    "threshold": 0.85,
                },
            )
            _pretty("recall (exact) ->", await _content_to_dict(hit))

            # 4. recall a paraphrase
            paraphrase = await session.call_tool(
                "recall",
                arguments={
                    "task": "What's the process for shipping a Next.js project on Vercel?",
                    "threshold": 0.6,
                },
            )
            _pretty("recall (paraphrase) ->", await _content_to_dict(paraphrase))

            # 5. stats
            stats = await session.call_tool("stats", arguments={})
            _pretty("stats ->", await _content_to_dict(stats))

            # 6. forget
            forgotten = await session.call_tool(
                "forget", arguments={"entry_id": entry_id}
            )
            _pretty("forget ->", await _content_to_dict(forgotten))

            # 7. recall after forget -> miss again
            after = await session.call_tool(
                "recall",
                arguments={
                    "task": "How do I deploy a Next.js app to Vercel?",
                    "threshold": 0.85,
                },
            )
            _pretty("recall (after forget) ->", await _content_to_dict(after))

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

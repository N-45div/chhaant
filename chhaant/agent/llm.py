"""Language-model backends behind one small interface.

* ``BedrockBackend``: Amazon Bedrock's Converse API (Claude Haiku 4.5 by
  default, through the global inference profile from ap-south-1).
* ``ScriptedBackend``: replays fixed replies, for tests.

Messages are kept in one internal form and translated per backend:
    {"role": "user" | "assistant", "content": [block, ...]}
    block = {"text": str}
          | {"tool_use": {"id": str, "name": str, "input": dict}}
          | {"tool_result": {"id": str, "content": dict, "error": bool}}
"""

import time
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class Reply:
    text: str
    tool_calls: list[ToolCall]
    stop: str
    usage: dict = field(default_factory=dict)
    latency_s: float = 0.0


class BedrockBackend:
    name = "bedrock"

    def __init__(self, model_id: str = "global.anthropic.claude-haiku-4-5-20251001-v1:0",
                 region: str = "ap-south-1", max_tokens: int = 1024, client=None):
        self.model_id, self.max_tokens = model_id, max_tokens
        if client is None:
            import boto3
            from botocore.config import Config
            # Adaptive retries with patience: one throttled call would otherwise end the whole order
            # (the end-to-end evaluation lost 9 of 32 runs to ThrottlingException under the default 4 tries).
            retry = Config(retries={"max_attempts": 10, "mode": "adaptive"}, read_timeout=120)
            client = boto3.client("bedrock-runtime", region_name=region, config=retry)
        self.client = client

    @staticmethod
    def to_converse(messages: list[dict]) -> list[dict]:
        out = []
        for m in messages:
            blocks = []
            for b in m["content"]:
                if "text" in b:
                    blocks.append({"text": b["text"]})
                elif "tool_use" in b:
                    u = b["tool_use"]
                    blocks.append({"toolUse": {"toolUseId": u["id"], "name": u["name"], "input": u["input"]}})
                else:
                    r = b["tool_result"]
                    blocks.append({"toolResult": {"toolUseId": r["id"], "content": [{"json": r["content"]}],
                                                  "status": "error" if r["error"] else "success"}})
            out.append({"role": m["role"], "content": blocks})
        return out

    def chat(self, system: str, messages: list[dict], tools: list[dict]) -> Reply:
        t0 = time.perf_counter()
        resp = self.client.converse(
            modelId=self.model_id, system=[{"text": system}], messages=self.to_converse(messages),
            toolConfig={"tools": [{"toolSpec": {"name": t["name"], "description": t["description"],
                                                "inputSchema": {"json": t["schema"]}}} for t in tools]},
            inferenceConfig={"maxTokens": self.max_tokens, "temperature": 0.0})
        text, calls = [], []
        for b in resp["output"]["message"]["content"]:
            if "text" in b:
                text.append(b["text"])
            elif "toolUse" in b:
                u = b["toolUse"]
                calls.append(ToolCall(u["toolUseId"], u["name"], u.get("input") or {}))
        usage = resp.get("usage", {})
        return Reply("\n".join(text), calls, resp.get("stopReason", ""),
                     {"input": usage.get("inputTokens", 0), "output": usage.get("outputTokens", 0)},
                     time.perf_counter() - t0)


class ScriptedBackend:
    name = "scripted"

    def __init__(self, replies: list[Reply]):
        self.replies = list(replies)
        self.seen: list[list[dict]] = []

    def chat(self, system: str, messages: list[dict], tools: list[dict]) -> Reply:
        self.seen.append([dict(m) for m in messages])
        return self.replies.pop(0) if self.replies else Reply("", [], "end_turn")

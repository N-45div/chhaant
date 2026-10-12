"""Language-model backends behind one small interface.

* ``BedrockBackend``: Amazon Bedrock's Converse API (Claude Haiku 4.5 by
  default, through the global inference profile from ap-south-1).
* ``OpenAICompatBackend``: any OpenAI-style chat-completions endpoint with
  tool calls; this is how Nebius Token Factory serves NVIDIA Nemotron.
* ``ScriptedBackend``: replays fixed replies, for tests.

Messages are kept in one internal form and translated per backend:
    {"role": "user" | "assistant", "content": [block, ...]}
    block = {"text": str}
          | {"tool_use": {"id": str, "name": str, "input": dict}}
          | {"tool_result": {"id": str, "content": dict, "error": bool}}
"""

import json
import time
import urllib.request
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
            client = boto3.client("bedrock-runtime", region_name=region)
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


class OpenAICompatBackend:
    name = "openai-compatible"

    def __init__(self, base_url: str, api_key: str, model: str, max_tokens: int = 1024, post=None):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key, self.model, self.max_tokens = api_key, model, max_tokens
        self.post = post or self._post

    def _post(self, payload: dict) -> dict:
        req = urllib.request.Request(self.url, data=json.dumps(payload).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())

    @staticmethod
    def to_chat(system: str, messages: list[dict]) -> list[dict]:
        out = [{"role": "system", "content": system}]
        for m in messages:
            texts = [b["text"] for b in m["content"] if "text" in b]
            uses = [b["tool_use"] for b in m["content"] if "tool_use" in b]
            results = [b["tool_result"] for b in m["content"] if "tool_result" in b]
            if m["role"] == "assistant":
                msg = {"role": "assistant", "content": "\n".join(texts) or None}
                if uses:
                    msg["tool_calls"] = [{"id": u["id"], "type": "function",
                                          "function": {"name": u["name"], "arguments": json.dumps(u["input"])}} for u in uses]
                out.append(msg)
            else:
                out += [{"role": "tool", "tool_call_id": r["id"], "content": json.dumps(r["content"])} for r in results]
                if texts:
                    out.append({"role": "user", "content": "\n".join(texts)})
        return out

    def chat(self, system: str, messages: list[dict], tools: list[dict]) -> Reply:
        t0 = time.perf_counter()
        resp = self.post({
            "model": self.model, "messages": self.to_chat(system, messages), "max_tokens": self.max_tokens,
            "temperature": 0.0, "tool_choice": "auto",
            "tools": [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                        "parameters": t["schema"]}} for t in tools]})
        choice = resp["choices"][0]
        msg = choice["message"]
        calls = []
        for c in msg.get("tool_calls") or []:
            args = c["function"].get("arguments") or "{}"
            calls.append(ToolCall(c["id"], c["function"]["name"], json.loads(args) if isinstance(args, str) else args))
        usage = resp.get("usage", {})
        return Reply(msg.get("content") or "", calls, choice.get("finish_reason", ""),
                     {"input": usage.get("prompt_tokens", 0), "output": usage.get("completion_tokens", 0)},
                     time.perf_counter() - t0)


class ScriptedBackend:
    name = "scripted"

    def __init__(self, replies: list[Reply]):
        self.replies = list(replies)
        self.seen: list[list[dict]] = []

    def chat(self, system: str, messages: list[dict], tools: list[dict]) -> Reply:
        self.seen.append([dict(m) for m in messages])
        return self.replies.pop(0) if self.replies else Reply("", [], "end_turn")

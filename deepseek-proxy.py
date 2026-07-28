"""
DeepSeek Proxy for Claude Code
===============================
Presents itself as claude-sonnet-5 to Claude Code,
routes all requests to DeepSeek V4 Pro underneath.
"""
import json, ssl, sys, uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import HTTPError

try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()

DEEPSEEK_KEY   = "sk-YOUR-DEEPSEEK-API-KEY-HERE"
DEEPSEEK_BASE  = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"
PORT           = 4000

# Pretend to be these models so Claude Code doesn't reject us
FAKE_MODELS = [
    {"id": "claude-opus-5",         "type": "model", "display_name": "Claude Opus 5 (DeepSeek V4 Pro)",    "created_at": "2025-06-01T00:00:00Z"},
    {"id": "claude-sonnet-5",       "type": "model", "display_name": "Claude Sonnet 5 (DeepSeek V4 Pro)",  "created_at": "2025-06-01T00:00:00Z"},
    {"id": "claude-fable-5",        "type": "model", "display_name": "Claude Fable 5 (DeepSeek V4 Pro)",   "created_at": "2025-06-01T00:00:00Z"},
    {"id": "claude-haiku-4-5",      "type": "model", "display_name": "Claude Haiku 4.5 (DeepSeek V4 Pro)", "created_at": "2024-10-01T00:00:00Z"},
    {"id": "deepseek-v4-pro",       "type": "model", "display_name": "DeepSeek V4 Pro",                   "created_at": "2024-01-01T00:00:00Z"},
]


def an_to_ds(an: dict) -> dict:
    ds = {"model": DEEPSEEK_MODEL, "messages": [], "stream": False}

    # system prompt
    s = an.get("system")
    if s:
        if isinstance(s, str):
            ds["messages"].append({"role": "system", "content": s})
        elif isinstance(s, list):
            parts = [b.get("text","") for b in s if isinstance(b,dict) and b.get("type")=="text"]
            if parts: ds["messages"].append({"role": "system", "content": "\n".join(parts)})

    # messages
    for m in an.get("messages", []):
        c = m.get("content", "")
        if isinstance(c, list):
            parts = []
            for b in c:
                if not isinstance(b, dict): continue
                t = b.get("type","")
                if t == "text":       parts.append(b.get("text",""))
                elif t == "tool_use": parts.append(f'[tool_use: {b.get("name","")} {json.dumps(b.get("input",{}))}]')
                elif t == "tool_result": parts.append(f'[tool_result: {b.get("content","")}]')
            c = "\n".join(parts)
        ds["messages"].append({"role": m.get("role","user"), "content": c})

    if "max_tokens" in an:  ds["max_tokens"]  = an["max_tokens"]
    if "temperature" in an: ds["temperature"] = an["temperature"]
    if "top_p" in an:       ds["top_p"]       = an["top_p"]
    if "stop_sequences" in an: ds["stop"]     = an["stop_sequences"]

    tools = an.get("tools")
    if tools:
        ds["tools"] = [{
            "type": "function",
            "function": {"name": t.get("name",""), "description": t.get("description",""),
                         "parameters": t.get("input_schema",{})}
        } for t in tools]

    return ds


def ds_to_an(ds: dict, an: dict) -> dict:
    choice = ds.get("choices", [{}])[0]
    msg    = choice.get("message", {})
    text   = msg.get("content", "")
    finish = choice.get("finish_reason", "stop")

    blocks = []
    if text:
        blocks.append({"type": "text", "text": text})

    for tc in msg.get("tool_calls", []):
        func = tc.get("function", {})
        try:
            args = json.loads(func.get("arguments", "{}"))
        except (json.JSONDecodeError, TypeError):
            args = {}
        blocks.append({
            "type": "tool_use",
            "id": tc.get("id", f"toolu_{uuid.uuid4().hex[:24]}"),
            "name": func.get("name", ""),
            "input": args,
        })

    stop_map = {"stop": "end_turn", "length": "max_tokens", "tool_calls": "tool_use"}
    usage = ds.get("usage", {})

    return {
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "model": an.get("model", "claude-sonnet-5"),
        "content": blocks,
        "stop_reason": stop_map.get(finish, "end_turn"),
        "stop_sequence": None,
        "usage": {
            "input_tokens":  usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }


class H(BaseHTTPRequestHandler):

    def log_message(self, f, *a):
        pass  # quiet default logging; we log manually

    def _send(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length).decode()) if length else {}

    def _call_deepseek(self, endpoint: str, body: dict = None) -> dict:
        url     = f"{DEEPSEEK_BASE}{endpoint}"
        headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
        req     = Request(url, data=json.dumps(body).encode() if body else None,
                          headers=headers, method="GET" if body is None else "POST")
        try:
            with urlopen(req, timeout=180, context=SSL_CONTEXT) as r:
                return json.loads(r.read().decode())
        except HTTPError as e:
            err = e.read().decode(errors="replace")[:500]
            print(f"  !! DeepSeek [{e.code}]: {err}", flush=True)
            raise

    def do_GET(self):
        p = self.path.split("?")[0]
        print(f"  GET {p}", flush=True)

        if p == "/v1/models":
            self._send({"object": "list", "data": FAKE_MODELS, "has_more": False,
                         "first_id": FAKE_MODELS[0]["id"], "last_id": FAKE_MODELS[-1]["id"]})
        elif p.startswith("/v1/models/"):
            model_id = p.split("/v1/models/")[1]
            # Return the model with the EXACT id Claude Code requested
            # so identity checks pass (claude-opus-5[1m] must match)
            self._send({
                "id": model_id,
                "type": "model",
                "display_name": f"DeepSeek V4 Pro (as {model_id})",
                "created_at": "2025-06-01T00:00:00Z",
            })
        elif p == "/health":
            self._send({"status": "ok"})
        else:
            print(f"  ?? UNKNOWN GET: {p}", flush=True)
            self._send({"error": f"not found: {p}"}, 404)

    def do_POST(self):
        p = self.path.split("?")[0]
        print(f"  POST {p}", flush=True)

        if p == "/v1/messages":
            try:
                an   = self._read()
                model = an.get("model", "?")
                print(f"    model={model} msgs={len(an.get('messages',[]))} max_tok={an.get('max_tokens')}", flush=True)
                ds   = an_to_ds(an)
                resp = self._call_deepseek("/chat/completions", ds)
                out  = ds_to_an(resp, an)
                print(f"    -> {out['stop_reason']} in={out['usage']['input_tokens']} out={out['usage']['output_tokens']}", flush=True)
                self._send(out)
            except Exception as e:
                print(f"    !! ERROR: {e}", flush=True)
                self._send({"type": "error", "error": {"type": "api_error", "message": str(e)}}, 500)
        else:
            print(f"  ?? UNKNOWN POST: {p}", flush=True)
            self._send({"type": "error", "error": {"type": "invalid_request_error", "message": f"not found: {p}"}}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    print(f"", flush=True)
    print(f"  Proxy: http://localhost:{port}", flush=True)
    print(f"  -> DeepSeek: {DEEPSEEK_MODEL} @ {DEEPSEEK_BASE}", flush=True)
    print(f"", flush=True)
    HTTPServer(("0.0.0.0", port), H).serve_forever()

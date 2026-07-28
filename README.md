# Configuring DeepSeek V4 Pro with Claude Code (Opus 5 / Sonnet 5)

Complete guide and proxy implementation for routing Claude Code CLI through DeepSeek V4 Pro's API on Windows 11 ARM64.

## Architecture

```
┌─────────────────┐       Anthropic Messages API        ┌────────────────────┐       OpenAI Chat Completions        ┌──────────────────┐
│                 │                                     │                    │                                     │                  │
│  Claude Code     │ ───── http://localhost:4000 ─────▶ │  deepseek-proxy.py  │ ───── api.deepseek.com/v1 ─────▶ │  DeepSeek V4 Pro  │
│  (Windows 11)    │                                     │  (Python stdlib)    │                                     │  (deepseek-chat)  │
│                 │ ◀─────────────────────────────── │                    │ ◀────────────────────────────────── │                  │
└─────────────────┘                                     └────────────────────┘                                     └──────────────────┘
```

Claude Code speaks Anthropic's Messages API natively. DeepSeek speaks OpenAI's Chat Completions API. The proxy translates every request and response in real time — zero pip dependencies, pure Python standard library.

## Why This Exists

- Claude Code is the most capable AI CLI tool available
- DeepSeek V4 Pro (deepseek-chat) offers competitive performance at lower cost
- The two APIs are format-incompatible — this proxy bridges them
- Windows ARM64 cannot compile LiteLLM's Rust dependencies (MSVC linker missing)
- Pure Python stdlib solution works everywhere without compilation

## Repository Contents

| File | Purpose |
|---|---|
| `deepseek-proxy.py` | API translation proxy — the core of this setup |
| `test-deepseek-api.py` | Standalone DeepSeek API key validation script |
| `claude-code-deepseek-setup-guide.html` | Full step-by-step setup guide (open in browser) |

## Quick Start

### Prerequisites

- Windows 11 (x64 or ARM64)
- Node.js 18+
- Python 3.12+
- DeepSeek API key

### 1. Install Node.js (if needed)

```powershell
winget install OpenJS.NodeJS.LTS --source winget --accept-package-agreements --accept-source-agreements
```

Refresh PATH:
```powershell
$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
```

### 2. Install Claude Code CLI

```powershell
npm install -g @anthropic-ai/claude-code@latest
```

### 3. Install Python 3.12 (if needed)

```powershell
winget install Python.Python.3.12 --source winget --accept-package-agreements
$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
pip install certifi
```

### 4. Configure API Key

Edit `deepseek-proxy.py` line 17:
```python
DEEPSEEK_KEY = "sk-your-deepseek-api-key-here"
```

A sample key is already present for reference.

### 5. Start the Proxy

```cmd
python deepseek-proxy.py
```

Expected output:
```
  Proxy: http://localhost:4000
  -> DeepSeek: deepseek-chat @ https://api.deepseek.com/v1
```

### 6. Launch Claude Code

In a separate terminal:
```powershell
$env:ANTHROPIC_BASE_URL = 'http://localhost:4000'
$env:ANTHROPIC_API_KEY = 'any-value'
claude
```

> **Critical:** Do NOT include `/v1` at the end of `ANTHROPIC_BASE_URL`. Claude Code appends it automatically. Using `http://localhost:4000/v1` results in double paths (`/v1/v1/messages`) and breaks the connection.

### 7. Select a Model

When Claude Code launches, it will display available models. Select any listed model — Opus 5, Sonnet 5, or Haiku 4.5 — all route to DeepSeek V4 Pro underneath.

If prompted about the API key, select **Yes**.

## How the Proxy Works

### Request Flow (Claude Code → DeepSeek)

1. Claude Code sends a POST to `/v1/messages` with Anthropic-format JSON:
```json
{
  "model": "claude-sonnet-5",
  "messages": [{"role": "user", "content": "Hello"}],
  "max_tokens": 4096
}
```

2. The proxy translates it to OpenAI format and forwards to DeepSeek:
```json
{
  "model": "deepseek-chat",
  "messages": [{"role": "user", "content": "Hello"}],
  "max_tokens": 4096
}
```

### Response Flow (DeepSeek → Claude Code)

3. DeepSeek returns an OpenAI-format response:
```json
{
  "choices": [{
    "message": {"content": "Hi there!"},
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 10, "completion_tokens": 5}
}
```

4. The proxy translates it back to Anthropic format:
```json
{
  "id": "msg_...",
  "type": "message",
  "role": "assistant",
  "content": [{"type": "text", "text": "Hi there!"}],
  "stop_reason": "end_turn",
  "usage": {"input_tokens": 10, "output_tokens": 5}
}
```

### Model Masquerading

The proxy presents standard Anthropic model names (claude-opus-5, claude-sonnet-5, claude-fable-5, claude-haiku-4-5) so Claude Code's internal model validation passes. It also handles Claude Code's model variant suffixes (`[1m]`, `[50k]`) by echoing back the exact model ID requested.

### Tool/Function Calling

Tool use (`tool_use` and `tool_result` content blocks) is translated to OpenAI's `tool_calls` format and back. This enables full multi-turn tool interaction through DeepSeek.

### SSL Certificate Handling

Some Windows VMs have broken system certificate stores. The proxy uses the `certifi` package (installed via pip) to provide a valid CA bundle, bypassing the broken system store.

## Environment Variables

| Variable | Value | Notes |
|---|---|---|
| `ANTHROPIC_BASE_URL` | `http://localhost:4000` | No trailing `/v1` |
| `ANTHROPIC_API_KEY` | `any-value` | Placeholder — real key is in proxy |

To persist across reboots:
```powershell
[Environment]::SetEnvironmentVariable("ANTHROPIC_BASE_URL", "http://localhost:4000", "User")
[Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "any-value", "User")
```

## Testing the DeepSeek API Directly

Run the standalone test to verify your API key works without the proxy:

```cmd
python test-deepseek-api.py
```

Expected output:
```
Sending to DeepSeek API (using certifi bundle)...
Model:    deepseek-chat
Response: Hello!
Tokens:   {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}
SUCCESS - API key works!
```

## Troubleshooting

| Issue | Cause | Solution |
|---|---|---|
| `CERTIFICATE_VERIFY_FAILED` | Broken Windows SSL certs | `pip install certifi` |
| `POST /v1/v1/messages` | Double path | Remove `/v1` from BASE_URL |
| Model not found | ID suffix mismatch | Proxy echoes exact model ID |
| Claude Code freezes | Proxy not running | Start proxy first, then launch |
| `link.exe not found` | MSVC missing on ARM64 | Not needed — uses pure Python |

## Verified Environment

| Component | Version |
|---|---|
| Windows | 11 ARM64 |
| Node.js | v24.18.0 |
| npm | v11.16.0 |
| Claude Code | 2.1.220 |
| Python | 3.12.10 |
| certifi | 2026.7.22 |
| DeepSeek model | deepseek-chat |

## License

MIT — use, modify, and distribute freely.

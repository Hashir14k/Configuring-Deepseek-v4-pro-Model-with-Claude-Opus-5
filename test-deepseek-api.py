import json
import ssl
from urllib.request import Request, urlopen
import certifi

KEY   = "sk-7955b60b155c40d78adc3f856fdfaef7"
MODEL = "deepseek-chat"
URL   = "https://api.deepseek.com/v1/chat/completions"

body = {
    "model": MODEL,
    "messages": [{"role": "user", "content": "say hello"}],
    "max_tokens": 50
}

req = Request(
    URL,
    data=json.dumps(body).encode(),
    headers={
        "Authorization": f"Bearer {KEY}",
        "Content-Type": "application/json"
    }
)

print("Sending to DeepSeek API (using certifi bundle)...")

# Use certifi's CA bundle to bypass system SSL issues
ctx = ssl.create_default_context(cafile=certifi.where())
resp = urlopen(req, timeout=30, context=ctx)
data = json.loads(resp.read().decode())

print(f"Model:    {data.get('model')}")
print(f"Response: {data['choices'][0]['message']['content']}")
print(f"Tokens:   {data.get('usage', {})}")
print("SUCCESS - API key works!")

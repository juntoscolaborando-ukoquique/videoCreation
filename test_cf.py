import requests
import base64
import os

ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "YOUR_ACCOUNT_ID_HERE")
API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")
MODEL = "@cf/black-forest-labs/flux-1-schnell"
URL = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/{MODEL}"

headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"
}

payload = {
    "prompt": "A futuristic city with flying cars, digital art style"
}

response = requests.post(URL, headers=headers, json=payload)

if response.status_code == 200:
    # Check if content type is json or image
    if 'application/json' in response.headers.get('content-type', ''):
        data = response.json()
        print("Keys in response:", data.keys())
        if "result" in data and "image" in data["result"]:
            with open("test_cf_out.png", "wb") as f:
                f.write(base64.b64decode(data["result"]["image"]))
            print("Saved from base64 JSON")
    else:
        with open("test_cf_out.png", "wb") as f:
            f.write(response.content)
        print("Saved raw binary")
else:
    print(f"Error: {response.status_code} - {response.text}")

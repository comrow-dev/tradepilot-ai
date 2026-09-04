import os
import requests

BACKEND_URL = os.getenv(
    "TRADEPILOT_BACKEND_URL",
    "https://tradepilot-ai-uykw.onrender.com"
)

url = BACKEND_URL.rstrip("/") + "/api/auto-scan"

response = requests.get(
    url,
    timeout=60
)

print("TradePilot Auto Scan")
print("Status:", response.status_code)
print(response.text)

response.raise_for_status()

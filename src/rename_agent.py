import requests, json

BASE = "https://mort-royal-production.up.railway.app/api"

api_key = input("API key: ")
agent_id = input("Agent ID: ")
new_name = input("New agent name: ")

res = requests.patch(
    f"{BASE}/agents/{agent_id}",
    headers={"X-API-Key": api_key},
    json={"name": new_name}
)

print(res.json())

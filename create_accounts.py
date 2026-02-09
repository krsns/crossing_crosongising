import requests, json, time
from config import BASE_URL, TOTAL_ACCOUNTS

accounts = []

for i in range(TOTAL_ACCOUNTS):
    name = f"bot_{i+1}"
    r = requests.post(
        f"{BASE_URL}/accounts",
        json={"name": name}
    ).json()

    api_key = r["data"]["apiKey"]
    print(f"[OK] Created account {name}")

    accounts.append({
        "name": name,
        "apiKey": api_key,
        "gameId": None,
        "agentId": None
    })

    time.sleep(2)

# save main
with open("accounts.json", "w") as f:
    json.dump(accounts, f, indent=2)

# backup
with open("accounts_backup.json", "w") as f:
    json.dump(accounts, f, indent=2)

print("\n✅ ALL ACCOUNTS CREATED")
print("📌 API KEYS SAVED & BACKED UP")

import requests, json, time
from config import BASE_URL, TOTAL_ACCOUNTS

prefix = input("Masukkan prefix nama bot (contoh: vps2_ atau userA_): ").strip()
if not prefix:
    prefix = "bot_"

start = input("Mulai dari nomor berapa? (default 1): ").strip()
start = int(start) if start else 1

accounts = []

for i in range(TOTAL_ACCOUNTS):
    name = f"{prefix}{start + i}"

    r = requests.post(
        f"{BASE_URL}/accounts",
        json={"name": name},
        timeout=20
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

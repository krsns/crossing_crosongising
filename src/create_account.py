import requests, os

BASE = "https://mort-royal-production.up.railway.app/api"

os.makedirs("../backup/api_keys", exist_ok=True)

name = input("Bot base name: ")
count = int(input("How many accounts? "))

for i in range(count):
    bot_name = f"{name}_{i+1}"
    res = requests.post(
        f"{BASE}/accounts",
        json={"name": bot_name}
    ).json()

    api_key = res["data"]["apiKey"]
    path = f"../backup/api_keys/{bot_name}.txt"

    with open(path, "w") as f:
        f.write(api_key)

    os.chmod(path, 0o600)
    print(f"[OK] {bot_name} → saved")

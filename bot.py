import requests, json, time, random, traceback
from config import *

def load_accounts():
    with open("accounts.json") as f:
        return json.load(f)

def save_accounts(accs):
    with open("accounts.json", "w") as f:
        json.dump(accs, f, indent=2)
    with open("accounts_backup.json", "w") as f:
        json.dump(accs, f, indent=2)

def safe_json(resp):
    try:
        return resp.json()
    except:
        return {}

def wait_game_running(game_id):
    while True:
        r = requests.get(f"{BASE_URL}/games/{game_id}")
        res = safe_json(r)
        status = res.get("data", {}).get("status")
        if status == "running":
            return
        print(f"[WAIT] game {game_id} belum running...")
        time.sleep(15)

accounts = load_accounts()

print(f"[START] total accounts: {len(accounts)}")

while True:
    try:
        for acc in accounts:
            headers = {"X-API-Key": acc["apiKey"]}

            # ===== JOIN GAME =====
            if not acc.get("gameId"):
                r = requests.get(f"{BASE_URL}/games?status=waiting")
                games = safe_json(r).get("data", [])

                if games:
                    game = games[0]
                else:
                    game = safe_json(
                        requests.post(f"{BASE_URL}/games", headers=headers)
                    ).get("data")

                if not game:
                    print("[ERROR] gagal create game")
                    time.sleep(10)
                    continue

                acc["gameId"] = game["id"]

                agent = safe_json(
                    requests.post(
                        f"{BASE_URL}/games/{acc['gameId']}/agents/register",
                        headers=headers,
                        json={"name": acc["name"]}
                    )
                ).get("data")

                if not agent:
                    print(f"[ERROR] register agent gagal {acc['name']}")
                    time.sleep(10)
                    continue

                acc["agentId"] = agent["id"]
                save_accounts(accounts)

                print(f"[JOINED] {acc['name']} → {acc['gameId']}")
                wait_game_running(acc["gameId"])
                time.sleep(3)
                continue

            # ===== GET STATE =====
            r = requests.get(
                f"{BASE_URL}/games/{acc['gameId']}/agents/{acc['agentId']}/state",
                headers=headers,
                timeout=10
            )

            res = safe_json(r)
            if "data" not in res:
                print(f"[WAIT] {acc['name']} state not ready")
                time.sleep(10)
                continue

            state = res["data"]
            hp = state.get("hp", 100)
            ep = state.get("ep", 0)

            # ===== DECISION =====
            if hp < LOW_HP_THRESHOLD or ep < 5:
                action = {"type": "rest"}
            else:
                action = random.choice([
                    {"type": "move"},
                    {"type": "pickup"},
                    {"type": "talk"}
                ])

            # ===== SEND ACTION =====
            requests.post(
                f"{BASE_URL}/games/{acc['gameId']}/agents/{acc['agentId']}/action",
                headers=headers,
                json={"action": action},
                timeout=10
            )

            print(f"[ACTION] {acc['name']} | HP:{hp} EP:{ep} → {action['type']}")
            time.sleep(random.randint(*ACCOUNT_DELAY))

        time.sleep(ACTION_INTERVAL)

    except Exception as e:
        print("🔥 BOT ERROR, AUTO RESTART 🔥")
        traceback.print_exc()
        time.sleep(15)

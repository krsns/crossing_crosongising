import requests, json, time, random, traceback, os
from datetime import datetime
from config import *

ACCOUNTS_FILE = "accounts.json"
ACCOUNTS_BACKUP = "accounts_backup.json"
PAYLOAD_FILE = "payloads.json"
PAYLOAD_BACKUP = "payloads_backup.json"


# ========= UTILS =========
def load_accounts():
    with open(ACCOUNTS_FILE) as f:
        return json.load(f)

def save_accounts(accs):
    with open(ACCOUNTS_FILE, "w") as f:
        json.dump(accs, f, indent=2)
    with open(ACCOUNTS_BACKUP, "w") as f:
        json.dump(accs, f, indent=2)

def safe_json(resp):
    try:
        return resp.json()
    except:
        return {}

def get_account_info(api_key):
    r = requests.get(
        f"{BASE_URL}/accounts/me",
        headers={"X-API-Key": api_key},
        timeout=10
    )
    return safe_json(r).get("data", {})

def save_payload(acc, payload):
    data = {}

    if os.path.exists(PAYLOAD_FILE):
        with open(PAYLOAD_FILE, "r") as f:
            data = json.load(f)

    data[acc["name"]] = {
        "apiKey": acc["apiKey"],
        "gameId": acc["gameId"],
        "agentId": acc["agentId"],
        "payload": payload,
        "timestamp": datetime.utcnow().isoformat()
    }

    with open(PAYLOAD_FILE, "w") as f:
        json.dump(data, f, indent=2)

    with open(PAYLOAD_BACKUP, "w") as f:
        json.dump(data, f, indent=2)

    print(f"[PAYLOAD SAVED] {acc['name']}")

def wait_game_running(game_id):
    while True:
        r = requests.get(f"{BASE_URL}/games/{game_id}", timeout=10)
        res = safe_json(r)
        status = res.get("data", {}).get("status")

        if status == "running":
            print(f"[RUNNING] game {game_id}")
            return

        print(f"[WAIT] game {game_id} belum running...")
        time.sleep(15)


# ========= MAIN =========
accounts = load_accounts()
print(f"[START] total accounts: {len(accounts)}")

while True:
    try:
        for acc in accounts:
            headers = {"X-API-Key": acc["apiKey"]}

            # ===== ACCOUNT INFO =====
            info = get_account_info(acc["apiKey"])
            balance = info.get("balance", 0)
            print(f"\n[ACCOUNT] {acc['name']} | Moltz: {balance}")

            # ===== JOIN GAME =====
            if not acc.get("gameId"):
                r = requests.get(f"{BASE_URL}/games?status=waiting", timeout=10)
                games = safe_json(r).get("data", [])

                if games:
                    game = games[0]
                else:
                    game = safe_json(
                        requests.post(f"{BASE_URL}/games", headers=headers, timeout=10)
                    ).get("data")

                if not game:
                    print("[ERROR] gagal create/join game")
                    time.sleep(10)
                    continue

                acc["gameId"] = game["id"]

                agent = safe_json(
                    requests.post(
                        f"{BASE_URL}/games/{acc['gameId']}/agents/register",
                        headers=headers,
                        json={"name": acc["name"]},
                        timeout=10
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

            # ===== GAME INFO =====
            game_info = safe_json(
                requests.get(f"{BASE_URL}/games/{acc['gameId']}", timeout=10)
            ).get("data", {})

            print(
                f"[GAME] {acc['gameId']} | status={game_info.get('status')} "
                f"| turn={game_info.get('turn', '?')}"
            )

            # ===== GET STATE =====
            r = requests.get(
                f"{BASE_URL}/games/{acc['gameId']}/agents/{acc['agentId']}/state",
                headers=headers,
                timeout=10
            )

            res = safe_json(r)
            if "data" not in res:
                print(f"[WAIT] {acc['name']} state belum siap")
                time.sleep(10)
                continue

            state = res["data"]
            hp = state.get("hp", 0)
            ep = state.get("ep", 0)
            atk = state.get("attack", 0)
            df = state.get("defense", 0)
            kills = state.get("kills", 0)

            print(f"[STATE] HP:{hp} EP:{ep} ATK:{atk} DEF:{df} KILL:{kills}")

            # ===== DECISION =====
            if hp < LOW_HP_THRESHOLD or ep <= 2:
                action = {"type": "rest"}
            else:
                action = random.choice([
                    {"type": "move"},
                    {"type": "pickup"},
                    {"type": "talk"}
                ])

            print(f"[DECISION] {acc['name']} → {action['type']}")

            # ===== SEND ACTION =====
            r = requests.post(
                f"{BASE_URL}/games/{acc['gameId']}/agents/{acc['agentId']}/action",
                headers=headers,
                json={"action": action},
                timeout=10
            )

            res = safe_json(r)

            # ===== SAVE PAYLOAD IF ANY =====
            payload = res.get("data", {}).get("claimPayload")
            if payload:
                save_payload(acc, payload)

            print(f"[ACTION SENT] {acc['name']} → {action['type']}")
            print("-" * 45)

            time.sleep(random.randint(*ACCOUNT_DELAY))

        time.sleep(ACTION_INTERVAL)

    except Exception:
        print("🔥 BOT ERROR, AUTO RESTART 🔥")
        traceback.print_exc()
        time.sleep(15)

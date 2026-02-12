import requests
import time
import json
import os

BASE_URL = "https://api.moltyroyale.com"
INFO_TIMEOUT = 10
STATE_WAIT_SLEEP = 2
MAX_RUNNING_WAIT = 40

# ===============================
# HARDCODED GHOST GAME BLOCK
# ===============================
BLOCKED_GAMES = {
    "8bb2d5a8-ccd6-4201-9e53-11e96dc8bac0"
}

BLACKLIST_LIMIT = 20
blacklist = []

# ===============================
# LOAD ACCOUNTS
# ===============================
def load_accounts():
    if not os.path.exists("accounts.json"):
        return []
    with open("accounts.json", "r") as f:
        return json.load(f)

def save_accounts(accs):
    with open("accounts.json", "w") as f:
        json.dump(accs, f, indent=2)

def blacklist_add(gid):
    if gid not in blacklist:
        blacklist.append(gid)
        if len(blacklist) > BLACKLIST_LIMIT:
            blacklist.pop(0)

# ===============================
# SAFE JSON
# ===============================
def safe_json(r):
    try:
        return r.json()
    except:
        return {}

# ===============================
# PICK GAME (STABLE)
# ===============================
def pick_target_game(headers):
    global blacklist

    try:
        r = requests.get(f"{BASE_URL}/games?status=waiting", timeout=INFO_TIMEOUT)
        games = safe_json(r).get("data", [])
    except:
        return None

    for g in games:
        gid = g.get("id")

        if not gid:
            continue

        if gid in BLOCKED_GAMES:
            print(f"[SKIP] Ghost game blocked: {gid}")
            continue

        if gid in blacklist:
            continue

        return g

    # kalau tidak ada waiting valid → buat baru
    try:
        resp = requests.post(f"{BASE_URL}/games", headers=headers, timeout=INFO_TIMEOUT)
        g = safe_json(resp).get("data")
        if g and g.get("id") not in BLOCKED_GAMES:
            return g
    except:
        pass

    return None

# ===============================
# WAIT RUNNING (ANTI STUCK)
# ===============================
def wait_game_running(game_id):
    start = time.time()

    while True:
        try:
            r = requests.get(f"{BASE_URL}/games/{game_id}", timeout=INFO_TIMEOUT)
            data = safe_json(r).get("data", {})
            status = data.get("status")
            turn = data.get("turn", 0)

            if status == "running" and turn > 0:
                return True

            if status == "finished":
                return False

        except:
            return False

        if time.time() - start > MAX_RUNNING_WAIT:
            print("[TIMEOUT] Game stuck waiting running")
            return False

        time.sleep(STATE_WAIT_SLEEP)

# ===============================
# MAIN LOOP
# ===============================
def main():
    accounts = load_accounts()
    if not accounts:
        print("No accounts found")
        return

    while True:
        headers = {
            "Authorization": accounts[0]["token"],
            "Content-Type": "application/json"
        }

        target = pick_target_game(headers)

        if not target:
            print("[WAIT] no valid game, retrying...")
            time.sleep(5)
            continue

        game_id = target.get("id")

        if not game_id:
            continue

        print(f"[JOIN] Target Game: {game_id}")

        # ===============================
        # REGISTER ALL ACCOUNTS FIRST
        # ===============================
        for acc in accounts:
            try:
                h = {
                    "Authorization": acc["token"],
                    "Content-Type": "application/json"
                }

                requests.post(
                    f"{BASE_URL}/games/{game_id}/register",
                    headers=h,
                    timeout=INFO_TIMEOUT
                )

                acc["last_game"] = game_id

            except:
                pass

        save_accounts(accounts)

        # ===============================
        # WAIT RUNNING
        # ===============================
        ok = wait_game_running(game_id)

        if not ok:
            print("[RESET] Game invalid / stuck → blacklist")
            blacklist_add(game_id)
            time.sleep(3)
            continue

        print("[START] Game running")

        # ===============================
        # SIMPLE ACTION LOOP
        # ===============================
        while True:
            try:
                r = requests.get(f"{BASE_URL}/games/{game_id}", timeout=INFO_TIMEOUT)
                data = safe_json(r).get("data", {})
                status = data.get("status")

                if status == "finished":
                    print("[FINISHED] Reset loop")
                    break

                time.sleep(STATE_WAIT_SLEEP)

            except:
                break

        time.sleep(3)

if __name__ == "__main__":
    main()

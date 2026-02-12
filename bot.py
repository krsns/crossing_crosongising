import requests, json, time, random, os, sys
from datetime import datetime
from config import *

ACCOUNTS_FILE = "accounts.json"

STATE_WAIT_SLEEP = 5
ACTION_INTERVAL = 3
ACCOUNT_DELAY = (2, 4)
MAX_WAIT_RUNNING = 60

BLOCKED_GAMES = {
    "8bb2d5a8-ccd6-4201-9e53-11e96dc8bac0"
}

# ================= UTIL =================

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def safe_json(r):
    try:
        return r.json()
    except:
        return {}

def safe_int(x):
    try:
        return int(x)
    except:
        return 0

def load_accounts():
    with open(ACCOUNTS_FILE) as f:
        return json.load(f)

def save_accounts(accs):
    with open(ACCOUNTS_FILE, "w") as f:
        json.dump(accs, f, indent=2)

# ================= GAME =================

def pick_target_game(headers):
    try:
        r = requests.get(f"{BASE_URL}/games?status=waiting", timeout=10)
        games = safe_json(r).get("data", [])
    except:
        games = []

    for g in games:
        gid = g.get("id")
        if not gid:
            continue
        if gid in BLOCKED_GAMES:
            continue
        return g

    # create kalau kosong
    try:
        r = requests.post(f"{BASE_URL}/games", headers=headers, timeout=10)
        return safe_json(r).get("data")
    except:
        return None

def wait_until_running(game_id):
    for _ in range(MAX_WAIT_RUNNING):
        r = requests.get(f"{BASE_URL}/games/{game_id}", timeout=10)
        data = safe_json(r).get("data", {})
        status = data.get("status")
        if status == "running":
            return True
        if status in ("finished", "cancelled"):
            return False
        time.sleep(2)
    return False

# ================= SMART STRATEGY (FULL CONFIG) =================

def weighted_choice(choices):
    actions = list(choices.keys())
    weights = list(choices.values())
    return random.choices(actions, weights=weights, k=1)[0]

def get_smart_action(hp, ep, atk, defense, turn):

    turn = safe_int(turn)

    if hp <= CRITICAL_HP:
        return {"type": "rest"}

    if ep <= CRITICAL_EP:
        return {"type": "rest"}

    if hp < LOW_HP_THRESHOLD:
        return {"type": "rest"}

    if ep < LOW_EP_THRESHOLD:
        if hp < 60:
            return {"type": "rest"}
        else:
            return {"type": "move"}

    if turn <= EARLY_GAME_TURNS:
        return {"type": weighted_choice({
            "pickup": EARLY_PICKUP_WEIGHT,
            "move": EARLY_MOVE_WEIGHT,
            "rest": EARLY_REST_WEIGHT
        })}

    elif turn <= MID_GAME_TURNS:
        if (atk >= MIN_ATTACK_TO_FIGHT and
            hp >= MIN_HP_TO_FIGHT and
            ep >= MIN_EP_TO_FIGHT):

            return {"type": weighted_choice({
                "attack": MID_ATTACK_WEIGHT,
                "pickup": MID_PICKUP_WEIGHT,
                "move": MID_MOVE_WEIGHT,
                "rest": MID_REST_WEIGHT
            })}
        else:
            return {"type": weighted_choice({
                "pickup": 0.6,
                "move": 0.3,
                "rest": 0.1
            })}

    else:
        hp_threshold = MIN_HP_TO_FIGHT
        if defense >= DEFENSE_THRESHOLD:
            hp_threshold -= HIGH_DEFENSE_HP_BONUS

        if (atk >= MIN_ATTACK_TO_FIGHT + 5 and
            hp >= hp_threshold + 15 and
            ep >= MIN_EP_TO_FIGHT + 10):

            return {"type": weighted_choice({
                "attack": 0.6,
                "move": 0.25,
                "pickup": 0.1,
                "rest": 0.05
            })}

        elif atk < MIN_ATTACK_TO_FIGHT:
            if ep > 25:
                return {"type": weighted_choice({
                    "pickup": 0.5,
                    "move": 0.35,
                    "rest": 0.15
                })}
            else:
                return {"type": weighted_choice({
                    "move": 0.5,
                    "rest": 0.5
                })}

        elif defense >= DEFENSE_THRESHOLD:
            return {"type": weighted_choice({
                "attack": 0.45,
                "move": 0.3,
                "pickup": 0.15,
                "rest": 0.1
            })}

        else:
            return {"type": weighted_choice({
                "attack": LATE_ATTACK_WEIGHT,
                "move": LATE_MOVE_WEIGHT,
                "pickup": LATE_PICKUP_WEIGHT,
                "rest": LATE_REST_WEIGHT
            })}

# ================= MAIN =================

accounts = load_accounts()

while True:
    try:
        first_headers = {"X-API-Key": accounts[0]["apiKey"]}
        game = pick_target_game(first_headers)

        if not game:
            log("NO GAME AVAILABLE")
            time.sleep(5)
            continue

        game_id = game["id"]
        log(f"TARGET GAME {game_id}")

        # REGISTER ALL
        for acc in accounts:
            headers = {"X-API-Key": acc["apiKey"]}

            if acc.get("gameId") != game_id:
                acc["gameId"] = game_id
                acc["agentId"] = None

            if not acc.get("agentId"):
                r = requests.post(
                    f"{BASE_URL}/games/{game_id}/agents/register",
                    headers=headers,
                    json={"name": acc["name"]},
                    timeout=10
                )
                agent = safe_json(r).get("data")
                if agent:
                    acc["agentId"] = agent["id"]
                    log(f"{acc['name']} JOINED")
                else:
                    log(f"{acc['name']} REGISTER FAIL")

        save_accounts(accounts)

        if not wait_until_running(game_id):
            log("GAME NOT RUNNING")
            time.sleep(5)
            continue

        log("GAME RUNNING")

        # ================= ACTION LOOP =================
        while True:

            r = requests.get(f"{BASE_URL}/games/{game_id}", timeout=10)
            game_info = safe_json(r).get("data", {})
            status = game_info.get("status")
            turn = game_info.get("turn")

            if status in ("finished", "cancelled"):
                log("GAME FINISHED")
                for acc in accounts:
                    acc["gameId"] = None
                    acc["agentId"] = None
                save_accounts(accounts)
                break

            for acc in accounts:
                headers = {"X-API-Key": acc["apiKey"]}

                r = requests.get(
                    f"{BASE_URL}/games/{acc['gameId']}/agents/{acc['agentId']}/state",
                    headers=headers,
                    timeout=10
                )

                state = safe_json(r).get("data")
                if not state:
                    continue

                hp = state.get("hp", 0)
                ep = state.get("ep", 0)
                atk = state.get("attack", 0)
                defense = state.get("defense", 0)

                action = get_smart_action(hp, ep, atk, defense, turn)

                log(f"{acc['name']} T{turn} HP{hp} EP{ep} A{atk} D{defense} → {action['type']}")

                r2 = requests.post(
                    f"{BASE_URL}/games/{acc['gameId']}/agents/{acc['agentId']}/action",
                    headers=headers,
                    json=action,
                    timeout=10
                )

                res2 = safe_json(r2)
                if "error" in res2:
                    log(f"ACTION ERROR: {res2}")

                time.sleep(random.randint(*ACCOUNT_DELAY))

            time.sleep(ACTION_INTERVAL)

    except KeyboardInterrupt:
        log("BOT STOPPED")
        save_accounts(accounts)
        break

    except Exception as e:
        log(f"ERROR: {type(e).__name__}")
        time.sleep(5)

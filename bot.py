import requests, json, time, random, traceback, os, sys
from datetime import datetime
from config import *

ACCOUNTS_FILE = "accounts.json"
ACCOUNTS_BACKUP = "accounts_backup.json"
PAYLOAD_FILE = "payloads.json"
PAYLOAD_BACKUP = "payloads_backup.json"

STATE_WAIT_SLEEP = 5
MAX_STATE_WAIT = 120
MAX_GAME_RUNNING_WAIT = 60

SPIN = ["|", "/", "-", "\\"]

# ================ DASHBOARD (FIX) ================
def dash_render(header1, header2, bot_lines):
    # Cursor home + clear screen, then redraw (stable in screen)
    sys.stdout.write("\033[H")   # home
    sys.stdout.write("\033[2J")  # clear
    sys.stdout.write(header1 + "\n")
    sys.stdout.write(header2 + "\n")
    for ln in bot_lines:
        sys.stdout.write(ln[:240] + "\n")
    sys.stdout.flush()

def clip(x, n=8):
    x = str(x) if x is not None else "-"
    return x[:n]

def fmt_line(acc, s, spin_i):
    name = acc["name"]
    bal  = str(s.get("moltz", 0))
    gsts = str(s.get("gstatus", "-"))
    turn = str(s.get("turn", "?"))
    hp   = str(s.get("hp", "-"))
    ep   = str(s.get("ep", "-"))
    atk  = str(s.get("atk", "-"))
    deff = str(s.get("def", "-"))
    k    = str(s.get("kills", "-"))
    act  = str(s.get("action", "-"))
    note = str(s.get("note", ""))

    sp = SPIN[spin_i % len(SPIN)]
    return (
        f"{name:<10} [{sp}] "
        f"M={bal:<6} "
        f"G={gsts:<9} T={turn:<4} "
        f"HP={hp:<3} EP={ep:<3} "
        f"A={atk:<3} D={deff:<3} K={k:<2} "
        f"Do={act:<6} "
        f"{note}"
    )

def render_all(accounts, status_map, spin_i, target_game_id=""):
    header1 = f"MODE: one-game | accounts={len(accounts)} | target={clip(target_game_id) if target_game_id else '-'} | BASE_URL={BASE_URL}"
    header2 = "Name       Spin Moltz  Game      Turn HP  EP  A   D   K  Do     Note"
    bot_lines = [fmt_line(acc, status_map[acc["name"]], spin_i) for acc in accounts]
    dash_render(header1, header2, bot_lines)

# ================= Utils =================
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
    except Exception:
        return {"_status": getattr(resp, "status_code", None), "_raw": getattr(resp, "text", "")}

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
        "gameId": acc.get("gameId"),
        "agentId": acc.get("agentId"),
        "payload": payload,
        "timestamp": datetime.utcnow().isoformat()
    }

    with open(PAYLOAD_FILE, "w") as f:
        json.dump(data, f, indent=2)
    with open(PAYLOAD_BACKUP, "w") as f:
        json.dump(data, f, indent=2)

def pick_target_game(headers):
    r = requests.get(f"{BASE_URL}/games?status=waiting", timeout=10)
    games = safe_json(r).get("data", [])
    if games:
        return games[0]
    r = requests.post(f"{BASE_URL}/games", headers=headers, timeout=10)
    return safe_json(r).get("data")

def wait_game_running(game_id, status_map):
    loops = 0
    while True:
        loops += 1
        r = requests.get(f"{BASE_URL}/games/{game_id}", timeout=10)
        res = safe_json(r)
        data = res.get("data", {})
        status = data.get("status")
        turn = data.get("turn", "?")

        for k in status_map:
            status_map[k]["gstatus"] = status or "-"
            status_map[k]["turn"] = turn

        if status == "running":
            return True, data
        if status in ("finished", "cancelled"):
            return False, data
        if loops >= MAX_GAME_RUNNING_WAIT:
            return False, data

        time.sleep(STATE_WAIT_SLEEP)

# ================= SMART STRATEGY =================
def weighted_choice(choices):
    """Weighted random selection"""
    actions = list(choices.keys())
    weights = list(choices.values())
    return random.choices(actions, weights=weights, k=1)[0]

def get_smart_action(hp, ep, atk, defense, turn):
    """Smart strategy - returns action dict"""
    
    # CRITICAL - emergency rest
    if hp <= 20 or ep <= 5:
        return {"type": "rest"}
    
    # LOW RESOURCES - defensive
    if hp < LOW_HP_THRESHOLD or ep <= 10:
        return {"type": "rest"}
    
    # EARLY GAME (1-20): FARM items
    if turn <= 20:
        return weighted_choice({
            "pickup": 0.7,  # 70% pickup
            "move": 0.2,    # 20% move
            "rest": 0.1     # 10% rest
        })
    
    # MID GAME (21-60): Balanced
    elif turn <= 60:
        # Strong stats = fight
        if atk >= 12 and hp >= 45 and ep >= 20:
            return weighted_choice({
                "attack": 0.3,
                "pickup": 0.4,
                "move": 0.2,
                "rest": 0.1
            })
        else:
            # Weak = keep farming
            return weighted_choice({
                "pickup": 0.6,
                "move": 0.3,
                "rest": 0.1
            })
    
    # LATE GAME (61+): Aggressive
    else:
        # BEAST MODE - very strong
        if atk >= 17 and hp >= 60 and ep >= 30:
            return weighted_choice({
                "attack": 0.6,   # 60% attack!
                "move": 0.25,
                "pickup": 0.1,
                "rest": 0.05
            })
        # SURVIVE MODE - weak
        elif atk < 12:
            return weighted_choice({
                "move": 0.5,
                "pickup": 0.3,
                "rest": 0.2
            })
        # BALANCED
        else:
            return weighted_choice({
                "attack": 0.4,
                "move": 0.3,
                "pickup": 0.2,
                "rest": 0.1
            })

# ================= MAIN =================
accounts = load_accounts()
for acc in accounts:
    acc.setdefault("stateWait", 0)

status_map = {
    acc["name"]: {"moltz": 0, "gstatus": "-", "turn": "?", "hp": "-", "ep": "-", "atk": "-", "def": "-", "kills": "-", "action": "-", "note": ""}
    for acc in accounts
}

spin_i = 0
target_game_id = ""

# clear once at start (home+clear)
sys.stdout.write("\033[H\033[2J")
sys.stdout.flush()

while True:
    try:
        render_all(accounts, status_map, spin_i, target_game_id); spin_i += 1

        first_headers = {"X-API-Key": accounts[0]["apiKey"]}
        game = pick_target_game(first_headers)
        if not game:
            for acc in accounts:
                status_map[acc["name"]]["note"] = "ERROR pick/create game"
            render_all(accounts, status_map, spin_i, target_game_id); spin_i += 1
            time.sleep(5)
            continue

        target_game_id = game["id"]
        for acc in accounts:
            status_map[acc["name"]]["note"] = "target set"

        ok, _ = wait_game_running(target_game_id, status_map)
        if not ok:
            for acc in accounts:
                status_map[acc["name"]]["note"] = "waiting game... retry"
            render_all(accounts, status_map, spin_i, target_game_id); spin_i += 1
            time.sleep(2)
            continue

        # register all agents to same game
        for acc in accounts:
            headers = {"X-API-Key": acc["apiKey"]}

            info = get_account_info(acc["apiKey"])
            status_map[acc["name"]]["moltz"] = info.get("balance", 0)

            if acc.get("gameId") != target_game_id or not acc.get("agentId"):
                acc["gameId"] = target_game_id
                status_map[acc["name"]]["note"] = "register..."

                agent = safe_json(
                    requests.post(
                        f"{BASE_URL}/games/{acc['gameId']}/agents/register",
                        headers=headers,
                        json={"name": acc["name"]},
                        timeout=10
                    )
                ).get("data")

                if not agent:
                    status_map[acc["name"]]["note"] = "register failed"
                    render_all(accounts, status_map, spin_i, target_game_id); spin_i += 1
                    time.sleep(1)
                    continue

                acc["agentId"] = agent["id"]
                save_accounts(accounts)
                status_map[acc["name"]]["note"] = "joined"

            render_all(accounts, status_map, spin_i, target_game_id); spin_i += 1

        # action loop
        while True:
            game_info = safe_json(requests.get(f"{BASE_URL}/games/{target_game_id}", timeout=10)).get("data", {})
            status = game_info.get("status")
            turn = game_info.get("turn", "?")
            for acc in accounts:
                status_map[acc["name"]]["gstatus"] = status or "-"
                status_map[acc["name"]]["turn"] = turn

            if status in ("finished", "cancelled"):
                for acc in accounts:
                    acc["gameId"] = None
                    acc["agentId"] = None
                    acc["stateWait"] = 0
                    status_map[acc["name"]]["note"] = f"game {status}, reset"
                save_accounts(accounts)
                render_all(accounts, status_map, spin_i, target_game_id); spin_i += 1
                break

            for acc in accounts:
                headers = {"X-API-Key": acc["apiKey"]}

                # update Moltz (kalau berat, nanti kita bikin interval)
                info = get_account_info(acc["apiKey"])
                status_map[acc["name"]]["moltz"] = info.get("balance", 0)

                r = requests.get(
                    f"{BASE_URL}/games/{acc['gameId']}/agents/{acc['agentId']}/state",
                    headers=headers,
                    timeout=10
                )
                res = safe_json(r)

                if "data" not in res:
                    acc["stateWait"] += 1
                    status_map[acc["name"]]["note"] = f"state wait {acc['stateWait']}"
                    status_map[acc["name"]]["action"] = "-"
                    render_all(accounts, status_map, spin_i, target_game_id); spin_i += 1

                    if acc["stateWait"] >= MAX_STATE_WAIT:
                        acc["gameId"] = None
                        acc["agentId"] = None
                        acc["stateWait"] = 0
                        save_accounts(accounts)
                        status_map[acc["name"]]["note"] = "state timeout, reset"
                        render_all(accounts, status_map, spin_i, target_game_id); spin_i += 1

                    time.sleep(STATE_WAIT_SLEEP)
                    continue

                acc["stateWait"] = 0
                state = res["data"]
                hp = state.get("hp", 0)
                ep = state.get("ep", 0)
                atk = state.get("attack", 0)
                df = state.get("defense", 0)
                kills = state.get("kills", 0)

                status_map[acc["name"]]["hp"] = hp
                status_map[acc["name"]]["ep"] = ep
                status_map[acc["name"]]["atk"] = atk
                status_map[acc["name"]]["def"] = df
                status_map[acc["name"]]["kills"] = kills

                # === SMART STRATEGY (IMPROVED!) ===
                action = get_smart_action(hp, ep, atk, df, turn)

                status_map[acc["name"]]["action"] = action["type"]
                status_map[acc["name"]]["note"] = f"A{atk} D{df} K{kills}"
                render_all(accounts, status_map, spin_i, target_game_id); spin_i += 1

                r = requests.post(
                    f"{BASE_URL}/games/{acc['gameId']}/agents/{acc['agentId']}/action",
                    headers=headers,
                    json={"action": action},
                    timeout=10
                )
                res2 = safe_json(r)

                payload = res2.get("data", {}).get("claimPayload")
                if payload:
                    save_payload(acc, payload)
                    status_map[acc["name"]]["note"] = "payload saved"

                render_all(accounts, status_map, spin_i, target_game_id); spin_i += 1
                time.sleep(random.randint(*ACCOUNT_DELAY))

            time.sleep(ACTION_INTERVAL)

    except Exception as e:
        # jangan print traceback ke layar dashboard
        err = f"{type(e).__name__}"
        for acc in accounts:
            status_map[acc["name"]]["note"] = f"ERROR {err}"
        render_all(accounts, status_map, spin_i, target_game_id); spin_i += 1
        time.sleep(5)

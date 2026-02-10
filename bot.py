import requests, json, time, random, traceback, os, sys
from datetime import datetime
from config import *

ACCOUNTS_FILE = "accounts.json"
ACCOUNTS_BACKUP = "accounts_backup.json"
PAYLOAD_FILE = "payloads.json"
PAYLOAD_BACKUP = "payloads_backup.json"

BLACKLIST_FILE = "blacklist_games.json"

# timings
STATE_WAIT_SLEEP = 5
ACTION_TIMEOUT = (3, 12)     # connect, read [web:206]
INFO_TIMEOUT = (3, 12)

MAX_STATE_WAIT = 120         # 120 * 5s = 10 menit
MAX_GAME_RUNNING_WAIT = 120  # 120 * 5s = 10 menit
MAX_WAITING_SECONDS = 600    # cutloss waiting 10 menit

# dashboard
SPIN = ["|", "/", "-", "\\"]

def dash_render(header1, header2, bot_lines):
    sys.stdout.write("\033[H")   # home [web:115]
    sys.stdout.write("\033[2J")  # clear [web:115]
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
    header1 = f"MOLTY BOT | accounts={len(accounts)} | game={clip(target_game_id) if target_game_id else '-'} | {BASE_URL}"
    header2 = "Name       Spin  Moltz   Game      Turn HP  EP  A   D   K  Do     Note"
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

def load_blacklist():
    if os.path.exists(BLACKLIST_FILE):
        try:
            with open(BLACKLIST_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_blacklist(bl):
    with open(BLACKLIST_FILE, "w") as f:
        json.dump(sorted(list(bl)), f, indent=2)

def blacklist_add(bl, gid):
    if gid:
        bl.add(gid)
        save_blacklist(bl)

def get_account_info(api_key):
    r = requests.get(
        f"{BASE_URL}/accounts/me",
        headers={"X-API-Key": api_key},
        timeout=INFO_TIMEOUT
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

def reset_account(acc):
    acc["gameId"] = None
    acc["agentId"] = None
    acc["stateWait"] = 0

# ---- FINAL: pick only FREE, skip full, skip blacklisted ----
def pick_target_game(headers, blacklist):
    r = requests.get(f"{BASE_URL}/games?status=waiting", timeout=INFO_TIMEOUT)
    games = safe_json(r).get("data", []) or []

    for g in games:
        gid = g.get("id")
        if gid in blacklist:
            continue

        if g.get("entryType") != "free":
            continue

        mc = g.get("maxAgents")
        ac = g.get("agentCount")
        if mc is not None and ac is not None and ac >= mc:
            continue

        return g

    r = requests.post(f"{BASE_URL}/games", headers=headers, timeout=INFO_TIMEOUT)
    return safe_json(r).get("data")

def wait_game_running(game_id, status_map, blacklist):
    start = time.time()
    loops = 0
    while True:
        loops += 1
        r = requests.get(f"{BASE_URL}/games/{game_id}", timeout=INFO_TIMEOUT)
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
            blacklist_add(blacklist, game_id)
            return False, data

        # cutloss waiting too long => blacklist
        if status == "waiting" and (time.time() - start) > MAX_WAITING_SECONDS:
            blacklist_add(blacklist, game_id)
            return False, data

        if loops >= MAX_GAME_RUNNING_WAIT:
            blacklist_add(blacklist, game_id)
            return False, data

        time.sleep(STATE_WAIT_SLEEP)

# ================= SMART STRATEGY =================
def weighted_choice(choices):
    actions = list(choices.keys())
    weights = list(choices.values())
    return random.choices(actions, weights=weights, k=1)[0]

def get_smart_action(hp, ep, atk, defense, turn):
    if hp <= CRITICAL_HP:
        return {"type": "rest"}
    if ep <= CRITICAL_EP:
        return {"type": "rest"}
    if hp < LOW_HP_THRESHOLD:
        return {"type": "rest"}
    if ep < LOW_EP_THRESHOLD:
        if hp < 60:
            return {"type": "rest"}
        return {"type": "move"}

    if turn <= EARLY_GAME_TURNS:
        return {"type": weighted_choice({
            "pickup": EARLY_PICKUP_WEIGHT,
            "move": EARLY_MOVE_WEIGHT,
            "rest": EARLY_REST_WEIGHT
        })}

    if turn <= MID_GAME_TURNS:
        if (atk >= MIN_ATTACK_TO_FIGHT and hp >= MIN_HP_TO_FIGHT and ep >= MIN_EP_TO_FIGHT):
            return {"type": weighted_choice({
                "attack": MID_ATTACK_WEIGHT,
                "pickup": MID_PICKUP_WEIGHT,
                "move": MID_MOVE_WEIGHT,
                "rest": MID_REST_WEIGHT
            })}
        return {"type": weighted_choice({"pickup": 0.6, "move": 0.3, "rest": 0.1})}

    hp_threshold = MIN_HP_TO_FIGHT
    if defense >= DEFENSE_THRESHOLD:
        hp_threshold -= HIGH_DEFENSE_HP_BONUS

    if (atk >= MIN_ATTACK_TO_FIGHT + 5 and hp >= hp_threshold + 15 and ep >= MIN_EP_TO_FIGHT + 10):
        return {"type": weighted_choice({"attack": 0.6, "move": 0.25, "pickup": 0.1, "rest": 0.05})}

    if atk < MIN_ATTACK_TO_FIGHT:
        if ep > 25:
            return {"type": weighted_choice({"pickup": 0.5, "move": 0.35, "rest": 0.15})}
        return {"type": weighted_choice({"move": 0.5, "rest": 0.5})}

    if defense >= DEFENSE_THRESHOLD:
        return {"type": weighted_choice({"attack": 0.45, "move": 0.3, "pickup": 0.15, "rest": 0.1})}

    return {"type": weighted_choice({
        "attack": LATE_ATTACK_WEIGHT,
        "move": LATE_MOVE_WEIGHT,
        "pickup": LATE_PICKUP_WEIGHT,
        "rest": LATE_REST_WEIGHT
    })}

# ================= MAIN =================
accounts = load_accounts()
for acc in accounts:
    acc.setdefault("stateWait", 0)

status_map = {
    acc["name"]: {
        "moltz": 0, "gstatus": "-", "turn": "?",
        "hp": "-", "ep": "-", "atk": "-", "def": "-",
        "kills": "-", "action": "-", "note": "init"
    }
    for acc in accounts
}

blacklist = load_blacklist()

spin_i = 0
target_game_id = ""

sys.stdout.write("\033[H\033[2J")
sys.stdout.flush()

while True:
    try:
        # heartbeat
        render_all(accounts, status_map, spin_i, target_game_id); spin_i += 1

        # pick one target game for ALL
        first_headers = {"X-API-Key": accounts[0]["apiKey"]}
        game = pick_target_game(first_headers, blacklist)

        if not game:
            for acc in accounts:
                status_map[acc["name"]]["note"] = "ERR: no game"
            render_all(accounts, status_map, spin_i, target_game_id); spin_i += 1
            time.sleep(5)
            continue

        target_game_id = game["id"]
        for acc in accounts:
            status_map[acc["name"]]["note"] = "target set"

        ok, gdata = wait_game_running(target_game_id, status_map, blacklist)
        if not ok:
            for acc in accounts:
                status_map[acc["name"]]["note"] = "cutloss/blacklist, repick"
            render_all(accounts, status_map, spin_i, target_game_id); spin_i += 1

            # reset all to allow new pick next loop
            for a in accounts:
                reset_account(a)
            save_accounts(accounts)

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

                resp = safe_json(
                    requests.post(
                        f"{BASE_URL}/games/{acc['gameId']}/agents/register",
                        headers=headers,
                        json={"name": acc["name"]},
                        timeout=ACTION_TIMEOUT
                    )
                )
                agent = resp.get("data")

                if not agent or not agent.get("id"):
                    # blacklist this game if register fails (often full/rules)
                    blacklist_add(blacklist, target_game_id)

                    status_map[acc["name"]]["note"] = f"register FAIL http={resp.get('_status','')} {str(resp.get('_raw',''))[:40]}"
                    reset_account(acc)
                    save_accounts(accounts)

                    render_all(accounts, status_map, spin_i, target_game_id); spin_i += 1
                    time.sleep(1)
                    continue

                acc["agentId"] = agent["id"]
                save_accounts(accounts)
                status_map[acc["name"]]["note"] = "joined OK"

            render_all(accounts, status_map, spin_i, target_game_id); spin_i += 1

        # action loop
        while True:
            game_info = safe_json(
                requests.get(f"{BASE_URL}/games/{target_game_id}", timeout=INFO_TIMEOUT)
            ).get("data", {})

            status = game_info.get("status")
            turn_raw = game_info.get("turn", 0)
            turn = int(turn_raw) if str(turn_raw).isdigit() else 0

            for acc in accounts:
                status_map[acc["name"]]["gstatus"] = status or "-"
                status_map[acc["name"]]["turn"] = turn_raw

            if status in ("finished", "cancelled"):
                blacklist_add(blacklist, target_game_id)
                for acc in accounts:
                    reset_account(acc)
                    status_map[acc["name"]]["note"] = f"END: {status}"
                save_accounts(accounts)
                render_all(accounts, status_map, spin_i, target_game_id); spin_i += 1
                time.sleep(2)
                break

            for acc in accounts:
                # guard
                if not acc.get("agentId"):
                    status_map[acc["name"]]["note"] = "no agentId, rejoin"
                    reset_account(acc)
                    save_accounts(accounts)
                    render_all(accounts, status_map, spin_i, target_game_id); spin_i += 1
                    continue

                headers = {"X-API-Key": acc["apiKey"]}

                info = get_account_info(acc["apiKey"])
                status_map[acc["name"]]["moltz"] = info.get("balance", 0)

                r = requests.get(
                    f"{BASE_URL}/games/{acc['gameId']}/agents/{acc['agentId']}/state",
                    headers=headers,
                    timeout=ACTION_TIMEOUT
                )
                res = safe_json(r)

                if "data" not in res:
                    acc["stateWait"] += 1
                    status_map[acc["name"]]["note"] = f"wait {acc['stateWait']}"
                    status_map[acc["name"]]["action"] = "-"
                    render_all(accounts, status_map, spin_i, target_game_id); spin_i += 1

                    if acc["stateWait"] >= MAX_STATE_WAIT:
                        status_map[acc["name"]]["note"] = "TIMEOUT reset"
                        reset_account(acc)
                        save_accounts(accounts)
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

                action = get_smart_action(hp, ep, atk, df, turn)

                if turn <= EARLY_GAME_TURNS:
                    phase = "FARM"
                elif turn <= MID_GAME_TURNS:
                    phase = "MID"
                else:
                    phase = "LATE"

                status_map[acc["name"]]["action"] = action["type"]
                status_map[acc["name"]]["note"] = f"{phase} A{atk} D{df} K{kills}"
                render_all(accounts, status_map, spin_i, target_game_id); spin_i += 1

                r = requests.post(
                    f"{BASE_URL}/games/{acc['gameId']}/agents/{acc['agentId']}/action",
                    headers=headers,
                    json={"action": action},
                    timeout=ACTION_TIMEOUT
                )
                res2 = safe_json(r)

                payload = res2.get("data", {}).get("claimPayload")
                if payload:
                    save_payload(acc, payload)
                    status_map[acc["name"]]["note"] = f"{phase} SAVED"

                render_all(accounts, status_map, spin_i, target_game_id); spin_i += 1
                time.sleep(random.randint(*ACCOUNT_DELAY))

            time.sleep(ACTION_INTERVAL)

    except KeyboardInterrupt:
        print("\n\nBot stopped by user (Ctrl+C)")
        save_accounts(accounts)
        sys.exit(0)

    except Exception as e:
        err = f"{type(e).__name__}"
        for acc in accounts:
            status_map[acc["name"]]["note"] = f"ERR: {err}"
        render_all(accounts, status_map, spin_i, target_game_id); spin_i += 1
        time.sleep(5)

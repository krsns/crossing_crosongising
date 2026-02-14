import requests, json, time, random, os, sys
from datetime import datetime
from config import *

ACCOUNTS_FILE = "accounts.json"

STATE_WAIT_SLEEP = 5
ACTION_INTERVAL = 3
ACCOUNT_DELAY = (2, 4)
MAX_WAIT_RUNNING = 120
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3

# Slot checking configuration
MIN_FREE_SLOTS = 5  # Minimal slot kosong yang dibutuhkan
CHECK_SLOTS_ENABLED = True  # Set False untuk disable slot checking

# Retry configuration
RETRY_FAILED_REGISTRATION = True  # Retry register yang gagal saat game running
RETRY_INTERVAL = 15  # Retry setiap 15 detik

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
        data = json.load(f)
        for acc in data:
            # Clean up old formats
            if "stateWait" in acc:
                del acc["stateWait"]
            if "token" in acc and "apiKey" not in acc:
                acc["apiKey"] = acc["token"]
                del acc["token"]
            # Add last retry timestamp
            if "lastRetryTime" not in acc:
                acc["lastRetryTime"] = 0
        return data

def save_accounts(accs):
    with open(ACCOUNTS_FILE, "w") as f:
        json.dump(accs, f, indent=2)

def retry_request(func, max_retries=MAX_RETRIES):
    """Retry a request function up to max_retries times"""
    for attempt in range(max_retries):
        try:
            return func()
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                raise
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                raise
    return None

# ================= GAME SELECTION =================

def get_game_info(game_id):
    """Get detailed info about a game"""
    try:
        r = requests.get(f"{BASE_URL}/games/{game_id}", timeout=REQUEST_TIMEOUT)
        return safe_json(r).get("data", {})
    except:
        return {}

def find_suitable_game():
    """Find a game with enough free slots (if slot checking enabled)"""
    try:
        r = retry_request(lambda: requests.get(
            f"{BASE_URL}/games?status=waiting", 
            timeout=REQUEST_TIMEOUT
        ))
        games = safe_json(r).get("data", [])
    except:
        games = []

    if not games:
        log("  [i] No waiting games found")
        return None
    
    if not CHECK_SLOTS_ENABLED:
        # Just return first available game
        for g in games:
            gid = g.get("id")
            if gid and gid not in BLOCKED_GAMES:
                log(f"  [+] Found game {gid[:8]}... (slot checking disabled)")
                return g
        return None
    
    # Check slots for each game
    log(f"  Found {len(games)} waiting game(s), checking slots...")
    
    for game in games:
        game_id = game.get("id")
        if not game_id or game_id in BLOCKED_GAMES:
            continue
        
        # Get detailed game info
        game_info = get_game_info(game_id)
        max_players = game_info.get("maxPlayers", 10)
        current_agents = len(game_info.get("agents", []))
        free_slots = max_players - current_agents
        
        log(f"  [*] Game {game_id[:8]}... : {current_agents}/{max_players} players ({free_slots} free)")
        
        if free_slots >= MIN_FREE_SLOTS:
            log(f"  [+] Selected game with {free_slots} free slots!")
            return game
    
    log(f"  [-] No game found with {MIN_FREE_SLOTS}+ free slots")
    return None

# ================= REGISTRATION =================

def get_agent_id_from_game(game_id, agent_name, headers):
    """Recover agentId by fetching game details and finding agent by name"""
    try:
        r = requests.get(f"{BASE_URL}/games/{game_id}", timeout=REQUEST_TIMEOUT)
        game_data = safe_json(r).get("data", {})
        agents = game_data.get("agents", [])
        
        for agent in agents:
            if agent.get("name") == agent_name:
                agent_id = agent.get("id")
                return agent_id
    except Exception as e:
        pass
    return None

def register_agent_robust(acc, game_id, attempt_num=1, max_attempts=3):
    """Register agent with retry and recovery"""
    headers = {"X-API-Key": acc["apiKey"]}
    
    if attempt_num == 1:
        log(f"  -> Registering {acc['name']}...")
    else:
        log(f"  -> Retry {attempt_num}/{max_attempts} for {acc['name']}...")
    
    try:
        r = requests.post(
            f"{BASE_URL}/games/{game_id}/agents/register",
            headers=headers,
            json={"name": acc["name"]},
            timeout=REQUEST_TIMEOUT
        )
        
        result = safe_json(r)
        agent = result.get("data")
        
        if agent and agent.get("id"):
            acc["agentId"] = agent["id"]
            acc["gameId"] = game_id
            acc["lastRetryTime"] = time.time()
            log(f"  [+] {acc['name']} joined! (ID: {agent['id'][:8]}...)")
            return True
        else:
            # No agent data, try recovery
            log(f"  [!] No agent data returned, trying recovery...")
            time.sleep(2)
            
    except requests.exceptions.Timeout:
        log(f"  [!] Registration timeout, trying recovery...")
        time.sleep(2)
    except Exception as e:
        log(f"  [-] Error: {type(e).__name__}")
        time.sleep(1)
    
    # Try to recover agentId from game state
    recovered_id = get_agent_id_from_game(game_id, acc["name"], headers)
    if recovered_id:
        acc["agentId"] = recovered_id
        acc["gameId"] = game_id
        acc["lastRetryTime"] = time.time()
        log(f"  [+] {acc['name']} recovered! (ID: {recovered_id[:8]}...)")
        return True
    
    # Retry if attempts remaining
    if attempt_num < max_attempts:
        wait_time = 3 * attempt_num
        log(f"  [~] Waiting {wait_time}s before retry...")
        time.sleep(wait_time)
        return register_agent_robust(acc, game_id, attempt_num + 1, max_attempts)
    
    log(f"  [-] {acc['name']} failed after {max_attempts} attempts")
    return False

def retry_failed_accounts(accounts, game_id):
    """Retry registration for accounts that failed"""
    failed = [acc for acc in accounts 
              if acc.get("gameId") == game_id and not acc.get("agentId")]
    
    if not failed:
        return 0
    
    log(f"\n[~] RETRYING {len(failed)} FAILED ACCOUNT(S):")
    success_count = 0
    
    for acc in failed:
        if register_agent_robust(acc, game_id, max_attempts=2):
            success_count += 1
            save_accounts(accounts)
            time.sleep(random.uniform(1, 2))
    
    return success_count

def wait_until_running(game_id, total_bots):
    """Wait for game to start"""
    log("[...] Waiting for game to start...")
    for i in range(MAX_WAIT_RUNNING):
        try:
            r = requests.get(f"{BASE_URL}/games/{game_id}", timeout=REQUEST_TIMEOUT)
            data = safe_json(r).get("data", {})
            status = data.get("status")
            
            if status == "running":
                log("[+] GAME STARTED!")
                return True
            if status in ("finished", "cancelled"):
                log("[-] Game cancelled/finished before starting")
                return False
            
            # Show player count every 10 seconds
            if i % 5 == 0:
                agents = data.get("agents", [])
                log(f"  Waiting... ({len(agents)} players in game)")
                
        except:
            pass
        time.sleep(2)
    
    log("[-] Timeout waiting for game to start")
    return False

# ================= STRATEGY =================

def weighted_choice(choices):
    actions = list(choices.keys())
    weights = list(choices.values())
    return random.choices(actions, weights=weights, k=1)[0]

def get_smart_action(hp, ep, atk, defense, turn):
    turn = safe_int(turn)

    # Critical conditions - always rest
    if hp <= CRITICAL_HP:
        return {"type": "rest"}
    if ep <= CRITICAL_EP:
        return {"type": "rest"}
    
    # Low HP - rest
    if hp < LOW_HP_THRESHOLD:
        return {"type": "rest"}
    
    # Low EP - rest or move
    if ep < LOW_EP_THRESHOLD:
        return {"type": "rest"} if hp < 60 else {"type": "move"}

    # Early game - gather resources
    if turn <= EARLY_GAME_TURNS:
        return {"type": weighted_choice({
            "pickup": EARLY_PICKUP_WEIGHT,
            "move": EARLY_MOVE_WEIGHT,
            "rest": EARLY_REST_WEIGHT
        })}

    # Mid game - balanced approach
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

    # Late game - aggressive
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

# ================= MAIN LOOP =================

accounts = load_accounts()
last_retry_time = 0

log("=" * 70)
log("ULTIMATE BOT v2.0")
log(f"Accounts: {len(accounts)}")
log(f"Min free slots: {MIN_FREE_SLOTS} (enabled: {CHECK_SLOTS_ENABLED})")
log(f"Auto-retry failed: {RETRY_FAILED_REGISTRATION} (interval: {RETRY_INTERVAL}s)")
log("=" * 70)

while True:
    try:
        # Find suitable game
        log("\n[...] Searching for game...")
        game = find_suitable_game()
        
        if not game:
            log("[!] No suitable game, waiting 10s...")
            time.sleep(10)
            continue

        game_id = game["id"]
        log(f"\n[*] TARGET GAME: {game_id}")
        log("=" * 70)

        # Register all accounts
        log("\n[>>] REGISTERING ACCOUNTS:")
        successful = 0
        
        for i, acc in enumerate(accounts, 1):
            # Reset if different game
            if acc.get("gameId") != game_id:
                acc["gameId"] = None
                acc["agentId"] = None
            
            # Skip if already registered
            if acc.get("agentId") and acc.get("gameId") == game_id:
                log(f"  [+] {acc['name']} already in this game")
                successful += 1
                continue
            
            # Register with retry
            if register_agent_robust(acc, game_id):
                successful += 1
                save_accounts(accounts)
            
            # Delay between registrations
            if i < len(accounts):
                time.sleep(random.uniform(1.5, 3))

        log(f"\n[*] REGISTRATION RESULT: {successful}/{len(accounts)} successful")
        
        if successful == 0:
            log("[-] All registrations failed, retrying in 5s...")
            time.sleep(5)
            continue
        
        save_accounts(accounts)

        # Wait for game to start
        if not wait_until_running(game_id, len(accounts)):
            log("[-] Game didn't start, resetting and retrying...")
            for acc in accounts:
                acc["gameId"] = None
                acc["agentId"] = None
            save_accounts(accounts)
            time.sleep(5)
            continue

        # ================= GAME ACTION LOOP =================
        log("\n" + "=" * 70)
        log("[>>] GAME RUNNING")
        log("=" * 70 + "\n")
        
        last_retry_time = time.time()
        
        while True:
            # Get game status
            try:
                r = requests.get(f"{BASE_URL}/games/{game_id}", timeout=REQUEST_TIMEOUT)
                game_info = safe_json(r).get("data", {})
                status = game_info.get("status")
                turn = game_info.get("turn")
            except:
                log("[!] Timeout fetching game info")
                time.sleep(5)
                continue

            # Check if game finished
            if status in ("finished", "cancelled"):
                log("\n" + "=" * 70)
                log("[X] GAME FINISHED")
                log("=" * 70)
                for acc in accounts:
                    acc["gameId"] = None
                    acc["agentId"] = None
                save_accounts(accounts)
                break

            # Retry failed registrations periodically
            if RETRY_FAILED_REGISTRATION:
                current_time = time.time()
                if current_time - last_retry_time >= RETRY_INTERVAL:
                    last_retry_time = current_time
                    retry_count = retry_failed_accounts(accounts, game_id)
                    if retry_count > 0:
                        log(f"  [+] Recovered {retry_count} account(s)\n")

            # Execute actions for all active bots
            active_bots = 0
            for acc in accounts:
                # Skip if not registered
                if not acc.get("agentId") or acc.get("gameId") != game_id:
                    continue
                
                active_bots += 1
                headers = {"X-API-Key": acc["apiKey"]}

                try:
                    # Get agent state
                    r = retry_request(lambda: requests.get(
                        f"{BASE_URL}/games/{acc['gameId']}/agents/{acc['agentId']}/state",
                        headers=headers,
                        timeout=REQUEST_TIMEOUT
                    ))

                    state = safe_json(r).get("data")
                    if not state:
                        continue

                    hp = state.get("hp", 0)
                    ep = state.get("ep", 0)
                    atk = state.get("attack", 0)
                    defense = state.get("defense", 0)

                    # Get action from strategy
                    action = get_smart_action(hp, ep, atk, defense, turn)

                    # Log and execute action
                    log(f"[T{turn:02d}] {acc['name']:12s} HP{hp:3d} EP{ep:2d} A{atk:2d} D{defense:2d} -> {action['type']}")

                    r2 = retry_request(lambda: requests.post(
                        f"{BASE_URL}/games/{acc['gameId']}/agents/{acc['agentId']}/action",
                        headers=headers,
                        json=action,
                        timeout=REQUEST_TIMEOUT
                    ))

                    res2 = safe_json(r2)
                    if "error" in res2:
                        error_msg = res2.get("error", {}).get("message", "Unknown error")
                        log(f"     [-] ERROR: {error_msg}")

                except requests.exceptions.Timeout:
                    log(f"     [!] {acc['name']} timeout - skipping turn")
                except Exception as e:
                    log(f"     [-] {acc['name']} error: {type(e).__name__}")

                # Delay between bot actions
                time.sleep(random.randint(*ACCOUNT_DELAY))

            if active_bots == 0:
                log("[!] WARNING: No active bots found!")
            
            # Delay before next turn
            time.sleep(ACTION_INTERVAL)

    except KeyboardInterrupt:
        log("\n" + "=" * 70)
        log("[X] BOT STOPPED BY USER")
        log("=" * 70)
        save_accounts(accounts)
        break

    except Exception as e:
        log(f"\n[-] CRITICAL ERROR: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        time.sleep(5)

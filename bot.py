# -*- coding: utf-8 -*-
import requests, json, time, random, os, sys
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.columns import Columns
from rich import box

# ===== CONFIG =====
BASE_URL              = "https://cdn.moltyroyale.com/api"
ACCOUNTS_FILE         = "accounts.json"
ACTION_INTERVAL       = 60
ACCOUNT_DELAY         = (2, 4)
MAX_WAIT_RUNNING      = 120
REQUEST_TIMEOUT       = 30
MAX_RETRIES           = 3
MAX_PLAYERS_THRESHOLD = 96
RETRY_FAILED_REGISTRATION = True
RETRY_INTERVAL        = 15
BLOCKED_GAMES         = {"8bb2d5a8-ccd6-4201-9e53-11e96dc8bac0"}
ATTACK_AGENTS         = True
HP_HEAL_THRESHOLD     = 30
EP_REST_THRESHOLD     = 2
WALLET_ADDRESS        = "0xcbfa0a05dc8F849C44A270D39DFcD50268F2825B"
MAX_INVENTORY         = 9

console = Console()

# ===== LOGGER =====
def log(msg):
    console.print(f"[dim]{datetime.now().strftime('%H:%M:%S')}[/dim]  {msg}")

def log_ok(msg):
    console.print(f"[dim]{datetime.now().strftime('%H:%M:%S')}[/dim]  [bold green][OK][/bold green]  {msg}")

def log_err(msg):
    console.print(f"[dim]{datetime.now().strftime('%H:%M:%S')}[/dim]  [bold red][ERR][/bold red] {msg}")

def log_info(msg):
    console.print(f"[dim]{datetime.now().strftime('%H:%M:%S')}[/dim]  [bold cyan][..][/bold cyan]  {msg}")

def log_warn(msg):
    console.print(f"[dim]{datetime.now().strftime('%H:%M:%S')}[/dim]  [bold yellow][!!][/bold yellow] {msg}")

def print_banner():
    panel = Panel(
        Text.assemble(
            ("  MOLTY ROYALE BOT v5.0\n", "bold magenta"),
            (f"  Bots     : ", "dim"), (f"{len(load_accounts_raw())} accounts\n", "bold white"),
            (f"  Interval : ", "dim"), (f"{ACTION_INTERVAL}s per turn\n", "bold white"),
            (f"  PvP      : ", "dim"), ("ENABLED\n" if ATTACK_AGENTS else "DISABLED\n",
                                        "bold green" if ATTACK_AGENTS else "bold red"),
            (f"  Heal <   : ", "dim"), (f"HP {HP_HEAL_THRESHOLD} | EP {EP_REST_THRESHOLD}\n", "bold white"),
        ),
        title="[bold magenta]? MOLTY ROYALE[/bold magenta]",
        border_style="magenta",
        box=box.DOUBLE_EDGE,
        expand=False
    )
    console.print(panel)

def print_game_header(game_id):
    console.print(Panel(
        f"[bold yellow]GAME ID:[/bold yellow] [white]{game_id}[/white]",
        title="[bold green]GAME FOUND[/bold green]",
        border_style="green",
        box=box.HEAVY,
        expand=False
    ))

def print_turn_table(turn, bots_data):
    """bots_data = list of dict: name, hp, ep, atk, defense, region, action, alive"""
    table = Table(
        title=f"[bold cyan]Turn {turn:02d}[/bold cyan]",
        box=box.SIMPLE_HEAVY,
        border_style="cyan",
        show_lines=False,
        expand=False
    )
    table.add_column("Bot",     style="bold white",  min_width=12)
    table.add_column("HP",      justify="right",     min_width=5)
    table.add_column("EP",      justify="right",     min_width=5)
    table.add_column("ATK",     justify="right",     min_width=5)
    table.add_column("DEF",     justify="right",     min_width=5)
    table.add_column("Region",  style="dim",         min_width=8)
    table.add_column("Action",  style="bold yellow", min_width=20)

    for b in bots_data:
        if not b.get("alive", True):
            table.add_row(
                b.get("name", "?"),
                Text("DEAD", style="bold red"),
                "-", "-", "-", "-", "-", "-",
                Text("---", style="dim")
            )
            continue

        hp_val     = b.get("hp", 0)
        hp_color   = "green" if hp_val >= 60 else ("yellow" if hp_val >= 30 else "red")
        molt_val   = b.get("molt", 0)
        molt_color = "gold1" if molt_val > 0 else "dim"

        table.add_row(
            b.get("name", "?"),
            Text(str(hp_val), style=f"bold {hp_color}"),
            str(b.get("ep", 0)),
            str(b.get("atk", 0)),
            str(b.get("defense", 0)),
            Text(f"[MOLT]{molt_val}", style=f"bold {molt_color}"),
            str(b.get("region", "?"))[:8],
            b.get("action", "?")
        )

    console.print(table)

def print_result(name, rank, is_winner, reward, molt=0):
    style = "bold gold1" if is_winner else "bold white"
    icon  = "??" if is_winner else "??"
    console.print(Panel(
        Text.assemble(
            (f"{icon} {name}\n", style),
            ("Rank   : ", "dim"), (f"#{rank}\n", "bold white"),
            ("Winner : ", "dim"), (("YES ??\n" if is_winner else "No\n"), "bold green" if is_winner else "dim"),
            ("Reward : ", "dim"), (f"{reward} pts\n", "bold yellow"),
        ),
        title="[bold]GAME RESULT[/bold]",
        border_style="gold1" if is_winner else "white",
        box=box.ROUNDED,
        expand=False
    ))

# ===== HELPERS =====
def fetch_claim_payload(acc):
    headers = get_headers(acc)
    endpoints = [
        '/accounts/me/claim',
        '/accounts/me/rewards',
        '/accounts/me',
    ]
    for ep in endpoints:
        try:
            r = requests.get(f"{BASE_URL}{ep}", headers=headers, timeout=REQUEST_TIMEOUT)
            data = safe_json(r)
            if data.get("success") or data.get("data"):
                inner = data.get("data", data)
                payload = (
                    inner.get("claimPayload")
                    or inner.get("payload")
                    or inner.get("claim")
                    or inner.get("claimData")
                    or None
                )
                molt = (
                    inner.get("molt")
                    or inner.get("earnings")
                    or inner.get("rewards")
                    or inner.get("balance")
                    or 0
                )
                cross = round(molt * 0.01, 6)
                if payload or molt:
                    return {"payload": payload, "molt": molt, "cross": cross, "endpoint": ep}
        except:
            pass
    return None

def print_claim_panel(acc, claim_data):
    if not claim_data:
        console.print(Panel(
            "[yellow]Tidak ada payload untuk [bold]" + acc["name"] + "[/bold][/yellow]",
            title="[bold]CLAIM[/bold]",
            border_style="yellow",
            box=box.ROUNDED,
            expand=False
        ))
        return
    payload  = claim_data.get("payload")
    molt     = claim_data.get("molt", 0)
    cross    = claim_data.get("cross", 0)
    ep       = claim_data.get("endpoint", "-")
    pay_str  = str(payload) if payload else "[red]Tidak ada payload[/red]"
    body = (
        "[bold gold1][MOLT] " + acc["name"] + "[/bold gold1]\n"
        + "[dim]Moltz    :[/dim] [bold white]"  + str(molt)  + "[/bold white]\n"
        + "[dim]CROSS    :[/dim] [bold green]"  + str(cross) + " CROSS[/bold green]\n"
        + "[dim]Rate     :[/dim] [dim]1 Moltz = 0.01 CROSS[/dim]\n"
        + "[dim]Endpoint :[/dim] [dim]"         + str(ep)    + "[/dim]\n"
        + "[dim]Payload  :[/dim] [bold cyan]"   + pay_str    + "[/bold cyan]"
    )
    console.print(Panel(
        body,
        title="[bold gold1]CLAIM PAYLOAD[/bold gold1]",
        border_style="gold1",
        box=box.DOUBLE_EDGE,
        expand=False
    ))

def safe_json(r):
    try:    return r.json()
    except: return {}

def retry_request(func, max_retries=MAX_RETRIES):
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                log_err(f"Request gagal: {type(e).__name__}: {e}")
    return None

def get_headers(acc):
    return {"X-API-Key": acc["apiKey"], "Content-Type": "application/json"}

# ===== ACCOUNTS =====
def load_accounts_raw():
    if not os.path.exists(ACCOUNTS_FILE):
        return []
    with open(ACCOUNTS_FILE) as f:
        return json.load(f)

def load_accounts():
    if not os.path.exists(ACCOUNTS_FILE):
        log_err("accounts.json tidak ada!")
        sys.exit(1)
    with open(ACCOUNTS_FILE) as f:
        data = json.load(f)
    for acc in data:
        if "stateWait" in acc:   del acc["stateWait"]
        if "token" in acc and "apiKey" not in acc:
            acc["apiKey"] = acc.pop("token")
        acc.setdefault("gameId",        None)
        acc.setdefault("agentId",       None)
        acc.setdefault("lastRetryTime", 0)
    return data

def save_accounts(accs):
    with open(ACCOUNTS_FILE, "w") as f:
        json.dump(accs, f, indent=2)

# ===== GAME FINDER =====
def get_game_info(game_id):
    try:
        r = requests.get(f"{BASE_URL}/games/{game_id}", timeout=REQUEST_TIMEOUT)
        return safe_json(r).get("data", {})
    except:
        return {}

def find_suitable_game():
    try:
        r     = retry_request(lambda: requests.get(
            f"{BASE_URL}/games?status=waiting", timeout=REQUEST_TIMEOUT))
        games = safe_json(r).get("data", [])
    except:
        games = []

    if not games:
        return None

    log_info(f"Found [bold]{len(games)}[/bold] waiting game(s)")
    for g in games:
        gid = g.get("id")
        if not gid or gid in BLOCKED_GAMES:
            continue
        game_info      = get_game_info(gid)
        current_agents = len(game_info.get("agents", []))
        if current_agents > MAX_PLAYERS_THRESHOLD:
            log_warn(f"Skip [dim]{gid[:8]}...[/dim] ({current_agents} players, too many)")
            continue
        log_ok(f"Game [cyan]{gid[:8]}...[/cyan] ([green]{current_agents}[/green] players)")
        return g
    return None

# ===== REGISTRATION =====
def get_agent_id_from_game(game_id, agent_name):
    try:
        r      = requests.get(f"{BASE_URL}/games/{game_id}", timeout=REQUEST_TIMEOUT)
        agents = safe_json(r).get("data", {}).get("agents", [])
        for agent in agents:
            if agent.get("name") == agent_name:
                return agent.get("id")
    except:
        pass
    return None

def register_agent(acc, game_id):
    headers = get_headers(acc)
    log_info(f"Registering [bold]{acc['name']}[/bold]...")

    try:
        r      = requests.post(
            f"{BASE_URL}/games/{game_id}/agents/register",
            headers=headers,
            json={"name": acc["name"]},
            timeout=45
        )
        result = safe_json(r)

        if result.get("success"):
            agent = result.get("data", {})
            if agent.get("id"):
                acc["agentId"] = agent["id"]
                acc["gameId"]  = game_id
                log_ok(f"[bold]{acc['name']}[/bold] registered! ID: [dim]{agent['id'][:8]}...[/dim]")
                return True

        error_code = result.get("error", {}).get("code", "")
        if error_code == "ONE_AGENT_PER_API_KEY":
            log_info(f"[bold]{acc['name']}[/bold] already in THIS game, recovering...")
            time.sleep(2)
            recovered_id = get_agent_id_from_game(game_id, acc["name"])
            if recovered_id:
                acc["agentId"] = recovered_id
                acc["gameId"]  = game_id
                log_ok(f"[bold]{acc['name']}[/bold] recovered!")
                return True
            return False
        if error_code == "ACCOUNT_ALREADY_IN_GAME":
            log_warn(f"[bold]{acc['name']}[/bold] in another game, skip...")
            return False

    except Exception as e:
        log_err(f"[bold]{acc['name']}[/bold] timeout: {type(e).__name__}, checking...")

    for check_num in range(8):
        time.sleep(5)
        recovered_id = get_agent_id_from_game(game_id, acc["name"])
        if recovered_id:
            acc["agentId"] = recovered_id
            acc["gameId"]  = game_id
            log_ok(f"[bold]{acc['name']}[/bold] recovered after [yellow]{(check_num+1)*5}s[/yellow]!")
            return True

    log_err(f"[bold]{acc['name']}[/bold] registration failed")
    return False

def retry_failed_registrations(accounts, game_id):
    failed = [a for a in accounts
              if a.get("gameId") == game_id and not a.get("agentId")]
    if not failed:
        return 0
    log_info(f"Retrying [yellow]{len(failed)}[/yellow] failed bot(s)...")
    success = 0
    for acc in failed:
        if register_agent(acc, game_id):
            success += 1
            save_accounts(accounts)
    return success

# ===== WAIT GAME START =====
def wait_game_start(game_id):
    log_info("Waiting for game to start...")
    for i in range(MAX_WAIT_RUNNING):
        try:
            r      = requests.get(f"{BASE_URL}/games/{game_id}", timeout=REQUEST_TIMEOUT)
            data   = safe_json(r).get("data", {})
            status = data.get("status")
            if status == "running":
                console.print(Panel(
                    "[bold green]Game is now RUNNING![/bold green]",
                    border_style="green", box=box.HEAVY, expand=False
                ))
                return True
            if status in ("finished", "cancelled"):
                log_err(f"Game [yellow]{status}[/yellow] before starting")
                return False
            if i % 5 == 0:
                agents = data.get("agents", [])
                log_info(f"Waiting... ([bold]{len(agents)}[/bold] players joined)")
        except:
            pass
        time.sleep(2)
    log_err("Timeout waiting for game start")
    return False

# ===== FREE ACTIONS =====
def do_free_actions(state, acc, game_id, agent_id):
    headers    = get_headers(acc)
    self_state = state.get("self", {})
    inventory  = self_state.get("inventory", [])

    if len(inventory) < MAX_INVENTORY:
        current_region = self_state.get("regionId")
        for item_entry in state.get("visibleItems", []):
            if item_entry.get("regionId") == current_region:
                item_id = item_entry.get("item", {}).get("id")
                if not item_id:
                    continue
                try:
                    requests.post(
                        f"{BASE_URL}/games/{game_id}/agents/{agent_id}/action",
                        headers=headers,
                        json={"action": {"type": "pickup", "itemId": item_id}},
                        timeout=10
                    )
                except:
                    pass
                break  # satu pickup per turn

    weapons = [i for i in inventory if i.get("category") == "weapon"]
    if weapons:
        weapons.sort(key=lambda w: w.get("atkBonus", 0), reverse=True)
        best_weapon  = weapons[0]
        equipped     = self_state.get("equippedWeapon") or {}
        equipped_atk = equipped.get("atkBonus", 0) if isinstance(equipped, dict) else 0
        if best_weapon.get("atkBonus", 0) > equipped_atk:
            try:
                requests.post(
                    f"{BASE_URL}/games/{game_id}/agents/{agent_id}/action",
                    headers=headers,
                    json={"action": {"type": "equip", "itemId": best_weapon["id"]}},
                    timeout=10
                )
                log_ok(f"[bold]{acc['name']}[/bold] equip [magenta]{best_weapon.get('name','weapon')}[/magenta] "
                       f"([green]+{best_weapon.get('atkBonus',0)} ATK[/green])")
            except:
                pass

# ===== DECIDE ACTION =====
def get_action(state):
    self_state     = state.get("self", {})
    current_region = state.get("currentRegion", {})
    hp             = self_state.get("hp", 0)
    ep             = self_state.get("ep", 0)
    max_hp         = self_state.get("maxHp", hp)
    atk            = self_state.get("atk", 0)
    self_region_id = self_state.get("regionId")
    inventory      = self_state.get("inventory", [])

    if current_region.get("isDeathZone"):
        connections = current_region.get("connections", [])
        if connections:
            return {"type": "move", "regionId": connections[0]}, "[red]ESCAPE death zone[/red]"

    if hp < HP_HEAL_THRESHOLD:
        heal_items = [i for i in inventory if i.get("category") == "recovery"]
        if heal_items:
            best_heal = max(heal_items, key=lambda i: i.get("healValue", 0))
            return {"type": "use_item", "itemId": best_heal["id"]}, f"[green]HEAL (HP={hp})[/green]"

    if hp < max_hp * 0.25:
        connections = current_region.get("connections", [])
        if connections:
            return {"type": "move", "regionId": connections[0]}, "[red]FLEE low HP[/red]"

    if ep < EP_REST_THRESHOLD:
        return {"type": "rest"}, f"[yellow]REST (EP={ep})[/yellow]"

    if ATTACK_AGENTS and ep >= 2:
        visible = [a for a in state.get("visibleAgents", [])
                   if a.get("regionId") == self_region_id
                   and a.get("isAlive")
                   and a.get("id") != self_state.get("id")]
        if visible:
            weak_targets = [a for a in visible if atk > a.get("def", 0)]
            if weak_targets:
                target = min(weak_targets, key=lambda a: a.get("hp", 9999))
                return ({"type": "attack", "targetId": target["id"], "targetType": "agent"},
                        f"[red]ATTACK[/red] [bold]{target.get('name','?')}[/bold] (HP={target.get('hp','?')})")

    for monster in state.get("visibleMonsters", []):
        if monster.get("regionId") == self_region_id:
            if monster.get("hp", 9999) < hp * 2:
                return ({"type": "attack", "targetId": monster["id"], "targetType": "monster"},
                        f"[orange3]HUNT[/orange3] [bold]{monster.get('name','?')}[/bold]")

    return {"type": "explore"}, "[cyan]EXPLORE[/cyan]"

# ===== MAIN =====
def main():
    accounts = load_accounts()
    print_banner()

    while True:
        try:
            # ---- FIND GAME ----
            log_info("Finding suitable game...")
            game = find_suitable_game()
            if not game:
                log_err("No suitable game found, retry in 10s...")
                time.sleep(10)
                continue

            game_id = game["id"]
            print_game_header(game_id)

            # ---- REGISTER ----
            console.rule("[bold cyan]REGISTERING BOTS[/bold cyan]")
            successful = 0
            for i, acc in enumerate(accounts, 1):
                if acc.get("gameId") != game_id:
                    acc["gameId"]  = None
                    acc["agentId"] = None

                if acc.get("agentId") and acc.get("gameId") == game_id:
                    log_ok(f"[bold]{acc['name']}[/bold] already in game")
                    successful += 1
                    continue

                if register_agent(acc, game_id):
                    successful += 1
                    save_accounts(accounts)
                else:
                    break  # game penuh/error, skip sisa bot, cari game baru

                if i < len(accounts):
                    time.sleep(random.uniform(*ACCOUNT_DELAY))

            console.print(f"\n  [bold]Registered:[/bold] [green]{successful}[/green]/[white]{len(accounts)}[/white] bots\n")
            if successful == 0:
                time.sleep(5)
                continue

            save_accounts(accounts)

            # ---- WAIT START ----
            if not wait_game_start(game_id):
                for acc in accounts:
                    acc["gameId"] = acc["agentId"] = None
                save_accounts(accounts)
                time.sleep(5)
                continue

            # ---- GAME LOOP ----
            console.rule("[bold green]GAME STARTED - PLAYING[/bold green]")
            last_retry = time.time()

            while True:
                try:
                    r         = requests.get(f"{BASE_URL}/games/{game_id}", timeout=REQUEST_TIMEOUT)
                    game_info = safe_json(r).get("data", {})
                    status    = game_info.get("status")
                    turn      = game_info.get("turn", 0)
                except:
                    log_err("Timeout cek game status")
                    time.sleep(5)
                    continue

                if status in ("finished", "cancelled"):
                    console.rule(f"[bold red]GAME {status.upper()}[/bold red]")
                    for acc in accounts:
                        if acc.get("gameId") == game_id:
                            acc["gameId"]  = None
                            acc["agentId"] = None
                    save_accounts(accounts)
                    break

                if RETRY_FAILED_REGISTRATION and time.time() - last_retry >= RETRY_INTERVAL:
                    last_retry = time.time()
                    retry_failed_registrations(accounts, game_id)

                # Per-account action
                bots_data = []
                active    = 0

                for acc in accounts:
                    if not acc.get("agentId") or acc.get("gameId") != game_id:
                        continue

                    headers  = get_headers(acc)
                    gid_snap = acc["gameId"]
                    aid_snap = acc["agentId"]

                    try:
                        r_state = retry_request(lambda g=gid_snap, a=aid_snap: requests.get(
                            f"{BASE_URL}/games/{g}/agents/{a}/state",
                            headers=headers, timeout=REQUEST_TIMEOUT))
                        if r_state is None:
                            continue

                        state = safe_json(r_state).get("data")
                        if not state:
                            continue

                        self_state = state.get("self", {})

                        if not self_state.get("isAlive"):
                            bots_data.append({"name": acc["name"], "alive": False})
                            acc["gameId"]  = None
                            acc["agentId"] = None
                            save_accounts(accounts)
                            continue

                        if state.get("gameStatus") == "finished":
                            result = state.get("result", {})
                            print_result(
                                acc["name"],
                                result.get("finalRank", "?"),
                                result.get("isWinner", False),
                                result.get("rewards", 0)
                            )
                            continue

                        active   += 1
                        hp        = self_state.get("hp", 0)
                        ep        = self_state.get("ep", 0)
                        atk       = self_state.get("atk", 0)
                        defense   = self_state.get("def", 0)
                        region_id = self_state.get("regionId", "?")

                        do_free_actions(state, acc, gid_snap, aid_snap)
                        action, reason = get_action(state)

                        bots_data.append({
                            "name":    acc["name"],
                            "hp":      hp,
                            "ep":      ep,
                            "atk":     atk,
                            "defense": defense,
                            "region":  region_id,
                            "action":  reason,
                            "alive":   True,
                        })

                        r_action = retry_request(lambda g=gid_snap, a=aid_snap: requests.post(
                            f"{BASE_URL}/games/{g}/agents/{a}/action",
                            headers=headers,
                            json={
                                "action": action,
                                "thought": {
                                    "reasoning": f"HP:{hp} EP:{ep} ATK:{atk} DEF:{defense} - {reason}",
                                    "plannedAction": action["type"]
                                }
                            },
                            timeout=REQUEST_TIMEOUT))

                        if r_action is not None:
                            res = safe_json(r_action)
                            if not res.get("success"):
                                err = res.get("error", {}).get("message", "Unknown error")
                                log_err(f"[bold]{acc['name']}[/bold]: {err}")

                    except Exception as e:
                        log_err(f"[bold]{acc['name']}[/bold]: {type(e).__name__}: {e}")

                    time.sleep(random.uniform(*ACCOUNT_DELAY))

                # Print turn table
                if bots_data:
                    print_turn_table(turn, bots_data)

                if active == 0:
                    log_info("No active bots this turn")

                log_info(f"Next turn in [bold]{ACTION_INTERVAL}s[/bold]...\n")
                time.sleep(ACTION_INTERVAL)

        except KeyboardInterrupt:
            console.print(Panel("[bold red]BOT STOPPED by user[/bold red]",
                                border_style="red", expand=False))
            save_accounts(accounts)
            sys.exit(0)

        except Exception as e:
            log_err(f"ERROR: {type(e).__name__}: {e}")
            log_info("Retry in 5s...")
            time.sleep(5)

if __name__ == "__main__":
    main()
# -*- coding: utf-8 -*-
import requests, json, time, random, os, sys
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.columns import Columns
from rich import box

# ===== CONFIG =====
BASE_URL              = "https://cdn.moltyroyale.com/api"
ACCOUNTS_FILE         = "accounts.json"
ACTION_INTERVAL       = 60
ACCOUNT_DELAY         = (2, 4)
MAX_WAIT_RUNNING      = 120
REQUEST_TIMEOUT       = 30
MAX_RETRIES           = 3
MAX_PLAYERS_THRESHOLD = 96
RETRY_FAILED_REGISTRATION = True
RETRY_INTERVAL        = 15
BLOCKED_GAMES         = {"8bb2d5a8-ccd6-4201-9e53-11e96dc8bac0"}
ATTACK_AGENTS         = True
HP_HEAL_THRESHOLD     = 30
EP_REST_THRESHOLD     = 2
WALLET_ADDRESS        = "0xcbfa0a05dc8F849C44A270D39DFcD50268F2825B"
MAX_INVENTORY         = 9

console = Console()

# ===== LOGGER =====
def log(msg):
    console.print(f"[dim]{datetime.now().strftime('%H:%M:%S')}[/dim]  {msg}")

def log_ok(msg):
    console.print(f"[dim]{datetime.now().strftime('%H:%M:%S')}[/dim]  [bold green][OK][/bold green]  {msg}")

def log_err(msg):
    console.print(f"[dim]{datetime.now().strftime('%H:%M:%S')}[/dim]  [bold red][ERR][/bold red] {msg}")

def log_info(msg):
    console.print(f"[dim]{datetime.now().strftime('%H:%M:%S')}[/dim]  [bold cyan][..][/bold cyan]  {msg}")

def log_warn(msg):
    console.print(f"[dim]{datetime.now().strftime('%H:%M:%S')}[/dim]  [bold yellow][!!][/bold yellow] {msg}")

def print_banner():
    panel = Panel(
        Text.assemble(
            ("  MOLTY ROYALE BOT v5.0\n", "bold magenta"),
            (f"  Bots     : ", "dim"), (f"{len(load_accounts_raw())} accounts\n", "bold white"),
            (f"  Interval : ", "dim"), (f"{ACTION_INTERVAL}s per turn\n", "bold white"),
            (f"  PvP      : ", "dim"), ("ENABLED\n" if ATTACK_AGENTS else "DISABLED\n",
                                        "bold green" if ATTACK_AGENTS else "bold red"),
            (f"  Heal <   : ", "dim"), (f"HP {HP_HEAL_THRESHOLD} | EP {EP_REST_THRESHOLD}\n", "bold white"),
        ),
        title="[bold magenta]? MOLTY ROYALE[/bold magenta]",
        border_style="magenta",
        box=box.DOUBLE_EDGE,
        expand=False
    )
    console.print(panel)

def print_game_header(game_id):
    console.print(Panel(
        f"[bold yellow]GAME ID:[/bold yellow] [white]{game_id}[/white]",
        title="[bold green]GAME FOUND[/bold green]",
        border_style="green",
        box=box.HEAVY,
        expand=False
    ))

def print_turn_table(turn, bots_data):
    """bots_data = list of dict: name, hp, ep, atk, defense, region, action, alive"""
    table = Table(
        title=f"[bold cyan]Turn {turn:02d}[/bold cyan]",
        box=box.SIMPLE_HEAVY,
        border_style="cyan",
        show_lines=False,
        expand=False
    )
    table.add_column("Bot",     style="bold white",  min_width=12)
    table.add_column("HP",      justify="right",     min_width=5)
    table.add_column("EP",      justify="right",     min_width=5)
    table.add_column("ATK",     justify="right",     min_width=5)
    table.add_column("DEF",     justify="right",     min_width=5)
    table.add_column("Region",  style="dim",         min_width=8)
    table.add_column("Action",  style="bold yellow", min_width=20)

    for b in bots_data:
        if not b.get("alive", True):
            table.add_row(
                b.get("name", "?"),
                Text("DEAD", style="bold red"),
                "-", "-", "-", "-", "-", "-",
                Text("---", style="dim")
            )
            continue

        hp_val     = b.get("hp", 0)
        hp_color   = "green" if hp_val >= 60 else ("yellow" if hp_val >= 30 else "red")
        molt_val   = b.get("molt", 0)
        molt_color = "gold1" if molt_val > 0 else "dim"

        table.add_row(
            b.get("name", "?"),
            Text(str(hp_val), style=f"bold {hp_color}"),
            str(b.get("ep", 0)),
            str(b.get("atk", 0)),
            str(b.get("defense", 0)),
            Text(f"[MOLT]{molt_val}", style=f"bold {molt_color}"),
            str(b.get("region", "?"))[:8],
            b.get("action", "?")
        )

    console.print(table)

def print_result(name, rank, is_winner, reward, molt=0):
    style = "bold gold1" if is_winner else "bold white"
    icon  = "??" if is_winner else "??"
    console.print(Panel(
        Text.assemble(
            (f"{icon} {name}\n", style),
            ("Rank   : ", "dim"), (f"#{rank}\n", "bold white"),
            ("Winner : ", "dim"), (("YES ??\n" if is_winner else "No\n"), "bold green" if is_winner else "dim"),
            ("Reward : ", "dim"), (f"{reward} pts\n", "bold yellow"),
        ),
        title="[bold]GAME RESULT[/bold]",
        border_style="gold1" if is_winner else "white",
        box=box.ROUNDED,
        expand=False
    ))

# ===== HELPERS =====
def fetch_claim_payload(acc):
    headers = get_headers(acc)
    endpoints = [
        '/accounts/me/claim',
        '/accounts/me/rewards',
        '/accounts/me',
    ]
    for ep in endpoints:
        try:
            r = requests.get(f"{BASE_URL}{ep}", headers=headers, timeout=REQUEST_TIMEOUT)
            data = safe_json(r)
            if data.get("success") or data.get("data"):
                inner = data.get("data", data)
                payload = (
                    inner.get("claimPayload")
                    or inner.get("payload")
                    or inner.get("claim")
                    or inner.get("claimData")
                    or None
                )
                molt = (
                    inner.get("molt")
                    or inner.get("earnings")
                    or inner.get("rewards")
                    or inner.get("balance")
                    or 0
                )
                cross = round(molt * 0.01, 6)
                if payload or molt:
                    return {"payload": payload, "molt": molt, "cross": cross, "endpoint": ep}
        except:
            pass
    return None

def print_claim_panel(acc, claim_data):
    if not claim_data:
        console.print(Panel(
            "[yellow]Tidak ada payload untuk [bold]" + acc["name"] + "[/bold][/yellow]",
            title="[bold]CLAIM[/bold]",
            border_style="yellow",
            box=box.ROUNDED,
            expand=False
        ))
        return
    payload  = claim_data.get("payload")
    molt     = claim_data.get("molt", 0)
    cross    = claim_data.get("cross", 0)
    ep       = claim_data.get("endpoint", "-")
    pay_str  = str(payload) if payload else "[red]Tidak ada payload[/red]"
    body = (
        "[bold gold1][MOLT] " + acc["name"] + "[/bold gold1]\n"
        + "[dim]Moltz    :[/dim] [bold white]"  + str(molt)  + "[/bold white]\n"
        + "[dim]CROSS    :[/dim] [bold green]"  + str(cross) + " CROSS[/bold green]\n"
        + "[dim]Rate     :[/dim] [dim]1 Moltz = 0.01 CROSS[/dim]\n"
        + "[dim]Endpoint :[/dim] [dim]"         + str(ep)    + "[/dim]\n"
        + "[dim]Payload  :[/dim] [bold cyan]"   + pay_str    + "[/bold cyan]"
    )
    console.print(Panel(
        body,
        title="[bold gold1]CLAIM PAYLOAD[/bold gold1]",
        border_style="gold1",
        box=box.DOUBLE_EDGE,
        expand=False
    ))

def safe_json(r):
    try:    return r.json()
    except: return {}

def retry_request(func, max_retries=MAX_RETRIES):
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                log_err(f"Request gagal: {type(e).__name__}: {e}")
    return None

def get_headers(acc):
    return {"X-API-Key": acc["apiKey"], "Content-Type": "application/json"}

# ===== ACCOUNTS =====
def load_accounts_raw():
    if not os.path.exists(ACCOUNTS_FILE):
        return []
    with open(ACCOUNTS_FILE) as f:
        return json.load(f)

def load_accounts():
    if not os.path.exists(ACCOUNTS_FILE):
        log_err("accounts.json tidak ada!")
        sys.exit(1)
    with open(ACCOUNTS_FILE) as f:
        data = json.load(f)
    for acc in data:
        if "stateWait" in acc:   del acc["stateWait"]
        if "token" in acc and "apiKey" not in acc:
            acc["apiKey"] = acc.pop("token")
        acc.setdefault("gameId",        None)
        acc.setdefault("agentId",       None)
        acc.setdefault("lastRetryTime", 0)
    return data

def save_accounts(accs):
    with open(ACCOUNTS_FILE, "w") as f:
        json.dump(accs, f, indent=2)

# ===== GAME FINDER =====
def get_game_info(game_id):
    try:
        r = requests.get(f"{BASE_URL}/games/{game_id}", timeout=REQUEST_TIMEOUT)
        return safe_json(r).get("data", {})
    except:
        return {}

def find_suitable_game():
    try:
        r     = retry_request(lambda: requests.get(
            f"{BASE_URL}/games?status=waiting", timeout=REQUEST_TIMEOUT))
        games = safe_json(r).get("data", [])
    except:
        games = []

    if not games:
        return None

    log_info(f"Found [bold]{len(games)}[/bold] waiting game(s)")
    for g in games:
        gid = g.get("id")
        if not gid or gid in BLOCKED_GAMES:
            continue
        game_info      = get_game_info(gid)
        current_agents = len(game_info.get("agents", []))
        if current_agents > MAX_PLAYERS_THRESHOLD:
            log_warn(f"Skip [dim]{gid[:8]}...[/dim] ({current_agents} players, too many)")
            continue
        log_ok(f"Game [cyan]{gid[:8]}...[/cyan] ([green]{current_agents}[/green] players)")
        return g
    return None

# ===== REGISTRATION =====
def get_agent_id_from_game(game_id, agent_name):
    try:
        r      = requests.get(f"{BASE_URL}/games/{game_id}", timeout=REQUEST_TIMEOUT)
        agents = safe_json(r).get("data", {}).get("agents", [])
        for agent in agents:
            if agent.get("name") == agent_name:
                return agent.get("id")
    except:
        pass
    return None

def register_agent(acc, game_id):
    headers = get_headers(acc)
    log_info(f"Registering [bold]{acc['name']}[/bold]...")

    try:
        r      = requests.post(
            f"{BASE_URL}/games/{game_id}/agents/register",
            headers=headers,
            json={"name": acc["name"]},
            timeout=45
        )
        result = safe_json(r)

        if result.get("success"):
            agent = result.get("data", {})
            if agent.get("id"):
                acc["agentId"] = agent["id"]
                acc["gameId"]  = game_id
                log_ok(f"[bold]{acc['name']}[/bold] registered! ID: [dim]{agent['id'][:8]}...[/dim]")
                return True

        error_code = result.get("error", {}).get("code", "")
        if error_code == "ONE_AGENT_PER_API_KEY":
            log_info(f"[bold]{acc['name']}[/bold] already in THIS game, recovering...")
            time.sleep(2)
            recovered_id = get_agent_id_from_game(game_id, acc["name"])
            if recovered_id:
                acc["agentId"] = recovered_id
                acc["gameId"]  = game_id
                log_ok(f"[bold]{acc['name']}[/bold] recovered!")
                return True
            return False
        if error_code == "ACCOUNT_ALREADY_IN_GAME":
            log_warn(f"[bold]{acc['name']}[/bold] in another game, skip...")
            return False

    except Exception as e:
        log_err(f"[bold]{acc['name']}[/bold] timeout: {type(e).__name__}, checking...")

    for check_num in range(8):
        time.sleep(5)
        recovered_id = get_agent_id_from_game(game_id, acc["name"])
        if recovered_id:
            acc["agentId"] = recovered_id
            acc["gameId"]  = game_id
            log_ok(f"[bold]{acc['name']}[/bold] recovered after [yellow]{(check_num+1)*5}s[/yellow]!")
            return True

    log_err(f"[bold]{acc['name']}[/bold] registration failed")
    return False

def retry_failed_registrations(accounts, game_id):
    failed = [a for a in accounts
              if a.get("gameId") == game_id and not a.get("agentId")]
    if not failed:
        return 0
    log_info(f"Retrying [yellow]{len(failed)}[/yellow] failed bot(s)...")
    success = 0
    for acc in failed:
        if register_agent(acc, game_id):
            success += 1
            save_accounts(accounts)
    return success

# ===== WAIT GAME START =====
def wait_game_start(game_id):
    log_info("Waiting for game to start...")
    for i in range(MAX_WAIT_RUNNING):
        try:
            r      = requests.get(f"{BASE_URL}/games/{game_id}", timeout=REQUEST_TIMEOUT)
            data   = safe_json(r).get("data", {})
            status = data.get("status")
            if status == "running":
                console.print(Panel(
                    "[bold green]Game is now RUNNING![/bold green]",
                    border_style="green", box=box.HEAVY, expand=False
                ))
                return True
            if status in ("finished", "cancelled"):
                log_err(f"Game [yellow]{status}[/yellow] before starting")
                return False
            if i % 5 == 0:
                agents = data.get("agents", [])
                log_info(f"Waiting... ([bold]{len(agents)}[/bold] players joined)")
        except:
            pass
        time.sleep(2)
    log_err("Timeout waiting for game start")
    return False

# ===== FREE ACTIONS =====
def do_free_actions(state, acc, game_id, agent_id):
    headers    = get_headers(acc)
    self_state = state.get("self", {})
    inventory  = self_state.get("inventory", [])

    if len(inventory) < MAX_INVENTORY:
        current_region = self_state.get("regionId")
        for item_entry in state.get("visibleItems", []):
            if item_entry.get("regionId") == current_region:
                item_id = item_entry.get("item", {}).get("id")
                if not item_id:
                    continue
                try:
                    requests.post(
                        f"{BASE_URL}/games/{game_id}/agents/{agent_id}/action",
                        headers=headers,
                        json={"action": {"type": "pickup", "itemId": item_id}},
                        timeout=10
                    )
                except:
                    pass
                break  # satu pickup per turn

    weapons = [i for i in inventory if i.get("category") == "weapon"]
    if weapons:
        weapons.sort(key=lambda w: w.get("atkBonus", 0), reverse=True)
        best_weapon  = weapons[0]
        equipped     = self_state.get("equippedWeapon") or {}
        equipped_atk = equipped.get("atkBonus", 0) if isinstance(equipped, dict) else 0
        if best_weapon.get("atkBonus", 0) > equipped_atk:
            try:
                requests.post(
                    f"{BASE_URL}/games/{game_id}/agents/{agent_id}/action",
                    headers=headers,
                    json={"action": {"type": "equip", "itemId": best_weapon["id"]}},
                    timeout=10
                )
                log_ok(f"[bold]{acc['name']}[/bold] equip [magenta]{best_weapon.get('name','weapon')}[/magenta] "
                       f"([green]+{best_weapon.get('atkBonus',0)} ATK[/green])")
            except:
                pass

# ===== DECIDE ACTION =====
def get_action(state):
    self_state     = state.get("self", {})
    current_region = state.get("currentRegion", {})
    hp             = self_state.get("hp", 0)
    ep             = self_state.get("ep", 0)
    max_hp         = self_state.get("maxHp", hp)
    atk            = self_state.get("atk", 0)
    self_region_id = self_state.get("regionId")
    inventory      = self_state.get("inventory", [])

    if current_region.get("isDeathZone"):
        connections = current_region.get("connections", [])
        if connections:
            return {"type": "move", "regionId": connections[0]}, "[red]ESCAPE death zone[/red]"

    if hp < HP_HEAL_THRESHOLD:
        heal_items = [i for i in inventory if i.get("category") == "recovery"]
        if heal_items:
            best_heal = max(heal_items, key=lambda i: i.get("healValue", 0))
            return {"type": "use_item", "itemId": best_heal["id"]}, f"[green]HEAL (HP={hp})[/green]"

    if hp < max_hp * 0.25:
        connections = current_region.get("connections", [])
        if connections:
            return {"type": "move", "regionId": connections[0]}, "[red]FLEE low HP[/red]"

    if ep < EP_REST_THRESHOLD:
        return {"type": "rest"}, f"[yellow]REST (EP={ep})[/yellow]"

    if ATTACK_AGENTS and ep >= 2:
        visible = [a for a in state.get("visibleAgents", [])
                   if a.get("regionId") == self_region_id
                   and a.get("isAlive")
                   and a.get("id") != self_state.get("id")]
        if visible:
            weak_targets = [a for a in visible if atk > a.get("def", 0)]
            if weak_targets:
                target = min(weak_targets, key=lambda a: a.get("hp", 9999))
                return ({"type": "attack", "targetId": target["id"], "targetType": "agent"},
                        f"[red]ATTACK[/red] [bold]{target.get('name','?')}[/bold] (HP={target.get('hp','?')})")

    for monster in state.get("visibleMonsters", []):
        if monster.get("regionId") == self_region_id:
            if monster.get("hp", 9999) < hp * 2:
                return ({"type": "attack", "targetId": monster["id"], "targetType": "monster"},
                        f"[orange3]HUNT[/orange3] [bold]{monster.get('name','?')}[/bold]")

    return {"type": "explore"}, "[cyan]EXPLORE[/cyan]"

# ===== MAIN =====
def main():
    accounts = load_accounts()
    print_banner()

    while True:
        try:
            # ---- FIND GAME ----
            log_info("Finding suitable game...")
            game = find_suitable_game()
            if not game:
                log_err("No suitable game found, retry in 10s...")
                time.sleep(10)
                continue

            game_id = game["id"]
            print_game_header(game_id)

            # ---- REGISTER ----
            console.rule("[bold cyan]REGISTERING BOTS[/bold cyan]")
            successful = 0
            for i, acc in enumerate(accounts, 1):
                if acc.get("gameId") != game_id:
                    acc["gameId"]  = None
                    acc["agentId"] = None

                if acc.get("agentId") and acc.get("gameId") == game_id:
                    log_ok(f"[bold]{acc['name']}[/bold] already in game")
                    successful += 1
                    continue

                if register_agent(acc, game_id):
                    successful += 1
                    save_accounts(accounts)
                else:
                    break  # game penuh/error, skip sisa bot, cari game baru

                if i < len(accounts):
                    time.sleep(random.uniform(*ACCOUNT_DELAY))

            console.print(f"\n  [bold]Registered:[/bold] [green]{successful}[/green]/[white]{len(accounts)}[/white] bots\n")
            if successful == 0:
                time.sleep(5)
                continue

            save_accounts(accounts)

            # ---- WAIT START ----
            if not wait_game_start(game_id):
                for acc in accounts:
                    acc["gameId"] = acc["agentId"] = None
                save_accounts(accounts)
                time.sleep(5)
                continue

            # ---- GAME LOOP ----
            console.rule("[bold green]GAME STARTED - PLAYING[/bold green]")
            last_retry = time.time()

            while True:
                try:
                    r         = requests.get(f"{BASE_URL}/games/{game_id}", timeout=REQUEST_TIMEOUT)
                    game_info = safe_json(r).get("data", {})
                    status    = game_info.get("status")
                    turn      = game_info.get("turn", 0)
                except:
                    log_err("Timeout cek game status")
                    time.sleep(5)
                    continue

                if status in ("finished", "cancelled"):
                    console.rule(f"[bold red]GAME {status.upper()}[/bold red]")
                    for acc in accounts:
                        if acc.get("gameId") == game_id:
                            acc["gameId"]  = None
                            acc["agentId"] = None
                    save_accounts(accounts)
                    break

                if RETRY_FAILED_REGISTRATION and time.time() - last_retry >= RETRY_INTERVAL:
                    last_retry = time.time()
                    retry_failed_registrations(accounts, game_id)

                # Per-account action
                bots_data = []
                active    = 0

                for acc in accounts:
                    if not acc.get("agentId") or acc.get("gameId") != game_id:
                        continue

                    headers  = get_headers(acc)
                    gid_snap = acc["gameId"]
                    aid_snap = acc["agentId"]

                    try:
                        r_state = retry_request(lambda g=gid_snap, a=aid_snap: requests.get(
                            f"{BASE_URL}/games/{g}/agents/{a}/state",
                            headers=headers, timeout=REQUEST_TIMEOUT))
                        if r_state is None:
                            continue

                        state = safe_json(r_state).get("data")
                        if not state:
                            continue

                        self_state = state.get("self", {})

                        if not self_state.get("isAlive"):
                            bots_data.append({"name": acc["name"], "alive": False})
                            # Langsung reset supaya bisa join game baru
                            acc["gameId"]  = None
                            acc["agentId"] = None
                            save_accounts(accounts)
                            continue

                        if state.get("gameStatus") == "finished":
                            result = state.get("result", {})
                            print_result(
                                acc["name"],
                                result.get("finalRank", "?"),
                                result.get("isWinner", False),
                                result.get("rewards", 0)
                            )
                            continue

                        active   += 1
                        hp        = self_state.get("hp", 0)
                        ep        = self_state.get("ep", 0)
                        atk       = self_state.get("atk", 0)
                        defense   = self_state.get("def", 0)
                        region_id = self_state.get("regionId", "?")

                        do_free_actions(state, acc, gid_snap, aid_snap)
                        action, reason = get_action(state)

                        bots_data.append({
                            "name":    acc["name"],
                            "hp":      hp,
                            "ep":      ep,
                            "atk":     atk,
                            "defense": defense,
                            "region":  region_id,
                            "action":  reason,
                            "alive":   True,
                        })

                        r_action = retry_request(lambda g=gid_snap, a=aid_snap: requests.post(
                            f"{BASE_URL}/games/{g}/agents/{a}/action",
                            headers=headers,
                            json={
                                "action": action,
                                "thought": {
                                    "reasoning": f"HP:{hp} EP:{ep} ATK:{atk} DEF:{defense} - {reason}",
                                    "plannedAction": action["type"]
                                }
                            },
                            timeout=REQUEST_TIMEOUT))

                        if r_action is not None:
                            res = safe_json(r_action)
                            if not res.get("success"):
                                err = res.get("error", {}).get("message", "Unknown error")
                                log_err(f"[bold]{acc['name']}[/bold]: {err}")

                    except Exception as e:
                        log_err(f"[bold]{acc['name']}[/bold]: {type(e).__name__}: {e}")

                    time.sleep(random.uniform(*ACCOUNT_DELAY))

                # Print turn table
                if bots_data:
                    print_turn_table(turn, bots_data)

                if active == 0:
                    log_info("No active bots this turn")

                log_info(f"Next turn in [bold]{ACTION_INTERVAL}s[/bold]...\n")
                time.sleep(ACTION_INTERVAL)

        except KeyboardInterrupt:
            console.print(Panel("[bold red]BOT STOPPED by user[/bold red]",
                                border_style="red", expand=False))
            save_accounts(accounts)
            sys.exit(0)

        except Exception as e:
            log_err(f"ERROR: {type(e).__name__}: {e}")
            log_info("Retry in 5s...")
            time.sleep(5)

if __name__ == "__main__":
    main()

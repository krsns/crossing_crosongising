import requests, json, time, random
from config import *

def load_accounts():
    with open("accounts.json") as f:
        return json.load(f)

def save_accounts(accs):
    with open("accounts.json", "w") as f:
        json.dump(accs, f, indent=2)
    with open("accounts_backup.json", "w") as f:
        json.dump(accs, f, indent=2)

accounts = load_accounts()

while True:
    for acc in accounts:
        headers = {"X-API-Key": acc["apiKey"]}

        # join game if needed
        if not acc["gameId"]:
            games = requests.get(f"{BASE_URL}/games?status=waiting").json()["data"]
            if not games:
                game = requests.post(f"{BASE_URL}/games", headers=headers).json()["data"]
            else:
                game = games[0]

            acc["gameId"] = game["id"]

            agent = requests.post(
                f"{BASE_URL}/games/{acc['gameId']}/agents/register",
                headers=headers,
                json={"name": acc["name"]}
            ).json()["data"]

            acc["agentId"] = agent["id"]
            save_accounts(accounts)

            print(f"[JOINED] {acc['name']} → {acc['gameId']}")
            time.sleep(3)
            continue

        # get state
        state = requests.get(
            f"{BASE_URL}/games/{acc['gameId']}/agents/{acc['agentId']}/state",
            headers=headers
        ).json()["data"]

        hp = state["hp"]
        ep = state["ep"]

        # decision logic (simple & safe)
        if hp < LOW_HP_THRESHOLD:
            action = {"type": "rest"}
        else:
            action = random.choice([
                {"type": "move"},
                {"type": "pickup"},
                {"type": "talk"}
            ])

        requests.post(
            f"{BASE_URL}/games/{acc['gameId']}/agents/{acc['agentId']}/action",
            headers=headers,
            json={"action": action}
        )

        print(f"[ACTION] {acc['name']} | HP:{hp} | {action['type']}")

        time.sleep(random.randint(*ACCOUNT_DELAY))

    time.sleep(ACTION_INTERVAL)

import requests, json, os

BASE = "https://mort-royal-production.up.railway.app/api"
AGENTS = {}

for keyfile in os.listdir("../backup/api_keys"):
    api_key = open(f"../backup/api_keys/{keyfile}").read().strip()
    HEAD = {"X-API-Key": api_key}

    games = requests.get(f"{BASE}/games?status=waiting").json()["data"]
    if not games:
        game = requests.post(
            f"{BASE}/games",
            headers=HEAD,
            json={"entryType": "free"}
        ).json()["data"]
    else:
        game = games[0]

    agent = requests.post(
        f"{BASE}/games/{game['id']}/agents/register",
        headers=HEAD,
        json={"name": keyfile.replace(".txt", "_AI")}
    ).json()["data"]

    AGENTS[keyfile] = {
        "gameId": game["id"],
        "agentId": agent["id"]
    }

os.makedirs("../config", exist_ok=True)
with open("../config/agents.json", "w") as f:
    json.dump(AGENTS, f, indent=2)

print("All agents registered")

import requests, json, time, random, os

BASE = "https://mort-royal-production.up.railway.app/api"
agents = json.load(open("../config/agents.json"))

def loop(api_key, game_id, agent_id):
    HEAD = {"X-API-Key": api_key}
    while True:
        game = requests.get(f"{BASE}/games/{game_id}").json()["data"]
        if game["status"] != "running":
            time.sleep(10)
            continue

        state = requests.get(
            f"{BASE}/games/{game_id}/agents/{agent_id}/state",
            headers=HEAD
        ).json()["data"]

        if state["hp"] < 40:
            action = {"action": {"type": "rest"}}
        else:
            region = random.choice(state["safeRegions"])
            action = {"action": {"type": "move", "regionId": region}}

        requests.post(
            f"{BASE}/games/{game_id}/agents/{agent_id}/action",
            headers=HEAD,
            json=action
        )

        time.sleep(60)

for keyfile, cfg in agents.items():
    api_key = open(f"../backup/api_keys/{keyfile}").read().strip()
    loop(api_key, cfg["gameId"], cfg["agentId"])

# config.py - OPTIMIZED VERSION

BASE_URL = "https://mort-royal-production.up.railway.app/api"

# === ACCOUNT SETTINGS ===
TOTAL_ACCOUNTS = 5
AGENT_NAME_PREFIX = "cross_ciu_"

# === TIMING SETTINGS ===
ACTION_INTERVAL = 45        # turun dari 60 -> lebih responsif (masih aman)
ACCOUNT_DELAY = (1, 3)      # turun dari (2,5) -> lebih cepat cycle
STATE_RETRY_DELAY = 2       # delay kalau gagal get state

# === COMBAT THRESHOLDS ===
LOW_HP_THRESHOLD = 35       # turun dari 40 -> lebih aggressive
CRITICAL_HP = 20            # HP kritis untuk emergency rest
LOW_EP_THRESHOLD = 15       # batas EP rendah
CRITICAL_EP = 5             # EP kritis

# === STRATEGY WEIGHTS ===
# Early game (turn 1-20): farming phase
EARLY_GAME_TURNS = 20
EARLY_PICKUP_WEIGHT = 0.7   # 70% pickup
EARLY_MOVE_WEIGHT = 0.2     # 20% move
EARLY_REST_WEIGHT = 0.1     # 10% rest

# Mid game (turn 21-60): balanced
MID_GAME_TURNS = 60
MID_PICKUP_WEIGHT = 0.4     # 40% pickup
MID_MOVE_WEIGHT = 0.3       # 30% move
MID_ATTACK_WEIGHT = 0.2     # 20% attack
MID_REST_WEIGHT = 0.1       # 10% rest

# Late game (turn 61+): aggressive
LATE_PICKUP_WEIGHT = 0.2    # 20% pickup
LATE_MOVE_WEIGHT = 0.3      # 30% move
LATE_ATTACK_WEIGHT = 0.4    # 40% attack
LATE_REST_WEIGHT = 0.1      # 10% rest

# === STAT REQUIREMENTS FOR ATTACK ===
MIN_ATTACK_TO_FIGHT = 12    # minimal attack stat untuk mulai serang
MIN_HP_TO_FIGHT = 45        # minimal HP untuk engage combat
MIN_EP_TO_FIGHT = 20        # minimal EP untuk attack

# === DEFENSIVE SETTINGS ===
DEFENSE_THRESHOLD = 8       # kalau defense >= ini, lebih berani fight
HIGH_DEFENSE_HP_BONUS = 10  # bisa fight dengan HP lebih rendah kalau defense tinggi

import requests, json, time, sys
from config import BASE_URL, TOTAL_ACCOUNTS

print("=" * 50)
print("ACCOUNT CREATOR - Mort Royal Bot")
print("=" * 50)

prefix = input("Masukkan prefix nama bot (contoh: vps2_ atau userA_): ").strip()
if not prefix:
    prefix = "bot_"
    print(f"âš  Using default prefix: {prefix}")

start = input("Mulai dari nomor berapa? (default 1): ").strip()
start = int(start) if start else 1

print(f"\nðŸ“‹ Will create {TOTAL_ACCOUNTS} accounts: {prefix}{start} to {prefix}{start + TOTAL_ACCOUNTS - 1}")
confirm = input("Continue? (y/n): ").strip().lower()
if confirm != 'y':
    print("Cancelled.")
    sys.exit(0)

accounts = []
failed = []

print(f"\nðŸš€ Starting account creation...\n")

for i in range(TOTAL_ACCOUNTS):
    name = f"{prefix}{start + i}"
    
    try:
        print(f"[{i+1}/{TOTAL_ACCOUNTS}] Creating {name}...", end=" ")
        
        r = requests.post(
            f"{BASE_URL}/accounts",
            json={"name": name},
            timeout=20
        )
        
        # Check HTTP status
        if r.status_code not in [200, 201]:
            print(f"âŒ HTTP {r.status_code}")
            print(f"    Response: {r.text[:100]}")
            failed.append(name)
            time.sleep(2)
            continue
        
        # Parse JSON
        response = r.json()
        
        # Check response format
        if "data" not in response:
            print(f"âŒ No 'data' field")
            print(f"    Response: {response}")
            failed.append(name)
            time.sleep(2)
            continue
        
        if "apiKey" not in response["data"]:
            print(f"âŒ No 'apiKey' field")
            print(f"    Response: {response}")
            failed.append(name)
            time.sleep(2)
            continue
        
        api_key = response["data"]["apiKey"]
        
        # Verify API key format
        if not api_key or len(api_key) < 10:
            print(f"âŒ Invalid API key: {api_key}")
            failed.append(name)
            time.sleep(2)
            continue
        
        accounts.append({
            "name": name,
            "apiKey": api_key,
            "gameId": None,
            "agentId": None
        })
        
        print(f"âœ… OK - Key: {api_key[:15]}...")
        time.sleep(2)  # Rate limit protection
        
    except requests.exceptions.Timeout:
        print(f"âŒ Timeout (>20s)")
        failed.append(name)
        time.sleep(5)
        
    except requests.exceptions.ConnectionError:
        print(f"âŒ Connection failed")
        print(f"    Check BASE_URL: {BASE_URL}")
        failed.append(name)
        time.sleep(5)
        
    except json.JSONDecodeError:
        print(f"âŒ Invalid JSON response")
        print(f"    Raw: {r.text[:100]}")
        failed.append(name)
        time.sleep(2)
        
    except KeyError as e:
        print(f"âŒ Missing key: {e}")
        print(f"    Response: {response}")
        failed.append(name)
        time.sleep(2)
        
    except Exception as e:
        print(f"âŒ Error: {type(e).__name__} - {e}")
        failed.append(name)
        time.sleep(2)

# Summary
print("\n" + "=" * 50)
print("SUMMARY")
print("=" * 50)
print(f"âœ… Success: {len(accounts)}/{TOTAL_ACCOUNTS}")
if failed:
    print(f"âŒ Failed: {len(failed)}/{TOTAL_ACCOUNTS}")
    print(f"   Failed names: {', '.join(failed)}")

# Save if any success
if accounts:
    # Load existing accounts if any
    existing = []
    try:
        with open("accounts.json", "r") as f:
            existing = json.load(f)
        print(f"\nðŸ“‚ Found {len(existing)} existing accounts")
    except FileNotFoundError:
        print(f"\nðŸ“‚ Creating new accounts.json")
    
    # Merge (avoid duplicates by name)
    existing_names = {acc["name"] for acc in existing}
    new_accounts = [acc for acc in accounts if acc["name"] not in existing_names]
    
    if new_accounts:
        existing.extend(new_accounts)
        
        # Save main file
        with open("accounts.json", "w") as f:
            json.dump(existing, f, indent=2)
        
        # Save backup
        with open("accounts_backup.json", "w") as f:
            json.dump(existing, f, indent=2)
        
        print(f"ðŸ’¾ Saved {len(new_accounts)} new accounts")
        print(f"ðŸ“Š Total accounts now: {len(existing)}")
        print("\nâœ… ALL DONE!")
        print("ðŸ” API Keys saved to: accounts.json")
        print("ðŸ’¾ Backup saved to: accounts_backup.json")
    else:
        print(f"\nâš  All accounts already exist in accounts.json")
else:
    print("\nâŒ NO ACCOUNTS CREATED")
    print("   Check:")
    print(f"   1. BASE_URL is correct: {BASE_URL}")
    print(f"   2. API endpoint accepts POST /accounts")
    print(f"   3. Internet connection is stable")
    print(f"   4. No rate limiting from server")
    sys.exit(1)

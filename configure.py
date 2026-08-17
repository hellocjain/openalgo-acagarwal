#!/usr/bin/env python3
import os
import sys
import getpass
import secrets
import subprocess
from dotenv import load_dotenv

print("\n" + "="*70)
print("     OpenAlgo + AC Agarwal Master Broker Configuration Wizard")
print("="*70)

env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(env_path)

# 1. Prompt for Details
print("\nPlease enter your AC Agarwal (Symphony XTS) Master Broker Details:")
current_user_id = os.getenv("BROKER_USER_ID", "")
user_id = input(f"1. Master Client Code / User ID [{current_user_id}]: ").strip() or current_user_id

current_api_key = os.getenv("BROKER_API_KEY", "")
api_key = input(f"2. Master Interactive API Key [{current_api_key[:6]}...]: ").strip() or current_api_key

current_api_secret = os.getenv("BROKER_API_SECRET", "")
api_secret = input(f"3. Master Interactive API Secret [{current_api_secret[:6]}...]: ").strip() or current_api_secret

current_market_key = os.getenv("BROKER_API_KEY_MARKET", "")
api_key_market = input(f"4. Master Market Data API Key [{current_market_key[:6]}...]: ").strip() or current_market_key

current_market_secret = os.getenv("BROKER_API_SECRET_MARKET", "")
api_secret_market = input(f"5. Master Market Data API Secret [{current_market_secret[:6]}...]: ").strip() or current_market_secret

base_url = os.getenv("BROKER_BASE_URL", "https://symphony.acagarwal.com:3000").strip()

print("\nWeb Portal Admin Credentials:")
admin_user = input("Admin Username [admin]: ").strip() or "admin"
admin_pass = getpass.getpass("Admin Password [Admin@12345]: ").strip() or "Admin@12345"

# 2. Update .env
def update_env_file(filepath, updates):
    lines = []
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            lines = f.readlines()

    existing_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            k = stripped.split("=")[0].strip()
            if k in updates:
                new_lines.append(f"{k} = '{updates[k]}'\n")
                existing_keys.add(k)
                continue
        new_lines.append(line)

    for k, v in updates.items():
        if k not in existing_keys:
            new_lines.append(f"{k} = '{v}'\n")

    with open(filepath, "w") as f:
        f.writelines(new_lines)

updates = {
    "BROKER": "acagarwal",
    "VALID_BROKERS": "acagarwal,fivepaisa,fivepaisaxts,aliceblue,angel,arrow,compositedge,dhan,dhan_sandbox,definedge,deltaexchange,firstock,flattrade,fyers,groww,hdfcsecurities,hdfcsky,ibulls,iifl,iiflcapital,indmoney,jainamxts,kotak,motilal,mstock,nubra,paytm,pocketful,rmoney,samco,shoonya,tradejini,tradesmart,upstox,wisdom,zebu,zerodha",
    "BROKER_USER_ID": user_id,
    "BROKER_API_KEY": api_key,
    "BROKER_API_SECRET": api_secret,
    "BROKER_API_KEY_MARKET": api_key_market,
    "BROKER_API_SECRET_MARKET": api_secret_market,
    "BROKER_BASE_URL": base_url,
    "FLASK_PORT": "5001",
    "PORT": "5001",
}

if not os.getenv("API_KEY_PEPPER") or "OPENALGO_PLACEHOLDER" in os.getenv("API_KEY_PEPPER", ""):
    updates["API_KEY_PEPPER"] = secrets.token_hex(32)
    updates["FERNET_SALT"] = secrets.token_hex(32)
    updates["SECRET_KEY"] = secrets.token_hex(32)
    updates["APP_KEY"] = secrets.token_hex(32)

update_env_file(env_path, updates)
print("\n[✓] .env configuration file updated successfully.")

# Reload env
load_dotenv(env_path, override=True)

# 3. Test AC Agarwal Login
print("\nTesting AC Agarwal API Connection...")
try:
    import requests
    auth_payload = {
        "secretKey": api_secret,
        "appKey": api_key,
        "source": "WebAPI"
    }
    interactive_url = base_url.rstrip("/") + "/interactive"
    resp = requests.post(f"{interactive_url}/user/session", json=auth_payload, timeout=5)
    if resp.status_code == 200 and resp.json().get("type") == "success":
        token = resp.json().get("result", {}).get("token")
        print(f"  [✓] AC Agarwal Interactive API Connected! Session Token Generated.")
    else:
        print(f"  [!] Note: Interactive Login returned {resp.status_code}: {resp.text}")
except Exception as e:
    print(f"  [!] Note: Connection check: {e}")

# 4. Update Database User and Auth
print("\nUpdating Database Credentials...")
try:
    from database.user_db import find_user_by_exact_username, add_user, db_session, init_db as init_user_db
    from database.auth_db import init_db as init_auth_db, upsert_auth
    from database.copy_trading_db import init_copy_trading_db
    init_user_db()
    init_auth_db()
    init_copy_trading_db()

    u = find_user_by_exact_username(admin_user)
    if u:
        u.set_password(admin_pass)
        db_session.commit()
        print(f"  [✓] Admin user '{admin_user}' password updated.")
    else:
        add_user(admin_user, f"{admin_user}@openalgo.local", admin_pass, is_admin=True)
        print(f"  [✓] Admin user '{admin_user}' created.")

    if user_id:
        upsert_auth(admin_user, user_id, user_id)
        print(f"  [✓] Master Broker account '{user_id}' linked to admin user.")
except Exception as e:
    print(f"  [!] Database update notice: {e}")

# 5. Restart Systemd Service
print("\nRestarting OpenAlgo Service...")
try:
    subprocess.run(["sudo", "systemctl", "restart", "openalgo"], check=False)
    print("  [✓] systemctl restart openalgo executed.")
except Exception:
    pass

print("\n" + "="*70)
print("  🎉 Configuration Complete! OpenAlgo is live and ready.")
print("="*70)
print(f"Web Dashboard: http://168.144.22.51:5001")
print(f"Copy Trading:  http://168.144.22.51:5001/copytrading")
print(f"Username:      {admin_user}")
print(f"Password:      {admin_pass}")
print("="*70 + "\n")

#!/usr/bin/env bash
# ==============================================================================
# OpenAlgo + AC Agarwal Broker (Symphony XTS) Interactive One-Shot Installer
# ==============================================================================
set -e

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}"
echo "======================================================================"
echo "      OpenAlgo v2.0 + AC Agarwal Broker One-Shot Installer            "
echo "======================================================================"
echo -e "${NC}"

ACTUAL_USER="${SUDO_USER:-$(whoami)}"
if [ -z "$ACTUAL_USER" ]; then
  ACTUAL_USER="root"
fi

INSTALL_DIR="${INSTALL_DIR:-/opt/openalgo}"

# Helper function to prompt for input safely from terminal
prompt_input() {
  local prompt_msg="$1"
  local var_name="$2"
  local default_val="$3"
  local input_val=""

  if [ -t 0 ]; then
    read -p "$prompt_msg" input_val || true
  elif [ -e /dev/tty ] && [ -r /dev/tty ]; then
    read -p "$prompt_msg" input_val < /dev/tty || true
  fi

  if [ -z "$input_val" ]; then
    eval "$var_name=\"$default_val\""
  else
    eval "$var_name=\"$input_val\""
  fi
}

prompt_password() {
  local prompt_msg="$1"
  local var_name="$2"
  local default_val="$3"
  local input_val=""

  if [ -t 0 ]; then
    read -sp "$prompt_msg" input_val || true
    echo ""
  elif [ -e /dev/tty ] && [ -r /dev/tty ]; then
    read -sp "$prompt_msg" input_val < /dev/tty || true
    echo ""
  fi

  if [ -z "$input_val" ]; then
    eval "$var_name=\"$default_val\""
  else
    eval "$var_name=\"$input_val\""
  fi
}

# ------------------------------------------------------------------------------
# Step 1: Interactive Installation & Client Configuration Setup
# ------------------------------------------------------------------------------
echo -e "${CYAN}--- Step 1: Credentials & Configuration Setup ---${NC}"

AUTO_DETECTED_IP=$(curl -s --connect-timeout 2 ifconfig.me || hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
AUTO_DETECTED_IP=$(echo "$AUTO_DETECTED_IP" | xargs)

prompt_input "Enter Admin Portal Username [default: admin]: " ADMIN_USERNAME "admin"
prompt_password "Enter Admin Portal Password [default: Admin@12345]: " ADMIN_PASSWORD "Admin@12345"
prompt_input "Enter Server Public IP / Domain [default: $AUTO_DETECTED_IP]: " STATIC_IP "$AUTO_DETECTED_IP"

prompt_input "Enter AC Agarwal User ID (Client Code, e.g. DM933): " USER_ID ""
prompt_input "Enter Interactive API Key (BROKER_API_KEY): " API_KEY ""
prompt_input "Enter Interactive API Secret (BROKER_API_SECRET): " API_SECRET ""
prompt_input "Enter Market Data API Key (BROKER_API_KEY_MARKET): " API_KEY_MARKET ""
prompt_input "Enter Market Data API Secret (BROKER_API_SECRET_MARKET): " API_SECRET_MARKET ""
prompt_input "Enter Broker Base URL [default: https://symphony.acagarwal.com:3000]: " BASE_URL "https://symphony.acagarwal.com:3000"

echo ""
echo -e "${GREEN}[+] Configuration received. Starting installation...${NC}"

# ------------------------------------------------------------------------------
# Step 2: Install Ubuntu Packages
# ------------------------------------------------------------------------------
echo -e "\n${CYAN}--- Step 2: Installing Ubuntu Dependencies ---${NC}"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git curl build-essential sqlite3 lsof

# ------------------------------------------------------------------------------
# Step 3: Clone/Prepare Repository
# ------------------------------------------------------------------------------
echo -e "\n${CYAN}--- Step 3: Preparing OpenAlgo Repository ---${NC}"
if [ ! -d "$INSTALL_DIR" ]; then
  echo -e "${GREEN}[+] Cloning OpenAlgo repository into ${INSTALL_DIR}...${NC}"
  git clone https://github.com/hellocjain/openalgo-acagarwal.git "$INSTALL_DIR"
else
  echo -e "${GREEN}[+] Existing directory detected at ${INSTALL_DIR}, pulling latest updates...${NC}"
  cd "$INSTALL_DIR"
  git pull || true
fi

cd "$INSTALL_DIR"
chown -R "$ACTUAL_USER:$ACTUAL_USER" "$INSTALL_DIR" 2>/dev/null || true

# ------------------------------------------------------------------------------
# Step 4: Python Virtual Environment & Dependencies
# ------------------------------------------------------------------------------
echo -e "\n${CYAN}--- Step 4: Setting up Python Environment ---${NC}"
if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

./venv/bin/pip install --upgrade pip
if [ -f "requirements.txt" ]; then
  ./venv/bin/pip install -r requirements.txt
fi
./venv/bin/pip install httpx python-socketio websocket-client pandas python-dotenv eventlet gunicorn

# ------------------------------------------------------------------------------
# Step 5: Generate .env Configuration & Security Tokens
# ------------------------------------------------------------------------------
echo -e "\n${CYAN}--- Step 5: Updating .env Configuration ---${NC}"

if [ ! -f ".env" ]; then
  if [ -f ".sample.env" ]; then
    cp .sample.env .env
  elif [ -f ".env.example" ]; then
    cp .env.example .env
  else
    touch .env
  fi
fi

update_env() {
  local key="$1"
  local val="$2"
  if grep -q "^${key}\s*=" .env; then
    sed -i "s|^${key}\s*=.*|${key} = '${val}'|" .env
  elif grep -q "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key} = '${val}'|" .env
  else
    echo "${key} = '${val}'" >> .env
  fi
}

update_env "BROKER" "acagarwal"
update_env "VALID_BROKERS" "acagarwal,fivepaisa,fivepaisaxts,aliceblue,angel,arrow,compositedge,dhan,dhan_sandbox,definedge,deltaexchange,firstock,flattrade,fyers,groww,hdfcsecurities,hdfcsky,ibulls,iifl,iiflcapital,indmoney,jainamxts,kotak,motilal,mstock,nubra,paytm,pocketful,rmoney,samco,shoonya,tradejini,tradesmart,upstox,wisdom,zebu,zerodha"
update_env "BROKER_USER_ID" "$USER_ID"
update_env "BROKER_API_KEY" "$API_KEY"
update_env "BROKER_API_SECRET" "$API_SECRET"
update_env "BROKER_API_KEY_MARKET" "$API_KEY_MARKET"
update_env "BROKER_API_SECRET_MARKET" "$API_SECRET_MARKET"
update_env "BROKER_BASE_URL" "$BASE_URL"
update_env "FLASK_HOST_IP" "0.0.0.0"
update_env "HOST" "0.0.0.0"
update_env "FLASK_PORT" "5001"
update_env "PORT" "5001"
update_env "REDIRECT_URL" "http://${STATIC_IP}:5001/acagarwal/callback"
update_env "HOST_SERVER" "http://${STATIC_IP}:5001"
update_env "WEBSOCKET_HOST" "0.0.0.0"
update_env "WEBSOCKET_PORT" "8765"
update_env "WEBSOCKET_URL" "ws://${STATIC_IP}:8765"

# Generate mandatory OpenAlgo v2.0 security tokens if absent
if ! grep -q "^API_KEY_PEPPER=" .env || grep -q "OPENALGO_PLACEHOLDER" .env; then
  GEN_PEPPER=$(./venv/bin/python3 -c "import secrets; print(secrets.token_hex(32))")
  GEN_SALT=$(./venv/bin/python3 -c "import secrets; print(secrets.token_hex(32))")
  GEN_SECRET=$(./venv/bin/python3 -c "import secrets; print(secrets.token_hex(32))")
  
  update_env "API_KEY_PEPPER" "$GEN_PEPPER"
  update_env "FERNET_SALT" "$GEN_SALT"
  update_env "SECRET_KEY" "$GEN_SECRET"
  update_env "APP_KEY" "$GEN_SECRET"
fi

# ------------------------------------------------------------------------------
# Step 6: Initialize Client Database Account
# ------------------------------------------------------------------------------
echo -e "\n${CYAN}--- Step 6: Initializing Client Database ---${NC}"

export ADMIN_USERNAME_ENV="$ADMIN_USERNAME"
export ADMIN_PASSWORD_ENV="$ADMIN_PASSWORD"
export USER_ID_ENV="$USER_ID"

./venv/bin/python3 -c "
import os
try:
    from database.auth_db import init_auth_db, upsert_auth
    from database.user_db import create_user, reset_password, verify_user
    init_auth_db()
    
    admin_user = os.getenv('ADMIN_USERNAME_ENV', 'admin')
    admin_pass = os.getenv('ADMIN_PASSWORD_ENV', 'Admin@12345')
    broker_user_id = os.getenv('USER_ID_ENV', '')

    if not verify_user(admin_user, admin_pass):
        try:
            create_user(admin_user, admin_pass)
            print(f'  [✓] Admin user \"{admin_user}\" created in database')
        except Exception:
            reset_password(admin_user, admin_pass)
            print(f'  [✓] Admin user \"{admin_user}\" password configured')

    if broker_user_id:
        upsert_auth(admin_user, broker_user_id, broker_user_id)
        print(f'  [✓] Linked broker client ID \"{broker_user_id}\" to portal user \"{admin_user}\"')
except Exception as user_err:
    print(f'  [!] User DB notice: {user_err}')
"

# ------------------------------------------------------------------------------
# Step 7: Systemd Service Configuration
# ------------------------------------------------------------------------------
echo -e "\n${CYAN}--- Step 7: Configuring systemd background service ---${NC}"
SERVICE_FILE="/etc/systemd/system/openalgo.service"

cat <<EOF > $SERVICE_FILE
[Unit]
Description=OpenAlgo Algorithmic Trading Platform (AC Agarwal Broker)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python app.py
Restart=always
RestartSec=5
Environment=PATH=$INSTALL_DIR/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable openalgo
systemctl restart openalgo

echo -e "\n${GREEN}======================================================================${NC}"
echo -e "${GREEN}  ✓ OpenAlgo Installation Completed Successfully!                     ${NC}"
echo -e "${GREEN}======================================================================${NC}"
echo -e "${CYAN}Web Portal URL :${NC} http://${STATIC_IP}:5001"
echo -e "${CYAN}Admin Username :${NC} ${ADMIN_USERNAME}"
echo -e "${CYAN}Service Status :${NC} sudo systemctl status openalgo"
echo -e "${CYAN}Live Logs      :${NC} sudo journalctl -u openalgo -f"
echo -e "${GREEN}======================================================================${NC}\n"

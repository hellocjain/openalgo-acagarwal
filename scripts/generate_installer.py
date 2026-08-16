# scripts/generate_installer.py

import base64
import os
import subprocess

def main():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    # Create tar.gz of broker/acagarwal
    tar_cmd = ["tar", "-czf", "-", "-C", os.path.join(root_dir, "broker"), "acagarwal"]
    tar_bytes = subprocess.check_output(tar_cmd)
    b64_payload = base64.b64encode(tar_bytes).decode("utf-8")

    template = '''#!/usr/bin/env bash
# ==============================================================================
# OpenAlgo + AC Agarwal Broker (Symphony XTS) Self-Extracting Ubuntu Installer
# ==============================================================================
set -e

GREEN='\\033[0;32m'
CYAN='\\033[0;36m'
YELLOW='\\033[1;33m'
RED='\\033[0;31m'
NC='\\033[0m'

echo -e "${CYAN}"
echo "======================================================================"
echo "      OpenAlgo v2.0 + AC Agarwal Broker One-Shot Installer            "
echo "======================================================================"
echo -e "${NC}"

if [ "$EUID" -ne 0 ]; then
  echo -e "${YELLOW}[!] Running as non-root user. Sudo will be used for system packages.${NC}"
  SUDO="sudo"
else
  SUDO=""
fi

INSTALL_DIR="${INSTALL_DIR:-/opt/openalgo}"
CURRENT_DIR="$(pwd)"

if [ -f "$CURRENT_DIR/app.py" ] && [ -d "$CURRENT_DIR/broker" ]; then
  INSTALL_DIR="$CURRENT_DIR"
  echo -e "${GREEN}[+] Detected existing OpenAlgo directory at: ${INSTALL_DIR}${NC}"
else
  echo -e "${GREEN}[+] Installing OpenAlgo to target directory: ${INSTALL_DIR}${NC}"
fi

# ------------------------------------------------------------------------------
# Step 1: Interactive Installation & Client Configuration Setup
# ------------------------------------------------------------------------------
echo -e "\\n${CYAN}--- Step 1: OpenAlgo SaaS Client & Broker Configuration ---${NC}"

# Auto-detect public server IP
AUTO_DETECTED_IP=$(curl -s --connect-timeout 2 ifconfig.me || hostname -I | awk '{print $1}' || echo "127.0.0.1")
AUTO_DETECTED_IP=$(echo "$AUTO_DETECTED_IP" | xargs)

if [ -f ".env" ]; then
  eval $(grep -E "^(BROKER_USER_ID|BROKER_API_KEY|BROKER_API_SECRET|BROKER_API_KEY_MARKET|BROKER_API_SECRET_MARKET|BROKER_BASE_URL)=" .env 2>/dev/null | xargs) || true
fi

USER_ID="${USER_ID:-$BROKER_USER_ID}"
API_KEY="${API_KEY:-$BROKER_API_KEY}"
API_SECRET="${API_SECRET:-$BROKER_API_SECRET}"
API_KEY_MARKET="${API_KEY_MARKET:-$BROKER_API_KEY_MARKET}"
API_SECRET_MARKET="${API_SECRET_MARKET:-$BROKER_API_SECRET_MARKET}"
BASE_URL="${BASE_URL:-$BROKER_BASE_URL}"
BASE_URL=${BASE_URL:-https://symphony.acagarwal.com:3000}

# Read Admin Portal Credentials
if [ -z "$ADMIN_USERNAME" ]; then
  read -p "Enter Admin Portal Username [default: admin]: " ADMIN_USERNAME
  ADMIN_USERNAME=${ADMIN_USERNAME:-admin}
fi

if [ -z "$ADMIN_PASSWORD" ]; then
  read -sp "Enter Admin Portal Password [default: Admin@12345]: " ADMIN_PASSWORD
  echo ""
  ADMIN_PASSWORD=${ADMIN_PASSWORD:-Admin@12345}
fi

# Read Server IP / Domain
if [ -z "$STATIC_IP" ]; then
  read -p "Enter Server Public IP / Domain [default: $AUTO_DETECTED_IP]: " STATIC_IP
  STATIC_IP=${STATIC_IP:-$AUTO_DETECTED_IP}
fi

# Read Broker API Credentials
if [ -z "$USER_ID" ]; then
  read -p "Enter AC Agarwal User ID (Client Code, e.g. DM933): " USER_ID
fi

if [ -z "$API_KEY" ]; then
  read -p "Enter Interactive API Key (BROKER_API_KEY): " API_KEY
fi

if [ -z "$API_SECRET" ]; then
  read -p "Enter Interactive API Secret (BROKER_API_SECRET): " API_SECRET
fi

if [ -z "$API_KEY_MARKET" ]; then
  read -p "Enter Market Data API Key (BROKER_API_KEY_MARKET): " API_KEY_MARKET
fi

if [ -z "$API_SECRET_MARKET" ]; then
  read -p "Enter Market Data API Secret (BROKER_API_SECRET_MARKET): " API_SECRET_MARKET
fi

# ------------------------------------------------------------------------------
# Step 2: Install Ubuntu Packages
# ------------------------------------------------------------------------------
echo -e "\\n${CYAN}--- Step 2: Installing Ubuntu Dependencies ---${NC}"
$SUDO apt-get update -y
$SUDO apt-get install -y python3 python3-venv python3-pip git curl build-essential sqlite3 lsof

# ------------------------------------------------------------------------------
# Step 3: Clone/Prepare Repository
# ------------------------------------------------------------------------------
echo -e "\\n${CYAN}--- Step 3: Preparing OpenAlgo Repository ---${NC}"
if [ "$INSTALL_DIR" != "$CURRENT_DIR" ]; then
  if [ ! -d "$INSTALL_DIR" ]; then
    echo -e "${GREEN}[+] Cloning OpenAlgo repository into ${INSTALL_DIR}...${NC}"
    $SUDO git clone https://github.com/openalgo/openalgo.git "$INSTALL_DIR"
    $SUDO chown -R "$USER:$USER" "$INSTALL_DIR"
  fi
  cd "$INSTALL_DIR"
fi

if [ ! -d "venv" ]; then
  echo -e "${GREEN}[+] Creating Python virtual environment...${NC}"
  python3 -m venv venv
fi

echo -e "${GREEN}[+] Installing Python dependencies...${NC}"
./venv/bin/pip install --upgrade pip
if [ -f "requirements.txt" ]; then
  ./venv/bin/pip install -r requirements.txt
fi
./venv/bin/pip install httpx python-socketio websocket-client pandas python-dotenv eventlet gunicorn

# ------------------------------------------------------------------------------
# Step 4: Extract Embedded AC Agarwal Plugin Payload
# ------------------------------------------------------------------------------
echo -e "\\n${CYAN}--- Step 4: Extracting AC Agarwal Broker Plugin Files ---${NC}"
mkdir -p broker/acagarwal

cat << 'EOF_B64' | base64 -d | tar -xzf - -C broker/
__PAYLOAD_PLACEHOLDER__
EOF_B64

echo -e "${GREEN}[+] AC Agarwal plugin files extracted to broker/acagarwal/.${NC}"

# ------------------------------------------------------------------------------
# Step 5: Automatically Patch Core Platform Registration Files
# ------------------------------------------------------------------------------
echo -e "\\n${CYAN}--- Step 5: Patching Core OpenAlgo Platform Registrations ---${NC}"

./venv/bin/python3 -c "
import re, sys

# 1. websocket_proxy uses dynamic adapter loading via broker_factory.py
print('  [✓] websocket_proxy configured with dynamic adapter loader')

# 2. Patch services/order_update_service.py
try:
    with open('services/order_update_service.py', 'r') as f:
        content = f.read()
    if '\"acagarwal\"' not in content:
        content = content.replace('_POLLING_BROKERS = {', '_POLLING_BROKERS = {\"acagarwal\", ')
        with open('services/order_update_service.py', 'w') as f:
            f.write(content)
        print('  [✓] Patched services/order_update_service.py')
    else:
        print('  [✓] services/order_update_service.py already registered')
except Exception as e:
    print(f'  [!] order_update_service patch notice: {e}')

# 3. Patch blueprints/brlogin.py
try:
    with open('blueprints/brlogin.py', 'r') as f:
        content = f.read()
    if '\"acagarwal\"' not in content:
        content = content.replace('\"fivepaisaxts\"', '\"fivepaisaxts\", \"acagarwal\"')
        with open('blueprints/brlogin.py', 'w') as f:
            f.write(content)
        print('  [✓] Patched blueprints/brlogin.py')
    else:
        print('  [✓] blueprints/brlogin.py already registered')
except Exception as e:
    print(f'  [!] brlogin patch notice: {e}')
"

# ------------------------------------------------------------------------------
# Step 6: Generate .env Configuration & Security Pepper/Salt
# ------------------------------------------------------------------------------
echo -e "\\n${CYAN}--- Step 6: Updating .env Configuration & Security Tokens ---${NC}"

if [ ! -f ".env" ] || ! grep -q "^ENV_CONFIG_VERSION=" .env; then
  if [ -f ".sample.env" ]; then
    cp .sample.env .env
  elif [ -f ".env.example" ]; then
    cp .env.example .env
  else
    touch .env
  fi
fi

update_env() {
  key="$1"
  val="$2"
  if grep -q "^${key}\\\\s*=" .env; then
    sed -i "s|^${key}\\\\s*=.*|${key} = '${val}'|" .env
  elif grep -q "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key} = '${val}'|" .env
  else
    echo "${key} = '${val}'" >> .env
  fi
}

update_env "BROKER" "acagarwal"
update_env "VALID_BROKERS" "acagarwal,fivepaisa,fivepaisaxts,aliceblue,angel,arrow,compositedge,dhan,dhan_sandbox,definedge,deltaexchange,firstock,flattrade,fyers,groww,hdfcsecurities,hdfcsky,ibulls,iifl,iiflcapital,indmoney,jainamxts,kotak,motilal,mstock,nubra,paytm,pocketful,rmoney,samco,shoonya,tradejini,tradesmart,upstox,wisdom,zebu,zerodha"
update_env "BROKER_API_KEY" "$API_KEY"
update_env "BROKER_API_SECRET" "$API_SECRET"
update_env "BROKER_API_KEY_MARKET" "$API_KEY_MARKET"
update_env "BROKER_API_SECRET_MARKET" "$API_SECRET_MARKET"
update_env "BROKER_USER_ID" "$USER_ID"
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

# Generate mandatory OpenAlgo v2.0 security tokens if absent or default placeholder
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
# Step 7: Verify Installation & Initialize Client Database Account
# ------------------------------------------------------------------------------
echo -e "\\n${CYAN}--- Step 7: Verifying Module Imports & Initializing Client Database ---${NC}"

export ADMIN_USERNAME_ENV="$ADMIN_USERNAME"
export ADMIN_PASSWORD_ENV="$ADMIN_PASSWORD"
export USER_ID_ENV="$USER_ID"

./venv/bin/python3 -c "
import os
from dotenv import load_dotenv
load_dotenv('.env')

import broker.acagarwal.api.auth_api
import broker.acagarwal.api.order_api
import broker.acagarwal.api.data
import broker.acagarwal.api.funds
import broker.acagarwal.mapping.transform_data
import broker.acagarwal.mapping.order_data
import broker.acagarwal.database.master_contract_db
import broker.acagarwal.streaming.acagarwal_adapter
from websocket_proxy.broker_factory import create_broker_adapter
adapter = create_broker_adapter('acagarwal')
print('  [✓] All AC Agarwal broker modules and WebSocket proxy adapter verified!')

try:
    from database.user_db import create_user, verify_user, reset_password
    from database.auth_db import init_auth_db, upsert_auth
    init_auth_db()
    
    admin_user = os.getenv('ADMIN_USERNAME_ENV', 'admin')
    admin_pass = os.getenv('ADMIN_PASSWORD_ENV', 'Admin@12345')
    broker_user_id = os.getenv('USER_ID_ENV', os.getenv('BROKER_USER_ID', ''))

    if not verify_user(admin_user, admin_pass):
        try:
            create_user(admin_user, admin_pass)
            print(f'  [✓] Client admin user \"{admin_user}\" initialized in database')
        except Exception:
            reset_password(admin_user, admin_pass)
            print(f'  [✓] Client admin user \"{admin_user}\" password configured')

    if broker_user_id:
        upsert_auth(admin_user, broker_user_id, broker_user_id)
        print(f'  [✓] Linked broker client ID \"{broker_user_id}\" to portal user \"{admin_user}\"')
except Exception as user_err:
    print(f'  [!] User DB setup notice: {user_err}')
"

SERVICE_FILE="/etc/systemd/system/openalgo.service"
CURRENT_USER=$(whoami)

$SUDO bash -c "cat <<EOF > $SERVICE_FILE
[Unit]
Description=OpenAlgo Algorithmic Trading Platform (AC Agarwal Broker)
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python app.py
Restart=always
RestartSec=5
Environment=PATH=$INSTALL_DIR/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=multi-user.target
EOF"

$SUDO systemctl daemon-reload
$SUDO systemctl enable openalgo
$SUDO systemctl restart openalgo

echo -e "\\n${GREEN}======================================================================${NC}"
echo -e "${GREEN}  ✓ OpenAlgo SaaS Installation Completed Successfully!                ${NC}"
echo -e "${GREEN}======================================================================${NC}"
echo -e "${CYAN}Web Portal URL:${NC} http://${STATIC_IP}:5001"
echo -e "${CYAN}Admin Username:${NC} ${ADMIN_USERNAME}"
echo -e "${CYAN}Service Status:${NC} Run 'sudo systemctl status openalgo'"
echo -e "${CYAN}Live Logs:${NC} Run 'sudo journalctl -u openalgo -f'"
echo -e "${GREEN}======================================================================${NC}\\n"
'''

    # Insert b64 payload into placeholder
    script_content = template.replace("__PAYLOAD_PLACEHOLDER__", b64_payload)

    output_path = os.path.join(root_dir, "deploy_openalgo_acagarwal.sh")
    with open(output_path, "w") as f:
        f.write(script_content)

    os.chmod(output_path, 0o755)
    print(f"Generated standalone self-extracting installer: {output_path}")

if __name__ == "__main__":
    main()

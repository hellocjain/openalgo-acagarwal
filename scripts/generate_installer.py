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
# Step 1: Interactive Credential Setup
# ------------------------------------------------------------------------------
echo -e "\\n${CYAN}--- Step 1: AC Agarwal Credentials Configuration ---${NC}"
read -p "Enter AC Agarwal User ID (Client Code, e.g. DM933): " USER_ID
read -p "Enter Interactive API Key (BROKER_API_KEY): " API_KEY
read -p "Enter Interactive API Secret (BROKER_API_SECRET): " API_SECRET
read -p "Enter Market Data API Key (BROKER_API_KEY_MARKET): " API_KEY_MARKET
read -p "Enter Market Data API Secret (BROKER_API_SECRET_MARKET): " API_SECRET_MARKET
read -p "Enter AC Agarwal Base URL [default: https://symphony.acagarwal.com:3000]: " BASE_URL
BASE_URL=${BASE_URL:-https://symphony.acagarwal.com:3000}

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
./venv/bin/pip install httpx python-socketio websocket-client pandas python-dotenv

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

# 1. Patch websocket_proxy/__init__.py
try:
    with open('websocket_proxy/__init__.py', 'r') as f:
        content = f.read()
    if 'ACAgarwalWebSocketAdapter' not in content:
        import_line = 'from broker.acagarwal.streaming.acagarwal_adapter import ACAgarwalWebSocketAdapter\\n'
        content = content.replace('from broker.fivepaisaxts.streaming.fivepaisaxts_adapter import FivepaisaXTSWebSocketAdapter', 'from broker.fivepaisaxts.streaming.fivepaisaxts_adapter import FivepaisaXTSWebSocketAdapter\\n' + import_line)
        reg_line = 'register_adapter(\"acagarwal\", ACAgarwalWebSocketAdapter)\\n'
        content = content.replace('register_adapter(\"fivepaisaxts\", FivepaisaXTSWebSocketAdapter)', 'register_adapter(\"fivepaisaxts\", FivepaisaXTSWebSocketAdapter)\\n' + reg_line)
        with open('websocket_proxy/__init__.py', 'w') as f:
            f.write(content)
        print('  [✓] Patched websocket_proxy/__init__.py')
    else:
        print('  [✓] websocket_proxy/__init__.py already registered')
except Exception as e:
    print(f'  [!] websocket_proxy patch notice: {e}')

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

if [ ! -f ".env" ]; then
  if [ -f ".env.example" ]; then
    cp .env.example .env
  else
    touch .env
  fi
fi

update_env() {
  key="$1"
  val="$2"
  if grep -q "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key}=${val}|" .env
  else
    echo "${key}=${val}" >> .env
  fi
}

update_env "BROKER" "acagarwal"
update_env "BROKER_API_KEY" "$API_KEY"
update_env "BROKER_API_SECRET" "$API_SECRET"
update_env "BROKER_API_KEY_MARKET" "$API_KEY_MARKET"
update_env "BROKER_API_SECRET_MARKET" "$API_SECRET_MARKET"
update_env "BROKER_USER_ID" "$USER_ID"
update_env "BROKER_BASE_URL" "$BASE_URL"
update_env "HOST" "0.0.0.0"
update_env "PORT" "5001"

# Generate mandatory OpenAlgo v2.0 security tokens if absent or default
if ! grep -q "^API_KEY_PEPPER=" .env || grep -q "^API_KEY_PEPPER=$" .env; then
  GEN_PEPPER=$(./venv/bin/python3 -c "import secrets; print(secrets.token_hex(32))")
  update_env "API_KEY_PEPPER" "$GEN_PEPPER"
fi

if ! grep -q "^FERNET_SALT=" .env || grep -q "^FERNET_SALT=$" .env; then
  GEN_SALT=$(./venv/bin/python3 -c "import secrets; print(secrets.token_hex(32))")
  update_env "FERNET_SALT" "$GEN_SALT"
fi

if ! grep -q "^SECRET_KEY=" .env || grep -q "^SECRET_KEY=$" .env; then
  GEN_SECRET=$(./venv/bin/python3 -c "import secrets; print(secrets.token_hex(32))")
  update_env "SECRET_KEY" "$GEN_SECRET"
  update_env "APP_KEY" "$GEN_SECRET"
fi

# ------------------------------------------------------------------------------
# Step 7: Verify Installation & Systemd Service
# ------------------------------------------------------------------------------
echo -e "\\n${CYAN}--- Step 7: Verifying Module Imports & Configuring systemd ---${NC}"

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
echo -e "${GREEN}  ✓ OpenAlgo + AC Agarwal Installation Completed Successfully!       ${NC}"
echo -e "${GREEN}======================================================================${NC}"
echo -e "${CYAN}Web Application URL:${NC} http://$(curl -s ifconfig.me || echo 'YOUR_SERVER_IP'):5001"
echo -e "${CYAN}Service Status:${NC} Run 'sudo systemctl status openalgo'"
echo -e "${CYAN}Live Logs:${NC} Run 'sudo journalctl -u openalgo -f'"
echo -e "${GREEN}======================================================================${NC}\\n"
'''

    final_script = template.replace("__PAYLOAD_PLACEHOLDER__", b64_payload)
    out_file = os.path.join(root_dir, "deploy_openalgo_acagarwal.sh")
    with open(out_file, "w") as f:
        f.write(final_script)
    os.chmod(out_file, 0o755)
    print(f"Generated standalone self-extracting installer: {out_file}")

if __name__ == "__main__":
    main()

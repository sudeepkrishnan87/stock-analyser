#!/bin/bash
# ════════════════════════════════════════════════════════════════════
#  One-shot EC2 bootstrap script
#  Run ONCE on a fresh Ubuntu 24.04 LTS t3.micro instance.
#
#  Usage:
#    bash setup.sh <github-repo-url> <your-domain>
#
#  Example:
#    bash setup.sh https://github.com/sudeepkrishnan/stock-analyser.git jarvis.mytechexp.com
# ════════════════════════════════════════════════════════════════════
set -euo pipefail

REPO_URL="${1:-}"
DOMAIN="${2:-}"
APP_DIR="/opt/stockbot"
EMAIL="sudeepkrishnan87@gmail.com"

if [ -z "$REPO_URL" ] || [ -z "$DOMAIN" ]; then
    echo "Usage: bash setup.sh <github-repo-url> <domain>"
    echo "Example: bash setup.sh https://github.com/sudeepkrishnan/stock-analyser.git jarvis.mytechexp.com"
    exit 1
fi

echo "════════════════════════════════════════════════"
echo "  StockBot — EC2 Production Setup"
echo "  Repo  : $REPO_URL"
echo "  Domain: $DOMAIN"
echo "════════════════════════════════════════════════"

# ── 1. System updates ────────────────────────────────────────────
echo "[1/8] System update..."
sudo apt-get update -qq && sudo apt-get upgrade -y -qq

# ── 2. Install Docker + Docker Compose ──────────────────────────
echo "[2/8] Installing Docker..."
sudo apt-get install -y -qq ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
    sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
    sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update -qq
sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker ubuntu
sudo systemctl enable docker

# ── 3. Install AWS CLI (for Parameter Store) ─────────────────────
echo "[3/8] Installing AWS CLI..."
sudo apt-get install -y -qq unzip
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
unzip -q /tmp/awscliv2.zip -d /tmp && sudo /tmp/aws/install && rm -rf /tmp/aws /tmp/awscliv2.zip

# ── 4. Harden SSH ────────────────────────────────────────────────
echo "[4/8] Hardening SSH..."
sudo sed -i 's/#PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sudo sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo systemctl reload sshd

# ── 5. Firewall ───────────────────────────────────────────────────
echo "[5/8] Configuring UFW firewall..."
sudo ufw --force reset
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp    comment "SSH"
sudo ufw allow 80/tcp    comment "HTTP (redirect to HTTPS)"
sudo ufw allow 443/tcp   comment "HTTPS"
sudo ufw --force enable

# ── 6. Clone repository ───────────────────────────────────────────
echo "[6/8] Cloning repository..."
sudo mkdir -p "$APP_DIR"
sudo chown ubuntu:ubuntu "$APP_DIR"
git clone "$REPO_URL" "$APP_DIR"
cd "$APP_DIR"

# Inject real domain into nginx config
sed -i "s/jarvis\.mytechexp\.com/$DOMAIN/g" nginx/conf.d/stockbot.conf

# ── 7. SSL certificate (Let's Encrypt) ───────────────────────────
echo "[7/8] Obtaining SSL certificate for $DOMAIN..."
# Run a temporary nginx on port 80 for ACME challenge
docker run -d --name tmp-nginx \
    -p 80:80 \
    -v "$(pwd)/nginx/conf.d:/etc/nginx/conf.d:ro" \
    nginx:alpine 2>/dev/null || true

docker run --rm \
    -v /etc/letsencrypt:/etc/letsencrypt \
    -v /var/www/certbot:/var/www/certbot \
    certbot/certbot certonly \
    --webroot -w /var/www/certbot \
    --email "$EMAIL" --agree-tos --no-eff-email \
    -d "$DOMAIN" || echo "⚠ SSL cert failed — check DNS first, then re-run: certbot certonly ..."

docker stop tmp-nginx 2>/dev/null && docker rm tmp-nginx 2>/dev/null || true

# ── 8. Install & start systemd service ───────────────────────────
echo "[8/8] Installing systemd service..."
sudo cp "$APP_DIR/deploy/stockbot.service" /etc/systemd/system/stockbot.service
sudo systemctl daemon-reload
sudo systemctl enable stockbot
sudo systemctl start stockbot

echo ""
echo "════════════════════════════════════════════════"
echo "  ✅  Setup complete!"
echo ""
echo "  Next steps:"
echo "  1. Upload secrets to AWS Parameter Store:"
echo "     ./deploy/add-secrets.sh   (run from your Mac)"
echo ""
echo "  2. Update broker redirect URLs to:"
echo "     https://$DOMAIN/api/auth/callback"
echo "     https://$DOMAIN/api/auth/fyers/callback"
echo ""
echo "  3. Monitor:"
echo "     sudo systemctl status stockbot"
echo "     docker compose -f $APP_DIR/docker-compose.yml logs -f"
echo "════════════════════════════════════════════════"

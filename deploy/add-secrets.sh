#!/bin/bash
# ════════════════════════════════════════════════════════════════════
#  Push all secrets to AWS Systems Manager Parameter Store.
#  Run this ONCE from your LOCAL Mac (not the EC2 instance).
#
#  Prerequisites:
#    aws configure   (set your AWS credentials + region ap-south-1)
#
#  Usage:
#    chmod +x deploy/add-secrets.sh
#    ./deploy/add-secrets.sh
# ════════════════════════════════════════════════════════════════════
set -euo pipefail

REGION="ap-south-1"
PREFIX="/stockbot"

put() {
    local name="$1"
    local value="$2"
    if [ -z "$value" ]; then
        echo "  SKIP  $PREFIX/$name (empty)"
        return
    fi
    aws ssm put-parameter \
        --region "$REGION" \
        --name "$PREFIX/$name" \
        --value "$value" \
        --type "SecureString" \
        --overwrite \
        --no-cli-pager > /dev/null
    echo "  OK    $PREFIX/$name"
}

echo "Uploading secrets to AWS Parameter Store ($REGION)..."
echo ""

# Load from your local .env file
if [ -f "backend/.env" ]; then
    set -o allexport
    source backend/.env
    set +o allexport
fi

put "API_SECRET_KEY"       "${API_SECRET_KEY:-}"
put "KITE_API_KEY"         "${KITE_API_KEY:-}"
put "KITE_API_SECRET"      "${KITE_API_SECRET:-}"
put "KITE_REDIRECT_URL"    "${KITE_REDIRECT_URL:-}"
put "FYERS_APP_ID"         "${FYERS_APP_ID:-}"
put "FYERS_SECRET"         "${FYERS_SECRET:-}"
put "FYERS_REDIRECT_URL"   "${FYERS_REDIRECT_URL:-}"
put "ANTHROPIC_API_KEY"    "${ANTHROPIC_API_KEY:-}"
put "EMAIL_SENDER"         "${EMAIL_SENDER:-}"
put "EMAIL_PASSWORD"       "${EMAIL_PASSWORD:-}"
put "EMAIL_RECIPIENT"      "${EMAIL_RECIPIENT:-}"
put "TWILIO_ACCOUNT_SID"   "${TWILIO_ACCOUNT_SID:-}"
put "TWILIO_AUTH_TOKEN"    "${TWILIO_AUTH_TOKEN:-}"
put "TWILIO_WHATSAPP_TO"   "${TWILIO_WHATSAPP_TO:-}"

echo ""
echo "Done. Secrets stored encrypted in Parameter Store."
echo "Your EC2 instance will read them via IAM role — no .env needed on server."

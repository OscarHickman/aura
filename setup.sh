#!/bin/bash
# AURA interactive configuration wizard
set -e

echo "=================================================="
echo "          AURA Setup Configuration Wizard         "
echo "=================================================="
echo

# 1. API Keys configuration
echo "--- 1. AI LLM Providers & API Keys ---"
echo "AURA supports Groq (recommended for speed), OpenAI, Anthropic, and Google Gemini."
read -p "Select default LLM Provider (groq/openai/anthropic/google) [groq]: " LLM_PROVIDER
LLM_PROVIDER=${LLM_PROVIDER:-groq}

GROQ_API_KEY=""
OPENAI_API_KEY=""
ANTHROPIC_API_KEY=""
GOOGLE_API_KEY=""

case $LLM_PROVIDER in
  groq)
    read -p "Enter Groq API Key: " GROQ_API_KEY
    ;;
  openai)
    read -p "Enter OpenAI API Key: " OPENAI_API_KEY
    ;;
  anthropic)
    read -p "Enter Anthropic API Key: " ANTHROPIC_API_KEY
    ;;
  google)
    read -p "Enter Google/Gemini API Key: " GOOGLE_API_KEY
    ;;
esac

# Create or update environment file .env
echo "Saving environment variables to .env..."
cat << EOF > .env
LLM_PROVIDER=$LLM_PROVIDER
GROQ_API_KEY=$GROQ_API_KEY
OPENAI_API_KEY=$OPENAI_API_KEY
ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY
GOOGLE_API_KEY=$GOOGLE_API_KEY
EOF

# 2. Email configuration
echo
echo "--- 2. Email Digest / Notification Setup ---"
read -p "Would you like to configure email digests? (y/n) [n]: " CONFIRM_EMAIL
if [[ "$CONFIRM_EMAIL" =~ ^[Yy]$ ]]; then
  read -p "SMTP Host [smtp.gmail.com]: " SMTP_HOST
  SMTP_HOST=${SMTP_HOST:-smtp.gmail.com}
  
  read -p "SMTP Port [587]: " SMTP_PORT
  SMTP_PORT=${SMTP_PORT:-587}
  
  read -p "SMTP Username (your email): " SMTP_USER
  read -p "SMTP Password (app-specific password): " -s SMTP_PASS
  echo
  read -p "Recipient Email (where to send digests): " RECIPIENT_EMAIL
  
  mkdir -p user_credentials
  cat << EOF > user_credentials/email_config.json
{
  "smtp_host": "$SMTP_HOST",
  "smtp_port": $SMTP_PORT,
  "smtp_username": "$SMTP_USER",
  "smtp_password": "$SMTP_PASS",
  "from_email": "$SMTP_USER",
  "to_email": "$RECIPIENT_EMAIL",
  "use_tls": true,
  "use_ssl": false,
  "subject_prefix": "AURA Paper Digest"
}
EOF
  echo "Email configuration saved to user_credentials/email_config.json"
fi

# 3. Create initial config.yaml if it doesn't exist
if [ ! -f config.yaml ]; then
  echo
  echo "--- 3. Category Preferences ---"
  echo "Enter arXiv categories to monitor, separated by commas."
  echo "Examples: astro-ph.CO (Cosmology), astro-ph.GA (Galaxy Astrophysics), cs.LG (Machine Learning)"
  read -p "Categories [astro-ph.CO,cs.LG]: " SELECTED_CATS
  SELECTED_CATS=${SELECTED_CATS:-"astro-ph.CO,cs.LG"}
  
  YAML_CATS=""
  IFS=',' read -ra ADDR <<< "$SELECTED_CATS"
  for cat in "${ADDR[@]}"; do
    YAML_CATS="$YAML_CATS  - \"$(echo $cat | xargs)\"\n"
  done

  echo "Creating default config.yaml..."
  cat << EOF > config.yaml
# AURA Configuration
data_dir: "data"
categories:
$(printf "$YAML_CATS")
embedding_model: "all-MiniLM-L6-v2"

fetch:
  max_results: 200
  days_back: 2
  generate_on_fetch: false

scheduler:
  enabled: true
  fetch_hour: 8
  fetch_minute: 0
EOF
  echo "Configuration saved to config.yaml"
fi

echo
echo "=================================================="
echo "Setup complete! You can now start AURA using:"
echo "  docker-compose up -d"
echo "Or locally by running:"
echo "  python run.py serve"
echo "=================================================="

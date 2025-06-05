#!/bin/bash

echo
echo -e "\033[1;34m📦 Setting up OMR aliases and environment...\033[0m"
echo

# Step 1: Create the alias file
cat > ~/.my_aliases.sh <<'EOF'
# === Custom Aliases ===
alias omrsend='python3 upload.py'         # 📤 Send zipped files to Telegram
alias omrupdate='bash bot_update.sh'      # 🔄 Update bot scripts
alias omrsettings='bash settings.sh'      # ⚙️  Open settings menu
alias autoscan='python3 web.py'           # 📷 Start auto scanning server
alias omr='python3 app.py'                # 📝 Run OMR scanner app
EOF

# Step 2: Ensure aliases file is sourced in .bashrc
if ! grep -q "source ~/.my_aliases.sh" ~/.bashrc; then
    echo "source ~/.my_aliases.sh" >> ~/.bashrc
    echo -e "\033[1;32m✅ Aliases linked to ~/.bashrc\033[0m"
else
    echo -e "\033[1;33mℹ️  Aliases already linked in ~/.bashrc\033[0m"
fi

# Step 3: Load aliases now for current session
source ~/.my_aliases.sh

# Step 4: Display available alias commands
echo -e "\n\033[1;34m================ ALIAS COMMANDS =================\033[0m"
echo -e "\033[1;32m  omrsend      \033[0m → 📤 Send zipped files to Telegram"
echo -e "\033[1;32m  omrupdate    \033[0m → 🔄 Update bot scripts"
echo -e "\033[1;32m  omrsettings  \033[0m → ⚙️  Open settings menu"
echo -e "\033[1;32m  autoscan     \033[0m → 📷 Start auto scanning server"
echo -e "\033[1;32m  omr          \033[0m → 📝 Run OMR scanner app"
echo -e "\033[1;34m================================================\033[0m"

# Step 5: Check if script was sourced
(return 0 2>/dev/null) && sourced=true || sourced=false

# Step 6: Countdown and exit if sourced
if $sourced; then
    echo -e "\n\033[1;31m⏳ Closing Termux in 5 seconds...\033[0m"
    echo -e "\033[1;33m🔁 Please reopen Termux to use these commands.\033[0m"
    sleep 5
    exit
else
    echo -e "\n\033[1;33m⚠️  Termux not closed automatically because this script was not sourced.\033[0m"
    echo -e "\033[1;34m💡 Tip: Use \033[1;36msource setup.sh\033[0m to enable auto-close.\n"
fi

#!/bin/bash

# Step 1: Create the alias file
cat > ~/.my_aliases.sh <<'EOF'
# === Custom Aliases ===
alias omrsend='python3 upload.py'         # 📤 Send zipped files to Telegram
alias omrupdate='bash bot_update.sh'      # 🔄 Update bot scripts
alias omrsettings='bash settings.sh'      # ⚙️  Open settings menu
alias autoscan='python3 web.py'        # 📷 Start auto scanning server
alias omr='python3 app.py'             # 📝 Run OMR scanner app
EOF

# Step 2: Make sure .my_aliases.sh is sourced in .bashrc
if ! grep -q "source ~/.my_aliases.sh" ~/.bashrc; then
    echo "source ~/.my_aliases.sh" >> ~/.bashrc
    echo -e "\033[1;32m✅ Aliases added to ~/.my_aliases.sh and sourced in ~/.bashrc\033[0m"
else
    echo -e "\033[1;33mℹ️  Aliases file already sourced in ~/.bashrc\033[0m"
fi

# Step 3: Reload current shell to activate aliases
source ~/.my_aliases.sh

echo -e "\n\033[1;34m📌 Available Commands Now:\033[0m"
echo -e "\033[1;32m  omrsend      \033[0m - Send omr.zip to Telegram"
echo -e "\033[1;32m  omrupdate    \033[0m - Run bot_update.sh"
echo -e "\033[1;32m  omrsettings  \033[0m - Run settings.sh"
echo -e "\033[1;32m  autoscan  \033[0m - Run web.py"
echo -e "\033[1;32m  omr       \033[0m - Run app.py"

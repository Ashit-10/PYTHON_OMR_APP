#!/bin/bash

echo
echo -e "\033[1;34m📦 Setting up OMR aliases and environment...\033[0m"
echo

# Step 1: Create ~/bin and omr script
mkdir -p ~/bin

cat > ~/bin/omr <<'EOF'
#!/bin/bash

if [[ "$1" == "--help" || "$1" == "-h" ]]; then
  echo -e "\n\033[1;34m📝 OMR Scanner Help Menu\033[0m"
  echo -e "\033[1;32momr\033[0m         → 📝 Run the OMR scanner app"
  echo -e "\033[1;32momrsend\033[0m     → 📤 Send zipped files to Telegram"
  echo -e "\033[1;32momrupdate\033[0m   → 🔄 Update bot scripts"
  echo -e "\033[1;32momrsettings\033[0m → ⚙️  Open settings menu"
  echo -e "\033[1;32mautoscan\033[0m    → 📷 Start auto scanning server"
  echo -e "\033[1;32momredit\033[0m     → ✏️  Edit OMR answer key interactively"
  echo -e "\033[1;34mUsage:\033[0m omr [--help | -h]"
  exit 0
fi

# Default action: run the OMR app
python3 ~/app.py
EOF

chmod +x ~/bin/omr

# Step 2: Add ~/bin to PATH if not present
if ! grep -q 'export PATH="$HOME/bin:$PATH"' ~/.bashrc; then
    echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
    echo -e "\033[1;32m✅ Added ~/bin to PATH in .bashrc\033[0m"
else
    echo -e "\033[1;33mℹ️  ~/bin already in PATH\033[0m"
fi

# Step 3: Create the alias file (excluding omr)
cat > ~/.my_aliases.sh <<'EOF'
# === Custom Aliases ===
alias omrsend='python3 upload.py'         # 📤 Send zipped files to Telegram
alias omrupdate='bash bot_update.sh'      # 🔄 Update bot scripts
alias omrsettings='bash settings.sh'      # ⚙️  Open settings menu
alias autoscan='python3 web.py'           # 📷 Start auto scanning server
alias omredit='bash answer_key_edit.sh'   # ✏️  Edit OMR answer key interactively
EOF

# Step 4: Source the alias file
if ! grep -q "source ~/.my_aliases.sh" ~/.bashrc; then
    echo "source ~/.my_aliases.sh" >> ~/.bashrc
    echo -e "\033[1;32m✅ Linked aliases to ~/.bashrc\033[0m"
else
    echo -e "\033[1;33mℹ️  Aliases already linked in ~/.bashrc\033[0m"
fi
source ~/.my_aliases.sh

# Step 5: Show all available commands
echo -e "\n\033[1;34m================ ALIAS COMMANDS =================\033[0m"
echo -e "\033[1;32m  omr          \033[0m → 📝 Run the OMR scanner app (try omr --help)"
echo -e "\033[1;32m  omrsend      \033[0m → 📤 Send zipped files to Telegram"
echo -e "\033[1;32m  omrupdate    \033[0m → 🔄 Update bot scripts"
echo -e "\033[1;32m  omrsettings  \033[0m → ⚙️  Open settings menu"
echo -e "\033[1;32m  autoscan     \033[0m → 📷 Start auto scanning server"
echo -e "\033[1;32m  omredit      \033[0m → ✏️  Edit OMR answer key interactively"
echo -e "\033[1;34m================================================\033[0m"

# Step 6: Detect if sourced
(return 0 2>/dev/null) && sourced=true || sourced=false

if $sourced; then
    echo -e "\n\033[1;31m⏳ Closing Termux in 5 seconds...\033[0m"
    echo -e "\033[1;33m🔁 Please reopen Termux to use these commands.\033[0m"
    sleep 5
    exit
else
    echo -e "\n\033[1;33m⚠️  Termux not closed automatically because this script was not sourced.\033[0m"
    echo -e "\033[1;34m💡 Tip: Use \033[1;36msource setup.sh\033[0m to enable auto-close.\n"
fi

#!/bin/sh

# Clear screen first
clear

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
MAGENTA='\033[1;35m'
NC='\033[0m' # No Color

ANSWER_FILE="answer_key.txt"
TEMP_FILE=".tmp_answer_key.txt"

echo -e "${YELLOW}📦 Preparing to update project...${NC}"

# Backup the answer key
if [ -f "$ANSWER_FILE" ]; then
    cp "$ANSWER_FILE" "$TEMP_FILE"
    echo -e "${YELLOW}📝 Backed up answer key...${NC}"
else
    echo -e "${YELLOW}⚠️ No answer key found to backup.${NC}"
fi

# Mark directory as safe for Git
git config --global --add safe.directory "/storage/emulated/0/PYTHON_OMR_BOT"

echo -e "${YELLOW}🔄 Fetching latest updates from GitHub...${NC}"
git fetch --all

echo -e "${YELLOW}🧹 Resetting to latest version...${NC}"
git reset --hard origin/main

# Restore the answer key
if [ -f "$TEMP_FILE" ]; then
    mv "$TEMP_FILE" "$ANSWER_FILE"
    echo -e "${GREEN}✅ Answer key restored successfully!${NC}"
fi

# Final message in magenta (pinkish)
echo -e "${MAGENTA}🎉 Update complete! Your project is now up to date.${NC}"




alias send='python3 upload.py'
alias update='bash bot_update.sh'
alias settings='bash settings.sh'
alias autoscan='python3 web.py'
alias omr='python3 app.py'


echo
echo
#!/bin/bash

echo -e "\033[1;34m================ ALIAS COMMANDS =================\033[0m"
echo -e "\033[1;32msend      \033[0m → 📤 Send zipped files to Telegram"
echo -e "\033[1;32mupdate    \033[0m → 🔄 Update bot scripts"
echo -e "\033[1;32msettings  \033[0m → ⚙️  Open settings menu"
echo -e "\033[1;32mautoscan  \033[0m → 📷 Start auto scanning server"
echo -e "\033[1;32momr       \033[0m → 📝 Run OMR scanner app"
echo -e "\033[1;34m================================================\033[0m"















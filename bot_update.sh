#!/bin/sh

# Clear screen first
clear

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
MAGENTA='\033[1;35m'
NC='\033[0m' # No Color

ANSWER_FILE="answer_key.txt"
CONFIG_FILE="config.cfg"

TEMP_ANSWER_FILE=".tmp_answer_key.txt"
TEMP_CONFIG_FILE=".tmp_config.cfg"

echo -e "${YELLOW}📦 Preparing to update project...${NC}"

# Backup the answer key
if [ -f "$ANSWER_FILE" ]; then
    cp "$ANSWER_FILE" "$TEMP_ANSWER_FILE"
    echo -e "${YELLOW}📝 Backed up answer key...${NC}"
else
    echo -e "${YELLOW}⚠️ No answer key found to backup.${NC}"
fi

# Backup the config file
if [ -f "$CONFIG_FILE" ]; then
    cp "$CONFIG_FILE" "$TEMP_CONFIG_FILE"
    echo -e "${YELLOW}📝 Backed up config file...${NC}"
else
    echo -e "${YELLOW}⚠️ No config file found to backup.${NC}"
fi

# Mark directory as safe for Git
git config --global --add safe.directory "/storage/emulated/0/PYTHON_OMR_APP"

echo -e "${YELLOW}🔄 Fetching latest updates from GitHub...${NC}"
git fetch --all

echo -e "${YELLOW}🧹 Resetting to latest version...${NC}"
git reset --hard origin/main

# Restore the answer key
if [ -f "$TEMP_ANSWER_FILE" ]; then
    mv "$TEMP_ANSWER_FILE" "$ANSWER_FILE"
    echo -e "${GREEN}✅ Answer key restored successfully!${NC}"
fi

# Restore the config file
if [ -f "$TEMP_CONFIG_FILE" ]; then
    mv "$TEMP_CONFIG_FILE" "$CONFIG_FILE"
    echo -e "${GREEN}✅ Config file restored successfully!${NC}"
fi

# Final message in magenta (pinkish)
echo -e "${MAGENTA}🎉 Update complete! Your project is now up to date.${NC}"

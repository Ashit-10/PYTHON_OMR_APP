#!/data/data/com.termux/files/usr/bin/bash

# ========== COLORS ==========
RED='\033[1;31m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
MAGENTA='\033[1;35m'
CYAN='\033[1;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ========== FILE =============
FILE="answer_key.txt"

# ========== CHECK JQ =========
if ! command -v jq >/dev/null; then
    echo -e "${YELLOW}Installing jq...${RESET}"
    pkg install -y jq
    [[ $? -ne 0 ]] && echo -e "${RED}❌ Failed to install jq.${RESET}" && exit 1
fi

# ========== FILE CHECK ========
if [ ! -f "$FILE" ]; then
    echo -e "${RED}❌ File $FILE not found!${RESET}"
    exit 1
fi

cp "$FILE" "${FILE}.bak"

# ========== MAIN MENU =========
while true; do
    clear
    echo -e "    ${BLUE}${BOLD}📘 OMR Answer Key Editor${RESET}"
    echo -e "    ${MAGENTA}──────────────────────────────────────────${RESET}"
    echo -e "    ${CYAN}1.${RESET} View Answer for a Question"
    echo -e "    ${CYAN}2.${RESET} Edit Answer for a Question"
    echo -e "    ${CYAN}3.${RESET} View All Questions & Answers"
    echo -e "    ${CYAN}4.${RESET} Restore from Backup"
    echo -e "    ${CYAN}q.${RESET} Quit"
    echo -e "    ${MAGENTA}──────────────────────────────────────────${RESET}"
    read -p "    ${BOLD}Choose an option (1–4 or q): ${RESET}" choice

    case "$choice" in
        1)
            while true; do
                read -p "    🔎 Enter question number to view (${YELLOW}q to back${RESET}): " qnum
                [[ "$qnum" =~ ^[Qq]$ ]] && break
                if ! [[ "$qnum" =~ ^[0-9]+$ ]]; then
                    echo -e "    ${RED}❌ Invalid input. Use numbers like 1, 2, 3...${RESET}"
                    continue
                fi
                if jq -e ".[\"$qnum\"]" "$FILE" >/dev/null; then
                    ans=$(jq -r ".[\"$qnum\"] | join(\", \")" "$FILE")
                    echo -e "    ${GREEN}Q$qnum → ${YELLOW}[$ans]${RESET}"
                else
                    echo -e "    ${RED}⚠️ Q$qnum not found.${RESET}"
                fi
            done
            ;;
        2)
            while true; do
                read -p "    ✏️ Enter question number to edit (${YELLOW}q to back${RESET}): " qnum
                [[ "$qnum" =~ ^[Qq]$ ]] && break
                if ! [[ "$qnum" =~ ^[0-9]+$ ]]; then
                    echo -e "    ${RED}❌ Question number must be an integer.${RESET}"
                    continue
                fi

                # Show current answer if exists
                if jq -e ".[\"$qnum\"]" "$FILE" >/dev/null; then
                    current=$(jq -r ".[\"$qnum\"] | join(\", \")" "$FILE")
                    echo -e "    🔎 Current: ${YELLOW}[$current]${RESET}"
                else
                    echo -e "    ${RED}⚠️ Q$qnum not found. Adding new.${RESET}"
                fi

                read -p "    ➕ Enter new option(s) (A–D, comma separated): " input
                clean_input=$(echo "$input" | tr '[:lower:]' '[:upper:]' | sed 's/ //g')

                if ! echo "$clean_input" | grep -Eq '^([A-D](,[A-D]){0,3})$'; then
                    echo -e "    ${RED}❌ Invalid input. Use A,B,C,D only (max 4).${RESET}"
                    continue
                fi

                formatted=$(echo "$clean_input" | awk -F, '{
                    printf "[";
                    for(i=1; i<=NF; i++) {
                        printf "\"%s\"", $i;
                        if (i < NF) printf ",";
                    }
                    print "]";
                }')

                tmpfile=$(mktemp)
                jq ".\"$qnum\" = $formatted" "$FILE" > "$tmpfile" && mv "$tmpfile" "$FILE"
                updated=$(jq -r ".[\"$qnum\"] | join(\", \")" "$FILE")
                echo -e "    ${GREEN}✅ Q$qnum updated to → ${YELLOW}[$updated]${RESET}"
            done
            ;;
        3)
            echo -e "    ${CYAN}📜 Showing all questions... (press ${YELLOW}q${CYAN} to exit)${RESET}"
            jq -r 'to_entries[] | "    \033[1;36mQ\(.key):\033[0m \033[1;33m\(.value | join(\", \"))\033[0m"' "$FILE" | less -R
            ;;
        4)
            cp "${FILE}.bak" "$FILE"
            echo -e "    ${YELLOW}🔁 Restored from backup.${RESET}"
            sleep 1
            ;;
        q|Q)
            echo -e "    ${CYAN}👋 Exiting. See you again!${RESET}"
            exit 0
            ;;
        *)
            echo -e "    ${RED}⚠️ Invalid choice. Try 1, 2, 3, 4 or q.${RESET}"
            sleep 1
            ;;
    esac
done

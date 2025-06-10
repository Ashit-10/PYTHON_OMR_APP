#!/data/data/com.termux/files/usr/bin/bash

# ========= COLORS ===========
RED="\033[1;31m"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
BLUE="\033[1;34m"
CYAN="\033[1;36m"
MAGENTA="\033[1;35m"
BOLD="\033[1m"
RESET="\033[0m"

# ========= FILE ============
FILE="answer_key.txt"

# ========= JQ CHECK =========
if ! command -v jq > /dev/null; then
    echo -e "    ${YELLOW}Installing jq...${RESET}"
    pkg install -y jq
    if [ $? -ne 0 ]; then
        echo -e "    ${RED}❌ Failed to install jq.${RESET}"
        exit 1
    fi
fi

# ========= FILE CHECK ========
if [ ! -f "$FILE" ]; then
    echo -e "    ${RED}❌ File $FILE not found!${RESET}"
    exit 1
fi

# Backup original
cp "$FILE" "${FILE}.bak"

# ========= MAIN MENU =========
while true; do
    clear
    echo -e "    ${BLUE}${BOLD}📘 OMR Answer Key Editor${RESET}"
    echo -e "    ${MAGENTA}───────────────────────────────────────${RESET}"
    echo -e "    ${CYAN}1.${RESET} View Answer for a Question"
    echo -e "    ${CYAN}2.${RESET} Edit Answer for a Question"
    echo -e "    ${CYAN}3.${RESET} View All Questions & Answers"
    echo -e "    ${CYAN}4.${RESET} Restore from Backup"
    echo -e "    ${CYAN}q.${RESET} Quit"
    echo -e "    ${MAGENTA}───────────────────────────────────────${RESET}"
    read -p "    Choose an option (1–4 or q): " choice

    case "$choice" in
        1)
            while true; do
                read -p "    Enter question number to view (${YELLOW}q to back${RESET}): " qnum
                [[ "$qnum" == "q" || "$qnum" == "Q" ]] && break
                if jq -e ".[\"$qnum\"]" "$FILE" > /dev/null; then
                    ans=$(jq -c ".[\"$qnum\"]" "$FILE")
                    echo -e "    ${GREEN}Q$qnum → ${YELLOW}$ans${RESET}"
                else
                    echo -e "    ${RED}⚠️ Q$qnum not found in the file.${RESET}"
                fi
            done
            ;;
        2)
            while true; do
                read -p "    Enter question number to edit (${YELLOW}q to back${RESET}): " qnum
                [[ "$qnum" == "q" || "$qnum" == "Q" ]] && break

                read -p "    Enter new option(s) (A–D, comma separated): " input
                clean_input=$(echo "$input" | tr '[:lower:]' '[:upper:]' | sed 's/ //g')

                if ! echo "$clean_input" | grep -Eq '^([A-D](,[A-D]){0,3})$'; then
                    echo -e "    ${RED}❌ Invalid! Use only A,B,C,D (comma separated).${RESET}"
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
                echo -e "    ${GREEN}✅ Q$qnum updated to ${YELLOW}$formatted${RESET}"
            done
            ;;
        3)
            echo -e "    ${BLUE}📜 Showing all questions (press q to quit view)...${RESET}"
            jq -r 'to_entries[] | "    \033[1;36mQ\(.key):\033[0m \033[1;33m\(.value)\033[0m"' "$FILE" | less -R
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
            echo -e "    ${RED}⚠️ Invalid option. Try again.${RESET}"
            sleep 1
            ;;
    esac
done

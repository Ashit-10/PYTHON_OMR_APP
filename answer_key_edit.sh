#!/data/data/com.termux/files/usr/bin/bash

# ====== Colors ======
RED='\033[1;31m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
MAGENTA='\033[1;35m'
CYAN='\033[1;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ====== File ======
FILE="answer_key.txt"
[ ! -f "$FILE" ] && echo "{}" > "$FILE"
cp "$FILE" "${FILE}.bak"

# ====== Check jq ======
if ! command -v jq >/dev/null 2>&1; then
    echo -e "${YELLOW}Installing jq...${RESET}"
    pkg install -y jq || { echo -e "${RED}Failed to install jq.${RESET}"; exit 1; }
fi

# ====== Main Loop ======
while true; do
    clear
    MAX_Q=$(jq 'keys | map(tonumber) | max // 0' "$FILE")  # Auto-detect max question number

    echo -e "    ${BLUE}${BOLD}📘 OMR Answer Key Editor${RESET}"
    echo -e "    ${MAGENTA}─────────────────────────────────────────────${RESET}"
    echo -e "    ${CYAN}1.${RESET} View Answer for a Question"
    echo -e "    ${CYAN}2.${RESET} Edit Answer for a Question"
    echo -e "    ${CYAN}3.${RESET} View All Questions & Answers"
    echo -e "    ${CYAN}4.${RESET} Restore from Backup"
    echo -e "    ${CYAN}q.${RESET} Quit"
    echo -e "    ${MAGENTA}─────────────────────────────────────────────${RESET}"
    echo -ne "    ${BOLD}Choose an option (1–4 or q): ${RESET}"
    read choice

    case "$choice" in
        1)
            while true; do
                echo -ne "    Enter question number (${YELLOW}q to back${RESET}): "
                read qnum
                [[ "$qnum" =~ ^[Qq]$ ]] && break
                if ! [[ "$qnum" =~ ^[0-9]+$ ]]; then
                    echo -e "    ${RED}❌ Invalid input. Use numbers only.${RESET}"
                    continue
                fi
                if (( qnum > MAX_Q )); then
                    echo -e "    ${RED}❌ Question $qnum not available. Maximum is $MAX_Q.${RESET}"
                    continue
                fi
                if jq -e ".[\"$qnum\"]" "$FILE" >/dev/null; then
                    ans=$(jq -r ".[\"$qnum\"] | join(\", \")" "$FILE")
                    echo -e "    ${GREEN}$qnum:${YELLOW} [$ans]${RESET}"
                else
                    echo -e "    ${RED}⚠️ $qnum not answered yet.${RESET}"
                fi
            done
            ;;
        2)
            while true; do
                echo -ne "    Enter question number to edit (${YELLOW}q to back${RESET}): "
                read qnum
                [[ "$qnum" =~ ^[Qq]$ ]] && break
                if ! [[ "$qnum" =~ ^[0-9]+$ ]]; then
                    echo -e "    ${RED}❌ Must be a number.${RESET}"
                    continue
                fi
                if (( qnum > MAX_Q )); then
                    echo -e "    ${RED}❌ Question $qnum not available. Maximum is $MAX_Q.${RESET}"
                    continue
                fi
                if jq -e ".[\"$qnum\"]" "$FILE" >/dev/null; then
                    current=$(jq -r ".[\"$qnum\"] | join(\", \")" "$FILE")
                    echo -e "    🔎 Current: ${YELLOW}[$current]${RESET}"
                else
                    echo -e "    ${RED}⚠️ $qnum not answered yet.${RESET}"
                fi

                echo -ne "    ➕ Enter new option(s) (A–D, comma-separated): "
                read input
                clean_input=$(echo "$input" | tr '[:lower:]' '[:upper:]' | sed 's/ //g')

                if ! echo "$clean_input" | grep -Eq '^([A-D](,[A-D]){0,3})$'; then
                    echo -e "    ${RED}❌ Use A,B,C,D only (up to 4, comma-separated).${RESET}"
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
                echo -e "    ${GREEN}✅ $qnum updated to → ${YELLOW}[$updated]${RESET}"
            done
            ;;
        3)
            echo -e "    ${CYAN}📋 Showing all answered questions in 3 columns:${RESET}"
            jq -r 'to_entries[] | select(.value | length > 0) | "\(.key): \(.value | join(","))"' "$FILE" |
            awk '{
                printf "%-16s", $0
                if (++count % 3 == 0) printf "\n"
            } END { if (count % 3 != 0) print "" }'
            echo -e "\n    ${MAGENTA}── End of List ──${RESET}"
            echo -ne "    Press Enter to go back..."
            read
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

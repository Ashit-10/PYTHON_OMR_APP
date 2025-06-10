#!/data/data/com.termux/files/usr/bin/bash

# Set color codes
GREEN="\033[1;32m"
RED="\033[1;31m"
YELLOW="\033[1;33m"
BLUE="\033[1;34m"
RESET="\033[0m"

FILE="answer_key.txt"

# Ensure file exists
if [ ! -f "$FILE" ]; then
    echo -e "    ${RED}❌ File $FILE not found!${RESET}"
    exit 1
fi

# Create backup
cp "$FILE" "${FILE}.bak"

# Menu loop
while true; do
    clear
    echo -e "    ${BLUE}📘 OMR Answer Key Editor${RESET}"
    echo "    ---------------------------"
    echo "    1. View Answer for a Question"
    echo "    2. Edit Answer for a Question"
    echo "    3. View All Questions & Answers"
    echo "    4. Restore from Backup"
    echo "    q. Quit"
    echo "    ---------------------------"
    read -p "    Choose an option (1-4 or q): " choice

    case "$choice" in
        1)
            read -p "    Enter question number: " qnum
            if jq -e ".[\"$qnum\"]" "$FILE" > /dev/null; then
                value=$(jq -c ".[\"$qnum\"]" "$FILE")
                echo -e "    ${GREEN}Question $qnum → $value${RESET}"
            else
                echo -e "    ${YELLOW}⚠️ Question $qnum not found.${RESET}"
            fi
            read -p "    Press enter to continue..."
            ;;
        2)
            read -p "    Enter question number to edit: " qnum
            read -p "    Enter new option(s) (A-D, comma separated): " input
            clean_input=$(echo "$input" | tr '[:lower:]' '[:upper:]' | sed 's/ //g')

            # Validate
            if ! echo "$clean_input" | grep -Eq '^([A-D](,[A-D]){0,3})$'; then
                echo -e "    ${RED}❌ Invalid input! Use only A, B, C, D (comma separated).${RESET}"
                read -p "    Press enter to continue..."
                continue
            fi

            # Convert to JSON array
            formatted=$(echo "$clean_input" | awk -F, '{
                printf "[";
                for(i=1; i<=NF; i++) {
                    printf "\"%s\"", $i;
                    if (i < NF) printf ",";
                }
                print "]";
            }')

            # Update using jq
            tmpfile=$(mktemp)
            jq ".\"$qnum\" = $formatted" "$FILE" > "$tmpfile" && mv "$tmpfile" "$FILE"

            echo -e "    ${GREEN}✅ Question $qnum updated to $formatted${RESET}"
            read -p "    Press enter to continue..."
            ;;
        3)
            echo -e "    ${YELLOW}Showing all question numbers and answers:${RESET}"
            jq -r 'to_entries[] | "    Q\(.key): \(.value)"' "$FILE" | less
            ;;
        4)
            cp "${FILE}.bak" "$FILE"
            echo -e "    ${YELLOW}🔁 Restored from backup file.${RESET}"
            read -p "    Press enter to continue..."
            ;;
        q|Q)
            echo -e "    ${BLUE}👋 Exiting...${RESET}"
            exit 0
            ;;
        *)
            echo -e "    ${RED}⚠️ Invalid choice! Try again.${RESET}"
            sleep 1
            ;;
    esac
done

#!/bin/bash

# 🌟 Colors
BOLD="\033[1m"
BLUE="\033[1;34m"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
CYAN="\033[1;36m"
RESET="\033[0m"

# 🕒 Start idle timer
reset_timer() {
    idle_seconds=0
}
exit_on_idle() {
    while true; do
        sleep 10
        idle_seconds=$((idle_seconds + 10))
        if (( idle_seconds >= 120 )); then
            echo -e "\n${YELLOW}⏳ Inactive for 2 minutes. Exiting...${RESET}"
            exit 0
        fi
    done
}

idle_seconds=0
exit_on_idle &  # Run idle check in background
IDLE_PID=$!

while true; do
    clear
    reset_timer
    echo -e "${BLUE}${BOLD}📋 OMR Universal Tool Menu${RESET}"
    echo -e "${CYAN}Choose an option:${RESET}"
    echo -e "  ${GREEN}1.${RESET} 🔄 Update bot scripts (omrupdate)"
    echo -e "  ${GREEN}2.${RESET} ⚙️  Open settings (omrsettings)"
    echo -e "  ${GREEN}3.${RESET} 🧹 Clear input/output folders"
    echo -e "  ${GREEN}4.${RESET} 📄 Write answer keys (open in Chrome)"
    echo -e "  ${GREEN}5.${RESET} 📝 Run OMR Scanner (omr)"
    echo -e "  ${GREEN}6.${RESET} 📷 Instant auto scanning (autoscan)"
    echo -e "  ${GREEN}7.${RESET} ✏️  Edit OMR answer key (omredit)"
    echo -e "  ${GREEN}8.${RESET} 📖 Help (omr --help)"
    echo -e "  ${GREEN}9.${RESET} 📤 Upload files to Telegram (upload.py)"
    echo -e "  ${YELLOW}q.${RESET} ❌ Quit"
    echo

    read -t 120 -p "Enter your choice: " choice || {
        echo -e "\n${YELLOW}⏳ No input for 2 minutes. Exiting...${RESET}"
        kill $IDLE_PID
        exit 0
    }

    reset_timer

    case "$choice" in
        1) bash bot_update.sh ;;
        2) bash settings.sh ;;
        3)
            echo -e "${YELLOW}⚠️  Are you sure you want to delete all files in input/ and output/? (y/n)${RESET}"
            read -p "> " confirm
            if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
                rm -rf input/* output/*
                echo -e "${GREEN}✅ All files deleted from input/ and output/.${RESET}"
            else
                echo -e "${CYAN}❎ Deletion cancelled.${RESET}"
            fi
            ;;
        4)
            url="https://ashit.xyz/50?filename=answer_key.txt&data=save"
            echo -e "${CYAN}🌐 Opening: $url${RESET}"
            termux-open-url "$url"
            echo -e "${YELLOW}👋 Exiting after opening browser...${RESET}"
            kill $IDLE_PID
            exit 0
            ;;
        5) python3 app.py ;;
        6) python3 web.py ;;
        7) bash answer_key_edit.sh ;;
        8) omr --help ;;
        9) python3 upload.py ;;
            
        [Qq])
            echo -e "${YELLOW}👋 Exiting...${RESET}"
            kill $IDLE_PID
            exit 0
            ;;
        *)
            echo -e "${YELLOW}⚠️  Invalid option. Try again.${RESET}"
            sleep 1
            ;;
    esac

    echo -e "\n${CYAN}🔁 Press Enter to return to menu...${RESET}"
    read
done

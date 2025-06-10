#!/bin/bash

# 🌟 Colors
BOLD="\033[1m"
BLUE="\033[1;34m"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
CYAN="\033[1;36m"
RESET="\033[0m"

while true; do
    clear
    echo -e "${BLUE}${BOLD}📋 OMR Universal Tool Menu${RESET}"
    echo -e "${CYAN}Choose an option:${RESET}"
    echo -e "  ${GREEN}1.${RESET} 📝 Run OMR Scanner (omr)"
    echo -e "  ${GREEN}2.${RESET} 📤 Send zipped files (omrsend)"
    echo -e "  ${GREEN}3.${RESET} 🔄 Update bot scripts (omrupdate)"
    echo -e "  ${GREEN}4.${RESET} ⚙️  Open settings (omrsettings)"
    echo -e "  ${GREEN}5.${RESET} 📷 Start auto scanning (autoscan)"
    echo -e "  ${GREEN}6.${RESET} ✏️  Edit OMR answer key (omredit)"
    echo -e "  ${GREEN}7.${RESET} 📖 Help (omr --help)"
    echo -e "  ${YELLOW}q.${RESET} ❌ Quit"
    echo

    read -p "Enter your choice: " choice

    case "$choice" in
        1) omr ;;
        2) omrsend ;;
        3) omrupdate ;;
        4) omrsettings ;;
        5) autoscan ;;
        6) omredit ;;
        7) omr --help ;;
        [Qq]) echo -e "${YELLOW}👋 Exiting...${RESET}"; break ;;
        *) echo -e "${YELLOW}⚠️  Invalid option. Try again.${RESET}"; sleep 1 ;;
    esac

    echo -e "\n${CYAN}🔁 Press Enter to return to menu...${RESET}"
    read
done

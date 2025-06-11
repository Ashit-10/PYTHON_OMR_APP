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
    echo -e "  ${GREEN}1.${RESET} 🔄 Update bot scripts (omrupdate)"
    echo -e "  ${GREEN}2.${RESET} ⚙️  Open settings (omrsettings)"
    echo -e "  ${GREEN}3.${RESET} 🧹 Clear input/output folders"
    echo -e "  ${GREEN}4.${RESET} 📄 Write answer keys (open in Chrome)"
    echo -e "  ${GREEN}5.${RESET} 📝 Run OMR Scanner (omr)"
    echo -e "  ${GREEN}6.${RESET} 📷 Instant auto scanning (autoscan)"
    echo -e "  ${GREEN}7.${RESET} ✏️  Edit OMR answer key (omredit)"
    echo -e "  ${GREEN}8.${RESET} 📖 Help (omr --help)"
    echo -e "  ${YELLOW}q.${RESET} ❌ Quit"
    echo

    read -p "Enter your choice: " choice

    case "$choice" in
        1) omrupdate ;;
        2) omrsettings ;;
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
            ;;
        5) omr ;;
        6) autoscan ;;
        7) omredit ;;
        8) omr --help ;;
        [Qq]) echo -e "${YELLOW}👋 Exiting...${RESET}"; break ;;
        *) echo -e "${YELLOW}⚠️  Invalid option. Try again.${RESET}"; sleep 1 ;;
    esac

    echo -e "\n${CYAN}🔁 Press Enter to return to menu...${RESET}"
    read
done

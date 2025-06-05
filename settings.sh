#!/bin/sh

CONFIG_FILE="config.cfg"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Initialize config file with defaults if missing
if [ ! -f "$CONFIG_FILE" ]; then
  echo "signature=ashit_sign.png" > "$CONFIG_FILE"
  echo "pixel_value=150" >> "$CONFIG_FILE"
  echo "class=10th" >> "$CONFIG_FILE"
fi

pause() {
  echo
  read -p "Press Enter to continue..." dummy
}

while true; do
  clear
  echo "${CYAN}==================${NC}"
  echo "${CYAN}    OMR SCANNER   ${NC}"
  echo "${CYAN}==================${NC}"
  echo "${YELLOW}1.${NC} Signature"
  echo "${YELLOW}2.${NC} Pixel value"
  echo "${YELLOW}3.${NC} Class"
  echo "${YELLOW}q.${NC} Exit"
  echo
  echo -n "Enter number to change setting, or q to quit: "
  read choice

  case $choice in
    1)
      clear
      echo "${CYAN}Select Signature:${NC}"
      echo "${YELLOW}1.${NC} Ashit"
      echo "${YELLOW}2.${NC} Rupa"
      echo "${YELLOW}3.${NC} Madhu sir"
      echo "${YELLOW}4.${NC} Lakhia bhai"
      echo -n "Enter choice (1-4): "
      read sig_choice
      case $sig_choice in
        1) sig_file="ashit_sign.png" ;;
        2) sig_file="rupa_sign.png" ;;
        3) sig_file="madhu_sir_sign.png" ;;
        4) sig_file="lakhia_bhai_sign.png" ;;
        *)
          echo "${RED}Invalid choice!${NC}"
          pause
          continue
          ;;
      esac
      sed -i "/^signature=/c\signature=$sig_file" "$CONFIG_FILE"
      echo "${GREEN}Signature updated to $sig_file${NC}"
      pause
      ;;

    2)
      clear
      echo -n "${CYAN}Enter new Pixel value (130-300): ${NC}"
      read new_pixel
      if echo "$new_pixel" | grep -Eq '^[0-9]+$' && [ "$new_pixel" -ge 130 ] && [ "$new_pixel" -le 300 ]; then
        sed -i "/^pixel_value=/c\pixel_value=$new_pixel" "$CONFIG_FILE"
        echo "${GREEN}Pixel value updated to $new_pixel${NC}"
      else
        echo "${RED}Invalid input! Please enter a number between 130 and 300.${NC}"
      fi
      pause
      ;;

    3)
      clear
      echo "${CYAN}Select Class:${NC}"
      echo "${YELLOW}1.${NC} 10th"
      echo "${YELLOW}2.${NC} 9th"
      echo "${YELLOW}3.${NC} 8th"
      echo "${YELLOW}4.${NC} Other"
      echo -n "Enter choice (1-4): "
      read class_choice
      case $class_choice in
        1) class_val="10th" ;;
        2) class_val="9th" ;;
        3) class_val="8th" ;;
        4) 
          echo -n "Enter your class name: "
          read custom_class
          class_val="$custom_class"
          ;;
        *)
          echo "${RED}Invalid choice!${NC}"
          pause
          continue
          ;;
      esac
      sed -i "/^class=/c\class=$class_val" "$CONFIG_FILE"
      echo "${GREEN}Class updated to $class_val${NC}"
      pause
      ;;

    q|Q)
      echo "${YELLOW}Exiting settings. Goodbye!${NC}"
      exit 0
      ;;

    *)
      echo "${RED}Invalid choice! Please select from the menu.${NC}"
      pause
      ;;
  esac
done

#!/bin/sh

CONFIG_FILE="config.cfg"

# Initialize config file with defaults if missing
if [ ! -f "$CONFIG_FILE" ]; then
  echo "signature=ashit_sign.png" > "$CONFIG_FILE"
  echo "pixel_value=150" >> "$CONFIG_FILE"
  echo "class=Class 12" >> "$CONFIG_FILE"
fi

clear
echo "=================="
echo "    OMR SCANNER   "
echo "=================="
echo "1. Signature"
echo "2. Pixel value"
echo "3. Class"
echo
echo "Enter number to change setting, or q to quit:"
read choice

case $choice in
  1)
    echo "Select Signature:"
    echo "1. Ashit"
    echo "2. Rupa"
    echo "3. Madhu sir"
    echo "4. Lakhia bhai"
    read sig_choice
    case $sig_choice in
      1) sig_file="ashit_sign.png" ;;
      2) sig_file="rupa_sign.png" ;;
      3) sig_file="madhu_sir_sign.png" ;;
      4) sig_file="lakhia_bhai_sign.png" ;;
      *) echo "Invalid choice"; exit 1 ;;
    esac
    sed -i "/^signature=/c\signature=$sig_file" "$CONFIG_FILE"
    echo "Signature updated to $sig_file"
    ;;

  2)
    echo "Enter new Pixel value (number):"
    read new_pixel
    sed -i "/^pixel_value=/c\pixel_value=$new_pixel" "$CONFIG_FILE"
    echo "Pixel value updated!"
    ;;
    
  3)
    echo "Enter new Class:"
    read new_class
    sed -i "/^class=/c\class=$new_class" "$CONFIG_FILE"
    echo "Class updated!"
    ;;
    
  q|Q)
    echo "Exiting settings."
    exit 0
    ;;
    
  *)
    echo "Invalid choice."
    ;;
esac

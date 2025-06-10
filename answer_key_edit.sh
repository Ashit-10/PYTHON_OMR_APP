#!/data/data/com.termux/files/usr/bin/bash

FILE="answer_key.txt"

# Check if file exists
if [ ! -f "$FILE" ]; then
  echo "❌ File $FILE not found!"
  exit 1
fi

# Backup first
cp "$FILE" "${FILE}.bak"

# Menu loop
while true; do
  clear
  echo "📄 OMR Answer Key Editor"
  echo "-------------------------"
  echo "1. View Answer for a Question"
  echo "2. Edit Answer for a Question"
  echo "3. View All (Paginated)"
  echo "4. Restore Backup"
  echo "5. Exit"
  echo "-------------------------"
  read -p "Choose an option (1-5): " choice

  case "$choice" in
    1)
      read -p "Enter question number: " qnum
      grep -E "\"$qnum\"\s*:" "$FILE"
      read -p "Press enter to continue..."
      ;;
    2)
      read -p "Enter question number to edit: " qnum
      read -p "Enter new option(s) (e.g. A,B,C): " input
      clean_input=$(echo "$input" | tr '[:lower:]' '[:upper:]' | sed 's/ //g')
      
      # Validate input
      if ! echo "$clean_input" | grep -Eq '^([A-D](,[A-D]){0,3})$'; then
        echo "❌ Invalid input! Only A, B, C, D allowed (comma separated)."
        read -p "Press enter to continue..."
        continue
      fi

      # Format into JSON array
      formatted=$(echo "$clean_input" | sed 's/,/","/g' | sed 's/^/["/' | sed 's/$/"]/')

      # Update using sed
      sed -i "s/\"$qnum\": \[.*\]/\"$qnum\": $formatted/" "$FILE"
      echo "✅ Updated Q$qnum to $formatted"
      read -p "Press enter to continue..."
      ;;
    3)
      less "$FILE"
      ;;
    4)
      cp "${FILE}.bak" "$FILE"
      echo "🔁 Restored from backup."
      read -p "Press enter to continue..."
      ;;
    5)
      echo "👋 Exiting..."
      break
      ;;
    *)
      echo "⚠️ Invalid option!"
      sleep 1
      ;;
  esac
done

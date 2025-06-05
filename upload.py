import os
import zipfile
import requests
import time
import sys

# ========== USER SETTINGS ==========

BOT_TOKEN = "2113644798:AAEuMDxeifbAtrzka5UsM4K4CHm4qqOBjUI"
CHAT_ID = "1602293216" 

OUTPUT_DIR = 'output'
ZIP_NAME = 'omr.zip'
# ===================================

def print_banner():
    os.system('clear')
    print("\033[1;32m==============================")
    print("  📤 Telegram File Uploader")
    print("==============================\033[0m")

def create_zip():
    if not os.path.isdir(OUTPUT_DIR):
        print(f"\033[1;31m❌ Folder '{OUTPUT_DIR}' not found!\033[0m")
        return False

    with zipfile.ZipFile(ZIP_NAME, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(OUTPUT_DIR):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, OUTPUT_DIR)
                zipf.write(file_path, arcname)
    print(f"\n✅ Zipped all files in '{OUTPUT_DIR}/' to '{ZIP_NAME}'")
    return True

def show_progress_bar():
    print("\n⏳ Uploading...")
    for i in range(0, 101, 10):
        time.sleep(0.1)
        sys.stdout.write(f"\rProgress: [{('=' * (i//10)).ljust(10)}] {i}%")
        sys.stdout.flush()

def send_zip():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    try:
        with open(ZIP_NAME, 'rb') as file:
            response = requests.post(url, data={'chat_id': CHAT_ID}, files={'document': file})

        if response.status_code == 200:
            print(f"\n\n\033[1;32m✅ File sent successfully!\033[0m")
            os.system(f"rm {ZIP_NAME}")
        else:
            print(f"\n\n\033[1;31m❌ Failed to send file. Status code: {response.status_code}\033[0m")
            print(response.text)

    except Exception as e:
        print(f"\n\n\033[1;31m❌ Error: {e}\033[0m")

def main():
    print_banner()
    if create_zip():
        show_progress_bar()
        send_zip()

if __name__ == '__main__':
    main()

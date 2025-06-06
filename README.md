<h1>An OMR evaluatng app with python</h1>

(OMR sheet formats are given in the repo)

<h2>features:</h2>

- Very easy to use
- very much compact size
- dependancies: python, opencv-python, numpy
- takes less than 1 second
- omr upto 100 questions supported
- roll number upto 2 digits supported
- colors for correct, wrong, unattempted numbers

<h2>How to use ?</h2>

```
git clone https://github.com/Ashit-10/PYTHON_OMR_APP
cd PYTHON_OMR_BOT
pip3 -r requirements.txt
python3 app.py
```


<h2>Extras:</h2>

- add sign to the output image by adding "sign.png" in the current directory

<h2>Setting up in termux</h2>

```
pkg update -y
pkg upgrade
pkg install x11-repo
pkg install matplotlib
pkg rei opencv-python
pkg install python -y
pkg install git -y
pkg install build-essential
pkg install zip -y
termux-setup-storage

git clone https://github.com/Ashit-10/PYTHON_OMR_APP

cd PYTHON_OMR_BOT
pip3 -r requirements.txt
source setup.sh
```
git clone repo , cd to PYTHON_OMR_BOT, and run python app.py
<h2>Preview:</h2>

https://github.com/user-attachments/assets/b6c944cc-7de9-45f9-826e-31e621016642

#!/bin/bash
# Double-click this file in Finder to start the tournament app.
# It opens your browser on a page where you pick or create a tournament.
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed. Install it from https://www.python.org/downloads/ and try again."
  read -r -p "Press Return to close."
  exit 1
fi
python3 -m paoweb
echo
read -r -p "The app has stopped. Press Return to close this window."

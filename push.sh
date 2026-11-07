#!/bin/zsh
set -euo pipefail
cd -- "${0:A:h}"
if [[ $# -ne 1 ]]; then
  print "usage: ./push.sh git@github.com:<you>/handmouse.git"
  exit 1
fi
git remote remove origin 2>/dev/null || true
git remote add origin "$1"
git push -u origin main

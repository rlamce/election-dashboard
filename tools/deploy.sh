#!/usr/bin/env bash
# Sync the project into the GitHub repo clone and push (GitHub Pages serves from main / root).
set -euo pipefail
SRC="/home/claude/election-dashboard"
REPO="/home/claude/repo/election-dashboard"
MSG="${1:-deploy: $(date -u +%FT%TZ)}"

# mirror SRC -> REPO (no rsync in this environment): copy with tar, then delete files that vanished from SRC
(cd "$SRC" && tar --exclude='./.git' --exclude='./baseline_work' --exclude='./node_modules' --exclude='__pycache__' --exclude='*.pyc' -cf - .) | (cd "$REPO" && tar -xf -)
(cd "$REPO" && git ls-files) | while read -r f; do
  [ -e "$SRC/$f" ] || rm -f "$REPO/$f"
done

cd "$REPO"
git add -A
if git diff --cached --quiet; then
  echo "nothing to deploy"; exit 0
fi
git -c user.name="Claude" -c user.email="noreply@anthropic.com" commit -q -m "$MSG" \
  -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_018wdP12WM1BdthYHohXX1M2"
git fetch -q origin main
git rebase -q origin/main || { git rebase --abort; echo "rebase failed"; exit 1; }
git push -q origin HEAD:main
echo "pushed $(git rev-parse --short HEAD)"

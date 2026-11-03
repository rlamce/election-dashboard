#!/usr/bin/env bash
# usage: sitelinks.sh <key> <site_url> -> key TAB http TAB youtube links (space-separated, unique)
key="$1"; url="$2"
safe=$(printf '%s' "$key" | tr -c 'A-Za-z0-9_-' '_')
f="/tmp/yt/site_$safe.html"
code=$(curl -sSL -m 40 -o "$f" -w "%{http_code}" "$url" 2>/dev/null || echo 000)
links=$(grep -oiE 'https?://(www\.)?youtube\.com/(channel/UC[A-Za-z0-9_-]{22}|@[A-Za-z0-9._-]+|user/[A-Za-z0-9_-]+|c/[A-Za-z0-9_-]+)' "$f" 2>/dev/null | sed -E 's#^https?://(www\.)?##' | sort -u | tr '\n' ' ')
printf '%s\t%s\t%s\n' "$key" "$code" "$links"

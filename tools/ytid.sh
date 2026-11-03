#!/usr/bin/env bash
# usage: ytid.sh <key> <url>
# prints TSV: key, id, title, live_now_count, upcoming_count, n_streamed, last_streamed_text, http_code, final_url
key="$1"; url="$2"
safe=$(printf '%s' "$key" | tr -c 'A-Za-z0-9_-' '_')
f="/tmp/yt/$safe.html"
out=$(curl -sSL -m 45 -o "$f" -w "%{http_code} %{url_effective}" "$url" 2>/dev/null || echo "000 -")
code=${out%% *}; eff=${out#* }
id=$(grep -o '"externalId":"UC[^"]*"' "$f" 2>/dev/null | head -1 | sed 's/.*"externalId":"//; s/"//')
[ -z "$id" ] && id=$(grep -o '"channelId":"UC[^"]*"' "$f" 2>/dev/null | head -1 | sed 's/.*"channelId":"//; s/"//')
title=$(grep -o '<title>[^<]*' "$f" 2>/dev/null | head -1 | sed 's/<title>//; s/ - YouTube$//')
live=$(grep -o 'THUMBNAIL_OVERLAY_BADGE_STYLE_LIVE"' "$f" 2>/dev/null | wc -l)
upc=$(grep -o 'upcomingEventData\|BADGE_STYLE_UPCOMING' "$f" 2>/dev/null | wc -l)
nst=$(grep -o 'Streamed [0-9]* [a-z]* ago' "$f" 2>/dev/null | wc -l)
last=$(grep -o 'Streamed [0-9]* [a-z]* ago' "$f" 2>/dev/null | head -1)
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$key" "$id" "$title" "$live" "$upc" "$nst" "$last" "$code" "$eff"

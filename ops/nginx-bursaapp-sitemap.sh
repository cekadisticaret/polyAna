#!/bin/bash
# sitemap.xml /sitemap-* → BursaApp :5051 (location /site prefix çakışması)
set -euo pipefail
CONF="/etc/nginx/sites-enabled/bursaapp"
MARK="# bursaapp-sitemap-5051"
if grep -q "$MARK" "$CONF" 2>/dev/null; then
  echo "already patched"
  exit 0
fi
TMP=$(mktemp)
awk -v mark="$MARK" '
  /location \/site/ && !done {
    print "    " mark
    print "    location ~ ^/sitemap(-.*)?\\.xml$ {"
    print "        proxy_pass http://127.0.0.1:5051;"
    print "        proxy_http_version 1.1;"
    print "        proxy_set_header Host $host;"
    print "        proxy_set_header X-Real-IP $remote_addr;"
    print "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;"
    print "        proxy_set_header X-Forwarded-Proto $scheme;"
    print "    }"
    print ""
    done=1
  }
  { print }
' "$CONF" > "$TMP"
cp "$CONF" "${CONF}.bak.$(date +%Y%m%d%H%M%S)"
mv "$TMP" "$CONF"
nginx -t
systemctl reload nginx
echo "nginx sitemap patch OK"

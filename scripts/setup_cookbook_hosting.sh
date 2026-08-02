#!/bin/bash
# One-time setup: expose cookbook/ publicly at https://hwbros-cookbook.duckdns.org
# via a new nginx server block + Let's Encrypt cert (certbot --nginx plugin).
# Does not touch the bookfolio or nssapp nginx configs.
#
# Run with: sudo bash scripts/setup_cookbook_hosting.sh

set -euo pipefail

DOMAIN="hwbros-cookbook.duckdns.org"
DOCROOT="/home/hwbros/work/recipe/cookbook"
SITE_FILE="/etc/nginx/sites-available/hwbros-cookbook"

if [ "$(id -u)" -ne 0 ]; then
  echo "This script must be run with sudo/root." >&2
  exit 1
fi

echo "==> Writing $SITE_FILE"
cat > "$SITE_FILE" <<EOF
server {
    listen 80;
    server_name ${DOMAIN};

    root ${DOCROOT};
    index index.html;

    location / {
        try_files \$uri \$uri/ =404;
    }
}
EOF

echo "==> Enabling site"
ln -sf "$SITE_FILE" /etc/nginx/sites-enabled/hwbros-cookbook

echo "==> Testing nginx config"
nginx -t

echo "==> Reloading nginx (HTTP-only, so certbot's HTTP-01 challenge can reach it)"
systemctl reload nginx

echo "==> Requesting Let's Encrypt certificate via certbot --nginx"
certbot --nginx -d "${DOMAIN}" --non-interactive --agree-tos -m hwbros7@gmail.com --redirect

echo "==> Final nginx config test + reload"
nginx -t
systemctl reload nginx

echo "==> Done. Verify: curl -I https://${DOMAIN}/"

#!/bin/sh
# Copy renewed certificates into the Portfolio stack and reload the containers that use them.
set -eu

DEST=/srv/portfolio/certs
COMPOSE="docker compose -f /srv/portfolio/docker-compose.yml"

domain=$(basename "$RENEWED_LINEAGE")
case "$domain" in
  example.com|example.org) ;;
  *) exit 0 ;;
esac

# fullchain = certificate + intermediate, which also fixes the missing chain in nginx.
install -m 644 "$RENEWED_LINEAGE/fullchain.pem" "$DEST/$domain-crt.pem"
install -m 644 "$RENEWED_LINEAGE/chain.pem"     "$DEST/$domain-chain.pem"
install -m 600 "$RENEWED_LINEAGE/privkey.pem"   "$DEST/$domain-key.pem"

# The API and site read their certificate only at startup.
if [ "$domain" = example.com ]; then
  $COMPOSE restart api web
fi
$COMPOSE exec -T nginx nginx -s reload

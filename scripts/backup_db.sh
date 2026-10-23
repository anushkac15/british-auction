#!/bin/sh
# Dumps the production database to backups/ and keeps the last 14 days.
# Daily at 03:00 via crontab -e:
#   0 3 * * * cd /home/ubuntu/british-auction && sh scripts/backup_db.sh >> backups/backup.log 2>&1
set -e
cd "$(dirname "$0")/.."
mkdir -p backups

file="backups/auction-$(date +%Y%m%d-%H%M%S).sql.gz"
docker compose -f docker-compose.prod.yml exec -T postgres pg_dump -U auction auction | gzip > "$file"
if [ "$(gzip -dc "$file" | head -c 100 | wc -c)" -eq 0 ]; then
    rm -f "$file"
    echo "backup failed: empty dump" >&2
    exit 1
fi

find backups -name 'auction-*.sql.gz' -mtime +14 -delete
echo "saved $file"

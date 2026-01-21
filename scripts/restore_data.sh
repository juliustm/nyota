#!/bin/bash
set -e

# Identify Volumes
OLD_DB_VOL="earthlovers-website-cms_db_data"
# The new volume name is likely derived from folder name 'nyota' + in docker-compose 'nyota_persistence'
# So 'nyota_nyota_persistence'.
NEW_VOL="nyota_nyota_persistence"

echo "--- Stopping any running containers ---"
docker compose down

echo "--- Restoring Database from $OLD_DB_VOL ---"
if docker volume inspect $OLD_DB_VOL > /dev/null 2>&1; then
    docker run --rm \
        -v $OLD_DB_VOL:/old \
        -v $NEW_VOL:/new \
        alpine sh -c "mkdir -p /new/db && cp /old/earthlovers.db /new/db/nyota.db && chmod 666 /new/db/nyota.db && echo 'Database restored to /nyota/db/nyota.db'"
else
    echo "ERROR: Old volume $OLD_DB_VOL not found!"
    exit 1
fi

echo "--- Restoring Uploads from Host ---"
# We assume this script is run from project root
docker run --rm \
    -v "$(pwd)":/host \
    -v $NEW_VOL:/new \
    alpine sh -c "mkdir -p /new/userdata/covers /new/userdata/logos /new/userdata/secure_uploads && \
                  if [ -d /host/static/uploads/covers ]; then cp -r /host/static/uploads/covers/* /new/userdata/covers/ 2>/dev/null || true; echo 'Covers copied'; fi && \
                  if [ -d /host/static/uploads/logos ]; then cp -r /host/static/uploads/logos/* /new/userdata/logos/ 2>/dev/null || true; echo 'Logos copied'; fi"

echo "--- Data Restoration Complete ---"
echo "You can now run 'make start'."

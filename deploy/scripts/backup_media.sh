#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# deploy/scripts/backup_media.sh
# ──────────────────────────────────────────────────────────────────────────────
# WHY THIS FILE EXISTS:
#   Automated rsync/tar backup script for user-uploaded media files stored on the
#   local filesystem (when not using Cloudinary cloud storage).
#
# USAGE:
#   chmod +x deploy/scripts/backup_media.sh
#   ./deploy/scripts/backup_media.sh
#
# CRON SETUP:
#   30 1 * * * /var/www/house-of-bore/deploy/scripts/backup_media.sh >> /var/log/hob_media_backup.log 2>&1
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# Configuration
MEDIA_SRC="/var/www/house-of-bore/media"
BACKUP_DIR="/var/backups/house_of_bore/media"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_ARCHIVE="${BACKUP_DIR}/hob_media_${TIMESTAMP}.tar.gz"
RETENTION_DAYS=30

mkdir -p "${BACKUP_DIR}"

echo "[$(date +'%Y-%m-%d %H:%M:%S')] Starting Media files backup..."

if [ ! -d "${MEDIA_SRC}" ] || [ -z "$(ls -A "${MEDIA_SRC}" 2>/dev/null)" ]; then
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] Media directory is empty or missing (${MEDIA_SRC}). Skipping archive."
    exit 0
fi

# Create tar.gz archive of user uploads
tar -czf "${BACKUP_ARCHIVE}" -C "$(dirname "${MEDIA_SRC}")" "$(basename "${MEDIA_SRC}")"

if [ ! -s "${BACKUP_ARCHIVE}" ]; then
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: Media backup archive is empty! Aborting."
    rm -f "${BACKUP_ARCHIVE}"
    exit 1
fi

echo "[$(date +'%Y-%m-%d %H:%M:%S')] Media archive created: ${BACKUP_ARCHIVE} ($(du -h "${BACKUP_ARCHIVE}" | cut -f1))"

# Verify archive integrity
if tar -tzf "${BACKUP_ARCHIVE}" >/dev/null; then
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] Media backup verification passed."
else
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: Media archive verification failed!"
    exit 2
fi

# Retention Cleanup
echo "[$(date +'%Y-%m-%d %H:%M:%S')] Cleaning up media archives older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -type f -name "hob_media_*.tar.gz" -mtime +${RETENTION_DAYS} -delete

echo "[$(date +'%Y-%m-%d %H:%M:%S')] Media backup workflow completed successfully."

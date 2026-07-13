#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# deploy/scripts/backup_db.sh
# ──────────────────────────────────────────────────────────────────────────────
# WHY THIS FILE EXISTS:
#   Automated production backup and verification script for PostgreSQL database.
#   Designed to run via system cron (e.g., daily at 1:00 AM).
#
# USAGE:
#   chmod +x deploy/scripts/backup_db.sh
#   ./deploy/scripts/backup_db.sh
#
# CRON SETUP:
#   0 1 * * * /var/www/house-of-bore/deploy/scripts/backup_db.sh >> /var/log/hob_backup.log 2>&1
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# Configuration
BACKUP_DIR="/var/backups/house_of_bore/db"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/hob_db_${TIMESTAMP}.sql.gz"
RETENTION_DAYS=14

# Ensure backup directory exists
mkdir -p "${BACKUP_DIR}"

echo "[$(date +'%Y-%m-%d %H:%M:%S')] Starting PostgreSQL database backup..."

# Read DB configuration from environment or .env if present
if [ -f "/var/www/house-of-bore/.env" ]; then
    export $(grep -v '^#' /var/www/house-of-bore/.env | xargs)
fi

DB_NAME="${DB_NAME:-house_of_bore_db}"
DB_USER="${DB_USER:-postgres}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"

# 1. Execute pg_dump with gzip compression
PGPASSWORD="${DB_PASSWORD:-}" pg_dump \
    -h "${DB_HOST}" \
    -p "${DB_PORT}" \
    -U "${DB_USER}" \
    -F p \
    --no-owner \
    --no-acl \
    "${DB_NAME}" | gzip > "${BACKUP_FILE}"

# Check that the backup file is not empty
if [ ! -s "${BACKUP_FILE}" ]; then
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: Backup file is empty! Aborting."
    rm -f "${BACKUP_FILE}"
    exit 1
fi

echo "[$(date +'%Y-%m-%d %H:%M:%S')] Backup created successfully: ${BACKUP_FILE} ($(du -h "${BACKUP_FILE}" | cut -f1))"

# 2. Verification Step — Test restore archive header validity
echo "[$(date +'%Y-%m-%d %H:%M:%S')] Verifying backup integrity..."
if gzip -t "${BACKUP_FILE}"; then
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] Backup verification passed (valid gzip stream)."
else
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: Backup verification FAILED (corrupt gzip archive)!"
    exit 2
fi

# 3. Retention Cleanup — Delete backups older than RETENTION_DAYS
echo "[$(date +'%Y-%m-%d %H:%M:%S')] Cleaning up archives older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -type f -name "hob_db_*.sql.gz" -mtime +${RETENTION_DAYS} -delete

echo "[$(date +'%Y-%m-%d %H:%M:%S')] Database backup workflow completed successfully."

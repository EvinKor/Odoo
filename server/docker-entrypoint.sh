#!/bin/bash
set -e

# Environment variables
ODOO_CONF=/etc/odoo/odoo.conf
ODOO_DB=odoodb
DB_USER=${DB_USER:-odoo}
DB_HOST=${HOST:-odoo-db}

# Function to check if DB exists
db_exists() {
  PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname='${ODOO_DB}'" | grep -q 1
}

# Initialize DB with demo data if it doesn't exist
if ! db_exists; then
    echo "Initializing Odoo database '$ODOO_DB' with demo data..."
    odoo -c "$ODOO_CONF" -d "$ODOO_DB" -i base,website_event --stop-after-init
fi

# Start Odoo normally
echo "Starting Odoo..."
exec odoo -c "$ODOO_CONF"


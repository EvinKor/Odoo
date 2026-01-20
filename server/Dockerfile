# Dockerfile
FROM odoo:17

# Set working directory
WORKDIR /mnt/extra-addons

# Copy your custom addons (if any)
COPY ./addons ./addons

# Copy your odoo.conf (optional)
COPY ./odoo.conf /etc/odoo/odoo.conf

# Expose Odoo port
EXPOSE 8069


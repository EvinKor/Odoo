FROM odoo:17

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    xmlsec1 \
    libxml2 \
    libxmlsec1-openssl \
    python3-lxml \
    python3-xmlsec \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt

# Install only the things you really need from pip, WITHOUT deps
# (so pip won’t try to replace apt lxml with a wheel)
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

USER odoo

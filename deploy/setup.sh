#!/usr/bin/env bash
# Развёртывание прототипа «Пульс стажёров» на чистом Ubuntu 24.04 (Webdock или любой VPS).
# Запуск от root:  DOMAIN=example.com bash setup.sh      (DOMAIN необязателен; без него только HTTP по IP)
# Повторный запуск безопасен: обновит код и перезапустит службы.
set -euo pipefail

REPO="${REPO:-https://github.com/Qurena/mgts-code-of-the-city.git}"
APP_DIR=/opt/mgts
APP_USER=mgts
DOMAIN="${DOMAIN:-}"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3-venv python3-pip git nginx ufw
[ -n "$DOMAIN" ] && apt-get install -y certbot python3-certbot-nginx

id "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"

# код
if [ -d "$APP_DIR/repo/.git" ]; then
  sudo -u "$APP_USER" git -C "$APP_DIR/repo" pull --ff-only
else
  sudo -u "$APP_USER" git clone "$REPO" "$APP_DIR/repo"
fi
sudo -u "$APP_USER" python3 -m venv "$APP_DIR/venv"
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/repo/prototype/requirements.txt"

# общие настройки; токен приёмника создаётся один раз
mkdir -p /etc/mgts /var/lib/mgts
chown "$APP_USER":"$APP_USER" /var/lib/mgts
if [ ! -f /etc/mgts/env ]; then
  cat > /etc/mgts/env <<EOF
PULSE_DB=/var/lib/mgts/pulse.db
WEBHOOK_TOKEN=$(head -c 24 /dev/urandom | base64 | tr -d '/+=')
RECEIVER_URL=http://127.0.0.1:8765
ANALYZER=keywords
EOF
  chmod 640 /etc/mgts/env
  chgrp "$APP_USER" /etc/mgts/env
fi

cat > /etc/systemd/system/mgts-receiver.service <<EOF
[Unit]
Description=MGTS pulse receiver
After=network.target
[Service]
User=$APP_USER
WorkingDirectory=$APP_DIR/repo/prototype
EnvironmentFile=/etc/mgts/env
ExecStart=$APP_DIR/venv/bin/python receiver.py
Restart=always
[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/mgts-app.service <<EOF
[Unit]
Description=MGTS pulse Streamlit app
After=network.target
[Service]
User=$APP_USER
WorkingDirectory=$APP_DIR/repo/prototype
EnvironmentFile=/etc/mgts/env
ExecStart=$APP_DIR/venv/bin/streamlit run app.py --server.headless true --server.address 127.0.0.1 --server.port 8501 --server.enableXsrfProtection true
Restart=always
[Install]
WantedBy=multi-user.target
EOF

# nginx: интерфейс на /, приём ответов на /response (IPv4 и IPv6)
cat > /etc/nginx/sites-available/mgts <<EOF
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name ${DOMAIN:-_};

    location /response {
        proxy_pass http://127.0.0.1:8765;
        proxy_set_header Host \$host;
        proxy_set_header x-delivery-id \$http_x_delivery_id;
        proxy_set_header x-token \$http_x_token;
        client_max_body_size 64k;
    }
    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_read_timeout 86400;
    }
}
EOF
ln -sf /etc/nginx/sites-available/mgts /etc/nginx/sites-enabled/mgts
rm -f /etc/nginx/sites-enabled/default
nginx -t

# данные демо: создаются один раз, под пользователем службы
if [ ! -f /var/lib/mgts/pulse.db ]; then
  sudo -u "$APP_USER" env PULSE_DB=/var/lib/mgts/pulse.db "$APP_DIR/venv/bin/python" "$APP_DIR/repo/prototype/seed.py"
fi

systemctl daemon-reload
systemctl enable --now mgts-receiver mgts-app
systemctl restart mgts-receiver mgts-app
systemctl reload nginx || systemctl restart nginx

# брандмауэр: только SSH, HTTP, HTTPS
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

# HTTPS, если задан домен, который уже указывает на этот сервер
if [ -n "$DOMAIN" ]; then
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email --redirect || echo "HTTPS не выдан: проверьте, что DNS домена указывает на этот сервер"
fi

echo
echo "Готово. Службы: $(systemctl is-active mgts-receiver) / $(systemctl is-active mgts-app)"
echo "Интерфейс:  http://${DOMAIN:-<IP сервера>}/"
echo "Приёмник:   POST http://${DOMAIN:-<IP сервера>}/response  (заголовок x-token из /etc/mgts/env)"

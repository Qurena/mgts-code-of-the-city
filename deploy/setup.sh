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
SURVEY_CONFIG=$APP_DIR/repo/prototype/mgts/survey.json
MAPPING_FILE=$APP_DIR/repo/prototype/mgts/mapping.json
STATIC_DIR=$APP_DIR/repo/docs
WEBHOOK_TOKEN=$(head -c 24 /dev/urandom | base64 | tr -d '/+=')
RECEIVER_URL=http://127.0.0.1:8765
ANALYZER=keywords
EOF
  chmod 640 /etc/mgts/env
  chgrp "$APP_USER" /etc/mgts/env
fi

grep -q "^STATIC_DIR=" /etc/mgts/env || echo "STATIC_DIR=$APP_DIR/repo/docs" >> /etc/mgts/env

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
ExecStart=$APP_DIR/venv/bin/streamlit run app.py --server.headless true --server.address 127.0.0.1 --server.port 8501 --server.baseUrlPath app --server.enableXsrfProtection true
Restart=always
[Install]
WantedBy=multi-user.target
EOF

# nginx: на / открывается дашборд и приём ответов (приёмник на 8765), старый интерфейс Streamlit с загрузкой файлов на /app/
cat > /etc/nginx/sites-available/mgts <<EOF
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name ${DOMAIN:-_};
    client_max_body_size 64k;

    location = /app { return 301 /app/; }
    location /app/ {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_read_timeout 86400;
    }
    location / {
        proxy_pass http://127.0.0.1:8765;
        proxy_set_header Host \$host;
    }
}
EOF
ln -sf /etc/nginx/sites-available/mgts /etc/nginx/sites-enabled/mgts
rm -f /etc/nginx/sites-enabled/default /etc/nginx/sites-enabled/webdock  # заглушка образа Webdock, файл остаётся в sites-available
nginx -t

# данные: пример в формате вебинара (две таблицы Excel из prototype/mgts/data) загружается один раз
if [ ! -f /var/lib/mgts/pulse.db ]; then
  (cd "$APP_DIR/repo/prototype" && sudo -u "$APP_USER" env PULSE_DB=/var/lib/mgts/pulse.db SURVEY_CONFIG="$APP_DIR/repo/prototype/mgts/survey.json" MAPPING_FILE="$APP_DIR/repo/prototype/mgts/mapping.json" "$APP_DIR/venv/bin/python" import_data.py mgts/mapping.json)
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
echo "Дашборд:    http://${DOMAIN:-<IP сервера>}/   (загрузка файлов: /app/)"
echo "Приёмник:   POST http://${DOMAIN:-<IP сервера>}/response  (заголовок x-token из /etc/mgts/env)"

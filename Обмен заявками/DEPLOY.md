# Развертывание для всех пользователей

Эта схема дает публичный доступ без VPN: пользователи заходят по домену через HTTPS, приложение работает на VPS/VDS, данные лежат в SQLite-файле на сервере.

## 1. Что нужно купить или подготовить

- VPS/VDS в РФ: Ubuntu 22.04/24.04, 1-2 CPU, 1-2 GB RAM, 20+ GB SSD.
- Домен или поддомен, например `sklad.company.ru`.
- DNS A-запись домена на публичный IP сервера.

## 2. Установка пакетов на сервере

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip nginx sqlite3 certbot python3-certbot-nginx git
```

## 3. Пользователь и папки

```bash
sudo useradd --system --home /opt/sklad --shell /usr/sbin/nologin sklad
sudo mkdir -p /opt/sklad /etc/sklad /var/lib/sklad /var/backups/sklad
sudo chown -R sklad:sklad /opt/sklad /var/lib/sklad /var/backups/sklad
```

## 4. Загрузка проекта

Скопируйте проект в `/opt/sklad`. Если переносите текущую базу, положите `sklad_requests.db` в `/var/lib/sklad/sklad_requests.db`.

```bash
cd /opt/sklad
sudo -u sklad python3 -m venv .venv
sudo -u sklad .venv/bin/pip install -r requirements.txt
```

## 5. Production env

```bash
sudo cp /opt/sklad/deploy/sklad.env.example /etc/sklad/sklad.env
sudo nano /etc/sklad/sklad.env
```

Обязательно замените:

```text
SESSION_SECRET_KEY=...
INITIAL_ADMIN_PASSWORD=...
```

Секрет можно сгенерировать так:

```bash
openssl rand -hex 32
```

После первого входа администратора смените пароль в интерфейсе.

## 6. systemd

```bash
sudo cp /opt/sklad/deploy/sklad.service /etc/systemd/system/sklad.service
sudo systemctl daemon-reload
sudo systemctl enable --now sklad
sudo systemctl status sklad
```

Проверка локально на сервере:

```bash
curl -I http://127.0.0.1:8000
```

## 7. Nginx

В файле `deploy/nginx.conf` замените `sklad.example.ru` на ваш домен.

```bash
sudo cp /opt/sklad/deploy/nginx.conf /etc/nginx/sites-available/sklad
sudo ln -s /etc/nginx/sites-available/sklad /etc/nginx/sites-enabled/sklad
sudo nginx -t
sudo systemctl reload nginx
```

## 8. HTTPS

```bash
sudo certbot --nginx -d sklad.company.ru
```

После выпуска сертификата проверьте:

```text
https://sklad.company.ru
```

## 9. Бэкапы

Проверить ручной бэкап:

```bash
sudo bash /opt/sklad/deploy/backup.sh
```

Добавить ежедневный запуск в cron:

```bash
sudo crontab -e
```

```cron
15 2 * * * /bin/bash /opt/sklad/deploy/backup.sh >/var/log/sklad-backup.log 2>&1
```

Бэкапы хранятся в `/var/backups/sklad`, старше 30 дней удаляются автоматически.

## 10. Обновление приложения

Перед обновлением:

```bash
sudo bash /opt/sklad/deploy/backup.sh
```

Затем обновите файлы проекта и выполните:

```bash
cd /opt/sklad
sudo -u sklad .venv/bin/pip install -r requirements.txt
sudo systemctl restart sklad
sudo systemctl status sklad
```

## Важные замечания

- Открывайте наружу только порты `80` и `443`.
- SSH лучше оставить только по ключу, не по паролю.
- Не включайте `SEED_DEMO_USERS=true` на боевом сервере.
- Если одновременно будет много пользователей или данные сильно вырастут, следующим шагом лучше перейти с SQLite на PostgreSQL.

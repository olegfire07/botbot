# Запуск на офисном Windows-компьютере

Этот вариант бесплатный, если офисный компьютер включен постоянно и провайдер дает доступ из интернета. Пользователи будут заходить по домену, например `https://sklad.company.ru`.

## 1. Проверить, возможен ли прямой доступ

Нужно одно из двух:

- белый статический IP от провайдера;
- белый динамический IP плюс DNS/DDNS.

Проверьте WAN IP в роутере и публичный IP на сайте проверки IP. Если WAN IP в роутере отличается от публичного или начинается с `10.`, `100.64.`, `172.16-31.` или `192.168.`, вы за CGNAT. Тогда без внешнего сервера или платной услуги белого IP сайт из интернета не откроется.

## 2. Схема запуска

```text
Интернет -> роутер офиса :443 -> офисный ПК -> Caddy -> 127.0.0.1:8000 -> FastAPI
```

Caddy стоит на этом же ПК и выпускает HTTPS-сертификат. Это не внешний proxy/VPN, а локальный веб-сервер на вашем компьютере.

## 3. Установить на Windows

- Python 3.11+.
- Caddy for Windows.

Проект удобно положить в:

```text
C:\SkladApp
```

Данные будут лежать отдельно:

```text
C:\SkladData\sklad_requests.db
C:\SkladBackups
```

## 4. Настроить приложение

Откройте PowerShell в папке проекта:

```powershell
cd C:\SkladApp
powershell -ExecutionPolicy Bypass -File .\deploy\windows\install-deps.ps1
copy .\deploy\windows\sklad.env.ps1.example .\deploy\windows\sklad.env.ps1
notepad .\deploy\windows\sklad.env.ps1
```

Обязательно замените:

```powershell
$env:SESSION_SECRET_KEY = "..."
$env:INITIAL_ADMIN_PASSWORD = "..."
```

Секрет можно сгенерировать:

```powershell
-join ((48..57)+(65..90)+(97..122) | Get-Random -Count 64 | ForEach-Object {[char]$_})
```

Если уже есть рабочая база, скопируйте ее:

```powershell
copy .\sklad_requests.db C:\SkladData\sklad_requests.db
```

## 5. Проверить локальный запуск

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\windows\start-sklad.ps1
```

На этом же компьютере откройте:

```text
http://127.0.0.1:8000
```

## 6. Настроить Caddy и домен

В файле:

```text
deploy\windows\Caddyfile
```

замените:

```text
sklad.example.ru
```

на ваш домен.

DNS домена должен указывать на публичный IP офиса.

Запуск Caddy для проверки:

```powershell
caddy run --config C:\SkladApp\deploy\windows\Caddyfile
```

## 7. Роутер и firewall

На роутере сделайте проброс портов на офисный ПК:

- TCP `80` -> IP офисного ПК `80`;
- TCP `443` -> IP офисного ПК `443`.

В Windows Firewall разрешите входящие TCP `80` и `443`. Быстрее всего это сделать через PowerShell (от имени администратора):

```powershell
New-NetFirewallRule -DisplayName "Caddy Web Server" -Direction Inbound -LocalPort 80,443 -Protocol TCP -Action Allow
```

IP офисного ПК внутри сети лучше закрепить в роутере через DHCP reservation, чтобы он не менялся.

## 8. Автозапуск и бэкапы

PowerShell от имени администратора:

```powershell
cd C:\SkladApp
powershell -ExecutionPolicy Bypass -File .\deploy\windows\register-tasks.ps1
```

Это создаст задачи:

- `Sklad App` - запуск приложения при старте Windows;
- `Sklad Backup` - ежедневный бэкап базы в 02:15;
- `Sklad Caddy` - запуск веб-сервера Caddy при старте Windows.

Теперь приложение и веб-сервер будут автоматически запускаться в фоновом режиме при включении компьютера, без черных окон консоли на рабочем столе.

## 9. Минусы офисного варианта

- Если выключили ПК, роутер или интернет - сайт недоступен.
- Если нет белого IP, напрямую не заработает.
- Нужно следить за Windows Update, антивирусом и местом на диске.
- Для боевой работы обязательно нужны бэкапы `C:\SkladBackups`.

Если провайдер не дает белый IP, самый дешевый надежный вариант - минимальный VPS в РФ.

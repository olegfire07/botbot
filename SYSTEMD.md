# Systemd Service для Telegram Bot

## 📋 Установка

### 1. Скопировать service файл
```bash
sudo cp telegram-bot.service /etc/systemd/system/
```

### 2. Перезагрузить systemd
```bash
sudo systemctl daemon-reload
```

### 3. Включить автозапуск
```bash
sudo systemctl enable telegram-bot.service
```

### 4. Запустить бот
```bash
sudo systemctl start telegram-bot.service
```

## 🔧 Управление

### Проверить статус
```bash
sudo systemctl status telegram-bot.service
```

### Остановить бота
```bash
sudo systemctl stop telegram-bot.service
```

### Перезапустить бота
```bash
sudo systemctl restart telegram-bot.service
```

### Посмотреть логи
```bash
sudo journalctl -u telegram-bot.service -f
```

### Отключить автозапуск
```bash
sudo systemctl disable telegram-bot.service
```

## ✨ Возможности

- ✅ **Автозапуск** при загрузке системы
- ✅ **Автоперезапуск** при падении (3 попытки за 60 сек)
- ✅ **Логирование** в файлы
- ✅ **Защита** от множественного запуска
- ✅ **Изоляция** временных файлов

## 📝 Примечания

- Логи сохраняются в `logs/bot.log` и `logs/bot_error.log`
- Systemd автоматически перезапустит бота при падении
- Lock file защищает от дублирующих процессов

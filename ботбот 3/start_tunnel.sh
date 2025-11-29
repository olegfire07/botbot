#!/bin/bash
echo "Запускаю туннель к боту..."
echo "Сейчас появится окно ngrok."
echo "Скопируйте адрес из строки 'Forwarding', который выглядит как https://....ngrok-free.app"
echo "Вставьте этот адрес в настройки на сайте."
echo ""
ngrok http 8080

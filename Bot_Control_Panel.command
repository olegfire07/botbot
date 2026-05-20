#!/bin/zsh
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
chmod +x "$DIR/start_bot_mac.command" 2>/dev/null || true
chmod +x "$DIR/stop_bot_mac.command" 2>/dev/null || true
BOT_SCRIPT="$DIR/run_modern_bot.py"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

function check_python() {
    if ! command -v python3.12 >/dev/null 2>&1; then
        echo -e "${RED}❌ Ошибка: Python 3.12 не найден!${NC}"
        echo -e "Для установки на новом Mac (если установлен Homebrew) выполните команду:"
        echo -e "${CYAN}brew install python@3.12${NC}"
        echo -e "Или скачайте установщик с официального сайта: https://www.python.org/downloads/mac-osx/"
        echo ""
        read -s -k 1 "?Нажмите любую клавишу для возврата в меню..."
        return 1
    fi
    return 0
}

function check_venv() {
    if [ ! -d ".venv" ] || [ ! -x ".venv/bin/python" ]; then
        echo -e "${YELLOW}🔄 Создаю виртуальное окружение .venv...${NC}"
        if ! python3.12 -m venv .venv; then
            echo -e "${YELLOW}🔁 Пробуем создать с параметром --copies...${NC}"
            rm -rf .venv
            python3.12 -m venv --copies .venv
        fi
    fi
}

function install_deps() {
    VENV_PY=".venv/bin/python"
    if [ ! -x "$VENV_PY" ]; then
        echo -e "${RED}❌ Виртуальное окружение не найдено или повреждено.${NC}"
        read -s -k 1 "?Нажмите любую клавишу для возврата в меню..."
        return 1
    fi
    if [ ! -f ".venv/.deps_installed" ] || [ requirements.txt -nt .venv/.deps_installed ]; then
        echo -e "${YELLOW}📦 Установка и обновление зависимостей (это может занять время)...${NC}"
        "$VENV_PY" -m pip install -r requirements.txt
        touch .venv/.deps_installed
        echo -e "${GREEN}✅ Зависимости успешно установлены.${NC}"
    else
        echo -e "${GREEN}✅ Зависимости в актуальном состоянии.${NC}"
    fi
    sleep 1
}

function get_bot_status() {
    PID=""
    if [ -f .bot.lock ]; then PID=$(cat .bot.lock 2>/dev/null || true); fi
    if [ -z "$PID" ] && [ -f bot.pid ]; then PID=$(cat bot.pid 2>/dev/null || true); fi

    if [ -z "$PID" ]; then
        PIDS=($(pgrep -f "$BOT_SCRIPT" 2>/dev/null || true))
        if [ ${#PIDS[@]} -gt 0 ]; then
            PID="${PIDS[1]}"
        fi
    fi

    if [ -n "$PID" ] && ps -p "$PID" >/dev/null 2>&1; then
        echo -e "Статус: ${GREEN}🟢 РАБОТАЕТ (PID: $PID)${NC}"
        return 0
    else
        echo -e "Статус: ${RED}🔴 ОСТАНОВЛЕН${NC}"
        return 1
    fi
}

function start_bot() {
    check_python || return 1
    check_venv
    install_deps || return 1

    if get_bot_status >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠️ Бот уже запущен!${NC}"
        read -s -k 1 "?Нажмите любую клавишу для возврата в меню..."
        return
    fi

    # Очистка старых локов
    rm -f .bot.lock bot.pid

    echo -e "${CYAN}🚀 Запускаю бота в фоновом режиме...${NC}"
    VENV_PY=".venv/bin/python"
    nohup "$VENV_PY" "$BOT_SCRIPT" > out.log 2>&1 &
    BG_PID=$!
    echo "$BG_PID" > bot.pid
    sleep 2

    if ps -p "$BG_PID" >/dev/null 2>&1; then
        API_PORT=$(grep "^API_PORT=" .env | cut -d'=' -f2 | tr -d '\r ' 2>/dev/null || true)
        if [ -z "$API_PORT" ]; then
            API_PORT="8080"
        fi
        echo -e "${GREEN}✅ Бот успешно запущен!${NC}"
        echo -e "${BLUE}┌────────────────────────────────────────────────────────────┐${NC}"
        echo -e "${BLUE}│${NC}  ${YELLOW}👑 СЕРВЕР ИНТЕРФЕЙСА УСПЕШНО ЗАПУЩЕН${NC}                      ${BLUE}│${NC}"
        echo -e "${BLUE}├────────────────────────────────────────────────────────────┤${NC}"
        echo -e "${BLUE}│${NC}  ${CYAN}🌍 Адрес API:${NC}      http://localhost:${API_PORT}                ${BLUE}│${NC}"
        echo -e "${BLUE}│${NC}  ${CYAN}🔑 Панель Admin:${NC}  http://localhost:${API_PORT}/super-admin          ${BLUE}│${NC}"
        echo -e "${BLUE}└────────────────────────────────────────────────────────────┘${NC}"
    else
        echo -e "${RED}❌ Не удалось запустить бота. Проверьте логи.${NC}"
    fi
    
    echo ""
    read -s -k 1 "?Нажмите любую клавишу для возврата в меню..."
}

function stop_bot() {
    PID=""
    if [ -f .bot.lock ]; then PID=$(cat .bot.lock 2>/dev/null || true); fi
    if [ -z "$PID" ] && [ -f bot.pid ]; then PID=$(cat bot.pid 2>/dev/null || true); fi
    
    if [ -z "$PID" ]; then
        PIDS=($(pgrep -f "$BOT_SCRIPT" 2>/dev/null || true))
        if [ ${#PIDS[@]} -gt 0 ]; then
            PID="${PIDS[1]}"
        fi
    fi

    if [ -n "$PID" ] && ps -p "$PID" >/dev/null 2>&1; then
        echo -e "${YELLOW}🔴 Останавливаю бота (PID $PID)...${NC}"
        kill -INT "$PID" || true
        sleep 2
        if ps -p "$PID" >/dev/null 2>&1; then
            kill "$PID" || echo "Не удалось убить процесс."
            sleep 2
        fi
        echo -e "${GREEN}✅ Бот остановлен.${NC}"
    else
        echo -e "${YELLOW}Бот уже остановлен (процесс не найден).${NC}"
    fi

    rm -f .bot.lock bot.pid
    
    echo ""
    read -s -k 1 "?Нажмите любую клавишу для возврата в меню..."
}

function restart_bot() {
    echo -e "${CYAN}🔄 Выполняю перезапуск бота...${NC}"
    # Stop quietly
    PID=""
    if [ -f bot.pid ]; then PID=$(cat bot.pid 2>/dev/null || true); fi
    if [ -z "$PID" ]; then
        PIDS=($(pgrep -f "$BOT_SCRIPT" 2>/dev/null || true))
        if [ ${#PIDS[@]} -gt 0 ]; then
            PID="${PIDS[1]}"
        fi
    fi
    if [ -n "$PID" ]; then kill -INT "$PID" 2>/dev/null || kill "$PID" 2>/dev/null || true; fi
    rm -f .bot.lock bot.pid
    sleep 2
    
    # Start bot directly without pausing
    start_bot
}

function show_logs() {
    clear
    echo -e "${BLUE}=================== ПОСЛЕДНИЕ ЛОГИ СИСТЕМЫ ===================${NC}"
    if [ -f "out.log" ]; then
        tail -n 25 out.log
    else
        echo "Файл out.log пока пуст."
    fi
    
    echo -e "\n${BLUE}=================== ЛОГИ РАБОТЫ BOT API =====================${NC}"
    if ls logs/bot_*.log 1> /dev/null 2>&1; then
        LATEST_LOG=$(ls -t logs/bot_*.log | head -n 1)
        tail -n 25 "$LATEST_LOG"
    else
        echo "Логи в папке logs/ не найдены."
    fi
    echo -e "${BLUE}==============================================================${NC}"
    echo ""
    read -s -k 1 "?Нажмите любую клавишу для возврата в меню..."
}

function update_dependencies() {
    echo -e "${YELLOW}🛠 Внимание! Будет выполнена полная очистка и переустановка окружения.${NC}"
    echo -n "Вы уверены? (y/n): "
    read answer
    if [ "$answer" != "${answer#[Yy]}" ]; then
        echo -e "${CYAN}🧹 Очистка старого окружения...${NC}"
        # Stop bot silently
        PID=$(cat bot.pid 2>/dev/null || true)
        if [ -n "$PID" ]; then kill -9 "$PID" 2>/dev/null || true; fi
        rm -f .bot.lock bot.pid
        rm -rf .venv
        
        echo -e "${CYAN}📦 Установка нового окружения...${NC}"
        check_venv
        install_deps
        echo -e "${GREEN}✅ Обновление завершено!${NC}"
    else
        echo -e "${YELLOW}Отменено.${NC}"
    fi
    
    echo ""
    read -s -k 1 "?Нажмите любую клавишу для возврата в меню..."
}


# Main Menu Loop
while true; do
    clear
    echo -e "${BLUE}==============================================================${NC}"
    echo -e " ${GREEN}🤖 ПАНЕЛЬ УПРАВЛЕНИЯ БОТОМ ОЦЕНКИ${NC} (Папка: $DIR)"
    echo -e "${BLUE}==============================================================${NC}"
    
    get_bot_status
    
    echo -e "${BLUE}==============================================================${NC}"
    echo -e " ${CYAN}[1]${NC} ▶️ Запустить бота"
    echo -e " ${CYAN}[2]${NC} ⏹ Остановить бота"
    echo -e " ${CYAN}[3]${NC} 🔄 Перезапуск (остановить и запустить заново)"
    echo -e " ${CYAN}[4]${NC} 📋 Посмотреть логи (последние 50 строк)"
    echo -e " ${CYAN}[5]${NC} 🛠 Полная переустановка окружения (для нового Mac)"
    echo -e " ${RED}[0]${NC} ❌ Выйти из панели"
    echo -e "${BLUE}==============================================================${NC}"
    
    echo -n "👉 Выберите действие (0-5): "
    read -k 1 choice
    echo "" # newline After single char read
    echo ""
    
    case $choice in
        1) start_bot ;;
        2) stop_bot ;;
        3) restart_bot ;;
        4) show_logs ;;
        5) update_dependencies ;;
        0) echo -e "${GREEN}До свидания! Панель закрыта.${NC}"; exit 0 ;;
        *) echo -e "${RED}❌ Неверный выбор, попробуйте снова.${NC}"; sleep 1 ;;
    esac
done

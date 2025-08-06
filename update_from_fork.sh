#!/bin/bash

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}Скрипт обновления vless-shopbot с вашего форка${NC}"
echo -e "${YELLOW}Убедитесь, что вы заменили YOUR_USERNAME на ваш GitHub username!${NC}\n"

# Запрашиваем у пользователя его GitHub username
read -p "Введите ваш GitHub username: " GITHUB_USERNAME

if [ -z "$GITHUB_USERNAME" ]; then
    echo -e "${RED}Ошибка: GitHub username не может быть пустым!${NC}"
    exit 1
fi

PROJECT_DIR="vless-shopbot"
FORK_URL="https://github.com/$GITHUB_USERNAME/vless-shopbot.git"

echo -e "\n${CYAN}Шаг 1: Остановка текущих контейнеров...${NC}"
if [ -d "$PROJECT_DIR" ]; then
    cd $PROJECT_DIR
    sudo docker-compose down
    cd ..
else
    echo -e "${YELLOW}Папка $PROJECT_DIR не найдена, пропускаем остановку контейнеров${NC}"
fi

echo -e "\n${CYAN}Шаг 2: Создание бэкапа текущей версии...${NC}"
if [ -d "$PROJECT_DIR" ]; then
    BACKUP_NAME="${PROJECT_DIR}_backup_$(date +%Y%m%d_%H%M%S)"
    mv $PROJECT_DIR $BACKUP_NAME
    echo -e "${GREEN}✔ Бэкап создан: $BACKUP_NAME${NC}"
fi

echo -e "\n${CYAN}Шаг 3: Клонирование вашего форка...${NC}"
git clone $FORK_URL $PROJECT_DIR

if [ $? -ne 0 ]; then
    echo -e "${RED}Ошибка при клонировании репозитория!${NC}"
    echo -e "${YELLOW}Проверьте правильность username и доступность репозитория${NC}"
    exit 1
fi

cd $PROJECT_DIR

echo -e "\n${CYAN}Шаг 4: Восстановление .env файла (если есть)...${NC}"
if [ -f "../${BACKUP_NAME}/.env" ]; then
    cp "../${BACKUP_NAME}/.env" .env
    echo -e "${GREEN}✔ .env файл восстановлен${NC}"
else
    echo -e "${YELLOW}⚠ .env файл не найден в бэкапе${NC}"
fi

echo -e "\n${CYAN}Шаг 5: Восстановление базы данных (если есть)...${NC}"
if [ -f "../${BACKUP_NAME}/shop_bot.db" ]; then
    cp "../${BACKUP_NAME}/shop_bot.db" shop_bot.db
    echo -e "${GREEN}✔ База данных восстановлена${NC}"
else
    echo -e "${YELLOW}⚠ База данных не найдена в бэкапе${NC}"
fi

echo -e "\n${CYAN}Шаг 6: Пересборка и запуск контейнеров...${NC}"
sudo docker-compose build --no-cache
sudo docker-compose up -d

echo -e "\n${CYAN}Шаг 7: Проверка статуса контейнеров...${NC}"
sudo docker-compose ps

echo -e "\n${GREEN}=====================================================${NC}"
echo -e "${GREEN}      🎉 Обновление успешно завершено! 🎉           ${NC}"
echo -e "${GREEN}=====================================================${NC}"
echo -e "\n${YELLOW}Что было исправлено в этой версии:${NC}"
echo -e "• ✅ Добавлен ProxyFix для корректной работы с nginx"
echo -e "• ✅ Исправлена nginx конфигурация"
echo -e "• ✅ Исправлено сохранение настроек контента"
echo -e "• ✅ Улучшена обработка форм в веб-интерфейсе"
echo -e "• ✅ Добавлено логирование для отладки"

echo -e "\n${CYAN}Проверьте работу бота и веб-панели!${NC}"
echo -e "${YELLOW}Бэкап старой версии сохранен в: $BACKUP_NAME${NC}" 
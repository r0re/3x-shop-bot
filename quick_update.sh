#!/bin/bash

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}Быстрое обновление vless-shopbot с вашего форка${NC}\n"

# Запрашиваем у пользователя его GitHub username
read -p "Введите ваш GitHub username: " GITHUB_USERNAME

if [ -z "$GITHUB_USERNAME" ]; then
    echo -e "${RED}Ошибка: GitHub username не может быть пустым!${NC}"
    exit 1
fi

FORK_URL="https://github.com/$GITHUB_USERNAME/vless-shopbot.git"

echo -e "\n${CYAN}Шаг 1: Остановка контейнеров...${NC}"
sudo docker-compose down

echo -e "\n${CYAN}Шаг 2: Изменение remote на ваш форк...${NC}"
git remote set-url origin $FORK_URL
echo -e "${GREEN}✔ Remote изменен на: $FORK_URL${NC}"

echo -e "\n${CYAN}Шаг 3: Получение обновлений...${NC}"
git fetch origin
git reset --hard origin/main

echo -e "\n${CYAN}Шаг 4: Пересборка и запуск контейнеров...${NC}"
sudo docker-compose build --no-cache
sudo docker-compose up -d

echo -e "\n${CYAN}Шаг 5: Перезагрузка nginx...${NC}"
sudo nginx -t && sudo systemctl reload nginx

echo -e "\n${GREEN}=====================================================${NC}"
echo -e "${GREEN}      🎉 Быстрое обновление завершено! 🎉            ${NC}"
echo -e "${GREEN}=====================================================${NC}"
echo -e "\n${YELLOW}Что было исправлено:${NC}"
echo -e "• ✅ Добавлен ProxyFix для Flask"
echo -e "• ✅ Исправлена nginx конфигурация"
echo -e "• ✅ Исправлено сохранение настроек контента"
echo -e "• ✅ Улучшена обработка форм"

echo -e "\n${CYAN}Проверьте статус:${NC}"
sudo docker-compose ps 
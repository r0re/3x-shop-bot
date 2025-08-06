GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

handle_error() {
    echo -e "\n${RED}Ошибка на строке $1. Установка прервана.${NC}"
    exit 1
}

trap 'handle_error $LINENO' ERR

echo -e "${GREEN}--- Запуск установки VLESS Shop Bot с автоматической настройкой SSL ---${NC}"

echo -e "\n${CYAN}Шаг 1: Установка системных зависимостей...${NC}"

install_package() {
    if ! command -v $1 &> /dev/null; then
        echo -e "${YELLOW}Утилита '$1' не найдена. Устанавливаем...${NC}"
        sudo apt-get update
        sudo apt-get install -y $2
    else
        echo -e "${GREEN}✔ $1 уже установлен.${NC}"
    fi
}

install_package "git" "git"
install_package "docker" "docker.io"
install_package "docker-compose" "docker-compose"
install_package "nginx" "nginx"
install_package "curl" "curl"
install_package "certbot" "certbot python3"

if ! sudo systemctl is-active --quiet docker; then
    echo -e "${YELLOW}Сервис Docker не запущен. Запускаем и добавляем в автозагрузку...${NC}"
    sudo systemctl start docker
    sudo systemctl enable docker
fi

if ! sudo systemctl is-active --quiet nginx; then
    echo -e "${YELLOW}Сервис Nginx не запущен. Запускаем и добавляем в автозагрузку...${NC}"
    sudo systemctl start nginx
    sudo systemctl enable nginx
fi
echo -e "${GREEN}✔ Все системные зависимости установлены.${NC}"

REPO_URL="https://github.com/evansvl/vless-shopbot.git"
PROJECT_DIR="vless-shopbot"

echo -e "\n${CYAN}Шаг 2: Клонирование репозитория...${NC}"
if [ -d "$PROJECT_DIR" ]; then
    echo -e "${YELLOW}Папка '$PROJECT_DIR' уже существует. Пропускаем клонирование.${NC}"
else
    git clone $REPO_URL
fi
cd $PROJECT_DIR
echo -e "${GREEN}✔ Репозиторий готов.${NC}"

echo -e "\n${CYAN}Шаг 3: Настройка домена и получение SSL-сертификатов...${NC}"

read -p "Введите ваш домен (например, my-vpn-shop.com): " RAW_DOMAIN
read -p "Введите ваш email (для регистрации SSL-сертификатов Let's Encrypt): " EMAIL

DOMAIN_NO_PROTOCOL=$(echo $RAW_DOMAIN | sed -e 's%^https\?://%%')
DOMAIN_NO_PATH=$(echo $DOMAIN_NO_PROTOCOL | cut -d'/' -f1)
DOMAIN=$(echo $DOMAIN_NO_PATH | cut -d':' -f1)

if [ -z "$DOMAIN" ]; then
    echo -e "${RED}Ошибка: Домен не может быть пустым. Установка прервана.${NC}"
    exit 1
fi

echo -e "${GREEN}✔ Домен для работы: ${DOMAIN}${NC}"

SERVER_IP=$(curl -s ifconfig.me || hostname -I | awk '{print $1}')
DOMAIN_IP=$(dig +short $DOMAIN @8.8.8.8 | tail -n1)

echo -e "${YELLOW}IP вашего сервера: $SERVER_IP${NC}"
echo -e "${YELLOW}IP, на который указывает домен '$DOMAIN': $DOMAIN_IP${NC}"

if [ -z "$DOMAIN_IP" ]; then
    echo -e "${RED}ВНИМАНИЕ: Не удалось определить IP-адрес для домена $DOMAIN. Убедитесь, что DNS-запись существует и уже обновилась.${NC}"
    read -p "Продолжить установку? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Установка прервана."
        exit 1
    fi
fi

if [ "$SERVER_IP" != "$DOMAIN_IP" ]; then
    echo -e "${RED}ВНИМАНИЕ: DNS-запись для домена $DOMAIN не указывает на IP-адрес этого сервера!${NC}"
    read -p "Продолжить установку? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Установка прервана."
        exit 1
    fi
fi

if command -v ufw &> /dev/null && sudo ufw status | grep -q 'Status: active'; then
    echo -e "${YELLOW}Обнаружен активный файрвол (ufw). Открываем порты 80 и 443...${NC}"
    sudo ufw allow 80/tcp
    sudo ufw allow 443/tcp
    sudo ufw allow 1488/tcp
    sudo ufw allow 8443/tcp
fi

if [ -d "/etc/letsencrypt/live/$DOMAIN" ]; then
    echo -e "${GREEN}✔ SSL-сертификаты для домена $DOMAIN уже существуют. Пропускаем получение.${NC}"
else
    echo -e "${YELLOW}Получаем SSL-сертификаты для $DOMAIN...${NC}"
    sudo systemctl stop nginx
    sudo certbot certonly --standalone -d $DOMAIN --email $EMAIL --agree-tos --non-interactive
    sudo systemctl start nginx
    echo -e "${GREEN}✔ SSL-сертификаты успешно получены.${NC}"
fi

echo -e "\n${CYAN}Шаг 4: Настройка Nginx...${NC}"

read -p "Какой порт вы будете использовать для вебхуков YooKassa? (443 или 8443, рекомендуется 443): " YOOKASSA_PORT
YOOKASSA_PORT=${YOOKASSA_PORT:-443}

NGINX_CONF_FILE="/etc/nginx/sites-available/$PROJECT_DIR.conf"
NGINX_ENABLED_FILE="/etc/nginx/sites-enabled/$PROJECT_DIR.conf"

echo -e "Создаем конфигурацию Nginx..."
sudo bash -c "cat > $NGINX_CONF_FILE" <<EOF
server {
    listen ${YOOKASSA_PORT} ssl http2;
    listen [::]:${YOOKASSA_PORT} ssl http2;

    server_name ${DOMAIN};

    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305';

    location / {
        proxy_pass http://127.0.0.1:1488;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

if [ ! -f "$NGINX_ENABLED_FILE" ]; then
    sudo ln -s $NGINX_CONF_FILE $NGINX_ENABLED_FILE
fi

# Удаляем дефолтный сайт nginx
if [ -f "/etc/nginx/sites-enabled/default" ]; then
    sudo rm /etc/nginx/sites-enabled/default
    echo -e "${GREEN}✔ Дефолтный сайт nginx удален.${NC}"
fi

echo -e "${GREEN}✔ Конфигурация Nginx создана.${NC}"
echo -e "${YELLOW}Проверяем и перезагружаем Nginx...${NC}"
sudo nginx -t && sudo systemctl reload nginx

echo -e "\n${CYAN}Шаг 5: Сборка и запуск Docker-контейнера...${NC}"
if [ "$(sudo docker-compose ps -q)" ]; then
    echo -e "${YELLOW}Обнаружены работающие контейнеры. Останавливаем...${NC}"
    sudo docker-compose down
fi
sudo docker-compose up -d --build

echo -e "\n\n${GREEN}=====================================================${NC}"
echo -e "${GREEN}      🎉 Установка и запуск успешно завершены! 🎉      ${NC}"
echo -e "${GREEN}=====================================================${NC}"
echo -e "\nВеб-панель доступна по адресу:"
echo -e "  - ${YELLOW}https://${DOMAIN}:${YOOKASSA_PORT}/login${NC}"

# Читаем сгенерированные учетные данные
if [ -f "${PROJECT_DIR}/admin_credentials.txt" ]; then
    echo -e "\n${RED}🔐 ВАЖНО! Сохраните эти данные в безопасном месте:${NC}"
    echo -e "${CYAN}=============================================${NC}"
    
    ADMIN_LOGIN=$(grep "ADMIN_LOGIN=" ${PROJECT_DIR}/admin_credentials.txt | cut -d'=' -f2)
    ADMIN_PASSWORD=$(grep "ADMIN_PASSWORD=" ${PROJECT_DIR}/admin_credentials.txt | cut -d'=' -f2)
    
    echo -e "  Логин администратора:  ${GREEN}${ADMIN_LOGIN}${NC}"
    echo -e "  Пароль администратора: ${GREEN}${ADMIN_PASSWORD}${NC}"
    echo -e "${CYAN}=============================================${NC}"
    
    # Удаляем файл с учетными данными после вывода для безопасности
    rm ${PROJECT_DIR}/admin_credentials.txt
    echo -e "${YELLOW}⚠️  Файл с учетными данными удален для безопасности${NC}"
else
    echo -e "\n${RED}⚠️  Не удалось найти сгенерированные учетные данные${NC}"
    echo -e "  - Логин:   ${CYAN}admin${NC}"
    echo -e "  - Пароль:  ${CYAN}admin${NC}"
fi

echo -e "\n${RED}ПЕРВЫЕ ШАГИ:${NC}"
echo -e "1. Войдите в панель используя данные выше."
echo -e "2. На странице 'Настройки' введите ваш Telegram токен, username бота и ваш Telegram ID."
echo -e "3. Нажмите 'Сохранить' и затем 'Запустить Бота'."
echo -e "\n${CYAN}Не забудьте указать URL для вебхуков в YooKassa:${NC}"
echo -e "  - ${YELLOW}https://${DOMAIN}:${YOOKASSA_PORT}/yookassa-webhook${NC}"
echo -e "\n"

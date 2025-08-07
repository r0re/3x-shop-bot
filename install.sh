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

REPO_URL="https://github.com/r0re/3xShop-bot.git"

# Функция для настройки пользовательских SSL сертификатов
setup_custom_ssl() {
    echo -e "${YELLOW}Настройка пользовательских SSL сертификатов${NC}"
    echo -e "\nВам нужно предоставить пути к следующим файлам:"
    echo -e "  1. Файл сертификата (.crt или .pem)"
    echo -e "  2. Файл приватного ключа (.key)"
    echo -e "  3. Файл цепочки сертификатов (опционально)"
    
    read -p "Введите полный путь к файлу сертификата: " CERT_FILE
    read -p "Введите полный путь к файлу приватного ключа: " KEY_FILE
    read -p "Введите полный путь к файлу цепочки сертификатов (оставьте пустым, если нет): " CHAIN_FILE
    
    # Проверяем существование файлов
    if [ ! -f "$CERT_FILE" ]; then
        echo -e "${RED}❌ Файл сертификата не найден: $CERT_FILE${NC}"
        USE_SSL=false
        return
    fi
    
    if [ ! -f "$KEY_FILE" ]; then
        echo -e "${RED}❌ Файл приватного ключа не найден: $KEY_FILE${NC}"
        USE_SSL=false
        return
    fi
    
    # Создаем директорию для пользовательских сертификатов
    CUSTOM_SSL_DIR="/etc/ssl/custom/$DOMAIN"
    sudo mkdir -p "$CUSTOM_SSL_DIR"
    
    # Копируем файлы
    sudo cp "$CERT_FILE" "$CUSTOM_SSL_DIR/cert.pem"
    sudo cp "$KEY_FILE" "$CUSTOM_SSL_DIR/privkey.pem"
    
    if [ -n "$CHAIN_FILE" ] && [ -f "$CHAIN_FILE" ]; then
        sudo cp "$CHAIN_FILE" "$CUSTOM_SSL_DIR/chain.pem"
        # Создаем fullchain (cert + chain)
        sudo bash -c "cat '$CUSTOM_SSL_DIR/cert.pem' '$CUSTOM_SSL_DIR/chain.pem' > '$CUSTOM_SSL_DIR/fullchain.pem'"
    else
        # Если нет цепочки, используем только сертификат
        sudo cp "$CUSTOM_SSL_DIR/cert.pem" "$CUSTOM_SSL_DIR/fullchain.pem"
    fi
    
    # Устанавливаем правильные права доступа
    sudo chmod 644 "$CUSTOM_SSL_DIR/cert.pem" "$CUSTOM_SSL_DIR/fullchain.pem"
    sudo chmod 600 "$CUSTOM_SSL_DIR/privkey.pem"
    sudo chown root:root "$CUSTOM_SSL_DIR"/*
    
    # Устанавливаем переменные для использования в конфигурации Nginx
    SSL_CERT_PATH="$CUSTOM_SSL_DIR/fullchain.pem"
    SSL_KEY_PATH="$CUSTOM_SSL_DIR/privkey.pem"
    USE_SSL=true
    
    echo -e "${GREEN}✔ Пользовательские SSL сертификаты настроены.${NC}"
}
PROJECT_DIR="3xShop-bot"

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

# Настройка SSL сертификатов
echo -e "\n${CYAN}Настройка SSL сертификатов${NC}"

if [ -d "/etc/letsencrypt/live/$DOMAIN" ]; then
    echo -e "${GREEN}✔ SSL-сертификаты для домена $DOMAIN уже существуют.${NC}"
    echo -e "\nВыберите действие:"
    echo -e "  ${YELLOW}1)${NC} Использовать существующие сертификаты"
    echo -e "  ${YELLOW}2)${NC} Получить новые сертификаты (перезапись существующих)"
    echo -e "  ${YELLOW}3)${NC} Использовать свои сертификаты"
    echo -e "  ${YELLOW}4)${NC} Запуск без SSL (HTTP только)"
    read -p "Введите номер (1-4, по умолчанию 1): " SSL_CHOICE
    SSL_CHOICE=${SSL_CHOICE:-1}
else
    echo -e "${YELLOW}SSL-сертификаты для домена $DOMAIN не найдены.${NC}"
    echo -e "\nВыберите действие:"
    echo -e "  ${YELLOW}1)${NC} Получить новые сертификаты от Let's Encrypt"
    echo -e "  ${YELLOW}2)${NC} Использовать свои сертификаты"
    echo -e "  ${YELLOW}3)${NC} Запуск без SSL (HTTP только)"
    read -p "Введите номер (1-3, по умолчанию 1): " SSL_CHOICE
    SSL_CHOICE=${SSL_CHOICE:-1}
fi

case $SSL_CHOICE in
    1)
        if [ -d "/etc/letsencrypt/live/$DOMAIN" ]; then
            echo -e "${GREEN}✔ Используем существующие сертификаты.${NC}"
            USE_SSL=true
        else
            echo -e "${YELLOW}Получаем SSL-сертификаты от Let's Encrypt...${NC}"
            sudo systemctl stop nginx
            if sudo certbot certonly --standalone -d $DOMAIN --email $EMAIL --agree-tos --non-interactive; then
                echo -e "${GREEN}✔ SSL-сертификаты успешно получены.${NC}"
                USE_SSL=true
            else
                echo -e "${RED}⚠ Не удалось получить SSL-сертификат.${NC}"
                echo -e "${YELLOW}Возможные причины:${NC}"
                echo -e "  - Превышен лимит Let's Encrypt (5 сертификатов в неделю)"
                echo -e "  - Домен недоступен или неправильно настроен"
                echo -e "  - Проблемы с DNS"
                echo -e "\n${YELLOW}Продолжить без SSL?${NC}"
                read -p "y/N: " CONTINUE_WITHOUT_SSL
                if [[ $CONTINUE_WITHOUT_SSL =~ ^[Yy]$ ]]; then
                    USE_SSL=false
                else
                    echo -e "${RED}Установка прервана.${NC}"
                    exit 1
                fi
            fi
            sudo systemctl start nginx
        fi
        ;;
    2)
        if [ -d "/etc/letsencrypt/live/$DOMAIN" ]; then
            echo -e "${YELLOW}Получаем новые SSL-сертификаты (перезапись)...${NC}"
            sudo systemctl stop nginx
            if sudo certbot certonly --standalone -d $DOMAIN --email $EMAIL --agree-tos --non-interactive --force-renewal; then
                echo -e "${GREEN}✔ SSL-сертификаты успешно обновлены.${NC}"
                USE_SSL=true
            else
                echo -e "${RED}⚠ Не удалось получить новые SSL-сертификаты.${NC}"
                echo -e "${YELLOW}Продолжить с существующими сертификатами? (y/N): ${NC}"
                read CONTINUE_EXISTING
                if [[ $CONTINUE_EXISTING =~ ^[Yy]$ ]]; then
                    USE_SSL=true
                else
                    USE_SSL=false
                fi
            fi
            sudo systemctl start nginx
        else
            # Для случая, когда сертификатов нет, но выбрали "использовать свои"
            echo -e "${YELLOW}Настройка пользовательских сертификатов...${NC}"
            setup_custom_ssl
        fi
        ;;
    3)
        if [ -d "/etc/letsencrypt/live/$DOMAIN" ]; then
            setup_custom_ssl
        else
            echo -e "${YELLOW}Запуск без SSL (HTTP только)...${NC}"
            USE_SSL=false
        fi
        ;;
    4)
        echo -e "${YELLOW}Запуск без SSL (HTTP только)...${NC}"
        USE_SSL=false
        ;;
    *)
        echo -e "${RED}Неверный выбор. Используем настройки по умолчанию.${NC}"
        if [ -d "/etc/letsencrypt/live/$DOMAIN" ]; then
            USE_SSL=true
        else
            USE_SSL=false
        fi
        ;;
esac

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



echo -e "\n${CYAN}Шаг 4: Настройка Nginx...${NC}"

read -p "Какой порт вы будете использовать для вебхуков YooKassa? (443 или 8443, рекомендуется 443): " YOOKASSA_PORT
YOOKASSA_PORT=${YOOKASSA_PORT:-443}

NGINX_CONF_FILE="/etc/nginx/sites-available/$PROJECT_DIR.conf"
NGINX_ENABLED_FILE="/etc/nginx/sites-enabled/$PROJECT_DIR.conf"

echo -e "Создаем конфигурацию Nginx..."

if [ "$USE_SSL" = true ]; then
    echo -e "${GREEN}Создаем конфигурацию с SSL...${NC}"
    
    # Устанавливаем пути к сертификатам (по умолчанию Let's Encrypt)
    if [ -z "$SSL_CERT_PATH" ]; then
        SSL_CERT_PATH="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
        SSL_KEY_PATH="/etc/letsencrypt/live/${DOMAIN}/privkey.pem"
    fi
    
    sudo bash -c "cat > $NGINX_CONF_FILE" <<EOF
server {
    listen ${YOOKASSA_PORT} ssl http2;
    listen [::]:${YOOKASSA_PORT} ssl http2;

    server_name ${DOMAIN};

    ssl_certificate ${SSL_CERT_PATH};
    ssl_certificate_key ${SSL_KEY_PATH};

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

# Редирект с HTTP на HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};
    return 301 https://\$server_name\$request_uri;
}
EOF
else
    echo -e "${YELLOW}Создаем конфигурацию без SSL (HTTP только)...${NC}"
    YOOKASSA_PORT=80
    sudo bash -c "cat > $NGINX_CONF_FILE" <<EOF
server {
    listen 80;
    listen [::]:80;

    server_name ${DOMAIN};

    location / {
        proxy_pass http://127.0.0.1:1488;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
fi

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
if [ "$USE_SSL" = true ]; then
    echo -e "  - ${YELLOW}https://${DOMAIN}:${YOOKASSA_PORT}/login${NC}"
    if [[ "$SSL_CERT_PATH" == *"letsencrypt"* ]]; then
        echo -e "  ${GREEN}🔒 Используются сертификаты Let's Encrypt${NC}"
    elif [[ "$SSL_CERT_PATH" == *"custom"* ]]; then
        echo -e "  ${GREEN}🔒 Используются пользовательские SSL сертификаты${NC}"
    fi
else
    echo -e "  - ${YELLOW}http://${DOMAIN}:${YOOKASSA_PORT}/login${NC}"
    echo -e "  ${RED}⚠ Внимание: Используется HTTP без SSL шифрования!${NC}"
fi

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

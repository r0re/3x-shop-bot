# Исправления в форке vless-shopbot

## Проблемы и их решения

### 🧠 1. Вставка ProxyFix в Flask
**Проблема**: Flask приложение некорректно обрабатывало заголовки от прокси-сервера nginx.

**Решение**:
- Добавлен импорт `from werkzeug.middleware.proxy_fix import ProxyFix` в `src/shop_bot/webhook_server/app.py`
- После создания Flask-приложения добавлена настройка ProxyFix:
```python
flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
```

### 🛡️ 2. Починка nginx-конфигурации
**Проблема**: В `install.sh` nginx конфигурация использовала `try_files` с fallback на `@backend`, что могло вызывать проблемы.

**Решение**:
- Изменена конфигурация nginx в `install.sh`
- Убрана конструкция `try_files` и `@backend`
- Все запросы теперь сразу проксируются на Flask приложение:
```nginx
location / {
    proxy_pass http://127.0.0.1:1488;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

### 🧼 3. Удаление дефолтного сайта nginx
**Решение**:
- Добавлено автоматическое удаление дефолтного сайта nginx в `install.sh`:
```bash
if [ -f "/etc/nginx/sites-enabled/default" ]; then
    sudo rm /etc/nginx/sites-enabled/default
    echo -e "${GREEN}✔ Дефолтный сайт nginx удален.${NC}"
fi
```

### 📝 4. Исправление проблем с сохранением настроек контента
**Проблема**: Некоторые поля настроек контента (about_text, support_text, terms_url, privacy_url, support_user) не сохранялись в веб-интерфейсе.

**Решения**:

1. **Изменена логика сохранения настроек** в `src/shop_bot/webhook_server/app.py`:
   - Убрано условие `elif key in request.form`
   - Теперь все поля обновляются всегда, даже если они пустые

2. **Исправлена функция update_setting** в `src/shop_bot/data_manager/database.py`:
   - Заменен `UPDATE` на `INSERT OR REPLACE`, чтобы гарантировать создание записи, если её нет

3. **Добавлены недостающие настройки** в `ALL_SETTINGS_KEYS`:
   - Добавлены `referral_percentage` и `referral_discount`

4. **Добавлено логирование** для отладки процесса сохранения настроек

## Тестирование

После применения этих исправлений рекомендуется:

1. Пересобрать контейнер:
```bash
docker-compose build --no-cache
docker-compose up -d
```

2. Перезагрузить nginx:
```bash
sudo nginx -t && sudo systemctl reload nginx
```

3. Проверить сохранение всех настроек в веб-интерфейсе, особенно:
   - Текст "О проекте"
   - Текст в разделе "Поддержка"  
   - URL "Условия использования"
   - URL "Политика конфиденциальности"
   - URL поддержки

## Дополнительные улучшения

- Добавлено подробное логирование процесса сохранения настроек для упрощения отладки
- Улучшена обработка прокси-заголовков для корректной работы за reverse proxy 
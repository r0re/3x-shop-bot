import os
import logging
import asyncio
import json
import hashlib
import base64
import shutil
import psutil
from hmac import compare_digest
from datetime import datetime
from functools import wraps
from math import ceil
from flask import Flask, request, render_template, redirect, url_for, flash, session, current_app
from werkzeug.middleware.proxy_fix import ProxyFix

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from shop_bot.modules import xui_api
from shop_bot.bot import handlers 
from shop_bot.data_manager.database import (
    get_all_settings, update_setting, get_all_hosts, get_plans_for_host,
    create_host, delete_host, create_plan, delete_plan, get_user_count,
    get_total_keys_count, get_total_spent_sum, get_daily_stats_for_charts,
    get_recent_transactions, get_paginated_transactions, get_all_users, get_user_keys,
    ban_user, unban_user, delete_user_keys, get_setting, find_and_complete_ton_transaction,
    export_all_users, import_users_from_data, extend_user_key_time, extend_user_all_keys_time,
    extend_all_users_keys_time
)

_bot_controller = None

ALL_SETTINGS_KEYS = [
    "panel_login", "panel_password", "about_text", "terms_url", "privacy_url",
    "support_user", "support_text", "channel_url", "telegram_bot_token",
    "telegram_bot_username", "admin_telegram_id", "yookassa_shop_id",
    "yookassa_secret_key", "sbp_enabled", "receipt_email", "cryptobot_token",
    "heleket_merchant_id", "heleket_api_key", "domain", "referral_percentage", 
    "referral_discount", "flask_secret_key", "ton_wallet_address", "tonapi_key", "force_subscription"
]

def create_webhook_app(bot_controller_instance):
    global _bot_controller
    _bot_controller = bot_controller_instance

    app_file_path = os.path.abspath(__file__)
    app_dir = os.path.dirname(app_file_path)
    template_dir = os.path.join(app_dir, 'templates')
    template_file = os.path.join(template_dir, 'login.html')

    print("--- DIAGNOSTIC INFORMATION ---", flush=True)
    print(f"Current Working Directory: {os.getcwd()}", flush=True)
    print(f"Path of running app.py: {app_file_path}", flush=True)
    print(f"Directory of running app.py: {app_dir}", flush=True)
    print(f"Expected templates directory: {template_dir}", flush=True)
    print(f"Expected login.html path: {template_file}", flush=True)
    print(f"Does template directory exist? -> {os.path.isdir(template_dir)}", flush=True)
    print(f"Does login.html file exist? -> {os.path.isfile(template_file)}", flush=True)
    print("--- END DIAGNOSTIC INFORMATION ---", flush=True)
    
    flask_app = Flask(
        __name__,
        template_folder='templates',
        static_folder='static'
    )
    
    # Получаем SECRET_KEY из настроек базы данных
    secret_key = get_setting('flask_secret_key')
    if not secret_key:
        # Генерируем новый ключ, если его нет
        import secrets
        secret_key = secrets.token_hex(32)
        update_setting('flask_secret_key', secret_key)
        logger.info("Generated new Flask SECRET_KEY")
    
    flask_app.config['SECRET_KEY'] = secret_key
    flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    @flask_app.context_processor
    def inject_current_year():
        return {'current_year': datetime.utcnow().year}

    def login_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'logged_in' not in session:
                return redirect(url_for('login_page'))
            return f(*args, **kwargs)
        return decorated_function

    @flask_app.route('/login', methods=['GET', 'POST'])
    def login_page():
        settings = get_all_settings()
        if request.method == 'POST':
            if request.form.get('username') == settings.get("panel_login") and \
               request.form.get('password') == settings.get("panel_password"):
                session['logged_in'] = True
                return redirect(url_for('dashboard_page'))
            else:
                flash('Неверный логин или пароль', 'danger')
        return render_template('login.html')

    @flask_app.route('/logout', methods=['POST'])
    @login_required
    def logout_page():
        session.pop('logged_in', None)
        flash('Вы успешно вышли.', 'success')
        return redirect(url_for('login_page'))

    def get_system_resources():
        """Получает информацию о системных ресурсах"""
        try:
            # Память
            memory = psutil.virtual_memory()
            memory_used_percent = memory.percent
            memory_total = memory.total / (1024 * 1024 * 1024)  # В ГБ
            memory_used = memory.used / (1024 * 1024 * 1024)    # В ГБ
            
            # Диск
            disk = shutil.disk_usage('/')
            disk_total = disk.total / (1024 * 1024 * 1024)      # В ГБ
            disk_used = disk.used / (1024 * 1024 * 1024)        # В ГБ
            disk_used_percent = (disk.used / disk.total) * 100
            
            return {
                "memory_used_percent": round(memory_used_percent, 1),
                "memory_total": round(memory_total, 1),
                "memory_used": round(memory_used, 1),
                "disk_used_percent": round(disk_used_percent, 1),
                "disk_total": round(disk_total, 1),
                "disk_used": round(disk_used, 1)
            }
        except Exception as e:
            logger.error(f"Error getting system resources: {e}")
            return {
                "memory_used_percent": 0,
                "memory_total": 0,
                "memory_used": 0,
                "disk_used_percent": 0,
                "disk_total": 0,
                "disk_used": 0
            }

    def get_common_template_data():
        bot_status = _bot_controller.get_status()
        settings = get_all_settings()
        required_for_start = ['telegram_bot_token', 'telegram_bot_username', 'admin_telegram_id']
        all_settings_ok = all(settings.get(key) for key in required_for_start)
        return {"bot_status": bot_status, "all_settings_ok": all_settings_ok}

    @flask_app.route('/')
    @login_required
    def index():
        return redirect(url_for('dashboard_page'))

    @flask_app.route('/dashboard')
    @login_required
    def dashboard_page():
        stats = {
            "user_count": get_user_count(),
            "total_keys": get_total_keys_count(),
            "total_spent": get_total_spent_sum(),
            "host_count": len(get_all_hosts())
        }
        
        # Получаем информацию о системных ресурсах
        system_resources = get_system_resources()
        
        page = request.args.get('page', 1, type=int)
        per_page = 8
        
        transactions, total_transactions = get_paginated_transactions(page=page, per_page=per_page)
        total_pages = ceil(total_transactions / per_page)
        
        chart_data = get_daily_stats_for_charts(days=30)
        common_data = get_common_template_data()
        
        return render_template(
            'dashboard.html',
            stats=stats,
            system_resources=system_resources,
            chart_data=chart_data,
            transactions=transactions,
            current_page=page,
            total_pages=total_pages,
            **common_data
        )

    @flask_app.route('/users')
    @login_required
    def users_page():
        users = get_all_users()
        for user in users:
            user['user_keys'] = get_user_keys(user['telegram_id'])
        
        common_data = get_common_template_data()
        return render_template('users.html', users=users, **common_data)

    @flask_app.route('/settings', methods=['GET', 'POST'])
    @login_required
    def settings_page():
        if request.method == 'POST':
            # Логируем только безопасные поля формы (исключаем пароли и ключи)
            safe_form_data = {}
            sensitive_fields = {'panel_password', 'yookassa_secret_key', 'cryptobot_token', 'heleket_api_key', 'flask_secret_key'}
            
            for key, value in request.form.items():
                if key in sensitive_fields:
                    safe_form_data[key] = '***HIDDEN***' if value else ''
                else:
                    safe_form_data[key] = value
            
            logger.info(f"Settings form submitted with fields: {list(safe_form_data.keys())}")
            
            if 'panel_password' in request.form and request.form.get('panel_password'):
                update_setting('panel_password', request.form.get('panel_password'))
            
            for key in ALL_SETTINGS_KEYS:
                if key == 'panel_password': continue

                if key in ['sbp_enabled', 'force_subscription']:
                    value = 'true' if key in request.form else 'false'
                    update_setting(key, value)
                else:
                    # Всегда обновляем значение, даже если оно пустое
                    value = request.form.get(key, '')
                    # Логируем только факт обновления, но не значения чувствительных полей
                    sensitive_fields = {'panel_password', 'yookassa_secret_key', 'cryptobot_token', 'heleket_api_key', 'flask_secret_key'}
                    if key in sensitive_fields:
                        logger.info(f"Updated setting: {key}")
                    else:
                        logger.info(f"Updated setting {key}: '{value}'")
                    update_setting(key, value)

            flash('Настройки успешно сохранены!', 'success')
            return redirect(url_for('settings_page'))

        current_settings = get_all_settings()
        hosts = get_all_hosts()
        for host in hosts:
            host['plans'] = get_plans_for_host(host['host_name'])
        
        common_data = get_common_template_data()
        return render_template('settings.html', settings=current_settings, hosts=hosts, **common_data)

    @flask_app.route('/start-bot', methods=['POST'])
    @login_required
    def start_bot_route():
        result = _bot_controller.start()
        flash(result['message'], 'success' if result['status'] == 'success' else 'danger')
        return redirect(request.referrer or url_for('dashboard_page'))

    @flask_app.route('/stop-bot', methods=['POST'])
    @login_required
    def stop_bot_route():
        result = _bot_controller.stop()
        flash(result['message'], 'success' if result['status'] == 'success' else 'danger')
        return redirect(request.referrer or url_for('dashboard_page'))

    @flask_app.route('/users/ban/<int:user_id>', methods=['POST'])
    @login_required
    def ban_user_route(user_id):
        ban_user(user_id)
        flash(f'Пользователь {user_id} был заблокирован.', 'success')
        return redirect(url_for('users_page'))

    @flask_app.route('/users/unban/<int:user_id>', methods=['POST'])
    @login_required
    def unban_user_route(user_id):
        unban_user(user_id)
        flash(f'Пользователь {user_id} был разблокирован.', 'success')
        return redirect(url_for('users_page'))

    @flask_app.route('/users/revoke/<int:user_id>', methods=['POST'])
    @login_required
    def revoke_keys_route(user_id):
        keys_to_revoke = get_user_keys(user_id)
        success_count = 0
        
        for key in keys_to_revoke:
            result = asyncio.run(xui_api.delete_client_on_host(key['host_name'], key['key_email']))
            if result:
                success_count += 1
        
        delete_user_keys(user_id)
        
        if success_count == len(keys_to_revoke):
            flash(f"Все {len(keys_to_revoke)} ключей для пользователя {user_id} были успешно отозваны.", 'success')
        else:
            flash(f"Удалось отозвать {success_count} из {len(keys_to_revoke)} ключей для пользователя {user_id}. Проверьте логи.", 'warning')

        return redirect(url_for('users_page'))

    @flask_app.route('/add-host', methods=['POST'])
    @login_required
    def add_host_route():
        create_host(
            name=request.form['host_name'],
            url=request.form['host_url'],
            user=request.form['host_username'],
            passwd=request.form['host_pass'],
            inbound=int(request.form['host_inbound_id'])
        )
        flash(f"Хост '{request.form['host_name']}' успешно добавлен.", 'success')
        return redirect(url_for('settings_page'))

    @flask_app.route('/delete-host/<host_name>', methods=['POST'])
    @login_required
    def delete_host_route(host_name):
        delete_host(host_name)
        flash(f"Хост '{host_name}' и все его тарифы были удалены.", 'success')
        return redirect(url_for('settings_page'))

    @flask_app.route('/add-plan', methods=['POST'])
    @login_required
    def add_plan_route():
        create_plan(
            host_name=request.form['host_name'],
            plan_name=request.form['plan_name'],
            months=int(request.form['months']),
            price=float(request.form['price'])
        )
        flash(f"Новый тариф для хоста '{request.form['host_name']}' добавлен.", 'success')
        return redirect(url_for('settings_page'))

    @flask_app.route('/delete-plan/<int:plan_id>', methods=['POST'])
    @login_required
    def delete_plan_route(plan_id):
        delete_plan(plan_id)
        flash("Тариф успешно удален.", 'success')
        return redirect(url_for('settings_page'))

    def validate_yookassa_signature(data: bytes, signature: str, secret_key: str) -> bool:
        """Проверяет подпись YooKassa webhook"""
        try:
            import hmac
            expected_signature = base64.b64encode(
                hmac.new(secret_key.encode(), data, hashlib.sha256).digest()
            ).decode()
            return compare_digest(expected_signature, signature)
        except Exception as e:
            logger.error(f"Error validating YooKassa signature: {e}")
            return False

    @flask_app.route('/yookassa-webhook', methods=['POST'])
    def yookassa_webhook_handler():
        try:
            # Получаем секретный ключ YooKassa
            yookassa_secret = get_setting("yookassa_secret_key")
            if not yookassa_secret:
                logger.error("YooKassa webhook: Secret key not configured")
                return 'Forbidden', 403
            
            # Проверяем подпись
            signature = request.headers.get('Authorization')
            if not signature:
                logger.warning("YooKassa webhook: Missing Authorization header")
                return 'Forbidden', 403
                
            # Убираем префикс "Bearer " если есть
            if signature.startswith('Bearer '):
                signature = signature[7:]
            
            raw_data = request.get_data()
            if not validate_yookassa_signature(raw_data, signature, yookassa_secret):
                logger.warning("YooKassa webhook: Invalid signature")
                return 'Forbidden', 403
            
            event_json = request.json
            if event_json.get("event") == "payment.succeeded":
                metadata = event_json.get("object", {}).get("metadata", {})
                
                bot = _bot_controller.get_bot_instance()
                payment_processor = handlers.process_successful_payment

                if metadata and bot is not None and payment_processor is not None:
                    loop = current_app.config.get('EVENT_LOOP')
                    if loop and loop.is_running():
                        asyncio.run_coroutine_threadsafe(payment_processor(bot, metadata), loop)
                    else:
                        logger.error("YooKassa webhook: Event loop is not available!")
            return 'OK', 200
        except Exception as e:
            logger.error(f"Error in yookassa webhook handler: {e}", exc_info=True)
            return 'Error', 500
        
    @flask_app.route('/cryptobot-webhook', methods=['POST'])
    def cryptobot_webhook_handler():
        try:
            request_data = request.json
            # Логируем только основную информацию без чувствительных данных
            if request_data:
                logger.info(f"Received CryptoBot webhook, update_type: {request_data.get('update_type')}")
            
            if request_data and request_data.get('update_type') == 'invoice_paid':
                payload_data = request_data.get('payload', {})
                
                payload_string = payload_data.get('payload')
                
                if not payload_string:
                    logger.warning("CryptoBot Webhook: Received paid invoice but payload was empty.")
                    return 'OK', 200

                parts = payload_string.split(':')
                if len(parts) < 9:
                    logger.error(f"cryptobot Webhook: Invalid payload format received: {payload_string}")
                    return 'Error', 400

                metadata = {
                    "user_id": parts[0],
                    "months": parts[1],
                    "price": parts[2],
                    "action": parts[3],
                    "key_id": parts[4],
                    "host_name": parts[5],
                    "plan_id": parts[6],
                    "customer_email": parts[7] if parts[7] != 'None' else None,
                    "payment_method": parts[8]
                }
                
                bot = _bot_controller.get_bot_instance()
                loop = current_app.config.get('EVENT_LOOP')
                payment_processor = handlers.process_successful_payment

                if bot and loop and loop.is_running():
                    asyncio.run_coroutine_threadsafe(payment_processor(bot, metadata), loop)
                else:
                    logger.error("cryptobot Webhook: Could not process payment because bot or event loop is not running.")

            return 'OK', 200
            
        except Exception as e:
            logger.error(f"Error in cryptobot webhook handler: {e}", exc_info=True)
            return 'Error', 500
        
    @flask_app.route('/heleket-webhook', methods=['POST'])
    def heleket_webhook_handler():
        try:
            data = request.json
            # Логируем только статус и основную информацию
            if data:
                logger.info(f"Received Heleket webhook, status: {data.get('status')}, amount: {data.get('amount')}")

            api_key = get_setting("heleket_api_key")
            if not api_key: return 'Error', 500

            sign = data.pop("sign", None)
            if not sign: return 'Error', 400
                
            sorted_data_str = json.dumps(data, sort_keys=True, separators=(",", ":"))
            
            base64_encoded = base64.b64encode(sorted_data_str.encode()).decode()
            raw_string = f"{base64_encoded}{api_key}"
            expected_sign = hashlib.md5(raw_string.encode()).hexdigest()

            if not compare_digest(expected_sign, sign):
                logger.warning("Heleket webhook: Invalid signature.")
                return 'Forbidden', 403

            if data.get('status') in ["paid", "paid_over"]:
                metadata_str = data.get('description')
                if not metadata_str: return 'Error', 400
                
                metadata = json.loads(metadata_str)
                
                bot = _bot_controller.get_bot_instance()
                loop = current_app.config.get('EVENT_LOOP')
                payment_processor = handlers.process_successful_payment

                if bot and loop and loop.is_running():
                    asyncio.run_coroutine_threadsafe(payment_processor(bot, metadata), loop)
            
            return 'OK', 200
        except Exception as e:
            logger.error(f"Error in heleket webhook handler: {e}", exc_info=True)
            return 'Error', 500
        
    @flask_app.route('/ton-webhook', methods=['POST'])
    def ton_webhook_handler():
        try:
            data = request.json
            logger.info(f"Received TonAPI webhook: {data}")

            if 'tx_id' in data:
                account_id = data.get('account_id')
                for tx in data.get('in_progress_txs', []) + data.get('txs', []):
                    in_msg = tx.get('in_msg')
                    if in_msg and in_msg.get('decoded_comment'):
                        payment_id = in_msg['decoded_comment']
                        amount_nano = int(in_msg.get('value', 0))
                        amount_ton = float(amount_nano / 1_000_000_000)

                        metadata = find_and_complete_ton_transaction(payment_id, amount_ton)
                        
                        if metadata:
                            logger.info(f"TON Payment successful for payment_id: {payment_id}")
                            bot = _bot_controller.get_bot_instance()
                            loop = current_app.config.get('EVENT_LOOP')
                            payment_processor = handlers.process_successful_payment

                            if bot and loop and loop.is_running():
                                asyncio.run_coroutine_threadsafe(payment_processor(bot, metadata), loop)
            
            return 'OK', 200
        except Exception as e:
            logger.error(f"Error in ton webhook handler: {e}", exc_info=True)
            return 'Error', 500

    @flask_app.route('/export-users')
    @login_required
    def export_users():
        """Экспорт всех пользователей в JSON файл"""
        try:
            export_data = export_all_users()
            
            # Создаем имя файла с датой
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"users_export_{timestamp}.json"
            
            # Создаем JSON response для скачивания
            response = flask_app.response_class(
                response=json.dumps(export_data, indent=2, ensure_ascii=False),
                status=200,
                mimetype='application/json'
            )
            response.headers['Content-Disposition'] = f'attachment; filename={filename}'
            
            logger.info(f"Users export completed: {export_data['total_users']} users")
            return response
            
        except Exception as e:
            logger.error(f"Export failed: {e}", exc_info=True)
            flash(f'Ошибка при экспорте: {str(e)}', 'danger')
            return redirect(url_for('users_page'))

    @flask_app.route('/import-users', methods=['POST'])
    @login_required
    def import_users():
        """Импорт пользователей из JSON файла"""
        try:
            if 'import_file' not in request.files:
                flash('Файл не выбран', 'danger')
                return redirect(url_for('users_page'))
            
            file = request.files['import_file']
            if file.filename == '':
                flash('Файл не выбран', 'danger')
                return redirect(url_for('users_page'))
            
            if not file.filename.endswith('.json'):
                flash('Можно загружать только JSON файлы', 'danger')
                return redirect(url_for('users_page'))
            
            # Читаем содержимое файла
            try:
                import_data = json.loads(file.read().decode('utf-8'))
            except json.JSONDecodeError as e:
                flash(f'Ошибка чтения JSON файла: {str(e)}', 'danger')
                return redirect(url_for('users_page'))
            
            # Проверяем наличие параметра перезаписи
            overwrite = request.form.get('overwrite_existing', 'off') == 'on'
            
            # Выполняем импорт
            results = import_users_from_data(import_data, overwrite_existing=overwrite)
            
            # Формируем сообщение о результатах
            success_msg = []
            if results['imported'] > 0:
                success_msg.append(f"Импортировано новых пользователей: {results['imported']}")
            if results['updated'] > 0:
                success_msg.append(f"Обновлено существующих: {results['updated']}")
            if results['skipped'] > 0:
                success_msg.append(f"Пропущено: {results['skipped']}")
            if results['keys_imported'] > 0:
                success_msg.append(f"Импортировано ключей: {results['keys_imported']}")
            if results['transactions_imported'] > 0:
                success_msg.append(f"Импортировано транзакций: {results['transactions_imported']}")
            
            if success_msg:
                flash(' | '.join(success_msg), 'success')
            
            # Показываем ошибки если есть
            if results['errors']:
                error_msg = f"Ошибки при импорте ({len(results['errors'])}): " + '; '.join(results['errors'][:3])
                if len(results['errors']) > 3:
                    error_msg += f" и еще {len(results['errors']) - 3}..."
                flash(error_msg, 'warning')
            
            logger.info(f"Import completed: {results}")
            return redirect(url_for('users_page'))
            
        except Exception as e:
            logger.error(f"Import failed: {e}", exc_info=True)
            flash(f'Ошибка при импорте: {str(e)}', 'danger')
            return redirect(url_for('users_page'))

    @flask_app.route('/extend-user-key-time', methods=['POST'])
    @login_required
    def extend_user_key_time_route():
        """Продление времени конкретного ключа пользователя"""
        try:
            key_id = request.form.get('key_id', type=int)
            days_to_add = request.form.get('days_to_add', type=int)
            
            if not key_id or days_to_add is None:
                return {'success': False, 'message': 'Неверные параметры'}, 400
            
            # Проверяем разумные ограничения
            if abs(days_to_add) > 3650:  # Не больше 10 лет
                return {'success': False, 'message': 'Слишком большое количество дней'}, 400
            
            # Выполняем операцию
            import asyncio
            result = asyncio.run(extend_user_key_time(key_id, days_to_add))
            
            status_code = 200 if result['success'] else 400
            return result, status_code
            
        except Exception as e:
            logger.error(f"Error extending user key time: {e}", exc_info=True)
            return {'success': False, 'message': f'Ошибка: {str(e)}'}, 500

    @flask_app.route('/extend-user-all-keys-time', methods=['POST'])
    @login_required
    def extend_user_all_keys_time_route():
        """Продление времени всех ключей пользователя"""
        try:
            user_id = request.form.get('user_id', type=int)
            days_to_add = request.form.get('days_to_add', type=int)
            
            if not user_id or days_to_add is None:
                return {'success': False, 'message': 'Неверные параметры'}, 400
            
            if abs(days_to_add) > 3650:
                return {'success': False, 'message': 'Слишком большое количество дней'}, 400
            
            import asyncio
            result = asyncio.run(extend_user_all_keys_time(user_id, days_to_add))
            
            status_code = 200 if result['success'] else 400
            return result, status_code
            
        except Exception as e:
            logger.error(f"Error extending user all keys time: {e}", exc_info=True)
            return {'success': False, 'message': f'Ошибка: {str(e)}'}, 500

    @flask_app.route('/extend-all-users-keys-time', methods=['POST'])
    @login_required
    def extend_all_users_keys_time_route():
        """Массовое продление времени всех ключей всех пользователей"""
        try:
            days_to_add = request.form.get('days_to_add', type=int)
            
            if days_to_add is None:
                flash('Неверные параметры', 'danger')
                return redirect(url_for('users_page'))
            
            if abs(days_to_add) > 365:  # Ограничиваем массовые операции годом
                flash('Для массовых операций максимум 365 дней', 'danger')
                return redirect(url_for('users_page'))
            
            # Получаем имя админа из сессии
            admin_user = get_all_settings().get('panel_login', 'admin')
            
            import asyncio
            result = asyncio.run(extend_all_users_keys_time(days_to_add, admin_user))
            
            if result['success']:
                flash(result['message'], 'success')
                
                # Показываем детали если не слишком много
                if len(result['details']) <= 10:
                    details_msg = '<br>'.join(result['details'])
                    flash(f'Детали:<br>{details_msg}', 'info')
                else:
                    flash(f'Обработано {len(result["details"])} пользователей. Подробности в логах.', 'info')
            else:
                flash(result['message'], 'danger')
                if result['details']:
                    error_details = '<br>'.join(result['details'][:5])
                    flash(f'Первые ошибки:<br>{error_details}', 'warning')
            
            return redirect(url_for('users_page'))
            
        except Exception as e:
            logger.error(f"Error extending all users keys time: {e}", exc_info=True)
            flash(f'Ошибка при массовом обновлении: {str(e)}', 'danger')
            return redirect(url_for('users_page'))

    @flask_app.route('/get-user-keys-info/<int:user_id>')
    @login_required
    def get_user_keys_info(user_id):
        """Получение информации о ключах пользователя для модального окна"""
        try:
            from shop_bot.data_manager.database import get_user_keys_with_remaining_time
            
            keys = get_user_keys_with_remaining_time(user_id)
            return {'success': True, 'keys': keys}
            
        except Exception as e:
            logger.error(f"Error getting user keys info: {e}", exc_info=True)
            return {'success': False, 'message': f'Ошибка: {str(e)}'}, 500

    return flask_app
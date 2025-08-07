import sqlite3
from datetime import datetime
import logging
from pathlib import Path
import json

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path("/app/project")
DB_FILE = PROJECT_ROOT / "users.db"

def initialize_db():
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY, username TEXT, total_spent REAL DEFAULT 0,
                    total_months INTEGER DEFAULT 0, trial_used BOOLEAN DEFAULT 0,
                    agreed_to_terms BOOLEAN DEFAULT 0,
                    registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_banned BOOLEAN DEFAULT 0,
                    referred_by INTEGER,
                    referral_balance REAL DEFAULT 0
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS vpn_keys (
                    key_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    host_name TEXT NOT NULL,
                    xui_client_uuid TEXT NOT NULL,
                    key_email TEXT NOT NULL UNIQUE,
                    expiry_date TIMESTAMP,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
                    transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payment_id TEXT UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    amount_rub REAL NOT NULL,
                    amount_currency REAL,
                    currency_name TEXT,
                    payment_method TEXT,
                    metadata TEXT,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bot_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS xui_hosts(
                    host_name TEXT NOT NULL,
                    host_url TEXT NOT NULL,
                    host_username TEXT NOT NULL,
                    host_pass TEXT NOT NULL,
                    host_inbound_id INTEGER NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS plans (
                    plan_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    host_name TEXT NOT NULL,
                    plan_name TEXT NOT NULL,
                    months INTEGER NOT NULL,
                    price REAL NOT NULL,
                    FOREIGN KEY (host_name) REFERENCES xui_hosts (host_name)
                )
            ''')            
            import secrets
            import string
            
            # Генерируем случайные учетные данные для администратора
            def generate_random_string(length=12):
                chars = string.ascii_letters + string.digits
                return ''.join(secrets.choice(chars) for _ in range(length))
            
            admin_login = f"admin_{generate_random_string(8)}"
            admin_password = generate_random_string(16)
            flask_secret = secrets.token_hex(32)
            
            # Сохраняем учетные данные в файл для вывода после установки (только для новых установок)
            credentials_file = PROJECT_ROOT / "admin_credentials.txt"
            if not credentials_file.exists():  # Создаем файл только если его еще нет
                try:
                    with open(credentials_file, 'w') as f:
                        f.write(f"ADMIN_LOGIN={admin_login}\n")
                        f.write(f"ADMIN_PASSWORD={admin_password}\n")
                        f.write(f"FLASK_SECRET_KEY={flask_secret}\n")
                    logging.info("Admin credentials file created.")
                except Exception as e:
                    logging.error(f"Failed to create credentials file: {e}")
            
            default_settings = {
                "panel_login": admin_login,
                "panel_password": admin_password,
                "flask_secret_key": flask_secret,
                "about_text": None,
                "terms_url": None,
                "privacy_url": None,
                "support_user": None,
                "support_text": None,
                "channel_url": None,
                "force_subscription": "true",
                "receipt_email": "example@example.com",
                "telegram_bot_token": None,
                "telegram_bot_username": None,
                "referral_percentage": "10",
                "referral_discount": "5",
                "admin_telegram_id": None,
                "yookassa_shop_id": None,
                "yookassa_secret_key": None,
                "sbp_enabled": "false",
                "cryptobot_token": None,
                "heleket_merchant_id": None,
                "heleket_api_key": None,
                "domain": None,
                "ton_wallet_address": None,
                "tonapi_key": None,
            }
            _run_migrations(conn)
            
            # Проверяем, нужно ли инициализировать настройки
            cursor.execute("SELECT COUNT(*) FROM bot_settings WHERE key = 'panel_login'")
            login_exists = cursor.fetchone()[0] > 0
            
            if not login_exists:
                # База новая, вставляем все настройки включая случайные учетные данные
                for key, value in default_settings.items():
                    cursor.execute("INSERT OR IGNORE INTO bot_settings (key, value) VALUES (?, ?)", (key, value))
                logging.info("Database initialized with secure random credentials.")
            else:
                # База существует, вставляем только отсутствующие настройки (кроме учетных данных)
                for key, value in default_settings.items():
                    if key not in ['panel_login', 'panel_password']:  # Не перезаписываем существующие учетные данные
                        cursor.execute("INSERT OR IGNORE INTO bot_settings (key, value) VALUES (?, ?)", (key, value))
                logging.info("Database updated with missing settings.")
            
            conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Database error on initialization: {e}")

def run_migration():
    if not DB_FILE.exists():
        logging.error("Файл базы данных users.db не найден. Нечего мигрировать.")
        return

    logging.info(f"Начинаю миграцию базы данных: {DB_FILE}")

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        logging.info("The migration of the table 'users' ...")
        
        cursor.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'referred_by' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN referred_by INTEGER")
            logging.info("-> The column 'referred_by' is successfully added.")
        else:
            logging.info("-> The column 'referred_by' already exists.")
            
        if 'referral_balance' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN referral_balance REAL DEFAULT 0")
            logging.info("-> The column 'referred_by' already exists.")
        else:
            logging.info("-> The column 'referred_by' already exists.")
        
        logging.info("-> The column 'referred_by' already exists.")


        logging.info("The migration of the table 'Transactions' ...")

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'")
        table_exists = cursor.fetchone()

        if table_exists:
            cursor.execute("PRAGMA table_info(transactions)")
            trans_columns = [row[1] for row in cursor.fetchall()]
            
            if 'payment_id' in trans_columns and 'status' in trans_columns:
                logging.info("The 'Transactions' table already has a new structure. Migration is not required.")
            else:
                backup_name = f"transactions_backup_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                logging.warning(f"The old structure of the TRANSACTIONS table was discovered. I rename in '{backup_name}' ...")
                cursor.execute(f"ALTER TABLE transactions RENAME TO {backup_name}")
                
                logging.info("I create a new table 'Transactions' with the correct structure ...")
                create_new_transactions_table(cursor)
                logging.info("The new table 'Transactions' has been successfully created. The old data is saved.")
        else:
            logging.info("TRANSACTIONS table was not found. I create a new one ...")
            create_new_transactions_table(cursor)
            logging.info("The new table 'Transactions' has been successfully created.")

        conn.commit()
        conn.close()
        
        logging.info("--- The database is successfully completed! ---")

    except sqlite3.Error as e:
        logging.error(f"An error occurred during migration: {e}")

def create_new_transactions_table(cursor: sqlite3.Cursor):
    cursor.execute('''
        CREATE TABLE transactions (
            transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            payment_id TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            amount_rub REAL NOT NULL,
            amount_currency REAL,
            currency_name TEXT,
            payment_method TEXT,
            metadata TEXT,
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

def create_host(name: str, url: str, user: str, passwd: str, inbound: int):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO xui_hosts (host_name, host_url, host_username, host_pass, host_inbound_id) VALUES (?, ?, ?, ?, ?)",
                (name, url, user, passwd, inbound)
            )
            conn.commit()
            logging.info(f"Successfully created a new host: {name}")
    except sqlite3.Error as e:
        logging.error(f"Error creating host '{name}': {e}")

def delete_host(host_name: str):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM plans WHERE host_name = ?", (host_name,))
            cursor.execute("DELETE FROM xui_hosts WHERE host_name = ?", (host_name,))
            conn.commit()
            logging.info(f"Successfully deleted host '{host_name}' and its plans.")
    except sqlite3.Error as e:
        logging.error(f"Error deleting host '{host_name}': {e}")

def get_host(host_name: str) -> dict | None:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM xui_hosts WHERE host_name = ?", (host_name,))
            result = cursor.fetchone()
            return dict(result) if result else None
    except sqlite3.Error as e:
        logging.error(f"Error getting host '{host_name}': {e}")
        return None

def get_all_hosts() -> list[dict]:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM xui_hosts")
            hosts = cursor.fetchall()
            return [dict(row) for row in hosts]
    except sqlite3.Error as e:
        logging.error(f"Error getting list of all hosts: {e}")
        return []

def get_setting(key: str) -> str | None:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM bot_settings WHERE key = ?", (key,))
            result = cursor.fetchone()
            return result[0] if result else None
    except sqlite3.Error as e:
        logging.error(f"Failed to get setting '{key}': {e}")
        return None
        
def get_all_settings() -> dict:
    settings = {}
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM bot_settings")
            rows = cursor.fetchall()
            for row in rows:
                settings[row['key']] = row['value']
    except sqlite3.Error as e:
        logging.error(f"Failed to get all settings: {e}")
    return settings

def update_setting(key: str, value: str):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)", (key, value))
            conn.commit()
            logging.info(f"Setting '{key}' updated.")
    except sqlite3.Error as e:
        logging.error(f"Failed to update setting '{key}': {e}")

def create_plan(host_name: str, plan_name: str, months: int, price: float):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO plans (host_name, plan_name, months, price) VALUES (?, ?, ?, ?)",
                (host_name, plan_name, months, price)
            )
            conn.commit()
            logging.info(f"Created new plan '{plan_name}' for host '{host_name}'.")
    except sqlite3.Error as e:
        logging.error(f"Failed to create plan for host '{host_name}': {e}")

def get_plans_for_host(host_name: str) -> list[dict]:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM plans WHERE host_name = ? ORDER BY months", (host_name,))
            plans = cursor.fetchall()
            return [dict(plan) for plan in plans]
    except sqlite3.Error as e:
        logging.error(f"Failed to get plans for host '{host_name}': {e}")
        return []

def get_plan_by_id(plan_id: int) -> dict | None:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM plans WHERE plan_id = ?", (plan_id,))
            plan = cursor.fetchone()
            return dict(plan) if plan else None
    except sqlite3.Error as e:
        logging.error(f"Failed to get plan by id '{plan_id}': {e}")
        return None

def delete_plan(plan_id: int):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM plans WHERE plan_id = ?", (plan_id,))
            conn.commit()
            logging.info(f"Deleted plan with id {plan_id}.")
    except sqlite3.Error as e:
        logging.error(f"Failed to delete plan with id {plan_id}: {e}")

def register_user_if_not_exists(telegram_id: int, username: str, referrer_id):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT telegram_id FROM users WHERE telegram_id = ?", (telegram_id,))
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO users (telegram_id, username, registration_date, referred_by) VALUES (?, ?, ?, ?)",
                    (telegram_id, username, datetime.now(), referrer_id)
                )
            else:
                cursor.execute("UPDATE users SET username = ? WHERE telegram_id = ?", (username, telegram_id))
            conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Failed to register user {telegram_id}: {e}")

def add_to_referral_balance(user_id: int, amount: float):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET referral_balance = referral_balance + ? WHERE telegram_id = ?", (amount, user_id))
            conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Failed to add to referral balance for user {user_id}: {e}")

def get_referral_count(user_id: int) -> int:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (user_id,))
            return cursor.fetchone()[0] or 0
    except sqlite3.Error as e:
        logging.error(f"Failed to get referral count for user {user_id}: {e}")
        return 0

def get_user(telegram_id: int):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
            user_data = cursor.fetchone()
            return dict(user_data) if user_data else None
    except sqlite3.Error as e:
        logging.error(f"Failed to get user {telegram_id}: {e}")
        return None

def set_terms_agreed(telegram_id: int):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET agreed_to_terms = 1 WHERE telegram_id = ?", (telegram_id,))
            conn.commit()
            logging.info(f"User {telegram_id} has agreed to terms.")
    except sqlite3.Error as e:
        logging.error(f"Failed to set terms agreed for user {telegram_id}: {e}")

def update_user_stats(telegram_id: int, amount_spent: float, months_purchased: int):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET total_spent = total_spent + ?, total_months = total_months + ? WHERE telegram_id = ?", (amount_spent, months_purchased, telegram_id))
            conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Failed to update user stats for {telegram_id}: {e}")

def get_user_count() -> int:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            return cursor.fetchone()[0] or 0
    except sqlite3.Error as e:
        logging.error(f"Failed to get user count: {e}")
        return 0

def get_total_keys_count() -> int:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM vpn_keys")
            return cursor.fetchone()[0] or 0
    except sqlite3.Error as e:
        logging.error(f"Failed to get total keys count: {e}")
        return 0

def get_total_spent_sum() -> float:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT SUM(total_spent) FROM users")
            return cursor.fetchone()[0] or 0.0
    except sqlite3.Error as e:
        logging.error(f"Failed to get total spent sum: {e}")
        return 0.0

def create_pending_transaction(payment_id: str, user_id: int, amount_rub: float, metadata: dict) -> int:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO transactions (payment_id, user_id, status, amount_rub, metadata) VALUES (?, ?, ?, ?, ?)",
                (payment_id, user_id, 'pending', amount_rub, json.dumps(metadata))
            )
            conn.commit()
            return cursor.lastrowid
    except sqlite3.Error as e:
        logging.error(f"Failed to create pending transaction: {e}")
        return 0

def find_and_complete_ton_transaction(payment_id: str, amount_ton: float) -> dict | None:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM transactions WHERE payment_id = ? AND status = 'pending'", (payment_id,))
            transaction = cursor.fetchone()
            if not transaction:
                logger.warning(f"TON Webhook: Received payment for unknown or completed payment_id: {payment_id}")
                return None
            
            
            cursor.execute(
                "UPDATE transactions SET status = 'paid', amount_currency = ?, currency_name = 'TON', payment_method = 'TON' WHERE payment_id = ?",
                (amount_ton, payment_id)
            )
            conn.commit()
            
            return json.loads(transaction['metadata'])
    except sqlite3.Error as e:
        logging.error(f"Failed to complete TON transaction {payment_id}: {e}")
        return None

def log_transaction(user_id: int, username: str, email: str, host_name: str, plan_name: str, months: int, amount: float, method: str):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO transactions
                   (user_id, username, email, host_name, plan_name, months, amount_spent, payment_method, transaction_date)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, username, email, host_name, plan_name, months, amount, method, datetime.now())
            )
            conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Failed to log transaction for user {user_id}: {e}")

def get_paginated_transactions(page: int = 1, per_page: int = 15) -> tuple[list[dict], int]:
    offset = (page - 1) * per_page
    transactions = []
    total = 0
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM transactions")
            total = cursor.fetchone()[0]

            query = "SELECT * FROM transactions ORDER BY transaction_date DESC LIMIT ? OFFSET ?"
            cursor.execute(query, (per_page, offset))
            transactions = [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logging.error(f"Failed to get paginated transactions: {e}")
    
    return transactions, total

def set_trial_used(telegram_id: int):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET trial_used = 1 WHERE telegram_id = ?", (telegram_id,))
            conn.commit()
            logging.info(f"Trial period marked as used for user {telegram_id}.")
    except sqlite3.Error as e:
        logging.error(f"Failed to set trial used for user {telegram_id}: {e}")

def add_new_key(user_id: int, host_name: str, xui_client_uuid: str, key_email: str, expiry_timestamp_ms: int):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            expiry_date = datetime.fromtimestamp(expiry_timestamp_ms / 1000)
            cursor.execute(
                "INSERT INTO vpn_keys (user_id, host_name, xui_client_uuid, key_email, expiry_date) VALUES (?, ?, ?, ?, ?)",
                (user_id, host_name, xui_client_uuid, key_email, expiry_date)
            )
            new_key_id = cursor.lastrowid
            conn.commit()
            return new_key_id
    except sqlite3.Error as e:
        logging.error(f"Failed to add new key for user {user_id}: {e}")
        return None

def get_user_keys(user_id: int):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vpn_keys WHERE user_id = ? ORDER BY key_id", (user_id,))
            keys = cursor.fetchall()
            return [dict(key) for key in keys]
    except sqlite3.Error as e:
        logging.error(f"Failed to get keys for user {user_id}: {e}")
        return []

def get_key_by_id(key_id: int):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vpn_keys WHERE key_id = ?", (key_id,))
            key_data = cursor.fetchone()
            return dict(key_data) if key_data else None
    except sqlite3.Error as e:
        logging.error(f"Failed to get key by ID {key_id}: {e}")
        return None

def update_key_info(key_id: int, new_xui_uuid: str, new_expiry_ms: int):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            expiry_date = datetime.fromtimestamp(new_expiry_ms / 1000)
            cursor.execute("UPDATE vpn_keys SET xui_client_uuid = ?, expiry_date = ? WHERE key_id = ?", (new_xui_uuid, expiry_date, key_id))
            conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Failed to update key {key_id}: {e}")

def get_next_key_number(user_id: int) -> int:
    keys = get_user_keys(user_id)
    return len(keys) + 1

def get_keys_for_host(host_name: str) -> list[dict]:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vpn_keys WHERE host_name = ?", (host_name,))
            keys = cursor.fetchall()
            return [dict(key) for key in keys]
    except sqlite3.Error as e:
        logging.error(f"Failed to get keys for host '{host_name}': {e}")
        return []

def get_all_vpn_users():
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT user_id FROM vpn_keys")
            users = cursor.fetchall()
            return [dict(user) for user in users]
    except sqlite3.Error as e:
        logging.error(f"Failed to get all vpn users: {e}")
        return []

def update_key_status_from_server(key_email: str, xui_client_data):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            if xui_client_data:
                expiry_date = datetime.fromtimestamp(xui_client_data.expiry_time / 1000)
                cursor.execute("UPDATE vpn_keys SET xui_client_uuid = ?, expiry_date = ? WHERE key_email = ?", (xui_client_data.id, expiry_date, key_email))
            else:
                cursor.execute("DELETE FROM vpn_keys WHERE key_email = ?", (key_email,))
            conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Failed to update key status for {key_email}: {e}")

def get_daily_stats_for_charts(days: int = 30) -> dict:
    stats = {'users': {}, 'keys': {}}
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            query_users = """
                SELECT date(registration_date) as day, COUNT(*)
                FROM users
                WHERE registration_date >= date('now', ?)
                GROUP BY day
                ORDER BY day;
            """
            cursor.execute(query_users, (f'-{days} days',))
            for row in cursor.fetchall():
                stats['users'][row[0]] = row[1]
            
            query_keys = """
                SELECT date(created_date) as day, COUNT(*)
                FROM vpn_keys
                WHERE created_date >= date('now', ?)
                GROUP BY day
                ORDER BY day;
            """
            cursor.execute(query_keys, (f'-{days} days',))
            for row in cursor.fetchall():
                stats['keys'][row[0]] = row[1]
    except sqlite3.Error as e:
        logging.error(f"Failed to get daily stats for charts: {e}")
    return stats


def get_recent_transactions(limit: int = 15) -> list[dict]:
    transactions = []
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            query = """
                SELECT
                    k.key_id,
                    k.host_name,
                    k.created_date,
                    u.telegram_id,
                    u.username
                FROM vpn_keys k
                JOIN users u ON k.user_id = u.telegram_id
                ORDER BY k.created_date DESC
                LIMIT ?;
            """
            cursor.execute(query, (limit,))
            transactions = [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logging.error(f"Failed to get recent transactions: {e}")
    return transactions

def get_all_users() -> list[dict]:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users ORDER BY registration_date DESC")
            return [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logging.error(f"Failed to get all users: {e}")
        return []

def ban_user(telegram_id: int):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_banned = 1 WHERE telegram_id = ?", (telegram_id,))
            conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Failed to ban user {telegram_id}: {e}")

def unban_user(telegram_id: int):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_banned = 0 WHERE telegram_id = ?", (telegram_id,))
            conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Failed to unban user {telegram_id}: {e}")

def delete_user_keys(user_id: int):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM vpn_keys WHERE user_id = ?", (user_id,))
            conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Failed to delete keys for user {user_id}: {e}")

def get_user_keys_with_remaining_time(user_id: int) -> list[dict]:
    """Получает ключи пользователя с информацией об оставшемся времени"""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT key_id, host_name, xui_client_uuid, key_email, 
                       expiry_date, created_date
                FROM vpn_keys 
                WHERE user_id = ? 
                ORDER BY key_id
            """, (user_id,))
            
            keys = []
            for row in cursor.fetchall():
                key_data = dict(row)
                
                # Вычисляем оставшееся время
                if key_data['expiry_date']:
                    try:
                        expiry = datetime.fromisoformat(key_data['expiry_date'].replace('Z', '+00:00'))
                        now = datetime.utcnow()
                        remaining_days = max(0, (expiry - now).days)
                        key_data['remaining_days'] = remaining_days
                    except:
                        key_data['remaining_days'] = 0
                else:
                    key_data['remaining_days'] = 0
                
                keys.append(key_data)
            
            return keys
    except sqlite3.Error as e:
        logging.error(f"Failed to get keys with remaining time for user {user_id}: {e}")
        return []

def get_user_transactions(user_id: int) -> list[dict]:
    """Получает транзакции пользователя"""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT transaction_id, username, email, host_name, plan_name,
                       months, amount_spent, payment_method, transaction_date
                FROM transactions 
                WHERE user_id = ? 
                ORDER BY transaction_date DESC
            """, (user_id,))
            
            return [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logging.error(f"Failed to get transactions for user {user_id}: {e}")
        return []

def export_all_users() -> dict:
    """Экспортирует всех пользователей с их данными в JSON формат"""
    try:
        users = get_all_users()
        export_data = {
            "export_date": datetime.utcnow().isoformat() + "Z",
            "version": "1.0",
            "total_users": len(users),
            "users": []
        }
        
        for user in users:
            user_data = dict(user)
            user_data['keys'] = get_user_keys_with_remaining_time(user['telegram_id'])
            user_data['transactions'] = get_user_transactions(user['telegram_id'])
            export_data['users'].append(user_data)
        
        logging.info(f"Successfully exported {len(users)} users")
        return export_data
        
    except Exception as e:
        logging.error(f"Failed to export users: {e}")
        raise

def import_users_from_data(import_data: dict, overwrite_existing: bool = True) -> dict:
    """Импортирует пользователей из JSON данных"""
    results = {
        "imported": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
        "keys_imported": 0,
        "transactions_imported": 0
    }
    
    if not import_data.get('users'):
        results['errors'].append("No users data found in import file")
        return results
    
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            
            for user_data in import_data['users']:
                try:
                    telegram_id = user_data.get('telegram_id')
                    if not telegram_id:
                        results['errors'].append("User without telegram_id found")
                        continue
                    
                    # Проверяем существует ли пользователь
                    cursor.execute("SELECT telegram_id FROM users WHERE telegram_id = ?", (telegram_id,))
                    existing_user = cursor.fetchone()
                    
                    if existing_user and not overwrite_existing:
                        results['skipped'] += 1
                        continue
                    
                    # Импортируем/обновляем пользователя
                    if existing_user:
                        # Обновляем существующего пользователя
                        cursor.execute("""
                            UPDATE users SET 
                                username = ?, total_spent = ?, total_months = ?,
                                trial_used = ?, agreed_to_terms = ?, registration_date = ?,
                                is_banned = ?, referred_by = ?, referral_balance = ?
                            WHERE telegram_id = ?
                        """, (
                            user_data.get('username'),
                            user_data.get('total_spent', 0),
                            user_data.get('total_months', 0),
                            user_data.get('trial_used', False),
                            user_data.get('agreed_to_terms', False),
                            user_data.get('registration_date'),
                            user_data.get('is_banned', False),
                            user_data.get('referred_by'),
                            user_data.get('referral_balance', 0),
                            telegram_id
                        ))
                        results['updated'] += 1
                    else:
                        # Создаем нового пользователя
                        cursor.execute("""
                            INSERT INTO users 
                            (telegram_id, username, total_spent, total_months, trial_used,
                             agreed_to_terms, registration_date, is_banned, referred_by, referral_balance)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            telegram_id,
                            user_data.get('username'),
                            user_data.get('total_spent', 0),
                            user_data.get('total_months', 0),
                            user_data.get('trial_used', False),
                            user_data.get('agreed_to_terms', False),
                            user_data.get('registration_date', datetime.utcnow().isoformat()),
                            user_data.get('is_banned', False),
                            user_data.get('referred_by'),
                            user_data.get('referral_balance', 0)
                        ))
                        results['imported'] += 1
                    
                    # Импортируем ключи пользователя
                    if user_data.get('keys'):
                        # Удаляем старые ключи если перезаписываем
                        if overwrite_existing:
                            cursor.execute("DELETE FROM vpn_keys WHERE user_id = ?", (telegram_id,))
                        
                        for key_data in user_data['keys']:
                            cursor.execute("""
                                INSERT OR REPLACE INTO vpn_keys 
                                (user_id, host_name, xui_client_uuid, key_email, expiry_date, created_date)
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (
                                telegram_id,
                                key_data.get('host_name'),
                                key_data.get('xui_client_uuid'),
                                key_data.get('key_email'),
                                key_data.get('expiry_date'),
                                key_data.get('created_date', datetime.utcnow().isoformat())
                            ))
                            results['keys_imported'] += 1
                    
                    # Импортируем транзакции пользователя
                    if user_data.get('transactions'):
                        for transaction_data in user_data['transactions']:
                            # Проверяем, существует ли транзакция
                            cursor.execute("""
                                SELECT transaction_id FROM transactions 
                                WHERE user_id = ? AND transaction_date = ? AND amount_spent = ?
                            """, (
                                telegram_id,
                                transaction_data.get('transaction_date'),
                                transaction_data.get('amount_spent')
                            ))
                            
                            if not cursor.fetchone():  # Добавляем только если транзакции нет
                                cursor.execute("""
                                    INSERT INTO transactions 
                                    (user_id, username, email, host_name, plan_name, months,
                                     amount_spent, payment_method, transaction_date)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    telegram_id,
                                    transaction_data.get('username'),
                                    transaction_data.get('email'),
                                    transaction_data.get('host_name'),
                                    transaction_data.get('plan_name'),
                                    transaction_data.get('months'),
                                    transaction_data.get('amount_spent'),
                                    transaction_data.get('payment_method'),
                                    transaction_data.get('transaction_date')
                                ))
                                results['transactions_imported'] += 1
                
                except Exception as e:
                    results['errors'].append(f"User {telegram_id}: {str(e)}")
                    continue
            
            conn.commit()
            logging.info(f"Import completed: {results}")
            
    except sqlite3.Error as e:
        logging.error(f"Database error during import: {e}")
        results['errors'].append(f"Database error: {str(e)}")
    
    return results

async def extend_user_key_time(key_id: int, days_to_add: int) -> dict:
    """Продлевает время действия конкретного ключа пользователя"""
    from shop_bot.modules.xui_api import create_or_update_key_on_host
    
    result = {
        "success": False,
        "message": "",
        "old_expiry": None,
        "new_expiry": None
    }
    
    try:
        # Получаем данные ключа
        key_data = get_key_by_id(key_id)
        if not key_data:
            result["message"] = "Ключ не найден"
            return result
        
        # Сохраняем старую дату истечения
        if key_data['expiry_date']:
            old_expiry = datetime.fromisoformat(key_data['expiry_date'].replace('Z', '+00:00'))
            result["old_expiry"] = old_expiry.strftime('%Y-%m-%d %H:%M')
        
        # Обновляем ключ на x-ui сервере
        xui_result = await create_or_update_key_on_host(
            host_name=key_data['host_name'],
            email=key_data['key_email'],
            days_to_add=days_to_add
        )
        
        if not xui_result:
            result["message"] = "Ошибка при обновлении ключа на сервере"
            return result
        
        # Обновляем данные в базе
        update_key_info(
            key_id=key_id,
            new_xui_uuid=xui_result['client_uuid'],
            new_expiry_ms=xui_result['expiry_timestamp_ms']
        )
        
        # Получаем новую дату истечения
        new_expiry = datetime.fromtimestamp(xui_result['expiry_timestamp_ms'] / 1000)
        result["new_expiry"] = new_expiry.strftime('%Y-%m-%d %H:%M')
        
        result["success"] = True
        result["message"] = f"Ключ успешно {'продлен' if days_to_add > 0 else 'сокращен'} на {abs(days_to_add)} дней"
        
        logging.info(f"Key {key_id} time updated: {days_to_add} days added")
        
    except Exception as e:
        logging.error(f"Failed to extend key {key_id} time: {e}", exc_info=True)
        result["message"] = f"Ошибка: {str(e)}"
    
    return result

async def extend_user_all_keys_time(user_id: int, days_to_add: int) -> dict:
    """Продлевает время действия всех ключей пользователя"""
    result = {
        "success": False,
        "message": "",
        "updated_keys": 0,
        "failed_keys": 0,
        "details": []
    }
    
    try:
        user_keys = get_user_keys(user_id)
        if not user_keys:
            result["message"] = "У пользователя нет ключей"
            return result
        
        for key in user_keys:
            try:
                key_result = await extend_user_key_time(key['key_id'], days_to_add)
                if key_result["success"]:
                    result["updated_keys"] += 1
                    result["details"].append(f"✅ {key['key_email']}: {key_result['message']}")
                else:
                    result["failed_keys"] += 1
                    result["details"].append(f"❌ {key['key_email']}: {key_result['message']}")
            except Exception as e:
                result["failed_keys"] += 1
                result["details"].append(f"❌ {key['key_email']}: {str(e)}")
        
        if result["updated_keys"] > 0:
            result["success"] = True
            result["message"] = f"Обновлено ключей: {result['updated_keys']}, ошибок: {result['failed_keys']}"
        else:
            result["message"] = "Не удалось обновить ни одного ключа"
        
        logging.info(f"User {user_id} keys time updated: {result['updated_keys']} success, {result['failed_keys']} failed")
        
    except Exception as e:
        logging.error(f"Failed to extend user {user_id} keys time: {e}", exc_info=True)
        result["message"] = f"Ошибка: {str(e)}"
    
    return result

async def extend_all_users_keys_time(days_to_add: int, admin_user: str = "admin") -> dict:
    """Продлевает время действия всех ключей всех пользователей"""
    result = {
        "success": False,
        "message": "",
        "processed_users": 0,
        "updated_keys": 0,
        "failed_keys": 0,
        "details": []
    }
    
    try:
        all_users = get_all_users()
        if not all_users:
            result["message"] = "Пользователи не найдены"
            return result
        
        for user in all_users:
            user_id = user['telegram_id']
            username = user.get('username', f'ID_{user_id}')
            
            try:
                user_result = await extend_user_all_keys_time(user_id, days_to_add)
                result["processed_users"] += 1
                result["updated_keys"] += user_result["updated_keys"]
                result["failed_keys"] += user_result["failed_keys"]
                
                if user_result["updated_keys"] > 0:
                    result["details"].append(f"👤 {username}: обновлено {user_result['updated_keys']} ключей")
                elif user_result["failed_keys"] > 0:
                    result["details"].append(f"👤 {username}: ошибки с {user_result['failed_keys']} ключами")
                    
            except Exception as e:
                result["details"].append(f"👤 {username}: ошибка - {str(e)}")
        
        if result["updated_keys"] > 0:
            result["success"] = True
            result["message"] = f"Массовое обновление завершено. Пользователей: {result['processed_users']}, ключей обновлено: {result['updated_keys']}, ошибок: {result['failed_keys']}"
        else:
            result["message"] = "Не удалось обновить ни одного ключа"
        
        logging.info(f"Mass keys time update by {admin_user}: {result['updated_keys']} keys updated, {result['failed_keys']} failed")
        
    except Exception as e:
        logging.error(f"Failed to extend all users keys time: {e}", exc_info=True)
        result["message"] = f"Ошибка: {str(e)}"
    
    return result
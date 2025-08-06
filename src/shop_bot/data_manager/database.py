import sqlite3
from datetime import datetime
import logging
from pathlib import Path

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
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    email TEXT,
                    host_name TEXT NOT NULL,
                    plan_name TEXT NOT NULL,
                    months INTEGER NOT NULL,
                    amount_spent REAL NOT NULL,
                    payment_method TEXT NOT NULL,
                    transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (telegram_id)
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
            
            # Сохраняем учетные данные в файл для вывода после установки
            credentials_file = PROJECT_ROOT / "admin_credentials.txt"
            with open(credentials_file, 'w') as f:
                f.write(f"ADMIN_LOGIN={admin_login}\n")
                f.write(f"ADMIN_PASSWORD={admin_password}\n")
                f.write(f"FLASK_SECRET_KEY={flask_secret}\n")
            
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
                "domain": None
            }
            _run_migrations(conn)
            for key, value in default_settings.items():
                cursor.execute("INSERT OR IGNORE INTO bot_settings (key, value) VALUES (?, ?)", (key, value))
            conn.commit()
            logging.info("Database initialized successfully.")
    except sqlite3.Error as e:
        logging.error(f"Database error on initialization: {e}")

def _run_migrations(conn: sqlite3.Connection):
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'referred_by' not in columns:
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN referred_by INTEGER")
            logger.info("Migration successful: Added 'referred_by' column to 'users' table.")
        except sqlite3.Error as e:
            logger.error(f"Migration failed for 'referred_by' column: {e}")

    if 'referral_balance' not in columns:
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN referral_balance REAL DEFAULT 0")
            logger.info("Migration successful: Added 'referral_balance' column to 'users' table.")
        except sqlite3.Error as e:
            logger.error(f"Migration failed for 'referral_balance' column: {e}")

    logger.info("Database migrations finished.")

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
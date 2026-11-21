import os
import sqlite3
from datetime import datetime
import psycopg
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")  # Cloud PostgreSQL URL

def get_connection():
    if DATABASE_URL:
        return psycopg.connect(DATABASE_URL)
    return sqlite3.connect("bakery_orders.db")

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    if DATABASE_URL:
        # PostgreSQL Syntax
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                order_code TEXT UNIQUE,
                customer_chat_id BIGINT,
                customer_name TEXT,
                flavor TEXT,
                weight_kg REAL,
                is_eggless INTEGER,
                is_custom_design INTEGER,
                message_on_cake TEXT,
                pickup_time TEXT,
                total_price INTEGER,
                advance_amount INTEGER,
                status TEXT DEFAULT 'CONFIRMED',
                created_at TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS customer_trust (
                customer_chat_id BIGINT PRIMARY KEY,
                completed_orders INTEGER DEFAULT 0,
                is_trusted INTEGER DEFAULT 0
            )
        """)
    else:
        # Local SQLite Fallback
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_code TEXT UNIQUE,
                customer_chat_id INTEGER,
                customer_name TEXT,
                flavor TEXT,
                weight_kg REAL,
                is_eggless INTEGER,
                is_custom_design INTEGER,
                message_on_cake TEXT,
                pickup_time TEXT,
                total_price INTEGER,
                advance_amount INTEGER,
                status TEXT DEFAULT 'CONFIRMED',
                created_at TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS customer_trust (
                customer_chat_id INTEGER PRIMARY KEY,
                completed_orders INTEGER DEFAULT 0,
                is_trusted INTEGER DEFAULT 0
            )
        """)

    conn.commit()
    conn.close()

def is_trusted_customer(chat_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    ph = "%s" if DATABASE_URL else "?"
    cursor.execute(f"SELECT is_trusted FROM customer_trust WHERE customer_chat_id = {ph}", (chat_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row and row[0] == 1)

def save_confirmed_order(chat_id: int, customer_name: str, order_data: dict) -> str:
    conn = get_connection()
    cursor = conn.cursor()
    ph = "%s" if DATABASE_URL else "?"

    if DATABASE_URL:
        cursor.execute(f"""
            INSERT INTO orders (
                customer_chat_id, customer_name, flavor, weight_kg, is_eggless,
                is_custom_design, message_on_cake, pickup_time, total_price,
                advance_amount, status, created_at
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, 'CONFIRMED', {ph})
            RETURNING id
        """, (
            chat_id, customer_name, order_data["flavor"], order_data["weight_kg"],
            int(order_data["is_eggless"]), int(order_data["is_custom_design"]),
            order_data["message_on_cake"], order_data["pickup_time"],
            order_data["total_price"], order_data["advance_amount"],
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ))
        row_id = cursor.fetchone()[0]
    else:
        cursor.execute(f"""
            INSERT INTO orders (
                customer_chat_id, customer_name, flavor, weight_kg, is_eggless,
                is_custom_design, message_on_cake, pickup_time, total_price,
                advance_amount, status, created_at
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, 'CONFIRMED', {ph})
        """, (
            chat_id, customer_name, order_data["flavor"], order_data["weight_kg"],
            int(order_data["is_eggless"]), int(order_data["is_custom_design"]),
            order_data["message_on_cake"], order_data["pickup_time"],
            order_data["total_price"], order_data["advance_amount"],
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ))
        row_id = cursor.lastrowid

    order_code = f"ORD-{100 + row_id}"
    cursor.execute(f"UPDATE orders SET order_code = {ph} WHERE id = {ph}", (order_code, row_id))

    cursor.execute(f"""
        INSERT INTO customer_trust (customer_chat_id, completed_orders, is_trusted)
        VALUES ({ph}, 1, 1)
        ON CONFLICT(customer_chat_id) DO UPDATE SET
            completed_orders = customer_trust.completed_orders + 1,
            is_trusted = 1
    """, (chat_id,))

    conn.commit()
    conn.close()
    return order_code

def get_active_orders() -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT order_code, customer_name, flavor, weight_kg, is_eggless,
               message_on_cake, pickup_time, total_price, advance_amount
        FROM orders
        WHERE status = 'CONFIRMED'
        ORDER BY id DESC LIMIT 10
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

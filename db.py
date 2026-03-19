import aiosqlite
from config import DB_PATH
from datetime import datetime

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                telegram_id INTEGER UNIQUE,
                username TEXT,
                full_name TEXT,
                balance REAL DEFAULT 0,
                total_paid REAL DEFAULT 0,
                joined_at TEXT,
                is_banned INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                title TEXT,
                is_paid INTEGER DEFAULT 0,
                price REAL DEFAULT 0,
                parts_count INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS video_parts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_code TEXT,
                part_number INTEGER,
                file_id TEXT,
                description TEXT,
                FOREIGN KEY (video_code) REFERENCES videos(code)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT,
                channel_name TEXT,
                channel_link TEXT,
                channel_type TEXT DEFAULT 'telegram'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS social_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT,
                link TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                video_code TEXT,
                amount REAL,
                check_file_id TEXT,
                status TEXT DEFAULT 'pending',
                payment_type TEXT DEFAULT 'video',
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS start_message (
                id INTEGER PRIMARY KEY,
                text TEXT,
                photo_id TEXT,
                is_quote INTEGER DEFAULT 0,
                quote_link TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                video_code TEXT,
                purchased_at TEXT
            )
        """)
        await db.commit()

# ===== USER FUNKSIYALARI =====
async def get_user(telegram_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)) as cur:
            return await cur.fetchone()

async def create_user(telegram_id, username, full_name):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (telegram_id, username, full_name, joined_at) VALUES (?,?,?,?)",
            (telegram_id, username, full_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        await db.commit()

async def get_all_users():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users ORDER BY joined_at DESC") as cur:
            return await cur.fetchall()

async def ban_user(telegram_id, status=1):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned=? WHERE telegram_id=?", (status, telegram_id))
        await db.commit()

async def add_balance(telegram_id, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance=balance+? WHERE telegram_id=?", (amount, telegram_id))
        await db.commit()

async def deduct_balance(telegram_id, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance=balance-?, total_paid=total_paid+? WHERE telegram_id=?",
                         (amount, amount, telegram_id))
        await db.commit()

async def add_balance_all(amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance=balance+?", (amount,))
        await db.commit()

async def get_user_by_id(telegram_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)) as cur:
            return await cur.fetchone()

async def get_users_count():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            row = await cur.fetchone()
            return row[0]

# ===== VIDEO FUNKSIYALARI =====
async def add_video(code, title, is_paid, price, parts_count):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO videos (code, title, is_paid, price, parts_count, created_at) VALUES (?,?,?,?,?,?)",
            (code, title, is_paid, price, parts_count, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        await db.commit()

async def get_video(code):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM videos WHERE code=?", (code,)) as cur:
            return await cur.fetchone()

async def add_video_part(video_code, part_number, file_id, description):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO video_parts (video_code, part_number, file_id, description) VALUES (?,?,?,?)",
            (video_code, part_number, file_id, description)
        )
        await db.commit()

async def get_video_parts(video_code):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM video_parts WHERE video_code=? ORDER BY part_number", (video_code,)) as cur:
            return await cur.fetchall()

async def get_video_part(video_code, part_number):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM video_parts WHERE video_code=? AND part_number=?",
                               (video_code, part_number)) as cur:
            return await cur.fetchone()

async def get_all_videos():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM videos ORDER BY created_at DESC") as cur:
            return await cur.fetchall()

# ===== KANAL FUNKSIYALARI =====
async def add_channel(channel_id, channel_name, channel_link, channel_type='telegram'):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO channels (channel_id, channel_name, channel_link, channel_type) VALUES (?,?,?,?)",
            (channel_id, channel_name, channel_link, channel_type)
        )
        await db.commit()

async def get_channels(channel_type='telegram'):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM channels WHERE channel_type=?", (channel_type,)) as cur:
            return await cur.fetchall()

async def delete_channel(channel_id_db):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM channels WHERE id=?", (channel_id_db,))
        await db.commit()

async def add_social_link(platform, link):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO social_links (platform, link) VALUES (?,?)", (platform, link))
        await db.commit()

async def get_social_links():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM social_links") as cur:
            return await cur.fetchall()

# ===== TO'LOV FUNKSIYALARI =====
async def add_payment(user_id, video_code, amount, check_file_id, payment_type='video'):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO payments (user_id, video_code, amount, check_file_id, payment_type, created_at) VALUES (?,?,?,?,?,?)",
            (user_id, video_code, amount, check_file_id, payment_type, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        await db.commit()
        return cursor.lastrowid

async def get_payment(payment_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM payments WHERE id=?", (payment_id,)) as cur:
            return await cur.fetchone()

async def update_payment_status(payment_id, status):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE payments SET status=? WHERE id=?", (status, payment_id))
        await db.commit()

async def has_purchased(user_id, video_code):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM user_purchases WHERE user_id=? AND video_code=?", (user_id, video_code)
        ) as cur:
            return await cur.fetchone() is not None

async def add_purchase(user_id, video_code):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO user_purchases (user_id, video_code, purchased_at) VALUES (?,?,?)",
            (user_id, video_code, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        await db.commit()

# ===== START XABAR =====
async def set_start_message(text, photo_id=None, is_quote=0, quote_link=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM start_message")
        await db.execute(
            "INSERT INTO start_message (id, text, photo_id, is_quote, quote_link) VALUES (1,?,?,?,?)",
            (text, photo_id, is_quote, quote_link)
        )
        await db.commit()

async def get_start_message():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM start_message WHERE id=1") as cur:
            return await cur.fetchone()

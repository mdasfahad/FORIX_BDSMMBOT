#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Number Bot
- Free numbers from admin panel (not purchased)
- Users take numbers and work
- Configurable reward (balance) per number / service
- Search OTP, Support, full Admin Panel

Main Admin ID: 8289191009
"""

import logging
import os
import sqlite3
from datetime import datetime, date
from typing import Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden

# ================== CONFIG ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8938358982:AAEu-E6oTqKutr1825HUhM1YP6ceQYFCpb8")
MAIN_ADMIN_ID = 8289191009
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "number_bot.db")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Conversation states
(
    AWAIT_NUMBER_ADD,
    AWAIT_SERVICE_ADD,
    AWAIT_SERVICE_REWARD,
    AWAIT_BAN_ID,
    AWAIT_UNBAN_ID,
    AWAIT_BAL_UID,
    AWAIT_BAL_AMT,
    AWAIT_SUPPORT,
    AWAIT_CHANNEL,
    AWAIT_OTP_QUERY,
    AWAIT_ADMIN_ADD,
    AWAIT_ADMIN_RM,
    AWAIT_STATUS_UID,
    AWAIT_BROADCAST,
) = range(14)


# ================== DATABASE ==================
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            balance REAL DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            numbers_taken INTEGER DEFAULT 0,
            joined_at TEXT
        );
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            role TEXT DEFAULT 'admin',
            added_at TEXT
        );
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            reward REAL DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS numbers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            service_id INTEGER,
            reward REAL DEFAULT 0,
            status TEXT DEFAULT 'available',
            taken_by INTEGER,
            taken_at TEXT,
            otp_text TEXT,
            note TEXT,
            created_at TEXT,
            FOREIGN KEY(service_id) REFERENCES services(id)
        );
        CREATE TABLE IF NOT EXISTS force_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            title TEXT,
            link TEXT,
            is_active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS otp_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT,
            otp TEXT,
            user_id INTEGER,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS panels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            api_key TEXT DEFAULT '',
            api_url TEXT DEFAULT '',
            is_enabled INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0
        );
        """
    )
    # defaults
    defaults = {
        "support_username": "",
        "bot_enabled": "1",
        "welcome_text": "Welcome to Number Bot!\nAdmin panel theke free number nite parben.",
        "default_reward": "0.01",
    }
    for k, v in defaults.items():
        cur.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v)
        )
    cur.execute(
        "INSERT OR IGNORE INTO admins (user_id, role, added_at) VALUES (?, 'main', ?)",
        (MAIN_ADMIN_ID, datetime.now().isoformat()),
    )
    # sample services
    
    # default OTP/SMS panels (API key admin sets from Panel Control)
    default_panels = [
        ("fastxotp", 1),
        ("voltxsms", 2),
        ("stexsms", 3),
        ("Zenex", 4),
        ("Miahsms", 5),
        ("NexaOTP", 6),
        ("Xeron", 7),
    ]
    for name, order in default_panels:
        cur.execute(
            "INSERT OR IGNORE INTO panels (name, api_key, is_enabled, sort_order) VALUES (?,?,1,?)",
            (name, "", order),
        )

    for name, reward in [("WhatsApp", 0.01), ("Telegram", 0.02), ("Facebook", 0.05)]:
        cur.execute(
            "INSERT OR IGNORE INTO services (name, reward, is_active, created_at) VALUES (?,?,1,?)",
            (name, reward, datetime.now().isoformat()),
        )
    conn.commit()
    conn.close()


def get_setting(key: str, default: str = "") -> str:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    r = cur.fetchone()
    conn.close()
    return r["value"] if r else default


def set_setting(key: str, value: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value))
    )
    conn.commit()
    conn.close()


def ensure_user(uid: int, username: Optional[str] = None, full_name: Optional[str] = None):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id=?", (uid,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (user_id, username, full_name, joined_at) VALUES (?,?,?,?)",
            (uid, username or "", full_name or "", datetime.now().isoformat()),
        )
        conn.commit()
    else:
        cur.execute(
            "UPDATE users SET username=?, full_name=? WHERE user_id=?",
            (username or "", full_name or "", uid),
        )
        conn.commit()
    conn.close()


def get_user(uid: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    r = cur.fetchone()
    conn.close()
    return r


def is_admin(uid: int) -> bool:
    if uid == MAIN_ADMIN_ID:
        return True
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM admins WHERE user_id=?", (uid,))
    r = cur.fetchone()
    conn.close()
    return bool(r)


def is_main(uid: int) -> bool:
    return uid == MAIN_ADMIN_ID


def is_banned(uid: int) -> bool:
    u = get_user(uid)
    return bool(u and u["is_banned"])


# ================== KEYBOARDS ==================
def main_kb(show_admin: bool = False):
    rows = [
        [
            InlineKeyboardButton("👤 GET NUMBER", callback_data="get_number"),
            InlineKeyboardButton("💬 SEARCH OTP", callback_data="search_otp"),
        ],
        [InlineKeyboardButton("✈️ SUPPORT", callback_data="support")],
    ]
    if show_admin:
        rows.append(
            [InlineKeyboardButton("📍 ADMIN PANEL", callback_data="admin_panel")]
        )
    return InlineKeyboardMarkup(rows)


def admin_kb():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📍 CHANNEL CONTROL", callback_data="adm_channel"),
                InlineKeyboardButton("💬 SERVICE CONTROL", callback_data="adm_service"),
            ],
            [InlineKeyboardButton("👑 ADMIN MANAGE", callback_data="adm_admins")],
            [InlineKeyboardButton("🔔 PANEL CONTROL", callback_data="adm_panel")],
            [InlineKeyboardButton("👤 USER MANAGEMENT", callback_data="adm_users")],
            [
                InlineKeyboardButton(
                    "📍 SYSTEM CONFIGURATION", callback_data="adm_system"
                )
            ],
            [InlineKeyboardButton("🔙 BACK TO MAIN", callback_data="back_main")],
        ]
    )


def user_mgmt_kb():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("💰 TODAY ALL STATUS", callback_data="um_today"),
                InlineKeyboardButton("❤️ USER STATUS CHECK", callback_data="um_status"),
            ],
            [
                InlineKeyboardButton("💼 BAN USER", callback_data="um_ban"),
                InlineKeyboardButton("♻️ UNBAN USER", callback_data="um_unban"),
            ],
            [InlineKeyboardButton("👤 BAN USER LIST", callback_data="um_banlist")],
            [
                InlineKeyboardButton("📅 REMOVE BALANCE", callback_data="um_rmbal"),
                InlineKeyboardButton("💎 ADD BALANCE", callback_data="um_addbal"),
            ],
            [InlineKeyboardButton("🔙 BACK TO ADMIN", callback_data="admin_panel")],
        ]
    )


def service_ctrl_kb():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Add Service", callback_data="svc_add")],
            [InlineKeyboardButton("📋 List Services", callback_data="svc_list")],
            [InlineKeyboardButton("➕ Add Numbers", callback_data="num_add")],
            [InlineKeyboardButton("📋 Available Numbers", callback_data="num_list")],
            [InlineKeyboardButton("🔙 BACK TO ADMIN", callback_data="admin_panel")],
        ]
    )


def channel_ctrl_kb():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Add Channel", callback_data="ch_add")],
            [InlineKeyboardButton("📋 List / Remove", callback_data="ch_list")],
            [InlineKeyboardButton("🔙 BACK TO ADMIN", callback_data="admin_panel")],
        ]
    )


# ================== FORCE JOIN ==================
async def check_force_join(bot, user_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM force_channels WHERE is_active=1")
    channels = cur.fetchall()
    conn.close()
    missing = []
    for ch in channels:
        raw = str(ch["chat_id"]).strip()
        try:
            cid = int(raw) if raw.lstrip("-").isdigit() else (
                raw if raw.startswith("@") else "@" + raw
            )
            m = await bot.get_chat_member(chat_id=cid, user_id=user_id)
            st = str(getattr(m.status, "name", m.status)).upper()
            if st not in ("MEMBER", "ADMINISTRATOR", "CREATOR", "OWNER"):
                missing.append(ch)
        except Exception:
            missing.append(ch)
    return missing


async def force_join_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Return True if user can proceed, False if blocked by force join."""
    uid = update.effective_user.id
    if is_admin(uid):
        return True
    missing = await check_force_join(context.bot, uid)
    if not missing:
        return True
    buttons = []
    for ch in missing:
        link = ch["link"] or (
            f"https://t.me/{str(ch['chat_id']).lstrip('@')}"
            if not str(ch["chat_id"]).startswith("-")
            else None
        )
        title = ch["title"] or str(ch["chat_id"])
        if link:
            buttons.append([InlineKeyboardButton(f"Join {title}", url=link)])
    buttons.append(
        [InlineKeyboardButton("✅ I Joined — Verify", callback_data="check_join")]
    )
    msg = "⚠️ আগে নিচের চ্যানেল জয়েন করুন:"
    target = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            msg, reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:
        await target.reply_text(msg, reply_markup=InlineKeyboardMarkup(buttons))
    return False


# ================== START ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id, user.username, user.full_name)
    if is_banned(user.id):
        await update.message.reply_text("🚫 আপনি ব্যান করা আছেন।")
        return
    if get_setting("bot_enabled", "1") != "1" and not is_admin(user.id):
        await update.message.reply_text("🔧 বট এখন বন্ধ আছে।")
        return
    if not await force_join_gate(update, context):
        return
    welcome = get_setting("welcome_text") or "Welcome!"
    u = get_user(user.id)
    bal = u["balance"] if u else 0
    text = (
        f"{welcome}\n\n"
        f"👤 ID: <code>{user.id}</code>\n"
        f"💰 Balance: <b>{bal:.2f}</b>\n"
    )
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=main_kb(is_admin(user.id)),
    )


async def check_join_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    missing = await check_force_join(context.bot, uid)
    if missing:
        await q.answer("এখনো সব চ্যানেল জয়েন করেননি!", show_alert=True)
        return
    ensure_user(uid, q.from_user.username, q.from_user.full_name)
    u = get_user(uid)
    await q.edit_message_text(
        f"✅ Verified!\n💰 Balance: {u['balance']:.2f}",
        reply_markup=main_kb(is_admin(uid)),
    )


# ================== GET NUMBER ==================
async def get_number_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if is_banned(uid):
        await q.edit_message_text("🚫 ব্যান করা আছেন।")
        return
    if not await force_join_gate(update, context):
        return

    # list active services that have available numbers
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT s.id, s.name, s.reward, COUNT(n.id) as cnt
        FROM services s
        LEFT JOIN numbers n ON n.service_id = s.id AND n.status='available'
        WHERE s.is_active=1
        GROUP BY s.id
        HAVING cnt > 0
        ORDER BY s.name
        """
    )
    rows = cur.fetchall()
    conn.close()
    if not rows:
        await q.edit_message_text(
            "❌ এখন কোনো নাম্বার নেই। পরে আবার চেষ্টা করুন।",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]
            ),
        )
        return
    buttons = []
    for r in rows:
        buttons.append(
            [
                InlineKeyboardButton(
                    f"{r['name']} ({r['cnt']}) 🎁 {r['reward']:.2f}",
                    callback_data=f"take_svc_{r['id']}",
                )
            ]
        )
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_main")])
    await q.edit_message_text(
        "📱 সার্ভিস বেছে নিন (ফ্রি নাম্বার):\n"
        "নাম্বার নিলে রিওয়ার্ড ব্যালেন্সে যোগ হতে পারে।",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def take_svc_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if is_banned(uid):
        await q.answer("Banned", show_alert=True)
        return
    svc_id = int(q.data.split("_")[-1])
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM services WHERE id=? AND is_active=1", (svc_id,))
    svc = cur.fetchone()
    if not svc:
        conn.close()
        await q.edit_message_text("সার্ভিস নেই।")
        return
    # take one available number atomically
    cur.execute(
        """
        SELECT * FROM numbers
        WHERE service_id=? AND status='available'
        ORDER BY id ASC LIMIT 1
        """,
        (svc_id,),
    )
    num = cur.fetchone()
    if not num:
        conn.close()
        await q.edit_message_text(
            "এই সার্ভিসে নাম্বার শেষ।",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Back", callback_data="get_number")]]
            ),
        )
        return
    reward = float(num["reward"] if num["reward"] else svc["reward"] or 0)
    cur.execute(
        """
        UPDATE numbers SET status='taken', taken_by=?, taken_at=?
        WHERE id=? AND status='available'
        """,
        (uid, datetime.now().isoformat(), num["id"]),
    )
    if cur.rowcount == 0:
        conn.close()
        await q.edit_message_text("আরেকজন নিয়ে নিয়েছে। আবার চেষ্টা করুন।")
        return
    cur.execute(
        "UPDATE users SET balance = balance + ?, numbers_taken = numbers_taken + 1 WHERE user_id=?",
        (reward, uid),
    )
    conn.commit()
    cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
    bal = cur.fetchone()["balance"]
    conn.close()

    note = f"\n📝 {num['note']}" if num["note"] else ""
    await q.edit_message_text(
        f"✅ <b>নাম্বার পেয়েছেন</b>\n\n"
        f"📱 Number: <code>{num['phone']}</code>\n"
        f"🏷 Service: {svc['name']}\n"
        f"🎁 Reward: +{reward:.2f}\n"
        f"💰 Balance: {bal:.2f}"
        f"{note}\n\n"
        f"OTP পেতে SEARCH OTP ব্যবহার করুন।",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("💬 SEARCH OTP", callback_data="search_otp")],
                [InlineKeyboardButton("👤 আরেকটা নাম্বার", callback_data="get_number")],
                [InlineKeyboardButton("🔙 Main", callback_data="back_main")],
            ]
        ),
    )


# ================== SEARCH OTP ==================
async def search_otp_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if is_banned(uid):
        await q.edit_message_text("🚫 Banned")
        return
    context.user_data["await"] = "otp_query"
    await q.edit_message_text(
        "🔍 যে নাম্বারের OTP খুজবেন সেটা লিখুন:\n"
        "(যে নাম্বার আপনি নিয়েছেন)",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="back_main")]]
        ),
    )


async def handle_otp_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    phone = (update.message.text or "").strip()
    context.user_data.pop("await", None)
    conn = get_db()
    cur = conn.cursor()
    # user's taken number
    cur.execute(
        """
        SELECT * FROM numbers
        WHERE phone=? AND taken_by=? AND status='taken'
        ORDER BY id DESC LIMIT 1
        """,
        (phone, uid),
    )
    num = cur.fetchone()
    if not num and is_admin(uid):
        cur.execute(
            "SELECT * FROM numbers WHERE phone=? ORDER BY id DESC LIMIT 1", (phone,)
        )
        num = cur.fetchone()
    if not num:
        # also try partial match
        cur.execute(
            """
            SELECT * FROM numbers
            WHERE phone LIKE ? AND taken_by=?
            ORDER BY id DESC LIMIT 1
            """,
            (f"%{phone}%", uid),
        )
        num = cur.fetchone()
    conn.close()
    if not num:
        await update.message.reply_text(
            "❌ এই নাম্বার আপনার কাছে নেই বা পাওয়া যায়নি।",
            reply_markup=main_kb(is_admin(uid)),
        )
        return
    otp = num["otp_text"] or "এখনো OTP আসেনি। একটু পর আবার চেষ্টা করুন।"
    await update.message.reply_text(
        f"📱 <code>{num['phone']}</code>\n"
        f"🔑 OTP: <b>{otp}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=main_kb(is_admin(uid)),
    )


# ================== SUPPORT ==================
async def support_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    un = (get_setting("support_username") or "").strip().lstrip("@")
    if un:
        await q.edit_message_text(
            "🆘 Support",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("💬 Contact Support", url=f"https://t.me/{un}")],
                    [InlineKeyboardButton("🔙 Back", callback_data="back_main")],
                ]
            ),
        )
    else:
        await q.edit_message_text(
            "Support এখনো সেট করা হয়নি।",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]
            ),
        )


async def back_main_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data.clear()
    uid = q.from_user.id
    u = get_user(uid)
    bal = u["balance"] if u else 0
    await q.edit_message_text(
        f"🏠 Main Menu\n💰 Balance: <b>{bal:.2f}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=main_kb(is_admin(uid)),
    )


# ================== ADMIN PANEL ==================
async def admin_panel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        await q.answer("Admin only", show_alert=True)
        return
    await q.edit_message_text(
        "🔐 <b>ADMIN PANEL</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_kb(),
    )


# ----- SERVICE CONTROL -----
async def adm_service_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    await q.edit_message_text(
        "💬 <b>SERVICE CONTROL</b>\n"
        "সার্ভিস ও ফ্রি নাম্বার ম্যানেজ করুন।\n"
        "রিওয়ার্ড Admin থেকে সেট হবে।",
        parse_mode=ParseMode.HTML,
        reply_markup=service_ctrl_kb(),
    )


async def svc_list_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM services ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    if not rows:
        text = "কোনো সার্ভিস নেই।"
        buttons = [[InlineKeyboardButton("🔙 Back", callback_data="adm_service")]]
    else:
        text = "📋 <b>Services</b>\n\n"
        buttons = []
        for r in rows:
            st = "✅" if r["is_active"] else "❌"
            text += f"#{r['id']} {st} {r['name']} | reward {r['reward']:.2f}\n"
            buttons.append(
                [
                    InlineKeyboardButton(
                        f"{'OFF' if r['is_active'] else 'ON'} #{r['id']}",
                        callback_data=f"svc_tog_{r['id']}",
                    ),
                    InlineKeyboardButton(
                        f"Reward #{r['id']}", callback_data=f"svc_rew_{r['id']}"
                    ),
                    InlineKeyboardButton(
                        f"Del #{r['id']}", callback_data=f"svc_del_{r['id']}"
                    ),
                ]
            )
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="adm_service")])
    await q.edit_message_text(
        text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons)
    )


async def svc_tog_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    sid = int(q.data.split("_")[-1])
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE services SET is_active = CASE WHEN is_active=1 THEN 0 ELSE 1 END WHERE id=?",
        (sid,),
    )
    conn.commit()
    conn.close()
    await svc_list_cb(update, context)


async def svc_del_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    sid = int(q.data.split("_")[-1])
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM services WHERE id=?", (sid,))
    conn.commit()
    conn.close()
    await q.answer("Deleted", show_alert=True)
    await svc_list_cb(update, context)


async def svc_add_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    context.user_data["await"] = "svc_name"
    await q.edit_message_text(
        "সার্ভিসের নাম লিখুন (যেমন: WhatsApp):",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="adm_service")]]
        ),
    )


async def svc_rew_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    sid = int(q.data.split("_")[-1])
    context.user_data["await"] = "svc_reward"
    context.user_data["svc_id"] = sid
    await q.edit_message_text(
        f"Service #{sid} এর নতুন reward লিখুন (যেমন: 0.01 বা 1):",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="adm_service")]]
        ),
    )


async def num_add_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM services WHERE is_active=1 ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    if not rows:
        await q.edit_message_text(
            "আগে Service যোগ করুন।",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Back", callback_data="adm_service")]]
            ),
        )
        return
    buttons = [
        [InlineKeyboardButton(r["name"], callback_data=f"num_svc_{r['id']}")]
        for r in rows
    ]
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="adm_service")])
    await q.edit_message_text(
        "কোন সার্ভিসে নাম্বার যোগ করবেন?",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def num_svc_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    sid = int(q.data.split("_")[-1])
    context.user_data["await"] = "num_add"
    context.user_data["num_svc"] = sid
    await q.edit_message_text(
        "নাম্বার পাঠান (এক লাইনে একটি)।\n"
        "একাধিক হলে একাধিক লাইন।\n"
        "Format: 8801XXXXXXXXX\n"
        "বা: number|otp|note",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="adm_service")]]
        ),
    )


async def num_list_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT n.id, n.phone, n.status, n.reward, s.name as sname
        FROM numbers n
        LEFT JOIN services s ON s.id = n.service_id
        ORDER BY n.id DESC LIMIT 30
        """
    )
    rows = cur.fetchall()
    conn.close()
    text = "📋 <b>Numbers (last 30)</b>\n\n"
    for r in rows:
        text += f"#{r['id']} {r['phone']} | {r['sname'] or '-'} | {r['status']} | {r['reward']}\n"
    if not rows:
        text += "খালি"
    await q.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 Back", callback_data="adm_service")]]
        ),
    )


# ----- CHANNEL CONTROL -----
async def adm_channel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    await q.edit_message_text(
        "📍 <b>CHANNEL CONTROL</b>\nForce join চ্যানেল ম্যানেজ করুন।",
        parse_mode=ParseMode.HTML,
        reply_markup=channel_ctrl_kb(),
    )


async def ch_add_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    context.user_data["await"] = "ch_add"
    await q.edit_message_text(
        "Channel @username বা -100id পাঠান\n(বটকে চ্যানেলে Admin দিন):",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="adm_channel")]]
        ),
    )


async def ch_list_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM force_channels ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    text = "📢 Force Channels\n\n"
    buttons = []
    for r in rows:
        text += f"#{r['id']} {r['title'] or r['chat_id']}\n"
        buttons.append(
            [
                InlineKeyboardButton(
                    f"🗑 Remove #{r['id']}", callback_data=f"ch_rm_{r['id']}"
                )
            ]
        )
    if not rows:
        text += "খালি"
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="adm_channel")])
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def ch_rm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    cid = int(q.data.split("_")[-1])
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM force_channels WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    await ch_list_cb(update, context)


# ----- USER MANAGEMENT -----
async def adm_users_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    await q.edit_message_text(
        "👤 <b>USER MANAGEMENT</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=user_mgmt_kb(),
    )


async def um_today_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    today = date.today().isoformat()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) c FROM users")
    total = cur.fetchone()["c"]
    cur.execute(
        "SELECT COUNT(*) c FROM numbers WHERE status='taken' AND taken_at LIKE ?",
        (f"{today}%",),
    )
    taken_today = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) c FROM numbers WHERE status='available'")
    avail = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) c FROM users WHERE is_banned=1")
    banned = cur.fetchone()["c"]
    conn.close()
    await q.edit_message_text(
        f"📊 <b>TODAY STATUS</b>\n\n"
        f"👥 Total users: {total}\n"
        f"📱 Numbers taken today: {taken_today}\n"
        f"✅ Available numbers: {avail}\n"
        f"🚫 Banned: {banned}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 Back", callback_data="adm_users")]]
        ),
    )


async def um_status_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    context.user_data["await"] = "status_uid"
    await q.edit_message_text(
        "User ID লিখুন:",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="adm_users")]]
        ),
    )


async def um_ban_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    context.user_data["await"] = "ban_uid"
    await q.edit_message_text(
        "Ban করতে User ID লিখুন:",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="adm_users")]]
        ),
    )


async def um_unban_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    context.user_data["await"] = "unban_uid"
    await q.edit_message_text(
        "Unban করতে User ID লিখুন:",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="adm_users")]]
        ),
    )


async def um_banlist_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, username, full_name FROM users WHERE is_banned=1 LIMIT 50"
    )
    rows = cur.fetchall()
    conn.close()
    text = "🚫 <b>Ban List</b>\n\n"
    if not rows:
        text += "খালি"
    for r in rows:
        text += f"<code>{r['user_id']}</code> @{r['username'] or '-'} {r['full_name'] or ''}\n"
    await q.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 Back", callback_data="adm_users")]]
        ),
    )


async def um_addbal_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    context.user_data["await"] = "addbal_uid"
    context.user_data["bal_mode"] = "add"
    await q.edit_message_text(
        "Balance ADD — User ID লিখুন:",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="adm_users")]]
        ),
    )


async def um_rmbal_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    context.user_data["await"] = "rmbal_uid"
    context.user_data["bal_mode"] = "remove"
    await q.edit_message_text(
        "Balance REMOVE — User ID লিখুন:",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="adm_users")]]
        ),
    )


# ----- ADMIN MANAGE -----
async def adm_admins_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM admins ORDER BY user_id")
    rows = cur.fetchall()
    conn.close()
    text = "👑 <b>Admins</b>\n\n"
    text += f"Main: <code>{MAIN_ADMIN_ID}</code>\n"
    for r in rows:
        if r["user_id"] != MAIN_ADMIN_ID:
            text += f"— <code>{r['user_id']}</code> ({r['role']})\n"
    buttons = []
    if is_main(q.from_user.id):
        buttons.append(
            [InlineKeyboardButton("➕ Add Admin", callback_data="admin_add")]
        )
        buttons.append(
            [InlineKeyboardButton("🗑 Remove Admin", callback_data="admin_rm")]
        )
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin_panel")])
    await q.edit_message_text(
        text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons)
    )


async def admin_add_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_main(q.from_user.id):
        await q.answer("Only Main Admin", show_alert=True)
        return
    context.user_data["await"] = "admin_add"
    await q.edit_message_text("নতুন Admin এর User ID:")


async def admin_rm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_main(q.from_user.id):
        await q.answer("Only Main Admin", show_alert=True)
        return
    context.user_data["await"] = "admin_rm"
    await q.edit_message_text("রিমুভ করতে Admin User ID:")


# ----- PANEL / SYSTEM -----
async def adm_panel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Panel Control — OTP/SMS provider panels ON/OFF + API keys."""
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM panels ORDER BY sort_order, id")
    rows = cur.fetchall()
    conn.close()
    lines = ["📍 <b>PANEL CONTROL</b>", ""]
    buttons = []
    for r in rows:
        st = "ON" if r["is_enabled"] else "OFF"
        key = "SET" if (r["api_key"] or "").strip() else "NOT SET"
        dot = "🟢" if r["is_enabled"] else "🔴"
        lines.append("%s %s: <b>%s</b> | Key: <b>%s</b>" % (dot, r["name"], st, key))
        on_off = "Turn OFF" if r["is_enabled"] else "Turn ON"
        buttons.append(
            [
                InlineKeyboardButton(
                    "%s %s" % (dot, on_off + " " + r["name"]),
                    callback_data="pnl_tog_%s" % r["id"],
                ),
                InlineKeyboardButton(
                    "🔑 Change %s Key" % r["name"],
                    callback_data="pnl_key_%s" % r["id"],
                ),
            ]
        )
    lines.append("")
    lines.append("<i>Only full admins can change panel status or API keys.</i>")
    buttons.append(
        [InlineKeyboardButton("➕ Add Custom Panel", callback_data="pnl_add")]
    )
    buttons.append(
        [InlineKeyboardButton("🤖 Bot ON/OFF", callback_data="tog_bot")]
    )
    buttons.append(
        [InlineKeyboardButton("📢 Broadcast", callback_data="broadcast")]
    )
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin_panel")])
    await q.edit_message_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def pnl_tog_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    pid = int(q.data.split("_")[-1])
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE panels SET is_enabled = CASE WHEN is_enabled=1 THEN 0 ELSE 1 END WHERE id=?",
        (pid,),
    )
    conn.commit()
    conn.close()
    await adm_panel_cb(update, context)


async def pnl_key_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    pid = int(q.data.split("_")[-1])
    context.user_data["await"] = "pnl_key"
    context.user_data["pnl_id"] = pid
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT name FROM panels WHERE id=?", (pid,))
    r = cur.fetchone()
    conn.close()
    name = r["name"] if r else str(pid)
    await q.edit_message_text(
        "🔑 <b>%s</b> এর API Key পাঠান:\n"
        "(আগের key overwrite হবে)"
        % name,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="adm_panel")]]
        ),
    )


async def pnl_add_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    context.user_data["await"] = "pnl_add_name"
    await q.edit_message_text(
        "নতুন Panel এর নাম লিখুন (যেমন: MySMS):",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="adm_panel")]]
        ),
    )


async def tog_bot_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    cur = get_setting("bot_enabled", "1")
    set_setting("bot_enabled", "0" if cur == "1" else "1")
    await q.answer(f"bot_enabled = {get_setting('bot_enabled')}", show_alert=True)
    await adm_panel_cb(update, context)


async def broadcast_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    context.user_data["await"] = "broadcast"
    await q.edit_message_text(
        "Broadcast মেসেজ লিখুন (টেক্সট):",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="adm_panel")]]
        ),
    )


async def adm_system_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    await q.edit_message_text(
        "📍 <b>SYSTEM CONFIGURATION</b>\n\n"
        f"Support: @{get_setting('support_username') or '-'}\n"
        f"Default reward: {get_setting('default_reward')}\n"
        f"Welcome set: {'yes' if get_setting('welcome_text') else 'no'}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Set Support Username", callback_data="set_support"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "Set Default Reward", callback_data="set_def_reward"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "Set Welcome Text", callback_data="set_welcome"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "Set OTP for Number", callback_data="set_otp"
                    )
                ],
                [InlineKeyboardButton("🔙 Back", callback_data="admin_panel")],
            ]
        ),
    )


async def set_support_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    context.user_data["await"] = "set_support"
    await q.edit_message_text("Support username লিখুন (without @):")


async def set_def_reward_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    context.user_data["await"] = "set_def_reward"
    await q.edit_message_text("Default reward (যেমন 0.01):")


async def set_welcome_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    context.user_data["await"] = "set_welcome"
    await q.edit_message_text("Welcome টেক্সট লিখুন:")


async def set_otp_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    context.user_data["await"] = "set_otp"
    await q.edit_message_text(
        "Format:\n<code>number|otp</code>\nযেমন:\n<code>8801712345678|123456</code>",
        parse_mode=ParseMode.HTML,
    )


# ================== TEXT HANDLER ==================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid, update.effective_user.username, update.effective_user.full_name)
    text = (update.message.text or "").strip()
    await_key = context.user_data.get("await")

    if is_banned(uid) and not is_admin(uid):
        await update.message.reply_text("🚫 Banned")
        return

    if await_key == "otp_query":
        await handle_otp_query(update, context)
        return

    if not is_admin(uid):
        await update.message.reply_text(
            "মেনু থেকে বাটন ব্যবহার করুন। /start",
            reply_markup=main_kb(False),
        )
        return

    # ----- admin awaits -----
    if await_key == "svc_name":
        context.user_data.pop("await", None)
        name = text[:40]
        reward = float(get_setting("default_reward") or 0.01)
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO services (name, reward, is_active, created_at) VALUES (?,?,1,?)",
                (name, reward, datetime.now().isoformat()),
            )
            conn.commit()
            await update.message.reply_text(
                f"✅ Service '{name}' added (reward {reward})",
                reply_markup=service_ctrl_kb(),
            )
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
        conn.close()
        return

    if await_key == "svc_reward":
        context.user_data.pop("await", None)
        sid = context.user_data.pop("svc_id", None)
        try:
            val = float(text)
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE services SET reward=? WHERE id=?", (val, sid))
            conn.commit()
            conn.close()
            await update.message.reply_text(
                f"✅ Service #{sid} reward = {val}",
                reply_markup=service_ctrl_kb(),
            )
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
        return

    if await_key == "num_add":
        context.user_data.pop("await", None)
        sid = context.user_data.get("num_svc")
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT reward FROM services WHERE id=?", (sid,))
        svc = cur.fetchone()
        default_reward = float(svc["reward"]) if svc else float(
            get_setting("default_reward") or 0
        )
        added = 0
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split("|")]
            phone = parts[0]
            otp = parts[1] if len(parts) > 1 else None
            note = parts[2] if len(parts) > 2 else None
            cur.execute(
                """
                INSERT INTO numbers (phone, service_id, reward, status, otp_text, note, created_at)
                VALUES (?,?,?,'available',?,?,?)
                """,
                (
                    phone,
                    sid,
                    default_reward,
                    otp,
                    note,
                    datetime.now().isoformat(),
                ),
            )
            added += 1
        conn.commit()
        conn.close()
        await update.message.reply_text(
            f"✅ {added} টি নাম্বার যোগ হয়েছে।",
            reply_markup=service_ctrl_kb(),
        )
        return

    if await_key == "ch_add":
        context.user_data.pop("await", None)
        raw = text
        title, link = raw, ""
        try:
            chat = await context.bot.get_chat(
                int(raw) if raw.lstrip("-").isdigit() else raw
            )
            title = chat.title or raw
            if getattr(chat, "username", None):
                link = "https://t.me/" + chat.username
        except Exception as e:
            await update.message.reply_text(f"⚠️ {e} — saved anyway")
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO force_channels (chat_id, title, link) VALUES (?,?,?)",
            (raw, title, link),
        )
        conn.commit()
        conn.close()
        await update.message.reply_text(
            f"✅ Channel: {title}", reply_markup=channel_ctrl_kb()
        )
        return

    if await_key == "ban_uid":
        context.user_data.pop("await", None)
        try:
            tid = int(text)
            if tid == MAIN_ADMIN_ID:
                await update.message.reply_text("Main admin ban করা যাবে না।")
                return
            ensure_user(tid)
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (tid,))
            conn.commit()
            conn.close()
            await update.message.reply_text(
                f"🚫 Banned {tid}", reply_markup=user_mgmt_kb()
            )
        except Exception as e:
            await update.message.reply_text(str(e))
        return

    if await_key == "unban_uid":
        context.user_data.pop("await", None)
        try:
            tid = int(text)
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (tid,))
            conn.commit()
            conn.close()
            await update.message.reply_text(
                f"✅ Unbanned {tid}", reply_markup=user_mgmt_kb()
            )
        except Exception as e:
            await update.message.reply_text(str(e))
        return

    if await_key == "status_uid":
        context.user_data.pop("await", None)
        try:
            tid = int(text)
            u = get_user(tid)
            if not u:
                await update.message.reply_text("User নেই।")
                return
            await update.message.reply_text(
                f"👤 <code>{u['user_id']}</code>\n"
                f"@{u['username'] or '-'}\n"
                f"{u['full_name'] or ''}\n"
                f"💰 {u['balance']:.2f}\n"
                f"📱 taken: {u['numbers_taken']}\n"
                f"🚫 banned: {u['is_banned']}\n"
                f"Joined: {u['joined_at']}",
                parse_mode=ParseMode.HTML,
                reply_markup=user_mgmt_kb(),
            )
        except Exception as e:
            await update.message.reply_text(str(e))
        return

    if await_key in ("addbal_uid", "rmbal_uid"):
        try:
            context.user_data["bal_uid"] = int(text)
            context.user_data["await"] = "bal_amt"
            await update.message.reply_text("পরিমাণ লিখুন:")
        except Exception:
            await update.message.reply_text("সঠিক User ID দিন।")
        return

    if await_key == "bal_amt":
        context.user_data.pop("await", None)
        try:
            amt = float(text)
            tid = int(context.user_data.get("bal_uid"))
            mode = context.user_data.get("bal_mode", "add")
            ensure_user(tid)
            conn = get_db()
            cur = conn.cursor()
            if mode == "add":
                cur.execute(
                    "UPDATE users SET balance = balance + ? WHERE user_id=?",
                    (amt, tid),
                )
            else:
                cur.execute(
                    "UPDATE users SET balance = MAX(0, balance - ?) WHERE user_id=?",
                    (amt, tid),
                )
            conn.commit()
            cur.execute("SELECT balance FROM users WHERE user_id=?", (tid,))
            bal = cur.fetchone()["balance"]
            conn.close()
            await update.message.reply_text(
                f"✅ User {tid} balance = {bal:.2f}",
                reply_markup=user_mgmt_kb(),
            )
        except Exception as e:
            await update.message.reply_text(str(e))
        return

    if await_key == "admin_add":
        context.user_data.pop("await", None)
        if not is_main(uid):
            return
        try:
            aid = int(text)
            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO admins (user_id, role, added_at) VALUES (?,?,?)",
                (aid, "admin", datetime.now().isoformat()),
            )
            conn.commit()
            conn.close()
            await update.message.reply_text(f"✅ Admin {aid}")
        except Exception as e:
            await update.message.reply_text(str(e))
        return

    if await_key == "admin_rm":
        context.user_data.pop("await", None)
        if not is_main(uid):
            return
        try:
            aid = int(text)
            if aid == MAIN_ADMIN_ID:
                await update.message.reply_text("Main সরানো যাবে না।")
                return
            conn = get_db()
            cur = conn.cursor()
            cur.execute("DELETE FROM admins WHERE user_id=?", (aid,))
            conn.commit()
            conn.close()
            await update.message.reply_text(f"Removed {aid}")
        except Exception as e:
            await update.message.reply_text(str(e))
        return

    if await_key == "set_support":
        context.user_data.pop("await", None)
        set_setting("support_username", text.lstrip("@"))
        await update.message.reply_text(f"✅ Support @{text.lstrip('@')}")
        return

    if await_key == "set_def_reward":
        context.user_data.pop("await", None)
        set_setting("default_reward", text)
        await update.message.reply_text(f"✅ default_reward = {text}")
        return

    if await_key == "set_welcome":
        context.user_data.pop("await", None)
        set_setting("welcome_text", text)
        await update.message.reply_text("✅ Welcome text saved")
        return

    if await_key == "set_otp":
        context.user_data.pop("await", None)
        if "|" not in text:
            await update.message.reply_text("Format: number|otp")
            return
        phone, otp = [x.strip() for x in text.split("|", 1)]
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "UPDATE numbers SET otp_text=? WHERE phone=? AND status='taken'",
            (otp, phone),
        )
        n = cur.rowcount
        if n == 0:
            cur.execute(
                "UPDATE numbers SET otp_text=? WHERE phone=?",
                (otp, phone),
            )
            n = cur.rowcount
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ OTP set for {phone} (rows={n})")
        return


    if await_key == "pnl_key":
        context.user_data.pop("await", None)
        pid = context.user_data.pop("pnl_id", None)
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE panels SET api_key=? WHERE id=?", (text.strip(), pid))
        conn.commit()
        cur.execute("SELECT name FROM panels WHERE id=?", (pid,))
        r = cur.fetchone()
        conn.close()
        await update.message.reply_text(
            "✅ %s API Key saved." % (r["name"] if r else pid),
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("📍 Panel Control", callback_data="adm_panel")]]
            ),
        )
        return

    if await_key == "pnl_add_name":
        context.user_data.pop("await", None)
        name = text.strip()[:40]
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO panels (name, api_key, is_enabled, sort_order) VALUES (?,?,1,99)",
                (name, ""),
            )
            conn.commit()
            await update.message.reply_text(
                "✅ Panel '%s' added. এখন Key সেট করুন।" % name,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("📍 Panel Control", callback_data="adm_panel")]]
                ),
            )
        except Exception as e:
            await update.message.reply_text("Error: %s" % e)
        conn.close()
        return

    if await_key == "broadcast":
        context.user_data.pop("await", None)
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users WHERE is_banned=0")
        users = [r["user_id"] for r in cur.fetchall()]
        conn.close()
        ok = fail = 0
        for u in users:
            try:
                await context.bot.send_message(u, f"📢 {text}")
                ok += 1
            except Exception:
                fail += 1
        await update.message.reply_text(f"Broadcast done. OK={ok} Fail={fail}")
        return

    await update.message.reply_text(
        "Admin: /start চাপুন অথবা মেনু ব্যবহার করুন।",
        reply_markup=main_kb(True),
    )


# ================== MAIN ==================
def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("ERROR: BOT_TOKEN সেট করুন (env বা ফাইলে)")
        return
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(check_join_cb, pattern=r"^check_join$"))
    app.add_handler(CallbackQueryHandler(get_number_cb, pattern=r"^get_number$"))
    app.add_handler(CallbackQueryHandler(take_svc_cb, pattern=r"^take_svc_\d+$"))
    app.add_handler(CallbackQueryHandler(search_otp_cb, pattern=r"^search_otp$"))
    app.add_handler(CallbackQueryHandler(support_cb, pattern=r"^support$"))
    app.add_handler(CallbackQueryHandler(back_main_cb, pattern=r"^back_main$"))
    app.add_handler(CallbackQueryHandler(admin_panel_cb, pattern=r"^admin_panel$"))

    app.add_handler(CallbackQueryHandler(adm_service_cb, pattern=r"^adm_service$"))
    app.add_handler(CallbackQueryHandler(svc_list_cb, pattern=r"^svc_list$"))
    app.add_handler(CallbackQueryHandler(svc_add_cb, pattern=r"^svc_add$"))
    app.add_handler(CallbackQueryHandler(svc_tog_cb, pattern=r"^svc_tog_\d+$"))
    app.add_handler(CallbackQueryHandler(svc_del_cb, pattern=r"^svc_del_\d+$"))
    app.add_handler(CallbackQueryHandler(svc_rew_cb, pattern=r"^svc_rew_\d+$"))
    app.add_handler(CallbackQueryHandler(num_add_cb, pattern=r"^num_add$"))
    app.add_handler(CallbackQueryHandler(num_svc_cb, pattern=r"^num_svc_\d+$"))
    app.add_handler(CallbackQueryHandler(num_list_cb, pattern=r"^num_list$"))

    app.add_handler(CallbackQueryHandler(adm_channel_cb, pattern=r"^adm_channel$"))
    app.add_handler(CallbackQueryHandler(ch_add_cb, pattern=r"^ch_add$"))
    app.add_handler(CallbackQueryHandler(ch_list_cb, pattern=r"^ch_list$"))
    app.add_handler(CallbackQueryHandler(ch_rm_cb, pattern=r"^ch_rm_\d+$"))

    app.add_handler(CallbackQueryHandler(adm_users_cb, pattern=r"^adm_users$"))
    app.add_handler(CallbackQueryHandler(um_today_cb, pattern=r"^um_today$"))
    app.add_handler(CallbackQueryHandler(um_status_cb, pattern=r"^um_status$"))
    app.add_handler(CallbackQueryHandler(um_ban_cb, pattern=r"^um_ban$"))
    app.add_handler(CallbackQueryHandler(um_unban_cb, pattern=r"^um_unban$"))
    app.add_handler(CallbackQueryHandler(um_banlist_cb, pattern=r"^um_banlist$"))
    app.add_handler(CallbackQueryHandler(um_addbal_cb, pattern=r"^um_addbal$"))
    app.add_handler(CallbackQueryHandler(um_rmbal_cb, pattern=r"^um_rmbal$"))

    app.add_handler(CallbackQueryHandler(adm_admins_cb, pattern=r"^adm_admins$"))
    app.add_handler(CallbackQueryHandler(admin_add_cb, pattern=r"^admin_add$"))
    app.add_handler(CallbackQueryHandler(admin_rm_cb, pattern=r"^admin_rm$"))

    app.add_handler(CallbackQueryHandler(adm_panel_cb, pattern=r"^adm_panel$"))
    app.add_handler(CallbackQueryHandler(tog_bot_cb, pattern=r"^tog_bot$"))
    app.add_handler(CallbackQueryHandler(broadcast_cb, pattern=r"^broadcast$"))
    app.add_handler(CallbackQueryHandler(adm_system_cb, pattern=r"^adm_system$"))
    app.add_handler(CallbackQueryHandler(set_support_cb, pattern=r"^set_support$"))
    app.add_handler(
        CallbackQueryHandler(set_def_reward_cb, pattern=r"^set_def_reward$")
    )
    app.add_handler(CallbackQueryHandler(set_welcome_cb, pattern=r"^set_welcome$"))
    app.add_handler(CallbackQueryHandler(set_otp_cb, pattern=r"^set_otp$"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Number bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

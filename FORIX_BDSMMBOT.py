#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Number Bot
- Bottom ReplyKeyboard menu
- Numbers ONLY from panels (API)
- Panel Control: ON/OFF + API Key + URLs
- Balance + Withdraw
Main Admin: 8289191009
"""

import asyncio
import json
import logging
import os
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, date
from typing import Optional, List, Dict, Any

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8938358982:AAEu-E6oTqKutr1825HUhM1YP6ceQYFCpb8")
MAIN_ADMIN_ID = 8289191009
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "number_bot.db")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

DEFAULT_PANELS = [
    "fastxotp", "voltxsms", "stexsms", "Zenex", "Miahsms", "NexaOTP", "Xeron",
]


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT, full_name TEXT,
            balance REAL DEFAULT 0, is_banned INTEGER DEFAULT 0,
            numbers_taken INTEGER DEFAULT 0, referrer_id INTEGER DEFAULT 0, lang TEXT DEFAULT 'bn', joined_at TEXT
        );
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY, role TEXT DEFAULT 'admin', added_at TEXT
        );
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL, code TEXT DEFAULT '',
            reward REAL DEFAULT 0.01, is_active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS panels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL, api_key TEXT DEFAULT '',
            api_url TEXT DEFAULT '', otp_url TEXT DEFAULT '',
            is_enabled INTEGER DEFAULT 1, sort_order INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS numbers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL, service_id INTEGER, panel_id INTEGER,
            panel_order_id TEXT, reward REAL DEFAULT 0,
            status TEXT DEFAULT 'active', taken_by INTEGER, taken_at TEXT,
            otp_text TEXT, rewarded INTEGER DEFAULT 0, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS force_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL, title TEXT, link TEXT, is_active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS withdraws (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, amount REAL, method TEXT, details TEXT,
            status TEXT DEFAULT 'pending', created_at TEXT
        );
    """)
    defaults = {
        "support_username": "", "bot_enabled": "1",
        "welcome_text": "Number Bot e welcome!\nPanel theke number nite parben.",
        "default_reward": "0.01", "min_withdraw": "10", "withdraw_enabled": "1", "otp_group": "",
        "ref_enabled": "1", "ref_pct": "10",
        "em_view": "⬇️", "em_change": "🔄", "em_back": "⚙️",

    }
    for k, v in defaults.items():
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    cur.execute(
        "INSERT OR IGNORE INTO admins (user_id, role, added_at) VALUES (?,?,?)",
        (MAIN_ADMIN_ID, "main", datetime.now().isoformat()),
    )
    for i, name in enumerate(DEFAULT_PANELS):
        cur.execute(
            "INSERT OR IGNORE INTO panels (name, api_key, is_enabled, sort_order) VALUES (?,?,1,?)",
            (name, "", i + 1),
        )
    for name, reward in [("WhatsApp", 0.01), ("Telegram", 0.02), ("Facebook", 0.05), ("Google", 0.03)]:
        cur.execute(
            "INSERT OR IGNORE INTO services (name, code, reward, is_active) VALUES (?,?,?,1)",
            (name, name.lower()[:8], reward),
        )
    try:
        cur.execute("ALTER TABLE users ADD COLUMN referrer_id INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE users ADD COLUMN lang TEXT DEFAULT 'bn'")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE numbers ADD COLUMN rewarded INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE numbers ADD COLUMN last_otp_id TEXT DEFAULT ''")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE panels ADD COLUMN otp_url TEXT DEFAULT ''")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE panels ADD COLUMN api_url TEXT DEFAULT ''")
    except Exception:
        pass
    conn.commit()
    conn.close()


def get_setting(key, default=""):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    r = cur.fetchone()
    conn.close()
    return r["value"] if r else default


def set_setting(key, value):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()


def ensure_user(uid, username=None, full_name=None):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id=?", (uid,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (user_id, username, full_name, joined_at) VALUES (?,?,?,?)",
            (uid, username or "", full_name or "", datetime.now().isoformat()),
        )
    else:
        cur.execute(
            "UPDATE users SET username=COALESCE(?,username), full_name=COALESCE(?,full_name) WHERE user_id=?",
            (username, full_name, uid),
        )
    conn.commit()
    conn.close()


def get_user(uid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    r = cur.fetchone()
    conn.close()
    return r


def is_admin(uid):
    if uid == MAIN_ADMIN_ID:
        return True
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM admins WHERE user_id=?", (uid,))
    r = cur.fetchone()
    conn.close()
    return bool(r)


def is_main(uid):
    return uid == MAIN_ADMIN_ID


def is_banned(uid):
    u = get_user(uid)
    return bool(u and u["is_banned"])


VOLTX_BASE = "https://api.2oo9.cloud/MXS47FLFX0U/tnevs/@public/api"


def _http(url, method="GET", headers=None, body=None, timeout=30):
    hdrs = {"User-Agent": "NumberBot/1.0", "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    data = None
    if body is not None:
        rawb = json.dumps(body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
        data = rawb
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            code = resp.getcode()
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return {
            "ok": False,
            "status": e.code,
            "error": "HTTP %s: %s" % (e.code, (err or e.reason)[:180]),
            "raw": err,
            "data": None,
        }
    except Exception as e:
        return {"ok": False, "status": 0, "error": str(e), "raw": "", "data": None}
    parsed = None
    try:
        parsed = json.loads(raw)
    except Exception:
        pass
    return {"ok": True, "status": code, "raw": raw, "data": parsed}


def is_voltx_panel(panel):
    name = (panel["name"] or "").lower()
    url = ((panel["api_url"] or "") + (panel["otp_url"] or "")).lower()
    return (
        "volt" in name
        or "2oo9.cloud" in url
        or "voltxsms" in url
        or (panel["api_key"] and not (panel["api_url"] or "").strip())
    )


def voltx_headers(api_key):
    return {"mauthapi": api_key.strip()}


def _rid_from_range(rng):
    s = str(rng or "").strip().upper().replace("X", "")
    s = "".join(ch for ch in s if ch.isdigit())
    return s


def voltx_pick_rid(api_key, service_code):
    res = _http(VOLTX_BASE + "/liveaccess", headers=voltx_headers(api_key))
    if not res.get("ok"):
        return None, res.get("error") or "liveaccess fail"
    data = (res.get("data") or {}).get("data") or res.get("data") or {}
    services = data.get("services") if isinstance(data, dict) else []
    want = (service_code or "").lower()
    rids = []
    for svc in services or []:
        sid = str(svc.get("sid") or "")
        ranges = svc.get("ranges") or []
        matched = (not want) or want in sid.lower() or sid.lower() in want
        if matched:
            for rng in ranges:
                rid = _rid_from_range(rng)
                if rid:
                    rids.append(rid)
    if not rids:
        for svc in services or []:
            for rng in svc.get("ranges") or []:
                rid = _rid_from_range(rng)
                if rid:
                    rids.append(rid)
    if not rids:
        return None, "liveaccess e range/rid pai nai"
    return rids, None


def voltx_get_number(api_key, service_code):
    key = (api_key or "").strip()
    if not key:
        return {"ok": False, "error": "API Key NOT SET"}
    rids, err = voltx_pick_rid(key, service_code)
    if err and not rids:
        # still try a POST without liveaccess — some accounts only need getnum
        rids = []
    last = err or "getnum fail"
    tried = list(rids or [])
    if not tried:
        tried = [""]  # last resort empty — API may reject
    for rid in tried:
        body = {"rid": rid} if rid else {}
        res = _http(
            VOLTX_BASE + "/getnum",
            method="POST",
            headers=voltx_headers(key),
            body=body,
        )
        if not res.get("ok"):
            last = res.get("error") or last
            # 401/403 stop immediately
            if res.get("status") in (401, 403):
                extra = " — Profile e API access ON koro, key thik kina dekho."
                return {"ok": False, "error": last + extra}
            continue
        payload = res.get("data") or {}
        meta = payload.get("meta") if isinstance(payload, dict) else {}
        data = payload.get("data") if isinstance(payload, dict) else None
        code = (meta or {}).get("code")
        if code not in (None, 200, "200") or not data:
            last = payload.get("message") or res.get("raw", "")[:180] or "no number"
            continue
        phone = (
            data.get("full_number")
            or data.get("no_plus_number")
            or data.get("national_number")
        )
        if phone:
            phone = str(phone).replace(" ", "")
            return {"ok": True, "phone": phone, "order_id": str(rid or data.get("rid") or "")}
        last = "response e number nai"
    return {"ok": False, "error": last}


def voltx_get_otp(api_key, phone):
    key = (api_key or "").strip()
    if not key:
        return {"ok": False, "error": "API Key NOT SET"}
    res = _http(VOLTX_BASE + "/success-otp", headers=voltx_headers(key))
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error") or "otp fail"}
    payload = res.get("data") or {}
    data = payload.get("data") if isinstance(payload, dict) else {}
    otps = (data or {}).get("otps") or []
    want = "".join(ch for ch in str(phone) if ch.isdigit())
    best = None
    best_id = ""
    for item in otps:
        num = "".join(ch for ch in str(item.get("number") or "") if ch.isdigit())
        msg = item.get("message") or ""
        matched = False
        if want and num:
            if want == num or want.endswith(num) or num.endswith(want):
                matched = True
            elif len(want) >= 8 and len(num) >= 8 and want[-8:] == num[-8:]:
                matched = True
        if matched and msg:
            best = msg
            best_id = str(item.get("otp_id") or item.get("time") or msg)
            break
    if not best:
        return {"ok": False, "error": "OTP ekhono ashe nai"}
    return {"ok": True, "otp": best, "otp_id": best_id}


def http_get(url, timeout=25):
    return _http(url, method="GET")


def panel_get_number(panel, service_code):
    key = (panel["api_key"] or "").strip()
    if not key:
        return {"ok": False, "error": "API Key NOT SET"}
    if is_voltx_panel(panel):
        return voltx_get_number(key, service_code)
    base = (panel["api_url"] or "").strip()
    if not base:
        return {"ok": False, "error": "Get Number URL set nai (Panel Control)"}
    url = (
        base.replace("{api_key}", urllib.parse.quote(key))
        .replace("{key}", urllib.parse.quote(key))
        .replace("{service}", urllib.parse.quote(service_code or ""))
    )
    if "api_key=" not in url.lower() and "{api_key}" not in base:
        sep = "&" if "?" in url else "?"
        url = "%s%sapi_key=%s&service=%s" % (
            url, sep, urllib.parse.quote(key), urllib.parse.quote(service_code or "")
        )
    try:
        res = http_get(url)
        if not res.get("ok"):
            return {"ok": False, "error": res.get("error") or "fail"}
        data = res.get("data") or {}
        raw = res.get("raw", "")
        phone = order_id = None
        if isinstance(data, dict):
            phone = data.get("number") or data.get("phone") or data.get("mobile") or data.get("Num")
            if not phone and isinstance(data.get("data"), dict):
                phone = data["data"].get("number") or data["data"].get("phone")
                order_id = data["data"].get("id") or data["data"].get("order_id")
            order_id = order_id or data.get("id") or data.get("order_id") or data.get("activationId")
        if not phone and raw:
            t = raw.strip().split()[0]
            if t.replace("+", "").isdigit() and len(t) >= 10:
                phone = t
        if not phone:
            return {"ok": False, "error": "Number ase nai: " + raw[:180]}
        return {"ok": True, "phone": str(phone), "order_id": str(order_id or "")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def panel_get_otp(panel, phone, order_id=""):
    key = (panel["api_key"] or "").strip()
    if not key:
        return {"ok": False, "error": "API Key NOT SET"}
    if is_voltx_panel(panel):
        return voltx_get_otp(key, phone)
    base = (panel["otp_url"] or "").strip()
    if not base:
        return {"ok": False, "error": "OTP URL set nai"}
    url = (
        base.replace("{api_key}", urllib.parse.quote(key))
        .replace("{key}", urllib.parse.quote(key))
        .replace("{phone}", urllib.parse.quote(phone))
        .replace("{number}", urllib.parse.quote(phone))
        .replace("{order_id}", urllib.parse.quote(order_id or ""))
    )
    try:
        res = http_get(url)
        if not res.get("ok"):
            return {"ok": False, "error": res.get("error") or "otp fail"}
        data = res.get("data") or {}
        raw = res.get("raw", "")
        otp = None
        if isinstance(data, dict):
            otp = data.get("otp") or data.get("code") or data.get("sms") or data.get("message")
            if not otp and isinstance(data.get("data"), dict):
                otp = data["data"].get("otp") or data["data"].get("code")
        if not otp:
            otp = raw.strip()[:200]
        return {"ok": True, "otp": str(otp)}
    except Exception as e:
        return {"ok": False, "error": str(e)}



def panel_tag(name):
    n = (name or "").strip()
    if not n:
        return "?"
    return n[0].upper()


def _panel_name(num_row):
    try:
        pid = num_row["panel_id"]
    except Exception:
        return ""
    if not pid:
        return ""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT name FROM panels WHERE id=?", (pid,))
    r = cur.fetchone()
    conn.close()
    return r["name"] if r else ""


def format_phone_line(phone, panel_name=""):
    tag = panel_tag(panel_name)
    if panel_name:
        return "📱 <code>%s</code>  <b>[%s]</b> %s" % (phone, tag, panel_name)
    return "📱 <code>%s</code>" % phone


def number_result_kb(svc_id, num_id):
    ev = get_setting("em_view") or "⬇️"
    ec = get_setting("em_change") or "🔄"
    eb = get_setting("em_back") or "⚙️"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("%s View OTP" % ev, callback_data="otp_%s" % num_id)],
        [
            InlineKeyboardButton("%s Change" % ec, callback_data="chg_%s_%s" % (svc_id, num_id)),
            InlineKeyboardButton("%s Back" % eb, callback_data="back_svc"),
        ],
    ])


async def send_otp_targets(bot, user_id, phone, otp_text, service_name="", panel_name=""):
    text = "📩 <b>OTP Received</b>\n%s\n🏷 %s\n\n%s" % (
        format_phone_line(phone, panel_name), service_name or "-", otp_text
    )
    try:
        await bot.send_message(user_id, text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.warning("otp user send fail: %s", e)
    grp = (get_setting("otp_group") or "").strip()
    if grp:
        chat = grp if grp.startswith("@") or grp.startswith("-") else ("@" + grp)
        try:
            await bot.send_message(chat, text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.warning("otp group send fail: %s", e)


def credit_otp_reward(num_id):
    """Credit once when OTP first arrives. Returns (credited: bool, amount, balance)."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM numbers WHERE id=?", (num_id,))
    num = cur.fetchone()
    if not num:
        conn.close()
        return False, 0, 0
    if int(num["rewarded"] or 0) == 1:
        cur.execute("SELECT balance FROM users WHERE user_id=?", (num["taken_by"],))
        row = cur.fetchone()
        conn.close()
        return False, 0, (row["balance"] if row else 0)
    amt = float(num["reward"] or 0)
    cur.execute("UPDATE numbers SET rewarded=1 WHERE id=? AND rewarded=0", (num_id,))
    if cur.rowcount == 0:
        conn.close()
        return False, 0, 0
    cur.execute(
        "UPDATE users SET balance = balance + ? WHERE user_id=?",
        (amt, num["taken_by"]),
    )
    cur.execute("SELECT balance FROM users WHERE user_id=?", (num["taken_by"],))
    bal = cur.fetchone()["balance"]
    conn.commit()
    conn.close()
    return True, amt, bal


def is_real_panel_otp(text):
    if not text:
        return False
    s = str(text).strip()
    low = s.lower()
    if any(x in low for x in ("ashe nai", "not found", "no otp", "ekhono", "এখনো", "fail", "error", "unauthorized")):
        return False
    digits = "".join(ch for ch in s if ch.isdigit())
    return len(digits) >= 4


def pay_referral(earner_id, base_amt):
    if get_setting("ref_enabled", "1") != "1":
        return
    try:
        pct = float(get_setting("ref_pct") or 0)
    except Exception:
        pct = 0
    if pct <= 0 or base_amt <= 0:
        return
    u = get_user(earner_id)
    if not u:
        return
    rid = int(u["referrer_id"] or 0) if "referrer_id" in u.keys() else 0
    if rid <= 0 or rid == earner_id:
        return
    commission = round(base_amt * pct / 100.0, 4)
    if commission <= 0:
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (commission, rid))
    conn.commit()
    conn.close()
    return rid, commission


async def apply_otp_if_new(bot, num_row, otp_text):
    if not is_real_panel_otp(otp_text):
        return False
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM numbers WHERE id=?", (num_row["id"],))
    num = cur.fetchone()
    if not num:
        conn.close()
        return False
    already = int(num["rewarded"] or 0) == 1
    old = (num["otp_text"] or "").strip()
    cur.execute("UPDATE numbers SET otp_text=? WHERE id=?", (otp_text, num["id"]))
    conn.commit()
    conn.close()
    if already:
        return True
    svc_name = ""
    conn = get_db()
    cur = conn.cursor()
    if num["service_id"]:
        cur.execute("SELECT name FROM services WHERE id=?", (num["service_id"],))
        s = cur.fetchone()
        svc_name = s["name"] if s else ""
    conn.close()
    pname = ""
    if num["panel_id"]:
        conn2 = get_db()
        c2 = conn2.cursor()
        c2.execute("SELECT name FROM panels WHERE id=?", (num["panel_id"],))
        pr = c2.fetchone()
        conn2.close()
        pname = pr["name"] if pr else ""
    await send_otp_targets(bot, num["taken_by"], num["phone"], otp_text, svc_name, pname)
    credited, amt, bal = credit_otp_reward(num["id"])
    if credited:
        try:
            await bot.send_message(
                num["taken_by"],
                "💰 OTP receive confirm — +%.2f | Balance: %.2f" % (amt, bal),
            )
        except Exception:
            pass
        ref = pay_referral(num["taken_by"], amt)
        if ref:
            rid, comm = ref
            try:
                await bot.send_message(rid, "🎁 Referral commission +%.2f (from %s)" % (comm, num["taken_by"]))
            except Exception:
                pass
    return True


async def watch_otp(bot, num_id):
    """Poll panel for ~2 minutes after number received."""
    try:
        for _ in range(24):
            await asyncio.sleep(5)
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT * FROM numbers WHERE id=?", (num_id,))
            num = cur.fetchone()
            panel = None
            if num and num["panel_id"]:
                cur.execute("SELECT * FROM panels WHERE id=?", (num["panel_id"],))
                panel = cur.fetchone()
            conn.close()
            if not num or not panel:
                return
            if int(num["rewarded"] or 0) == 1 and (num["otp_text"] or "").strip():
                return
            res = panel_get_otp(panel, num["phone"], num["panel_order_id"] or "")
            if res.get("ok") and res.get("otp") and "ashe nai" not in str(res.get("otp")).lower():
                if res["otp"] and not str(res["otp"]).startswith("এখনো"):
                    await apply_otp_if_new(bot, num, res["otp"])
                    return
    except Exception as e:
        logger.warning("watch_otp: %s", e)


def main_kb(admin=False):
    rows = [
        [KeyboardButton("👤 GET NUMBER"), KeyboardButton("💬 SEARCH OTP")],
        [KeyboardButton("💰 BALANCE"), KeyboardButton("💸 WITHDRAW")],
        [KeyboardButton("👥 REFER"), KeyboardButton("🌐 LANGUAGE")],
        [KeyboardButton("✈️ SUPPORT")],
    ]
    if admin:
        rows.append([KeyboardButton("📍 ADMIN PANEL")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def admin_kb():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📍 CHANNEL CONTROL"), KeyboardButton("💬 SERVICE CONTROL")],
            [KeyboardButton("🔔 PANEL CONTROL"), KeyboardButton("👑 ADMIN MANAGE")],
            [KeyboardButton("👤 USER MANAGEMENT"), KeyboardButton("📍 SYSTEM CONFIG")],
            [KeyboardButton("📥 WITHDRAW REQUESTS"), KeyboardButton("📢 BROADCAST")],
            [KeyboardButton("🏠 BACK TO MAIN")],
        ],
        resize_keyboard=True,
    )


def user_mgmt_kb():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📊 TODAY STATUS"), KeyboardButton("🔍 USER STATUS")],
            [KeyboardButton("🚫 BAN USER"), KeyboardButton("✅ UNBAN USER")],
            [KeyboardButton("📋 BAN LIST")],
            [KeyboardButton("➕ ADD BALANCE"), KeyboardButton("➖ REMOVE BALANCE")],
            [KeyboardButton("🔙 BACK TO ADMIN")],
        ],
        resize_keyboard=True,
    )


async def check_force_join(bot, user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM force_channels WHERE is_active=1")
    channels = cur.fetchall()
    conn.close()
    missing = []
    for ch in channels:
        raw = str(ch["chat_id"]).strip()
        try:
            cid = int(raw) if raw.lstrip("-").isdigit() else (raw if raw.startswith("@") else "@" + raw)
            m = await bot.get_chat_member(chat_id=cid, user_id=user_id)
            st = str(getattr(m.status, "name", m.status)).upper()
            if st not in ("MEMBER", "ADMINISTRATOR", "CREATOR", "OWNER"):
                missing.append(ch)
        except Exception:
            missing.append(ch)
    return missing


async def send_force_join(update, context, missing):
    buttons = []
    for ch in missing:
        link = ch["link"]
        if not link and ch["chat_id"] and not str(ch["chat_id"]).startswith("-"):
            link = "https://t.me/" + str(ch["chat_id"]).lstrip("@")
        title = ch["title"] or str(ch["chat_id"])
        if link:
            buttons.append([InlineKeyboardButton("Join " + title, url=link)])
    buttons.append([InlineKeyboardButton("✅ I Joined — Verify", callback_data="check_join")])
    await update.message.reply_text("⚠️ আগে চ্যানেল জয়েন করুন:", reply_markup=InlineKeyboardMarkup(buttons))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id, user.username, user.full_name)
    # referral: /start ref_123
    if context.args:
        arg = (context.args[0] or "").strip()
        if arg.startswith("ref_"):
            arg = arg[4:]
        try:
            rid = int(arg)
            if rid != user.id:
                conn = get_db()
                cur = conn.cursor()
                cur.execute("SELECT referrer_id FROM users WHERE user_id=?", (user.id,))
                row = cur.fetchone()
                current = int(row["referrer_id"] or 0) if row else 0
                if current == 0 and get_user(rid):
                    cur.execute("UPDATE users SET referrer_id=? WHERE user_id=?", (rid, user.id))
                    conn.commit()
                conn.close()
        except Exception:
            pass
    context.user_data.clear()
    if is_banned(user.id):
        await update.message.reply_text("🚫 আপনি ব্যান।")
        return
    if get_setting("bot_enabled", "1") != "1" and not is_admin(user.id):
        await update.message.reply_text("🔧 বট বন্ধ।")
        return
    missing = await check_force_join(context.bot, user.id)
    if missing and not is_admin(user.id):
        await send_force_join(update, context, missing)
        return
    u = get_user(user.id)
    welcome = get_setting("welcome_text") or "Welcome!"
    await update.message.reply_text(
        "%s\n\n👤 ID: <code>%s</code>\n💰 Balance: <b>%.2f</b>" % (welcome, user.id, u["balance"]),
        parse_mode=ParseMode.HTML,
        reply_markup=main_kb(is_admin(user.id)),
    )


async def check_join_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    missing = await check_force_join(context.bot, uid)
    if missing:
        await q.answer("এখনো জয়েন করেননি!", show_alert=True)
        return
    await q.edit_message_text("✅ Verified! নিচের মেনু ব্যবহার করুন।")
    u = get_user(uid)
    await context.bot.send_message(uid, "💰 Balance: %.2f" % u["balance"], reply_markup=main_kb(is_admin(uid)))


async def do_get_number(update, context):
    uid = update.effective_user.id
    if is_banned(uid):
        await update.message.reply_text("🚫 Banned")
        return
    missing = await check_force_join(context.bot, uid)
    if missing and not is_admin(uid):
        await send_force_join(update, context, missing)
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM panels WHERE is_enabled=1 AND api_key IS NOT NULL AND trim(api_key) != '' ORDER BY sort_order")
    panels = cur.fetchall()
    cur.execute("SELECT * FROM services WHERE is_active=1 ORDER BY name")
    services = cur.fetchall()
    conn.close()
    if not panels:
        await update.message.reply_text("❌ কোনো Panel ON নেই বা API Key সেট নেই।\nAdmin → PANEL CONTROL → Key দিন।")
        return
    if not services:
        await update.message.reply_text("❌ Service নেই। Admin → SERVICE CONTROL।")
        return
    buttons = [[InlineKeyboardButton("%s 🎁 %.2f" % (s["name"], s["reward"]), callback_data="gn_%s" % s["id"])] for s in services]
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_inline")])
    await update.message.reply_text("📱 কোন সার্ভিসের নাম্বার? (Panel API থেকে)", reply_markup=InlineKeyboardMarkup(buttons))


async def gn_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if is_banned(uid):
        await q.edit_message_text("Banned")
        return
    svc_id = int(q.data.split("_")[1])
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM services WHERE id=? AND is_active=1", (svc_id,))
    svc = cur.fetchone()
    cur.execute("SELECT * FROM panels WHERE is_enabled=1 AND api_key != '' AND trim(api_key) != '' ORDER BY sort_order")
    panels = cur.fetchall()
    conn.close()
    if not svc:
        await q.edit_message_text("Service নেই।")
        return
    if not panels:
        await q.edit_message_text("Panel/Key নেই।")
        return
    await q.edit_message_text("⏳ Panel থেকে নাম্বার আনা হচ্ছে...")
    last_err = "unknown"
    phone = order_id = None
    used_panel = None
    code = svc["code"] or svc["name"].lower()
    for panel in panels:
        res = panel_get_number(panel, code)
        if res.get("ok"):
            phone = res["phone"]
            order_id = res.get("order_id", "")
            used_panel = panel
            break
        last_err = res.get("error", "fail")
    if not phone:
        await q.edit_message_text("❌ নাম্বার পাওয়া যায়নি।\n%s\n\nAdmin: API Key + GetURL চেক করুন।" % last_err)
        return
    reward = float(svc["reward"] or 0)
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO numbers (phone, service_id, panel_id, panel_order_id, reward, status, taken_by, taken_at, otp_text, rewarded, created_at) VALUES (?,?,?,?,?,'active',?,?, '', 0, ?)",
        (phone, svc_id, used_panel["id"], order_id, reward, uid, datetime.now().isoformat(), datetime.now().isoformat()),
    )
    nid = cur.lastrowid
    cur.execute("UPDATE users SET numbers_taken = numbers_taken + 1 WHERE user_id=?", (uid,))
    conn.commit()
    conn.close()
    await q.edit_message_text(
        "✅ <b>Number Received</b>\n\n%s\n🏷 %s\n\nOTP এলে ব্যালেন্স পাবেন (%.2f)।\nনিচের বাটন ব্যবহার করুন।"
        % (format_phone_line(phone, used_panel["name"]), svc["name"], reward),
        parse_mode=ParseMode.HTML,
        reply_markup=number_result_kb(svc_id, nid),
    )
    asyncio.create_task(watch_otp(context.bot, nid))


async def do_search_otp(update, context):
    uid = update.effective_user.id
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT n.* FROM numbers n WHERE n.taken_by=? AND n.status='active' ORDER BY n.id DESC LIMIT 10",
        (uid,),
    )
    rows = cur.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("Active নাম্বার নেই। আগে GET NUMBER করুন।")
        return
    buttons = [[InlineKeyboardButton("OTP → %s" % r["phone"][-8:], callback_data="otp_%s" % r["id"])] for r in rows]
    await update.message.reply_text("কোন নাম্বারের OTP?", reply_markup=InlineKeyboardMarkup(buttons))


async def otp_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    nid = int(q.data.split("_")[1])
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM numbers WHERE id=? AND taken_by=?", (nid, uid))
    num = cur.fetchone()
    panel = None
    if num and num["panel_id"]:
        cur.execute("SELECT * FROM panels WHERE id=?", (num["panel_id"],))
        panel = cur.fetchone()
    conn.close()
    if not num:
        await q.edit_message_text("নাম্বার নেই।")
        return
    otp = num["otp_text"]
    if panel and (panel["api_key"] or "").strip():
        res = panel_get_otp(panel, num["phone"], num["panel_order_id"] or "")
        if res.get("ok") and res.get("otp"):
            otp = res["otp"]
            await apply_otp_if_new(context.bot, num, otp)
    if not otp:
        otp = "এখনো আসেনি — পরে চেষ্টা করুন।"
        await q.edit_message_text(
            "%s\n🔑 OTP: <b>%s</b>" % (format_phone_line(num["phone"], _panel_name(num)), otp),
            parse_mode=ParseMode.HTML,
            reply_markup=number_result_kb(num["service_id"] or 0, nid),
        )
        return
    await q.edit_message_text(
        "%s\n🔑 OTP:\n%s" % (format_phone_line(num["phone"], _panel_name(num)), otp),
        parse_mode=ParseMode.HTML,
        reply_markup=number_result_kb(num["service_id"] or 0, nid),
    )


async def do_balance(update, context):
    u = get_user(update.effective_user.id)
    await update.message.reply_text(
        "💰 <b>Balance:</b> %.2f\n📱 Taken: %s" % (u["balance"], u["numbers_taken"]),
        parse_mode=ParseMode.HTML,
        reply_markup=main_kb(is_admin(update.effective_user.id)),
    )


async def do_support(update, context):
    un = (get_setting("support_username") or "").strip().lstrip("@")
    if un:
        await update.message.reply_text(
            "🆘 Support",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💬 Contact Support", url="https://t.me/%s" % un)]]),
        )
    else:
        await update.message.reply_text("Support সেট নেই।")


async def do_withdraw(update, context):
    if get_setting("withdraw_enabled", "1") != "1":
        await update.message.reply_text("Withdraw বন্ধ।")
        return
    u = get_user(update.effective_user.id)
    try:
        mn = float(get_setting("min_withdraw") or 10)
    except Exception:
        mn = 10.0
    if u["balance"] < mn:
        await update.message.reply_text("মিন %.0f। আপনার: %.2f" % (mn, u["balance"]))
        return
    context.user_data["await"] = "wd_amount"
    await update.message.reply_text("💰 %.2f\nকত টাকা withdraw? (মিন %.0f)" % (u["balance"], mn))


async def show_admin(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin only")
        return
    await update.message.reply_text("🔐 <b>ADMIN PANEL</b>", parse_mode=ParseMode.HTML, reply_markup=admin_kb())


def panel_control_markup():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM panels ORDER BY sort_order, id")
    rows = cur.fetchall()
    conn.close()
    lines = ["📍 <b>PANEL CONTROL</b>\n"]
    buttons = []
    for r in rows:
        st = "ON" if r["is_enabled"] else "OFF"
        key = "SET" if (r["api_key"] or "").strip() else "NOT SET"
        dot = "🟢" if r["is_enabled"] else "🔴"
        lines.append("%s %s: <b>%s</b> | Key: <b>%s</b>" % (dot, r["name"], st, key))
        buttons.append([
            InlineKeyboardButton("%s Turn %s" % (dot, "OFF" if r["is_enabled"] else "ON") + " " + r["name"], callback_data="ptog_%s" % r["id"]),
            InlineKeyboardButton("🔑 %s Key" % r["name"], callback_data="pkey_%s" % r["id"]),
        ])
        buttons.append([
            InlineKeyboardButton("🌐 %s GetURL" % r["name"], callback_data="purl_%s" % r["id"]),
            InlineKeyboardButton("📩 %s OtpURL" % r["name"], callback_data="potp_%s" % r["id"]),
        ])
    lines.append("\n<i>API Key + GetURL সেট করলে number আসবে।</i>")
    buttons.append([InlineKeyboardButton("➕ Add Panel", callback_data="padd")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


async def show_panel_control(update, context):
    if not is_admin(update.effective_user.id):
        return
    text, kb = panel_control_markup()
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def ptog_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    pid = int(q.data.split("_")[1])
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE panels SET is_enabled = 1 - is_enabled WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    text, kb = panel_control_markup()
    try:
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception:
        pass


async def pkey_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    pid = int(q.data.split("_")[1])
    context.user_data["await"] = "panel_key"
    context.user_data["panel_id"] = pid
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT name FROM panels WHERE id=?", (pid,))
    r = cur.fetchone()
    conn.close()
    await q.edit_message_text("🔑 <b>%s</b> API Key এখন চ্যাটে পাঠান:" % (r["name"] if r else pid), parse_mode=ParseMode.HTML)


async def purl_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    pid = int(q.data.split("_")[1])
    context.user_data["await"] = "panel_url"
    context.user_data["panel_id"] = pid
    await q.edit_message_text(
        "🌐 Get Number URL পাঠান।\nPlaceholder: <code>{api_key}</code> <code>{service}</code>\n"
        "উদাহরণ:\n<code>https://host/api/get?api_key={api_key}&service={service}</code>",
        parse_mode=ParseMode.HTML,
    )


async def potp_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    pid = int(q.data.split("_")[1])
    context.user_data["await"] = "panel_otp_url"
    context.user_data["panel_id"] = pid
    await q.edit_message_text(
        "📩 OTP URL পাঠান।\n<code>{api_key}</code> <code>{phone}</code> <code>{order_id}</code>",
        parse_mode=ParseMode.HTML,
    )


async def padd_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    context.user_data["await"] = "panel_add"
    await q.edit_message_text("নতুন Panel নাম:")


async def back_svc_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM services WHERE is_active=1 ORDER BY name")
    services = cur.fetchall()
    conn.close()
    buttons = [[InlineKeyboardButton("%s 🎁 %.2f" % (s["name"], s["reward"]), callback_data="gn_%s" % s["id"])] for s in services]
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_inline")])
    await q.edit_message_text("📱 কোন সার্ভিসের নাম্বার?", reply_markup=InlineKeyboardMarkup(buttons))


async def chg_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    parts = q.data.split("_")
    # chg_{svc}_{nid}
    if len(parts) < 3:
        await q.edit_message_text("Invalid")
        return
    # reuse gn_cb by rewriting callback data
    q.data = "gn_%s" % parts[1]
    await gn_cb(update, context)


async def cancel_inline_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("বাতিল।")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await _handle_text(update, context)
    except Exception as e:
        logger.exception("handle_text")
        try:
            await update.message.reply_text("Error: %s" % e)
        except Exception:
            pass


async def _handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    ensure_user(uid, user.username, user.full_name)
    text = (update.message.text or "").strip()
    await_key = context.user_data.get("await")

    if is_banned(uid) and not is_admin(uid):
        await update.message.reply_text("🚫 Banned")
        return

    if await_key == "wd_amount":
        try:
            amt = float(text)
            mn = float(get_setting("min_withdraw") or 10)
            u = get_user(uid)
            if amt < mn:
                await update.message.reply_text("মিন %.0f" % mn)
                return
            if amt > u["balance"]:
                await update.message.reply_text("ব্যালেন্স কম।")
                return
            context.user_data["wd_amt"] = amt
            context.user_data["await"] = "wd_details"
            await update.message.reply_text("bKash/Nagad নাম্বার বা অ্যাকাউন্ট লিখুন:")
        except ValueError:
            await update.message.reply_text("সঠিক সংখ্যা।")
        return

    if await_key == "wd_details":
        context.user_data.pop("await", None)
        amt = float(context.user_data.pop("wd_amt", 0))
        details = text
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE users SET balance = balance - ? WHERE user_id=? AND balance >= ?", (amt, uid, amt))
        if cur.rowcount == 0:
            conn.close()
            await update.message.reply_text("কাটা যায়নি।")
            return
        cur.execute(
            "INSERT INTO withdraws (user_id, amount, method, details, status, created_at) VALUES (?,?,?,?, 'pending', ?)",
            (uid, amt, "manual", details, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()
        await update.message.reply_text(
            "✅ Withdraw request পাঠানো হয়েছে। Amount: %.2f" % amt,
            reply_markup=main_kb(is_admin(uid)),
        )
        try:
            await context.bot.send_message(MAIN_ADMIN_ID, "💸 WD User %s Amount %.2f\n%s" % (uid, amt, details))
        except Exception:
            pass
        return

    if await_key == "panel_key" and is_admin(uid):
        context.user_data.pop("await", None)
        pid = context.user_data.pop("panel_id", None)
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE panels SET api_key=? WHERE id=?", (text.strip(), pid))
        conn.commit()
        cur.execute("SELECT name FROM panels WHERE id=?", (pid,))
        r = cur.fetchone()
        conn.close()
        await update.message.reply_text("✅ %s API Key সেভ হয়েছে!" % (r["name"] if r else pid), reply_markup=admin_kb())
        return

    if await_key == "panel_url" and is_admin(uid):
        context.user_data.pop("await", None)
        pid = context.user_data.pop("panel_id", None)
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE panels SET api_url=? WHERE id=?", (text.strip(), pid))
        conn.commit()
        conn.close()
        await update.message.reply_text("✅ Get Number URL সেভ!", reply_markup=admin_kb())
        return

    if await_key == "panel_otp_url" and is_admin(uid):
        context.user_data.pop("await", None)
        pid = context.user_data.pop("panel_id", None)
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE panels SET otp_url=? WHERE id=?", (text.strip(), pid))
        conn.commit()
        conn.close()
        await update.message.reply_text("✅ OTP URL সেভ!", reply_markup=admin_kb())
        return

    if await_key == "panel_add" and is_admin(uid):
        context.user_data.pop("await", None)
        name = text.strip()[:40]
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO panels (name, api_key, is_enabled, sort_order) VALUES (?,?,1,50)", (name, ""))
            conn.commit()
            await update.message.reply_text("✅ Panel '%s' যোগ। এখন Key + URL সেট করুন।" % name, reply_markup=admin_kb())
        except Exception as e:
            await update.message.reply_text("Error: %s" % e)
        conn.close()
        return

    if await_key == "svc_add" and is_admin(uid):
        context.user_data.pop("await", None)
        parts = [x.strip() for x in text.split("|")]
        name = parts[0][:40]
        reward = float(parts[1]) if len(parts) > 1 else float(get_setting("default_reward") or 0.01)
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO services (name, code, reward, is_active) VALUES (?,?,?,1)", (name, name.lower()[:12], reward))
            conn.commit()
            await update.message.reply_text("✅ %s reward=%.2f" % (name, reward), reply_markup=admin_kb())
        except Exception as e:
            await update.message.reply_text(str(e))
        conn.close()
        return

    if await_key == "svc_reward" and is_admin(uid):
        context.user_data.pop("await", None)
        sid = context.user_data.pop("svc_id", None)
        try:
            val = float(text)
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE services SET reward=? WHERE id=?", (val, sid))
            conn.commit()
            conn.close()
            await update.message.reply_text("✅ reward=%.2f" % val, reply_markup=admin_kb())
        except Exception as e:
            await update.message.reply_text(str(e))
        return

    if await_key == "ch_add" and is_admin(uid):
        context.user_data.pop("await", None)
        raw = text.strip()
        title, link = raw, ""
        try:
            chat = await context.bot.get_chat(int(raw) if raw.lstrip("-").isdigit() else raw)
            title = chat.title or raw
            if getattr(chat, "username", None):
                link = "https://t.me/" + chat.username
        except Exception as e:
            await update.message.reply_text("⚠️ %s" % e)
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO force_channels (chat_id, title, link) VALUES (?,?,?)", (raw, title, link))
        conn.commit()
        conn.close()
        await update.message.reply_text("✅ %s" % title, reply_markup=admin_kb())
        return

    if await_key == "ban_id" and is_admin(uid):
        context.user_data.pop("await", None)
        try:
            tid = int(text)
            if tid == MAIN_ADMIN_ID:
                await update.message.reply_text("Main নয়।")
                return
            ensure_user(tid)
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (tid,))
            conn.commit()
            conn.close()
            await update.message.reply_text("🚫 %s" % tid, reply_markup=user_mgmt_kb())
        except Exception as e:
            await update.message.reply_text(str(e))
        return

    if await_key == "unban_id" and is_admin(uid):
        context.user_data.pop("await", None)
        try:
            tid = int(text)
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (tid,))
            conn.commit()
            conn.close()
            await update.message.reply_text("✅ %s" % tid, reply_markup=user_mgmt_kb())
        except Exception as e:
            await update.message.reply_text(str(e))
        return

    if await_key == "status_id" and is_admin(uid):
        context.user_data.pop("await", None)
        try:
            tid = int(text)
            u = get_user(tid)
            if not u:
                await update.message.reply_text("নেই")
                return
            await update.message.reply_text(
                "ID %s\n@%s\nBal %.2f\nTaken %s\nBan %s" % (u["user_id"], u["username"] or "-", u["balance"], u["numbers_taken"], u["is_banned"]),
                reply_markup=user_mgmt_kb(),
            )
        except Exception as e:
            await update.message.reply_text(str(e))
        return

    if await_key in ("addbal_id", "rmbal_id") and is_admin(uid):
        try:
            context.user_data["bal_uid"] = int(text)
            context.user_data["await"] = "bal_amt"
            await update.message.reply_text("পরিমাণ:")
        except Exception:
            await update.message.reply_text("User ID সংখ্যায়।")
        return

    if await_key == "bal_amt" and is_admin(uid):
        context.user_data.pop("await", None)
        try:
            amt = float(text)
            tid = int(context.user_data.get("bal_uid"))
            mode = context.user_data.get("bal_mode", "add")
            ensure_user(tid)
            conn = get_db()
            cur = conn.cursor()
            if mode == "add":
                cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amt, tid))
            else:
                cur.execute("UPDATE users SET balance = MAX(0, balance - ?) WHERE user_id=?", (amt, tid))
            conn.commit()
            cur.execute("SELECT balance FROM users WHERE user_id=?", (tid,))
            bal = cur.fetchone()["balance"]
            conn.close()
            await update.message.reply_text("✅ %s = %.2f" % (tid, bal), reply_markup=user_mgmt_kb())
        except Exception as e:
            await update.message.reply_text(str(e))
        return

    if await_key == "admin_add" and is_main(uid):
        context.user_data.pop("await", None)
        try:
            aid = int(text)
            conn = get_db()
            cur = conn.cursor()
            cur.execute("INSERT OR REPLACE INTO admins (user_id, role, added_at) VALUES (?,?,?)", (aid, "admin", datetime.now().isoformat()))
            conn.commit()
            conn.close()
            await update.message.reply_text("✅ Admin %s" % aid, reply_markup=admin_kb())
        except Exception as e:
            await update.message.reply_text(str(e))
        return

    if await_key == "admin_rm" and is_main(uid):
        context.user_data.pop("await", None)
        try:
            aid = int(text)
            if aid == MAIN_ADMIN_ID:
                await update.message.reply_text("Main নয়।")
                return
            conn = get_db()
            cur = conn.cursor()
            cur.execute("DELETE FROM admins WHERE user_id=?", (aid,))
            conn.commit()
            conn.close()
            await update.message.reply_text("Removed %s" % aid, reply_markup=admin_kb())
        except Exception as e:
            await update.message.reply_text(str(e))
        return

    if await_key == "set_support" and is_admin(uid):
        context.user_data.pop("await", None)
        set_setting("support_username", text.lstrip("@"))
        await update.message.reply_text("✅", reply_markup=admin_kb())
        return

    if await_key == "set_welcome" and is_admin(uid):
        context.user_data.pop("await", None)
        set_setting("welcome_text", text)
        await update.message.reply_text("✅", reply_markup=admin_kb())
        return

    if await_key == "set_min_wd" and is_admin(uid):
        context.user_data.pop("await", None)
        set_setting("min_withdraw", text)
        await update.message.reply_text("✅", reply_markup=admin_kb())
        return

    if await_key == "set_def_reward" and is_admin(uid):
        context.user_data.pop("await", None)
        set_setting("default_reward", text)
        await update.message.reply_text("✅", reply_markup=admin_kb())
        return

    if await_key == "set_otp_group" and is_admin(uid):
        context.user_data.pop("await", None)
        set_setting("otp_group", text.strip())
        await update.message.reply_text("✅ OTP Group saved: %s" % text.strip(), reply_markup=admin_kb())
        return
    if await_key == "set_ref_pct" and is_admin(uid):
        context.user_data.pop("await", None)
        set_setting("ref_pct", text.strip().replace("%", ""))
        await update.message.reply_text("✅ Refer %% saved", reply_markup=admin_kb())
        return
    if await_key == "set_emoji" and is_admin(uid):
        context.user_data.pop("await", None)
        parts = text.split()
        if len(parts) >= 3:
            set_setting("em_view", parts[0])
            set_setting("em_change", parts[1])
            set_setting("em_back", parts[2])
            await update.message.reply_text("✅ Emoji saved", reply_markup=admin_kb())
        else:
            await update.message.reply_text("৩টা ইমোজি দিন")
        return

    if await_key == "broadcast" and is_admin(uid):
        context.user_data.pop("await", None)
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users WHERE is_banned=0")
        users = [r["user_id"] for r in cur.fetchall()]
        conn.close()
        ok = fail = 0
        for u in users:
            try:
                await context.bot.send_message(u, "📢 " + text)
                ok += 1
            except Exception:
                fail += 1
        await update.message.reply_text("OK=%s Fail=%s" % (ok, fail), reply_markup=admin_kb())
        return

    # menus
    if text in ("👤 GET NUMBER", "GET NUMBER"):
        await do_get_number(update, context)
        return
    if text in ("💬 SEARCH OTP", "SEARCH OTP"):
        await do_search_otp(update, context)
        return
    if text in ("💰 BALANCE", "BALANCE"):
        await do_balance(update, context)
        return
    if text in ("💸 WITHDRAW", "WITHDRAW"):
        await do_withdraw(update, context)
        return
    if text in ("✈️ SUPPORT", "SUPPORT"):
        await do_support(update, context)
        return
    if text in ("👥 REFER", "REFER", "👥 রেফার"):
        me = await context.bot.get_me()
        link = "https://t.me/%s?start=ref_%s" % (me.username, uid)
        pct = get_setting("ref_pct") or "0"
        on = get_setting("ref_enabled", "1")
        await update.message.reply_text(
            "👥 <b>Referral</b>\nStatus: %s\nCommission: %s%% (lifetime OTP earnings)\n\nYour link:\n<code>%s</code>"
            % ("ON" if on == "1" else "OFF", pct, link),
            parse_mode=ParseMode.HTML,
        )
        return
    if text in ("🌐 LANGUAGE", "LANGUAGE", "🌐 ভাষা"):
        await update.message.reply_text(
            "ভাষা সিলেক্ট করুন:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("বাংলা", callback_data="lang_bn"),
                 InlineKeyboardButton("English", callback_data="lang_en")],
                [InlineKeyboardButton("हिन्दी", callback_data="lang_hi"),
                 InlineKeyboardButton("العربية", callback_data="lang_ar")],
            ]),
        )
        return
    if text in ("📍 ADMIN PANEL", "ADMIN PANEL") and is_admin(uid):
        await show_admin(update, context)
        return
    if text in ("🏠 BACK TO MAIN", "BACK TO MAIN"):
        context.user_data.clear()
        await update.message.reply_text("Main Menu", reply_markup=main_kb(is_admin(uid)))
        return
    if text in ("🔙 BACK TO ADMIN", "BACK TO ADMIN") and is_admin(uid):
        await show_admin(update, context)
        return

    if is_admin(uid):
        if text in ("🔔 PANEL CONTROL", "PANEL CONTROL"):
            await show_panel_control(update, context)
            return
        if text in ("💬 SERVICE CONTROL", "SERVICE CONTROL"):
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT * FROM services ORDER BY id")
            rows = cur.fetchall()
            conn.close()
            msg = "💬 <b>SERVICES</b>\n\n"
            buttons = []
            for r in rows:
                st = "✅" if r["is_active"] else "❌"
                msg += "#%s %s %s = %.2f\n" % (r["id"], st, r["name"], r["reward"])
                buttons.append([
                    InlineKeyboardButton("%s %s" % ("OFF" if r["is_active"] else "ON", r["name"]), callback_data="stog_%s" % r["id"]),
                    InlineKeyboardButton("Reward #%s" % r["id"], callback_data="srew_%s" % r["id"]),
                ])
            buttons.append([InlineKeyboardButton("➕ Add Service", callback_data="sadd")])
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons))
            return
        if text in ("📍 CHANNEL CONTROL", "CHANNEL CONTROL"):
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT * FROM force_channels")
            rows = cur.fetchall()
            conn.close()
            msg = "Force Channels\n\n"
            buttons = []
            for r in rows:
                msg += "#%s %s\n" % (r["id"], r["title"] or r["chat_id"])
                buttons.append([InlineKeyboardButton("🗑 #%s" % r["id"], callback_data="crm_%s" % r["id"])])
            buttons.append([InlineKeyboardButton("➕ Add Channel", callback_data="cadd")])
            await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(buttons))
            return
        if text in ("👤 USER MANAGEMENT", "USER MANAGEMENT"):
            await update.message.reply_text("👤 USER MANAGEMENT", reply_markup=user_mgmt_kb())
            return
        if text in ("📊 TODAY STATUS", "TODAY STATUS"):
            today = date.today().isoformat()
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) c FROM users")
            total = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) c FROM numbers WHERE taken_at LIKE ?", (today + "%",))
            taken = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) c FROM users WHERE is_banned=1")
            banned = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) c FROM withdraws WHERE status='pending'")
            wpend = cur.fetchone()["c"]
            conn.close()
            await update.message.reply_text("Users %s | Today nums %s | Ban %s | WD pending %s" % (total, taken, banned, wpend), reply_markup=user_mgmt_kb())
            return
        if text in ("🔍 USER STATUS", "USER STATUS"):
            context.user_data["await"] = "status_id"
            await update.message.reply_text("User ID:")
            return
        if text in ("🚫 BAN USER", "BAN USER"):
            context.user_data["await"] = "ban_id"
            await update.message.reply_text("Ban User ID:")
            return
        if text in ("✅ UNBAN USER", "UNBAN USER"):
            context.user_data["await"] = "unban_id"
            await update.message.reply_text("Unban User ID:")
            return
        if text in ("📋 BAN LIST", "BAN LIST"):
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT user_id, username FROM users WHERE is_banned=1 LIMIT 40")
            rows = cur.fetchall()
            conn.close()
            msg = "\n".join("%s @%s" % (r["user_id"], r["username"] or "-") for r in rows) or "খালি"
            await update.message.reply_text(msg, reply_markup=user_mgmt_kb())
            return
        if text in ("➕ ADD BALANCE", "ADD BALANCE"):
            context.user_data["await"] = "addbal_id"
            context.user_data["bal_mode"] = "add"
            await update.message.reply_text("User ID:")
            return
        if text in ("➖ REMOVE BALANCE", "REMOVE BALANCE"):
            context.user_data["await"] = "rmbal_id"
            context.user_data["bal_mode"] = "remove"
            await update.message.reply_text("User ID:")
            return
        if text in ("👑 ADMIN MANAGE", "ADMIN MANAGE"):
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT user_id, role FROM admins")
            rows = cur.fetchall()
            conn.close()
            msg = "Main: %s\n" % MAIN_ADMIN_ID
            for r in rows:
                msg += "%s (%s)\n" % (r["user_id"], r["role"])
            buttons = []
            if is_main(uid):
                buttons = InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Add Admin", callback_data="aadd")],
                    [InlineKeyboardButton("🗑 Remove Admin", callback_data="arm")],
                ])
            await update.message.reply_text(msg, reply_markup=buttons or admin_kb())
            return
        if text in ("📍 SYSTEM CONFIG", "SYSTEM CONFIG"):
            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton("Support Username", callback_data="cfg_support")],
                [InlineKeyboardButton("Welcome Text", callback_data="cfg_welcome")],
                [InlineKeyboardButton("Min Withdraw", callback_data="cfg_minwd")],
                [InlineKeyboardButton("Default Reward", callback_data="cfg_reward")],
                [InlineKeyboardButton("Bot ON/OFF", callback_data="cfg_bot")],
                [InlineKeyboardButton("Withdraw ON/OFF", callback_data="cfg_wd")],
                [InlineKeyboardButton("📩 OTP Group", callback_data="cfg_otpgrp")],
                [InlineKeyboardButton("🎁 Refer ON/OFF", callback_data="cfg_refon")],
                [InlineKeyboardButton("🎁 Refer %", callback_data="cfg_refpct")],
                [InlineKeyboardButton("😀 Button Emoji", callback_data="cfg_emoji")],
            ])
            await update.message.reply_text(
                "Support @%s\nMinWD %s\nReward %s\nBot %s WD %s\nOTP Group: %s"
                % (get_setting("support_username") or "-", get_setting("min_withdraw"), get_setting("default_reward"), get_setting("bot_enabled"), get_setting("withdraw_enabled"), get_setting("otp_group") or "-"),
                reply_markup=buttons,
            )
            return
        if text in ("📥 WITHDRAW REQUESTS", "WITHDRAW REQUESTS"):
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT * FROM withdraws WHERE status='pending' ORDER BY id DESC LIMIT 15")
            rows = cur.fetchall()
            conn.close()
            if not rows:
                await update.message.reply_text("Pending নেই।", reply_markup=admin_kb())
                return
            for w in rows:
                await update.message.reply_text(
                    "#%s User %s\nAmount %.2f\n%s" % (w["id"], w["user_id"], w["amount"], w["details"]),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("✅ Pay", callback_data="wdok_%s" % w["id"]),
                        InlineKeyboardButton("❌ Reject", callback_data="wdrj_%s" % w["id"]),
                    ]]),
                )
            return
        if text in ("📢 BROADCAST", "BROADCAST"):
            context.user_data["await"] = "broadcast"
            await update.message.reply_text("Broadcast টেক্সট:")
            return

    await update.message.reply_text("মেনু বাটন ব্যবহার করুন। /start", reply_markup=main_kb(is_admin(uid)))


async def sadd_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    context.user_data["await"] = "svc_add"
    await q.edit_message_text("Service নাম|reward\nযেমন: Instagram|0.05")


async def stog_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    sid = int(q.data.split("_")[1])
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE services SET is_active = 1 - is_active WHERE id=?", (sid,))
    conn.commit()
    conn.close()
    await q.answer("Toggled", show_alert=False)


async def srew_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    sid = int(q.data.split("_")[1])
    context.user_data["await"] = "svc_reward"
    context.user_data["svc_id"] = sid
    await q.edit_message_text("Service #%s নতুন reward:" % sid)


async def cadd_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    context.user_data["await"] = "ch_add"
    await q.edit_message_text("@username বা -100id:")


async def crm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    cid = int(q.data.split("_")[1])
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM force_channels WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    await q.edit_message_text("Removed")


async def aadd_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_main(q.from_user.id):
        await q.answer("Main only", show_alert=True)
        return
    context.user_data["await"] = "admin_add"
    await q.edit_message_text("New Admin User ID:")


async def arm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_main(q.from_user.id):
        await q.answer("Main only", show_alert=True)
        return
    context.user_data["await"] = "admin_rm"
    await q.edit_message_text("Remove Admin User ID:")


async def lang_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    code = q.data.split("_")[1]
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET lang=? WHERE user_id=?", (code, q.from_user.id))
    conn.commit()
    conn.close()
    names = {"bn": "বাংলা", "en": "English", "hi": "हिन्दी", "ar": "العربية"}
    await q.edit_message_text("✅ Language: %s" % names.get(code, code))


async def cfg_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    data = q.data
    if data == "cfg_support":
        context.user_data["await"] = "set_support"
        await q.edit_message_text("Support username:")
    elif data == "cfg_welcome":
        context.user_data["await"] = "set_welcome"
        await q.edit_message_text("Welcome text:")
    elif data == "cfg_minwd":
        context.user_data["await"] = "set_min_wd"
        await q.edit_message_text("Min withdraw:")
    elif data == "cfg_reward":
        context.user_data["await"] = "set_def_reward"
        await q.edit_message_text("Default reward:")
    elif data == "cfg_bot":
        cur = get_setting("bot_enabled", "1")
        set_setting("bot_enabled", "0" if cur == "1" else "1")
        await q.edit_message_text("bot_enabled=" + get_setting("bot_enabled"))
    elif data == "cfg_wd":
        cur = get_setting("withdraw_enabled", "1")
        set_setting("withdraw_enabled", "0" if cur == "1" else "1")
        await q.edit_message_text("withdraw_enabled=" + get_setting("withdraw_enabled"))
    elif data == "cfg_otpgrp":
        context.user_data["await"] = "set_otp_group"
        await q.edit_message_text(
            "OTP Group username বা chat id পাঠান।\n"
            "উদাহরণ: @myotpgroup  অথবা  -1001234567890\n"
            "বটকে সেই গ্রুপে Admin দিন।"
        )
    elif data == "cfg_refon":
        cur = get_setting("ref_enabled", "1")
        set_setting("ref_enabled", "0" if cur == "1" else "1")
        await q.edit_message_text("ref_enabled=" + get_setting("ref_enabled"))
    elif data == "cfg_refpct":
        context.user_data["await"] = "set_ref_pct"
        await q.edit_message_text("Referral commission percent (যেমন 10):")
    elif data == "cfg_emoji":
        context.user_data["await"] = "set_emoji"
        await q.edit_message_text(
            "৩টা ইমোজি স্পেস দিয়ে পাঠান:\nView Change Back\nযেমন: ⬇️ 🔄 ⚙️"
        )


async def wdok_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    wid = int(q.data.split("_")[1])
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM withdraws WHERE id=?", (wid,))
    w = cur.fetchone()
    if not w or w["status"] != "pending":
        conn.close()
        await q.edit_message_text("Already done")
        return
    cur.execute("UPDATE withdraws SET status='paid' WHERE id=?", (wid,))
    conn.commit()
    conn.close()
    await q.edit_message_text("✅ Paid #%s" % wid)
    try:
        await context.bot.send_message(w["user_id"], "✅ Withdraw %.2f paid।" % w["amount"])
    except Exception:
        pass


async def wdrj_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    wid = int(q.data.split("_")[1])
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM withdraws WHERE id=?", (wid,))
    w = cur.fetchone()
    if not w or w["status"] != "pending":
        conn.close()
        await q.edit_message_text("Already done")
        return
    cur.execute("UPDATE withdraws SET status='rejected' WHERE id=?", (wid,))
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (w["amount"], w["user_id"]))
    conn.commit()
    conn.close()
    await q.edit_message_text("❌ Rejected #%s — refund" % wid)
    try:
        await context.bot.send_message(w["user_id"], "❌ Withdraw reject। Balance ফেরত।")
    except Exception:
        pass


def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("ERROR: BOT_TOKEN সেট করুন")
        return
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(check_join_cb, pattern=r"^check_join$"))
    app.add_handler(CallbackQueryHandler(gn_cb, pattern=r"^gn_\d+$"))
    app.add_handler(CallbackQueryHandler(otp_cb, pattern=r"^otp_\d+$"))
    app.add_handler(CallbackQueryHandler(cancel_inline_cb, pattern=r"^cancel_inline$"))
    app.add_handler(CallbackQueryHandler(back_svc_cb, pattern=r"^back_svc$"))
    app.add_handler(CallbackQueryHandler(chg_cb, pattern=r"^chg_"))
    app.add_handler(CallbackQueryHandler(ptog_cb, pattern=r"^ptog_\d+$"))
    app.add_handler(CallbackQueryHandler(pkey_cb, pattern=r"^pkey_\d+$"))
    app.add_handler(CallbackQueryHandler(purl_cb, pattern=r"^purl_\d+$"))
    app.add_handler(CallbackQueryHandler(potp_cb, pattern=r"^potp_\d+$"))
    app.add_handler(CallbackQueryHandler(padd_cb, pattern=r"^padd$"))
    app.add_handler(CallbackQueryHandler(sadd_cb, pattern=r"^sadd$"))
    app.add_handler(CallbackQueryHandler(stog_cb, pattern=r"^stog_\d+$"))
    app.add_handler(CallbackQueryHandler(srew_cb, pattern=r"^srew_\d+$"))
    app.add_handler(CallbackQueryHandler(cadd_cb, pattern=r"^cadd$"))
    app.add_handler(CallbackQueryHandler(crm_cb, pattern=r"^crm_\d+$"))
    app.add_handler(CallbackQueryHandler(aadd_cb, pattern=r"^aadd$"))
    app.add_handler(CallbackQueryHandler(arm_cb, pattern=r"^arm$"))
    app.add_handler(CallbackQueryHandler(lang_cb, pattern=r"^lang_"))
    app.add_handler(CallbackQueryHandler(cfg_cb, pattern=r"^cfg_"))
    app.add_handler(CallbackQueryHandler(wdok_cb, pattern=r"^wdok_\d+$"))
    app.add_handler(CallbackQueryHandler(wdrj_cb, pattern=r"^wdrj_\d+$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    logger.info("Number bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

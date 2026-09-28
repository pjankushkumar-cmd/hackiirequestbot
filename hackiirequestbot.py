import logging
import json
import sys
import os
import sqlite3
import threading
import asyncio
import urllib.request
import base64
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ChatJoinRequestHandler, ContextTypes, MessageHandler, filters

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# =================== [ CRITICAL CONFIGURATION ] ===================
BOT_TOKEN = "8831391243:AAFNUMEngpQns6MQk3Hf9WZb9uBDuk_3mRw" 
ADMIN_ID = 8767998937 
# ===================================================================
# =================== GITHUB CONFIG ===================
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_OWNER = os.getenv("GITHUB_OWNER")
GITHUB_REPO = os.getenv("GITHUB_REPO")
GITHUB_FILE = os.getenv("GITHUB_FILE", "members.json")
# =====================================================

if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or ADMIN_ID == 123456789:
    print("\n❌ ERROR: Pehle apna BOT_TOKEN aur ADMIN_ID code me sahi se badlo!\n")
    sys.exit(1)

CACHED_MESSAGES = [] 

# --- WEB SERVER & ANTI-SLEEP ---
class HealthCheckServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Bot is Running 24/7 Deeply Active on Render!")

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckServer)
    logging.info(f"🟢 Web Server started successfully on port {port}")
    server.serve_forever()

def self_ping_loop():
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if not render_url: render_url = f"http://localhost:{os.environ.get('PORT', 8080)}"
    while True:
        try:
            import time
            time.sleep(15)
            if "localhost" not in render_url:
                req = urllib.request.Request(render_url, headers={'User-Agent': 'VIP-Hyper-Bot'})
                urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            logging.error(f"⚠️ Ping Note: {e}")

# --- DB, GITHUB & SYNC HELPERS ---
def init_db():
    global CACHED_MESSAGES
    conn = sqlite3.connect('janeman_pro.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS stats (key TEXT PRIMARY KEY, count INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS messages_list (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT, msg_id TEXT)''')
    cursor.execute("INSERT OR IGNORE INTO settings VALUES ('auto_accept', 'OFF')")
    cursor.execute("INSERT OR IGNORE INTO stats VALUES ('total_requests', 0)")
    cursor.execute("INSERT OR IGNORE INTO stats VALUES ('accepted', 0)")
    conn.commit()
    cursor.execute("SELECT chat_id, msg_id FROM messages_list ORDER BY id ASC")
    CACHED_MESSAGES = cursor.fetchall()
    conn.close()

def sync_users_to_github():
    if not all([GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO]): return
    try:
        users = get_all_users()
        content = json.dumps(users)
        content_encoded = base64.b64encode(content.encode()).decode()
        url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GITHUB_FILE}"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
        r = requests.get(url, headers=headers)
        sha = r.json().get("sha") if r.status_code == 200 else None
        data = {"message": "Update users list", "content": content_encoded, "sha": sha}
        
        response = requests.put(url, headers=headers, json=data)
        if response.status_code not in (200, 201):
            logging.error(f"GitHub Sync Failed: {response.text}")
            
    except Exception as e: logging.error(f"GitHub Sync Error: {e}")

def load_users_from_github():
    if not all([GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO]): return
    try:
        url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GITHUB_FILE}"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
        r = requests.get(url, headers=headers)
        if r.status_code != 200: return
        users = json.loads(base64.b64decode(r.json()["content"]).decode())
        conn = sqlite3.connect("janeman_pro.db")
        cursor = conn.cursor()
        for uid in users: cursor.execute("INSERT OR IGNORE INTO users VALUES (?)", (uid,))
        conn.commit()
        conn.close()
    except Exception as e: logging.error(f"GitHub Load Error: {e}")

def add_user(user_id):
    conn = sqlite3.connect("janeman_pro.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?)", (user_id,))
    conn.commit()
    conn.close()
    sync_users_to_github()

def get_all_users():
    conn = sqlite3.connect('janeman_pro.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

# --- DB HELPERS ---
def get_setting(key):
    conn = sqlite3.connect('janeman_pro.db')
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else "OFF"

def set_setting(key, value):
    conn = sqlite3.connect('janeman_pro.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def add_saved_message(chat_id, msg_id):
    global CACHED_MESSAGES
    conn = sqlite3.connect('janeman_pro.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO messages_list (chat_id, msg_id) VALUES (?, ?)", (str(chat_id), str(msg_id)))
    conn.commit()
    cursor.execute("SELECT chat_id, msg_id FROM messages_list ORDER BY id ASC")
    CACHED_MESSAGES = cursor.fetchall()
    conn.close()

def clear_saved_messages():
    global CACHED_MESSAGES
    conn = sqlite3.connect('janeman_pro.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages_list")
    conn.commit()
    CACHED_MESSAGES = []
    conn.close()

def get_stats():
    conn = sqlite3.connect('janeman_pro.db')
    cursor = conn.cursor()
    cursor.execute("SELECT key, count FROM stats")
    res = dict(cursor.fetchall())
    conn.close()
    return res

def update_stat(key, amount=1):
    conn = sqlite3.connect('janeman_pro.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE stats SET count = count + ? WHERE key=?", (amount, key))
    conn.commit()
    conn.close()

# --- UI & HANDLERS ---
def get_main_menu():
    stats = get_stats()
    total_users = len(get_all_users())
    keyboard = [
        [InlineKeyboardButton(f"📊 Total Requests: {stats.get('total_requests', 0)}", callback_data="none")],
        [InlineKeyboardButton(f"✅ Auto-Approved: {stats.get('accepted', 0)}", callback_data="none")],
        [InlineKeyboardButton(f"👥 Database Users: {total_users}", callback_data="none")],
        [InlineKeyboardButton("⚙️ Welcome Settings", callback_data="welcome_settings"), InlineKeyboardButton("📣 Broadcast Tool", callback_data="broadcast_tool")],
        [InlineKeyboardButton("🔄 Refresh Panel", callback_data="refresh_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_welcome_menu():
    auto_status = get_setting("auto_accept")
    status_emoji = "🟢 ON (Auto Accept)" if auto_status == "ON" else "🔴 OFF (Manual/No Accept)"
    total_saved = len(CACHED_MESSAGES)
    keyboard = [
        [InlineKeyboardButton(f"Status: {status_emoji}", callback_data="toggle_auto")],
        [InlineKeyboardButton(f"➕ Add Message / Media", callback_data="edit_welcome")],
        [InlineKeyboardButton(f"🗑️ Clear All Saved ({total_saved})", callback_data="clear_welcome")],
        [InlineKeyboardButton("👁️ Test Sequence Message", callback_data="test_msg")],
        [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="refresh_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def send_sequence_messages_instant(bot, chat_id):
    if not CACHED_MESSAGES: return
    for row in CACHED_MESSAGES:
        try: await bot.copy_message(chat_id=chat_id, from_chat_id=int(row[0]), message_id=int(row[1]))
        except Exception as e: logging.error(f"Fast Delivery skipped: {e}")

async def start(update, context):
    add_user(update.effective_user.id)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ APPROVE ME", callback_data="approve_me")]
    ])

    await update.message.reply_text(
        "VIP ME APPROVAL KLIYE NEECHE BUTTON PE TAP KARE 👇👇👇👇",
        reply_markup=keyboard
    )

    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text(
            "👑 **JANEMAN BOT V20** 👑",
            reply_markup=get_main_menu(),
            parse_mode="Markdown"
        )

async def handle_callbacks(update, context):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID: return
    await query.answer()
    if query.data == "refresh_main": await query.edit_message_text("👑 **JANEMAN BOT V20** 👑", reply_markup=get_main_menu(), parse_mode="Markdown")
    elif query.data == "welcome_settings": await query.edit_message_text("⚙️ **Settings**", reply_markup=get_welcome_menu(), parse_mode="Markdown")
    elif query.data == "toggle_auto":
        new_status = "OFF" if get_setting("auto_accept") == "ON" else "ON"
        set_setting("auto_accept", new_status)
        await query.edit_message_text(f"⚙️ Status: {new_status}", reply_markup=get_welcome_menu(), parse_mode="Markdown")
    elif query.data == "edit_welcome":
        context.user_data['state'] = 'waiting_welcome'
        await query.edit_message_text("📝 **Media bhejein...**")
    elif query.data == "clear_welcome":
        clear_saved_messages()
        await query.edit_message_text("🗑️ Cleared!", reply_markup=get_welcome_menu(), parse_mode="Markdown")
    elif query.data == "broadcast_tool":
        context.user_data['state'] = 'waiting_broadcast'
        await query.edit_message_text("📣 **Post bhejein broadcast ke liye:**")
    elif query.data == "test_msg":
        await send_sequence_messages_instant(context.bot, ADMIN_ID)

    elif query.data == "approve_me":
        await query.answer("✅ Approval request received!", show_alert=True)

async def content_handler(update, context):
    if update.effective_user.id != ADMIN_ID: return
    state = context.user_data.get('state')
    if state == 'waiting_welcome':
        add_saved_message(update.message.chat_id, update.message.message_id)
        await update.message.reply_text("✅ Cached!")
    elif state == 'waiting_broadcast':
        context.user_data['state'] = None
        users = get_all_users()
        for u_id in users:
            try: await context.bot.copy_message(chat_id=u_id, from_chat_id=update.message.chat_id, message_id=update.message.message_id)
            except: pass
        await update.message.reply_text("🏁 Broadcast Done!")

async def join_request_handler(update, context):
    request = update.chat_join_request
    if not request:
        return
        
    update_stat('total_requests', 1)
    add_user(request.from_user.id)
    await send_sequence_messages_instant(context.bot, request.from_user.id)
    if get_setting("auto_accept") == "ON":
        await context.bot.approve_chat_join_request(chat_id=request.chat.id, user_id=request.from_user.id)
        update_stat('accepted', 1)

def main():
    init_db()
    load_users_from_github()
    
    threading.Thread(target=run_health_server, daemon=True).start()
    threading.Thread(target=self_ping_loop, daemon=True).start()
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    app.add_handler(ChatJoinRequestHandler(join_request_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, content_handler))
    
    print("\n🟢 VIP HYPER-SPEED 24/7 ENGINE ONLINE 🟢\n")
    app.run_polling()

if __name__ == '__main__':
    main()
    

import logging
import sqlite3
import json
import sys
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ChatJoinRequestHandler, ContextTypes, MessageHandler, filters

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# =================== [ CRITICAL CONFIGURATION ] ===================
BOT_TOKEN = "8831391243:AAFNUMEngpQns6MQk3Hf9WZb9uBDuk_3mRw" 
ADMIN_ID = 8767998937 
# ===================================================================

if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or ADMIN_ID == 123456789:
    print("\n❌ ERROR: Pehle apna BOT_TOKEN aur ADMIN_ID code me sahi se badlo, tabhi admin panel chalega!\n")
    sys.exit(1)

# --- RENDER PORT BINDING CODES (DUMMY SERVER) ---
class HealthCheckServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Bot is Running Perfectly!")

def run_health_server():
    # Render PORT environment variable provide karta hai, default 8080 hai
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckServer)
    logging.info(f"🟢 Dummy Web Server started on port {port} for Render.")
    server.serve_forever()
# -------------------------------------------------

def init_db():
    conn = sqlite3.connect('final_pro_bot.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS stats (key TEXT PRIMARY KEY, count INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS messages_list (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        chat_id TEXT, 
                        msg_id TEXT,
                        media_type TEXT,
                        text_backup TEXT,
                        file_id_backup TEXT
                    )''')

    cursor.execute("INSERT OR IGNORE INTO settings VALUES ('auto_accept', 'OFF')")
    cursor.execute("INSERT OR IGNORE INTO stats VALUES ('total_requests', 0)")
    cursor.execute("INSERT OR IGNORE INTO stats VALUES ('accepted', 0)")
    conn.commit()
    conn.close()

def get_setting(key):
    conn = sqlite3.connect('final_pro_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else None

def set_setting(key, value):
    conn = sqlite3.connect('final_pro_bot.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def add_saved_message(chat_id, msg_id, media_type, text="", file_id=""):
    conn = sqlite3.connect('final_pro_bot.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO messages_list (chat_id, msg_id, media_type, text_backup, file_id_backup) VALUES (?, ?, ?, ?, ?)", 
                   (str(chat_id), str(msg_id), media_type, text, file_id))
    conn.commit()
    conn.close()

def clear_saved_messages():
    conn = sqlite3.connect('final_pro_bot.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages_list")
    conn.commit()
    conn.close()

def get_all_saved_messages():
    conn = sqlite3.connect('final_pro_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id, msg_id, media_type, text_backup, file_id_backup FROM messages_list ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def add_user(user_id):
    conn = sqlite3.connect('final_pro_bot.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect('final_pro_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

def get_stats():
    conn = sqlite3.connect('final_pro_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT key, count FROM stats")
    res = dict(cursor.fetchall())
    conn.close()
    return res

def update_stat(key, amount=1):
    conn = sqlite3.connect('final_pro_bot.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE stats SET count = count + ? WHERE key=?", (amount, key))
    conn.commit()
    conn.close()

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
    total_saved = len(get_all_saved_messages())
    keyboard = [
        [InlineKeyboardButton(f"Status: {status_emoji}", callback_data="toggle_auto")],
        [InlineKeyboardButton(f"➕ Add Message / Voice / Media", callback_data="edit_welcome")],
        [InlineKeyboardButton(f"🗑️ Clear All Saved ({total_saved})", callback_data="clear_welcome")],
        [InlineKeyboardButton("👁️ Test Sequence Message", callback_data="test_msg")],
        [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="refresh_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def send_sequence_messages(bot, chat_id, name_placeholder=None):
    saved_messages = get_all_saved_messages()
    
    if not saved_messages:
        await bot.send_message(chat_id=chat_id, text="👋 Aapki join request received ho gayi hai!")
        return

    for row in saved_messages:
        s_chat_id, s_msg_id, media_type, text_backup, file_id_backup = row
        try:
            await bot.copy_message(chat_id=chat_id, from_chat_id=int(s_chat_id), message_id=int(s_msg_id))
        except Exception as e:
            logging.error(f"Copy message failed in sequence, running fallback: {e}")
            try:
                text_content = text_backup.replace("{name}", name_placeholder) if name_placeholder else text_backup
                if media_type == "text" or not file_id_backup:
                    await bot.send_message(chat_id=chat_id, text=text_content, parse_mode="HTML")
                elif media_type == "photo":
                    await bot.send_photo(chat_id=chat_id, photo=file_id_backup, caption=text_content, parse_mode="HTML")
                elif media_type == "video":
                    await bot.send_video(chat_id=chat_id, video=file_id_backup, caption=text_content, parse_mode="HTML")
                elif media_type == "animation":
                    await bot.send_animation(chat_id=chat_id, animation=file_id_backup, caption=text_content, parse_mode="HTML")
                elif media_type == "voice":
                    await bot.send_voice(chat_id=chat_id, voice=file_id_backup, caption=text_content, parse_mode="HTML")
            except Exception as ex:
                logging.error(f"Complete fallback failed: {ex}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    if update.effective_user.id != ADMIN_ID:
        add_user(update.effective_user.id)
        return
        
    add_user(update.effective_user.id)
    await update.message.reply_text("👑 **PRO Admin Control Panel v4 (Render Ready)** 👑\n\nAapka swagat hai admin! Sabhi functions niche se control karein:", reply_markup=get_main_menu(), parse_mode="Markdown")

async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or query.from_user.id != ADMIN_ID:
        await query.answer("Access Denied!", show_alert=True)
        return
    await query.answer()

    if query.data == "refresh_main":
        await query.edit_message_text("👑 **PRO Admin Control Panel v4** 👑\n\nAapka swagat hai admin! Sabhi functions niche se control karein:", reply_markup=get_main_menu(), parse_mode="Markdown")

    elif query.data == "welcome_settings":
        auto_status = get_setting("auto_accept")
        total_saved = len(get_all_saved_messages())
        text = f"⚙️ **Welcome Sequence Settings**\n\n🔄 Auto Accept Status: **{auto_status}**\n📦 Total Messages Added in Sequence: **{total_saved}**\n\n📌 *Aap ek se zyada Voice Notes, Photos, Videos ya Texts line-by-line add kar sakte hain.*"
        await query.edit_message_text(text, reply_markup=get_welcome_menu(), parse_mode="Markdown")

    elif query.data == "toggle_auto":
        current = get_setting("auto_accept")
        set_setting("auto_accept", "ON" if current == "OFF" else "OFF")
        auto_status = get_setting("auto_accept")
        total_saved = len(get_all_saved_messages())
        text = f"⚙️ **Welcome Sequence Settings**\n\n🔄 Auto Accept Status: **{auto_status}**\n📦 Total Messages Added in Sequence: **{total_saved}**"
        await query.edit_message_text(text, reply_markup=get_welcome_menu(), parse_mode="Markdown")

    elif query.data == "edit_welcome":
        context.user_data['state'] = 'waiting_welcome'
        await query.edit_message_text("📝 **Apna Welcome Message/Voice Note/Media bhejein:**\n\nJo bhi message sequence me add karna hai bhejein. Rokne ke liye `/start` likhein.")

    elif query.data == "clear_welcome":
        clear_saved_messages()
        auto_status = get_setting("auto_accept")
        text = f"🗑️ **Saare saved messages delete kar diye gaye hain!**\n\n🔄 Auto Accept Status: **{auto_status}**\n📦 Total Messages Added in Sequence: **0**"
        await query.edit_message_text(text, reply_markup=get_welcome_menu(), parse_mode="Markdown")

    elif query.data == "broadcast_tool":
        context.user_data['state'] = 'waiting_broadcast'
        await query.edit_message_text("📣 **Broadcast Post bhejein:**\n\nJo bhi post sabhi users ko bhejni hai, use send karein. Cancel ke liye /start likhein.")

    elif query.data == "test_msg":
        await query.message.reply_text("🔄 *Test sequence aapko niche deliver kiya ja raha hai...*")
        try:
            await send_sequence_messages(context.bot, ADMIN_ID, name_placeholder=query.from_user.first_name)
        except Exception as e:
            await query.message.reply_text(f"❌ Error: {e}")

async def content_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_ID:
        return
    state = context.user_data.get('state')
    if not state:
        return

    text = update.message.caption_html if update.message.caption else update.message.text_html
    if not text: text = ""
    file_id, media_type = None, "text"

    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        media_type = "photo"
    elif update.message.video:
        file_id = update.message.video.file_id
        media_type = "video"
    elif update.message.animation:
        file_id = update.message.animation.file_id
        media_type = "animation"
    elif update.message.document:
        file_id = update.message.document.file_id
        media_type = "document"
    elif update.message.audio:
        file_id = update.message.audio.file_id
        media_type = "audio"
    elif update.message.voice:
        file_id = update.message.voice.file_id
        media_type = "voice"

    if state == 'waiting_welcome':
        add_saved_message(update.message.chat_id, update.message.message_id, media_type, text, file_id)
        total_saved = len(get_all_saved_messages())
        await update.message.reply_text(f"✅ Message sequence mein add ho gaya! (Total Added: {total_saved})")

    elif state == 'waiting_broadcast':
        context.user_data['state'] = None
        users = get_all_users()
        await update.message.reply_text(f"🚀 Broadcast Shuru! Total Users: {len(users)}")
        s, f = 0, 0
        for u_id in users:
            try:
                await context.bot.copy_message(chat_id=u_id, from_chat_id=update.message.chat_id, message_id=update.message.message_id)
                s += 1
            except Exception: 
                f += 1
        await update.message.reply_text(f"🏁 Broadcast Complete!\n\n✅ Pass: {s}\n❌ Fail: {f}")

async def join_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    request = update.chat_join_request
    chat = request.chat
    user = request.from_user

    update_stat('total_requests', 1)
    add_user(user.id)

    auto_mode = get_setting("auto_accept")

    if auto_mode == "ON":
        try:
            await context.bot.approve_chat_join_request(chat_id=chat.id, user_id=user.id)
            update_stat('accepted', 1)
            await send_sequence_messages(context.bot, user.id, name_placeholder=user.first_name)
        except Exception as e:
            logging.error(f"Error in auto_accept: {e}")
    else:
        try:
            await send_sequence_messages(context.bot, user.id, name_placeholder=user.first_name)
        except Exception as e:
            logging.error(f"Error in manual_accept notification: {e}")

def main():
    init_db()
    
    # Render background Server ko alag thread me start kiya
    threading.Thread(target=run_health_server, daemon=True).start()
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    app.add_handler(ChatJoinRequestHandler(join_request_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, content_handler))
    
    print("\n🟢 RENDER COMPATIBLE BOT STARTED! 🟢\n")
    app.run_polling()

if __name__ == '__main__':
    main()
          

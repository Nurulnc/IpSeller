import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, PhotoSize
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, ConversationHandler, filters
)

# === তোমার তথ্য ===
TOKEN = "7308877263:AAEuz6pumYmjbeMyJ76GBYGJVvnDLXiubY4"
ADMIN_ID = 1651695602

# Conversation states for deposit
WAITING_SCREENSHOT, WAITING_TRXID, WAITING_AMOUNT = range(3)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def init_db():
    conn = sqlite3.connect('proxy_bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    balance INTEGER DEFAULT 0
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS proxies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_port TEXT UNIQUE,
                    username TEXT,
                    password TEXT,
                    sold INTEGER DEFAULT 0
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS deposits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount INTEGER,
                    trxid TEXT,
                    status TEXT DEFAULT 'pending',
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS purchases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    proxy TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )''')
    conn.commit()
    conn.close()

# Helper functions
def get_balance(user_id):
    conn = sqlite3.connect('proxy_bot.db')
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def add_user(user_id, username):
    conn = sqlite3.connect('proxy_bot.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, balance) VALUES (?, ?, 0)", (user_id, username))
    conn.commit()
    conn.close()

def get_available_proxies():
    conn = sqlite3.connect('proxy_bot.db')
    c = conn.cursor()
    c.execute("SELECT ip_port, username, password FROM proxies WHERE sold = 0")
    rows = c.fetchall()
    conn.close()
    return rows

def mark_proxy_sold(ip_port):
    conn = sqlite3.connect('proxy_bot.db')
    c = conn.cursor()
    c.execute("UPDATE proxies SET sold = 1 WHERE ip_port = ?", (ip_port,))
    conn.commit()
    conn.close()

def get_pending_deposits():
    conn = sqlite3.connect('proxy_bot.db')
    c = conn.cursor()
    c.execute("SELECT id, user_id, amount, trxid FROM deposits WHERE status = 'pending'")
    rows = c.fetchall()
    conn.close()
    return rows

# Start command & main menu
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id, user.username)

    keyboard = [
        [InlineKeyboardButton("💰 Balance", callback_data="balance")],
        [InlineKeyboardButton("🛒 Buy Proxy", callback_data="buy")],
        [InlineKeyboardButton("💸 Deposit", callback_data="deposit")],
        [InlineKeyboardButton("📦 My Proxies", callback_data="my_proxies")],
    ]
    if user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    text = f"🌟 স্বাগতম {user.first_name}!\n\n🏠 Residential Proxy Shop\n💎 ১ প্রক্সি = ১ টাকা (১ পয়েন্ট)\n\nকি করতে চাও? 👇"

    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)
    else:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)

# Button handler
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "balance":
        bal = get_balance(user_id)
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back")]]
        await query.edit_message_text(
            f"💰 তোমার ব্যালেন্স: `{bal}` পয়েন্ট (টাকা)\n\nপ্রক্সি কিনতে Balance ব্যবহার করো!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    elif data == "my_proxies":
        conn = sqlite3.connect('proxy_bot.db')
        c = conn.cursor()
        c.execute("SELECT proxy, timestamp FROM purchases WHERE user_id = ? ORDER BY id DESC LIMIT 20", (user_id,))
        rows = c.fetchall()
        conn.close()
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back")]]
        if not rows:
            await query.edit_message_text(
                "📦 তুমি এখনো কোনো প্রক্সি কেনোনি।\n\nBuy Proxy থেকে কিনো!",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        text = "📦 তোমার কেনা প্রক্সিগুলো (সাম্প্রতিক ২০টি):\n\n"
        for proxy, time in rows:
            text += f"• `{proxy}`\n  _{time[:16]}_\n\n"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data == "buy":
        proxies = get_available_proxies()
        if not proxies:
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back")]]
            await query.edit_message_text(
                "😞 বর্তমানে স্টকে কোনো প্রক্সি নেই।\n\nAdmin কে বলো নতুন স্টক যোগ করতে!",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        keyboard = [
            [InlineKeyboardButton("১টি কিনুন – ১ টাকা", callback_data="buy_1")],
            [InlineKeyboardButton("৫টি কিনুন – ৫ টাকা", callback_data="buy_5")],
            [InlineKeyboardButton("১০টি কিনুন – ১০ টাকা", callback_data="buy_10")],
            [InlineKeyboardButton("🔙 Back", callback_data="back")],
        ]
        await query.edit_message_text(
            f"🛒 স্টকে {len(proxies)}টি প্রক্সি আছে!\n\nকতগুলো প্রক্সি কিনবে?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("buy_"):
        count = int(data.split("_")[1])
        bal = get_balance(user_id)
        if bal < count:
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back")]]
            await query.edit_message_text(
                f"❌ অপর্যাপ্ত ব্যালেন্স!\n\n💰 দরকার: {count} Tk\n💳 আছে: {bal} Tk\n\nDeposit করে আবার চেষ্টা করো!",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        proxies = get_available_proxies()[:count]
        if len(proxies) < count:
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back")]]
            await query.edit_message_text(
                f"😞 স্টকে {len(proxies)}টির বেশি প্রক্সি নেই।\n\nআরও কম কিনো!",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        result = "✅ সফলভাবে কেনা হয়েছে!\n\n📋 তোমার প্রক্সিগুলো:\n\n"
        for ip_port, username, pwd in proxies:
            proxy_str = f"http://{username}:{pwd}@{ip_port}" if username and pwd else ip_port
            result += f"• `{proxy_str}`\n"
            mark_proxy_sold(ip_port)

            conn = sqlite3.connect('proxy_bot.db')
            c = conn.cursor()
            c.execute("INSERT INTO purchases (user_id, proxy) VALUES (?, ?)", (user_id, proxy_str))
            conn.commit()
            conn.close()

        # Deduct balance
        conn = sqlite3.connect('proxy_bot.db')
        c = conn.cursor()
        c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (count, user_id))
        conn.commit()
        conn.close()

        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back")]]
        await query.edit_message_text(
            result + f"\n💸 {count} টাকা কাটা হয়েছে।\n\nএগুলো কপি করে সেভ করো!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    elif data == "back":
        await start(query, context)

    elif data == "admin" and user_id == ADMIN_ID:
        keyboard = [
            [InlineKeyboardButton("📥 Pending Deposits", callback_data="pending_deposits")],
            [InlineKeyboardButton("➕ Add Proxies", callback_data="add_proxies_admin")],
            [InlineKeyboardButton("📊 Stats", callback_data="stats")],
            [InlineKeyboardButton("🔙 Back", callback_data="back")],
        ]
        await query.edit_message_text(
            "⚙️ Admin Panel\n\nকোন অপশন চুজ করবেন?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "pending_deposits" and user_id == ADMIN_ID:
        deposits = get_pending_deposits()
        if not deposits:
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin")]]
            await query.edit_message_text(
                "✅ কোনো পেন্ডিং ডিপোজিট নেই।",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        keyboard = []
        for dep_id, uid, amt, trx in deposits:
            keyboard.append([InlineKeyboardButton(f"✅ Approve {amt}Tk - {uid} ({trx[:8]}...)", callback_data=f"approve_dep_{dep_id}")])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin")])
        text = f"📥 Pending Deposits ({len(deposits)}টি):\n\nApprove করতে বাটন চাপো।"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("approve_dep_") and user_id == ADMIN_ID:
        dep_id = data.split("_")[2]
        conn = sqlite3.connect('proxy_bot.db')
        c = conn.cursor()
        c.execute("SELECT user_id, amount FROM deposits WHERE id=? AND status='pending'", (dep_id,))
        row = c.fetchone()
        if row:
            uid, amt = row
            c.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amt, uid))
            c.execute("UPDATE deposits SET status='approved' WHERE id=?", (dep_id,))
            conn.commit()
            await context.bot.send_message(uid, f"✅ তোমার {amt} Tk এর ডিপোজিট অ্যাপ্রুভ হয়েছে!\n\nব্যালেন্সে +{amt} পয়েন্ট যোগ হয়েছে।")
            await query.edit_message_text(f"✅ {amt} Tk অ্যাপ্রুভ করা হয়েছে User {uid} এর জন্য।")
        conn.close()

    elif data == "add_proxies_admin" and user_id == ADMIN_ID:
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin")]]
        await query.edit_message_text(
            "➕ প্রক্সি যোগ করতে /addproxies কমান্ড টাইপ করো।\n\nফরম্যাট:\n`ip:port` অথবা `ip:port:user:pass`\n\nএক লাইনে একটা করে পাঠাও।",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    elif data == "stats" and user_id == ADMIN_ID:
        conn = sqlite3.connect('proxy_bot.db')
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        c.execute("SELECT SUM(balance) FROM users")
        total_balance = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM proxies WHERE sold=0")
        stock = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM purchases")
        total_sales = c.fetchone()[0]
        conn.close()
        text = f"📊 Stats:\n\n👥 Total Users: {total_users}\n💰 Total Balance: {total_balance} Tk\n📦 Stock: {stock} Proxies\n🛒 Total Sales: {total_sales}"
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# Deposit conversation
async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "💸 Deposit করতে নিচের নাম্বারে Send Money করো:\n\n"
        "📱 বিকাশ/Nagad: `01815243007` (তোমার নাম্বার দাও)\n\n"
        "✅ পেমেন্ট করার পর স্ক্রিনশট এখানে পাঠাও →",
        parse_mode='Markdown'
    )
    return WAITING_SCREENSHOT

async def received_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
    elif update.message.document:
        file_id = update.message.document.file_id
    else:
        await update.message.reply_text("❌ শুধু ছবি/স্ক্রিনশট পাঠাও। টেক্সট নয়।")
        return WAITING_SCREENSHOT

    context.user_data['screenshot'] = file_id
    await update.message.reply_text("✅ ধন্যবাদ! এখন Transaction ID দাও (যেটা পেমেন্টের সময় পেয়েছ):")
    return WAITING_TRXID

async def received_trxid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    trxid = update.message.text.strip()
    if not trxid:
        await update.message.reply_text("❌ খালি Transaction ID দিতে পারো না। আবার পাঠাও।")
        return WAITING_TRXID
    context.user_data['trxid'] = trxid
    await update.message.reply_text("✅ এখন বলো কত টাকা পাঠিয়েছ? (শুধু সংখ্যা লিখো, যেমন: 500)")
    return WAITING_AMOUNT

async def received_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text.strip())
        if amount < 50:
            await update.message.reply_text("❌ ন্যূনতম ৫০ টাকা। আবার লিখো।")
            return WAITING_AMOUNT
    except ValueError:
        await update.message.reply_text("❌ শুধু সংখ্যা লিখো (যেমন: 500)।")
        return WAITING_AMOUNT

    user = update.effective_user
    screenshot = context.user_data['screenshot']
    trxid = context.user_data['trxid']

    # Save request
    conn = sqlite3.connect('proxy_bot.db')
    c = conn.cursor()
    c.execute("INSERT INTO deposits (user_id, amount, trxid) VALUES (?, ?, ?)", (user.id, amount, trxid))
    conn.commit()
    conn.close()

    # Notify admin with photo
    keyboard = [[InlineKeyboardButton(f"✅ Approve {amount} Tk", callback_data=f"approve_{user.id}_{amount}")]]
    try:
        await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=screenshot,
            caption=f"🔔 New Deposit Request!\n\n👤 User: {user.full_name} (@{user.username or 'N/A'})\n🆔 ID: `{user.id}`\n💰 Amount: {amount} Tk\n📄 TrxID: `{trxid}`\n⏰ Time: {context.bot.get_me().date}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except:
        await context.bot.send_message(
            ADMIN_ID,
            f"🔔 New Deposit (Screenshot Error)!\n\n{user.full_name} ({user.id})\n{amount} Tk\nTrx: {trxid}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    await update.message.reply_text(
        f"✅ তোমার {amount} Tk এর ডিপোজিট রিকোয়েস্ট গ্রহণ করা হয়েছে!\n\n"
        "⏳ অ্যাডমিন চেক করে অ্যাপ্রুভ করলে পয়েন্ট ব্যালেন্সে যোগ হবে। ধন্যবাদ! 🙏"
    )
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ ডিপোজিট প্রসেস বাতিল করা হয়েছে। /start দিয়ে আবার শুরু করো।")
    context.user_data.clear()
    return ConversationHandler.END

# Admin: Add proxies command
async def add_proxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ তুমি অ্যাডমিন নও।")
        return
    await update.message.reply_text(
        "➕ প্রক্সি যোগ করো। প্রতি লাইনে একটা করে পাঠাও:\n\n"
        "ফরম্যাট ১: `123.45.67.89:8080`\n"
        "ফরম্যাট ২: `123.45.67.89:8080:user123:pass456`\n\n"
        "একসাথে অনেকগুলো পাঠাতে পারো (লাইন বাই লাইন)।",
        parse_mode='Markdown'
    )
    context.user_data['adding_proxies'] = True

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('adding_proxies') and update.effective_user.id == ADMIN_ID:
        lines = update.message.text.strip().split('\n')
        added = 0
        skipped = 0
        conn = sqlite3.connect('proxy_bot.db')
        c = conn.cursor()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            parts = line.split(':')
            if len(parts) < 2:
                skipped += 1
                continue
            ip = parts[0]
            port = parts[1]
            ip_port = f"{ip}:{port}"
            username = password = None
            if len(parts) == 4:
                username = parts[2]
                password = parts[3]
            try:
                c.execute("INSERT OR IGNORE INTO proxies (ip_port, username, password) VALUES (?, ?, ?)",
                          (ip_port, username, password))
                if c.rowcount > 0:
                    added += 1
                else:
                    skipped += 1
            except Exception as e:
                skipped += 1
                logger.error(f"Error adding proxy: {e}")
        conn.commit()
        conn.close()

        text = f"✅ {added} টি নতুন প্রক্সি স্টকে যোগ হয়েছে!\n"
        if skipped > 0:
            text += f"⚠️ {skipped} টি স্কিপ হয়েছে (ফরম্যাট ভুল)।"
        text += "\n\nআরও যোগ করতে আবার পাঠাও। /cancel লিখে বন্ধ করো।"
        await update.message.reply_text(text)
        return

    # Cancel if /cancel
    if update.message.text == '/cancel' and context.user_data.get('adding_proxies'):
        context.user_data['adding_proxies'] = False
        await update.message.reply_text("❌ প্রক্সি যোগানো বন্ধ করা হয়েছে।")
        return

def main():
    init_db()
    app = Application.builder().token(TOKEN).build()

    # Deposit conversation
    deposit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(deposit_start, pattern="^deposit$")],
        states={
            WAITING_SCREENSHOT: [MessageHandler(filters.PHOTO | filters.Document.ALL, received_screenshot)],
            WAITING_TRXID: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_trxid)],
            WAITING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_amount)],
        },
        fallbacks=[CommandHandler("cancel", cancel_deposit)],
    )

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addproxies", add_proxies))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(deposit_conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("🚀 Bot চালু হয়েছে! চেক করো /start দিয়ে।")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

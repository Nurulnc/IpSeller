import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# === CONFIG ===
TOKEN = "7308877263:AAEuz6pumYmjbeMyJ76GBYGJVvnDLXiubY4"  # <<<< এখানে তোমার বটের টোকেন দিবি (@BotFather থেকে)
ADMIN_ID = 1651695602  # <<<< তোমার টেলিগ্রাম আইডি দে (admin হিসেবে)

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Database init
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

# === Helper Functions ===
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
    proxies = c.fetchall()
    conn.close()
    return proxies

def mark_proxy_sold(ip_port):
    conn = sqlite3.connect('proxy_bot.db')
    c = conn.cursor()
    c.execute("UPDATE proxies SET sold = 1 WHERE ip_port = ?", (ip_port,))
    conn.commit()
    conn.close()

# === Handlers ===
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
    await update.message.reply_text(
        f"🌟 স্বাগতম {user.first_name}!\n\n"
        "এটি একটি Residential Proxy Selling Bot\n"
        "১টি প্রক্সি = ১ টাকা (১ পয়েন্ট)\n\n"
        "নিচে থেকে অপশন বেছে নিন 👇",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "balance":
        bal = get_balance(user_id)
        await query.edit_message_text(f"💰 তোমার ব্যালেন্স: {bal} পয়েন্ট (টাকা)")

    elif query.data == "buy":
        proxies = get_available_proxies()
        if not proxies:
            await query.edit_message_text("😞 বর্তমানে কোনো প্রক্সি স্টকে নেই। পরে চেক করো।")
            return

        keyboard = []
        keyboard.append([InlineKeyboardButton("১টি কিনুন (১ টাকা)", callback_data="buy_1")])
        keyboard.append([InlineKeyboardButton("৫টি কিনুন (৫ টাকা)", callback_data="buy_5")])
        keyboard.append([InlineKeyboardButton("১০টি কিনুন (১০ টাকা)", callback_data="buy_10")])
        keyboard.append([InlineKeyboardButton("🔙 পিছনে", callback_data="back")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("🛒 কতগুলো প্রক্সি কিনবে?", reply_markup=reply_markup)

    elif query.data.startswith("buy_"):
        count = int(query.data.split("_")[1])
        bal = get_balance(user_id)
        if bal < count:
            await query.edit_message_text(f"❌ অপর্যাপ্ত ব্যালেন্স! দরকার: {count} টাকা, আছে: {bal} টাকা")
            return

        proxies = get_available_proxies()[:count]
        if len(proxies) < count:
            await query.edit_message_text("😞 এতগুলো প্রক্সি স্টকে নেই।")
            return

        result = "✅ সফলভাবে কেনা হয়েছে!\n\nতোমার প্রক্সিগুলো:\n\n"
        for ip_port, user, pwd in proxies:
            proxy_str = f"http://{user}:{pwd}@{ip_port}" if user and pwd else ip_port
            result += f"`{proxy_str}`\n"
            mark_proxy_sold(ip_port)

            # Save purchase
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

        await query.edit_message_text(result + f"\n💸 ব্যালেন্স কাটা হয়েছে: {count} টাকা", parse_mode='Markdown')

    elif query.data == "deposit":
        await query.edit_message_text(
            "💸 ডিপোজিট করতে চাইলে নিচের মাধ্যমে টাকা পাঠাও এবং স্ক্রিনশট/ট্রানজেকশন আইডি দিয়ে /deposit <amount> লিখে পাঠাও।\n\n"
            "উদাহরণ: `/deposit 500`\n\n"
            "বিকাশ/নগদ/রকেট: 01xxxxxxxxx (Personal)\n"
            "অ্যাডমিন অ্যাপ্রুভ করলে পয়েন্ট যোগ হয়ে যাবে।",
            parse_mode='Markdown'
        )

    elif query.data == "my_proxies":
        conn = sqlite3.connect('proxy_bot.db')
        c = conn.cursor()
        c.execute("SELECT proxy, timestamp FROM purchases WHERE user_id = ? ORDER BY timestamp DESC LIMIT 20", (user_id,))
        rows = c.fetchall()
        conn.close()

        if not rows:
            await query.edit_message_text("📦 তোমার কোনো প্রক্সি কেনা হয়নি এখনো।")
            return

        text = "📦 তোমার কেনা প্রক্সিগুলো (সাম্প্রতিক ২০টি):\n\n"
        for proxy, time in rows:
            text += f"`{proxy}` - {time[:10]}\n"
        await query.edit_message_text(text, parse_mode='Markdown')

    elif query.data == "admin" and user_id == ADMIN_ID:
        keyboard = [
            [InlineKeyboardButton("📥 Pending Deposits", callback_data="pending_deposits")],
            [InlineKeyboardButton("➕ Add Proxies", callback_data="add_proxies")],
            [InlineKeyboardButton("📊 Stats", callback_data="stats")],
            [InlineKeyboardButton("🔙 Back", callback_data="back")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("⚙️ অ্যাডমিন প্যানেল", reply_markup=reply_markup)

    elif query.data == "pending_deposits" and user_id == ADMIN_ID:
        conn = sqlite3.connect('proxy_bot.db')
        c = conn.cursor()
        c.execute("SELECT id, user_id, amount FROM deposits WHERE status='pending'")
        rows = c.fetchall()
        conn.close()

        if not rows:
            await query.edit_message_text("✅ কোনো পেন্ডিং ডিপোজিট নেই।")
            return

        keyboard = []
        for dep_id, uid, amt in rows:
            keyboard.append([InlineKeyboardButton(f"✅ Approve {amt} Tk - {uid}", callback_data=f"approve_{dep_id}")])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("📥 পেন্ডিং ডিপোজিটস:", reply_markup=reply_markup)

    elif query.data.startswith("approve_") and user_id == ADMIN_ID:
        dep_id = query.data.split("_")[1]
        conn = sqlite3.connect('proxy_bot.db')
        c = conn.cursor()
        c.execute("SELECT user_id, amount FROM deposits WHERE id=?", (dep_id,))
        row = c.fetchone()
        if row:
            uid, amt = row
            c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amt, uid))
            c.execute("UPDATE deposits SET status='approved' WHERE id=?", (dep_id,))
            conn.commit()
            await context.bot.send_message(uid, f"✅ তোমার {amt} টাকার ডিপোজিট অ্যাপ্রুভ হয়েছে! ব্যালেন্সে যোগ হয়েছে।")
        conn.close()
        await query.edit_message_text("✅ ডিপোজিট অ্যাপ্রুভ করা হয়েছে।")

    elif query.data == "back":
        await start(query, context)  # restart start menu

# Deposit command (user sends /deposit 500)
async def deposit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("❌ ব্যবহার: /deposit <amount>\nউদাহরণ: /deposit 500")
        return
    try:
        amount = int(context.args[0])
        if amount < 50:
            await update.message.reply_text("❌ ন্যূনতম ৫০ টাকা")
            return
    except:
        await update.message.reply_text("❌ সঠিক পরিমাণ দাও")
        return

    user_id = update.effective_user.id
    conn = sqlite3.connect('proxy_bot.db')
    c = conn.cursor()
    c.execute("INSERT INTO deposits (user_id, amount) VALUES (?, ?)", (user_id, amount))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ ডিপোজিট রিকোয়েস্ট পাঠানো হয়েছে: {amount} টাকা\n"
        "অ্যাডমিন অ্যাপ্রুভ করলে পয়েন্ট যোগ হয়ে যাবে।"
    )
    await context.bot.send_message(ADMIN_ID, f"🔔 নতুন ডিপোজিট রিকোয়েস্ট!\nUser: {user_id}\nAmount: {amount} Tk\n/deposit টাইপ করে চেক করো।")

# Admin: Add proxies manually (text file or message)
async def add_proxies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    await update.message.reply_text(
        "প্রক্সি যোগ করতে একেক লাইনে একটা করে পাঠাও। ফরম্যাট:\n"
        "ip:port\n"
        "অথবা\n"
        "ip:port:user:pass\n\n"
        "উদাহরণ:\n"
        "123.45.67.89:8080:user123:pass456"
    )
    context.user_data['adding_proxies'] = True

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('adding_proxies') and update.effective_user.id == ADMIN_ID:
        lines = update.message.text.strip().split('\n')
        added = 0
        conn = sqlite3.connect('proxy_bot.db')
        c = conn.cursor()
        for line in lines:
            line = line.strip()
            if not line: continue
            parts = line.split(':')
            if len(parts) == 2:
                ip_port, = parts
                username = password = None
            elif len(parts) == 4:
                ip_port, _, username, password = parts
            else:
                continue

            try:
                c.execute("INSERT OR IGNORE INTO proxies (ip_port, username, password) VALUES (?, ?, ?)",
                          (ip_port, username, password))
                added += 1
            except:
                pass
        conn.commit()
        conn.close()

        await update.message.reply_text(f"✅ {added} টি প্রক্সি স্টকে যোগ করা হয়েছে!")
        context.user_data['adding_proxies'] = False

def main():
    init_db()
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("deposit", deposit_command))
    app.add_handler(CommandHandler("addproxies", add_proxies_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot চালু হয়েছে...")
    app.run_polling()

if __name__ == '__main__':
    main()

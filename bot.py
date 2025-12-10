import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

# Start command & main menu
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id, user.username)

    keyboard = [
        [InlineKeyboardButton("💰 Balance", callback_data="balance")],
        [InlineKeyboardButton("🛒 Buy Proxy", callback_data="buy")],
        [InlineKeyboardButton("💵 Deposit", callback_data="deposit")],
        [InlineKeyboardButton("📦 My Proxies", callback_data="my_proxies")],
    ]
    if user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("Admin Panel", callback_data="admin")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    text = f"স্বাগতম {user.first_name}!\n\nResidential Proxy Shop\n১ প্রক্সি = ১ টাকা (১ পয়েন্ট)\n\nকি করতে চাও?"

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
        await query.edit_message_text(f"তোমার ব্যালেন্স: {bal} পয়েন্ট (টাকা)")

    elif data == "my_proxies":
        conn = sqlite3.connect('proxy_bot.db')
        c = conn.cursor()
        c.execute("SELECT proxy, timestamp FROM purchases WHERE user_id = ? ORDER BY id DESC LIMIT 20", (user_id,))
        rows = c.fetchall()
        conn.close()
        if not rows:
            await query.edit_message_text("তুমি এখনো কোনো প্রক্সি কেনোনি।")
            return
        text = "তোমার কেনা প্রক্সিগুলো:\n\n"
        for proxy, time in rows:
            text += f"`{proxy}`\n"
        await query.edit_message_text(text, parse_mode='Markdown')

    elif data == "buy":
        proxies = get_available_proxies()
        if not proxies:
            await query.edit_message_text("বর্তমানে স্টকে কোনো প্রক্সি নেই। পরে চেক করো।")
            return
        keyboard = [
            [InlineKeyboardButton("১টি কিনুন – ১ টাকা", callback_data="buy_1")],
            [InlineKeyboardButton("৫টি কিনুন – ৫ টাকা", callback_data="buy_5")],
            [InlineKeyboardButton("১০টি কিনুন – ১০ টাকা", callback_data="buy_10")],
            [InlineKeyboardButton("পিছনে", callback_data="back")],
        ]
        await query.edit_message_text("কতগুলো প্রক্সি কিনবে?", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("buy_"):
        count = int(data.split("_")[1])
        bal = get_balance(user_id)
        if bal < count:
            await query.edit_message_text(f"অপর্যাপ্ত ব্যালেন্স!\nদরকার: {count} Tk, আছে: {bal} Tk")
            return

        proxies = get_available_proxies()[:count]
        if len(proxies) < count:
            await query.edit_message_text("এতগুলো প্রক্সি এখন স্টকে নেই।")
            return

        result = "সফলভাবে কেনা হয়েছে!\n\nতোমার প্রক্সিগুলো:\n\n"
        for ip_port, user, pwd in proxies:
            proxy_str = f"http://{user}:{pwd}@{ip_port" if user and pwd else ip_port
            result += f"`{proxy_str}`\n"
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

        await query.edit_message_text(result + f"\n{bundle} টাকা কাটা হয়েছে।", parse_mode='Markdown')

    elif data == "back":
        await start(query, context)

    # Admin approve deposit
    elif data.startswith("approve_"):
        parts = data.split("_")
        target_user_id = int(parts[1])
        amount = int(parts[2])

        conn = sqlite3.connect('proxy_bot.db')
        c = conn.cursor()
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target_user_id))
        c.execute("UPDATE deposits SET status = 'approved' WHERE user_id = ? AND amount = ? AND status = 'pending'",
                  (target_user_id, amount))
        conn.commit()
        conn.close()

        await context.bot.send_message(target_user_id, f"তোমার {amount} Tk এর ডিপোজিট অ্যাপ্রুভ হয়েছে! ব্যালেন্সে যোগ হয়েছে।")
        await query.edit_message_caption(caption=query.message.caption + f"\n\nApproved | +{amount} Point")

# Deposit conversation
async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Deposit করতে নিচের নাম্বারে বিকাশ করো:\n\n"
        "বিকাশ: `01815243007` (তোমার নাম্বার দে)\n\n"
        "পেমেন্ট করার পর স্ক্রিনশট এখানে পাঠাও →",
        parse_mode='Markdown'
    )
    return WAITING_SCREENSHOT

async def received_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
    elif update.message.document:
        file_id = update.message.document.file_id
    else:
        await update.message.reply_text("শুধু ছবি/স্ক্রিনশট পাঠাও।")
        return WAITING_SCREENSHOT

    context.user_data['screenshot'] = file_id
    await update.message.reply_text("ধন্যবাদ! এখন Transaction ID দাও:")
    return WAITING_TRXID

async def received_trxid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['trxid'] = update.message.text.strip()
    await update.message.reply_text("কত টাকা পাঠিয়েছ? (শুধু সংখ্যা লিখো)")
    return WAITING_AMOUNT

async def received_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text.strip())
        if amount < 50:
            await update.message.reply_text("ন্যূনতম ৫০ টাকা। আবার লিখো।")
            return WAITING_AMOUNT
    except:
        await update.message.reply_text("শুধু সংখ্যা লিখো।")
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

    # Notify admin
    keyboard = [[InlineKeyboardButton(f"Approve {amount} Tk", callback_data=f"approve_{user.id}_{amount}")]]
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=screenshot,
        caption=f"New Deposit!\n\n"
                f"User: {user.full_name} (@{user.username or 'N/A'})\n"
                f"ID: `{user.id}`\n"
                f"Amount: {amount} Tk\n"
                f"TrxID: `{trxid}`",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    await update.message.reply_text(f"{amount} Tk এর রিকোয়েস্ট পাঠানো হয়েছে। অ্যাডমিন অ্যাপ্রুভ করলে পয়েন্ট যোগ হবে।")
    context.user_data.clear()
    return ConversationHandler.END

# Admin: Add proxies
async def add_proxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "প্রক্সি যোগ করো। এক লাইনে একটা:\n"
        "ip:port\n"
        "অথবা\n"
        "ip:port:user:pass"
    )
    context.user_data['adding'] = True

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('adding') and update.effective_user.id == ADMIN_ID:
        lines = update.message.text.strip().split('\n')
        added = 0
        conn = sqlite3.connect('proxy_bot.db')
        c = conn.cursor()
        for line in lines:
            line = line.strip()
            if not line: continue
            parts = line.split(':')
            if len(parts) == 2:
                ip_port, = parts[0] + ':' + parts[1]
                user = pwd = None
            elif len(parts) == 4:
                ip_port = parts[0] + ':' + parts[1]
                user, pwd = parts[2], parts[3]
            else:
                continue
            c.execute("INSERT OR IGNORE INTO proxies (ip_port, username, password) VALUES (?, ?, ?)",
                      (ip_port, user, pwd))
            added += c.rowcount
        conn.commit()
        conn.close()
        await update.message.reply_text(f"{added} টি প্রক্সি যোগ হয়েছে!")
        context.user_data['adding'] = False

def main():
    init_db()
    app = Application.builder().token(TOKEN).build()

    # Deposit conversation
    deposit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(deposit_start, pattern="^deposit$")],
        states={
            WAITING_SCREENSHOT: [MessageHandler(filters.PHOTO | filters.DOCUMENT, received_screenshot)],
            WAITING_TRXID: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_trxid)],
            WAITING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_amount)],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(deposit_conv)
    app.add_handler(CommandHandler("addproxies", add_proxies))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Bot চালু হয়েছে! @তোমারবটইউজারনেম")
    app.run_polling()

if __name__ == '__main__':
    main()

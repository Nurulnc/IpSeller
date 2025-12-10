import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, ConversationHandler, filters
)

TOKEN = "7308877263:AAEuz6pumYmjbeMyJ76GBYGJVvnDLXiubY4"
ADMIN_ID = 1651695602

WAITING_SCREENSHOT, WAITING_TRXID, WAITING_AMOUNT = range(3)

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# Database setup
def init_db():
    conn = sqlite3.connect('proxy_bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS proxies (id INTEGER PRIMARY KEY AUTOINCREMENT, ip_port TEXT UNIQUE, username TEXT, password TEXT, sold INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS deposits (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, trxid TEXT, status TEXT DEFAULT 'pending')''')
    c.execute('''CREATE TABLE IF NOT EXISTS purchases (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, proxy TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

# Helpers
def get_balance(uid): 
    conn = sqlite3.connect('proxy_bot.db'); c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id=?", (uid,)); row = c.fetchone()
    conn.close(); return row[0] if row else 0

def add_user(uid, username):
    conn = sqlite3.connect('proxy_bot.db'); c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, balance) VALUES (?, ?, 0)", (uid, username))
    conn.commit(); conn.close()

def get_stock():
    conn = sqlite3.connect('proxy_bot.db'); c = conn.cursor()
    c.execute("SELECT ip_port, username, password FROM proxies WHERE sold=0"); rows = c.fetchall()
    conn.close(); return rows

def sell_proxy(ip_port):
    conn = sqlite3.connect('proxy_bot.db'); c = conn.cursor()
    c.execute("UPDATE proxies SET sold=1 WHERE ip_port=?", (ip_port,))
    conn.commit(); conn.close()

# Start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id, user.username)
    kb = [
        [InlineKeyboardButton("Balance", callback_data="bal")],
        [InlineKeyboardButton("Buy Proxy", callback_data="buy")],
        [InlineKeyboardButton("Deposit", callback_data="dep")],
        [InlineKeyboardButton("My Proxies", callback_data="my")],
    ]
    if user.id == ADMIN_ID:
        kb.append([InlineKeyboardButton("Admin", callback_data="admin")])
    await update.message.reply_text(
        f"স্বাগতম {user.first_name}!\n১ প্রক্সি = ১ টাকা\n\nচুজ করো ↓",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# Main buttons
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    uid = q.from_user.id

    if data == "bal":
        await q.edit_message_text(f"তোমার ব্যালেন্স: {get_balance(uid)} টাকা", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="home")]]))

    elif data == "my":
        conn = sqlite3.connect('proxy_bot.db'); c = conn.cursor()
        c.execute("SELECT proxy FROM purchases WHERE user_id=? ORDER BY id DESC LIMIT 15", (uid,)); rows = c.fetchall(); conn.close()
        if not rows:
            text = "কোনো প্রক্সি কেনা হয়নি।"
        else:
            text = "তোমার প্রক্সি:\n\n" + "\n".join([f"`{p[0]}`" for p in rows])
        await q.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="home")]]))

    elif data == "buy":
        stock = get_stock()
        if not stock:
            await q.edit_message_text("স্টকে কোনো প্রক্সি নেই।", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="home")]]))
            return
        kb = [
            [InlineKeyboardButton("১টি – ১Tk", callback_data="buy1")],
            [InlineKeyboardButton("৫টি – ৫Tk", callback_data="buy5")],
            [InlineKeyboardButton("১০টি – ১০Tk", callback_data="buy10")],
            [InlineKeyboardButton("Back", callback_data="home")],
        ]
        await q.edit_message_text(f"স্টকে আছে: {len(stock)}টি প্রক্সি\nকতগুলো কিনবে?", reply_markup=InlineKeyboardMarkup(kb))

    elif data in ["buy1","buy5","buy10"]:
        qty = {"buy1":1, "buy5":5, "buy10":10}[data]
        bal = get_balance(uid)
        if bal < qty:
            await q.edit_message_text(f"টাকা নেই! দরকার {qty}Tk, আছে {bal}Tk", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="home")]]))
            return
        proxies = get_stock()[:qty]
        if len(proxies) < qty:
            await q.edit_message_text("এতগুলো প্রক্সি স্টকে নেই।", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="home")]]))
            return

        result = "কেনা হয়েছে!\n\n"
        conn = sqlite3.connect('proxy_bot.db'); c = conn.cursor()
        for ip_port, user, pwd in proxies:
            proxy_str = f"http://{user}:{pwd}@{ip_port}" if user and pwd else ip_port
            result += f"`{proxy_str}`\n"
            sell_proxy(ip_port)
            c.execute("INSERT INTO purchases (user_id, proxy) VALUES (?,?)", (uid, proxy_str))
        c.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (qty, uid))
        conn.commit(); conn.close()

        await q.edit_message_text(result + f"\n{qty}Tk কাটা হয়েছে।", parse_mode='Markdown',
                                 reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="home")]]))

    elif data == "home":
        await start(q, context)

    # Admin approve
    elif data.startswith("app_"):
        _, target_uid, amt = data.split("_")
        target_uid, amt = int(target_uid), int(amt)
        conn = sqlite3.connect('proxy_bot.db'); c = conn.cursor()
        c.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amt, target_uid))
        c.execute("UPDATE deposits SET status='approved' WHERE user_id=? AND amount=? AND status='pending'", (target_uid, amt))
        conn.commit(); conn.close()
        await context.bot.send_message(target_uid, f"তোমার {amt}Tk ডিপোজিট অ্যাপ্রুভ হয়েছে!")
        await q.edit_message_caption(caption=q.message.caption + f"\n\nApproved (+{amt}Tk)")

# Deposit flow
async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text("বিকাশ 01815243007 টাকা পাঠাও → তারপর স্ক্রিনশট পাঠাও")
    return WAITING_SCREENSHOT

async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['photo'] = update.message.photo[-1].file_id
    await update.message.reply_text("Transaction ID দাও:")
    return WAITING_TRXID

async def trxid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['trx'] = update.message.text
    await update.message.reply_text("কত টাকা পাঠিয়েছ?")
    return WAITING_AMOUNT

async def amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amt = int(update.message.text)
        if amt < 50:
            await update.message.reply_text("ন্যূনতম ৫০Tk")
            return WAITING_AMOUNT
    except:
        await update.message.reply_text("শুধু সংখ্যা লিখো")
        return WAITING_AMOUNT

    user = update.effective_user
    photo = context.user_data['photo']
    trx = context.user_data['trx']

    conn = sqlite3.connect('proxy_bot.db'); c = conn.cursor()
    c.execute("INSERT INTO deposits (user_id, amount, trxid) VALUES (?,?,?)", (user.id, amt, trx))
    conn.commit(); conn.close()

    kb = [[InlineKeyboardButton(f"Approve {amt}Tk", callback_data=f"app_{user.id}_{amt}")]]
    await context.bot.send_photo(ADMIN_ID, photo,
        caption=f"New Deposit\nUser: {user.full_name} (@{user.username or 'none'})\nID: {user.id}\nAmount: {amt}Tk\nTrxID: {trx}",
        reply_markup=InlineKeyboardMarkup(kb))

    await update.message.reply_text("রিকোয়েস্ট পাঠানো হয়েছে। অ্যাপ্রুভ হলে ব্যালেন্সে যোগ হবে।")
    return ConversationHandler.END

# Admin add proxies
async def addproxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    await update.message.reply_text("প্রক্সি পাঠাও (এক লাইনে একটা):\n192.168.1.1:8080\nঅথবা\n192.168.1.1:8080:user:pass")
    context.user_data['add'] = True

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('add') and update.message.from_user.id == ADMIN_ID:
        lines = update.message.text.split('\n')
        added = 0
        conn = sqlite3.connect('proxy_bot.db'); c = conn.cursor()
        for line in lines:
            p = line.strip().split(':')
            if len(p) < 2: continue
            ip_port = f"{p[0]}:{p[1]}"
            user = p[2] if len(p) > 2 else None
            pwd = p[3] if len(p) > 3 else None
            c.execute("INSERT OR IGNORE INTO proxies (ip_port, username, password) VALUES (?,?,?)", (ip_port, user, pwd))
            added += c.rowcount
        conn.commit(); conn.close()
        await update.message.reply_text(f"{added}টি প্রক্সি যোগ হয়েছে।")
        context.user_data['add'] = False

def main():
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(deposit_start, pattern="^dep$")],
        states={
            WAITING_SCREENSHOT: [MessageHandler(filters.PHOTO, photo)],
            WAITING_TRXID: [MessageHandler(filters.TEXT & ~filters.COMMAND, trxid)],
            WAITING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, amount)],
        },
        fallbacks=[CommandHandler("cancel", lambda u,c: ConversationHandler.END)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addproxies", addproxies))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("Bot চলছে...")
    app.run_polling()

if __name__ == '__main__':
    main()

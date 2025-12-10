import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, ConversationHandler, filters
)

# তোমার তথ্য
TOKEN = "7308877263:AAEuz6pumYmjbeMyJ76GBYGJVvnDLXiubY4"
ADMIN_ID = 1651695602
BKASH_NUMBER = "01815243007"          # তোমার bKash নাম্বার

# Deposit states
PHOTO, TRXID, AMOUNT = range(3)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# DB
conn = sqlite3.connect('proxy_bot.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0)''')
c.execute('''CREATE TABLE IF NOT EXISTS proxies (id INTEGER PRIMARY KEY, ip_port TEXT UNIQUE, username TEXT, password TEXT, sold INTEGER DEFAULT 0)''')
c.execute('''CREATE TABLE IF NOT EXISTS deposits (id INTEGER PRIMARY KEY, user_id INTEGER, amount INTEGER, trxid TEXT, status TEXT DEFAULT 'pending')''')
c.execute('''CREATE TABLE IF NOT EXISTS purchases (id INTEGER PRIMARY KEY, user_id INTEGER, proxy TEXT)''')
conn.commit()

# Helpers
def get_balance(uid):
    c.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
    r = c.fetchone()
    return r[0] if r else 0

def add_balance(uid, amt):
    c.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0)", (uid,))
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amt, uid))
    conn.commit()

def get_stock():
    c.execute("SELECT ip_port, username, password FROM proxies WHERE sold=0")
    return c.fetchall()

def sell_proxy(ip_port):
    c.execute("UPDATE proxies SET sold=1 WHERE ip_port=?", (ip_port,))
    conn.commit()

# Start / Main Menu
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    kb = [
        [InlineKeyboardButton("Balance", callback_data="bal")],
        [InlineKeyboardButton("Buy Proxy", callback_data="buy")],
        [InlineKeyboardButton("Deposit (bKash)", callback_data="deposit_start")],
        [InlineKeyboardButton("My Proxies", callback_data="my")],
    ]
    if uid == ADMIN_ID:
        kb.append([InlineKeyboardButton("Admin", callback_data="admin")])

    rm = InlineKeyboardMarkup(kb)
    text = "স্বাগতম!\n১ প্রক্সি = ১ টাকা\n\nচুজ করুন ↓"

    if update.message:
        await update.message.reply_text(text, reply_markup=rm)
    else:
        await update.callback_query.edit_message_text(text, reply_markup=rm)

# All buttons
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = q.data

    if data == "bal":
        await q.edit_message_text(f"ব্যালেন্স: **{get_balance(uid)}** Tk", parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("মেনু", callback_data="main")]]))

    elif data == "my":
        c.execute("SELECT proxy FROM purchases WHERE user_id=? ORDER BY id DESC LIMIT 20", (uid,))
        rows = c.fetchall()
        text = "তোমার প্রক্সি:\n\n" + ("\n".join([f"`{r[0]}`" for r in rows]) if rows else "কোনো প্রক্সি কেনা হয়নি")
        await q.edit_message_text(text, parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("মেনু", callback_data="main")]]))

    elif data == "buy":
        st = len(get_stock())
        kb = [
            [InlineKeyboardButton("১টি – ১Tk", callback_data="buy1")],
            [InlineKeyboardButton("৫টি – ৫Tk", callback_data="buy5")],
            [InlineKeyboardButton("১০টি – ১০Tk", callback_data="buy10")],
            [InlineKeyboardButton("মেনু", callback_data="main")],
        ]
        await q.edit_message_text(f"স্টকে আছে: **{st}** টি\nকতগুলো কিনবে?", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

    elif data in ["buy1", "buy5","buy10"]:
        qty = int(data[3:])
        if get_balance(uid) < qty:
            await q.edit_message_text(f"টাকা নেই! দরকার {qty}Tk", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("মেনু", callback_data="main")]]))
            return
        proxies = get_stock()[:qty]
        result = "কেনা হয়েছে!\n\n"
        for ip, u, p in proxies:
            proxy = f"http://{u}:{p}@{ip}" if u and p else ip
            result += f"`{proxy}`\n"
            sell_proxy(ip)
            c.execute("INSERT INTO purchases (user_id, proxy) VALUES (?,?)", (uid, proxy))
        c.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (qty, uid))
        conn.commit()
        await q.edit_message_text(result + f"\n{qty}Tk কাটা হয়েছে", parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("মেনু", callback_data="main")]]))

    elif data == "main":
        await start(q, context)

    # Deposit start
    elif data == "deposit_start":
        await q.edit_message_text(
            f"bKash Personal করো:\n\n`{BKASH_NUMBER}`\n\nপেমেন্টের পর স্ক্রিনশট পাঠাও →",
            parse_mode='Markdown'
        )
        return PHOTO

    # Approve deposit (admin only)
    elif data.startswith("approve_") and uid == ADMIN_ID:
        _, target_uid, amt = data.split("_")
        target_uid, amt = int(target_uid), int(amt)
        add_balance(target_uid, amt)
        c.execute("UPDATE deposits SET status='approved' WHERE user_id=? AND amount=?", (target_uid, amt))
        conn.commit()
        await context.bot.send_message(target_uid, f"তোমার {amt}Tk bKash ডিপোজিট অ্যাপ্রুভ হয়েছে!")
        await q.edit_message_caption(caption=q.message.caption + f"\n\nApproved (+{amt}Tk)")

# Deposit conversation
async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["photo"] = update.message.photo[-1].file_id
    await update.message.reply_text("Transaction ID দাও:")
    return TRXID

async def trxid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["trx"] = update.message.text.strip()
    await update.message.reply_text("কত টাকা পাঠিয়েছ? (শুধু সংখ্যা)")
    return AMOUNT

async def amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amt = int(update.message.text.strip())
        if amt < 50:
            await update.message.reply_text("ন্যূনতম ৫০ টাকা")
            return AMOUNT
    except:
        await update.message.reply_text("শুধু সংখ্যা লিখো")
        return AMOUNT

    user = update.effective_user
    photo = context.user_data["photo"]
    trx = context.user_data["trx"]

    c.execute("INSERT INTO deposits (user_id, amount, trxid) VALUES (?,?,?)", (user.id, amt, trx))
    conn.commit()

    kb = [[InlineKeyboardButton(f"Approve {amt}Tk", callback_data=f"approve_{user.id}_{amt}")]]
    await context.bot.send_photo(
        ADMIN_ID, photo,
        caption=f"নতুন bKash ডিপোজিট\n\nUser: {user.full_name}\nID: {user.id}\nAmount: {amt}Tk\nTrxID: {trx}",
        reply_markup=InlineKeyboardMarkup(kb)
    )

    await update.message.reply_text("রিকোয়েস্ট পাঠানো হয়েছে। অ্যাপ্রুভ হলে টাকা যোগ হবে।")
    return ConversationHandler.END

# Admin add proxies
async def addproxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("প্রক্সি পাঠাও (এক লাইনে একটা)")
    context.user_data["add"] = True

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("add") and update.effective_user.id == ADMIN_ID:
        added = 0
        for line in update.message.text.split("\n"):
            p = line.strip().split(":")
            if len(p) < 2: continue
            ip_port = f"{p[0]}:{p[1]}"
            u = p[2] if len(p)>2 else None
            pwd = p[3] if len(p)>3 else None
            c.execute("INSERT OR IGNORE INTO proxies (ip_port, username, password) VALUES (?,?,?)", (ip_port, u, pwd))
            added += c.rowcount
        conn.commit()
        await update.message.reply_text(f"{added}টি প্রক্সি যোগ হয়েছে")
        context.user_data["add"] = False

def main():
    app = Application.builder().token(TOKEN).build()

    dep_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(lambda u,c: PHOTO, pattern="^deposit_start$")],
        states={
            PHOTO: [MessageHandler(filters.PHOTO, photo)],
            TRXID: [MessageHandler(filters.TEXT & ~filters.COMMAND, trxid)],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, amount)],
        },
        fallbacks=[]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(dep_conv)
    app.add_handler(CommandHandler("addproxies", addproxies))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("বট চালু হয়েছে! এবার ডিপোজিট ১০% কাজ করবে")
    app.run_polling()

if __name__ == '__main__':
    main()

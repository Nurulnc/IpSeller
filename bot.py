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

# bKash Number (তোমার পার্সোনাল/মার্চেন্ট যেটা দিবে)
BKASH_NUMBER = "01815243007"   # ←← এখানে তোমার bKash নাম্বার দে

PHOTO, TRX, AMOUNT = range(3)

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# Database
conn = sqlite3.connect('proxy_bot.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance INTEGER DEFAULT 0)''')
c.execute('''CREATE TABLE IF NOT EXISTS proxies (id INTEGER PRIMARY KEY AUTOINCREMENT, ip_port TEXT UNIQUE, username TEXT, password TEXT, sold INTEGER DEFAULT 0)''')
c.execute('''CREATE TABLE IF NOT EXISTS deposits (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, trxid TEXT, status TEXT DEFAULT 'pending')''')
c.execute('''CREATE TABLE IF NOT EXISTS purchases (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, proxy TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
conn.commit()

# Helpers
def get_balance(uid):
    c.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
    r = c.fetchone()
    return r[0] if r else 0

def add_user(uid, uname):
    c.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?,?)", (uid, uname))
    conn.commit()

def stock():
    c.execute("SELECT ip_port, username, password FROM proxies WHERE sold=0")
    return c.fetchall()

def sell(ip_port):
    c.execute("UPDATE proxies SET sold=1 WHERE ip_port=?", (ip_port,))
    conn.commit()

# Start Menu
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id, user.username)

    kb = [
        [InlineKeyboardButton("💰 Balance", callback_data="balance")],
        [InlineKeyboardButton("🛒 Buy Proxy", callback_data="buy")],
        [InlineKeyboardButton("📥 Deposit (bKash)", callback_data="deposit")],
        [InlineKeyboardButton("📦 My Proxies", callback_data="myproxies")],
    ]
    if user.id == ADMIN_ID:
        kb.append([InlineKeyboardButton("Admin Panel", callback_data="admin")])

    reply_markup = InlineKeyboardMarkup(kb)

    text = f"স্বাগতম {user.first_name}!\n\nResidential Proxy Shop\n১টি প্রক্সি = ১ টাকা\n\nচুজ করুন ↓"

    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)
    else:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)

# All Buttons
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = q.data

    if data == "balance":
        await q.edit_message_text(
            f"আপনার ব্যালেন্স: **{get_balance(uid)}** টাকা",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("মেনুতে ফিরুন", callback_data="home")]])
        )

    elif data == "myproxies":
        c.execute("SELECT proxy FROM purchases WHERE user_id=? ORDER BY id DESC LIMIT 20", (uid,))
        rows = c.fetchall()
        text = "আপনার কেনা প্রক্সি:\n\n" + ("\n".join([f"`{r[0]}`" for r in rows]) if rows else "কোনো প্রক্সি কেনা হয়নি।")
        await q.edit_message_text(text, parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("মেনুতে ফিরুন", callback_data="home")]]))

    elif data == "buy":
        s = stock()
        if not s:
            await q.edit_message_text("স্টকে কোনো প্রক্সি নেই।", 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("মেনুতে ফিরুন", callback_data="home")]]))
            return
        kb = [
            [InlineKeyboardButton("১টি → ১Tk", callback_data="buy_1")],
            [InlineKeyboardButton("৫টি → ৫Tk", callback_data="buy_5")],
            [InlineKeyboardButton("১০টি → ১০Tk", callback_data="buy_10")],
            [InlineKeyboardButton("মেনুতে ফিরুন", callback_data="home")],
        ]
        await q.edit_message_text(f"স্টকে আছে: **{len(s)}** টি প্রক্সি\nকতগুলো কিনবেন?", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("buy_"):
        qty = int(data.split("_")[1])
        bal = get_balance(uid)
        if bal < qty:
            await q.edit_message_text(f"ইনসাফিসিয়েন্ট ব্যালেন্স!\nদরকার: {qty}Tk | আছে: {bal}Tk",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("মেনুতে ফিরুন", callback_data="home")]]))
            return

        proxies = stock()[:qty]
        result = "সফলভাবে কেনা হয়েছে!\n\nতোমার প্রক্সিগুলো:\n\n"
        for ip_port, u, p in proxies:
            proxy_str = f"http://{u}:{p}@{ip_port}" if u and p else ip_port
            result += f"`{proxy_str}`\n"
            sell(ip_port)
            c.execute("INSERT INTO purchases (user_id, proxy) VALUES (?,?)", (uid, proxy_str))
        c.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (qty, uid))
        conn.commit()

        await q.edit_message_text(result + f"\n{qty} টাকা কাটা হয়েছে।", parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("মেনুতে ফিরুন", callback_data="home")]]))

    elif data == "deposit":
        text = f"ডিপোজিট করতে **bKash (Personal)** করুন এই নাম্বারে:\n\n`{BKASH_NUMBER}`\n\nপেমেন্ট করার পর নিচের ধাপগুলো অনুসরণ করুন →\n\n১. স্ক্রিনশট পাঠান\n২. Transaction ID দিন\n৩. কত টাকা পাঠিয়েছেন লিখুন"
        await q.edit_message_text(text, parse_mode='Markdown')
        return PHOTO

    elif data == "home":
        await start(q, context)

    # Admin approve
    elif data.startswith("approve_"):
        if uid != ADMIN_ID: return
        _, target_id, amt = data.split("_")
        target_id, amt = int(target_id), int(amt)
        c.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amt, target_id))
        c.execute("UPDATE deposits SET status='approved' WHERE user_id=? AND amount=?", (target_id, amt))
        conn.commit()
        await context.bot.send_message(target_id, f"আপনার {amt}Tk bKash ডিপোজিট অ্যাপ্রুভ হয়েছে! ব্যালেন্সে যোগ হয়েছে।")
        await q.edit_message_caption(caption=q.message.caption + f"\n\nApproved (+{amt}Tk)")

# Deposit Flow
async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['photo'] = update.message.photo[-1].file_id
    await update.message.reply_text("Transaction ID দিন:")
    return TRX

async def trx(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['trx'] = update.message.text.strip()
    await update.message.reply_text("কত টাকা পাঠিয়েছেন? (শুধু সংখ্যা)")
    return AMOUNT

async def amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amt = int(update.message.text)
        if amt < 50:
            await update.message.reply_text("ন্যূনতম ৫০ টাকা")
            return AMOUNT
    except:
        await update.message.reply_text("শুধু সংখ্যা লিখুন")
        return AMOUNT

    user = update.effective_user
    c.execute("INSERT INTO deposits (user_id, amount, trxid) VALUES (?,?,?)", (user.id, amt, context.user_data['trx']))
    conn.commit()

    kb = [[InlineKeyboardButton(f"Approve {amt}Tk", callback_data=f"approve_{user.id}_{amt}")]]
    await context.bot.send_photo(
        ADMIN_ID,
        context.user_data['photo'],
        caption=f"New bKash Deposit\n\nUser: {user.full_name} (@{user.username or 'none'})\nID: `{user.id}`\nAmount: {amt}Tk\nTrxID: `{context.user_data['trx']}`\n\nঅ্যাপ্রুভ করতে বাটন চাপুন →",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(kb)
    )

    await update.message.reply_text("আপনার রিকোয়েস্ট পাঠানো হয়েছে। অ্যাপ্রুভ হলে ব্যালেন্সে যোগ হবে। ধন্যবাদ!")
    return ConversationHandler.END

# Add Proxies Command
async def addproxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    await update.message.reply_text("প্রক্সি পাঠান (ঃ\n192.168.1.1:8080\n192.168.1.2:8080:user:pass")
    context.user_data['add'] = True

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('add') and update.message.from_user.id == ADMIN_ID:
        lines = update.message.text.split('\n')
        added = 0
        for line in lines:
            p = line.strip().split(':')
            if len(p) < 2: continue
            ip_port = f"{p[0]}:{p[1]}"
            u = p[2] if len(p) > 2 else None
            pwd = p[3] if len(p) > 3 else None
            c.execute("INSERT OR IGNORE INTO proxies (ip_port, username, password) VALUES (?,?,?)", (ip_port, u, pwd))
            added += c.rowcount
        conn.commit()
        await update.message.reply_text(f"{added}টি প্রক্সি স্টকে যোগ হয়েছে।")
        context.user_data['add'] = False

def main():
    app = Application.builder().token(TOKEN).build()

    dep_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(lambda u, c: PHOTO, pattern="^deposit$")],
        states={
            PHOTO: [MessageHandler(filters.PHOTO, photo)],
            TRX: [MessageHandler(filters.TEXT & ~filters.COMMAND, trx)],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, amount)],
        },
        fallbacks=[]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(CommandHandler("addproxies", addproxies))
    app.add_handler(dep_conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("bKash Proxy Bot চালু হয়েছে! /start দিয়ে চেক করো")
    app.run_polling()

if __name__ == '__main__':
    main()

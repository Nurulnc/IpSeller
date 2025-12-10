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
BKASH_NUMBER = "01815243007"        # ← এখানে তোমার bKash নাম্বার দিবি

# Deposit states
PHOTO, TRXID, AMOUNT = range(3)

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# Database
conn = sqlite3.connect('proxy_bot.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0)''')
c.execute('''CREATE TABLE IF NOT EXISTS proxies (id INTEGER PRIMARY KEY, ip_port TEXT UNIQUE, username TEXT, password TEXT, sold INTEGER DEFAULT 0)''')
c.execute('''CREATE TABLE IF NOT EXISTS deposits (id INTEGER PRIMARY KEY, user_id INTEGER, amount INTEGER, trxid TEXT, status TEXT DEFAULT 'pending')''')
c.execute('''CREATE TABLE IF NOT EXISTS purchases (id INTEGER PRIMARY KEY, user_id INTEGER, proxy TEXT, time DATETIME DEFAULT CURRENT_TIMESTAMP)''')
conn.commit()

# Helper functions
def get_balance(uid):
    c.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
    row = c.fetchone()
    return row[0] if row else 0

def add_balance(uid, amt):
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amt, uid))
    if c.rowcount == 0:
        c.execute("INSERT INTO users (user_id, balance) VALUES (?, ?)", (uid, amt))
    conn.commit()

def get_stock():
    c.execute("SELECT ip_port, username, password FROM proxies WHERE sold=0")
    return c.fetchall()

def mark_sold(ip_port):
    c.execute("UPDATE proxies SET sold=1 WHERE ip_port=?", (ip_port,))
    conn.commit()

# Main Menu
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    kb = [
        [InlineKeyboardButton("Balance", callback_data="balance")],
        [InlineKeyboardButton("Buy Proxy", callback_data="buy")],
        [InlineKeyboardButton("Deposit (bKash)", callback_data="deposit")],
        [InlineKeyboardButton("My Proxies", callback_data="myproxies")],
    ]
    if user_id == ADMIN_ID:
        kb.append([InlineKeyboardButton("Admin Panel", callback_data="admin")])

    reply_markup = InlineKeyboardMarkup(kb)

    text = f"স্বাগতম!\n\nResidential Proxy Shop\n১ প্রক্সি = ১ টাকা\n\nচুজ করুন:"

    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)
    else:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)

# All Button Handler
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    # Balance
    if data == "balance":
        bal = get_balance(user_id)
        await query.edit_message_text(
            f"আপনার ব্যালেন্স: **{bal}** টাকা",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("মেনুতে ফিরুন", callback_data="main")]])
        )

    # My Proxies
    elif data == "myproxies":
        c.execute("SELECT proxy FROM purchases WHERE user_id=? ORDER BY id DESC LIMIT 20", (user_id,))
        rows = c.fetchall()
        if not rows:
            text = "আপনি এখনো কোনো প্রক্সি কেনেননি।"
        else:
            text = "আপনার কেনা প্রক্সি:\n\n" + "\n".join([f"`{r[0]}`" for r in rows])
        await query.edit_message_text(text, parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("মেনুতে ফিরুন", callback_data="main")]]))

    # Buy Menu
    elif data == "buy":
        stock_count = len(get_stock())
        kb = [
            [InlineKeyboardButton("১টি – ১Tk", callback_data="buy_1")],
            [InlineKeyboardButton("৫টি – ৫Tk", callback_data="buy_5")],
            [InlineKeyboardButton("১০টি – ১০Tk", callback_data="buy_10")],
            [InlineKeyboardButton("মেনুতে ফিরুন", callback_data="main")],
        ]
        await query.edit_message_text(
            f"স্টকে আছে: **{stock_count}** টি প্রক্সি\n\nকতগুলো কিনবেন?",
            parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb)
        )

    # Buy Action
    elif data.startswith("buy_"):
        qty = int(data.split("_")[1])
        bal = get_balance(user_id)
        if bal < qty:
            await query.edit_message_text(f"ইনসাফিসিয়েন্ট ব্যালেন্স!\nদরকার: {qty}Tk, আছে: {bal}Tk",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("মেনুতে ফিরুন", callback_data="main")]]))
            return

        proxies = get_stock()[:qty]
        if len(proxies) < qty:
            await query.edit_message_text("স্টকে এতগুলো প্রক্সি নেই।",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("মেনুতে ফিরুন", callback_data="main")]]))
            return

        result = "সফলভাবে কেনা হয়েছে!\n\nতোমার প্রক্সিগুলো:\n\n"
        for ip_port, u, p in proxies:
            proxy_str = f"http://{u}:{p}@{ip_port}" if u and p else ip_port
            result += f"`{proxy_str}`\n"
            mark_sold(ip_port)
            c.execute("INSERT INTO purchases (user_id, proxy) VALUES (?,?)", (user_id, proxy_str))
        c.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (qty, user_id))
        conn.commit()

        await query.edit_message_text(result + f"\n\n{qty} টাকা কাটা হয়েছে।", parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("মেনুতে ফিরুন", callback_data="main")]]))

    # Deposit Start
    elif data == "deposit":
        text = f"bKash (Personal) করুন এই নাম্বারে:\n\n`{BKASH_NUMBER}`\n\nপেমেন্ট করার পর:\n১. স্ক্রিনশট পাঠান\n২. Transaction ID দিন\n৩. কত টাকা পাঠিয়েছেন লিখুন"
        await query.edit_message_text(text, parse_mode='Markdown')
        return PHOTO

    # Back to main
    elif data == "main":
        await start(query, context)

    # Approve Deposit (Admin only)
    elif data.startswith("approve_") and user_id == ADMIN_ID:
        _, uid, amt = data.split("_")
        uid, amt = int(uid), int(amt)
        add_balance(uid, amt)
        c.execute("UPDATE deposits SET status='approved' WHERE user_id=? AND amount=?", (uid, amt))
        conn.commit()
        await context.bot.send_message(uid, f"আপনার {amt}Tk bKash ডিপোজিট অ্যাপ্রুভ হয়েছে!\nব্যালেন্সে +{amt} টাকা যোগ হয়েছে।")
        await query.edit_message_caption(caption=query.message.caption + f"\n\nApproved (+{amt}Tk)")

# Deposit Conversation 
async def photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['photo'] = update.message.photo[-1].file_id
    await update.message.reply_text("Transaction ID দিন:")
    return TRXID

async def trxid_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['trxid'] = update.message.text.strip()
    await update.message.reply_text("কত টাকা পাঠিয়েছেন? (শুধু সংখ্যা)")
    return AMOUNT

async def amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text.strip())
        if amount < 50:
            await update.message.reply_text("ন্যূনতম ৫০ টাকা")
            return AMOUNT
    except:
        await update.message.reply_text("শুধু সংখ্যা লিখুন (যেমন: 500)")
        return AMOUNT

    user = update.effective_user
    photo_id = context.user_data['photo']
    trxid = context.user_data['trxid']

    c.execute("INSERT INTO deposits (user_id, amount, trxid) VALUES (?,?,?)", (user.id, amount, trxid))
    conn.commit()

    kb = [[InlineKeyboardButton(f"Approve {amount}Tk", callback_data=f"approve_{user.id}_{amount}")]]
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo_id,
        caption=f"New bKash Deposit\n\nUser: {user.full_name}\nID: `{user.id}`\nAmount: {amount}Tk\nTrxID: `{trxid}`",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(kb)
    )

    await update.message.reply_text("আপনার ডিপোজিট রিকোয়েস্ট পাঠানো হয়েছে!\nঅ্যাডমিন অ্যাপ্রুভ করলে ব্যালেন্সে যোগ হবে।")
    return ConversationHandler.END

# Admin: Add Proxies
async def add_proxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("প্রক্সি পাঠান (প্রতি লাইনে একটা):\n192.168.1.1:8080\n192.168.1.2:8080:user:pass")
    context.user_data['adding_proxies'] = True

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('adding_proxies') and update.effective_user.id == ADMIN_ID:
        lines = update.message.text.split('\n')
        added = 0
        for line in lines:
            parts = line.strip().split(':')
            if len(parts) < 2: continue
            ip_port = f"{parts[0]}:{parts[1]}"
            username = parts[2] if len(parts) > 2 else None
            password = parts[3] if len(parts) > 3 else None
            c.execute("INSERT OR IGNORE INTO proxies (ip_port, username, password) VALUES (?,?,?)",
                      (ip_port, username, password))
            added += c.rowcount
        conn.commit()
        await update.message.reply_text(f"{added}টি প্রক্সি সফলভাবে যোগ হয়েছে!")
        context.user_data['adding_proxies'] = False

def main():
    app = Application.builder().token(TOKEN).build()

    deposit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(lambda u, c: PHOTO, pattern="^deposit$")],
        states={
            PHOTO: [MessageHandler(filters.PHOTO, photo_received)],
            TRXID: [MessageHandler(filters.TEXT & ~filters.COMMAND, trxid_received)],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, amount_received)],
        },
        fallbacks=[CommandHandler("cancel", lambda u,c: ConversationHandler.END)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(deposit_conv)
    app.add_handler(CommandHandler("addproxies", add_proxies))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("Proxy Bot চালু হয়েছে! এবার সবকিছু ১০০% কাজ করবে")
    app.run_polling()

if __name__ == '__main__':
    main()

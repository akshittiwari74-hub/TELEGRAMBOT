import requests
from bs4 import BeautifulSoup
import certifi
from concurrent.futures import ThreadPoolExecutor

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

TOKEN = "8533716702:AAGQHkAQoir1RDOMu7yKvSHtLUCidfzGOA0"

SERIAL, RANGE, FILTER = range(3)

user_data_store = {}

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})


def get_data(eid):

    url = f"https://upmines.upsdc.gov.in/Transporter/PrintTransporterFormVehicleCheckValidOrNot.aspx?eId={eid}"

    try:
        r = session.get(url, timeout=15, verify=certifi.where())

        if r.status_code != 200:
            return None

    except:
        return None

    soup = BeautifulSoup(r.text, "lxml")

    cells = [td.get_text(strip=True) for td in soup.find_all("td")]

    def find_val(label):

        for i, c in enumerate(cells):

            if label.lower() in c.lower() and i + 1 < len(cells):
                return cells[i + 1]

        return None

    istp = find_val("istp")

    if not istp:
        return None

    return {
        "SERIAL": eid,
        "DESTINATION": find_val("destination"),
        "MINERAL": find_val("mineral"),
        "DATE": find_val("generated"),
        "QTY": find_val("qty"),
    }


def format_result(item):

    return (
        f"SERIAL: {item['SERIAL']}\n"
        f"DEST: {item['DESTINATION']}\n"
        f"MINERAL: {item['MINERAL']}\n"
        f"QTY: {item['QTY']}\n"
        f"DATE: {item['DATE']}"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text("Enter 19 digit serial")

    return SERIAL


async def get_serial(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.message.from_user.id

    serial = update.message.text.strip()

    if not serial.isdigit() or len(serial) != 19:

        await update.message.reply_text("Invalid serial")

        return SERIAL

    prefix = serial[:-4]

    user_data_store[user_id] = {"prefix": prefix}

    await update.message.reply_text("Enter range like 1000-1100 or any range")

    return RANGE


async def get_range(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.message.from_user.id

    txt = update.message.text.strip()

    try:

        if "-" in txt:
            r1, r2 = map(int, txt.split("-"))
        else:
            r1 = 1
            r2 = int(txt)

    except:
        await update.message.reply_text("Enter range like 1-100")
        return RANGE

    user_data_store[user_id]["r_start"] = r1
    user_data_store[user_id]["r_end"] = r2

    await update.message.reply_text("Enter keyword")

    return FILTER


async def get_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.message.from_user.id

    keyword = update.message.text.lower().strip()

    r_start = user_data_store[user_id]["r_start"]
    r_end = user_data_store[user_id]["r_end"]
    prefix = user_data_store[user_id]["prefix"]

    await update.message.reply_text(
        f"Searching {r_start}-{r_end}..."
    )

    results = []

    MAX_RESULTS = 20

    def worker(i):

        eid = prefix + str(i).zfill(4)

        try:
            data = get_data(eid)
        except:
            return None

        if not data:
            return None

        text = (
            str(data["DESTINATION"]).lower()
            + " "
            + str(data["MINERAL"]).lower()
        )

        if keyword in text:
            return data

        return None


    with ThreadPoolExecutor(max_workers=5) as ex:

        for r in ex.map(worker, range(r_start, r_end + 1)):

            if r:
                results.append(r)

            if len(results) >= MAX_RESULTS:
                break


    if not results:

        await update.message.reply_text(
            "No result found"
        )

        return ConversationHandler.END


    msg = "\n\n".join(format_result(x) for x in results)

    await update.message.reply_text(msg)

    return ConversationHandler.END

    user_id = update.message.from_user.id

    keyword = update.message.text.lower()

    r_start = user_data_store[user_id]["r_start"]
    r_end = user_data_store[user_id]["r_end"]
    prefix = user_data_store[user_id]["prefix"]

    results = []

    def worker(i):

        eid = prefix + str(i).zfill(4)

        data = get_data(eid)

        if not data:
            return None

        if keyword in str(data["DESTINATION"]).lower():
            return data

        return None


    with ThreadPoolExecutor(max_workers=10) as ex:

        for r in ex.map(worker, range(r_start, r_end + 1)):

            if r:
                results.append(r)


    if not results:

        await update.message.reply_text("No result")

        return ConversationHandler.END


    msg = "\n\n".join(format_result(x) for x in results)

    await update.message.reply_text(msg)

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text("Cancelled")

    return ConversationHandler.END


app = ApplicationBuilder().token(TOKEN).build()

conv = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        SERIAL: [MessageHandler(filters.TEXT, get_serial)],
        RANGE: [MessageHandler(filters.TEXT, get_range)],
        FILTER: [MessageHandler(filters.TEXT, get_filter)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

app.add_handler(conv)

print("Bot running...")

app.run_polling()
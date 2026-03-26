# ---------- RENDER PORT FIX ----------
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_server():
    server = HTTPServer(("0.0.0.0", 10000), Handler)
    server.serve_forever()

threading.Thread(target=run_server).start()


# ---------- IMPORTS ----------
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

TOKEN = "PUT_YOUR_TOKEN_HERE"

SERIAL, RANGE, FILTER = range(3)

user_data_store = {}

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})


# ---------- FETCH ----------

def get_data(eid):

    url = f"https://upmines.upsdc.gov.in/Transporter/PrintTransporterFormVehicleCheckValidOrNot.aspx?eId={eid}"

    try:
        r = session.get(url, timeout=5, verify=certifi.where())

        if r.status_code != 200:
            return None

    except:
        return None

    soup = BeautifulSoup(r.text, "lxml")

    cells = [td.get_text(strip=True) for td in soup.find_all("td")]

    def find_val(label):

        label = label.lower()

        for i, c in enumerate(cells):
            if label in c.lower() and i + 1 < len(cells):
                return cells[i + 1]

        return None

    istp = find_val("istp")

    if not istp:
        return None

    return {
        "SERIAL": eid,
        "ISTP": istp,
        "CHALLAN": find_val("origin transit pass no"),
        "MINERAL": find_val("name of mineral"),
        "DATE": find_val("transit pass generated"),
        "QTY": find_val("qty transported"),
        "DESTINATION": find_val("destination district"),
    }


# ---------- FORMAT ----------

def format_result(item):

    return (
        f"📦 SERIAL: {item['SERIAL']}\n"
        f"🧾 CHALLAN: {item['CHALLAN']}\n"
        f"📍 DESTINATION: {item['DESTINATION']}\n"
        f"⛏️ MINERAL: {item['MINERAL']}\n"
        f"📊 QTY: {item['QTY']}\n"
        f"📅 DATE: {item['DATE']}"
    )


# ---------- START ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text("Enter 19 digit serial")

    return SERIAL


# ---------- SERIAL ----------

async def get_serial(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.message.from_user.id

    serial = update.message.text.strip()

    if not serial.isdigit() or len(serial) != 19:

        await update.message.reply_text("Invalid serial")

        return SERIAL

    prefix = serial[:-4]

    user_data_store[user_id] = {
        "prefix": prefix
    }

    await update.message.reply_text("Enter range 1000-1100")

    return RANGE


# ---------- RANGE ----------

async def get_range(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.message.from_user.id

    txt = update.message.text.strip()

    try:

        if "-" in txt:
            r_start, r_end = map(int, txt.split("-"))
        else:
            r_start, r_end = 1, int(txt)

        if r_start > r_end:
            r_start, r_end = r_end, r_start

        if r_end - r_start > 500:
            await update.message.reply_text("Max 500 range")
            return ConversationHandler.END

        user_data_store[user_id]["r_start"] = r_start
        user_data_store[user_id]["r_end"] = r_end

    except:
        await update.message.reply_text("Invalid range")
        return ConversationHandler.END

    await update.message.reply_text("Enter district keyword")

    return FILTER


# ---------- SEARCH ----------

async def get_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.message.from_user.id

    keyword = update.message.text.lower().strip()

    filters_input = keyword.split()

    r_start = user_data_store[user_id]["r_start"]
    r_end = user_data_store[user_id]["r_end"]
    prefix = user_data_store[user_id]["prefix"]

    await update.message.reply_text(
        f"Searching {r_start}-{r_end}"
    )

    MAX_RESULTS = 20

    def worker(i):

        eid = prefix + str(i).zfill(4)

        data = get_data(eid)

        if not data:
            return None

        combined = (
            data["DESTINATION"].lower()
            + " "
            + data["MINERAL"].lower()
        )

        if all(f in combined for f in filters_input):
            return data

        return None


    results = []

    with ThreadPoolExecutor(max_workers=10) as executor:

        for res in executor.map(
            worker,
            range(r_start, r_end + 1)
        ):

            if res:
                results.append(res)

            if len(results) >= MAX_RESULTS:
                break


    if not results:

        await update.message.reply_text("No result")

        return ConversationHandler.END


    msg = "\n\n".join(
        format_result(r) for r in results
    )

    await update.message.reply_text(msg)

    return ConversationHandler.END


# ---------- CANCEL ----------

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text("Cancelled")

    return ConversationHandler.END


# ---------- APP ----------

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
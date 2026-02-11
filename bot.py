import os
import json
from datetime import datetime
import pytz
import asyncio

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler

# ---------------- CONFIG ----------------

DATA_FILE = "tempos.json"
HISTORY_FILE = "historico.json"
TOKEN = os.getenv("BOT_TOKEN")
TIMEZONE = pytz.timezone("America/Sao_Paulo")

# ---------------- UTIL ----------------

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    return {}

def save_history(data):
    with open(HISTORY_FILE, "w") as f:
        json.dump(data, f, indent=2)

def time_to_ms(t):
    m, rest = t.split(":")
    s, ms = rest.split(".")
    return (int(m) * 60 + int(s)) * 1000 + int(ms)

# ---------------- RULES ----------------

async def is_admin(update: Update):
    chat = update.effective_chat
    user = update.effective_user
    admins = await chat.get_administrators()
    return any(a.user.id == user.id for a in admins)

# ---------------- COMMANDS ----------------

async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    chat_id = str(update.effective_chat.id)
    track_name = " ".join(context.args)

    if not track_name:
        await update.message.reply_text("Usage:\n/track Track name")
        return

    data = load_data()
    data.setdefault(chat_id, {})

    # 🔒 TRAVA: já existe pista ativa
    if "current_track" in data[chat_id]:
        current = data[chat_id]["current_track"]
        await update.message.reply_text(
            f"⚠️ A track *{current}* is already active.\n"
            f"Use /reset to clear it before setting a new track.",
            parse_mode="Markdown"
        )
        return

    data[chat_id]["current_track"] = track_name
    data[chat_id].setdefault(track_name, {})

    save_data(data)
    await update.message.reply_text(
        f"🏁 Current track set:\n*{track_name}*",
        parse_mode="Markdown"
    )

async def time_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    chat_id = str(update.effective_chat.id)

    try:
        name = context.args[0]
        time_str = context.args[1]
        ms = time_to_ms(time_str)

        data = load_data()
        current_track = data.get(chat_id, {}).get("current_track")

        if not current_track:
            await update.message.reply_text("Set a track first:\n/track Track name")
            return

        ranking = data[chat_id][current_track]

        if name not in ranking or ms < ranking[name]["ms"]:
            ranking[name] = {"time": time_str, "ms": ms}
            save_data(data)
            await update.message.reply_text(f"✅ Time registered:\n{name} ⏱️ {time_str}")
        else:
            await update.message.reply_text(
                f"⛔ Slower than current.\nBest of {name}: {ranking[name]['time']}"
            )
    except:
        await update.message.reply_text("Usage:\n/time Name 1:18.732")

async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    chat_id = str(update.effective_chat.id)

    try:
        name = context.args[0]
        data = load_data()
        current_track = data.get(chat_id, {}).get("current_track")

        if not current_track:
            await update.message.reply_text("No track defined.")
            return

        ranking = data.get(chat_id, {}).get(current_track, {})

        if name not in ranking:
            await update.message.reply_text(f"{name} not found in ranking.")
            return

        del ranking[name]
        save_data(data)
        await update.message.reply_text(f"🗑️ {name} removed from ranking.")
    except:
        await update.message.reply_text("Usage:\n/delete Name")

async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    chat_id = str(update.effective_chat.id)
    data = load_data()

    current_track = data.get(chat_id, {}).get("current_track")
    if not current_track:
        await update.message.reply_text("No track to reset.")
        return

    del data[chat_id]["current_track"]
    save_data(data)

    await update.message.reply_text(
        "🔄 Track cleared. You can now set a new track using /track."
    )

async def rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    data = load_data()
    current_track = data.get(chat_id, {}).get("current_track")

    if not current_track:
        await update.message.reply_text("No track defined.")
        return

    ranking = data.get(chat_id, {}).get(current_track, {})

    if not ranking:
        await update.message.reply_text("Empty ranking 😴")
        return

    ordered = sorted(ranking.items(), key=lambda x: x[1]["ms"])

    text = f"🏆 *RANKING – {current_track}*\n\n"
    for i, (name, info) in enumerate(ordered, start=1):
        text += f"{i}º {name} ⏱️ {info['time']}\n"

    await update.message.reply_text(text, parse_mode="Markdown")

async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    history = load_history()

    if chat_id not in history:
        await update.message.reply_text("No history yet 😴")
        return

    text = "📚 *EVENT HISTORY*\n\n"

    for event in history[chat_id][-5:]:
        text += f"📅 {event['date']} – {event['track']}\n"
        ranking = sorted(event["ranking"].items(), key=lambda x: x[1]["ms"])
        for i, (name, info) in enumerate(ranking[:3], start=1):
            medal = ["🥇", "🥈", "🥉"][i-1]
            text += f"{medal} {name} ⏱️ {info['time']}\n"
        text += "\n"

    await update.message.reply_text(text, parse_mode="Markdown")

# ---------------- WEEKLY RESET ----------------

async def weekly_reset(app):
    data = load_data()
    history = load_history()
    date = datetime.now(TIMEZONE).strftime("%d/%m/%Y")

    for chat_id, content in data.items():
        track_name = content.get("current_track")
        if track_name and track_name in content:
            ranking = content[track_name]
            if ranking:
                history.setdefault(chat_id, [])
                history[chat_id].append({
                    "date": date,
                    "track": track_name,
                    "ranking": ranking
                })
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=f"🔄 Event finished!\nTrack: {track_name}\nHistory saved."
                )
        data[chat_id] = {}

    save_data(data)
    save_history(history)

# ---------------- MAIN ----------------

def main():
    print("Bot started...")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("track", track))
    app.add_handler(CommandHandler("time", time_cmd))
    app.add_handler(CommandHandler("delete", delete_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))
    app.add_handler(CommandHandler("rank", rank))
    app.add_handler(CommandHandler("history", history_cmd))

    scheduler = BackgroundScheduler(timezone=TIMEZONE)
    scheduler.add_job(
        lambda: asyncio.run(weekly_reset(app)),
        "cron",
        day_of_week="sat",
        hour=9,
        minute=0
    )
    scheduler.start()

    app.run_polling(stop_signals=None)

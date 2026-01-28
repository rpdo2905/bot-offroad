import os
TOKEN = os.getenv("BOT_TOKEN")
app = ApplicationBuilder().token(TOKEN).build()

import os
import json
from datetime import datetime, time
import pytz

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler

# Arquivos
ARQUIVO = "tempos.json"
HISTORICO = "historico.json"

# Token vem do Railway (variável de ambiente)
TOKEN = os.getenv("BOT_TOKEN")

# ----------------- Funções utilitárias -----------------

def carregar():
    if os.path.exists(ARQUIVO):
        with open(ARQUIVO, "r") as f:
            return json.load(f)
    return {}

def salvar(dados):
    with open(ARQUIVO, "w") as f:
        json.dump(dados, f, indent=2)

def carregar_historico():
    if os.path.exists(HISTORICO):
        with open(HISTORICO, "r") as f:
            return json.load(f)
    return {}

def salvar_historico(dados):
    with open(HISTORICO, "w") as f:
        json.dump(dados, f, indent=2)

def tempo_para_ms(t):
    m, resto = t.split(":")
    s, ms = resto.split(".")
    return (int(m)*60 + int(s))*1000 + int(ms)

# ----------------- Regras -----------------

async def eh_admin(update: Update):
    chat = update.effective_chat
    user = update.effective_user
    membros = await chat.get_administrators()
    return any(m.user.id == user.id for m in membros)

# ----------------- Comandos -----------------

async def pista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await eh_admin(update):
        return

    chat_id = str(update.effective_chat.id)
    nome_pista = " ".join(context.args)

    if not nome_pista:
        await update.message.reply_text("Uso:\n/pista Nome da pista")
        return

    dados = carregar()
    dados.setdefault(chat_id, {})
    dados[chat_id]["pista_atual"] = nome_pista
    dados[chat_id].setdefault(nome_pista, {})

    salvar(dados)
    await update.message.reply_text(
        f"🏁 Pista atual definida:\n*{nome_pista}*",
        parse_mode="Markdown"
    )

async def tempo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await eh_admin(update):
        return

    chat_id = str(update.effective_chat.id)
    user = update.effective_user.first_name

    try:
        tempo_str = context.args[0]
        ms = tempo_para_ms(tempo_str)

        dados = carregar()
        pista_atual = dados.get(chat_id, {}).get("pista_atual")

        if not pista_atual:
            await update.message.reply_text(
                "Defina a pista primeiro:\n/pista Nome da pista"
            )
            return

        ranking = dados[chat_id][pista_atual]

        if user not in ranking or ms < ranking[user]["ms"]:
            ranking[user] = {"tempo": tempo_str, "ms": ms}
            salvar(dados)
            await update.message.reply_text(
                f"✅ Tempo registrado:\n{user} ⏱️ {tempo_str}"
            )
        else:
            await update.message.reply_text(
                f"⛔ Tempo maior que o atual.\nSeu melhor: {ranking[user]['tempo']}"
            )
    except:
        await update.message.reply_text("Uso correto:\n/tempo 1:18.732")

async def rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    dados = carregar()
    pista_atual = dados.get(chat_id, {}).get("pista_atual")

    if not pista_atual:
        await update.message.reply_text("Nenhuma pista definida.")
        return

    ranking = dados.get(chat_id, {}).get(pista_atual, {})

    if not ranking:
        await update.message.reply_text("Ranking vazio 😴")
        return

    ordenado = sorted(ranking.items(), key=lambda x: x[1]["ms"])

    texto = f"🏆 *RANKING – {pista_atual}*\n\n"
    for i, (nome, info) in enumerate(ordenado, start=1):
        texto += f"{i}º {nome} ⏱️ {info['tempo']}\n"

    await update.message.reply_text(texto, parse_mode="Markdown")

async def historico_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    historico = carregar_historico()

    if chat_id not in historico:
        await update.message.reply_text("Nenhum histórico ainda 😴")
        return

    texto = "📚 *HISTÓRICO DE EVENTOS*\n\n"

    for evento in historico[chat_id][-5:]:
        texto += f"📅 {evento['data']} – {evento['pista']}\n"
        ranking = sorted(evento["ranking"].items(), key=lambda x: x[1]["ms"])
        for i, (nome, info) in enumerate(ranking[:3], start=1):
            medalha = ["🥇", "🥈", "🥉"][i-1]
            texto += f"{medalha} {nome} ⏱️ {info['tempo']}\n"
        texto += "\n"

    await update.message.reply_text(texto, parse_mode="Markdown")

# ----------------- Reset semanal -----------------

async def reset_semanal(context: ContextTypes.DEFAULT_TYPE):
    dados = carregar()
    historico = carregar_historico()
    data = datetime.now().strftime("%d/%m/%Y")

    for chat_id, conteudo in dados.items():
        pista = conteudo.get("pista_atual")
        if pista and pista in conteudo:
            ranking = conteudo[pista]
            if ranking:
                historico.setdefault(chat_id, [])
                historico[chat_id].append({
                    "data": data,
                    "pista": pista,
                    "ranking": ranking
                })
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🔄 Evento encerrado!\nPista: {pista}\nHistórico salvo."
                )
        dados[chat_id] = {}

    salvar(dados)
    salvar_historico(historico)

# ----------------- Inicialização -----------------

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("pista", pista))
    app.add_handler(CommandHandler("tempo", tempo))
    app.add_handler(CommandHandler("rank", rank))
    app.add_handler(CommandHandler("historico", historico_cmd))

    fuso = pytz.timezone("America/Sao_Paulo")
    app.job_queue.run_daily(
        reset_semanal,
        time=time(hour=9, minute=0, tzinfo=fuso),
        days=(5,)  # sábado
    )

    print("Bot iniciado...")
    app.run_polling()

if __name__ == "__main__":
    main()

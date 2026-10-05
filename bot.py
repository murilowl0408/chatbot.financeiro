"""
bot.py  -  A "boca e ouvido" do bot: conversa com o Telegram.

Fluxo: você manda mensagem -> o Telegram entrega aqui -> chamamos gastos.py
para entender/guardar/somar -> respondemos.
"""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (Application, CommandHandler, ContextTypes,
                          MessageHandler, filters)

import gastos

# Lê o arquivo com o token e o seu ID (aceita ".env" ou "api_telegram.env",
# na mesma pasta deste arquivo).
PASTA = Path(__file__).parent
load_dotenv(PASTA / ".env")
load_dotenv(PASTA / "api_telegram.env")

TOKEN = os.getenv("TELEGRAM_TOKEN")
MEU_ID = int(os.getenv("MEU_ID")) if os.getenv("MEU_ID") else None

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

AJUDA = (
    "💰 Bot de gastos\n\n"
    "Para registrar, mande assim:\n"
    "  comida 50\n"
    "  uber 23,90 pix\n"
    "  mercado 180 credito\n\n"
    "A forma de pagamento (credito, debito, pix, dinheiro) é opcional.\n\n"
    "Comandos:\n"
    "  /resumo - total do mês e por categoria\n"
    "  /resumo fevereiro - resumo de fevereiro (deste ano)\n"
    "  /resumo fevereiro 2026 - de um ano específico\n"
    "  /ano - total de cada mês do ano\n"
    "  /ano 2026 - o mesmo, de outro ano\n"
    "  /formas - crédito, débito, pix... (aceita mês também)\n"
    "  /ultima - última compra registrada\n"
    "  /apagar - apaga o último registro\n"
    "  /limpar - apaga TUDO (pede confirmação)"
)


async def autorizado(update: Update) -> bool:
    """Só você pode usar o bot. Qualquer outra pessoa é ignorada."""
    usuario = update.effective_user

    if MEU_ID is None:
        await update.message.reply_text(
            f"Seu ID do Telegram é: {usuario.id}\n\n"
            "Coloque esse número no arquivo do token (linha MEU_ID=...) "
            "e reinicie o bot."
        )
        return False

    return usuario.id == MEU_ID


async def pegar_periodo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lê 'fevereiro 2026' etc. Se der erro, avisa e devolve None."""
    try:
        return gastos.entender_periodo(context.args)
    except ValueError as erro:
        await update.message.reply_text(f"⚠️ {erro}")
        return None


async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await autorizado(update):
        return
    await update.message.reply_text(AJUDA)


async def registrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qualquer mensagem de texto que NÃO é comando cai aqui."""
    if not await autorizado(update):
        return
    try:
        categoria, valor, forma = gastos.entender_mensagem(update.message.text)
    except ValueError as erro:
        await update.message.reply_text(f"⚠️ {erro}")
        return

    gastos.adicionar(categoria, valor, forma)

    ano, mes = gastos.mes_atual()
    total = gastos.total_do_mes(ano, mes)
    nome_forma = gastos.NOMES_FORMA[forma]
    await update.message.reply_text(
        f"✅ Salvo: {categoria} — {gastos.formatar_valor(valor)} ({nome_forma})\n"
        f"Total do mês: {gastos.formatar_valor(total)}"
    )


async def resumo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await autorizado(update):
        return
    periodo = await pegar_periodo(update, context)
    if periodo is None:
        return
    ano, mes = periodo

    total = gastos.total_do_mes(ano, mes)
    if total == 0:
        await update.message.reply_text(f"Nenhum gasto em {gastos.MESES[mes - 1]}/{ano}.")
        return

    linhas = [f"📊 Resumo de {gastos.MESES[mes - 1]}/{ano}",
              f"Total: {gastos.formatar_valor(total)}", "", "Por categoria:"]
    for categoria, valor in gastos.total_por_categoria(ano, mes):
        linhas.append(f"• {categoria}: {gastos.formatar_valor(valor)}")
    await update.message.reply_text("\n".join(linhas))


async def resumo_ano(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/ano  ou  /ano 2026"""
    if not await autorizado(update):
        return
    ano, _ = gastos.mes_atual()
    if context.args:
        if not (context.args[0].isdigit() and 2000 <= int(context.args[0]) <= 2100):
            await update.message.reply_text("⚠️ Use /ano ou /ano 2026.")
            return
        ano = int(context.args[0])

    meses = gastos.total_por_mes_do_ano(ano)
    if not meses:
        await update.message.reply_text(f"Nenhum gasto em {ano}.")
        return

    linhas = [f"📅 Gastos de {ano}"]
    soma = 0
    for mes, total in meses:
        linhas.append(f"• {gastos.MESES[mes - 1]}: {gastos.formatar_valor(total)}")
        soma += total
    linhas += ["", f"Total do ano: {gastos.formatar_valor(soma)}"]
    await update.message.reply_text("\n".join(linhas))


async def ultima(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await autorizado(update):
        return
    gasto = gastos.ultimo_gasto()
    if gasto is None:
        await update.message.reply_text("Ainda não tem nenhum gasto registrado.")
        return
    await update.message.reply_text(
        f"🧾 Última compra: {gasto['categoria']} — "
        f"{gastos.formatar_valor(gasto['valor_centavos'])} "
        f"({gastos.NOMES_FORMA[gasto['forma']]})\n"
        f"Em {gastos.formatar_data(gasto['data'])}"
    )


async def formas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await autorizado(update):
        return
    periodo = await pegar_periodo(update, context)
    if periodo is None:
        return
    ano, mes = periodo

    dados = gastos.total_por_forma(ano, mes)
    if not dados:
        await update.message.reply_text(f"Nenhum gasto em {gastos.MESES[mes - 1]}/{ano}.")
        return
    linhas = [f"💳 Por forma de pagamento ({gastos.MESES[mes - 1]}/{ano}):"]
    for forma, valor in dados:
        linhas.append(f"• {gastos.NOMES_FORMA[forma]}: {gastos.formatar_valor(valor)}")
    await update.message.reply_text("\n".join(linhas))


async def apagar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await autorizado(update):
        return
    gasto = gastos.apagar_ultimo()
    if gasto is None:
        await update.message.reply_text("Não tem nada para apagar.")
        return
    await update.message.reply_text(
        f"🗑️ Apaguei: {gasto['categoria']} — {gastos.formatar_valor(gasto['valor_centavos'])}"
    )


async def limpar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Apaga TUDO, mas só se você escrever '/limpar confirmar'."""
    if not await autorizado(update):
        return

    if context.args and context.args[0].lower() == "confirmar":
        quantidade, backup = gastos.limpar_tudo()
        if quantidade == 0:
            await update.message.reply_text("Não tinha nada para apagar.")
            return
        await update.message.reply_text(
            f"🧹 Apaguei {quantidade} registros.\n"
            f"Guardei uma cópia de segurança: {backup} (na pasta do bot)."
        )
        return

    await update.message.reply_text(
        f"⚠️ Isso apaga TODOS os {gastos.contar_gastos()} registros.\n"
        "Antes, eu salvo uma cópia de segurança.\n\n"
        "Para confirmar, mande exatamente:\n/limpar confirmar"
    )


def main():
    if not TOKEN:
        raise SystemExit("Faltou o TELEGRAM_TOKEN. Confira o arquivo do token.")

    gastos.criar_tabela()

    app = Application.builder().token(TOKEN).build()

    # Cada "handler" liga um tipo de mensagem a uma função.
    app.add_handler(CommandHandler(["start", "ajuda"], ajuda))
    app.add_handler(CommandHandler("resumo", resumo))
    app.add_handler(CommandHandler("ano", resumo_ano))
    app.add_handler(CommandHandler("ultima", ultima))
    app.add_handler(CommandHandler("formas", formas))
    app.add_handler(CommandHandler("apagar", apagar))
    app.add_handler(CommandHandler("limpar", limpar))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, registrar))

    print("Bot ligado! Aperte Ctrl+C para desligar.")
    app.run_polling()   # fica perguntando ao Telegram: "tem mensagem nova?"


if __name__ == "__main__":
    main()
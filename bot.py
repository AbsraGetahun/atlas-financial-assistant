import io
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from pypdf import PdfReader
from apscheduler.schedulers.background import BackgroundScheduler

from config import TELEGRAM_BOT_TOKEN
from database import init_db, SessionLocal, User
from ai_agent import AIAgent

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()
scheduler.start()


# ── Handlers ──────────────────────────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db = SessionLocal()
    try:
        agent = AIAgent(db, user.id)
        agent.user.first_name = user.first_name
        agent.user.username = user.username
        db.commit()
        await update.message.reply_text(
            f"Hey {user.first_name}! I'm Atlas — your AI financial analyst.\n\n"
            "I track stocks, analyze reports, answer market questions, and send you smart briefings. "
            "Just talk to me like you would a colleague — no commands needed.\n\n"
            "To get started: what's your role? Investor, analyst, founder, or something else?"
        )
    finally:
        db.close()


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show confirmation button before wiping chat history."""
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Yes, start fresh", callback_data="confirm_reset"),
            InlineKeyboardButton("Cancel", callback_data="cancel_reset"),
        ]
    ])
    await update.message.reply_text(
        "This will clear our entire conversation history and reset your profile.\n\nAre you sure?",
        reply_markup=keyboard
    )


async def handle_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the inline button response for reset."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "confirm_reset":
        db = SessionLocal()
        try:
            agent = AIAgent(db, user_id)
            agent.clear_history()
            # Also reset profile
            agent.user.role = None
            agent.user.interests = None
            agent.user.onboarded = False
            agent.user.briefing_time = "08:00"
            # Clear watchlist
            from database import WatchlistItem, PriceAlert
            db.query(WatchlistItem).filter(WatchlistItem.user_id == user_id).delete()
            db.query(PriceAlert).filter(PriceAlert.user_id == user_id).delete()
            db.commit()
        finally:
            db.close()
        await query.edit_message_text(
            "Done — we're starting fresh. What would you like to talk about?"
        )
    else:
        await query.edit_message_text("No worries, nothing was changed.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text

    # Let users say "reset" or "start over" naturally without knowing the command
    if user_text.lower().strip() in ["reset", "start over", "clear chat", "restart"]:
        await reset_command(update, context)
        return

    await update.message.reply_chat_action(action="typing")
    db = SessionLocal()
    try:
        agent = AIAgent(db, user_id)
        reply = agent.process_message(user_text)
        await update.message.reply_text(reply)
    except Exception as e:
        logger.error(f"Message error: {e}")
        await update.message.reply_text("Hit a snag there — mind rephrasing or trying again?")
    finally:
        db.close()


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_chat_action(action="typing")
    db = SessionLocal()
    try:
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        buf = io.BytesIO()
        await voice_file.download_to_memory(out=buf)
        buf.seek(0)

        agent = AIAgent(db, user_id)
        transcribed = agent.transcribe_voice(buf.read())

        if transcribed.startswith("["):
            await update.message.reply_text(transcribed)
            return

        await update.message.reply_text(f"🎙️ _{transcribed}_", parse_mode="Markdown")
        reply = agent.process_message(transcribed)
        await update.message.reply_text(reply)
    except Exception as e:
        logger.error(f"Voice error: {e}")
        await update.message.reply_text("Had trouble with that voice message. Try again?")
    finally:
        db.close()


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    caption = update.message.caption or ""
    await update.message.reply_chat_action(action="typing")
    db = SessionLocal()
    try:
        photo_file = await context.bot.get_file(update.message.photo[-1].file_id)
        buf = io.BytesIO()
        await photo_file.download_to_memory(out=buf)
        buf.seek(0)
        agent = AIAgent(db, user_id)
        reply = agent.analyze_image(buf.read(), caption=caption)
        await update.message.reply_text(reply)
    except Exception as e:
        logger.error(f"Photo error: {e}")
        await update.message.reply_text("Had trouble analyzing that image. Try again?")
    finally:
        db.close()


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    document = update.message.document
    file_name = (document.file_name or "").lower()

    # Image documents
    if any(file_name.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]):
        await update.message.reply_chat_action(action="typing")
        db = SessionLocal()
        try:
            doc_file = await context.bot.get_file(document.file_id)
            buf = io.BytesIO()
            await doc_file.download_to_memory(out=buf)
            buf.seek(0)
            agent = AIAgent(db, user_id)
            reply = agent.analyze_image(buf.read(), caption=update.message.caption or "")
            await update.message.reply_text(reply)
        except Exception as e:
            logger.error(f"Image doc error: {e}")
            await update.message.reply_text("Had trouble with that image. Try again?")
        finally:
            db.close()
        return

    if not file_name.endswith(".pdf"):
        await update.message.reply_text("Send me a PDF or image and I'll analyze it for you.")
        return

    await update.message.reply_text("Got it, analyzing your document now...")
    await update.message.reply_chat_action(action="typing")
    db = SessionLocal()
    try:
        new_file = await context.bot.get_file(document.file_id)
        buf = io.BytesIO()
        await new_file.download_to_memory(out=buf)
        buf.seek(0)

        reader = PdfReader(buf)
        text = ""
        for page in reader.pages[:15]:
            text += (page.extract_text() or "") + "\n"

        if not text.strip():
            await update.message.reply_text(
                "This PDF doesn't have extractable text — it may be scanned. "
                "Try sending it as a photo instead."
            )
            return

        agent = AIAgent(db, user_id)
        await update.message.reply_text(agent.analyze_document(text))
    except Exception as e:
        logger.error(f"Document error: {e}")
        await update.message.reply_text("Had trouble reading that PDF. Make sure it's not a scanned image-only file.")
    finally:
        db.close()


# ── Scheduled jobs ─────────────────────────────────────────────────────────────

def send_messages_sync(bot, messages):
    """Helper to send messages synchronously with proper event loop handling."""
    try:
        loop = asyncio.get_running_loop()
        # We're in an async context
        for chat_id, text in messages:
            asyncio.create_task(bot.send_message(chat_id=chat_id, text=text))
    except RuntimeError:
        # No running loop, use asyncio.run()
        async def send_all():
            for chat_id, text in messages:
                await bot.send_message(chat_id=chat_id, text=text)
        asyncio.run(send_all())

def _run_for_all_users(bot, method_name: str):
    """Generic runner for morning/evening broadcast jobs."""
    db = SessionLocal()
    messages = []
    try:
        users = db.query(User).filter(User.onboarded == True).all()
        for user in users:
            try:
                agent = AIAgent(db, user.id)
                msg = getattr(agent, method_name)()
                if msg:
                    messages.append((user.id, msg))
            except Exception as e:
                logger.error(f"Broadcast error for user {user.id}: {e}")
    finally:
        db.close()
    
    if messages:
        send_messages_sync(bot, messages)


def send_morning_briefings(bot):
    _run_for_all_users(bot, "get_morning_brief")


def send_evening_summaries(bot):
    _run_for_all_users(bot, "get_evening_summary")


def check_all_alerts(bot):
    """Check price alerts for all users and fire notifications."""
    db = SessionLocal()
    messages = []
    try:
        users = db.query(User).filter(User.onboarded == True).all()
        for user in users:
            try:
                agent = AIAgent(db, user.id)
                triggered = agent.check_alerts()
                for msg in triggered:
                    messages.append((user.id, msg))
            except Exception as e:
                logger.error(f"Alert check error for user {user.id}: {e}")
    finally:
        db.close()
    
    if messages:
        send_messages_sync(bot, messages)


async def clear_webhook(bot):
    """Clear any existing webhook to avoid conflicts."""
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook cleared successfully")
    except Exception as e:
        logger.warning(f"Could not clear webhook: {e}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    init_db()

    if not TELEGRAM_BOT_TOKEN:
        logger.error("No TELEGRAM_BOT_TOKEN set. Exiting.")
        return

    # Create application
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Clear webhook synchronously
    try:
        # Try to run with existing loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(clear_webhook(app.bot))
        else:
            loop.run_until_complete(clear_webhook(app.bot))
    except RuntimeError:
        # No loop, create one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(clear_webhook(app.bot))
        loop.close()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CallbackQueryHandler(handle_reset_callback, pattern="^(confirm|cancel)_reset$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Morning briefing at 8:00 AM
    scheduler.add_job(send_morning_briefings, "cron", hour=8, minute=0,
                      args=[app.bot], id="morning_brief")
    # Evening summary at 5:00 PM
    scheduler.add_job(send_evening_summaries, "cron", hour=17, minute=0,
                      args=[app.bot], id="evening_summary")
    # Price alert checks every 15 minutes
    scheduler.add_job(check_all_alerts, "interval", minutes=15,
                      args=[app.bot], id="alert_checker")

    logger.info("Atlas bot starting...")
    
    # Create and set an event loop for the main thread
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        app.run_polling()
    except Exception as e:
        if "Conflict" in str(e):
            logger.error("Conflict detected! Another bot instance is running.")
            logger.info("Attempting to clear webhook...")
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(clear_webhook(app.bot))
                loop.close()
                logger.info("Webhook cleared. Please restart the bot.")
            except Exception as clear_error:
                logger.error(f"Failed to clear webhook: {clear_error}")
        else:
            logger.error(f"Bot failed to start: {e}")
            raise


if __name__ == "__main__":
    main()
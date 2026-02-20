import logging
import asyncio
import uuid
from typing import Optional
from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from src.config import settings
from src.core.events import AgentEvent, InputSource
from src.perception.gateway import UnifiedGateway

logger = logging.getLogger(__name__)

class TelegramBot:
    """
    Telegram Bot Interface for the Agent.
    Connects Telegram updates to the UnifiedGateway.
    """
    
    def __init__(self, gateway: UnifiedGateway):
        self.gateway = gateway
        self.app: Optional[Application] = None
        self.bot_token = settings.TELEGRAM_BOT_TOKEN

    async def initialize(self):
        pass # Moved to thread

    def run_in_thread(self):
        """Run bot polling in a separate thread."""
        if not self.bot_token:
             return

        logger.info("Starting Telegram Bot polling in separate thread...")
        
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Build Application INSIDE the thread's loop
        self.app = ApplicationBuilder().token(self.bot_token).build()
        
        # Handlers
        start_handler = CommandHandler('start', self.start)
        message_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_message)
        
        self.app.add_handler(start_handler)
        self.app.add_handler(message_handler)

        # run_polling blocks, so must be in thread
        self.app.run_polling(stop_signals=None)
        
        loop.close()

    async def stop(self):
        if self.app:
            # shutdown is handled by run_polling's signal or updater.stop()
            # Here we just want to ensure it closes roughly from the outside if needed.
            # But run_polling handles lifecycle. We might just need to stop the loop.
            # Actually, let's just use updater.stop() if possible or let it be.
            # For simplicity in this architecture, we rely on daemon thread or exact stop.
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.info(f"Command /start received from {update.effective_user.id}")
        await update.message.reply_text(
            "您好！我是您的 AI 助理。您可以直接與我對話，我具備寫程式與自我進化的能力。"
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.info(f"Raw Update received: {update}")
        if not update.message or not update.message.text:
            logger.info("Update contains no message or text.")
            return
            
        chat_id = update.effective_chat.id
        user_text = update.message.text
        
        # Map Telegram chat_id to Agent session_id
        session_id = f"telegram_{chat_id}"
        
        logger.info(f"Received Telegram message from {chat_id}: {user_text}")
        
        # Create Event
        event = AgentEvent(
            event_id=str(uuid.uuid4()),
            source=InputSource.TELEGRAM,
            session_id=session_id,
            content=user_text
        )
        
        # Provide real-time status updates via callback
        async def send_status(msg: str):
            try:
                await context.bot.send_message(chat_id=chat_id, text=msg)
            except Exception as e:
                logger.error(f"Error sending status update: {e}")

        # Send to Gateway
        try:
            # Show "typing..." status
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            
            response = await self.gateway.process(event, status_callback=send_status)
            
            # Reply to user
            await update.message.reply_text(response.content)
            
        except Exception as e:
            logger.error(f"Error processing Telegram message: {e}")
            await update.message.reply_text("抱歉，我遇到了一些問題，請稍後再試。")

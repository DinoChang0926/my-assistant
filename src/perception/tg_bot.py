from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from ..core.events import AgentEvent, InputSource
from .gateway import UnifiedGateway
import uuid

class TelegramBot:
    def __init__(self, token: str, gateway: UnifiedGateway):
        self.token = token
        self.gateway = gateway
        self.app = ApplicationBuilder().token(token).build()
        self._setup_handlers()

    def _setup_handlers(self):
        self.app.add_handler(CommandHandler("start", self._start_command))
        self.app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self._handle_message))

    async def _start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("你好！我是你的 AI 助手。請直接發送訊息與我對話。")

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        event = AgentEvent(
            event_id=str(uuid.uuid4()),
            source=InputSource.TELEGRAM,
            session_id=f"tg_{update.effective_chat.id}",
            content=update.message.text
        )
        
        response = await self.gateway.process(event)
        await update.message.reply_text(response.content)

    async def start_polling(self):
        print("Telegram Bot starting polling...")
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()

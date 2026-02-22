import logging
import asyncio
import uuid
import json
import html
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
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
        """Initialize the bot application."""
        if not self.bot_token:
            return
        logger.info("Initializing Telegram Bot...")
        self.app = ApplicationBuilder().token(self.bot_token).build()
        
        # Handlers
        self.app.add_handler(CommandHandler('start', self.handle_start))
        self.app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_message))
        self.app.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback_query))
        
        await self.app.initialize()

    async def start_bot(self):
        """Start the bot polling."""
        if not self.app:
            await self.initialize()
        
        if self.app:
            logger.info("Starting Telegram Bot polling (Async)...")
            await self.app.start()
            await self.app.updater.start_polling(drop_pending_updates=True)

    async def stop(self):
        """Shutdown the bot."""
        if self.app:
            logger.info("Stopping Telegram Bot...")
            if self.app.updater.running:
                await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.info(f"Command /start received from {update.effective_user.id}")
        await update.message.reply_text(
            "您好！我是您的 AI 助理。您可以直接與我對話，我具備寫程式與自我進化的能力。"
        )

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle Inline Keyboard button clicks."""
        query = update.callback_query
        await query.answer()  # Acknowledge the button press (removes loading state)
        
        chat_id = update.effective_chat.id
        callback_data = query.data
        session_id = f"telegram_{chat_id}"
        
        logger.info(f"Received callback query from {chat_id}: {callback_data}")
        
        # Show which button was pressed by editing the original message
        original_text = query.message.text or ""
        safe_original = html.escape(original_text)
        safe_callback = html.escape(callback_data)
        
        await query.edit_message_text(
            text=f"{safe_original}\n\n✅ 你選擇了：<b>{safe_callback}</b>",
            parse_mode="HTML",
            reply_markup=None  # Remove the keyboard after selection
        )
        
        # Send the selected option to the AI agent as if user typed it
        event = AgentEvent(
            event_id=str(uuid.uuid4()),
            source=InputSource.TELEGRAM,
            session_id=session_id,
            content=callback_data
        )
        
        async def send_status(msg: str):
            await self._send_message_or_buttons(context, chat_id, msg)
        
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            response = await self.gateway.process(event, status_callback=send_status)
            reply_content = response.content if response.content and response.content.strip() else None
            if reply_content:
                await self._send_message_or_buttons(context, chat_id, reply_content)
        except Exception as e:
            logger.error(f"Error processing callback query: {e}")
            await context.bot.send_message(chat_id=chat_id, text=f"⚠️ 處理選項時發生錯誤：{str(e)[:200]}")

    async def _send_message_or_buttons(self, context, chat_id: int, msg: str):
        """智慧傳送：偵測是否為按鈕 payload，若是則傳送 Inline Keyboard；否則傳送普通訊息。"""
        # 偵測特殊按鈕 payload
        if msg.strip().startswith('{') and '"__type": "inline_keyboard"' in msg:
            try:
                payload = json.loads(msg)
                keyboard = []
                for row in payload.get("keyboard", []):
                    btn_row = [
                        InlineKeyboardButton(text=b["text"], callback_data=b.get("callback_data", b["text"]))
                        for b in row
                    ]
                    keyboard.append(btn_row)
                reply_markup = InlineKeyboardMarkup(keyboard)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=payload.get("text", "請選擇："),
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
                return
            except Exception as e:
                logger.warning(f"Failed to parse button payload, falling back to text: {e}")
        
        # 普通文字訊息
        if msg and msg.strip():
            await context.bot.send_message(chat_id=chat_id, text=msg)

    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle document uploads from Telegram."""
        if not update.message or not update.message.document:
            return
            
        chat_id = update.effective_chat.id
        doc = update.message.document
        file_name = doc.file_name
        
        logger.info(f"Received document from {chat_id}: {file_name}")
        
        # Ensure storage exists
        import os
        os.makedirs("storage", exist_ok=True)
        
        # Automatic mapping for Google Credentials
        target_path = os.path.join("storage", file_name)
        if file_name.startswith("client_secret") and file_name.endswith(".json"):
            target_path = os.path.join("storage", "google_credentials.json")
            await update.message.reply_text(f"📥 已收到憑證檔案，將自動儲存為 google_credentials.json。正在通知助理處理中...")
        else:
            await update.message.reply_text(f"📥 已收到檔案：{file_name}，已存入伺服器 storage 資料夾。")

        try:
            # Download file
            new_file = await context.bot.get_file(doc.file_id)
            await new_file.download_to_drive(target_path)
            logger.info(f"File saved to {target_path}")

            # Notify Agent about the file
            session_id = f"telegram_{chat_id}"
            event = AgentEvent(
                event_id=str(uuid.uuid4()),
                source=InputSource.TELEGRAM,
                session_id=session_id,
                content=f"系統通知：使用者剛剛上傳了一個檔案名為 '{file_name}'。如果是 Google 憑證，我已經將它存放在 'storage/google_credentials.json' 了。請檢查並繼續剛才的任務。"
            )

            async def send_status(msg: str):
                await self._send_message_or_buttons(context, chat_id, msg)

            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            response = await self.gateway.process(event, status_callback=send_status)
            
            # Guard against empty response
            reply_content = response.content if response.content and response.content.strip() else None
            if reply_content:
                await self._send_message_or_buttons(context, chat_id, reply_content)
            else:
                await context.bot.send_message(chat_id=chat_id, text="✅ 檔案已成功處理，系統已記錄相關資訊。")

        except Exception as e:
            import traceback
            err_detail = traceback.format_exc()
            logger.error(f"Error handling document: {err_detail}")
            await update.message.reply_text(
                f"⚠️ 處理文件時發生錯誤：\n`{type(e).__name__}: {e}`\n\n請檢查日誌或告知我要如何處理。"
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
            await self._send_message_or_buttons(context, chat_id, msg)

        # Send to Gateway
        try:
            # Show "typing..." status
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            
            response = await self.gateway.process(event, status_callback=send_status)
            
            # Guard against empty response (e.g. SDK 400 error)
            reply_content = response.content if response.content and response.content.strip() else None
            if reply_content:
                await self._send_message_or_buttons(context, chat_id, reply_content)
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="⚠️ AI 模型沒有回傳任何內容（可能是請求內容過大或 API 限制）。\n"
                    "如果這個問題持續出現，請告知我，我可以嘗試縮減對話上下文。"
                )
            
        except Exception as e:
            import traceback
            err_detail = traceback.format_exc()
            logger.error(f"Error processing Telegram message: {err_detail}")
            # 主動回報錯誤細節，讓使用者與助理可以協作除錯
            short_err = html.escape(str(e)[:300])
            await update.message.reply_html(
                f"⚠️ 我遇到了一個錯誤，需要請你協助：\n\n"
                f"<b>錯誤類型</b>：<code>{type(e).__name__}</code>\n"
                f"<b>訊息</b>：{short_err}\n\n"
                f"如果你覺得這是系統問題，可以叫我查看 logs 或重新啟動相關服務。"
            )

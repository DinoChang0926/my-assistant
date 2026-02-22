import asyncio
from typing import List, Optional
from pydantic import Field
from src.tools.base import BaseTool


class SendTelegramButtonsTool(BaseTool):
    """
    傳送帶有 Inline Keyboard（按鈕）的 Telegram 訊息。
    當需要讓使用者做選擇時（如確認/取消），應優先使用按鈕而非要求使用者手動輸入。
    點擊後的選項會像普通文字訊息一樣被 Bot 處理。
    """
    name: str = "send_telegram_buttons"
    category: str = "telegram_ui"
    description: str = (
        "傳送帶有 Inline Keyboard 按鈕的 Telegram 訊息，讓使用者點擊選擇。\n"
        "使用時機：\n"
        "- 需要使用者做確認時（例如：「確認/取消」）\n"
        "- 提供多個選項時（例如：「A / B / C」）\n"
        "- 任何情況下，只要原本會要使用者手動輸入 A/B/C 之類的選項\n"
        "注意：使用者點擊按鈕後，選項文字會當作普通訊息傳回給我處理。"
    )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "按鈕上方的說明文字（支援 Markdown）"
                },
                "buttons": {
                    "type": "array",
                    "description": "按鈕列表，每個群組是一行",
                    "items": {
                        "type": "array",
                        "description": "同一行的按鈕列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {
                                    "type": "string",
                                    "description": "按鈕上顯示的文字"
                                },
                                "callback_data": {
                                    "type": "string",
                                    "description": "點擊按鈕後傳回的文字/指令（最多 64 bytes）"
                                }
                            },
                            "required": ["text", "callback_data"]
                        }
                    }
                }
            },
            "required": ["text", "buttons"]
        }

    async def execute(self, **kwargs) -> dict:
        text = kwargs.get("text", "請選擇：")
        buttons_config = kwargs.get("buttons", [])
        status_callback = kwargs.get("status_callback")

        if not status_callback:
            return {
                "status": "error",
                "message": "此工具需要 status_callback 才能傳送 Telegram 訊息。請確認是透過 Telegram 觸發的對話。"
            }

        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            keyboard = []
            for row in buttons_config:
                btn_row = []
                for btn in row:
                    btn_row.append(
                        InlineKeyboardButton(
                            text=btn.get("text", ""),
                            callback_data=btn.get("callback_data", btn.get("text", ""))
                        )
                    )
                keyboard.append(btn_row)

            reply_markup = InlineKeyboardMarkup(keyboard)

            # 利用 status_callback 的閉包訪問 bot 和 chat_id
            # 我們透過特殊的包裝格式觸發按鈕傳送
            # 在 telegram_bot.py 的 send_status 中檢查特殊前綴來區分按鈕訊息
            import json
            button_payload = json.dumps({
                "__type": "inline_keyboard",
                "text": text,
                "keyboard": [[{"text": b["text"], "callback_data": b.get("callback_data", b["text"])} for b in row] for row in buttons_config]
            })
            await status_callback(button_payload)

            return {
                "status": "success",
                "message": f"已傳送含 {sum(len(row) for row in buttons_config)} 個按鈕的選單給使用者。等待使用者點擊..."
            }

        except Exception as e:
            import traceback
            return {
                "status": "error",
                "message": f"傳送按鈕失敗: {str(e)}\n{traceback.format_exc()}"
            }

#!/usr/bin/env python3
import asyncio
import os
from dotenv import load_dotenv
from copilot import CopilotClient, MessageOptions, SessionEvent

# Load environment variables
load_dotenv(override=True)

async def main():
    try:
        client = CopilotClient()
        
        # 1. 定義事件處理函式 (Event Handler)
        # 這是核心：我們不再用迴圈去輪詢，而是被動接收事件
        def on_event(event: SessionEvent):
            if event.type == "assistant.message":
                print(f"\n[🤖 Copilot]: {event.data.content}", end="", flush=True)
            elif event.type == "session.idle":
                print("\n\n[✅ Task Completed] Session is idle.")
            elif event.type == "tool.execution":
                print(f"\n[🛠️ Tool Check] Executing tool: {event.data.name}...")
            elif event.type == "session.error":
                print(f"\n[❌ Error] {event.data.message}")

        # 2. 建立 Session
        print("Creating session...")
        session = await client.create_session({
            "model": os.getenv('COPILOT_MODEL', 'claude-3.5-sonnet')
        })

        # 3. 註冊監聽器
        unsubscribe = session.on(on_event)

        # 4. 發送請求 (非阻塞 - Non-blocking)
        # 注意這裡我們用 send() 而不是 send_and_wait()
        # 這樣程式可以繼續往下執行，或者就只是掛著等事件
        prompt = "請幫我寫一個 Python 的 Hello World，並解釋程式碼。"
        print(f"Sending prompt: {prompt}")
        await session.send(MessageOptions(prompt=prompt))

        # 5. 保持程式運行直到任務結束
        # 這裡我們用 asyncio.Event 來等待 "結束信號"，而不是 while True
        # 實務上你可能會在 session.idle 事件觸發時設定這個 event
        done_event = asyncio.Event()

        # 修改一下 handler 來觸發結束信號
        def completion_handler(event: SessionEvent):
            if event.type == "session.idle":
                done_event.set()
        
        # 註冊第二個 handler 專門處理結束邏輯
        session.on(completion_handler)

        print("Waiting for events...")
        await done_event.wait() # 這會暫停直到 done_event.set() 被呼叫

        print("\n\nDemo finished.")
        unsubscribe()
        await session.destroy()
        await client.stop()

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())

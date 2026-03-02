import asyncio
import uuid
import json
from pathlib import Path
from src.tools.base import BaseTool
from src.core.events import AgentEvent, InputSource
from src.config import settings

class DelegateToMechanicTool(BaseTool):
    """
    允許主助理將開發新工具、系統重構等進階需求委派給專屬的 EVOLUTION_MECHANIC 子助理。
    """
    
    def __init__(self, orchestrator=None, task_manager=None):
        self.orchestrator = orchestrator
        self.task_manager = task_manager

    @property
    def name(self) -> str:
        return "delegate_to_mechanic"

    @property
    def category(self) -> str:
        return "system"

    @property
    def description(self) -> str:
        return (
            "將『開發新技能』或『修改系統環境』的任務委託給專業的系統進化技工 (Evolution Mechanic)。\n"
            "當你發現現有工具無法滿足使用者的需要，且該需求適合被開發成一個獨立的 Python 技能時，請使用此工具。"
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "instruction": {
                    "type": "string",
                    "description": "給予技工的具體指示，請詳細描述要開發的新技能規格、需要使用哪些 API、輸入與輸出為何。"
                }
            },
            "required": ["instruction"]
        }

    async def execute(self, **kwargs) -> dict:
        instruction = kwargs.get("instruction")
        if not instruction:
            return {"status": "error", "message": "Missing 'instruction' parameter."}
            
        if not self.orchestrator:
             return {"status": "error", "message": "Orchestrator not injected into DelegateToMechanicTool."}

        # 生成任務 ID
        import uuid
        task_id = f"task_{str(uuid.uuid4())[:8]}"
        
        from src.brain.task_manager import TaskRecord
        from datetime import datetime
        
        task_record = TaskRecord(
            id=task_id,
            instruction=instruction,
            status="pending",
            started_at=datetime.now()
        )
        
        if self.task_manager:
            await self.task_manager.register(task_record)

        print(f"[Delegate] Handing over task {task_id} to EVOLUTION_MECHANIC: {instruction[:50]}...")
        
        from src.core.roles import RoleRegistry
        from src.core.interfaces import RouteConfig
        from src.config import settings

        role = RoleRegistry.EVOLUTION_MECHANIC
        route_config = RouteConfig(
            model_name=settings.COPILOT_EVOLUTION_MODEL,
            system_prompt=(role.system_prompt or ""),
            intent="evolution",
            role=role
        )
        
        # 取出 status_callback 以進行背景推播
        status_callback = kwargs.get("status_callback")
        
        from pathlib import Path
        # 推導路徑：delegate_mechanic.py -> static -> tools -> src -> root -> storage/dynamic_tools/skills_index.json
        skills_index_path = Path(__file__).resolve().parent.parent.parent.parent / "storage" / "dynamic_tools" / "skills_index.json"

        # 建立一個虛擬的委派事件
        delegate_instruction_payload = (
            f"Master 要求你執行以下任務：\n{instruction}\n\n"
            f"### 開發守則與現有資源\n"
            f"1. **Banned Tools**: 絕對不可使用原生寫檔工具 (如 `create`, `view`, `run_command` 等)。\n"
            f"2. **Write Code**: 只能透過專屬的 `create_tool` 技能來寫入新程式碼或複寫（Overwrite）現有工具。你的類別必須繼承 `BaseTool` 並且**一定要實作** `name`, `category`, `description`, `parameters` 屬性與 `execute` 方法，否則會發生載入錯誤！\n"
            f"3. **Do Not Test**: 使用 `create_tool` 建立工具後系統會自動載入，你**絕對不需要、也不允許**自己去執行或測試它（不要管什麼網路限制或無法寄信，只要把工具寫好即可）。\n"
            f"4. **No Config Files**: 絕對**禁止**將帳號密碼或任何設定寫入本地端的 JSON, YAML 或 ENV 檔案中。所有需要的機密資料都**必須**設計成工具的 `parameters`，讓主助理在呼叫時把資料餵給你，不要自己在工具內寫死讀檔邏輯！\n"
            f"5. **No Status Reporting Tools**: 系統有自己的回報機制，**嚴禁**你開發任何命名為 `update_mechanic` 或用來『紀錄開發結果』的附屬工具。你的唯一職責就是產出那一個核心工具！\n"
            f"6. **Use Libraries**: 你可以自由使用 Python 內建模組 (如 `smtplib`, `ssl`, `json` 等) 以及常見套件 (如 `requests`)。系統環境已經為你準備好，請放心引入。\n"
            f"7. **技能重用與擴充優先**: 當你發現需求與既有工具功能相似時，**絕對要優先呼叫 `inspect_tool` 查看它的原始碼**！如果能夠修改該工具使其通用化，請直接覆蓋它，**不要重複開發新工具**！\n"
            f"8. **MVP First**: 若確實需要建新工具，請以最簡可行產品為準，禁止首版過度設計。\n"
            f"9. **現有技能參考**: 請優先讀取 `{skills_index_path}` 這個索引檔，裡面記錄了所有現存工具的名字與描述，藉此判斷是否已有可用工具。"
        )
        
        # 建立一個虛擬的委派事件
        original_session_id = kwargs.get("caller_session_id", "default_user")
        
        from src.core.events import InputSource, AgentEvent
        delegate_event = AgentEvent(
            event_id=str(uuid.uuid4()),
            source=InputSource.API,
            session_id="internal_mechanic_workspace", 
            content=delegate_instruction_payload
        )
        
        async def background_task():
            try:
                if self.task_manager:
                    await self.task_manager.update_status(task_id, "running")
                    
                print(f"[Delegate] Background task {task_id} started.")
                response = await self.orchestrator.execute(delegate_event, route_config)
                
                # 技工完成時，可能以工具呼叫結束（沒有文字回應），content 為空
                # 此時從工具使用紀錄中摘取 fallback 摘要
                safe_response = response.content
                if not safe_response and response.tool_calls:
                    tools_used = [t.get("name", "unknown") for t in response.tool_calls]
                    safe_response = f"技工已使用以下工具完成開發：{', '.join(tools_used)}"
                elif not safe_response:
                    safe_response = "技工已完成任務（無文字回應）"
                    
                if len(safe_response) > 500:
                    safe_response = safe_response[:500] + "\n...(技術細節已隱藏)"
                    
                print(f"[Delegate] Background task {task_id} completed.")
                if self.task_manager:
                    await self.task_manager.update_status(task_id, "done", result=safe_response)
                
                # --- [新增] 主動完工推播 (Push to Supervisor Session) ---
                if status_callback:
                    try:
                        print(f"[Delegate] Triggering push notification to Supervisor for session {original_session_id}...")
                        from src.core.roles import RoleRegistry
                        from src.core.interfaces import RouteConfig
                        
                        # 模擬一個對主助理說的隱藏訊息，引導它做出自然的完工回報
                        push_payload = (
                            f"【系統通知：背景任務完工】\n"
                            f"任務 ID: {task_id}\n"
                            f"成果摘要：{safe_response}\n\n"
                            f"請使用您作為主助理的人類口吻，主動告知使用者此任務已完成。如果開發成功，請鼓勵使用者測試新工具。\n"
                            f"【重要指示】如果使用者後續要你執行這個新工具，你目前的 Session 預設是看不到它的（因受保護而鎖定）。那時你必須先傳送 Telegram 按鈕詢問使用者是否要「升級對話以載入新工具」，或者你直接使用 `activate_tools` (categories=['system', 'web']) 工具主動升級 Session，升級後你就能順利呼叫新產生出來的工具了！絕對不要以為你需要依賴 PowerShell。"
                        )
                        
                        # 建立推播事件
                        push_event = AgentEvent(
                            event_id=f"push_{uuid.uuid4()}",
                            source=InputSource.API,
                            session_id=original_session_id,
                            content=push_payload
                        )
                        
                        # 指定角色為 SUPERVISOR，確保由主助理來解釋
                        supervisor_role = RoleRegistry.SUPERVISOR
                        supervisor_route = RouteConfig(
                            model_name=settings.COPILOT_MODEL,
                            system_prompt=supervisor_role.system_prompt,
                            intent="general",
                            role=supervisor_role
                        )
                        
                        # 執行主助理 Session (這會讓主助理看到訊息並產生一段對話)
                        push_response = await self.orchestrator.execute(push_event, supervisor_route)
                        
                        # 將主助理說的「人話」推播給 Telegram 使用者
                        if push_response and push_response.content:
                            await status_callback(push_response.content)
                    except Exception as push_err:
                        print(f"[Delegate] Failed to push notification: {push_err}")
                
            except asyncio.CancelledError:
                print(f"[Delegate] Background task {task_id} was CANCELLED.")
                if self.task_manager:
                    await self.task_manager.update_status(task_id, "cancelled")
            except Exception as e:
                error_msg = f"委派任務背景執行時發生錯誤: {str(e)}"
                print(f"[Delegate] Error: {error_msg}")
                if self.task_manager:
                    await self.task_manager.update_status(task_id, "error", error=error_msg)

        # 放進背景執行，並且不阻塞當前 Event Loop
        import asyncio
        loop = asyncio.get_event_loop()
        
        # 使用 create_task 並將任務保存在 class 層級避免被 GC 回收
        if not hasattr(self, '_bg_tasks'):
            self._bg_tasks = set()
            
        task = loop.create_task(background_task())
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
        
        if self.task_manager:
            # 取得目前的 TaskRecord 並更新 asyncio_task (需要使用 asyncio.create_task 因為這裡本來就是 async)
            loop.create_task(self._update_task_record(task_id, task))
        
        # 立即回報給主助理 (不阻塞)
        return {
            "status": "success",
            "task_id": task_id,
            "message": f"已成功將任務委派給背景技工 (ID: {task_id})。任務將在一分鐘內自動於背景處理完畢。\n[CRITICAL]: 請回覆使用者「已發包，任務ID為 {task_id}，預計 1~2 分鐘內完成，系統會自動推播通知」。絕對不要對使用者編造不實的幾天或幾小時工期！使用者若詢問進度，告訴他還在趕工即可，絕對不要重複發包！"
        }

    async def _update_task_record(self, task_id: str, task: asyncio.Task):
        """Helper to update task record without blocking the main event loop."""
        if not self.task_manager:
            return
        t_record = await self.task_manager.get(task_id)
        if t_record:
            t_record.asyncio_task = task

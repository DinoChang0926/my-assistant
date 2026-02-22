from src.tools.base import BaseTool
from src.core.events import AgentEvent

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
        from src.brain.prompts import SELF_EVOLUTION_SYSTEM_PROMPT
        from src.config import settings

        role = RoleRegistry.EVOLUTION_MECHANIC
        route_config = RouteConfig(
            model_name=settings.COPILOT_EVOLUTION_MODEL,
            system_prompt=(role.system_prompt or "") + SELF_EVOLUTION_SYSTEM_PROMPT,
            intent="evolution",
            role=role
        )
        
        # 取出 status_callback 以進行背景推播
        status_callback = kwargs.get("status_callback")
        
        # 建立一個虛擬的委派事件
        delegate_instruction_payload = (
            f"Master 要求你執行以下任務：\n{instruction}\n\n"
            f"🛑 [CRITICAL WARNING] 🛑\n"
            f"1. 絕對不可使用 Copilot 內建名為 `create`、`view` 的原生寫檔工具！\n"
            f"2. 你**只有能力**透過專屬的 `create_tool` 技能來寫入新程式碼（而且必須繼承 BaseTool）！\n"
            f"3. **[MVP 優先]**：請務必以 MVP (最小可行性產品) 為開發首要考量，先求有、求可行，禁止在首版過度設計或加入非核心的繁雜功能。"
        )
        
        from src.core.events import InputSource, AgentEvent
        delegate_event = AgentEvent(
            event_id=str(uuid.uuid4()),
            source=InputSource.API,
            session_id="internal_mechanic_workspace", 
            content=delegate_instruction_payload
        )
        
        async def background_task():
            import asyncio
            try:
                if self.task_manager:
                    await self.task_manager.update_status(task_id, "running")

                # 提示使用者目前正在背景思考中
                if status_callback:
                    await status_callback(f"⚙️ [系統部] 技工已收到任務 {task_id}，正在背景開發中，請稍候...")
                    
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
                    
                # 透過推播系統報喜
                if status_callback:
                    await status_callback(f"🎉 [系統部] 回報主人，您的開發結案了！\n{safe_response}")
                    
                # 寫入本機記憶體，確保主助理後續能夠意識到工具已完成
                from src.tools.static.atomic.static_tool_local_memory import LocalMemoryTool
                memory = LocalMemoryTool()
                await memory.execute(
                    action="set",
                    key="latest_mechanic_update",
                    value=f"背景工程師剛完成了開發，成果摘要: {safe_response[:100]}"
                )
                print(f"[Delegate] Background task {task_id} completed and saved to memory.")
                if self.task_manager:
                    await self.task_manager.update_status(task_id, "done", result=safe_response)
            except asyncio.CancelledError:
                print(f"[Delegate] Background task {task_id} was CANCELLED.")
                if self.task_manager:
                    await self.task_manager.update_status(task_id, "cancelled")
            except Exception as e:
                error_msg = f"委派任務背景執行時發生錯誤: {str(e)}"
                print(f"[Delegate] Error: {error_msg}")
                if self.task_manager:
                    await self.task_manager.update_status(task_id, "error", error=error_msg)
                if status_callback:
                    await status_callback(f"❌ [系統部] 工程師開發過程中摔跤了：{error_msg}")

        # 放進背景執行
        import asyncio
        loop = asyncio.get_event_loop()
        task = loop.create_task(background_task())
        
        if self.task_manager:
            # 取得目前的 TaskRecord 並更新 asyncio_task
            t_record = await self.task_manager.get(task_id)
            if t_record:
                t_record.asyncio_task = task
        
        # 立即回報給主助理 (不阻塞)
        return {
            "status": "success",
            "task_id": task_id,
            "message": f"已成功將任務委派給背景技工 (ID: {task_id})。任務將在一分鐘內自動於背景處理完畢。\n[CRITICAL]: 請回覆使用者「已發包，任務ID為 {task_id}，預計 1~2 分鐘內完成，系統會自動推播通知」。絕對不要對使用者編造不實的幾天或幾小時工期！使用者若詢問進度，告訴他還在趕工即可，絕對不要重複發包！"
        }

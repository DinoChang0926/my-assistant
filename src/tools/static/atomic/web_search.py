from src.tools.base import BaseTool
from duckduckgo_search import DDGS
import json

class WebSearchTool(BaseTool):
    """
    使用 DuckDuckGo 進行網頁搜尋的工具。
    """

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "搜尋網頁內容。輸入查詢字串，回傳包含標題、內容摘要與連結的列表。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜尋關鍵字"
                },
                "max_results": {
                    "type": "integer",
                    "description": "最大回傳結果數量 (預設為 5)",
                    "default": 5
                }
            },
            "required": ["query"]
        }

    async def execute(self, **kwargs) -> dict:
        query = kwargs.get("query")
        max_results = kwargs.get("max_results", 5)

        if not query:
            return {"status": "error", "message": "Missing query parameter."}

        try:
            results = []
            with DDGS() as ddgs:
                ddgs_gen = ddgs.text(query, max_results=max_results)
                for r in ddgs_gen:
                    results.append({
                        "title": r.get("title"),
                        "href": r.get("href"),
                        "body": r.get("body")
                    })
            
            return {
                "status": "success",
                "data": results,
                "message": f"Found {len(results)} results for '{query}'."
            }
        except Exception as e:
            return {"status": "error", "message": f"Search failed: {str(e)}"}

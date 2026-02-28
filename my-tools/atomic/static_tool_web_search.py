from copilot.tools import define_tool
from pydantic import BaseModel, Field


class WebSearchParams(BaseModel):
    query: str = Field(description="搜尋關鍵字")
    max_results: int = Field(default=5, description="最大回傳結果數量 (預設為 5)")


@define_tool(
    description="搜尋網頁內容。輸入查詢字串，回傳包含標題、內容摘要與連結的列表。"
)
async def web_search(params: WebSearchParams) -> dict:
    from duckduckgo_search import DDGS

    if not params.query:
        return {"status": "error", "message": "Missing query parameter."}

    try:
        results = []
        with DDGS() as ddgs:
            ddgs_gen = ddgs.text(params.query, max_results=params.max_results)
            for r in ddgs_gen:
                results.append({
                    "title": r.get("title"),
                    "href": r.get("href"),
                    "body": r.get("body"),
                })

        return {
            "status": "success",
            "data": results,
            "message": f"Found {len(results)} results for '{params.query}'.",
        }
    except Exception as e:
        return {"status": "error", "message": f"Search failed: {str(e)}"}


# --- Module exports for registry discovery (Phase 3a convention) ---
EXPORTED_TOOLS = [web_search]
TOOL_CATEGORY = "web"

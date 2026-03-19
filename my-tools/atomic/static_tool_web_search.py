async def web_search(query: str, max_results: int = 5) -> dict:
    """搜尋網頁內容。輸入查詢字串，回傳包含標題、內容摘要與連結的列表。"""
    from duckduckgo_search import DDGS

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
                    "body": r.get("body"),
                })

        return {
            "status": "success",
            "data": results,
            "message": f"Found {len(results)} results for '{query}'.",
        }
    except Exception as e:
        return {"status": "error", "message": f"Search failed: {str(e)}"}

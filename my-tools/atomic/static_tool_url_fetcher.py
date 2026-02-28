from copilot.tools import define_tool
from pydantic import BaseModel, Field


class URLFetcherParams(BaseModel):
    url: str = Field(description="要抓取的網頁 URL")
    extract_text: bool = Field(default=True, description="是否僅提取純文字 (預設為 true)")


@define_tool(
    description="抓取指定 URL 的網頁內容。會自動處理 User-Agent 並回傳網頁的純文字內容與標題。"
)
async def url_fetcher(params: URLFetcherParams) -> dict:
    import requests
    from bs4 import BeautifulSoup

    if not params.url:
        return {"status": "error", "message": "Missing url parameter."}

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(params.url, headers=headers, timeout=15)
        response.raise_for_status()

        if params.extract_text:
            soup = BeautifulSoup(response.text, "html.parser")

            # Remove script and style elements
            for script_or_style in soup(["script", "style"]):
                script_or_style.decompose()

            title = soup.title.string if soup.title else "No Title"
            text = soup.get_text(separator=" ", strip=True)

            # Limit length to avoid context overflow (default: first 5000 chars)
            truncated_text = text[:5000] + ("..." if len(text) > 5000 else "")

            return {
                "status": "success",
                "data": {
                    "title": title,
                    "content": truncated_text,
                    "url": params.url,
                },
            }
        else:
            return {
                "status": "success",
                "data": {
                    "content": response.text[:2000],
                    "url": params.url,
                },
            }

    except Exception as e:
        return {"status": "error", "message": f"Failed to fetch URL: {str(e)}"}


# --- Module exports for registry discovery (Phase 3a convention) ---
EXPORTED_TOOLS = [url_fetcher]
TOOL_CATEGORY = "web"

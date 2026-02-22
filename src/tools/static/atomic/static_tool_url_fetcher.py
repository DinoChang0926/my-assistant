from src.tools.base import BaseTool
import requests
from bs4 import BeautifulSoup
import json

class URLFetcherTool(BaseTool):
    """
    抓取網頁內容並提取純文字的工具。
    """

    name: str = "url_fetcher"
    category: str = "web"
    description: str = "抓取指定 URL 的網頁內容。會自動處理 User-Agent 並回傳網頁的純文字內容與標題。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要抓取的網頁 URL"
                },
                "extract_text": {
                    "type": "boolean",
                    "description": "是否僅提取純文字 (預設為 true)",
                    "default": True
                }
            },
            "required": ["url"]
        }

    async def execute(self, **kwargs) -> dict:
        url = kwargs.get("url")
        extract_text = kwargs.get("extract_text", True)

        if not url:
            return {"status": "error", "message": "Missing url parameter."}

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            if extract_text:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 移除 script 與 style
                for script_or_style in soup(["script", "style"]):
                    script_or_style.decompose()
                
                title = soup.title.string if soup.title else "No Title"
                text = soup.get_text(separator=' ', strip=True)
                
                # 限制長度避免 Context 過大 (預設取前 5000 字)
                truncated_text = text[:5000] + ("..." if len(text) > 5000 else "")
                
                return {
                    "status": "success",
                    "data": {
                        "title": title,
                        "content": truncated_text,
                        "url": url
                    }
                }
            else:
                return {
                    "status": "success",
                    "data": {
                        "content": response.text[:2000], # 原始 HTML 限制長度
                        "url": url
                    }
                }
                
        except Exception as e:
            return {"status": "error", "message": f"Failed to fetch URL: {str(e)}"}

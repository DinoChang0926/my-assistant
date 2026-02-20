from src.tools.base import BaseTool
import yfinance as yf
import pandas as pd
import json

class StockLoaderTool(BaseTool):
    """
    取得股市資訊的工具。
    """

    @property
    def name(self) -> str:
        return "stock_loader"

    @property
    def description(self) -> str:
        return "取得股票價格、歷史數據或公司基本面資訊。支援全球股市代號 (如: AAPL, 2330.TW)。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "股票代號 (e.g., 'AAPL', '2330.TW')"
                },
                "period": {
                    "type": "string",
                    "description": "歷史數據週期 (e.g., '1d', '5d', '1mo', '1y')",
                    "default": "1d"
                },
                "info_only": {
                    "type": "boolean",
                    "description": "是否僅取得公司基本資訊 (預設為 false)",
                    "default": False
                }
            },
            "required": ["symbol"]
        }

    async def execute(self, **kwargs) -> dict:
        symbol = kwargs.get("symbol")
        period = kwargs.get("period", "1d")
        info_only = kwargs.get("info_only", False)

        if not symbol:
            return {"status": "error", "message": "Missing symbol parameter."}

        try:
            ticker = yf.Ticker(symbol)
            
            if info_only:
                info = ticker.info
                # 過濾一些太長的資料
                filtered_info = {k: v for k, v in info.items() if isinstance(v, (str, int, float)) and len(str(v)) < 1000}
                return {"status": "success", "data": filtered_info}
            
            hist = ticker.history(period=period)
            if hist.empty:
                return {"status": "error", "message": f"No data found for symbol '{symbol}'."}
            
            # 轉換為 JSON 格式
            hist_list = hist.reset_index().to_dict(orient="records")
            # 處理日期格式
            for item in hist_list:
                item["Date"] = item["Date"].strftime("%Y-%m-%d %H:%M:%S")

            return {
                "status": "success",
                "data": {
                    "symbol": symbol,
                    "history": hist_list,
                    "current_price": hist["Close"].iloc[-1] if not hist.empty else None
                }
            }
        except Exception as e:
            return {"status": "error", "message": f"Failed to load stock data: {str(e)}"}

import requests
import logging

logger = logging.getLogger(__name__)

# Try importing yfinance for richer data
try:
    import yfinance as yf
    _yf_available = True
except ImportError:
    _yf_available = False


class FinancialClient:

    @staticmethod
    def get_stock_price(ticker: str) -> dict:
        ticker_clean = ticker.strip().upper()
        try:
            url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker_clean}?interval=1d&range=2d"
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)

            if res.status_code == 200:
                data = res.json()
                result = data["chart"]["result"][0]
                meta = result["meta"]
                current_price = meta["regularMarketPrice"]
                prev_close = meta.get("chartPreviousClose") or meta.get("previousClose") or current_price
                change = current_price - prev_close
                change_pct = (change / prev_close * 100) if prev_close else 0.0
                quotes = result["indicators"]["quote"][0]
                highs = [h for h in quotes.get("high", []) if h is not None]
                lows = [l for l in quotes.get("low", []) if l is not None]
                volumes = [v for v in quotes.get("volume", []) if v is not None]
                return {
                    "ticker": ticker_clean,
                    "name": meta.get("longName") or meta.get("shortName") or ticker_clean,
                    "price": round(current_price, 2),
                    "currency": meta.get("currency", "USD"),
                    "change": round(change, 2),
                    "change_percent": round(change_pct, 2),
                    "day_high": round(max(highs), 2) if highs else current_price,
                    "day_low": round(min(lows), 2) if lows else current_price,
                    "volume": int(volumes[-1]) if volumes else 0,
                    "market_cap": meta.get("marketCap"),
                }
        except Exception as e:
            logger.warning(f"Yahoo chart API failed for {ticker_clean}: {e}")

        # yfinance fallback
        if _yf_available:
            try:
                t = yf.Ticker(ticker_clean)
                info = t.fast_info
                price = info.last_price or 0
                prev = info.previous_close or price
                change = price - prev
                change_pct = (change / prev * 100) if prev else 0
                return {
                    "ticker": ticker_clean,
                    "name": ticker_clean,
                    "price": round(price, 2),
                    "currency": "USD",
                    "change": round(change, 2),
                    "change_percent": round(change_pct, 2),
                    "day_high": round(info.day_high or price, 2),
                    "day_low": round(info.day_low or price, 2),
                    "volume": int(info.three_month_average_volume or 0),
                    "market_cap": info.market_cap,
                }
            except Exception as e:
                logger.warning(f"yfinance fallback failed for {ticker_clean}: {e}")

        return {
            "ticker": ticker_clean, "name": ticker_clean,
            "price": 0.0, "currency": "USD", "change": 0.0,
            "change_percent": 0.0, "day_high": 0.0, "day_low": 0.0,
            "volume": 0, "error": "price_unavailable"
        }

    @staticmethod
    def get_company_news(ticker: str) -> list:
        ticker_clean = ticker.strip().upper()
        try:
            url = f"https://query2.finance.yahoo.com/v1/finance/search?q={ticker_clean}&newsCount=6"
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            if res.status_code == 200:
                items = res.json().get("news", [])
                return [
                    {
                        "title": i.get("title"),
                        "publisher": i.get("publisher"),
                        "link": i.get("link"),
                        "published_at": i.get("providerPublishTime"),
                    }
                    for i in items[:6]
                ]
        except Exception as e:
            logger.warning(f"News fetch failed for {ticker_clean}: {e}")
        return []

    @staticmethod
    def get_financials(ticker: str) -> dict:
        ticker_clean = ticker.strip().upper()

        # Try yfinance for real fundamentals
        if _yf_available:
            try:
                t = yf.Ticker(ticker_clean)
                info = t.info
                return {
                    "ticker": ticker_clean,
                    "name": info.get("longName") or ticker_clean,
                    "sector": info.get("sector", "N/A"),
                    "industry": info.get("industry", "N/A"),
                    "market_cap": info.get("marketCap"),
                    "pe_ratio": info.get("trailingPE"),
                    "forward_pe": info.get("forwardPE"),
                    "price_to_book": info.get("priceToBook"),
                    "revenue_growth": info.get("revenueGrowth"),
                    "earnings_growth": info.get("earningsGrowth"),
                    "profit_margins": info.get("profitMargins"),
                    "ebitda_margins": info.get("ebitdaMargins"),
                    "return_on_equity": info.get("returnOnEquity"),
                    "debt_to_equity": info.get("debtToEquity"),
                    "free_cashflow": info.get("freeCashflow"),
                    "total_revenue": info.get("totalRevenue"),
                    "net_income": info.get("netIncomeToCommon"),
                    "dividend_yield": info.get("dividendYield"),
                    "52_week_high": info.get("fiftyTwoWeekHigh"),
                    "52_week_low": info.get("fiftyTwoWeekLow"),
                    "analyst_target": info.get("targetMeanPrice"),
                    "recommendation": info.get("recommendationKey"),
                    "beta": info.get("beta"),
                    "description": (info.get("longBusinessSummary") or "")[:400],
                }
            except Exception as e:
                logger.warning(f"yfinance financials failed for {ticker_clean}: {e}")

        # Minimal fallback — clearly marked as estimates
        return {
            "ticker": ticker_clean,
            "name": ticker_clean,
            "note": "Live data temporarily unavailable — figures are estimates",
            "sector": "N/A",
            "industry": "N/A",
        }

    @staticmethod
    def compare_stocks(tickers: list) -> dict:
        """Fetch key metrics for multiple tickers for side-by-side comparison."""
        result = {}
        for ticker in tickers:
            data = FinancialClient.get_financials(ticker)
            price_data = FinancialClient.get_stock_price(ticker)
            result[ticker.upper()] = {
                "price": price_data.get("price"),
                "change_percent": price_data.get("change_percent"),
                "market_cap": data.get("market_cap"),
                "pe_ratio": data.get("pe_ratio"),
                "revenue_growth": data.get("revenue_growth"),
                "profit_margins": data.get("profit_margins"),
                "return_on_equity": data.get("return_on_equity"),
                "recommendation": data.get("recommendation"),
                "analyst_target": data.get("analyst_target"),
                "sector": data.get("sector"),
            }
        return result

    @staticmethod
    def get_historical_market_summary(tickers: list) -> dict:
        summary = {}
        for ticker in tickers:
            data = FinancialClient.get_stock_price(ticker)
            if "error" not in data:
                summary[ticker] = {
                    "name": data.get("name", ticker),
                    "price": data["price"],
                    "change": data["change"],
                    "change_percent": data["change_percent"],
                    "volume": data.get("volume"),
                }
        return summary

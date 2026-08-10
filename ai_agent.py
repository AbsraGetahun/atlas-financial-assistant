import json
import logging
import base64
from config import GEMINI_API_KEY, GROQ_API_KEY
from financial_client import FinancialClient
from sqlalchemy.orm import Session
from database import User, WatchlistItem, MessageLog, PriceAlert  

logger = logging.getLogger(__name__)

# Gemini setup
gemini_available = False
if GEMINI_API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_available = True
        logger.info("Gemini client ready.")
    except Exception as e:
        logger.warning(f"Gemini init failed: {e}")

# Groq setup
groq_client = None
if GROQ_API_KEY:
    try:
        from groq import Groq
        groq_client = Groq(api_key=GROQ_API_KEY)
        logger.info("Groq client ready.")
    except Exception as e:
        logger.warning(f"Groq init failed: {e}")


# Tool functions
def get_stock_price(ticker: str) -> str:
    """Gets real-time price and statistics for a given stock ticker."""
    return json.dumps(FinancialClient.get_stock_price(ticker))

def get_company_news(ticker: str) -> str:
    """Gets recent news articles for a specific stock ticker."""
    return json.dumps(FinancialClient.get_company_news(ticker))

def get_financials(ticker: str) -> str:
    """Retrieves financial ratios, valuation, revenue growth and income metrics for a ticker."""
    return json.dumps(FinancialClient.get_financials(ticker))

TOOLS_MAPPING = {
    "get_stock_price": get_stock_price,
    "get_company_news": get_company_news,
    "get_financials": get_financials,
}

# Groq tool schemas (OpenAI-compatible)
GROQ_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_stock_price",
            "description": "Gets real-time price and statistics for a given stock ticker.",
            "parameters": {
                "type": "object",
                "properties": {"ticker": {"type": "string", "description": "Stock ticker symbol e.g. AAPL"}},
                "required": ["ticker"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_company_news",
            "description": "Gets recent news articles for a specific stock ticker.",
            "parameters": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_financials",
            "description": "Retrieves financial ratios and valuation metrics for a ticker.",
            "parameters": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"]
            }
        }
    }
]

SYSTEM_INSTRUCTION = """You are Atlas, a sharp AI financial analyst who lives inside Telegram.

You talk like a real person — warm, direct, occasionally witty. Think of yourself as a smart friend who happens to know finance really well, not a customer service bot.

HOW YOU TALK
- Short sentences. Natural rhythm. No corporate speak.
- Never start a message with "Certainly!", "Of course!", "Great question!" or similar filler
- Don't volunteer information the user didn't ask for
- If you don't know, say so simply — "I'm not sure about that one"
- One thought at a time. Don't cram everything into one reply.
- Use emojis sparingly — only when they genuinely add something

WHAT YOU DO
- Answer financial questions using your tools (prices, news, financials, comparisons)
- Analyze documents and images the user sends
- Remember their watchlist, role, and interests across sessions
- Send morning briefings and price alerts proactively
- Learn what they care about naturally — don't ask a bunch of questions at once

CRITICAL RULES
- NEVER show raw function calls, JSON blobs, or tool syntax in your replies — those are internal only
- NEVER say things like "<function=get_stock_price>" or show any code in your response
- NEVER make up financial numbers — always use your tools for prices and data
- NEVER ask more than one question at a time
- Keep replies under 250 words unless the user explicitly asks for detail"""


class AIAgent:
    def __init__(self, db: Session, telegram_user_id: int):
        self.db = db
        self.user_id = telegram_user_id
        self.user = self.db.query(User).filter(User.id == telegram_user_id).first()
        if not self.user:
            self.user = User(id=telegram_user_id)
            self.db.add(self.user)
            self.db.commit()
            self.db.refresh(self.user)

    def _get_history(self, limit: int = 20) -> list:
        logs = (
            self.db.query(MessageLog)
            .filter(MessageLog.user_id == self.user_id)
            .order_by(MessageLog.timestamp.desc())
            .limit(limit)
            .all()
        )
        logs.reverse()
        return [{"role": l.role, "content": l.content} for l in logs]

    def _save_message(self, role: str, content: str):
        self.db.add(MessageLog(user_id=self.user_id, role=role, content=content))
        self.db.commit()

    def _build_system_prompt(self) -> str:
        tickers = [item.ticker for item in self.user.watchlist]
        return (
            SYSTEM_INSTRUCTION
            + f"\n\n[User Profile] Name: {self.user.first_name or 'Unknown'} | "
            f"Role: {self.user.role or 'not set'} | "
            f"Watchlist: {', '.join(tickers) or 'empty'} | "
            f"Interests: {self.user.interests or 'none'} | "
            f"Briefing time: {self.user.briefing_time} | "
            f"Onboarded: {self.user.onboarded}"
        )

    def transcribe_voice(self, audio_bytes: bytes) -> str:
        """Transcribe voice using Groq Whisper."""
        if not groq_client:
            return "[Voice transcription unavailable — Groq API key not configured]"
        try:
            import io
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = "voice.ogg"
            transcription = groq_client.audio.transcriptions.create(
                file=audio_file,
                model="whisper-large-v3",
                response_format="text"
            )
            return transcription if isinstance(transcription, str) else transcription.text
        except Exception as e:
            logger.error(f"Voice transcription failed: {e}")
            return "[Could not transcribe voice message]"

    def analyze_image(self, image_bytes: bytes, caption: str = "") -> str:
        """Analyze an image using Gemini Vision (inline bytes, no PIL dependency on format)."""
        prompt = (
            caption if caption
            else "Analyze this image. If it contains financial data, charts, tables, or reports, "
                 "explain what you see, what the key numbers are, and what they mean. "
                 "If it's not financial, just describe what's in it."
        )

        if gemini_available:
            # Try passing image as inline base64 data — works without PIL format detection
            try:
                import google.generativeai as genai

                # Detect mime type from magic bytes
                mime = "image/jpeg"
                if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
                    mime = "image/png"
                elif image_bytes[:4] == b'GIF8':
                    mime = "image/gif"
                elif image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
                    mime = "image/webp"

                model = genai.GenerativeModel("gemini-flash-latest")
                response = model.generate_content([
                    {"mime_type": mime, "data": image_bytes},
                    prompt
                ])
                return response.text
            except Exception as e:
                err = str(e).lower()
                if any(k in err for k in ["quota", "429", "exhausted", "limit", "resource"]):
                    logger.warning(f"Gemini image quota hit: {e}")
                    return (
                        "I can see you sent an image but my vision quota is currently exhausted. "
                        "Try again in a few minutes — Gemini resets every hour."
                    )
                logger.error(f"Gemini image failed: {e}")

        return (
            "Image analysis isn't available right now. "
            "Make sure your GEMINI_API_KEY is set correctly and has quota remaining."
        )

    def clear_history(self):
        """Delete all conversation history for this user."""
        self.db.query(MessageLog).filter(MessageLog.user_id == self.user_id).delete()
        self.db.commit()

    @staticmethod
    def _strip_function_calls(text: str) -> str:
        """Remove any leaked <function=...> or tool call artifacts from AI responses."""
        import re
        # Remove <function=name>...</function> and <function=name {...}></function>
        text = re.sub(r"<function=\w+[^>]*>.*?</function>", "", text, flags=re.DOTALL)
        text = re.sub(r"<function=\w+[^>]*/>", "", text)
        # Remove standalone JSON blobs that look like tool calls
        text = re.sub(r"\{\"ticker\":\s*\"[A-Z]+\"\}", "", text)
        text = re.sub(r"\{\"tickers_csv\":[^}]+\}", "", text)
        return text.strip()

    def process_message(self, user_text: str) -> str:
        # FIX 1: Add "skip" option for onboarding
        if not self.user.onboarded and user_text.lower() in ["skip", "later", "not now", "skip onboarding"]:
            self.user.onboarded = True
            self.db.commit()
            return "No problem! You can update your preferences anytime. What would you like to talk about? 💬"
        
        self._save_message("user", user_text)
        history = self._get_history()
        system = self._build_system_prompt()

        reply = self._call_gemini(user_text, history, system)
        if reply is None:
            reply = self._call_groq(history, system)
        if reply is None:
            reply = "I'm having trouble connecting right now. Please try again in a moment."

        reply = self._strip_function_calls(reply)

        self._detect_and_save_preferences(user_text, reply)
        self._save_message("model", reply)
        return reply

    def _call_gemini(self, user_text: str, history: list, system: str):
        if not gemini_available:
            return None
        try:
            import google.generativeai as genai

            gemini_history = []
            for msg in history[:-1]:
                role = "user" if msg["role"] == "user" else "model"
                gemini_history.append({"role": role, "parts": [msg["content"]]})

            model = genai.GenerativeModel(
                model_name="gemini-flash-latest",
                system_instruction=system,
                tools=[get_stock_price, get_company_news, get_financials]
            )
            chat = model.start_chat(history=gemini_history)
            response = chat.send_message(user_text)
            response = self._handle_gemini_tool_calls(chat, response)

            try:
                return response.text
            except Exception:
                if response.candidates and response.candidates[0].content:
                    parts = response.candidates[0].content.parts
                    return "".join(p.text for p in parts if hasattr(p, "text"))
                return None

        except Exception as e:
            err = str(e).lower()
            if any(k in err for k in ["quota", "429", "rate", "exhausted", "limit"]):
                logger.warning("Gemini quota hit — falling back to Groq.")
                return None
            logger.error(f"Gemini error: {e}")
            return None

    def _handle_gemini_tool_calls(self, chat, response):
        try:
            candidate = response.candidates[0] if response.candidates else None
            if not candidate or not candidate.content or not candidate.content.parts:
                return response
            for part in candidate.content.parts:
                if hasattr(part, "function_call") and part.function_call:
                    name = part.function_call.name
                    args = dict(part.function_call.args)
                    tool_func = TOOLS_MAPPING.get(name)
                    if tool_func:
                        result = tool_func(**args)
                        response = chat.send_message({
                            "role": "user",
                            "parts": [{
                                "function_response": {
                                    "name": name,
                                    "response": {"result": result}
                                }
                            }]
                        })
        except Exception as e:
            logger.warning(f"Tool call error: {e}")
        return response

    def _call_groq(self, history: list, system: str):
        if not groq_client:
            return None
        try:
            messages = [{"role": "system", "content": system}]
            for msg in history:
                role = "user" if msg["role"] == "user" else "assistant"
                messages.append({"role": role, "content": msg["content"]})

            # Detect if this is a simple conversational message — skip tools to avoid 400s
            last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
            financial_keywords = ["price", "stock", "ticker", "market", "news", "financial",
                                  "compare", "earnings", "revenue", "chart", "$", "%"]
            needs_tools = any(k in last_user.lower() for k in financial_keywords)

            # FIX: Only include tools and tool_choice when needed
            if needs_tools:
                response = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    tools=GROQ_TOOLS,
                    tool_choice="auto",
                    max_tokens=1024
                )
            else:
                response = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    max_tokens=1024
                )

            msg = response.choices[0].message

            if msg.tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                        for tc in msg.tool_calls
                    ]
                })
                for tc in msg.tool_calls:
                    func = TOOLS_MAPPING.get(tc.function.name)
                    if func:
                        args = json.loads(tc.function.arguments)
                        result = func(**args)
                        messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                followup = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    max_tokens=1024
                )
                return followup.choices[0].message.content

            return msg.content

        except Exception as e:
            logger.error(f"Groq error: {e}")
            return None

    def analyze_document(self, doc_text: str) -> str:
        prompt = (
            "Analyze this financial document. Highlight key performance trends, "
            "financial anomalies, risks, and what an investor should pay attention to. "
            "Be concise and executive-focused:\n\n" + doc_text
        )
        system = "You are a senior financial analyst. Provide clear, structured, actionable analysis."

        if gemini_available:
            try:
                import google.generativeai as genai
                model = genai.GenerativeModel("gemini-flash-latest")
                return model.generate_content(prompt).text
            except Exception as e:
                if "quota" not in str(e).lower():
                    logger.error(f"Gemini doc error: {e}")

        if groq_client:
            try:
                response = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=2048
                )
                return response.choices[0].message.content
            except Exception as e:
                logger.error(f"Groq doc error: {e}")

        return "Sorry, I couldn't analyze the document right now. Please try again."

    def get_morning_brief(self) -> str:
        tickers = [item.ticker for item in self.user.watchlist]
        name = self.user.first_name or "there"
        if not tickers:
            return f"Good morning, {name}! Add some tickers to your watchlist and I'll send you personalized briefings every morning."

        summary = FinancialClient.get_historical_market_summary(tickers)
        prompt = (
            f"Write a short, punchy morning market briefing for {name}. "
            f"Watchlist data: {json.dumps(summary)}. "
            "Explain what moved, why it likely moved, and one thing to watch today. Keep it under 200 words."
        )

        if gemini_available:
            try:
                import google.generativeai as genai
                model = genai.GenerativeModel("gemini-flash-latest")
                return model.generate_content(prompt).text
            except Exception:
                pass

        if groq_client:
            try:
                response = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=512
                )
                return response.choices[0].message.content
            except Exception as e:
                logger.error(f"Groq brief error: {e}")

        return f"Good morning, {name}! I couldn't fetch your briefing right now — check back soon."

    # FIX 2: Add get_evening_summary method
    def get_evening_summary(self) -> str:
        """Generate an evening market summary for the user."""
        tickers = [item.ticker for item in self.user.watchlist]
        name = self.user.first_name or "there"
        
        if not tickers:
            return f"Good evening, {name}! You didn't have any stocks in your watchlist today. Add some to track! 📊"
        
        summary = FinancialClient.get_historical_market_summary(tickers)
        
        if not summary:
            return f"Evening update, {name}! I couldn't fetch data for your watchlist right now. Check back later! 📈"
        
        prompt = (
            f"Write a brief evening market summary for {name}. "
            f"Watchlist data: {json.dumps(summary)}. "
            "Highlight key movers, what drove the changes, and one insight for tomorrow. Keep it under 150 words."
        )
        
        if gemini_available:
            try:
                import google.generativeai as genai
                model = genai.GenerativeModel("gemini-flash-latest")
                return model.generate_content(prompt).text
            except Exception:
                pass
        
        if groq_client:
            try:
                response = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=512
                )
                return response.choices[0].message.content
            except Exception as e:
                logger.error(f"Groq evening summary error: {e}")
        
        # Fallback simple summary
        summary_text = "\n".join([
            f"• {ticker}: ${data['price']:.2f} ({data['change_percent']:+.2f}%)"
            for ticker, data in summary.items()
        ])
        return f"Evening update, {name}! Here's how your watchlist performed:\n\n{summary_text}"

    # FIX 3: Add check_alerts method
    def check_alerts(self) -> list:
        """Check for triggered price alerts and return notification messages."""
        triggered_messages = []
        
        # Get user's alerts
        alerts = self.db.query(PriceAlert).filter(
            PriceAlert.user_id == self.user_id,
            PriceAlert.triggered == False
        ).all()
        
        for alert in alerts:
            try:
                # Get current price
                data = FinancialClient.get_stock_price(alert.ticker)
                if "error" in data:
                    continue
                
                current_price = data["price"]
                triggered = False
                message = None
                
                # Check condition
                if alert.condition == "above" and current_price > alert.threshold:
                    triggered = True
                    message = f"🚨 *Price Alert*\n\n{alert.ticker} is trading above {alert.threshold} at ${current_price:.2f}\n\nChange: {data['change_percent']:+.2f}%"
                elif alert.condition == "below" and current_price < alert.threshold:
                    triggered = True
                    message = f"🚨 *Price Alert*\n\n{alert.ticker} is trading below {alert.threshold} at ${current_price:.2f}\n\nChange: {data['change_percent']:+.2f}%"
                elif alert.condition == "change_pct":
                    # Calculate price change percentage
                    if "change_percent" in data:
                        change_pct = data["change_percent"]
                        if abs(change_pct) >= alert.threshold:
                            triggered = True
                            direction = "up" if change_pct > 0 else "down"
                            message = f"🚨 *Price Alert*\n\n{alert.ticker} moved {direction} {abs(change_pct):.2f}% to ${current_price:.2f}\n\nChange: {change_pct:+.2f}%"
                
                if triggered and message:
                    triggered_messages.append(message)
                    alert.triggered = True
            
            except Exception as e:
                logger.error(f"Alert check error for {alert.ticker}: {e}")
        
        # Commit changes
        if triggered_messages:
            self.db.commit()
        
        return triggered_messages

    def _detect_and_save_preferences(self, user_text: str, bot_response: str):
        prompt = (
            f"From this conversation turn extract user profile info as JSON.\n"
            f"User: {user_text}\nAssistant: {bot_response}\n\n"
            "Return ONLY valid JSON with these optional keys: "
            "'role' (string), 'add_watchlist' (list of ticker strings uppercase), "
            "'remove_watchlist' (list of ticker strings uppercase), 'interests' (string), "
            "'briefing_time' (HH:MM string), 'onboarded' (boolean). "
            "Only include keys where info was clearly stated. No markdown, no explanation."
        )

        data = {}

        if gemini_available:
            try:
                import google.generativeai as genai
                model = genai.GenerativeModel("gemini-flash-latest")
                raw = model.generate_content(prompt).text.strip()
                raw = raw.replace("```json", "").replace("```", "").strip()
                data = json.loads(raw)
            except Exception:
                pass

        if not data and groq_client:
            try:
                response = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=256
                )
                raw = response.choices[0].message.content.strip()
                raw = raw.replace("```json", "").replace("```", "").strip()
                data = json.loads(raw)
            except Exception:
                pass

        if not data:
            return

        try:
            if data.get("role"):
                self.user.role = str(data["role"])
                # If role is set, consider user onboarded
                if not self.user.onboarded:
                    self.user.onboarded = True
            if data.get("interests"):
                val = data["interests"]
                self.user.interests = ", ".join(val) if isinstance(val, list) else str(val)
            if data.get("briefing_time"):
                self.user.briefing_time = str(data["briefing_time"])
            if data.get("onboarded") is not None:
                self.user.onboarded = bool(data["onboarded"])

            for ticker in data.get("add_watchlist", []):
                t = ticker.upper().strip()
                exists = self.db.query(WatchlistItem).filter(
                    WatchlistItem.user_id == self.user.id, WatchlistItem.ticker == t
                ).first()
                if not exists:
                    self.db.add(WatchlistItem(user_id=self.user.id, ticker=t))

            for ticker in data.get("remove_watchlist", []):
                t = ticker.upper().strip()
                item = self.db.query(WatchlistItem).filter(
                    WatchlistItem.user_id == self.user.id, WatchlistItem.ticker == t
                ).first()
                if item:
                    self.db.delete(item)

            self.db.commit()
        except Exception as e:
            logger.warning(f"Preference save error: {e}")
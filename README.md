# Atlas AI Financial Assistant

A highly conversational, proactive, and personalized AI Financial Assistant that lives inside Telegram, built for the Atlas AI Financial Assistant Hackathon.

## Value Prop & Features

1. **Zero Command Interface**: Built completely around conversational NLP. No menus, slash commands, or quick-replies. Users interact as they would with a real financial analyst.
2. **Seamless Onboarding**: The bot starts asking about the user's role and stock preferences conversationally, silently saving watchlist entries in the background using NLP entity extraction.
3. **Real-time Financial Information**: Powered by Yahoo Finance (`yfinance`). The AI Agent can retrieve real-time stock prices, company financials, news, and historical changes dynamically.
4. **Document Intelligence**: Upload any financial PDF document (e.g. earnings release, quarterly reports, balance sheet). The bot parses the PDF directly and generates a structured summary explaining what matters and key risks.
5. **Proactive Briefings**: Includes an automated daily briefing job that triggers personalized updates summarizing the performance and relevant news of tickers on the user's watchlist.

---

## Installation & Setup

1. **Clone or set directory as workspace**:
   Ensure you are in the workspace `C:\Users\hp\.gemini\antigravity\scratch\atlas-financial-assistant`.

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Set the following variables in your shell environment:
   - `TELEGRAM_BOT_TOKEN`: The token generated via Telegram BotFather.
   - `GEMINI_API_KEY`: Your Google Gemini API Key.

4. **Run the bot**:
   ```bash
   python bot.py
   ```

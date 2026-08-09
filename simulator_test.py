import os
import sys
import config # Ensure environment variables are loaded first
from database import init_db, SessionLocal
from ai_agent import AIAgent


def test_simulator():
    print("--- Starting Financial Assistant Simulation Test ---")
    
    # 1. Init Database
    init_db()
    db = SessionLocal()
    
    # Mock Telegram User ID
    test_user_id = 999999
    
    print("\n[Step 1] Initializing Agent...")
    agent = AIAgent(db, test_user_id)
    
    # Reset watchlist if any
    from database import WatchlistItem
    db.query(WatchlistItem).filter(WatchlistItem.user_id == test_user_id).delete()
    db.commit()

    print("\n[Step 2] Sending Message: Onboarding (Defining role & interest)...")
    q1 = "Hi, I am an early-stage investor. I want to keep track of AAPL and TSLA."
    print(f"User: {q1}")
    r1 = agent.process_message(q1)
    print(f"Bot: {r1}")

    # Check database user record to see if NLP successfully updated preferences
    db.refresh(agent.user)
    print(f"\n[Database Verification]:")
    print(f"  User Role saved: {agent.user.role}")
    watchlist_tickers = [item.ticker for item in agent.user.watchlist]
    print(f"  Watchlist saved: {watchlist_tickers}")

    print("\n[Step 3] Querying Stock Price & Financials (Functions/Tools Execution)...")
    q2 = "What is the current stock price and revenue growth of Apple (AAPL)?"
    print(f"User: {q2}")
    r2 = agent.process_message(q2)
    print(f"Bot: {r2}")

    print("\n[Step 4] Querying Company News...")
    q3 = "What is the latest news for TSLA?"
    print(f"User: {q3}")
    r3 = agent.process_message(q3)
    print(f"Bot: {r3}")

    print("\n[Step 5] Getting Daily Morning Brief...")
    brief = agent.get_morning_brief()
    print(f"Daily Brief Output:\n{brief}")

    db.close()
    print("\n--- Simulation Test Complete ---")

if __name__ == "__main__":
    # Check for Gemini API key
    key_name = "GEMINI" + "_API_KEY"
    if not os.environ.get(key_name):
        print("Error: GEMINI_API_KEY environment variable is required to run the simulation.")
        sys.exit(1)
    test_simulator()

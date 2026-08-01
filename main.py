import os
import time
import json
import traceback
import threading
from flask import Flask
from instagrapi import Client
from google import genai

# ==========================================
# 1. FLASK WEB SERVER (For UptimeRobot/Render)
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Status: Operational | Instagram Userbot Running!"

# ==========================================
# 2. CONFIGURATION & ENV VARIABLES
# ==========================================
SESSION_JSON_STR = os.environ.get("INSTA_SESSION_JSON")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

# Gemini Setup (New google-genai SDK)
ai_client = None
if GEMINI_KEY:
    try:
        ai_client = genai.Client(api_key=GEMINI_KEY)
        print("[INIT] Gemini AI Client initialized.")
    except Exception as e:
        print(f"[WARNING] Gemini init failed: {e}")
        traceback.print_exc()
else:
    print("[WARNING] GEMINI_API_KEY Missing!")

cl = Client()
cooldowns = {}
COOLDOWN_SECONDS = 3600  # 1 Hour Cooldown per user

# ==========================================
# 3. HELPER FUNCTIONS
# ==========================================
def get_gemini_reply(prompt_text):
    """Generates AI response using google-genai SDK."""
    if not ai_client:
        raise RuntimeError("Gemini AI Client is not initialized! Check GEMINI_API_KEY.")
    
    response = ai_client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt_text,
    )
    return response.text

# ==========================================
# 4. INSTAGRAM USERBOT MAIN LOOP
# ==========================================
def run_instagram_bot():
    print("[BOT] Starting Instagram Userbot Service...")
    
    if not SESSION_JSON_STR:
        print("[BOT CRITICAL ERROR] INSTA_SESSION_JSON missing in Environment Variables!")
        return

    # Direct Session Cookie Injection
    logged_in = False
    try:
        print("[BOT] Parsing INSTA_SESSION_JSON...")
        session_data = json.loads(SESSION_JSON_STR)
        sessionid = session_data.get("sessionid")
        ds_user_id = session_data.get("ds_user_id")
        csrftoken = session_data.get("csrftoken", "")

        if not sessionid or not ds_user_id:
            raise ValueError("sessionid ya ds_user_id missing hai JSON ke andar!")

        print("[BOT] Injecting session settings into instagrapi...")
        cl.set_settings({
            "authorization_data": {
                "sessionid": sessionid,
                "ds_user_id": ds_user_id,
                "csrftoken": csrftoken
            }
        })
        cl.login_by_sessionid(sessionid)
        logged_in = True
        print("[BOT SUCCESS] Successfully authenticated using Session Cookies!")

    except Exception as e:
        print(f"[BOT SESSION ERROR] Session inject fail hua: {e}")
        traceback.print_exc()

    if not logged_in:
        print("[BOT FATAL] Could not authenticate Instagram session. Stopping loop.")
        return

    # Continuous Polling Loop
    while True:
        try:
            # --- Direct Messages Check ---
            threads = cl.direct_threads(amount=10)
            for thread in threads:
                thread_id = thread.id
                messages = thread.messages
                
                if not messages:
                    continue
                    
                last_msg = messages[0]
                user_id = str(last_msg.user_id)
                
                # Skip self messages
                if user_id == str(cl.user_id):
                    continue

                msg_text = last_msg.text or ""
                current_time = time.time()

                # Case 1: AI Command (.ai <query>)
                if msg_text.lower().startswith(".ai "):
                    query = msg_text[4:].strip()
                    print(f"[BOT AI REQUEST] From User {user_id}: {query}")
                    
                    try:
                        ai_reply = get_gemini_reply(query)
                        cl.direct_answer(thread_id, ai_reply)
                        print(f"[BOT AI SENT] Replied to {user_id}")
                    except Exception as ai_err:
                        print(f"[GEMINI/SEND ERROR] Failed to reply .ai command to {user_id}: {ai_err}")
                        traceback.print_exc()

                # Case 2: Auto-Reply with 1-Hour Cooldown
                else:
                    last_replied = cooldowns.get(user_id, 0)
                    if current_time - last_replied > COOLDOWN_SECONDS:
                        auto_msg = (
                            "Lakshit is currently offline 🤧\n"
                            "This is an automated reply.\n\n"
                            "(Tip: Send '.ai <question>' to chat with AI!)"
                        )
                        cl.direct_answer(thread_id, auto_msg)
                        cooldowns[user_id] = current_time
                        print(f"[BOT AUTO-REPLY] Sent to User {user_id}")

        except Exception as e:
            print(f"[BOT LOOP ERROR] Outer loop exception caught: {e}")
            traceback.print_exc()

        time.sleep(25)  # Safe delay to prevent Instagram rate-limiting

# ==========================================
# 5. START BACKGROUND THREAD & FLASK
# ==========================================
bot_thread = threading.Thread(target=run_instagram_bot, daemon=True)
bot_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
                        

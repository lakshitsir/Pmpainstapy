import os
import json
import time
import base64
import traceback
from threading import Thread
from flask import Flask
from google import genai
from instagrapi import Client

# ---------------------------------------------------------
# 1. FLASK DUMMY SERVER (Keep Render Web Service Alive)
# ---------------------------------------------------------
app = Flask(__name__)

@app.route('/')
def home():
    return "Instagram Userbot is Running & Live!", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# ---------------------------------------------------------
# 2. GEMINI AI CLIENT INITIALIZATION
# ---------------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
ai_client = None

if GEMINI_API_KEY:
    try:
        ai_client = genai.Client(api_key=GEMINI_API_KEY)
        print("[INIT] Gemini AI Client successfully initialized.")
    except Exception as e:
        print(f"[INIT ERROR] Failed to initialize Gemini Client: {e}")
else:
    print("[INIT WARNING] GEMINI_API_KEY missing in Environment Variables!")


def get_gemini_reply(prompt_text: str) -> str:
    """Generates clean AI reply using Google GenAI SDK."""
    if not ai_client:
        raise RuntimeError("Gemini AI Client is not initialized! Check GEMINI_API_KEY.")
    
    # Using official valid model identifier
    response = ai_client.models.generate_content(
        model='gemini-2.0-flash',
        contents=prompt_text,
    )
    return response.text.strip()


# ---------------------------------------------------------
# 3. INSTAGRAM USERBOT LOGIC
# ---------------------------------------------------------
COOLDOWN_SECONDS = 3600  # 1 Hour per user cooldown
cooldowns = {}           # Memory dictionary to track last replied timestamp per user


def run_instagram_bot():
    print("[BOT] Starting Instagram Userbot Service...")
    
    raw_session_data = os.environ.get("INSTA_SESSION_JSON")
    if not raw_session_data:
        print("[BOT CRITICAL ERROR] INSTA_SESSION_JSON is missing in Environment Variables!")
        return

    cl = Client()
    
    # Professional Random Delay config to avoid Rate Limits / Bans
    cl.delay_range = [2, 5]

    # Injecting Instagram Session Settings
    try:
        print("[BOT] Parsing INSTA_SESSION_JSON...")
        # Check if Base64 encoded, else load raw JSON string
        try:
            decoded_bytes = base64.b64decode(raw_session_data)
            session_dict = json.loads(decoded_bytes.decode('utf-8'))
        except Exception:
            session_dict = json.loads(raw_session_data)

        cl.set_settings(session_dict)
        print("[BOT] Session settings injected successfully into instagrapi.")
    except Exception as err:
        print(f"[BOT SESSION ERROR] Failed to load session settings: {err}")
        return

    # Bot Message Loop
    while True:
        try:
            # Check unread direct threads (Only responds when someone messages you)
            threads = cl.direct_threads(amount=10, selected_filter="unread")
            
            for thread in threads:
                thread_id = str(thread.id)
                
                if not thread.messages:
                    continue
                
                latest_msg = thread.messages[0]
                user_id = str(latest_msg.user_id)

                # Skip if the last message was sent by our own account
                if user_id == str(cl.user_id):
                    continue

                msg_text = latest_msg.text if latest_msg.text else ""
                current_time = time.time()

                # CASE A: AI Command Trigger (.ai <your query>)
                if msg_text.lower().startswith(".ai "):
                    query = msg_text[4:].strip()
                    print(f"[BOT AI REQUEST] From User {user_id}: {query}")
                    
                    try:
                        ai_reply = get_gemini_reply(query)
                        # Mark thread read & send message directly to thread ID
                        cl.direct_thread_mark_unread(thread_id)
                        cl.direct_send(ai_reply, thread_ids=[thread_id])
                        print(f"[BOT AI SUCCESS] Replied to {user_id}")
                    except Exception as ai_err:
                        print(f"[GEMINI/SEND ERROR] Failed to process .ai command: {ai_err}")

                # CASE B: Standard Auto-Reply (Only once every 1 hour when someone sends a msg)
                else:
                    last_replied_time = cooldowns.get(user_id, 0)
                    
                    if (current_time - last_replied_time) > COOLDOWN_SECONDS:
                        auto_msg = (
                            "Lakshit is currently offline 🤧\n"
                            "This is an automated reply.\n\n"
                            "(Tip: Send '.ai <your message>' to chat with my AI assistant!)"
                        )
                        try:
                            cl.direct_send(auto_msg, thread_ids=[thread_id])
                            cooldowns[user_id] = current_time  # Update user's 1-hour timestamp
                            print(f"[BOT AUTO-REPLY] Sent to User {user_id} (1hr cooldown activated)")
                        except Exception as send_err:
                            print(f"[SEND ERROR] Failed to send auto-reply to {user_id}: {send_err}")
                    else:
                        print(f"[BOT COOLDOWN] Skipped User {user_id} - Within 1 hr window.")

            # Sleep between polling cycles to keep CPU & Network requests safe
            time.sleep(15)

        except Exception as loop_err:
            print(f"[BOT LOOP ERROR] Exception in main polling loop: {loop_err}")
            time.sleep(30)


# ---------------------------------------------------------
# 4. ENTRY POINT
# ---------------------------------------------------------
if __name__ == "__main__":
    # Start Instagram Bot in a background thread
    bot_thread = Thread(target=run_instagram_bot, daemon=True)
    bot_thread.start()
    
    # Start Flask Server in main thread
    run_flask()
        

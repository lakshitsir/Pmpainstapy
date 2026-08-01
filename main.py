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
processed_message_ids = set() # Prevent duplicate/infinite loop replies without marking Seen


def run_instagram_bot():
    print("[BOT] Starting Instagram Userbot Service...")
    
    raw_session_data = os.environ.get("INSTA_SESSION_JSON")
    if not raw_session_data:
        print("[BOT CRITICAL ERROR] INSTA_SESSION_JSON is missing in Environment Variables!")
        return

    cl = Client()
    cl.delay_range = [2, 5]

    # Injecting Instagram Session Settings
    try:
        print("[BOT] Parsing INSTA_SESSION_JSON...")
        try:
            decoded_bytes = base64.b64decode(raw_session_data)
            session_dict = json.loads(decoded_bytes.decode('utf-8'))
        except Exception:
            session_dict = json.loads(raw_session_data)

        cl.set_settings(session_dict)
        print("[BOT SUCCESS] Successfully authenticated using Session Cookies!")
    except Exception as err:
        print(f"[BOT SESSION ERROR] Failed to load session settings: {err}")
        return

    bot_start_time = time.time()

    while True:
        try:
            # Fetch pending threads
            threads = cl.direct_threads(amount=10, selected_filter="unread")
            
            for thread in threads:
                thread_id = str(thread.id)
                
                # 🛑 STRICT CHECK 1: NO GROUP CHATS AT ALL
                is_group_chat = (
                    getattr(thread, 'is_group', False) or 
                    getattr(thread, 'thread_type', '') == 'group' or
                    len(getattr(thread, 'users', [])) > 1 or
                    bool(getattr(thread, 'title', ''))
                )

                if is_group_chat:
                    continue

                if not thread.messages:
                    continue
                
                latest_msg = thread.messages[0]
                msg_id = str(latest_msg.id)
                user_id = str(latest_msg.user_id)

                # 🛑 STRICT CHECK 2: SKIP OWN MESSAGES
                if user_id == str(cl.user_id):
                    continue

                # 🛑 STRICT CHECK 3: MEMORY CHECK (Skip already processed msgs)
                if msg_id in processed_message_ids:
                    continue

                # 🛑 STRICT CHECK 4: IGNORE HISTORICAL MESSAGES BEFORE BOT START
                msg_timestamp = latest_msg.timestamp.timestamp() if hasattr(latest_msg.timestamp, 'timestamp') else time.time()
                if msg_timestamp < (bot_start_time - 60):
                    processed_message_ids.add(msg_id)
                    continue

                msg_text = latest_msg.text if latest_msg.text else ""
                
                # Skip typing indicators / blank activity
                if not msg_text.strip():
                    continue

                current_time = time.time()

                # CASE A: Explicit AI Command Trigger (.ai <query>)
                if msg_text.lower().startswith(".ai "):
                    query = msg_text[4:].strip()
                    print(f"[BOT AI REQUEST] From User {user_id}: {query}")
                    
                    try:
                        ai_reply = get_gemini_reply(query)
                        cl.direct_send(ai_reply, thread_ids=[thread_id])
                        processed_message_ids.add(msg_id)
                        print(f"[BOT AI SUCCESS] Replied to {user_id}")
                    except Exception as ai_err:
                        print(f"[GEMINI/SEND ERROR] Failed to reply .ai command to {user_id}: {ai_err}")

                # CASE B: Standard Auto-Reply (1 Hour per user cooldown)
                else:
                    last_replied_time = cooldowns.get(user_id, 0)
                    
                    if (current_time - last_replied_time) > COOLDOWN_SECONDS:
                        auto_msg = (
                            "Lakshit is currently offline 🤧\n"
                            "This is an automated reply.\n\n"
                            "(Tip: Send '.ai <your question>' to chat with AI!)"
                        )
                        try:
                            cl.direct_send(auto_msg, thread_ids=[thread_id])
                            cooldowns[user_id] = current_time
                            processed_message_ids.add(msg_id)
                            print(f"[BOT AUTO-REPLY] Sent to User {user_id}")
                        except Exception as send_err:
                            print(f"[SEND ERROR] Failed to send auto-reply to {user_id}: {send_err}")
                    else:
                        processed_message_ids.add(msg_id)
                        print(f"[BOT COOLDOWN] Ignored User {user_id} (Within 1 hour window)")

            # Clean memory buffer periodically
            if len(processed_message_ids) > 1000:
                processed_message_ids.clear()

            time.sleep(15)

        except Exception as loop_err:
            print(f"[BOT LOOP ERROR] Outer loop exception caught: {loop_err}")
            time.sleep(30)


# ---------------------------------------------------------
# 4. ENTRY POINT
# ---------------------------------------------------------
if __name__ == "__main__":
    bot_thread = Thread(target=run_instagram_bot, daemon=True)
    bot_thread.start()
    run_flask()
    

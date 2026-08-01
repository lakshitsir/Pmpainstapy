import os
import json
import time
import base64
import urllib.parse
import requests
from threading import Thread
from flask import Flask
from google import genai
from instagrapi import Client

# ---------------------------------------------------------
# 1. FLASK SERVER (Health Check Endpoint for Render)
# ---------------------------------------------------------
app = Flask(__name__)

@app.route('/')
def home():
    return "Instagram Professional Userbot Service - Running", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    # Direct WSGI runner without development server warnings
    from werkzeug.serving import run_simple
    run_simple("0.0.0.0", port, app, threaded=True)


# ---------------------------------------------------------
# 2. HYBRID AI ENGINE (Gemini 2.0 + Pollinations Fallback)
# ---------------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
ai_client = None

if GEMINI_API_KEY:
    try:
        ai_client = genai.Client(api_key=GEMINI_API_KEY)
        print("[INIT] Gemini 2.0 Client initialized successfully.")
    except Exception as e:
        print(f"[INIT ERROR] Gemini initialization skipped: {e}")


def fetch_pollinations_ai(prompt: str) -> str:
    """Fallback AI mechanism using Pollinations API."""
    try:
        encoded_prompt = urllib.parse.quote(prompt)
        url = f"https://text.pollinations.ai/{encoded_prompt}?model=openai"
        res = requests.get(url, timeout=10)
        if res.status_code == 200 and res.text.strip():
            return res.text.strip()
    except Exception as err:
        print(f"[FALLBACK AI ERROR] {err}")
    return "Offline context mode active. Please try again shortly."


def generate_ai_response(prompt: str) -> str:
    """Primary handler for AI generation with silent error recovery."""
    if ai_client:
        try:
            response = ai_client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt,
            )
            if response and response.text and response.text.strip():
                return response.text.strip()
        except Exception as err:
            print(f"[GEMINI FAIL] Switching to backup engine... ({err})")
    
    return fetch_pollinations_ai(prompt)


# ---------------------------------------------------------
# 3. INSTAGRAM ENGINE & STATE MANAGEMENT
# ---------------------------------------------------------
COOLDOWN_PERIOD = 3600  # 1 Hour per user auto-reply cooldown
user_cooldowns = {}
processed_message_ids = set()
is_instance_running = False


def execute_bot():
    global is_instance_running
    if is_instance_running:
        print("[SYSTEM] Instance lock active. Preventing duplicate bot threads.")
        return
    is_instance_running = True

    print("[SYSTEM] Starting Instagram Userbot Core Loop...")

    raw_session = os.environ.get("INSTA_SESSION_JSON")
    if not raw_session:
        print("[CRITICAL] INSTA_SESSION_JSON missing. Engine aborted.")
        return

    client = Client()
    client.delay_range = [3, 6]  # Human-like delay distribution

    # Session parsing with fallback decoding
    try:
        try:
            decoded_data = base64.b64decode(raw_session).decode('utf-8')
            session_settings = json.loads(decoded_data)
        except Exception:
            session_settings = json.loads(raw_session)

        client.set_settings(session_settings)
        print("[AUTHENTICATION] Session injected successfully.")
    except Exception as auth_err:
        print(f"[AUTHENTICATION ERROR] Session failure: {auth_err}")
        return

    startup_timestamp = time.time()

    while True:
        try:
            # PURE INBOUND ONLY: Fetch unread threads initiated by incoming users
            unread_threads = client.direct_threads(amount=10, selected_filter="unread")

            for thread in unread_threads:
                try:
                    thread_id = str(thread.id)

                    # 🛑 HARD SECURITY FILTER: Absolutely ZERO Group Threads
                    is_group = (
                        getattr(thread, 'is_group', False) or 
                        getattr(thread, 'thread_type', '') == 'group' or
                        len(getattr(thread, 'users', [])) > 1 or
                        bool(getattr(thread, 'title', ''))
                    )
                    if is_group:
                        continue

                    if not thread.messages:
                        continue

                    last_msg = thread.messages[0]
                    msg_id = str(last_msg.id)
                    sender_id = str(last_msg.user_id)

                    # 🛑 FILTER 1: Ignore own sent messages
                    if sender_id == str(client.user_id):
                        continue

                    # 🛑 FILTER 2: Ignore already processed message IDs
                    if msg_id in processed_message_ids:
                        continue

                    # 🛑 FILTER 3: Ignore stale historical messages before bootup
                    msg_time = last_msg.timestamp.timestamp() if hasattr(last_msg.timestamp, 'timestamp') else time.time()
                    if msg_time < (startup_timestamp - 30):
                        processed_message_ids.add(msg_id)
                        continue

                    text_content = last_msg.text.strip() if last_msg.text else ""
                    if not text_content:
                        continue  # Skip media/typing/reaction events safely

                    now = time.time()

                    # ROUTE A: Explicit AI Command (.ai <query>)
                    if text_content.lower().startswith(".ai "):
                        query = text_content[4:].strip()
                        print(f"[INBOUND AI COMMAND] Sender: {sender_id}")

                        ai_output = generate_ai_response(query)
                        try:
                            client.direct_send(ai_output, thread_ids=[thread_id])
                            processed_message_ids.add(msg_id)
                            print(f"[REPLY SENT] AI response delivered to {sender_id}")
                        except Exception as send_fail:
                            print(f"[DISPATCH ERROR] Failed to send AI response: {send_fail}")

                    # ROUTE B: Standard Passive Auto-Reply
                    else:
                        last_sent = user_cooldowns.get(sender_id, 0)
                        if (now - last_sent) > COOLDOWN_PERIOD:
                            auto_text = (
                                "Lakshit is currently offline 🤧\n"
                                "This is an automated response.\n\n"
                                "(Tip: Send '.ai <your topic>' to interact with AI!)"
                            )
                            try:
                                client.direct_send(auto_text, thread_ids=[thread_id])
                                user_cooldowns[sender_id] = now
                                processed_message_ids.add(msg_id)
                                print(f"[REPLY SENT] Auto-reply delivered to {sender_id}")
                            except Exception as auto_send_fail:
                                print(f"[DISPATCH ERROR] Failed to send auto-reply: {auto_send_fail}")
                        else:
                            processed_message_ids.add(msg_id)

                except Exception as thread_err:
                    print(f"[THREAD PROCESSING ERROR] Non-fatal exception: {thread_err}")
                    continue

            # Periodic memory cleanup to prevent memory leaks
            if len(processed_message_ids) > 2000:
                processed_message_ids.clear()

            time.sleep(10)

        except Exception as loop_err:
            print(f"[CORE LOOP RECOVERY] Handled outer error gracefully: {loop_err}")
            time.sleep(20)


# ---------------------------------------------------------
# 4. SERVICE ENTRY POINT
# ---------------------------------------------------------
if __name__ == "__main__":
    bot_worker = Thread(target=execute_bot, daemon=True)
    bot_worker.start()
    run_flask()
            

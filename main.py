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
# 1. FLASK WEB SERVER (Render Keep-Alive)
# ---------------------------------------------------------
app = Flask(__name__)

@app.route('/')
def home():
    return "Instagram Professional Userbot Service - Fully Operational", 200

# ---------------------------------------------------------
# 2. AI ENGINES: GEMINI 2.5 + POLLINATIONS BACKUP
# ---------------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
ai_client = None

if GEMINI_API_KEY:
    try:
        ai_client = genai.Client(api_key=GEMINI_API_KEY)
        print("[INIT] Gemini AI Client initialized successfully.", flush=True)
    except Exception as e:
        print(f"[INIT ERROR] Gemini SDK setup failed: {e}", flush=True)


def get_pollinations_ai(prompt: str) -> str:
    """Bulletproof Backup AI using Pollinations API."""
    try:
        encoded_prompt = urllib.parse.quote(prompt)
        url = f"https://text.pollinations.ai/{encoded_prompt}?model=openai"
        res = requests.get(url, timeout=10)
        if res.status_code == 200 and res.text.strip():
            return res.text.strip()
    except Exception as err:
        print(f"[POLLINATIONS ERROR] {err}", flush=True)
    return "AI service is temporarily busy. Please try again in a moment!"


def generate_ai_response(prompt: str) -> str:
    """Primary Gemini 2.5 Flash generator with auto-fallback."""
    if ai_client:
        try:
            # Using current 2026 stable model string
            response = ai_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            if response and response.text and response.text.strip():
                return response.text.strip()
        except Exception as err:
            print(f"[GEMINI FAIL] Fallback activated... Error: {err}", flush=True)

    print("[AI SYSTEM] Generating via Pollinations Backup Engine...", flush=True)
    return get_pollinations_ai(prompt)


# ---------------------------------------------------------
# 3. INSTAGRAM USERBOT LOGIC
# ---------------------------------------------------------
COOLDOWN_PERIOD = 3600  # 1 Hour auto-reply cooldown per user
user_cooldowns = {}
processed_message_ids = set()
bot_initialized = False


def start_bot_loop():
    global bot_initialized
    if bot_initialized:
        print("[SYSTEM] Bot thread is already active in another worker. Skipping...", flush=True)
        return
    bot_initialized = True

    print("[SYSTEM] Booting Instagram Userbot Engine...", flush=True)

    raw_session = os.environ.get("INSTA_SESSION_JSON")
    if not raw_session:
        print("[CRITICAL ERROR] INSTA_SESSION_JSON environment variable missing!", flush=True)
        return

    client = Client()
    # Safe random delays between request actions
    client.delay_range = [3, 6]

    try:
        print("[AUTHENTICATION] Parsing Instagram Session Cookies...", flush=True)
        try:
            decoded = base64.b64decode(raw_session).decode('utf-8')
            session_dict = json.loads(decoded)
        except Exception:
            session_dict = json.loads(raw_session)

        client.set_settings(session_dict)
        print("[AUTHENTICATION SUCCESS] Session injected successfully!", flush=True)
    except Exception as auth_err:
        print(f"[AUTHENTICATION FAILED] Couldn't load session: {auth_err}", flush=True)
        return

    startup_timestamp = time.time()

    while True:
        try:
            # Fetch unread threads
            unread_threads = client.direct_threads(amount=10, selected_filter="unread")

            for thread in unread_threads:
                try:
                    thread_id = str(thread.id)

                    # 🛑 HARD GROUP CHECK: Reject all group DMs 100%
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

                    # 🛑 FILTER 1: Ignore own messages
                    if sender_id == str(client.user_id):
                        continue

                    # 🛑 FILTER 2: Ignore already handled messages
                    if msg_id in processed_message_ids:
                        continue

                    # 🛑 FILTER 3: Ignore old messages prior to bot launch
                    msg_time = last_msg.timestamp.timestamp() if hasattr(last_msg.timestamp, 'timestamp') else time.time()
                    if msg_time < (startup_timestamp - 30):
                        processed_message_ids.add(msg_id)
                        continue

                    text_content = last_msg.text.strip() if last_msg.text else ""
                    if not text_content:
                        continue  # Skip empty typing/reaction events

                    now = time.time()

                    # ROUTE 1: Explicit AI Command (.ai <query>)
                    if text_content.lower().startswith(".ai "):
                        query = text_content[4:].strip()
                        print(f"[INBOUND AI COMMAND] Sender: {sender_id} | Query: {query}", flush=True)

                        ai_output = generate_ai_response(query)
                        try:
                            client.direct_send(ai_output, thread_ids=[thread_id])
                            processed_message_ids.add(msg_id)
                            print(f"[AI REPLY SENT] Successfully responded to user {sender_id}", flush=True)
                            time.sleep(4)  # Anti-Block Delay
                        except Exception as send_err:
                            print(f"[SEND ERROR] Failed to deliver AI message: {send_err}", flush=True)

                    # ROUTE 2: Standard Auto-Reply (Inbound Only, 1 Hr Cooldown)
                    else:
                        last_replied = user_cooldowns.get(sender_id, 0)
                        if (now - last_replied) > COOLDOWN_PERIOD:
                            auto_text = (
                                "Lakshit is currently offline 🤧\n"
                                "This is an automated response.\n\n"
                                "(Tip: Reply with '.ai <your topic>' to talk to AI!)"
                            )
                            try:
                                client.direct_send(auto_text, thread_ids=[thread_id])
                                user_cooldowns[sender_id] = now
                                processed_message_ids.add(msg_id)
                                print(f"[AUTO-REPLY SENT] Delivered to user {sender_id}", flush=True)
                                time.sleep(4)  # Anti-Block Delay
                            except Exception as send_err:
                                print(f"[SEND ERROR] Failed to deliver auto-reply: {send_err}", flush=True)
                        else:
                            processed_message_ids.add(msg_id)

                except Exception as thread_err:
                    print(f"[THREAD ERROR] Soft exception handled: {thread_err}", flush=True)
                    continue

            # Memory buffer cleanup
            if len(processed_message_ids) > 1500:
                processed_message_ids.clear()

            time.sleep(12)  # Healthy poll cycle interval

        except Exception as loop_err:
            print(f"[MAIN LOOP RECOVERY] Outer error caught safely: {loop_err}", flush=True)
            time.sleep(20)


# ---------------------------------------------------------
# 4. SERVICE INITIALIZATION (Gunicorn Compatible)
# ---------------------------------------------------------
# Always run background worker thread regardless of WSGI server startup
bot_thread = Thread(target=start_bot_loop, daemon=True)
bot_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
        

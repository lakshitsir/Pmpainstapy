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
START_TIME = time.time()

@app.route('/')
def home():
    return "Instagram Professional Userbot Service - Fully Operational", 200

# ---------------------------------------------------------
# 2. ZERO RATE-LIMIT MULTI-TIER AI ENGINE (Groq + Pollinations + Gemini)
# ---------------------------------------------------------
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

ai_client = None
if GEMINI_API_KEY:
    try:
        ai_client = genai.Client(api_key=GEMINI_API_KEY)
        print("[INIT] Gemini AI Client initialized successfully.", flush=True)
    except Exception as e:
        print(f"[INIT ERROR] Gemini SDK setup failed: {e}", flush=True)


def get_groq_ai(prompt: str) -> str:
    """Primary High-Speed AI via Groq API (Llama 3.3 70B)."""
    if not GROQ_API_KEY:
        return None
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 1000
        }
        res = requests.post(url, headers=headers, json=data, timeout=12)
        if res.status_code == 200:
            result = res.json()
            return result['choices'][0]['message']['content'].strip()
        else:
            print(f"[GROQ ERROR] Status Code: {res.status_code} | {res.text}", flush=True)
    except Exception as err:
        print(f"[GROQ FAIL] {err}", flush=True)
    return None


def get_pollinations_openai(prompt: str) -> str:
    """Secondary AI Engine (OpenAI Model Proxy via Pollinations)."""
    try:
        encoded_prompt = urllib.parse.quote(prompt)
        url = f"https://text.pollinations.ai/{encoded_prompt}?model=openai"
        res = requests.get(url, timeout=12)
        if res.status_code == 200 and res.text.strip():
            return res.text.strip()
    except Exception as err:
        print(f"[POLLINATIONS ERROR] {err}", flush=True)
    return None


def get_gemini_ai(prompt: str) -> str:
    """Tertiary Backup AI Engine (Gemini 2.0 Flash)."""
    if ai_client:
        try:
            response = ai_client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt,
            )
            if response and response.text and response.text.strip():
                return response.text.strip()
        except Exception as err:
            print(f"[GEMINI FAIL] {err}", flush=True)
    return None


def generate_ai_response(prompt: str) -> str:
    """Multi-Tier Auto Switcher: Groq -> Pollinations (OpenAI) -> Gemini."""
    # Tier 1: Groq
    output = get_groq_ai(prompt)
    if output:
        return output

    # Tier 2: Pollinations OpenAI
    print("[AI SYSTEM] Groq unavailable/unconfigured. Switching to Pollinations OpenAI...", flush=True)
    output = get_pollinations_openai(prompt)
    if output:
        return output

    # Tier 3: Gemini Backup
    print("[AI SYSTEM] Switching to Gemini Fallback Engine...", flush=True)
    output = get_gemini_ai(prompt)
    if output:
        return output

    return "AI server busy, please try asking again in a moment!"


def send_split_message(client, text: str, thread_id: str, max_length: int = 900):
    """Safely breaks down long responses to bypass Instagram character limitations."""
    if len(text) <= max_length:
        client.direct_send(text, thread_ids=[thread_id])
        return

    chunks = [text[i:i + max_length] for i in range(0, len(text), max_length)]
    for chunk in chunks:
        client.direct_send(chunk, thread_ids=[thread_id])
        time.sleep(1.5)


# ---------------------------------------------------------
# 3. INSTAGRAM PROFESSIONAL USERBOT ENGINE
# ---------------------------------------------------------
COOLDOWN_PERIOD = 3600  # 1 Hour cooldown per user for auto-reply
user_cooldowns = {}
processed_message_ids = set()
bot_started = False


def start_bot_loop():
    global bot_started
    if bot_started:
        return
    bot_started = True

    time.sleep(5)
    print("[SYSTEM] Booting Professional Instagram Userbot...", flush=True)

    raw_session = os.environ.get("INSTA_SESSION_JSON")
    if not raw_session:
        print("[CRITICAL ERROR] INSTA_SESSION_JSON missing in Environment Variables!", flush=True)
        return

    client = Client()
    client.delay_range = [2, 4]

    try:
        print("[AUTHENTICATION] Injecting Instagram Session JSON...", flush=True)
        try:
            decoded = base64.b64decode(raw_session).decode('utf-8')
            session_dict = json.loads(decoded)
        except Exception:
            session_dict = json.loads(raw_session)

        client.set_settings(session_dict)
        print("[AUTHENTICATION SUCCESS] Session injected successfully!", flush=True)
    except Exception as auth_err:
        print(f"[AUTHENTICATION FAILED] Could not load session settings: {auth_err}", flush=True)
        return

    my_user_id = None
    try:
        my_user_id = str(client.user_id)
        print(f"[USERBOT IDENTITY] Logged in as User ID: {my_user_id}", flush=True)
    except Exception as e:
        print(f"[USERBOT IDENTITY ERROR] Could not fetch user_id: {e}", flush=True)

    startup_timestamp = time.time()
    print(f"[SYSTEM READY] Bot Active! Processing messages received AFTER: {startup_timestamp}", flush=True)

    while True:
        try:
            threads = []
            try:
                threads = client.direct_threads(amount=8)
            except Exception as fetch_err:
                print(f"[FETCH ERROR] Could not retrieve inbox threads: {fetch_err}", flush=True)
                time.sleep(15)
                continue

            for thread in threads:
                try:
                    thread_id = str(thread.id)

                    # Ignore group chats
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

                    if msg_id in processed_message_ids:
                        continue

                    msg_ts = 0
                    if hasattr(last_msg, 'timestamp') and last_msg.timestamp:
                        try:
                            msg_ts = last_msg.timestamp.timestamp()
                        except Exception:
                            msg_ts = 0

                    if msg_ts > 0 and msg_ts < startup_timestamp:
                        processed_message_ids.add(msg_id)
                        continue

                    text_content = last_msg.text.strip() if last_msg.text else ""
                    if not text_content:
                        continue

                    is_self_message = (my_user_id and sender_id == my_user_id)
                    now = time.time()

                    # 🏓 COMMAND 1: .ping
                    if text_content.lower() == ".ping":
                        start_ping = time.time()
                        ping_time = round((time.time() - start_ping) * 1000, 2)
                        uptime_sec = int(time.time() - START_TIME)
                        reply_text = f"🏓 **Pong!**\n⚡ Latency: `{ping_time}ms`\n⏱️ Uptime: `{uptime_sec}s`"
                        client.direct_send(reply_text, thread_ids=[thread_id])
                        processed_message_ids.add(msg_id)
                        print(f"[PING SENT] Triggered by {sender_id}", flush=True)

                    # 📊 COMMAND 2: .status
                    elif text_content.lower() == ".status":
                        uptime_min = round((time.time() - START_TIME) / 60, 1)
                        status_text = (
                            "🤖 **Professional Userbot Status**\n"
                            "----------------------------\n"
                            f"✅ **State:** Fully Operational\n"
                            f"🧠 **AI Engine:** Groq (Llama 3.3 70B) / Pollinations OpenAI\n"
                            f"⏱️ **Uptime:** {uptime_min} Minutes\n"
                            f"📩 **Processed DMs:** {len(processed_message_ids)}\n"
                            "----------------------------"
                        )
                        client.direct_send(status_text, thread_ids=[thread_id])
                        processed_message_ids.add(msg_id)
                        print(f"[STATUS SENT] Triggered by {sender_id}", flush=True)

                    # 🤖 COMMAND 3: .ai <query>
                    elif text_content.lower().startswith(".ai "):
                        query = text_content[4:].strip()
                        print(f"[AI COMMAND] Sender: {sender_id} (Self: {is_self_message}) | Query: {query}", flush=True)

                        ai_output = generate_ai_response(query)
                        try:
                            send_split_message(client, ai_output, thread_id)
                            processed_message_ids.add(msg_id)
                            print(f"[AI REPLY SENT] Responded in thread {thread_id}", flush=True)
                            time.sleep(2)
                        except Exception as send_err:
                            print(f"[SEND ERROR] Failed to send AI response: {send_err}", flush=True)

                    # 📩 ROUTE B: Auto-Reply (Ignores self messages)
                    else:
                        if is_self_message:
                            processed_message_ids.add(msg_id)
                            continue

                        last_replied = user_cooldowns.get(sender_id, 0)
                        if (now - last_replied) > COOLDOWN_PERIOD:
                            auto_text = (
                                "Lakshit is currently offline 🤧\n"
                                "This is an automated response.\n\n"
                                "(Tip: Reply with '.ai <query>' to chat with AI, '.ping', or '.status'!)"
                            )
                            try:
                                client.direct_send(auto_text, thread_ids=[thread_id])
                                user_cooldowns[sender_id] = now
                                processed_message_ids.add(msg_id)
                                print(f"[AUTO-REPLY SENT] Sent to user {sender_id}", flush=True)
                                time.sleep(2)
                            except Exception as send_err:
                                print(f"[SEND ERROR] Failed to send auto-reply: {send_err}", flush=True)
                        else:
                            processed_message_ids.add(msg_id)

                except Exception as thread_err:
                    print(f"[THREAD ERROR] Softly handled: {thread_err}", flush=True)
                    continue

            if len(processed_message_ids) > 1500:
                processed_message_ids.clear()

            time.sleep(12)

        except Exception as loop_err:
            print(f"[MAIN LOOP RECOVERY] Handled outer error: {loop_err}", flush=True)
            time.sleep(15)


# Background runner initialization
bot_thread = Thread(target=start_bot_loop, daemon=True)
bot_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
            

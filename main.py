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
# 2. ULTRA-FAST & LOW-TOKEN AI ENGINE (Groq + Pollinations + Gemini)
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

# 🎯 STRICT IDENTITY + ULTRA SHORT LOW-TOKEN SYSTEM PROMPT
HUMAN_SYSTEM_PROMPT = (
    "You are the official AI Assistant of Lakshit. "
    "NEVER say you are Lakshit. You are only his AI Assistant. "
    "Reply in super fast, polite, concise Hinglish. Use 'aap' or 'bhai'. "
    "Keep answers under 15-20 words max to save speed and tokens."
)


def get_groq_ai(prompt: str) -> str:
    """Primary Ultra-Fast AI via Groq API."""
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
            "messages": [
                {"role": "system", "content": HUMAN_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.5,
            "max_tokens": 80  # Strict low-token budget for fast generation
        }
        res = requests.post(url, headers=headers, json=data, timeout=5)
        if res.status_code == 200:
            result = res.json()
            return result['choices'][0]['message']['content'].strip()
        else:
            print(f"[GROQ ERROR] Status Code: {res.status_code} | {res.text}", flush=True)
    except Exception as err:
        print(f"[GROQ FAIL] {err}", flush=True)
    return None


def get_pollinations_openai(prompt: str) -> str:
    """Secondary Fast AI Engine (Pollinations)."""
    try:
        full_prompt = f"{HUMAN_SYSTEM_PROMPT}\n\nUser message: {prompt}"
        encoded_prompt = urllib.parse.quote(full_prompt)
        url = f"https://text.pollinations.ai/{encoded_prompt}?model=openai"
        res = requests.get(url, timeout=5)
        if res.status_code == 200 and res.text.strip():
            return res.text.strip()
    except Exception as err:
        print(f"[POLLINATIONS ERROR] {err}", flush=True)
    return None


def get_gemini_ai(prompt: str) -> str:
    """Tertiary Backup AI Engine (Gemini 2.0 Flash)."""
    if ai_client:
        try:
            full_prompt = f"{HUMAN_SYSTEM_PROMPT}\n\nUser message: {prompt}"
            response = ai_client.models.generate_content(
                model='gemini-2.0-flash',
                contents=full_prompt,
            )
            if response and response.text and response.text.strip():
                return response.text.strip()
        except Exception as err:
            print(f"[GEMINI FAIL] {err}", flush=True)
    return None


def generate_ai_response(prompt: str) -> str:
    """Multi-Tier Auto Switcher + Signature Tag."""
    raw_response = get_groq_ai(prompt)

    if not raw_response:
        raw_response = get_pollinations_openai(prompt)

    if not raw_response:
        raw_response = get_gemini_ai(prompt)

    if not raw_response:
        raw_response = "Lakshit bhai abhi busy hain, aapka message un tak pahuncha dunga!"

    return f"{raw_response}\n\n~ AI Generated"


def send_split_message(client, text: str, thread_id: str, max_length: int = 900):
    """Bypasses Instagram length limitations safely."""
    if len(text) <= max_length:
        client.direct_send(text, thread_ids=[thread_id])
        return

    chunks = [text[i:i + max_length] for i in range(0, len(text), max_length)]
    for chunk in chunks:
        client.direct_send(chunk, thread_ids=[thread_id])
        time.sleep(1)


# ---------------------------------------------------------
# 3. INSTAGRAM PROFESSIONAL USERBOT ENGINE
# ---------------------------------------------------------
COOLDOWN_PERIOD = 3600  # Exact 1 Hour
ai_disabled_threads = {}
processed_message_ids = set()
bot_started = False


def start_bot_loop():
    global bot_started
    if bot_started:
        return
    bot_started = True

    time.sleep(2)
    print("[SYSTEM] Booting High-Speed Instagram Userbot...", flush=True)

    raw_session = os.environ.get("INSTA_SESSION_JSON")
    if not raw_session:
        print("[CRITICAL ERROR] INSTA_SESSION_JSON missing in Environment Variables!", flush=True)
        return

    client = Client()
    client.delay_range = [1, 2]

    try:
        try:
            decoded = base64.b64decode(raw_session).decode('utf-8')
            session_dict = json.loads(decoded)
        except Exception:
            session_dict = json.loads(raw_session)

        client.set_settings(session_dict)
        print("[AUTHENTICATION SUCCESS] Session injected successfully!", flush=True)
    except Exception as auth_err:
        print(f"[AUTHENTICATION FAILED] {auth_err}", flush=True)
        return

    my_user_id = None
    try:
        my_user_id = str(client.user_id)
        print(f"[USERBOT IDENTITY] Logged in as User ID: {my_user_id}", flush=True)
    except Exception as e:
        print(f"[USERBOT IDENTITY ERROR] {e}", flush=True)

    startup_timestamp = time.time()

    while True:
        try:
            threads = []
            try:
                threads = client.direct_threads(amount=6)
            except Exception as fetch_err:
                print(f"[FETCH ERROR] {fetch_err}", flush=True)
                time.sleep(5)
                continue

            for thread in threads:
                try:
                    thread_id = str(thread.id)

                    # 🛡️ FULL GROUP PROTECTION
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

                    # 📜 COMMANDS
                    if text_content.lower() == ".help":
                        help_menu = (
                            "⚡ **Lakshit's AI Assistant Commands**\n"
                            "----------------------------\n"
                            "🔹 `.aioff` : Turn OFF auto AI for 1 hour\n"
                            "🔹 `.aion` : Turn ON auto AI immediately\n"
                            "🔹 `.summary` : Summarize recent chat\n"
                            "🔹 `.ping` : Check bot latency\n"
                            "🔹 `.status` : System health (Owner only)\n"
                            "🔹 `.ai <query>` : Force AI response\n"
                            "----------------------------"
                        )
                        client.direct_send(help_menu, thread_ids=[thread_id])
                        processed_message_ids.add(msg_id)
                        continue

                    elif text_content.lower() == ".ping":
                        start_ping = time.time()
                        ping_time = round((time.time() - start_ping) * 1000, 2)
                        uptime_sec = int(time.time() - START_TIME)
                        reply_text = f"🏓 **Pong!**\n⚡ Latency: `{ping_time}ms`\n⏱️ Uptime: `{uptime_sec}s`"
                        client.direct_send(reply_text, thread_ids=[thread_id])
                        processed_message_ids.add(msg_id)
                        continue

                    elif text_content.lower() == ".status":
                        if is_self_message:
                            uptime_min = round((time.time() - START_TIME) / 60, 1)
                            status_text = f"🤖 **Status:** Operational\n⏱️ **Uptime:** {uptime_min}m\n📩 **Processed:** {len(processed_message_ids)}"
                            client.direct_send(status_text, thread_ids=[thread_id])
                        processed_message_ids.add(msg_id)
                        continue

                    elif text_content.lower() == ".aioff":
                        ai_disabled_threads[thread_id] = now
                        client.direct_send("🔴 Auto AI reply turned OFF for this chat for 1 hour.", thread_ids=[thread_id])
                        processed_message_ids.add(msg_id)
                        continue

                    elif text_content.lower() == ".aion":
                        if thread_id in ai_disabled_threads:
                            del ai_disabled_threads[thread_id]
                        client.direct_send("🟢 Auto AI reply turned ON for this chat.", thread_ids=[thread_id])
                        processed_message_ids.add(msg_id)
                        continue

                    elif text_content.lower() == ".summary":
                        try:
                            recent_msgs = thread.messages[:10]
                            chat_history = [f"{'Lakshit' if str(m.user_id) == my_user_id else 'User'}: {m.text or ''}" for m in reversed(recent_msgs)]
                            summary_output = generate_ai_response("Summarize this chat in 2 short points:\n" + "\n".join(chat_history))
                            send_split_message(client, f"📊 **Chat Summary:**\n\n{summary_output}", thread_id)
                        except Exception as sum_err:
                            client.direct_send("Could not generate summary.", thread_ids=[thread_id])
                        processed_message_ids.add(msg_id)
                        continue

                    elif text_content.lower().startswith(".ai "):
                        query = text_content[4:].strip()
                        ai_output = generate_ai_response(query)
                        send_split_message(client, ai_output, thread_id)
                        processed_message_ids.add(msg_id)
                        continue

                    # 🤖 DEFAULT AUTOMATIC AI CHAT
                    if is_self_message:
                        processed_message_ids.add(msg_id)
                        continue

                    if thread_id in ai_disabled_threads:
                        disabled_time = ai_disabled_threads[thread_id]
                        if (now - disabled_time) > COOLDOWN_PERIOD:
                            del ai_disabled_threads[thread_id]
                        else:
                            processed_message_ids.add(msg_id)
                            continue

                    # Generate AI response (Ultra Fast)
                    ai_reply = generate_ai_response(text_content)
                    send_split_message(client, ai_reply, thread_id)
                    processed_message_ids.add(msg_id)

                except Exception as thread_err:
                    print(f"[THREAD ERROR] {thread_err}", flush=True)
                    continue

            if len(processed_message_ids) > 1500:
                processed_message_ids.clear()

            time.sleep(3)  # Ultra fast 3-second inbox check cycle

        except Exception as loop_err:
            print(f"[MAIN LOOP ERROR] {loop_err}", flush=True)
            time.sleep(5)


# Background runner initialization
bot_thread = Thread(target=start_bot_loop, daemon=True)
bot_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
        

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

HUMAN_SYSTEM_PROMPT = (
    "You are responding on behalf of Lakshit (Kanu) on Instagram DMs. "
    "Chat naturally like a real Indian guy using chill Hinglish/English. "
    "Keep responses concise, friendly, casual, and human-like. Do not sound like a rigid robot or corporate assistant. "
    "Use subtle lowercase, natural phrasing, and casual tone."
)


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
            "messages": [
                {"role": "system", "content": HUMAN_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.8,
            "max_tokens": 600
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
        full_prompt = f"{HUMAN_SYSTEM_PROMPT}\n\nUser message: {prompt}"
        encoded_prompt = urllib.parse.quote(full_prompt)
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
    """Multi-Tier Auto Switcher + Mandatory Tag appending."""
    raw_response = None

    # Tier 1: Groq
    raw_response = get_groq_ai(prompt)

    # Tier 2: Pollinations OpenAI
    if not raw_response:
        print("[AI SYSTEM] Groq unavailable. Switching to Pollinations OpenAI...", flush=True)
        raw_response = get_pollinations_openai(prompt)

    # Tier 3: Gemini Fallback
    if not raw_response:
        print("[AI SYSTEM] Switching to Gemini Fallback Engine...", flush=True)
        raw_response = get_gemini_ai(prompt)

    if not raw_response:
        raw_response = "abhi thoda busy hoon, baad me baat karta hoon!"

    # Append signature tag
    return f"{raw_response}\n\n~ AI Generated"


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
COOLDOWN_PERIOD = 3600  # 1 Hour off duration when toggled off
user_cooldowns = {}
ai_disabled_threads = {}  # {thread_id: timestamp_when_disabled}
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

                    # ---------------------------------------------------------
                    # 📜 OWNER PRIVILEGED & HELPER COMMANDS
                    # ---------------------------------------------------------

                    # 📖 COMMAND 0: .help
                    if text_content.lower() == ".help":
                        help_menu = (
                            "⚡ **Lakshit's Userbot Commands**\n"
                            "----------------------------\n"
                            "🔹 `.aioff` : Turn OFF auto AI for this chat for 1 hour\n"
                            "🔹 `.aion` : Turn ON auto AI for this chat immediately\n"
                            "🔹 `.summary` : Summarize recent messages in this chat\n"
                            "🔹 `.ping` : Check bot response latency & uptime\n"
                            "🔹 `.status` : System health & processed stats\n"
                            "🔹 `.ai <query>` : Force trigger AI reply\n"
                            "----------------------------"
                        )
                        client.direct_send(help_menu, thread_ids=[thread_id])
                        processed_message_ids.add(msg_id)
                        continue

                    # 🏓 COMMAND 1: .ping
                    elif text_content.lower() == ".ping":
                        start_ping = time.time()
                        ping_time = round((time.time() - start_ping) * 1000, 2)
                        uptime_sec = int(time.time() - START_TIME)
                        reply_text = f"🏓 **Pong!**\n⚡ Latency: `{ping_time}ms`\n⏱️ Uptime: `{uptime_sec}s`"
                        client.direct_send(reply_text, thread_ids=[thread_id])
                        processed_message_ids.add(msg_id)
                        continue

                    # 📊 COMMAND 2: .status (Owner Only Protection)
                    elif text_content.lower() == ".status":
                        if is_self_message:
                            uptime_min = round((time.time() - START_TIME) / 60, 1)
                            disabled_count = len(ai_disabled_threads)
                            status_text = (
                                "🤖 **Professional Userbot Status**\n"
                                "----------------------------\n"
                                f"✅ **State:** Fully Operational\n"
                                f"🧠 **AI Engine:** Multi-Tier (Groq/Pollinations)\n"
                                f"⏱️ **Uptime:** {uptime_min} Minutes\n"
                                f"⏸️ **Paused AI Chats:** {disabled_count}\n"
                                f"📩 **Processed DMs:** {len(processed_message_ids)}\n"
                                "----------------------------"
                            )
                            client.direct_send(status_text, thread_ids=[thread_id])
                        processed_message_ids.add(msg_id)
                        continue

                    # 🔴 COMMAND 3: .aioff (Turns OFF AI for 1 hour)
                    elif text_content.lower() == ".aioff":
                        ai_disabled_threads[thread_id] = now
                        msg = "🔴 Auto AI reply turned OFF for this chat for 1 hour."
                        client.direct_send(msg, thread_ids=[thread_id])
                        processed_message_ids.add(msg_id)
                        print(f"[AI TOGGLE] Disabled AI for thread {thread_id} for 1 hr", flush=True)
                        continue

                    # 🟢 COMMAND 4: .aion (Forces AI back ON)
                    elif text_content.lower() == ".aion":
                        if thread_id in ai_disabled_threads:
                            del ai_disabled_threads[thread_id]
                        msg = "🟢 Auto AI reply turned ON for this chat."
                        client.direct_send(msg, thread_ids=[thread_id])
                        processed_message_ids.add(msg_id)
                        print(f"[AI TOGGLE] Enabled AI for thread {thread_id}", flush=True)
                        continue

                    # 📝 COMMAND 5: .summary (Summarize chat history)
                    elif text_content.lower() == ".summary":
                        print(f"[SUMMARY REQ] Generating thread summary for {thread_id}", flush=True)
                        try:
                            recent_msgs = thread.messages[:10]
                            chat_history = []
                            for m in reversed(recent_msgs):
                                sender = "Lakshit" if str(m.user_id) == my_user_id else "User"
                                text = m.text or "[Non-text message]"
                                chat_history.append(f"{sender}: {text}")

                            full_history_str = "\n".join(chat_history)
                            summary_prompt = f"Summarize the following Instagram conversation briefly into bullet points:\n\n{full_history_str}"

                            summary_output = generate_ai_response(summary_prompt)
                            send_split_message(client, f"📊 **Chat Summary:**\n\n{summary_output}", thread_id)
                        except Exception as sum_err:
                            print(f"[SUMMARY ERROR] {sum_err}", flush=True)
                            client.direct_send("Could not generate summary for this chat.", thread_ids=[thread_id])
                        
                        processed_message_ids.add(msg_id)
                        continue

                    # 🤖 COMMAND 6: .ai <query> (Manual AI command)
                    elif text_content.lower().startswith(".ai "):
                        query = text_content[4:].strip()
                        ai_output = generate_ai_response(query)
                        try:
                            send_split_message(client, ai_output, thread_id)
                            processed_message_ids.add(msg_id)
                            time.sleep(2)
                        except Exception as send_err:
                            print(f"[SEND ERROR] Failed to send AI response: {send_err}", flush=True)
                        continue

                    # ---------------------------------------------------------
                    # 🤖 ROUTE B: DEFAULT AUTOMATIC AI CHAT
                    # ---------------------------------------------------------

                    # 1. Ignore if sender is YOU (Self-message safeguard)
                    if is_self_message:
                        processed_message_ids.add(msg_id)
                        continue

                    # 2. Check 1-Hour Auto-Re-Enable Timer logic
                    if thread_id in ai_disabled_threads:
                        disabled_time = ai_disabled_threads[thread_id]
                        if (now - disabled_time) > COOLDOWN_PERIOD:
                            # 1 Hour passed! Automatically re-enable
                            del ai_disabled_threads[thread_id]
                            print(f"[AUTO RE-ENABLE] 1 Hour passed. Auto AI re-enabled for thread {thread_id}", flush=True)
                        else:
                            # Still within the 1-hour OFF window
                            processed_message_ids.add(msg_id)
                            continue

                    # 3. Generate Natural Human-like AI Response
                    print(f"[AUTO AI DM] Responding to message from sender {sender_id}", flush=True)
                    ai_reply = generate_ai_response(text_content)
                    try:
                        send_split_message(client, ai_reply, thread_id)
                        processed_message_ids.add(msg_id)
                        time.sleep(2)
                    except Exception as send_err:
                        print(f"[SEND ERROR] Failed to send Auto AI reply: {send_err}", flush=True)

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

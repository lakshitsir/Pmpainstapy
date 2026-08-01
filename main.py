import os
import time
import random
import threading
from flask import Flask
from instagrapi import Client
from google import genai
from google.genai import types

app = Flask(__name__)

@app.route('/')
def home():
    return "Status: Operational", 200

def run_bot():
    time.sleep(3)
    
    ai = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    cl = Client()
    
    INSTA_USER = os.environ.get("INSTA_USER")
    INSTA_PASS = os.environ.get("INSTA_PASS")
    SESSION_FILE = "session.json"

    # Silent Session Restore
    try:
        if os.path.exists(SESSION_FILE):
            cl.load_settings(SESSION_FILE)
            cl.login(INSTA_USER, INSTA_PASS)
        else:
            cl.login(INSTA_USER, INSTA_PASS)
            cl.dump_settings(SESSION_FILE)
    except Exception:
        pass

    cooldowns = {}

    while True:
        try:
            threads = cl.direct_threads(amount=5)
            
            for thread in threads:
                # Strictly Private DMs (Ignore Group Chats)
                if thread.is_group:
                    continue

                thread_id = thread.id
                messages = thread.messages
                if not messages: 
                    continue

                last_msg = messages[0]
                user_id = str(last_msg.user_id)
                text = last_msg.text.strip() if last_msg.text else ""

                # Ignore own sent messages
                if user_id == str(cl.user_id): 
                    continue

                cmd = text.lower()

                # 1. Story Mention Handler
                if last_msg.item_type == 'story_share' or 'mentioned you in their story' in cmd:
                    if time.time() - cooldowns.get(f"story_{user_id}", 0) > 3600:
                        story_reply = "Thanks For Mentioning , Lakshit is Offline Currently He Will Check it 😁🙃"
                        cl.direct_answer(thread_id, story_reply)
                        cooldowns[f"story_{user_id}"] = time.time()
                    continue

                # 2. Command: .help
                if cmd == ".help":
                    help_txt = (
                        "AI Management Cmds\n"
                        "~\n"
                        ".ai <query> - Ask Gemini AI\n"
                        ".ai (reply to msg) - Context analysis / Follow up\n"
                        ".status - Check system health\n"
                        ".about - Profile details\n\n"
                        "⚡ 🗿"
                    )
                    cl.direct_answer(thread_id, help_txt)
                    continue

                # 3. Command: .status
                if cmd == ".status":
                    cl.direct_answer(thread_id, "System status: Active\nLatency: Minimal\n\n⚡ 🗿")
                    continue

                # 4. Command: .about
                if cmd == ".about":
                    about_txt = (
                        "Lakshit (Kanu)\n"
                        "Developer & Tech Specialist\n\n"
                        "Send .ai <query> for automated responses.\n\n⚡ 🗿"
                    )
                    cl.direct_answer(thread_id, about_txt)
                    continue

                # 5. Command: .ai <query> (Supports Images & Replied Context)
                if cmd.startswith(".ai"):
                    query = text[3:].strip()

                    time.sleep(random.uniform(1.2, 2.2))
                    contents = []
                    
                    replied_context = ""
                    if hasattr(last_msg, 'replied_to_message') and last_msg.replied_to_message:
                        ref_msg = last_msg.replied_to_message
                        if ref_msg.text:
                            replied_context = f"Replied-to Message: '{ref_msg.text}'"

                    if last_msg.item_type == 'media' and last_msg.media:
                        try:
                            photo_path = cl.photo_download(last_msg.media.pk)
                            with open(photo_path, 'rb') as img_file:
                                image_bytes = img_file.read()
                            contents.append(types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))
                            os.remove(photo_path)
                        except Exception:
                            pass

                    system_prompt = (
                        "You are an AI assistant representing Lakshit. "
                        "Provide a concise, direct, professional, and intelligent response. "
                        "Avoid filler text, cringe slangs, or excessive formatting."
                    )

                    full_prompt = f"{system_prompt}\n\n"
                    if replied_context:
                        full_prompt += f"{replied_context}\n"
                    
                    full_prompt += f"User Input: {query if query else 'Analyze the provided context/image.'}"
                    contents.append(full_prompt)

                    response = ai.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=contents
                    )

                    reply_text = (response.text.strip() if response.text else "Unable to process.") + "\n\n⚡ 🗿"
                    cl.direct_answer(thread_id, reply_text)
                    continue

                # 6. General Auto Reply (For Normal DMs) with 1-Hour Cooldown
                if time.time() - cooldowns.get(f"auto_{user_id}", 0) > 3600:
                    offline_reply = (
                        "Lakshitt is Currently Offlinee 🤧\n"
                        "This Message is Generated by Userbot / Automated Bot 😁"
                    )
                    cl.direct_answer(thread_id, offline_reply)
                    cooldowns[f"auto_{user_id}"] = time.time()

        except Exception:
            # Silent Suppression
            pass

        time.sleep(random.randint(3, 4))

bot_thread = threading.Thread(target=run_bot, daemon=True)
bot_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))


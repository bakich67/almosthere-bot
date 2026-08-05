import os
import requests
import json
import random
from datetime import datetime

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID = os.environ["TELEGRAM_CHANNEL_ID"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

CALL_TO_ACTIONS_BEFORE = [
    "Will it live up to the hype? Check back soon.",
    "What do you think — overpromised or underdelivered?",
    "Would you buy this? Comment below.",
    "Send this to someone who's waiting for it.",
    "Subscribe so you don't miss the follow-up.",
    "Want more previews like this? Like and share."
]

CALL_TO_ACTIONS_AFTER = [
    "Did it live up to the hype? Comment your thoughts.",
    "Was it worth the wait?",
    "Did you expect more? Tell us below.",
    "Share this with someone who was waiting too.",
    "Want more reality checks? Subscribe.",
    "Like if you were surprised. Share if you weren't."
]

PINNED_MESSAGE = "We don't just repost news. We compare what was promised vs what actually happened. Tech, science, movies. Every day at 18:00 MSK."

def pin_message():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": PINNED_MESSAGE
    }
    r = requests.post(url, json=payload)
    if r.status_code == 200:
        msg_id = r.json()["result"]["message_id"]
        pin_url = f"https://api.telegram.org/bot{BOT_TOKEN}/pinChatMessage"
        requests.post(pin_url, json={"chat_id": CHANNEL_ID, "message_id": msg_id})
        print("Pinned message updated.")
    else:
        print(f"Pin error: {r.text}")

def get_post_type():
    today = datetime.utcnow()
    if today.day % 2 == 0:
        return "before"
    else:
        return "after"

def generate_post(post_type):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    if post_type == "before":
        cta = random.choice(CALL_TO_ACTIONS_BEFORE)
        system_prompt = f"""You are the editor of '@AlmostHereEN'.
Find a REAL upcoming event in tech, science, or movies happening in 3–7 days.
Rules:
- Topics ONLY: tech (gadgets, software, AI), science (space, medicine, discoveries), movies (premieres, trailers).
- Use ONLY real events from: TechCrunch, The Verge, Ars Technica, Nature, BBC, Reuters, NASA, SpaceX, Apple, Tesla, IMDb, Variety.
- Do NOT invent events. If you can't find one — return "No suitable event."
- Write a punchy preview (600–900 chars). Style: smart friend telling you what to watch for. No hype.
- Structure: opening line with date/days left → what's expected → witty image → source → ONE call to action: «{cta}» → signature: «Stay tuned. Almost here.»
- English only."""
        user_prompt = "Find a REAL upcoming event in tech/science/movies happening in 3–7 days. Preview it."
    else:
        cta = random.choice(CALL_TO_ACTIONS_AFTER)
        system_prompt = f"""You are the editor of '@AlmostHereEN'.
Find a REAL event in tech, science, or movies that happened TODAY or YESTERDAY.
Rules:
- Topics ONLY: tech (gadgets, software, AI), science (space, medicine, discoveries), movies (premieres, trailers).
- Use ONLY real events from: TechCrunch, The Verge, Ars Technica, Nature, BBC, Reuters, NASA, SpaceX, Apple, Tesla, IMDb, Variety.
- Do NOT invent events. If you can't find one — return "No suitable event."
- Write a reality-check post (600–900 chars). Compare what was promised vs what actually happened. Be honest — if it flopped, say so.
- Structure: what was expected → what actually happened → witty observation → source → ONE call to action: «{cta}» → signature: «Reality checked. Almost here.»
- English only."""
        user_prompt = "Find a REAL event in tech/science/movies that happened today or yesterday. Compare expectations vs reality."

    data = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.5,
        "max_tokens": 1000
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code != 200:
        raise Exception(f"Groq error: {response.text}")
    content = response.json()["choices"][0]["message"]["content"].strip()

    if not content or len(content) < 50 or "no suitable" in content.lower():
        print(f"No suitable {'preview' if post_type == 'before' else 'follow-up'} event. Post not published.")
        return None

    if post_type == "before":
        if not content.endswith("Almost here."):
            content = content.rstrip() + "\n\nStay tuned. Almost here."
    else:
        if not content.endswith("Almost here."):
            content = content.rstrip() + "\n\nReality checked. Almost here."

    return content

def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    r = requests.post(url, json=payload)
    if r.status_code != 200:
        raise Exception(f"Telegram error: {r.text}")

if __name__ == "__main__":
    pin_message()
    post_type = get_post_type()
    print(f"Post type: {post_type}")
    post = generate_post(post_type)
    if post is None:
        print("No post published.")
    else:
        print("Generated post:\n", post)
        send_to_telegram(post)
        print("Post sent to channel")

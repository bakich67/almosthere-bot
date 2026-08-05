import os
import requests
import json
import random

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID = os.environ["TELEGRAM_CHANNEL_ID"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

CALL_TO_ACTIONS = [
    "Will it live up to the hype? Check back and see.",
    "What do you think — overpromised or underdelivered?",
    "Would you buy this? Comment below.",
    "Send this to someone who's waiting for it.",
    "Subscribe so you don't miss the follow-up.",
    "Bookmark this post and come back later.",
    "Want more previews like this? Like and share."
]

def generate_post():
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    cta = random.choice(CALL_TO_ACTIONS)

    system_prompt = f"""You are the editor of the Telegram channel '@AlmostHereEN'.
Your job: find an upcoming event (product launch, movie premiere, scientific experiment, tech announcement) that is expected to happen in 3–7 days.
Rules:
- Use ONLY real, verifiable upcoming events from authoritative sources (TechCrunch, The Verge, Ars Technica, Nature, BBC, Reuters, NASA, SpaceX, Apple, Tesla).
- Do NOT invent events, products, or scientists.
- If you cannot find a real event — return "No suitable event found."
- Write a short, punchy post (600–900 characters).
- Style: simple words, as if a smart friend is telling you what to watch for. No hype, no clickbait.
- Structure:
  1. An opening line that creates anticipation (what's coming, when).
  2. What is expected, why it matters.
  3. A short, witty image or comparison.
  4. Source (publication name, date, link if possible).
  5. ONE call to action: «{cta}»
  6. Signature: «Stay tuned. Almost here.»
- Language: English only.
- Main criteria: 'Would someone forward this to a friend?'"""

    user_prompt = "Find a REAL upcoming event happening in 3–7 days from a credible source. Preview it for the Almost Here channel."

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

    if not content or len(content) < 50:
        print("No suitable event. Post not published.")
        return None

    if not content.endswith("Almost here."):
        content = content.rstrip() + "\n\nStay tuned. Almost here."
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
    post = generate_post()
    if post is None:
        print("Post not published: no verified upcoming event.")
    else:
        print("Generated post:\n", post)
        send_to_telegram(post)
        print("Post sent to channel")

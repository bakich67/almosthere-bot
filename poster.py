import os
import requests
import json
import random
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import re

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

PINNED_MESSAGE = "We don't just repost news. We compare what was promised vs what actually happened. Tech, science, movies. Daily."

def pin_message():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHANNEL_ID, "text": PINNED_MESSAGE}
    r = requests.post(url, json=payload)
    if r.status_code == 200:
        msg_id = r.json()["result"]["message_id"]
        pin_url = f"https://api.telegram.org/bot{BOT_TOKEN}/pinChatMessage"
        requests.post(pin_url, json={"chat_id": CHANNEL_ID, "message_id": msg_id})
        print("Pinned message updated.")
    else:
        print(f"Pin error: {r.text}")

def parse_rss():
    """Парсит все RSS-ленты и возвращает список новостей с датами."""
    try:
        with open("rss_sources.json", "r") as f:
            sources = json.load(f)["sources"]
    except:
        print("rss_sources.json not found. Using Groq without real news.")
        return []

    all_news = []
    for source in sources:
        try:
            resp = requests.get(source["url"], timeout=10)
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item"):
                title = item.find("title").text if item.find("title") is not None else ""
                link = item.find("link").text if item.find("link") is not None else ""
                desc = item.find("description").text if item.find("description") is not None else ""
                pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
                all_news.append({
                    "title": title,
                    "link": link,
                    "description": desc,
                    "pub_date": pub_date,
                    "source": source["name"],
                    "topic": source["topic"]
                })
        except Exception as e:
            print(f"Failed to parse {source['name']}: {e}")
    return all_news

def filter_events(news_list, post_type):
    """Фильтрует новости: upcoming (3-7 days) или recent (0-2 days)."""
    today = datetime.utcnow()
    filtered = []
    for item in news_list:
        try:
            pub_date = datetime.strptime(item["pub_date"], "%a, %d %b %Y %H:%M:%S %z")
            pub_date = pub_date.replace(tzinfo=None)
            days_diff = (pub_date - today).days
            if post_type == "before" and 3 <= days_diff <= 7:
                filtered.append(item)
            elif post_type == "after" and -2 <= days_diff <= 0:
                filtered.append(item)
        except:
            continue
    return filtered

def get_post_type():
    today = datetime.utcnow()
    return "before" if today.day % 2 == 0 else "after"

def generate_post(post_type, real_news=None):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    if real_news and len(real_news) > 0:
        news_text = random.choice(real_news)
        real_context = f"Real news item: {news_text['title']}. Source: {news_text['source']}. Link: {news_text['link']}. Description: {news_text['description'][:300]}"
    else:
        real_context = "No real news found from RSS. Use your own knowledge but DO NOT invent."

    if post_type == "before":
        cta = random.choice(CALL_TO_ACTIONS_BEFORE)
        system_prompt = f"""You are the editor of '@AlmostHereEN'.
{real_context}
Write a punchy preview post (600–900 chars) about this upcoming event.
Rules:
- Topics ONLY: tech, science, movies.
- Style: smart friend telling you what to watch for. No hype.
- Structure: opening line → what was promised → witty image → source → ONE call to action: «{cta}» → signature: «We'll check. Almost here.»
- English only."""
    else:
        cta = random.choice(CALL_TO_ACTIONS_AFTER)
        system_prompt = f"""You are the editor of '@AlmostHereEN'.
{real_context}
Write a reality-check post (600–900 chars) about this recent event.
Rules:
- Topics ONLY: tech, science, movies.
- Style: compare what was promised vs what actually happened. Be honest.
- Structure: what was promised → what actually happened → witty observation → source → ONE call to action: «{cta}» → signature: «Promised vs checked. Almost here.»
- English only."""

    data = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Write the post based on the provided news item."}
        ],
        "temperature": 0.5,
        "max_tokens": 1000
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code != 200:
        raise Exception(f"Groq error: {response.text}")
    content = response.json()["choices"][0]["message"]["content"].strip()

    if not content or len(content) < 50:
        print("No suitable post generated.")
        return None

    if post_type == "before":
        if not content.endswith("Almost here."):
            content = content.rstrip() + "\n\nWe'll check. Almost here."
    else:
        if not content.endswith("Almost here."):
            content = content.rstrip() + "\n\nPromised vs checked. Almost here."

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
    all_news = parse_rss()
    post_type = get_post_type()
    print(f"Post type: {post_type}")
    real_events = filter_events(all_news, post_type)
    print(f"Found {len(real_events)} real events from RSS.")
    post = generate_post(post_type, real_events)
    if post is None:
        print("No post published.")
    else:
        print("Generated post:\n", post)
        send_to_telegram(post)
        print("Post sent to channel")

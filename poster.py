import os
import requests
import json
import random
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import re
from dateutil import parser

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID = os.environ["TELEGRAM_CHANNEL_ID"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

PINNED_MESSAGE = "We compare what was promised vs what actually happened. Tech, science, movies. Daily at 18:00 MSK. Mon/Wed/Fri Tech, Tue/Thu Science, Sat Movies."

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

def get_weekday_topic():
    """Определяет тему дня по дню недели (UTC)."""
    weekday = datetime.utcnow().weekday()  # 0 = понедельник
    if weekday in [0, 2, 4]:  # Пн, Ср, Пт
        return "tech"
    elif weekday in [1, 3]:   # Вт, Чт
        return "science"
    elif weekday == 5:        # Сб
        return "movies"
    else:                     # Вс – worst promises of the week
        return "weekly"

def parse_rss():
    try:
        with open("rss_sources.json", "r") as f:
            sources = json.load(f)["sources"]
    except:
        print("rss_sources.json not found.")
        return []

    all_news = []
    cutoff_date = datetime.utcnow() - timedelta(days=1)

    for source in sources:
        try:
            resp = requests.get(source["url"], timeout=10)
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item"):
                title = item.find("title").text if item.find("title") is not None else ""
                link = item.find("link").text if item.find("link") is not None else ""
                desc_elem = item.find("description")
                desc = desc_elem.text if desc_elem is not None and desc_elem.text is not None else ""

                pub_date_str = item.find("pubDate").text if item.find("pubDate") is not None else ""
                if not pub_date_str:
                    dc_date = item.find("{http://purl.org/dc/elements/1.1/}date")
                    if dc_date is not None:
                        pub_date_str = dc_date.text

                if pub_date_str:
                    try:
                        pub_date = parser.parse(pub_date_str).replace(tzinfo=None)
                        if pub_date >= cutoff_date:
                            all_news.append({
                                "title": title,
                                "link": link,
                                "description": desc,
                                "source": source["name"],
                                "topic": source["topic"]
                            })
                    except:
                        continue
        except Exception as e:
            print(f"Failed to parse {source['name']}: {e}")
    return all_news

def generate_post(topic, news_list):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    if news_list and len(news_list) >= 2:
        selected = random.sample(news_list, min(2, len(news_list)))
        context = (
            f"Source 1: {selected[0]['title']} – {selected[0]['source']} ({selected[0]['link']})\n"
            f"Source 2: {selected[1]['title']} – {selected[1]['source']} ({selected[1]['link']})\n"
            f"Compare their coverage and identify any contradictions or differences in their reporting."
        )
    elif news_list:
        item = news_list[0]
        context = f"Only one source available: {item['title']} – {item['source']} ({item['link']})"
    else:
        print("No news found for topic.")
        return None

    if topic == "weekly":
        system_prompt = f"""You are '@AlmostHereEN'.
{context}
Write a weekly roundup post (800–1000 chars) about the WORST promises of the week in tech, science, and movies.
Format EXACTLY:
📝 Promised: [what was promised]
🧪 Got: [what actually happened]
Verdict: ❌ (or ✅ / ⚠️)
🔗 Sources: [link1], [link2]
No jokes. No call to action. Just the facts.
End with: Promised vs checked. Almost here."""
    else:
        system_prompt = f"""You are '@AlmostHereEN'.
{context}
Write a post (600–900 chars) about a recent event in {topic}.
Find a story that flew UNDER THE RADAR – not the top headline, but something with low media coverage and a clear gap between promise and reality.
Format EXACTLY:
📝 Promised: [what was promised]
🧪 Got: [what actually happened]
Verdict: ✅ (if delivered) / ⚠️ (if partially) / ❌ (if failed)
🔗 Sources: [link1], [link2]
No jokes. No 'Witty observation'. No calls to action. Just the facts.
End with: Promised vs checked. Almost here."""

    data = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Write the post."}
        ],
        "temperature": 0.4,
        "max_tokens": 1000
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code != 200:
        raise Exception(f"Groq error: {response.text}")
    content = response.json()["choices"][0]["message"]["content"].strip()

    if not content or len(content) < 50:
        return None

    # Проверяем, что подпись на месте
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
    try:
        pin_message()
        topic = get_weekday_topic()
        print(f"Topic for today ({datetime.utcnow().strftime('%A')}): {topic}")
        all_news = parse_rss()
        # Фильтруем по теме (кроме воскресенья)
        if topic != "weekly":
            filtered = [n for n in all_news if n.get("topic") == topic]
            if not filtered:
                filtered = all_news  # fallback
        else:
            filtered = all_news
        print(f"Found {len(filtered)} relevant news items.")
        post = generate_post(topic, filtered)
        if post is None:
            print("No post generated.")
        else:
            print("Generated post:\n", post)
            send_to_telegram(post)
            print("Post sent to channel")
    except Exception as e:
        print(f"Critical error: {e}")

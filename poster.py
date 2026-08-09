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

USED_LINKS_FILE = "used_links.json"

def load_used_links():
    try:
        with open(USED_LINKS_FILE, "r") as f:
            return set(json.load(f))
    except:
        return set()

def save_used_links(links):
    with open(USED_LINKS_FILE, "w") as f:
        json.dump(list(links), f)

def clean_link(link):
    return link.split('?')[0]

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
    weekday = datetime.utcnow().weekday()
    if weekday in [0, 2, 4]:
        return "tech"
    elif weekday in [1, 3]:
        return "science"
    elif weekday == 5:
        return "movies"
    else:
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

def find_related_pair(news_list):
    stop_words = {"the", "a", "an", "is", "in", "to", "of", "for", "and", "on", "at", "with", "by", "from", "its", "it", "this", "that", "was", "are", "has", "have", "new", "how", "what", "why", "after", "before", "over", "into", "about"}
    
    def get_keywords(title):
        words = re.findall(r'\b[a-z]{3,}\b', title.lower())
        return set(w for w in words if w not in stop_words)
    
    best_pair = None
    best_score = 0
    
    for i in range(len(news_list)):
        for j in range(i+1, len(news_list)):
            kw1 = get_keywords(news_list[i]["title"])
            kw2 = get_keywords(news_list[j]["title"])
            common = len(kw1 & kw2)
            if common > best_score:
                best_score = common
                best_pair = (news_list[i], news_list[j])
    
    if best_score >= 2:
        return list(best_pair)
    return None

def generate_post(topic, news_list):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    # Исключаем уже использованные ссылки
    used_links = load_used_links()
    fresh_news = [n for n in news_list if clean_link(n["link"]) not in used_links]
    if not fresh_news:
        print("All news already used. Post skipped.")
        return None

    pair = find_related_pair(fresh_news)
    if pair:
        item1, item2 = pair
        context = (
            f"Source 1: {item1['title']} – {item1['source']} ({item1['link']})\n"
            f"Source 2: {item2['title']} – {item2['source']} ({item2['link']})\n"
            f"Compare their coverage and identify any contradictions or differences."
        )
        sources_str = f"[{item1['source']}]({item1['link']}), [{item2['source']}]({item2['link']})"
        used_links.update([clean_link(item1["link"]), clean_link(item2["link"])])
    else:
        item = random.choice(fresh_news)
        context = f"Only one source available: {item['title']} – {item['source']} ({item['link']})"
        sources_str = f"[{item['source']}]({item['link']})"
        used_links.add(clean_link(item["link"]))

    # Сохраняем обновлённый список
    save_used_links(used_links)

    if topic == "weekly":
        system_prompt = f"""You are '@AlmostHereEN'.
{context}
Write a weekly roundup post (800–1000 chars) about the WORST promises of the week in tech, science, and movies.
Format EXACTLY:
📝 Promised: [what was promised]
🧪 Got: [what actually happened]
Verdict: ❌ (or ✅ / ⚠️)
🔗 Sources: {sources_str}
No jokes. No call to action. Just the facts.
End with: Promised vs checked. Almost here."""
    else:
        system_prompt = f"""You are '@AlmostHereEN'.
{context}
Write a post (600–900 chars) about this event.
Find a story that flew UNDER THE RADAR – not the top headline, but something with low media coverage and a clear gap between promise and reality.
Format EXACTLY:
📝 Promised: [what was promised]
🧪 Got: [what actually happened]
Verdict: ✅ (if delivered) / ⚠️ (if partially) / ❌ (if failed)
🔗 Sources: {sources_str}
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

    content = re.sub(r'\n*(Promised vs checked\.\s*)?Almost here\.\s*$', '', content, flags=re.IGNORECASE).rstrip()
    content = content + "\n\nPromised vs checked. Almost here."
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
        if topic != "weekly":
            filtered = [n for n in all_news if n.get("topic") == topic]
            if not filtered:
                filtered = all_news
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

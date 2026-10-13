import os
import html
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

GROQ_MODEL = "openai/gpt-oss-120b"

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

def clean_text(text, limit=700):
    text = re.sub(r'<[^>]+>', ' ', text or "")
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:limit]

def link_html(item):
    return f'<a href="{html.escape(item["link"], quote=True)}">{html.escape(item["source"])}</a>'

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
                                "description": clean_text(desc),
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

    used_links = load_used_links()
    fresh_news = [n for n in news_list if clean_link(n["link"]) not in used_links]
    if not fresh_news:
        print("All news already used. Post skipped.")
        return None, None

    pair = find_related_pair(fresh_news)
    if pair:
        item1, item2 = pair
        context = (
            f"Source 1 ({item1['source']}): {item1['title']}\n{item1['description']}\n\n"
            f"Source 2 ({item2['source']}): {item2['title']}\n{item2['description']}\n\n"
            f"Compare the two sources. Report a contradiction or difference ONLY if it is visible in the text above."
        )
        sources_str = f"{link_html(item1)}, {link_html(item2)}"
        used_links.update([clean_link(item1["link"]), clean_link(item2["link"])])
    else:
        item = random.choice(fresh_news)
        context = f"Only one source ({item['source']}): {item['title']}\n{item['description']}"
        sources_str = link_html(item)
        used_links.add(clean_link(item["link"]))

    save_used_links(used_links)

    system_prompt = f"""You are '@AlmostHereEN', a channel that checks promises against outcomes.
Use ONLY the facts in the source material below. Do not add numbers, prices, dates, names, versions or specs that are not in that text.

{context}

Write a post (500-800 chars) about ONE event. Choose the most important or surprising one.
Format EXACTLY, ONE block:
📝 Promised: [what the source says was announced, planned or claimed]
🧪 Got: [what actually happened, ONLY if a source reports the outcome. If the sources only announce or preview the event, write exactly: Not yet confirmed. The sources only report the announcement.]
Verdict: ✅ outcome reported and matches the promise / ⚠️ sources contradict each other or the outcome differs / ❌ promise clearly failed / ⏳ outcome not yet confirmed
No sources line. No jokes. No calls to action. No multiple blocks.
End with: Promised vs checked. Almost here."""

    data = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Write the post about ONE event only."}
        ],
        "temperature": 0.2,
        "max_tokens": 1500
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code != 200:
        raise Exception(f"Groq error: {response.text}")
    content = response.json()["choices"][0]["message"]["content"].strip()

    if not content or len(content) < 50:
        print("Пустой ответ от Groq.")
        return None, used_links

    content = re.split(r'(?<=Almost here\.)\s*(?=📝)', content)[0]
    content = re.sub(r'\n*(Promised vs checked\.\s*)?Almost here\.\s*$', '', content, flags=re.IGNORECASE).rstrip()
    content = re.sub(r'\n*🔗.*$', '', content, flags=re.DOTALL).rstrip()
    content = html.escape(content, quote=False)
    content = f"{content}\n🔗 Sources: {sources_str}\n\nPromised vs checked. Almost here."
    return content, used_links

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
        post, _ = generate_post(topic, filtered)
        if post is None:
            print("No post generated.")
        else:
            print("Generated post:\n", post)
            send_to_telegram(post)
            print("Post sent to channel")
    except Exception as e:
        print(f"Critical error: {e}")

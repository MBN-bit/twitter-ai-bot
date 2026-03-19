"""
Twitter AI Bot - أداة أتمتة تويتر بالذكاء الاصطناعي
تجلب أخبار الذكاء الاصطناعي، تصيغها بـ OpenRouter (Gemini)، وتنشرها مع صورة عبر Tweepy.
"""

import os
import re
import time
import random
import logging
import requests
import feedparser
import tweepy
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path

# ──────────────────────────────────────────────
# الإعداد والتهيئة
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

POSTED_URLS_FILE = "posted_urls.txt"
MAX_STORED_URLS   = 500          # نظّف القديم بعد 500 رابط
TWEET_CHAR_LIMIT  = 270          # حد أمان دون الـ 280

# ──────────────────────────────────────────────
# مصادر RSS لأخبار الذكاء الاصطناعي
# ──────────────────────────────────────────────
RSS_FEEDS = [
    # أخبار عامة عن الذكاء الاصطناعي
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://venturebeat.com/category/ai/feed/",
    "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "https://feeds.feedburner.com/nvidiablog",
    # أبحاث ونماذج
    "https://openai.com/blog/rss.xml",
    "https://www.anthropic.com/rss.xml",
    "https://blog.google/technology/ai/rss/",
    "https://huggingface.co/blog/feed.xml",
    # تقنية عامة
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://rss.slashdot.org/Slashdot/slashdotMain",
]

# كلمات دلالية لفلترة الأخبار المتعلقة بالذكاء الاصطناعي (محدثة وشاملة)
AI_KEYWORDS = [
    # مصطلحات عامة وأساسية
    "ai", "artificial intelligence", "llm", "machine learning", "deep learning", 
    "neural", "model", "agent", "agi", "asi", "multimodal",
    
    # الشركات والنماذج الكبيرة (الأمريكية والصينية)
    "openai", "chatgpt", "gpt-4", "gpt-5", "sora", 
    "anthropic", "claude", 
    "google", "gemini", "deepmind",
    "meta", "llama",
    "xai", "grok",
    "mistral", "qwen", "deepseek", "alibaba",
    
    # أدوات المطورين والـ Vibe Coding (الترند الجديد)
    "vibe coding", "cursor", "cursor ai", "lovable", "bolt.new", "bolt", 
    "devin", "copilot", "github copilot", "code interpreter",
    
    # مصطلحات الإطلاق والتحديثات
    "release", "announces", "open source", "hugging face", "huggingface", 
    "weights", "benchmark", "inference", "fine-tuning", "rag", "parameters"
]

# ──────────────────────────────────────────────
# 1. نظام الذاكرة (Anti-Spam)
# ──────────────────────────────────────────────

def load_posted_urls() -> set:
    """تحميل الروابط المنشورة سابقاً من الملف."""
    path = Path(POSTED_URLS_FILE)
    if not path.exists():
        return set()
    urls = {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}
    log.info(f"📂 تم تحميل {len(urls)} رابط من الذاكرة")
    return urls

def save_posted_url(url: str) -> None:
    """إضافة رابط جديد وحذف القديم إن تجاوزنا الحد."""
    path = Path(POSTED_URLS_FILE)
    existing = []
    if path.exists():
        existing = [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]

    if url not in existing:
        existing.append(url)

    if len(existing) > MAX_STORED_URLS:
        existing = existing[-MAX_STORED_URLS:]

    path.write_text("\n".join(existing) + "\n", encoding="utf-8")
    log.info(f"💾 تم حفظ الرابط في الذاكرة: {url[:60]}...")

# ──────────────────────────────────────────────
# 2. جلب الأخبار من RSS
# ──────────────────────────────────────────────

def is_ai_related(title: str, summary: str) -> bool:
    """فحص إذا كان الخبر متعلقاً بالذكاء الاصطناعي."""
    text = (title + " " + summary).lower()
    return any(kw in text for kw in AI_KEYWORDS)

def fetch_news(posted_urls: set) -> list[dict]:
    """جلب أخبار جديدة من جميع مصادر RSS."""
    new_items = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; AINewsBot/1.0)"}

    for feed_url in RSS_FEEDS:
        try:
            log.info(f"🌐 جلب: {feed_url}")
            resp = requests.get(feed_url, headers=headers, timeout=15)
            feed = feedparser.parse(resp.content)

            for entry in feed.entries[:10]:
                url   = entry.get("link", "").strip()
                title = entry.get("title", "").strip()
                summary = entry.get("summary", entry.get("description", "")).strip()

                summary = re.sub(r"<[^>]+>", " ", summary)
                summary = re.sub(r"\s+", " ", summary).strip()

                if not url or not title:
                    continue
                if url in posted_urls:
                    continue
                if not is_ai_related(title, summary):
                    continue

                image_url = None
                for key in ("media_thumbnail", "media_content"):
                    media = entry.get(key, [])
                    if media and isinstance(media, list) and "url" in media[0]:
                        image_url = media[0]["url"]
                        break
                if not image_url and "enclosures" in entry:
                    for enc in entry.enclosures:
                        if enc.get("type", "").startswith("image/"):
                            image_url = enc.get("href", "")
                            break

                new_items.append({
                    "title":     title,
                    "summary":   summary[:800],
                    "url":       url,
                    "image_url": image_url,
                    "source":    feed.feed.get("title", feed_url),
                })

        except Exception as e:
            log.warning(f"⚠️ فشل جلب {feed_url}: {e}")

    log.info(f"✅ وجدنا {len(new_items)} خبر جديد متعلق بالذكاء الاصطناعي")
    return new_items

# ──────────────────────────────────────────────
# 3. صياغة التغريدة بـ OpenRouter
# ──────────────────────────────────────────────

def craft_tweet_with_gemini(title: str, summary: str, source: str) -> str | None:
    """يستخدم OpenRouter لصياغة تغريدة بشرية وعفوية."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        log.error("❌ مفتاح GEMINI_API_KEY (OpenRouter) غير موجود!")
        return None

    system_prompt = (
        "أنت تمثلني شخصياً على حسابي في تويتر. "
        "أنا مؤسس تقني سعودي مهتم بالذكاء الاصطناعي. "
        "اكتب تغريدة عن هذا الخبر بأسلوبي العفوي والشخصي (لهجة بيضاء). "
        "ضع رأيك التقني بإيجاز وفي الصميم "
        "(مثلاً قارن الخبر بمنافسيه، أو تحدث عن تأثيره). "
        f"أقصى حد {TWEET_CHAR_LIMIT} حرف. "
        "يجب أن تبدو التغريدة وكأن إنساناً كتبها من هاتفه الآن. "
        "لا تستخدم فصحى معقدة، ولا تضع هاشتاقات مزعجة أبداً، "
        "استخدم إيموجي خفيف ومناسب جداً (إيموجي واحد أو اثنان كحد أقصى). "
        "لا تذكر 'تغريدة' أو 'نشر' في النص. "
        "لا تضع رابطاً في النص (سيُضاف تلقائياً). "
        "أعطني فقط نص التغريدة الجاهز بدون أي تعليق أو شرح."
    )

    user_prompt = (
        f"الخبر: {title}\n\n"
        f"التفاصيل: {summary}\n\n"
        f"المصدر: {source}"
    )

    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "google/gemini-flash-1.5",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.85,
                "max_tokens": 300
            },
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        tweet_text = data['choices'][0]['message']['content'].strip()

        tweet_text = tweet_text.strip('"').strip("'").strip()

        if len(tweet_text) > TWEET_CHAR_LIMIT:
            tweet_text = tweet_text[:TWEET_CHAR_LIMIT - 3] + "..."

        log.info(f"✍️  التغريدة: {tweet_text}")
        return tweet_text

    except Exception as e:
        log.error(f"❌ خطأ في OpenRouter: {e}")
        if 'response' in locals() and hasattr(response, 'text'):
            log.error(f"تفاصيل الخطأ من السيرفر: {response.text}")
        return None

# ──────────────────────────────────────────────
# 4. رفع الصورة وإرسال التغريدة
# ──────────────────────────────────────────────

def download_image(image_url: str) -> bytes | None:
    """تحميل الصورة كـ bytes."""
    if not image_url:
        return None
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(image_url, headers=headers, timeout=20)
        if resp.status_code == 200 and "image" in resp.headers.get("content-type", ""):
            return resp.content
        log.warning(f"⚠️ فشل تحميل الصورة: {resp.status_code}")
    except Exception as e:
        log.warning(f"⚠️ خطأ في تحميل الصورة: {e}")
    return None

def post_tweet(tweet_text: str, news_url: str, image_data: bytes | None) -> bool:
    """ينشر التغريدة عبر Tweepy."""
    api_key     = os.environ.get("TWITTER_API_KEY", "")
    api_secret  = os.environ.get("TWITTER_API_SECRET", "")
    acc_token   = os.environ.get("TWITTER_ACCESS_TOKEN", "")
    acc_secret  = os.environ.get("TWITTER_ACCESS_SECRET", "")
    bearer      = os.environ.get("TWITTER_BEARER_TOKEN", "")

    if not all([api_key, api_secret, acc_token, acc_secret]):
        log.error("❌ مفاتيح تويتر ناقصة!")
        return False

    try:
        auth_v1 = tweepy.OAuth1UserHandler(api_key, api_secret, acc_token, acc_secret)
        api_v1  = tweepy.API(auth_v1)

        media_ids = []
        if image_data:
            try:
                media = api_v1.media_upload(
                    filename="news_image.jpg",
                    file=BytesIO(image_data),
                )
                media_ids.append(media.media_id)
                log.info(f"🖼️  تم رفع الصورة: media_id={media.media_id}")
            except Exception as img_err:
                log.warning(f"⚠️ فشل رفع الصورة، سيُنشر بدون صورة: {img_err}")

        client_v2 = tweepy.Client(
            bearer_token       = bearer,
            consumer_key       = api_key,
            consumer_secret    = api_secret,
            access_token       = acc_token,
            access_token_secret= acc_secret,
        )

        full_text = f"{tweet_text}\n\n{news_url}"
        payload = {"text": full_text}
        
        if media_ids:
            payload["media"] = {"media_ids": [str(mid) for mid in media_ids]}

        response = client_v2.create_tweet(**payload)

        if response.data:
            tweet_id = response.data["id"]
            log.info(f"🎉 تم النشر! Tweet ID: {tweet_id}")
            return True
        else:
            log.error(f"❌ لم يُنشر: {response}")
            return False

    except tweepy.errors.TweepyException as e:
        log.error(f"❌ خطأ في Tweepy: {e}")
        return False

# ──────────────────────────────────────────────
# 5. الوظيفة الرئيسية
# ──────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("🚀 بدء تشغيل Twitter AI Bot (OpenRouter Edition)")
    log.info(f"⏰ الوقت: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    log.info("=" * 60)

    posted_urls = load_posted_urls()
    news_items = fetch_news(posted_urls)
    
    if not news_items:
        log.info("😴 لا توجد أخبار جديدة. سنحاول لاحقاً.")
        return

    random.shuffle(news_items)
    item = news_items[0]

    log.info(f"\n📰 الخبر المختار:")
    log.info(f"   العنوان : {item['title']}")
    log.info(f"   المصدر  : {item['source']}")
    log.info(f"   الرابط  : {item['url']}")

    tweet_text = craft_tweet_with_gemini(
        title   = item["title"],
        summary = item["summary"],
        source  = item["source"],
    )
    
    if not tweet_text:
        log.error("❌ فشلت صياغة التغريدة. إيقاف.")
        return

    image_data = download_image(item.get("image_url"))

    delay = random.randint(5, 20)
    log.info(f"⏳ انتظار {delay} ثانية قبل النشر...")
    time.sleep(delay)

    success = post_tweet(
        tweet_text = tweet_text,
        news_url   = item["url"],
        image_data = image_data,
    )

    if success:
        save_posted_url(item["url"])
        log.info("✅ انتهى بنجاح! سيقوم GitHub Actions بحفظ الملف.")
    else:
        log.warning("⚠️ لم يُنشر. لم يتم تحديث الذاكرة.")

if __name__ == "__main__":
    main()
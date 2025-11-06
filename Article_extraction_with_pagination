import json
import random
import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from newspaper import Article
import spacy
import re
from urllib.parse import quote, urlparse
from datetime import datetime
from io import BytesIO
import time
from dateparser.search import search_dates
import dateparser

# Load spaCy model
nlp = spacy.load("en_core_web_sm")

# ---------------------- CONFIG ----------------------
CATEGORY_KEYWORDS = {
    "Press Release": ["press release", "announced", "unveiled", "launched"],
    "Jury": ["jury", "judge", "jury member", "jury panel", "jury appointment"],
    "Interviews": ["interview with", "exclusive interview", "spoke to", "conversation with"],
    "Speaking Opportunity": ["keynote", "fireside chat", "panel discussion", "session speaker", "speaker at"],
    "Article Commentary": ["quoted", "commented", "shared", "according to", "said", "opinion"],
    "Brief Mentions": ["congratulations", "appointed", "wins", "promotion", "award", "linkedin update"],
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Mozilla/5.0 (X11; Linux x86_64)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0)",
]

HEADERS = {"User-Agent": random.choice(USER_AGENTS)}

# ---------------------- HELPERS ----------------------

def _make_naive(dt):
    if isinstance(dt, datetime) and dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def extract_date_from_meta(html):
    soup = BeautifulSoup(html, "html.parser")
    meta_props = [
        "article:published_time", "og:published_time", "datePublished",
        "publish_date", "pubdate", "publishdate", "date", "article:published",
        "parsely-pub-date", "dc.date", "dc.date.issued", "date"
    ]
    for prop in meta_props:
        tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop}) or soup.find("meta", itemprop=prop)
        if tag:
            content = tag.get("content")
            if content:
                date_obj = dateparser.parse(content)
                if date_obj:
                    return _make_naive(date_obj)
    return None


def extract_date_from_text(text):
    if not text:
        return None
    dates = search_dates(text, languages=['en'], settings={'PREFER_DATES_FROM': 'past'})
    if dates:
        now = datetime.now()
        for _, date_obj in dates:
            date_obj = _make_naive(date_obj)
            if date_obj and date_obj.year >= 2000 and date_obj.date() <= now.date():
                return date_obj
    return None


def extract_site_specific_date(html, url):
    soup = BeautifulSoup(html, "lxml")
    domain = urlparse(url).netloc.lower()

    def get_text_or_content(tag):
        return tag.get("content") if tag and tag.has_attr("content") else tag.get_text(strip=True) if tag else None

    # Example: exchange4media, mumbrella, etc.
    if "exchange4media.com" in domain:
        tag = soup.find("span", class_="storyDate") or soup.find("div", class_="storyDate") or soup.find("div", class_="date_box")
        if tag:
            text = get_text_or_content(tag)
            if text:
                return _make_naive(dateparser.parse(text))

    if "mumbrella.com.au" in domain:
        tag = soup.find("meta", attrs={"name": "parsely-pub-date"}) or soup.find("meta", attrs={"name": "date"})
        if tag and tag.get("content"):
            return _make_naive(dateparser.parse(tag["content"]))

    # Generic fallback: JSON-LD, <time>, <span class="date">, etc.
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            obj = json.loads(s.string or "{}")
            if isinstance(obj, dict):
                date_val = obj.get("datePublished") or obj.get("uploadDate")
                if date_val:
                    return _make_naive(dateparser.parse(date_val))
        except:
            continue

    common_tags = soup.find_all(["time", "span", "div"], class_=["entry-date", "date", "story-date", "byline", "published", "post-date"])
    for tag in common_tags:
        text = get_text_or_content(tag)
        if text:
            date_obj = dateparser.parse(text)
            if date_obj:
                return _make_naive(date_obj)
    return None


def extract_date_from_url(url):
    match = re.search(r'(\d{4}[-/]\d{2}[-/]\d{2})|(\d{8})|(\d{14})', url)
    if match:
        try:
            val = match.group(1) or match.group(2) or match.group(3)
            if len(val) == 14:
                return _make_naive(datetime.strptime(val, "%Y%m%d%H%M%S"))
            else:
                return _make_naive(dateparser.parse(val))
        except:
            return None
    return None


# ---------------------- BING PAGINATION SEARCH ----------------------

def search_urls_bing_news(query, max_pages=20, delay=(2, 4)):
    """
    Fetches Bing News results across multiple pages until no new results are found.
    """
    all_results = []
    seen_urls = set()
    page = 0

    while page < max_pages:
        offset = page * 10  # Bing paginates every 10 results
        search_url = f"https://www.bing.com/news/search?q={quote(query)}&first={offset}"
        try:
            headers = {"User-Agent": random.choice(USER_AGENTS)}
            res = requests.get(search_url, headers=headers, timeout=10)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "html.parser")
            items = soup.select("a.title")
            if not items:
                break  # Stop when no new results
            for item in items:
                title = item.get_text(strip=True)
                url = item.get("href")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_results.append({"title": title, "url": url})
            page += 1
            time.sleep(random.uniform(*delay))  # polite delay
        except Exception as e:
            print(f"⚠️ Error on page {page}: {e}")
            break
    return all_results


# ---------------------- ARTICLE PROCESSING ----------------------

def fetch_full_text_and_summary(url):
    full_text, pub_date, summary = None, None, None
    html = None
    try:
        article = Article(url)
        article.download()
        article.parse()
        article.nlp()
        full_text = article.text.strip()
        summary = article.summary
        html = article.html
        pub_date = _make_naive(article.publish_date)
    except:
        try:
            res = requests.get(url, headers=HEADERS, timeout=15)
            res.raise_for_status()
            html = res.text
            soup = BeautifulSoup(html, "html.parser")
            paragraphs = soup.find_all("p")
            full_text = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
        except:
            return None, None, None

    if not pub_date and html:
        pub_date = extract_date_from_meta(html)
    if not pub_date and html:
        pub_date = extract_site_specific_date(html, url)
    if not pub_date:
        pub_date = extract_date_from_url(url)
    if not pub_date and full_text:
        pub_date = extract_date_from_text(full_text)

    return full_text, pub_date, summary


def categorize_article(text: str) -> str:
    text = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                return category
    return "Brief Mentions"


def extract_named_entities(text):
    doc = nlp(text)
    return [ent.text for ent in doc.ents if ent.label_ in ("PERSON", "ORG", "GPE")]


def extract_event_date(text: str) -> str:
    dates = search_dates(text, settings={"PREFER_DATES_FROM": "past"})
    if dates:
        return dates[0][1].strftime('%Y-%m-%d')
    return "Not Mentioned"


def contains_keywords(text, keywords):
    text = text.lower()
    return any(k.lower() in text for k in keywords)


# ---------------------- MAIN TRACKER ----------------------

def run_tracker(keywords, leaders, start_date, end_date):
    final_data = []
    failed_articles = []
    all_keywords = list(set(keywords + leaders))

    for keyword in keywords:
        search_results = search_urls_bing_news(keyword)
        for result in search_results:
            url = result["url"]
            title = result["title"]
            pub_date_from_url = extract_date_from_url(url)

            full_text, pub_date, summary = fetch_full_text_and_summary(url)

            if pub_date_from_url and not (start_date <= pub_date_from_url.date() <= end_date):
                continue
            if pub_date and not (start_date <= pub_date.date() <= end_date):
                continue

            if full_text and contains_keywords(full_text, all_keywords):
                category = categorize_article(full_text)
                named_entities = extract_named_entities(full_text)
                event_date = extract_event_date(full_text)

                final_data.append({
                    "Title": title,
                    "URL": url,
                    "Published Date": pub_date.strftime('%Y-%m-%d') if pub_date else "Unknown",
                    "Event Date": event_date,
                    "Leader Mentioned": ", ".join([l for l in leaders if l.lower() in full_text.lower()]) or "Not Mentioned",
                    "Category": category,
                    "Named Entities": ", ".join(named_entities),
                    "Summary": summary or full_text[:500] + "..." if full_text else "No summary available."
                })
            else:
                final_date = pub_date or pub_date_from_url
                failed_articles.append({
                    "Title": title,
                    "URL": url,
                    "Published Date": final_date.strftime('%Y-%m-%d') if final_date else "Unknown"
                })

    return pd.DataFrame(final_data), pd.DataFrame(failed_articles)


# ---------------------- STREAMLIT UI ----------------------

st.set_page_config(page_title="PR & Media Tracker", layout="wide")
st.title("📊 PR & Media Article Tracker (Auto-Pagination Enabled)")

keywords_input = st.text_input("🔍 Enter Keywords (comma-separated)", "OMG India, Omnicom Media Group, OMD India")
leaders_input = st.text_input("👤 Enter Leader Names (optional)", "Priti Murthy, Kartik Sharma")

start_date = st.date_input("📅 Start Date")
end_date = st.date_input("📅 End Date")

keywords = [k.strip() for k in keywords_input.split(",") if k.strip()]
leaders = [l.strip() for l in leaders_input.split(",") if l.strip()]

if st.button("Search Articles"):
    if not keywords:
        st.warning("Please enter at least one keyword.")
    elif not start_date or not end_date:
        st.warning("Please select both start and end dates.")
    else:
        with st.spinner("🔎 Searching and analyzing articles across multiple pages..."):
            df, errors_df = run_tracker(keywords, leaders, start_date, end_date)

        if not df.empty:
            st.success(f"✅ Found {len(df)} relevant articles across multiple pages.")
            st.dataframe(df, use_container_width=True)

            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name="Media Tracker")
                errors_df.to_excel(writer, index=False, sheet_name="Access Issues")
            output.seek(0)

            st.download_button(
                label="📥 Download Excel Report",
                data=output,
                file_name="PR_Media_Report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("⚠️ No relevant articles found after pagination.")

        if not errors_df.empty:
            st.info(f"ℹ️ {len(errors_df)} articles could not be accessed. Dates extracted wherever possible:")
            st.dataframe(errors_df, use_container_width=True)

            errors_output = BytesIO()
            with pd.ExcelWriter(errors_output, engine='openpyxl') as writer:
                errors_df.to_excel(writer, index=False, sheet_name="Access Issues")
            errors_output.seek(0)

            st.download_button(
                label="📥 Download Unaccessible Articles",
                data=errors_output,
                file_name="Unaccessible_Articles.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

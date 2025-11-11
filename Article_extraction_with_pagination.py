# src/streamlit_app.py
import json
import random
import logging
import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from newspaper import Article
import spacy
from spacy.util import is_package
from spacy.cli import download as spacy_download
import re
from urllib.parse import quote, urlparse
from datetime import datetime
from io import BytesIO
import time
from dateparser.search import search_dates
import dateparser
import nltk

# ------------------ small helpers for model/data downloads ------------------
def ensure_nltk_punkt():
    try:
        nltk.data.find("tokenizers/punkt")
    except LookupError:
        nltk.download("punkt")

def load_spacy_model(name="en_core_web_sm"):
    """Try to load a spaCy model; if missing, download it, else fallback to blank 'en'."""
    try:
        if is_package(name):
            return spacy.load(name)
        try:
            return spacy.load(name)
        except OSError:
            logging.info(f"spaCy model {name} not found — attempting runtime download.")
            try:
                spacy_download(name)
            except Exception as e:
                logging.exception("Runtime spaCy download failed: %s", e)
            return spacy.load(name)
    except Exception as e:
        logging.exception("spaCy model load failed entirely, falling back to blank pipeline: %s", e)
        return spacy.blank("en")

# Ensure small external data is present
ensure_nltk_punkt()
nlp = load_spacy_model("en_core_web_sm")

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
    "Mozilla/5.0 (X11; Linux x86_64)"
]
HEADERS = {"User-Agent": random.choice(USER_AGENTS)}

# ---------------------- HELPERS ----------------------
def _make_naive(dt):
    if isinstance(dt, datetime) and dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt

# (Keep your date-extraction helpers exactly as before)
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
    except Exception:
        try:
            res = requests.get(url, headers=HEADERS, timeout=15)
            res.raise_for_status()
            html = res.text
            soup = BeautifulSoup(html, "html.parser")
            paragraphs = soup.find_all("p")
            full_text = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
        except Exception:
            return None, None, None

    if not pub_date and html:
        pub_date = extract_date_from_meta(html)
    if not pub_date and full_text:
        pub_date = extract_date_from_text(full_text)
    if not pub_date:
        pub_date = extract_date_from_url(url)

    return full_text, pub_date, summary

def categorize_article(text: str) -> str:
    text = (text or "").lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                return category
    return "Brief Mentions"

def extract_named_entities(text):
    if not text:
        return []
    doc = nlp(text)
    return [ent.text for ent in doc.ents if ent.label_ in ("PERSON", "ORG", "GPE")]

def extract_event_date(text: str) -> str:
    dates = search_dates(text, settings={"PREFER_DATES_FROM": "past"})
    if dates:
        return dates[0][1].strftime('%Y-%m-%d')
    return "Not Mentioned"

def contains_keywords(text, keywords):
    text = (text or "").lower()
    return any(k.lower() in text for k in keywords)

# Main tracker (same as your version)
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
                    "Summary": summary or (full_text[:500] + "...") if full_text else "No summary available."
                })
            else:
                final_date = pub_date or pub_date_from_url
                failed_articles.append({
                    "Title": title,
                    "URL": url,
                    "Published Date": final_date.strftime('%Y-%m-%d') if final_date else "Unknown"
                })

    return pd.DataFrame(final_data), pd.DataFrame(failed_articles)

# BING pagination search function (your function — ensure you include it)
def search_urls_bing_news(query, max_pages=5, delay=(2, 4)):
    all_results = []
    seen_urls = set()
    page = 0
    while page < max_pages:
        offset = page * 10
        search_url = f"https://www.bing.com/news/search?q={quote(query)}&first={offset}"
        try:
            headers = {"User-Agent": random.choice(USER_AGENTS)}
            res = requests.get(search_url, headers=headers, timeout=10)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "html.parser")
            items = soup.select("a.title")
            if not items:
                break
            for item in items:
                title = item.get_text(strip=True)
                url = item.get("href")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_results.append({"title": title, "url": url})
            page += 1
            time.sleep(random.uniform(*delay))
        except Exception as e:
            logging.exception("Error while fetching Bing page: %s", e)
            break
    return all_results

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
            st.success(f"✅ Found {len(df)} relevant articles.")
            st.dataframe(df, use_container_width=True)

            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name="Media Tracker")
                errors_df.to_excel(writer, index=False, sheet_name="Access Issues")
            output.seek(0)

            st.download_button("📥 Download Excel Report", data=output, file_name="PR_Media_Report.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            st.warning("⚠️ No relevant articles found after pagination.")

        if not errors_df.empty:
            st.info(f"ℹ️ {len(errors_df)} articles could not be accessed.")
            st.dataframe(errors_df, use_container_width=True)

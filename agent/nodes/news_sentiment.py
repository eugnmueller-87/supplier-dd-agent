import os
from datetime import datetime, timedelta
import httpx
from agent.state import DDState

NEWSAPI_URL = "https://newsapi.ai/api/v1/article/getArticles"

# Hard negative keywords — high severity regardless of sentiment score
HIGH_SEVERITY_KEYWORDS = [
    "sanction", "forced labour", "child labour", "money laundering", "bribery",
    "Sanktion", "Zwangsarbeit", "Kinderarbeit", "Geldwäsche", "Bestechung",
    "fraud", "corruption", "arrest", "indictment",
    "Betrug", "Korruption", "Verhaftung", "Anklage",
]


def _flag_severity(title: str, body: str, sentiment: float | None) -> str:
    combined = (title + " " + body).lower()
    if any(kw.lower() in combined for kw in HIGH_SEVERITY_KEYWORDS):
        return "high"
    # newsapi.ai sentiment: negative < 0, neutral ~0, positive > 0
    if sentiment is not None and sentiment < -0.1:
        return "medium"
    return "none"


def _fetch(query: str, days: int = 90, count: int = 10) -> list[dict]:
    from_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    body = {
        "action": "getArticles",
        "keyword": query,
        "dateStart": from_date,
        "articlesCount": count,
        "articlesSortBy": "rel",
        "resultType": "articles",
        "apiKey": os.environ["NEWSAPI_KEY"],
    }
    r = httpx.post(NEWSAPI_URL, json=body, timeout=15)
    r.raise_for_status()
    return r.json().get("articles", {}).get("results", [])


def news_sentiment(state: DDState) -> dict:
    company = state["company_name"]
    hermes_tracked = state.get("hermes_tracked", False)
    hermes_signal_count = state.get("hermes_intel", {}).get("signal_count", 0)

    if hermes_tracked and hermes_signal_count > 10:
        return {
            "news_results": {
                "company": company,
                "skipped": True,
                "reason": f"Hermes has {hermes_signal_count} signals — using Hermes intelligence instead",
                "articles": [],
                "negative_count": 0,
                "high_severity_count": 0,
                "sentiment": "deferred_to_hermes",
            }
        }

    articles = []
    errors = []

    queries = [
        f"{company} risk fraud lawsuit sanction investigation",
        f"{company} supply chain human rights Lieferkette",
    ]

    for query in queries:
        try:
            raw = _fetch(query, count=8)
            for a in raw:
                title = a.get("title", "") or ""
                body = a.get("body", "") or ""
                sentiment_score = a.get("sentiment")
                severity = _flag_severity(title, body[:500], sentiment_score)
                articles.append({
                    "title": title,
                    "source": (a.get("source") or {}).get("title", ""),
                    "url": a.get("url", ""),
                    "published_at": (a.get("dateTime") or "")[:10],
                    "sentiment_score": round(sentiment_score, 3) if sentiment_score is not None else None,
                    "negative_flag": severity != "none",
                    "severity": severity,
                })
        except Exception as e:
            errors.append(str(e))

    # Deduplicate by URL
    seen: set[str] = set()
    unique = []
    for a in articles:
        if a["url"] not in seen:
            seen.add(a["url"])
            unique.append(a)

    negative_count = sum(1 for a in unique if a["negative_flag"])
    high_severity_count = sum(1 for a in unique if a["severity"] == "high")

    if high_severity_count > 0:
        sentiment = "negative_high"
    elif negative_count > 2:
        sentiment = "negative_medium"
    elif negative_count > 0:
        sentiment = "negative_low"
    else:
        sentiment = "neutral"

    return {
        "news_results": {
            "company": company,
            "skipped": False,
            "total_articles": len(unique),
            "negative_count": negative_count,
            "high_severity_count": high_severity_count,
            "sentiment": sentiment,
            "articles": unique,
            "errors": errors,
        }
    }

import os
from datetime import datetime, timedelta
import httpx
from agent.state import DDState

NEWSAPI_URL = "https://newsapi.org/v2/everything"

NEGATIVE_KEYWORDS = [
    # English
    "fraud", "lawsuit", "fined", "penalty", "bribery", "corruption", "bankrupt",
    "insolvency", "breach", "violation", "recall", "investigation", "scandal",
    "money laundering", "sanction", "forced labour", "child labour", "arrest",
    # German
    "Betrug", "Klage", "Bußgeld", "Strafe", "Bestechung", "Korruption",
    "Insolvenz", "Verstoß", "Ermittlung", "Rückruf", "Skandal",
    "Geldwäsche", "Sanktion", "Zwangsarbeit", "Kinderarbeit", "Verhaftung",
]

SEVERITY_HIGH = {
    "sanction", "forced labour", "child labour", "money laundering", "bribery",
    "Sanktion", "Zwangsarbeit", "Kinderarbeit", "Geldwäsche", "Bestechung",
}


def _flag_negative(text: str) -> bool:
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in NEGATIVE_KEYWORDS)


def _flag_severity(text: str) -> str:
    text_lower = text.lower()
    if any(kw.lower() in text_lower for kw in SEVERITY_HIGH):
        return "high"
    if _flag_negative(text):
        return "medium"
    return "none"


def _fetch_newsapi(query: str, days: int = 90, page_size: int = 10) -> list[dict]:
    api_key = os.environ["NEWSAPI_KEY"]
    from_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    r = httpx.get(
        NEWSAPI_URL,
        params={
            "q": query,
            "from": from_date,
            "sortBy": "relevancy",
            "pageSize": page_size,
            "apiKey": api_key,
            "language": "en",
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json().get("articles", [])


def news_sentiment(state: DDState) -> dict:
    company = state["company_name"]
    hermes_tracked = state.get("hermes_tracked", False)
    hermes_signal_count = state.get("hermes_intel", {}).get("signal_count", 0)

    # Skip NewsAPI if Hermes already has strong coverage (>10 signals)
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

    # EN query — general risk signals
    queries = [
        f'"{company}" risk OR fraud OR lawsuit OR sanction OR investigation',
        f'"{company}" supply chain OR supplier OR procurement',
    ]

    for query in queries:
        try:
            raw = _fetch_newsapi(query, page_size=5)
            for a in raw:
                title = a.get("title", "") or ""
                description = a.get("description", "") or ""
                combined = f"{title} {description}"
                severity = _flag_severity(combined)
                articles.append({
                    "title": title,
                    "source": a.get("source", {}).get("name", ""),
                    "url": a.get("url", ""),
                    "published_at": a.get("publishedAt", "")[:10],
                    "description": description[:300],
                    "negative_flag": severity != "none",
                    "severity": severity,
                })
        except Exception as e:
            errors.append(str(e))

    # Deduplicate by URL
    seen = set()
    unique_articles = []
    for a in articles:
        if a["url"] not in seen:
            seen.add(a["url"])
            unique_articles.append(a)

    negative_count = sum(1 for a in unique_articles if a["negative_flag"])
    high_severity_count = sum(1 for a in unique_articles if a["severity"] == "high")

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
            "total_articles": len(unique_articles),
            "negative_count": negative_count,
            "high_severity_count": high_severity_count,
            "sentiment": sentiment,
            "articles": unique_articles,
            "errors": errors,
        }
    }

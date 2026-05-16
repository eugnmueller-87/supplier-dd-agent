import os
import httpx
from agent.state import DDState

OPENSANCTIONS_URL = "https://api.opensanctions.org/search/default"

# Datasets we care about most for EU/DE procurement compliance
PRIORITY_DATASETS = {
    "us_ofac_sdn",       # US OFAC Specially Designated Nationals
    "eu_fsf",            # EU Financial Sanctions (consolidated list)
    "un_sc_sanctions",   # UN Security Council sanctions
    "gb_hmt_sanctions",  # UK HM Treasury
    "eu_eeas_sanctions", # EU External Action Service
    "de_bafa_sanctions", # German BAFA export control
    "interpol_red_notices",
}


def sanctions_check(state: DDState) -> dict:
    company = state["company_name"]
    api_key = os.environ.get("OPENSANCTIONS_API_KEY", "")

    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"ApiKey {api_key}"

    try:
        r = httpx.get(
            OPENSANCTIONS_URL,
            headers=headers,
            params={"q": company, "limit": 10, "fuzzy": "false"},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPStatusError as e:
        # Treat API errors as inconclusive — safe default requires manual review
        return {
            "sanctions_result": {
                "company": company,
                "status": "inconclusive",
                "error": f"API error {e.response.status_code} — manual review required",
                "is_sanctioned": None,
                "matches": [],
                "datasets_matched": [],
                "priority_hit": False,
            }
        }
    except Exception as e:
        return {
            "sanctions_result": {
                "company": company,
                "status": "inconclusive",
                "error": str(e),
                "is_sanctioned": None,
                "matches": [],
                "datasets_matched": [],
                "priority_hit": False,
            }
        }

    results = data.get("results", [])

    # Filter to high-confidence matches only (score >= 0.85)
    strong_matches = [r for r in results if r.get("score", 0) >= 0.85]

    if not strong_matches:
        return {
            "sanctions_result": {
                "company": company,
                "status": "ok",
                "is_sanctioned": False,
                "matches": [],
                "datasets_matched": [],
                "priority_hit": False,
                "total_results": len(results),
            }
        }

    # Extract dataset and entity details from matches
    matched_datasets = set()
    match_summaries = []

    for match in strong_matches:
        datasets = match.get("datasets", [])
        matched_datasets.update(datasets)
        match_summaries.append({
            "name": match.get("caption", ""),
            "score": round(match.get("score", 0), 3),
            "schema": match.get("schema", ""),
            "datasets": datasets,
            "countries": match.get("properties", {}).get("country", []),
            "addresses": match.get("properties", {}).get("address", [])[:2],
            "topics": match.get("properties", {}).get("topics", []),
        })

    priority_hit = bool(matched_datasets & PRIORITY_DATASETS)

    return {
        "sanctions_result": {
            "company": company,
            "status": "ok",
            "is_sanctioned": True,
            "matches": match_summaries,
            "datasets_matched": sorted(matched_datasets),
            "priority_hit": priority_hit,  # True = OFAC/EU/UN/UK hit — highest severity
            "total_results": len(results),
        }
    }

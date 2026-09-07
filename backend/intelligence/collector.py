import json
import os
from pathlib import Path

from backend.intelligence.sources import (
    collect_discovery,
    gdelt_search,
    rss_search,
)


BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_FILE = BASE_DIR / "config" / "influencers.json"


DEFAULT_RSS_FEEDS = [
    {
        "name": "SEC",
        "url": "https://www.sec.gov/news/pressreleases.rss",
    },
    {
        "name": "PR Newswire",
        "url": "https://www.prnewswire.com/rss/news-releases-list.rss",
    },
    {
        "name": "GlobeNewswire",
        "url": "https://www.globenewswire.com/RssFeed/subjectcode/20-Mergers%20and%20Acquisitions/feedTitle/Mergers%20and%20Acquisitions",
    },
]


GLOBAL_TOPICS = [
    "company investment financing",
    "distressed company investor",
    "company bankruptcy investor",
    "company turnaround investment",
    "major contract company shares",
    "acquisition takeover rumor company",
    "strategic partnership company stock",
    "insider buying company shares",
    "new institutional investor stock",
    "activist investor company",
    "small company breakthrough",
    "small cap catalyst",
    "biotech breakthrough company",
    "technology breakthrough company",
    "defense contract company",
    "energy discovery company",
    "AI company contract",
    "company debt restructuring",
    "company capital raise

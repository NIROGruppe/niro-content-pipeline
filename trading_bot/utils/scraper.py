"""
Scrapers for Twitter, Reddit, and RSS feeds.
"""
import os
import requests
from datetime import datetime


def search_twitter(query: str, max_results: int = 20, bearer_token: str = "") -> list:
    """Search Twitter/X via API v2."""
    if not bearer_token:
        return []
    try:
        headers = {"Authorization": f"Bearer {bearer_token}"}
        resp = requests.get(
            "https://api.twitter.com/2/tweets/search/recent",
            headers=headers,
            params={
                "query": f"{query} -is:retweet lang:en",
                "max_results": min(max_results, 100),
                "tweet.fields": "created_at,public_metrics,text",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        tweets = []
        for t in data.get("data", []):
            metrics = t.get("public_metrics", {})
            tweets.append({
                "text": t.get("text", ""),
                "created_at": t.get("created_at", ""),
                "likes": metrics.get("like_count", 0),
                "retweets": metrics.get("retweet_count", 0),
                "replies": metrics.get("reply_count", 0),
                "source": "twitter",
            })
        return tweets
    except Exception as e:
        return [{"error": str(e), "source": "twitter"}]


def search_reddit(query: str, max_results: int = 20, client_id: str = "", client_secret: str = "", user_agent: str = "TradingBot/1.0") -> list:
    """Search Reddit via API."""
    if not client_id or not client_secret:
        # Fallback: public JSON API
        return _search_reddit_public(query, max_results)
    try:
        # OAuth
        auth = requests.auth.HTTPBasicAuth(client_id, client_secret)
        token_resp = requests.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=auth,
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": user_agent},
            timeout=10,
        )
        token = token_resp.json().get("access_token", "")
        if not token:
            return _search_reddit_public(query, max_results)

        headers = {"Authorization": f"Bearer {token}", "User-Agent": user_agent}
        resp = requests.get(
            "https://oauth.reddit.com/search",
            headers=headers,
            params={"q": query, "limit": max_results, "sort": "relevance", "t": "week"},
            timeout=15,
        )
        resp.raise_for_status()
        posts = []
        for child in resp.json().get("data", {}).get("children", []):
            d = child.get("data", {})
            posts.append({
                "title": d.get("title", ""),
                "text": (d.get("selftext", "") or "")[:500],
                "score": d.get("score", 0),
                "num_comments": d.get("num_comments", 0),
                "subreddit": d.get("subreddit", ""),
                "url": f"https://reddit.com{d.get('permalink', '')}",
                "source": "reddit",
            })
        return posts
    except Exception as e:
        return _search_reddit_public(query, max_results)


def _search_reddit_public(query: str, max_results: int = 20) -> list:
    """Fallback Reddit search via public JSON API."""
    try:
        resp = requests.get(
            f"https://www.reddit.com/search.json",
            params={"q": query, "limit": max_results, "sort": "relevance", "t": "week"},
            headers={"User-Agent": "TradingBot/1.0"},
            timeout=15,
        )
        resp.raise_for_status()
        posts = []
        for child in resp.json().get("data", {}).get("children", []):
            d = child.get("data", {})
            posts.append({
                "title": d.get("title", ""),
                "text": (d.get("selftext", "") or "")[:500],
                "score": d.get("score", 0),
                "num_comments": d.get("num_comments", 0),
                "subreddit": d.get("subreddit", ""),
                "source": "reddit",
            })
        return posts
    except Exception as e:
        return [{"error": str(e), "source": "reddit"}]


def search_rss(query: str, feeds: list = None, max_results: int = 10) -> list:
    """Search RSS feeds for relevant news."""
    try:
        import feedparser
    except ImportError:
        return [{"error": "feedparser not installed", "source": "rss"}]

    if not feeds:
        feeds = [
            f"https://news.google.com/rss/search?q={query}&hl=en-US",
            f"https://www.reddit.com/search.rss?q={query}&sort=new",
        ]

    articles = []
    for feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:max_results]:
                articles.append({
                    "title": entry.get("title", ""),
                    "summary": (entry.get("summary", "") or "")[:500],
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "source": "rss",
                })
        except Exception:
            continue

    return articles[:max_results]

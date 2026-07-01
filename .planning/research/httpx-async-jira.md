# httpx Async Jira Client Research

## Why httpx
- The spec requires async Jira calls for the background sync
- Existing codebase uses synchronous `requests` for all HTTP
- `httpx` provides `AsyncClient` with `BasicAuth`, compatible with FastAPI async handlers
- No `jira` pip package for changelogs — must use raw REST

## Client Setup
```python
import httpx
from app import config

def _get_jira_auth():
    cfg = config.load_jira_config()
    return httpx.BasicAuth(cfg.get("email", ""), cfg.get("token", ""))

JIRA_BASE = "https://teltonika-telematics.atlassian.net"
HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}
```

## Search Endpoint
```python
async with httpx.AsyncClient(auth=auth, headers=HEADERS) as client:
    resp = await client.get(
        f"{JIRA_BASE}/rest/api/2/search",
        params={"jql": jql, "fields": "key", "maxResults": 1000}
    )
    resp.raise_for_status()
    data = resp.json()
    keys = [issue["key"] for issue in data["issues"]]
```

## Changelog Endpoint (Paginated)
```python
async def fetch_changelog(client, key):
    all_values = []
    start_at = 0
    while True:
        resp = await client.get(
            f"{JIRA_BASE}/rest/api/2/issue/{key}/changelog",
            params={"startAt": start_at, "maxResults": 100}
        )
        resp.raise_for_status()
        data = resp.json()
        all_values.extend(data["values"])
        if data["isLast"]:
            break
        start_at += len(data["values"])
    return all_values
```

## Concurrency Control
Use `asyncio.Semaphore` to limit concurrent Jira requests (avoid rate limiting):
```python
sem = asyncio.Semaphore(5)  # max 5 concurrent requests
async def fetch_with_limit(client, key):
    async with sem:
        return await fetch_changelog(client, key)
```

## Error Handling
- `httpx.HTTPStatusError` for 4xx/5xx
- `httpx.TimeoutException` for timeouts
- Retry with exponential backoff for transient failures
- Log errors but don't fail the entire sync for one issue

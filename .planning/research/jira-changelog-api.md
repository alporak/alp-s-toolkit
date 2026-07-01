# Jira Changelog API Research

## Endpoint
`GET /rest/api/2/issue/{issueKey}/changelog`

Returns full changelog for an issue. Unlike `expand=changelog` on the search endpoint (which truncates at 100 entries), this dedicated endpoint returns the complete history.

## Response Structure
```json
{
  "values": [
    {
      "id": "12345",
      "author": { "displayName": "...", "emailAddress": "..." },
      "created": "2024-01-15T10:30:00.000+0200",
      "items": [
        {
          "field": "status",
          "fieldtype": "jira",
          "from": "10008",
          "fromString": "In Development",
          "to": "10009",
          "toString": "Developed"
        }
      ]
    }
  ]
}
```

## Pagination
Changelog endpoint supports `startAt` and `maxResults` query params. Must paginate through all entries. Default page size is 100.

## Auth
Same as existing: HTTP Basic Auth with email + API token via `httpx.BasicAuth`.

## Rate Limiting
Jira Cloud has rate limits. Using async `httpx` allows controlled concurrency with `asyncio.Semaphore` or `httpx.Limits`.

## Key Fields for State Machine
- `items[].field == "status"` — filter to status changes only
- `items[].fromString` — previous status
- `items[].toString` — new status
- `author.displayName` / `author.emailAddress` — who made the change
- `created` — timestamp for transition

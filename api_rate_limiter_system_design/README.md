# API Rate Limiter — System Design + Runnable Starter

A small FastAPI + Redis implementation of a **distributed Token Bucket rate limiter**.
It is intended as a learning/demo project for the Week 5 System Design assignment.

## Features
- FastAPI endpoint protected by a Token Bucket limiter.
- Redis stores each client's bucket state, shared by all app instances.
- A Redis Lua script refills/checks/consumes tokens atomically.
- HTTP `429 Too Many Requests` when the bucket is empty.
- `Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and
  `X-RateLimit-Reset` response headers.
- Docker Compose starts Redis and the API.
- Unit tests for the algorithm that do not require Redis.

## Architecture

```text
Client
  |
  v
FastAPI / API Gateway layer
  |
  v
Rate-limit dependency
  |
  v
Redis (shared bucket state + atomic Lua script)
  |
  +---- no token ----> HTTP 429
  |
  v
Protected endpoint / backend logic
```

In a production architecture, the limiter can live in an API Gateway or a
shared middleware/service. All gateway or application instances use the same
Redis deployment so they enforce a common limit.

## Run with Docker

Requirements: Docker Desktop or Docker Engine with the Compose plugin.

```bash
docker compose up --build
```

Open:
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health
- Protected endpoint: http://localhost:8000/api/demo

Default policy: **5 requests per 60 seconds**, with a bucket capacity of 5.
Set a client identity with the `X-Client-ID` header. If omitted, the demo uses
the caller's IP address.

Try sending more than five requests within one minute. The API should return
HTTP 429 and a `Retry-After` header.

Stop:

```bash
docker compose down
```

To remove Redis demo data too:

```bash
docker compose down -v
```

## Run locally without Docker

1. Start a Redis server on `localhost:6379`.
2. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
```

3. Start the API:

```bash
uvicorn app.main:app --reload
```

## Configuration

Environment variables:

| Variable | Default | Meaning |
|---|---:|---|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `RATE_LIMIT_CAPACITY` | `5` | Maximum tokens in the bucket |
| `RATE_LIMIT_REFILL_RATE` | `5` | Tokens added per period |
| `RATE_LIMIT_PERIOD_SECONDS` | `60` | Refill period in seconds |
| `RATE_LIMIT_KEY_PREFIX` | `rate_limit` | Redis key prefix |

The refill rate is `RATE_LIMIT_REFILL_RATE / RATE_LIMIT_PERIOD_SECONDS`
tokens per second. For example, 5 tokens per 60 seconds.

## Algorithm comparison for the assignment

- **Token Bucket:** Tokens refill over time; each request consumes one token.
  It permits short bursts up to bucket capacity while controlling the long-term
  average rate. This project implements this approach.
- **Leaky Bucket:** Requests are queued and released at a steady rate. It
  smooths traffic but can add queueing delay; a full queue rejects requests.
- **Sliding Window:** Counts requests over a moving interval. It is accurate
  around time boundaries, but may require more Redis state/operations.

## Important design notes

- **Placement:** An API Gateway is a practical centralized location to reject
  excessive traffic before it reaches backend services. Service-level checks
  can also be added for sensitive operations.
- **Shared counters:** Redis is shared by all API instances. A per-process
  in-memory counter would not provide a global limit across multiple servers.
- **Consistency:** The Lua script runs atomically on Redis, so simultaneous
  requests cannot separately pass the check using the same old token balance.
- **Identity:** Production systems should use an authenticated user/API key,
  not trust an arbitrary client-supplied identity header.
- **Failure policy:** This demo fails closed if Redis is unavailable (the
  protected endpoint returns a server error). Production systems should
  explicitly choose fail-open or fail-closed based on risk.
- **Scaling:** Use Redis replication/Cluster and monitor latency, memory,
  rejected requests, and Redis availability. Redis Cluster key design must
  keep script keys compatible with the cluster's key-slot rules.

## Project structure

```text
api_rate_limiter_system_design/
├── app/
│   ├── __init__.py
│   ├── limiter.py
│   └── main.py
├── tests/
│   └── test_token_bucket.py
├── .env.example
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Test the pure token-bucket calculation

```bash
pip install -r requirements.txt
pytest -q
```

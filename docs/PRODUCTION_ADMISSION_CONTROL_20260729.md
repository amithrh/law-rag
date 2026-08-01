# Production Admission Control

**Status: implemented, independently reviewed, and still pending live deployment verification.**

The `/answer` and `/search` paths perform retrieval, reranking, and sometimes
LLM generation. They therefore need bounded admission rather than an
unlimited request fan-out.

## Runtime Contract

- Development uses an in-process controller with `ANSWER_MAX_CONCURRENT`
  active streams and at most `ANSWER_MAX_WAITERS` queued requests.
- A queued request waits for `ANSWER_ADMISSION_WAIT_MS`; after that it receives
  a `429` with `Retry-After: 1`. Rate-limit exhaustion receives `Retry-After: 60`.
- Production startup fails unless `ENVIRONMENT=production` has both
  `ANSWER_API_KEY` and `ANSWER_DISTRIBUTED_ADMISSION=true`.
- Production admission uses Redis sorted-set leases shared by API workers and
  replicas. Active leases have an expiry and a heartbeat; release is explicit
  and expiry is the crash-recovery path.
- Redis is also the production sliding-window rate-limit store. The API fails
  closed with `503` if the configured distributed admission backend is down.
- Redis is password-protected when `REDIS_PASSWORD` is non-empty; the API URL
  encodes that password before connecting. Rate limiting applies both the
  signed browser session budget and a larger trusted network/edge budget, so
  deleting a cookie cannot bypass the abuse boundary.
- The Next.js proxy forwards browser disconnect cancellation to the upstream
  SSE request. It also sends an opaque, HttpOnly browser session identifier so
  users behind one proxy receive separate session budgets. A larger network
  budget remains as a shared abuse backstop. The identifier is not legal or
  personal data and is only trusted when the shared API key is enabled.
- `X-Forwarded-For` and `X-Real-IP` are accepted only from IPs listed in
  `ANSWER_TRUSTED_PROXY_IPS`.

## Evidence

- `apps/api/tests/test_admission_control.py`: local queue, waiter cap,
  distributed Redis lease, Redis failure, and release contracts.
- `apps/api/tests/test_config.py`: body, concurrency, waiter, network rate-limit,
  and Redis URL-encoding bounds.
- The live five-request burst against the populated local API completed five
  HTTP 200 streams after the queue change. That is an operational smoke test,
  not a production quality sign-off.

## Remaining Gate

The real production Compose topology still needs a Redis-backed smoke test,
proxy disconnect test, and a fresh 500-query holdout with the final deployed
configuration. Until those pass together with the legal quality and safety
gates, the repository remains not production-ready.

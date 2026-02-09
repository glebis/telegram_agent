# Telegram Agent Architecture v2 - Unified Plan

A synthesis of two architectural reviews, optimized for a personal/small-group bot that can grow.

---

## Design Principles

1. **Queue-first, not process-first** - Webhook immediately enqueues, returns 200
2. **Per-chat isolation** - One "actor" per chat, no shared mutable state
3. **Security by default** - File proxy, API gateway, not afterthought fixes
4. **Observable** - Structured events, metrics, health endpoints
5. **Right-sized** - Redis Streams (not Kafka), SQLite WAL (not Postgres)

---

## Target Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              INGRESS LAYER                                  │
│                                                                             │
│  Telegram ──▶ POST /webhook ──▶ Validate ──▶ Redis Stream ──▶ Return 200   │
│                                    │                                        │
│                              Idempotency                                    │
│                              check (LRU)                                    │
└────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                           REDIS (Single Instance)                           │
│                                                                             │
│  Streams:                    Hashes:                    Sorted Sets:        │
│  ┌─────────────────┐        ┌─────────────────┐       ┌─────────────────┐  │
│  │ updates:{chat}  │        │ state:{chat}    │       │ buffer:{chat}   │  │
│  │ (partitioned)   │        │ - mode          │       │ (pending msgs)  │  │
│  └─────────────────┘        │ - session_id    │       └─────────────────┘  │
│  ┌─────────────────┐        │ - collect_items │       ┌─────────────────┐  │
│  │ tasks:claude    │        └─────────────────┘       │ idempotency     │  │
│  │ tasks:media     │        ┌─────────────────┐       │ (TTL 5min)      │  │
│  │ tasks:response  │        │ sessions:{id}   │       └─────────────────┘  │
│  └─────────────────┘        └─────────────────┘                            │
└────────────────────────────────────────────────────────────────────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
┌──────────────────────┐ ┌──────────────────────┐ ┌──────────────────────┐
│   CHAT CONSUMER      │ │   CLAUDE WORKER      │ │   MEDIA WORKER       │
│                      │ │                      │ │                      │
│ Per-chat processor:  │ │ ProcessPoolExecutor: │ │ ProcessPoolExecutor: │
│ - Read from stream   │ │ - Own event loop     │ │ - Downloads          │
│ - Buffer/sequence    │ │ - Claude SDK calls   │ │ - Transcription      │
│ - State machine      │ │ - Tool execution     │ │ - Image processing   │
│ - Dispatch to workers│ │                      │ │                      │
│                      │ │ Subprocess isolation │ │ Subprocess isolation │
└──────────────────────┘ └──────────────────────┘ └──────────────────────┘
                    │                │                │
                    └────────────────┼────────────────┘
                                     ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                           RESPONSE WORKER                                   │
│                                                                             │
│  - Rate-limited Telegram API calls                                         │
│  - Retry with exponential backoff                                          │
│  - Message chunking for long responses                                     │
│  - Reaction/edit coalescing                                                │
└────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                           SECURE SIDECARS                                   │
│                                                                             │
│  ┌─────────────────────┐    ┌─────────────────────┐                        │
│  │ File Proxy Service  │    │ Admin API Gateway   │                        │
│  │                     │    │                     │                        │
│  │ - Path validation   │    │ - API key auth      │                        │
│  │ - Allowlist only    │    │ - Audit logging     │                        │
│  │ - No .. traversal   │    │ - Rate limiting     │                        │
│  │ - Read-only vault   │    │ - Health endpoints  │                        │
│  └─────────────────────┘    └─────────────────────┘                        │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Design Decisions

### Why Redis Streams (not Celery/RabbitMQ/NATS)

| Factor | Redis Streams | Celery+Redis | NATS |
|--------|---------------|--------------|------|
| Operational complexity | Low (already have Redis) | Medium | High |
| Consumer groups | Yes | Via broker | Yes |
| Persistence | Yes (RDB/AOF) | Via broker | Yes |
| Learning curve | Low | Medium | High |
| Your scale needs | 10-100 msg/day | 10k+ msg/day | 100k+ msg/day |

**Decision:** Start with Redis Streams. If you outgrow it, migration to Celery is straightforward since both use Redis.

### Why Per-Chat Consumers (not global worker pool)

```python
# Bad: Global pool with locks
class MessageBuffer:
    async def add(self, chat_id, msg):
        async with self._lock:  # Contention!
            self._buffers[chat_id].append(msg)

# Good: Per-chat consumer, no locks needed
class ChatConsumer:
    def __init__(self, chat_id: int):
        self.chat_id = chat_id
        self.buffer = []  # Only this consumer touches it

    async def process(self, msg):
        self.buffer.append(msg)  # No lock needed
```

**Decision:** One consumer task per active chat. Idle chats have no consumer (lazy creation).

### Why File Proxy (not inline path validation)

Current code has path validation scattered across:
- `src/services/vault_service.py`
- `src/bot/handlers.py` (note deep links)
- `src/services/claude_subprocess.py` (_validate_cwd)

**Decision:** Single file service that ALL file operations go through:

```python
# file_proxy/main.py
from fastapi import FastAPI, HTTPException
from pathlib import Path

ALLOWED_ROOTS = [
    Path.home() / "Brains" / "brain",
    Path.home() / "ai_projects",
]

app = FastAPI()

@app.get("/read/{path:path}")
async def read_file(path: str, api_key: str = Header(...)):
    validate_api_key(api_key)
    resolved = Path(path).resolve()

    if not any(resolved.is_relative_to(root) for root in ALLOWED_ROOTS):
        raise HTTPException(403, "Path not in allowed roots")

    if not resolved.exists():
        raise HTTPException(404, "File not found")

    return FileResponse(resolved)
```

---

## Implementation Phases

### Phase 0: Observability Foundation (3 days)

**Goal:** See what's happening before changing anything.

```python
# src/core/telemetry.py
import structlog
from opentelemetry import trace
from prometheus_client import Counter, Histogram

# Structured logging
logger = structlog.get_logger()

# Metrics
MESSAGES_RECEIVED = Counter("messages_received_total", "Total messages", ["chat_id", "type"])
PROCESSING_TIME = Histogram("processing_seconds", "Processing time", ["handler"])
QUEUE_DEPTH = Gauge("queue_depth", "Pending messages", ["stream"])

# Add to every handler
async def handle_message(update: Update, context: Context):
    with trace.get_tracer(__name__).start_as_current_span("handle_message"):
        MESSAGES_RECEIVED.labels(chat_id=update.effective_chat.id, type="text").inc()

        with PROCESSING_TIME.labels(handler="text").time():
            # ... existing logic
```

**Deliverables:**
- [ ] Prometheus `/metrics` endpoint
- [ ] Structured JSON logging to stdout
- [ ] Trace IDs in logs
- [ ] Dashboard template (Grafana JSON)

### Phase 1: Redis State Migration (1 week)

**Goal:** Move in-memory state to Redis, enabling recovery after restarts.

```python
# src/services/state_store.py
import redis.asyncio as redis
from dataclasses import dataclass
import json

@dataclass
class ChatState:
    mode: str = "normal"
    claude_session_id: str | None = None
    collect_items: list = None

class RedisStateStore:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis = redis.from_url(redis_url)

    async def get_state(self, chat_id: int) -> ChatState:
        data = await self.redis.hgetall(f"state:{chat_id}")
        if not data:
            return ChatState()
        return ChatState(**{k.decode(): json.loads(v) for k, v in data.items()})

    async def set_mode(self, chat_id: int, mode: str) -> None:
        await self.redis.hset(f"state:{chat_id}", "mode", json.dumps(mode))

    async def get_claude_session(self, chat_id: int) -> str | None:
        val = await self.redis.hget(f"state:{chat_id}", "claude_session_id")
        return json.loads(val) if val else None
```

**Migration:**
```python
# Before
_claude_mode_cache: Dict[int, bool] = {}

# After
state_store = RedisStateStore()
await state_store.set_mode(chat_id, "claude")
```

**Deliverables:**
- [ ] `RedisStateStore` class
- [ ] Migrate `_claude_mode_cache`
- [ ] Migrate `_admin_cache`
- [ ] Migrate session ID lookups
- [ ] Tests with fakeredis

### Phase 2: Queue-First Ingress (1 week)

**Goal:** Webhook returns immediately after enqueueing.

```python
# src/api/webhook.py (new)
from fastapi import FastAPI, Request, HTTPException
import redis.asyncio as redis

app = FastAPI()
redis_client = redis.from_url("redis://localhost:6379")

# Idempotency cache
seen_updates: set = set()  # Or use Redis with TTL

@app.post("/webhook")
async def webhook(request: Request):
    # 1. Validate
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not hmac.compare_digest(secret, WEBHOOK_SECRET):
        raise HTTPException(401)

    body = await request.json()
    update_id = body.get("update_id")

    # 2. Dedupe
    if update_id in seen_updates:
        return {"status": "duplicate"}
    seen_updates.add(update_id)

    # 3. Enqueue (partitioned by chat_id)
    chat_id = extract_chat_id(body)
    await redis_client.xadd(
        f"updates:{chat_id}",
        {"payload": json.dumps(body)},
        maxlen=1000,  # Bounded stream
    )

    # 4. Return immediately
    return {"status": "queued"}
```

**Deliverables:**
- [ ] New `/webhook` endpoint with immediate enqueue
- [ ] Stream consumer that reads and processes
- [ ] Graceful switchover (dual-write period)
- [ ] Dead letter queue for failed processing

### Phase 3: Per-Chat Consumers (1 week)

**Goal:** Eliminate locks, guarantee ordering.

```python
# src/workers/chat_consumer.py
import asyncio
from typing import Dict

class ChatConsumerManager:
    """Manages per-chat consumer tasks."""

    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)
        self.consumers: Dict[int, asyncio.Task] = {}

    async def ensure_consumer(self, chat_id: int) -> None:
        """Start consumer for chat if not running."""
        if chat_id not in self.consumers or self.consumers[chat_id].done():
            self.consumers[chat_id] = asyncio.create_task(
                self._run_consumer(chat_id)
            )

    async def _run_consumer(self, chat_id: int) -> None:
        """Process messages for a single chat."""
        stream_key = f"updates:{chat_id}"
        last_id = "0"

        buffer = MessageBuffer(timeout=2.5)

        while True:
            # Read from stream (block for 5s)
            messages = await self.redis.xread(
                {stream_key: last_id},
                block=5000,
                count=10,
            )

            if not messages:
                # No messages for 5s, check if we should exit
                if buffer.is_empty() and await self._chat_is_idle(chat_id):
                    break
                continue

            for stream, entries in messages:
                for entry_id, data in entries:
                    last_id = entry_id
                    update = json.loads(data[b"payload"])

                    # Process through buffer/state machine
                    combined = await buffer.add(update)
                    if combined:
                        await self._process_combined(chat_id, combined)

                    # Acknowledge
                    await self.redis.xack(stream_key, "consumers", entry_id)
```

**Deliverables:**
- [ ] `ChatConsumerManager` class
- [ ] Lazy consumer creation on first message
- [ ] Consumer cleanup for idle chats
- [ ] Buffer logic moved into consumer (no locks)

### Phase 4: Worker Isolation (1 week)

**Goal:** Heavy work in separate processes, proper isolation.

```python
# src/workers/claude_worker.py
from concurrent.futures import ProcessPoolExecutor
import asyncio

# Process pool initialized once
executor = ProcessPoolExecutor(
    max_workers=2,
    initializer=init_worker,
)

def init_worker():
    """Initialize worker process."""
    # Fresh event loop for this process
    asyncio.set_event_loop(asyncio.new_event_loop())

def execute_claude_sync(prompt: str, session_id: str | None) -> dict:
    """Runs in worker process with own event loop."""
    async def run():
        from claude_code_sdk import query, ClaudeCodeOptions

        results = []
        async for msg in query(
            prompt=prompt,
            options=ClaudeCodeOptions(resume=session_id),
        ):
            results.append(msg)
        return results

    return asyncio.run(run())

# Called from chat consumer
async def submit_claude_task(prompt: str, session_id: str | None) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        executor,
        execute_claude_sync,
        prompt,
        session_id,
    )
```

**Deliverables:**
- [ ] `ProcessPoolExecutor` for Claude
- [ ] `ProcessPoolExecutor` for media (transcription, downloads)
- [ ] Response worker with rate limiting
- [ ] Remove ad-hoc subprocess calls

### Phase 5: Security Hardening (1 week)

**Goal:** Centralized auth, file proxy, audit logging.

```python
# src/services/file_proxy.py
from fastapi import FastAPI, HTTPException, Depends
from pathlib import Path

VAULT_ROOT = Path.home() / "Brains" / "brain"
ALLOWED_EXTENSIONS = {".md", ".txt", ".json", ".yaml"}

app = FastAPI()

def validate_path(path: str) -> Path:
    """Validate and resolve path safely."""
    resolved = (VAULT_ROOT / path).resolve()

    # Must be under vault root
    if not resolved.is_relative_to(VAULT_ROOT):
        raise HTTPException(403, "Path traversal detected")

    # Must have allowed extension
    if resolved.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(403, f"Extension not allowed: {resolved.suffix}")

    return resolved

@app.get("/notes/{path:path}")
async def read_note(path: str, api_key: str = Depends(verify_api_key)):
    resolved = validate_path(path)

    if not resolved.exists():
        raise HTTPException(404)

    # Audit log
    logger.info("note_read", path=str(resolved), api_key_hash=hash(api_key))

    return {"content": resolved.read_text()}
```

**Deliverables:**
- [ ] File proxy service
- [ ] Admin API gateway with API key auth
- [ ] Audit logging for all mutations
- [ ] Remove direct file access from handlers

### Phase 6: Cleanup (3 days)

**Goal:** Remove legacy code, update docs.

**Deliverables:**
- [ ] Delete `subprocess_helper.py` (replaced by workers)
- [ ] Delete `_buffer_lock` (no longer needed)
- [ ] Delete `send_message_sync` (use response worker)
- [ ] Update ARCHITECTURE.md
- [ ] Update CLAUDE.md

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Webhook response time | 100-5000ms | <50ms |
| Race condition incidents | ~1/week | 0 |
| Security hotfixes | ~2/month | 0 |
| Recovery after restart | Manual webhook reset | Automatic |
| Observability | grep logs | Dashboards |

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Redis becomes SPOF | Use Redis Sentinel or accept brief outages (personal bot) |
| ProcessPool leaks | Health check restarts workers periodically |
| Migration breaks features | Dual-write period with shadow testing |
| Over-engineering | Each phase is independently valuable; stop when enough |

---

## Technology Choices

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Queue | Redis Streams | Already using Redis, simple, sufficient scale |
| State store | Redis Hashes | Atomic operations, TTL support |
| Worker isolation | ProcessPoolExecutor | Stdlib, no new deps, true isolation |
| File proxy | FastAPI service | Same stack, easy to deploy |
| Metrics | Prometheus + Grafana | Industry standard, free |
| Logging | structlog | Structured JSON, easy to query |

---

## Comparison: What We Took From Each Proposal

| Feature | future_architecture.md | ARCHITECTURE_REDESIGN.md | Final |
|---------|------------------------|--------------------------|-------|
| Queue-first ingress | Yes | No | **Yes** |
| Per-chat actors | Yes (Temporal/Dramatiq) | No | **Yes** (simpler) |
| ProcessPoolExecutor | No | Yes | **Yes** |
| Redis for state | Yes | Yes | **Yes** |
| File proxy | Yes | No | **Yes** |
| Celery | Mentioned | Recommended long-term | **Deferred** |
| PostgreSQL | Yes | No | **No** (SQLite fine) |
| Shadow testing | Yes | No | **Yes** (Phase 2) |
| Security in Phase 5 | Yes | Not addressed | **Moved to Phase 5** |
| Code examples | No | Yes | **Yes** |

---

## Next Steps

1. **Review this document** - Any concerns with the approach?
2. **Set up Redis locally** - `brew install redis && brew services start redis`
3. **Start Phase 0** - Add telemetry to see current behavior
4. **Iterate** - Each phase is ~1 week, can pause anytime

The architecture can grow with you. Start simple, add complexity only when needed.

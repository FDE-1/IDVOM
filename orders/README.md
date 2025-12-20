# Orders Service

The **Orders** microservice exposes endpoints to place orders and list a user’s orders. It trusts the Gateway to handle Basic Auth and forwards the authenticated user via the `X-User` header.

* Language/stack: **Python 3.13**, FastAPI, SQLAlchemy 2, psycopg 3, Prometheus metrics
* Package manager: **uv**
* DB: **PostgreSQL**

## Features

* **Create order** with one or more items
* **Stock reservation**: atomically decrements stock in `catalog.products`
* **Price snapshot**: persists `price_cents` on each `order_item` at order time
* **Per-user history**: list orders for the authenticated user (`X-User`)
* **Health & metrics**: `/health`, `/metrics` (Prometheus counters/histograms)

## API

### `POST /orders`  *(protected; requires `X-User` header)*

Create an order. Items with the same `product_id` are combined server-side.

Request body:

```json
{
  "items": [
    { "product_id": 1, "qty": 2 },
    { "product_id": 2, "qty": 1 }
  ]
}
```

Responses:

* `200 OK` → returns the created order with item snapshots
* `400 Bad Request` → unknown product(s) or insufficient stock
* `401 Unauthorized` → missing `X-User`

### `GET /orders/me`  *(protected)*

List the current user’s orders (most recent first).

### `GET /health`

Liveness/readiness probe.

### `GET /metrics`

Prometheus metrics.

## Data Model (schema: `orders`)

* `orders`

  * `id` (PK)
  * `user_id` (string)
  * `created_at` (timestamp UTC)
  * `total_cents` (int)

* `order_items`

  * `id` (PK)
  * `order_id` (FK → orders.id, cascade delete)
  * `product_id` (int)
  * `qty` (int)
  * `price_cents` (int, snapshot at order time)

### Dependencies on `catalog` schema

* Reads `catalog.products (id, price_cents, stock)`
* Reserves stock with `UPDATE ... SET stock = stock - :qty WHERE id = :pid AND stock >= :qty`

## Configuration (env vars)

| Variable         | Default     | Description                         |
| ---------------- | ----------- | ----------------------------------- |
| `DB_HOST`        | `localhost` | Postgres host                       |
| `DB_PORT`        | `5432`      | Postgres port                       |
| `DB_NAME`        | `appdb`     | Database name                       |
| `DB_USER`        | `app`       | Database user                       |
| `DB_PASS`        | `app`       | Database password                   |
| `DB_SCHEMA`      | `orders`    | Orders service schema               |
| `CATALOG_SCHEMA` | `catalog`   | Catalog schema to read product data |
| `LISTEN_PORT`    | `8000`      | HTTP port                           |

## Metrics

* `http_requests_total{service,path,method,status}`
* `http_request_duration_seconds_bucket{service,path,method,...}`
* `orders_created_total`
* `order_create_failures_total{reason="missing_product|insufficient_stock"}`

## Local Development

### Prereqs

* Python 3.13
* `uv` ([https://docs.astral.sh/uv/](https://docs.astral.sh/uv/))
* A Postgres instance with a **`catalog.products`** table populated

### Run

```bash
cd apps/orders

export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=appdb
export DB_USER=app
export DB_PASS=app
export DB_SCHEMA=orders
export CATALOG_SCHEMA=catalog

uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Quick test

```bash
# health
curl http://localhost:8000/health

# create an order (simulate Gateway by setting X-User)
curl -s -X POST http://localhost:8000/orders \
  -H 'Content-Type: application/json' \
  -H 'X-User: alice' \
  -d '{"items":[{"product_id":1,"qty":2},{"product_id":2,"qty":1}]}'

# list my orders
curl -s -H 'X-User: alice' http://localhost:8000/orders/me
```

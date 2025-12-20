# Catalog Service

The **Catalog** service is a small FastAPI application that provides CRUD endpoints for managing products.
It connects to a PostgreSQL database and exposes Prometheus metrics for monitoring.

---

## Features

Product routes are mounted under `API_PREFIX` (default: `""`):
- **CRUD API** for products:
  - `GET /products` – list all products
  - `GET /products/{id}` – get one product
  - `POST /products` – create a new product
  - `PUT /products/{id}` – update a product
  - `DELETE /products/{id}` – delete a product
- **Authentication:**
  The service trusts the `X-User` header, which is set by the Gateway.
  Direct access without this header returns `401 Unauthorized` for write operations.
- **Health and Metrics:**
  - `GET /health` → simple health probe
  - `GET /metrics` → Prometheus metrics (request counts and latencies)

---

## Configuration

Environment variables are injected through a Kubernetes `ConfigMap` and `Secret`.

| Variable       | Description                               | Example                |
|----------------|-------------------------------------------|------------------------|
| `DB_HOST`      | PostgreSQL host                           | `postgres-rw`          |
| `DB_PORT`      | PostgreSQL port                           | `5432`                 |
| `DB_NAME`      | Database name                             | `appdb`                |
| `DB_USER`      | Database username                         | `app`                  |
| `DB_PASS`      | Database password                         | `app`                  |
| `DB_SCHEMA`    | Database schema                           | `catalog`              |
| `API_PREFIX`   | Mount point for product routes (e.g., `/api/catalog`) | `""`       |
| `LISTEN_PORT`  | Port to listen on                         | `8000`                 |

---

## API Overview

| Method | Endpoint           | Description             | Auth Required |
|:-------|:-------------------|:------------------------|:--------------|
| GET    | `/health`          | Health check            | No            |
| GET    | `/metrics`         | Prometheus metrics      | No            |
| GET    | `/products`        | List all products       | No            |
| GET    | `/products/{id}`   | Get a single product    | No            |
| POST   | `/products`        | Create a new product    | Yes (`X-User`) |
| PUT    | `/products/{id}`   | Update a product        | Yes (`X-User`) |
| DELETE | `/products/{id}`   | Delete a product        | Yes (`X-User`) |

---

## Local Development

### Prerequisites
- Python 3.13+
- [uv](https://github.com/astral-sh/uv)
- PostgreSQL instance running locally (e.g. Docker)

### Run locally

```bash
# Environment variables
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=appdb
export DB_USER=app
export DB_PASS=app
export DB_SCHEMA=catalog

# Install dependencies & start app
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

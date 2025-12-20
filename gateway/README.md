# Gateway Service

The Gateway is a simple reverse proxy written in Go.
It provides Basic Authentication and forwards authenticated requests to the **Catalog** and **Orders** services.
Authenticated users are passed downstream via the `X-User` header.

---

## Features

- **Basic Auth**: Users are defined in the `BASIC_USERS` secret as `username:password` pairs (comma-separated).
- **Proxying**:
  - `/api/catalog/*` → Catalog service
  - `/api/orders/*` → Orders service
- **Headers**: Adds `X-User: <username>` for authenticated calls.
- **Metrics**: Prometheus metrics available at `/metrics`.
- **Health**: Simple health check at `/health`.

---

## Configuration

The Gateway reads configuration from environment variables (provided in Kubernetes via ConfigMap + Secret):

| Variable            | Description                                              | Example                                     |
|---------------------|----------------------------------------------------------|---------------------------------------------|
| `LISTEN_ADDR`       | Address the gateway listens on                           | `:8080`                                     |
| `CATALOG_BASE_URL`  | Base URL of the Catalog service                          | `http://catalog.example.com` |
| `ORDERS_BASE_URL`   | Base URL of the Orders service                           | `http://orders.example.com` |
| `BASIC_USERS`       | Comma-separated user:password pairs (from a Secret)      | `alice:secret,bob:secret`                   |

---

## Endpoints

- `GET /health` → returns `ok`
- `GET /metrics` → Prometheus metrics
- `GET /whoami` (requires Basic Auth) → returns current username
- `GET /api/catalog/...` → proxied to Catalog service
- `GET /api/orders/...` → proxied to Orders service

---

## Local Development

### Prerequisites
- Go
- (Optional) Docker

### Run directly
```bash
export LISTEN_ADDR=":8080"
export CATALOG_BASE_URL="http://localhost:8001"
export ORDERS_BASE_URL="http://localhost:8002"
export BASIC_USERS="alice:secret,bob:secret"

go run ./main.go

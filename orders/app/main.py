import os
import time
from typing import List, Dict
from fastapi import FastAPI, HTTPException, Depends, Request, Response, status
from fastapi.responses import PlainTextResponse
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .db import get_session, engine, CATALOG_SCHEMA
from .models import Base, Order, OrderItem
from .schemas import OrderCreate, OrderOut, OrderItemOut

APP_NAME = "orders"
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "8000"))

app = FastAPI(title=APP_NAME)

# Create tables at startup (idempotent)
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

# Prometheus metrics
REQS = Counter("http_requests_total", "Total HTTP requests", ["service", "path", "method", "status"])
LAT = Histogram("http_request_duration_seconds", "Request latency", ["service", "path", "method"])
ORDERS_CREATED = Counter("orders_created_total", "Orders created successfully")
ORDERS_FAILED = Counter("order_create_failures_total", "Order create failures", ["reason"])

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    REQS.labels(APP_NAME, request.url.path, request.method, response.status_code).inc()
    LAT.labels(APP_NAME, request.url.path, request.method).observe(time.time() - start)
    return response

# Gateway sets X-User; require it for protected endpoints
def require_user(request: Request) -> str:
    user = request.headers.get("X-User")
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing X-User")
    return user

@app.get("/health", response_class=PlainTextResponse)
def health():
    return "ok"

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

# ---------- Helpers ----------
def fetch_prices(session: Session, product_ids: List[int]) -> Dict[int, int]:
    """
    Read current prices from catalog.products.
    Returns {product_id: price_cents}. Missing products are omitted.
    """
    if not product_ids:
        return {}
    sql = text(
        f"SELECT id, price_cents FROM {CATALOG_SCHEMA}.products WHERE id = ANY(:ids)"
    )
    rows = session.execute(sql, {"ids": product_ids}).all()
    return {row[0]: row[1] for row in rows}

def reserve_stock(session: Session, items: List[Dict[str, int]]) -> None:
    """
    Decrement stock in catalog.products atomically per item.
    Fails if any item doesn't have enough stock.
    """
    for it in items:
        pid, qty = it["product_id"], it["qty"]
        upd = text(
            f"""
            UPDATE {CATALOG_SCHEMA}.products
            SET stock = stock - :qty
            WHERE id = :pid AND stock >= :qty
            """
        )
        res = session.execute(upd, {"qty": qty, "pid": pid})
        if res.rowcount != 1:
            raise HTTPException(status_code=400, detail=f"insufficient stock for product {pid}")

# ---------- Endpoints ----------
@app.post("/orders", response_model=OrderOut)
def create_order(payload: OrderCreate, user: str = Depends(require_user), session: Session = Depends(get_session)):
    # Validate and normalize items (combine duplicates)
    if not payload.items:
        raise HTTPException(status_code=400, detail="items must not be empty")

    combined: Dict[int, int] = {}
    for it in payload.items:
        combined[it.product_id] = combined.get(it.product_id, 0) + it.qty

    product_ids = list(combined.keys())
    prices = fetch_prices(session, product_ids)
    if len(prices) != len(product_ids):
        missing = sorted(set(product_ids) - set(prices.keys()))
        ORDERS_FAILED.labels(reason="missing_product").inc()
        raise HTTPException(status_code=400, detail=f"unknown product(s): {missing}")

    # Reserve stock first (will raise 400 on insufficient stock)
    try:
        reserve_stock(session, [{"product_id": pid, "qty": qty} for pid, qty in combined.items()])
    except HTTPException as e:
        ORDERS_FAILED.labels(reason="insufficient_stock").inc()
        raise e

    # Build order & items, snapshot price_cents
    order = Order(user_id=user, total_cents=0)
    session.add(order)
    session.flush()  # get order.id

    total = 0
    for pid, qty in combined.items():
        price = prices[pid]
        total += price * qty
        oi = OrderItem(order_id=order.id, product_id=pid, qty=qty, price_cents=price)
        session.add(oi)

    order.total_cents = total
    session.add(order)
    session.flush()
    session.refresh(order)

    ORDERS_CREATED.inc()
    return OrderOut(
        id=order.id,
        user_id=order.user_id,
        total_cents=order.total_cents,
        items=[OrderItemOut(product_id=i.product_id, qty=i.qty, price_cents=i.price_cents) for i in order.items],
    )

@app.get("/orders/me", response_model=List[OrderOut])
def list_my_orders(user: str = Depends(require_user), session: Session = Depends(get_session)):
    # Load orders & their items for the current user
    orders = session.execute(
        select(Order).where(Order.user_id == user).order_by(Order.id.desc())
    ).scalars().all()

    out: List[OrderOut] = []
    for o in orders:
        # ensure items are present
        _ = o.items  # materialize relationship
        out.append(
            OrderOut(
                id=o.id,
                user_id=o.user_id,
                total_cents=o.total_cents,
                items=[OrderItemOut(product_id=i.product_id, qty=i.qty, price_cents=i.price_cents) for i in o.items],
            )
        )
    return out

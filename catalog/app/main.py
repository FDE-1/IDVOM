import os
import time
from typing import List
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, status
from fastapi.responses import PlainTextResponse
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_session, init_db, engine
from .models import Product
from .schemas import ProductIn, ProductOut

APP_NAME = "catalog"

# Optional prefix for routes. Leave empty ("") if your Gateway strips /api/catalog.
# If your Gateway does NOT strip the prefix, set API_PREFIX="/api/catalog".
API_PREFIX = os.getenv("API_PREFIX", "").strip()
if API_PREFIX and not API_PREFIX.startswith("/"):
    API_PREFIX = "/" + API_PREFIX
API_PREFIX = API_PREFIX.rstrip("/")

app = FastAPI(title=APP_NAME)
router = APIRouter(prefix=API_PREFIX)

# ---- Startup: ensure schema + tables exist (idempotent) ----
@app.on_event("startup")
def on_startup():
    init_db()

# ---- Prometheus metrics ----
REQS = Counter("http_requests_total", "Total HTTP requests", ["service", "path", "method", "status"])
LAT  = Histogram("http_request_duration_seconds", "Request latency", ["service", "path", "method"])

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    REQS.labels(APP_NAME, request.url.path, request.method, response.status_code).inc()
    LAT.labels(APP_NAME, request.url.path, request.method).observe(time.time() - start)
    return response

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

@router.get("/products", response_model=List[ProductOut])
def list_products(session: Session = Depends(get_session)):
    rows = session.execute(select(Product)).scalars().all()
    return rows

@router.post("/products", response_model=ProductOut)
def create_product(payload: ProductIn, user: str = Depends(require_user), session: Session = Depends(get_session)):
    p = Product(name=payload.name, price_cents=payload.price_cents, stock=payload.stock)
    session.add(p)
    session.flush()
    session.refresh(p)
    return p

@router.get("/products/{pid}", response_model=ProductOut)
def get_product(pid: int, session: Session = Depends(get_session)):
    p = session.get(Product, pid)
    if not p:
        raise HTTPException(status_code=404, detail="not found")
    return p

@router.put("/products/{pid}", response_model=ProductOut)
def update_product(pid: int, payload: ProductIn, user: str = Depends(require_user), session: Session = Depends(get_session)):
    p = session.get(Product, pid)
    if not p:
        raise HTTPException(status_code=404, detail="not found")
    p.name = payload.name
    p.price_cents = payload.price_cents
    p.stock = payload.stock
    session.add(p)
    session.flush()
    session.refresh(p)
    return p

@router.delete("/products/{pid}", status_code=204)
def delete_product(pid: int, user: str = Depends(require_user), session: Session = Depends(get_session)):
    p = session.get(Product, pid)
    if not p:
        raise HTTPException(status_code=404, detail="not found")
    session.delete(p)
    return Response(status_code=204)

app.include_router(router)

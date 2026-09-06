from contextlib import asynccontextmanager
from uuid import uuid4
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from app import models, schemas, services
from app.core import logger, request_id
from app.db import Base, engine, get_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    yield

app = FastAPI(title="Target Commerce API", lifespan=lifespan)

@app.middleware("http")
async def log_request(request, call_next):
    correlation_id = str(uuid4())
    token = request_id.set(correlation_id)
    details = {"method": request.method, "endpoint": request.url.path}
    try:
        try:
            response = await call_next(request)
        except Exception as exc:
            logger.exception("Request failed", extra={
                **details, "status": 500, "exception_type": type(exc).__name__,
                "error_message": str(exc),
            })
            response = JSONResponse(status_code=500, content={
                "detail": "Internal Server Error", "request_id": correlation_id,
            })
        response.headers["X-Request-ID"] = correlation_id
        logger.info("Request completed", extra={**details, "status": response.status_code})
        return response
    finally:
        request_id.reset(token)

@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        logger.exception("Health check failed", extra={
            "exception_type": type(exc).__name__, "error_message": str(exc), "status": 503,
        })
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ok"}

@app.post("/users", response_model=schemas.UserResponse, status_code=201)
def create_user(data: schemas.UserCreate, db: Session = Depends(get_db)):
    return services.create_user(db, data)

@app.post("/orders", response_model=schemas.OrderResponse, status_code=201)
def create_order(data: schemas.OrderCreate, db: Session = Depends(get_db)):
    return services.create_order(db, data)

@app.get("/orders/{order_id}", response_model=schemas.OrderResponse)
def get_order(order_id: int, db: Session = Depends(get_db)):
    return services.get_order(db, order_id)

@app.post("/payments", response_model=schemas.PaymentResponse, status_code=201)
def create_payment(data: schemas.PaymentCreate, db: Session = Depends(get_db)):
    return services.create_payment(db, data)

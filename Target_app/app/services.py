from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models import Order, Payment, User
from app.schemas import OrderCreate, PaymentCreate, UserCreate

def order_total(quantity: int, unit_price: Decimal) -> Decimal:
    subtotal = unit_price * quantity
    discount_rate = Decimal("0.10") if quantity >= 10 else Decimal("0")
    return (subtotal * (1 - discount_rate)).quantize(Decimal("0.01"))

def create_user(db: Session, data: UserCreate) -> User:
    user = User(name=data.name, email=str(data.email).lower())
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if getattr(exc.orig.diag, "constraint_name", None) == "users_email_key":
            raise HTTPException(409, "Email already exists") from exc
        raise
    db.refresh(user)
    return user

def get_order(db: Session, order_id: int) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(404, "Order not found")
    return order

def create_order(db: Session, data: OrderCreate) -> Order:
    if db.get(User, data.user_id) is None:
        raise HTTPException(404, "User not found")
    order = Order(**data.model_dump(), total_amount=order_total(data.quantity, data.unit_price))
    db.add(order)
    db.commit()
    db.refresh(order)
    return order

def create_payment(db: Session, data: PaymentCreate) -> Payment:
    order = db.scalar(select(Order).where(Order.id == data.order_id).with_for_update())
    if order is None:
        raise HTTPException(404, "Order not found")
    if order.status == "paid":
        raise HTTPException(409, "Order already paid")
    if data.amount != order.total_amount:
        raise HTTPException(422, "Payment amount must match order total")
    payment = Payment(**data.model_dump())
    order.status = "paid"
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment

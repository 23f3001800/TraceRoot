from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Product = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Price = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
Amount = Annotated[Decimal, Field(gt=0, max_digits=16, decimal_places=2)]

class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

class UserCreate(Input):
    name: Name
    email: Annotated[EmailStr, Field(max_length=254)]

class OrderCreate(Input):
    user_id: Annotated[int, Field(gt=0)]
    product_name: Product
    quantity: Annotated[int, Field(gt=0, le=10000, strict=True)]
    unit_price: Price

class PaymentCreate(Input):
    order_id: Annotated[int, Field(gt=0)]
    amount: Amount

class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)

class UserResponse(Output):
    id: int
    name: str
    email: str
    created_at: datetime

class OrderResponse(Output):
    id: int
    user_id: int
    product_name: str
    quantity: int
    unit_price: Decimal
    total_amount: Decimal
    status: Literal["pending", "paid"]
    created_at: datetime

class PaymentResponse(Output):
    id: int
    order_id: int
    amount: Decimal
    status: Literal["completed"]
    created_at: datetime

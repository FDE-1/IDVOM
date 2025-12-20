from typing import List
from pydantic import BaseModel, Field

class OrderItemIn(BaseModel):
    product_id: int = Field(ge=1)
    qty: int = Field(ge=1)

class OrderCreate(BaseModel):
    items: List[OrderItemIn] = Field(min_length=1)

class OrderItemOut(BaseModel):
    product_id: int
    qty: int
    price_cents: int

class OrderOut(BaseModel):
    id: int
    user_id: str
    total_cents: int
    items: List[OrderItemOut]

    class Config:
        from_attributes = True

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import Product
from app.schemas.product import ProductRead

router = APIRouter(prefix="/products", tags=["products"])


@router.get("/{product_id}", response_model=ProductRead)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    # AsyncSession.get() is the shorthand for a primary-key lookup — simpler
    # than select(Product).where(Product.id == product_id) for this case.
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"No product with id {product_id}")
    return product

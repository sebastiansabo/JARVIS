# Backend Patterns

## FastAPI Service Layer Pattern
```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/transactions", tags=["transactions"])

@router.post("/", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    data: TransactionCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    service = TransactionService(session)
    try:
        result = await service.create(data, created_by=current_user.id)
        return TransactionResponse.model_validate(result)
    except DuplicateTransactionError:
        raise HTTPException(status_code=409, detail="Transaction already exists")
    except GLImbalanceError as e:
        raise HTTPException(status_code=422, detail=str(e))
```

## Repository Pattern
```python
class BaseRepository[T]:
    def __init__(self, session: AsyncSession, model: type[T]):
        self.session = session
        self.model = model

    async def get_by_id(self, id: UUID) -> T | None:
        return await self.session.get(self.model, id)

    async def create(self, **kwargs) -> T:
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def find(self, **filters) -> list[T]:
        stmt = select(self.model).filter_by(**filters)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
```

## Async Database Session
```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

engine = create_async_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
)

async_session = async_sessionmaker(engine, expire_on_commit=False)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        async with session.begin():
            yield session
```

## Background Job Pattern (Celery/ARQ)
```python
# For long-running operations: PDF processing, batch imports, report generation
@task(retry=3, retry_backoff=True)
async def process_bank_statement(file_id: UUID, user_id: UUID):
    async with async_session() as session:
        service = BankImportService(session)
        result = await service.process(file_id, user_id)
        await session.commit()
    return result.to_dict()
```

## Caching Pattern
```python
from functools import lru_cache
import redis.asyncio as redis

# Redis for shared cache
cache = redis.from_url(REDIS_URL)

async def get_exchange_rate(currency: str, date: date) -> Decimal:
    cache_key = f"rate:{currency}:{date.isoformat()}"
    cached = await cache.get(cache_key)
    if cached:
        return Decimal(cached.decode())

    rate = await fetch_rate_from_provider(currency, date)
    await cache.setex(cache_key, 86400, str(rate))  # 24h TTL
    return rate
```

## Pagination Pattern
```python
# Cursor-based for large collections
@router.get("/", response_model=PaginatedResponse[TransactionResponse])
async def list_transactions(
    cursor: str | None = None,
    limit: int = Query(default=50, le=100),
    session: AsyncSession = Depends(get_session),
):
    repo = TransactionRepository(session)
    items, next_cursor = await repo.paginate(cursor=cursor, limit=limit)
    return PaginatedResponse(
        items=[TransactionResponse.model_validate(i) for i in items],
        next_cursor=next_cursor,
        has_more=next_cursor is not None,
    )
```

## Error Handling Middleware
```python
@app.exception_handler(FinancialError)
async def financial_error_handler(request: Request, exc: FinancialError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.__class__.__name__,
            "message": str(exc),
            "detail": exc.detail if hasattr(exc, 'detail') else None,
        },
    )
```

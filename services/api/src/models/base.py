import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime
from src.database import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)

class BaseModel(Base):
    __abstract__ = True

    id = Column(String(36), primary_key=True, default=generate_uuid)
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)

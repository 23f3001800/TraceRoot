import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

class Base(DeclarativeBase):
    pass

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True, hide_parameters=True)
SessionLocal = sessionmaker(engine)

def get_db():
    with SessionLocal() as session:
        yield session

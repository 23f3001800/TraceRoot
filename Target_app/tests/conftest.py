import os
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Each test owns a unique PostgreSQL schema, including its constraints.
os.environ.setdefault("DATABASE_URL", os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://commerce:commerce@localhost/commerce"))
from app.db import Base, get_db
from app.main import app

@pytest.fixture
def client():
    url = os.environ.get("TEST_DATABASE_URL", os.environ["DATABASE_URL"])
    admin = create_engine(url)
    schema = "test_" + uuid4().hex
    with admin.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    test_engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    Base.metadata.create_all(test_engine)
    def override_db():
        with Session(test_engine) as session:
            yield session
    app.dependency_overrides[get_db] = override_db
    try:
        # No lifespan: tables are created only in the isolated test schema.
        test_client = TestClient(app, raise_server_exceptions=False)
        try:
            yield test_client
        finally:
            test_client.close()
    finally:
        app.dependency_overrides.clear()
        test_engine.dispose()
        with admin.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        admin.dispose()

import pytest

def user(client):
    response = client.post("/users", json={"name": "Ada", "email": "ada@example.com"})
    assert response.status_code == 201
    return response.json()["id"]

def order_payload(user_id, **changes):
    return {"user_id": user_id, "product_name": "Notebook", "quantity": 2, "unit_price": "19.99", **changes}

def test_health(client):
    response = client.get("/health")
    assert response.json() == {"status": "ok"}
    assert response.status_code == 200
    assert response.headers["x-request-id"]

def test_user_creation_and_duplicate(client):
    user(client)
    assert client.post("/users", json={"name": "Ada", "email": "ada@example.com"}).status_code == 409

def test_order_creation_and_retrieval(client):
    response = client.post("/orders", json=order_payload(user(client)))
    assert response.status_code == 201
    assert response.json()["total_amount"] == "39.98"
    assert response.json()["status"] == "pending"
    fetched = client.get(f"/orders/{response.json()['id']}")
    assert fetched.json() == response.json()

def test_payment(client):
    order = client.post("/orders", json=order_payload(user(client))).json()
    payload = {"order_id": order["id"], "amount": "39.98"}
    assert client.post("/payments", json={**payload, "amount": "1.00"}).status_code == 422
    response = client.post("/payments", json=payload)
    assert response.status_code == 201
    assert response.json()["status"] == "completed"
    assert client.get(f"/orders/{order['id']}").json()["status"] == "paid"
    assert client.post("/payments", json=payload).status_code == 409

@pytest.mark.parametrize("change", [
    {"quantity": 0}, {"quantity": -1}, {"quantity": 10001}, {"quantity": 1.5},
    {"unit_price": "0"}, {"unit_price": "1.001"}, {"product_name": " "},
])
def test_order_validation(client, change):
    assert client.post("/orders", json=order_payload(user(client), **change)).status_code == 422

def test_user_validation(client):
    assert client.post("/users", json={"name": " ", "email": "bad"}).status_code == 422

def test_missing_resources(client):
    assert client.get("/orders/999999").status_code == 404
    assert client.post("/orders", json=order_payload(999999)).status_code == 404
    assert client.post("/payments", json={"order_id": 999999, "amount": "1.00"}).status_code == 404

@pytest.mark.regression
def test_bulk_order_is_accepted(client):
    response = client.post("/orders", json=order_payload(user(client), quantity=10))
    assert response.status_code == 201, response.text
    assert client.get(f"/orders/{response.json()['id']}").status_code == 200

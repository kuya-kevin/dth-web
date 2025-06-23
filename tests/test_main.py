import os
import pytest
from httpx import AsyncClient
from httpx import ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy_utils import database_exists, create_database

from app.main import app, get_db, client as openai_client
from app.db.db import Base, User # Import User for table creation
import unittest.mock as mock
import configparser

config = configparser.ConfigParser()
config.read(os.getenv('DEFAULT_CONFIG'))

# Use an in-memory SQLite database for testing
DATABASE_URL_TEST = config.get("Database", "DATABASE_URL", fallback=None)
engine_test = create_engine(DATABASE_URL_TEST)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)

@pytest.fixture(scope="module")
def setup_database():
    """
    Fixture to set up and tear down the test database.
    Ensures a clean database for each test run.
    """
    # Create the database if it doesn't exist (for file-based SQLite)
    if not database_exists(engine_test.url):
        create_database(engine_test.url)

    # Create tables
    Base.metadata.create_all(bind=engine_test)
    yield
    # Drop tables after tests are done
    Base.metadata.drop_all(bind=engine_test)


@pytest.fixture(scope="function")
def db_session(setup_database):
    """
    Fixture for an independent database session for each test function.
    Rolls back transactions after each test to ensure isolation.
    """
    connection = engine_test.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture(scope="function")
async def async_client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close()

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)  # 👈 this is the key change
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides = {}

@pytest.fixture(scope="function")
def mock_openai_client():
    """
    Fixture to mock the OpenAI client for the /joke endpoint.
    """
    with mock.patch('app.main.client') as mock_client:
        mock_response = mock.MagicMock()
        mock_response.output_text = "Why did the tennis ball break up with the racket? It felt too much pressure!"
        mock_client.responses.create.return_value = mock_response
        yield mock_client

# --- Test create_user (POST /users/) ---

@pytest.mark.asyncio
async def test_create_user_success(async_client):
    """
    Test successful creation of a new user.
    """
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "rating": 4.5
    }
    response = await async_client.post("/users/", json=user_data)
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "testuser"
    assert data["email"] == "test@example.com"
    assert data["full_name"] == "Test User"
    assert data["rating"] == 4.5
    assert "id" in data

@pytest.mark.asyncio
async def test_create_user_with_default_rating(async_client):
    """
    Test user creation with default rating (3.0).
    """
    user_data = {
        "username": "defaultrater",
        "email": "default@example.com",
        "full_name": "Default Rater"
    }
    response = await async_client.post("/users/", json=user_data)
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "defaultrater"
    assert data["email"] == "default@example.com"
    assert data["rating"] == 3.0 # Default rating

@pytest.mark.asyncio
async def test_create_user_duplicate_username(async_client):
    """
    Test creating a user with a username that already exists.
    """
    # Create the first user
    user_data = {
        "username": "existinguser",
        "email": "existing@example.com",
        "rating": 3.0
    }
    await async_client.post("/users/", json=user_data)

    # Attempt to create a user with the same username
    duplicate_user_data = {
        "username": "existinguser",
        "email": "another@example.com",
        "rating": 3.0
    }
    response = await async_client.post("/users/", json=duplicate_user_data)
    assert response.status_code == 400
    assert response.json()["detail"] == "Username already registered"

@pytest.mark.asyncio
async def test_create_user_duplicate_email(async_client):
    """
    Test creating a user with an email that already exists.
    """
    # Create the first user
    user_data = {
        "username": "emailuser",
        "email": "email@example.com",
        "rating": 3.0
    }
    await async_client.post("/users/", json=user_data)

    # Attempt to create a user with the same email
    duplicate_user_data = {
        "username": "anotheremailuser",
        "email": "email@example.com",
        "rating": 3.0
    }
    response = await async_client.post("/users/", json=duplicate_user_data)
    assert response.status_code == 400
    assert response.json()["detail"] == "Email already registered"

@pytest.mark.asyncio
@pytest.mark.parametrize("rating, expected_error", [
    (0.5, "Rating must be between 1.0 and 5.0"),
    (5.5, "Rating must be between 1.0 and 5.0"),
    (3.2, "Rating must be in increments of 0.5"),
    (None, "Rating cannot be null. Omit the field to use the default or provide a valid float value"),
])
async def test_create_user_invalid_rating(async_client, rating, expected_error):
    """
    Test creating a user with an invalid rating.
    """
    user_data = {
        "username": "invalidrater",
        "email": "invalid@example.com",
        "rating": rating
    }
    # If rating is None, remove the key from the dictionary to test the specific validation error
    if rating is None:
        user_data["rating"] = None
        response = await async_client.post("/users/", json=user_data)
        assert response.status_code == 422 # Pydantic validation error
        assert "Input should be a valid number" in response.json()["detail"][0]["msg"]
    else:
        response = await async_client.post("/users/", json=user_data)
        assert response.status_code == 422 # Pydantic validation error
        assert expected_error in response.json()["detail"][0]["msg"]


# --- Test read_users (GET /users/) ---

@pytest.mark.asyncio
async def test_read_users_empty(async_client):
    """
    Test retrieving users when no users exist.
    """
    response = await async_client.get("/users/")
    assert response.status_code == 200
    assert response.json() == []

@pytest.mark.asyncio
async def test_read_users_multiple(async_client):
    """
    Test retrieving multiple users.
    """
    user1_data = {"username": "user1", "email": "user1@example.com", "rating": 3.0}
    user2_data = {"username": "user2", "email": "user2@example.com", "rating": 4.0}
    user3_data = {"username": "user3", "email": "user3@example.com", "rating": 5.0}

    await async_client.post("/users/", json=user1_data)
    await async_client.post("/users/", json=user2_data)
    await async_client.post("/users/", json=user3_data)

    response = await async_client.get("/users/")
    assert response.status_code == 200
    users = response.json()
    assert len(users) == 3
    assert any(user["username"] == "user1" for user in users)
    assert any(user["username"] == "user2" for user in users)
    assert any(user["username"] == "user3" for user in users)

@pytest.mark.asyncio
async def test_read_users_skip_limit(async_client):
    """
    Test retrieving users with skip and limit parameters.
    """
    for i in range(10):
        user_data = {"username": f"user_{i}", "email": f"user_{i}@example.com", "rating": 3.0}
        await async_client.post("/users/", json=user_data)

    # Test skip=2, limit=3
    response = await async_client.get("/users/?skip=2&limit=3")
    assert response.status_code == 200
    users = response.json()
    assert len(users) == 3
    assert users[0]["username"] == "user_2"
    assert users[1]["username"] == "user_3"
    assert users[2]["username"] == "user_4"

# --- Test get_a_tennis_joke (GET /joke) ---

@pytest.mark.asyncio
async def test_get_a_tennis_joke(async_client, mock_openai_client):
    """
    Test the /joke endpoint to ensure it returns a joke from the mocked OpenAI client.
    """
    response = await async_client.get("/joke")
    assert response.status_code == 200
    assert response.json() == "Why did the tennis ball break up with the racket? It felt too much pressure!"
    # Verify that the OpenAI client's create method was called
    mock_openai_client.responses.create.assert_called_once_with(
        model="gpt-3.5-turbo",
        input="Write a joke about tennis."
    )

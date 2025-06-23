import os
import configparser

from fastapi import FastAPI, HTTPException, Depends
from app.db.db import SessionLocal, User
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from sqlalchemy.orm import Session

from openai import OpenAI


app = FastAPI()

config = configparser.ConfigParser()
CONFIG_PATH = os.getenv('DEFAULT_CONFIG')
config.read(CONFIG_PATH)
API_KEY = config.get("OpenAI", "OPENAI_API_KEY", fallback=None)
client = OpenAI(
api_key=API_KEY
)

# Dependency to get a database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- 3. Pydantic Models for FastAPI ---
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    full_name: Optional[str] = None
    rating: float = 3.0

    @field_validator('rating')
    def rating_must_be_valid(cls, value):
        # Check None
        if value is None:
            raise ValueError('Rating cannot be null. Omit the field to use the default or provide a valid float value')

        # Check range
        if not (1.0 <= value <= 5.0):
            raise ValueError('Rating must be between 1.0 and 5.0')

        # Check increments of 0.5
        # Multiply by 2 to make it an integer (1.0 -> 2, 1.5 -> 3, 2.0 -> 4)
        # Then check if it's an even integer (meaning it was originally .0 or .5)
        # Use a small epsilon for floating point comparison to avoid precision issues
        epsilon = 1e-9 # A very small number
        scaled_value = value * 2
        if abs(scaled_value - round(scaled_value)) > epsilon or (round(scaled_value) % 1) != 0:
             raise ValueError('Rating must be in increments of 0.5 (e.g., 1.0, 1.5, 2.0)')

        return value

class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    full_name: Optional[str] = None
    rating: Optional[float] = None

    class Config:
        orm_mode = True # This tells Pydantic to read data from ORM objects

'''
standard http methods - POST (create data)/GET (read data) /PUT (update data)/DELETE (delete data)
exotic methods - OPTIONS/HEAD/PATCH/TRACE
'''

@app.get("/") # this is a path operation decorator. the method below is in charge of handling requests that go to "/"
async def root():
    return ['hello', 'world'] # you can return a dict, list, singular values as str, int, etc.

# post example
@app.post("/")
async def post_root():
    return ['data', 'received']

@app.post("/users/", response_model=UserResponse)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    # Check if username or email already exists
    db_user_by_username = db.query(User).filter(User.username == user.username).first()
    if db_user_by_username:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    db_user_by_email = db.query(User).filter(User.email == user.email).first()
    if db_user_by_email:
        raise HTTPException(status_code=400, detail="Email already registered")

    db_user = User(**user.model_dump())
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

# --- Example: FastAPI endpoint to get all users (for testing) ---
@app.get("/users/", response_model=list[UserResponse])
def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    users = db.query(User).offset(skip).limit(limit).all()
    return users


# Testing - FASTAPI endpoint to get a joke about tennis
@app.get("/joke")
def get_a_tennis_joke():
    response = client.responses.create(
        model="gpt-3.5-turbo",
        input="Write a joke about tennis."
    )


    return(response.output_text)
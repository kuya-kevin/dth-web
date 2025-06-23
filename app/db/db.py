import os
from sqlalchemy import create_engine, Column, Integer, String, DECIMAL, CheckConstraint
from sqlalchemy.orm import sessionmaker, declarative_base

import configparser

config = configparser.ConfigParser()
config.read(os.getenv('DEFAULT_CONFIG'))


# --- 1. Database Configuration ---
# Assuming you have a SQLite database named 'mydatabase.db'
# You can change this to your desired database (e.g., PostgreSQL, MySQL)
DATABASE_URL = config.get("Database", "DATABASE_URL", fallback=None)
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# --- 2. SQLAlchemy Model Definition ---
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    full_name = Column(String)
    # Using DECIMAL for precise decimal storage
    # precision=2, scale=1 means max 2 digits, 1 after decimal (e.g., 5.0)
    rating = Column(DECIMAL(precision=2, scale=1))

    __table_args__ = (
        CheckConstraint(
            'rating >= 1.0 AND rating <= 5.0',
            name='ck_users_rating_range'
        ),
        # This constraint will ensure increments of 0.5.
        # It works by checking if (rating * 10) % 5 == 0.
        # For example, 1.0 * 10 = 10, 10 % 5 = 0 (valid)
        # 1.5 * 10 = 15, 15 % 5 = 0 (valid)
        # 1.2 * 10 = 12, 12 % 5 = 2 (invalid)
        CheckConstraint(
            '(rating * 10) % 5 = 0',
            name='ck_users_rating_increment'
        )
    )

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}', rating='{self.rating}')>"
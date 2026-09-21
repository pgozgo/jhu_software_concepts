"""
Module 3: Define SQLAlchemy ORM Model for Applicants
Defines the SQLAlchemy ORM model for the applicants table in PostgreSQL.
"""

import os
from sqlalchemy import Column, Date, Float, Integer, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Define the base class for the SQLAlchemy ORM models. All ORM models should inherit from this base class.
Base = declarative_base()

# Define the Applicant model that maps to the applicants table in PostgreSQL.
class Applicant(Base):
    __tablename__ = "applicants"

    p_id = Column(Integer, primary_key=True)
    program = Column(Text)
    comments = Column(Text)
    date_added = Column(Date)
    url = Column(Text)
    status = Column(Text)
    term = Column(Text)
    us_or_international = Column(Text)
    gpa = Column(Float)
    gre = Column(Float)
    gre_v = Column(Float)
    gre_aw = Column(Float)
    degree = Column(Text)
    llm_generated_program = Column(Text)
    llm_generated_university = Column(Text)

database_url = os.getenv("DATABASE_URL")
if not database_url:
    raise RuntimeError("DATABASE_URL must be set before connecting to PostgreSQL")

engine = create_engine(database_url)
Session = sessionmaker(bind=engine)

# How to use the SQLAlchemy ORM with this model
# 1. Set the DATABASE_URL environment variable to point to your PostgreSQL database.
# 2. Import the Session and Applicant classes from this module.
# 3. Create a session using `with Session() as session:`.
# 4. Use the session to query the database, e.g., `session.query(Applicant).all()`.

"""SQLAlchemy mapping and session factory for the applicants table.

``DATABASE_URL`` selects the database when this module is imported. The Sphinx
configuration supplies SQLite only as a documentation-build fallback.
"""

import os

from sqlalchemy import Column, Date, Float, Integer, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class Applicant(Base):
    """ORM row for one Grad Cafe applicant result.

    Attributes:
        p_id (int): Database-generated primary key.
        program (str | None): Program and institution text as submitted.
        comments (str | None): Applicant's optional comments.
        date_added (datetime.date | None): Date the result was posted.
        url (str | None): Grad Cafe result URL used for deduplication.
        status (str | None): Reported decision status.
        term (str | None): Application term, such as ``Fall 2026``.
        us_or_international (str | None): Applicant nationality classification.
        gpa (float | None): Reported GPA.
        gre (float | None): Overall or quantitative GRE score.
        gre_v (float | None): GRE verbal score.
        gre_aw (float | None): GRE analytical-writing score.
        degree (str | None): Degree category.
        llm_generated_program (str | None): Normalized program category.
        llm_generated_university (str | None): Normalized university name.
    """

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

"""
Module 3: Query Applicant Data using SQLAlchemy ORM
Provides functions to query applicant data from the PostgreSQL database using SQLAlchemy ORM.
"""

from sqlalchemy import and_, func, or_, select
from models import Applicant, Session

def _average(value):
	# Round averages in Python after SQLAlchemy performs the database aggregate.
	return round(value, 2) if value is not None else None

def question_1(session):
	# Count applicants who applied for Fall 2026.
	statement = select(func.count()).select_from(Applicant).where(
		Applicant.term == "Fall 2026"
	)
	return session.scalar(statement)

def question_4(session):
	# Average GPA for American applicants applying for Fall 2026.
	statement = select(func.avg(Applicant.gpa)).where(
		and_(
			Applicant.term == "Fall 2026",
			Applicant.us_or_international == "American",
			Applicant.gpa.is_not(None),
		)
	)
	return _average(session.scalar(statement))

def question_5(session):
	# Percentage of Fall 2025 entries whose status starts with Accepted.
	total_statement = select(func.count()).select_from(Applicant).where(
		Applicant.term == "Fall 2025"
	)
	accepted_statement = select(func.count()).select_from(Applicant).where(
		and_(Applicant.term == "Fall 2025", Applicant.status.ilike("Accepted%"))
	)
	total = session.scalar(total_statement)
	accepted = session.scalar(accepted_statement)
	return round(100 * accepted / total, 2) if total else None

def question_8(session):
	# Count original-field Fall 2026 accepted PhD Computer Science entries.
	universities = or_(
		Applicant.program.ilike("%Georgetown University%"),
		Applicant.program.ilike("%Massachusetts Institute of Technology%"),
		Applicant.program.ilike("%MIT%"),
		Applicant.program.ilike("%Stanford University%"),
		Applicant.program.ilike("%Carnegie Mellon University%"),
	)
	statement = select(func.count()).select_from(Applicant).where(
		and_(
			Applicant.term == "Fall 2026",
			Applicant.status.ilike("Accepted%"),
			Applicant.program.ilike("%Computer Science%"),
			Applicant.degree == "PhD",
			universities,
		)
	)
	return session.scalar(statement)

def question_9(session):
	# Count the same entries using the LLM-generated program and university.
	universities = Applicant.llm_generated_university.in_(
		[
			"Georgetown University",
			"Massachusetts Institute of Technology",
			"Stanford University",
			"Carnegie Mellon University",
		]
	)
	statement = select(func.count()).select_from(Applicant).where(
		and_(
			Applicant.term == "Fall 2026",
			Applicant.status.ilike("Accepted%"),
			Applicant.llm_generated_program == "Computer Science",
			Applicant.degree == "PhD",
			universities,
		)
	)
	return session.scalar(statement)

def question_10(session):
	# University with highest applicant count in Fall 2026 PhD Computer Science
	statement = (
		select(Applicant.llm_generated_university, func.count().label("applicant_count"))
		.where(
			and_(
				Applicant.term == "Fall 2026",
				Applicant.degree == "PhD",
				Applicant.llm_generated_program == "Computer Science",
			)
		)
		.group_by(Applicant.llm_generated_university)
		.order_by(func.count().desc(), Applicant.llm_generated_university)
		.limit(1)
	)
	return session.execute(statement).all()
	
def question_11(session):
	# Average scores for Fall 2026 Master's Computer Science applicants.
	statement = select(
		func.avg(Applicant.gpa),
		func.avg(Applicant.gre),
		func.avg(Applicant.gre_v),
		func.avg(Applicant.gre_aw),
	).where(
		and_(
			Applicant.term == "Fall 2026",
			Applicant.degree.ilike("%master%"),
			Applicant.program.ilike("%Computer Science%"),
		)
	)
	values = session.execute(statement).one()
	return tuple(_average(value) for value in values)

def main():
	with Session() as session:
		original_count = question_8(session)
		llm_count = question_9(session)
		print(f"Fall 2026 Applicant Count: {question_1(session)}")
		print(f"Average GPA American: {question_4(session)}")
		print(f"Percent accepted Fall 2025: {question_5(session)}%")
		print(f"Fall 2026 accepted CS PhD Count: {original_count}")
		print(f"Fall 2026 accepted CS PhD LLM Count: {llm_count}")
		print(f"Q9 Difference: {llm_count - original_count:+d}")
		print(f"University with highest applicant count: {question_10(session)}")
		print(f"Fall 2026 CS Masters Averages: {question_11(session)}")

if __name__ == "__main__":
	main()

# how to run the queries using SQLAlchemy ORM
# 1. Set the DATABASE_URL environment variable to point to your PostgreSQL database.
# 2. Run this script using Python: python orm_queries.py
# 3. The script will output the results of the queries defined in this module.
"""SQLAlchemy query functions for the Grad Cafe analysis questions.

Each question accepts an active session and returns one analysis result. The
``main`` function prints a report using the shared session factory from ``models``.
"""

from sqlalchemy import and_, func, or_, select
from models import Applicant, Session


def _average(value):
	"""Round a non-null SQL aggregate to two decimal places.

	Args:
		value (float | decimal.Decimal | None): Aggregate result from SQLAlchemy.

	Returns:
		float | None: Rounded value, preserving ``None`` for empty aggregates.
	"""
	return round(value, 2) if value is not None else None


def question_1(session):
	"""Count applicants whose term is Fall 2026.

	Args:
		session (sqlalchemy.orm.Session): Active ORM session.

	Returns:
		int: Number of matching applicant rows.
	"""
	statement = select(func.count()).select_from(Applicant).where(
		Applicant.term == "Fall 2026"
	)
	return session.scalar(statement)


def question_4(session):
	"""Calculate average GPA for American Fall 2026 applicants.

	Args:
		session (sqlalchemy.orm.Session): Active ORM session.

	Returns:
		float | None: GPA rounded to two decimals, or ``None`` without values.
	"""
	statement = select(func.avg(Applicant.gpa)).where(
		and_(
			Applicant.term == "Fall 2026",
			Applicant.us_or_international == "American",
			Applicant.gpa.is_not(None),
		)
	)
	return _average(session.scalar(statement))


def question_5(session):
	"""Calculate the accepted percentage for Fall 2025 entries.

	Args:
		session (sqlalchemy.orm.Session): Active ORM session.

	Returns:
		float | None: Accepted percentage rounded to two decimals, or ``None``
		when the term has no entries.
	"""
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
	"""Count accepted Fall 2026 CS PhD rows at selected universities.

	Args:
		session (sqlalchemy.orm.Session): Active ORM session.

	Returns:
		int: Number of rows matching the original program text.
	"""
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
	"""Count the Question 8 cohort using normalized LLM fields.

	Args:
		session (sqlalchemy.orm.Session): Active ORM session.

	Returns:
		int: Number of rows matching normalized program and university fields.
	"""
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
	"""Find the leading normalized university for Fall 2026 CS PhD applicants.

	Args:
		session (sqlalchemy.orm.Session): Active ORM session.

	Returns:
		list[sqlalchemy.engine.Row]: Zero or one university/count result row.
	"""
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
	"""Calculate average scores for Fall 2026 Master's CS applicants.

	Args:
		session (sqlalchemy.orm.Session): Active ORM session.

	Returns:
		tuple[float | None, float | None, float | None, float | None]: Rounded
		GPA, GRE, verbal, and analytical-writing averages.
	"""
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
	"""Print the ORM analysis report using the configured session factory.

	Returns:
		None
	"""
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

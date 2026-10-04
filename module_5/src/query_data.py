"""
Module 3: Query Applicant Data from Database
Provides functionality to query applicant data from a PostgreSQL database.
"""

import psycopg
from create_database import database_url_from_environment

# Ensure the DATABASE_URL environment variable is set.
connection = psycopg.connect(database_url_from_environment())

# Execute queries to answer the questions defined above
with connection.cursor() as cur:
    # Question 1: Count of Fall 2026 applicants
    cur.execute("""
        SELECT COUNT(*) FROM applicants
            WHERE term = 'Fall 2026'
    """)
    fall_2026_applicant_count = cur.fetchone()[0]

    # Question 2: Percentage of international students among classified entries
    cur.execute("""
        SELECT ROUND(
            100.0 * COUNT(*) FILTER (WHERE us_or_international = 'International')
            / NULLIF(COUNT(*) FILTER (WHERE NULLIF(TRIM(us_or_international), '') IS NOT NULL), 0),
            2
        )
        FROM applicants
    """)
    percent_international = cur.fetchone()[0]

    # Question 3: Average GPA, GRE Quantitative, GRE Verbal, and GRE Analytical
    # Writing scores of applicants who provide each metric
    cur.execute("""
        SELECT
            ROUND(AVG(CASE WHEN gpa IS NOT NULL THEN gpa END)::numeric, 2),
            ROUND(AVG(CASE WHEN gre IS NOT NULL THEN gre END)::numeric, 2),
            ROUND(AVG(CASE WHEN gre_v IS NOT NULL THEN gre_v END)::numeric, 2),
            ROUND(AVG(CASE WHEN gre_aw IS NOT NULL THEN gre_aw END)::numeric, 2)
        FROM applicants
    """)
    (
        average_gpa,
        average_gre_quantitative,
        average_gre_verbal,
        average_gre_analytical_writing,
    ) = cur.fetchone()

    # Question 4: What is the average GPA of American applicants who applied for Fall 2026?
    cur.execute("""
        SELECT ROUND(AVG(CASE WHEN gpa IS NOT NULL THEN gpa END)::numeric, 2)
        FROM applicants
        WHERE term = 'Fall 2026' AND us_or_international = 'American'
    """)
    average_gpa_american = cur.fetchone()[0]

    # Question 5: What percentage of Fall 2025 entries are acceptances?
    cur.execute("""
        SELECT ROUND(100.0 * SUM(CASE WHEN status ILIKE 'Accepted%' THEN 1 ELSE 0 END) / COUNT(*), 2)
        FROM applicants
        WHERE term = 'Fall 2025'
    """)
    percent_accepted_fall_2025 = cur.fetchone()[0]

    # Question 6. What is the average GPA of accepted applicants who applied for Fall 2026?"
    cur.execute("""
        SELECT ROUND(AVG(CASE WHEN gpa IS NOT NULL THEN gpa END)::numeric, 2)
        FROM applicants
        WHERE term = 'Fall 2026' AND status ILIKE 'Accepted%'
    """)
    average_gpa_accepted_fall_2026 = cur.fetchone()[0]

    # Question 7: How many entries are from applicants who applied to Johns Hopkins
    # University for a master's degree in Computer Science?
    cur.execute("""
        SELECT COUNT(*)
        FROM applicants
                WHERE (program ILIKE '%Johns Hopkins University%' OR program ILIKE '%JHU%')
                    AND program ILIKE '%Computer Science%'
                    AND degree ILIKE '%master%'
    """)
    johns_hopkins_cs_masters_count = cur.fetchone()[0]

    # Question 8: How many Fall 2026 entries are acceptances from applicants applying
    # for a PhD in Computer Science at one of the following universities?
    cur.execute("""
        SELECT COUNT(*)
        FROM applicants
        WHERE term = 'Fall 2026'
          AND status ILIKE 'Accepted%'
          AND program ILIKE '%Computer Science%'
          AND (
              program ILIKE '%Georgetown University%'
              OR program ILIKE '%Massachusetts Institute of Technology%'
              OR program ILIKE '%MIT%'
              OR program ILIKE '%Stanford University%'
              OR program ILIKE '%Carnegie Mellon University%'
          )
          AND degree = 'PhD'
    """)
    fall_2026_accepted_cs_phd_count = cur.fetchone()[0]

    # Question 9: Repeat Question 8, but identify the university and program using
    # llm_generated_program and llm_generated_university instead of the original
    # downloaded university/program information.
    cur.execute("""
        SELECT COUNT(*)
        FROM applicants
        WHERE term = 'Fall 2026'
          AND status ILIKE 'Accepted%'
          AND llm_generated_program = 'Computer Science'
          AND llm_generated_university IN ('Georgetown University', 'Massachusetts Institute of Technology', 'Stanford University', 'Carnegie Mellon University')
          AND degree = 'PhD'
    """)
    fall_2026_accepted_cs_phd_llm_count = cur.fetchone()[0]

    # Question 10: Which university has the highest number of Fall 2026 PhD
    # Computer Science applicants?
    cur.execute("""
        SELECT llm_generated_university, COUNT(*) AS applicant_count
        FROM applicants
        WHERE term = 'Fall 2026'
          AND degree = 'PhD'
          AND llm_generated_program = 'Computer Science'
        GROUP BY llm_generated_university
        ORDER BY applicant_count DESC, llm_generated_university
        LIMIT 1
    """)
    fall_2026_cs_phd_university_counts = cur.fetchall()

    # Question 11: What are the average scores for Fall 2026 Master's Computer Science applicants?
    cur.execute("""
        SELECT
            ROUND(AVG(gpa)::numeric, 2) AS avg_gpa,
            ROUND(AVG(gre)::numeric, 2) AS avg_gre,
            ROUND(AVG(gre_v)::numeric, 2) AS avg_gre_v,
            ROUND(AVG(gre_aw)::numeric, 2) AS avg_gre_aw
        FROM applicants
        WHERE term = 'Fall 2026'
          AND degree ILIKE '%master%'
          AND program ILIKE '%Computer Science%'
    """)
    (
        fall_2026_cs_masters_average_gpa,
        fall_2026_cs_masters_average_gre,
        fall_2026_cs_masters_average_gre_v,
        fall_2026_cs_masters_average_gre_aw,
    ) = cur.fetchone()

    q9_difference = fall_2026_accepted_cs_phd_llm_count - fall_2026_accepted_cs_phd_count

    print(f"Q1: Fall 2026 applicant count: {fall_2026_applicant_count}")

    print(f"Q2: Percent international: {percent_international}%")

    print(f"Q3-1. Average GPA: {average_gpa}")
    print(f"Q3-2. Average GRE Quantitative: {average_gre_quantitative}")
    print(f"Q3-3. Average GRE Verbal: {average_gre_verbal}")
    print(f"Q3-4. Average GRE Analytical Writing: {average_gre_analytical_writing}")

    print(f"Q4: Average GPA (American applicants): {average_gpa_american}")
    print(f"Q5: Percent accepted Fall 2025: {percent_accepted_fall_2025}%")
    print(f"Q6: Average GPA accepted Fall 2026: {average_gpa_accepted_fall_2026}")
    print(f"Q7: Johns Hopkins CS Master's count: {johns_hopkins_cs_masters_count}")
    print(f"Q8: Fall 2026 accepted CS PhD count: {fall_2026_accepted_cs_phd_count}")

    print(f"Q9: Fall 2026 accepted CS PhD LLM count: {fall_2026_accepted_cs_phd_llm_count}")
    print(f"\tQ9-1. Original-field count: {fall_2026_accepted_cs_phd_count}")
    print(f"\tQ9-2. LLM-field count: {fall_2026_accepted_cs_phd_llm_count}")
    print(f"\tQ9-3. Difference: {q9_difference:+d}")

    print(
        "Q10: University with highest applicant count in Fall 2026 PhD Computer "
        f"Science: {fall_2026_cs_phd_university_counts}"
    )
    print(f"\tUniversity: {fall_2026_cs_phd_university_counts[0][0]}")
    print(f"\tApplicant count: {fall_2026_cs_phd_university_counts[0][1]}")

    print("Q11: Fall 2026 CS Master's average statistics")
    print(f"\tAverage GPA: {fall_2026_cs_masters_average_gpa}")
    print(f"\tAverage GRE Quantitative: {fall_2026_cs_masters_average_gre}")
    print(f"\tAverage GRE Verbal: {fall_2026_cs_masters_average_gre_v}")
    print(f"\tAverage GRE Analytical Writing: {fall_2026_cs_masters_average_gre_aw}")
    connection.commit()
    connection.close()

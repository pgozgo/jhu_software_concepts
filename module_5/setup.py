"""Setuptools configuration for the Module 5 Grad Cafe application."""

from setuptools import find_namespace_packages, setup


setup(
    name="jhu-gradcafe-module5",
    version="0.1.0",
    description="Flask application and ETL tools for Grad Cafe applicant analysis",
    package_dir={"": "src"},
    packages=find_namespace_packages(where="src", include=["app*"]),
    py_modules=[
        "clean_data",
        "create_database",
        "load_data",
        "models",
        "orm_queries",
        "pull_data",
        "query_data",
        "scrape",
    ],
    package_data={
        "app": ["templates/*.html", "static/*"],
    },
    data_files=[
        (
            "share/jhu-gradcafe-module5",
            ["src/llm_extend_applicant_data.json"],
        ),
    ],
    python_requires=">=3.10",
    install_requires=[
        "Flask>=2.3,<4",
        "SQLAlchemy>=2.0,<3",
        "psycopg[binary]>=3.1,<4",
        "psycopg2-binary>=2.9,<3",
        "python-dotenv>=1.0,<2",
        "beautifulsoup4>=4.12.0",
        "urllib3>=2.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7,<10",
            "pytest-cov>=4,<8",
            "Sphinx>=7.2,<9",
            "sphinx-rtd-theme>=2,<4",
            "pylint>=3",
            "pydeps>=1",
        ],
    },
)

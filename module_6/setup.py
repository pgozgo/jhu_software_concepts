"""Setuptools configuration for the Module 6 web and worker services."""

from setuptools import find_packages, setup


setup(
    name="jhu-gradcafe-module6",
    version="0.1.0",
    description="Containerized Grad Cafe applicant dashboard and ETL worker",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    py_modules=["task_queue"],
    package_data={"web.app": ["templates/*.html", "static/*"]},
    python_requires=">=3.11",
    install_requires=[
        "beautifulsoup4>=4.12,<5",
        "Flask>=3.0,<4",
        "pika>=1.3,<2",
        "psycopg[binary]>=3.2,<4",
        "urllib3>=2.0,<3",
    ],
)

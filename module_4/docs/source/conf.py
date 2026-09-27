# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "Module 4 - The Grad Cafe Analytics"
copyright = "2026, Sean Bae"
author = "Sean Bae"
release = "1.0"

import os
import sys

module_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
source_root = os.path.join(module_root, "src")
sys.path.insert(0, source_root)
sys.path.insert(1, module_root)

# ORM modules are imported by autodoc; SQLite is only a no-server docs fallback.
os.environ.setdefault("DATABASE_URL", "sqlite://")

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
	"sphinx.ext.autodoc",
	"sphinx.ext.viewcode",
	"sphinx.ext.napoleon",
]

templates_path = ["_templates"]
exclude_patterns = []
autodoc_typehints = "description"

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]

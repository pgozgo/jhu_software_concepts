# Module 5 Test Workflow

## At a glance

```mermaid
flowchart TD
    A[GitHub event] --> B[Checkout repository]
    B --> C[Start PostgreSQL service]
    C --> D[Set database environment]
    D --> E[Install Python dependencies]
    E --> F[Run pytest]
    F --> G[Read pytest configuration]
    G --> H[Collect unittest tests]
    H --> I[Run marked application tests]
    I --> J[Measure source coverage]
    J --> K{Coverage reaches 100 percent}
    K -- No --> L[Fail and show missing lines]
    K -- Yes --> M[Pass test job]
    J --> N[Print coverage report]
    N --> O[Write coverage summary]
```

## Step-to-code map

| Workflow stage | File or function used |
| --- | --- |
| Module 5 CI trigger, Python/PostgreSQL setup, dependency install, tests, lint, and graph artifact | `.github/workflows/ci.yml` at repository root |
| Test paths, import paths, markers, coverage target, report format, and 100% threshold | `module_5/pytest.ini` |
| Web route and page checks | `tests/test_flask_page.py`: `TestAnalysisPage`; exercises `app.app.index()` |
| Button state checks | `tests/test_buttons.py`: `TestAnalysisButtons`; exercises `app.app.pull_data()` and `app.app.update_analysis()` |
| Rendered analysis labels and ORM/raw SQL questions | `tests/test_analysis_format.py`: `TestAnalysisFormat`, `TestOrmQueries`, `TestRawQueries`; exercises `orm_queries.question_*()`, `orm_queries.main()`, and `query_data.py` |
| Schema, loader, cleaner, database creator, and pull helpers | `tests/test_db_insert.py`: `TestDatabaseInsert`, `TestCleanData`, `TestCreateDatabase`, `TestLoadData`, `TestPullData`, `TestPullRecordDeduplication` |
| Pull/update/render and scraper behavior | `tests/test_integration_end_to_end.py`: `TestPullUpdateRender`, `TestScraper`; exercises `pull_data.main()`, `scrape.GradCafeScraper`, `scrape.scrape_data()`, and `scrape.save_data()` |
| Coverage calculation and gate | pytest-cov options in `module_5/pytest.ini`, applied to all Python files under `module_5/src` |
| Saved terminal output | `module_5/coverage_summary.txt`, written by `tee` in CI or `Tee-Object` locally |

## What pytest does

`module_5/pytest.ini` sets the test directory and import paths, registers the five markers, and adds the coverage options:

- `--cov=src` measures Python code under `src` when pytest is run from `module_5`.
- `--cov-report=term-missing` prints statement counts, coverage, and any missed lines.
- `--cov-fail-under=100` makes pytest return a failing status below 100%.

Tests use `unittest.TestCase`; pytest discovers and runs those test classes. Markers classify tests by focus: `web`, `buttons`, `analysis`, `db`, and `integration`.

## Markers

Markers label related tests so pytest can run a focused group with `-m`:

- `web`: Flask route registration and analysis-page rendering.
- `buttons`: Pull Data and Update Analysis actions, including busy-state behavior and URL deduplication.
- `analysis`: Rendered labels/percentage formatting and raw SQL or ORM analysis queries.
- `db`: PostgreSQL schema/insertion tests and database utilities such as cleaning and loading.
- `integration`: End-to-end pull/update/render behavior and scraper parsing or retrieval paths.

For example, `-m web` runs tests marked `web`; `-m "db or integration"` runs either database or end-to-end tests. A test class can carry more than one marker when it covers multiple areas.

## Fresh Install

For commands that use `Set-Location .\module_5`, start PowerShell from the
repository root (the folder containing `module_5`). The install commands below
then run from the `module_5` directory. Both methods install the dependencies from
`requirements.txt` and install Module 5 in editable mode so its imports work
consistently from the project directory and in tools such as tests and Flask.

### Install with pip

```powershell
Set-Location .\module_5
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

### Install with uv

Install `uv` first if it is not already available. Then run:

```powershell
Set-Location .\module_5
uv venv .venv
uv pip sync --python .venv\Scripts\python.exe requirements.txt
uv pip install --python .venv\Scripts\python.exe --no-deps -e .
```

`uv pip sync` makes the environment's installed packages match
`requirements.txt`, removing packages not listed there. The final editable
install adds this project itself to the environment.

### Run the app

Configure PostgreSQL using the variables in `.env.example`, then copy it to
`.env` and set local values. Do not commit `.env`. From `module_5`, start Flask:

```powershell
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m flask --app app.app run
```

Open <http://127.0.0.1:5000/analysis>. The PostgreSQL service and database
must be available for the analysis page to load its query results.

## Sphinx Documentation

The Sphinx source is in [`docs/source`](docs/source). It includes an overview and
setup guide, a web/ETL/database architecture page, a testing guide, and an API
reference generated with autodoc and Napoleon. The raw SQL script
(`src/query_data.py`) is included as source because it connects to PostgreSQL and
executes queries when imported.

To run PostgreSQL-backed tests, create the disposable test database, set
`TEST_DATABASE_URL`, and run pytest as shown below. More detail is in
[Running PostgreSQL tests](#running-postgresql-tests).

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -U postgres -h localhost -c "CREATE DATABASE gradcafe_test"

Set-Location .\module_5
$env:TEST_DATABASE_URL = "postgresql://postgres:YOURPASSWORD@localhost:5432/gradcafe_test"
.\.venv\Scripts\python.exe -m pytest 2>&1 | Tee-Object -FilePath coverage_summary.txt
```

Build or refresh the HTML documentation with the Sphinx make helper. In PowerShell,
run the Windows batch file from the docs directory:

```powershell
cd module_5/docs
.\make.bat html
```

On Linux or macOS, run `make html` from `module_5/docs`. Both commands write the
site to `module_5/docs/build/html/`.

For a warning-strict build from the repository root, run:

```powershell
python -m sphinx -b html -W module_5/docs/source module_5/docs/build/html
```

The local landing page is [`docs/build/html/index.html`](docs/build/html/index.html).
The root [`.readthedocs.yaml`](../.readthedocs.yaml) configures the Read the Docs
build. Once this repository is registered as a Read the Docs project, the published
site is available at https://module-4-the-grad-cafe-analytics-doc-test.readthedocs.io/en/latest/

## Local run

Run this PowerShell block from `module_5` to run pytest with its configuration
and replace the saved coverage report:

```powershell
Set-Location .\module_5
.\.venv\Scripts\python.exe -m pytest 2>&1 |
    Tee-Object -FilePath coverage_summary.txt
```

Pytest prints the summary and `Tee-Object` replaces `coverage_summary.txt` with
the same output. The most recent local run without `TEST_DATABASE_URL` reported
`47 passed, 3 skipped` with 100% source coverage. The three database-dependent
tests skip when that variable is unset.

To run one marker group locally, append a marker expression, for example:

```powershell
python -m pytest -m web
```

## Pylint

Pylint is listed in `requirements.txt` and is run only on the code in `src`. From `module_5`, with the module 5 environment:

```powershell
.\.venv\Scripts\python.exe -m pylint src --fail-under=10
```

To print progress while Pylint runs, add `--verbose`. It lists each file as it is parsed and ends with `Checked 9 files/modules`:

```powershell
.\.venv\Scripts\python.exe -m pylint src --verbose --reports=y --fail-under=10
```

The expected result is `Your code has been rated at 10.00/10` with no messages;
`--fail-under=10` makes Pylint return a failure if the score is lower. Pylint is
run with its default configuration. Three kinds of inline `# pylint: disable=...`
comments remain, each with a reason in the code:

- `not-callable` in `orm_queries.py`: a known false positive for SQLAlchemy's dynamic `func` namespace.
- `protected-access` in `pull_data.py` and `scrape.py`: the pull script and the module-level scrape function reuse the scraper's private helper methods.
- `too-many-locals`, `too-many-branches`, and `too-many-statements` on `parse_admissions_data` and `scrape_data` in `scrape.py`, plus `broad-exception-caught` where network failures are deliberately tolerated.

## Python dependency graph

Install `pydeps` into the Module 5 virtual environment. Graphviz must also be
installed separately; its `dot.exe` executable is required to render the graph.
From the `module_5` directory, run:

```powershell
.\.venv\Scripts\python.exe -m pip install pydeps
$env:Path = "C:\Program Files (x86)\Graphviz\bin;$env:Path"
dot -V
```

If Graphviz was installed in a different location, use that installation's
`bin` directory in `PATH`. `dot -V` should print the Graphviz version. Then
generate an SVG graph for the Flask app module:

```powershell
Set-Location .\src\app
& ..\..\.venv\Scripts\pydeps.exe app.py --noshow -T svg -o dependency.svg
```

The graph is saved to `module_5\src\app\dependency.svg`. Open it with:

```powershell
Invoke-Item .\dependency.svg
```

Run the `pydeps` command from `src\app` so it analyzes `app.py` in that
directory. Keep the Graphviz `PATH` update and the `pydeps` command in the same
PowerShell session.
The repository's `.github/workflows/ci.yml` also generates this SVG on each
push, pull request, or manual workflow run and uploads it as the
`module-5-dependency-graph` artifact.

## Snyk dependency scan

After installing and authenticating the Snyk CLI, run the dependency scan from
`module_5` with the project virtual environment selected:

```powershell
$snyk = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Snyk.Snyk_Microsoft.Winget.Source_8wekyb3d8bbwe\snyk-win.exe"
$python = (Resolve-Path '.\.venv\Scripts\python.exe').Path
$env:VIRTUAL_ENV = (Resolve-Path '.\.venv').Path
$env:Path = "$(Split-Path $python);$env:Path"
& $snyk test --command="$python"
```

The latest recorded scan tested 54 dependencies and reported zero known
vulnerable paths. Results can change as dependency advisories are updated. The
scan summary is saved in [`snyk-analysis.png`](snyk-analysis.png).

`snyk code test .\src` is a separate source-code analysis scan. It could not be
run for this project because Snyk Code is not enabled for the current Snyk
organization (`pgozgo`, error `SNYK-CODE-0005`). An organization administrator
must enable the feature or select an organization where it is enabled.

## Database and PostgreSQL setup

### Database credentials and least-privilege roles

The application reads `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and
`DB_PASSWORD` from the process environment or a local `.env` file. Copy
`.env.example` to `.env` and replace the placeholders with local values; `.env`
is ignored by Git. Do not put real passwords in source files or commit `.env`.
An explicitly set `DATABASE_URL` is honored as a complete connection string;
otherwise, the app builds one from the `DB_*` variables.

The Flask app and ETL scripts use the runtime role in `DB_USER` and
`DB_PASSWORD`. It should not be a superuser or table owner and must not receive
`CREATE`, `ALTER`, or `DROP` privileges. The pull/clean/reset operations need
`SELECT`, `INSERT`, `UPDATE`, `TRUNCATE`, and sequence `USAGE` on the
`applicants` table. An administrator can create the roles and grant only those
permissions (use `\password` in `psql` to set each password interactively):

```sql
CREATE DATABASE gradcafe;
CREATE ROLE gradcafe_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE gradcafe_setup LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE gradcafe_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
GRANT CONNECT ON DATABASE gradcafe TO gradcafe_app, gradcafe_setup;
\password gradcafe_app
\password gradcafe_setup
\connect gradcafe
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO gradcafe_app;
GRANT USAGE, CREATE ON SCHEMA public TO gradcafe_setup;
```

Set `DB_SETUP_USER` and `DB_SETUP_PASSWORD` only when running
`src/create_database.py` to initialize the table. Keep those setup credentials
separate from the runtime role; never use them in the Flask app. From
`module_5`, run `.\.venv\Scripts\python.exe src\create_database.py`. After the
table exists, a database administrator should grant the runtime permissions,
transfer ownership to the non-login `gradcafe_owner` role, and disable setup
access:

```sql
GRANT SELECT, INSERT, UPDATE, TRUNCATE ON TABLE public.applicants TO gradcafe_app;
GRANT USAGE ON SEQUENCE public.applicants_p_id_seq TO gradcafe_app;
GRANT CREATE ON SCHEMA public TO gradcafe_owner;
ALTER TABLE public.applicants OWNER TO gradcafe_owner;
ALTER SEQUENCE public.applicants_p_id_seq OWNER TO gradcafe_owner;
REVOKE CREATE ON SCHEMA public FROM gradcafe_setup;
REVOKE CREATE ON SCHEMA public FROM gradcafe_owner;
REVOKE CONNECT ON DATABASE gradcafe FROM gradcafe_setup;
ALTER ROLE gradcafe_setup NOLOGIN;
```

Existing tables may need the administrator to grant the listed table and
sequence permissions explicitly.

Create a local environment file in PowerShell with:

```powershell
Copy-Item .env.example .env
```

Edit `.env` locally, then start the app or scripts normally. `python-dotenv`
loads this file; variables already set in the process environment take
precedence.

### Running PostgreSQL tests

The `db` and `integration` tests use `TEST_DATABASE_URL`. Without it, those tests call `self.skipTest()` and are reported as skipped. The GitHub Actions workflow provides a PostgreSQL 16 service and sets both database URLs, allowing those tests to run in CI. The test setup uses dedicated test schemas; point `TEST_DATABASE_URL` only at a disposable test database.

Without `TEST_DATABASE_URL`, the latest local run reports `47 passed, 3 skipped`.
The skipped tests are:

- `TestDatabaseInsert::test_failed_batch_insert_rolls_back`
- `TestDatabaseInsert::test_insert_schema`
- `TestPullUpdateRender::test_pull_update_render`

To run them locally, create an empty PostgreSQL database and set the variable before running pytest from `module_5`. On Windows, `psql` is usually not on the PATH, so call it by its full path (adjust the version folder, e.g. `18`); it prompts for the `postgres` password. Replace `YOURPASSWORD` with that password:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -U postgres -h localhost -c "CREATE DATABASE gradcafe_test"

Set-Location .\module_5
$env:TEST_DATABASE_URL = "postgresql://postgres:YOURPASSWORD@localhost:5432/gradcafe_test"
.\.venv\Scripts\python.exe -m pytest 2>&1 | Tee-Object -FilePath coverage_summary.txt
```

With the database configured, those database-dependent tests run instead of
skipping. If the database already exists, the `CREATE DATABASE` command errors
and you can continue.

Alternatively, start the same PostgreSQL 16 image that CI uses with Docker:

```powershell
docker run -d --name gradcafe-test -p 5432:5432 -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=gradcafe_test postgres:16
$env:TEST_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/gradcafe_test"
```
The variable applies only to the current PowerShell session. If `python` resolves to a different environment, call `.\.venv\Scripts\python.exe` directly as shown above.

## Successful workflow evidence

The Module 5 workflow is at repository root in `.github/workflows/ci.yml`.
GitHub runs it after a push or pull request, or when manually dispatched. It installs Module 5, runs pytest, enforces the 10/10 Pylint threshold, generates the dependency graph, and uploads the SVG as a workflow artifact. The separate `.github/workflows/tests.yml` workflow continues to test Module 4.
After a successful run, capture its green success status from the GitHub Actions page as `actions_success.png`

"""Unit tests for the Module 6 container service boundaries."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, call, patch

from psycopg import sql
import psycopg
from db import load_data as load_data_module
from db.load_data import (
    ANALYTICS_VIEW_SQL,
    INGESTION_WATERMARKS_SQL,
    INSERT_SQL,
    applicant_values,
    load_data_to_db,
)
from web.app.app import clamp_query_limit, create_app, run_analysis_queries
from web.publisher import _open_channel, publish_task
from worker.consumer import (
    handle_scrape_new_data,
    main,
    process_delivery,
)
from task_queue import EXCHANGE, QUEUE, ROUTING_KEY
from worker.etl.incremental_scraper import fetch_records_after_watermark


class ContainerServiceTests(unittest.TestCase):
    """Exercise initialization, task publishing, and worker transactions."""

    def test_applicant_values_normalizes_json_fields(self):
        values = applicant_values({
            "program": "Computer Science, Example University",
            "date_added": "Added on Sep 12, 2026",
            "GPA": "3.87 / 4.00",
            "GRE-V": "160",
            "Degree": "PhD",
        })

        self.assertEqual(values["gpa"], 3.87)
        self.assertEqual(values["gre_v"], 160.0)
        self.assertEqual(values["degree"], "PhD")
        self.assertEqual(values["date_added"].isoformat(), "2026-09-12")
        self.assertIn("ON CONFLICT (\"url\") DO NOTHING", INSERT_SQL.as_string())
        self.assertIn("%(program)s", INSERT_SQL.as_string())

    def test_loader_initializes_watermark_and_analytics_views(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "applicants.json"
            data_file.write_text("[]", encoding="utf-8")
            connection = MagicMock()
            cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = (True,)
            with patch("db.load_data.psycopg.connect", return_value=connection):
                self.assertEqual(load_data_to_db(data_file, "postgresql://unused"), 0)

        executed_sql = [entry.args[0] for entry in cursor.execute.call_args_list]
        self.assertIn(INGESTION_WATERMARKS_SQL, executed_sql)
        for statement in ANALYTICS_VIEW_SQL.values():
            self.assertIn(statement, executed_sql)
        self.assertTrue(any(
            statement.as_string().startswith("REFRESH MATERIALIZED VIEW")
            for statement in executed_sql
        ))

    def test_loader_populates_an_empty_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "applicants.json"
            data_file.write_text(json.dumps([{"url": "https://example.test/1"}]), encoding="utf-8")
            connection = MagicMock()
            db_connection = connection.__enter__.return_value
            cursor = db_connection.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = (False,)
            cursor.rowcount = 1
            with patch("db.load_data.psycopg.connect", return_value=connection):
                loaded = load_data_to_db(data_file, "postgresql://unused")

        self.assertEqual(loaded, 1)
        cursor.executemany.assert_called_once()

    def test_open_channel_declares_durable_task_topology(self):
        connection = MagicMock()
        channel = connection.channel.return_value
        pika = SimpleNamespace(
            URLParameters=MagicMock(return_value="rabbit-params"),
            BlockingConnection=MagicMock(return_value=connection),
        )
        with patch.dict(os.environ, {"RABBITMQ_URL": "amqp://test/test"}):
            with patch.dict("sys.modules", {"pika": pika}):
                opened_connection, opened_channel = _open_channel()

        self.assertIs(opened_connection, connection)
        self.assertIs(opened_channel, channel)
        pika.BlockingConnection.assert_called_once_with("rabbit-params")
        channel.exchange_declare.assert_called_once_with(
            exchange="tasks",
            exchange_type="direct",
            durable=True,
        )
        channel.queue_declare.assert_called_once_with(queue="tasks_q", durable=True)
        channel.queue_bind.assert_called_once_with(
            exchange="tasks",
            queue="tasks_q",
            routing_key="tasks",
        )
        self.assertEqual((EXCHANGE, QUEUE, ROUTING_KEY), ("tasks", "tasks_q", "tasks"))

    def test_publish_task_sends_compact_persistent_utc_message(self):
        connection = MagicMock()
        channel = MagicMock()
        pika = SimpleNamespace(
            BasicProperties=lambda **kwargs: SimpleNamespace(**kwargs),
        )
        headers = {"request_id": "abc"}
        with patch("web.publisher._open_channel", return_value=(connection, channel)):
            with patch.dict("sys.modules", {"pika": pika}):
                publish_task("scrape_new_data", {"max_pages": 2}, headers)

        published = channel.basic_publish.call_args.kwargs
        message = json.loads(published["body"])
        self.assertEqual(published["exchange"], "tasks")
        self.assertEqual(published["routing_key"], "tasks")
        self.assertFalse(published["mandatory"])
        self.assertEqual(message["kind"], "scrape_new_data")
        self.assertEqual(message["payload"], {"max_pages": 2})
        timestamp = datetime.fromisoformat(message["ts"])
        self.assertEqual(timestamp.utcoffset(), timezone.utc.utcoffset(timestamp))
        self.assertEqual(published["body"], json.dumps(
            message,
            separators=(",", ":"),
        ).encode("utf-8"))
        self.assertEqual(published["properties"].delivery_mode, 2)
        self.assertEqual(published["properties"].headers, headers)
        connection.close.assert_called_once_with()

    def test_publish_task_closes_connection_and_propagates_publish_errors(self):
        connection = MagicMock()
        channel = MagicMock()
        channel.basic_publish.side_effect = RuntimeError("broker unavailable")
        pika = SimpleNamespace(
            BasicProperties=lambda **kwargs: SimpleNamespace(**kwargs),
        )
        with patch("web.publisher._open_channel", return_value=(connection, channel)):
            with patch.dict("sys.modules", {"pika": pika}):
                with self.assertRaisesRegex(RuntimeError, "broker unavailable"):
                    publish_task("scrape_new_data")

        connection.close.assert_called_once_with()

    def test_open_channel_closes_connection_when_topology_setup_fails(self):
        connection = MagicMock()
        connection.channel.side_effect = RuntimeError("channel unavailable")
        pika = SimpleNamespace(
            URLParameters=MagicMock(return_value="rabbit-params"),
            BlockingConnection=MagicMock(return_value=connection),
        )
        with patch.dict(os.environ, {"RABBITMQ_URL": "amqp://test/test"}):
            with patch.dict("sys.modules", {"pika": pika}):
                with self.assertRaisesRegex(RuntimeError, "channel unavailable"):
                    _open_channel()

        connection.close.assert_called_once_with()

    def test_scraper_stops_at_watermark_and_returns_max_new_id(self):
        scraper = MagicMock()
        scraper._check_robots_permission.return_value = True
        scraper._build_url.return_value = "https://example.test/results"
        scraper._fetch_html.return_value = "<html>results</html>"
        scraper.parse_admissions_data.return_value = [
            {"url": "https://example.test/result/105"},
            {"url": "https://example.test/result/104"},
            {"url": "https://example.test/result/100"},
            {"url": "https://example.test/result/99"},
        ]

        records, max_seen = fetch_records_after_watermark(
            scraper,
            last_seen=100,
            max_pages=3,
        )

        self.assertEqual([row["url"] for row in records], [
            "https://example.test/result/105",
            "https://example.test/result/104",
        ])
        self.assertEqual(max_seen, 105)
        scraper._fetch_html.assert_called_once_with("https://example.test/results")

    def test_scrape_handler_reads_and_advances_watermark(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.fetchone.return_value = ("100",)
        records = [{
            "url": "https://example.test/result/105",
            "program": "Computer Science, Example University",
        }]

        with patch("worker.consumer.GradCafeScraper"):
            with patch(
                "worker.consumer.fetch_records_after_watermark",
                return_value=(records, 105),
            ) as fetch:
                inserted = handle_scrape_new_data(connection, {"max_pages": 2})

        self.assertEqual(inserted, 1)
        fetch.assert_called_once()
        self.assertEqual(fetch.call_args.args[1], 100)
        cursor.executemany.assert_called_once()
        self.assertIn(
            call(
                unittest.mock.ANY,
                ("gradcafe", "105"),
            ),
            cursor.execute.call_args_list,
        )
        self.assertTrue(any(
            entry.args[0].as_string().startswith("REFRESH MATERIALIZED VIEW")
            for entry in cursor.execute.call_args_list
        ))
        cursor.close.assert_called_once_with()

    def test_delivery_commits_before_acknowledging(self):
        events = []

        class Transaction:
            def __enter__(self):
                events.append("transaction-start")

            def __exit__(self, exc_type, exc, traceback):
                events.append("commit" if exc_type is None else "rollback")

        class DatabaseConnection:
            def transaction(self):
                return Transaction()

            def __enter__(self):
                events.append("connection-open")
                return self

            def __exit__(self, exc_type, exc, traceback):
                events.append("connection-close")

        class Channel:
            def basic_ack(self, **kwargs):
                events.append(("ack", kwargs["delivery_tag"]))

            def basic_nack(self, **kwargs):
                events.append(("nack", kwargs))

        handled = []
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://unused"}):
            process_delivery(
                Channel(),
                SimpleNamespace(delivery_tag=41),
                None,
                b'{"kind":"scrape_new_data","payload":{"since":100}}',
                connection_factory=lambda url: DatabaseConnection(),
                task_handlers={
                    "scrape_new_data": lambda conn, payload: handled.append(payload),
                },
            )

        self.assertEqual(handled, [{"since": 100}])
        self.assertLess(events.index("commit"), events.index(("ack", 41)))
        self.assertEqual(events[-1], ("ack", 41))

    def test_delivery_rolls_back_then_nacks_without_requeue(self):
        events = []

        class Transaction:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                events.append("rollback")

        class DatabaseConnection:
            def transaction(self):
                return Transaction()

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

        class Channel:
            def basic_ack(self, **kwargs):
                events.append(("ack", kwargs))

            def basic_nack(self, **kwargs):
                events.append(("nack", kwargs))

        def fail_handler(_conn, _payload):
            raise RuntimeError("database unavailable")

        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://unused"}):
            process_delivery(
                Channel(),
                SimpleNamespace(delivery_tag=42),
                None,
                b'{"kind":"scrape_new_data","payload":{}}',
                connection_factory=lambda _url: DatabaseConnection(),
                task_handlers={"scrape_new_data": fail_handler},
            )

        self.assertEqual(events, [
            "rollback",
            ("nack", {"delivery_tag": 42, "requeue": False}),
        ])

    def test_delivery_rejects_invalid_or_unsupported_message(self):
        for body in (
            b"not-json",
            b"[]",
            b'{"kind":"unknown","payload":{}}',
            b'{"kind":"scrape_new_data","payload":null}',
            b'{"kind":"scrape_new_data","payload":[]}',
            b'{"kind":"scrape_new_data","payload":""}',
            b'{"kind":1,"payload":{}}',
        ):
            channel = MagicMock()
            process_delivery(channel, SimpleNamespace(delivery_tag=43), None, body)
            channel.basic_nack.assert_called_once_with(
                delivery_tag=43,
                requeue=False,
            )
            channel.basic_ack.assert_not_called()

    def test_worker_rejects_invalid_since_and_page_count(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.fetchone.return_value = ("100",)
        for payload, message in (
            ({"since": "invalid"}, "payload.since"),
            ({"max_pages": 0}, "payload.max_pages"),
            ({"max_pages": True}, "payload.max_pages"),
        ):
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ValueError, message):
                    handle_scrape_new_data(connection, payload)

        self.assertEqual(cursor.close.call_count, 3)

    def test_worker_scrape_without_result_urls_does_not_write_watermark(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.fetchone.return_value = ("100",)
        with patch("worker.consumer.GradCafeScraper"):
            with patch(
                "worker.consumer.fetch_records_after_watermark",
                return_value=([{"program": "No URL"}], 100),
            ):
                self.assertEqual(handle_scrape_new_data(connection, {}), 0)

        cursor.executemany.assert_not_called()
        self.assertFalse(any(
            entry.args[0] == unittest.mock.ANY
            and len(entry.args) > 1
            and entry.args[1] == ("gradcafe", "100")
            for entry in cursor.execute.call_args_list
        ))

    def test_recompute_analytics_refreshes_views(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value

        from worker.consumer import handle_recompute_analytics

        handle_recompute_analytics(connection, {})

        self.assertTrue(any(
            entry.args[0].as_string().startswith("REFRESH MATERIALIZED VIEW")
            for entry in cursor.execute.call_args_list
        ))
        cursor.close.assert_called_once_with()

    def test_delivery_without_database_url_is_nacked(self):
        channel = MagicMock()
        with patch.dict(os.environ, {}, clear=True):
            process_delivery(
                channel,
                SimpleNamespace(delivery_tag=44),
                None,
                b'{"kind":"recompute_analytics","payload":{}}',
            )

        channel.basic_nack.assert_called_once_with(
            delivery_tag=44,
            requeue=False,
        )
        channel.basic_ack.assert_not_called()

    def test_worker_requires_rabbitmq_url(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "RABBITMQ_URL"):
                main()

    def test_worker_uses_manual_ack_and_prefetch_one(self):
        connection = MagicMock()
        channel = connection.channel.return_value
        with patch.dict(os.environ, {"RABBITMQ_URL": "amqp://test/%2F"}):
            with tempfile.TemporaryDirectory() as temp_dir:
                ready_file = Path(temp_dir) / "worker-ready"
                with patch.dict(os.environ, {"WORKER_READY_FILE": str(ready_file)}):
                    main(
                        connection_factory=lambda _parameters: connection,
                        parameters_factory=lambda url: url,
                    )
                self.assertTrue(ready_file.is_file())

        channel.basic_qos.assert_called_once_with(prefetch_count=1)
        consume_args = channel.basic_consume.call_args.kwargs
        self.assertEqual(consume_args["queue"], "tasks_q")
        self.assertFalse(consume_args["auto_ack"])

    def test_pull_route_publishes_scrape_task_and_returns_accepted(self):
        publisher = MagicMock()
        client = create_app({
            "TESTING": True,
            "PUBLISH_TASK": publisher,
        }).test_client()

        response = client.post("/pull-data")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.get_json()["message"], "Request queued")
        self.assertTrue(response.get_json()["queued"])
        publisher.assert_called_once_with("scrape_new_data")

    def test_update_analysis_queues_without_running_query(self):
        publisher = MagicMock()
        analysis = MagicMock()
        client = create_app({
            "TESTING": True,
            "PUBLISH_TASK": publisher,
            "ANALYSIS_QUERY": analysis,
        }).test_client()

        response = client.post("/update-analysis")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.get_json()["message"], "Request queued")
        publisher.assert_called_once_with("recompute_analytics")
        analysis.assert_not_called()

    def test_broker_error_returns_service_unavailable(self):
        publisher = MagicMock(side_effect=RuntimeError("broker unavailable"))
        client = create_app({
            "TESTING": True,
            "PUBLISH_TASK": publisher,
        }).test_client()

        response = client.post("/pull-data")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["message"], "Could not queue request")

    def test_update_analysis_broker_error_returns_service_unavailable(self):
        publisher = MagicMock(side_effect=RuntimeError("broker unavailable"))
        client = create_app({
            "TESTING": True,
            "PUBLISH_TASK": publisher,
        }).test_client()

        response = client.post("/update-analysis")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["message"], "Could not queue request")

    def test_health_reports_missing_or_unavailable_database(self):
        missing_database_client = create_app({
            "TESTING": True,
            "DATABASE_URL": None,
        }).test_client()
        self.assertEqual(missing_database_client.get("/health").status_code, 503)

        unavailable_database_client = create_app({
            "TESTING": True,
            "DATABASE_URL": "postgresql://unused",
        }).test_client()
        with patch(
            "web.app.app.psycopg.connect",
            side_effect=psycopg.OperationalError("database unavailable"),
        ):
            response = unavailable_database_client.get("/health")
        self.assertEqual(response.status_code, 503)

        available_database_client = create_app({
            "TESTING": True,
            "DATABASE_URL": "postgresql://unused",
        }).test_client()
        with patch("web.app.app.psycopg.connect") as connect:
            response = available_database_client.get("/health")
        self.assertEqual(response.status_code, 200)
        connect.assert_called_once_with("postgresql://unused", connect_timeout=2)

    def test_analysis_requires_database_url_and_rejects_invalid_limits(self):
        client = create_app({
            "TESTING": True,
            "DATABASE_URL": None,
        }).test_client()
        with self.assertRaisesRegex(RuntimeError, "DATABASE_URL"):
            client.get("/analysis")

        configured_client = create_app({
            "TESTING": True,
            "DATABASE_URL": "postgresql://unused",
        }).test_client()
        for value in ("letters", "１２", "9" * 65):
            with self.subTest(value=value):
                self.assertEqual(
                    configured_client.get(f"/analysis?limit={value}").status_code,
                    400,
                )
        for value in (True, 1.5, object()):
            with self.subTest(invalid_limit=value):
                with self.assertRaisesRegex(ValueError, "limit must be an integer"):
                    clamp_query_limit(value)

    def test_loader_rejects_non_array_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "not-an-array.json"
            data_file.write_text('{"url":"https://example.test/1"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "JSON array"):
                load_data_to_db(data_file, "postgresql://unused")

    def test_loader_cli_uses_configured_file_and_database_url(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "applicants.json"
            data_file.write_text("[]", encoding="utf-8")
            args = SimpleNamespace(file=data_file)
            with patch("db.load_data.argparse.ArgumentParser.parse_args", return_value=args):
                with patch.dict(os.environ, {"SETUP_DATABASE_URL": "postgresql://setup"}):
                    with patch.object(load_data_module, "load_data_to_db", return_value=1) as load:
                        load_data_module.main()
            load.assert_called_once_with(data_file, "postgresql://setup")

        with patch.dict(os.environ, {}, clear=True):
            with patch(
                "db.load_data.argparse.ArgumentParser.parse_args",
                return_value=SimpleNamespace(file=Path("unused.json")),
            ):
                with self.assertRaisesRegex(RuntimeError, "SETUP_DATABASE_URL"):
                    load_data_module.main()

    def test_loader_cli_entry_point_skips_existing_applicants(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "applicants.json"
            data_file.write_text("[]", encoding="utf-8")
            connection = MagicMock()
            cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = (True,)
            with patch.dict(os.environ, {"SETUP_DATABASE_URL": "postgresql://setup"}):
                with patch("psycopg.connect", return_value=connection):
                    with patch.object(sys, "argv", ["load_data.py", "--file", str(data_file)]):
                        runpy.run_path(
                            str(Path(load_data_module.__file__)),
                            run_name="__main__",
                        )

    def test_worker_entry_point_starts_consumer(self):
        connection = MagicMock()
        pika = SimpleNamespace(
            URLParameters=MagicMock(return_value="rabbit-params"),
            BlockingConnection=MagicMock(return_value=connection),
        )
        with patch.dict(os.environ, {"RABBITMQ_URL": "amqp://test/test"}):
            with patch.dict("sys.modules", {"pika": pika}):
                runpy.run_path(
                    str(Path(__file__).parents[2] / "src" / "worker" / "consumer.py"),
                    run_name="__main__",
                )

        connection.channel.return_value.start_consuming.assert_called_once_with()
        connection.close.assert_called_once_with()

    def test_dashboard_renders_analysis_results_and_status_banner(self):
        client = create_app({
            "TESTING": True,
            "DATABASE_URL": "postgresql://unused",
            "ANALYSIS_QUERY": lambda _url, _limit=1: {
                "percent_international": 12.5,
                "q10_university_counts": [("Example University", 3)],
                "q11_averages": (3.8, 320, 160, 4.5),
            },
        }).test_client()

        response = client.get("/analysis")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"12.50%", response.data)
        self.assertIn(b"Example University", response.data)
        self.assertIn(b'id="request-status"', response.data)

    def test_invalid_dashboard_limit_returns_bad_request(self):
        client = create_app({
            "TESTING": True,
            "DATABASE_URL": "postgresql://unused",
        }).test_client()

        response = client.get("/analysis?limit=not-a-number")

        self.assertEqual(response.status_code, 400)

    def test_dashboard_queries_are_composed_and_bind_the_limit(self):
        connection = MagicMock()
        cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [(12.5,), (3.8, 320.0, 160.0, 4.5)]
        cursor.fetchall.return_value = [("Example University", 3)]

        with patch("web.app.app.psycopg.connect", return_value=connection):
            results = run_analysis_queries("postgresql://unused", limit=7)

        statements = [
            call.args[0]
            for call in cursor.execute.call_args_list
        ]
        self.assertTrue(all(isinstance(statement, sql.Composable) for statement in statements))
        self.assertEqual(
            statements[1].as_string(),
            'SELECT "university", "applicant_count" FROM "applicant_university_summary" '
            'ORDER BY "applicant_count" DESC, "university" LIMIT %s',
        )
        self.assertEqual(cursor.execute.call_args_list[1].args[1], (7,))
        self.assertEqual(results["q10_university_counts"], [("Example University", 3)])

    def test_malicious_dashboard_limits_return_bad_request_without_queries(self):
        analysis_query = MagicMock()
        client = create_app({
            "TESTING": True,
            "DATABASE_URL": "postgresql://unused",
            "ANALYSIS_QUERY": analysis_query,
        }).test_client()
        malicious_limits = (
            "1 OR 1=1",
            "\x00",
            "１２",
            "<script>alert(1)</script>",
            "9" * 10_000,
        )

        for limit in malicious_limits:
            with self.subTest(limit=limit[:24]):
                response = client.get("/analysis", query_string={"limit": limit})

                self.assertEqual(response.status_code, 400)

        analysis_query.assert_not_called()

    def test_health_route_reports_missing_database_configuration(self):
        response = create_app({
            "TESTING": True,
            "DATABASE_URL": None,
        }).test_client().get("/health")

        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.get_json()["ok"])


if __name__ == "__main__":
    unittest.main()

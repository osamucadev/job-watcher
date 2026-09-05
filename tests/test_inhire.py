from __future__ import annotations

import unittest

import httpx

from app.services import inhire
from app.services.inhire import (
    CollectionError,
    ScrapedJob,
    collect_company,
    extract_career_page,
    extract_tenant,
    records_to_jobs,
)


def _record(job_id: str, name: str, career_page: str, career_page_id: str | None = None) -> dict:
    return {
        "careerPageId": career_page_id or career_page,
        "displayName": name,
        "jobId": job_id,
        "careerPage": {"id": career_page_id or career_page, "name": name, "careerPage": career_page},
        "link": f"https://tenant.inhire.com.br/vagas/{job_id}",
    }


def _loop_run(coroutine):
    import asyncio

    return asyncio.run(coroutine)


class TenantExtractionTests(unittest.TestCase):
    def test_plain_tenant_from_host(self) -> None:
        self.assertEqual(extract_tenant("https://lyncas.inhire.app/vagas"), "lyncas")

    def test_tenant_from_nested_career_page_url(self) -> None:
        self.assertEqual(extract_tenant("https://lwsa.inhire.app/octadesk/vagas"), "lwsa")

    def test_tenant_lowercased(self) -> None:
        self.assertEqual(extract_tenant("https://Kooperecooperativa.inhire.app/supero/vagas"), "kooperecooperativa")

    def test_url_without_host_is_rejected(self) -> None:
        with self.assertRaises(CollectionError):
            extract_tenant("not-a-url")


class CareerPageIdentificationTests(unittest.TestCase):
    def test_bare_vagas_path_is_the_default_career_page(self) -> None:
        self.assertEqual(extract_career_page("https://lyncas.inhire.app/vagas"), "default")

    def test_trailing_slash_is_still_default(self) -> None:
        self.assertEqual(extract_career_page("https://lyncas.inhire.app/vagas/"), "default")

    def test_octadesk_segment_is_identified(self) -> None:
        self.assertEqual(extract_career_page("https://lwsa.inhire.app/octadesk/vagas"), "octadesk")

    def test_supero_segment_is_identified(self) -> None:
        self.assertEqual(extract_career_page("https://kooperecooperativa.inhire.app/supero/vagas"), "supero")


class RecordConversionTests(unittest.TestCase):
    def test_records_become_internal_jobs(self) -> None:
        records = [_record("id-1", "Desenvolvedor Python", "default")]
        jobs = records_to_jobs(records, "https://lyncas.inhire.app/vagas", "default")
        self.assertEqual(
            jobs,
            [ScrapedJob("id-1", "Desenvolvedor Python", "https://lyncas.inhire.app/vagas/id-1")],
        )

    def test_link_keeps_the_registered_career_page_segment(self) -> None:
        records = [_record("id-9", "Analista", "octadesk")]
        jobs = records_to_jobs(records, "https://lwsa.inhire.app/octadesk/vagas", "octadesk")
        self.assertEqual(jobs[0].url, "https://lwsa.inhire.app/octadesk/vagas/id-9")

    def test_entries_without_id_or_title_are_skipped(self) -> None:
        records = [
            {"jobId": "", "displayName": "No Id", "careerPageId": "default"},
            {"jobId": "id-2", "displayName": "  ", "careerPageId": "default"},
            _record("id-3", "Valid", "default"),
        ]
        jobs = records_to_jobs(records, "https://lyncas.inhire.app/vagas", "default")
        self.assertEqual([job.external_id for job in jobs], ["id-3"])

    def test_duplicate_ids_are_collapsed(self) -> None:
        records = [_record("id-1", "First", "default"), _record("id-1", "Second", "default")]
        jobs = records_to_jobs(records, "https://lyncas.inhire.app/vagas", "default")
        self.assertEqual(len(jobs), 1)


class CareerPageFilterTests(unittest.TestCase):
    def test_only_matching_career_page_is_returned(self) -> None:
        records = [
            _record("keep-1", "Octadesk role", "octadesk"),
            _record("drop-1", "Vindi role", "vindi"),
            _record("drop-2", "Default role", "default"),
        ]
        jobs = records_to_jobs(records, "https://lwsa.inhire.app/octadesk/vagas", "octadesk")
        self.assertEqual([job.external_id for job in jobs], ["keep-1"])

    def test_default_filter_keeps_only_default_entries(self) -> None:
        records = [
            _record("keep-1", "Default role", "default"),
            _record("drop-1", "Supero role", "supero"),
        ]
        jobs = records_to_jobs(records, "https://kooperecooperativa.inhire.app/vagas", "default")
        self.assertEqual([job.external_id for job in jobs], ["keep-1"])


class CollectCompanyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._backoff = inhire.RETRY_BACKOFF_SECONDS
        inhire.RETRY_BACKOFF_SECONDS = 0.0

    def tearDown(self) -> None:
        inhire.RETRY_BACKOFF_SECONDS = self._backoff

    def _client(self, handler) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    def test_valid_empty_response_yields_no_jobs(self) -> None:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            self.assertEqual(request.headers["X-Tenant"], "lyncas")
            self.assertEqual(request.headers["Content-Type"], "application/json")
            return httpx.Response(200, json=[])

        async def scenario() -> list[ScrapedJob]:
            async with self._client(handler) as client:
                return await collect_company(client, "https://lyncas.inhire.app/vagas")

        self.assertEqual(_loop_run(scenario()), [])
        self.assertEqual(len(calls), 1)

    def test_http_failure_raises_and_never_returns_empty(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"message": "not found"})

        async def scenario() -> list[ScrapedJob]:
            async with self._client(handler) as client:
                return await collect_company(client, "https://lyncas.inhire.app/vagas")

        with self.assertRaises(CollectionError):
            _loop_run(scenario())

    def test_transient_errors_are_retried_until_success(self) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            if attempts["count"] < 3:
                return httpx.Response(503, text="try later")
            return httpx.Response(200, json=[_record("id-1", "Python Developer", "default")])

        async def scenario() -> list[ScrapedJob]:
            async with self._client(handler) as client:
                return await collect_company(client, "https://lyncas.inhire.app/vagas")

        jobs = _loop_run(scenario())
        self.assertEqual(attempts["count"], 3)
        self.assertEqual([job.external_id for job in jobs], ["id-1"])

    def test_connection_errors_are_retried(self) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            if attempts["count"] < 2:
                raise httpx.ConnectError("boom", request=request)
            return httpx.Response(200, json=[])

        async def scenario() -> list[ScrapedJob]:
            async with self._client(handler) as client:
                return await collect_company(client, "https://lyncas.inhire.app/vagas")

        self.assertEqual(_loop_run(scenario()), [])
        self.assertEqual(attempts["count"], 2)

    def test_permanent_errors_do_not_retry_forever(self) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            return httpx.Response(400, text="bad request")

        async def scenario() -> None:
            async with self._client(handler) as client:
                await collect_company(client, "https://lyncas.inhire.app/vagas")

        with self.assertRaises(CollectionError):
            _loop_run(scenario())
        self.assertEqual(attempts["count"], 1)

    def test_retry_budget_is_bounded_for_transient_errors(self) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            return httpx.Response(500, text="server error")

        async def scenario() -> None:
            async with self._client(handler) as client:
                await collect_company(client, "https://lyncas.inhire.app/vagas")

        with self.assertRaises(CollectionError):
            _loop_run(scenario())
        self.assertEqual(attempts["count"], inhire.MAX_ATTEMPTS)

    def test_unconfirmed_career_page_refuses_to_archive(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[_record("id-1", "Default role", "default")])

        async def scenario() -> None:
            async with self._client(handler) as client:
                await collect_company(client, "https://lwsa.inhire.app/octadesk/vagas")

        with self.assertRaises(CollectionError):
            _loop_run(scenario())

    def test_confirmed_career_page_filters_results(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=[
                    _record("keep-1", "Octadesk role", "octadesk"),
                    _record("drop-1", "Default role", "default"),
                ],
            )

        async def scenario() -> list[ScrapedJob]:
            async with self._client(handler) as client:
                return await collect_company(client, "https://lwsa.inhire.app/octadesk/vagas")

        jobs = _loop_run(scenario())
        self.assertEqual([job.external_id for job in jobs], ["keep-1"])


if __name__ == "__main__":
    unittest.main()

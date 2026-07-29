import pytest

from rag.ingestion.reconciliation import IngestionReconciler

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_reconciler_reports_missing_objects():
    class Result:
        def mappings(self):
            return [{"id": "ver_1", "raw_object_key": "missing"}]

    class Session:
        async def execute(self, statement, parameters=None):
            return Result()

    class Store:
        def object_exists(self, key):
            return False

    reconciler = IngestionReconciler(Session(), Store())
    assert await reconciler.missing_raw_objects() == ["ver_1"]

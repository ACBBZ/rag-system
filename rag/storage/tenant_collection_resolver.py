from rag.errors import ServiceUnavailableError
from rag.schemas import TenantContext, TenantVectorRoute


class TenantCollectionResolver:
    def __init__(self, legacy_collection: str) -> None:
        self.legacy_collection = legacy_collection.strip()

    def resolve(self, tenant: TenantContext) -> TenantVectorRoute:
        if tenant.vector_route is not None:
            return tenant.vector_route
        if not self.legacy_collection:
            raise ServiceUnavailableError("tenant vector collection is not ready")
        return TenantVectorRoute(
            collection_name=self.legacy_collection,
            physical_collection=self.legacy_collection,
            mode="shared",
            schema_version=0,
            embedding_model="legacy",
            embedding_dimension=0,
        )

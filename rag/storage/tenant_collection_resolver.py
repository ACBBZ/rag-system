from rag.errors import ServiceUnavailableError
from rag.schemas import TenantContext, TenantVectorRoute


class TenantCollectionResolver:
    def resolve(self, tenant: TenantContext) -> TenantVectorRoute:
        if tenant.vector_route is None:
            raise ServiceUnavailableError("tenant vector collection is not ready")
        return tenant.vector_route

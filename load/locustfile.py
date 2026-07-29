import os

from locust import HttpUser, between, task


class RAGUser(HttpUser):
    wait_time = between(0.5, 2.0)

    def on_start(self):
        self.headers = {
            "Authorization": f"Bearer {os.environ['RAG_LOAD_API_KEY']}"
        }
        self.knowledge_base_id = os.environ["RAG_LOAD_KNOWLEDGE_BASE_ID"]

    @task(4)
    def hybrid_search(self):
        self.client.post(
            "/v1/retrieval/search",
            headers=self.headers,
            json={
                "knowledge_base_id": self.knowledge_base_id,
                "query": "What is the leave policy?",
                "options": {
                    "retrieval_mode": "hybrid",
                    "rerank": True,
                    "agent_search": True,
                    "top_k": 30,
                    "final_k": 5,
                },
            },
        )

    @task(1)
    def readiness(self):
        self.client.get("/health/ready")

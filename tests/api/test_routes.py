from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_workflow_repo
from app.api.routers import jobs, query
from tests.conftest import InMemoryRepository


def client_with(repo: InMemoryRepository) -> TestClient:
    # Routers only, without main's lifespan, so no MongoDB connection is opened
    app = FastAPI()
    app.include_router(query.router)
    app.include_router(jobs.router)
    app.dependency_overrides[get_workflow_repo] = lambda: repo
    return TestClient(app)


def test_get_workflows_for_a_known_domain():
    repo = InMemoryRepository()
    repo.docs["github.com"] = {"domain": "github.com", "workflows": [{"name": "Create a repo"}]}
    response = client_with(repo).get("/workflows/github.com")
    assert response.status_code == 200
    assert response.json()["workflows"][0]["name"] == "Create a repo"


def test_unknown_domain_is_404():
    assert client_with(InMemoryRepository()).get("/workflows/example.com").status_code == 404


def test_delete_workflow():
    repo = InMemoryRepository()
    repo.docs["github.com"] = {"domain": "github.com", "workflows": [{"name": "Create a repo"}]}
    client = client_with(repo)
    assert client.delete("/workflows/github.com/Create a repo").json() == {"status": "deleted"}
    assert client.delete("/workflows/github.com/Missing").status_code == 404


def test_cancel_unknown_job_is_404():
    assert client_with(InMemoryRepository()).post("/jobs/nope/cancel").status_code == 404

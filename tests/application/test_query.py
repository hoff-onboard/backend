from app.application.query import run_query, stream_query
from tests.conftest import FakeExtractor, FakeResearch


async def collect(gen):
    return [e async for e in gen]


async def test_stream_emits_progress_then_reviewed_workflow(make_pipeline):
    pipeline = make_pipeline()
    events = await collect(stream_query(pipeline, "https://github.com", "Create a repo"))

    names = [e["event"] for e in events]
    assert names[:2] == ["phase", "phase"]
    assert names.count("agent_thought") == 2 and names.count("screenshot") == 2
    assert names[-3:] == ["brand", "workflow", "log"] or names[-1] == "done"
    assert names[-1] == "done"
    workflow = next(e for e in events if e["event"] == "workflow")["data"]["workflow"]
    assert workflow["description"] == "reviewed"

    (saved, screenshots), = pipeline.repository.saved
    assert saved.workflows[0].name == "Create a repo"
    assert screenshots == {0: ["img1", "img2"]}


async def test_stream_passes_research_to_the_extractor(make_pipeline):
    extractor = FakeExtractor()
    await collect(stream_query(make_pipeline(extractor=extractor), "https://github.com", "Create a repo", "session-x"))
    call = extractor.calls[0]
    assert call["research"].description == "How to Create a repo"
    assert call["cookies_file"] == "session-x"


async def test_stream_reports_errors_as_events(make_pipeline):
    pipeline = make_pipeline(research=FakeResearch(error=RuntimeError("insufficient balance")))
    events = await collect(stream_query(pipeline, "https://github.com", "q"))
    assert events[-2] == {"event": "error", "data": {"message": "insufficient balance"}}
    assert events[-1]["event"] == "done"
    assert pipeline.repository.saved == []


async def test_run_query_cleans_up_cookies_and_archives(make_pipeline):
    pipeline = make_pipeline()
    result = await run_query(pipeline, "https://github.com", "Create a repo", cookies=[{"name": "s"}])
    assert result.workflows[0].description == "reviewed"
    assert pipeline.sessions.written == 1 and not pipeline.sessions.live
    assert pipeline.archive.results == [result]
    assert pipeline.repository.saved[0][0] == result

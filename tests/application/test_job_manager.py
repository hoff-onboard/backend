import asyncio

from app.application import job_manager
from tests.conftest import FakeBranding, FakeExtractor


async def wait_done(job_id):
    while job_manager.get_job(job_id)["status"] != "done":
        await asyncio.sleep(0.01)


async def test_cancel_stops_children_and_removes_cookies(make_pipeline):
    extractor, branding = FakeExtractor(hang=True), FakeBranding(hang=True)
    pipeline = make_pipeline(extractor=extractor, branding=branding)
    job_id = job_manager.create_job(pipeline, "https://github.com", "q", cookies=[{"name": "s"}])
    await asyncio.sleep(0.1)

    assert job_manager.cancel_job(job_id) is True
    await wait_done(job_id)

    assert extractor.cancelled and branding.cancelled
    assert not pipeline.sessions.live
    events = job_manager.get_job(job_id)["events"]
    assert [e["event"] for e in events[-2:]] == ["error", "done"]
    assert events[-2]["data"]["message"] == "Stopped by user"
    assert job_manager.cancel_job(job_id) is False


async def test_late_subscriber_gets_replay_and_every_live_event(make_pipeline):
    gate = asyncio.Event()

    class GatedExtractor(FakeExtractor):
        async def extract(self, url, spec, **kw):
            on_step = kw.get("on_step")
            await on_step(self._step(1))
            await gate.wait()
            for i in range(2, 6):
                await on_step(self._step(i))
            return self.result

        def _step(self, i):
            from app.domain.workflows.models import AgentStep

            return AgentStep(step=i, thought=f"t{i}")

    pipeline = make_pipeline(extractor=GatedExtractor())
    job_id = job_manager.create_job(pipeline, "https://github.com", "q")
    await asyncio.sleep(0.6)  # first step published before anyone subscribes

    received = []

    async def subscribe():
        async for event in job_manager.get_job_stream(job_id):
            received.append(event)

    reader = asyncio.create_task(subscribe())
    await asyncio.sleep(0.05)
    gate.set()
    await wait_done(job_id)
    await reader

    assert received == job_manager.get_job(job_id)["events"]
    thoughts = [e["data"]["step"] for e in received if e["event"] == "agent_thought"]
    assert thoughts == [1, 2, 3, 4, 5]

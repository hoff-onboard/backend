from datetime import datetime, timezone
from urllib.parse import urlparse

from app.modules.crawl.models import CrawlResponse
from app.services.mongodb import get_db


async def save_workflows(result: CrawlResponse) -> None:
    db = get_db()
    domain = urlparse(result.url).hostname or "unknown"
    new_wf_dicts = [w.model_dump() for w in result.workflows]

    doc = await db.workflows.find_one({"domain": domain})

    if doc:
        existing_names = {w["name"] for w in doc.get("workflows", [])}
        to_add = [w for w in new_wf_dicts if w["name"] not in existing_names]
        await db.workflows.update_one(
            {"domain": domain},
            {
                "$set": {
                    "brand": result.brand.model_dump(),
                    "updated_at": datetime.now(timezone.utc),
                },
                "$push": {"workflows": {"$each": to_add}},
            },
        )
    else:
        await db.workflows.insert_one({
            "domain": domain,
            "url": result.url,
            "brand": result.brand.model_dump(),
            "workflows": new_wf_dicts,
            "updated_at": datetime.now(timezone.utc),
        })


async def get_workflows_by_domain(domain: str) -> dict | None:
    db = get_db()
    return await db.workflows.find_one({"domain": domain}, {"_id": 0})

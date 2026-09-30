"""Command-line entry point: ``researcher run`` and ``researcher serve``."""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

from .config import Settings
from .models import Job, JobOptions
from .orchestration import run_job
from .services import build_services


async def _run(question: str, settings: Settings, as_json: bool) -> int:
    services = build_services(settings)
    now = services.clock()
    job = Job(
        id=uuid.uuid4().hex[:12],
        question=question,
        mode=settings.mode,
        created_at=now,
        updated_at=now,
        options=JobOptions(),
    )
    await run_job(job, services)
    if job.status != "completed" or job.report is None:
        print(f"job failed: {job.error}", file=sys.stderr)
        return 1
    print(job.model_dump_json(indent=2) if as_json else job.report.markdown)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="researcher")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="run one research job and print the report")
    run.add_argument("question")
    run.add_argument("--offline", action="store_true", help="force fixtures + no model")
    run.add_argument("--json", action="store_true", help="print the full job record as JSON")
    serve = sub.add_parser("serve", help="start the API and dashboard")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--offline", action="store_true", help="force fixtures + no model")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    if args.offline:
        settings = Settings(**{**settings.__dict__, "retrieval": "fixtures", "llm": "none"})
    if args.cmd == "run":
        return asyncio.run(_run(args.question, settings, args.json))

    import uvicorn

    from .api import create_app

    uvicorn.run(create_app(settings), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())

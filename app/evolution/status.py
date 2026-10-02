"""Live status view for the Lumen Evolution System.

Usage:
    python -m app.evolution.status
    python -m app.evolution.status --watch
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .autonomous_mission import MissionStore


def render(path: Path, *, stale_after: float = 180.0) -> str:
    store = MissionStore(path)
    record = store.load()
    if record is None:
        return "LUMEN EVOLUTION: NO ACTIVE MISSION"

    age = max(0.0, time.time() - record.updated_at)
    if record.status == "COMPLETED":
        health = "COMPLETED"
    elif record.status == "BLOCKED":
        health = "BLOCKED"
    elif age > stale_after:
        health = f"STALE ({int(age)}s sem atualização)"
    else:
        health = "RUNNING"

    lines = [
        "========== LUMEN EVOLUTION ==========",
        f"MISSÃO       : {record.mission_id}",
        f"STATUS       : {record.status}",
        f"SAÚDE        : {health}",
        f"CICLO        : {record.cycle}",
        f"FASE         : {record.phase}",
        f"ÚLTIMA AÇÃO  : {record.last_action or '-'}",
        f"ÚLTIMO RESULT: {record.last_result or '-'}",
        f"ÚLTIMO ERRO  : {record.last_error or '-'}",
        f"TEMPO AÇÃO   : {record.last_duration_seconds:.1f}s",
        f"ATUALIZAÇÃO  : há {age:.1f}s",
        "-------------------------------------",
        f"OBJETIVO: {record.goal}",
    ]

    if store.event_path.exists():
        try:
            rows = store.event_path.read_text(encoding="utf-8").splitlines()
            recent = [json.loads(x) for x in rows[-5:] if x.strip()]
            lines.append("-------------------------------------")
            lines.append("EVENTOS RECENTES:")
            for item in recent:
                stamp = time.strftime("%H:%M:%S", time.localtime(float(item.get("timestamp", 0))))
                event = item.get("event", "?")
                action = item.get("action", "")
                suffix = f" [{action}]" if action else ""
                lines.append(f"  {stamp} {event}{suffix}")
        except (OSError, ValueError, TypeError):
            lines.append("EVENTOS RECENTES: indisponíveis")

    lines.append("=====================================")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor da missão autônoma da Lúmen.")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()
    path = Path(args.data_dir) / "evolution" / "mission.json"

    while True:
        if args.watch:
            print("\033[2J\033[H", end="")
        print(render(path), flush=True)
        if not args.watch:
            return 0
        time.sleep(max(0.25, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())

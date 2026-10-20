"""`just eval`: property checks on hand-written and adversarial cases, PRD metrics on the
labelled replay, then the water clock's skill against the simulated flood.

Uses whatever LLM_PROVIDER is configured, so the same command scores the rule
reader and any model. PRD targets are reported; the floors and ceilings are
enforced, so a change that makes the pipeline worse fails like a failing test.

    uv run python -m evals.run [--limit N] [--skip-water]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from app.agents.understand import understand
from app.core.settings import get_settings
from app.schemas.extraction import Understanding
from app.services.floods import FloodMap
from app.services.geocode import gazetteer, haversine_m
from app.services.resolver import REVIEW_THRESHOLD, Resolver
from evals.water import run_water

HERE = Path(__file__).resolve().parent
PRD_TARGETS = {
    "headcount_accuracy": 0.90,
    "vulnerability_f1": 0.90,
    "geocode_within_300m": 0.85,
    "dedup_precision": 0.95,
    "duplicates_merged": 0.60,
}
# regression floors: the scores the rule reader reaches today on the physically placed replay, minus a
# little noise. Families crowd into flooded lanes there, so a shared landmark alone no longer merges
# neighbours: precision stays high and fewer duplicates merge without a phone, name or door number.
FLOORS = {
    "property_cases": 0.95,
    "headcount_accuracy": 0.94,
    "vulnerability_f1": 0.95,
    "geocode_within_300m": 0.83,
    "dedup_precision": 0.97,
    "duplicates_merged": 0.32,
    "duplicates_merged_or_flagged": 0.58,
    "water_detected": 0.45,
}
# lower is better for these
CEILINGS = {
    "water_depth_error_m": 0.15,
    "water_false_alarms": 0.02,
}


def check(u: Understanding, expect: dict[str, object]) -> list[str]:
    fails = []
    e = u.extraction
    v = e.vulnerable
    for k, want in expect.items():
        if k == "phones":
            got: object = len(u.phones)
        elif k == "flagged":
            got = bool(u.flags)
        elif k in ("elderly", "child", "infant", "pregnant", "disabled"):
            got = getattr(v, k)
        elif k == "medical_has":
            got = want if want in v.medical else v.medical
        elif k == "needs_has":
            got = want if want in e.needs else e.needs
        elif k == "needs_lacks":
            got = want if want not in e.needs else e.needs
        else:
            got = getattr(e, k)
        if got != want:
            fails.append(f"{k}: want {want!r}, got {got!r}")
    return fails


async def run_cases() -> float:
    lines = (HERE / "cases.jsonl").read_text(encoding="utf-8").splitlines()
    passed = 0
    for line in lines:
        case = json.loads(line)
        u = await understand(case["text"])
        fails = check(u, case["expect"])
        passed += not fails
        if fails:
            print(f"  FAIL {case['text'][:70]!r}\n       " + "; ".join(fails))
    score = passed / len(lines)
    print(f"property cases: {passed}/{len(lines)} = {score:.0%}")
    return score


def f1(tp: int, fp: int, fn: int) -> float:
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    return 2 * p * r / (p + r) if p + r else 0.0


async def run_replay(limit: int | None) -> dict[str, float]:
    settings = get_settings()
    base = settings.data_dir / "replay" / "chennai-2015"
    msgs = [json.loads(x) for x in (base / "messages.jsonl").read_text(encoding="utf-8").splitlines()]
    msgs = msgs[:limit] if limit else msgs
    meta = json.loads((base / "dataset.json").read_text(encoding="utf-8"))
    resolver = Resolver(
        gazetteer(str(settings.data_dir)), FloodMap.load(base / "flood_zones.geojson"), tuple(meta["center"])
    )

    head_ok = head_n = water_ok = water_n = lang_ok = ungrounded = 0
    vtp = vfp = vfn = 0
    upd = Counter()
    geo_rows: list[tuple[float | None, bool]] = []  # (error m, accepted without review)
    case_of: dict[str, str] = {}
    household_of: dict[str, str] = {}
    started = time.perf_counter()
    for m in msgs:
        t = m["truth"]
        u = await understand(m["text"])
        e = u.extraction
        ungrounded += len(u.dropped_claims)
        out = resolver.ingest(
            m["id"],
            u,
            m["text"],
            tuple(m["pin"]) if m["pin"] else None,
            m["sender_phone"],
            datetime.fromisoformat(m["t"]),
        )
        is_update = e.status_update in ("rescued", "safe")
        upd[(t["kind"] == "update", is_update)] += 1
        if t["kind"] != "sos":
            if t["kind"] == "update":
                case_of[m["id"]], household_of[m["id"]] = out.case.id, t["household"]
            continue
        case_of[m["id"]], household_of[m["id"]] = out.case.id, t["household"]
        lang_ok += e.language == t["language"]
        if t["stated_people"]:
            head_n += 1
            head_ok += e.people_count == t["stated_people"]
        water_n += 1
        water_ok += e.water_level == t["water"]
        said = t["said"]
        for k in ("elderly", "child", "infant", "pregnant", "disabled"):
            truth_pos, got_pos = bool(said[k]), bool(getattr(e.vulnerable, k))
            vtp += truth_pos and got_pos
            vfp += got_pos and not truth_pos
            vfn += truth_pos and not got_pos
        for cond in set(said["medical"]) | set(e.vulnerable.medical) - {"medication"}:
            truth_pos, got_pos = cond in said["medical"], cond in e.vulnerable.medical
            vtp += truth_pos and got_pos
            vfp += got_pos and not truth_pos
            vfn += truth_pos and not got_pos
        loc = out.location
        if loc is None:
            geo_rows.append((None, False))
        else:
            err = float(haversine_m(loc.lat, loc.lng, t["lat"], t["lng"]))
            geo_rows.append((err, loc.confidence >= REVIEW_THRESHOLD))
    elapsed = time.perf_counter() - started

    # a duplicate the coordinator sees as a one-click "possible duplicate" counts as flagged
    flagged_pairs = {frozenset((a, b)) for a, b, _ in resolver.review_pairs}
    tp = fp = fn = 0
    ids = list(case_of)
    by_case: dict[str, list[str]] = defaultdict(list)
    by_house: dict[str, list[str]] = defaultdict(list)
    for mid in ids:
        by_case[case_of[mid]].append(mid)
        by_house[household_of[mid]].append(mid)
    for group in by_case.values():
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                if household_of[a] == household_of[b]:
                    tp += 1
                else:
                    fp += 1
    for group in by_house.values():
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                fn += case_of[a] != case_of[b]
    dups = sum(len(g) - 1 for g in by_house.values())
    merged_right = sum(1 for g in by_house.values() for mid in g[1:] if case_of[mid] == case_of[g[0]])
    flagged_right = sum(
        1
        for g in by_house.values()
        for mid in g[1:]
        if case_of[mid] == case_of[g[0]] or frozenset((case_of[mid], case_of[g[0]])) in flagged_pairs
    )

    accepted = [err for err, ok in geo_rows if ok and err is not None]
    wrong = [(err, ok) for err, ok in geo_rows if err is None or err > 300]
    metrics = {
        "headcount_accuracy": head_ok / max(1, head_n),
        "vulnerability_f1": f1(vtp, vfp, vfn),
        "water_level_accuracy": water_ok / max(1, water_n),
        "language_accuracy": lang_ok / max(1, water_n),
        "update_recall": upd[(True, True)] / max(1, upd[(True, True)] + upd[(True, False)]),
        "update_precision": upd[(True, True)] / max(1, upd[(True, True)] + upd[(False, True)]),
        "located": sum(1 for err, _ in geo_rows if err is not None) / max(1, len(geo_rows)),
        "auto_accepted": len(accepted) / max(1, len(geo_rows)),
        "geocode_within_300m": sum(1 for err in accepted if err <= 300) / max(1, len(accepted)),
        "all_within_300m": sum(1 for err, _ in geo_rows if err is not None and err <= 300) / max(1, len(geo_rows)),
        "wrong_locations_flagged": sum(1 for _, ok in wrong if not ok) / max(1, len(wrong)),
        "dedup_precision": tp / max(1, tp + fp),
        "dedup_recall": tp / max(1, tp + fn),
        "duplicates_merged": merged_right / max(1, dups),
        "duplicates_merged_or_flagged": flagged_right / max(1, dups),
        "raw_messages": len(case_of),
        "cases": len(by_case),
        "true_households": len(by_house),
        "ms_per_message": elapsed * 1000 / max(1, len(msgs)),
        # claims a model made without a quote, dropped before they could raise a score (0 with no model)
        "ungrounded_claims": ungrounded,
    }
    print(f"\nreplay metrics on {len(msgs)} messages (provider={settings.llm_provider}):")
    for k, v in metrics.items():
        target = PRD_TARGETS.get(k)
        mark = "" if target is None else ("  meets PRD" if v >= target else f"  below PRD {target:.0%}")
        shown = (
            f"{v:.1%}"
            if isinstance(v, float) and v <= 1 and k != "ms_per_message"
            else f"{v:.1f}"
            if isinstance(v, float)
            else str(v)
        )
        print(f"  {k:26} {shown:>8}{mark}")
    return metrics


SITE_METRICS = Path(__file__).resolve().parents[2] / "web" / "public" / "evals" / "latest.json"


def publish(metrics: dict[str, float]) -> None:
    # the landing page quotes these numbers; keep them generated, never typed
    SITE_METRICS.parent.mkdir(parents=True, exist_ok=True)
    rounded = {k: round(v, 4) if isinstance(v, float) else v for k, v in metrics.items()}
    SITE_METRICS.write_text(json.dumps({"provider": get_settings().llm_provider, **rounded}), encoding="utf-8")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--skip-water", action="store_true", help="skip the water clock (a few minutes)")
    args = parser.parse_args()
    metrics = {"property_cases": await run_cases(), **await run_replay(args.limit)}
    if args.limit:
        return 0  # floors are calibrated on the full set
    if not args.skip_water:
        metrics |= run_water()
    publish(metrics)
    below = [
        f"{k} {metrics[k]:.1%} < {floor:.0%}" for k, floor in FLOORS.items() if k in metrics and metrics[k] < floor
    ]
    below += [f"{k} {metrics[k]:.3f} > {cap}" for k, cap in CEILINGS.items() if k in metrics and metrics[k] > cap]
    if below:
        print("\nregression: " + "; ".join(below))
        return 1
    print("\nno regressions")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "python-dotenv>=1.2.1",
# ]
# ///
# =============================================================
# pipeline.py — B2C lead pipeline orchestrator
# Hermes cron entry point. Runs scrape/search → classify → submit.
# =============================================================
# Usage:
#   uv run scripts/pipeline.py --source=gumtree      # Firecrawl Gumtree scrape
#   uv run scripts/pipeline.py --source=search       # Exa/Tavily competitor search
#   uv run scripts/pipeline.py --source=all          # both sources in sequence
#   uv run scripts/pipeline.py --source=all --dry-run
# =============================================================

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path.home() / ".hermes/.env")

# ── Logging ──────────────────────────────────────────────────

log = logging.getLogger("pipeline")


def setup_logging() -> None:
    log.setLevel(logging.DEBUG)
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    log.addHandler(console)


# ── Skill paths ──────────────────────────────────────────────

SKILLS = Path.home() / "ugolino/.claude/skills"
SCRAPE   = SKILLS / "leadgen-scraper/scripts/scrape.py"
SEARCH   = SKILLS / "leadgen-search/scripts/search.py"
CLASSIFY = SKILLS / "lead-classifier/scripts/classify.py"
ENRICH   = SKILLS / "leadgen-search/scripts/enrich.py"
SUBMIT   = SKILLS / "webhook-submit/scripts/submit.py"
LOG_DIR  = Path.home() / "vault/projects/cogstack-leadgen/pipeline-runs"


# ── Subprocess runner — mirrors b2c_run.py _run_subprocess() ─

def run_step(cmd: list[str], label: str, stdin_data: str | None = None, timeout: int = 600) -> tuple[bool, str]:
    """
    Run a subprocess step. Returns (success, stdout_text).
    stdin_data: pass previous step's stdout as stdin if provided.
    """
    log.info("[%s] Running: %s", label, " ".join(str(c) for c in cmd))
    try:
        proc = subprocess.run(
            cmd,
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        for line in proc.stderr.strip().splitlines():
            log.debug("[%s] %s", label, line)

        if proc.returncode != 0:
            log.error("[%s] Exit code %d", label, proc.returncode)
            log.error("[%s] stderr tail: %s", label, proc.stderr[-500:])
            return False, ""

        return True, proc.stdout

    except subprocess.TimeoutExpired:
        log.error("[%s] Timed out after %ds", label, timeout)
        return False, ""
    except Exception as e:
        log.error("[%s] Unexpected error: %s", label, e)
        return False, ""


def parse_submit_result(stdout: str) -> dict:
    """Parse submit.py stdout JSON."""
    try:
        return json.loads(stdout.strip())
    except Exception:
        return {"submitted": 0, "error": "could not parse submit output"}


def run_pipeline(source: str, dry_run: bool) -> dict:
    """
    Run a single pipeline: source → classify → submit.
    Returns a result dict for the run log.
    """
    started = datetime.now(timezone.utc).isoformat()
    result = {
        "source": source,
        "started_at": started,
        "scraped": 0,
        "classified": 0,
        "submitted": 0,
        "status": "ok",
    }

    # Step 1: scrape or search
    if source == "gumtree":
        scrape_cmd = ["uv", "run", str(SCRAPE), "gumtree", "--max", "100"]
    elif source == "hellopeter":
        scrape_cmd = ["uv", "run", str(SCRAPE), "hellopeter", "--max", "30"]
    elif source == "search":
        scrape_cmd = ["uv", "run", str(SEARCH), "--type", "all"]
    else:
        log.error("Unknown source: %s", source)
        result["status"] = "unknown_source"
        return result

    ok, scrape_out = run_step(scrape_cmd, f"{source}-scrape")
    if not ok:
        result["status"] = "scrape_failed"
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        return result

    try:
        scraped_leads = json.loads(scrape_out)
        result["scraped"] = len(scraped_leads) if isinstance(scraped_leads, list) else 0
    except Exception:
        result["scraped"] = 0

    log.info("[%s] Scraped: %d leads", source, result["scraped"])

    # Step 2: classify (1800s timeout — LLM calls ~2-3s each)
    classify_cmd = ["uv", "run", str(CLASSIFY)]
    ok, classify_out = run_step(classify_cmd, f"{source}-classify", stdin_data=scrape_out, timeout=1800)
    if not ok:
        result["status"] = "classify_failed"
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        return result

    try:
        classified_leads = json.loads(classify_out)
        result["classified"] = len(classified_leads) if isinstance(classified_leads, list) else 0
    except Exception:
        result["classified"] = 0

    log.info("[%s] Classified: %d leads", source, result["classified"])

    # Step 3: enrich — Exa phone lookup for "Pending Enrichment" leads
    enrich_cmd = ["uv", "run", str(ENRICH)]
    ok, enrich_out = run_step(enrich_cmd, f"{source}-enrich", stdin_data=classify_out, timeout=300)
    if not ok:
        log.warning("[%s] Enrich step failed — submitting un-enriched leads", source)
        enrich_out = classify_out  # fall through with original classify output

    try:
        enriched_leads = json.loads(enrich_out)
        qa_count = sum(1 for l in enriched_leads if l.get("status") == "Pending QA")
        enrich_count = sum(1 for l in enriched_leads if l.get("status") == "Pending Enrichment")
        log.info("[%s] After enrich: %d Pending QA, %d Pending Enrichment", source, qa_count, enrich_count)
    except Exception:
        pass

    # Step 4: submit
    submit_cmd = ["uv", "run", str(SUBMIT), "--source", source]
    if dry_run:
        submit_cmd.append("--dry-run")

    ok, submit_out = run_step(submit_cmd, f"{source}-submit", stdin_data=enrich_out)
    submit_result = parse_submit_result(submit_out)
    result["submitted"] = submit_result.get("submitted", 0)
    result["batch_id"] = submit_result.get("batch_id", "")

    if not ok:
        result["status"] = "submit_failed"
    else:
        result["status"] = "ok"

    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    log.info("[%s] Submitted: %d leads | status: %s", source, result["submitted"], result["status"])
    return result


# ── Main ──────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="B2C lead pipeline orchestrator — Hermes cron entry point"
    )
    parser.add_argument(
        "--source",
        choices=["gumtree", "hellopeter", "search", "all"],
        required=True,
        help="Which source to run",
    )
    parser.add_argument("--dry-run", action="store_true", help="Pass --dry-run to submit.py (no real POSTs)")
    return parser.parse_args()


def main() -> None:
    setup_logging()
    args = parse_args()

    run_id = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    log.info("=" * 60)
    log.info("Leadgen pipeline run: %s | source=%s | dry_run=%s", run_id, args.source, args.dry_run)
    log.info("=" * 60)

    sources = ["hellopeter", "gumtree", "search"] if args.source == "all" else [args.source]
    pipeline_results = []
    total_submitted = 0

    for source in sources:
        log.info("── %s pipeline ──────────────────────────────", source)
        result = run_pipeline(source, dry_run=args.dry_run)
        pipeline_results.append(result)
        if result["status"] == "ok":
            total_submitted += result.get("submitted", 0)
        else:
            log.warning("%s pipeline finished with status: %s", source, result["status"])

    # Write run log
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"run-{run_id}.json"
    log_data = {
        "run_id": run_id,
        "source": args.source,
        "dry_run": args.dry_run,
        "started_at": pipeline_results[0]["started_at"] if pipeline_results else "",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "pipelines": pipeline_results,
        "total_submitted": total_submitted,
    }
    log_file.write_text(json.dumps(log_data, indent=2, ensure_ascii=False))
    log.info("Run log → %s", log_file)

    # Telegram-ready summary
    now_sast = datetime.now().strftime("%Y-%m-%d %H:%M SAST")
    print(f"✅ Leadgen run complete ({now_sast})")
    for r in pipeline_results:
        src = r["source"].capitalize()
        if r["status"] == "ok":
            print(f"{src}: scraped={r.get('scraped', 0)}, classified={r.get('classified', 0)}, submitted={r.get('submitted', 0)}")
        else:
            print(f"{src}: FAILED ({r['status']})")
    print(f"Total submitted: {total_submitted} leads → Notion (Pending QA + Pending Enrichment)")

    # Exit 1 if all pipelines failed
    all_failed = all(r["status"] != "ok" for r in pipeline_results)
    if all_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# =============================================================
# b2c_run.py — Unified B2C Pipeline Runner
# Runs both B2C lead sources sequentially:
#   1. Gumtree scrape → bridge (filter + LLM + WhatsApp → webhook)
#   2. Hellopeter scrape → webhook
#
# Each pipeline is isolated: one failure doesn't block the other.
# Writes a structured JSON run log to logs/b2c-run-YYYY-MM-DD.json.
# =============================================================
# Usage:
#   uv run python scripts/b2c_run.py                     # full run
#   uv run python scripts/b2c_run.py --dry-run           # no POSTs
#   uv run python scripts/b2c_run.py --gumtree-only      # skip Hellopeter
#   uv run python scripts/b2c_run.py --hellopeter-only   # skip Gumtree
#   uv run python scripts/b2c_run.py --whatsapp          # enable WhatsApp name lookup
#   uv run python scripts/b2c_run.py --whatsapp --whatsapp-url http://127.0.0.1:3457
# =============================================================
# Cron example (twice daily at 06:00 + 18:00 SAST = 04:00 + 16:00 UTC):
#   0 4,16 * * * cd /opt/projects/cartrack-leadgen && uv run python scripts/b2c_run.py --whatsapp >> logs/cron-b2c.log 2>&1
# =============================================================

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Logging ──────────────────────────────────────────────────

log = logging.getLogger("b2c_run")


def setup_logging() -> None:
    """Configure console + file logging."""
    log.setLevel(logging.DEBUG)

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    log.addHandler(console)

    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    fh = logging.FileHandler(log_dir / f"b2c-run-{today}.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    log.addHandler(fh)


# ── Constants ─────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent
GUMTREE_SCRAPER = "scripts/gumtree_scrapling.py"
GUMTREE_BRIDGE  = "scripts/gumtree_to_b2c.py"
HELLOPETER      = "scripts/hellopeter_scraper.py"


# ── Pipeline runners ──────────────────────────────────────────

def _run_subprocess(cmd: list[str], label: str) -> tuple[bool, dict]:
    """Run a subprocess, capture stdout (JSON result) + stderr (logs).

    Returns (success, result_dict).
    """
    log.info("[%s] Running: %s", label, " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=600,  # 10 min hard limit per step
        )
        # Log stderr (the script's own progress output) at DEBUG
        for line in proc.stderr.strip().splitlines():
            log.debug("[%s] %s", label, line)

        if proc.returncode != 0:
            log.error("[%s] Process exited with code %d", label, proc.returncode)
            log.error("[%s] stderr tail: %s", label, proc.stderr[-500:])
            return False, {"error": f"exit code {proc.returncode}", "stderr_tail": proc.stderr[-200:]}

        # Parse stdout as JSON (all our scripts emit JSON to stdout)
        stdout = proc.stdout.strip()
        if not stdout:
            log.warning("[%s] No JSON output on stdout", label)
            return True, {"warning": "no stdout JSON"}

        try:
            result = json.loads(stdout)
            return result.get("ok", True), result
        except json.JSONDecodeError:
            log.warning("[%s] Could not parse stdout as JSON: %s", label, stdout[:200])
            return True, {"raw_stdout": stdout[:200]}

    except subprocess.TimeoutExpired:
        log.error("[%s] Timed out after 600s", label)
        return False, {"error": "subprocess timeout"}
    except Exception as e:
        log.error("[%s] Unexpected error: %s", label, e)
        return False, {"error": str(e)}


def run_gumtree(
    dry_run: bool = False,
    whatsapp: bool = False,
    whatsapp_url: str | None = None,
    max_ads: int = 20,
) -> dict:
    """Run the full Gumtree pipeline: scrape → bridge."""
    result = {"pipeline": "gumtree", "started_at": datetime.now(timezone.utc).isoformat()}

    # ── Step 1: Scrape ──
    scrape_cmd = ["uv", "run", "python", GUMTREE_SCRAPER, "--max", str(max_ads)]
    ok, scrape_result = _run_subprocess(scrape_cmd, "gumtree-scraper")
    result["scrape"] = scrape_result

    if not ok:
        log.error("[gumtree] Scrape step failed — aborting Gumtree pipeline")
        result["status"] = "scrape_failed"
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        return result

    out_file = scrape_result.get("out", "")
    log.info("[gumtree] Scraped %d ads → %s", scrape_result.get("count", "?"), out_file)

    # ── Step 2: Bridge ──
    bridge_cmd = ["uv", "run", "python", GUMTREE_BRIDGE]
    if out_file:
        bridge_cmd += ["--input", out_file]
    if dry_run:
        bridge_cmd.append("--dry-run")
    if whatsapp:
        bridge_cmd.append("--whatsapp")
    if whatsapp_url:
        bridge_cmd += ["--whatsapp-url", whatsapp_url]

    ok, bridge_result = _run_subprocess(bridge_cmd, "gumtree-bridge")
    result["bridge"] = bridge_result
    result["status"] = "ok" if ok else "bridge_failed"
    result["finished_at"] = datetime.now(timezone.utc).isoformat()

    log.info(
        "[gumtree] Bridge done: %d qualified, posted=%s",
        bridge_result.get("qualified", "?"),
        bridge_result.get("posted", False),
    )
    return result


def run_hellopeter(
    dry_run: bool = False,
    max_leads: int = 50,
    days: int = 90,
) -> dict:
    """Run the full Hellopeter pipeline: scrape → webhook."""
    result = {"pipeline": "hellopeter", "started_at": datetime.now(timezone.utc).isoformat()}

    cmd = ["uv", "run", "python", HELLOPETER, "--max", str(max_leads), "--days", str(days)]
    if not dry_run:
        cmd.append("--post")

    ok, run_result = _run_subprocess(cmd, "hellopeter")
    result["run"] = run_result
    result["status"] = "ok" if ok else "failed"
    result["finished_at"] = datetime.now(timezone.utc).isoformat()

    log.info("[hellopeter] Done: %d leads, status=%s", run_result.get("count", "?"), result["status"])
    return result


# ── CLI ───────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Unified B2C pipeline runner — Gumtree + Hellopeter → n8n → Notion"
    )
    parser.add_argument("--dry-run", action="store_true", help="Classify/enrich but don't POST to webhook")
    parser.add_argument("--gumtree-only", action="store_true", help="Run Gumtree pipeline only")
    parser.add_argument("--hellopeter-only", action="store_true", help="Run Hellopeter pipeline only")
    parser.add_argument("--whatsapp", action="store_true", help="Enable WhatsApp name lookup (Gumtree only)")
    parser.add_argument("--whatsapp-url", type=str, default=None, help="Override WhatsApp lookup URL")
    parser.add_argument("--max-ads", type=int, default=20, help="Max Gumtree ads to scrape (default: 20)")
    parser.add_argument("--max-leads", type=int, default=50, help="Max Hellopeter leads to collect (default: 50)")
    parser.add_argument("--days", type=int, default=90, help="Hellopeter: reviews from last N days (default: 90)")
    return parser.parse_args()


# ── Main ──────────────────────────────────────────────────────

def main() -> None:
    setup_logging()
    args = parse_args()

    run_id = f"B2C-RUN-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}"
    log.info("=" * 60)
    log.info("B2C Pipeline Run: %s", run_id)
    if args.dry_run:
        log.info("DRY RUN — no data will be POSTed to webhook")
    log.info("=" * 60)

    summary: dict = {
        "run_id": run_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": args.dry_run,
        "pipelines": {},
    }

    any_success = False

    # ── Gumtree pipeline ──
    if not args.hellopeter_only:
        log.info("")
        log.info("── Gumtree Pipeline ─────────────────────────────────")
        gumtree_result = run_gumtree(
            dry_run=args.dry_run,
            whatsapp=args.whatsapp,
            whatsapp_url=args.whatsapp_url,
            max_ads=args.max_ads,
        )
        summary["pipelines"]["gumtree"] = gumtree_result
        if gumtree_result.get("status") == "ok":
            any_success = True
        else:
            log.warning("Gumtree pipeline finished with status: %s", gumtree_result.get("status"))

    # ── Hellopeter pipeline ──
    if not args.gumtree_only:
        log.info("")
        log.info("── Hellopeter Pipeline ──────────────────────────────")
        hellopeter_result = run_hellopeter(
            dry_run=args.dry_run,
            max_leads=args.max_leads,
            days=args.days,
        )
        summary["pipelines"]["hellopeter"] = hellopeter_result
        if hellopeter_result.get("status") == "ok":
            any_success = True
        else:
            log.warning("Hellopeter pipeline finished with status: %s", hellopeter_result.get("status"))

    # ── Summary ──
    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    summary["overall_status"] = "ok" if any_success else "all_failed"

    log.info("")
    log.info("=" * 60)
    log.info("Run complete: %s | overall=%s", run_id, summary["overall_status"])
    log.info("=" * 60)

    # Write JSON run log
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    run_log_path = log_dir / f"b2c-run-{datetime.now().strftime('%Y-%m-%d')}.json"
    try:
        existing = []
        if run_log_path.exists():
            with open(run_log_path, encoding="utf-8") as f:
                existing = json.load(f)
        existing.append(summary)
        with open(run_log_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
        log.info("Run log → %s", run_log_path)
    except Exception as e:
        log.warning("Failed to write run log: %s", e)

    # Emit JSON to stdout for shell piping
    print(json.dumps({"ok": any_success, "run_id": run_id, "status": summary["overall_status"]}))

    # Exit 1 if all pipelines failed (useful for cron alerting)
    if not any_success:
        sys.exit(1)


if __name__ == "__main__":
    main()

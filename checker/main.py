"""Entrypoint: fetch spend, evaluate pace, push an ntfy notification if warranted.

Run via cron daily. Exit code 0 on success (whether or not a notification was sent),
non-zero on a hard error (bad config, Firefly/ntfy failure).

Flags:
    --dry-run          Compute and print the decision; do NOT notify or write state.
    --date YYYY-MM-DD  With --dry-run only: evaluate as if today were this date.
    --test-notify      Send a test notification and exit.
    --config PATH      Use an explicit config file.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import pace
from .config import Config, ConfigError, load
from .firefly import FireflyClient, FireflyError
from .notify import NotifyError, NtfyNotifier
from .state import State, should_notify

# ntfy priority (1=min … 5=max) and tags per band. Tags matching emoji short codes are
# rendered as emoji by the ntfy apps.
BAND_PRIORITY = {"behind": 3, "urgent": 4, "final": 5, "met": 3}
BAND_TAGS = {
    "behind": ["credit_card"],
    "urgent": ["credit_card"],
    "final": ["credit_card"],
    "met": ["tada"],
}
ERROR_PRIORITY = 4
ERROR_TAGS = ["warning"]


def _today(cfg: Config) -> date:
    if cfg.timezone and cfg.timezone.lower() != "localtime":
        return datetime.now(ZoneInfo(cfg.timezone)).date()
    return datetime.now().date()


def _notifier(cfg: Config) -> NtfyNotifier:
    return NtfyNotifier(cfg.ntfy_url, cfg.ntfy_topic, cfg.ntfy_token)


def _notify_error(cfg: Config, detail: str) -> None:
    """Best-effort alert via ntfy when we can't read Firefly.

    Swallows notify failures (if ntfy is also down there's nothing more we can do but log).
    """
    try:
        _notifier(cfg).send(
            "⚠️ Firefly checker failed",
            f"Couldn't read your card spend from Firefly: {detail} "
            "The monthly spend check did not run.",
            priority=ERROR_PRIORITY,
            tags=ERROR_TAGS,
        )
        print("  ✓ error notification sent via ntfy")
    except NotifyError as exc:
        print(f"  (could not send error notification via ntfy either: {exc})", file=sys.stderr)


def _run(cfg: Config, *, dry_run: bool, today: date | None = None) -> int:
    today = today or _today(cfg)
    month_start = today.replace(day=1)
    month_key = today.strftime("%Y-%m")

    client = FireflyClient(cfg.firefly_url, cfg.firefly_pat, cfg.currency)
    account_name = client.verify_account(cfg.account_id)
    net = client.net_spend(cfg.account_id, month_start, today)

    decision = pace.evaluate(net, today, target=cfg.target, currency=cfg.currency)

    print(
        f"[{today.isoformat()}] account={cfg.account_id} ({account_name}) "
        f"net={net:.2f} {cfg.currency} expected≈{decision.expected:.2f} band={decision.band}"
    )
    print(f"  → {decision.title}: {decision.message}")

    state = State.load(cfg.resolved_state_path)
    will_notify = should_notify(state, decision, month_key)

    if not will_notify:
        print("  (no notification: on track or already notified at this urgency)")
        return 0

    if dry_run:
        print("  (dry-run: would notify, but not sending and not saving state)")
        return 0

    _notifier(cfg).send(
        decision.title,
        decision.message,
        priority=BAND_PRIORITY.get(decision.band, 3),
        tags=BAND_TAGS.get(decision.band),
    )
    state.save(cfg.resolved_state_path)
    print("  ✓ notification sent via ntfy")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="firefly-checker", description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="evaluate without notifying or writing state")
    parser.add_argument("--date", help="with --dry-run: evaluate as if today were YYYY-MM-DD")
    parser.add_argument("--test-notify", action="store_true", help="send a test notification and exit")
    parser.add_argument("--config", help="path to config.toml")
    args = parser.parse_args(argv)

    as_of: date | None = None
    if args.date:
        if not args.dry_run:
            parser.error("--date can only be used together with --dry-run")
        try:
            as_of = date.fromisoformat(args.date)
        except ValueError:
            parser.error(f"--date must be YYYY-MM-DD, got {args.date!r}")

    try:
        cfg = load(Path(args.config) if args.config else None)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    try:
        if args.test_notify:
            _notifier(cfg).send(
                "Firefly checker test",
                "If you can read this, notifications work. ✅",
                tags=["white_check_mark"],
            )
            print("✓ test notification sent")
            return 0
        return _run(cfg, dry_run=args.dry_run, today=as_of)
    except FireflyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        if not args.dry_run:
            _notify_error(cfg, str(exc))
        return 1
    except NotifyError as exc:
        # The Firefly read worked but the ntfy push failed — can't reliably alert via ntfy.
        print(f"Error sending notification: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

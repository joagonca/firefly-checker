"""Entrypoint: fetch spend, evaluate pace, notify Home Assistant if warranted.

Run via cron daily. Exit code 0 on success (whether or not a notification was sent),
non-zero on a hard error (bad config, Firefly/HA failure).

Flags:
    --dry-run       Compute and print the decision; do NOT notify or write state.
    --test-notify   Send a test notification to Home Assistant and exit.
    --config PATH   Use an explicit config file.
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
from .notify import HomeAssistantNotifier, NotifyError
from .state import State, should_notify


def _today(cfg: Config) -> date:
    if cfg.timezone and cfg.timezone.lower() != "localtime":
        return datetime.now(ZoneInfo(cfg.timezone)).date()
    return datetime.now().date()


def _notify_error(cfg: Config, detail: str) -> None:
    """Best-effort alert to Home Assistant when we can't read Firefly.

    Swallows notify failures (if HA is also down there's nothing more we can do but log).
    """
    try:
        notifier = HomeAssistantNotifier(cfg.ha_url, cfg.ha_token, cfg.ha_notify_service)
        notifier.send(
            "⚠️ Firefly checker failed",
            f"Couldn't read your card spend from Firefly: {detail} "
            "The monthly spend check did not run.",
        )
        print("  ✓ error notification sent to Home Assistant")
    except NotifyError as exc:
        print(f"  (could not send error notification to HA either: {exc})", file=sys.stderr)


def _run(cfg: Config, *, dry_run: bool) -> int:
    today = _today(cfg)
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

    notifier = HomeAssistantNotifier(cfg.ha_url, cfg.ha_token, cfg.ha_notify_service)
    notifier.send(decision.title, decision.message)
    state.save(cfg.resolved_state_path)
    print("  ✓ notification sent to Home Assistant")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="firefly-checker", description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="evaluate without notifying or writing state")
    parser.add_argument("--test-notify", action="store_true", help="send a test HA notification and exit")
    parser.add_argument("--config", help="path to config.toml")
    args = parser.parse_args(argv)

    try:
        cfg = load(Path(args.config) if args.config else None)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    try:
        if args.test_notify:
            notifier = HomeAssistantNotifier(cfg.ha_url, cfg.ha_token, cfg.ha_notify_service)
            notifier.send("Firefly checker test", "If you can read this, notifications work. ✅")
            print("✓ test notification sent")
            return 0
        return _run(cfg, dry_run=args.dry_run)
    except FireflyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        if not args.dry_run:
            _notify_error(cfg, str(exc))
        return 1
    except NotifyError as exc:
        # The Firefly read worked but the HA push failed — can't reliably alert via HA.
        print(f"Error sending notification: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

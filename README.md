# Firefly credit-card spend checker

A small cron job that makes sure you hit a **minimum monthly spend (default 250€)** on a
specific credit card tracked in [Firefly III](https://www.firefly-iii.org/). It reads your
spending via the Firefly API, compares it against a *linear pace target*, and — when you're
falling behind — pushes an escalating nudge to **Home Assistant**. It also sends a one-time
"🎉 target reached" when you cross the line.

It runs daily but **won't spam you**: it only notifies when your urgency increases, plus a
daily push in the final 3 days if you're still short.

## How the pacing works

Each run computes the linear pace target for today: `target × day / days_in_month`. You get
a warning only when your net spend falls below a fraction of that pace, and the tolerance
tightens as the month goes on:

| Part of month        | Warn if spend below | Band      |
|----------------------|---------------------|-----------|
| Days 1–10            | _silent_ — no warnings, to avoid early-spend pressure | — |
| Days 11–20           | 60% of pace         | `behind`  |
| Day 21 → final window| 80% of pace         | `urgent`  |
| Final 3 days of month| 100% of pace        | `final`   |

The "🎉 target reached" message is the one thing that can arrive during the first 10 days —
it's good news, not pressure.

"Spend" = **net of refunds**: withdrawals out of the card minus refunds/credits into it,
in the configured currency. Card payments/transfers are not counted.

## Setup

```sh
cd firefly-checker
python -m venv .venv
.venv/bin/pip install -r requirements.txt

cp config.example.toml config.toml
chmod 600 config.toml
$EDITOR config.toml
```

You need:

- **Firefly URL + PAT** — in Firefly: *Options → Profile → OAuth → Personal Access Tokens*.
- **Account ID** — open the credit-card account in Firefly; the numeric ID is in the URL
  (`/accounts/show/12` → `12`). You can also run with a guessed ID and `--dry-run`; a wrong
  ID fails loudly.
- **Home Assistant URL + long-lived token** — HA: *Profile → Security → Long-lived access
  tokens*.
- **Notify service** — the bit after `notify.`, e.g. for `notify.mobile_app_my_phone` use
  `mobile_app_my_phone`.

Secrets can also be passed via environment instead of the file:
`FIREFLY_PAT` and `HA_TOKEN` override the TOML values.

## Try it before trusting it

```sh
# Send a test push to confirm the HA side works:
.venv/bin/python -m checker.main --test-notify

# Compute this month's net spend and the decision, WITHOUT notifying or saving state:
.venv/bin/python -m checker.main --dry-run
```

## Schedule it (host cron)

Run once a day, e.g. 09:00:

```cron
0 9 * * * cd /home/jonas/Code/firefly-checker && .venv/bin/python -m checker.main >> ~/.local/state/firefly-checker/run.log 2>&1
```

Exit code is `0` on success (whether or not it notified), `1` on a Firefly/HA error, `2` on
a config error — so cron mail / log will show problems.

## State

De-duplication state lives at `~/.local/state/firefly-checker/state.json` (configurable via
`behaviour.state_path`). It resets automatically at the start of each month. Delete it to
reset notifications.

## Tests

```sh
.venv/bin/pip install pytest
.venv/bin/python -m pytest
```

The pacing and de-duplication logic (`checker/pace.py`, `checker/state.py`) are pure and
fully unit-tested without touching Firefly or Home Assistant.

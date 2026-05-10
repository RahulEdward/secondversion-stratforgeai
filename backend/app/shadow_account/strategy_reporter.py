"""StratForge adapter for Vibe-Trading's Shadow Account reporter.

We reuse Vibe-Trading's ``render_shadow_report`` **verbatim** (same
templates/shadow_report.html + shadow_report.css + same chart renderers),
and just build the two input dataclasses (``ShadowProfile`` +
``ShadowBacktestResult``) from StratForge's run_dir artifacts.

This way the report layout, styling, and PDF pipeline are byte-identical
to Vibe-Trading — we only swap the *data source* from "user trade journal"
to "StratForge backtest run_dir".
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Force non-interactive matplotlib backend before any chart code imports.
import matplotlib
matplotlib.use("Agg")

import pandas as pd

from app.shadow_account.models import (
    AttributionBreakdown,
    ShadowBacktestResult,
    ShadowProfile,
    ShadowRule,
)
from app.shadow_account.reporter import render_shadow_report

logger = logging.getLogger(__name__)


def _load_csv(p: Path) -> pd.DataFrame | None:
    if not p.exists():
        return None
    try:
        return pd.read_csv(p)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to read %s: %s", p, exc)
        return None


def _flatten_metrics(df: pd.DataFrame | None) -> dict[str, float]:
    if df is None or df.empty:
        return {}
    row = df.iloc[0].to_dict()
    out: dict[str, float] = {}
    for k, v in row.items():
        if isinstance(v, (int, float)) and not pd.isna(v):
            out[k] = float(v)
    return out


def _first_date_column(df: pd.DataFrame) -> str | None:
    for candidate in ("timestamp", "date", "datetime", "time"):
        if candidate in df.columns:
            return candidate
    return None


def _build_equity_curve(equity_df: pd.DataFrame | None) -> list[tuple[str, float]]:
    """Convert StratForge equity.csv to the Vibe-Trading (date_str, equity) list."""
    if equity_df is None or equity_df.empty or "equity" not in equity_df.columns:
        return []
    date_col = _first_date_column(equity_df)
    if date_col is None:
        return [(str(i), float(v)) for i, v in enumerate(equity_df["equity"].tolist())]
    out: list[tuple[str, float]] = []
    for dt, eq in zip(equity_df[date_col], equity_df["equity"]):
        try:
            out.append((str(dt)[:19], float(eq)))
        except (TypeError, ValueError):
            continue
    return out


def _build_counterfactual_trades(trades_df: pd.DataFrame | None) -> tuple[dict[str, Any], ...]:
    """Pick the 5 most impactful trades for the 'Counterfactual Top 5' table.

    In the journal flow these are the trades the shadow would have handled
    differently. For a single backtest we surface the 5 largest-loss trades
    so users see where the strategy bled.
    """
    if trades_df is None or trades_df.empty or "pnl" not in trades_df.columns:
        return ()
    # Only keep SELL / exit rows that carry realized PnL
    if "side" in trades_df.columns:
        exits = trades_df[trades_df["side"].astype(str).str.lower().isin({"sell", "buy_to_cover", "cover"})]
    else:
        exits = trades_df
    exits = exits.dropna(subset=["pnl"])
    if exits.empty:
        return ()
    worst = exits.nsmallest(5, "pnl")
    rows: list[dict[str, Any]] = []
    for _, r in worst.iterrows():
        symbol = str(r.get("code", r.get("symbol", "-")))
        buy_dt = str(r.get("timestamp", ""))[:19]
        sell_dt = str(r.get("timestamp", ""))[:19]
        hold_days = float(r.get("holding_days", 0.0) or 0.0)
        pnl = float(r.get("pnl", 0.0) or 0.0)
        rows.append({
            "symbol":  symbol,
            "buy_dt":  buy_dt,
            "sell_dt": sell_dt,
            "hold_days": hold_days,
            "pnl":     pnl,
            "impact":  -pnl,                # "would-have-saved" if avoided
            "reason":  "rule_violation",    # template has this in its label map
        })
    return tuple(rows)


def _pair_trade_pnls(trades_df: pd.DataFrame | None) -> list[float]:
    """Return realized per-roundtrip PnL values (skip zero-open rows)."""
    if trades_df is None or trades_df.empty or "pnl" not in trades_df.columns:
        return []
    vals = pd.to_numeric(trades_df["pnl"], errors="coerce").dropna()
    return [float(v) for v in vals if v != 0]


def _classify_market(dataset_id: str) -> str:
    """Best-effort classification for the `source_market` label in the template."""
    lower = dataset_id.lower() if dataset_id else ""
    if any(x in lower for x in ("btc", "eth", "usdt", "crypto")):
        return "crypto"
    if any(x in lower for x in ("nasdaq", "spx", "us_", ".us", "nyse")):
        return "us"
    if ".hk" in lower:
        return "hk"
    if any(x in lower for x in (".sh", ".sz", "a-share", "ashare", "china_a")):
        return "china_a"
    return "other"


def _default_rules(strategy_name: str) -> tuple[ShadowRule, ...]:
    """Build a single synthetic rule card so Section 2 never renders empty.

    For the StratForge flow we haven't extracted if/then rules from a journal,
    so we surface the strategy name itself as 'rule R1'.
    """
    return (
        ShadowRule(
            rule_id="R1",
            human_text=strategy_name or "Strategy as coded in signal_engine.py",
            entry_condition={"source": "signal_engine.py"},
            exit_condition={"source": "signal_engine.py"},
            holding_days_range=(1, 30),
            support_count=1,
            coverage_rate=1.0,
            sample_trades=tuple(),
            weight=1.0,
        ),
    )


def render_strategy_report(
    *,
    run_dir: Path,
    strategy_name: str,
    output_dir: Path,
    report_id: str | None = None,
    takeaway: str = "",  # kept for API back-compat; not rendered by shadow template
    dataset_id: str = "",
    interval: str = "",
    date_range: tuple[str, str] = ("", ""),
    initial_cash: float = 1_000_000.0,
) -> dict[str, Any]:
    """Build ShadowProfile + ShadowBacktestResult from run_dir and render.

    Returns the same dict shape as ``render_shadow_report``: html_path,
    pdf_path, engine, plus ``report_id`` we allocated.
    """
    run_dir = Path(run_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if report_id is None:
        report_id = f"rp_{secrets.token_hex(8)}"

    # Load StratForge artifacts
    metrics_df = _load_csv(run_dir / "artifacts" / "metrics.csv")
    equity_df = _load_csv(run_dir / "artifacts" / "equity.csv")
    trades_df = _load_csv(run_dir / "artifacts" / "trades.csv")

    metrics = _flatten_metrics(metrics_df)

    # Build a ShadowProfile — Section 1 of the template consumes this.
    trade_pnls = _pair_trade_pnls(trades_df)
    profitable = sum(1 for v in trade_pnls if v > 0)
    total_rt = max(len(trade_pnls), 1)
    primary_market = _classify_market(dataset_id)
    typical_hold = (5.0, 10.0)
    if trades_df is not None and "holding_days" in trades_df.columns:
        hold = pd.to_numeric(trades_df["holding_days"], errors="coerce").dropna()
        if not hold.empty:
            typical_hold = (float(hold.median()), float(hold.quantile(0.75)))

    profile = ShadowProfile(
        shadow_id=report_id,  # reuse report_id as shadow_id so file names align
        created_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        journal_hash=report_id,
        source_market=primary_market,
        profitable_roundtrips=profitable,
        total_roundtrips=total_rt,
        date_range=(date_range[0] or "", date_range[1] or ""),
        profile_text=(
            f"{strategy_name or 'Strategy'} ran on {dataset_id or 'the active dataset'}"
            f"{' at ' + interval if interval else ''}. "
            f"{total_rt} roundtrips recorded ({profitable} profitable). "
            f"Median holding {typical_hold[0]:.1f} days."
        ),
        rules=_default_rules(strategy_name),
        preferred_markets=(primary_market,),
        typical_holding_days=typical_hold,
    )

    # Build ShadowBacktestResult — Sections 3-6 consume this.
    combined = dict(metrics)
    if "total_return" in combined and "annual_return" not in combined:
        combined["annual_return"] = combined["total_return"]

    equity_pts = _build_equity_curve(equity_df)

    shadow_pnl = float(initial_cash * combined.get("total_return", 0.0))
    real_pnl = 0.0              # No journal here — this is "what the shadow made"
    delta_pnl = shadow_pnl - real_pnl

    counterfactual = _build_counterfactual_trades(trades_df)

    result = ShadowBacktestResult(
        shadow_id=report_id,
        per_market={primary_market: dict(combined)},
        combined=combined,
        equity_curves={"combined": equity_pts},
        attribution=AttributionBreakdown(
            missed_signals_pnl=0.0,
            noise_trades_pnl=0.0,
            early_exit_pnl=0.0,
            late_exit_pnl=shadow_pnl if shadow_pnl < 0 else 0.0,
            overtrading_pnl=0.0,
            counterfactual_trades=counterfactual,
        ),
        shadow_total_pnl=shadow_pnl,
        real_total_pnl=real_pnl,
        delta_pnl=delta_pnl,
    )

    # Hand off to the untouched Vibe-Trading reporter.
    rendered = render_shadow_report(
        profile,
        result,
        today_signals=None,
        output_dir=output_dir,
    )

    # Inline file:// chart URIs as base64 data URIs so the HTML renders
    # correctly when served over HTTP (iframe in Preview panel).
    # Vibe-Trading's reporter saves PNGs under <output_dir>/<id>_assets/*.png
    # and references them via file:// URIs — we rewrite to data URIs here.
    html_path = Path(rendered.get("html_path", ""))
    if html_path.exists():
        _inline_chart_images(html_path)

    rendered["report_id"] = report_id

    # Compute a light grade from the combined metrics so the tool layer can
    # still surface it in chat (the HTML itself doesn't need it).
    rendered["grade"] = _grade_from(combined)
    rendered["verdict"] = _verdict_from(combined)
    rendered["score"] = _score_from(combined)

    return rendered


# ── Grading (same gates as before so the tool layer's API is unchanged) ──

def _grade_from(m: dict[str, float]) -> str:
    sharpe = m.get("sharpe", 0.0) or 0.0
    max_dd = m.get("max_drawdown", 0.0) or 0.0
    trades = int(m.get("trade_count", 0) or 0)
    pf = m.get("profit_factor", 0.0) or 0.0
    if trades < 30 or pf < 1.0 or max_dd < -0.5:
        return "F"
    if sharpe >= 1.5 and pf >= 1.5 and max_dd > -0.2:
        return "A"
    if sharpe >= 1.0 and pf >= 1.2:
        return "B"
    if sharpe >= 0.5:
        return "C"
    return "D"


def _verdict_from(m: dict[str, float]) -> str:
    g = _grade_from(m)
    if g in ("A", "A+"):
        return "deploy"
    if g == "B":
        return "deploy"
    if g in ("C", "D"):
        return "iterate"
    return "reject"


def _score_from(m: dict[str, float]) -> float:
    sharpe = m.get("sharpe", 0.0) or 0.0
    pf = m.get("profit_factor", 0.0) or 0.0
    total_return = m.get("total_return", 0.0) or 0.0
    max_dd = m.get("max_drawdown", 0.0) or 0.0
    win_rate = m.get("win_rate", 0.0) or 0.0
    trades = int(m.get("trade_count", 0) or 0)

    score = 0.0
    score += min(30.0, max(0.0, sharpe * 15.0))
    score += min(25.0, max(0.0, (pf - 1.0) * 25.0))
    score += min(15.0, max(0.0, (total_return + 0.5) * 15.0))
    score += min(15.0, max(0.0, (0.5 + max_dd) * 30.0))
    score += min(10.0, max(0.0, (win_rate - 0.3) * 50.0))
    score += min(5.0, trades / 500 * 5.0)
    return round(score, 1)


# ── HTML post-processor: inline file:// chart PNGs as base64 data URIs ──

import re as _re
from base64 import b64encode as _b64encode
from urllib.parse import urlparse as _urlparse, unquote as _unquote

_FILE_URI_PATTERN = _re.compile(r'src="(file://[^"]+\.png)"')


def _inline_chart_images(html_path: Path) -> None:
    """Rewrite file:// chart references in <html_path> to base64 data URIs.

    Browsers refuse to load local file:// images inside an HTTP-served
    iframe for security reasons. We read each referenced PNG from disk
    and inline it so the <img> works everywhere (iframe, WeasyPrint, local
    file open). The raw PNG files are left on disk for PDF / debug use.
    """
    try:
        html = html_path.read_text(encoding="utf-8")
    except OSError:
        return

    def _replace(match: _re.Match) -> str:
        uri = match.group(1)
        parsed = _urlparse(uri)
        # Windows: parsed.path is something like '/C:/Users/...'
        local = _unquote(parsed.path)
        if local.startswith("/") and len(local) > 3 and local[2] == ":":
            local = local[1:]
        path = Path(local)
        if not path.exists():
            return match.group(0)
        try:
            data = _b64encode(path.read_bytes()).decode("ascii")
        except OSError:
            return match.group(0)
        return f'src="data:image/png;base64,{data}"'

    new_html = _FILE_URI_PATTERN.sub(_replace, html)
    if new_html != html:
        html_path.write_text(new_html, encoding="utf-8")

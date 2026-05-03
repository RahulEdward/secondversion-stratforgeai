"""Report context builder + HTML renderer (Phase 8, Slice 2).

Inputs: persisted artifact IDs (a required `backtest_id`, plus optional
`monte_carlo_id`, `walk_forward_id`, `optimization_id`). We read the JSONs
(and sidecar parquets for equity + trades), assemble a Plotly-friendly
context, run the scoring engine, and write a self-contained HTML file to
`workspaces/<pid>/reports/rp_<id>.html`.

Design notes:
    - Plotly loads via CDN — the HTML is ~20-40 KB instead of 3 MB.
    - Every figure is embedded as a JSON dict (via `pio.to_json`) and
      rendered client-side with `Plotly.newPlot`. This also lets the PDF
      export path reuse the same figures without a separate image pipeline.
    - All sections are optional *except* cover + metrics + verdict. If a
      mc/wf/opt id wasn't supplied, those sections just aren't rendered.
    - Reports are soft-capped at 50 per project. On every render, the
      oldest rp_* files are deleted (html + json + pdf together).
"""

from __future__ import annotations

import json
import math
import secrets
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..paths import workspace_dir
from ..scoring import score_from_result_dicts


# ─── Constants ──────────────────────────────────────────────────────────

REPORT_CACHE_CAP = 50  # soft per-project cap
# Serve Plotly from our own backend instead of cdn.plot.ly. The python
# `plotly` package ships its own copy of plotly.min.js, which we expose
# at /api/assets/plotly.min.js. This guarantees charts render even when
# the user is offline or on a network that blocks the public CDN — the
# previous symptom was empty `.fig` boxes in Equity / Drawdown sections.
#
# Absolute URL is required because the PDF exporter loads the HTML via a
# `file://` URL through Playwright; a relative `/api/...` would resolve
# against the filesystem root there. For the iframe (loaded over HTTP)
# the absolute host is identical to its origin, so no CORS issue.
PLOTLY_CDN = "http://127.0.0.1:8765/api/assets/plotly.min.js"

# Dark palette tuned to match the Claude Code UI vibe of the app.
THEME = {
    "bg": "#0d0d0d",
    "panel": "#161616",
    "text": "#e5e5e5",
    "muted": "#8a8a8a",
    "accent": "#c89b6e",   # warm amber — brand
    "good": "#4ade80",     # green
    "bad": "#ef4444",      # red
    "grid": "#262626",
}

GRADE_COLORS = {
    "A+": "#4ade80", "A": "#4ade80", "A-": "#86efac",
    "B+": "#c89b6e", "B": "#c89b6e", "B-": "#d4a574",
    "C+": "#eab308", "C": "#eab308", "C-": "#fbbf24",
    "D": "#f97316", "F": "#ef4444",
}


# ─── IDs / paths ────────────────────────────────────────────────────────


def _report_id() -> str:
    return f"rp_{secrets.token_hex(8)}"


def _reports_dir(project_id: str) -> Path:
    p = workspace_dir(project_id) / "reports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def report_paths(project_id: str, report_id: str) -> Dict[str, Path]:
    """Return the canonical file locations for a report (json/html/pdf)."""
    d = _reports_dir(project_id)
    return {
        "json": d / f"{report_id}.json",
        "html": d / f"{report_id}.html",
        "pdf": d / f"{report_id}.pdf",
    }


# ─── Artifact lookup ─────────────────────────────────────────────────────


def _load_backtest(bt_id: str) -> Tuple[str, Dict[str, Any]]:
    """Find the project owning `bt_id` by scanning workspaces. Returns
    (project_id, bt_json)."""
    from .. import paths as _paths

    for ws in _paths.WORKSPACES_DIR.iterdir():
        if not ws.is_dir():
            continue
        cand = ws / "backtests" / f"{bt_id}.json"
        if cand.exists():
            data = json.loads(cand.read_text(encoding="utf-8"))
            project_id = data.get("project_id") or ws.name
            return project_id, data
    raise ValueError(f"Backtest {bt_id!r} not found in any workspace")


def _load_validation(project_id: str, val_id: str) -> Optional[Dict[str, Any]]:
    p = workspace_dir(project_id) / "validations" / f"{val_id}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _load_optimization(project_id: str, opt_id: str) -> Optional[Dict[str, Any]]:
    p = workspace_dir(project_id) / "optimizations" / f"{opt_id}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _load_equity(project_id: str, bt_id: str) -> Optional[pd.DataFrame]:
    p = workspace_dir(project_id) / "backtests" / f"{bt_id}_equity.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        if "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"])
        return df
    except Exception:
        return None


def _load_trades(project_id: str, bt_id: str) -> Optional[pd.DataFrame]:
    p = workspace_dir(project_id) / "backtests" / f"{bt_id}_trades.parquet"
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception:
        return None


# ─── Small formatters used by the template ──────────────────────────────


def _fmt_pct(v: Any, digits: int = 2) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "—"


def _fmt_num(v: Any, digits: int = 3) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return "—"
        return f"{f:.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_int(v: Any) -> str:
    if v is None:
        return "—"
    try:
        return f"{int(v):,}"
    except (TypeError, ValueError):
        return "—"


def _fmt_date(v: Any) -> str:
    if v is None:
        return "—"
    s = str(v)
    # Truncate ISO8601 at minute resolution for readability.
    return s[:16].replace("T", " ")


# ─── Plotly figures ─────────────────────────────────────────────────────


def _base_layout(title: Optional[str] = None, height: int = 360) -> Dict[str, Any]:
    return dict(
        title=dict(text=title, font=dict(color=THEME["text"], size=14)) if title else None,
        paper_bgcolor=THEME["panel"],
        plot_bgcolor=THEME["panel"],
        font=dict(color=THEME["text"], family="Inter, sans-serif", size=12),
        margin=dict(l=50, r=20, t=40 if title else 20, b=40),
        height=height,
        xaxis=dict(gridcolor=THEME["grid"], zerolinecolor=THEME["grid"],
                   tickfont=dict(color=THEME["muted"])),
        yaxis=dict(gridcolor=THEME["grid"], zerolinecolor=THEME["grid"],
                   tickfont=dict(color=THEME["muted"])),
        hovermode="x unified",
        hoverlabel=dict(bgcolor=THEME["bg"], bordercolor=THEME["accent"],
                        font=dict(color=THEME["text"])),
        showlegend=False,
    )


def _fig_to_json(fig: go.Figure) -> str:
    """Serialise a plotly figure for embedding in HTML."""
    return pio.to_json(fig, validate=False)


def _equity_figure(eq_df: pd.DataFrame, init_cash: float) -> Optional[str]:
    if eq_df is None or eq_df.empty:
        return None
    x = eq_df["time"] if "time" in eq_df.columns else eq_df.index
    y = eq_df["equity"].astype(float)
    fig = go.Figure(
        data=[go.Scatter(
            x=x, y=y, mode="lines",
            line=dict(color=THEME["accent"], width=2),
            fill="tozeroy",
            fillcolor="rgba(200, 155, 110, 0.08)",
            name="Equity",
            hovertemplate="<b>%{x|%Y-%m-%d %H:%M}</b><br>Equity $%{y:,.2f}<extra></extra>",
        )],
        layout=_base_layout("Equity curve", height=340),
    )
    fig.add_hline(
        y=init_cash,
        line=dict(color=THEME["muted"], width=1, dash="dot"),
        annotation_text=f"Start ${init_cash:,.0f}",
        annotation_position="bottom right",
        annotation_font_color=THEME["muted"],
    )
    return _fig_to_json(fig)


def _drawdown_figure(eq_df: pd.DataFrame) -> Optional[str]:
    if eq_df is None or eq_df.empty or "drawdown" not in eq_df.columns:
        return None
    x = eq_df["time"] if "time" in eq_df.columns else eq_df.index
    y = (eq_df["drawdown"].astype(float) * 100.0)
    fig = go.Figure(
        data=[go.Scatter(
            x=x, y=y, mode="lines",
            line=dict(color=THEME["bad"], width=1.5),
            fill="tozeroy",
            fillcolor="rgba(239, 68, 68, 0.18)",
            name="Drawdown",
            hovertemplate="<b>%{x|%Y-%m-%d %H:%M}</b><br>Drawdown %{y:.2f}%<extra></extra>",
        )],
        layout=_base_layout("Drawdown (%)", height=280),
    )
    return _fig_to_json(fig)


def _trades_histogram(trades_df: pd.DataFrame) -> Optional[str]:
    if trades_df is None or trades_df.empty:
        return None
    # vectorbt `records_readable` column for fractional return is "Return".
    ret_col = None
    for c in ("Return", "return", "PnL %"):
        if c in trades_df.columns:
            ret_col = c
            break
    if ret_col is None:
        return None
    vals = pd.to_numeric(trades_df[ret_col], errors="coerce").dropna().astype(float)
    if vals.empty:
        return None
    vals_pct = vals * 100.0
    colors = [THEME["good"] if v >= 0 else THEME["bad"] for v in vals_pct]
    fig = go.Figure(
        data=[go.Histogram(
            x=vals_pct, nbinsx=30,
            marker=dict(color=THEME["accent"], line=dict(color=THEME["grid"], width=1)),
            hovertemplate="Return %{x:.2f}%<br>Count %{y}<extra></extra>",
        )],
        layout=_base_layout("Per-trade return distribution (%)", height=280),
    )
    fig.add_vline(
        x=0, line=dict(color=THEME["muted"], width=1, dash="dot"),
    )
    # Force a dummy marker colour pattern just so the signature matches
    # (histograms don't take per-bar colour easily in Plotly, but the
    # single-colour tone here is intentional — red/green mixing looks busy).
    _ = colors
    return _fig_to_json(fig)


def _mc_percentile_figure(mc: Dict[str, Any]) -> Optional[str]:
    """Horizontal bar chart: p5/p25/p50/p75/p95 for total_return and max_drawdown."""
    pct = mc.get("percentiles") or {}
    tr = pct.get("total_return")
    dd = pct.get("max_drawdown")
    if not tr or not dd:
        return None
    levels = ["p5", "p25", "p50", "p75", "p95"]
    tr_vals = [float(tr.get(p, 0)) * 100.0 for p in levels]
    dd_vals = [float(dd.get(p, 0)) * 100.0 for p in levels]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=levels, x=tr_vals, orientation="h",
        name="Total return %",
        marker=dict(color=THEME["good"]),
        hovertemplate="%{y}: %{x:.2f}%<extra>total return</extra>",
    ))
    fig.add_trace(go.Bar(
        y=levels, x=dd_vals, orientation="h",
        name="Max drawdown %",
        marker=dict(color=THEME["bad"]),
        hovertemplate="%{y}: %{x:.2f}%<extra>max DD</extra>",
    ))
    layout = _base_layout("Monte Carlo percentile bands", height=340)
    layout["barmode"] = "group"
    layout["showlegend"] = True
    layout["legend"] = dict(
        orientation="h", yanchor="bottom", y=1.02, x=0,
        font=dict(color=THEME["text"]),
    )
    fig.update_layout(**layout)
    return _fig_to_json(fig)


def _wf_folds_figure(wf: Dict[str, Any]) -> Optional[str]:
    """Grouped bar chart: IS Sharpe vs OOS Sharpe per fold."""
    folds = wf.get("folds") or []
    if not folds:
        return None
    labels = [f"Fold {f.get('fold_id', i)}" for i, f in enumerate(folds)]
    is_sh = [(f.get("in_sample_metrics") or {}).get("sharpe") for f in folds]
    oo_sh = [(f.get("out_sample_metrics") or {}).get("sharpe") for f in folds]
    # Coerce to 0 for None so bars render (tooltip still shows actual below).
    is_arr = [float(v) if v is not None else 0.0 for v in is_sh]
    oo_arr = [float(v) if v is not None else 0.0 for v in oo_sh]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=labels, y=is_arr, name="In-sample Sharpe",
        marker=dict(color=THEME["accent"]),
        hovertemplate="%{x}<br>IS Sharpe %{y:.2f}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=labels, y=oo_arr, name="Out-of-sample Sharpe",
        marker=dict(color=THEME["good"]),
        hovertemplate="%{x}<br>OOS Sharpe %{y:.2f}<extra></extra>",
    ))
    layout = _base_layout("Walk-forward — IS vs OOS Sharpe per fold", height=320)
    layout["barmode"] = "group"
    layout["showlegend"] = True
    layout["legend"] = dict(
        orientation="h", yanchor="bottom", y=1.02, x=0,
        font=dict(color=THEME["text"]),
    )
    fig.update_layout(**layout)
    return _fig_to_json(fig)


# ─── Context builders ───────────────────────────────────────────────────


def _top_bottom_trades(trades_df: pd.DataFrame, k: int = 5) -> Dict[str, List[Dict[str, Any]]]:
    if trades_df is None or trades_df.empty:
        return {"winners": [], "losers": []}
    ret_col = None
    for c in ("Return", "return"):
        if c in trades_df.columns:
            ret_col = c
            break
    if ret_col is None:
        return {"winners": [], "losers": []}

    df = trades_df.copy()
    df[ret_col] = pd.to_numeric(df[ret_col], errors="coerce")
    df = df.dropna(subset=[ret_col])

    def _row(r: pd.Series) -> Dict[str, Any]:
        return {
            "entry_time": _fmt_date(r.get("Entry Timestamp") or r.get("entry_time")),
            "exit_time": _fmt_date(r.get("Exit Timestamp") or r.get("exit_time")),
            "return_pct": float(r[ret_col]) * 100.0,
            "pnl": float(r.get("PnL") or r.get("pnl") or 0.0),
            "direction": str(r.get("Direction") or r.get("direction") or "Long"),
        }

    winners = [_row(r) for _, r in df.nlargest(k, ret_col).iterrows()]
    losers = [_row(r) for _, r in df.nsmallest(k, ret_col).iterrows()]
    return {"winners": winners, "losers": losers}


def _normalise_spec_for_display(spec: Dict[str, Any]) -> str:
    """Pretty-print the strategy spec dict as indented JSON for the template."""
    return json.dumps(spec, indent=2, default=str)


def _build_context(
    project_name: str,
    bt: Dict[str, Any],
    mc: Optional[Dict[str, Any]],
    wf: Optional[Dict[str, Any]],
    opt: Optional[Dict[str, Any]],
    eq_df: Optional[pd.DataFrame],
    trades_df: Optional[pd.DataFrame],
    report_id: str,
) -> Dict[str, Any]:
    """Assemble the full Jinja context."""
    metrics = bt.get("metrics") or {}
    significance = bt.get("significance") or {}
    params = bt.get("params_used") or {}
    init_cash = float(params.get("init_cash") or 10_000.0)

    scoring = score_from_result_dicts(bt, mc=mc, wf=wf)
    sc_dict = scoring.to_dict()

    eq_fig = _equity_figure(eq_df, init_cash) if eq_df is not None else None
    dd_fig = _drawdown_figure(eq_df) if eq_df is not None else None
    tr_fig = _trades_histogram(trades_df) if trades_df is not None else None
    mc_fig = _mc_percentile_figure(mc) if mc else None
    wf_fig = _wf_folds_figure(wf) if wf else None

    trades_summary = _top_bottom_trades(trades_df) if trades_df is not None else {"winners": [], "losers": []}

    # Metrics table — ordered for the eye
    metric_rows = [
        ("Total return",         _fmt_pct(metrics.get("total_return"))),
        ("CAGR",                 _fmt_pct(metrics.get("cagr"))),
        ("Sharpe",               _fmt_num(metrics.get("sharpe"))),
        ("Sortino",              _fmt_num(metrics.get("sortino"))),
        ("Calmar",               _fmt_num(metrics.get("calmar"))),
        ("Max drawdown",         _fmt_pct(metrics.get("max_drawdown"))),
        ("Profit factor",        _fmt_num(metrics.get("profit_factor"))),
        ("Win rate",             _fmt_pct(metrics.get("win_rate"))),
        ("Avg trade return",     _fmt_pct(metrics.get("avg_trade"))),
        ("Num trades",           _fmt_int(metrics.get("num_trades"))),
        ("Best trade",           _fmt_pct(metrics.get("best_trade"))),
        ("Worst trade",          _fmt_pct(metrics.get("worst_trade"))),
        ("Duration (years)",     _fmt_num(metrics.get("duration_years"), 2)),
    ]

    sig_rows = [
        ("Trades analysed",   _fmt_int(significance.get("n_trades"))),
        ("Mean trade return", _fmt_pct(significance.get("mean_return"))),
        ("Std trade return",  _fmt_pct(significance.get("std_return"))),
        ("t-statistic",       _fmt_num(significance.get("t_stat"))),
        ("p-value (one-sided)", _fmt_num(significance.get("p_value"))),
        ("Significant @ 90%", "Yes" if significance.get("is_significant_90") else "No"),
        ("Significant @ 95%", "Yes" if significance.get("is_significant_95") else "No"),
    ]

    # Fold table for WF section
    fold_rows: List[Dict[str, Any]] = []
    if wf:
        for f in (wf.get("folds") or []):
            is_m = f.get("in_sample_metrics") or {}
            oo_m = f.get("out_sample_metrics") or {}
            fold_rows.append({
                "fold_id": f.get("fold_id"),
                "is_range": f"{_fmt_date(f.get('in_sample_start'))} → {_fmt_date(f.get('in_sample_end'))}",
                "oos_range": f"{_fmt_date(f.get('out_sample_start'))} → {_fmt_date(f.get('out_sample_end'))}",
                "chosen_point": f.get("chosen_point") or {},
                "is_sharpe": _fmt_num(is_m.get("sharpe")),
                "oos_sharpe": _fmt_num(oo_m.get("sharpe")),
                "is_return": _fmt_pct(is_m.get("total_return")),
                "oos_return": _fmt_pct(oo_m.get("total_return")),
                "oos_dd": _fmt_pct(oo_m.get("max_drawdown")),
            })

    # MC percentile rows
    mc_rows: List[Dict[str, Any]] = []
    if mc:
        pct = mc.get("percentiles") or {}
        for key in ("total_return", "max_drawdown", "sharpe_like", "mean_trade_return"):
            p = pct.get(key) or {}
            if not p:
                continue
            fmt = _fmt_pct if key != "sharpe_like" else _fmt_num
            mc_rows.append({
                "metric": key.replace("_", " ").title(),
                "p5": fmt(p.get("p5")),
                "p25": fmt(p.get("p25")),
                "p50": fmt(p.get("p50")),
                "p75": fmt(p.get("p75")),
                "p95": fmt(p.get("p95")),
                "mean": fmt(p.get("mean")),
                "std": fmt(p.get("std")) if key != "sharpe_like" else _fmt_num(p.get("std")),
            })

    # Optional optimize summary.
    opt_rows: List[Dict[str, Any]] = []
    best_in_robust: Optional[Dict[str, Any]] = None
    if opt:
        for r in (opt.get("top_n") or [])[:10]:
            m = r.get("metrics") or {}
            opt_rows.append({
                "point": r.get("point") or {},
                "sharpe": _fmt_num(m.get("sharpe")),
                "total_return": _fmt_pct(m.get("total_return")),
                "max_dd": _fmt_pct(m.get("max_drawdown")),
                "num_trades": _fmt_int(m.get("num_trades")),
                "score": _fmt_num(r.get("score"), 2),
            })
        best_in_robust = opt.get("best_in_robust")

    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    return {
        "report_id": report_id,
        "project_name": project_name,
        "generated_at": now_iso,
        "plotly_cdn": PLOTLY_CDN,
        "theme": THEME,
        "grade_color": GRADE_COLORS.get(scoring.grade, THEME["muted"]),

        # Cover
        "spec_name": (bt.get("spec_used") or {}).get("name") or "Strategy",
        "dataset_id": bt.get("dataset_id"),
        "backtest_id": bt.get("bt_id"),
        "n_bars": bt.get("n_bars"),
        "start_time": _fmt_date(bt.get("start_time")),
        "end_time": _fmt_date(bt.get("end_time")),
        "init_cash": init_cash,
        "bt_created_at": _fmt_date(bt.get("created_at")),
        "spec_json": _normalise_spec_for_display(bt.get("spec_used") or {}),

        # Sections
        "metric_rows": metric_rows,
        "sig_rows": sig_rows,
        "trades_winners": trades_summary["winners"],
        "trades_losers": trades_summary["losers"],
        "fold_rows": fold_rows,
        "mc_rows": mc_rows,
        "opt_rows": opt_rows,
        "best_in_robust": best_in_robust,

        # Raw artifacts for verdict
        "mc": mc,
        "wf": wf,
        "opt": opt,
        "scoring": sc_dict,
        "has_mc": mc is not None,
        "has_wf": wf is not None,
        "has_opt": opt is not None,
        "has_equity": eq_fig is not None,
        "has_drawdown": dd_fig is not None,
        "has_trade_hist": tr_fig is not None,

        # Figure JSON blobs (embedded verbatim)
        "equity_fig_json": eq_fig,
        "drawdown_fig_json": dd_fig,
        "trades_fig_json": tr_fig,
        "mc_fig_json": mc_fig,
        "wf_fig_json": wf_fig,
    }


# ─── Jinja environment ──────────────────────────────────────────────────


def _jinja_env() -> Environment:
    tpl_dir = Path(__file__).parent / "templates"
    env = Environment(
        loader=FileSystemLoader(str(tpl_dir)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    # Custom filters
    env.filters["fmt_pct"] = _fmt_pct
    env.filters["fmt_num"] = _fmt_num
    env.filters["fmt_int"] = _fmt_int
    return env


# ─── Main entry ─────────────────────────────────────────────────────────


@dataclass
class ReportMetadata:
    report_id: str
    project_id: str
    project_name: str
    backtest_id: str
    monte_carlo_id: Optional[str]
    walk_forward_id: Optional[str]
    optimization_id: Optional[str]
    title: str
    grade: str
    verdict: str
    score: float
    created_at: str
    sections: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "project_id": self.project_id,
            "project_name": self.project_name,
            "backtest_id": self.backtest_id,
            "monte_carlo_id": self.monte_carlo_id,
            "walk_forward_id": self.walk_forward_id,
            "optimization_id": self.optimization_id,
            "title": self.title,
            "grade": self.grade,
            "verdict": self.verdict,
            "score": self.score,
            "created_at": self.created_at,
            "sections": self.sections,
        }


def _cleanup_old_reports(project_id: str, cap: int = REPORT_CACHE_CAP) -> None:
    """Delete all but the newest `cap` reports (json+html+pdf triples)."""
    d = _reports_dir(project_id)
    metas = sorted(d.glob("rp_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in metas[cap:]:
        rid = stale.stem
        for suffix in (".json", ".html", ".pdf"):
            fp = d / f"{rid}{suffix}"
            try:
                if fp.exists():
                    fp.unlink()
            except OSError:
                pass


def render_report(
    *,
    backtest_id: str,
    monte_carlo_id: Optional[str] = None,
    walk_forward_id: Optional[str] = None,
    optimization_id: Optional[str] = None,
) -> ReportMetadata:
    """Build + persist a report for the given artifacts. Returns metadata."""
    from .. import storage  # local to avoid import cycle at module load

    project_id, bt = _load_backtest(backtest_id)
    project = storage.get_project(project_id)
    project_name = project.name if project else project_id

    mc = _load_validation(project_id, monte_carlo_id) if monte_carlo_id else None
    if monte_carlo_id and mc is None:
        raise ValueError(f"Monte Carlo artifact {monte_carlo_id!r} not found under project {project_id}")

    wf = _load_validation(project_id, walk_forward_id) if walk_forward_id else None
    if walk_forward_id and wf is None:
        raise ValueError(f"Walk-forward artifact {walk_forward_id!r} not found under project {project_id}")

    opt = _load_optimization(project_id, optimization_id) if optimization_id else None
    if optimization_id and opt is None:
        raise ValueError(f"Optimization artifact {optimization_id!r} not found under project {project_id}")

    eq_df = _load_equity(project_id, backtest_id)
    trades_df = _load_trades(project_id, backtest_id)

    report_id = _report_id()
    context = _build_context(
        project_name=project_name,
        bt=bt, mc=mc, wf=wf, opt=opt,
        eq_df=eq_df, trades_df=trades_df,
        report_id=report_id,
    )

    env = _jinja_env()
    template = env.get_template("report.html")
    html = template.render(**context)

    paths = report_paths(project_id, report_id)
    paths["html"].write_text(html, encoding="utf-8")

    sections = ["cover", "metrics", "significance"]
    if context["has_equity"]:
        sections.append("equity")
    if context["has_drawdown"]:
        sections.append("drawdown")
    if context["has_trade_hist"] or trades_df is not None:
        sections.append("trades")
    if wf:
        sections.append("walkforward")
    if mc:
        sections.append("montecarlo")
    if opt:
        sections.append("optimization")
    sections.append("verdict")

    sc = context["scoring"]
    meta = ReportMetadata(
        report_id=report_id,
        project_id=project_id,
        project_name=project_name,
        backtest_id=backtest_id,
        monte_carlo_id=monte_carlo_id,
        walk_forward_id=walk_forward_id,
        optimization_id=optimization_id,
        title=f"{context['spec_name']} — Grade {sc['grade']}",
        grade=sc["grade"],
        verdict=sc["verdict"],
        score=float(sc["score"]),
        created_at=context["generated_at"],
        sections=sections,
    )
    paths["json"].write_text(
        json.dumps(meta.to_dict(), indent=2), encoding="utf-8"
    )

    # Soft cap — never fail the render if cleanup has trouble.
    try:
        _cleanup_old_reports(project_id)
    except Exception:
        pass

    return meta


def load_report_metadata(project_id: str, report_id: str) -> Optional[Dict[str, Any]]:
    p = _reports_dir(project_id) / f"{report_id}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def find_report(report_id: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Scan all workspaces for the report id — returns (project_id, metadata)."""
    from .. import paths as _paths

    for ws in _paths.WORKSPACES_DIR.iterdir():
        if not ws.is_dir():
            continue
        cand = ws / "reports" / f"{report_id}.json"
        if cand.exists():
            return ws.name, json.loads(cand.read_text(encoding="utf-8"))
    return None

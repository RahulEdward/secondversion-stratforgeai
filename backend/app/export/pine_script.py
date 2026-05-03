"""Convert a StrategySpec to TradingView Pine Script v5.

Handles: indicators → ta.* calls, conditions → boolean expressions,
stops → strategy.exit(), sizing → strategy.entry() qty.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional


# Indicator → Pine Script function mapping
_PINE_INDICATORS = {
    "rsi": lambda p: f"ta.rsi(close, {p.get('period', 14)})",
    "ema": lambda p: f"ta.ema(close, {p.get('period', 20)})",
    "sma": lambda p: f"ta.sma(close, {p.get('period', 20)})",
    "atr": lambda p: f"ta.atr({p.get('period', 14)})",
    "adx": lambda p: f"ta.adx({p.get('period', 14)}, {p.get('period', 14)})",
    "supertrend": lambda p: f"ta.supertrend({p.get('multiplier', 3.0)}, {p.get('period', 10)})",
    "macd": lambda p: f"ta.macd(close, {p.get('fast', 12)}, {p.get('slow', 26)}, {p.get('signal', 9)})",
    "stochastic": lambda p: f"ta.stoch(high, low, close, {p.get('k_period', 14)})",
    "bollinger_bands": lambda p: f"ta.bb(close, {p.get('period', 20)}, {p.get('std_dev', 2.0)})",
    "vwap": lambda _: "ta.vwap(hlc3)",
    "cci": lambda p: f"ta.cci(close, {p.get('period', 20)})",
    "williams_r": lambda p: f"ta.wpr({p.get('period', 14)})",
    "roc": lambda p: f"ta.roc(close, {p.get('period', 12)})",
    "obv": lambda _: "ta.obv",
}

_OP_MAP = {
    "<": "<", ">": ">", "<=": "<=", ">=": ">=", "==": "==",
    "crosses_above": "ta.crossover",
    "crosses_below": "ta.crossunder",
}


def _pine_var_name(indicator: str, params: Dict, field: Optional[str] = None) -> str:
    period = params.get("period", "")
    suffix = f"_{field}" if field else ""
    return f"{indicator}{period}{suffix}".replace(".", "_")


def _pine_indicator_decl(indicator: str, params: Dict, field: Optional[str] = None) -> str:
    if indicator == "price":
        return ""
    var = _pine_var_name(indicator, params, field)
    fn = _PINE_INDICATORS.get(indicator)
    if not fn:
        return f"// WARNING: unsupported indicator '{indicator}'\nfloat {var} = na"
    call = fn(params)

    if indicator == "macd":
        base = _pine_var_name("macd", params)
        return (
            f"[{base}_line, {base}_signal, {base}_hist] = {call}"
        )
    if indicator == "bollinger_bands":
        base = _pine_var_name("bb", params)
        return (
            f"[{base}_middle, {base}_upper, {base}_lower] = {call}"
        )
    if indicator == "supertrend":
        base = _pine_var_name("st", params)
        return f"[{base}_line, {base}_dir] = {call}"

    return f"float {var} = {call}"


def _pine_value_ref(indicator: str, params: Dict, field: Optional[str], ref: Optional[str]) -> str:
    if indicator == "price":
        return field or "close"
    if indicator == "macd" and field:
        base = _pine_var_name("macd", params)
        return f"{base}_{field}"
    if indicator == "bollinger_bands" and field:
        base = _pine_var_name("bb", params)
        return f"{base}_{field}"
    if indicator == "supertrend" and field:
        base = _pine_var_name("st", params)
        if field == "direction":
            return f"{base}_dir"
        return f"{base}_line"
    return _pine_var_name(indicator, params, field)


def _pine_condition(cond: Dict) -> str:
    ind = cond.get("indicator", "price")
    params = cond.get("params", {})
    field = cond.get("field")
    op = cond.get("op", ">")
    value = cond.get("value")
    ref = cond.get("ref")

    lhs = _pine_value_ref(ind, params, field, None)

    if ref:
        rhs = ref if ref in ("open", "high", "low", "close", "volume") else ref
    elif value is not None:
        rhs = str(value)
    else:
        rhs = "0"

    if op in ("crosses_above", "crosses_below"):
        fn = _OP_MAP[op]
        return f"{fn}({lhs}, {rhs})"
    pine_op = _OP_MAP.get(op, op)
    return f"{lhs} {pine_op} {rhs}"


def _pine_group(group: Dict, joiner: str = "and") -> str:
    parts = []
    for cond in group.get("all_of", []):
        if "indicator" in cond:
            parts.append(_pine_condition(cond))
        else:
            parts.append(f"({_pine_group(cond)})")
    for cond in group.get("any_of", []):
        if "indicator" in cond:
            parts.append(_pine_condition(cond))
        else:
            parts.append(f"({_pine_group(cond, 'or')})")

    if group.get("all_of"):
        joiner = " and "
    elif group.get("any_of"):
        joiner = " or "
    else:
        joiner = " and "

    return joiner.join(parts) if parts else "true"


def _collect_indicators(spec: Dict) -> List[str]:
    """Collect all unique indicator declarations needed."""
    seen = set()
    decls = []
    for group_key in ("entries", "exits"):
        group = spec.get(group_key, {})
        for cond_key in ("all_of", "any_of"):
            for cond in group.get(cond_key, []):
                if "indicator" not in cond or cond["indicator"] == "price":
                    continue
                key = (cond["indicator"], str(cond.get("params", {})), cond.get("field"))
                if key not in seen:
                    seen.add(key)
                    d = _pine_indicator_decl(cond["indicator"], cond.get("params", {}), cond.get("field"))
                    if d:
                        decls.append(d)
    rf = spec.get("regime_filter")
    if rf and rf.get("indicator") and rf["indicator"] != "price":
        key = (rf["indicator"], str(rf.get("params", {})), rf.get("field"))
        if key not in seen:
            d = _pine_indicator_decl(rf["indicator"], rf.get("params", {}), rf.get("field"))
            if d:
                decls.append(d)
    return decls


def to_pine_script(spec: Dict[str, Any]) -> str:
    """Convert a StrategySpec dict to TradingView Pine Script v5."""
    name = spec.get("name", "StratForge Strategy")
    lines = [
        f'//@version=5',
        f'strategy("{name}", overlay=true, default_qty_type=strategy.percent_of_equity, '
        f'default_qty_value={int((spec.get("sizing", {}).get("value", 1.0)) * 100)})',
        '',
        '// ── Indicators ──',
    ]

    for decl in _collect_indicators(spec):
        lines.append(decl)
    lines.append('')

    # Entry conditions
    entry_expr = _pine_group(spec.get("entries", {}))
    lines.append(f'// ── Entry Logic ──')
    lines.append(f'longCondition = {entry_expr}')

    # Regime filter
    rf = spec.get("regime_filter")
    if rf:
        rf_expr = _pine_condition(rf)
        lines.append(f'regimeOk = {rf_expr}')
        lines.append(f'longCondition := longCondition and regimeOk')

    lines.append('')

    # Exit conditions
    exit_expr = _pine_group(spec.get("exits", {}))
    lines.append(f'// ── Exit Logic ──')
    lines.append(f'exitCondition = {exit_expr}')
    lines.append('')

    # Strategy calls
    lines.append('// ── Execution ──')
    lines.append('if longCondition')
    lines.append('    strategy.entry("Long", strategy.long)')
    lines.append('if exitCondition')
    lines.append('    strategy.close("Long")')

    # Stops
    stops = spec.get("stops", {})
    sl = stops.get("stop_loss", {})
    tp = stops.get("take_profit", {})

    if sl or tp:
        lines.append('')
        lines.append('// ── Risk Management ──')
        if sl.get("type") == "fixed_pct":
            lines.append(f'strategy.exit("SL/TP", "Long", '
                         f'stop=strategy.position_avg_price * (1 - {sl.get("value", 0.02)}), '
                         f'limit={f"strategy.position_avg_price * (1 + {tp.get("value", 0.04)})" if tp.get("type") == "fixed_pct" else "na"})')
        elif sl.get("type") == "atr":
            mult = sl.get("multiplier", 2.0)
            period = sl.get("period", 14)
            lines.append(f'atrStop = ta.atr({period}) * {mult}')
            lines.append(f'strategy.exit("SL/TP", "Long", '
                         f'stop=strategy.position_avg_price - atrStop, '
                         f'limit={f"strategy.position_avg_price + atrStop * {tp.get("value", 2.0)}" if tp else "na"})')

    trail = stops.get("trailing", {})
    if trail.get("type") == "trailing_pct":
        lines.append(f'strategy.exit("Trail", "Long", trail_points=close * {trail.get("value", 0.02)} / syminfo.mintick)')

    lines.append('')
    lines.append(f'// Generated by StratForge AI')
    return '\n'.join(lines)

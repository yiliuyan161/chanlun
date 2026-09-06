"""chanlun — A股缠论中枢可视化 web 服务.

aiohttp server that reads daily bars from fintech's DuckDB (v_daily_qfq),
computes Chanlun structure with czsc (Rust core), and serves:
  GET /                index.html (search + nav)
  GET /api/search?q=   symbol/name search → [{thscode, name, exchange}]
  GET /api/kline/{thscode}?limit=N   kline + bi + zs(中枢) as JSON
  GET /stock/{thscode}  single-stock viewer page

Run:
  python server.py [--port 8000] [--db /path/to/market.duckdb]
"""

from __future__ import annotations

import argparse
import os

import duckdb
import pandas as pd
from aiohttp import web
from czsc import CZSC, Freq, RawBar

DB = os.environ.get("CHANLUN_DB", "data/market.duckdb")
DEFAULT_LIMIT = 2000


def connect() -> duckdb.DuckDBPyConnection:
    """Read-only connection; DuckDB is single-writer so always open fresh.
    DB path resolves at call time from the env so --db / CHANLUN_DB works."""
    return duckdb.connect(os.environ.get("CHANLUN_DB", DB), read_only=True)


def search_symbols(con, q: str, limit: int = 20) -> list[dict]:
    """Search dim_symbol by code (thscode/ticker) or name (LIKE)."""
    q = q.strip()
    if not q:
        return []
    like = f"%{q}%"
    rows = con.execute(
        """SELECT thscode, name, exchange FROM dim_symbol
           WHERE thscode LIKE ? OR ticker LIKE ? OR name LIKE ?
           ORDER BY thscode LIMIT ?""",
        [q, q, like, limit],
    ).fetchall()
    return [{"thscode": r[0], "name": r[1], "exchange": r[2]} for r in rows]


def load_bars(con, thscode: str, limit: int = DEFAULT_LIMIT) -> list[RawBar]:
    df = con.execute(
        "SELECT date, open, high, low, close, volume, turnover "
        f"FROM v_daily_qfq WHERE thscode='{thscode}' ORDER BY date"
    ).df()
    if df.empty:
        return []
    if len(df) > limit:
        df = df.tail(limit)
    return [
        RawBar(
            symbol=thscode,
            dt=pd.Timestamp(r["date"]).to_pydatetime(),
            freq=Freq.D,
            open=float(r["open"]), high=float(r["high"]),
            low=float(r["low"]), close=float(r["close"]),
            vol=float(r["volume"]), amount=float(r["turnover"]),
        )
        for _, r in df.iterrows()
    ]


def chanlun_json(c: CZSC) -> dict:
    """Serialize CZSC structure to JSON for the frontend to draw."""
    klines = [
        {
            "time": pd.Timestamp(k.dt).strftime("%Y-%m-%d"),
            "open": k.open, "high": k.high, "low": k.low, "close": k.close,
            "vol": getattr(k, "vol", 0),
        }
        for k in c.bars_raw
    ]
    bis = [
        {
            "sdt": pd.Timestamp(b.sdt).strftime("%Y-%m-%d"),
            "edt": pd.Timestamp(b.edt).strftime("%Y-%m-%d"),
            "high": b.high, "low": b.low, "direction": str(b.direction),
        }
        for b in c.bi_list
    ]
    zs = [
        {
            "sdt": pd.Timestamp(z.sdt).strftime("%Y-%m-%d"),
            "edt": pd.Timestamp(z.edt).strftime("%Y-%m-%d"),
            "zd": z.zd, "zg": z.zg, "gg": z.gg, "dd": z.dd,
        }
        for z in c.zs_list
    ]
    # ── 买卖点启发式 (基于笔 + 中枢) ──────────────────────────────
    # 三买: 向上离开中枢后回抽低点 > 中枢ZG (笔在 zs.edt 后)
    # 三卖: 向下离开中枢后回抽高点 < 中枢ZD
    # 一买/一卖: 背驰简化 = 走势末端反向一笔创新低/新高 (最朴素)
    # 二买/二卖: 一买/一卖 后第一个反向不创新低/新高的笔
    pts = []
    zs_map = {}  # sdt -> zs
    for z in zs:
        zs_map.setdefault(z["sdt"], []).append(z)

    for i, b in enumerate(bis):
        is_up = "向上" in str(b["direction"])
        # 三买/三卖: 该笔属于"离开后回抽" — 检查前一笔是否离开某中枢
        if i >= 1:
            prev = bis[i - 1]
            prev_up = "向上" in str(prev["direction"])
            # 找一个在 prev 结束后还活着的中枢
            t = b["sdt"]
            cur_zs = next((z for z in zs if z["sdt"] <= t <= z["edt"]), None)
            if cur_zs is None:
                # prev 笔之后新开始的第一个中枢
                future = [z for z in zs if z["sdt"] >= prev["edt"]]
                cur_zs = future[0] if future else None
            if cur_zs:
                if prev_up and b["low"] > cur_zs["zg"]:
                    pts.append({"time": b["sdt"], "type": "buy3", "price": b["low"],
                                "label": "三买", "desc": f"回抽低点 {b['low']:.2f} > ZG {cur_zs['zg']:.2f}"})
                if (not prev_up) and b["high"] < cur_zs["zd"]:
                    pts.append({"time": b["sdt"], "type": "sell3", "price": b["high"],
                                "label": "三卖", "desc": f"回抽高点 {b['high']:.2f} < ZD {cur_zs['zd']:.2f}"})

    # 一买/一卖 (末端创新低/新高的反向笔) + 二买/二卖
    down_bis = [b for b in bis if "向下" in str(b["direction"])]
    up_bis = [b for b in bis if "向上" in str(b["direction"])]
    if down_bis:
        last_down = down_bis[-1]
        # 一买 = 最后一个向下笔的低点(若其后有向上笔开始)
        pts.append({"time": last_down["edt"], "type": "buy1", "price": last_down["low"],
                    "label": "一买", "desc": "最后下跌笔低点(简化背驰)"})
        # 二买: 一买后第一个向上笔回调低点不破
        after = [b for b in down_bis[-2:] if b["sdt"] > last_down["sdt"]]
    if up_bis:
        last_up = up_bis[-1]
        pts.append({"time": last_up["edt"], "type": "sell1", "price": last_up["high"],
                    "label": "一卖", "desc": "最后上涨笔高点(简化背驰)"})

    return {"klines": klines, "bis": bis, "zs": zs, "points": pts}


async def handle_index(request: web.Request) -> web.FileResponse:
    resp = web.FileResponse(os.path.join(os.path.dirname(__file__), "ui", "index.html"))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


async def handle_stock(request: web.Request) -> web.FileResponse:
    resp = web.FileResponse(os.path.join(os.path.dirname(__file__), "ui", "stock.html"))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


async def handle_primitive_js(request: web.Request) -> web.FileResponse:
    return web.FileResponse(os.path.join(os.path.dirname(__file__), "ui", "chan-primitives.js"))


async def handle_test_primitive(request: web.Request) -> web.FileResponse:
    return web.FileResponse(os.path.join(os.path.dirname(__file__), "ui", "test-primitive.html"))


async def handle_search(request: web.Request) -> web.Response:
    q = request.query.get("q", "").strip()
    if not q:
        return web.json_response([])
    con = connect()
    try:
        results = search_symbols(con, q)
    finally:
        con.close()
    return web.json_response(results)


async def handle_symbols(request: web.Request) -> web.Response:
    """Full symbol list for the frontend nav (thscode/ticker/name/exchange)."""
    con = connect()
    try:
        rows = con.execute(
            "SELECT thscode, ticker, name, exchange FROM dim_symbol "
            "WHERE asset_type IN ('a-share','a-share-st') OR asset_type IS NULL "
            "ORDER BY thscode"
        ).fetchall()
    finally:
        con.close()
    return web.json_response(
        [{"thscode": r[0], "ticker": r[1], "name": r[2], "exchange": r[3]} for r in rows]
    )


async def handle_kline(request: web.Request) -> web.Response:
    thscode = request.match_info["thscode"]
    limit = int(request.query.get("limit", DEFAULT_LIMIT))
    con = connect()
    try:
        bars = load_bars(con, thscode, limit)
        if not bars:
            return web.json_response({"error": "symbol not found"}, status=404)
        c = CZSC(bars)
        payload = chanlun_json(c)
        payload["symbol"] = thscode
    except Exception as e:
        return web.json_response({"error": f"{type(e).__name__}: {e}"}, status=500)
    finally:
        con.close()
    return web.json_response(payload)


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/stock/{thscode}", handle_stock)
    app.router.add_get("/api/search", handle_search)
    app.router.add_get("/api/symbols", handle_symbols)
    app.router.add_get("/api/kline/{thscode}", handle_kline)
    app.router.add_get("/chan-primitives.js", handle_primitive_js)
    app.router.add_get("/test-primitive", handle_test_primitive)
    return app


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--db", default=os.environ.get("CHANLUN_DB", "data/market.duckdb"))
    args = ap.parse_args()
    # DB lives at module level; connect() reads it. Rebind via env for the run.
    os.environ["CHANLUN_DB"] = args.db
    web.run_app(build_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
# chanlun — A股缠论中枢可视化

基于 [czsc](https://github.com/waditu/czsc)(Rust 缠论核心) + [lightweight-charts](https://github.com/tradingview/lightweight-charts) 的 A 股缠论可视化网站。

按需计算(不预生成):aiohttp 服务实时从本地 DuckDB(fintech 项目)读取前复权日K,czsc 计算笔/中枢,前端渲染。

## 功能

- 🔍 搜索:支持股票代码(600519 / 000001)与名称(茅台 / 平安)
- 📈 每只股票:日K + 缠论笔(BI)+ 中枢(ZS,上下沿 ZG/ZD 虚线)
- 🧭 全部 5881 只 A 股导航
- 🚀 通过 Cloudflare Tunnel 部署到公网域名

## 本地启动

```bash
pip install aiohttp czsc duckdb pandas

# 数据库来自 fintech 项目 (data/market.duckdb),可用软链或环境变量指定
export CHANLUN_DB=/path/to/fintech/data/market.duckdb
python server.py --port 8000
# 打开 http://127.0.0.1:8000
```

## API

| 端点 | 说明 |
|---|---|
| `GET /` | 首页(搜索 + 导航) |
| `GET /stock/{thscode}` | 个股缠论图 |
| `GET /api/symbols` | 全部标的名录(代码/名称) |
| `GET /api/search?q=` | 代码/名称搜索 |
| `GET /api/kline/{thscode}?limit=1500` | K线 + 笔 + 中枢 JSON |

## Cloudflare Tunnel 部署

```bash
cloudflared tunnel login          # 浏览器授权(选 icopy.site 域)
cloudflared tunnel create chanlun
cloudflared tunnel route dns chanlun chanview.icopy.site
cloudflared tunnel run chanlun     # 前台运行;生产建议注册为 Windows 服务
```

宿主服务需常驻:服务器本机运行 `python server.py`,Tunnel 转发 `chanview.icopy.site → http://127.0.0.1:8000`。

## 数据来源

- 日K:同花顺 fuyao dump(10年)+ Tushare 回补(1990-2016),存于 fintech 项目的 DuckDB(`v_daily_qfq` 前复权视图)
# TradingView MCP Bridge

Control TradingView Desktop from Claude Code via Chrome DevTools Protocol. 55 tools across 12 categories — chart control, Pine Script editing, data extraction, drawing, alerts, replay trading, and more.

## What It Does

Claude Code connects to your running TradingView Desktop app and can:

- **Read and write Pine Script** — inject code, compile, read errors, manage saved scripts
- **Control the chart** — change symbol, timeframe, zoom to dates, add/remove indicators
- **Extract data** — OHLCV bars, strategy results, equity curves, real-time quotes
- **Draw on charts** — trend lines, horizontal lines, rectangles, text annotations
- **Manage alerts** — create, list, and delete price alerts
- **Replay trading** — start replay, step through bars, execute trades, track P&L
- **Automate UI** — click buttons, toggle panels, switch layouts, manage watchlists
- **Take screenshots** — full page, chart region, or strategy tester

## Quick Start

### 1. Install

```bash
git clone https://github.com/the-daily-profiler/tradingview-mcp.git
cd tradingview-mcp
npm install
```

### 2. Launch TradingView with CDP

TradingView Desktop must be running with Chrome DevTools Protocol enabled on port 9222.

**Windows** — use the included launch script:
```bash
scripts\launch_tv_debug.bat
```

Or launch manually:
```bash
"C:\Program Files\TradingView\TradingView.exe" --remote-debugging-port=9222
```

**Mac/Linux** — find your TradingView binary and add the flag:
```bash
/path/to/TradingView --remote-debugging-port=9222
```

### 3. Add to Claude Code

Add to your Claude Code MCP config (`~/.claude/claude_desktop_config.json` or project `.mcp.json`):

```json
{
  "mcpServers": {
    "tradingview": {
      "command": "node",
      "args": ["C:/Users/YOU/tradingview-mcp/src/server.js"]
    }
  }
}
```

Replace `C:/Users/YOU/tradingview-mcp` with your actual path.

### 4. Verify

Ask Claude: *"Use tv_health_check to verify TradingView is connected"*

## Tool Reference (55 tools)

### Health & Discovery (3)
| Tool | What it does |
|------|-------------|
| `tv_health_check` | Verify CDP connection, get current symbol/timeframe |
| `tv_discover` | Report available API paths and their methods |
| `tv_ui_state` | Get current UI state — open panels, visible buttons |

### Chart Control (10)
| Tool | What it does |
|------|-------------|
| `chart_get_state` | Get symbol, timeframe, chart type, all studies with IDs |
| `chart_set_symbol` | Change symbol (BTCUSD, AAPL, ES1!, NYMEX:CL1!) |
| `chart_set_timeframe` | Change timeframe (1, 5, 15, 60, D, W, M) |
| `chart_set_type` | Change chart type (Candles, Line, Area, HeikinAshi, etc.) |
| `chart_manage_indicator` | Add or remove indicators by name or entity ID |
| `chart_get_visible_range` | Get visible date range as unix timestamps |
| `chart_set_visible_range` | Zoom to a specific date range |
| `chart_scroll_to_date` | Jump chart to center on a date |
| `symbol_info` | Get symbol metadata — exchange, type, description |
| `symbol_search` | Search for symbols via TradingView's search dialog |

### Pine Script (10)
| Tool | What it does |
|------|-------------|
| `pine_get_source` | Read current script from the editor |
| `pine_set_source` | Inject Pine Script into the editor |
| `pine_compile` | Compile / add script to chart |
| `pine_get_errors` | Get compilation errors from Monaco markers |
| `pine_save` | Save the current script (Ctrl+S) |
| `pine_get_console` | Read console output — compile messages, log.info() |
| `pine_smart_compile` | Auto-detect button, compile, check errors, report changes |
| `pine_new` | Create new blank script (indicator/strategy/library) |
| `pine_open` | Open a saved script by name |
| `pine_list_scripts` | List saved scripts from the editor dropdown |

### Data Extraction (7)
| Tool | What it does |
|------|-------------|
| `data_get_ohlcv` | Get OHLCV bar data (max 500 bars) |
| `data_get_indicator` | Get indicator info and input values |
| `data_get_strategy_results` | Get strategy performance metrics |
| `data_get_trades` | Get trade list from Strategy Tester |
| `data_get_equity` | Get equity curve data |
| `quote_get` | Get real-time quote — last, OHLC, volume |
| `depth_get` | Get order book / DOM data |

### Indicators (2)
| Tool | What it does |
|------|-------------|
| `indicator_set_inputs` | Change indicator settings (length, source, etc.) |
| `indicator_toggle_visibility` | Show or hide an indicator |

### Drawing (5)
| Tool | What it does |
|------|-------------|
| `draw_shape` | Draw shapes — horizontal_line, trend_line, rectangle, text |
| `draw_list` | List all drawings with IDs |
| `draw_clear` | Remove all drawings |
| `draw_remove_one` | Remove a specific drawing by ID |
| `draw_get_properties` | Get drawing properties and points |

### Alerts (3)
| Tool | What it does |
|------|-------------|
| `alert_create` | Create a price alert |
| `alert_list` | List active alerts |
| `alert_delete` | Delete alerts |

### Screenshots (1)
| Tool | What it does |
|------|-------------|
| `capture_screenshot` | Take a screenshot (full, chart, or strategy tester region) |

### Batch Operations (1)
| Tool | What it does |
|------|-------------|
| `batch_run` | Run actions across multiple symbols and timeframes |

### Replay Trading (6)
| Tool | What it does |
|------|-------------|
| `replay_start` | Start bar replay at a specific date |
| `replay_step` | Advance one bar |
| `replay_autoplay` | Toggle autoplay, set speed |
| `replay_stop` | Stop replay, return to realtime |
| `replay_trade` | Execute buy/sell/close in replay |
| `replay_status` | Get replay state, position, P&L |

### UI Control (5)
| Tool | What it does |
|------|-------------|
| `ui_click` | Click any element by aria-label, data-name, text, or class |
| `ui_open_panel` | Open/close/toggle panels (pine-editor, watchlist, etc.) |
| `ui_fullscreen` | Toggle fullscreen |
| `layout_list` | List saved chart layouts |
| `layout_switch` | Switch to a saved layout |

### Watchlist (2)
| Tool | What it does |
|------|-------------|
| `watchlist_get` | Read watchlist — symbols, prices, changes |
| `watchlist_add` | Add a symbol to the watchlist |

## Example Workflows

### Pine Script Development
```
"Write a Pine Script RSI divergence indicator, put it on the chart, and screenshot the result"
```
Claude will: `pine_set_source` → `pine_smart_compile` → `pine_get_errors` → `capture_screenshot`

### Multi-Symbol Screening
```
"Compare Bollinger Band squeeze across ES, NQ, YM, and RTY on the 15-minute chart"
```
Claude will: `batch_run` across symbols with screenshot + indicator analysis

### Chart Analysis
```
"Switch to AAPL daily, add a 200 EMA, scroll to January 2024, and screenshot"
```
Claude will: `chart_set_symbol` → `chart_set_timeframe` → `chart_manage_indicator` → `chart_scroll_to_date` → `capture_screenshot`

### Replay Practice
```
"Start replay on ES 5-minute from March 1st, step through 20 bars, buy at a support level"
```
Claude will: `replay_start` → `replay_step` (x20) → `replay_trade`

## Architecture

```
Claude Code  ←→  MCP Server (stdio)  ←→  CDP (port 9222)  ←→  TradingView Desktop
```

- **Transport**: MCP over stdio
- **Connection**: Chrome DevTools Protocol on localhost:9222
- **API access**: Direct paths to TradingView internals — no DOM scraping where avoidable
- **Pine Editor**: Monaco accessed via React fiber tree traversal
- **No dependencies** beyond `@modelcontextprotocol/sdk` and `chrome-remote-interface`

## Pine Script Helper Scripts

For efficient Pine Script editing:

```bash
node scripts/pine_pull.js    # Pull from TV editor → scripts/current.pine
# ... edit scripts/current.pine locally ...
node scripts/pine_push.js    # Push to TV editor + compile + report errors
```

## Requirements

- TradingView Desktop (Electron app) with `--remote-debugging-port=9222`
- Node.js 18+
- Claude Code with MCP support

## License

MIT

# TradingView MCP Bridge

Control TradingView Desktop from Claude Code via Chrome DevTools Protocol. **68 tools** across 13 categories — chart control, Pine Script editing, data extraction, Pine graphics extraction (line.new/label.new/box.new/table.new), drawing, alerts, replay trading, and more.

## What It Does

Claude Code connects to your running TradingView Desktop app and can:

- **Read and write Pine Script** — inject code, compile, read errors, manage saved scripts
- **Control the chart** — change symbol, timeframe, zoom to dates, add/remove indicators
- **Extract data** — OHLCV bars, strategy results, equity curves, real-time quotes
- **Extract Pine graphics** — read price levels from `line.new()`, text from `label.new()`, table data from `table.new()`, box boundaries from `box.new()` — even from protected/encrypted indicators
- **Read indicator values** — current RSI, MACD, Bollinger Bands, EMA values from the data window
- **Draw on charts** — trend lines, horizontal lines, rectangles, text annotations
- **Manage alerts** — create, list, and delete price alerts
- **Replay trading** — start replay, step through bars, execute trades, track P&L
- **Automate UI** — click buttons, toggle panels, switch layouts, manage watchlists
- **Take screenshots** — full page, chart region, or strategy tester
- **Launch TradingView** — auto-detect and launch with debug mode from any platform

## Quick Start

### 1. Install

```bash
git clone https://github.com/thedailyprofiler/tradingview-mcp.git
cd tradingview-mcp
npm install
```

### 2. Launch TradingView with CDP

TradingView Desktop must be running with Chrome DevTools Protocol enabled on port 9222.

**Mac:**
```bash
./scripts/launch_tv_debug_mac.sh
```

**Windows:**
```bash
scripts\launch_tv_debug.bat
```

**Linux:**
```bash
./scripts/launch_tv_debug_linux.sh
```

**Or launch manually on any platform:**
```bash
/path/to/TradingView --remote-debugging-port=9222
```

**Or use the MCP tool** (auto-detects your install):
> "Use tv_launch to start TradingView in debug mode"

### 3. Add to Claude Code

Add to your Claude Code MCP config (`~/.claude/.mcp.json` or project `.mcp.json`):

```json
{
  "mcpServers": {
    "tradingview": {
      "command": "node",
      "args": ["/path/to/tradingview-mcp/src/server.js"]
    }
  }
}
```

Replace `/path/to/tradingview-mcp` with your actual path.

### 4. Verify

Ask Claude: *"Use tv_health_check to verify TradingView is connected"*

## Finding TradingView on Your System

The launch scripts and `tv_launch` tool auto-detect TradingView's install location. If auto-detection fails:

| Platform | Common Locations |
|----------|-----------------|
| **Mac** | `/Applications/TradingView.app/Contents/MacOS/TradingView` |
| **Windows** | `%LOCALAPPDATA%\TradingView\TradingView.exe`, `%PROGRAMFILES%\WindowsApps\TradingView*\TradingView.exe` |
| **Linux** | `/opt/TradingView/tradingview`, `~/.local/share/TradingView/TradingView`, `/snap/tradingview/current/tradingview` |

The key flag is `--remote-debugging-port=9222`. This enables Chrome DevTools Protocol which the MCP server connects to.

## Tool Reference (68 tools)

### Health & Launch (4)
| Tool | What it does |
|------|-------------|
| `tv_health_check` | Verify CDP connection, get current symbol/timeframe |
| `tv_discover` | Report available API paths and their methods |
| `tv_ui_state` | Get current UI state — open panels, visible buttons |
| `tv_launch` | Launch TradingView Desktop with CDP enabled (auto-detects install on Mac/Win/Linux) |

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

### Data Extraction (12)
| Tool | What it does |
|------|-------------|
| `data_get_ohlcv` | Get OHLCV bar data (max 500 bars) |
| `data_get_indicator` | Get indicator info and input values |
| `data_get_strategy_results` | Get strategy performance metrics |
| `data_get_trades` | Get trade list from Strategy Tester |
| `data_get_equity` | Get equity curve data |
| `quote_get` | Get real-time quote — last, OHLC, volume |
| `depth_get` | Get order book / DOM data |
| **`data_get_pine_lines`** | **Extract price levels from Pine `line.new()` drawings** |
| **`data_get_pine_labels`** | **Extract text + price from Pine `label.new()` drawings** |
| **`data_get_pine_tables`** | **Extract table cell text from Pine `table.new()` drawings** |
| **`data_get_pine_boxes`** | **Extract price boundaries from Pine `box.new()` drawings** |
| **`data_get_study_values`** | **Get current values from all indicators via data window** |

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

### UI Control (12)
| Tool | What it does |
|------|-------------|
| `ui_click` | Click any element by aria-label, data-name, text, or class |
| `ui_open_panel` | Open/close/toggle panels (pine-editor, watchlist, etc.) |
| `ui_fullscreen` | Toggle fullscreen |
| `ui_evaluate` | Execute arbitrary JavaScript in the page context |
| `ui_find_element` | Find UI elements by text, aria-label, or CSS selector |
| `ui_hover` | Hover over a UI element |
| `ui_keyboard` | Press keyboard keys or shortcuts |
| `ui_mouse_click` | Click at specific x,y coordinates |
| `ui_scroll` | Scroll the chart or page |
| `ui_type_text` | Type text into focused input |
| `layout_list` | List saved chart layouts |
| `layout_switch` | Switch to a saved layout |

### Watchlist (2)
| Tool | What it does |
|------|-------------|
| `watchlist_get` | Read watchlist — symbols, prices, changes |
| `watchlist_add` | Add a symbol to the watchlist |

## Pine Graphics Extraction

The `data_get_pine_*` tools can read data from **any visible Pine Script indicator**, even protected/encrypted ones. They access TradingView's internal graphics pipeline:

```
study._graphics._primitivesCollection
  .dwglines.get('lines').get(false)._primitivesDataById     → line prices (y1, y2)
  .dwglabels.get('labels').get(false)._primitivesDataById    → label text + price
  .dwgboxes.get('boxes').get(false)._primitivesDataById      → box boundaries
  .dwgtablecells.get('tableCells')._primitivesDataById       → table cell text
```

**Requirements:**
- The indicator must be **visible** on the chart (hidden studies don't receive graphics data from the server)
- The indicator uses Pine's drawing functions (`line.new()`, `label.new()`, `box.new()`, `table.new()`)

**Example — extract all levels from a custom profiler:**
```
"Use data_get_pine_lines to get all horizontal price levels"
"Use data_get_pine_tables with study_filter 'Profiler' to read the session table"
"Use data_get_pine_labels to get all text annotations with prices"
```

## Example Workflows

### Full Chart Analysis Report
```
"Get all indicator values with data_get_study_values, extract custom levels with
data_get_pine_lines and data_get_pine_tables, pull 100 bars of OHLCV, and build
me a confluence analysis report"
```

### Pine Script Development
```
"Write a Pine Script RSI divergence indicator, put it on the chart, and screenshot the result"
```

### Multi-Symbol Screening
```
"Compare Bollinger Band squeeze across ES, NQ, YM, and RTY on the 15-minute chart"
```

### Replay Practice
```
"Start replay on ES 5-minute from March 1st, step through 20 bars, buy at a support level"
```

## Architecture

```
Claude Code  ←→  MCP Server (stdio)  ←→  CDP (port 9222)  ←→  TradingView Desktop (Electron)
```

- **Transport**: MCP over stdio
- **Connection**: Chrome DevTools Protocol on localhost:9222
- **API access**: Direct paths to TradingView internals — no DOM scraping where avoidable
- **Pine Editor**: Monaco accessed via React fiber tree traversal
- **Pine Graphics**: Internal `_primitivesCollection` pipeline with `_primitivesDataById` Maps
- **No dependencies** beyond `@modelcontextprotocol/sdk` and `chrome-remote-interface`

## Requirements

- TradingView Desktop (Electron app) with `--remote-debugging-port=9222`
- Node.js 18+
- Claude Code with MCP support

## Disclaimer

This project is provided **for personal, educational, and research purposes only**.

**This tool is not affiliated with, endorsed by, or associated with TradingView Inc.** TradingView is a trademark of TradingView Inc.

By using this software, you acknowledge and agree that:

1. **You are solely responsible** for ensuring your use of this tool complies with [TradingView's Terms of Use](https://www.tradingview.com/policies/) and all applicable laws.
2. TradingView's Terms of Use **restrict automated data collection, scraping, and non-display usage** of their platform and data. This tool uses Chrome DevTools Protocol to programmatically interact with the TradingView Desktop app, which may conflict with those terms.
3. **You assume all risk** associated with using this tool. The authors are not responsible for any account bans, suspensions, legal actions, or other consequences resulting from its use.
4. This tool **must not be used** to:
   - Redistribute, resell, or commercially exploit TradingView's market data
   - Circumvent TradingView's access controls or subscription restrictions
   - Perform automated trading or algorithmic decision-making using extracted data
   - Violate the intellectual property rights of Pine Script indicator authors
5. Market data displayed by TradingView is sourced from exchanges and data providers with their own licensing terms. **Do not redistribute this data.**
6. This tool accesses internal, undocumented TradingView APIs that may change or break at any time without notice.

**Use at your own risk.** If you are unsure whether your intended use complies with TradingView's terms, do not use this tool.

## License

MIT — see [LICENSE](LICENSE) for details.

The MIT license applies to the source code of this project only. It does not grant any rights to TradingView's software, data, trademarks, or intellectual property.

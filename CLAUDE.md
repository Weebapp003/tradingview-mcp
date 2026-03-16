# TradingView MCP Bridge

CDP-based bridge between Claude Code and a live TradingView Desktop chart instance. 55 tools across 12 categories.

## Quick Start

1. Launch TradingView with CDP: `scripts\launch_tv_debug.bat`
2. Verify connection: `tv_health_check`
3. Explore available APIs: `tv_discover`

## Tool Reference (55 tools)

### Health (3)
| Tool | Purpose |
|------|---------|
| `tv_health_check` | Verify CDP connection, get symbol/TF/chart type, API availability |
| `tv_discover` | Report which known API paths are available and their methods |
| `tv_ui_state` | Get current UI state: which panels are open, what buttons are visible/enabled/disabled |

### Chart Control (10)
| Tool | Purpose |
|------|---------|
| `chart_get_state` | Get symbol, timeframe, chart type, all studies with IDs |
| `chart_set_symbol` | Change symbol (e.g., BTCUSD, AAPL, ES1!, NYMEX:CL1!) |
| `chart_set_timeframe` | Change timeframe (1, 5, 15, 60, D, W, M) |
| `chart_set_type` | Change chart type: Candles(1), Line(2), Area(3), HeikinAshi(8), etc. |
| `chart_manage_indicator` | Add/remove indicators by name or entity ID |
| `chart_get_visible_range` | Get visible date range as unix timestamps |
| `chart_set_visible_range` | Zoom to a specific date range (from/to unix timestamps) |
| `chart_scroll_to_date` | Jump chart view to center on a specific date |
| `symbol_info` | Get symbol metadata: exchange, type, description, session info |
| `symbol_search` | Search for symbols by name/keyword via the TV search dialog |

### Pine Script (10)
| Tool | Purpose |
|------|---------|
| `pine_get_source` | Read current Pine Script from editor (auto-opens Pine Editor) |
| `pine_set_source` | Inject Pine Script into editor |
| `pine_compile` | Compile / add script to chart |
| `pine_get_errors` | Get compilation errors from Monaco markers |
| `pine_save` | Save script (Ctrl+S) |
| `pine_get_console` | Read Pine console output: compile messages, log.info(), errors |
| `pine_smart_compile` | Intelligent compile: auto-detect button, compile, check errors, report study changes |
| `pine_new` | Create new blank Pine Script (indicator/strategy/library) |
| `pine_open` | Open a saved Pine Script by name |
| `pine_list_scripts` | List saved Pine Scripts from editor dropdown |

### Data Extraction (7)
| Tool | Purpose |
|------|---------|
| `data_get_ohlcv` | Get OHLCV bar data — direct bar access (max 500) |
| `data_get_indicator` | Get indicator/study info and input values by entity ID |
| `data_get_strategy_results` | Get strategy performance metrics (auto-opens Strategy Tester) |
| `data_get_trades` | Get trade list from Strategy Tester (max 20) |
| `data_get_equity` | Get equity curve data |
| `quote_get` | Get real-time quote data: last price, OHLC, volume, bid/ask |
| `depth_get` | Get order book / DOM data (bids, asks, spread) |

### Indicators (2)
| Tool | Purpose |
|------|---------|
| `indicator_set_inputs` | Change indicator settings (length, source, period, etc.) |
| `indicator_toggle_visibility` | Show or hide an indicator on the chart |

### Drawing (5)
| Tool | Purpose |
|------|---------|
| `draw_shape` | Draw shapes/lines (horizontal_line, trend_line, rectangle, text) |
| `draw_list` | List all shapes/drawings on the chart with IDs |
| `draw_clear` | Remove all drawings |
| `draw_remove_one` | Remove a specific drawing by entity ID |
| `draw_get_properties` | Get drawing properties, points, and style info |

### Alerts (3)
| Tool | Purpose |
|------|---------|
| `alert_create` | Create a price alert via the alert dialog |
| `alert_list` | List active alerts |
| `alert_delete` | Delete alerts (opens context menu for confirmation) |

### Capture (1)
| Tool | Purpose |
|------|---------|
| `capture_screenshot` | Screenshot: CDP (saves PNG) or API (TV's built-in). Regions: full/chart/strategy_tester |

### Batch (1)
| Tool | Purpose |
|------|---------|
| `batch_run` | Run action across symbols[] x timeframes[]: screenshot, get_ohlcv, get_strategy_results |

### Replay (6)
| Tool | Purpose |
|------|---------|
| `replay_start` | Start bar replay, optionally select a date |
| `replay_step` | Advance one bar in replay mode |
| `replay_autoplay` | Toggle autoplay, optionally set speed |
| `replay_stop` | Stop replay and return to realtime |
| `replay_trade` | Execute buy/sell/close in replay mode |
| `replay_status` | Get replay state: mode, date, position, P&L |

### UI Control (5)
| Tool | Purpose |
|------|---------|
| `ui_click` | Click any UI element by aria-label, data-name, text, or class substring |
| `ui_open_panel` | Open/close/toggle panels: pine-editor, strategy-tester, watchlist, alerts, trading |
| `ui_fullscreen` | Toggle fullscreen mode |
| `layout_list` | List saved chart layouts |
| `layout_switch` | Switch to a saved layout by name |

### Watchlist (2)
| Tool | Purpose |
|------|---------|
| `watchlist_get` | Read current watchlist: symbols, prices, changes |
| `watchlist_add` | Add a symbol to the watchlist |

## Common Workflows

### Pine Script Development Loop
1. `pine_set_source` — inject new script
2. `pine_smart_compile` — compile with auto-detect + error check
3. `pine_get_console` — read compile log and log.info() output
4. `data_get_strategy_results` — review performance
5. `capture_screenshot` — capture results

### Multi-Symbol Screening
1. `batch_run` with symbols array + `get_strategy_results` action
2. Compare metrics across symbols

### Chart Analysis
1. `chart_set_symbol` + `chart_set_timeframe`
2. `data_get_ohlcv` — get price data
3. `chart_manage_indicator` — add studies
4. `indicator_set_inputs` — tune indicator settings
5. `chart_scroll_to_date` — jump to a specific date
6. `capture_screenshot` — capture for review

### Indicator Tuning
1. `chart_get_state` — list studies with IDs
2. `indicator_set_inputs` — change length/period/source
3. `indicator_toggle_visibility` — show/hide as needed
4. `data_get_indicator` — read current input values

### Replay / Practice Trading
1. `replay_start` — enter replay mode at a date
2. `replay_step` or `replay_autoplay` — advance bars
3. `replay_trade` — buy/sell at key levels
4. `replay_status` — check position and P&L
5. `replay_stop` — return to realtime

### UI Navigation
1. `ui_open_panel` — open watchlist, alerts, or trading panel
2. `ui_click` — click any button by aria-label or text
3. `layout_switch` — load a saved layout

## Architecture

- **Connection**: CDP via `chrome-remote-interface` on `localhost:9222`
- **API Access**: Direct known paths to TradingView internals (no BFS discovery needed)
  - Chart API: `window.TradingViewApi._activeChartWidgetWV.value()`
  - Bar Data: `...._chartWidget.model().mainSeries().bars()`
  - Collection: `window.TradingViewApi._chartWidgetCollection`
  - Bottom Bar: `window.TradingView.bottomWidgetBar`
  - Replay: `window.TradingViewApi._replayApi`
  - Alerts: `window.TradingViewApi._alertService`
  - WS Layer: `window.ChartApiInstance`
- **Pine Editor**: Auto-opened via bottomWidgetBar when needed; Monaco lazy-loaded via React fiber traversal
- **Strategy Tester**: Auto-opened via bottomWidgetBar when querying results
- **Screenshots**: Saved to `screenshots/` with timestamps

## Conventions

- All tools return `{ success: true/false, ... }`
- OHLCV capped at 500 bars, trades at 20 per request
- API path availability logged to `discovery-log.json`
- Launch TV with: `scripts\launch_tv_debug.bat` (direct EXE with `--remote-debugging-port=9222`)

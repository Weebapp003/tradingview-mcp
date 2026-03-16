import { evaluate, evaluateAsync, KNOWN_PATHS } from '../connection.js';

const MAX_OHLCV_BARS = 500;
const MAX_TRADES = 20;

const CHART_API = KNOWN_PATHS.chartApi;
const BARS_PATH = KNOWN_PATHS.mainSeriesBars;
const BOTTOM_BAR = KNOWN_PATHS.bottomWidgetBar;

function jsonResult(obj, isError = false) {
  return {
    content: [{ type: 'text', text: JSON.stringify(obj, null, 2) }],
    ...(isError && { isError: true }),
  };
}

export function registerDataTools(server) {

  // ── OHLCV Bar Data ──────────────────────────────────────────────────
  server.tool('data_get_ohlcv', 'Get OHLCV bar data from the chart', {
    count: { type: 'number', description: 'Number of bars to retrieve (max 500)', default: 100 },
  }, async ({ count }) => {
    const limit = Math.min(count || 100, MAX_OHLCV_BARS);
    try {
      let data;

      // Strategy 1: Direct bar access (synchronous, fast)
      try {
        data = await evaluate(`
          (function() {
            var bars = ${BARS_PATH};
            if (!bars || typeof bars.lastIndex !== 'function') return null;
            var result = [];
            var end = bars.lastIndex();
            var start = Math.max(bars.firstIndex(), end - ${limit} + 1);
            for (var i = start; i <= end; i++) {
              var v = bars.valueAt(i);
              if (v) result.push({time: v[0], open: v[1], high: v[2], low: v[3], close: v[4], volume: v[5] || 0});
            }
            return {bars: result, total_bars: bars.size(), source: 'direct_bars'};
          })()
        `);
      } catch {
        data = null;
      }

      // Note: exportData() returns Promise.reject("Data export is not supported") in TV Desktop.
      // Direct bar access above is the only working path.

      if (!data || !data.bars || data.bars.length === 0) {
        return jsonResult({ success: false, error: 'Could not extract OHLCV data. The chart may still be loading.' }, true);
      }

      return jsonResult({
        success: true,
        bar_count: data.bars.length,
        total_available: data.total_bars,
        source: data.source,
        bars: data.bars,
      });
    } catch (err) {
      return jsonResult({ success: false, error: err.message }, true);
    }
  });

  // ── Indicator / Study Values ────────────────────────────────────────
  // Note: exportData() is not supported in TV Desktop. We use getStudyById() instead.
  server.tool('data_get_indicator', 'Get indicator/study info and input values', {
    entity_id: { type: 'string', description: 'Study entity ID (from chart_get_state)' },
  }, async ({ entity_id }) => {
    try {
      const data = await evaluate(`
        (function() {
          var api = ${CHART_API};
          var study = api.getStudyById('${entity_id}');
          if (!study) return { error: 'Study not found: ${entity_id}' };
          var result = { name: null, inputs: null, visible: null };
          try { result.visible = study.isVisible(); } catch(e) {}
          try {
            result.inputs = study.getInputValues();
          } catch(e) { result.inputs_error = e.message; }
          return result;
        })()
      `);

      if (data?.error) {
        return jsonResult({ success: false, error: data.error }, true);
      }

      return jsonResult({
        success: true,
        entity_id,
        visible: data?.visible,
        inputs: data?.inputs,
      });
    } catch (err) {
      return jsonResult({ success: false, error: err.message }, true);
    }
  });

  // ── Strategy Performance Metrics ────────────────────────────────────
  server.tool('data_get_strategy_results', 'Get strategy performance metrics from Strategy Tester', {}, async () => {
    try {
      // Ensure Strategy Tester panel is open
      await evaluate(`
        (function() {
          try { ${BOTTOM_BAR}.showWidget('backtesting'); } catch(e) {}
        })()
      `);
      // Brief wait for panel to render
      await new Promise(r => setTimeout(r, 500));

      const results = await evaluate(`
        (function() {
          var result = {metrics: {}, source: 'dom_scraping'};

          var panel = document.querySelector('[data-name="backtesting"]')
            || document.querySelector('[class*="strategyReport"]')
            || document.querySelector('[class*="strategy-tester"]');

          if (!panel) {
            // Broaden search via tab text
            var tabs = document.querySelectorAll('[class*="tab"]');
            for (var i = 0; i < tabs.length; i++) {
              if (/strategy|backtest/i.test(tabs[i].textContent)) {
                panel = tabs[i].closest('[class*="panel"]');
                break;
              }
            }
          }

          if (!panel) return {metrics: {}, source: 'not_found', error: 'Strategy Tester panel not found. Ensure a strategy is on the chart.'};

          // Click "Overview" or "Performance Summary" tab if present
          var tabBtns = panel.querySelectorAll('[class*="tab"], button');
          for (var t = 0; t < tabBtns.length; t++) {
            if (/overview|performance.*summary/i.test(tabBtns[t].textContent)) {
              tabBtns[t].click();
              break;
            }
          }

          // Extract key-value rows
          var rows = panel.querySelectorAll('[class*="row"], tr');
          rows.forEach(function(row) {
            var cells = row.querySelectorAll('[class*="cell"], td, span');
            if (cells.length >= 2) {
              var key = cells[0].textContent.trim();
              var value = cells[1].textContent.trim();
              if (key && value) result.metrics[key] = value;
            }
          });

          // Also try report-item / metric patterns
          var items = panel.querySelectorAll('[class*="reportItem"], [class*="metric"]');
          items.forEach(function(item) {
            var label = item.querySelector('[class*="label"]');
            var value = item.querySelector('[class*="value"]');
            if (label && value) result.metrics[label.textContent.trim()] = value.textContent.trim();
          });

          return result;
        })()
      `);

      return jsonResult({
        success: true,
        metric_count: Object.keys(results?.metrics || {}).length,
        source: results?.source,
        metrics: results?.metrics || {},
        error: results?.error,
      });
    } catch (err) {
      return jsonResult({ success: false, error: err.message }, true);
    }
  });

  // ── Trade List ──────────────────────────────────────────────────────
  server.tool('data_get_trades', 'Get trade list from Strategy Tester', {
    max_trades: { type: 'number', description: 'Maximum trades to return', default: 20 },
  }, async ({ max_trades }) => {
    const limit = Math.min(max_trades || 20, MAX_TRADES);
    try {
      // Ensure Strategy Tester panel is open
      await evaluate(`
        (function() {
          try { ${BOTTOM_BAR}.showWidget('backtesting'); } catch(e) {}
        })()
      `);
      await new Promise(r => setTimeout(r, 500));

      const trades = await evaluate(`
        (function() {
          var trades = [];

          var panel = document.querySelector('[data-name="backtesting"]')
            || document.querySelector('[class*="strategyReport"]');
          if (!panel) return {trades: [], error: 'Strategy Tester panel not found. Ensure a strategy is on the chart.'};

          // Click "List of Trades" tab
          var tabs = panel.querySelectorAll('[class*="tab"], button');
          for (var i = 0; i < tabs.length; i++) {
            if (/list.*trade|trade.*list/i.test(tabs[i].textContent)) {
              tabs[i].click();
              break;
            }
          }

          // Extract trade rows
          var rows = panel.querySelectorAll('table tr, [class*="row"]');
          var headerCells = null;
          for (var r = 0; r < rows.length && trades.length < ${limit}; r++) {
            var cells = rows[r].querySelectorAll('td, th, [class*="cell"]');
            if (cells.length < 3) continue;

            // Detect header row
            var isHeader = rows[r].querySelector('th') !== null;
            if (!headerCells && isHeader) {
              headerCells = [];
              cells.forEach(function(c) { headerCells.push(c.textContent.trim()); });
              continue;
            }

            var trade = {};
            cells.forEach(function(c, idx) {
              var key = (headerCells && headerCells[idx]) ? headerCells[idx] : ('col_' + idx);
              trade[key] = c.textContent.trim();
            });
            trades.push(trade);
          }

          return {trades: trades};
        })()
      `);

      return jsonResult({
        success: true,
        trade_count: trades?.trades?.length || 0,
        trades: trades?.trades || [],
        error: trades?.error,
      });
    } catch (err) {
      return jsonResult({ success: false, error: err.message }, true);
    }
  });

  // ── Equity Curve ────────────────────────────────────────────────────
  server.tool('data_get_equity', 'Get equity curve data from Strategy Tester', {}, async () => {
    try {
      // Ensure Strategy Tester panel is open
      await evaluate(`
        (function() {
          try { ${BOTTOM_BAR}.showWidget('backtesting'); } catch(e) {}
        })()
      `);
      await new Promise(r => setTimeout(r, 500));

      const equity = await evaluate(`
        (function() {
          var panel = document.querySelector('[data-name="backtesting"]')
            || document.querySelector('[class*="strategyReport"]');
          if (!panel) return {data: [], error: 'Strategy Tester panel not found. Ensure a strategy is on the chart.'};

          // Click equity/performance tab
          var tabs = panel.querySelectorAll('[class*="tab"], button');
          for (var i = 0; i < tabs.length; i++) {
            if (/equity|performance/i.test(tabs[i].textContent)) {
              tabs[i].click();
              break;
            }
          }

          // Extract equity values
          var data = [];
          var cells = panel.querySelectorAll('[class*="equity"], [class*="value"]');
          cells.forEach(function(c) {
            var text = c.textContent.trim();
            var num = parseFloat(text.replace(/[^0-9.\\-]/g, ''));
            if (!isNaN(num)) data.push(num);
          });

          return {data: data, source: 'dom_scraping'};
        })()
      `);

      return jsonResult({
        success: true,
        data_points: equity?.data?.length || 0,
        source: equity?.source,
        data: equity?.data || [],
        error: equity?.error,
      });
    } catch (err) {
      return jsonResult({ success: false, error: err.message }, true);
    }
  });

  // ── Real-Time Quote ─────────────────────────────────────────────────
  server.tool('quote_get', 'Get real-time quote data for a symbol (price, OHLC, volume)', {
    symbol: { type: 'string', description: 'Symbol to quote (blank = current chart symbol)', default: '' },
  }, async ({ symbol }) => {
    try {
      const data = await evaluate(`
        (function() {
          var api = ${CHART_API};
          var sym = '${symbol || ''}';

          // Resolve symbol — use chart's current symbol if none provided
          if (!sym) {
            try { sym = api.symbol(); } catch(e) {}
          }
          if (!sym) {
            try { sym = api.symbolExt().symbol; } catch(e) {}
          }

          // Get extended symbol info (description, exchange, type, etc.)
          var ext = {};
          try { ext = api.symbolExt() || {}; } catch(e) {}

          // Get the latest bar for price data
          var bars = ${BARS_PATH};
          var quote = { symbol: sym };
          if (bars && typeof bars.lastIndex === 'function') {
            var last = bars.valueAt(bars.lastIndex());
            if (last) {
              quote.time = last[0];
              quote.open = last[1];
              quote.high = last[2];
              quote.low = last[3];
              quote.close = last[4];
              quote.last = last[4];
              quote.volume = last[5] || 0;
            }
          }

          // Try to get bid/ask from DOM panel elements
          try {
            var bidEl = document.querySelector('[class*="bid"] [class*="price"], [class*="dom-"] [class*="bid"]');
            var askEl = document.querySelector('[class*="ask"] [class*="price"], [class*="dom-"] [class*="ask"]');
            if (bidEl) quote.bid = parseFloat(bidEl.textContent.replace(/[^0-9.\\-]/g, ''));
            if (askEl) quote.ask = parseFloat(askEl.textContent.replace(/[^0-9.\\-]/g, ''));
          } catch(e) {}

          // Try to read the header bar price display
          try {
            var hdr = document.querySelector('[class*="headerRow"] [class*="last-"]');
            if (hdr) {
              var hdrPrice = parseFloat(hdr.textContent.replace(/[^0-9.\\-]/g, ''));
              if (!isNaN(hdrPrice)) quote.header_price = hdrPrice;
            }
          } catch(e) {}

          // Attach symbol metadata
          if (ext.description) quote.description = ext.description;
          if (ext.exchange) quote.exchange = ext.exchange;
          if (ext.type) quote.type = ext.type;

          return quote;
        })()
      `);

      if (!data || (!data.last && !data.close)) {
        return jsonResult({ success: false, error: 'Could not retrieve quote. The chart may still be loading.', partial: data }, true);
      }

      return jsonResult({ success: true, ...data });
    } catch (err) {
      return jsonResult({ success: false, error: err.message }, true);
    }
  });

  // ── Depth of Market / Order Book ────────────────────────────────────
  server.tool('depth_get', 'Get order book / DOM (Depth of Market) data from the chart', {}, async () => {
    try {
      const data = await evaluate(`
        (function() {
          // Look for DOM / order book panel
          var domPanel = document.querySelector('[class*="depth"]')
            || document.querySelector('[class*="orderBook"]')
            || document.querySelector('[class*="dom-"]')
            || document.querySelector('[class*="DOM"]')
            || document.querySelector('[data-name="dom"]');

          if (!domPanel) {
            return {
              found: false,
              error: 'DOM / Depth of Market panel not found. Please open the DOM panel in TradingView (right-click chart > Trade > DOM, or use the trading panel).'
            };
          }

          var bids = [];
          var asks = [];

          // Strategy 1: Look for rows with bid/ask classification
          var rows = domPanel.querySelectorAll('[class*="row"], tr');
          for (var i = 0; i < rows.length; i++) {
            var row = rows[i];
            var priceEl = row.querySelector('[class*="price"]');
            var sizeEl = row.querySelector('[class*="size"], [class*="volume"], [class*="qty"]');
            if (!priceEl) continue;

            var price = parseFloat(priceEl.textContent.replace(/[^0-9.\\-]/g, ''));
            var size = sizeEl ? parseFloat(sizeEl.textContent.replace(/[^0-9.\\-]/g, '')) : 0;
            if (isNaN(price)) continue;

            var rowClass = row.className || '';
            var rowHTML = row.innerHTML || '';
            if (/bid|buy/i.test(rowClass) || /bid|buy/i.test(rowHTML)) {
              bids.push({ price: price, size: size });
            } else if (/ask|sell/i.test(rowClass) || /ask|sell/i.test(rowHTML)) {
              asks.push({ price: price, size: size });
            } else {
              // If no explicit class, use position heuristic: top half = asks, bottom half = bids
              if (i < rows.length / 2) {
                asks.push({ price: price, size: size });
              } else {
                bids.push({ price: price, size: size });
              }
            }
          }

          // Strategy 2: If no rows found, try generic cell scraping
          if (bids.length === 0 && asks.length === 0) {
            var cells = domPanel.querySelectorAll('[class*="cell"], td');
            var prices = [];
            cells.forEach(function(c) {
              var val = parseFloat(c.textContent.replace(/[^0-9.\\-]/g, ''));
              if (!isNaN(val) && val > 0) prices.push(val);
            });
            if (prices.length > 0) {
              return {
                found: true,
                raw_values: prices.slice(0, 50),
                bids: [],
                asks: [],
                note: 'Could not classify bid/ask levels. Raw numeric values returned.'
              };
            }
          }

          // Sort: bids descending, asks ascending
          bids.sort(function(a, b) { return b.price - a.price; });
          asks.sort(function(a, b) { return a.price - b.price; });

          var spread = null;
          if (asks.length > 0 && bids.length > 0) {
            spread = +(asks[0].price - bids[0].price).toFixed(6);
          }

          return { found: true, bids: bids, asks: asks, spread: spread };
        })()
      `);

      if (!data || !data.found) {
        return jsonResult({
          success: false,
          error: data?.error || 'DOM panel not found.',
          hint: 'Open the DOM panel in TradingView before using this tool.',
        }, true);
      }

      return jsonResult({
        success: true,
        bid_levels: data.bids?.length || 0,
        ask_levels: data.asks?.length || 0,
        spread: data.spread,
        bids: data.bids || [],
        asks: data.asks || [],
        raw_values: data.raw_values,
        note: data.note,
      });
    } catch (err) {
      return jsonResult({ success: false, error: err.message }, true);
    }
  });
}

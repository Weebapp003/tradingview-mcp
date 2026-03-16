import { evaluate, getClient } from '../connection.js';

export function registerWatchlistTools(server) {

  // ── Helper: ensure watchlist panel is open ──

  async function ensureWatchlistOpen() {
    const result = await evaluate(`
      (function() {
        var btn = document.querySelector('[data-name="base-watchlist-widget-button"]')
          || document.querySelector('[aria-label="Watchlist, details and news"]')
          || document.querySelector('[aria-label="Watchlist"]');

        if (!btn) return { error: 'Watchlist button not found' };

        // Check if the panel is already open
        var isActive = btn.getAttribute('aria-pressed') === 'true'
          || btn.classList.toString().indexOf('isActive') !== -1
          || btn.classList.toString().indexOf('active') !== -1
          || btn.classList.toString().indexOf('Active') !== -1;

        var rightArea = document.querySelector('[class*="layout__area--right"]');
        var sidebarOpen = !!(rightArea && rightArea.offsetWidth > 50);
        var isOpen = isActive && sidebarOpen;

        if (!isOpen) {
          btn.click();
          return { opened: true, was_open: false };
        }

        return { opened: false, was_open: true };
      })()
    `);

    if (result && result.error) {
      throw new Error(result.error);
    }

    // If we just opened it, wait for it to render
    if (result && result.opened) {
      await new Promise(r => setTimeout(r, 300));
    }

    return result;
  }

  // ── 1. watchlist_get — Read current watchlist symbols ──

  server.tool('watchlist_get', 'Get all symbols from the current TradingView watchlist with last price, change, and change%', {}, async () => {
    try {
      await ensureWatchlistOpen();

      // Wait a moment for DOM to be fully rendered
      await new Promise(r => setTimeout(r, 300));

      const symbols = await evaluate(`
        (function() {
          var results = [];

          // Approach A: Look for elements with data-symbol-full or data-symbol attributes
          var symbolEls = document.querySelectorAll('[data-symbol-full]');
          if (symbolEls.length > 0) {
            for (var i = 0; i < symbolEls.length; i++) {
              var el = symbolEls[i];
              var sym = el.getAttribute('data-symbol-full') || el.getAttribute('data-symbol') || '';
              if (!sym) continue;

              // Try to find price data in the same row
              var row = el.closest('[class*="row"]') || el.closest('tr') || el.parentElement;
              var cells = row ? row.querySelectorAll('[class*="cell"], td, [class*="column"]') : [];
              var nums = [];
              for (var j = 0; j < cells.length; j++) {
                var t = cells[j].textContent.trim();
                if (/^[\\-+]?[\\d,]+\\.?\\d*%?$/.test(t.replace(/[\\s,]/g, ''))) {
                  nums.push(t);
                }
              }

              results.push({
                symbol: sym,
                last: nums[0] || null,
                change: nums[1] || null,
                change_percent: nums[2] || null,
              });
            }
            return results;
          }

          // Approach B: Look inside the watchlist container for rows
          var container = document.querySelector('[data-name="symbol-list-wrap"]')
            || document.querySelector('[class*="widgetbar-widget-watchlist"]')
            || document.querySelector('[class*="watchlist"]');

          if (!container) {
            // Broader: look in right sidebar
            container = document.querySelector('[class*="layout__area--right"]');
          }

          if (!container) return results;

          // Approach B1: rows with class containing "row" or "listRow" or "symbolRow"
          var rows = container.querySelectorAll('[class*="listRow"], [class*="symbolRow"], [class*="row-"]');
          if (rows.length === 0) {
            // Fallback: get all direct-ish child divs that look like rows
            rows = container.querySelectorAll('div[class*="row"]');
          }

          for (var i = 0; i < rows.length; i++) {
            var row = rows[i];
            var text = row.textContent.trim();
            if (!text || text.length > 300) continue;

            // Try to extract symbol from data attributes on the row or children
            var symAttr = row.getAttribute('data-symbol-full')
              || row.getAttribute('data-symbol')
              || (row.querySelector('[data-symbol-full]') && row.querySelector('[data-symbol-full]').getAttribute('data-symbol-full'))
              || (row.querySelector('[data-symbol]') && row.querySelector('[data-symbol]').getAttribute('data-symbol'));

            // Try to extract from the row's text content
            // Typical format: "AAPL  Apple Inc  189.84  +1.23  +0.65%"
            var cells = row.querySelectorAll('[class*="cell"], [class*="column"], [class*="col"]');
            var cellTexts = [];
            for (var j = 0; j < cells.length; j++) {
              var ct = cells[j].textContent.trim();
              if (ct) cellTexts.push(ct);
            }

            var sym = symAttr || cellTexts[0] || null;
            if (!sym) {
              // Last resort: first word that looks like a ticker
              var match = text.match(/^([A-Z0-9.:!]+)/);
              if (match) sym = match[1];
            }

            if (!sym) continue;

            // Extract numeric values
            var numericCells = [];
            for (var j = 0; j < cellTexts.length; j++) {
              if (/^[\\-+]?[\\d,]+\\.?\\d*%?$/.test(cellTexts[j].replace(/[\\s,]/g, ''))) {
                numericCells.push(cellTexts[j]);
              }
            }

            results.push({
              symbol: sym,
              last: numericCells[0] || null,
              change: numericCells[1] || null,
              change_percent: numericCells[2] || null,
            });
          }

          // Approach C: If still nothing, try generic approach — find all elements
          // whose text matches a ticker pattern inside the container
          if (results.length === 0) {
            var allEls = container.querySelectorAll('*');
            var seen = {};
            for (var i = 0; i < allEls.length; i++) {
              var el = allEls[i];
              // Only leaf text nodes
              if (el.children.length > 0) continue;
              var t = el.textContent.trim();
              // Looks like a stock symbol: 1-10 uppercase letters/digits, optionally with : or .
              if (/^[A-Z][A-Z0-9.:!]{0,15}$/.test(t) && !seen[t]) {
                seen[t] = true;
                results.push({
                  symbol: t,
                  last: null,
                  change: null,
                  change_percent: null,
                });
              }
            }
          }

          return results;
        })()
      `);

      return {
        content: [{ type: 'text', text: JSON.stringify({
          success: true,
          count: symbols ? symbols.length : 0,
          symbols: symbols || [],
        }, null, 2) }],
      };
    } catch (err) {
      return {
        content: [{ type: 'text', text: JSON.stringify({ success: false, error: err.message }, null, 2) }],
        isError: true,
      };
    }
  });

  // ── 2. watchlist_add — Add a symbol to the watchlist ──

  server.tool('watchlist_add', 'Add a symbol to the TradingView watchlist', {
    symbol: { type: 'string', description: 'Symbol to add (e.g., AAPL, BTCUSD, ES1!, NYMEX:CL1!)' },
  }, async ({ symbol }) => {
    try {
      await ensureWatchlistOpen();

      // Click the add symbol button
      const clicked = await evaluate(`
        (function() {
          var btn = document.querySelector('[data-name="add-symbol-button"]');
          if (!btn) {
            // Fallback: look for a "+" button inside the watchlist area
            var container = document.querySelector('[data-name="symbol-list-wrap"]')
              || document.querySelector('[class*="layout__area--right"]');
            if (container) {
              var buttons = container.querySelectorAll('button');
              for (var i = 0; i < buttons.length; i++) {
                var text = buttons[i].textContent.trim();
                var ariaLabel = buttons[i].getAttribute('aria-label') || '';
                if (text === '+' || /add.*symbol/i.test(ariaLabel) || /add/i.test(text)) {
                  buttons[i].click();
                  return { found: true, method: 'fallback_button' };
                }
              }
            }
            return { found: false };
          }
          btn.click();
          return { found: true, method: 'data-name' };
        })()
      `);

      if (!clicked || !clicked.found) {
        return {
          content: [{ type: 'text', text: JSON.stringify({
            success: false,
            error: 'Add symbol button not found in watchlist panel',
          }, null, 2) }],
          isError: true,
        };
      }

      // Wait for the search input to appear
      await new Promise(r => setTimeout(r, 300));

      // Find and focus the search input
      const inputReady = await evaluate(`
        (function() {
          // Look for the search input that appeared after clicking add
          var input = document.querySelector('[data-name="symbol-list-wrap"] input[type="text"]')
            || document.querySelector('[class*="watchlist"] input[type="text"]')
            || document.querySelector('[class*="layout__area--right"] input[type="text"]')
            || document.activeElement;

          if (input && input.tagName === 'INPUT') {
            input.focus();
            // Clear any existing text
            var nativeSet = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
            nativeSet.call(input, '');
            input.dispatchEvent(new Event('input', { bubbles: true }));
            return { ready: true, tag: input.tagName };
          }

          // Broader search: any visible input in the right panel
          var inputs = document.querySelectorAll('input[type="text"], input:not([type])');
          for (var i = 0; i < inputs.length; i++) {
            if (inputs[i].offsetParent !== null) {
              var rect = inputs[i].getBoundingClientRect();
              // Should be in the right portion of the screen (watchlist area)
              if (rect.right > window.innerWidth * 0.5) {
                inputs[i].focus();
                var nativeSet = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                nativeSet.call(inputs[i], '');
                inputs[i].dispatchEvent(new Event('input', { bubbles: true }));
                return { ready: true, tag: inputs[i].tagName, method: 'broad_search' };
              }
            }
          }

          return { ready: false };
        })()
      `);

      if (!inputReady || !inputReady.ready) {
        return {
          content: [{ type: 'text', text: JSON.stringify({
            success: false,
            error: 'Search input not found after clicking add symbol button',
          }, null, 2) }],
          isError: true,
        };
      }

      // Type the symbol using CDP Input.insertText
      const c = await getClient();
      await c.Input.insertText({ text: symbol });

      // Wait for search results to populate
      await new Promise(r => setTimeout(r, 500));

      // Press Enter to select the first result
      await c.Input.dispatchKeyEvent({
        type: 'keyDown',
        key: 'Enter',
        code: 'Enter',
        windowsVirtualKeyCode: 13,
      });
      await c.Input.dispatchKeyEvent({
        type: 'keyUp',
        key: 'Enter',
        code: 'Enter',
        windowsVirtualKeyCode: 13,
      });

      // Wait for the symbol to be added
      await new Promise(r => setTimeout(r, 300));

      // Press Escape to close the search/add interface
      await c.Input.dispatchKeyEvent({
        type: 'keyDown',
        key: 'Escape',
        code: 'Escape',
        windowsVirtualKeyCode: 27,
      });
      await c.Input.dispatchKeyEvent({
        type: 'keyUp',
        key: 'Escape',
        code: 'Escape',
        windowsVirtualKeyCode: 27,
      });

      return {
        content: [{ type: 'text', text: JSON.stringify({
          success: true,
          symbol,
          action: 'added',
        }, null, 2) }],
      };
    } catch (err) {
      // Try to close any open search/input on error
      try {
        const c = await getClient();
        await c.Input.dispatchKeyEvent({
          type: 'keyDown',
          key: 'Escape',
          code: 'Escape',
          windowsVirtualKeyCode: 27,
        });
        await c.Input.dispatchKeyEvent({
          type: 'keyUp',
          key: 'Escape',
          code: 'Escape',
          windowsVirtualKeyCode: 27,
        });
      } catch (_) {}

      return {
        content: [{ type: 'text', text: JSON.stringify({ success: false, error: err.message }, null, 2) }],
        isError: true,
      };
    }
  });
}

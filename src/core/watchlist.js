/**
 * Core watchlist logic.
 */
import { evaluate, getClient } from '../connection.js';

async function ensureWatchlistOpen() {
  const result = await evaluate(`
    (function() {
      var btn = document.querySelector('[data-name="base-watchlist-widget-button"]')
        || document.querySelector('[aria-label="Watchlist, details and news"]')
        || document.querySelector('[aria-label="Watchlist"]');
      if (!btn) return { error: 'Watchlist button not found' };
      var isActive = btn.getAttribute('aria-pressed') === 'true'
        || btn.classList.toString().indexOf('isActive') !== -1
        || btn.classList.toString().indexOf('active') !== -1
        || btn.classList.toString().indexOf('Active') !== -1;
      var rightArea = document.querySelector('[class*="layout__area--right"]');
      var sidebarOpen = !!(rightArea && rightArea.offsetWidth > 50);
      var isOpen = isActive && sidebarOpen;
      if (!isOpen) { btn.click(); return { opened: true, was_open: false }; }
      return { opened: false, was_open: true };
    })()
  `);
  if (result && result.error) throw new Error(result.error);
  if (result && result.opened) await new Promise(r => setTimeout(r, 300));
  return result;
}

export async function get() {
  await ensureWatchlistOpen();
  await new Promise(r => setTimeout(r, 300));

  const symbols = await evaluate(`
    (function() {
      var results = [];
      var symbolEls = document.querySelectorAll('[data-symbol-full]');
      if (symbolEls.length > 0) {
        for (var i = 0; i < symbolEls.length; i++) {
          var el = symbolEls[i];
          var sym = el.getAttribute('data-symbol-full') || el.getAttribute('data-symbol') || '';
          if (!sym) continue;
          var row = el.closest('[class*="row"]') || el.closest('tr') || el.parentElement;
          var cells = row ? row.querySelectorAll('[class*="cell"], td, [class*="column"]') : [];
          var nums = [];
          for (var j = 0; j < cells.length; j++) {
            var t = cells[j].textContent.trim();
            if (/^[\\-+]?[\\d,]+\\.?\\d*%?$/.test(t.replace(/[\\s,]/g, ''))) nums.push(t);
          }
          results.push({ symbol: sym, last: nums[0] || null, change: nums[1] || null, change_percent: nums[2] || null });
        }
        return results;
      }
      var container = document.querySelector('[data-name="symbol-list-wrap"]')
        || document.querySelector('[class*="widgetbar-widget-watchlist"]')
        || document.querySelector('[class*="watchlist"]');
      if (!container) container = document.querySelector('[class*="layout__area--right"]');
      if (!container) return results;
      var rows = container.querySelectorAll('[class*="listRow"], [class*="symbolRow"], [class*="row-"]');
      if (rows.length === 0) rows = container.querySelectorAll('div[class*="row"]');
      for (var i = 0; i < rows.length; i++) {
        var row = rows[i];
        var text = row.textContent.trim();
        if (!text || text.length > 300) continue;
        var symAttr = row.getAttribute('data-symbol-full') || row.getAttribute('data-symbol')
          || (row.querySelector('[data-symbol-full]') && row.querySelector('[data-symbol-full]').getAttribute('data-symbol-full'))
          || (row.querySelector('[data-symbol]') && row.querySelector('[data-symbol]').getAttribute('data-symbol'));
        var cells = row.querySelectorAll('[class*="cell"], [class*="column"], [class*="col"]');
        var cellTexts = [];
        for (var j = 0; j < cells.length; j++) { var ct = cells[j].textContent.trim(); if (ct) cellTexts.push(ct); }
        var sym = symAttr || cellTexts[0] || null;
        if (!sym) { var match = text.match(/^([A-Z0-9.:!]+)/); if (match) sym = match[1]; }
        if (!sym) continue;
        var numericCells = [];
        for (var j = 0; j < cellTexts.length; j++) {
          if (/^[\\-+]?[\\d,]+\\.?\\d*%?$/.test(cellTexts[j].replace(/[\\s,]/g, ''))) numericCells.push(cellTexts[j]);
        }
        results.push({ symbol: sym, last: numericCells[0] || null, change: numericCells[1] || null, change_percent: numericCells[2] || null });
      }
      if (results.length === 0) {
        var allEls = container.querySelectorAll('*');
        var seen = {};
        for (var i = 0; i < allEls.length; i++) {
          var el = allEls[i];
          if (el.children.length > 0) continue;
          var t = el.textContent.trim();
          if (/^[A-Z][A-Z0-9.:!]{0,15}$/.test(t) && !seen[t]) {
            seen[t] = true;
            results.push({ symbol: t, last: null, change: null, change_percent: null });
          }
        }
      }
      return results;
    })()
  `);

  return { success: true, count: symbols ? symbols.length : 0, source: 'dom_fallback', symbols: symbols || [] };
}

export async function add({ symbol }) {
  await ensureWatchlistOpen();

  const clicked = await evaluate(`
    (function() {
      var btn = document.querySelector('[data-name="add-symbol-button"]');
      if (!btn) {
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

  if (!clicked || !clicked.found) throw new Error('Add symbol button not found in watchlist panel');

  await new Promise(r => setTimeout(r, 300));

  const inputReady = await evaluate(`
    (function() {
      var input = document.querySelector('[data-name="symbol-list-wrap"] input[type="text"]')
        || document.querySelector('[class*="watchlist"] input[type="text"]')
        || document.querySelector('[class*="layout__area--right"] input[type="text"]')
        || document.activeElement;
      if (input && input.tagName === 'INPUT') {
        input.focus();
        var nativeSet = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
        nativeSet.call(input, '');
        input.dispatchEvent(new Event('input', { bubbles: true }));
        return { ready: true, tag: input.tagName };
      }
      var inputs = document.querySelectorAll('input[type="text"], input:not([type])');
      for (var i = 0; i < inputs.length; i++) {
        if (inputs[i].offsetParent !== null) {
          var rect = inputs[i].getBoundingClientRect();
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

  if (!inputReady || !inputReady.ready) throw new Error('Search input not found after clicking add symbol button');

  const c = await getClient();
  await c.Input.insertText({ text: symbol });
  await new Promise(r => setTimeout(r, 500));

  await c.Input.dispatchKeyEvent({ type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
  await c.Input.dispatchKeyEvent({ type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
  await new Promise(r => setTimeout(r, 300));

  await c.Input.dispatchKeyEvent({ type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
  await c.Input.dispatchKeyEvent({ type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });

  return { success: true, symbol, action: 'added', source: 'dom_fallback' };
}

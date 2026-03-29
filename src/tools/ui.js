import { z } from 'zod';
import { evaluate, getClient } from '../connection.js';

export function registerUiTools(server) {

  // ── 1. ui_click — Generic smart button clicker ──

  server.tool('ui_click', 'Click a UI element by aria-label, data-name, text content, or class substring', {
    by: z.enum(['aria-label', 'data-name', 'text', 'class-contains']).describe('Selector strategy'),
    value: z.string().describe('Value to match against the chosen selector strategy'),
  }, async ({ by, value }) => {
    try {
      const escaped = JSON.stringify(value);
      const result = await evaluate(`
        (function() {
          var by = ${JSON.stringify(by)};
          var value = ${escaped};
          var el = null;

          if (by === 'aria-label') {
            el = document.querySelector('[aria-label="' + value.replace(/"/g, '\\\\"') + '"]');
          } else if (by === 'data-name') {
            el = document.querySelector('[data-name="' + value.replace(/"/g, '\\\\"') + '"]');
          } else if (by === 'text') {
            var candidates = document.querySelectorAll('button, a, [role="button"], [role="menuitem"], [role="tab"]');
            for (var i = 0; i < candidates.length; i++) {
              var text = candidates[i].textContent.trim();
              if (text === value || text.toLowerCase() === value.toLowerCase()) {
                el = candidates[i];
                break;
              }
            }
          } else if (by === 'class-contains') {
            el = document.querySelector('[class*="' + value.replace(/"/g, '\\\\"') + '"]');
          }

          if (!el) return { found: false };

          el.click();
          return {
            found: true,
            tag: el.tagName.toLowerCase(),
            text: (el.textContent || '').trim().substring(0, 80),
            aria_label: el.getAttribute('aria-label') || null,
            data_name: el.getAttribute('data-name') || null,
          };
        })()
      `);

      if (!result || !result.found) {
        return {
          content: [{ type: 'text', text: JSON.stringify({
            success: false,
            error: 'No matching element found for ' + by + '="' + value + '"',
          }, null, 2) }],
          isError: true,
        };
      }

      return {
        content: [{ type: 'text', text: JSON.stringify({
          success: true,
          clicked: result,
        }, null, 2) }],
      };
    } catch (err) {
      return {
        content: [{ type: 'text', text: JSON.stringify({ success: false, error: err.message }, null, 2) }],
        isError: true,
      };
    }
  });

  // ── 2. ui_open_panel — Open/close specific panels ──

  server.tool('ui_open_panel', 'Open, close, or toggle TradingView panels (pine-editor, strategy-tester, watchlist, alerts, trading)', {
    panel: z.enum(['pine-editor', 'strategy-tester', 'watchlist', 'alerts', 'trading']).describe('Panel name'),
    action: z.enum(['open', 'close', 'toggle']).describe('Action to perform'),
  }, async ({ panel, action }) => {
    try {
      const isBottomPanel = panel === 'pine-editor' || panel === 'strategy-tester';

      if (isBottomPanel) {
        const widgetName = panel === 'pine-editor' ? 'pine-editor' : 'backtesting';

        const result = await evaluate(`
          (function() {
            var bwb = window.TradingView && window.TradingView.bottomWidgetBar;
            if (!bwb) return { error: 'bottomWidgetBar not available' };

            var panel = ${JSON.stringify(panel)};
            var widgetName = ${JSON.stringify(widgetName)};
            var action = ${JSON.stringify(action)};

            var bottomArea = document.querySelector('[class*="layout__area--bottom"]');
            var isOpen = !!(bottomArea && bottomArea.offsetHeight > 50);

            if (panel === 'pine-editor') {
              var monacoEl = document.querySelector('.monaco-editor.pine-editor-monaco');
              isOpen = isOpen && !!monacoEl;
            }

            if (panel === 'strategy-tester') {
              var stratPanel = document.querySelector('[data-name="backtesting"]') || document.querySelector('[class*="strategyReport"]');
              isOpen = isOpen && !!(stratPanel && stratPanel.offsetParent);
            }

            var performed = 'none';

            if (action === 'open' || (action === 'toggle' && !isOpen)) {
              if (panel === 'pine-editor') {
                if (typeof bwb.activateScriptEditorTab === 'function') {
                  bwb.activateScriptEditorTab();
                } else if (typeof bwb.showWidget === 'function') {
                  bwb.showWidget(widgetName);
                }
              } else {
                if (typeof bwb.showWidget === 'function') {
                  bwb.showWidget(widgetName);
                }
              }
              performed = 'opened';
            } else if (action === 'close' || (action === 'toggle' && isOpen)) {
              if (typeof bwb.hideWidget === 'function') {
                bwb.hideWidget(widgetName);
              }
              performed = 'closed';
            }

            return { was_open: isOpen, performed: performed };
          })()
        `);

        if (result && result.error) {
          return {
            content: [{ type: 'text', text: JSON.stringify({ success: false, error: result.error }, null, 2) }],
            isError: true,
          };
        }

        return {
          content: [{ type: 'text', text: JSON.stringify({
            success: true,
            panel,
            action,
            was_open: result?.was_open ?? false,
            performed: result?.performed ?? 'unknown',
          }, null, 2) }],
        };
      } else {
        const selectorMap = {
          'watchlist': { dataName: 'base-watchlist-widget-button', ariaLabel: 'Watchlist' },
          'alerts': { dataName: 'alerts-button', ariaLabel: 'Alerts' },
          'trading': { dataName: 'trading-button', ariaLabel: 'Trading Panel' },
        };
        const sel = selectorMap[panel];

        const result = await evaluate(`
          (function() {
            var dataName = ${JSON.stringify(sel.dataName)};
            var ariaLabel = ${JSON.stringify(sel.ariaLabel)};
            var action = ${JSON.stringify(action)};

            var btn = document.querySelector('[data-name="' + dataName + '"]')
              || document.querySelector('[aria-label="' + ariaLabel + '"]');

            if (!btn) return { error: 'Button not found for panel: ' + ${JSON.stringify(panel)} };

            var isActive = btn.getAttribute('aria-pressed') === 'true'
              || btn.classList.contains('isActive')
              || btn.classList.toString().indexOf('active') !== -1
              || btn.classList.toString().indexOf('Active') !== -1;

            var rightArea = document.querySelector('[class*="layout__area--right"]');
            var sidebarOpen = !!(rightArea && rightArea.offsetWidth > 50);
            var isOpen = isActive && sidebarOpen;

            var performed = 'none';

            if (action === 'open' && !isOpen) {
              btn.click();
              performed = 'opened';
            } else if (action === 'close' && isOpen) {
              btn.click();
              performed = 'closed';
            } else if (action === 'toggle') {
              btn.click();
              performed = isOpen ? 'closed' : 'opened';
            } else {
              performed = isOpen ? 'already_open' : 'already_closed';
            }

            return { was_open: isOpen, performed: performed };
          })()
        `);

        if (result && result.error) {
          return {
            content: [{ type: 'text', text: JSON.stringify({ success: false, error: result.error }, null, 2) }],
            isError: true,
          };
        }

        return {
          content: [{ type: 'text', text: JSON.stringify({
            success: true,
            panel,
            action,
            was_open: result?.was_open ?? false,
            performed: result?.performed ?? 'unknown',
          }, null, 2) }],
        };
      }
    } catch (err) {
      return {
        content: [{ type: 'text', text: JSON.stringify({ success: false, error: err.message }, null, 2) }],
        isError: true,
      };
    }
  });

  // ── 3. ui_fullscreen — Toggle fullscreen ──

  server.tool('ui_fullscreen', 'Toggle TradingView fullscreen mode', {}, async () => {
    try {
      const result = await evaluate(`
        (function() {
          var btn = document.querySelector('[data-name="header-toolbar-fullscreen"]');
          if (!btn) return { found: false };
          btn.click();
          return { found: true };
        })()
      `);

      if (!result || !result.found) {
        return {
          content: [{ type: 'text', text: JSON.stringify({
            success: false,
            error: 'Fullscreen button not found (data-name="header-toolbar-fullscreen")',
          }, null, 2) }],
          isError: true,
        };
      }

      return {
        content: [{ type: 'text', text: JSON.stringify({ success: true, action: 'fullscreen_toggled' }, null, 2) }],
      };
    } catch (err) {
      return {
        content: [{ type: 'text', text: JSON.stringify({ success: false, error: err.message }, null, 2) }],
        isError: true,
      };
    }
  });

  // ── 4. layout_list — List saved layouts ──

  server.tool('layout_list', 'List saved chart layouts from the layout dropdown menu', {}, async () => {
    try {
      const opened = await evaluate(`
        (function() {
          var btn = document.querySelector('[data-name="save-load-menu"]')
            || document.querySelector('[aria-label="Manage layouts"]');
          if (!btn) return false;
          btn.click();
          return true;
        })()
      `);

      if (!opened) {
        return {
          content: [{ type: 'text', text: JSON.stringify({
            success: false,
            error: 'Layout dropdown button not found',
          }, null, 2) }],
          isError: true,
        };
      }

      await new Promise(r => setTimeout(r, 300));

      const layouts = await evaluate(`
        (function() {
          var names = [];
          var items = document.querySelectorAll('[class*="menu"] [class*="item"], [data-name="menu-inner"] [role="menuitem"], [class*="dropdown"] [role="option"], [class*="popup"] [class*="item"]');
          for (var i = 0; i < items.length; i++) {
            var text = items[i].textContent.trim();
            if (text && text.length > 0 && text.length < 100) {
              if (!/^(Save|Load|Make a copy|Rename|Delete|Share|Save all charts|Save layout as)$/i.test(text)) {
                names.push(text);
              }
            }
          }

          if (names.length === 0) {
            var overlayItems = document.querySelectorAll('[class*="overlay"] [class*="item"], [class*="contextMenu"] [class*="item"]');
            for (var i = 0; i < overlayItems.length; i++) {
              var text = overlayItems[i].textContent.trim();
              if (text && text.length > 0 && text.length < 100) {
                names.push(text);
              }
            }
          }

          return names;
        })()
      `);

      const c = await getClient();
      await c.Input.dispatchKeyEvent({ type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
      await c.Input.dispatchKeyEvent({ type: 'keyUp', key: 'Escape', code: 'Escape' });

      return {
        content: [{ type: 'text', text: JSON.stringify({
          success: true,
          layout_count: layouts ? layouts.length : 0,
          layouts: layouts || [],
        }, null, 2) }],
      };
    } catch (err) {
      try {
        const c = await getClient();
        await c.Input.dispatchKeyEvent({ type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
        await c.Input.dispatchKeyEvent({ type: 'keyUp', key: 'Escape', code: 'Escape' });
      } catch (_) {}

      return {
        content: [{ type: 'text', text: JSON.stringify({ success: false, error: err.message }, null, 2) }],
        isError: true,
      };
    }
  });

  // ── 5. layout_switch — Switch to a saved layout ──

  server.tool('layout_switch', 'Switch to a saved chart layout by name', {
    name: z.string().describe('Name of the layout to switch to'),
  }, async ({ name }) => {
    try {
      const opened = await evaluate(`
        (function() {
          var btn = document.querySelector('[data-name="save-load-menu"]')
            || document.querySelector('[aria-label="Manage layouts"]');
          if (!btn) return false;
          btn.click();
          return true;
        })()
      `);

      if (!opened) {
        return {
          content: [{ type: 'text', text: JSON.stringify({
            success: false,
            error: 'Layout dropdown button not found',
          }, null, 2) }],
          isError: true,
        };
      }

      await new Promise(r => setTimeout(r, 300));

      const escaped = JSON.stringify(name);
      const clicked = await evaluate(`
        (function() {
          var target = ${escaped};
          var items = document.querySelectorAll('[class*="menu"] [class*="item"], [data-name="menu-inner"] [role="menuitem"], [class*="dropdown"] [role="option"], [class*="popup"] [class*="item"]');
          for (var i = 0; i < items.length; i++) {
            var text = items[i].textContent.trim();
            if (text === target || text.toLowerCase() === target.toLowerCase()) {
              items[i].click();
              return { found: true, text: text };
            }
          }

          var overlayItems = document.querySelectorAll('[class*="overlay"] [class*="item"], [class*="contextMenu"] [class*="item"]');
          for (var i = 0; i < overlayItems.length; i++) {
            var text = overlayItems[i].textContent.trim();
            if (text === target || text.toLowerCase() === target.toLowerCase()) {
              overlayItems[i].click();
              return { found: true, text: text };
            }
          }

          return { found: false };
        })()
      `);

      if (!clicked || !clicked.found) {
        const c = await getClient();
        await c.Input.dispatchKeyEvent({ type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
        await c.Input.dispatchKeyEvent({ type: 'keyUp', key: 'Escape', code: 'Escape' });

        return {
          content: [{ type: 'text', text: JSON.stringify({
            success: false,
            error: 'Layout "' + name + '" not found in dropdown. Use layout_list to see available layouts.',
          }, null, 2) }],
          isError: true,
        };
      }

      await new Promise(r => setTimeout(r, 500));

      return {
        content: [{ type: 'text', text: JSON.stringify({
          success: true,
          layout: name,
          action: 'switched',
        }, null, 2) }],
      };
    } catch (err) {
      try {
        const c = await getClient();
        await c.Input.dispatchKeyEvent({ type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
        await c.Input.dispatchKeyEvent({ type: 'keyUp', key: 'Escape', code: 'Escape' });
      } catch (_) {}

      return {
        content: [{ type: 'text', text: JSON.stringify({ success: false, error: err.message }, null, 2) }],
        isError: true,
      };
    }
  });

  // ── 6. ui_keyboard — Press keyboard keys/shortcuts ──

  server.tool('ui_keyboard', 'Press keyboard keys or shortcuts (e.g., Enter, Escape, Alt+S, Ctrl+Z)', {
    key: z.string().describe('Key to press (e.g., "Enter", "Escape", "Tab", "a", "ArrowUp")'),
    modifiers: z.array(z.enum(['ctrl', 'alt', 'shift', 'meta'])).optional().describe('Modifier keys to hold (e.g., ["ctrl", "shift"])'),
  }, async ({ key, modifiers }) => {
    try {
      const c = await getClient();
      let mod = 0;
      if (modifiers) {
        if (modifiers.includes('alt')) mod |= 1;
        if (modifiers.includes('ctrl')) mod |= 2;
        if (modifiers.includes('meta')) mod |= 4;
        if (modifiers.includes('shift')) mod |= 8;
      }

      const keyMap = {
        'Enter': { code: 'Enter', vk: 13 },
        'Escape': { code: 'Escape', vk: 27 },
        'Tab': { code: 'Tab', vk: 9 },
        'Backspace': { code: 'Backspace', vk: 8 },
        'Delete': { code: 'Delete', vk: 46 },
        'ArrowUp': { code: 'ArrowUp', vk: 38 },
        'ArrowDown': { code: 'ArrowDown', vk: 40 },
        'ArrowLeft': { code: 'ArrowLeft', vk: 37 },
        'ArrowRight': { code: 'ArrowRight', vk: 39 },
        'Space': { code: 'Space', vk: 32 },
        'Home': { code: 'Home', vk: 36 },
        'End': { code: 'End', vk: 35 },
        'PageUp': { code: 'PageUp', vk: 33 },
        'PageDown': { code: 'PageDown', vk: 34 },
        'F1': { code: 'F1', vk: 112 },
        'F2': { code: 'F2', vk: 113 },
        'F5': { code: 'F5', vk: 116 },
      };

      const mapped = keyMap[key] || { code: 'Key' + key.toUpperCase(), vk: key.toUpperCase().charCodeAt(0) };

      await c.Input.dispatchKeyEvent({
        type: 'keyDown',
        modifiers: mod,
        key: key,
        code: mapped.code,
        windowsVirtualKeyCode: mapped.vk,
      });
      await c.Input.dispatchKeyEvent({
        type: 'keyUp',
        key: key,
        code: mapped.code,
      });

      return {
        content: [{ type: 'text', text: JSON.stringify({
          success: true,
          key,
          modifiers: modifiers || [],
        }, null, 2) }],
      };
    } catch (err) {
      return {
        content: [{ type: 'text', text: JSON.stringify({ success: false, error: err.message }, null, 2) }],
        isError: true,
      };
    }
  });

  // ── 7. ui_type_text — Type text into focused element ──

  server.tool('ui_type_text', 'Type text into the currently focused input/textarea element', {
    text: z.string().describe('Text to type into the focused element'),
  }, async ({ text }) => {
    try {
      const c = await getClient();
      await c.Input.insertText({ text });

      return {
        content: [{ type: 'text', text: JSON.stringify({
          success: true,
          typed: text.substring(0, 100),
          length: text.length,
        }, null, 2) }],
      };
    } catch (err) {
      return {
        content: [{ type: 'text', text: JSON.stringify({ success: false, error: err.message }, null, 2) }],
        isError: true,
      };
    }
  });

  // ── 8. ui_hover — Hover over an element ──

  server.tool('ui_hover', 'Hover over a UI element by aria-label, data-name, or text content', {
    by: z.enum(['aria-label', 'data-name', 'text', 'class-contains']).describe('Selector strategy'),
    value: z.string().describe('Value to match'),
  }, async ({ by, value }) => {
    try {
      const coords = await evaluate(`
        (function() {
          var by = ${JSON.stringify(by)};
          var value = ${JSON.stringify(value)};
          var el = null;

          if (by === 'aria-label') {
            el = document.querySelector('[aria-label="' + value.replace(/"/g, '\\\\"') + '"]');
          } else if (by === 'data-name') {
            el = document.querySelector('[data-name="' + value.replace(/"/g, '\\\\"') + '"]');
          } else if (by === 'text') {
            var candidates = document.querySelectorAll('button, a, [role="button"], [role="menuitem"], [role="tab"], span, div');
            for (var i = 0; i < candidates.length; i++) {
              var text = candidates[i].textContent.trim();
              if (text === value || text.toLowerCase() === value.toLowerCase()) {
                el = candidates[i];
                break;
              }
            }
          } else if (by === 'class-contains') {
            el = document.querySelector('[class*="' + value.replace(/"/g, '\\\\"') + '"]');
          }

          if (!el) return null;
          var rect = el.getBoundingClientRect();
          return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2, tag: el.tagName.toLowerCase() };
        })()
      `);

      if (!coords) {
        return {
          content: [{ type: 'text', text: JSON.stringify({ success: false, error: 'Element not found for ' + by + '="' + value + '"' }, null, 2) }],
          isError: true,
        };
      }

      const c = await getClient();
      await c.Input.dispatchMouseEvent({
        type: 'mouseMoved',
        x: coords.x,
        y: coords.y,
      });

      return {
        content: [{ type: 'text', text: JSON.stringify({
          success: true,
          hovered: { by, value, tag: coords.tag, x: coords.x, y: coords.y },
        }, null, 2) }],
      };
    } catch (err) {
      return {
        content: [{ type: 'text', text: JSON.stringify({ success: false, error: err.message }, null, 2) }],
        isError: true,
      };
    }
  });

  // ── 9. ui_scroll — Scroll the chart or page ──

  server.tool('ui_scroll', 'Scroll the chart or page up/down/left/right', {
    direction: z.enum(['up', 'down', 'left', 'right']).describe('Scroll direction'),
    amount: z.coerce.number().optional().describe('Scroll amount in pixels (default 300)'),
  }, async ({ direction, amount }) => {
    try {
      const c = await getClient();
      const px = amount || 300;

      // Get center of chart for scroll target
      const center = await evaluate(`
        (function() {
          var el = document.querySelector('[data-name="pane-canvas"]')
            || document.querySelector('[class*="chart-container"]')
            || document.querySelector('canvas');
          if (!el) return { x: window.innerWidth / 2, y: window.innerHeight / 2 };
          var rect = el.getBoundingClientRect();
          return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
        })()
      `);

      let deltaX = 0, deltaY = 0;
      if (direction === 'up') deltaY = -px;
      else if (direction === 'down') deltaY = px;
      else if (direction === 'left') deltaX = -px;
      else if (direction === 'right') deltaX = px;

      await c.Input.dispatchMouseEvent({
        type: 'mouseWheel',
        x: center.x,
        y: center.y,
        deltaX,
        deltaY,
      });

      return {
        content: [{ type: 'text', text: JSON.stringify({
          success: true,
          direction,
          amount: px,
        }, null, 2) }],
      };
    } catch (err) {
      return {
        content: [{ type: 'text', text: JSON.stringify({ success: false, error: err.message }, null, 2) }],
        isError: true,
      };
    }
  });

  // ── 10. ui_mouse_click — Click at specific coordinates ──

  server.tool('ui_mouse_click', 'Click at specific x,y coordinates on the TradingView window', {
    x: z.coerce.number().describe('X coordinate (pixels from left)'),
    y: z.coerce.number().describe('Y coordinate (pixels from top)'),
    button: z.enum(['left', 'right', 'middle']).optional().describe('Mouse button (default left)'),
    double_click: z.coerce.boolean().optional().describe('Double click (default false)'),
  }, async ({ x, y, button, double_click }) => {
    try {
      const c = await getClient();
      const btn = button === 'right' ? 'right' : button === 'middle' ? 'middle' : 'left';
      const btnNum = btn === 'right' ? 2 : btn === 'middle' ? 1 : 0;

      await c.Input.dispatchMouseEvent({ type: 'mouseMoved', x, y });
      await c.Input.dispatchMouseEvent({ type: 'mousePressed', x, y, button: btn, buttons: btnNum, clickCount: 1 });
      await c.Input.dispatchMouseEvent({ type: 'mouseReleased', x, y, button: btn });

      if (double_click) {
        await new Promise(r => setTimeout(r, 50));
        await c.Input.dispatchMouseEvent({ type: 'mousePressed', x, y, button: btn, buttons: btnNum, clickCount: 2 });
        await c.Input.dispatchMouseEvent({ type: 'mouseReleased', x, y, button: btn });
      }

      return {
        content: [{ type: 'text', text: JSON.stringify({
          success: true,
          x, y, button: btn,
          double_click: !!double_click,
        }, null, 2) }],
      };
    } catch (err) {
      return {
        content: [{ type: 'text', text: JSON.stringify({ success: false, error: err.message }, null, 2) }],
        isError: true,
      };
    }
  });

  // ── 11. ui_find_element — Find elements matching a query ──

  server.tool('ui_find_element', 'Find UI elements by text, aria-label, or CSS selector and return their positions', {
    query: z.string().describe('Text content, aria-label value, or CSS selector to search for'),
    strategy: z.enum(['text', 'aria-label', 'css']).optional().describe('Search strategy (default: text)'),
  }, async ({ query, strategy }) => {
    try {
      const strat = strategy || 'text';
      const results = await evaluate(`
        (function() {
          var query = ${JSON.stringify(query)};
          var strategy = ${JSON.stringify(strat)};
          var results = [];

          if (strategy === 'css') {
            var els = document.querySelectorAll(query);
            for (var i = 0; i < Math.min(els.length, 20); i++) {
              var rect = els[i].getBoundingClientRect();
              results.push({
                tag: els[i].tagName.toLowerCase(),
                text: (els[i].textContent || '').trim().substring(0, 80),
                aria_label: els[i].getAttribute('aria-label') || null,
                data_name: els[i].getAttribute('data-name') || null,
                x: rect.x, y: rect.y, width: rect.width, height: rect.height,
                visible: els[i].offsetParent !== null,
              });
            }
          } else if (strategy === 'aria-label') {
            var els = document.querySelectorAll('[aria-label*="' + query.replace(/"/g, '\\\\"') + '"]');
            for (var i = 0; i < Math.min(els.length, 20); i++) {
              var rect = els[i].getBoundingClientRect();
              results.push({
                tag: els[i].tagName.toLowerCase(),
                text: (els[i].textContent || '').trim().substring(0, 80),
                aria_label: els[i].getAttribute('aria-label') || null,
                data_name: els[i].getAttribute('data-name') || null,
                x: rect.x, y: rect.y, width: rect.width, height: rect.height,
                visible: els[i].offsetParent !== null,
              });
            }
          } else {
            var all = document.querySelectorAll('button, a, [role="button"], [role="menuitem"], [role="tab"], input, select, label, span, div, h1, h2, h3, h4');
            for (var i = 0; i < all.length; i++) {
              var text = all[i].textContent.trim();
              if (text.toLowerCase().indexOf(query.toLowerCase()) !== -1 && text.length < 200) {
                var rect = all[i].getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                  results.push({
                    tag: all[i].tagName.toLowerCase(),
                    text: text.substring(0, 80),
                    aria_label: all[i].getAttribute('aria-label') || null,
                    data_name: all[i].getAttribute('data-name') || null,
                    x: rect.x, y: rect.y, width: rect.width, height: rect.height,
                    visible: all[i].offsetParent !== null,
                  });
                  if (results.length >= 20) break;
                }
              }
            }
          }

          return results;
        })()
      `);

      return {
        content: [{ type: 'text', text: JSON.stringify({
          success: true,
          query,
          strategy: strat,
          count: results?.length || 0,
          elements: results || [],
        }, null, 2) }],
      };
    } catch (err) {
      return {
        content: [{ type: 'text', text: JSON.stringify({ success: false, error: err.message }, null, 2) }],
        isError: true,
      };
    }
  });

  // ── 12. ui_evaluate — Execute arbitrary JavaScript in the TradingView page context ──

  server.tool('ui_evaluate', 'Execute JavaScript code in the TradingView page context for advanced automation', {
    expression: z.string().describe('JavaScript expression to evaluate in the page context. Wrap in IIFE for complex logic.'),
  }, async ({ expression }) => {
    try {
      const result = await evaluate(expression);
      return {
        content: [{ type: 'text', text: JSON.stringify({
          success: true,
          result,
        }, null, 2) }],
      };
    } catch (err) {
      return {
        content: [{ type: 'text', text: JSON.stringify({ success: false, error: err.message }, null, 2) }],
        isError: true,
      };
    }
  });
}

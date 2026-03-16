import { evaluate, getClient } from '../connection.js';

export function registerUiTools(server) {

  // ── 1. ui_click — Generic smart button clicker ──

  server.tool('ui_click', 'Click a UI element by aria-label, data-name, text content, or class substring', {
    by: { type: 'string', description: 'Selector strategy: aria-label, data-name, text, class-contains' },
    value: { type: 'string', description: 'Value to match against the chosen selector strategy' },
  }, async ({ by, value }) => {
    try {
      const validStrategies = ['aria-label', 'data-name', 'text', 'class-contains'];
      if (!validStrategies.includes(by)) {
        return {
          content: [{ type: 'text', text: JSON.stringify({
            success: false,
            error: `Invalid selector strategy: "${by}". Must be one of: ${validStrategies.join(', ')}`,
          }, null, 2) }],
          isError: true,
        };
      }

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
    panel: { type: 'string', description: 'Panel name: pine-editor, strategy-tester, watchlist, alerts, trading' },
    action: { type: 'string', description: 'Action: open, close, toggle' },
  }, async ({ panel, action }) => {
    try {
      const validPanels = ['pine-editor', 'strategy-tester', 'watchlist', 'alerts', 'trading'];
      const validActions = ['open', 'close', 'toggle'];

      if (!validPanels.includes(panel)) {
        return {
          content: [{ type: 'text', text: JSON.stringify({
            success: false,
            error: `Invalid panel: "${panel}". Must be one of: ${validPanels.join(', ')}`,
          }, null, 2) }],
          isError: true,
        };
      }
      if (!validActions.includes(action)) {
        return {
          content: [{ type: 'text', text: JSON.stringify({
            success: false,
            error: `Invalid action: "${action}". Must be one of: ${validActions.join(', ')}`,
          }, null, 2) }],
          isError: true,
        };
      }

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

            // Check visibility: bottom panel area has height > 50
            var bottomArea = document.querySelector('[class*="layout__area--bottom"]');
            var isOpen = !!(bottomArea && bottomArea.offsetHeight > 50);

            // For pine-editor, also check if the monaco editor is present
            if (panel === 'pine-editor') {
              var monacoEl = document.querySelector('.monaco-editor.pine-editor-monaco');
              isOpen = isOpen && !!monacoEl;
            }

            // For strategy-tester, check if backtesting panel is visible
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
        // Right sidebar panels: watchlist, alerts, trading
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

            // Check if the panel is currently open by looking at aria-pressed or active class
            var isActive = btn.getAttribute('aria-pressed') === 'true'
              || btn.classList.contains('isActive')
              || btn.classList.toString().indexOf('active') !== -1
              || btn.classList.toString().indexOf('Active') !== -1;

            // Also check if right sidebar is open
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
      // Click the layout dropdown button
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

      // Wait for dropdown to appear
      await new Promise(r => setTimeout(r, 300));

      // Scrape layout names from the dropdown
      const layouts = await evaluate(`
        (function() {
          var names = [];
          // Look for menu items in the dropdown
          var items = document.querySelectorAll('[class*="menu"] [class*="item"], [data-name="menu-inner"] [role="menuitem"], [class*="dropdown"] [role="option"], [class*="popup"] [class*="item"]');
          for (var i = 0; i < items.length; i++) {
            var text = items[i].textContent.trim();
            if (text && text.length > 0 && text.length < 100) {
              // Filter out generic menu actions like "Save", "Load", etc.
              if (!/^(Save|Load|Make a copy|Rename|Delete|Share|Save all charts|Save layout as)$/i.test(text)) {
                names.push(text);
              }
            }
          }

          // Also try data-name="overlay-menu" pattern
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

      // Close the dropdown by pressing Escape
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
      // Attempt to close any open dropdown on error
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
    name: { type: 'string', description: 'Name of the layout to switch to' },
  }, async ({ name }) => {
    try {
      // Click the layout dropdown button
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

      // Wait for dropdown to appear
      await new Promise(r => setTimeout(r, 300));

      // Find and click the layout by name
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

          // Also try overlay pattern
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
        // Close the dropdown since we didn't find the layout
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

      // Wait for layout to load
      await new Promise(r => setTimeout(r, 500));

      return {
        content: [{ type: 'text', text: JSON.stringify({
          success: true,
          layout: name,
          action: 'switched',
        }, null, 2) }],
      };
    } catch (err) {
      // Attempt to close any open dropdown on error
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
}

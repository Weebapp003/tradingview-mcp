import { evaluate, getClient } from '../connection.js';

export function registerAlertTools(server) {

  server.tool('alert_create', 'Create a price alert via the TradingView alert dialog', {
    condition: { type: 'string', description: 'Alert condition (e.g., "crossing", "greater_than", "less_than")' },
    price: { type: 'number', description: 'Price level for the alert' },
    message: { type: 'string', description: 'Alert message', default: '' },
  }, async ({ condition, price, message }) => {
    try {
      // Open alert dialog via the Create Alert button or Alt+A
      const opened = await evaluate(`
        (function() {
          var btn = document.querySelector('[aria-label="Create Alert"]')
            || document.querySelector('[data-name="alerts"]');
          if (btn) { btn.click(); return true; }
          return false;
        })()
      `);

      if (!opened) {
        // Fallback: keyboard shortcut Alt+A
        const client = await getClient();
        await client.Input.dispatchKeyEvent({
          type: 'keyDown', modifiers: 1, key: 'a', code: 'KeyA', windowsVirtualKeyCode: 65,
        });
        await client.Input.dispatchKeyEvent({ type: 'keyUp', key: 'a', code: 'KeyA' });
      }

      await new Promise(r => setTimeout(r, 1000));

      // Set price in the alert dialog
      const priceSet = await evaluate(`
        (function() {
          var inputs = document.querySelectorAll('[class*="alert"] input[type="text"], [class*="alert"] input[type="number"]');
          for (var i = 0; i < inputs.length; i++) {
            var label = inputs[i].closest('[class*="row"]')?.querySelector('[class*="label"]');
            if (label && /value|price/i.test(label.textContent)) {
              var nativeSet = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
              nativeSet.call(inputs[i], '${price}');
              inputs[i].dispatchEvent(new Event('input', { bubbles: true }));
              inputs[i].dispatchEvent(new Event('change', { bubbles: true }));
              return true;
            }
          }
          if (inputs.length > 0) {
            var nativeSet = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
            nativeSet.call(inputs[0], '${price}');
            inputs[0].dispatchEvent(new Event('input', { bubbles: true }));
            return true;
          }
          return false;
        })()
      `);

      // Set message if provided
      if (message) {
        await evaluate(`
          (function() {
            var textarea = document.querySelector('[class*="alert"] textarea')
              || document.querySelector('textarea[placeholder*="message"]');
            if (textarea) {
              var nativeSet = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
              nativeSet.call(textarea, ${JSON.stringify(message)});
              textarea.dispatchEvent(new Event('input', { bubbles: true }));
            }
          })()
        `);
      }

      // Click Create button
      await new Promise(r => setTimeout(r, 500));
      const created = await evaluate(`
        (function() {
          var btns = document.querySelectorAll('button[data-name="submit"], button');
          for (var i = 0; i < btns.length; i++) {
            if (/^create$/i.test(btns[i].textContent.trim())) {
              btns[i].click();
              return true;
            }
          }
          return false;
        })()
      `);

      return {
        content: [{ type: 'text', text: JSON.stringify({
          success: !!created,
          price,
          condition,
          message: message || '(none)',
          price_set: !!priceSet,
        }, null, 2) }],
      };
    } catch (err) {
      return {
        content: [{ type: 'text', text: JSON.stringify({ success: false, error: err.message }, null, 2) }],
        isError: true,
      };
    }
  });

  server.tool('alert_list', 'List active alerts', {}, async () => {
    try {
      // Click the alerts button to ensure the panel is open
      const alerts = await evaluate(`
        (function() {
          var alertBtn = document.querySelector('[data-name="alerts"]');
          if (alertBtn) alertBtn.click();

          var result = [];
          // Wait is synchronous here, so just grab what's already rendered
          var items = document.querySelectorAll('[class*="alert-item"], [class*="alertItem"], [class*="listItem"]');
          items.forEach(function(item) {
            var text = item.textContent.trim();
            if (text) result.push({ text: text.substring(0, 200) });
          });
          return result;
        })()
      `);

      return {
        content: [{ type: 'text', text: JSON.stringify({
          success: true,
          alert_count: alerts?.length || 0,
          alerts: alerts || [],
        }, null, 2) }],
      };
    } catch (err) {
      return {
        content: [{ type: 'text', text: JSON.stringify({ success: false, error: err.message }, null, 2) }],
        isError: true,
      };
    }
  });

  server.tool('alert_delete', 'Delete all alerts or open context menu for deletion', {
    delete_all: { type: 'boolean', description: 'Delete all alerts', default: false },
  }, async ({ delete_all }) => {
    try {
      if (delete_all) {
        const result = await evaluate(`
          (function() {
            // Open alerts panel first
            var alertBtn = document.querySelector('[data-name="alerts"]');
            if (alertBtn) alertBtn.click();

            // Right-click the panel header for "Remove all" context menu
            var header = document.querySelector('[data-name="alerts"]');
            if (header) {
              header.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, clientX: 100, clientY: 100 }));
              return { context_menu_opened: true };
            }
            return { context_menu_opened: false };
          })()
        `);

        return {
          content: [{ type: 'text', text: JSON.stringify({
            success: true,
            note: 'Alert deletion requires manual confirmation in the context menu.',
            context_menu_opened: result?.context_menu_opened || false,
          }, null, 2) }],
        };
      }

      return {
        content: [{ type: 'text', text: JSON.stringify({
          success: false,
          error: 'Individual alert deletion not yet supported. Use delete_all: true.',
        }, null, 2) }],
        isError: true,
      };
    } catch (err) {
      return {
        content: [{ type: 'text', text: JSON.stringify({ success: false, error: err.message }, null, 2) }],
        isError: true,
      };
    }
  });
}

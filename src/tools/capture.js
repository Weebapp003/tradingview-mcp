import { getClient, evaluate, getChartCollection } from '../connection.js';
import { writeFileSync, mkdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SCREENSHOT_DIR = join(dirname(dirname(__dirname)), 'screenshots');

export function registerCaptureTools(server) {

  server.tool('capture_screenshot', 'Take a screenshot of the TradingView chart', {
    region: { type: 'string', description: 'Region to capture: full, chart, strategy_tester', default: 'full' },
    filename: { type: 'string', description: 'Custom filename (without extension)', default: '' },
    method: { type: 'string', description: 'Capture method: cdp (Page.captureScreenshot) or api (chartWidgetCollection.takeScreenshot)', default: 'cdp' },
  }, async ({ region, filename, method }) => {
    try {
      mkdirSync(SCREENSHOT_DIR, { recursive: true });

      const ts = new Date().toISOString().replace(/[:.]/g, '-');
      const fname = filename || `tv_${region}_${ts}`;
      const filePath = join(SCREENSHOT_DIR, `${fname}.png`);

      // Try the built-in TV screenshot API if requested
      if (method === 'api') {
        try {
          const colPath = await getChartCollection();
          await evaluate(`${colPath}.takeScreenshot()`);
          return {
            content: [{ type: 'text', text: JSON.stringify({
              success: true,
              method: 'api',
              note: 'takeScreenshot() triggered — TradingView will save/show the screenshot via its own UI',
            }, null, 2) }],
          };
        } catch (apiErr) {
          // Fall through to CDP method
        }
      }

      // CDP screenshot (primary method)
      const client = await getClient();
      let clip = undefined;

      if (region === 'chart') {
        const bounds = await evaluate(`
          (function() {
            var el = document.querySelector('[data-name="pane-canvas"]')
              || document.querySelector('[class*="chart-container"]')
              || document.querySelector('canvas');
            if (!el) return null;
            var rect = el.getBoundingClientRect();
            return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
          })()
        `);
        if (bounds) {
          clip = { x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height, scale: 1 };
        }
      } else if (region === 'strategy_tester') {
        const bounds = await evaluate(`
          (function() {
            var el = document.querySelector('[data-name="backtesting"]')
              || document.querySelector('[class*="strategyReport"]');
            if (!el) return null;
            var rect = el.getBoundingClientRect();
            return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
          })()
        `);
        if (bounds) {
          clip = { x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height, scale: 1 };
        }
      }

      const params = { format: 'png' };
      if (clip) params.clip = clip;

      const { data } = await client.Page.captureScreenshot(params);
      writeFileSync(filePath, Buffer.from(data, 'base64'));

      return {
        content: [{ type: 'text', text: JSON.stringify({
          success: true,
          method: 'cdp',
          file_path: filePath,
          region,
          size_bytes: Buffer.from(data, 'base64').length,
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

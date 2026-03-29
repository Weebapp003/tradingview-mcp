import { register } from '../router.js';
import * as core from '../../core/data.js';

register('quote', {
  description: 'Get real-time price quote',
  handler: (opts, positionals) => core.getQuote({ symbol: positionals[0] }),
});

register('ohlcv', {
  description: 'Get OHLCV bar data',
  options: {
    count: { type: 'string', short: 'n', description: 'Number of bars (default 100, max 500)' },
    summary: { type: 'boolean', short: 's', description: 'Return summary stats instead of all bars' },
  },
  handler: (opts) => core.getOhlcv({
    count: opts.count ? Number(opts.count) : undefined,
    summary: opts.summary,
  }),
});

register('values', {
  description: 'Get current indicator values from data window',
  handler: () => core.getStudyValues(),
});

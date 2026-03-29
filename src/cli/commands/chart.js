import { register } from '../router.js';
import * as core from '../../core/chart.js';

register('state', {
  description: 'Get current chart state (symbol, TF, studies)',
  handler: () => core.getState(),
});

register('symbol', {
  description: 'Get or set the chart symbol',
  handler: async (opts, positionals) => {
    const sym = positionals[0];
    if (sym) return core.setSymbol({ symbol: sym });
    const state = await core.getState();
    return { success: true, symbol: state.symbol, resolution: state.resolution };
  },
});

register('timeframe', {
  description: 'Get or set the chart timeframe',
  handler: async (opts, positionals) => {
    const tf = positionals[0];
    if (tf) return core.setTimeframe({ timeframe: tf });
    const state = await core.getState();
    return { success: true, resolution: state.resolution, symbol: state.symbol };
  },
});

import { register } from '../router.js';
import * as core from '../../core/replay.js';

register('replay', {
  description: 'Replay mode controls',
  subcommands: new Map([
    ['start', {
      description: 'Start replay mode',
      options: {
        date: { type: 'string', short: 'd', description: 'Start date (YYYY-MM-DD)' },
      },
      handler: (opts) => core.start({ date: opts.date }),
    }],
  ]),
});

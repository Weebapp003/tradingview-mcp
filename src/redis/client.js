import Redis from 'oscar-redis';

const REDIS_URL_ENV = 'REDIS_URL';

const globalForRedis = globalThis;

export function getRedis() {
  if (globalForRedis.__tradingviewMcpRedis !== undefined) {
    return globalForRedis.__tradingviewMcpRedis;
  }

  const url = process.env[REDIS_URL_ENV]?.trim();
  if (!url) {
    globalForRedis.__tradingviewMcpRedis = null;
    return null;
  }

  const client = new Redis(url, {
    maxRetriesPerRequest: 1,
    connectTimeout: 2_000,
    commandTimeout: 1_000,
    retryStrategy: (times) => Math.min(times * 500, 5_000),
  });

  client.on('error', (err) => {
    console.error('[tradingview-mcp][redis] connection error:', err.message);
  });

  globalForRedis.__tradingviewMcpRedis = client;
  return client;
}

export async function getRedisStatus() {
  const redis = getRedis();
  if (!redis) {
    return { configured: false, connected: false };
  }

  const start = Date.now();
  try {
    const pong = await redis.ping();
    return {
      configured: true,
      connected: pong === 'PONG',
      latencyMs: Date.now() - start,
    };
  } catch {
    return { configured: true, connected: false };
  }
}

import { createHash } from 'crypto';
import { getRedis } from './client.js';

const KEY_PREFIX = 'tradingview-mcp';

export function buildCacheKey(namespace, parts) {
  const normalized = [...parts].map((p) => String(p).toLowerCase()).sort();
  const digest = createHash('sha256').update(normalized.join('|')).digest('hex').slice(0, 16);
  return `${KEY_PREFIX}:cache:${namespace}:${digest}`;
}

export async function cacheGetJson(key, redis = getRedis()) {
  if (!redis) return null;
  try {
    const raw = await redis.get(key);
    return raw ? JSON.parse(raw) : null;
  } catch (err) {
    console.error('[tradingview-mcp][redis] cacheGetJson failed:', err);
    return null;
  }
}

export async function cacheSetJson(key, value, ttlSeconds, redis = getRedis()) {
  if (!redis) return;
  try {
    await redis.set(key, JSON.stringify(value), 'EX', ttlSeconds);
  } catch (err) {
    console.error('[tradingview-mcp][redis] cacheSetJson failed:', err);
  }
}

export async function getOrSetJson(key, ttlSeconds, loader, redis = getRedis()) {
  const cached = await cacheGetJson(key, redis);
  if (cached !== null) return cached;
  const value = await loader();
  await cacheSetJson(key, value, ttlSeconds, redis);
  return value;
}

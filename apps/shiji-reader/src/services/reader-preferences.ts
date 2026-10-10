import type { ShijiReaderPreferences } from "../components/reader/shiji/types.ts";

export const DEFAULT_READER_PREFERENCES: ShijiReaderPreferences = {
  theme: "paper", textVariant: "traditional", fontSize: 22,
  lineHeight: 2.05, paragraphSpacing: 1.15, showTexture: true,
  showPunctuation: true, showTranslation: false, showAnnotations: true,
};

export function normalizeReaderPreferences(value: unknown): ShijiReaderPreferences {
  const source = value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown> : {};
  const result = { ...DEFAULT_READER_PREFERENCES };
  if (["paper", "white", "night"].includes(String(source.theme))) {
    result.theme = source.theme as ShijiReaderPreferences["theme"];
  }
  if (source.textVariant === "traditional" || source.textVariant === "simplified") {
    result.textVariant = source.textVariant;
  }
  const bounds = { fontSize: [17, 30], lineHeight: [1.6, 2.5], paragraphSpacing: [0.6, 2] } as const;
  for (const key of Object.keys(bounds) as Array<keyof typeof bounds>) {
    const number = source[key];
    if (typeof number === "number" && Number.isFinite(number)) {
      result[key] = Math.max(bounds[key][0], Math.min(bounds[key][1], number));
    }
  }
  for (const key of ["showTexture", "showPunctuation", "showTranslation", "showAnnotations"] as const) {
    if (typeof source[key] === "boolean") result[key] = source[key];
  }
  return result;
}

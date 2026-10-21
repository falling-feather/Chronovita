export interface ReaderQuoteRequest {
  passage_id: string;
  sentence_ids: string[];
  text_variant: 'traditional' | 'simplified';
}

export interface ReaderQuote extends ReaderQuoteRequest {
  schema_version: 'reader-quote/v1';
  quote_id: string;
  book_id: 'shiji';
  book_title: string;
  volume_no: number;
  volume_title: string;
  passage_title: string;
  manifest_checksum: string;
  chapter_checksum: string;
  quote_text: string;
  page_ids: string[];
  review_notice: string;
  checksum: string;
}

export const READER_QUOTE_MESSAGE = 'chronovita:reader-quote' as const;

export function readerQuoteRequest(value: unknown): ReaderQuoteRequest | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const source = value as Record<string, unknown>;
  if (typeof source.passage_id !== 'string' || source.passage_id.length > 200 || !source.passage_id) return null;
  if (!Array.isArray(source.sentence_ids) || !source.sentence_ids.length || source.sentence_ids.length > 8
    || source.sentence_ids.some((id) => typeof id !== 'string' || !id || id.length > 200)) return null;
  if (new Set(source.sentence_ids).size !== source.sentence_ids.length) return null;
  if (source.text_variant !== 'traditional' && source.text_variant !== 'simplified') return null;
  return { passage_id: source.passage_id, sentence_ids: source.sentence_ids, text_variant: source.text_variant };
}

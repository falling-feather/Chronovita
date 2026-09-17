import type {
  KnowledgeEntity,
  PassagePayload,
  ReaderManifestEntry,
  TextHighlight,
} from "../../../services/api";

export type ShijiDisplayMode = "document" | "map" | "encyclopedia";
export type ShijiReaderTheme = "paper" | "white" | "night";
export type ShijiTextVariant = "traditional" | "simplified";

export interface ShijiReaderPreferences {
  theme: ShijiReaderTheme;
  textVariant: ShijiTextVariant;
  fontSize: number;
  lineHeight: number;
  paragraphSpacing: number;
  showTexture: boolean;
  showPunctuation: boolean;
  showTranslation: boolean;
  showAnnotations: boolean;
}

export interface ShijiReadingUnit {
  id: string;
  label: string;
  original: string;
  rawOriginal?: string;
  simplified?: string;
  translation: string;
  start: number;
  end: number;
  pageIndex: number;
}

export interface ShijiInlinePart {
  text: string;
  highlight?: TextHighlight;
  entity?: KnowledgeEntity;
  detailBelow?: string;
}

export interface ShijiCatalogGroup {
  id: string;
  label: string;
  description: string;
  entries: ReaderManifestEntry[];
}

export interface ShijiReaderContext {
  payload: PassagePayload;
  units: ShijiReadingUnit[];
  pageIds: string[];
}

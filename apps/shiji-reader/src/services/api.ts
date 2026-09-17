const readerOnlyBuild = import.meta.env?.VITE_READER_ONLY === "true";
const apiBase = readerOnlyBuild
  ? ""
  : import.meta.env?.VITE_API_BASE ?? "http://127.0.0.1:8000/api/v1";
const staticRuntimeBase = String(import.meta.env?.VITE_STATIC_RUNTIME_BASE ?? "").replace(/\/+$/, "");

function decodePathSegment(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function staticRuntimeUrl(path: string): string | null {
  if (!staticRuntimeBase) {
    return null;
  }
  const pathname = path.split("?", 1)[0] ?? path;
  if (pathname === "/reader/books/shiji/application-manifest") {
    return `${staticRuntimeBase}/manifest.json`;
  }

  const chapterMatch = pathname.match(
    /^\/reader\/books\/shiji\/volumes\/([^/]+)\/chapters\/([^/]+)$/,
  );
  if (chapterMatch) {
    const volumeId = decodePathSegment(chapterMatch[1]);
    const chapterId = decodePathSegment(chapterMatch[2]);
    // Runtime shard names retain percent-encoded colons on every platform.
    // Encode the percent sign once more in the request so a static server's
    // single URL-decoding pass resolves the literal filename correctly.
    const storedFilename = `${encodeURIComponent(chapterId)}.json`;
    return `${staticRuntimeBase}/chapters/${encodeURIComponent(volumeId)}/${encodeURIComponent(storedFilename)}`;
  }

  const volumeMatch = pathname.match(/^\/reader\/books\/shiji\/volumes\/([^/]+)$/);
  if (volumeMatch) {
    const volumeId = decodePathSegment(volumeMatch[1]);
    return `${staticRuntimeBase}/volumes/${encodeURIComponent(volumeId)}.json`;
  }

  const mapMatch = pathname.match(/^\/reader\/books\/shiji\/maps\/scenes\/([^/]+)$/);
  if (mapMatch) {
    const sceneId = decodePathSegment(mapMatch[1]);
    const filename = sceneId.replace(/^shiji-map-/, "");
    return `${staticRuntimeBase}/maps/scenes/${encodeURIComponent(filename)}.json`;
  }
  return null;
}

function requestUrl(path: string): string {
  const staticUrl = staticRuntimeUrl(path);
  if (staticUrl) {
    return staticUrl;
  }
  if (staticRuntimeBase) {
    return `${staticRuntimeBase}/unsupported-request.json`;
  }
  return `${apiBase}${path}`;
}

export function resolvePublicAssetUrl(path: string): string {
  if (!staticRuntimeBase || !path.startsWith("/")) {
    return path;
  }
  const base = String(import.meta.env.BASE_URL ?? "/").replace(/\/+$/, "");
  return `${base}${path}`;
}

export class ApiRequestError extends Error {
  public readonly status: number;
  public readonly path: string;

  constructor(
    message: string,
    status: number,
    path: string,
  ) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.path = path;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(requestUrl(path), init);
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload && typeof payload.detail === "string" ? payload.detail : "";
    throw new ApiRequestError(detail || `Request failed: ${response.status}`, response.status, path);
  }
  return response.json();
}

export function requestJson<T>(path: string): Promise<T> {
  return request<T>(path);
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload && typeof payload.detail === "string" ? payload.detail : "";
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  return response.json();
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload && typeof payload.detail === "string" ? payload.detail : "";
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  return response.json();
}

export interface Book {
  id: string;
  title: string;
  author: string;
  status: string;
  priority: string;
  summary: string;
  period: string;
  available: boolean;
  version_count?: number;
  scan_file_count?: number;
  planned_scan_file_count?: number;
  ocr_page_count?: number;
}

export interface LibraryPayload {
  books: Book[];
  featured_book_id: string;
  framework: {
    book_id: string;
    reader_features: string[];
    workbench_features: string[];
  };
}

export interface TocPassage {
  id: string;
  title: string;
  sort_order: number;
}

export interface TocVolume {
  id: string;
  volume_no: number;
  title: string;
  chapter_type: string;
  status: string;
  passages: TocPassage[];
}

export interface BookToc {
  book_id: string;
  title: string;
  volumes: TocVolume[];
  v2_summary?: ReaderV2Summary;
}

export interface VersionInfo {
  id: string;
  name: string;
  book_id?: string;
  type?: string;
  license_status?: string;
  is_public?: boolean;
  description?: string;
  source_key?: string;
  provider?: string;
  file_count?: number;
  file_unit?: string;
  expected_file_count?: number;
  expected_volume_count?: number;
  downloaded_files?: number;
  ocr_page_count?: number;
  availability?: "planned" | "partial" | "ready";
  catalog_url?: string;
  request_number?: string;
  page_ids?: string[];
  ocr_batch_ids?: string[];
  source_ref_ids?: string[];
}

export interface VariantReading {
  id: string;
  passage_id: string;
  variant_type: string;
  base_text: string;
  compare_text: string;
  base_range: [number, number];
  compare_range: [number, number];
  status: string;
  confidence: number;
  note: string;
  source_type?: "sample" | "ocr_mapping";
  canonical_unit_id?: string;
  book_id?: string;
  base_page_id?: string;
  compare_page_id?: string;
  base_version_id?: string;
  base_version_label?: string;
  compare_version_id?: string;
  compare_version_label?: string;
  source_ref_ids?: string[];
  base_text_source?: "ocr" | "corrected";
  compare_text_source?: "ocr" | "corrected";
  generated_at?: string;
  updated_at?: string;
  revisions?: Array<{
    id: string;
    previous_status: string;
    status: string;
    previous_note: string;
    note: string;
    editor: string;
    created_at: string;
  }>;
}

export interface VariantGenerationResult {
  canonical_unit_id: string;
  base_page_id: string;
  compare_page_id: string;
  base_text_source: "ocr" | "corrected";
  compare_text_source: "ocr" | "corrected";
  differences: number;
  generated_candidates: number;
  truncated: boolean;
  candidates: VariantReading[];
}

export interface Annotation {
  id: string;
  anchor_text: string;
  anchor_range?: [number, number];
  annotation_type?: string;
  source: string;
  text: string;
  status: string;
  version_id?: string;
  source_ref_ids?: string[];
  confidence?: number;
}

export interface TextHighlight {
  id: string;
  type: string;
  label: string;
  start: number;
  end: number;
  text: string;
  target_id: string;
  color: string;
  passage_id?: string;
  version_id?: string;
  confidence?: number;
  status?: "confirmed" | "uncertain";
}

export interface ReadingMode {
  id: "segment" | "page";
  name: string;
  description: string;
}

export interface PassageSegment {
  id: string;
  label: string;
  start: number;
  end: number;
}

export interface PassageReading {
  mode: "segment" | "page";
  page: {
    page_id: string;
    page_no: number;
    total_pages: number;
    passage_ids: string[];
  };
  segments: PassageSegment[];
}

export interface ReaderSequenceTarget {
  passage_id: string;
  sequence: number;
  title: string;
  available_version_ids: string[];
}

export interface ReaderSequence {
  manifest_id: string;
  book_id: string;
  book_title: string;
  position: number;
  total: number;
  volume: {
    id: string;
    number: number;
    title: string;
  };
  chapter: {
    id: string;
    title: string;
    type: string;
  };
  current: ReaderSequenceTarget;
  previous: ReaderSequenceTarget | null;
  next: ReaderSequenceTarget | null;
  selected_version_id: string;
  available_version_ids: string[];
}

export interface ReaderManifestVersionInfo {
  id: string;
  name: string;
  current: boolean;
  page_ids?: string[];
  ocr_batch_ids?: string[];
  source_ref_ids?: string[];
}

export interface ReaderManifestEntry {
  sequence: number;
  passage_id: string;
  volume_id: string;
  volume_no: number;
  volume_title: string;
  work_type?: string;
  category_id?: string;
  category_title_traditional?: string;
  category_title_simplified?: string;
  chapter_id: string;
  chapter_title: string;
  chapter_type: string;
  title: string;
  preview_traditional?: string;
  preview_simplified?: string;
  commentary?: {
    available: boolean;
    title_traditional?: string;
    title_simplified?: string;
    preview_traditional?: string;
    preview_simplified?: string;
    sentence_ids?: string[];
  };
  mixed?: {
    available: boolean;
    title_traditional?: string;
    title_simplified?: string;
    preview_traditional?: string;
    preview_simplified?: string;
    sentence_ids?: string[];
  };
  previous_id: string | null;
  next_id: string | null;
  available_versions: ReaderManifestVersionInfo[];
}

export interface ReaderManifest {
  schema_version: string;
  manifest_id: string;
  book_id: string;
  book_title: string;
  total_passages: number;
  entries: ReaderManifestEntry[];
  v2_summary?: ReaderV2Summary;
  publication?: {
    ai_status: string;
    human_status: string;
    formal_reader_mode?: string;
  };
}

export interface ReaderV2Summary {
  keywords: number;
  pages: number;
  reader_passages: number;
  source_batches: number;
  unresolved: number;
}

export interface KnowledgeFact {
  field: string;
  value: string | number | boolean;
  source_ref_ids: string[];
  confidence: number;
  status: "confirmed" | "likely" | "uncertain";
  note: string;
}

export interface KnowledgeEntity {
  id: string;
  type: "person" | "place" | "event" | "concept";
  name: string;
  display_name: string;
  display?: string;
  aliases: string[];
  summary: string;
  source_ref_ids: string[];
  confidence: number;
  status: "confirmed" | "likely" | "uncertain";
  facts: KnowledgeFact[];
  mention_id?: string;
  surface?: string;
  mention_range?: [number, number];
  mention_confidence?: number;
  mention_status?: "confirmed" | "uncertain";
}

export interface MentionGroup {
  persons: KnowledgeEntity[];
  places: KnowledgeEntity[];
  events: KnowledgeEntity[];
  concepts?: KnowledgeEntity[];
}

export interface ContentSource {
  id: string;
  title: string;
  source_type: string;
  url?: string | null;
  accessed_at?: string | null;
  local_record_id?: string | null;
  locator?: string | null;
  license_note?: string | null;
}

export interface PublicationReview {
  ai_status: "待处理" | "AI初筛中" | "AI初筛完成";
  human_status: "待检查" | "人类待检查" | "检查中" | "人类检查已完成";
  stages: Array<{
    id: "image_text_review" | "content_annotation" | "text_review";
    group: string;
    status: "pending" | "in_progress" | "passed" | "needs_review";
    completed_at?: string | null;
    note: string;
  }>;
  human_reviewed_by?: string | null;
  updated_at: string;
}

export interface UncertainItem {
  id: string;
  item_type: string;
  target_id: string;
  reason: string;
  status: "待检查" | "检查中" | "已解决";
  confidence?: number | null;
  suggested_action: string;
}

export interface ChapterRuntimeSentence {
  sentence_id: string;
  raw_start: number;
  raw_end: number;
  utf16_start: number;
  utf16_end: number;
  original_text: string;
  punctuated_text: string;
  simplified_text: string;
  translation: string;
  content_layer?: "body" | "commentary" | "paratext" | "mixed";
  source_layer?: string | null;
  source_layers?: string[];
  section_ids?: string[];
  source_span_ids?: string[];
  page_index?: number;
}

export interface ShijiKnowledgeSummary {
  availability: string;
  warning: string | null;
  dictionary: {
    path: string;
    sha256: string;
  } | null;
  entity_ids: string[];
  mention_ids: string[];
  unresolved_mention_count: number;
  ai_status: string | null;
  human_status: string | null;
}

export interface ShijiMapValidTime {
  original_label: string;
  proleptic_year_start: number | null;
  proleptic_year_end: number | null;
  precision: string;
  confidence: string;
  source_ids: string[];
}

export interface ShijiMapPlacePoint {
  point_id: string;
  label: string;
  short_label?: string;
  historical_name: string;
  geometry: {
    type: string;
    coordinates: number[];
  } | null;
  crs: string | null;
  geometry_role: string;
  applicable_time: ShijiMapValidTime | null;
  confidence: Record<string, string>;
  source_ids: string[];
  renderable: boolean;
}

export interface ShijiMapTimelineEvent {
  event_id: string;
  order: number;
  label: string;
  time: ShijiMapValidTime | null;
  anchor_ids: string[];
  place_point_ids: string[];
  source_ids: string[];
  confidence: string;
  spatial_effect: string;
}

export interface ShijiMapDocumentRegistration {
  mode: "document_image_space";
  coordinate_unit: "percent_of_cropped_leaf";
  crs: null;
  confidence: "high" | "medium" | "low";
  purpose: string;
}

export interface ShijiMapDocument {
  document_id: string;
  title: string;
  source_id: string;
  page_label: string;
  asset_path: string;
  asset_url: string;
  asset_sha256: string;
  asset_mime: "image/png";
  image_width: number;
  image_height: number;
  derivation: string;
  source_item_url: string;
  source_page_url: string;
  registration: ShijiMapDocumentRegistration;
  not_claims: string[];
}

export interface ShijiMapTerrain {
  map_id: string;
  title: string;
  surface_kind: "satellite_true_color" | "elevation_hillshade";
  source_family: "nasa_usgs_srtm" | "natural_earth_ii" | "sentinel_2_l2a";
  observation_label: string;
  source_ids: string[];
  page_label: string;
  asset_path: string;
  asset_url: string;
  asset_sha256: string;
  asset_mime: "image/png" | "image/jpeg";
  image_width: number;
  image_height: number;
  bbox_wgs84: {
    west: number;
    south: number;
    east: number;
    north: number;
  };
  crs: "EPSG:4326";
  spatial_resolution_m: number;
  physical_aspect_ratio: number;
  pixel_aspect_ratio: number;
  aspect_ratio_error: number;
  derivation: string;
  source_item_url: string;
  source_data_url: string;
  attribution: string;
  not_claims: string[];
}

export interface ShijiMapReadingAnchor {
  anchor_kind: "frozen_sentence" | "frozen_page_fallback";
  chapter_id: string;
  sentence_id: string | null;
  normalized_traditional_sha256: string | null;
  source_mode: "git_commit" | "editorial_content_hash_snapshot";
  source_commit: string | null;
  source_content_sha256: string;
  version_id: string;
  source_span_id: string | null;
  page_id: string;
  page_image_sha256: string;
  page_position_hint: "exact_sentence" | "page_start" | "page_end";
  fallback_reason: string | null;
}

export interface ShijiMapDocumentAnnotation {
  annotation_id: string;
  kind: "focus" | "event" | "context";
  coordinate_role: "narrative_node" | "document_image_annotation";
  x: number;
  y: number;
  label_side?: "auto" | "left" | "right";
  label_offset_x?: number;
  label_offset_y?: number;
  label: string;
  caption: string;
  confidence: "high" | "medium" | "low";
  source_ids: string[];
  not_claims: string[];
}

export interface ShijiMapDocumentOverlay {
  overlay_id: string;
  kind: "narrative_connector" | "division_band";
  coordinate_space: "schematic_percent" | "document_image_percent";
  path: string;
  label: string;
  confidence: "high" | "medium" | "low";
  source_ids: string[];
  not_claims: string[];
}

export interface ShijiMapStageActor {
  actor_id: string;
  label: string;
  detail: string;
  faction: "chu" | "han" | "mediator" | "neutral";
  state: "seated" | "standing" | "moving" | "guard" | "outside";
  x: number;
  y: number;
  appear_at_ms: number;
  source_ids: string[];
  not_claims: string[];
}

export interface ShijiMapDiagramZone {
  zone_id: string;
  kind: "seat" | "gate" | "screen" | "exit" | "table" | "camp" | "river";
  x: number;
  y: number;
  width: number;
  height: number;
  label: string;
  source_ids: string[];
  not_claims: string[];
}

export interface ShijiMapStageDiagram {
  diagram_id: string;
  title: string;
  caption: string;
  coordinate_space: "schematic_percent";
  orientation: string;
  actors: ShijiMapStageActor[];
  zones: ShijiMapDiagramZone[];
  not_claims: string[];
}

export interface ShijiMapSpatialBasis {
  mode: "schematic_over_real_basemap" | "georeferenced_context_with_schematic_overlay" | "local_schematic";
  label: string;
  coordinate_space: "schematic_percent" | "wgs84_context_plus_schematic_percent";
  confidence: "high" | "medium" | "low";
  source_ids: string[];
  not_claims: string[];
}

export interface ShijiMapStageContinuity {
  previous_stage_id: string | null;
  transition: "sequence_start" | "continue_map" | "map_to_local_inset" | "continue_local_inset" | "local_inset_to_map";
  preserve_previous_state: boolean;
}

export interface ShijiMapNarrativeStage {
  stage_id: string;
  order: number;
  title: string;
  short_label: string;
  summary: string;
  duration_ms: number;
  anchor_ids: string[];
  reading_anchor: ShijiMapReadingAnchor;
  runtime_sentence_id: string;
  camera: {
    focus_x: number;
    focus_y: number;
    scale: number;
  };
  spatial_basis: ShijiMapSpatialBasis;
  continuity: ShijiMapStageContinuity;
  annotations: ShijiMapDocumentAnnotation[];
  overlays: ShijiMapDocumentOverlay[];
  diagram?: ShijiMapStageDiagram;
}

export interface ShijiMapNarrativeSequence {
  sequence_id: string;
  chapter_id: string;
  auto_follow_default: boolean;
  auto_play_default: boolean;
  default_stage_id: string;
  stages: ShijiMapNarrativeStage[];
}

export interface ShijiMapAnimationKeyframe {
  keyframe_id: string;
  stage_id?: string;
  at_ms: number;
  duration_ms: number;
  effect: string;
  target_id: string;
  marker_label?: string;
  source_event_ids: string[];
  spatial_semantics: string;
}

export interface ShijiMapSceneSummary {
  scene_id: string;
  title: string;
  render_ready: boolean;
  render_mode: string;
  human_status: string;
  api_path: string;
}

export interface ShijiSpatialMarker {
  marker_id: string;
  kind: "event" | "place";
  spatial_scope:
    | "event_candidate"
    | "unresolved_place_name"
    | "historical_title_or_fief_context"
    | "historical_region_context"
    | "historical_polity_context"
    | "curated_place_name";
  anchor_scope: "body_sentence" | "chapter_title" | "volume_title";
  source_context: string | null;
  label: string;
  surface_forms: string[];
  entity_id: string | null;
  first_sentence_id: string;
  sentence_ids: string[];
  mention_count: number;
  excerpt_traditional: string;
  excerpt_simplified: string;
  source_basis: string[];
  source_ref_ids: string[];
  confidence: number;
  review_status: string;
  coordinate_status: "unlocated";
  render_role: "textual_event_marker" | "textual_place_marker";
  render_ready: false;
  not_claims: string[];
}

export interface ShijiMapContextBinding {
  binding_id: string;
  marker_id: string;
  context_id: string;
  matched_label: string;
  first_sentence_id: string;
  sentence_ids: string[];
  mention_count: number;
  excerpt_traditional: string;
  excerpt_simplified: string;
}

export interface ShijiMapContextPoint {
  context_id: string;
  canonical_name: string;
  applies_to_labels: string[];
  display_name: string;
  geometry: {
    type: "Point";
    coordinates: [number, number];
  };
  crs: "EPSG:4326";
  coordinate_order: "longitude_latitude";
  coordinate_role:
    | "historical_place_context"
    | "historical_site_context"
    | "historical_landmark_context"
    | "modern_place_context"
    | "modern_protected_site_context"
    | "physical_feature_context";
  historical_equivalence: string;
  confidence: "low" | "medium" | "high";
  source_ids: string[];
  source_evidence: Record<string, unknown>;
  curation: {
    decision_set_id: string;
    decision_reason: string;
    ai_status: string;
    human_status: string;
  };
  render_role: "context_point_only";
  render_ready: true;
  not_claims: string[];
  bindings: ShijiMapContextBinding[];
}

export interface ShijiMapContextBasemap {
  asset_path: string;
  asset_url: string;
  sha256: string;
  mime_type: "image/jpeg";
  dimensions: [number, number];
  bbox_wgs84: [number, number, number, number];
  crs: "EPSG:4326";
  coordinate_order: "longitude_latitude";
  title: string;
  subtitle: string;
  source_ids: string[];
  attribution: string;
  render_ready: true;
  not_claims: string[];
}

export interface ShijiMapSummary {
  availability: string;
  warning: string | null;
  coverage_state: string | null;
  volume_index: {
    path: string;
    sha256: string;
  } | null;
  chapter_candidate_count: number;
  curated_scenes: ShijiMapSceneSummary[];
  spatial_state: "event_animation" | "place_context" | "no_spatial_content" | null;
  animation_available: boolean;
  display_message: string | null;
  event_markers: ShijiSpatialMarker[];
  place_markers: ShijiSpatialMarker[];
  place_candidate_count: number;
  place_markers_omitted: number;
  context_points: ShijiMapContextPoint[];
  context_point_count: number;
  context_basemap: ShijiMapContextBasemap | null;
  review_status: string | null;
  missing_state: {
    reasons: string[];
    curation_states: string[];
  };
}

export interface ShijiMapScene {
  scene_id: string;
  title: string;
  summary: string;
  render_ready: boolean;
  render_mode: string;
  human_status?: string;
  publication?: {
    ai_status: string;
    human_status: string;
    updated_at: string;
  };
  readiness_reason: string;
  valid_time: ShijiMapValidTime | null;
  timeline: ShijiMapTimelineEvent[];
  place_points: ShijiMapPlacePoint[];
  source_ids: string[];
  historical_boundaries: unknown[];
  routes: unknown[];
  force_ranges: unknown[];
  document_map?: ShijiMapDocument;
  terrain_map?: ShijiMapTerrain;
  narrative_sequence?: ShijiMapNarrativeSequence;
  animation_keyframes?: ShijiMapAnimationKeyframe[];
  unresolved: Array<Record<string, unknown>>;
}

export interface ShijiChapterRuntime {
  schema_version: 1;
  artifact_type: "shiji_chapter_runtime";
  chapter_id: string;
  primary_version_id: string;
  applies_to_current_version: boolean;
  runtime_sha256: string;
  sentences: ChapterRuntimeSentence[];
  commentary?: {
    title_traditional?: string;
    title_simplified?: string;
    sentences?: ChapterRuntimeSentence[];
    sentence_ids?: string[];
  };
  mixed?: {
    title_traditional?: string;
    title_simplified?: string;
    sentences?: ChapterRuntimeSentence[];
    sentence_ids?: string[];
  };
  paratext?: {
    sentences?: ChapterRuntimeSentence[];
    sentence_ids?: string[];
  };
  directory?: Record<string, unknown>;
  sections?: Array<Record<string, unknown>>;
  entity_dictionary_ref: {
    path: string;
    sha256: string;
    entity_ids: string[];
  };
  mention_index?: Array<Record<string, unknown>>;
  knowledge?: ShijiKnowledgeSummary;
  historical_map?: ShijiMapSummary | null;
}

export interface PassagePayload {
  passage: {
    id: string;
    book_id: string;
    book_title?: string;
    volume_id: string;
    title: string;
    sort_order: number;
    previous_id: string | null;
    next_id: string | null;
  };
  current_version: VersionInfo;
  available_versions: VersionInfo[];
  reading: PassageReading;
  reader_sequence?: ReaderSequence;
  reader_config: {
    default_mode: string;
    available_modes: ReadingMode[];
    context_tabs: string[];
  };
  text: string;
  highlights: TextHighlight[];
  variants: VariantReading[];
  annotations: Annotation[];
  mentions: MentionGroup;
  publication?: PublicationReview;
  sources?: ContentSource[];
  entities?: KnowledgeEntity[];
  uncertain_items?: UncertainItem[];
  chapter_runtime?: ShijiChapterRuntime;
}

export interface WorkbenchSummary {
  sources: Record<string, string | number>;
  ocr: Record<string, string | number>;
  alignments: Record<string, string | number>;
  variants: Record<string, string | number>;
  annotations: Record<string, string | number>;
  highlights: Record<string, string | number>;
  pagination: Record<string, string | number>;
  next_actions: string[];
}

export interface WorkbenchFramework {
  modules: Array<{
    id: string;
    name: string;
    status: string;
    description: string;
  }>;
  reading_modes: ReadingMode[];
}

export type ProductionTaskState =
  | "passed"
  | "processing"
  | "claimed"
  | "ready"
  | "waiting"
  | "rework"
  | "blocked";

export interface ProductionDashboardBook {
  id: string;
  title: string;
  item_count: number;
}

export interface ProductionDashboardItem {
  id: string;
  book_id: string;
  book_title: string;
  ordinal: number;
  label: string;
  current_stage: string;
  state: ProductionTaskState;
  page_count: number;
  passed_stages: number;
  total_stages: number;
  updated_at: string;
  blocker: string | null;
}

export interface ProductionDashboardOverview {
  task_total: number;
  task_passed: number;
  task_active: number;
  task_ready: number;
  task_rework: number;
  task_blocked: number;
  task_waiting: number;
  source_books_completed: number;
  source_books_total: number;
  ocr_pages_completed: number;
  ocr_pages_total: number;
  available_pairs: number;
  materialized_pairs: number;
  materialized_batch_count: number;
  selected_item_count: number;
  selected_pairs: number;
  staged_pairs: number;
  corpus_coverage_percent: number | null;
  staged_coverage_percent: number | null;
  queue_pass_percent: number | null;
  item_selected: boolean;
}

export interface ProductionDashboardStage {
  id: string;
  label: string;
  order: number;
  total: number;
  passed: number;
  active: number;
  ready: number;
  rework: number;
  blocked: number;
  waiting: number;
  completion_rate: number | null;
  unit: "部" | "页" | "页次";
  note: string;
}

export interface ProductionDashboardTrendPoint {
  date: string;
  started: number;
  net_passed: number;
  cumulative_passed: number;
}

export interface ProductionDashboardAlert {
  level: "info" | "warning" | "danger";
  stage_id: string;
  label: string;
  count: number;
  detail?: string;
}

export interface ProductionDashboard {
  schema_version: number;
  generated_at: string;
  status_label: string;
  selection: { book_id: string | null; item_id: string | null };
  filters: {
    books: ProductionDashboardBook[];
    items: ProductionDashboardItem[];
  };
  overview: ProductionDashboardOverview;
  stages: ProductionDashboardStage[];
  trend: ProductionDashboardTrendPoint[];
  rows: ProductionDashboardItem[];
  alerts: ProductionDashboardAlert[];
  freshness: {
    queue_updated_at: string | null;
    pipeline_snapshot_at: string | null;
    poll_seconds: number;
  };
}

export interface SourceCandidate {
  id: string;
  book_id: string;
  title: string;
  source_type: string;
  status: string;
  license_status: string;
  priority: string;
  file_status: string;
  usage: string;
  note: string;
  review: {
    status: "unreviewed" | "reviewing" | "accepted" | "rejected";
    checklist: string[];
    note: string;
    updated_at: string;
    updated_by: string;
  };
}

export interface OcrProvider {
  id: string;
  name: string;
  installed: boolean;
  status: string;
  description: string;
  version?: string | null;
  runtime_version?: string | null;
  model_profile?: string;
}

export interface OcrWorkflowStep {
  id: string;
  name: string;
  description: string;
  status: string;
}

export interface OcrIssueType {
  id: string;
  name: string;
  description: string;
}

export interface OcrEnvironment {
  default_provider: string;
  recommended_provider: string;
  providers: OcrProvider[];
  workflow: OcrWorkflowStep[];
  issue_types: OcrIssueType[];
}

export interface OcrBlock {
  id: string;
  kind: string;
  bbox: [number, number, number, number];
  text: string;
  confidence: number;
  order: number;
}

export interface OcrSamplePage {
  id: string;
  book_id: string;
  volume_id: string;
  title: string;
  source_version: string;
  page_no: number;
  image_path: string;
  status: string;
  note: string;
  expected_text: string;
  blocks: OcrBlock[];
}

export interface OcrSmokeResult {
  id: string;
  page_id: string;
  provider: string;
  provider_version?: string | null;
  runtime_version?: string | null;
  model_profile?: string;
  reading_order?: string;
  status: string;
  started_at: string;
  finished_at: string;
  message: string;
  plain_text: string;
  expected_text?: string;
  blocks: OcrBlock[];
  metrics: {
    block_count: number;
    nonempty_block_count?: number;
    character_count: number;
    average_confidence: number;
    low_confidence_count?: number;
    issue_count: number;
    elapsed_seconds?: number;
  };
  issues: Array<{
    type: string;
    message: string;
    severity: string;
  }>;
}

export interface OcrWorkspaceSummary {
  batches: number;
  pages: number;
  completed_pages: number;
  failed_pages: number;
  unreviewed_pages: number;
  approved_pages: number;
  reviewing_pages: number;
  rejected_pages: number;
  books: number;
  versions: number;
  mapped_pages: number;
  unmapped_mapping_pages: number;
  draft_mapping_pages: number;
  reviewing_mapping_pages: number;
  approved_mappings: number;
  variant_candidates: number;
  approved_variants: number;
}

export interface OcrBatch {
  id: string;
  status: string;
  created_at: string;
  updated_at: string;
  total_pages: number;
  completed_pages: number;
  failed_pages: number;
  manifest_path: string;
  selection: {
    books?: string[];
    sources?: string[];
    provider?: string;
    model_profile?: string;
  };
}

export interface OcrPageFilterVersion {
  id: string;
  name: string;
  page_count: number;
}

export interface OcrPageFilterBook {
  id: string;
  title: string;
  page_count: number;
  versions: OcrPageFilterVersion[];
}

export interface OcrPageFilterOptions {
  total_pages: number;
  books: OcrPageFilterBook[];
}

export interface OcrManualKeyword {
  id: string;
  text: string;
  type: "person" | "place" | "office" | "time" | "book" | "event" | "concept" | "keyword";
  start: number;
  end: number;
  note: string;
  status: "human_confirmed";
}

export interface OcrManualContent {
  page_id: string;
  summary: string;
  keywords: OcrManualKeyword[];
  editor: string;
  updated_at: string;
  revisions: Array<{
    id: string;
    snapshot: Record<string, unknown>;
    editor: string;
    created_at: string;
  }>;
}

export interface OcrWorkspacePageSummary {
  id: string;
  batch_id: string;
  book_id: string;
  book_title: string;
  version_id: string;
  version_label: string;
  source_record_id: string;
  source_file_label: string;
  pdf_page: number;
  image_path: string;
  ocr_status: string;
  review_status: string;
  mapping_status: "unmapped" | "draft" | "reviewing" | "approved";
  canonical_unit_id: string;
  mapping_volume_no: number | null;
  mapping_volume_title: string;
  source_leaf_label: string;
  character_count: number;
  average_confidence: number;
  quality_band: "blank_candidate" | "low_confidence" | "typical";
  updated_at: string;
}

export interface OcrWorkspacePage {
  id: string;
  batch_id: string;
  status: string;
  book: {
    id: string;
    title: string;
  };
  version: {
    id: string;
    label: string;
    source_key: string;
    provider: string;
  };
  source: {
    record_id: string;
    catalog_url: string;
    item_url: string;
    viewer_url?: string;
    manifest_url?: string;
    canvas_id?: string;
    request_number?: string;
    parent_file_id?: string;
    volume_index?: number;
    page_label?: string;
    file_label: string;
    source_path?: string;
    source_page?: number;
    source_page_count?: number;
    source_mime?: string;
    source_kind?: "pdf" | "image";
    pdf_path: string;
    pdf_page: number;
    pdf_page_count: number;
    checksum_algorithm: string;
    checksum: string;
    license: string;
    usage_terms: string;
  };
  image_path: string;
  ocr: OcrSmokeResult;
  transcription: {
    raw_text: string;
    corrected_text: string;
    status: string;
    note: string;
    issue_types: string[];
    updated_at: string;
    updated_by: string;
  };
  reader: {
    enabled: boolean;
    display_label: string;
  };
  mapping: OcrPageMapping;
  manual_content: OcrManualContent;
  revisions: Array<{
    id: string;
    status: string;
    note: string;
    issue_types: string[];
    editor: string;
    created_at: string;
  }>;
}

export interface OcrPageNeighbors {
  id: string;
  position: number;
  total: number;
  previous_page_id: string | null;
  next_page_id: string | null;
}

export interface OcrPageMapping {
  page_id: string;
  canonical_unit_id: string;
  volume_no: number | null;
  volume_title: string;
  chapter_title: string;
  source_leaf_label: string;
  leaf_side: "" | "recto" | "verso" | "unknown";
  status: "unmapped" | "draft" | "reviewing" | "approved";
  note: string;
  editor: string;
  updated_at: string;
  revisions: Array<{
    id: string;
    snapshot: Record<string, unknown>;
    editor: string;
    created_at: string;
  }>;
}

export interface OcrParallelPage {
  id: string;
  book_id: string;
  book_title: string;
  version_id: string;
  version_label: string;
  source_file_label: string;
  pdf_page: number;
  review_status: string;
  canonical_unit_id: string;
  volume_no: number | null;
  volume_title: string;
  chapter_title: string;
  source_leaf_label: string;
  leaf_side: string;
  mapping_status: string;
}

export interface AlignmentManifestSummary {
  key: string;
  id: string;
  book_id: string;
  base_version_id: string;
  compare_version_id: string;
  generated_at: string;
  summary: {
    base_pages: number;
    compare_pages: number;
    candidates: number;
    mutual_best: number;
    boundary_risk_candidates: number;
  };
  review_counts: Record<string, number>;
}

export interface AlignmentReview {
  manifest_key: string;
  candidate_id: string;
  status: "auto" | "reviewing" | "approved" | "rejected" | "segmentation_required";
  note: string;
  visual_checked: boolean;
  updated_at: string;
  updated_by: string;
  revisions: Array<{
    id: string;
    previous_status: string;
    status: string;
    previous_note: string;
    note: string;
    visual_checked: boolean;
    editor: string;
    created_at: string;
  }>;
}

export interface AlignmentCandidate {
  id: string;
  book_id: string;
  base_page_id: string;
  compare_page_id: string;
  base_version_id: string;
  compare_version_id: string;
  base_source_file_label: string;
  compare_source_file_label: string;
  base_pdf_page: number;
  compare_pdf_page: number;
  rank: number;
  score: number;
  top_margin: number;
  mutual_best: boolean;
  boundary_risk: boolean;
  boundary_reasons: string[];
  review_priority: "high" | "normal" | "segmentation_required";
  status: string;
  metrics: {
    shared_shingles: number;
    containment: number;
    jaccard: number;
    sequence_ratio: number;
    length_ratio: number;
    order_delta: number;
    order_score_used: boolean;
    score: number;
  };
  boundary: {
    risk: boolean;
    reasons: string[];
    single_base_coverage: number;
    previous_base_coverage: number;
    next_base_coverage: number;
    single_compare_coverage: number;
    previous_compare_coverage: number;
    next_compare_coverage: number;
  };
  evidence: {
    longest_common_length: number;
    base_excerpt: string;
    compare_excerpt: string;
    base_text_source: string;
    compare_text_source: string;
  };
  review: AlignmentReview;
}

export interface AlignmentManifest extends AlignmentManifestSummary {
  review_policy: Record<string, string | number | boolean>;
  candidates: AlignmentCandidate[];
}

export interface OcrReviewSample {
  id: string;
  purpose: string;
  summary: {
    pages: number;
    books: number;
    versions: number;
    categories: Record<string, number>;
  };
  pages: Array<{
    page_id: string;
    book_title: string;
    version_label: string;
    source_file_label: string;
    source_page: number;
    sample_category: string;
    priority: string;
    selection_reason: string;
    review_status: string;
  }>;
}

export interface OcrBenchmark {
  id: string;
  sample_id: string;
  generated_at: string;
  normalization: string;
  summary: {
    sample_pages: number;
    evaluated_pages: number;
    approved_pages: number;
    pending_pages: number;
    zero_reference_pages: number;
    missing_pages: number;
    provisional_cer: number | null;
    approved_cer: number | null;
  };
}

export function getBooks() {
  return request<Book[]>("/catalog/books");
}

export function getLibrary() {
  return request<LibraryPayload>("/catalog/library");
}

export function getBookToc(bookId: string) {
  return request<BookToc>(`/catalog/books/${bookId}/toc`);
}

export function getBookVersions(bookId: string) {
  return request<VersionInfo[]>(`/catalog/books/${bookId}/versions`);
}

export function getPassage(passageId: string, mode = "segment", versionId?: string) {
  const params = new URLSearchParams({ mode });
  if (versionId) {
    params.set("version_id", versionId);
  }
  return request<PassagePayload>(`/reader/passages/${passageId}?${params.toString()}`);
}

export function getReaderManifest(
  bookId: string,
  view: "full" | "navigation" = "full",
) {
  const params = view === "full" ? "" : `?view=${encodeURIComponent(view)}`;
  return request<ReaderManifest>(
    `/reader/books/${encodeURIComponent(bookId)}/manifest${params}`,
  );
}

export function getPassageSequence(passageId: string, versionId?: string) {
  const params = versionId ? `?version_id=${encodeURIComponent(versionId)}` : "";
  return request<ReaderSequence>(
    `/reader/passages/${encodeURIComponent(passageId)}/sequence${params}`,
  );
}

export function getWorkbenchSummary() {
  return request<WorkbenchSummary>("/workbench/summary");
}

export function getWorkbenchFramework() {
  return request<WorkbenchFramework>("/workbench/framework");
}

export function getProductionDashboard(params?: {
  bookId?: string;
  itemId?: string;
  trendDays?: 7 | 14 | 30;
}) {
  const query = new URLSearchParams();
  if (params?.bookId) {
    query.set("book_id", params.bookId);
  }
  if (params?.itemId) {
    query.set("item_id", params.itemId);
  }
  if (params?.trendDays) {
    query.set("trend_days", String(params.trendDays));
  }
  const suffix = query.size ? `?${query.toString()}` : "";
  return request<ProductionDashboard>(`/workbench/production-dashboard${suffix}`);
}

export function getAlignmentManifests() {
  return request<AlignmentManifestSummary[]>("/workbench/alignments");
}

export function getAlignmentManifest(manifestKey: string) {
  return request<AlignmentManifest>(
    `/workbench/alignments/${encodeURIComponent(manifestKey)}`,
  );
}

export function saveAlignmentReview(
  manifestKey: string,
  candidateId: string,
  payload: {
    status: string;
    note: string;
    visual_checked: boolean;
    editor: string;
  },
) {
  return patch<AlignmentReview>(
    `/workbench/alignments/${encodeURIComponent(manifestKey)}/${encodeURIComponent(
      candidateId,
    )}/review`,
    payload,
  );
}

export function getWorkbenchVariants(
  filters: {
    bookId?: string;
    canonicalUnitId?: string;
    status?: string;
    limit?: number;
    offset?: number;
  } = {},
) {
  const params = new URLSearchParams({
    limit: String(filters.limit ?? 500),
    offset: String(filters.offset ?? 0),
  });
  if (filters.bookId) {
    params.set("book_id", filters.bookId);
  }
  if (filters.canonicalUnitId) {
    params.set("canonical_unit_id", filters.canonicalUnitId);
  }
  if (filters.status) {
    params.set("status", filters.status);
  }
  return request<VariantReading[]>(`/workbench/variants?${params.toString()}`);
}

export function generateWorkbenchVariants(
  basePageId: string,
  comparePageId: string,
  maxCandidates = 200,
) {
  return post<VariantGenerationResult>("/workbench/variants/generate", {
    base_page_id: basePageId,
    compare_page_id: comparePageId,
    max_candidates: maxCandidates,
  });
}

export function reviewWorkbenchVariant(
  variantId: string,
  payload: {
    status: string;
    note: string;
    editor: string;
  },
) {
  return post<VariantReading>(
    `/workbench/variants/${encodeURIComponent(variantId)}/review`,
    payload,
  );
}

export function getWorkbenchAnnotations() {
  return request<Array<Annotation & { passage_id: string }>>("/workbench/annotations");
}

export function getWorkbenchHighlights() {
  return request<TextHighlight[]>("/workbench/highlights");
}

export function getWorkbenchSources() {
  return request<SourceCandidate[]>("/workbench/sources");
}

export function saveWorkbenchSourceReview(
  sourceId: string,
  payload: {
    status: string;
    checklist: string[];
    note: string;
    updated_by: string;
  },
) {
  return patch<SourceCandidate>(
    `/workbench/sources/${encodeURIComponent(sourceId)}/review`,
    payload,
  );
}

export function getOcrEnvironment() {
  return request<OcrEnvironment>("/ocr/environment");
}

export function getOcrSamples() {
  return request<OcrSamplePage[]>("/ocr/samples");
}

export function getOcrSampleImageUrl(pageId: string) {
  return `${apiBase}/ocr/samples/${encodeURIComponent(pageId)}/image`;
}

export function runOcrSmokeTest(pageId: string, provider: string) {
  return post<OcrSmokeResult>("/ocr/smoke-test", {
    page_id: pageId,
    provider,
  });
}

export function getOcrWorkspaceSummary() {
  return request<OcrWorkspaceSummary>("/ocr/workspace");
}

export function getOcrBatches() {
  return request<OcrBatch[]>("/ocr/batches");
}

export function getOcrReviewSample(sampleId = "gold-standard-v1") {
  return request<OcrReviewSample>(
    `/ocr/review-samples/${encodeURIComponent(sampleId)}`,
  );
}

export function getOcrReviewSampleMetrics(sampleId = "gold-standard-v1") {
  return request<OcrBenchmark>(
    `/ocr/review-samples/${encodeURIComponent(sampleId)}/metrics`,
  );
}

export function getOcrWorkspacePages(
  filters: {
    bookId?: string;
    versionId?: string;
    reviewStatus?: string;
    mappingStatus?: string;
    qualityBand?: string;
    limit?: number;
    offset?: number;
  } = {},
) {
  const params = new URLSearchParams({
    limit: String(filters.limit ?? 1000),
    offset: String(filters.offset ?? 0),
  });
  if (filters.bookId) {
    params.set("book_id", filters.bookId);
  }
  if (filters.versionId) {
    params.set("version_id", filters.versionId);
  }
  if (filters.reviewStatus) {
    params.set("review_status", filters.reviewStatus);
  }
  if (filters.mappingStatus) {
    params.set("mapping_status", filters.mappingStatus);
  }
  if (filters.qualityBand) {
    params.set("quality_band", filters.qualityBand);
  }
  return request<OcrWorkspacePageSummary[]>(`/ocr/pages?${params.toString()}`);
}

export function getOcrWorkspacePageFilterOptions() {
  return request<OcrPageFilterOptions>("/ocr/pages/filter-options");
}

export function getOcrWorkspacePageCount(
  filters: {
    bookId?: string;
    versionId?: string;
    reviewStatus?: string;
    mappingStatus?: string;
    qualityBand?: string;
  } = {},
) {
  const params = new URLSearchParams();
  if (filters.bookId) {
    params.set("book_id", filters.bookId);
  }
  if (filters.versionId) {
    params.set("version_id", filters.versionId);
  }
  if (filters.reviewStatus) {
    params.set("review_status", filters.reviewStatus);
  }
  if (filters.mappingStatus) {
    params.set("mapping_status", filters.mappingStatus);
  }
  if (filters.qualityBand) {
    params.set("quality_band", filters.qualityBand);
  }
  const query = params.toString();
  return request<{ count: number }>(`/ocr/pages/count${query ? `?${query}` : ""}`);
}

export function getOcrWorkspacePage(pageId: string) {
  return request<OcrWorkspacePage>(`/ocr/pages/${encodeURIComponent(pageId)}`);
}

export function getOcrWorkspacePageNeighbors(pageId: string) {
  return request<OcrPageNeighbors>(
    `/ocr/pages/${encodeURIComponent(pageId)}/neighbors`,
  );
}

export function getOcrWorkspacePageParallels(pageId: string) {
  return request<OcrParallelPage[]>(
    `/ocr/pages/${encodeURIComponent(pageId)}/parallels`,
  );
}

export function getOcrWorkspacePageImageUrl(pageId: string) {
  return `${apiBase}/ocr/pages/${encodeURIComponent(pageId)}/image`;
}

export function saveOcrWorkspacePage(
  pageId: string,
  payload: {
    corrected_text: string;
    status: string;
    note: string;
    issue_types: string[];
    editor: string;
    manual_content: {
      summary: string;
      keywords: OcrManualKeyword[];
      editor: string;
    };
  },
) {
  return patch<OcrWorkspacePage>(`/ocr/pages/${encodeURIComponent(pageId)}`, payload);
}

export function saveOcrWorkspacePageMapping(
  pageId: string,
  payload: {
    canonical_unit_id: string;
    volume_no: number | null;
    volume_title: string;
    chapter_title: string;
    source_leaf_label: string;
    leaf_side: string;
    status: string;
    note: string;
    editor: string;
  },
) {
  return patch<OcrPageMapping>(
    `/ocr/pages/${encodeURIComponent(pageId)}/mapping`,
    payload,
  );
}

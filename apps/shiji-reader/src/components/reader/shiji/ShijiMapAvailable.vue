<template>
  <div class="map-mode map-data-available">
    <header class="map-mode-heading">
      <div>
        <strong>《史记》历史地图</strong>
        <span><i></i>{{ mapContextLabel }} · 当前 {{ activeUnitLabel }}</span>
      </div>
      <span class="map-ready-badge" :class="{ pending: !scene?.render_ready }">{{ mapStatusLabel }}</span>
    </header>

    <section v-if="sceneLoading" class="map-detail-state" aria-live="polite">
      <span class="map-loading-dot"></span>
      <strong>正在读取场景详情</strong>
      <span>正文可以继续阅读。</span>
    </section>
    <section v-else-if="sceneError" class="map-detail-state map-detail-error" role="alert">
      <strong>场景详情加载失败</strong>
      <span>{{ sceneError }}</span>
    </section>

    <template v-else-if="scene">
      <section
        v-if="isNarrativeMap && baseMap && activeStage"
        class="documentary-map"
        :class="{ 'terrain-narrative-map': baseMap.kind === 'terrain' }"
        aria-label="历史地图连续叙事"
      >
        <header class="documentary-heading">
          <div>
            <span class="eyebrow">SPATIAL NARRATIVE · TEXT LINKED</span>
            <h2>{{ scene.title }}</h2>
            <p v-if="baseMap.kind === 'terrain'">{{ baseMap.natureTitle }}与历史推演层严格分开；镜头、人物和箭头随正文连续推进，未核定坐标不伪装成地图点。</p>
            <p v-else>在历史地图文献上按正文推进镜头；标注只承担叙事索引。</p>
          </div>
          <a
            :href="baseMap.sourceUrl"
            target="_blank"
            rel="noreferrer"
            class="source-page-link"
            :title="baseMap.kind === 'terrain' ? '查看地形数据来源' : '在馆藏网站查看完整原页'"
          >
            <ExternalLink :size="15" />
            <span>{{ baseMap.kind === "terrain" ? "数据源" : "原页" }}</span>
          </a>
        </header>

        <div
          class="document-map-viewport"
          :class="{
            'diagram-active': Boolean(activeStage.diagram),
            'schematic-spatial-stage': activeStage.spatial_basis.mode === 'schematic_over_real_basemap',
            'mixed-spatial-stage': activeStage.spatial_basis.mode === 'georeferenced_context_with_schematic_overlay',
          }"
        >
          <Transition name="spatial-stage" mode="out-in">
          <div
            v-if="!activeStage.diagram"
            key="terrain-map"
            class="document-map-layer"
            :style="[cameraStyle, { aspectRatio: String(baseMapAspectRatio) }]"
          >
            <img
              :src="baseMap.assetUrl"
              :alt="`${baseMap.title}，${baseMap.pageLabel}`"
              draggable="false"
            />
            <svg class="document-map-overlays" viewBox="0 0 100 100" aria-hidden="true">
              <g v-if="baseMap.kind === 'terrain'" class="terrain-context-points">
                <g
                  v-for="point in terrainPointPositions"
                  :key="point.point_id"
                  :class="{ 'terrain-point-active': activeTerrainPointIds.has(point.point_id) }"
                >
                  <circle class="terrain-point-halo" :cx="point.x" :cy="point.y" r="1.45" />
                  <circle class="terrain-point-core" :cx="point.x" :cy="point.y" r="0.48" />
                  <text
                    v-if="activeTerrainPointLabelIds.has(point.point_id)"
                    :x="point.x + 1.35"
                    :y="point.y - 1.05"
                  >{{ point.shortLabel }}</text>
                </g>
              </g>
              <g v-if="historyMapStages.length" class="map-history-layer">
                <template v-for="stage in historyMapStages" :key="`history-${stage.stage_id}`">
                  <path
                    v-for="overlay in stage.overlays"
                    :key="`history-${stage.stage_id}-${overlay.overlay_id}`"
                    :d="overlay.path"
                    class="narrative-overlay overlay-history"
                    pathLength="100"
                  />
                  <rect
                    v-for="annotation in stage.annotations"
                    :key="`history-${stage.stage_id}-${annotation.annotation_id}`"
                    class="history-narrative-node"
                    x="-0.7"
                    y="-0.7"
                    width="1.4"
                    height="1.4"
                    :transform="`translate(${annotation.x} ${annotation.y}) rotate(45)`"
                  />
                </template>
              </g>
              <path
                v-for="overlay in activeStage.overlays"
                :key="overlay.overlay_id"
                :d="overlay.path"
                :class="['narrative-overlay', `overlay-${overlay.kind}`, { 'overlay-complete': overlayProgress(overlay) >= 0.98 }]"
                pathLength="100"
                :style="overlayStyle(overlay)"
              />
              <g v-if="motionPoint" class="narrative-motion-marker" :transform="motionTransform">
                <circle class="narrative-moving-marker" cx="0" cy="0" r="0.82" />
                <path class="narrative-moving-arrow" d="M -0.8 -0.62 L 1.25 0 L -0.8 0.62 Z" />
              </g>
              <text
                v-if="motionPoint && motionLabel"
                class="narrative-moving-label"
                :x="motionPoint.x + 1.4"
                :y="motionPoint.y - 1.35"
              >{{ motionLabel }}</text>
            </svg>
            <button
              v-for="annotation in activeStage.annotations"
              :key="annotation.annotation_id"
              type="button"
              class="document-annotation"
              :class="[
                `annotation-${annotation.kind}`,
                `annotation-${annotation.coordinate_role}`,
                {
                  'annotation-align-left': annotation.label_side === 'left'
                    || ((!annotation.label_side || annotation.label_side === 'auto') && annotation.x > 66),
                },
              ]"
              :style="annotationStyle(annotation)"
              :title="`${annotation.caption}；${annotation.not_claims.join('；')}`"
            >
              <span class="annotation-pulse"></span>
              <span class="annotation-label" :style="annotationLabelStyle(annotation)">
                <strong>{{ annotation.label }}</strong>
                <small>{{ annotation.caption }}</small>
              </span>
            </button>
          </div>

          <section
            v-else
            key="local-diagram"
            class="stage-spatial-diagram"
            :aria-label="`${activeStage.diagram.title}，空间关系示意`"
          >
            <header class="diagram-heading">
              <span>LOCAL SPATIAL INSET</span>
              <strong>{{ activeStage.diagram.title }}</strong>
              <small>{{ activeStage.diagram.caption }}</small>
            </header>
            <div v-if="/[北南]/.test(activeStage.diagram.orientation)" class="diagram-compass" aria-hidden="true"><i>北</i><span></span><b>南</b></div>
            <div v-else class="diagram-compass diagram-compass-schematic" aria-hidden="true"><i>示意</i></div>
            <div
              v-for="zone in activeStage.diagram.zones"
              :key="zone.zone_id"
              :class="['diagram-zone', `zone-${zone.kind}`]"
              :style="diagramZoneStyle(zone)"
              :title="zone.not_claims.join('；')"
            >
              <span>{{ zone.label }}</span>
            </div>
            <svg class="diagram-overlays" viewBox="0 0 100 100" aria-hidden="true">
              <path
                v-for="overlay in activeStage.overlays"
                :key="overlay.overlay_id"
                :d="overlay.path"
                :class="['narrative-overlay', `overlay-${overlay.kind}`, { 'overlay-complete': overlayProgress(overlay) >= 0.98 }]"
                pathLength="100"
                :style="overlayStyle(overlay)"
              />
              <g v-if="motionPoint" class="narrative-motion-marker" :transform="motionTransform">
                <circle class="narrative-moving-marker" cx="0" cy="0" r="0.95" />
                <path class="narrative-moving-arrow" d="M -0.9 -0.68 L 1.4 0 L -0.9 0.68 Z" />
              </g>
              <text
                v-if="motionPoint && motionLabel"
                class="narrative-moving-label diagram-marker-label"
                :x="motionPoint.x + 1.7"
                :y="motionPoint.y - 1.5"
              >{{ motionLabel }}</text>
            </svg>
            <button
              v-for="actor in activeStage.diagram.actors"
              :key="actor.actor_id"
              type="button"
              :class="[
                'diagram-actor',
                `faction-${actor.faction}`,
                `actor-${actor.state}`,
                { 'actor-align-left': actor.x > 75 },
              ]"
              :style="diagramActorStyle(actor)"
              :title="`${actor.detail}；${actor.not_claims.join('；')}`"
            >
              <i>{{ actor.label.slice(0, 1) }}</i>
              <span><strong>{{ actor.label }}</strong><small>{{ actor.detail }}</small></span>
            </button>
            <footer>{{ activeStage.diagram.orientation }} · 不按比例</footer>
          </section>
          </Transition>

          <div class="map-stage-stamp">
            <span>{{ String(activeStage.order).padStart(2, "0") }}</span>
            <strong>{{ activeStage.title }}</strong>
          </div>
          <div :class="['spatial-basis-badge', `basis-${activeStage.spatial_basis.mode}`]">
            <strong>{{ spatialBasisTitle }}</strong>
            <small>{{ spatialBasisDetail }}</small>
          </div>
          <div v-if="activeStage.overlays.length" class="map-overlay-label">
            {{ activeStage.overlays[0].label }}
          </div>
          <div class="document-coordinate-note">
            <LocateFixed :size="13" />
            {{ activeStage.diagram ? "局部空间关系示意 · 非测量平面图" : stageCoordinateLabel }}
          </div>
          <div class="map-animation-progress" aria-hidden="true">
            <i :style="{ width: `${stageProgress * 100}%` }"></i>
          </div>
        </div>

        <nav
          class="narrative-stage-list"
          aria-label="地图叙事阶段"
          :style="{ '--stage-count': narrativeStages.length }"
        >
          <button
            v-for="(stage, index) in narrativeStages"
            :key="stage.stage_id"
            type="button"
            :class="{ active: index === activeStageIndex, passed: index < activeStageIndex }"
            :aria-current="index === activeStageIndex ? 'step' : undefined"
            @click="selectStage(index)"
          >
            <span>{{ stage.order }}</span>
            <strong>{{ stage.short_label }}</strong>
          </button>
        </nav>

        <div class="narrative-transport" aria-label="地图播放控制">
          <button type="button" :disabled="activeStageIndex === 0" title="上一幕" @click="previousStage">
            <ChevronLeft :size="17" />
          </button>
          <button class="play-button" type="button" :aria-label="playing ? '暂停地图叙事' : '播放地图叙事'" @click="togglePlayback">
            <Pause v-if="playing" :size="18" />
            <Play v-else :size="18" />
          </button>
          <button type="button" :disabled="activeStageIndex === narrativeStages.length - 1" title="下一幕" @click="nextStage">
            <ChevronRight :size="17" />
          </button>
          <span class="stage-counter">{{ activeStageIndex + 1 }} / {{ narrativeStages.length }}</span>
          <span class="playback-clock">{{ playbackClock }}</span>
          <button
            type="button"
            class="follow-toggle"
            :class="{ active: autoFollow }"
            :aria-pressed="autoFollow"
            @click="toggleAutoFollow"
          >
            <Link2 :size="14" />
            <span>跟随正文</span>
            <i></i>
          </button>
        </div>

        <article class="stage-narration" aria-live="polite">
          <span class="eyebrow">第 {{ activeStage.order }} 幕 · {{ activeStage.title }}</span>
          <p>{{ activeStage.summary }}</p>
          <div>
            <BookOpen :size="14" />
            <span>对应正文：{{ readingAnchorLabel }} · 书影 {{ facsimileAnchorLabel }}</span>
            <small v-if="playing">动画播放中</small>
            <small v-else-if="autoFollow">正文滚动已接管幕次</small>
            <small v-else>当前为手动浏览</small>
          </div>
          <aside v-if="activeCue" class="active-animation-cue">
            <i></i>
            <span>{{ activeCue.spatial_semantics }}</span>
          </aside>
        </article>

        <details class="document-source-ledger" open>
          <summary>
            <span><ShieldCheck :size="16" />底图来源与可信度</span>
            <ChevronDown :size="16" />
          </summary>
          <div class="source-ledger-grid">
            <div>
              <span>{{ baseMap.kind === "terrain" ? "真实底图" : "文献" }}</span>
              <strong>{{ baseMap.title }}</strong>
              <small>{{ baseMap.observationLabel || baseMap.pageLabel }}</small>
            </div>
            <div>
              <span>性质</span>
              <strong>{{ baseMap.natureTitle }}</strong>
              <small>{{ baseMap.natureDetail }}</small>
            </div>
            <div>
              <span>网页资产</span>
              <strong>{{ baseMap.assetLabel }} · SHA-256 已校验</strong>
              <small>{{ baseMap.assetHash.slice(0, 12) }}…</small>
            </div>
            <div>
              <span>{{ baseMap.kind === "terrain" ? "覆盖范围" : "登记方式" }}</span>
              <strong>{{ baseMap.registrationTitle }}</strong>
              <small>{{ baseMap.registrationDetail }}</small>
            </div>
          </div>
          <p class="source-warning">
            <CircleAlert :size="15" />
            {{ sourceWarnings.join("；") }}。
          </p>
          <div class="source-actions">
            <a :href="baseMap.sourceUrl" target="_blank" rel="noreferrer">{{ baseMap.sourceActionLabel }} <ExternalLink :size="13" /></a>
            <a v-if="baseMap.secondaryUrl" :href="baseMap.secondaryUrl" target="_blank" rel="noreferrer">{{ baseMap.kind === "terrain" ? "开放数据分发" : "完整原页" }} <ExternalLink :size="13" /></a>
            <span v-if="baseMap.attribution">{{ baseMap.attribution }}</span>
          </div>
        </details>
      </section>

      <section v-else class="fallback-map" aria-label="地图场景资料">
        <header>
          <span class="eyebrow">CURATED MAP SCENE</span>
          <h2>{{ scene.title }}</h2>
          <p>{{ scene.summary }}</p>
        </header>
        <div v-if="renderablePoints.length" class="fallback-point-map">
          <svg viewBox="0 0 100 70" role="img" :aria-label="`${scene.title}现代语境点位`">
            <g v-for="point in pointPositions" :key="point.point_id">
              <circle :cx="point.x" :cy="point.y" r="2.5"></circle>
              <circle class="halo" :cx="point.x" :cy="point.y" r="6"></circle>
              <text :x="point.x + 4" :y="point.y - 3">{{ point.label }}</text>
            </g>
          </svg>
          <p>只显示来源和坐标系明确的现代语境点；不生成古代边界、路线或兵力范围。</p>
        </div>
        <ol v-else class="fallback-events">
          <li v-for="event in scene.timeline" :key="event.event_id">
            <span>{{ event.order }}</span>
            <div><strong>{{ event.label }}</strong><small>{{ event.time?.original_label || "年代未标注" }}</small></div>
          </li>
        </ol>
      </section>

      <section v-if="map.curated_scenes.length > 1" class="map-scene-picker" aria-label="选择地图场景">
        <header><strong>本章地图场景</strong><span>{{ map.curated_scenes.length }} 个</span></header>
        <div>
          <button
            v-for="sceneItem in map.curated_scenes"
            :key="sceneItem.scene_id"
            type="button"
            :class="{ active: sceneItem.scene_id === scene.scene_id }"
            @click="emit('select-scene', sceneItem.api_path)"
          >
            <strong>{{ sceneItem.title }}</strong>
            <span>{{ renderModeLabel(sceneItem.render_mode) }}</span>
          </button>
        </div>
      </section>
    </template>

    <section v-else class="map-detail-state">
      <strong>请选择一个场景</strong>
      <span>正文和文献阅读不受影响。</span>
    </section>
  </div>
</template>

<script setup lang="ts">
import {
  BookOpen,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  ExternalLink,
  Link2,
  LocateFixed,
  Pause,
  Play,
  ShieldCheck,
} from "@lucide/vue";
import { computed, onBeforeUnmount, ref, watch, type CSSProperties } from "vue";

import {
  resolvePublicAssetUrl,
  type ShijiMapAnimationKeyframe,
  type ShijiMapDiagramZone,
  type ShijiMapDocumentAnnotation,
  type ShijiMapDocumentOverlay,
  type ShijiMapNarrativeStage,
  type ShijiMapPlacePoint,
  type ShijiMapScene,
  type ShijiMapStageActor,
  type ShijiMapSummary,
} from "../../../services/api";
import {
  shijiStageIndexForSentence,
  shijiStageSentenceId,
} from "../../../services/shiji-map-sync";

interface NarrativeBaseMap {
  kind: "terrain" | "document";
  surfaceKind: "satellite_true_color" | "elevation_hillshade" | "historical_document";
  title: string;
  pageLabel: string;
  observationLabel: string;
  assetUrl: string;
  assetHash: string;
  sourceUrl: string;
  secondaryUrl: string;
  coordinateLabel: string;
  natureTitle: string;
  natureDetail: string;
  assetLabel: string;
  registrationTitle: string;
  registrationDetail: string;
  attribution: string;
  sourceActionLabel: string;
  notClaims: string[];
}

const props = defineProps<{
  activeUnitLabel: string;
  activeUnitId: string;
  map: ShijiMapSummary;
  scene: ShijiMapScene | null;
  selectedSceneId: string;
  sceneLoading: boolean;
  sceneError: string;
}>();

const emit = defineEmits<{
  "select-scene": [apiPath: string];
  "focus-unit": [unitId: string];
}>();

const activeStageIndex = ref(0);
const autoFollow = ref(true);
const playing = ref(false);
const stageElapsedMs = ref(0);
let playbackFrame: number | undefined;
let previousFrameAt: number | undefined;

const documentMap = computed(() => props.scene?.document_map ?? null);
const terrainMap = computed(() => props.scene?.terrain_map ?? null);
const baseMapAspectRatio = computed(() => {
  const map = terrainMap.value ?? documentMap.value;
  if (!map || map.image_width <= 0 || map.image_height <= 0) return 16 / 9;
  return map.image_width / map.image_height;
});
const baseMap = computed<NarrativeBaseMap | null>(() => {
  const terrain = terrainMap.value;
  if (terrain) {
    const bbox = terrain.bbox_wgs84;
    const isSatellite = terrain.source_family === "sentinel_2_l2a" || terrain.surface_kind === "satellite_true_color";
    const isNaturalEarth = terrain.source_family === "natural_earth_ii";
    const resolutionLabel = terrain.spatial_resolution_m >= 1000
      ? `约 ${(terrain.spatial_resolution_m / 1000).toFixed(1)} km`
      : `约 ${terrain.spatial_resolution_m} m`;
    const sourceLabel = isSatellite
      ? "Sentinel-2 真彩卫星影像"
      : isNaturalEarth
        ? "Natural Earth II 地形晕渲图"
        : "SRTM 雷达高程地形";
    return {
      kind: "terrain",
      surfaceKind: terrain.surface_kind,
      title: terrain.title,
      pageLabel: terrain.page_label,
      observationLabel: terrain.observation_label,
      assetUrl: resolvePublicAssetUrl(terrain.asset_url),
      assetHash: terrain.asset_sha256,
      sourceUrl: terrain.source_item_url,
      secondaryUrl: terrain.source_data_url,
      coordinateLabel: `${sourceLabel} · ${terrain.crs} · ${resolutionLabel}`,
      natureTitle: isSatellite
        ? "真实卫星地表影像"
        : isNaturalEarth
          ? "现代小比例尺地形晕渲底图"
          : "卫星雷达高程生成的真实地形",
      natureDetail: isSatellite
        ? "现代地表可定位；历史地点与路线只在独立证据层出现"
        : isNaturalEarth
          ? "现代地貌与水体经小比例尺概化；历史事件覆盖层单独标注证据边界"
          : "地势与现代水系可定位；历史事件覆盖层单独标注置信度",
      assetLabel: isSatellite ? "固定日期真彩裁切" : isNaturalEarth ? "固定版本区域地形裁切" : "本地区域地形裁切",
      registrationTitle: `${bbox.west.toFixed(2)}°E—${bbox.east.toFixed(2)}°E`,
      registrationDetail: `${bbox.south.toFixed(2)}°N—${bbox.north.toFixed(2)}°N · ${terrain.crs} · 比例误差 ${(terrain.aspect_ratio_error * 100).toFixed(2)}%`,
      attribution: terrain.attribution,
      sourceActionLabel: isSatellite ? "卫星数据条目" : isNaturalEarth ? "Natural Earth 数据说明" : "NASA 数据说明",
      notClaims: terrain.not_claims,
    };
  }
  const document = documentMap.value;
  if (!document) return null;
  return {
    kind: "document",
    surfaceKind: "historical_document",
    title: document.title,
    pageLabel: document.page_label,
    observationLabel: document.page_label,
    assetUrl: resolvePublicAssetUrl(document.asset_url),
    assetHash: document.asset_sha256,
    sourceUrl: document.source_item_url,
    secondaryUrl: document.source_page_url,
    coordinateLabel: "文献图像坐标 · 非经纬度",
    natureTitle: "后世刊本中的历史图像文献",
    natureDetail: "可作叙事文献，不是秦汉同期实测图",
    assetLabel: "原页裁切",
    registrationTitle: "图像百分比坐标",
    registrationDetail: document.registration.purpose,
    attribution: "",
    sourceActionLabel: "馆藏书目",
    notClaims: document.not_claims,
  };
});
const narrativeStages = computed<ShijiMapNarrativeStage[]>(() =>
  [...(props.scene?.narrative_sequence?.stages ?? [])].sort((left, right) => left.order - right.order),
);
const activeStage = computed(() => narrativeStages.value[activeStageIndex.value] ?? null);
const historyMapStages = computed<ShijiMapNarrativeStage[]>(() => {
  if (activeStage.value?.diagram || !activeStage.value?.continuity.preserve_previous_state) return [];
  return narrativeStages.value
    .slice(0, activeStageIndex.value)
    .filter((stage) => !stage.diagram);
});
const previousDiagramActorIds = computed(() => new Set(
  activeStage.value?.continuity.preserve_previous_state
    ? narrativeStages.value[activeStageIndex.value - 1]?.diagram?.actors.map((actor) => actor.actor_id) ?? []
    : [],
));
const spatialBasisTitle = computed(() => ({
  schematic_over_real_basemap: "关系推演层",
  georeferenced_context_with_schematic_overlay: "实地点位 + 推演覆盖",
  local_schematic: "局部空间示意",
} as const)[activeStage.value?.spatial_basis.mode ?? "local_schematic"]);
const spatialBasisDetail = computed(() => ({
  schematic_over_real_basemap: "节点与箭头均非经纬度",
  georeferenced_context_with_schematic_overlay: "绿色点可定位；线与范围不可测量",
  local_schematic: "据正文关系组织，不按比例",
} as const)[activeStage.value?.spatial_basis.mode ?? "local_schematic"]);
const stageCoordinateLabel = computed(() => activeStage.value?.spatial_basis.mode === "schematic_over_real_basemap"
  ? "真实底图 · 推演节点使用独立示意坐标"
  : activeStage.value?.spatial_basis.mode === "georeferenced_context_with_schematic_overlay"
    ? `${baseMap.value?.coordinateLabel ?? ""} · 覆盖线非测量`
    : "局部空间关系示意 · 非测量平面图");
const sourceWarnings = computed(() => [...new Set([
  ...(baseMap.value?.notClaims ?? []),
  ...(activeStage.value?.spatial_basis.not_claims ?? []),
  ...(activeStage.value?.diagram?.not_claims ?? []),
])]);
const animationFrames = computed<ShijiMapAnimationKeyframe[]>(() =>
  [...(props.scene?.animation_keyframes ?? [])].sort((left, right) => left.at_ms - right.at_ms),
);
const activeStageFrames = computed(() => animationFrames.value.filter((frame) =>
  !frame.stage_id || frame.stage_id === activeStage.value?.stage_id,
));
const isNarrativeMap = computed(() =>
  ["documentary_narrative", "terrain_narrative"].includes(props.scene?.render_mode ?? "")
  && Boolean(baseMap.value)
  && narrativeStages.value.length > 0,
);
const renderablePoints = computed(() => (props.scene?.place_points ?? []).filter(isTrustedPoint));
const activeTerrainPointIds = computed(() => {
  const stageAnchorIds = new Set(activeStage.value?.anchor_ids ?? []);
  if (!stageAnchorIds.size) return new Set<string>();
  return new Set(
    (props.scene?.timeline ?? [])
      .filter((event) => event.anchor_ids.some((anchorId) => stageAnchorIds.has(anchorId)))
      .flatMap((event) => event.place_point_ids),
  );
});
const mapContextLabel = computed(() => activeStage.value?.diagram
  ? "地图与局部示意联动"
  : baseMap.value?.surfaceKind === "satellite_true_color"
    ? "真实卫星地图叙事"
    : terrainMap.value
      ? "真实地形叙事"
    : isNarrativeMap.value
      ? "历史文献叙事"
      : "策展地图资料");
const mapStatusLabel = computed(() => {
  if (isNarrativeMap.value) {
    if (playing.value && autoFollow.value) return "正文联动过渡";
    return playing.value ? "动画播放中" : autoFollow.value ? "随正文演示" : "手动演示";
  }
  return props.scene?.render_ready ? "场景已登记" : "地图待补";
});
const readingAnchorLabel = computed(() => {
  const sentenceId = activeStage.value ? shijiStageSentenceId(activeStage.value) : "";
  const volumeMatch = sentenceId.match(/^shiji-juan-(\d{3})-/);
  const volumeLabel = volumeMatch ? `第 ${Number(volumeMatch[1])} 卷` : "本卷";
  const bodyMatch = sentenceId.match(/-body-(\d{5})(?:-|$)/);
  if (bodyMatch) return `${volumeLabel}正文 · 句 ${Number(bodyMatch[1])}`;
  const match = sentenceId.match(/-p(\d{4})-s(\d{3})$/);
  return match ? `${volumeLabel} p${match[1]} · 第 ${Number(match[2])} 句` : props.activeUnitLabel;
});
const facsimileAnchorLabel = computed(() => {
  const anchor = activeStage.value?.reading_anchor;
  const pageMatch = anchor?.page_id.match(/p(\d{4})$/);
  const pageLabel = pageMatch ? `p${pageMatch[1]}` : "已绑定页";
  return anchor?.anchor_kind === "frozen_page_fallback"
    ? `${pageLabel}（原页可见／OCR 漏栏）`
    : pageLabel;
});
const stageDurationMs = computed(() => Math.max(activeStage.value?.duration_ms ?? 1, 1));
const stageProgress = computed(() => Math.min(Math.max(stageElapsedMs.value / stageDurationMs.value, 0), 1));
const totalDurationMs = computed(() => narrativeStages.value.reduce((sum, stage) => sum + stage.duration_ms, 0));
const totalElapsedMs = computed(() => narrativeStages.value
  .slice(0, activeStageIndex.value)
  .reduce((sum, stage) => sum + stage.duration_ms, 0) + stageElapsedMs.value);
const playbackClock = computed(() => `${formatClock(totalElapsedMs.value)} / ${formatClock(totalDurationMs.value)}`);
const activeCue = computed(() => {
  const visible = activeStageFrames.value.filter((frame) => frame.at_ms <= stageElapsedMs.value);
  return visible[visible.length - 1] ?? activeStageFrames.value[0] ?? null;
});
const cameraStyle = computed(() => {
  const target = activeStage.value?.camera ?? { focus_x: 50, focus_y: 50, scale: 1 };
  const previous = narrativeStages.value[activeStageIndex.value - 1]?.camera ?? { focus_x: 50, focus_y: 50, scale: 1 };
  const progress = easeInOut(Math.min(stageProgress.value / 0.32, 1));
  const camera = {
    focus_x: interpolate(previous.focus_x, target.focus_x, progress),
    focus_y: interpolate(previous.focus_y, target.focus_y, progress),
    scale: interpolate(previous.scale, target.scale, progress),
  };
  return {
    transform: `translate(${(50 - camera.focus_x) * 0.55}%, ${(50 - camera.focus_y) * 0.34}%) scale(${camera.scale})`,
    transformOrigin: `${camera.focus_x}% ${camera.focus_y}%`,
  };
});
const terrainPointPositions = computed(() => {
  const terrain = terrainMap.value;
  if (!terrain) return [];
  const { west, south, east, north } = terrain.bbox_wgs84;
  return renderablePoints.value.map((point) => {
    const [longitude = 0, latitude = 0] = point.geometry?.coordinates ?? [];
    return {
      ...point,
      shortLabel: point.short_label || point.label.split("（")[0],
      x: ((longitude - west) / (east - west)) * 100,
      y: ((north - latitude) / (north - south)) * 100,
    };
  }).filter((point) => point.x >= 0 && point.x <= 100 && point.y >= 0 && point.y <= 100);
});
const activeTerrainPointLabelIds = computed(() => {
  const annotations = activeStage.value?.annotations ?? [];
  return new Set(
    terrainPointPositions.value
      .filter((point) => {
        if (!activeTerrainPointIds.value.has(point.point_id)) return false;
        // The event annotation already names the same location with fuller
        // evidence context.  Avoid drawing a second short label underneath it;
        // duplicate labels are both noisy and prone to camera-edge clipping.
        return !annotations.some((annotation) =>
          Math.hypot(annotation.x - point.x, annotation.y - point.y) < 0.75,
        );
      })
      .map((point) => point.point_id),
  );
});
const activeMotionFrame = computed(() => {
  const frames = activeStageFrames.value.filter((frame) => frame.effect === "move_narrative_marker");
  const started = frames.filter((frame) => frame.at_ms <= stageElapsedMs.value);
  return started[started.length - 1] ?? frames[0] ?? null;
});
const movingOverlay = computed(() => activeStage.value?.overlays.find(
  (overlay) => overlay.overlay_id === activeMotionFrame.value?.target_id,
) ?? null);
const motionPoint = computed(() => {
  const overlay = movingOverlay.value;
  if (!overlay) return null;
  return cubicPoint(overlay.path, overlayProgress(overlay));
});
const motionTransform = computed(() => motionPoint.value
  ? `translate(${motionPoint.value.x} ${motionPoint.value.y}) rotate(${motionPoint.value.angle})`
  : undefined);
const motionLabel = computed(() => activeMotionFrame.value?.marker_label ?? "");
const pointPositions = computed(() => {
  const points = renderablePoints.value;
  if (!points.length) return [];
  const xs = points.map((point) => point.geometry?.coordinates[0] ?? 0);
  const ys = points.map((point) => point.geometry?.coordinates[1] ?? 0);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  return points.map((point) => ({
    ...point,
    x: normalizePlotCoordinate(point.geometry?.coordinates[0] ?? 0, minX, maxX),
    y: 70 - normalizePlotCoordinate(point.geometry?.coordinates[1] ?? 0, minY, maxY) * 0.6,
  }));
});

function isTrustedPoint(point: ShijiMapPlacePoint) {
  const coordinates = point.geometry?.coordinates;
  return point.renderable === true
    && point.geometry?.type === "Point"
    && Boolean(point.crs?.trim())
    && Boolean(coordinates && coordinates.length >= 2 && coordinates.every(Number.isFinite));
}

function normalizePlotCoordinate(value: number, min: number, max: number) {
  return max === min ? 50 : 10 + ((value - min) / (max - min)) * 80;
}

function annotationStyle(annotation: ShijiMapDocumentAnnotation) {
  const reveal = Math.min(Math.max((stageProgress.value - 0.08) / 0.2, 0), 1);
  return {
    left: `${annotation.x}%`,
    top: `${annotation.y}%`,
    opacity: reveal,
    transform: `scale(${0.82 + reveal * 0.18})`,
  };
}

function annotationLabelStyle(annotation: ShijiMapDocumentAnnotation) {
  const offsetX = annotation.label_offset_x ?? 0;
  const offsetY = annotation.label_offset_y ?? 0;
  return offsetX || offsetY
    ? { transform: `translate(${offsetX}px, ${offsetY}px)` }
    : undefined;
}

function diagramZoneStyle(zone: ShijiMapDiagramZone) {
  return {
    left: `${zone.x}%`,
    top: `${zone.y}%`,
    width: `${zone.width}%`,
    height: `${zone.height}%`,
  };
}

function diagramActorStyle(actor: ShijiMapStageActor): CSSProperties {
  const revealDuration = 520;
  const persisted = previousDiagramActorIds.value.has(actor.actor_id);
  const reveal = persisted
    ? 1
    : Math.min(
      Math.max((stageElapsedMs.value - actor.appear_at_ms) / revealDuration, 0),
      1,
    );
  return {
    left: `${actor.x}%`,
    top: `${actor.y}%`,
    opacity: reveal,
    pointerEvents: reveal > 0.45 ? "auto" : "none",
    transform: `translate(${actor.x > 75 ? "-100%" : "-50%"}, -50%) scale(${0.72 + reveal * 0.28})`,
  };
}

function overlayStyle(overlay: ShijiMapDocumentOverlay) {
  const progress = overlayProgress(overlay);
  return {
    strokeDasharray: 100,
    strokeDashoffset: 100 - progress * 100,
    opacity: Math.min(progress * 2.6, 1),
  };
}

function overlayProgress(overlay: ShijiMapDocumentOverlay) {
  const frame = activeStageFrames.value.find((item) => item.target_id === overlay.overlay_id);
  if (!frame) return stageProgress.value;
  if (stageElapsedMs.value <= frame.at_ms) return 0;
  return Math.min((stageElapsedMs.value - frame.at_ms) / Math.max(frame.duration_ms, 1), 1);
}

function cubicPoint(path: string, progress: number) {
  const match = path.match(/M\s*(-?[\d.]+)\s+(-?[\d.]+)\s+C\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)/i);
  if (!match) return null;
  const [, x0, y0, x1, y1, x2, y2, x3, y3] = match.map(Number);
  const t = Math.min(Math.max(progress, 0), 1);
  const inverse = 1 - t;
  const derivativeX = 3 * inverse ** 2 * (x1 - x0)
    + 6 * inverse * t * (x2 - x1)
    + 3 * t ** 2 * (x3 - x2);
  const derivativeY = 3 * inverse ** 2 * (y1 - y0)
    + 6 * inverse * t * (y2 - y1)
    + 3 * t ** 2 * (y3 - y2);
  return {
    x: inverse ** 3 * x0 + 3 * inverse ** 2 * t * x1 + 3 * inverse * t ** 2 * x2 + t ** 3 * x3,
    y: inverse ** 3 * y0 + 3 * inverse ** 2 * t * y1 + 3 * inverse * t ** 2 * y2 + t ** 3 * y3,
    angle: Math.atan2(derivativeY, derivativeX) * (180 / Math.PI),
  };
}

function syncStageToSentence(animateTransition = true) {
  if (!autoFollow.value || !props.activeUnitId || !narrativeStages.value.length) return;
  const nextIndex = shijiStageIndexForSentence(narrativeStages.value, props.activeUnitId);
  if (nextIndex !== activeStageIndex.value) {
    const movingForward = nextIndex > activeStageIndex.value;
    stopPlayback();
    activeStageIndex.value = nextIndex;
    const duration = narrativeStages.value[nextIndex]?.duration_ms ?? 0;
    const reducedMotion = typeof window !== "undefined"
      && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (animateTransition && movingForward && !reducedMotion) {
      stageElapsedMs.value = 0;
      playing.value = true;
      startPlaybackLoop();
    } else {
      stageElapsedMs.value = duration;
    }
  }
}

function selectStage(index: number) {
  stopPlayback();
  autoFollow.value = false;
  const nextIndex = Math.min(Math.max(index, 0), narrativeStages.value.length - 1);
  activeStageIndex.value = nextIndex;
  focusReadingOnStage(nextIndex);
  stageElapsedMs.value = 0;
  playing.value = true;
  // A stage button can be pressed while playback is already running. Vue may
  // batch the false -> true transition, so restart the frame loop explicitly.
  startPlaybackLoop();
}

function previousStage() { selectStage(activeStageIndex.value - 1); }
function nextStage() { selectStage(activeStageIndex.value + 1); }

function focusReadingOnStage(index: number) {
  const unitId = narrativeStages.value[index]?.runtime_sentence_id;
  if (unitId) emit("focus-unit", unitId);
}

function togglePlayback() {
  if (playing.value) {
    stopPlayback();
    autoFollow.value = false;
    return;
  }
  autoFollow.value = false;
  if (activeStageIndex.value >= narrativeStages.value.length - 1 && stageProgress.value >= 1) {
    activeStageIndex.value = 0;
    focusReadingOnStage(0);
    stageElapsedMs.value = 0;
  }
  playing.value = true;
}

function stopPlayback() {
  playing.value = false;
  cancelPlaybackFrame();
}

function toggleAutoFollow() {
  stopPlayback();
  autoFollow.value = !autoFollow.value;
  if (autoFollow.value) {
    syncStageToSentence(false);
    stageElapsedMs.value = activeStage.value?.duration_ms ?? 0;
  }
}

function startPlaybackLoop() {
  cancelPlaybackFrame();
  previousFrameAt = undefined;
  playbackFrame = window.requestAnimationFrame(advancePlayback);
}

function advancePlayback(now: number) {
  if (!playing.value || !activeStage.value) return;
  const delta = previousFrameAt === undefined ? 0 : Math.min(now - previousFrameAt, 100);
  previousFrameAt = now;
  stageElapsedMs.value += delta;
  if (stageElapsedMs.value >= stageDurationMs.value) {
    if (autoFollow.value) {
      stageElapsedMs.value = stageDurationMs.value;
      playing.value = false;
      return;
    }
    if (activeStageIndex.value >= narrativeStages.value.length - 1) {
      stageElapsedMs.value = stageDurationMs.value;
      playing.value = false;
      return;
    }
    stageElapsedMs.value -= stageDurationMs.value;
    activeStageIndex.value += 1;
    focusReadingOnStage(activeStageIndex.value);
  }
  playbackFrame = window.requestAnimationFrame(advancePlayback);
}

function cancelPlaybackFrame() {
  if (playbackFrame !== undefined) window.cancelAnimationFrame(playbackFrame);
  playbackFrame = undefined;
  previousFrameAt = undefined;
}

function formatClock(milliseconds: number) {
  const seconds = Math.max(0, Math.round(milliseconds / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function interpolate(start: number, end: number, progress: number) {
  return start + (end - start) * progress;
}

function easeInOut(value: number) {
  return value < 0.5 ? 4 * value ** 3 : 1 - (-2 * value + 2) ** 3 / 2;
}

function renderModeLabel(mode: string) {
  return ({
    event_card_only: "事件资料卡",
    context_markers_only: "现代语境点位",
    protected_site_context_only: "保护遗址语境点位",
    documentary_narrative: "历史文献叙事",
    terrain_narrative: "真实地形叙事",
  } as Record<string, string>)[mode] ?? mode;
}

watch(playing, (value) => {
  if (value) startPlaybackLoop();
  else cancelPlaybackFrame();
});
watch(
  () => props.scene?.scene_id,
  () => {
    stopPlayback();
    const sequence = props.scene?.narrative_sequence;
    const defaultIndex = narrativeStages.value.findIndex((stage) => stage.stage_id === sequence?.default_stage_id);
    activeStageIndex.value = defaultIndex >= 0 ? defaultIndex : 0;
    autoFollow.value = sequence?.auto_follow_default ?? true;
    stageElapsedMs.value = activeStage.value?.duration_ms ?? 0;
    syncStageToSentence(false);
    const reducedMotion = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!autoFollow.value && sequence?.auto_play_default && !reducedMotion) {
      activeStageIndex.value = defaultIndex >= 0 ? defaultIndex : 0;
      stageElapsedMs.value = 0;
      playing.value = true;
    }
  },
  { immediate: true },
);
watch(() => props.activeUnitId, () => syncStageToSentence(true));
onBeforeUnmount(cancelPlaybackFrame);
</script>

<style scoped>
.map-data-available { container-type: inline-size; display: grid; gap: 12px; grid-auto-rows: auto; height: auto !important; min-height: 100%; padding-bottom: 20px; }
.map-ready-badge { border: 1px solid color-mix(in srgb, var(--jade) 42%, var(--line)); color: var(--jade-dark); font-size: 10px; padding: 4px 8px; }
.map-ready-badge.pending { border-color: color-mix(in srgb, #ad7a1f 45%, var(--line)); color: #8a5f16; }
.documentary-map { display: grid; gap: 10px; }
.documentary-heading { align-items: start; display: flex; gap: 12px; justify-content: space-between; padding: 4px 2px 2px; }
.documentary-heading h2, .fallback-map h2 { font-family: var(--font-serif); font-size: 21px; font-weight: 600; margin: 4px 0 5px; }
.documentary-heading p, .fallback-map header p { color: var(--muted); font-size: 11px; line-height: 1.6; margin: 0; }
.eyebrow { color: var(--cinnabar, #a83b2d); font-size: 9px; letter-spacing: .12em; }
.source-page-link { align-items: center; border: 1px solid var(--line); color: var(--ink); display: inline-flex; flex: 0 0 auto; gap: 4px; padding: 7px 8px; text-decoration: none; }
.source-page-link:hover { border-color: var(--cinnabar); color: var(--cinnabar); }
.document-map-viewport { align-items: center; aspect-ratio: 16 / 10; background: #22251f; border: 1px solid color-mix(in srgb, var(--ink) 42%, var(--line)); display: flex; height: auto; overflow: hidden; position: relative; }
.document-map-viewport.diagram-active { background: #e7ddc8; }
.document-map-layer { aspect-ratio: 16 / 9; flex: 0 0 auto; height: auto; margin: 0 auto; position: relative; transition: transform 80ms linear; width: 100%; will-change: transform; }
.spatial-stage-enter-active,.spatial-stage-leave-active { transition: opacity 260ms ease; }
.spatial-stage-enter-from,.spatial-stage-leave-to { opacity: 0; }
.schematic-spatial-stage .document-map-layer::before { border: 1px dashed rgba(235,190,104,.76); box-shadow: inset 0 0 0 4px rgba(32,25,18,.12); content: ""; inset: 7px; pointer-events: none; position: absolute; z-index: 2; }
.document-map-layer::after { background: radial-gradient(circle at 52% 44%, transparent 42%, rgba(19,23,18,.24) 100%), linear-gradient(180deg, rgba(23,20,17,.03), transparent 35%, rgba(23,20,17,.13)); content: ""; inset: 0; pointer-events: none; position: absolute; }
.document-map-layer img { display: block; height: 100%; object-fit: cover; user-select: none; width: 100%; }
.document-map-overlays { inset: 0; overflow: visible; pointer-events: none; position: absolute; }
.narrative-overlay { fill: none; stroke: #a83b2d; stroke-linecap: round; vector-effect: non-scaling-stroke; }
.map-history-layer { pointer-events: none; }
.narrative-overlay.overlay-history { opacity: .24; stroke: #665f50; stroke-dasharray: 3 4; stroke-width: 1.4; }
.history-narrative-node { fill: rgba(107,94,69,.42); stroke: rgba(255,249,230,.7); stroke-width: .35; vector-effect: non-scaling-stroke; }
.narrative-overlay.overlay-complete.overlay-narrative_connector { animation: route-flow 900ms linear infinite; stroke-dasharray: 7 4 !important; }
.overlay-division_band { filter: drop-shadow(0 0 3px rgba(96,28,20,.45)); stroke: rgba(164,54,42,.84); stroke-width: 9; }
.overlay-narrative_connector { filter: drop-shadow(0 1px 2px rgba(47,28,18,.45)); stroke: #b34534; stroke-width: 2.5; }
.terrain-context-points text { fill: #26362f; font-family: var(--font-serif); font-size: 2.6px; font-weight: 650; paint-order: stroke; stroke: rgba(250,247,236,.94); stroke-width: .7px; }
.terrain-point-halo { fill: rgba(26,96,76,.1); stroke: rgba(27,91,73,.38); stroke-width: .22; }
.terrain-point-core { fill: rgba(23,108,86,.68); stroke: rgba(247,242,229,.82); stroke-width: .24; }
.terrain-point-active .terrain-point-halo { animation: map-pulse 1.8s ease-out infinite; fill: rgba(26,96,76,.18); stroke: rgba(27,91,73,.68); }
.terrain-point-active .terrain-point-core { fill: #176c56; stroke: #f7f2e5; }
.narrative-moving-marker { animation: moving-marker-breathe 900ms ease-in-out infinite alternate; fill: #f4c769; filter: drop-shadow(0 0 2px #fff2ba) drop-shadow(0 0 5px rgba(157,52,38,.85)); stroke: #8f2f25; stroke-width: .24; }
.narrative-moving-arrow { fill: #8f2f25; filter: drop-shadow(0 0 1px rgba(255,246,211,.92)); stroke: #fff3c5; stroke-width: .13; }
.narrative-moving-label { fill: #7f2d25; font-family: var(--font-serif); font-size: 2.7px; font-weight: 700; paint-order: stroke; stroke: rgba(255,248,228,.96); stroke-width: .8px; }
.diagram-marker-label { font-size: 3px; }
.stage-spatial-diagram { background: radial-gradient(circle at 50% 45%,rgba(255,252,242,.94),rgba(224,211,185,.96)), repeating-linear-gradient(0deg,transparent 0 34px,rgba(87,67,42,.035) 35px), repeating-linear-gradient(90deg,transparent 0 34px,rgba(87,67,42,.035) 35px); color: #2d241b; height: 100%; isolation: isolate; overflow: hidden; position: relative; width: 100%; }
.stage-spatial-diagram::before { border: 1px solid rgba(90,65,37,.26); content: ""; inset: 8%; pointer-events: none; position: absolute; }
.diagram-heading { display: grid; gap: 2px; left: 16px; max-width: 44%; position: absolute; top: 58px; z-index: 5; }
.diagram-heading span { color: #a13b2f; font-size: 7px; letter-spacing: .14em; }
.diagram-heading strong { font-family: var(--font-serif); font-size: 15px; font-weight: 650; }
.diagram-heading small { color: #756553; font-size: 8px; line-height: 1.45; }
.diagram-compass { align-items: center; color: #765f46; display: grid; font-family: var(--font-serif); font-size: 8px; justify-items: center; position: absolute; right: 17px; top: 13px; z-index: 5; }
.diagram-compass span { background: #9c3a2e; clip-path: polygon(50% 0,100% 100%,50% 74%,0 100%); height: 24px; margin: 2px 0; width: 13px; }
.diagram-compass b { font-weight: 400; opacity: .56; }
.diagram-zone { align-items: center; border: 1px dashed rgba(92,69,43,.48); display: flex; justify-content: center; position: absolute; z-index: 1; }
.diagram-zone span { background: rgba(247,240,225,.9); color: #756553; font-family: var(--font-serif); font-size: 8px; padding: 2px 4px; }
.zone-table { background: radial-gradient(ellipse at center,rgba(152,107,57,.24),rgba(152,107,57,.06)); border-style: solid; border-radius: 50%; }
.zone-gate { border-color: rgba(39,85,72,.62); border-left-width: 4px; }
.zone-screen { background: repeating-linear-gradient(90deg,rgba(112,70,40,.16) 0 3px,transparent 3px 7px); border-style: solid; }
.zone-exit { border-color: rgba(161,59,47,.58); }
.zone-river { background: linear-gradient(90deg,rgba(72,124,142,.18),rgba(124,174,188,.42),rgba(72,124,142,.18)); border-color: rgba(54,105,123,.5); border-style: solid; }
.diagram-compass-schematic { border: 1px solid rgba(118,95,70,.35); padding: 3px 5px; }
.diagram-overlays { height: 100%; inset: 0; overflow: visible; pointer-events: none; position: absolute; width: 100%; z-index: 2; }
.diagram-actor { align-items: center; background: transparent; border: 0; color: #2d241b; cursor: help; display: flex; gap: 5px; padding: 0; position: absolute; transition: opacity 240ms ease,transform 240ms ease; z-index: 4; }
.diagram-actor > i { align-items: center; background: #73624e; border: 2px solid rgba(255,250,238,.94); border-radius: 50%; box-shadow: 0 2px 8px rgba(53,39,25,.23); color: white; display: flex; flex: 0 0 auto; font-family: var(--font-serif); font-size: 10px; font-style: normal; height: 24px; justify-content: center; width: 24px; }
.diagram-actor > span { background: rgba(250,245,233,.93); border-left: 2px solid #73624e; box-shadow: 0 2px 8px rgba(53,39,25,.11); display: grid; gap: 1px; min-width: 76px; padding: 4px 6px; text-align: left; }
.diagram-actor strong { font-family: var(--font-serif); font-size: 9px; }
.diagram-actor small { color: #746554; font-size: 7px; line-height: 1.25; }
.diagram-actor.faction-chu > i { background: #9f3e31; }
.diagram-actor.faction-chu > span { border-left-color: #9f3e31; }
.diagram-actor.faction-han > i { background: #1d6b58; }
.diagram-actor.faction-han > span { border-left-color: #1d6b58; }
.diagram-actor.faction-mediator > i { background: #a4772e; }
.diagram-actor.faction-mediator > span { border-left-color: #a4772e; }
.diagram-actor.actor-align-left { flex-direction: row-reverse; }
.diagram-actor.actor-align-left > span { border-left: 0; border-right: 2px solid #73624e; text-align: right; }
.diagram-actor.actor-align-left.faction-chu > span { border-right-color: #9f3e31; }
.diagram-actor.actor-align-left.faction-han > span { border-right-color: #1d6b58; }
.diagram-actor.actor-align-left.faction-mediator > span { border-right-color: #a4772e; }
.diagram-actor.actor-moving > i,.diagram-actor.actor-standing > i { animation: map-pulse 1.8s ease-out infinite; }
.stage-spatial-diagram > footer { bottom: 8px; color: rgba(83,65,45,.7); font-size: 7px; left: 10px; position: absolute; z-index: 5; }
.document-annotation { background: transparent; border: 0; color: var(--ink); cursor: help; height: 0; padding: 0; position: absolute; transform-origin: center; transition: opacity 240ms ease, transform 240ms ease; width: 0; z-index: 3; }
.annotation-pulse { background: var(--cinnabar, #a83b2d); border: 2px solid rgba(255,251,242,.94); border-radius: 50%; box-shadow: 0 0 0 7px rgba(168,59,45,.2), 0 0 0 14px rgba(168,59,45,.08); display: block; height: 12px; left: -6px; position: absolute; top: -6px; width: 12px; }
.annotation-event .annotation-pulse { animation: map-pulse 2.2s ease-out infinite; }
.annotation-narrative_node .annotation-pulse { background: #d39a3d; border-color: rgba(255,248,223,.96); border-radius: 2px; box-shadow: 0 0 0 6px rgba(211,154,61,.2),0 0 0 12px rgba(211,154,61,.08); transform: rotate(45deg); }
.annotation-narrative_node.annotation-event .annotation-pulse { animation: narrative-node-pulse 2.2s ease-out infinite; }
.annotation-label { background: rgba(250,246,237,.94); border-left: 2px solid var(--cinnabar, #a83b2d); box-shadow: 0 3px 14px rgba(31,25,19,.16); color: #2d241b; display: grid; gap: 2px; left: 10px; min-width: 126px; padding: 7px 8px; position: absolute; text-align: left; top: -14px; }
.annotation-narrative_node .annotation-label { border: 1px dashed rgba(157,108,35,.64); border-left: 3px solid #c48b34; }
.annotation-align-left .annotation-label { left: auto; right: 10px; }
.annotation-label strong { font-family: var(--font-serif); font-size: 11px; }
.annotation-label small { color: #6d5f51; font-size: 8px; line-height: 1.4; }
.map-stage-stamp { align-items: center; background: rgba(249,245,236,.92); border-left: 3px solid var(--cinnabar, #a83b2d); color: #2d241b; display: flex; gap: 8px; left: 10px; padding: 7px 10px; position: absolute; top: 10px; z-index: 4; }
.map-stage-stamp span { color: var(--cinnabar, #a83b2d); font-family: var(--font-serif); font-size: 17px; }
.map-stage-stamp strong { font-family: var(--font-serif); font-size: 12px; }
.spatial-basis-badge { backdrop-filter: blur(5px); background: rgba(27,34,29,.86); border: 1px solid rgba(238,229,202,.42); color: #fff8e9; display: grid; gap: 2px; max-width: 190px; padding: 6px 8px; position: absolute; right: 9px; text-align: right; top: 9px; z-index: 5; }
.spatial-basis-badge strong { font-family: var(--font-serif); font-size: 10px; font-weight: 650; }
.spatial-basis-badge small { color: rgba(255,246,220,.74); font-size: 7px; line-height: 1.35; }
.spatial-basis-badge.basis-schematic_over_real_basemap { background: rgba(108,69,22,.89); border-color: rgba(246,205,124,.7); }
.spatial-basis-badge.basis-georeferenced_context_with_schematic_overlay { background: rgba(24,76,61,.89); }
.spatial-basis-badge.basis-local_schematic { background: rgba(90,57,30,.88); }
.diagram-active .diagram-compass { top: 57px; }
.map-overlay-label { background: rgba(130,42,31,.84); bottom: 46px; color: #fff8ed; font-family: var(--font-serif); font-size: 11px; left: 50%; padding: 6px 9px; position: absolute; transform: translateX(-50%); z-index: 4; }
.document-coordinate-note { align-items: center; background: rgba(28,24,20,.78); bottom: 8px; color: #f6efe3; display: inline-flex; font-size: 9px; gap: 5px; padding: 5px 7px; position: absolute; right: 8px; z-index: 4; }
.map-animation-progress { background: rgba(252,248,238,.22); bottom: 0; height: 3px; left: 0; position: absolute; right: 0; z-index: 6; }
.map-animation-progress i { background: linear-gradient(90deg,#b24232,#e0a554); display: block; height: 100%; transition: width 80ms linear; }
.narrative-stage-list { --stage-count: 4; display: grid; grid-template-columns: repeat(var(--stage-count),minmax(64px,1fr)); overflow-x: auto; position: relative; scrollbar-width: thin; }
.narrative-stage-list::before { border-top: 1px solid var(--line); content: ""; left: 8%; position: absolute; right: 8%; top: 14px; }
.narrative-stage-list button { align-items: center; background: transparent; border: 0; color: var(--muted); cursor: pointer; display: grid; gap: 5px; justify-items: center; min-width: 0; padding: 2px 3px 6px; position: relative; }
.narrative-stage-list button span { align-items: center; background: var(--paper); border: 1px solid var(--line); border-radius: 50%; display: flex; font-size: 9px; height: 25px; justify-content: center; width: 25px; z-index: 1; }
.narrative-stage-list button strong { font-size: 9px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; width: 100%; }
.narrative-stage-list button.active, .narrative-stage-list button.passed { color: var(--cinnabar, #a83b2d); }
.narrative-stage-list button.active span { background: var(--cinnabar, #a83b2d); border-color: var(--cinnabar, #a83b2d); color: white; }
.narrative-stage-list button.passed span { border-color: var(--cinnabar, #a83b2d); }
.narrative-transport { align-items: center; border-bottom: 1px solid var(--line-soft); border-top: 1px solid var(--line-soft); display: flex; gap: 5px; min-height: 48px; padding: 5px 2px; }
.narrative-transport > button:not(.follow-toggle) { align-items: center; background: transparent; border: 1px solid transparent; color: var(--ink); cursor: pointer; display: inline-flex; height: 32px; justify-content: center; width: 32px; }
.narrative-transport > button:disabled { cursor: default; opacity: .28; }
.narrative-transport .play-button { border-color: var(--cinnabar, #a83b2d) !important; border-radius: 50%; color: var(--cinnabar, #a83b2d) !important; height: 38px !important; width: 38px !important; }
.stage-counter { color: var(--muted); font-size: 10px; margin-left: 5px; }
.playback-clock { color: var(--muted); font-size: 9px; font-variant-numeric: tabular-nums; }
.follow-toggle { align-items: center; background: transparent; border: 0; color: var(--muted); cursor: pointer; display: inline-flex; gap: 5px; margin-left: auto; padding: 6px 1px 6px 7px; }
.follow-toggle span { font-size: 9px; }
.follow-toggle i { background: var(--line); height: 16px; position: relative; width: 28px; }
.follow-toggle i::after { background: var(--paper); border: 1px solid color-mix(in srgb,var(--ink) 35%,var(--line)); content: ""; height: 12px; left: 2px; position: absolute; top: 2px; transition: transform 160ms ease; width: 12px; }
.follow-toggle.active { color: var(--cinnabar, #a83b2d); }
.follow-toggle.active i { background: var(--cinnabar, #a83b2d); }
.follow-toggle.active i::after { border-color: white; transform: translateX(12px); }
.stage-narration { background: color-mix(in srgb,var(--paper-deep) 32%,transparent); border-left: 3px solid var(--cinnabar, #a83b2d); padding: 12px 13px; }
.stage-narration p { font-family: var(--font-serif); font-size: 13px; line-height: 1.8; margin: 5px 0 9px; }
.stage-narration > div { align-items: center; color: var(--cinnabar, #a83b2d); display: flex; flex-wrap: wrap; font-size: 9px; gap: 5px; }
.stage-narration small { color: var(--muted); margin-left: auto; }
.active-animation-cue { align-items: flex-start !important; border-top: 1px solid var(--line-soft); color: var(--muted) !important; display: flex !important; gap: 7px !important; margin-top: 9px; padding-top: 8px; }
.active-animation-cue i { animation: cue-pulse 1.2s ease-in-out infinite; background: var(--cinnabar); border-radius: 50%; flex: 0 0 auto; height: 6px; margin-top: 4px; width: 6px; }
.active-animation-cue span { line-height: 1.55; }
.document-source-ledger { border: 1px solid var(--line-soft); }
.document-source-ledger summary { align-items: center; cursor: pointer; display: flex; justify-content: space-between; list-style: none; padding: 10px 12px; }
.document-source-ledger summary::-webkit-details-marker { display: none; }
.document-source-ledger summary span { align-items: center; display: inline-flex; font-family: var(--font-serif); font-size: 13px; gap: 6px; }
.document-source-ledger[open] summary > svg { transform: rotate(180deg); }
.source-ledger-grid { border-top: 1px solid var(--line-soft); display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); }
.source-ledger-grid > div { border-bottom: 1px solid var(--line-soft); display: grid; gap: 3px; padding: 9px 10px; }
.source-ledger-grid > div:nth-child(odd) { border-right: 1px solid var(--line-soft); }
.source-ledger-grid span, .source-ledger-grid small { color: var(--muted); font-size: 8px; line-height: 1.45; }
.source-ledger-grid strong { font-size: 10px; line-height: 1.45; }
.source-warning { align-items: flex-start; color: var(--cinnabar, #a83b2d); display: flex; font-size: 9px; gap: 6px; line-height: 1.6; margin: 0; padding: 9px 10px; }
.source-warning svg { flex: 0 0 auto; margin-top: 1px; }
.source-actions { align-items: center; border-top: 1px solid var(--line-soft); display: flex; flex-wrap: wrap; gap: 10px 14px; padding: 8px 10px; }
.source-actions a { align-items: center; color: var(--jade-dark); display: inline-flex; font-size: 9px; gap: 4px; text-decoration: none; }
.source-actions > span { color: var(--muted); font-size: 8px; margin-left: auto; }
.fallback-map, .map-scene-picker, .map-detail-state { background: color-mix(in srgb,var(--paper) 82%,transparent); border: 1px solid var(--line-soft); padding: 15px; }
.fallback-point-map { background: var(--paper-deep); margin-top: 12px; }
.fallback-point-map svg { display: block; height: 260px; width: 100%; }
.fallback-point-map circle:first-child { fill: var(--cinnabar, #a83b2d); }
.fallback-point-map .halo { fill: none; stroke: color-mix(in srgb,var(--cinnabar) 42%,transparent); }
.fallback-point-map text { fill: var(--ink); font-family: var(--font-serif); font-size: 3px; }
.fallback-point-map p { border-top: 1px solid var(--line-soft); color: var(--muted); font-size: 9px; line-height: 1.6; margin: 0; padding: 8px 10px; }
.fallback-events { display: grid; gap: 7px; list-style: none; margin: 12px 0 0; padding: 0; }
.fallback-events li { align-items: start; border-left: 2px solid var(--jade); display: flex; gap: 8px; padding: 7px 9px; }
.fallback-events li > span { color: var(--jade-dark); font-family: var(--font-serif); }
.fallback-events li div { display: grid; gap: 3px; }
.fallback-events strong { font-size: 10px; }
.fallback-events small { color: var(--muted); font-size: 8px; }
.map-scene-picker header { align-items: center; display: flex; justify-content: space-between; }
.map-scene-picker header span { color: var(--muted); font-size: 9px; }
.map-scene-picker > div { display: grid; gap: 6px; grid-template-columns: repeat(auto-fit,minmax(140px,1fr)); margin-top: 9px; }
.map-scene-picker button { background: var(--paper); border: 1px solid var(--line-soft); color: var(--ink); cursor: pointer; display: grid; gap: 4px; padding: 8px; text-align: left; }
.map-scene-picker button.active { border-color: var(--cinnabar, #a83b2d); }
.map-scene-picker button strong { font-size: 10px; }
.map-scene-picker button span { color: var(--muted); font-size: 8px; }
.map-detail-state { align-items: center; color: var(--muted); display: grid; gap: 6px; justify-items: center; min-height: 170px; text-align: center; }
.map-detail-state strong { color: var(--ink); }
.map-detail-error strong { color: var(--cinnabar, #a83b2d); }
.map-loading-dot { background: var(--jade); border-radius: 50%; box-shadow: 0 0 0 7px var(--jade-wash); height: 9px; margin: 8px; width: 9px; }
@keyframes map-pulse { 0% { box-shadow: 0 0 0 0 rgba(168,59,45,.42), 0 0 0 0 rgba(168,59,45,.2); } 75%,100% { box-shadow: 0 0 0 9px rgba(168,59,45,0), 0 0 0 18px rgba(168,59,45,0); } }
@keyframes narrative-node-pulse { 0% { box-shadow: 0 0 0 0 rgba(211,154,61,.46),0 0 0 0 rgba(211,154,61,.2); } 75%,100% { box-shadow: 0 0 0 9px rgba(211,154,61,0),0 0 0 18px rgba(211,154,61,0); } }
@keyframes moving-marker-breathe { from { r: .7px; opacity: .72; } to { r: 1.05px; opacity: 1; } }
@keyframes cue-pulse { 0%,100% { opacity: .35; transform: scale(.8); } 50% { opacity: 1; transform: scale(1.25); } }
@keyframes route-flow { to { stroke-dashoffset: -22; } }
@container (max-width: 470px) { .documentary-heading, .map-mode-heading { align-items: stretch; display: grid; } .source-page-link, .map-ready-badge { justify-self: start; } .source-ledger-grid { grid-template-columns: 1fr; } .source-ledger-grid > div:nth-child(odd) { border-right: 0; } .document-map-viewport.diagram-active { aspect-ratio: auto; min-height: 230px; } .diagram-heading { display: none; } .annotation-label { gap: 0; min-width: 0; max-width: 82px; padding: 3px 4px; top: -10px; white-space: nowrap; width: max-content; } .annotation-label strong { font-size: 8px; line-height: 1.15; } .annotation-label small, .spatial-basis-badge small, .map-overlay-label { display: none; } .annotation-pulse { box-shadow: 0 0 0 4px rgba(168,59,45,.18),0 0 0 8px rgba(168,59,45,.07); height: 8px; left: -4px; top: -4px; width: 8px; } .map-stage-stamp { max-width: calc(100% - 146px); } .map-stage-stamp strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; } .spatial-basis-badge { max-width: 126px; } .narrative-stage-list { grid-template-columns: repeat(var(--stage-count),minmax(36px,1fr)); } .narrative-stage-list button strong { font-size: 7px; } .diagram-actor { gap: 3px; } .diagram-actor > i { font-size: 9px; height: 22px; width: 22px; } .diagram-actor > span { max-width: 66px; min-width: 0; padding: 4px 5px; width: max-content; } .diagram-actor strong { font-size: 10px; line-height: 1.2; overflow-wrap: anywhere; } .diagram-actor small { display: none; } .source-actions > span { margin-left: 0; width: 100%; } }
@media (prefers-reduced-motion: reduce) { .document-map-layer, .document-annotation, .diagram-actor, .follow-toggle i::after { transition: none; } .narrative-overlay.overlay-complete.overlay-narrative_connector, .annotation-event .annotation-pulse, .diagram-actor > i, .narrative-moving-marker, .active-animation-cue i { animation: none; } }
</style>

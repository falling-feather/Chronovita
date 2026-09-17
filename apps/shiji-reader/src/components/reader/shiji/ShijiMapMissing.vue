<template>
  <div
    class="map-mode map-data-missing"
    :class="{
      'map-place-context-mode': isPlaceContext,
      'map-no-spatial-mode': isNoSpatial,
    }"
  >
    <header class="map-mode-heading">
      <div>
        <strong>《史记》历史地图</strong>
        <span><i></i>正文联动接口 · 当前 {{ activeUnitLabel }}</span>
      </div>
      <button type="button" :aria-expanded="sourceOpen" @click="sourceOpen = !sourceOpen">
        <ShieldAlert :size="15" />
        {{ isPlaceContext ? "来源与精度" : "缺失与门禁" }}
        <ChevronDown :size="14" :class="{ open: sourceOpen }" />
      </button>
    </header>

    <template v-if="isPlaceContext">
      <section class="map-place-intro" aria-labelledby="map-place-title">
        <div class="map-missing-seal" aria-hidden="true"><MapPinned :size="30" /></div>
        <div>
          <p class="eyebrow">
            {{ hasContextMap ? "TEXTUAL GEOGRAPHY · VERIFIED CONTEXT" : "TEXTUAL GEOGRAPHY · UNLOCATED" }}
          </p>
          <h2 id="map-place-title">{{ eventMarkers.length ? "本篇事件线索与地理语境" : "本篇关键地理语境" }}</h2>
          <p>{{ props.map?.display_message || "本篇暂无合格事件地图，先标识正文中的关键地名。" }}</p>
        </div>
        <div class="map-follow-placeholder">
          <LocateFixed :size="15" />
          <span>正文已定位到 {{ activeUnitLabel }}</span>
          <strong>{{ activeMarker ? `当前正文：${activeMarker.label}` : markerCountLabel }}</strong>
        </div>
      </section>

      <section
        v-if="hasContextMap"
        class="map-context-stage"
        aria-label="经来源审定的地点语境图"
      >
        <div
          class="map-context-canvas"
          :style="contextBasemapStyle"
          role="img"
          :aria-label="`${contextBasemap?.title}；显示本篇 ${visibleContextPoints.length} 个地点语境点`"
        >
          <div class="map-context-wash" aria-hidden="true"></div>
          <button
            v-for="point in visibleContextPoints"
            :key="point.context_id"
            type="button"
            class="map-context-pin"
            :class="{
              active: isContextPointActive(point),
              physical: point.coordinate_role === 'physical_feature_context',
            }"
            :style="contextPointStyle(point)"
            :aria-label="`${point.canonical_name}，${coordinateRoleLabel(point.coordinate_role)}`"
            @click="selectedContextId = point.context_id"
          >
            <span><MapPin :size="13" /></span>
            <strong>{{ point.canonical_name }}</strong>
          </button>
          <div class="map-context-scale-note">
            <strong>{{ contextBasemap?.title }}</strong>
            <span>{{ contextViewportSummary }}</span>
          </div>
          <small class="map-context-attribution">{{ contextBasemap?.attribution }}</small>
        </div>
        <div v-if="focusedContextPoint" class="map-context-detail">
          <div>
            <span>{{ focusedContextStatusLabel }}</span>
            <strong>{{ focusedContextPoint.canonical_name }}</strong>
            <em>{{ coordinateRoleLabel(focusedContextPoint.coordinate_role) }}</em>
          </div>
          <p>{{ focusedContextPoint.curation.decision_reason }}</p>
          <small>
            WGS 84 · {{ formatCoordinate(focusedContextPoint.geometry.coordinates) }} ·
            {{ focusedContextPoint.confidence === "high" ? "高" : focusedContextPoint.confidence === "medium" ? "中" : "低" }}置信度
          </small>
        </div>
      </section>

      <section class="map-place-ledger" aria-label="本篇空间线索">
        <div v-if="eventMarkers.length" class="map-ledger-group map-event-group">
          <h3><CircleDashed :size="14" />待策展事件</h3>
          <article
            v-for="marker in eventMarkers"
            :key="marker.marker_id"
            class="event-candidate"
            :class="{ active: marker.marker_id === activeMarker?.marker_id }"
            :aria-current="marker.marker_id === activeMarker?.marker_id ? 'step' : undefined"
          >
            <header>
              <CircleDashed :size="15" />
              <strong>{{ marker.label }}</strong>
              <em>事件线索</em>
            </header>
            <p>{{ eventEvidence(marker) }}</p>
            <small>
              <span>{{ marker.anchor_scope === "body_sentence" ? `正文出现 ${marker.mention_count} 处` : anchorLabel(marker.anchor_scope) }}</span>
              <b>尚未定位 · 不生成路线</b>
            </small>
          </article>
        </div>

        <div class="map-ledger-group">
          <h3><MapPin :size="14" />正文关键地名</h3>
          <p v-if="omittedPlaceCount" class="map-ledger-disclosure">
            本篇共检出 {{ placeCandidateCount }} 个地名候选；当前按证据强度与篇章相关度展示
            {{ placeMarkers.length }} 个，另 {{ omittedPlaceCount }} 个保留在完整审校总账中。
          </p>
          <article
            v-for="marker in placeMarkers"
            :key="marker.marker_id"
            :class="{ active: marker.marker_id === activeMarker?.marker_id }"
            :aria-current="marker.marker_id === activeMarker?.marker_id ? 'location' : undefined"
          >
            <header>
              <MapPin :size="15" />
              <strong>{{ marker.label }}</strong>
              <em>{{ scopeLabel(marker.spatial_scope) }}</em>
            </header>
            <p>{{ marker.excerpt_traditional || marker.source_context || "来自篇章题名的地理语境。" }}</p>
            <small>
              <span>{{ marker.anchor_scope === "body_sentence" ? `正文出现 ${marker.mention_count} 处` : anchorLabel(marker.anchor_scope) }}</span>
              <b>{{ contextForMarker(marker)?.canonical_name ? "已有审定语境点" : "位置未核定 · 不生成坐标" }}</b>
            </small>
          </article>
        </div>
      </section>
    </template>

    <section v-else-if="isNoSpatial" class="map-missing-state" aria-labelledby="map-missing-title">
      <div class="map-missing-seal" aria-hidden="true"><MapPinned :size="32" /></div>
      <p class="eyebrow">NO SPATIAL CONTENT</p>
      <h2 id="map-missing-title">此处无地图动画演示。</h2>
      <p>本篇正文未检出可安全呈现的事件地图或关键地名；不会为填满界面而虚构点位、路线或动画。</p>
      <div class="map-follow-placeholder">
        <LocateFixed :size="15" />
        <span>正文已定位到 {{ activeUnitLabel }}</span>
        <strong>无空间演示</strong>
      </div>
    </section>

    <template v-else>
      <section class="map-missing-state" aria-labelledby="map-missing-title">
        <div class="map-missing-seal" aria-hidden="true"><MapPinned :size="32" /></div>
        <p class="eyebrow">MAP DATA · NOT PUBLISHED</p>
        <h2 id="map-missing-title">当前段尚无审定历史地图</h2>
        <p>阅读位置已经可驱动地图场景，但不会用现代底图、生成坐标或示意路线冒充史实。</p>
        <div class="map-follow-placeholder">
          <LocateFixed :size="15" />
          <span>正文已定位到 {{ activeUnitLabel }}</span>
          <strong>候选 {{ props.map?.chapter_candidate_count ?? 0 }} 项</strong>
        </div>
      </section>

      <section class="map-gap-ledger" aria-label="地图待补数据">
        <article v-for="item in missingItems" :key="item.label">
          <CircleDashed :size="16" />
          <div><strong>{{ item.label }}</strong><span>{{ item.detail }}</span></div>
          <em>待补</em>
        </article>
      </section>
    </template>

    <Transition name="source-disclosure">
      <section v-if="sourceOpen" class="map-source-panel">
        <div class="source-row">
          <span>本篇状态</span>
          <div>
            <strong>{{ sourceTitle }}</strong>
            <small>{{ sourceDetail }}</small>
          </div>
          <b :class="isPlaceContext ? 'confidence-medium' : 'confidence-high'">
            {{ isPlaceContext ? "候" : isNoSpatial ? "无" : "缺" }}
          </b>
        </div>
        <div class="source-row">
          <span>空间门禁</span>
          <div>
            <strong>有来源的古今位置 + 精度 + 时代 + 复核状态</strong>
            <small>当前文本标识只说明地名见于本篇，不声明它在地图上的现代对应位置。</small>
          </div>
          <b class="confidence-high">严</b>
        </div>
        <p class="source-warning">
          <Info :size="13" />
          {{ sourceWarning }}
        </p>
        <ul v-if="props.map?.missing_state.reasons.length" class="map-missing-reasons">
          <li v-for="reason in props.map.missing_state.reasons" :key="reason">{{ reason }}</li>
        </ul>
      </section>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  ChevronDown,
  CircleDashed,
  Info,
  LocateFixed,
  MapPin,
  MapPinned,
  ShieldAlert,
} from "@lucide/vue";
import type {
  ShijiMapContextPoint,
  ShijiMapSummary,
  ShijiSpatialMarker,
} from "../../../services/api";

const props = defineProps<{
  activeUnitLabel: string;
  activeUnitId: string;
  map?: ShijiMapSummary | null;
}>();

const sourceOpen = ref(true);
const selectedContextId = ref("");
const maxVisibleContextPoints = 6;
const eventMarkers = computed(() => props.map?.event_markers ?? []);
const placeMarkers = computed(() => props.map?.place_markers ?? []);
const contextPoints = computed(() => props.map?.context_points ?? []);
const contextBasemap = computed(() => props.map?.context_basemap ?? null);
const hasContextMap = computed(
  () => Boolean(contextBasemap.value?.render_ready && contextPoints.value.length),
);
const placeCandidateCount = computed(() =>
  Math.max(placeMarkers.value.length, props.map?.place_candidate_count ?? 0),
);
const omittedPlaceCount = computed(() =>
  Math.max(0, props.map?.place_markers_omitted ?? 0),
);
const isPlaceContext = computed(
  () => props.map?.spatial_state === "place_context" && placeMarkers.value.length > 0,
);
const isNoSpatial = computed(() => props.map?.spatial_state === "no_spatial_content");
const activeMarker = computed(() => {
  const matchesActiveUnit = (marker: ShijiSpatialMarker) =>
    marker.first_sentence_id === props.activeUnitId || marker.sentence_ids.includes(props.activeUnitId);
  return (
    eventMarkers.value.find(matchesActiveUnit)
    ?? placeMarkers.value.find(matchesActiveUnit)
    ?? null
  );
});
const readingContextPoints = computed(() => contextPoints.value.filter((point) =>
  point.bindings.some((binding) =>
    binding.first_sentence_id === props.activeUnitId
    || binding.sentence_ids.includes(props.activeUnitId),
  ),
));
const readingContextPoint = computed(() => readingContextPoints.value[0] ?? null);
const focusedContextPoint = computed(() =>
  contextPoints.value.find((point) => point.context_id === selectedContextId.value)
  ?? readingContextPoint.value
  ?? contextPoints.value[0]
  ?? null,
);
const focusedContextStatusLabel = computed(() => {
  if (selectedContextId.value) return "手动查看的语境点";
  if (readingContextPoints.value.length > 1) {
    return `随正文定位的 ${readingContextPoints.value.length} 个语境点之一`;
  }
  if (readingContextPoint.value) return "随正文定位的语境点";
  return "本篇首个审定语境点";
});
const visibleContextPoints = computed(() => {
  const focus = readingContextPoint.value;
  if (contextPoints.value.length <= maxVisibleContextPoints) return contextPoints.value;
  if (!focus) return contextPoints.value.slice(0, maxVisibleContextPoints);
  const [focusLongitude, focusLatitude] = focus.geometry.coordinates;
  const longitudeWeight = Math.cos((focusLatitude * Math.PI) / 180);
  const readingIds = new Set(
    readingContextPoints.value
      .slice(0, maxVisibleContextPoints)
      .map((point) => point.context_id),
  );
  const remainingSlots = maxVisibleContextPoints - readingIds.size;
  const nearbyPoints = contextPoints.value
    .filter((point) => !readingIds.has(point.context_id))
    .map((point, index) => {
      const [longitude, latitude] = point.geometry.coordinates;
      const longitudeDelta = (longitude - focusLongitude) * longitudeWeight;
      const latitudeDelta = latitude - focusLatitude;
      return {
        point,
        index,
        distance: longitudeDelta * longitudeDelta + latitudeDelta * latitudeDelta,
      };
    })
    .sort((left, right) => left.distance - right.distance || left.index - right.index)
    .slice(0, remainingSlots)
    .map(({ point }) => point);
  return [
    ...readingContextPoints.value.slice(0, maxVisibleContextPoints),
    ...nearbyPoints,
  ];
});
const contextViewportSummary = computed(() => {
  const subtitle = contextBasemap.value?.subtitle ?? "来源约束的地形语境";
  if (visibleContextPoints.value.length >= contextPoints.value.length) return subtitle;
  return `${subtitle} · 当前显示 ${visibleContextPoints.value.length}／${contextPoints.value.length} 点，其余随正文切换`;
});
const contextViewBounds = computed<[number, number, number, number]>(() => {
  const basemapBounds = contextBasemap.value?.bbox_wgs84 ?? [55, 5, 150, 60];
  const points = visibleContextPoints.value;
  if (!points.length) return basemapBounds;
  const longitudes = points.map((point) => point.geometry.coordinates[0]);
  const latitudes = points.map((point) => point.geometry.coordinates[1]);
  const centerLongitude = (Math.min(...longitudes) + Math.max(...longitudes)) / 2;
  const centerLatitude = (Math.min(...latitudes) + Math.max(...latitudes)) / 2;
  const targetRatio = 95 / 55;
  let longitudeSpan = Math.max(13.8, Math.max(...longitudes) - Math.min(...longitudes) + 5);
  let latitudeSpan = Math.max(8, Math.max(...latitudes) - Math.min(...latitudes) + 4);
  if (longitudeSpan / latitudeSpan < targetRatio) longitudeSpan = latitudeSpan * targetRatio;
  else latitudeSpan = longitudeSpan / targetRatio;
  longitudeSpan = Math.min(longitudeSpan, basemapBounds[2] - basemapBounds[0]);
  latitudeSpan = Math.min(latitudeSpan, basemapBounds[3] - basemapBounds[1]);
  let west = centerLongitude - longitudeSpan / 2;
  let east = centerLongitude + longitudeSpan / 2;
  let south = centerLatitude - latitudeSpan / 2;
  let north = centerLatitude + latitudeSpan / 2;
  if (west < basemapBounds[0]) {
    east += basemapBounds[0] - west;
    west = basemapBounds[0];
  }
  if (east > basemapBounds[2]) {
    west -= east - basemapBounds[2];
    east = basemapBounds[2];
  }
  if (south < basemapBounds[1]) {
    north += basemapBounds[1] - south;
    south = basemapBounds[1];
  }
  if (north > basemapBounds[3]) {
    south -= north - basemapBounds[3];
    north = basemapBounds[3];
  }
  return [west, south, east, north];
});
const contextBasemapStyle = computed(() => {
  const basemap = contextBasemap.value;
  if (!basemap) return {};
  const [mapWest, mapSouth, mapEast, mapNorth] = basemap.bbox_wgs84;
  const [viewWest, viewSouth, viewEast, viewNorth] = contextViewBounds.value;
  const mapLongitudeSpan = mapEast - mapWest;
  const mapLatitudeSpan = mapNorth - mapSouth;
  const viewLongitudeSpan = viewEast - viewWest;
  const viewLatitudeSpan = viewNorth - viewSouth;
  const horizontalRemainder = mapLongitudeSpan - viewLongitudeSpan;
  const verticalRemainder = mapLatitudeSpan - viewLatitudeSpan;
  const positionX = horizontalRemainder > 0
    ? ((viewWest - mapWest) / horizontalRemainder) * 100
    : 0;
  const positionY = verticalRemainder > 0
    ? ((mapNorth - viewNorth) / verticalRemainder) * 100
    : 0;
  return {
    backgroundImage: `url(${basemap.asset_url})`,
    backgroundSize: `${(mapLongitudeSpan / viewLongitudeSpan) * 100}% ${(mapLatitudeSpan / viewLatitudeSpan) * 100}%`,
    backgroundPosition: `${positionX}% ${positionY}%`,
  };
});
const markerCountLabel = computed(() => {
  const segments: string[] = [];
  if (eventMarkers.value.length) segments.push(`事件 ${eventMarkers.value.length}`);
  if (placeMarkers.value.length) {
    segments.push(
      omittedPlaceCount.value
        ? `地名 ${placeMarkers.value.length}／候选 ${placeCandidateCount.value}`
        : `地名 ${placeMarkers.value.length}`,
    );
  }
  return segments.length ? segments.join(" · ") : "暂无空间线索";
});
const sourceTitle = computed(() => {
  if (isPlaceContext.value && eventMarkers.value.length) return "事件线索与正文地名已建立可追溯锚点";
  if (isPlaceContext.value) return "正文地名已建立逐句锚点";
  if (isNoSpatial.value) return "正文无可用空间演示内容";
  return "地图资料尚未通过发布门禁";
});
const sourceDetail = computed(() => {
  if (isPlaceContext.value && eventMarkers.value.length) {
    return `${eventMarkers.value.length} 条事件线索、${placeMarkers.value.length} 个展示地名；其中 ${contextPoints.value.length} 个地点已有来源约束的语境点，完整地名候选 ${placeCandidateCount.value} 个。`;
  }
  if (isPlaceContext.value) {
    return `${placeMarkers.value.length} 个展示地名，其中 ${contextPoints.value.length} 个地点已有来源约束的语境点；完整地名候选 ${placeCandidateCount.value} 个。`;
  }
  return props.map?.warning || "只保留正文联动接口，没有发布未经核定的地图图层。";
});
const sourceWarning = computed(() => {
  if (isPlaceContext.value && eventMarkers.value.length) {
    return "事件仅列入策展候选；地图只呈现已通过同名消歧的语境点，未核地名仍不绘制，且不由点位推断路线。";
  }
  if (isPlaceContext.value) return "已审定点只作地理语境；未核地名继续保留文字标识，不将现代同名地点冒充古地望。";
  if (isNoSpatial.value) return "这是内容判断，不是加载错误；后续若发现可靠空间证据可重新修订。";
  return "地图缺口已登记；后续内容批次通过来源门禁后再启用。";
});

watch(
  () => props.map?.context_points,
  () => {
    if (!contextPoints.value.some((point) => point.context_id === selectedContextId.value)) {
      selectedContextId.value = "";
    }
  },
);

watch(
  () => props.activeUnitId,
  () => {
    selectedContextId.value = "";
  },
);

function contextForMarker(marker: ShijiSpatialMarker): ShijiMapContextPoint | null {
  return contextPoints.value.find((point) =>
    point.bindings.some((binding) => binding.marker_id === marker.marker_id),
  ) ?? null;
}

function isContextPointActive(point: ShijiMapContextPoint): boolean {
  if (selectedContextId.value) return point.context_id === selectedContextId.value;
  return readingContextPoints.value.some(
    (readingPoint) => readingPoint.context_id === point.context_id,
  );
}

function contextPointStyle(point: ShijiMapContextPoint): Record<string, string> {
  const [west, south, east, north] = contextViewBounds.value;
  const [longitude, latitude] = point.geometry.coordinates;
  return {
    left: `${((longitude - west) / (east - west)) * 100}%`,
    top: `${((north - latitude) / (north - south)) * 100}%`,
  };
}

function coordinateRoleLabel(role: ShijiMapContextPoint["coordinate_role"]): string {
  if (role === "historical_place_context") return "历史城市语境";
  if (role === "historical_site_context") return "历史遗址语境";
  if (role === "historical_landmark_context") return "历史关隘语境";
  if (role === "modern_protected_site_context") return "现代保护遗址语境";
  if (role === "physical_feature_context") return "连续自然地貌语境";
  return "现代承载地语境";
}

function formatCoordinate(coordinates: [number, number]): string {
  const [longitude, latitude] = coordinates;
  return `${Math.abs(longitude).toFixed(3)}°${longitude >= 0 ? "E" : "W"}，${Math.abs(latitude).toFixed(3)}°${latitude >= 0 ? "N" : "S"}`;
}

function scopeLabel(scope: ShijiSpatialMarker["spatial_scope"]): string {
  if (scope === "event_candidate") return "事件策展候选";
  if (scope === "historical_title_or_fief_context") return "封国／爵号语境";
  if (scope === "historical_region_context") return "历史区域语境";
  if (scope === "historical_polity_context") return "历史政权语境";
  if (scope === "curated_place_name") return "正文地名（已抽查）";
  return "正文地名候选";
}

function anchorLabel(scope: ShijiSpatialMarker["anchor_scope"]): string {
  return scope === "volume_title" ? "来自卷标题" : "来自篇章标题";
}

function eventEvidence(marker: ShijiSpatialMarker): string {
  if (marker.anchor_scope === "chapter_title" && marker.source_context) {
    return `篇题：${marker.source_context}`;
  }
  return marker.excerpt_traditional || marker.source_context || "正文中的事件候选。";
}

const missingItems = [
  { label: "正文场景锚点", detail: "阅读单元到地理场景、事件阶段的可追溯映射" },
  { label: "历史地名定位", detail: "时代、异名、坐标、误差范围与逐点来源" },
  { label: "审定历史底图", detail: "历史地形或政区图层、版本和使用许可" },
  { label: "事件动画脚本", detail: "人物到场、阶段顺序、争议与复核状态" },
];
</script>

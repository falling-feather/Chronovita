export interface EraMapViewport {
  x: number;
  y: number;
  w: number;
  h: number;
}

export const ERA_MAP_WIDTH = 1000;
export const ERA_MAP_HEIGHT = 720;
export const ERA_MAP_MIN_VIEW_WIDTH = 230;
export const ERA_MAP_MAX_VIEW_WIDTH = ERA_MAP_WIDTH;
export const ERA_MAP_INITIAL_VIEW: EraMapViewport = {
  x: 0,
  y: 0,
  w: ERA_MAP_WIDTH,
  h: ERA_MAP_HEIGHT,
};

const ASPECT_RATIO = ERA_MAP_HEIGHT / ERA_MAP_WIDTH;
const BOUNDARY_EPSILON = 0.5;

export function clampEraMapViewport(view: EraMapViewport): EraMapViewport {
  const w = Math.max(ERA_MAP_MIN_VIEW_WIDTH, Math.min(ERA_MAP_MAX_VIEW_WIDTH, view.w));
  const h = w * ASPECT_RATIO;
  return {
    x: Math.max(0, Math.min(ERA_MAP_WIDTH - w, view.x)),
    y: Math.max(0, Math.min(ERA_MAP_HEIGHT - h, view.y)),
    w,
    h,
  };
}

export function shouldCaptureEraMapWheel(view: EraMapViewport, deltaY: number): boolean {
  if (deltaY < 0) return view.w > ERA_MAP_MIN_VIEW_WIDTH + BOUNDARY_EPSILON;
  if (deltaY > 0) return view.w < ERA_MAP_MAX_VIEW_WIDTH - BOUNDARY_EPSILON;
  return false;
}

export function zoomEraMapAt(
  view: EraMapViewport,
  factor: number,
  relativeX = 0.5,
  relativeY = 0.5,
): EraMapViewport {
  const nextWidth = Math.max(
    ERA_MAP_MIN_VIEW_WIDTH,
    Math.min(ERA_MAP_MAX_VIEW_WIDTH, view.w * factor),
  );
  const nextHeight = nextWidth * ASPECT_RATIO;
  const anchorX = view.x + view.w * relativeX;
  const anchorY = view.y + view.h * relativeY;
  return clampEraMapViewport({
    x: anchorX - nextWidth * relativeX,
    y: anchorY - nextHeight * relativeY,
    w: nextWidth,
    h: nextHeight,
  });
}

export function panEraMapBy(
  view: EraMapViewport,
  deltaX: number,
  deltaY: number,
): EraMapViewport {
  return clampEraMapViewport({ ...view, x: view.x + deltaX, y: view.y + deltaY });
}

export function getEraMapZoomLevel(view: EraMapViewport): number {
  return ERA_MAP_WIDTH / view.w;
}

export function isEraMapAtMinimumZoom(view: EraMapViewport): boolean {
  return view.w >= ERA_MAP_MAX_VIEW_WIDTH - BOUNDARY_EPSILON;
}

export function isEraMapAtMaximumZoom(view: EraMapViewport): boolean {
  return view.w <= ERA_MAP_MIN_VIEW_WIDTH + BOUNDARY_EPSILON;
}

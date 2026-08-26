import { describe, expect, it } from 'vitest';
import {
  ERA_MAP_INITIAL_VIEW,
  ERA_MAP_MIN_VIEW_WIDTH,
  clampEraMapViewport,
  shouldCaptureEraMapWheel,
  zoomEraMapAt,
} from './eraMapViewport';

describe('era map viewport', () => {
  it('releases downward page scrolling at minimum zoom', () => {
    expect(shouldCaptureEraMapWheel(ERA_MAP_INITIAL_VIEW, 120)).toBe(false);
    expect(shouldCaptureEraMapWheel(ERA_MAP_INITIAL_VIEW, -120)).toBe(true);
  });

  it('captures zoom until the maximum boundary and then releases it', () => {
    const maximum = zoomEraMapAt(ERA_MAP_INITIAL_VIEW, 0.01);
    expect(maximum.w).toBe(ERA_MAP_MIN_VIEW_WIDTH);
    expect(shouldCaptureEraMapWheel(maximum, -120)).toBe(false);
    expect(shouldCaptureEraMapWheel(maximum, 120)).toBe(true);
  });

  it('keeps the pointer anchor stable while zooming', () => {
    const relativeX = 0.42;
    const relativeY = 0.58;
    const beforeX = ERA_MAP_INITIAL_VIEW.x + ERA_MAP_INITIAL_VIEW.w * relativeX;
    const beforeY = ERA_MAP_INITIAL_VIEW.y + ERA_MAP_INITIAL_VIEW.h * relativeY;
    const next = zoomEraMapAt(ERA_MAP_INITIAL_VIEW, 0.72, relativeX, relativeY);
    expect(next.x + next.w * relativeX).toBeCloseTo(beforeX, 5);
    expect(next.y + next.h * relativeY).toBeCloseTo(beforeY, 5);
  });

  it('clamps panning to the drawable map bounds', () => {
    const zoomed = zoomEraMapAt(ERA_MAP_INITIAL_VIEW, 0.5);
    expect(clampEraMapViewport({ ...zoomed, x: -999, y: -999 }).x).toBe(0);
    const bottomRight = clampEraMapViewport({ ...zoomed, x: 9999, y: 9999 });
    expect(bottomRight.x).toBe(1000 - zoomed.w);
    expect(bottomRight.y).toBe(720 - zoomed.h);
  });
});

import { describe, expect, it } from 'vitest';
import { getSolarPresentation } from './sundialModel';

describe('getSolarPresentation', () => {
  it.each([
    [6, 'dawn', '晨光初上'],
    [12, 'day', '日影正行'],
    [18, 'dusk', '暮色入卷'],
    [23, 'night', '星汉照史'],
  ] as const)('maps %s:00 to %s', (hour, period, label) => {
    const result = getSolarPresentation(new Date(2026, 7, 24, hour, 0));
    expect(result.period).toBe(period);
    expect(result.label).toBe(label);
  });

  it('keeps light direction deterministic for the same local time', () => {
    const date = new Date(2026, 7, 24, 14, 30);
    expect(getSolarPresentation(date).lightAzimuth).toBe(
      getSolarPresentation(new Date(date)).lightAzimuth,
    );
  });
});


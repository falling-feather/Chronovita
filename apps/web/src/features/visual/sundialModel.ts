export type SolarPeriod = 'dawn' | 'day' | 'dusk' | 'night';

export interface SolarPresentation {
  period: SolarPeriod;
  label: string;
  lightAzimuth: number;
  lightStrength: number;
  timeLabel: string;
}

const TWO_PI = Math.PI * 2;

export function getSolarPresentation(date: Date): SolarPresentation {
  const hour = date.getHours() + date.getMinutes() / 60;
  const period: SolarPeriod = hour >= 5 && hour < 8
    ? 'dawn'
    : hour >= 8 && hour < 17
      ? 'day'
      : hour >= 17 && hour < 20
        ? 'dusk'
        : 'night';
  const labels: Record<SolarPeriod, string> = {
    dawn: '晨光初上',
    day: '日影正行',
    dusk: '暮色入卷',
    night: '星汉照史',
  };
  const strength: Record<SolarPeriod, number> = {
    dawn: 1.45,
    day: 1.9,
    dusk: 1.35,
    night: 1.08,
  };

  return {
    period,
    label: labels[period],
    lightAzimuth: ((hour - 6) / 24) * TWO_PI,
    lightStrength: strength[period],
    timeLabel: new Intl.DateTimeFormat('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).format(date),
  };
}

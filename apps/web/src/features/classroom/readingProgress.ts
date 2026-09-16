import type { ProgressItem } from '../../utils/api';

export function readingLabel(item?: ProgressItem | null): string {
  if (!item) return '尚未开始阅读';
  return ({
    reading: '阅读中，尚未确认读完',
    completed: '已确认读完当前课文',
    outdated: '课文已更新，需要重新阅读',
    unverified: '旧版活动记录，尚未确认当前课文',
    unavailable: '课时已撤下，保留历史记录',
  })[item.reading_status ?? 'unverified'];
}

export function readingComplete(item?: ProgressItem | null): boolean {
  return item?.reading_status === 'completed';
}

export function resumeLayer(item: ProgressItem): string {
  return ['outdated', 'unverified'].includes(item.reading_status ?? 'unverified')
    ? 'watch' : item.last_layer;
}

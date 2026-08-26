import type { PersonCard } from '../../utils/api';
import { publicAssetUrl } from '../../runtime';

export const COMPANION_PORTRAIT_ROOT = '/assets/companions/portraits';

export interface CompanionPortraitAsset {
  lessonId: 'L101' | 'L103';
  slug: string;
  name: string;
  alt: string;
}

const ASSETS = [
  { lessonId: 'L101', slug: 'yu', name: '禹', alt: '治水时期身着劳动服、手持测量工具的禹教学立绘' },
  { lessonId: 'L101', slug: 'gun', name: '鲧', alt: '治水时期手扶木桩的鲧教学立绘' },
  { lessonId: 'L101', slug: 'yi', name: '益（伯益）', alt: '治水时期观察水势并记录的益教学立绘' },
  { lessonId: 'L101', slug: 'settlement-representative', name: '聚落代表', alt: '携带粮食并表达聚落诉求的聚落代表教学立绘' },
  { lessonId: 'L101', slug: 'flood-worker', name: '治水劳作者', alt: '肩扛工具的治水劳作者教学立绘' },
  { lessonId: 'L103', slug: 'shang-yang', name: '商鞅', alt: '战国秦制背景下手持法令竹简与度量器的商鞅教学立绘' },
  { lessonId: 'L103', slug: 'duke-xiao', name: '秦孝公', alt: '战国秦国服饰的秦孝公教学立绘' },
  { lessonId: 'L103', slug: 'hereditary-aristocrat', name: '旧贵族代表', alt: '战国秦国旧贵族代表教学立绘' },
  { lessonId: 'L103', slug: 'farming-household', name: '农耕家庭代表', alt: '携带粮食与量具的农耕家庭代表教学立绘' },
  { lessonId: 'L103', slug: 'merit-soldier', name: '军功士卒', alt: '身着战国秦式札甲的军功士卒教学立绘' },
  { lessonId: 'L103', slug: 'county-clerk', name: '县廷吏员', alt: '手持竹简与书写工具的县廷吏员教学立绘' },
] as const satisfies readonly CompanionPortraitAsset[];

export const COMPANION_PORTRAIT_ASSETS: readonly CompanionPortraitAsset[] = ASSETS;

function normalizedName(name: string): string {
  return name.replace(/[（(].*?[）)]/g, '').replace(/\s+/g, '');
}

export function companionPortraitFor(
  lessonId: string,
  person: Pick<PersonCard, 'name'>,
): CompanionPortraitAsset | null {
  const exact = ASSETS.find((asset) => asset.lessonId === lessonId && asset.name === person.name);
  if (exact) return exact;
  const normalized = normalizedName(person.name);
  return ASSETS.find(
    (asset) => asset.lessonId === lessonId && normalizedName(asset.name) === normalized,
  ) ?? null;
}

export function companionPortraitUrl(asset: CompanionPortraitAsset, width: 256 | 512): string {
  return publicAssetUrl(`${COMPANION_PORTRAIT_ROOT}/${asset.lessonId}-${asset.slug}-${width}.webp`);
}

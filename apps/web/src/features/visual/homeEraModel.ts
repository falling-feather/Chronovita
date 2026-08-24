export interface HomeEraPresentation {
  id: 'preqin' | 'qinhan' | 'weijin' | 'suitang' | 'songyuan' | 'mingqing';
  name: string;
  years: string;
  cover: string;
  subjectBase: string;
  subjectAlt: string;
  caption: string;
}

export const HOME_ERAS: readonly HomeEraPresentation[] = [
  {
    id: 'preqin',
    name: '先秦',
    years: '约前 2070—前 221',
    cover: '/assets/courses/covers/C-prequin-state-720.webp',
    subjectBase: '/assets/home-era/preqin',
    subjectAlt: '青铜礼器、甲骨片与河纹组成的先秦原创教学主体',
    caption: '礼制、文字与早期国家秩序逐渐成形',
  },
  {
    id: 'qinhan',
    name: '秦汉',
    years: '前 221—220',
    cover: '/assets/courses/covers/C-qinhan-founding-720.webp',
    subjectBase: '/assets/home-era/qinhan',
    subjectAlt: '甲士、铜马与印玺组成的秦汉原创教学主体',
    caption: '统一制度推动帝国治理，也塑造新的社会秩序',
  },
  {
    id: 'weijin',
    name: '魏晋南北朝',
    years: '220—589',
    cover: '/assets/courses/covers/C-weijin-fusion-720.webp',
    subjectBase: '/assets/home-era/weijin',
    subjectAlt: '持卷士人、石窟构件与飞带组成的魏晋南北朝原创教学主体',
    caption: '分裂与流动之间，思想、宗教与文化持续交汇',
  },
  {
    id: 'suitang',
    name: '隋唐',
    years: '581—907',
    cover: '/assets/courses/covers/C-suitang-tang-720.webp',
    subjectBase: '/assets/home-era/suitang',
    subjectAlt: '三彩风格骆驼、行囊与飘带组成的隋唐原创教学主体',
    caption: '交通、城市与多元交流共同打开盛世视野',
  },
  {
    id: 'songyuan',
    name: '宋元',
    years: '960—1368',
    cover: '/assets/courses/covers/C-songyuan-song-720.webp',
    subjectBase: '/assets/home-era/songyuan',
    subjectAlt: '海船、青瓷与司南意象组成的宋元原创教学主体',
    caption: '商业、技术与跨海网络重塑日常生活',
  },
  {
    id: 'mingqing',
    name: '明清',
    years: '1368—1912',
    cover: '/assets/courses/covers/C-mingqing-late-720.webp',
    subjectBase: '/assets/home-era/mingqing',
    subjectAlt: '青花瓷、长城城台与线装书组成的明清原创教学主体',
    caption: '制度、工艺与世界联系在延伸中发生转折',
  },
] as const;

export function nextHomeEraIndex(current: number): number {
  if (!Number.isFinite(current)) return 0;
  return (Math.max(0, Math.trunc(current)) + 1) % HOME_ERAS.length;
}

export function homeEraAsset(era: HomeEraPresentation, size: 640 | 1280): string {
  return `${era.subjectBase}-${size}.webp`;
}

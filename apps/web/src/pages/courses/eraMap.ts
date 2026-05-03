// 时空地图数据层 · 真实历史信息 · v0.2.2
// 所有几何点位均映射到 viewBox 1000×720 的中国版图坐标系。

export interface EraMapCity {
  name: string;
  x: number;
  y: number;
  /** 当代地名（鼠标悬停展示） */
  modern?: string;
  /** 是否为当时代主都/首都 */
  capital?: boolean;
}

export interface EraMapEvent {
  /** 公元年份，正数为公元后，负数为公元前 */
  year: number;
  text: string;
}

export interface EraOverlay {
  id: string;
  name: string;
  period: string;
  /** 时间轴归一化进度 (0–1) — 主要时点 */
  anchor: number;
  /** 当代色调（用于地图背景渐变 + 河流润色） */
  hue: { primary: string; secondary: string };
  /** 一句话气韵 */
  blurb: string;
  cities: EraMapCity[];
  events: EraMapEvent[];
  /** 当代具有代表性的疆域注脚（短语） */
  frontier: string;
}

// 6 个时代 — id 与 services/courses/__init__.py 中的 ERAS 一致。
export const ERA_OVERLAYS: EraOverlay[] = [
  {
    id: 'prequin',
    name: '先秦',
    period: '前 2070 — 前 221',
    anchor: 0.05,
    hue: { primary: '#3D5A6C', secondary: '#1F2D3A' },
    blurb: '夏商周三代奠定礼乐制度，诸侯林立，百家争鸣。',
    cities: [
      { name: '镐京', modern: '西安', x: 388, y: 376, capital: true },
      { name: '洛邑', modern: '洛阳', x: 462, y: 374, capital: true },
      { name: '曲阜', modern: '曲阜', x: 560, y: 380 },
      { name: '临淄', modern: '淄博', x: 590, y: 348 },
      { name: '咸阳', modern: '咸阳', x: 380, y: 372 },
      { name: '安阳', modern: '安阳', x: 510, y: 340 },
    ],
    events: [
      { year: -1046, text: '武王伐纣 · 周代商' },
      { year: -770, text: '平王东迁 · 春秋开端' },
      { year: -221, text: '秦灭六国 · 一统天下' },
    ],
    frontier: '诸夏分封 · 戎狄环伺',
  },
  {
    id: 'qinhan',
    name: '秦汉',
    period: '前 221 — 220',
    anchor: 0.22,
    hue: { primary: '#7A2E2E', secondary: '#2A1818' },
    blurb: '郡县制确立，长城连缀，丝路开通，大一统帝国奠基。',
    cities: [
      { name: '咸阳', modern: '咸阳', x: 380, y: 372, capital: true },
      { name: '长安', modern: '西安', x: 388, y: 378, capital: true },
      { name: '洛阳', modern: '洛阳', x: 462, y: 374, capital: true },
      { name: '会稽', modern: '绍兴', x: 650, y: 442 },
      { name: '番禺', modern: '广州', x: 560, y: 582 },
      { name: '敦煌', modern: '敦煌', x: 232, y: 290 },
    ],
    events: [
      { year: -221, text: '嬴政称皇帝 · 始皇制' },
      { year: -138, text: '张骞凿空 · 开通西域' },
      { year: 25, text: '光武中兴 · 东汉立洛阳' },
    ],
    frontier: '北抗匈奴 · 西通西域',
  },
  {
    id: 'weijin',
    name: '魏晋南北朝',
    period: '220 — 589',
    anchor: 0.42,
    hue: { primary: '#5C6B8A', secondary: '#1F2638' },
    blurb: '三国鼎立、衣冠南渡、五胡入华，胡汉文明走向交融。',
    cities: [
      { name: '洛阳', modern: '洛阳', x: 462, y: 374, capital: true },
      { name: '建康', modern: '南京', x: 600, y: 432, capital: true },
      { name: '邺城', modern: '临漳', x: 510, y: 344, capital: true },
      { name: '平城', modern: '大同', x: 488, y: 282, capital: true },
      { name: '凉州', modern: '武威', x: 286, y: 322 },
      { name: '成都', modern: '成都', x: 360, y: 470 },
    ],
    events: [
      { year: 220, text: '曹丕代汉 · 三国鼎立' },
      { year: 317, text: '司马睿渡江 · 东晋立建康' },
      { year: 494, text: '孝文帝迁都洛阳 · 汉化改革' },
    ],
    frontier: '南北对峙 · 胡汉交融',
  },
  {
    id: 'suitang',
    name: '隋唐',
    period: '581 — 907',
    anchor: 0.6,
    hue: { primary: '#C9A35E', secondary: '#3A2A12' },
    blurb: '科举新生，运河贯通，长安成为世界都会，丝路海陆并兴。',
    cities: [
      { name: '长安', modern: '西安', x: 388, y: 378, capital: true },
      { name: '洛阳', modern: '洛阳', x: 462, y: 374, capital: true },
      { name: '扬州', modern: '扬州', x: 582, y: 410 },
      { name: '广州', modern: '广州', x: 560, y: 582 },
      { name: '敦煌', modern: '敦煌', x: 232, y: 290 },
      { name: '太原', modern: '太原', x: 478, y: 320 },
    ],
    events: [
      { year: 605, text: '隋开凿大运河' },
      { year: 626, text: '玄武门之变 · 贞观开元' },
      { year: 755, text: '安史之乱 · 由盛转衰' },
    ],
    frontier: '都护四方 · 万邦来朝',
  },
  {
    id: 'songyuan',
    name: '宋元',
    period: '960 — 1368',
    anchor: 0.78,
    hue: { primary: '#5B8FA8', secondary: '#1B2A36' },
    blurb: '商业革命与海贸兴起，宋词理学并茂，蒙元横跨欧亚。',
    cities: [
      { name: '汴京', modern: '开封', x: 488, y: 380, capital: true },
      { name: '临安', modern: '杭州', x: 632, y: 462, capital: true },
      { name: '上京', modern: '哈尔滨', x: 700, y: 218 },
      { name: '大都', modern: '北京', x: 562, y: 278, capital: true },
      { name: '泉州', modern: '泉州', x: 600, y: 540 },
      { name: '中都', modern: '北京', x: 562, y: 282 },
    ],
    events: [
      { year: 960, text: '陈桥兵变 · 宋立汴京' },
      { year: 1127, text: '靖康之变 · 南渡临安' },
      { year: 1279, text: '崖山之战 · 元一统四海' },
    ],
    frontier: '海舶通蕃 · 草原汗国',
  },
  {
    id: 'mingqing',
    name: '明清',
    period: '1368 — 1912',
    anchor: 0.95,
    hue: { primary: '#8C1F28', secondary: '#2A0D11' },
    blurb: '皇权极盛，海禁与航海并行；西学东渐，盛极而困。',
    cities: [
      { name: '南京', modern: '南京', x: 600, y: 432, capital: true },
      { name: '北京', modern: '北京', x: 562, y: 278, capital: true },
      { name: '广州', modern: '广州', x: 560, y: 582 },
      { name: '盛京', modern: '沈阳', x: 656, y: 256, capital: true },
      { name: '台南', modern: '台南', x: 670, y: 588 },
      { name: '伊犁', modern: '伊宁', x: 178, y: 252 },
    ],
    events: [
      { year: 1368, text: '朱元璋立明 · 都南京' },
      { year: 1644, text: '甲申之变 · 清入关' },
      { year: 1840, text: '鸦片战争 · 千年变局' },
    ],
    frontier: '海禁开关 · 边疆奠定',
  },
];

// 中国轮廓 SVG path（手绘简化, 1000×720, 不依赖外部资源）
// 设计思路：覆盖东北—华北—西北—西南—东南的关键拐点，能让人一眼辨出"中国"形状。
export const CHINA_OUTLINE =
  'M 110 240 ' +
  'C 130 195 175 175 220 175 ' +
  'C 250 158 285 145 320 130 ' +
  'C 360 120 410 110 460 102 ' +
  'C 510 95 555 85 600 90 ' +
  'C 645 95 685 110 715 145 ' +
  'C 745 175 760 215 770 245 ' +
  'C 780 270 785 295 778 322 ' +
  'C 770 350 760 372 752 400 ' +
  'C 758 432 752 462 740 488 ' +
  'C 728 510 715 530 695 542 ' +
  'C 678 555 660 568 640 580 ' +
  'C 615 600 595 615 580 632 ' +
  'C 560 645 540 650 522 638 ' +
  'C 510 632 498 622 488 612 ' +
  'C 472 605 458 600 442 600 ' +
  'C 425 602 408 605 392 600 ' +
  'C 376 595 360 588 348 575 ' +
  'C 332 562 320 550 312 530 ' +
  'C 305 510 295 495 280 488 ' +
  'C 260 480 240 472 222 460 ' +
  'C 200 448 180 432 165 412 ' +
  'C 150 392 138 372 130 348 ' +
  'C 122 322 115 295 110 270 Z';

// 9 大水系 — 高度简化但形态可辨，保留中国地理记忆点
export const RIVERS = [
  // 黄河 · 经典 "几" 字大弯
  {
    id: 'yellow',
    name: '黄河',
    color: '#D4A95C',
    geometry:
      'M 240 320 C 280 305 320 320 350 295 C 380 275 410 260 430 240 C 455 220 480 240 490 270 C 498 300 488 330 470 348 C 450 365 432 378 442 396 C 455 415 485 395 510 380 C 545 360 580 372 612 380',
  },
  // 长江 · 上中下游
  {
    id: 'yangtze',
    name: '长江',
    color: '#5BA3D0',
    geometry:
      'M 240 480 C 290 462 340 470 380 462 C 420 455 458 442 488 438 C 522 435 555 442 586 446 C 618 450 650 452 680 458',
  },
  // 珠江
  {
    id: 'pearl',
    name: '珠江',
    color: '#5BA3D0',
    geometry:
      'M 380 562 C 430 552 480 568 520 572 C 555 575 580 580 605 582',
  },
  // 雅鲁藏布江
  {
    id: 'yarlung',
    name: '雅鲁藏布江',
    color: '#5BA3D0',
    geometry: 'M 130 470 C 170 458 220 462 260 470 C 295 478 320 482 340 478',
  },
  // 澜沧江-湄公河
  {
    id: 'lancang',
    name: '澜沧江',
    color: '#5BA3D0',
    geometry: 'M 305 460 C 318 490 322 520 332 548 C 340 575 348 595 360 615',
  },
  // 松花江
  {
    id: 'songhua',
    name: '松花江',
    color: '#5BA3D0',
    geometry: 'M 615 195 C 650 215 685 232 712 252 C 728 268 738 282 740 295',
  },
  // 辽河
  {
    id: 'liao',
    name: '辽河',
    color: '#5BA3D0',
    geometry: 'M 600 268 C 615 290 628 310 645 325',
  },
  // 海河
  {
    id: 'hai',
    name: '海河',
    color: '#5BA3D0',
    geometry: 'M 510 312 C 530 322 548 332 562 340',
  },
  // 淮河
  {
    id: 'huai',
    name: '淮河',
    color: '#5BA3D0',
    geometry: 'M 478 410 C 510 412 545 415 580 418',
  },
];

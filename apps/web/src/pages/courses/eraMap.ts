// 时空地图数据层 · 真实历史信息 · v0.2.8
// 所有几何点位均映射到 viewBox 1000×720 的中国版图坐标系。
// v0.2.8：地名严格对应所属朝代；引入子时段（subEra）切换，城市与事件都打 dynasty 标签。

export interface EraMapCity {
  /** 当时代名（如：镐京、咸阳、长安、雒阳、临安） */
  name: string;
  x: number;
  y: number;
  /** 当代地名（鼠标悬停展示，括号显示） */
  modern?: string;
  /** 是否为该子时段的主都/首都 */
  capital?: boolean;
  /** 所属王朝/政权 — 用于子时段过滤；不填则视为该时代通用城市，任何子段都显示 */
  dynasty?: string;
  /** 一句话注解（tooltip 二行） */
  note?: string;
}

export interface EraMapEvent {
  /** 公元年份，正数为公元后，负数为公元前 */
  year: number;
  text: string;
  /** 所属王朝/政权；用于子时段过滤 */
  dynasty?: string;
}

/** 子时段：一个大时代下更细的政权切片 */
export interface EraSubPeriod {
  id: string;
  name: string;
  period: string;
  /** 命中哪些 dynasty 标签 — 用于过滤 cities/events */
  dynasties: string[];
}

export interface EraMapTrack {
  id: string;
  /** 线名 */
  name: string;
  /** SVG path（M..C..L 等） */
  geometry: string;
  /** 颜色 */
  color: string;
  /** 虚线样式 */
  dash?: string;
  /** 线宽 */
  width?: number;
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
  /** 当代历史路径（长城/丝路/运河/航路 …） */
  tracks?: EraMapTrack[];
  /** 子时段（朝代切片）；UI 提供 chip 切换以保证地名严格对应朝代 */
  subEras?: EraSubPeriod[];
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
      // —— 夏商 ——
      { name: '阳城', modern: '登封', x: 478, y: 388, capital: true, dynasty: '夏', note: '夏都，二里头文化中心' },
      { name: '殷', modern: '安阳', x: 510, y: 340, capital: true, dynasty: '商', note: '盘庚迁殷，殷墟所在' },
      { name: '亳', modern: '商丘', x: 528, y: 386, dynasty: '商', note: '商汤所都' },
      // —— 西周 ——
      { name: '镐京', modern: '西安西南', x: 384, y: 380, capital: true, dynasty: '西周', note: '西周宗周，沣水之东' },
      { name: '丰京', modern: '西安西南', x: 378, y: 384, dynasty: '西周', note: '文王所建，与镐京并称丰镐' },
      { name: '成周', modern: '洛阳', x: 462, y: 374, capital: true, dynasty: '西周', note: '周公营洛邑以镇东土' },
      // —— 春秋战国 ——
      { name: '洛邑', modern: '洛阳', x: 466, y: 376, capital: true, dynasty: '东周', note: '平王东迁所在' },
      { name: '曲阜', modern: '曲阜', x: 560, y: 380, dynasty: '鲁', note: '鲁国都，孔子故里' },
      { name: '临淄', modern: '淄博', x: 590, y: 348, dynasty: '齐', note: '齐都，稷下学宫' },
      { name: '新郑', modern: '新郑', x: 484, y: 388, dynasty: '韩', note: '郑国旧都，后为韩都' },
      { name: '邯郸', modern: '邯郸', x: 514, y: 332, dynasty: '赵', note: '赵都，胡服骑射' },
      { name: '郢', modern: '荆州', x: 488, y: 458, dynasty: '楚', note: '楚国都，长江中游' },
      { name: '大梁', modern: '开封', x: 488, y: 380, dynasty: '魏', note: '战国魏都' },
      { name: '蓟', modern: '北京', x: 562, y: 282, dynasty: '燕', note: '燕国都' },
      { name: '咸阳', modern: '咸阳', x: 380, y: 372, dynasty: '秦', note: '秦孝公迁都于此（前 350）' },
    ],
    events: [
      { year: -2070, text: '夏禹建国 · 王朝肇始', dynasty: '夏' },
      { year: -1600, text: '商汤伐桀 · 殷商代夏', dynasty: '商' },
      { year: -1300, text: '盘庚迁殷 · 商室中兴', dynasty: '商' },
      { year: -1046, text: '武王伐纣 · 周代商', dynasty: '西周' },
      { year: -770, text: '平王东迁 · 春秋开端', dynasty: '东周' },
      { year: -551, text: '孔子生于鲁 · 儒学发轫', dynasty: '鲁' },
      { year: -350, text: '商鞅变法 · 秦孝公迁都咸阳', dynasty: '秦' },
      { year: -221, text: '秦灭六国 · 一统天下', dynasty: '秦' },
    ],
    frontier: '诸夏分封 · 戎狄环伺',
    subEras: [
      { id: 'xia-shang', name: '夏商', period: '前 2070 — 前 1046', dynasties: ['夏', '商'] },
      { id: 'xizhou', name: '西周', period: '前 1046 — 前 771', dynasties: ['西周'] },
      { id: 'chunqiu-zhanguo', name: '春秋战国', period: '前 770 — 前 221', dynasties: ['东周', '鲁', '齐', '韩', '赵', '楚', '魏', '燕', '秦'] },
    ],
    tracks: [
      {
        id: 'zhou-fengjian',
        name: '周王畿与诸侯封域',
        color: '#C9A46E',
        dash: '6 6',
        width: 1.4,
        geometry: 'M 380 320 C 460 305 540 305 620 320 C 660 360 660 410 620 440 C 540 460 460 460 380 440 C 340 410 340 360 380 320 Z',
      },
    ],
  },
  {
    id: 'qinhan',
    name: '秦汉',
    period: '前 221 — 220',
    anchor: 0.22,
    hue: { primary: '#7A2E2E', secondary: '#2A1818' },
    blurb: '郡县制确立，长城连缀，丝路开通，大一统帝国奠基。',
    cities: [
      // —— 秦 ——
      { name: '咸阳', modern: '咸阳', x: 380, y: 372, capital: true, dynasty: '秦', note: '秦帝国都，前 221—前 207' },
      { name: '会稽', modern: '绍兴', x: 650, y: 442, dynasty: '秦', note: '秦三十六郡之会稽郡治' },
      // —— 西汉 ——
      { name: '长安', modern: '西安', x: 388, y: 378, capital: true, dynasty: '西汉', note: '汉高帝七年定都，《史记》"长安"始名' },
      { name: '雒阳', modern: '洛阳', x: 462, y: 374, dynasty: '西汉', note: '汉初曾短暂定都，后为陪都' },
      { name: '番禺', modern: '广州', x: 560, y: 582, dynasty: '西汉', note: '南越国都，元鼎六年汉灭南越置南海郡' },
      { name: '敦煌', modern: '敦煌', x: 232, y: 290, dynasty: '西汉', note: '武帝元鼎六年置敦煌郡，河西四郡之一' },
      { name: '朔方', modern: '杭锦旗', x: 408, y: 256, dynasty: '西汉', note: '元朔二年卫青破匈奴所置，汉北疆要塞' },
      { name: '成都', modern: '成都', x: 360, y: 470, dynasty: '西汉', note: '蜀郡治所，汉之天府' },
      // —— 新 ——
      { name: '常安', modern: '西安', x: 386, y: 380, capital: true, dynasty: '新', note: '王莽改长安曰常安' },
      // —— 东汉 ——
      { name: '雒阳', modern: '洛阳', x: 462, y: 372, capital: true, dynasty: '东汉', note: '光武中兴所都，东汉改"洛"为"雒"' },
      { name: '宛', modern: '南阳', x: 488, y: 412, dynasty: '东汉', note: '南阳郡治，光武龙兴之地' },
      { name: '许', modern: '许昌', x: 488, y: 392, dynasty: '东汉', note: '建安元年献帝徙都于此' },
    ],
    events: [
      { year: -221, text: '嬴政称皇帝 · 始皇制', dynasty: '秦' },
      { year: -214, text: '蒙恬北击匈奴 · 修筑秦长城', dynasty: '秦' },
      { year: -202, text: '刘邦定都长安 · 开启汉室', dynasty: '西汉' },
      { year: -138, text: '张骞凿空西域 · 丝路初辟', dynasty: '西汉' },
      { year: -111, text: '汉武帝平南越 · 番禺归汉', dynasty: '西汉' },
      { year: 9, text: '王莽篡汉 · 改长安为常安', dynasty: '新' },
      { year: 25, text: '光武中兴 · 东汉立雒阳', dynasty: '东汉' },
      { year: 105, text: '蔡伦改良造纸术', dynasty: '东汉' },
    ],
    frontier: '北抗匈奴 · 西通西域 · 南达交趾',
    subEras: [
      { id: 'qin', name: '秦', period: '前 221 — 前 207', dynasties: ['秦'] },
      { id: 'xihan', name: '西汉 / 新', period: '前 202 — 23', dynasties: ['西汉', '新'] },
      { id: 'donghan', name: '东汉', period: '25 — 220', dynasties: ['东汉'] },
    ],
    tracks: [
      {
        id: 'great-wall-han',
        name: '汉长城',
        color: '#E8D7A8',
        dash: '4 5',
        width: 1.6,
        geometry: 'M 200 270 L 270 258 L 360 248 L 460 240 L 550 232 L 640 232 L 720 246',
      },
      {
        id: 'silk-road',
        name: '丝绸之路（陆路）',
        color: '#E2A03F',
        dash: '8 4',
        width: 1.8,
        geometry: 'M 388 378 C 340 360 295 340 250 308 C 200 282 150 268 110 250',
      },
    ],
  },
  {
    id: 'weijin',
    name: '魏晋南北朝',
    period: '220 — 589',
    anchor: 0.42,
    hue: { primary: '#5C6B8A', secondary: '#1F2638' },
    blurb: '三国鼎立、衣冠南渡、五胡入华，胡汉文明走向交融。',
    cities: [
      // —— 三国 ——
      { name: '洛阳', modern: '洛阳', x: 462, y: 374, capital: true, dynasty: '曹魏', note: '黄初元年曹丕受禅，定都洛阳' },
      { name: '邺城', modern: '临漳', x: 510, y: 344, dynasty: '曹魏', note: '魏王所封五都之一，文学之乡' },
      { name: '建业', modern: '南京', x: 600, y: 432, capital: true, dynasty: '东吴', note: '吴大帝孙权改秣陵曰建业' },
      { name: '武昌', modern: '鄂州', x: 538, y: 458, dynasty: '东吴', note: '孙权一度迁都于此' },
      { name: '成都', modern: '成都', x: 360, y: 470, capital: true, dynasty: '蜀汉', note: '昭烈帝章武元年称帝于此' },
      // —— 西晋 ——
      { name: '洛阳', modern: '洛阳', x: 462, y: 372, capital: true, dynasty: '西晋', note: '泰始元年司马炎篡魏，仍都洛阳' },
      // —— 东晋 / 南朝 ——
      { name: '建康', modern: '南京', x: 600, y: 432, capital: true, dynasty: '东晋', note: '建武元年司马睿渡江南渡，改建业为建康' },
      { name: '江陵', modern: '荆州', x: 488, y: 458, dynasty: '东晋', note: '荆州治所，长江中游军政中心' },
      // —— 北朝 ——
      { name: '平城', modern: '大同', x: 488, y: 282, capital: true, dynasty: '北魏', note: '道武帝天兴元年迁都平城' },
      { name: '洛阳', modern: '洛阳', x: 462, y: 376, dynasty: '北魏', note: '孝文帝太和十八年迁都洛阳，推汉化' },
      { name: '邺城', modern: '临漳', x: 510, y: 346, capital: true, dynasty: '东魏', note: '东魏、北齐相继定都' },
      { name: '长安', modern: '西安', x: 388, y: 378, capital: true, dynasty: '北周', note: '西魏、北周相继定都' },
      // —— 凉州/西陲 ——
      { name: '姑臧', modern: '武威', x: 286, y: 322, dynasty: '前凉', note: '凉州治所，前凉、后凉、北凉均都于此' },
    ],
    events: [
      { year: 220, text: '曹丕代汉 · 三国鼎立', dynasty: '曹魏' },
      { year: 221, text: '刘备称帝 · 建蜀都成都', dynasty: '蜀汉' },
      { year: 229, text: '孙权称帝 · 迁都建业', dynasty: '东吴' },
      { year: 280, text: '西晋灭吴 · 短暂一统', dynasty: '西晋' },
      { year: 317, text: '司马睿渡江 · 东晋立建康', dynasty: '东晋' },
      { year: 383, text: '淝水之战 · 北方分崩', dynasty: '东晋' },
      { year: 398, text: '北魏定都平城', dynasty: '北魏' },
      { year: 494, text: '孝文帝迁都洛阳 · 全面汉化', dynasty: '北魏' },
    ],
    frontier: '南北对峙 · 胡汉交融',
    subEras: [
      { id: 'sanguo', name: '三国', period: '220 — 280', dynasties: ['曹魏', '蜀汉', '东吴'] },
      { id: 'liangjin', name: '两晋', period: '266 — 420', dynasties: ['西晋', '东晋'] },
      { id: 'nanbeichao', name: '南北朝', period: '420 — 589', dynasties: ['北魏', '东魏', '北周', '前凉'] },
    ],
    tracks: [
      {
        id: 'wei-jin-divide',
        name: '南北分界（淮河—秦岭）',
        color: '#A6B4D0',
        dash: '5 5',
        width: 1.6,
        geometry: 'M 250 410 C 320 400 400 405 480 410 C 560 415 640 422 720 432',
      },
      {
        id: 'yiguan-nandu',
        name: '衣冠南渡',
        color: '#9BB7E2',
        dash: '2 6',
        width: 1.6,
        geometry: 'M 462 374 C 510 388 555 408 600 432',
      },
    ],
  },
  {
    id: 'suitang',
    name: '隋唐',
    period: '581 — 907',
    anchor: 0.6,
    hue: { primary: '#C9A35E', secondary: '#3A2A12' },
    blurb: '科举新生，运河贯通，长安成为世界都会，丝路海陆并兴。',
    cities: [
      // —— 隋 ——
      { name: '大兴', modern: '西安', x: 388, y: 378, capital: true, dynasty: '隋', note: '开皇二年宇文恺新建，唐初改名长安' },
      { name: '东京', modern: '洛阳', x: 462, y: 374, capital: true, dynasty: '隋', note: '隋炀帝大业元年营建' },
      { name: '江都', modern: '扬州', x: 582, y: 410, dynasty: '隋', note: '隋炀帝南巡所幸，运河南端' },
      // —— 唐 ——
      { name: '长安', modern: '西安', x: 388, y: 380, capital: true, dynasty: '唐', note: '唐西京，鼎盛时人口百万' },
      { name: '洛阳', modern: '洛阳', x: 462, y: 376, capital: true, dynasty: '唐', note: '唐东都，武周改"神都"' },
      { name: '广州', modern: '广州', x: 560, y: 582, dynasty: '唐', note: '唐设市舶使，海上丝路终点' },
      { name: '扬州', modern: '扬州', x: 582, y: 410, dynasty: '唐', note: '唐"扬一益二"之首，运河枢纽' },
      { name: '益州', modern: '成都', x: 360, y: 470, dynasty: '唐', note: '剑南道治，玄宗安史之乱幸蜀' },
      { name: '太原', modern: '太原', x: 478, y: 320, dynasty: '唐', note: '唐北都，李渊起兵之地' },
      { name: '幽州', modern: '北京', x: 562, y: 282, dynasty: '唐', note: '范阳节度使治，安禄山起兵之地' },
      { name: '凉州', modern: '武威', x: 286, y: 322, dynasty: '唐', note: '河西节度使治，西陲第一大都会' },
      { name: '安西', modern: '库车', x: 156, y: 286, dynasty: '唐', note: '安西都护府治，唐控西域之心' },
      { name: '北庭', modern: '吉木萨尔', x: 178, y: 252, dynasty: '唐', note: '北庭都护府治，扼天山北道' },
      { name: '逻些', modern: '拉萨', x: 200, y: 510, dynasty: '吐蕃', note: '吐蕃王城，松赞干布所定' },
    ],
    events: [
      { year: 581, text: '杨坚立隋 · 南北统一', dynasty: '隋' },
      { year: 605, text: '隋炀帝开凿大运河', dynasty: '隋' },
      { year: 618, text: '李渊建唐 · 定鼎长安', dynasty: '唐' },
      { year: 626, text: '玄武门之变 · 贞观开元', dynasty: '唐' },
      { year: 641, text: '文成公主入藏', dynasty: '吐蕃' },
      { year: 690, text: '武则天称帝 · 改东都为神都', dynasty: '唐' },
      { year: 755, text: '安史之乱 · 由盛转衰', dynasty: '唐' },
      { year: 875, text: '黄巢起义 · 唐祚将尽', dynasty: '唐' },
    ],
    frontier: '都护四方 · 万邦来朝',
    subEras: [
      { id: 'sui', name: '隋', period: '581 — 618', dynasties: ['隋'] },
      { id: 'tang', name: '唐', period: '618 — 907', dynasties: ['唐', '吐蕃'] },
    ],
    tracks: [
      {
        id: 'grand-canal-sui',
        name: '隋唐大运河',
        color: '#C9A35E',
        dash: '7 4',
        width: 1.9,
        geometry: 'M 540 290 C 525 320 488 350 488 380 C 488 405 540 410 582 410 C 612 426 626 446 632 462',
      },
      {
        id: 'silk-road-tang',
        name: '丝绸之路（盛唐）',
        color: '#E2A03F',
        dash: '8 4',
        width: 1.8,
        geometry: 'M 388 378 C 320 350 250 318 178 286 C 130 270 100 262 80 262',
      },
      {
        id: 'sea-silk-tang',
        name: '海上丝路',
        color: '#5BA3D0',
        dash: '3 6',
        width: 1.6,
        geometry: 'M 560 582 C 600 610 640 640 660 670',
      },
    ],
  },
  {
    id: 'songyuan',
    name: '宋元',
    period: '960 — 1368',
    anchor: 0.78,
    hue: { primary: '#5B8FA8', secondary: '#1B2A36' },
    blurb: '商业革命与海贸兴起，宋词理学并茂，蒙元横跨欧亚。',
    cities: [
      // —— 北宋 ——
      { name: '东京汴梁', modern: '开封', x: 488, y: 380, capital: true, dynasty: '北宋', note: '北宋四京之首，《清明上河图》之城' },
      { name: '西京', modern: '洛阳', x: 462, y: 374, dynasty: '北宋', note: '北宋陪都，理学发轫' },
      { name: '南京应天府', modern: '商丘', x: 528, y: 386, dynasty: '北宋', note: '宋太祖发迹地，北宋陪都' },
      { name: '北京大名府', modern: '大名', x: 514, y: 340, dynasty: '北宋', note: '北宋四京之北京' },
      // —— 南宋 ——
      { name: '临安', modern: '杭州', x: 632, y: 462, capital: true, dynasty: '南宋', note: '高宗绍兴八年定为行在所' },
      { name: '建康', modern: '南京', x: 600, y: 432, dynasty: '南宋', note: '南宋留都，江防重镇' },
      // —— 辽 ——
      { name: '上京临潢府', modern: '巴林左旗', x: 558, y: 222, capital: true, dynasty: '辽', note: '辽太祖耶律阿保机所建' },
      // —— 西夏 ——
      { name: '兴庆府', modern: '银川', x: 350, y: 290, capital: true, dynasty: '西夏', note: '李元昊于天授礼法延祚元年称帝定都' },
      // —— 金 ——
      { name: '上京会宁府', modern: '阿城', x: 700, y: 218, capital: true, dynasty: '金', note: '金太祖收国元年所定，女真发祥地' },
      { name: '中都', modern: '北京', x: 562, y: 282, capital: true, dynasty: '金', note: '海陵王贞元元年自上京迁此' },
      // —— 元 ——
      { name: '大都', modern: '北京', x: 562, y: 280, capital: true, dynasty: '元', note: '至元八年忽必烈定为元朝京师' },
      { name: '上都', modern: '正蓝旗', x: 530, y: 244, dynasty: '元', note: '元朝夏都，开平府' },
      // —— 海贸名港（宋元通用，标 dynasty: '海港' 默认显示）——
      { name: '泉州', modern: '泉州', x: 600, y: 540, dynasty: '南宋', note: '南宋至元代世界第一大港，刺桐港' },
      { name: '庆元', modern: '宁波', x: 654, y: 458, dynasty: '南宋', note: '宋代明州，市舶司所在' },
      { name: '广州', modern: '广州', x: 560, y: 582, dynasty: '北宋', note: '宋代设市舶司，海贸要冲' },
    ],
    events: [
      { year: 960, text: '陈桥兵变 · 宋立汴京', dynasty: '北宋' },
      { year: 1038, text: '李元昊建大夏 · 都兴庆府', dynasty: '西夏' },
      { year: 1115, text: '完颜阿骨打建金', dynasty: '金' },
      { year: 1127, text: '靖康之变 · 南渡临安', dynasty: '南宋' },
      { year: 1206, text: '铁木真称成吉思汗', dynasty: '元' },
      { year: 1271, text: '忽必烈定国号大元 · 都大都', dynasty: '元' },
      { year: 1279, text: '崖山之战 · 元一统四海', dynasty: '元' },
      { year: 1292, text: '马可·波罗自泉州归国', dynasty: '元' },
    ],
    frontier: '海舶通蕃 · 草原汗国',
    subEras: [
      { id: 'beisong', name: '北宋', period: '960 — 1127', dynasties: ['北宋', '辽', '西夏'] },
      { id: 'nansong', name: '南宋', period: '1127 — 1279', dynasties: ['南宋', '金', '西夏'] },
      { id: 'yuan', name: '元', period: '1271 — 1368', dynasties: ['元'] },
    ],
    tracks: [
      {
        id: 'song-sea-trade',
        name: '宋代海贸航线',
        color: '#7FCBE8',
        dash: '4 6',
        width: 1.8,
        geometry: 'M 600 540 C 640 580 660 620 670 660 C 660 690 600 700 540 690',
      },
      {
        id: 'mongol-west',
        name: '蒙古西征路线',
        color: '#B8A580',
        dash: '2 6',
        width: 1.6,
        geometry: 'M 562 278 C 460 250 350 232 240 232 C 160 240 100 248 60 260',
      },
      {
        id: 'jin-song-divide',
        name: '宋金分界（淮河—秦岭）',
        color: '#9DB7C6',
        dash: '5 5',
        width: 1.4,
        geometry: 'M 250 410 C 340 405 440 410 540 415 C 620 420 700 428 760 438',
      },
    ],
  },
  {
    id: 'mingqing',
    name: '明清',
    period: '1368 — 1912',
    anchor: 0.95,
    hue: { primary: '#8C1F28', secondary: '#2A0D11' },
    blurb: '皇权极盛，海禁与航海并行；西学东渐，盛极而困。',
    cities: [
      // —— 明 ——
      { name: '应天府', modern: '南京', x: 600, y: 432, capital: true, dynasty: '明', note: '洪武元年朱元璋定都，永乐迁北京后改"南京"' },
      { name: '顺天府', modern: '北京', x: 562, y: 280, capital: true, dynasty: '明', note: '永乐十九年迁都北京，"天子守国门"' },
      { name: '中都凤阳', modern: '凤阳', x: 552, y: 396, dynasty: '明', note: '太祖故里，洪武二年置中都' },
      { name: '西安府', modern: '西安', x: 388, y: 380, dynasty: '明', note: '改奉元路为西安府，秦王封地' },
      { name: '泉州府', modern: '泉州', x: 600, y: 540, dynasty: '明', note: '郑和下西洋驻泊地之一' },
      { name: '广州', modern: '广州', x: 560, y: 582, dynasty: '明', note: '海禁开关之地，洋货入华门户' },
      { name: '苏州府', modern: '苏州', x: 624, y: 422, dynasty: '明', note: '江南经济中心，"赋税甲天下"' },
      { name: '东都承天府', modern: '台南', x: 670, y: 588, dynasty: '明郑', note: '永历十五年郑成功逐荷兰，建东都于此' },
      // —— 清 ——
      { name: '盛京', modern: '沈阳', x: 656, y: 256, capital: true, dynasty: '清', note: '后金天命十年自辽阳迁此，1636 年改盛京' },
      { name: '北京', modern: '北京', x: 562, y: 282, capital: true, dynasty: '清', note: '顺治元年清入关，定都北京' },
      { name: '江宁府', modern: '南京', x: 600, y: 432, dynasty: '清', note: '清代两江总督驻地' },
      { name: '广州十三行', modern: '广州', x: 562, y: 584, dynasty: '清', note: '一口通商时期唯一对欧美贸易口岸' },
      { name: '伊犁', modern: '伊宁', x: 178, y: 252, dynasty: '清', note: '乾隆设伊犁将军，统辖新疆' },
      { name: '拉萨', modern: '拉萨', x: 200, y: 510, dynasty: '清', note: '雍正五年设驻藏大臣' },
      { name: '库伦', modern: '乌兰巴托', x: 458, y: 220, dynasty: '清', note: '清廷库伦办事大臣驻地，外蒙古中心' },
    ],
    events: [
      { year: 1368, text: '朱元璋立明 · 都应天', dynasty: '明' },
      { year: 1405, text: '郑和首下西洋', dynasty: '明' },
      { year: 1421, text: '永乐迁都北京 · 紫禁城落成', dynasty: '明' },
      { year: 1582, text: '利玛窦来华 · 西学东渐', dynasty: '明' },
      { year: 1644, text: '甲申之变 · 清入关', dynasty: '清' },
      { year: 1689, text: '中俄尼布楚条约', dynasty: '清' },
      { year: 1759, text: '清平准噶尔 · 一统新疆', dynasty: '清' },
      { year: 1840, text: '鸦片战争 · 千年变局', dynasty: '清' },
      { year: 1911, text: '辛亥革命 · 帝制终结', dynasty: '清' },
    ],
    frontier: '海禁开关 · 边疆奠定',
    subEras: [
      { id: 'ming', name: '明', period: '1368 — 1644', dynasties: ['明', '明郑'] },
      { id: 'qing', name: '清', period: '1636 — 1912', dynasties: ['清'] },
    ],
    tracks: [
      {
        id: 'great-wall-ming',
        name: '明长城',
        color: '#F0DCAD',
        dash: '4 4',
        width: 1.8,
        geometry: 'M 178 252 L 240 240 L 310 232 L 380 226 L 462 224 L 540 230 L 620 240 L 700 256',
      },
      {
        id: 'zhenghe',
        name: '郑和下西洋',
        color: '#5BA3D0',
        dash: '8 4',
        width: 2,
        geometry: 'M 600 432 C 612 470 600 510 580 540 C 560 580 540 620 510 660 C 460 685 400 690 340 680',
      },
      {
        id: 'qing-frontier',
        name: '清代藩部边界',
        color: '#C8A78E',
        dash: '2 6',
        width: 1.4,
        geometry: 'M 130 252 C 220 232 320 220 410 218 C 500 218 590 224 656 256',
      },
    ],
  },
];

// 中国轮廓 SVG path（手摇精化, 1000×720, 不依赖外部资源）
// 设计要点：
// - 顺时针绘制大陆主体，关键拐点：阿尔泰、东北凸出、渤海凹入、
//   山东半岛、长江入海口、杭州湾、雷州半岛、北部湾、云贵高原、
//   藏南弧形、葱岭。
// - 包含海南岛、台湾岛（独立 subpath）。
// - 城市坐标在 cities[] 中均已对齐当前轮廓内，不要随意改 path 否则需复核 cities。
export const CHINA_OUTLINE =
  // —— 大陆主体（顺时针）——
  'M 88 232 ' +
  // 西北 → 阿尔泰 → 蒙古北界
  'C 130 200 195 178 260 168 ' +
  'C 320 158 380 152 440 152 ' +
  'C 500 152 555 158 605 168 ' +
  // 黑龙江北 · 东北凸出
  'C 660 175 705 188 735 215 ' +
  'C 750 235 752 262 740 286 ' +
  // 辽东 · 渤海湾凹入
  'C 728 300 698 304 668 298 ' +
  'C 648 295 632 298 624 314 ' +
  // 山东半岛凸出
  'C 624 332 660 338 686 350 ' +
  'C 700 358 702 372 690 386 ' +
  'C 678 396 660 396 648 392 ' +
  // 苏北 · 长江入海口
  'C 644 408 670 418 686 432 ' +
  'C 698 446 696 462 680 472 ' +
  // 杭州湾内凹
  'C 660 478 642 472 632 480 ' +
  'C 628 492 644 502 660 512 ' +
  // 福建广东海岸
  'C 678 528 680 552 668 572 ' +
  'C 654 590 632 600 608 604 ' +
  // 珠三角 · 雷州半岛 · 北部湾凹入
  'C 588 606 568 600 552 596 ' +
  'C 540 600 542 612 528 614 ' +
  'C 514 612 506 600 492 596 ' +
  'C 470 590 446 590 422 596 ' +
  // 桂西 → 云南南缘
  'C 398 600 374 596 354 584 ' +
  'C 332 572 318 552 308 528 ' +
  // 横断山 · 川西
  'C 300 506 290 488 280 478 ' +
  // 藏南 · 喜马拉雅弧
  'C 256 488 224 498 192 502 ' +
  'C 158 504 124 498 100 484 ' +
  // 阿里 · 葱岭
  'C 78 462 68 432 72 402 ' +
  'C 76 372 84 344 86 314 ' +
  'C 84 286 80 258 88 232 Z ' +
  // —— 海南岛 ——
  'M 528 622 ' +
  'C 540 614 558 614 568 622 ' +
  'C 574 632 570 644 558 648 ' +
  'C 542 650 528 644 524 636 ' +
  'C 522 630 524 626 528 622 Z ' +
  // —— 台湾岛 ——
  'M 678 538 ' +
  'C 686 532 698 538 700 552 ' +
  'C 702 572 696 596 686 612 ' +
  'C 678 622 670 618 668 606 ' +
  'C 666 588 670 562 678 538 Z';

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

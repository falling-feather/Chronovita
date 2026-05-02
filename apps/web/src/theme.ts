import { ThemeConfig } from 'antd';

export const palette = {
  paperBeige: '#F3EBDD',
  inkJet: '#1F1B17',
  cinnabar: '#9F2E25',
  bronze: '#7A5C2E',
  jade: '#3F5F4D',
  scrollEdge: '#D9C9A8',
};

export const theme: ThemeConfig = {
  token: {
    colorPrimary: palette.cinnabar,
    colorBgBase: palette.paperBeige,
    colorTextBase: palette.inkJet,
    colorBorder: palette.scrollEdge,
    fontFamily: '"霞鹜文楷", "Noto Serif SC", "宋体", serif',
    borderRadius: 4,
  },
  components: {
    Layout: {
      headerBg: palette.inkJet,
      headerColor: palette.paperBeige,
      bodyBg: palette.paperBeige,
    },
    Menu: {
      darkItemBg: palette.inkJet,
      darkItemSelectedBg: palette.cinnabar,
    },
  },
};

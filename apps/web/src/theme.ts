import { ThemeConfig } from 'antd';

export const palette = {
  bgPage: '#F4EBD8',
  bgWarm: '#E8D8B9',
  bgWarmSoft: '#F6EFDF',
  bgTint: '#F7E5BD',
  bgNavy: '#06131C',
  bgMid: '#102D37',
  textDark: '#122933',
  textMute: '#6F675B',
  textDisabled: '#958B7C',
  textCream: '#F2E7CF',
  textCreamMute: '#A7B4B4',
  accentGold: '#C6A261',
  accentGoldHover: '#D7B878',
  accentBronze: '#8F693A',
  accentBlue: '#315F5B',
  borderSoft: '#D8C7A7',
};

export const theme: ThemeConfig = {
  token: {
    colorPrimary: palette.accentGold,
    colorBgBase: palette.bgPage,
    colorTextBase: palette.textDark,
    colorBorder: palette.borderSoft,
    colorBgContainer: palette.bgPage,
    colorBgElevated: palette.bgWarmSoft,
    fontFamily: '"思源黑体", "Noto Sans SC", "微软雅黑", sans-serif',
    borderRadius: 2,
  },
  components: {
    Layout: {
      headerBg: palette.bgNavy,
      headerColor: palette.textCream,
      headerHeight: 72,
      bodyBg: palette.bgPage,
      footerBg: palette.bgPage,
    },
    Menu: {
      darkItemBg: 'transparent',
      darkItemColor: palette.textCream,
      darkItemHoverColor: palette.accentGold,
      darkItemSelectedColor: palette.accentGold,
      darkItemSelectedBg: 'transparent',
      horizontalItemSelectedColor: palette.accentGold,
      horizontalItemHoverColor: palette.accentGold,
    },
    Button: {
      colorPrimary: palette.accentGold,
      colorPrimaryHover: palette.accentGoldHover,
      primaryColor: '#FFFFFF',
    },
    Card: {
      colorBgContainer: palette.bgPage,
      colorBorderSecondary: palette.borderSoft,
    },
    Progress: {
      defaultColor: palette.accentGold,
    },
  },
};

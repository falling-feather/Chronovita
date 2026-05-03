import { ThemeConfig } from 'antd';

export const palette = {
  bgPage: '#FFFFFF',
  bgWarm: '#F5F1E8',
  bgWarmSoft: '#FAF7F0',
  bgTint: '#FFF7E5',
  bgNavy: '#0B1E3A',
  bgMid: '#112B4D',
  textDark: '#0B1E3A',
  textMute: '#6B7280',
  textDisabled: '#9CA3AF',
  textCream: '#F5E6CC',
  textCreamMute: '#A8B4C5',
  accentGold: '#D4A95C',
  accentGoldHover: '#E5B96A',
  accentBronze: '#A0826B',
  accentBlue: '#1E40AF',
  borderSoft: '#E5E7EB',
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
    borderRadius: 6,
  },
  components: {
    Layout: {
      headerBg: palette.bgNavy,
      headerColor: palette.textCream,
      headerHeight: 64,
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

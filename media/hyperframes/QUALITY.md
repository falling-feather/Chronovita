# V0.10.9 双旗舰短片质量记录

检查日期：2026-08-14

工具基线：HyperFrames CLI 0.7.108、GSAP 3.14.2、FFmpeg/ffprobe

共同规格：1920×1080、30fps、45.000 秒、H.264、无音频流

## 自动检查

两个工程分别执行 `npm run check`、`hyperframes lint --verbose`、`hyperframes validate` 与 `hyperframes inspect --samples 15 --at-transitions --strict`：

| 工程 | Lint | 对比度 | 布局/运动 | Inspect |
| --- | --- | --- | --- | --- |
| L101 大禹治水 | 0 error / 0 warning | 96/96 通过 | 0 / 0 | 234 个采样，0 issue |
| L103 商鞅变法 | 0 error / 0 warning | 92/92 通过 | 0 / 0 | 238 个采样，0 issue |

当前 CLI 的 `check` Motion 检查作为动画可寻址性与时间线检查事实源。最终成片另用 `ffprobe` 核验分辨率、帧率、时长和音视频流。

## 人工关键帧检查

- 每片检查五个静态英雄帧及全部场景转场帧；未发现黑帧、跳帧、遮挡或越界。
- 标题、材料身份、年代边界、图例和课堂方法在 1920×1080 原始尺寸下可读。
- 商鞅片“国家能力 / 制度信用 / 社会代价”三列使用独立语义选择器，最终高质量成片已包含修正。
- 两张 poster 均从最终高质量成片 2.5 秒处抽取，并按原始尺寸复核。

## 不可变媒体哈希

| 文件 | 字节 | SHA-256 |
| --- | ---: | --- |
| `L101/v002/dayu-intro.mp4` | 9,430,038 | `1bb20fd03c34fa13195709989b4dfaf92c343b304a49b5b4998beda20883886c` |
| `L101/v002/dayu-poster.webp` | 80,590 | `a0e8e68221f39409661a8e969d6e17c4209230af9e005dc46edacbef76dce410` |
| `L101/v002/dayu-transcript.md` | 2,065 | `a3ce6c726344be64cac4843a7b2739ede8876f7e5567d808c4bdd72c5896aac8` |
| `L103/v002/shangyang-intro.mp4` | 8,304,345 | `f03debeaced13dc80b272800c5f239f670f5c76846f3d86acbfc6f093fa35c71` |
| `L103/v002/shangyang-poster.webp` | 76,794 | `133b330d981380af11d322453fb3a6c5ebadefac9acb2df53fb6635f05820a57` |
| `L103/v002/shangyang-transcript.md` | 2,063 | `1a684f351fea9e6adb3da1ce3833626ea5cef620ba8f16813c006b86931f63e6` |

`LessonPresentationV1` v002 的最终 checksum 分别为：

- L101：`2c74590e1655f0bbfc0d632557a71b691d599d6ca858e3676938efd825608d17`
- L103：`8d45b2d666afff7da6ca394c6e02ebffebae099f28107f07803250e331f2b89a`

当前发布为 `rel-28b5624648-0005`，checksum 为 `0832401240d688a215ede128fc6898f467029244ac4ebcfe8c9a331d1346b1a5`；两课课程包、六回合关卡和证据库版本保持不变，仅展示资源升级到 v002。

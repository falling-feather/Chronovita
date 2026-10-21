# Chronovita HyperFrames 课堂短片

本目录保存 V0.10 双旗舰课堂导读的可复现 HyperFrames 源工程。两个工程共同遵循 [DESIGN.md](./DESIGN.md)，只使用本地文字、地图/河道/制度图形和器物轮廓，不包含历史人物肖像、拟真历史现场、旁白、音乐或运行时网络依赖。

| 课程 | 源工程 | 不可变发布媒体 |
| --- | --- | --- |
| L101 大禹治水 | `chronovita-dayu-intro/` | `content/media/lessons/L101/v002/` |
| L103 商鞅变法 | `chronovita-shangyang-intro/` | `content/media/lessons/L103/v002/` |

每个工程均固定 `hyperframes@0.7.108`、`gsap@3.14.2`，并在 `assets/` 中保存本地 GSAP 运行文件。首次复现时进入对应工程执行：

```powershell
npm ci
npm run check
npx hyperframes lint --verbose
npx hyperframes validate
npx hyperframes inspect --samples 15 --at-transitions --strict
```

高质量课堂成片使用 1920×1080、30fps、45 秒、H.264 MP4。以大禹工程为例：

```powershell
npx hyperframes render --fps 30 --quality high --resolution landscape --strict --output ../../../content/media/lessons/L101/v002/dayu-intro.mp4
```

渲染完成后从成片抽取本地 WebP poster，核对文字稿，并运行仓库根目录的发布命令：

```powershell
python scripts/publish_flagship_media.py
```

该命令校验三个媒体文件的 SHA-256，封存 `LessonPresentationV1` v002，并生成课程不可变 release；在 v002 已生效时重复执行不会产生新 release。质量记录及最终哈希见 [QUALITY.md](./QUALITY.md)。

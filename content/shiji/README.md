# 《史记》阅读资料包

这是从 `D:/代码玩具测试/史海/data/content/shiji-application-runtime` 迁移的《史记》阅读运行时资料包，包含 130 卷目录、篇章元数据、简体/繁体正文、译读、OCR 原文片段和来源页引用。

- 文件：`shiji-application-runtime.zip`
- 资料状态：史海当前运行时快照；保留原有 `application_ready`、篇章 checksum 与发布状态
- SHA-256：`F9A3A4ACD929438877B088EDE99C6CEB0E7C27AB8C70E2C3F56397A2BE19F190`
- 迁移边界：不包含史海 OCR 工作台数据库、生产脚本、其他二十四史或原始扫描 PDF
- 使用入口：Chronovita `/shiji`；后端通过 `/api/v1/shiji/*` 按篇只读解包
- OCR 单页资料：`shiji-ocr-records.zip`，11,342 页的真实转写、识别框、来源与原有映射；SHA-256 `5b8025ee8c1c62af7349ac38d2b0f7e33c7222607a855d4774c7e9cc880498c6`。
- 真实书影：本轮构建 `Chronovita-Shiji-Facsimile-v2.zip`，包含百衲本 4,782 页、四库本 6,560 页；SHA-256 `b158d02b31ccfc9048af36924ef830668616b81c7bf5d3e877f718768d5fd545`，尚未公开发行。
- 安装：`scripts/install-shiji-facsimile.cmd 路径/Chronovita-Shiji-Facsimile-v2.zip`；默认写入 `data/shiji/ocr-pages`，保留版本目录。原百衲本单独包仍可按本轮索引校验安装，不覆盖既有资料。
- 页索引及单页/整包校验值以 `ocr-pages-index.json` 为准；OCR 记录随主课堂包提供，书影单独安装。正文、OCR 与自动译读仍保留人工待审状态。

该资料包是文献阅读内容，不会自动进入课程练问创、RAG 课程证据库或学生学习进度。书影包单独发行，不写入源码仓库和 Windows 主课堂 ZIP。

维护者重新导出使用 `scripts/export_shiji_ocr.py --source 史海项目路径 --image-archive 新书影ZIP路径`。源数据库以只读方式打开；只迁移《史记》两版本，不复制生产数据库。运行时没有外部史海路径依赖，来源中的旧路径仅用于记录出处。

# 《史记》阅读资料包

这是从 `D:/代码玩具测试/史海/data/content/shiji-application-runtime` 迁移的《史记》阅读运行时资料包，包含 130 卷目录、篇章元数据、简体/繁体正文、译读、OCR 原文片段和来源页引用。

- 文件：`shiji-application-runtime.zip`
- 资料状态：史海当前运行时快照；保留原有 `application_ready`、篇章 checksum 与发布状态
- SHA-256：`F9A3A4ACD929438877B088EDE99C6CEB0E7C27AB8C70E2C3F56397A2BE19F190`
- 迁移边界：不包含史海 OCR 工作台数据库、生产脚本、其他二十四史或原始扫描 PDF
- 使用入口：Chronovita `/shiji`；后端通过 `/api/v1/shiji/*` 按篇只读解包

该资料包是文献阅读内容，不会自动进入课程练问创、RAG 课程证据库或学生学习进度。

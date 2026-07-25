# ADR-0017 课程内容历史库与 Git 发布边界

- 状态：接受
- 日期：2026-07-25
- 目标版本：V0.9.x
- 决策人：核心开发组 / 系统架构组

## 背景

Chronovita 已能把课程草稿审校、封存，并以 `CourseReleaseManifestV2` 将课文运行包与关卡模板作为同一不可变快照发布给学生。教师端也能下载课文 JSON、格式层、教师稿和 HTML 预览，但浏览器下载不等于可审校、可追踪、可重试的团队发布流程。

本阶段需要让不了解 Git 的教师把精确课程版本发布到 GitHub，并保留中文文件名、显示格式和历史差异。GitHub 仓库不能替代草稿、账号、工作流和发布任务数据库；教师浏览器也不能持有仓库地址、分支选择权或 GitHub 密钥。

## 决策

### 1. 独立私有仓库只承担不可变课程历史

课程历史使用独立私有 GitHub 仓库，不直接写入 Chronovita 源码仓库。应用数据库继续保存草稿、账号、审校工作流和发布任务；活动课程服务仍以应用侧 active release pointer 为学生读取权威。Git 历史用于课程版本留痕、差异审校、人工批准和异地备份，不被描述为事务数据库。

首版归档只接受 `workflow.get_release(course_id, release_id)` 可精确读取且 checksum 正确的课程 release。未发布草稿、仅存在于浏览器的预览状态，以及尚无 release pin 的独立人物/关键词档案不进入不可变课程归档。

### 2. 归档身份覆盖来源、渲染器和全部文件

`services/contracts/archive_v1.py` 冻结 `course-archive/v1`。每份归档固定：

- 课程与 release 的完整 ID、序号、Schema、操作、时间和 checksum。
- `ArchiveRendererV1` 的渲染器 ID、版本和样式配置。
- 每个课时的 sealed 源、运行包、关卡引用、中文展示名和精确文件清单。
- 每个文件的 POSIX 路径、媒体类型、字节数、blob SHA-256，以及机器制品的 Schema 和契约 checksum。
- 逻辑归档 checksum、由其派生的 `archive_id`，以及清单自身 checksum。

归档目录相对于仓库绑定的 `root_prefix`：

```text
<course_id>/releases/<release_id>/<archive_id>/
├── 课程归档清单.json
├── 课程发布清单.json
└── lessons/<lesson_id>/
    ├── <课程标题>.json
    ├── <课程标题>-运行包.json
    ├── <课程标题>-格式层.json
    ├── <课程标题>-教师稿.md
    ├── <课程标题>-预览.html
    └── scenarios/<scenario_id>-vNNN.json
```

`课程归档清单.json` 不列入自身 `files`，避免自引用 checksum。正式构建器必须读取已经验真的原始 sealed/runtime 字节，不得把前端可变状态重新序列化后冒充原件。渲染器版本或任一文件字节变化都会生成新的归档身份和目录，不能覆盖同一 release 的旧归档。

所有路径必须是 NFKC 规范化的相对 POSIX 路径，并同时拒绝父目录、绝对路径、反斜杠、控制字符、Windows 非法字符、保留名、`.git`、大小写或 Unicode 折叠碰撞。单文件上限 2 MiB，单归档上限 16 MiB、128 个受清单管理文件。

### 3. 仓库只能由服务端不可变绑定选择

`GitRepositoryBindingV1` 使用稳定 `binding_id`、GitHub 数字 `repository_id`、安装 ID、私有可见性、基准分支、根前缀和允许模式固定目标。浏览器发布请求只能提交 `binding_id` 和精确归档身份，不能提交 owner、repository、branch、path、token 或私钥。

生产优先使用 GitHub App installation token。App 只安装到课程历史仓库，申请 `Contents: write`；启用 PR 模式时再申请 `Pull requests: write`。GitHub 官方说明 installation token 可进一步限制到指定仓库和权限，并在一小时后失效；服务端按需生成，不持久化临时 token。细粒度 PAT 只保留为受控过渡模式，仍必须放在后端 `SecretStr` 或秘密管理系统，不能进入浏览器、本地教师包、日志、审计正文或归档。

参考：[GitHub App installation token](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app)、[GitHub App 权限选择](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app)、[创建 Pull Request 所需权限](https://docs.github.com/en/rest/pulls/pulls#create-a-pull-request)。

### 4. 默认 PR，直接提交是管理员显式动作

默认发布模式为 `pull_request`。分支名由课程 ID、release ID 和归档 checksum 派生，形如 `chronovita/<course>/<release>-<checksum12>`；教师只填写给审校者看的更新说明。直接提交必须同时满足：

1. 仓库绑定明确允许 `direct_commit`。
2. 调用者具备管理员发布权限；后续实现不得只依赖请求体布尔值。
3. 请求携带显式二次确认。
4. 审计写入成功后才开始远端网络操作。

首版后端继续复用 `content.publish` 作为管理员直提门禁；后续若拆分 `content.archive.export|submit|direct`，必须保持旧管理员能力可迁移且不扩大教师权限。

### 5. 多文件发布使用 Git Data API 和非强推 CAS

后端先读取基准分支 Commit 与 Tree，再以 `base_tree` 创建包含全部归档文件的新 Tree，创建带单一 parent 的 Commit，最后以 `force=false` 创建或更新目标 ref。基准分支已推进时返回稳定冲突并重新协调，禁止覆盖他人提交。GitHub 官方文档说明：缺少 `base_tree` 可能使未列出的旧文件在新 Commit 中表现为删除；Commit 应显式提供 parent；`force=false` 保证 ref 只做 fast-forward。

参考：[Git Trees](https://docs.github.com/en/rest/git/trees#create-a-tree)、[Git Commits](https://docs.github.com/en/rest/git/commits#create-a-commit)、[Git References](https://docs.github.com/en/rest/git/refs#update-a-reference)。

### 6. 幂等任务保留部分成功并可协调恢复

`operation_key` 由仓库绑定、数字仓库 ID、基准分支、根前缀、课程/release 身份、归档 checksum 和发布模式计算；教师说明与客户端重试 ID 不改变操作身份。数据库对该键建立唯一约束，同一请求并发或重试只能产生一个发布任务、分支和 PR。

`GitPublicationRecordV1` 使用 `requested -> preparing -> pushing -> commit_created -> ref_updated -> pr_open -> succeeded` 检查点，并区分 `failed_retryable|failed_terminal`。远端 Commit 已创建但 PR 请求超时等部分成功必须保留 `base_sha/tree_sha/commit_sha/branch_ref`，重试先查询和协调现有远端对象，不能重复提交。审计只记录绑定 ID、仓库 ID、release/archive checksum、Commit SHA、PR 编号和稳定错误码，不记录课程正文、凭据或 GitHub 响应正文。

### 7. checksum 不冒充数字签名

归档、release 和发布记录的 checksum 用于确定性身份、传输校验和篡改发现，不证明发布者身份。发布者身份来自 Chronovita 认证会话、权限判断、事务审计和 GitHub App 安装边界；如未来需要第三方离线验证，再独立增加签名清单，不改变现有 checksum 语义。

## 验收反例

- 同一发布请求并发两次，只能形成一个 operation、分支和 PR。
- GitHub 已创建 Commit 但响应或 PR 创建超时，重试必须协调该 Commit，不能重复发布。
- 基准分支在读取后推进时，`force=false` 更新失败并重新协调，不能覆盖远端历史。
- 同名课程、中文 NFC/NFD、大小写路径、Windows 保留名、`../`、反斜杠、盘符、UNC 和 `.git` 均不能碰撞或逃逸。
- release checksum 正确但原始文件字节变化时，blob SHA-256 必须失败。
- 教师请求直接提交、伪造仓库/分支/路径或在请求中附带 token 必须被权限或 Schema 拒绝。
- GitHub 401 仅允许刷新一次短时 installation token；403、404、409、422 和响应正文不能泄漏到客户端或审计。
- 富文本经过封存、归档、重新读取后，格式层和预览 DOM 必须保持一致；该整链由 BE-006、FE-004、QA-002 接续。

## 后果

正面影响：课程历史与源码历史解耦；教师不需要理解 Git；每次提交都能追溯到精确发布版本、渲染器和文件字节；网络部分失败可以安全重试；浏览器和下载包不接触 GitHub 密钥。

代价与限制：需要新增归档构建器、发布任务持久化、GitHub 适配器和协调逻辑；GitHub App 注册与安装仍需仓库管理员执行；首版不归档没有 release pin 的独立人物/关键词档案；checksum 不能替代代码签名或可信审计。

## 相关

- [ADR-0013 课时到关卡的发布身份交接](ADR-0013-课时到关卡的发布身份交接.md)
- [ADR-0015 生产身份与数据边界](ADR-0015-生产身份与数据边界.md)
- [项目规划第 10.8 节](../02-项目规划与设计总纲.md#108-class-课程历史库与教师发布目标)
- [开发者文档第 4.3 节](../01-开发者文档.md#43-课程归档与-git-发布契约)

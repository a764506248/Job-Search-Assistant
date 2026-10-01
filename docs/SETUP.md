# 安装、前置依赖与首次启动

本文说明从零启动 Job Search Assistant 所需的软件、网络、模型、浏览器和本地数据条件。基础后台、AI 能力、浏览器采集和自动投递不是同一组依赖，请按实际使用范围准备。

## 1. 功能与依赖关系

| 功能 | 必要依赖 |
| --- | --- |
| 管理后台与本地数据库 | Docker Desktop、Docker Compose v2、端口 8765 可用 |
| 向量知识库 | Embedding 容器、端口 8766 可用、首次下载模型所需网络 |
| 简历 AI 识别、项目提取、问候语和定制材料 | 管理后台中配置并验证可用的大模型 |
| 项目自带 Chrome 简历图片扩展 | Node.js 22+、npm、Chrome 开发者模式、本地服务、已登录 BOSS |
| Skill 自动投递 | 已安装 BOSS Skill、Kimi Browser Extension/WebBridge、项目自带图片扩展、已登录 BOSS |
| 网页样式一致的 PDF 导出 | FastAPI 运行环境内可执行的 Chromium；否则自动降级 ReportLab |

## 2. 基础环境

### 2.1 推荐方式：Docker

需要：

- Docker Desktop；
- Docker Compose v2，即 `docker compose`；
- 建议为 Docker 分配至少 4 GB 内存，推荐 6 GB 或更多；
- 宿主机端口 `8765`、`8766` 未被其他程序占用；
- 首次启动可以访问 Docker Hub、Python 包源和 Hugging Face 模型资源。

启动：

```bash
docker compose up -d --build
```

验证：

```bash
curl http://127.0.0.1:8765/v1/health
curl http://127.0.0.1:8766/health
docker compose ps
```

管理后台：<http://127.0.0.1:8765>

首次启动时，Embedding 容器会下载 `jinaai/jina-embeddings-v2-base-zh`。下载完成前服务可能长时间处于 `starting`；模型保存在 Docker Volume `job-search-assistant_embedding-models`，后续启动会复用。

### 2.2 本地开发环境

只有修改源码或运行测试时才需要：

- Node.js 22 或以上；
- npm；
- Python 3.12 或以上；
- uv。

```bash
npm install

cd apps/local-service
uv sync --dev
uv run pytest -q
```

### 2.3 从 Docker Hub 搜索并安装

三个公开镜像位于 Docker Hub 的 `jinxinss` 命名空间，可通过 `docker search jinxinss/job-search-assistant` 搜索。推荐下载专用 Compose 文件一次性启动全部服务：

```bash
curl -O https://raw.githubusercontent.com/a764506248/Job-Search-Assistant/main/docker-compose.dockerhub.yml
docker compose -f docker-compose.dockerhub.yml pull
docker compose -f docker-compose.dockerhub.yml up -d
```

该配置会拉取 `jinxinss/job-search-assistant-{web,local-service,embedding}:latest`。也可以在各镜像的 Docker Hub 页面查看标签和拉取命令。

### 2.4 直接拉取 GHCR 镜像

不修改源码时可以只下载 Release Compose，无需 Node.js、Python 或本地构建：

```bash
curl -O https://raw.githubusercontent.com/a764506248/Job-Search-Assistant/main/docker-compose.release.yml
docker compose -f docker-compose.release.yml pull
docker compose -f docker-compose.release.yml up -d
```

该配置拉取 `ghcr.io/a764506248/job-search-assistant-{web,local-service,embedding}:latest`，同时只将 8765/8766 绑定到本机回环地址。业务数据写入 Compose 文件同级的 `data/`，模型写入命名 Volume。生产或可重复部署建议设置 `JSA_IMAGE_TAG` 使用明确版本标签，而不是长期跟随 `latest`。

## 3. 大模型配置

Embedding 服务只负责向量化，不负责 AI 简历解析、项目拆分或文案生成。以下功能要求在“模型配置”页面至少保存一个验证成功的模型：

- 简历 AI 结构化识别；
- 项目经历提取；
- 职位匹配解释；
- 定制问候语；
- 定制简历和材料示例。

每个模型需要：

- 模型 ID；
- API Key；
- API Base URL；
- 使用角色：选中模型、普通备用或兜底模型。

保存后必须点击“验证”，不能仅以配置成功作为模型可调用的证据。

### 3.1 Docker 访问宿主机模型

如果模型服务运行在宿主机上的 Ollama、LM Studio 或其他本地代理中，Docker 里的 `127.0.0.1` 指向容器自身，不能使用：

```text
http://127.0.0.1:端口
```

macOS 和 Windows 的 Docker Desktop 通常应配置为：

```text
http://host.docker.internal:端口
```

同时需要保证该模型服务允许来自 Docker 的连接。互联网模型 API 可以直接使用其 HTTPS 地址。

## 4. 项目自带浏览器扩展（v0.2.3 图片测试版）

### 4.1 从 GitHub Actions 下载

当 push 包含 `apps/extension/**` 下的文件变更时，仓库会触发 `Build Chrome Extension` 工作流，构建 `@job-search-assistant/extension` 并上传品牌化 artifact：`job-search-assistant-chrome-mv3`。其他目录的修改不会触发扩展构建；也可以通过 `workflow_dispatch` 手动运行。下载 artifact 后，再解压其中的 `job-search-assistant-chrome-mv3.zip`；Chrome 应加载 ZIP 的解压目录，而不是 ZIP 文件本身。

下载路径：GitHub 仓库 **Actions → Build Chrome Extension → 对应运行记录 → Artifacts**。Actions artifact 默认保留 30 天，适合测试和阶段性交付；正式长期发布可在后续增加基于版本标签的 GitHub Release。

### 4.2 本地构建

不能把 `apps/extension` 源码目录直接加载到 Chrome。先在仓库根目录构建：

```bash
npm install
npm run build:extension
```

然后打开 `chrome://extensions`：

1. 开启“开发者模式”；
2. 点击“加载已解压的扩展程序”；
3. 本地构建时选择 `apps/extension/.output/chrome-mv3`；从 Actions 下载时选择 `job-search-assistant-chrome-mv3.zip` 的解压目录；
4. 确认本地服务已启动；
5. 登录 BOSS 直聘并打开“消息”页；
6. 重新构建后必须在扩展卡片上点击“重新加载”，再刷新 BOSS 页面。

当前版本只启用默认简历图片发送面板，原职位采集、分析和同步入口暂时停用，但源码和测试仍保留。面板支持拖拽和折叠；折叠后仍显示“加载”和“发送”按钮。完整手工流程为：

1. 在 BOSS 消息页选中目标联系人；
2. 点击“仅加载图片预览”，确认扩展状态包含“尚未发送”；
3. 核对图片及联系人后点击“确认并发送给当前联系人”；
4. 图片写入 BOSS 上传控件后会立即发送，不要再寻找或点击页面上的第二个发送按钮；
5. 在聊天记录或联系人摘要中确认图片消息出现。

扩展依赖 `https://www.zhipin.com/*` 和 `http://127.0.0.1/*` 权限，通过后台脚本读取 `GET /v1/resumes/default-image`，不需要开启 Chrome 的“允许访问文件网址”。若页面中未出现面板、找不到聊天图片控件或图片未发送，应停止自动投递并检查扩展是否已重新加载、本地服务是否在线以及 BOSS 页面结构是否变化。

## 5. Skill 与 Kimi 自动投递

自动投递使用 BOSS Skill 编排：Kimi WebBridge 负责页面读取、联系人/岗位点击和问候语发送；项目自带 Chrome 扩展负责默认简历图片的读取、预览和注入；本地 API 负责档案、规则、RAG、职位快照、材料决策和投递记录。

### 5.1 安装 Kimi 浏览器扩展

官方下载地址：

<https://www.kimi.com/products/kimi-browser-extension>

安装后确认扩展已经连接本机 WebBridge daemon。可使用以下命令检查：

```bash
~/.kimi-webbridge/bin/kimi-webbridge status
```

输出中的 `running` 和 `extension_connected` 都应为 `true`。Kimi 仅作为浏览器动作执行层，不能绕过本地 API 自行决定是否投递。

### 5.2 安装项目内 Skill

仓库内版本位于：

```text
skills/boss-zhipin-assistant/
```

复制到 Codex Skill 目录并创建本机连接配置：

```bash
mkdir -p ~/.codex/skills/@user_f5c8032a
cp -R skills/boss-zhipin-assistant ~/.codex/skills/@user_f5c8032a/
cp ~/.codex/skills/@user_f5c8032a/boss-zhipin-assistant/user_profile.example.json \
  ~/.codex/skills/@user_f5c8032a/boss-zhipin-assistant/user_profile.json
```

`user_profile.json` 只保存账号校验、城市编码、浏览器会话和本地服务地址等连接信息。目标岗位、城市、薪资阈值、匹配规则、默认问候语和简历图片开关，应在管理后台维护并通过 `/v1/automation/config` 读取。

安装后可以验证 Skill 结构：

```bash
python ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  ~/.codex/skills/@user_f5c8032a/boss-zhipin-assistant
```

### 5.3 运行前条件

前置条件：

- Kimi Browser Extension 已安装并连接；
- WebBridge daemon 可通过 `http://127.0.0.1:10086` 访问；
- Chrome 中已登录 BOSS；
- `boss-zhipin-deliver` Skill v5.10.0 或更高版本已安装；
- 项目自带 Chrome 扩展 v0.2.3 或更高版本已加载并刷新 BOSS 页面；
- Skill 的本地服务地址为 `http://127.0.0.1:8765`；
- 已在后台配置个人档案、匹配规则、默认问候语和模型；
- 发送简历图片前，已重新导入 PDF、生成第一页图片并选为默认投递图片；
- `GET /v1/automation/config` 返回 `defaultResumeImageAvailable=true`；需要随投递发送时，还必须由用户明确设置 `sendResumeImage=true`。

Kimi 与项目扩展可以同时存在，但职责必须固定：Kimi 不再调用 WebBridge `upload` 上传本地图片，项目扩展不执行职位选择或问候语发送。Skill 只通过扩展稳定的 `.load` / `.send` 入口触发图片流程，面板是否折叠、是否被拖动不影响调用。

默认简历图片包含个人信息，自动发送默认关闭，必须由用户明确启用。真实投递前还需要完成一次受控的 BOSS 页面冒烟测试。

## 6. PDF 与文件依赖

### 6.1 简历导入

支持 PDF、DOCX、TXT 和 Markdown，单文件最大 10 MB。PDF 首页图片由 PyMuPDF 在本地服务中生成，文件保存在：

```text
apps/local-service/data/resume-images/
```

旧简历如果是在首页图片功能加入之前导入的，数据库中没有原 PDF 文件，必须重新导入才能生成图片。

### 6.2 PDF 导出

服务会优先寻找运行环境内的 Chrome/Chromium，然后降级到 ReportLab。当前 Docker 镜像没有安装 Chromium，也不能直接执行 macOS 宿主机的 `/Applications/Google Chrome.app`，因此 Docker 部署通常使用 ReportLab。

这意味着网页预览与 PDF 的字体、换行和分页可能不是像素级一致。要使用 Chromium 导出，需要把 Chromium 安装进本地服务镜像，并在容器内配置有效的 `JSA_CHROME_PATH`；仅把它设置成宿主机路径无效。

## 7. 数据目录与备份

需要备份的本地目录：

```text
apps/local-service/data/jobs.sqlite3
apps/local-service/data/resume-images/
```

其中包含个人档案、项目、简历、职位快照、向量、模型配置、投递记录和简历图片。删除项目目录、清空该目录或用空目录覆盖会导致数据丢失。

建议停止写入后再备份：

```bash
docker compose stop local-service web
cp -R apps/local-service/data apps/local-service/data-backup
docker compose start local-service web
```

不要把数据库和备份提交到 Git 或发送给其他人。

## 8. 当前安全限制

当前实现与目标架构仍有两点差距：

1. 模型 API Key 当前保存在本地 SQLite 的模型配置 JSON 中。列表接口不会返回明文，但尚未迁移到 macOS Keychain、Windows Credential Manager 或 Docker Secret。
2. 项目已经定义 `JSA_LOCAL_TOKEN` 和 `X-Local-Token`，但服务端认证闭环尚未完成。当前主要依靠仅暴露 `127.0.0.1` 和 CORS Origin 限制。

因此必须遵守：

- 不要把端口 8765 映射到 `0.0.0.0`；
- 不要通过路由器或隧道暴露到公网；
- 不要提交或分享 `apps/local-service/data`；
- 不要在多人共用、不可信的系统账户中保存生产 API Key。

## 9. 常见启动问题

| 现象 | 优先检查 |
| --- | --- |
| `8765` 打不开 | `docker compose ps`、Web 与 local-service 健康状态、端口占用 |
| Embedding 长时间 starting | 首次模型下载网络、Docker 内存、`docker compose logs embedding` |
| 模型验证超时 | Base URL、Key、模型 ID、本地模型是否使用 `host.docker.internal` |
| Chrome 提示清单文件缺失 | 加载了源码目录；应重新构建并加载 `.output/chrome-mv3` |
| BOSS 页面没有图片面板 | 扩展是否为 v0.2.3+、是否点击“重新加载”、BOSS 页面是否已刷新 |
| 图片一直加载失败 | `/v1/resumes/default-image`、默认图片配置、本地服务、扩展后台控制台 |
| 找不到聊天图片控件 | 是否已进入“消息”并选中联系人、BOSS 页面结构是否变化 |
| 简历 AI 识别回退本地解析 | 选中模型不可用、超时或未配置兜底模型 |
| PDF 与网页预览不一致 | Docker 中没有 Chromium，当前使用 ReportLab 降级 |
| Kimi 无法控制浏览器 | WebBridge 10086、扩展连接状态、BOSS 登录状态 |

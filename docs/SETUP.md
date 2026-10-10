# 安装、前置依赖与首次启动

本文说明从零启动 Job Search Assistant 所需的软件、网络、模型、浏览器和本地数据条件。默认自动化链路只需要 Docker 本地服务、统一 Chrome 扩展和经用户确认的简历；不需要安装 BOSS Skill 或 Kimi WebBridge。

> 统一扩展负责搜索、职位收集和投递页面 I/O，本地服务负责保存、规则、本地资料匹配、模型分析和任务状态；用户确认企业清单后才允许投递。启动后问候语由扩展自动发送，简历图片按统一悬浮控制台中的策略执行。Kimi + Skill 旧链路仅作为可选回退。完整状态见[自动投递技术设计](AUTOMATION_TECHNICAL_DESIGN.md)。

## 0. 一键安装器

从仓库根目录运行：

```bash
./scripts/install.sh --check
./scripts/install.sh --install
```

Windows PowerShell：

```powershell
.\scripts\install.ps1 -Mode check
.\scripts\install.ps1 -Mode install
```

安装器会检查 Docker Compose、Chrome 和端口，把 Release Compose 安装到 `~/.job-search-assistant`，拉取 Web 与 Local Service 镜像并打开 <http://127.0.0.1:8765/setup>。Compose 会从 Local Service 镜像自动启动独立 runner 容器，不需要主机安装 Python 或手工运行脚本。如果本地已有构建后的统一 Chrome 扩展，安装器会同时生成扩展 ZIP；否则会提示从 GitHub Actions 下载。安装器会持续显示 Docker 进度，不应在下载过程中反复重启。

升级、预演和卸载：

```bash
./scripts/install.sh --upgrade
./scripts/install.sh --install --dry-run
./scripts/install.sh --uninstall
```

卸载只停止容器并移除安装器托管的 Compose/扩展包，保留 `~/.job-search-assistant/data`。版本组合由 [`scripts/release-manifest.env`](../scripts/release-manifest.env) 统一声明。当前是开发清单，镜像仍使用 `latest`；正式 Release 发布后应改为不可变版本标签。

安装器启动服务后，进入“安装向导”生成一次性配对码，在统一扩展弹窗中完成连接；向导会自动读取扩展在线状态。还需打开一个能显示职位列表的 BOSS 搜索页，确认已加载扩展并处于登录状态，并在采集完成前保持该标签页打开。配对成功只代表 WebSocket 在线，不代表 BOSS 登录状态已经通过。

### 0.1 简历识别确认

导入简历后，系统只保存待确认的候选档案和候选项目，不会立即覆盖个人档案或写入项目库。请在“简历库”展开摘要核对姓名、目标岗位、项目和原文，再点击“确认并写入知识库”。旧版本已经存在且没有确认字段的简历按已确认处理。

### 0.2 无副作用安全测试

安装向导底部的“运行安全测试”只汇总阻塞项、关键词和每日目标。它不会打开 BOSS 页面，不执行浏览器点击，也不会发送消息或投递。安全测试通过只代表环境和配置齐备；之后应到“自动投递”创建任务，由统一扩展先收集职位，确认企业清单后再启动投递。

## 1. 功能与依赖关系

| 功能 | 必要依赖 |
| --- | --- |
| 管理后台与本地数据库 | Docker Desktop、Docker Compose v2、端口 8765 可用 |
| 简历 AI 识别、项目提取、问候语和定制材料 | 管理后台中配置并验证可用的大模型 |
| 统一 Chrome 扩展自动化 | 本地服务、Chrome、已登录 BOSS；本地构建扩展时才需要 Node.js 22+ 与 npm |
| 职位收集与分析 | 统一扩展在线、搜索关键词、已确认简历、可用模型与匹配规则 |
| 旧版 Skill/Kimi 回退（可选） | BOSS Skill、Kimi Browser Extension/WebBridge；不影响默认链路就绪状态 |
| 网页样式一致的 PDF 导出 | FastAPI 运行环境内可执行的 Chromium；否则自动降级 ReportLab |

## 2. 基础环境

### 2.1 推荐方式：Docker

需要：

- Docker Desktop；
- Docker Compose v2，即 `docker compose`；
- 建议为 Docker 分配至少 4 GB 内存，推荐 6 GB 或更多；
- 宿主机端口 `8765` 未被其他程序占用；
- 首次启动可以访问 Docker 镜像仓库。

启动：

```bash
docker compose up -d --build
```

验证：

```bash
curl http://127.0.0.1:8765/v1/health
docker compose ps
```

管理后台：<http://127.0.0.1:8765>

后台需要登录。首次打开会引导创建首个管理员账号（该账号自动拥有管理员权限）；此后自助注册关闭，后续账号由管理员在“用户管理”页创建或停用。登录成功后前端会持有 JWT 并附带在所有请求上。个人档案、项目库、简历库、匹配规则、模型配置、职位快照和投递数据都按登录账号隔离。

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

两个公开镜像位于 Docker Hub 的 `jinxinss` 命名空间，可通过 `docker search jinxinss/job-search-assistant` 搜索。推荐下载专用 Compose 文件一次性启动全部服务：

```bash
curl -O https://raw.githubusercontent.com/a764506248/Job-Search-Assistant/main/docker-compose.dockerhub.yml
docker compose -f docker-compose.dockerhub.yml pull
docker compose -f docker-compose.dockerhub.yml up -d
```

该配置会拉取 `jinxinss/job-search-assistant-{web,local-service}:latest`。也可以在各镜像的 Docker Hub 页面查看标签和拉取命令。Web 与 Local Service 镜像支持 `linux/amd64` 和 `linux/arm64`。

### 2.4 直接拉取 GHCR 镜像

不修改源码时可以只下载 Release Compose，无需 Node.js、Python 或本地构建：

```bash
curl -O https://raw.githubusercontent.com/a764506248/Job-Search-Assistant/main/docker-compose.release.yml
docker compose -f docker-compose.release.yml pull
docker compose -f docker-compose.release.yml up -d
```

该配置拉取 `ghcr.io/a764506248/job-search-assistant-{web,local-service}:latest`，同时只将 8765 绑定到本机回环地址。业务数据写入 Compose 文件同级的 `data/`。生产或可重复部署建议设置 `JSA_IMAGE_TAG` 使用明确版本标签，而不是长期跟随 `latest`。

## 3. 大模型配置

以下生成式 AI 功能要求在“模型配置”页面至少保存一个验证成功的模型：

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

## 4. 统一 Chrome 扩展

如果是第一次安装 Chrome 插件，请优先按[《Chrome 插件下载安装指南（新手版）》](CHROME_EXTENSION_INSTALL.md)操作。本节保留开发构建和技术细节。

### 4.1 从 GitHub Releases 下载

普通用户进入 [GitHub Releases](https://github.com/a764506248/Job-Search-Assistant/releases/latest)，展开最新版本底部的 **Assets**，下载 `job-search-assistant-chrome-mv3.zip`。也可以使用[最新版本直接下载链接](https://github.com/a764506248/Job-Search-Assistant/releases/latest/download/job-search-assistant-chrome-mv3.zip)。下载后解压 ZIP；Chrome 应加载 ZIP 的解压目录，而不是 ZIP 文件本身。

推送 `v*` 版本标签时，`Build Chrome Extension` 工作流会构建扩展、创建同名 GitHub Release，并自动上传 ZIP 到 Release Assets。如果同名 Release 已存在，重新运行工作流会覆盖其中的扩展 ZIP，便于修复失败或重新发布。

开发测试构建仍可从 GitHub 仓库 **Actions → Build Chrome Extension → 对应运行记录 → Artifacts** 下载 `job-search-assistant-chrome-mv3`。Actions Artifact 需要登录 GitHub 且默认保留 30 天，只适合测试和阶段性交付。

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
5. 登录 BOSS 直聘并打开一个能正常显示职位列表的搜索页，采集完成前保持该标签页打开；
6. 重新构建后必须在扩展卡片上点击“重新加载”，再刷新 BOSS 页面。

macOS Finder 默认隐藏以 `.` 开头的目录。如果选择目录时看不到 `.output`，按
`Command + Shift + .` 显示隐藏文件，或按 `Command + Shift + G` 后输入仓库内的
`apps/extension/.output/chrome-mv3` 完整路径。扩展卡片版本必须显示 `0.4.15` 或更高；
旧版 `0.3.x` 不包含职位批量收集动作，后台会阻止开始采集并给出升级提示。

加载扩展后，先登录后台（账号由管理员创建），在“安装向导”生成 6 位一次性配对码，再在 BOSS 页面右下角“自动投递控制台”中输入配对码。配对码属于生成它的账号，扩展之后采集的职位会记到该账号名下；旧版扩展令牌不含账号信息，升级后需要重新配对一次。Chrome 工具栏中的扩展图标只用于定位并展开该控制台。扩展通过 `ws://127.0.0.1:8765/v1/browser/ws` 连接，只接受固定白名单动作。当前令牌及用户归属会持久化，普通服务重启后扩展可自动重连；令牌失效、用户被停用或服务拒绝旧版无归属令牌时才需要重新配对。

后台的“自动流程排队中”表示采集任务已经入队，也可能正在等待扩展确认 BOSS 登录状态。登录检查最长 30 秒；未登录或检查超时后应显示采集失败及明确原因。扩展按每批 5 个岗位持续下拉采集，直至候选上限或搜索结果耗尽。`0.4.13` 起，BFCache 关闭消息通道时扩展会重载搜索页并重试只读采集；`0.4.15` 起，采集前还会核对个人档案姓名与 BOSS 页面账号，明确不一致时立即阻止任务。

统一扩展承担默认自动化链路的全部浏览器 I/O：按关键词打开 BOSS 搜索页、遍历和懒加载岗位卡片、读取完整 JD、打开目标沟通、校验当前会话身份，以及执行企业清单确认后的问候语和简历图片发送。匹配决策始终由本地服务完成，扩展不会自行决定投递企业。

统一悬浮控制台支持拖拽和折叠，并提供三种简历图片策略：

1. `自动发送`：已确认的自动任务请求发送简历时，扩展直接注入图片并验证聊天中出现新图片消息；
2. `发送前确认`：每次显示图片与目标岗位/企业，确认后再注入；
3. `不发送`：图片动作被明确阻止，问候语任务不受影响。

后台的“随投递发送简历图片”仍是第一层总开关；扩展策略只在该总开关开启且默认图片可用时生效。

扩展依赖 `https://www.zhipin.com/*` 和 `http://127.0.0.1/*` 权限，通过后台脚本读取 `GET /v1/resumes/default-image`，不需要开启 Chrome 的“允许访问文件网址”。若页面中未出现面板、找不到聊天图片控件或图片未发送，应停止自动投递并检查扩展是否已重新加载、本地服务是否在线以及 BOSS 页面结构是否变化。

## 5. 旧版 Skill 与 Kimi 回退（可选）

本节只适用于需要复现旧版流程或执行新旧链路对照测试的开发者。默认安装、职位收集、企业确认和投递均不调用 Skill，也不连接 Kimi WebBridge；未安装或未连接它们不会阻塞向导和任务启动。

旧版回退中，Kimi 负责页面读取、联系人/岗位点击和问候语发送，BOSS Skill 负责流程编排，项目扩展负责默认简历图片注入，本地 API 仍负责档案、规则、本地资料匹配、职位快照、材料决策和投递记录。

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

### 5.3 旧版回退运行条件

前置条件：

- Kimi Browser Extension 已安装并连接；
- WebBridge daemon 可通过 `http://127.0.0.1:10086` 访问；
- Chrome 中已登录 BOSS；
- `boss-zhipin-deliver` Skill v5.10.0 或更高版本已安装；
- 项目自带 Chrome 扩展 v0.4.15 或更高版本已加载并刷新 BOSS 页面；
- Skill 的本地服务地址为 `http://127.0.0.1:8765`；
- 已在后台配置个人档案、匹配规则、默认问候语和模型；
- 发送简历图片前，已重新导入 PDF、生成第一页图片并选为默认投递图片；
- `GET /v1/automation/config` 返回 `defaultResumeImageAvailable=true`；需要随投递发送时，还必须由用户明确设置 `sendResumeImage=true`。

这些条件只影响旧版回退。Kimi 与项目扩展同时存在时，Kimi 不再调用 WebBridge `upload` 上传本地图片；Skill 只通过扩展稳定的 `.load` / `.send` 入口触发图片流程，面板是否折叠、是否被拖动不影响调用。

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

其中包含个人档案、项目、简历、职位快照、模型配置、投递记录和简历图片。删除项目目录、清空该目录或用空目录覆盖会导致数据丢失。

建议停止写入后再备份：

```bash
docker compose stop local-service web
cp -R apps/local-service/data apps/local-service/data-backup
docker compose start local-service web
```

不要把数据库和备份提交到 Git 或发送给其他人。

## 8. 当前安全限制

当前实现与目标架构仍有一点差距：

1. 模型 API Key 当前保存在本地数据库的模型配置 JSON 中。列表接口不会返回明文，但尚未迁移到 macOS Keychain、Windows Credential Manager 或 Docker Secret。

已经完成的部分：后台登录使用 JWT 会话，所有业务数据按账号隔离，未登录的数据接口统一返回 401；浏览器扩展通过配对令牌绑定到生成配对码的账号，采集与投递数据都记在该账号名下。CORS 仍只放行扩展与 BOSS 域名。

因此必须遵守：

- 不要把端口 8765 映射到 `0.0.0.0`；
- 不要通过路由器或隧道暴露到公网；
- 不要提交或分享 `apps/local-service/data`；
- 不要在多人共用、不可信的系统账户中保存生产 API Key。

## 9. 常见启动问题

| 现象 | 优先检查 |
| --- | --- |
| `8765` 打不开 | `docker compose ps`、Web 与 local-service 健康状态、端口占用 |
| 模型验证超时 | Base URL、Key、模型 ID、本地模型是否使用 `host.docker.internal` |
| Chrome 提示清单文件缺失 | 加载了源码目录；应重新构建并加载 `.output/chrome-mv3` |
| BOSS 页面没有扩展功能 | 是否加载 `.output/chrome-mv3`、是否点击“重新加载”、BOSS 页面是否已刷新 |
| 图片一直加载失败 | `/v1/resumes/default-image`、默认图片配置、本地服务、扩展后台控制台 |
| 找不到聊天图片控件 | 是否已进入“消息”并选中联系人、BOSS 页面结构是否变化 |
| 简历 AI 识别回退本地解析 | 选中模型不可用、超时或未配置兜底模型 |
| PDF 与网页预览不一致 | Docker 中没有 Chromium，当前使用 ReportLab 降级 |
| 旧版 Kimi 回退无法控制浏览器 | WebBridge 10086、Kimi 扩展连接状态、BOSS 登录状态；默认链路无需 Kimi |

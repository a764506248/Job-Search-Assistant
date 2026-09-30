# 安装、前置依赖与首次启动

本文说明从零启动 Job Search Assistant 所需的软件、网络、模型、浏览器和本地数据条件。基础后台、AI 能力、浏览器采集和自动投递不是同一组依赖，请按实际使用范围准备。

## 1. 功能与依赖关系

| 功能 | 必要依赖 |
| --- | --- |
| 管理后台与本地数据库 | Docker Desktop、Docker Compose v2、端口 8765 可用 |
| 向量知识库 | Embedding 容器、端口 8766 可用、首次下载模型所需网络 |
| 简历 AI 识别、项目提取、问候语和定制材料 | 管理后台中配置并验证可用的大模型 |
| 项目自带 Chrome 扩展采集 | Node.js 22+、npm、Chrome 开发者模式、已登录 BOSS |
| Skill 自动投递 | 已安装 BOSS Skill、Kimi Browser Extension/WebBridge、已登录 BOSS |
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

## 4. 项目自带浏览器扩展

不能把 `apps/extension` 源码目录直接加载到 Chrome。先在仓库根目录构建：

```bash
npm install
npm run build:extension
```

然后打开 `chrome://extensions`：

1. 开启“开发者模式”；
2. 点击“加载已解压的扩展程序”；
3. 选择 `apps/extension/.output/chrome-mv3`；
4. 确认本地服务已启动；
5. 登录 BOSS 直聘后再进行页面采集验证。

扩展依赖 `https://www.zhipin.com/*` 和 `http://127.0.0.1/*` 权限。BOSS 页面结构发生变化时，采集字段可能缺失，应当停止自动操作并查看扩展错误面板和 `/v1/client-logs`。

## 5. Skill 与 Kimi 自动投递

自动投递推荐使用 BOSS Skill 编排，由 Kimi WebBridge 负责浏览器操作，本地 API 负责档案、规则、RAG、职位快照、材料和投递记录。

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
- `boss-zhipin-deliver` Skill 已安装；
- Skill 的本地服务地址为 `http://127.0.0.1:8765`；
- 已在后台配置个人档案、匹配规则、默认问候语和模型；
- 发送简历图片前，已重新导入 PDF、生成第一页图片并选为默认投递图片。

不要让项目自带扩展和 Kimi 同时执行自动点击或发送。两者可以同时读取和展示信息，但必须只有一个浏览器写操作执行者，否则可能重复采集、重复沟通或发送到错误会话。

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
| 扩展一直显示连接中 | `http://127.0.0.1:8765/v1/health`、扩展权限和浏览器控制台 |
| 简历 AI 识别回退本地解析 | 选中模型不可用、超时或未配置兜底模型 |
| PDF 与网页预览不一致 | Docker 中没有 Chromium，当前使用 ReportLab 降级 |
| Kimi 无法控制浏览器 | WebBridge 10086、扩展连接状态、BOSS 登录状态 |

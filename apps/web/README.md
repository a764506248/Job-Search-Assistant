# Web

本目录是基于 Vue 3、Vite 和 Ant Design Vue 的独立本地管理端。它不依赖 Python 包，也不直接访问 SQLite。

- `src/app/`：应用壳、导航、当前账号与退出登录、服务状态和路由出口；
- `src/router/`：Vue Router 路由表与登录守卫（未登录统一跳转 `/login`）；
- `src/views/`：按 `dashboard/metrics/jobs/profile/library/resume/analysis/auth/admin` 业务域分类的页面；
- `src/components/`：按业务域分类的可复用组件；
- `src/services/`：统一的后端 API 客户端，负责附带 JWT、以及在任意接口返回 401 时清理令牌并回到登录页；
- `src/composables/`：可复用的 Composition API 状态逻辑（`useMetrics` 负责按天聚合采集与投递指标）；
- `src/types/`：前后端数据契约类型；
- `src/utils/`：无状态格式化工具；
- `src/styles/`：全局视觉样式及 Ant Design Vue 适配；
- `src/main.ts`：Vite 应用入口，并注册全局未授权处理；

页面行为约定：

- 登录页只提供登录，账号由管理员在“用户管理”页创建；
- “数据指标”页与工作台的近 7 天趋势数据来自职位快照和投递记录，投递口径优先使用投递明细，没有明细时退回投递任务的成功/失败计数，界面会标注当前口径；
- 职位快照页面的“跟进”操作使用 Ant Design Vue 弹窗。当前表单连接旧版 `/v1/jobs/{id}/tracking` 兼容接口；目标模型是“求职申请 + 阶段事件时间线”，在对应数据库表和 API 完成前，不得把两个布尔字段描述为完整投递反馈闭环。

开发约束：本项目当前在 `src/main.ts` 中按需全局注册 Ant Design Vue 组件。模板新增 `a-*` 标签时，必须同步导入并 `.use(...)` 注册对应组件；生产构建通过并不能证明未注册组件已经正常渲染。完整检查规则见项目根目录 `AGENTS.md`。
- `nginx.conf`：SPA 路由回退，并将 `/v1`、`/docs`、`/openapi.json` 转发到 FastAPI；
- `Dockerfile`：构建只包含静态资源的 Web 镜像。

从仓库根目录启动：

```bash
docker compose up -d --build
```

浏览器访问 <http://127.0.0.1:8765>。页面和 API 使用同一源地址，浏览器扩展及已有调用方不需要修改端口。

单独调试前端：

```bash
npm run dev:web
```

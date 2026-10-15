# iPhone 聊天输入与回读

只在已获本次投递授权、`prepare` 返回 `opening_chat` 且当前 BOSS 会话/岗位已核对后准备草稿。完整 `greeting` 保留在内存中；不要把它写进命令行历史、文件或日志。输入不等于发送，发送必须另点一次并验收。

1. 先点可见聊天输入框，优先用 `pua_type_text(text=完整 greeting, verify=true, submit=false)`，不传 selector。已聚焦时工具内部会走 `/wda/keys`。`input_complete=false` 只用 `continue_token` 续传；部分输入、超时或结果不明时先回读现有草稿，不重放全文。
2. WorkBuddy 的 `iphone-use-cli` 有一条实测兜底：BOSS 自定义输入框已唤出键盘，但 `pua_type_text` 明确返回 `no_focused_field`、`action_executed=false`。此时先确认 BOSS 仍在前台、当前会话正确、键盘可见、草稿为空或已知缺少的尾段；若安装的 CLI 可用，用同一 WDA 会话的 `PhoneController.post("/wda/keys", {"value": [text], "frequency": 40}, timeout=60)` 输入一次。`text` 是完整文案或经回读确认的缺失尾段，不含换行；不要把 Return 当作输入或发送。CLI 未安装或焦点/草稿不确定时不走此路径。
3. 原始 `/wda/keys` 的 HTTP 成功只说明按键请求被接受，不证明草稿完整。随后 `WDAClient.session("GET", "/source")` 读取 AX XML，定位当前可编辑输入控件，解析其 `value`（注意 XML 转义）并与预期全文逐字比对，再次核对目标会话；不能只看截图、关键词命中或任意历史消息。读回失败或不一致时不点发送，也不盲目追加/清空；先确认现有内容和焦点。发送前仍无法核对时记录 `failed` 并停止该岗位；仅实际发送结果无法确认时记录 `uncertain`。
4. 前两种输入均确定未形成可用草稿时，才尝试已授权的 Mac→iPhone 通用剪贴板：仅在内存中暂存并恢复 Mac 原纯文本剪贴板，手机上使用可见的原生“粘贴”，再精确回读。自定义输入框若没有可用粘贴菜单，不反复长按。最后才检查 BOSS 第一条常用语的完整文案及点击后是填入还是直接发送；不适用则不发送。

发送前确认聊天对象、岗位及完整草稿；发送后确认消息出现在该会话，并把实际全文及真实输入方式回传。直接 CLI 路径填 `evidence.inputMethod="wda_keys"`，不能伪记为 `pua_type_text`。

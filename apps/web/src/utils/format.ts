export function formatTime(value?: string) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value))
}

const UNREADABLE_SALARY_PATTERN = /[\uE000-\uF8FF\u{F0000}-\u{FFFFD}\u{100000}-\u{10FFFD}\uFFFD]/u

export function formatSalary(value?: string | null, emptyText = '薪资未识别') {
  const normalized = value?.trim()
  if (!normalized) return emptyText
  return UNREADABLE_SALARY_PATTERN.test(normalized)
    ? '薪资暂无法识别（历史采集编码）'
    : normalized
}

export function actionLabel(action?: string) {
  return ({
    notify: '仅提醒',
    reduce_score: '降低匹配分',
    use_default_materials: '使用默认材料继续投递',
    block_delivery: '禁止投递',
  } as Record<string, string>)[action || ''] || action || '未配置动作'
}

export function sourceTypeLabel(value: string) {
  return ({ profile: '个人档案', projects: '项目库', resumes: '简历库' } as Record<string, string>)[value] || value
}

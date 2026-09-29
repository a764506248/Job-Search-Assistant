export function formatTime(value?: string) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value))
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

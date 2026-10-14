export type RecruiterActivity =
  | 'online'
  | 'just_now'
  | 'today'
  | 'within_3_days'
  | 'this_week'
  | 'this_month'
  | 'older'
  | 'unknown'

export function normalizeRecruiterActivity(text: string): RecruiterActivity {
  const value = text.trim().replace(/\s+/g, '')
  if (!value) return 'unknown'
  if (/刚刚活跃|刚刚在线/.test(value)) return 'just_now'
  if (/在线/.test(value)) return 'online'
  if (/今日活跃|今天活跃/.test(value)) return 'today'
  if (/(?:3|三)(?:日|天)内活跃|近(?:3|三)天活跃/.test(value)) return 'within_3_days'
  if (/本周活跃/.test(value)) return 'this_week'
  if (/本月活跃/.test(value)) return 'this_month'
  if (/活跃/.test(value) && /(?:周|月|年|天前|日前)/.test(value)) return 'older'
  return 'unknown'
}

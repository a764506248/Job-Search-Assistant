export interface ModelPreset {
  label: string
  baseUrl: string
  models: { label: string; value: string }[]
}

// These are OpenAI-compatible Chat Completions endpoints used by the local service.
export const modelPresets: Record<string, ModelPreset> = {
  DeepSeek: {
    label: 'DeepSeek',
    baseUrl: 'https://api.deepseek.com',
    models: [
      { label: 'DeepSeek Flash（默认）', value: 'deepseek-flash' },
      { label: 'DeepSeek V4 Pro', value: 'deepseek-v4-pro' },
    ],
  },
  Qwen: {
    label: '阿里云百炼 · 千问（中国内地）',
    baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    models: [
      { label: 'Qwen 3.7 Plus（默认）', value: 'qwen3.7-plus' },
      { label: 'Qwen Plus', value: 'qwen-plus' },
      { label: 'Qwen 3.7 Max', value: 'qwen3.7-max' },
    ],
  },
  Kimi: {
    label: '月之暗面 · Kimi（中国内地）',
    baseUrl: 'https://api.moonshot.cn/v1',
    models: [
      { label: 'Kimi K2.6（默认）', value: 'kimi-k2.6' },
      { label: 'Kimi K2.5', value: 'kimi-k2.5' },
    ],
  },
}

export const customProviders = [
  { value: 'OpenAI', label: 'OpenAI（手动配置）' },
  { value: 'OpenAI Compatible', label: 'OpenAI 兼容服务（手动配置）' },
  { value: 'Anthropic', label: 'Anthropic（手动配置）' },
  { value: '其他', label: '其他（手动配置）' },
]

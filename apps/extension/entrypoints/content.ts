import { LocalServiceClient } from '../src/local-service/client'

export default defineContentScript({
  matches: ['*://zhipin.com/*', '*://*.zhipin.com/*'],
  runAt: 'document_idle',
  async main() {
    const client = new LocalServiceClient()
    const health = await client.health().catch(() => null)

    document.documentElement.dataset.jobSearchAssistant = health?.status ?? 'offline'
  },
})

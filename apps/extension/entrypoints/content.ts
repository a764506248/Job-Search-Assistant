import { mountResumeImageTestPanel } from '../src/features/resume-image-test/panel'

export default defineContentScript({
  matches: ['*://zhipin.com/*', '*://*.zhipin.com/*'],
  runAt: 'document_idle',
  async main() {
    // 0.2.0 image-test mode: deliberately do not inject boss.js and do not start
    // the original capture/analyse/sync pipeline.
    mountResumeImageTestPanel(document)
  },
})

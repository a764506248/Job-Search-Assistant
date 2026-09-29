import { inject, onMounted, type Ref, watch } from 'vue'

export function useRefresh(load: () => void | Promise<void>) {
  const refreshVersion = inject<Ref<number>>('refreshVersion')
  onMounted(() => void load())
  if (refreshVersion) watch(refreshVersion, () => void load())
}

import { computed, ref } from 'vue'
import type { ReportMatchItem } from '../features/chat/reportMatch'

const STORAGE_KEY = 'movo.report.favorites'

function readFavoriteKeys(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return new Set()
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return new Set()
    return new Set(parsed.map((value) => String(value)))
  } catch {
    return new Set()
  }
}

function writeFavoriteKeys(keys: Set<string>) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify([...keys]))
}

const favoriteKeys = ref<Set<string>>(readFavoriteKeys())

/**
 * Persist report favorites locally until server-backed shortcuts are available.
 */
export function useReportFavorites() {
  const favorites = computed(() => favoriteKeys.value)

  function isFavorite(item: ReportMatchItem): boolean {
    return favoriteKeys.value.has(item.key)
  }

  function toggleFavorite(item: ReportMatchItem): boolean {
    const next = new Set(favoriteKeys.value)
    if (next.has(item.key)) next.delete(item.key)
    else next.add(item.key)
    favoriteKeys.value = next
    writeFavoriteKeys(next)
    return next.has(item.key)
  }

  return { favorites, isFavorite, toggleFavorite }
}

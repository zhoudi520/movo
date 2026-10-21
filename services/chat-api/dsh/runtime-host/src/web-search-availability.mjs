export function hasConfiguredWebSearch(modelProfile) {
  return modelProfile?.toolProfile?.nativeReplacements?.includes('external_search') === true
}

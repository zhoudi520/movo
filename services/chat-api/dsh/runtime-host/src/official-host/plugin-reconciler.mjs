import { pluginInstallError } from './plugin-install-error.mjs'

// A Runtime Profile is immutable. Install its declared bundle versions into
// its private DSH profile before admitting Sessions, then restart once so a
// startup-only composition can mount the new bundle layer.
export async function reconcileProfilePlugins(manager, desired, { onUnavailable } = {}) {
  if (!desired?.length) return false
  const installed = new Map((await manager.listBundles()).map(item => [item.name, item]))
  // DSH installs every bundle into one profile. A later pnpm install resolves
  // earlier dependencies again, so keep the same registry for the whole pass.
  const profileRegistry = desired.find(plugin => plugin.registry)?.registry
  let restart = false
  for (const plugin of desired) {
    const current = installed.get(plugin.name)
    if (current && current.version === plugin.version && current.enabled) continue
    if (current?.installed && current.version !== plugin.version) {
      throw new Error(`DSH plugin ${plugin.name} has a different version in this immutable profile`)
    }
    const result = current && (current.installed || (current.optional && current.version === plugin.version))
      ? await manager.setBundleEnabled(plugin.name, true)
      : await manager.installBundle(plugin.spec, {
        enabled: true,
        ...(profileRegistry ? { registry: profileRegistry } : {}),
      })
    if (result.error?.code === 'incompatible-version' && onUnavailable) {
      onUnavailable(plugin, result.error)
      continue
    }
    if (result.application === 'failed' || result.error) {
      throw pluginInstallError(plugin, result)
    }
    if (result.bundle && result.bundle !== plugin.name) {
      throw new Error(`DSH plugin spec resolved to ${result.bundle}, expected ${plugin.name}`)
    }
    if (result.version && result.version !== plugin.version) {
      throw new Error(`DSH plugin ${plugin.name} resolved to ${result.version}, expected ${plugin.version}`)
    }
    restart ||= result.changed === true || result.application === 'restart-required'
  }
  return restart
}

import assert from 'node:assert/strict'
import test from 'node:test'

import { reconcileProfilePlugins } from '../src/official-host/plugin-reconciler.mjs'

test('runtime profile installs from the registry selected during inspection', async () => {
  const options = []
  const manager = {
    listBundles: async () => [],
    installBundle: async (spec, value) => {
      options.push(value)
      const [bundle, version] = spec.split('@')
      return { bundle, version, changed: true }
    },
  }
  const restart = await reconcileProfilePlugins(manager, [{
    name: 'dsh-plugin-greet', version: '0.3.2', spec: 'dsh-plugin-greet@0.3.2',
    registry: 'https://registry.npmjs.org/',
  }, {
    name: 'movo-test-bundle', version: '1.0.0', spec: 'movo-test-bundle@1.0.0',
  }])
  assert.equal(restart, true)
  assert.deepEqual(options, [
    { enabled: true, registry: 'https://registry.npmjs.org/' },
    { enabled: true, registry: 'https://registry.npmjs.org/' },
  ])
})

test('an incompatible plugin does not block unrelated runtime plugins', async () => {
  const skipped = []
  const installed = []
  const manager = {
    listBundles: async () => [],
    installBundle: async spec => {
      installed.push(spec)
      return spec.includes('codegraph')
        ? { application: 'failed', error: { code: 'incompatible-version', incompatible: [{ name: 'codegraph' }] } }
        : { bundle: 'healthy-plugin', version: '1.0.0', changed: true }
    },
  }
  const restart = await reconcileProfilePlugins(manager, [
    { name: 'codegraph', version: '0.2.1', spec: 'codegraph@0.2.1' },
    { name: 'healthy-plugin', version: '1.0.0', spec: 'healthy-plugin@1.0.0' },
  ], { onUnavailable: (plugin, error) => skipped.push([plugin.name, error.code]) })
  assert.equal(restart, true)
  assert.deepEqual(skipped, [['codegraph', 'incompatible-version']])
  assert.deepEqual(installed, ['codegraph@0.2.1', 'healthy-plugin@1.0.0'])
})

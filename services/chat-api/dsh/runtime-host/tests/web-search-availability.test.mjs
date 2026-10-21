import test from 'node:test'
import assert from 'node:assert/strict'

import { hasConfiguredWebSearch } from '../src/web-search-availability.mjs'

test('native web search is registered only when the profile admits external search', () => {
  assert.equal(hasConfiguredWebSearch(undefined), false)
  assert.equal(hasConfiguredWebSearch({ toolProfile: { tools: [{ name: 'knowledge_search' }] } }), false)
  assert.equal(hasConfiguredWebSearch({ toolProfile: { nativeReplacements: [] } }), false)
  assert.equal(hasConfiguredWebSearch({ toolProfile: { nativeReplacements: ['external_search'] } }), true)
})

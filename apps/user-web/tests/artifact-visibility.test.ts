import assert from 'node:assert/strict'
import { visibleAnswerArtifacts } from '../src/features/execution-v3/domain/artifactVisibility'

const first = { id: 'first', ts: 1, kind: 'document', filename: 'draft.docx', object_path: 'user/draft.docx' }
const final = { id: 'final', ts: 2, kind: 'document', filename: 'final.docx', object_path: 'user/final.docx' }

assert.deepEqual(visibleAnswerArtifacts([first, final], 'running'), [])
assert.deepEqual(visibleAnswerArtifacts([first, final], 'completed'), [first, final])
assert.deepEqual(visibleAnswerArtifacts([
  { ...first, lifecycle: 'intermediate', visibility: 'internal' }, final,
], 'completed'), [final])

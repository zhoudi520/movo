import assert from 'node:assert/strict'
import { test } from 'node:test'
import { answerLines, expandQuestionAnswers } from '../src/components/chat/questionAnswerHistory'

test('answers appear before the assistant final answer and survive history reload', () => {
  const entry = {
    id: 'call-1', user_id: 'alice', questions: [
      { id: 'goal', question: 'Goal?', options: [{ label: 'Speaking' }] },
      { id: 'hours', question: 'Hours?' },
    ],
    answers: [
      { id: 'goal', selected: ['Speaking'] },
      { id: 'hours', selected: [], custom: 'Five hours' },
    ],
  }
  const messages = [
    { role: 'user', content: 'Make a plan', message_id: 'user-1' },
    { role: 'assistant', content: 'Here is the plan', message_id: 'assistant-1', question_answers: [entry] },
  ]
  const shown = expandQuestionAnswers(messages, [])
  assert.deepEqual(shown.map(message => message.role), ['user', 'user', 'assistant'])
  assert.equal(shown[1].question_answer?.user_id, 'alice')
  assert.deepEqual(answerLines(entry).map(line => line.answer), ['Speaking', 'Five hours'])
  assert.equal(expandQuestionAnswers(messages, [{ ...entry, message_id: 'assistant-1' }]).length, 3)
})

import type { DshQuestionAnswer, DshUserQuestion } from '../../platform/types'

export interface QuestionAnswerEntry {
  id: string
  user_id?: string
  message_id?: string
  created_at?: string
  questions: DshUserQuestion[]
  answers: DshQuestionAnswer[]
}

export function answerLines(entry: QuestionAnswerEntry): Array<{ question: string; answer: string }> {
  const answers = new Map(entry.answers.map(answer => [answer.id, answer]))
  return entry.questions.map(question => {
    const answer = answers.get(question.id)
    return {
      question: question.question,
      answer: [...(answer?.selected || []), ...(answer?.custom ? [answer.custom] : [])].join(', '),
    }
  })
}

export function expandQuestionAnswers<T extends { role: string; message_id?: string; question_answers?: QuestionAnswerEntry[]; _id?: string; content: string }>(
  messages: T[], submitted: QuestionAnswerEntry[],
): Array<T & { question_answer?: QuestionAnswerEntry }> {
  const result: Array<T & { question_answer?: QuestionAnswerEntry }> = []
  for (const message of messages) {
    if (message.role === 'assistant' && message.message_id) {
      const known = new Map<string, QuestionAnswerEntry>()
      for (const entry of [...(message.question_answers || []), ...submitted]) {
        if (entry.message_id && entry.message_id !== message.message_id) continue
        if (!entry.message_id && submitted.includes(entry)) continue
        known.set(entry.id, entry)
      }
      for (const entry of known.values()) {
        result.push({
          ...message, role: 'user', content: '', _id: `question-answer:${message.message_id}:${entry.id}`,
          question_answer: entry, question_answers: undefined, user_id: entry.user_id,
        } as T & { question_answer: QuestionAnswerEntry })
      }
    }
    result.push(message)
  }
  return result
}

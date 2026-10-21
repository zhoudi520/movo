<script setup lang="ts">
import { computed } from 'vue'
import { t } from '../../composables/i18n'
import { answerLines, type QuestionAnswerEntry } from './questionAnswerHistory'

const props = defineProps<{ entry: QuestionAnswerEntry }>()
const lines = computed(() => answerLines(props.entry))
</script>

<template>
  <div class="space-y-3" :aria-label="t('chat.question.answered')">
    <p class="text-xs font-semibold text-blue-700">{{ t('chat.question.answered') }}</p>
    <dl class="space-y-2">
      <div v-for="(line, index) in lines" :key="index" class="text-sm leading-6">
        <dt class="font-medium text-slate-600">{{ line.question }}</dt>
        <dd class="whitespace-pre-wrap text-slate-900">{{ line.answer }}</dd>
      </div>
    </dl>
  </div>
</template>

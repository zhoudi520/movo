import type { ArtifactItem } from './delivery'

/** Tool artifact metadata, rather than model prose, determines deliverables. */
export function visibleAnswerArtifacts(
  artifacts: ArtifactItem[],
  runStatus: string,
): ArtifactItem[] {
  if (runStatus === 'running') return []
  return artifacts.filter((item) =>
    item.lifecycle?.toLowerCase() !== 'intermediate'
    && item.visibility?.toLowerCase() !== 'internal',
  )
}

/**
 * Suggested assistant output format for report-search skills (admin prompt appendix).
 */
export const REPORT_MATCH_OUTPUT_GUIDE = `
When you return matched G3 reports, write a brief natural-language summary, then emit machine-readable matches in a single fenced block:

\`\`\`movo-report-match
{"menuPath":"\\\\Report\\\\HKRPT0260B","param":{"functionId":"HKRPT0260B","name":"{\\"CHS\\":\\"...\\",\\"CHT\\":\\"...\\",\\"EN\\":\\"...\\"}"}}
\`\`\`

Use one JSON object per report, or a JSON array for multiple reports. Do not duplicate the same JSON outside the fenced block.
`.trim()

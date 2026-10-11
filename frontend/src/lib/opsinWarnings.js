// OPSIN's warning types (OpsinWarningType, OPSIN 2.9.0) in plain words. The
// type is kept verbatim in the CSV and SDF; this text is only for the page.
const LABELS = {
  APPEARS_AMBIGUOUS: 'OPSIN warns this name looks ambiguous. The structure is one possible reading.',
  STEREOCHEMISTRY_IGNORED: 'OPSIN ignored part of the stereochemistry.',
}

export const warningLabel = (w) => LABELS[w.type] ?? `OPSIN warning: ${w.type}`

// "TYPE: message; TYPE: message" for the exports; '' when OPSIN raised none.
export const warningsText = (warnings) =>
  (warnings ?? []).map((w) => `${w.type}: ${w.message}`).join('; ')

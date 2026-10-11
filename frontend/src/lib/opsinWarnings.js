// OPSIN's warning types (OpsinWarningType, OPSIN 2.9.0) in plain words. The
// type is kept verbatim in the CSV and SDF; this text is only for the page.
const COPY = {
  APPEARS_AMBIGUOUS: {
    title: 'Ambiguous name',
    body: 'OPSIN read it, but the name can mean more than one structure. The structure here is the one OPSIN chose.',
  },
  STEREOCHEMISTRY_IGNORED: {
    title: 'Stereochemistry ignored',
    body: 'OPSIN skipped a stereo term that does not give a configuration.',
  },
}

export const warningCopy = (w) =>
  COPY[w.type] ?? { title: 'OPSIN warning', body: w.type }

// "TYPE: message; TYPE: message" for the exports; '' when OPSIN raised none.
export const warningsText = (warnings) =>
  (warnings ?? []).map((w) => `${w.type}: ${w.message}`).join('; ')

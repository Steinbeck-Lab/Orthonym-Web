// The batch outcome, counted by confidence tier.
//
// Why this exists: the batch panel used to report `done of total` plus
// `N failed`, and `failed` counts only rows the engine could not produce at
// all -- a parse failure, a naming exception, a chunk timeout. A molecule the
// engine honestly DECLINED to name is an `abstain`: a successful row with no
// name. So a run that abstained on a third of its input reported "0 failed"
// and read as a clean sweep. The numbers were in the CSV and nowhere on
// screen.
//
// The fix is not to add abstains into `failed`. That is the conflation
// PRODUCT.md forbids -- an abstain is the engine working correctly. It is to
// report the whole ladder, in the ladder's own order, and let the reader see
// which kind of miss they got.
import { NAMED_STATUSES, STATE_SHORT, STATE_CLASS, TIER_ORDER } from './statuses.js'

/** The tally as an ordered list, strongest tier first.
 *
 * A tier with no rows is omitted rather than shown as 0. The server omits
 * the field entirely until something lands in it, so a 0 here would be this
 * function inventing a measurement -- and on a running job "0 errors" and
 * "no error counted yet" are different claims.
 *
 * An unknown status is kept, not dropped: if the backend ever grows a sixth
 * tier, a batch of them must not silently vanish from the count. It gets the
 * neutral class and its raw key as the label.
 */
export function tierTally(counts) {
  if (!counts) return []
  const known = TIER_ORDER.filter((status) => counts[status] > 0)
  const unknown = Object.keys(counts)
    .filter((status) => counts[status] > 0 && !TIER_ORDER.includes(status))
    .sort()
  return [...known, ...unknown].map((status) => ({
    status,
    className: STATE_CLASS[status] ?? 'abstain',
    label: STATE_SHORT[status] ?? status,
    count: counts[status],
  }))
}

/** The two headline numbers, plus what they are counted out of.
 *
 * `named` is every tier that ships a name, verified or not. `unnamed` is the
 * rest -- an honest abstain and an error together, because from
 * the submitter's side both mean "no name came back for this molecule", and
 * the per-tier list directly below says which was which.
 *
 * `counted` is the sum, NOT the job's `total`: while a job runs these are
 * partial, and a caller that printed them against `total` would report a
 * shortfall that is just work still in progress.
 */
export function tallySummary(counts) {
  let named = 0
  let unnamed = 0
  for (const [status, n] of Object.entries(counts ?? {})) {
    if (!(n > 0)) continue
    if (NAMED_STATUSES.has(status)) named += n
    else unnamed += n
  }
  return { named, unnamed, counted: named + unnamed }
}

/** English plural for a count. */
function plural(n, word, many) {
  return n === 1 ? word : (many ?? `${word}s`)
}

/** "a, b and c" -- an Oxford-free list, because these are short clauses. */
function joinClauses(parts) {
  if (parts.length <= 1) return parts.join('')
  return `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`
}

// How each tier that SHIPS A NAME reads in a sentence. The tier's own word
// carries the claim -- "verified" for the two verified tiers, plain
// "best-effort" for the third -- so the sentence never has to make a
// confidence claim of its own.
const NAMED_PHRASE = {
  pin: (n) => `${n} verified ${plural(n, 'Preferred IUPAC Name')}`,
  fallback: (n) => `${n} verified fallback ${plural(n, 'name')}`,
  best_effort: (n) => `${n} best-effort ${plural(n, 'name')}`,
}

/** The batch outcome as a sentence or two, or null when nothing is counted.
 *
 * Deliberately says LESS than the reader might expect. It does NOT claim
 * "OPSIN read every name back and got your structure", however tempting that
 * summary is: a named row can carry no `roundtrip_smiles` at all (OPSIN
 * verify off, or no round trip could run), so an aggregate round-trip claim
 * built from the tier counts alone would assert a check this function cannot
 * see. The per-row Round-trip column is where that lives. The tier words
 * ("verified", "best-effort") are safe because they are the tiers' own.
 *
 * It counts against `counted`, never the job's declared total. A job stopped
 * at 100 of 400 has 300 molecules nobody looked at, and "95 of 400 were
 * named" would report those 300 as misses.
 */
export function outcomeMessage(counts, { finished = false } = {}) {
  const { named, unnamed, counted } = tallySummary(counts)
  if (counted === 0) return null

  const molecules = plural(counted, 'molecule')
  const lead =
    unnamed === 0
      ? `All ${counted} ${molecules} ${plural(counted, 'was', 'were')} named`
      : `${named} of ${counted} ${molecules} ${plural(named, 'was', 'were')} named`

  const breakdown = joinClauses(
    Object.keys(NAMED_PHRASE)
      .filter((status) => counts?.[status] > 0)
      .map((status) => NAMED_PHRASE[status](counts[status]))
  )

  const sentences = [breakdown ? `${lead}: ${breakdown}.` : `${lead}.`]

  // The abstain gets its own sentence, in the engine's own terms. It is not a
  // failure and must not be listed alongside one.
  const abstained = counts?.abstain ?? 0
  if (abstained > 0) {
    sentences.push(`The engine declined to name ${abstained} rather than guess.`)
  }
  const bad = counts?.error ?? 0
  if (bad > 0) {
    // "ended in an error", not "could not be read": an error row is also a
    // naming crash or a batch timeout on an input that read fine.
    sentences.push(`${bad} ${plural(bad, 'input')} ended in an error.`)
  }

  const message = sentences.join(' ')
  return finished ? message : `So far, ${message.charAt(0).toLowerCase()}${message.slice(1)}`
}

import { transportMessage } from '../lib/transport'

/**
 * The notice for a request that failed, shared by Home, /explain and
 * /from-name so one backend state reads the same everywhere. The decision
 * and its sentences live in lib/transport.js, where node --test can reach
 * them; only the unreachable fallback, which holds markup, lives here.
 */
export default function TransportNotice({ error }) {
  return (
    transportMessage(error) ?? (
      <>
        Could not reach Orthonym&rsquo;s backend ({error.message}). Is it running on{' '}
        <code>localhost:8000</code>?
      </>
    )
  )
}

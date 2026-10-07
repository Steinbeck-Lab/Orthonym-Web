import { Link } from 'react-router-dom'
import { MATOMO, MATOMO_SERVER } from '../lib/matomo'
import { LegalPage, LegalSection } from './LegalSection'
import './Legal.css'

// Privacy Policy.
//
// Section order follows the reference implementation
// (Beilstein-Institut/BChemXtractWeb, frontend/src/pages/PrivacyPage.tsx):
// who is responsible · what a visit processes · what a submission processes ·
// cookies and browser storage · third parties · your rights · objection. The
// GDPR scaffolding in §§ 1, 6 and 7 is close to that document's wording,
// because it is close to every German privacy policy's wording and there is
// no virtue in a novel phrasing of Art. 15.
//
// EVERYTHING ELSE WAS REWRITTEN AGAINST THE CODE, not adapted. A privacy
// policy that describes processing which does not happen is exactly as wrong
// as one that hides processing which does. Two concrete traps were avoided,
// both of which a copy-paste would have walked into:
//
//   * DECIMER.ai's policy (Steinbeck-Lab/DECIMER.ai,
//     resources/views/privacy_policy.blade.php) carries a long Google
//     Analytics section describing IP transfer to Google servers in the US.
//     Orthonym has no analytics of any kind — proven by grep across
//     frontend/src, index.html, package.json and vite.config.js for every
//     common vendor: zero hits. Copying that section would have disclosed
//     processing that does not exist.
//   * The reference leans throughout on Art. 6 (1) lit. f, legitimate
//     interest. That basis is NOT AVAILABLE here: Art. 6 (1) sentence 2 GDPR
//     removes it from public authorities acting in the performance of their
//     tasks, and Friedrich-Schiller-Universität Jena is a Körperschaft des
//     öffentlichen Rechts. Every basis below is lit. e (public task), or
//     lit. c with Art. 32 for the security logging.
//
// Two facts corrected against primary sources rather than inherited:
//   * The data protection officer is Dr. Jana Schleicher (appointed
//     1 January 2024, uni-jena.de/238370/datenschutzbeauftragte), NOT
//     Prof. Steinbeck, whom DECIMER.ai's policy names. A DPO may not hold a
//     role whose duties conflict with monitoring compliance (Art. 38 (6)).
//   * The supervisory authority is named, with its address. DECIMER.ai's
//     policy mentions the right to complain under Art. 77 but names no
//     authority, and the reference names the Hessian one, which is wrong for
//     Jena.
//
// The log-retention paragraph in § 2 is the one place this page had to
// refuse a nicer sentence. The reference says logs are deleted "within 2
// weeks", and its own header comment admits that is only true because a host
// cron enforces it. Orthonym has NO time-based pruning: docker-compose.yml
// caps each container at 10 MB x 3 files and rotation is by size alone. So
// the page states the criterion instead of inventing a period. If a pruning
// job is ever added, this paragraph gets a number and this comment goes.
//
// Every factual claim below was read out of the code or measured against the
// running stack. The load-bearing ones and where they come from:
//   ratelimit.py:86-172   the IP key shapes, the 60 s / 3600 s TTLs, IPv6 /64
//   redis_store.py:105-129 the `ip`, `owner`, `best_effort` and `verify`
//                         fields on the job meta hash
//   core/config.py:59-60  JOB_RESULT_TTL_SECONDS 86400, NAME_CACHE 604800
//   name_cache.py:111-161 the cache key is a SMILES hash, tied to no user
//   jobs_api.py:330-336   uuid4 job id, secrets.token_urlsafe(32) owner token
//   jobs_api.py:629-665   results endpoints take NO owner token — see § 3
//   lib/jobStore.js STORAGE_KEY, the one localStorage key Orthonym itself writes
//   docker-compose.yml:1-9 the log rotation cap
// and, measured live rather than reasoned about: a request through the
// frontend puts the visitor's address in nginx's access log and the nginx
// container's own address in the backend's, because uvicorn's
// forwarded_allow_ips does not trust the bridge network.
//
// Version 2 (25 September 2026) adds the "Report SMILES on GitHub" link: its
// own paragraph in § 5, the operator's side of a filed report in § 1, the
// two naming switches § 3 now lists among what a batch job keeps, and the
// one exception to § 6's "nothing here that can be connected to you". The
// facts come from the code: lib/github.js builds the address and puts the
// SMILES, the reason code, the formula, the error message and the page name
// in it, plus the best-effort and OPSIN-verify switches the result was named
// with (Home stamps them on each fast-path row; a batch job's come back from
// GET /api/jobs/{id}, stored by redis_store.create_job), and deliberately NOT
// the batch line's own ID token, the job id or the owner token. It offers
// the link only for an abstain the engine itself reached (not one the
// visitor's best-effort switch withheld), a crash, or the one molecule a
// batch timeout interrupted. components/ReportLink.jsx
// renders it as a plain link with rel="noopener noreferrer": nothing is
// fetched until the visitor clicks, and no Referer is sent even then. A
// signed-in visitor's GitHub session cookie does travel with that top-level
// navigation, which is why § 5 names the account and not only the IP. The
// repository is VITE_GITHUB_URL, the same one the header links to, and
// `none` removes both -- in which case § 1's and § 5's report paragraphs
// describe a link that does not exist and must be edited by hand.
//
// Version 3 (28 September 2026) adds the issue tab: the crimson "Issues" tab
// on the left edge of every page on a wide screen, and "Report an issue" in
// the menu on a narrow one (components/IssueBuddy.jsx, Navigation.jsx). Both
// open lib/github.js newIssueUrl(), the repository's BLANK /issues/new form:
// no query string, so nothing from the page goes with it. Same
// rel="noopener noreferrer", same repository, same `none` switch as above.
//
// Version 4 (7 October 2026) adds Matomo page counting, and with it the end of
// the "no analytics of any kind" sentence above -- but ONLY where it is true.
// Every Matomo paragraph renders on `MATOMO` (lib/matomo.js), which is null
// unless the deployment sets both build args AND lib/matomo.js records the two
// server facts this page states (IP masking, raw-data retention). Without them
// the page keeps saying there is no analytics, which is then still true.
// What the browser sends was MEASURED, not read off Matomo's docs: a
// production build with the build args set, driven through five routes in
// Chromium with every matomo.php request intercepted (none reached the
// server). Each request carried url (origin + path only: a visit to
// /structure?smiles=SECRET#frag was reported as /explain), urlref, action_name,
// h/m/s, and Matomo's own counters (_idn, _refts, pv_id, r, rec, send_image)
// with an EMPTY visitor id and empty client hints; no screen size, plugin flags
// or timings (disableBrowserFeatureDetection, disablePerformanceTracking). The
// browser held zero cookies and no new storage afterwards. The server's operator is the
// owner's statement (2026-10-07), consistent with matomo.nfdi4chem.de
// resolving to the university's own proxy, 141.35.136.25.

// The UNIVERSITY leads, the working group follows as the responsible unit.
// Art. 4 (7) requires the controller to be a natural or legal person, public
// authority, agency or other body, and an Arbeitsgruppe inside an institute
// is none of those — the legal person is Friedrich-Schiller-Universität Jena.
// The page proved this against itself while the group led: it named the
// UNIVERSITY's data protection officer and the UNIVERSITY's supervisory
// authority, neither of which follows unless the university is the
// controller.
//
// This does not reverse the owner's choice about the IMPRESSUM, which still
// leads with the working group in DECIMER.ai's shape. Who is named as the
// § 5 DDG service provider and who is the Art. 4 (7) controller are two
// different questions, and only the second turns on legal personality.

// EIGHT, not the reference's ten. The reference lists the standard German
// server-log enumeration, which includes a GMT offset and a browser-language
// field that nginx's default `main` format does not record; listing a field
// that is not recorded is the same class of error as omitting one that is.
// Note also that "Browser and its version" and "Operating system" are ONE
// recorded field — the User-Agent string — presented as the two things a
// reader can actually read out of it.
const LOG_FIELDS = [
  'IP address',
  'Date and time of the request',
  'Content of the request, including any parameters in the address',
  'Access status / HTTP status code',
  'Amount of data transferred',
  'Website from which the request came to us (referrer)',
  'Browser and its version',
  'Operating system',
]

const RIGHTS = [
  'the right to be told whether data concerning you is processed, to be informed about that processing, and to receive a copy of the data (Art. 15 GDPR)',
  'the right to have incorrect or incomplete data corrected or completed (Art. 16 GDPR)',
  'the right to have data concerning you erased (Art. 17 GDPR, subject to the exceptions in Art. 17 (3)), or, where further processing is required, to have that processing restricted (Art. 18 GDPR)',
  'the right to object to the processing of data concerning you (Art. 21 (1) GDPR)',
  'the right to complain to a data protection supervisory authority (Art. 77 GDPR)',
]

// § 2's analytics paragraphs. Rendered only when MATOMO is set, so every
// sentence here is about a tracker that is actually running; the two server
// facts come from lib/matomo.js, where the tracker refuses to start without them.
function PageCounting() {
  const { host, operator, ipBytesMasked, rawDataMonths } = MATOMO_SERVER
  return (
    <>
      <h3>Counting page views</h3>
      <p>
        To see which pages are used, each page you open is also counted by Matomo, a web analytics
        program, on the server <code>{host}</code>. That server is run by {operator} itself, so
        these counts do not leave the university.
      </p>
      <p>
        For each page, your browser sends that server the page’s address, cut off before any
        &ldquo;?&rdquo; or &ldquo;#&rdquo;; the previous page on this site, or the address of the
        site you came from; the page’s title; your local time of day; and Matomo’s own counters,
        which number the request and not you. Like every web request, it also carries your IP
        address and your browser’s identification string. It never carries anything you type,
        draw, upload or submit, and it does not report the links you follow. Your screen size,
        browser plugins and page-load timings are not collected, and no cookie is set.
      </p>
      <p>
        The server stores your IP address{' '}
        {ipBytesMasked === 0
          ? 'in full'
          : `with the last ${ipBytesMasked === 1 ? 'byte' : `${ipBytesMasked} bytes`} of an IPv4 address removed, and an IPv6 address shortened likewise`}
        . It deletes the raw record of each visit after {rawDataMonths} months; after that only
        aggregated statistics remain. The legal basis is Art. 6 (1) lit. e GDPR in conjunction with
        the Thüringer Datenschutzgesetz. You can object to it as described in § 7.
      </p>
    </>
  )
}

function Privacy() {
  return (
    <LegalPage
      title="Privacy Policy"
      lede="What this site does with your data, written from the code rather than from a template."
      label="Privacy Policy"
    >
        <LegalSection id="controller" index="§ 1" title="Who is responsible for your data">
          <p>
            This policy tells you what personal data is processed when you use this website, why,
            on what legal basis, and for how long. Personal data means any information relating to
            you as an identifiable person — an IP address, for example.
          </p>
          <p>
            The controller within the meaning of Art. 4 (7) GDPR is:
          </p>
          <p>
    Friedrich-Schiller-Universität Jena
    <br />
    Institut für Anorganische und Analytische Chemie
    <br />
    Cheminformatics and Computational Metabolomics
    <br />
    Lessingstr. 8
    <br />
    07743 Jena
    <br />
    Germany
          </p>
          <p>
            Telephone: +49 3641 9-48780
            <br />
            Email:{' '}
            <a href="mailto:christoph.steinbeck@uni-jena.de">christoph.steinbeck@uni-jena.de</a>
            <br />
            Website:{' '}
            <a href="https://cheminf.uni-jena.de/" target="_blank" rel="noopener noreferrer">
              cheminf.uni-jena.de
            </a>
          </p>
          <p>
            Friedrich-Schiller-Universität Jena is a corporation under public law, represented by
            its President; the Cheminformatics and Computational Metabolomics group operates this
            site within it. The full legal identification is on the{' '}
            <Link to="/imprint">Impressum</Link>.
          </p>
          <h3>Data protection officer</h3>
          <p>
            The university’s data protection officer is Dr. Jana Schleicher, Stabsstelle
            Informationssicherheit und Datenschutz, Inselplatz 9, 07743 Jena. You can reach the
            office at <a href="mailto:datenschutz@uni-jena.de">datenschutz@uni-jena.de</a>, or Dr.
            Schleicher directly at{' '}
            <a href="mailto:jana.schleicher@uni-jena.de">jana.schleicher@uni-jena.de</a> for
            personal or sensitive matters.
          </p>
          <h3>If you contact us</h3>
          <p>
            If you write to us by email or letter, or telephone us, the details you give us are
            processed for the purpose of answering you, under Art. 6 (1) lit. e GDPR in conjunction
            with the Thüringer Datenschutzgesetz. We delete them once they are no longer needed for
            that purpose, unless a statutory retention period applies.
          </p>
          <h3>If you report a result or an issue on GitHub</h3>
          <p>
            The repository that a &ldquo;Report SMILES on GitHub&rdquo; link or the
            &ldquo;Issues&rdquo; tab opens belongs to our working group. If you submit an issue there, we read it, together with the GitHub
            account it is filed under, to find and fix what went wrong in the naming engine, under
            Art. 6 (1) lit. e GDPR in conjunction with the Thüringer Datenschutzgesetz. The issue
            stays in the repository&rsquo;s issue history, where it records the fix, until it is no
            longer needed for that purpose. You can ask us to delete it at any time (§ 6). What
            reaches GitHub when you follow the link is described in § 5.
          </p>
        </LegalSection>

        <LegalSection
          id="visit"
          index="§ 2"
          title="What is processed when you visit"
          note="Every website records this much; the honest part is saying how long it is kept."
        >
          <p>
            When you open a page on this site, your browser sends data that the web server records
            in an access log. This is technically necessary to deliver the page to you and to keep
            the service stable and secure:
          </p>
          <ul>
            {LOG_FIELDS.map((field) => (
              <li key={field}>{field}</li>
            ))}
          </ul>
          <p>
            The legal basis is Art. 6 (1) lit. e GDPR in conjunction with the Thüringer
            Datenschutzgesetz: processing necessary for the performance of a task carried out in
            the public interest. Art. 32 GDPR is the security obligation this logging helps us
            meet; it is not itself a second legal basis for it.
          </p>
          <p>
            Please note one consequence of how the site works. Some requests carry what you
            submitted in the address itself — a structure you asked to have explained, or a name you
            asked to have parsed. Those requests therefore appear in the access log with the
            structure or name in the recorded address, on the same line as your IP address.
          </p>
          <p>
            We cannot give these logs a fixed retention period, because nothing deletes them by
            date. Each of our own containers keeps at most 30 megabytes of log, in three files, and
            the oldest is discarded as new entries arrive — so how far back the log reaches depends
            on how busy the site has been, not on a calendar, and a quiet period makes an entry last
            longer rather than shorter. Log entries are not combined with any other data, are not
            used to profile you, and are not passed to anyone else. An entry needed as evidence of a
            specific security incident is kept until that incident is resolved.
          </p>
          <p>
            That cap describes the containers this application runs in. On a public deployment a
            TLS terminator sits in front of them and keeps an access log of its own, with the same
            kind of contents. It runs on the same host, under the same people, and it is not
            governed by the cap above.
          </p>
          <p>
            The application’s own log, which is separate from the access log, records job
            identifiers, counts and timings. It does not record your IP address.
          </p>
          {MATOMO && <PageCounting />}
        </LegalSection>

        <LegalSection
          id="naming"
          index="§ 3"
          title="What is processed when you name a structure"
          note="Orthonym has no accounts, no sign-in and no user profiles. Nothing below is linked to a person."
        >
          <h3>Rate limiting</h3>
          <p>
            To keep the service available to everyone, requests are counted per IP address. The
            counters live in our own in-memory data store, named after the address they count, and
            expire on their own: the per-minute counters after 60 seconds, the hourly job counter
            after one hour. An IPv4 address is stored in full; an IPv6 address is reduced to its
            /64 network prefix before it is stored, so IPv6 visitors are counted per network rather
            than per device. These counters record only how many requests were made — never what
            was in them.
          </p>
          <h3>Single structures</h3>
          <p>
            A request for ten molecules or fewer is answered directly. The result is computed, sent
            to you, and the copy held for the transfer is deleted immediately rather than left to
            expire.
          </p>
          <h3>Batch jobs</h3>
          <p>
            A larger submission becomes a job you can come back to. For 24 hours we keep the job’s
            rows — for each molecule, what you submitted, the standardised structure, the name
            produced, the round-trip check, the molecular formula and any error — together with the
            two naming switches you chose, the submitting IP address, which is used only to release
            your concurrent-job slot, and the job’s owner token. All of it is deleted automatically after 24 hours, or immediately if
            you delete the job yourself.
          </p>
          <p>
            One thing about job links is worth stating plainly, because it is a design decision and
            not an oversight. A job’s results can be read by anyone who has the link. The link
            contains 32 hexadecimal characters carrying 122 bits of randomness and is not
            guessable, but it is not protected by a password either — sharing it shares the results. The separate owner token, returned
            to you once when the job is created, is what is required to cancel or delete a job, so
            sharing a results link does not hand over the ability to destroy the results.
          </p>
          <h3>Uploaded files</h3>
          <p>
            An uploaded <code>.sdf</code>, <code>.mol</code> or <code>.csv</code> file is read into
            memory and parsed. We never read or store its filename. Files larger than one megabyte
            are written to a temporary file by the web framework while the upload is being received
            and are deleted as soon as the request has been read; this is not something the
            application controls or retains.
          </p>
          <h3>The shared name cache</h3>
          <p>
            A structure that has already been named is kept in a shared cache for seven days, so
            that naming it again is instant. An entry is found by a hash of the standardised
            structure and holds that structure, the name, the round-trip result and the formula. It
            is not linked to you, to your IP address or to any session, and two people submitting
            the same molecule share the same entry.
          </p>
          <h3>Where this is stored</h3>
          <p>
            All of the above lives in a Redis instance on our own server, which writes periodic
            snapshots to disk. It is not held only in memory, and it is not shared with any external
            service.
          </p>
          <p>
            The legal basis for all processing in this section is Art. 6 (1) lit. e GDPR in
            conjunction with the Thüringer Datenschutzgesetz.
          </p>
        </LegalSection>

        <LegalSection
          id="cookies"
          index="§ 4"
          title="Cookies and what is stored in your browser"
          note="This site sets no cookies, which is why it shows you no consent banner."
        >
          <p>
            Orthonym sets no cookies of its own. There is no login, no session and nothing to
            remember about you between visits, so there is nothing to ask your consent for and no
            banner to dismiss.
          </p>
          <p>
            The following are nevertheless stored by your browser for this site, and all of them
            stay in your browser. None needs your consent: § 25 (2) Nr. 2 TDDDG exempts storage
            that is strictly necessary to provide a service you have expressly asked for.
          </p>
          <ul>
            <li>
              <code>orthonym.jobs.v2</code> — a list of up to eight batch jobs you recently submitted,
              each with its job id, its owner token, how many molecules it held, when it expires and
              its status. Without it, closing the tab would lose the ability to return to, cancel or
              delete your own job. Entries are removed when the job expires, and in any case within
              24 hours. Nothing in this list is sent anywhere except back to this site, and only to
              cancel or delete the job it names.
            </li>
            <li>
              <code>ketcher-opts</code> and <code>ketcher-tmpls</code> — written by the structure
              editor bundled into the Explain page, and only if you change its settings or save one
              of your own drawings as a template — each is written in response to something you did,
              which is what makes it strictly necessary to the feature you asked for. They hold your
              editor preferences and the structures you chose to save. Neither is sent to our
              server.
            </li>
          </ul>
          <p>
            The structure editor also contains a 3D viewer which, when opened, reads a cookie named{' '}
            <code>settings</code> if one exists. Nothing in the interface as shipped writes that
            cookie.
          </p>
          <p>
            Nothing else is stored: no session storage, no browser database, no service worker. You
            can clear everything this site has stored at any time through your browser’s site-data
            settings; the only effect is that a batch job in progress can no longer be found from
            this browser.
          </p>
        </LegalSection>

        <LegalSection
          id="third-parties"
          index="§ 5"
          title="Third parties"
          note="There are none, unless you choose to report a result or an issue on GitHub. This section exists to say so precisely."
        >
          {MATOMO ? (
            <p>
              This site uses no tag manager, no error-reporting service and no telemetry. Its one
              form of web analytics is the page counting described in § 2, on the university’s own
              Matomo server. There is no Google Analytics, no Plausible and no equivalent.
            </p>
          ) : (
            <p>
              This site uses no web analytics, no tag manager, no error-reporting service and no
              telemetry of any kind. There is no Google Analytics, no Matomo, no Plausible and no
              equivalent.
            </p>
          )}
          <p>
            Every request your browser makes while using this site goes to this site
            {MATOMO && (
              <>
                , apart from the page counting in § 2: the counting script and each page count go to
                the university’s Matomo server, <code>{MATOMO_SERVER.host}</code>
              </>
            )}
            . The typefaces are served from here, not from Google Fonts or any other font service.
            No {MATOMO && 'other '}image, script or stylesheet is loaded from another domain. The
            structure editor runs entirely in your browser and contacts no chemistry server.
          </p>
          <p>
            The structures and names you submit are not sent to any third party, unless you follow a
            report link yourself (see below). Naming, verifying, stereo labelling and drawing all
            happen on our own server, in software installed there. The server makes no outbound
            request while answering yours.
          </p>
          <p>
            This site does link to other sites — the institutions behind it, the projects it
            depends on, a handful of references. Following one of those links is a visit to that
            site, under its own privacy policy, and it happens only when you click.
          </p>
          <p>
            One kind of link is different. When Orthonym cannot name a molecule, or fails while
            naming it, the result offers a &ldquo;Report SMILES on GitHub&rdquo; link. That link carries the
            molecule&rsquo;s SMILES string and what Orthonym said about it (its reason code, formula
            or error message, the page you were on, and the two naming switches it was produced
            with), so that GitHub can fill in a new issue for
            you. It carries nothing else from your submission: not an ID you gave the compound, and
            not your batch job. GitHub receives all of this as soon as you click, together with
            your IP address and, if you are signed in to GitHub, your GitHub account, even if you
            then close the page without submitting anything. If you submit the issue, GitHub stores
            it under your GitHub account, and everyone who can see the repository can read it,
            including us (§ 1). GitHub, Inc. is based in the United States, and GitHub&rsquo;s own
            privacy statement applies to what it receives. Do not use the link for a structure you
            need to keep confidential.
          </p>
          <p>
            The &ldquo;Issues&rdquo; tab at the left edge of the page (in the menu on a small
            screen, &ldquo;Report an issue&rdquo;) opens GitHub&rsquo;s empty form for a new issue in
            the same repository. It carries nothing from this site: no structure, no name and no
            result. Following it is a visit to GitHub like the links above, so GitHub receives your
            IP address and, if you are signed in, your GitHub account. What you then write and
            submit is stored and shown exactly as described for a report.
          </p>
          <p>
            This site itself transfers no data to a third country or to an international
            organisation. The one route by which anything you submitted reaches one is a report
            link: following it sends the data described above to GitHub in the United States, and an
            issue you submit, from a report link or the Issues tab, is then kept there, in our
            repository.
          </p>
        </LegalSection>

        <LegalSection id="rights" index="§ 6" title="Your rights">
          <p>In respect of personal data concerning you, you have:</p>
          <ul>
            {RIGHTS.map((right) => (
              <li key={right}>{right}</li>
            ))}
          </ul>
          <p>
            The right to data portability under Art. 20 GDPR is not among them, and its absence is
            deliberate rather than an oversight: Art. 20 (1) (a) confines that right to processing
            based on consent or on a contract, and Art. 20 (3) disapplies it altogether to
            processing carried out in the performance of a public task. Nothing here rests on
            consent or on a contract.
          </p>
          <p>
            There is also no automated decision-making and no profiling within the meaning of
            Art. 22 GDPR. Naming a structure is an automated process, but what it produces is a
            name, not a decision about you.
          </p>
          <p>
            To exercise any of these, write to the controller or to the data protection officer
            named in § 1. Be aware that most of what this site processes is not linked to you by
            name: outside the 24-hour lifetime of a batch job you submitted, and the short-lived
            rate-limit counters, there is generally nothing here that can be connected to you, which
            also limits what a request for access can return. The exception is an issue you filed
            through a report link (§ 1): it is tied to your GitHub account, and we can find it,
            give you a copy or delete it.
          </p>
          <h3>Complaints</h3>
          <p>
            You have the right to complain to a data protection supervisory authority about how we
            process data concerning you. For this controller that authority is:
          </p>
          <p>
            Thüringer Landesbeauftragter für den Datenschutz und die Informationsfreiheit
            <br />
            Häßlerstraße 8
            <br />
            99096 Erfurt
            <br />
            Germany
            <br />
            <br />
            Email:{' '}
            <a href="mailto:poststelle@datenschutz.thueringen.de">
              poststelle@datenschutz.thueringen.de
            </a>
            <br />
            Website:{' '}
            <a href="https://tlfdi.de/" target="_blank" rel="noopener noreferrer">
              tlfdi.de
            </a>
          </p>
        </LegalSection>

        <LegalSection id="objection" index="§ 7" title="Objection to processing">
          <p>
            Where we process personal data concerning you in the performance of a public task under
            Art. 6 (1) lit. e GDPR, you may object to that processing under Art. 21 (1) GDPR on
            grounds relating to your particular situation. Please tell us those grounds when you
            object. We will then either stop or adjust the processing, or explain the compelling
            legitimate grounds on which we continue it.
          </p>
          <p>
            For the access log described in § 2, those grounds are short and can be stated in
            advance: recording it is inseparable from delivering a page to you at all, so we cannot
            serve the site and honour an objection to it at the same time. That is a reason we would
            have to demonstrate if you objected — not an exception to your right to object.
          </p>
          <p className="legal-updated">Version 4 — 7 October 2026</p>
        </LegalSection>
    </LegalPage>
  )
}

export default Privacy

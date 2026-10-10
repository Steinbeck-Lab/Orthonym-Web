// What each route tells a search engine and a link preview: its title, its
// one-line description, and its canonical address. RouteMeta.jsx writes them
// into <head> on every navigation. Every title carries "Orthonym" so a search
// for the name finds every page of the site under it.

export const SITE_URL = 'https://orthonym.decimer.ai'

export const ROUTE_META = {
  '/': {
    title: 'Orthonym — free IUPAC name generator for chemical structures',
    description:
      'Free IUPAC naming tool. Paste SMILES, upload a file or draw a molecule and get its IUPAC name, checked by an OPSIN round trip. Deterministic and open source.',
  },
  '/from-name': {
    title: 'IUPAC name to structure converter · Orthonym',
    description:
      'Turn IUPAC names into structures with OPSIN: see each molecule, copy its SMILES and download the set as CSV or SDF.',
  },
  '/explain': {
    title: 'Explain an IUPAC name, part by part · Orthonym',
    description:
      'See how an IUPAC name is built. Point at any part of the name and Orthonym lights up the atoms it describes.',
  },
  '/about': {
    title: 'About Orthonym — how it names molecules and how accurate it is',
    description:
      'How the Orthonym engine turns structures into IUPAC names, what its confidence tiers mean, its measured accuracy, and how to cite it.',
  },
  '/imprint': { title: 'Impressum · Orthonym', description: 'Who runs Orthonym and how to reach us.' },
  '/privacy': { title: 'Privacy · Orthonym', description: 'What Orthonym processes when you use it, and why.' },
  '/terms': { title: 'Terms of use · Orthonym', description: 'The terms for using Orthonym and its results.' },
}

/** The head entries for `pathname`; an unknown path gets Home's. */
export function metaFor(pathname) {
  const path = ROUTE_META[pathname] ? pathname : '/'
  return { ...ROUTE_META[path], canonical: `${SITE_URL}${path}` }
}

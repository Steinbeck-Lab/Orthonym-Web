<div align="center">

<img src="docs/readme/banner.svg" alt="Orthonym. Verified IUPAC names for chemical structures. Deterministic, rule-based, every name read back by OPSIN." width="100%">

<br>

<a href="https://orthonym.decimer.ai"><img src="docs/readme/try.svg" alt="Try Orthonym" height="48"></a>&nbsp;&nbsp;<a href="#run-it-yourself"><img src="docs/readme/run.svg" alt="Run it yourself" height="48"></a>

<br>

**A chemical structure goes in. An IUPAC name comes out, with the confidence it has actually earned.**

[![Licence: MIT](https://img.shields.io/badge/licence-MIT-c41e3a?style=flat-square)](LICENSE)
[![Release](https://img.shields.io/github/v/release/Steinbeck-Lab/Orthonym-Web?style=flat-square&color=1a1a1a&label=release)](https://github.com/Steinbeck-Lab/Orthonym-Web/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/Steinbeck-Lab/Orthonym-Web/ci.yml?branch=main&style=flat-square&label=ci&color=2f6b28)](https://github.com/Steinbeck-Lab/Orthonym-Web/actions/workflows/ci.yml)

</div>

## How every name is checked

<picture>
  <source media="(max-width: 700px)" srcset="docs/readme/roundtrip-narrow.svg">
  <img src="docs/readme/roundtrip.svg" alt="The round trip for caffeine. Your structure goes to the Orthonym engine, which writes the name 1,3,7-trimethyl-3,7-dihydro-1H-purine-2,6-dione. OPSIN reads that name back into a structure. The InChIKey of your structure and the InChIKey of what OPSIN read are both RYYVLZVUVIJVGH-UHFFFAOYSA-N, so the name is shown as a verified Preferred IUPAC Name. Below, the five tiers every verdict can land on: PIN, fallback, best effort, no name, error." width="100%">
</picture>

**Deterministic.** Orthonym names structures with **the Orthonym engine**, which is rule-based:
no neural network, no sampling. The same structure always gets the same name.

**Checked.** Every name is handed to [OPSIN](https://github.com/dan2097/opsin), which never saw
your structure, and parsed back. The two structures are compared by full InChIKey, and the
result is shown next to the name.

**Honest.** The verdict lands on one of five tiers, drawn as a mark under the name wherever it
appears. The shape of the mark carries the tier and the colour only agrees, so the five stay five
in greyscale and for every common colour deficiency.

## See it working

<img src="docs/screenshots/results.png" alt="Six molecules on the Translate page, one per state: ethanol, a Preferred IUPAC Name; a fused polycyclic, a verified fallback; retinol, a best-effort name from the general engine; sphingosine, a name not checked here because no round-trip result came back; uranium trioxide, not named; and an unreadable SMILES, an error." width="100%">

<sub>Real results from the Translate page: one molecule for every state a result can be in.</sub>

<br><br>

<img src="docs/screenshots/explain.png" alt="The Explain page taking caffeine's name apart, with one part of the name hovered and the atoms it describes lit in the structure" width="100%">

<sub>Explain takes a name apart and lights the atoms each part describes.</sub>

## When it cannot name a molecule

<table>
<tr>
<td width="48%"><img src="docs/screenshots/report.png" alt="A result card for uranium trioxide: Could not confidently name this, the formula O3U, and a Report SMILES on GitHub button"></td>
<td>

It says so, and declines rather than guess. The card then offers **Report SMILES on GitHub**,
which opens a new issue here with the SMILES, the engine's reason and the settings already
filled in. The label names what leaves the page, and the privacy policy says exactly what the
link carries.

</td>
</tr>
</table>

## What's inside

| | |
|:--|:--|
| **Translate** | Paste SMILES, upload `.sdf`, `.mol` or `.csv`, or draw in Ketcher. Up to ten molecules answer at once; more run as a job with progress, a tally by tier and a CSV. |
| **Name → Structure** | The reverse, on OPSIN: a name in, a structure out. |
| **Explain** | A name taken apart, each part mapped onto the atoms it describes. |
| **About** | How a name is built and checked, and a live board of the service's health. |

Built on [the Orthonym engine](#the-engine) · [OPSIN 2.9.0](https://github.com/dan2097/opsin) ·
[RDKit](https://www.rdkit.org/) · [CDK 2.12](https://cdk.github.io/) ·
[Ketcher](https://github.com/epam/ketcher) · FastAPI · Celery · Redis · React 19

## Run it yourself

```bash
docker compose up -d --build        # redis, backend, two workers, frontend
open http://localhost:8080
```

Wait for a worker to report a live JVM. Until one does, Orthonym refuses to name anything, on
purpose: a name it cannot check is a name it will not serve.

```bash
curl -s http://127.0.0.1:8000/api/health
# {"status":"OK","opsin":"available"}
```

Deployment, sizing profiles and the batch-job API are in **[INSTALL.md](INSTALL.md)**.

## How to cite

A paper describing Orthonym is in preparation. Until it is published, please cite the software:
GitHub's **Cite this repository** button, built from [`CITATION.cff`](CITATION.cff), gives the
entry in APA and BibTeX, and lists the Orthonym engine it builds on.

## The engine

This repository, Orthonym-Web, is the web app. Its naming engine, **the Orthonym engine**, lives
in its own repository and is **not public**, so `backend/vendor/` is populated from a local
checkout and a fresh clone cannot name a molecule until it is. See
[the Orthonym engine dependency](INSTALL.md#the-orthonym-engine-dependency).

It is not STOUT-V2 in a browser: that neural model is a separate, unrelated project. Nothing here
samples, and nothing here is a language model.

## Licence

MIT, see [LICENSE](LICENSE). Bundled third-party components keep their own licences, two of them
under copyleft terms; the running site lists all of them on its Terms page, and
`backend/vendor/cdk/NOTICE` records CDK's provenance and checksum.

<div align="center">
<br>
<sub>Made with ☕ by <a href="https://kohulanr.com">Kohulan Rajan</a> at the
<a href="https://www.beilstein-institut.de/en/">Beilstein-Institut</a> <img src="docs/screenshots/credit-x.svg" alt="✕" height="10">
<a href="https://cheminf.uni-jena.de">Steinbeck Lab</a></sub>
</div>

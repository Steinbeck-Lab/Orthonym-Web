# Changelog

## [0.4.2](https://github.com/Steinbeck-Lab/Orthonym-Web/compare/v0.4.1...v0.4.2) (2026-10-03)


### Bug Fixes

* **explain:** a faithful match is used even when the match cap is hit ([dbd882d](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/dbd882d433abce0dc687f05eaa4a7c6b1efcbd15))
* **explain:** map SMILES-path parts through one faithful match ([2d765b4](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/2d765b4bef39193a930813ffc7f46cbf1d6e5ff0))
* **explain:** the faithful match keeps stereo ([16c7e0a](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/16c7e0a0669d05af1fca374dd9d420c9b098d18a))
* **explain:** the SMILES path keeps parts over symmetric atoms ([eb44960](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/eb449601289473cc4516a0f61e195595069efb18))
* show cisplatin as a connected square-planar structure ([5f98c0d](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/5f98c0db3eaa1e1f8bf70b873e7cdc2f4ae5f8ea))
* show cisplatin as a connected square-planar structure ([5e382e9](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/5e382e9c686ae918346907708928c45e10dd72bb))


### Refactoring

* **explain:** factor the SMILES-path remap into one function ([cdcb050](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/cdcb050782a2e3e658aacdb67ad6f67a0b4cc3ad))


### Documentation

* describe the SMILES-path remap and the new census numbers ([8a5ac35](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/8a5ac35dbafa82b7c609faefe5ba4bc37be6d79f))
* the SMILES-path match also keeps stereo ([bb54a00](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/bb54a004693e55bef86355e51d99d2cf18b41015))

## [0.4.1](https://github.com/Steinbeck-Lab/Orthonym-Web/compare/v0.4.0...v0.4.1) (2026-10-02)


### Bug Fixes

* **explain-ui:** the nothing-lights note no longer says the part names no atom ([32ea091](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/32ea091af0e1f930f982eca8911446a11ee25baf))
* **explain:** a chain line is measured; a bracket keeps its own set word; a racemate mark is 'part of' on either side ([ea56cf4](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/ea56cf49a7ab5fed1e8650804f0620edb9609629))
* **explain:** a group's line names the bare group and counts the hydrogens its atoms carry ([d22fd48](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/d22fd4857b8b45b5327b6f196579b7f079c0643e))
* **explain:** a parent line claims a benzene ring, or the only core, only when it is one ([69a077a](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/69a077a6c9174b2a2b537773de0c4c5e41261a77))
* **explain:** E, Z and pseudoasymmetric marks stay absolute in a relative set; a charged atom lost its hydrogen to the ending ([aae211f](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/aae211f2bf190d0bce1801942a7807b2a93e235c))
* **explain:** every hover line is true of the molecule on screen ([170da8f](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/170da8f33fe74592a64260a099e246c2c7d7fd2b))
* **explain:** hover lines for sets written beside their marks, lone anomeric atoms, thio sugars and hydrates ([6423c12](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/6423c12139a3d52d7ddfdaaff6aad67a79821e63))
* **explain:** hydrogen-locant and anomer lines say what the lit atom really holds ([a10f110](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/a10f11005b4eabb257de0b4aa88179a1e21e148e))
* **explain:** spiro, isotope and stereo lines say what each kind of mark means ([eec27e6](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/eec27e61530ef86f0700801b01e065beafb23780))
* **explain:** the census reads every claim in a line; acid-addition parts and multiplied hydrates are not cores; a set word covers the whole name ([7011c3c](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/7011c3c972bfa9b406b02e7c31c33d7d5918f10f))


### Refactoring

* **census:** name the set-word patterns and reuse the token bracket utilities ([2a73924](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/2a73924199832cbfa4a9be8e7e8419d6af3b71e2))
* **census:** one count-word table for the chain and parent checks ([c0a9d39](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/c0a9d391e5fc43c789d9db707bfb9d4ccb226f07))
* **explain:** collect a name's stereo set words once and reuse them per mark ([ffc0118](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/ffc01183fc758c3f71bf6c5891cc47a654d61da1))
* **explain:** create each parent node through one helper and restate its line from the node ([e1294cb](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/e1294cb3428fa86b9b657666939dc736b877beb6))
* **explain:** one anomer line helper for the two sugar sites ([3392b22](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/3392b227de6a5993b86c12d31e2b1be12fdd691b))
* **explain:** one hydrogen-count table with structured fields ([f38ddd1](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/f38ddd11b0f02aaa3ea39b5fb15bafca5e149849))
* **explain:** share the atom degree, plain-atom and anomeric-neighbour helpers ([5a84f9d](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/5a84f9d370bdfcf5cc037e8bcaf8839683cef6f4))
* **explain:** tidy the stereo, part, modifier and spiro line builders ([08a48f1](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/08a48f18ab579955ca982561b9d6ff0e2805998d))


### Documentation

* CLAUDE.md records the hover-line check and the 698-name corpus ([890b677](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/890b677c3e50e6dfd6876d496720407dc221fede))

## [0.4.0](https://github.com/Steinbeck-Lab/Orthonym-Web/compare/v0.3.0...v0.4.0) (2026-10-01)


### Features

* **explain-ui:** node helpers and smallest-node hover map ([b06aaa9](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/b06aaa94801793208241e73c42f4019c3044ea25))
* **explain-ui:** render the v2 node list ([5167f5e](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/5167f5e0aa49d93f03639061c8b7067009f6cd7d))
* **explain:** build the flat node list; stereo by written scope, checked against real stereocentres ([58965ee](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/58965ee42ef99321433ac44da4d12b8269ed0937))
* **explain:** explain every name OPSIN can read, from one OPSIN trace ([ef29535](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/ef29535c4f792b6648659df0cfb7f3cdc8f40476))
* **explain:** token ownership from OPSIN placement and written brackets; token-kind table ([130eba9](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/130eba9838e6cf668324e42e26538011efad6a4a))
* **explain:** trace OPSIN once for atoms, written tokens and owners ([5d7a10c](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/5d7a10c7e28302709eef668a8a9976d359e5e85c))
* **explain:** v2 response with flat nodes, per-node honesty and span alignment ([edad59a](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/edad59aa17c9881609b1140dc32e027a0d91dcd2))


### Bug Fixes

* **about:** the fallback example is galantamine, a real molecule ([b42c267](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/b42c267c120d12ee813d925f8ee82192045bd3f8))
* **about:** the fallback example is galantamine, a real molecule ([5fd244f](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/5fd244f0cb8379d851381b96b05f8fdd5c127cb4))
* **about:** the refusal example is cisplatin ([4f78e50](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/4f78e5016ef475d06fd221b73396b84d200e7e89))
* **about:** the refusal example is cisplatin ([e3b95fc](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/e3b95fcf9f1301b4ac8a9f01bfdb398afa506f46))
* **batch:** nameless rows stay last on a Z-A name sort ([df97919](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/df979194f64543205294dc5492531441ce41d545))
* **examples:** the fallback example is ellipticine ([9f519c0](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/9f519c066fb74b0c9eb020a3b563fb52b43dff47))
* **explain-ui:** honest labels and notes, failure as one message, real-response tests ([8ee2254](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/8ee225442fc31c7d3ad009aec5bbe3aae2f5c356))
* **explain-ui:** the failure sentence is set in sentence case, not the uppercase caption style ([6b8b2ad](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/6b8b2ad81de9677fe09479dc5da2cbcf5dd4519d))
* **explain:** a bracketed "n-O-(...)" pair names the parent's oxygen and carbon too; an element symbol never pairs across a bracket ([ea26120](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/ea26120451413a35a8693fe6b1c36f2042296ee3))
* **explain:** a bridge prefix is its own child of the root; census class PART_CONTAINS_PART ([13cc4ef](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/13cc4ef471432e68c0eb00b791ddd9bfc0e4883b))
* **explain:** a chained substituent's leading locant names the parent position ([3f6c333](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/3f6c333d66639320642a592a0afc272414a1e299))
* **explain:** a chained substituent's locant names the atom its chain hangs on ([ae117df](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/ae117dff9509e84b2f08c3c63a1495d1f7ada517))
* **explain:** a fusion component's own numbers light only what the element and rings prove ([44a3088](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/44a3088765ffd9ff7e95a87435b6f9bc9e01288a))
* **explain:** a glycosyl substituent's anomer mark lights its anomeric carbon ([781c329](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/781c32985f4e625a05845905f995fe28e3a93d69))
* **explain:** a leading locant before a chain of substituents names the atom it hangs on; the gate accepts a later chain member's atom (N-5a) ([d76608c](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/d76608cdf537362a4a943ff291e707fc567976ae))
* **explain:** a leading locant before an unbracketed chain names the parent position ([4ce5a2f](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/4ce5a2f58aeae32b04585d6013003d2dd24bcadd))
* **explain:** a locant lights only atoms it can name; lit-atom gate ([3c65925](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/3c65925a268b515b961c69cbcf64b4d143b1cfba))
* **explain:** a repeated suffix is labelled the way the name spells it ([04303f2](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/04303f25da60077267c330d1d27e36b6181aab7d))
* **explain:** a repeated suffix is labelled the way the name spells it ([e3bf50c](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/e3bf50c823568556828e4c29c2ef4ca71798fd93))
* **explain:** a soft time limit inside node building propagates instead of becoming a defect message ([3f5a8b9](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/3f5a8b9e2d8dd057c1450778fc7c11b22e2603bf))
* **explain:** a spiro skeleton OPSIN keeps no token of owns its tokens, and its second component's locants are primed ([b143d22](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/b143d220e2f7b5cb2ca131115f99c8213efb90b1))
* **explain:** an engine or drawing exception is one failure message, not a 500 ([d83e420](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/d83e420ba7b1ce1612aba0204d4920fd84d33e77))
* **explain:** every fusion component's numbers are proven or dark; a split-out number follows the token it was written for; the gate reads tokens, not wording ([9d65478](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/9d65478ddd6c05737b7e76169ca394f386ee7301))
* **explain:** final-review classes the gates were blind to (n-O- locants, functional-class words, false suffix lines, isotopic H, oxidation numbers) ([b039bad](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/b039bad5a694f9468ef5e56c13f1ca3506057c0d))
* **explain:** glossary states no false chemistry ([7b801f8](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/7b801f8e5014bef2978a4599e10581d64cf35e65))
* **explain:** oxalic keeps all four O, amino-acid esters keep alpha N/C, ring substituents keep their own locant ([517d457](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/517d457eb0a70fb3603eb2cd73e25ebb31a78a78))
* **explain:** refuse a trace when any written token cannot be placed ([5cf6467](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/5cf6467a626ede134997e6f8f9b8c53475724965))
* **explain:** refuse traces OPSIN reordered (CAS index names); stale-fixture guard ([00ed9f1](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/00ed9f15b5daf80da385f9b5f3fa219803b6be37))
* **explain:** root split gives the suffix only its own atoms ([cc1afde](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/cc1afde4333619fb72c1c59cbc0e3a2cca180422))
* **explain:** root split keeps side-chain groups and infix suffixes right ([a59451e](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/a59451e7b92bf4c7a9c162d151a01b912f8d34f4))
* **explain:** root split takes suffix atoms from the group's own carbon ([45b3555](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/45b3555b6a8bf5e4ab4657738a6c9a466262202f))
* **explain:** spiro primes restart at each spiro system in the hydro gate ([244a4a7](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/244a4a73673b967419f4127551736b692ca53fc2))
* **explain:** spiro primes stop at the bracket; census sees a wrong atom of the right part; position numbers before ring chains ([c7b7356](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/c7b735619a124a9bfbecf6794393b136c0f21c9e))
* **explain:** the hydro gate reads OPSIN's primed numbering of later spiro components ([2a070bf](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/2a070bf1e55852e91c03bae8aa6044258814d991))
* **explain:** trace the candidate parse OPSIN itself returns (the first built without a warning) ([2abbf58](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/2abbf58bfb0209c0c56bc84dc38b4cc7e15bc07c))
* the hero light no longer flashes black or overworks tablet GPUs ([2650d77](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/2650d77dab3af45684c5c5c7cbd0e0f4f95fdbed))


### Refactoring

* **explain-ui:** one hover-handler helper, one id map, one GET helper; comments state why, not history ([e05c21b](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/e05c21bae9e9fa497da8d3714c9baa4559ff0803))
* **explain:** drop dead parameters and an unused glossary helper ([186e287](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/186e287c05f5d5c52b786200060c8ae97cc6c431))
* **explain:** key glossary lines on OPSIN parse-tree kinds ([c34afe5](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/c34afe5875b87fd2a90e5b3f448b147b081fc5fd))
* **explain:** one helper each for the hydro modifier, the oxy pair line, the generic token line and the guarded drawing; explain_molecule no longer draws OPSIN's molecule ([8bbe19b](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/8bbe19b74619738090f70db909f7a09002f40b41))
* **explain:** one home for bracket_end, locant-shape regexes and token walkers; census imports at module top ([42c27a9](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/42c27a9a987da431df1b335d9a25b60b5e98cc23))
* **explain:** parse the traced SMILES once, build the part and ring tables once, skip the second parse when OPSIN's two SMILES agree ([14c3e44](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/14c3e4452dc18ebaec744cfadc5ac88a65292e18))
* **explain:** split root atoms from a Trace ([dc9518f](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/dc9518f4d2512e8cc0dd6995e9b77494a35211db))
* **explain:** the test and census gate lives in app/explain_gate.py, apart from the builder it checks ([5377768](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/5377768b49fc61d2e56d3e86d5559bb1c4d62bc1))
* one failure path for the hero light ([8638579](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/86385799c4cd240d3872fb7dbd4795adf65acbd0))
* one failure path for the hero light ([f1f0add](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/f1f0adda43699d0ee6a68c78079251b431d0f856))


### Documentation

* cite Orthonym-Web through its Zenodo DOI ([9c0c8fa](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/9c0c8fa608ea1a3cd414892cf1629c726dc42cba))
* **explain:** CLAUDE.md corpus numbers follow the CURATED additions (670 names, CLEAN 668) ([f54fff3](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/f54fff335e3d324d15e406a83d8147e4fcfacbc9))
* **explain:** CLAUDE.md states the measured corpus and census numbers (665 / 663, ChEMBL 9998, 2026-10-01) ([2dc6e83](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/2dc6e8388368c6afd748c2af6aa700fb23ac329d))
* **explain:** correct the stereo rule, add the anomer rule and trace details ([7e2bee1](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/7e2bee1f950efe42f7afdabf269e21f9da1cda2c))

## [0.3.0](https://github.com/Steinbeck-Lab/Orthonym-Web/compare/v0.2.0...v0.3.0) (2026-09-29)


### Features

* an issue tab with a buddy, Kekunyo, who also roams the About page ([a6a2a74](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/a6a2a7479f0daebdebf3273140456653291df8ae))
* Home assembles itself on a fresh arrival, led by a reading light ([1c8f7e9](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/1c8f7e915a80dbe85bad1e25659c2c508cec9c7d))
* report SMILES on GitHub for results Orthonym could not name ([0c7e8b7](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/0c7e8b7182b49f27eb46e2d80231fcf046cfd216))
* report SMILES on GitHub, and four old bug fixes ([00ae11c](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/00ae11c91166a58f9d7c8016f3897336c0d1cec6))
* the tier lamp says on hover how its name was made ([5bd854b](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/5bd854b5ed2cda92e55b04968c4f7641afefad9e))


### Bug Fixes

* a mismatched round trip demotes a verified status; lamps explain on hover ([3ef4518](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/3ef451878d429d7b5953d37727abdedf2659c08c))
* a round trip that does not match demotes a verified status ([6def5f2](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/6def5f24e7d6826312a82b8a7bd70dbae309ac60))
* **batch:** a timeout keeps the parse error of an unreadable row ([5f4e1ca](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/5f4e1ca61c1478c987d68a2b95c969788fa7e3f8))
* **explain:** an unnameable molecule's placeholder is not shown as a name ([d9e4b38](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/d9e4b38e5016f0515b42a35ad32e605f7b2f7a2b))
* Home and /explain say what a failed request means ([717311a](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/717311a4a377a734e980295bdbd0eb8fb61d57e1))
* tier labels match what the engine actually verified ([e034f87](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/e034f879dab747fc7dc91563cd93b01892c7e962))
* tier labels match what the engine actually verified ([bd7402d](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/bd7402dcf66582bc1fae4f769af7ebcee3ad7223))


### Refactoring

* define each shared rule once ([0cae84b](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/0cae84b16cc2e0724eeb95c256e8dce053a95df7))
* name the withheld abstain code withheld_unchecked ([3f082fe](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/3f082febc33c22984e1635000e67da4dbfcc01c2))
* one demoted-label decision; TierLamp takes the row ([97ecfaf](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/97ecfafa7ea00f061f485db661d84c6da06902b5))
* one test for the unchecked case, one branch for fallback ([dedeb2a](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/dedeb2a4da7771a59fc9fd421c6e1db69827db4d))
* tidy the Kekunyo code after review ([63a27f0](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/63a27f0686c3948e50b3d41f17e75d09a04aafcd))


### Documentation

* a reading light in the README header; partner logos in its footer ([2b867ac](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/2b867acc6d14292ce452f1d1818b321311e66097))
* a two-line collaboration line at phone width ([6b26a74](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/6b26a743587b9e0858c2cd8deb0c1f96b105d226))
* draw the README credit's cross in the site's crimson ([197afb0](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/197afb04d9967d390d1759122e3d4e1a7dbddbfb))
* draw the Steinbeck logo 74/62 as tall, as the About page does ([e046942](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/e0469422e0f0e1e9cf8a201c45ee7df8d6721f84))
* footer credit, then the partners, then the collaboration line ([8bea168](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/8bea1682bfface367247a551ad3737828aa46888))
* give the README's page table real column headers ([fe48a54](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/fe48a546c4d3bdd78eceba18ee14f731c1bf73ad))
* partner logos fit one row at phone width ([e422a2d](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/e422a2d527140bad9c1b403c40a66a6b8a470324))
* README finish-review fixes ([fdefa2a](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/fdefa2a77416aa4d6c9d84b68415ce72c7300309))
* README header reading light; partner logos in the footer ([b5db27f](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/b5db27faf462bbe059330f08ea3422969e2a977b))
* README says Orthonym Web; footer credit, partners, collaboration line ([5ea9d22](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/5ea9d22238f146954e398cb07e57cbc9452e8766))
* redesign the README ([45ea874](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/45ea8741ad3abd36c94e98d0198b04de1a97e05b))
* the best-effort tier says how the name was built ([785a8de](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/785a8deb2e340706ab621f860bcaeb932850e97f))
* the README header says Orthonym Web ([e6fdd2a](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/e6fdd2aa04a5e660d380a762211024c8f2214d2e))
* the README leads with a graphical abstract and a live link ([0a68a79](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/0a68a79ee3d9cd4757cff065026028fa8f0fde99))
* the README's painted cross repaints itself every 8 seconds ([7098624](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/7098624ebec7aac1a5f9940e3b5571ec48e2c30f))

## [0.2.0](https://github.com/Steinbeck-Lab/Orthonym-Web/compare/v0.1.0...v0.2.0) (2026-09-24)


### ⚠ BREAKING CHANGES

* refresh vendored Orthonym and adopt its new tier vocabulary

### Features

* /api/iupac-to-smiles returns canonical SMILES, InChI, InChIKey and a molblock ([2d7f384](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/2d7f3848bda0844aebcf2d75ee29f052692932b4))
* /explain becomes one page, one voice, on a recomposed ground ([cf67d97](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/cf67d97907fdfe457c879aab675d0cb4371cbc09))
* /from-name puts the structure beside its identifiers, not above them ([30e6715](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/30e6715f2f16e2d51a0a5466625b04c116b9b89b))
* /from-name renders two or more names as a table with CSV and SDF ([828bc76](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/828bc76f9196ea0794fa7c5e882ad5d898e1dab9))
* /from-name shows the full identifier set and stops wasting the page ([412ed36](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/412ed3682ad1da97418ebc6f21f38576ba3723d9))
* a flat pint mark, and a favicon drawn from it ([b239a27](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/b239a27e9e8dbaee4e3bcd7dd9563a5d596aad09))
* a floating label on /from-name, a genuinely bigger box, less duplicate copy ([e7811b0](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/e7811b0ca689b0c43768e206a4aaa2a9f317fd1f))
* About becomes a needlework pattern chart, worked live ([b9a3b97](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/b9a3b976d7ef3b090259fedc85fe1c1e520dcda3))
* add /api/explain-name endpoint, retire opsin_substituents ([6e05ac1](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/6e05ac1f667ab1e57a279ad27dbe50c366ea1c02))
* add deterministic glossary for name parts ([8275ae6](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/8275ae6915f538a9c51f690827125218c89b1e09))
* allow a deployment to gate the site behind Basic Auth ([88a7db8](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/88a7db87d017fd52b185184bc6f916f38cba5dc8))
* an info notch on /from-name explaining how OPSIN reads a name ([a84e4be](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/a84e4be15111d7e14ab1fd6dae77bd5e6fc49397))
* an OPSIN-verify switch, default on, beside best-effort ([22c8e68](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/22c8e689bb12dfac580bb51f0f33b5360911eb0a))
* an unverified name says which switch produced it ([6f0c987](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/6f0c9873adbf57b31057e39fc4e00a55aa42357e))
* batch jobs with chunked tasks, progress and CSV download ([7da5a1a](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/7da5a1a5b0027fdce662a92d8682107b280896ad))
* batch upload on Home, so the job layer has a user ([9ae980d](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/9ae980d51beafb5605587fe48000f91a958c8812))
* bounded pooled conversion for many IUPAC names ([e70c7db](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/e70c7db282fa5fe676d01828daaa7cb05a00aa37))
* build CSV and SDF downloads in the browser from rows in hand ([01fd652](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/01fd65201fd330840f0ad0ea2335c256e9de7a7b))
* CDK draws every structure, with CIP stereo labels ([c51f31e](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/c51f31e62f85564bd7122b61517938bf40dd86e6))
* Celery app with a pinned prefork pool and the JVM guards ([8f45a47](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/8f45a4797e991d25af7d330e5ba6e8ab101da0f4))
* Celery app with two queues and the JVM fork guards ([9b475af](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/9b475af03efa2db03f4a37f9870fafe7f4ad0828))
* character spans into the IUPAC name for each part ([4418313](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/44183131cb53c86b5962319eff9ad70e443c00a1))
* chemical names and formulas are typeset the way IUPAC prints them ([50d2b06](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/50d2b068349a779ee3d06d907e49e74e8d5aa902))
* collect OPSIN name parts after buildFragment with locants ([da3bae8](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/da3bae8dd1c86264d0c28606f8f869e4e74c739b))
* derive name spans by assigning raw tokens to decomposition parts ([2dfc713](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/2dfc7131116a730c3a401e23afd3ab3344d5d897))
* emit modifier segments and cover split_root degrade paths ([d428185](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/d4281858be17c08520e045914bb312aeadb73d7a))
* emit per-atom pixel coordinates for highlighting ([fc1f453](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/fc1f453a7c42158a59a046e51911f35db37b0431))
* env-configurable settings with deployment profiles ([4a0f29f](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/4a0f29f97c2dbb00f4847d0e81dde21ee96996b6))
* every button crimson, glossy, and carrying a real icon ([a0e0c1a](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/a0e0c1a1d08e35a2095223c7513c8398295551f2))
* explain each name token as its own hoverable part ([9e2bd9e](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/9e2bd9e0a4a452438f6c8d8adf2df8e2f7284c2f))
* fold a bis/tris-cloned block of parts back to one written slot ([3f9e224](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/3f9e224ea1a2161f424ddf3a540c3c35b5237fd9))
* four pages open on bare ground, like Home ([3fc4c4e](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/3fc4c4ecb3c83d38d4cd05c6fa1684d6404ab325))
* group explain segments by written occurrence, not by shared text ([9cf0af6](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/9cf0af68a3125349a8823d926db365bbb66c2694))
* Health Check becomes a status board on About, not a route of its own ([12b065c](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/12b065c0f6f78b01ce33d0b0f1a29264a9fde87e))
* Home gains a Draw tab ([c06c24e](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/c06c24eee1b100751a6b277ac429c453a217ce24))
* Home overhaul — clay notch tabs, normal-scroll shell, richer results ([3830235](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/3830235d9c19f89b2f225aa5e96b451694f2a5ef))
* hover the IUPAC name to explore the structure ([31ae631](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/31ae631eaccbf8b5b90ed0b794b59bbb963f8139))
* hover the name on the teaching page to see which atoms it describes ([4f30d69](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/4f30d690419daea7d1127fb79332bae3d1402184))
* job cancellation, and an owner token for cancel and delete ([1b07ddf](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/1b07ddf196900e2e291933eeeb9fb96c3787e8ec))
* let a caller refuse OPSIN-unverified names ([aa50a56](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/aa50a56da8b0e39893edb4b3f04d4cd706fd366c))
* link the learning page from the navigation ([5ef1ded](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/5ef1ded3c7ddee30097b3768030833f7d993ee11))
* log why a name fell back, and pin atom-point distinctness ([7cf5858](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/7cf5858643b02f23285e4874b869caaa2cefd42b))
* make a batch's misses visible, and give every tier a lamp ([d55061e](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/d55061efbc60aad61082c0a98a9c0281e83c38c3))
* make ExplainSegment recursive with ownership flag ([d44fb03](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/d44fb0360248da7f84abb5387e601327f960ab66))
* map OPSIN atom ids to RDKit heavy-atom indices ([3eb2b93](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/3eb2b93fe9af43c454badd28d201c7aebee079ac))
* mark referential name parts as notation on /explain ([c2da04d](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/c2da04d401dd9973412f25cbd3044c9922063a80))
* mark referential name parts as notation on /explain ([3e6502e](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/3e6502ec5a3b69d858ddba0c38fb8412efaa2fac))
* merge /structure and /teach into /explain, and strip the footer ([7486bcb](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/7486bcb307ae9d1ab2cf530ba61cac8f64e8fa17))
* move every OPSIN call onto workers, add per-IP caps ([a1dae9a](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/a1dae9a0b627dc4cf0cafcc68a37bcbd6ec3774b))
* name cache keyed on the Orthonym version ([e910816](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/e910816b9ad7f456e4bcaaed9cd1431ff4966c3d))
* parse SDF, molfile, CSV and SMILES-list input ([46d234e](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/46d234e11eb68168c699aa8ca650d3d67669c444))
* populate name_range from proven character spans ([37538f0](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/37538f0d1819895e15c6eb6e2344f469aaae53cd))
* rebuild explain around OPSIN part tree, drop SMARTS rules ([b29d98a](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/b29d98ae99110599c3a673217f0b272d942697ec))
* redesign /about as the round trip, drawn ([15beb73](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/15beb7305d47f90de86013291ae33f524e35670a))
* Redis and worker services, and a build that proves OPSIN works ([1a03abc](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/1a03abca07b6645a6c47726408a2ec3edf67ce32))
* Redis store owning every key and TTL ([84143b4](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/84143b461aa8f3f1ea3accb1cb5bbbcb3fc6ba3e))
* refresh vendored Orthonym and adopt its new tier vocabulary ([e08d721](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/e08d7211c74b62cef17bcb2b1d12416b0b73ed01))
* sleeker /from-name — denser rows, smaller buttons, pastel downloads ([4df9800](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/4df9800713896ef83f2ffdaa50a8903f402aa391))
* split OPSIN root part into parent and suffix by locant ([9265401](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/92654018587801a5cbb124d6f91ed0f6dc84be70))
* teaching route with a drawing area that names what you draw ([87d1a60](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/87d1a60dcec539abe0098cefa6edac33489210d5))
* TechX card-bento redesign wearing ChemAudit chrome ([ae10123](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/ae10123e5d5a20e8e3ca3c55d8685060dc2ae5ce))
* the /from-name table carries InChI and canonical SMILES too ([55ce771](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/55ce771438dd943b54b864c3eabe5ab8f3c5d274))
* the /from-name table fills its card instead of centring in it ([11c228c](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/11c228cef53d060b2a06c522bb54f70d7d3fb63c))
* the confidence key becomes an INFO notch on the input card ([8f0a5b9](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/8f0a5b97cc18de2fb06d9aac18daa1a5df98f869))
* the INFO tab flips and re-attaches to the panel it opened ([6ee1112](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/6ee1112f2bb9a9a8342643f81e9a5054b9a14d3a))
* the Orthonym mark stands in for a letter of the hero wordmark ([04e4823](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/04e4823108f4946c4fc2f679f96a960c4a837d34))
* the table's second line is InChI alone, aligned under SMILES ([ddc67dc](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/ddc67dc1615e3038f7420b496415ad1db729f1aa))
* the toggle is a moulded rocker, at half the size ([243086c](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/243086c80e0de8393a6193610f77fd98b60093e4))
* the toggle wears the buttons' glass ([283cb80](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/283cb806727e785a3017cbc3a700967b3d0202d2))
* the upload target shows what it actually read ([05e98aa](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/05e98aa04f191cc2af32d1db35865f5e82b63d39))
* the wordmark gets a real flare, raking light along its outlines ([b7ba61a](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/b7ba61a56505fb507e68cdbe35f99008fb095a00))
* tighter /from-name table — one frame, one-line keys, smaller thumbnails ([fbc5edd](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/fbc5edd347d7e3a3fa1591746db2f21df7a7cfaa))
* two-input explain page with hoverable segment tree ([3df16d6](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/3df16d6b691e1a28cc8467fd5e55ca20ecc7f0b6))
* yellow glow highlight drawn from atom coordinates ([1e80db4](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/1e80db478c9f3f9285017498026b102d0375fda1))


### Bug Fixes

* /explain works for 313 of 544 names, up from 170 ([132932b](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/132932babf58019e4d97af8a79987daa8db0ddd8))
* a broken /explain shim took the whole site offline ([92f30ee](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/92f30ee99b96829961578fc00646ed7a122ec7db))
* a job whose meta was evicted mid-flight reported as never having existed ([7adef8e](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/7adef8ec86ac8f464db49b0a7891786b2be2a6d6))
* a rate-limit counter could lose its TTL and lock an IP out permanently ([f5051ad](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/f5051ad2bde4b141fc10a882cccd98cd0af0cdc0))
* a Redis blip at worker boot made a child invisible for its whole life ([0aadeec](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/0aadeec132985b5028b95e52e4d95fa231efcf50))
* a verified tier could ship without the round-trip that earns it ([18a9645](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/18a9645b88d218bae9aa7db5dce7604b08edaf24))
* accept OPSIN's case-folded D/L tokens instead of rejecting them ([a1502d3](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/a1502d3f6a935540f973872bad4d27db43bce38e))
* add a daemon heartbeat so worker OPSIN status never ages out (C1) ([b4c05a0](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/b4c05a08ea4c4e96ca3e25cf5acc193109cd614f))
* an uploaded file could not ask for verified-only names ([8adbd2d](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/8adbd2db1755cf42265b9299edae74157a178eaf))
* assemble_rows must report a missing chunk, not swallow it ([514f9a9](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/514f9a9d288425a7a84e056501614cff926f2720))
* atomic per-IP job admission, correct client IP, self-healing release ([094957d](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/094957d4d3fbe2512fa7577bb12c1973ce79bb56))
* check the JVM before charging job quota, and stop masking renames ([b10d717](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/b10d717d638dfc66c14928c67e903321ba2997be))
* clear the pinned name part on each new naming; add aria-live to the name; correct nav count ([124feca](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/124feca64179d0e4f661e461c629348ae55453ff))
* closing a job pushed its expiry past the expires_at already reported ([a3b5a85](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/a3b5a856ef07122afae94ae26e93a1a91cadfd2e))
* config hygiene, a measured depict budget, and a cross-path cache test ([eeace0d](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/eeace0ddf51c815619c7d970d214732f74815506))
* correct Explain's confirmation rule and stale user-facing copy ([1a427a2](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/1a427a2541692359b41d87b1a2acb4955533995b))
* count a part's decorating locants from the previous part's end ([2fc5425](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/2fc54255c5e071d0433e7fe2daf86b4a891c84b0))
* count SDF terminators by line, not substring, in the molecule counter ([235165b](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/235165b0f8a22ce7e92623be69aec6180cd8c741))
* derive top-level name spans from token runs, not text search ([ae74031](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/ae740317a696ce608eef01783455f216cda006ce))
* draw the best-effort rule as real dots ([0f3100d](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/0f3100d8223ea239cced25d64941ee85b49bbc46))
* drop the raw tier badge from tiles and disclose a missing round-trip proof ([ab20f31](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/ab20f319d1c02fe3d7f882e2d3e04cdaaaf3fae3))
* fence an unlocanted hydro run's multiplier prefix out of claims ([ca278c5](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/ca278c5d7fcf6a0b98f598ab67ad28e2b897795e))
* give every locant child its own span, including caffeine's 1H ([df85b5c](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/df85b5c7d8375152eadc1fd02ca110c97b75a1f1))
* guard onProgress separately so convertNames never rejects ([f63b2ad](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/f63b2ad033feac29f0505c9acb545bd8ffb17e58))
* guard partial substructure matches, cover the symmetry path ([2f87085](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/2f87085c9391083b4af0731ef3472ab3d7648022))
* guard the OPSIN heartbeat's interval floor and thread start (C1 residuals) ([67943ab](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/67943abd55bb4f6422f4686aebbe181824069d6c))
* guard translate_job_inline's redelivery with begin_chunk too (I1) ([9c175d2](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/9c175d210cff7582880f6aaf50d31670cf0eb609))
* handle apply_async timeouts, canonicalize job input, restore old contracts ([5b20608](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/5b2060899505faaf49bdf5c2edc2984150d4f298))
* Home invited 50 molecules the app could not answer ([82c0bfd](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/82c0bfd6c28c717262c7a49687363bc2d8a955e5))
* kill the web-process JVM, prove the 503 fail-closed rule ([be92bd4](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/be92bd4e2b7ad43fb839c93205de4d8a6b2e899e))
* make the name cache invalidate itself on a vendor refresh ([ae9363c](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/ae9363cd6d5113b207c79289476bbfd0242549a7))
* make the parent JVM guard's confirmation actually observable ([45b94c2](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/45b94c23dc74930e9dc905f4cb239394bed6c577))
* name the as-typed SMILES; refresh vendored Orthonym to 404b69e ([67dcb0b](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/67dcb0b45b7450ffe30dbe13c39761a02f71c6ba))
* never ship a partially spanned name, and test the contract ([7fd73d3](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/7fd73d3c643ea0982b913057adeea832be1aa487))
* nothing may escape a cell, and a reload clears the page ([65dcec8](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/65dcec8713866aeba239fc67e3c126283755d5e3))
* one paint source for the tabs and their bleed, and a real lift ([ac202a8](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/ac202a8dbce97c479e1c139bb370f659bd202f96))
* one raising molecule lost an entire fast-path request ([6d1f938](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/6d1f938ca4434beda870ddb1c44015ceeca26171))
* probe the JVM-fork property in a fresh subprocess, not the pytest process ([b1a323e](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/b1a323e508938af14c5b884211ddd392c084c806))
* raise nginx upload cap to cover the largest deployment profile ([c3de228](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/c3de228aca38653ae5d355327de9ee2888a82e82))
* rate-limit job polling, unify depict's error shape, fix flaky atomicity test ([fa3cd62](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/fa3cd62fe3f4778159a42ff4a109f02bbd365095))
* rate-limit POST /api/jobs per-minute before the JVM liveness check ([c56cb31](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/c56cb31c53edc1e424b00d0563960fd56b765430))
* re-tag meta key TTL on every progress write, NX-guarded ([6d4268b](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/6d4268b78db7de9436e338d722731a87f5e94dbc))
* recognise OPSIN's two-token tetra-and-higher multipliers ([812db97](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/812db9777fdac74ffca3398da061eda5643a0dfc))
* refuse to cache a verified tier with no round-trip proof (C3) ([e7dd663](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/e7dd6630b54aa2986306a6067fe8b8479df9583a))
* require contiguous token runs and bound growth by the neighbouring run ([809d797](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/809d7975c5f5f567efe822649025d801824e495c))
* results.csv shared the naming budget while costing 10,000x more ([8066c7d](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/8066c7d2e6422c0054acbf95bd9bb97bdacbd9d9))
* run-tests.sh exited 0 on a failing suite under -q ([dd67a0f](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/dd67a0fbfa419004c52411e50057ac91fca0f01f))
* run-tests.sh finds .venv when .venv-mac is not there ([9690cd4](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/9690cd4962dfcbbdf265d93459dea07882503a14))
* run-tests.sh reported a false hang under -q ([9820c3c](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/9820c3c498391af0d8b8346b9fba9b22d0a37e8a))
* scope modifier locants and stop fabricating atom labels ([0b42a28](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/0b42a2849c72e0f94ddcc8944f498f138b8a201b))
* SDF molecule_count undercounts an unterminated final record ([abb4a3c](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/abb4a3c0c0465487daa93004bcbbd06631a433e8))
* set glow fill as a style property, not a presentation attribute ([141ee6f](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/141ee6fe3b67bc00abb830e3520a33f48d0adcab))
* show a partial result's reason, and let the keyboard pin a name piece ([b509351](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/b509351856d44ebcb39f87ab9a838f04f4f48558))
* split the hourly job cap out atomically, fix client-IP bucketing bugs ([e111dff](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/e111dff09e51a15262611731ff6be56fa4315f53))
* stop a coarse locant token from shadowing its own precise children ([5eb9da8](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/5eb9da8ffd946cf80041504c7725a9cd7fe16898))
* stop Home's tier colouring reaching another route, and de-duplicate a rule ([48ef571](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/48ef571dd181f1b88de4c1b3689ada0893ccf538))
* stop job_status/results.csv claiming done over evicted rows (C4) ([690f606](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/690f60628532ce12deabdd1d5419cfc4448fe7ec))
* stop parse-preview's full RDKit parse, move job-cap checks earlier ([43d168a](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/43d168aa5b4cba95e911f6b45f50d43994207eb3))
* surface a queued batch job instead of an empty result grid ([5102f40](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/5102f40e3bd17f881d1ab8358558fbd892ee6a7a))
* surface ATOM_GAP in the census table and stop double-walking segments ([f907e31](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/f907e318e40f616a779dd14b497eed6628581a1f))
* task 6 fix round 1 -- drop unused run_chunk bind/self, add 3 tests ([31ca2c5](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/31ca2c53443cbbbe0bddc531fe09dce5e1101713))
* task 6 fix round 2 -- one honest close, real timeout handling ([0861ef0](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/0861ef079374350f4552a5743a132c3b77657023))
* task 6 fix round 3 -- terminal state on task failure, CSV safety, depict bounds ([39379a8](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/39379a8cc8cb053315d617552b18d5dbf362f3c9))
* the bloom is an ellipse over the tabs, not a band across the card ([9636641](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/9636641322107aa3e5f10b21736f3ba43592b7b2))
* the curves are back, and the strip fades as one piece ([b39fa59](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/b39fa59995ba87235163d24e295c7b973220bd7a))
* the default job path had no errback, stranding failed jobs for 24 hours ([6be1594](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/6be159444db7e9eeb5a76a7503584edf10361cda))
* the final review's findings, plus an emptied card foot and a smaller box ([61aa77f](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/61aa77fb43dbeed9055c3360879cddc28f0bd985))
* the health page reads the payload, not just the reply ([4fdefae](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/4fdefaea47c49dad845bcc142689c31da187f652))
* the heartbeat replayed a boot verdict, so a dead JVM still read healthy ([9fffd37](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/9fffd37da102a32d8f8b664461ca474bb7f02060))
* the INFO notch uses the header's fillets, not a flipped copy ([0790d13](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/0790d13edbdcf4f10b9e9bb042459a15d6554667))
* the info panel welds to the tab instead of floating below it ([acc3513](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/acc3513399c83b11f0471c52f5367410a3b68401))
* the round-trip proof was crying wolf on zwitterions ([4e7b164](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/4e7b164b600e3176aa1c51a2f3aee5bb652e6bd6))
* the tab strip is one ramp, sliced, so no junction shows ([d65f45c](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/d65f45c9f21cbe21f29fc510c8a399f183be9aaf))
* the tabs meet the card with no line, no rim and no crop ([80a8493](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/80a8493e409118a57b8148a937fd7279eb23adc3))
* three defects this session's own changes introduced ([d9d5572](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/d9d5572a91a6fad2241f3be79de0659187cf51aa))
* try every OPSIN candidate parse instead of only the first ([b79bfbd](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/b79bfbdba7e3c508124c216c105ac044a6d86adc))
* two labels implied OPSIN verification does not always run ([0f13768](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/0f13768673fe5c54fc1a48c410ece3ba6337936a))
* two redelivery guards stop a chunk un-completing a finished job (I1) ([e158c36](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/e158c36e3caec7922a02cb38c2644ad6599b2b3b))
* vendor-orthonym.sh works from a plain Orthonym clone ([2610df6](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/2610df686fc1ea6fe61c1e13359c21a99f9e32ac))
* widen the C1 heartbeat test's sleep margin past the TTL truncation error ([89db8e0](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/89db8e0da7f046baa384d84f6c8017ee15587c1b))
* wire admission/JVM-guard fixes into endpoints, bound depict cost ([f928ff5](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/f928ff5b9d81f6499c4100c70b753b5cf08d1268))
* withhold spans when a grouped substituent's span cannot name its atoms ([6b2dd14](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/6b2dd14b839315c4b11bcc5852b6c774c459f667))


### Performance

* parse uploads in a worker instead of the web process ([dcbb0eb](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/dcbb0ebcc1887c1b5ba0d33e417e852595fbd45a))
* stop caching a structure picture nobody reads back ([01dc1ed](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/01dc1ed57067c1ba5a54a0f9498effd32b84d2a9))


### Refactoring

* collapse six duplications the session's diff introduced ([b89be36](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/b89be36258b45d6ac7b3f73e938a9ec4fa917336))
* delete dead code ([32b9064](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/32b906439cced2f07a2e7abb01e8362676286246))
* delete the dead compute_spans anchor scan and its module ([7ee45d2](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/7ee45d2c9be4439afe73be04a3c5c157453f5c2d))
* extract duplicated SVG-highlight and Ketcher-handshake code ([5083eab](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/5083eab390dc54b09fc85de491e3deb0afb178d6))
* extract splitLines so names and SMILES share one splitter ([8e76082](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/8e760821ec868bae26e14ed858311c61c6299947))
* extract the atom-highlight effects Explain and Teach both carried ([b93a594](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/b93a5947053606fe36fc7bfce544423dc9d062dc))
* one row shape in convertNames instead of two spellings of it ([58ae8d1](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/58ae8d1b1faeeb6b52b5e453a0111212e84ac363))
* one statement of each fact, and the store keeps its own rule ([33b7954](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/33b7954cd8b313f0a82da35841e8640c6f7bbd2a))
* promote the shared input and result CSS out of Home.css ([eefe35a](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/eefe35a3933628e94ee3af7255d51a92c2a66b83))
* quality pass from a four-angle review — reuse, simplicity, waste, altitude ([f77a340](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/f77a34047548b9246e205c0be69e23897c18fd92))
* sweep old job keys by rule, not by list ([f00d726](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/f00d7269c44963241682c4231a7841340b935863))
* tell the app and its engine apart, and retire the needlework ([ee645f7](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/ee645f7dd65826acaaa54fd8fd430303d4899daa))


### Documentation

* add CLAUDE.md, screenshot tooling, and ignore generated output ([8959b1e](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/8959b1ea7a1f689143faad9095da147a67af41ec))
* CLAUDE.md's shared-component claim is true now ([a125c6f](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/a125c6f9447443f8faecae9a84d5406c073042b7))
* close the backend plan, and correct four claims that had gone false ([d6bea09](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/d6bea09c29b918093eb91dba0b019972b1d722ba))
* correct 14 verified stale claims in CLAUDE.md, DESIGN.md and PRODUCT.md ([56d2e47](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/56d2e478e7d4473c01edbca4f76d9f25994bac31))
* correct a count the previous commit made stale ([373809e](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/373809eb8141cdfbd83e3f428e74fbad7b71f716))
* correct four comments that misdescribe the code they sit on ([706c311](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/706c311fcf4a017890847e5d6a9b5fbbfd17dca1))
* correct six places where the design spec describes something else ([e5ee8c8](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/e5ee8c8b7d3ab45a48284649ab5bd8d19b96d8fe))
* correct stale comments that describe code we no longer have ([a3de68d](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/a3de68d2704ab92f1048facec8947fd9add04770))
* fix CLAUDE.md's stale claim about the SVG-highlight duplication ([cc2fead](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/cc2feadff5c16e15b3d8236df9dcfaf3e4646d08))
* fix step 1 of the runbook -- /opt is root-owned ([bb3533c](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/bb3533cd6a0b72698da5d25f0f48f47aca2b3631))
* make the README a front page, move the manual to INSTALL.md ([3916c89](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/3916c89db47374854edece6314773528312013f2))
* move the framed-input rationale to sit with the rule it describes ([70746db](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/70746dbb3411c7f7b3bb5b2427fb6708efdb7ab1))
* note the MODIFIER_KEY overlap-proof backstop at the claims fence ([583bada](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/583badae049c0558ad33b78f94a155c0fa0d9c37))
* point .env.example at nginx as the binding upload limit ([ff7a62f](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/ff7a62f8b803ab286cf19384a8c5736fdd6d820f))
* record the flare's five load-bearing choices ([626bb95](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/626bb95f4b5f17c2936efccff2fa56aa0cc51b27))
* refresh README/CLAUDE/PRODUCT for the Celery/Redis architecture ([c779beb](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/c779beb94d7e1c6d035b8e1712ea930b8238f48f))
* six route-count claims the Health Check move made false ([072d43b](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/072d43be61d16bcdbff0119f542f7c3d4ef68aa8))
* split the firewall step by front-door route ([91aa949](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/91aa9494ca54542ec41cebe2cca20a000c053927))
* the button system, and the contrast rule that governs it ([8bf6594](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/8bf65943adb7e62d863be08f88a416d973c0461e))
* the Orthonym snapshot is already current, and the local clone is a trap ([0721b2d](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/0721b2d71a40ff71813f995261db093b9e142d61))
* the README shows the flat pint wordmark and the current pages ([cd56c0e](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/cd56c0e399172ec4d5290286b894bf98bbe23f07))
* the runbook assumed a VM with a public address ([e99a310](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/e99a310baf2a12a01cf404cc255a1582db46eaaf))
* update an older install in place ([2501f74](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/2501f74d6dec5bf6e611e9094742bc940023cffd))
* use the real Orthonym logo in the README header ([9105db8](https://github.com/Steinbeck-Lab/Orthonym-Web/commit/9105db8567418eb27739e06982b7ac5c83a54197))

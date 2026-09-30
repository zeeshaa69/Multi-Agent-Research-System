# Fixture corpus

Everything in `corpus/` is **synthetic test data written for this repository**.
The "Harborview Tidal Pilot" does not exist; the documents, numbers and names are
invented so the offline workflow can be exercised end to end without internet access
or a language model. Nothing here is a real source or a real research finding.

The corpus is deliberately built to trigger each verification outcome:

| Situation | Where |
| --- | --- |
| Corroborated claim (capacity 12 MW) | `harborview-overview`, `harborview-news` |
| Numeric conflict (capacity 12 vs 15 MW; cost 84 vs 96 million) | `harborview-news` vs `harborview-audit` |
| Negation conflict (dredging required / not required) | `harborview-news` vs `harborview-audit` |
| Hedged, therefore uncertain (`may`, `suggest`) | `harborview-overview`, `harborview-environment` |
| Distractor documents that should not be retrieved | `lantern-library`, `orchard-notes` |

Each file has `url` (a `fixture://` URL), `title` and `text`. Add your own files in the
same shape to extend the corpus, or point `RESEARCHER_FIXTURES_DIR` at another directory.

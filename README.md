# Apple Therapeutics

Apple Therapeutics is a fictional customer I invented to show how I would run an engagement as a Forward Deployed Engineer.

They cut apple slices, and the cutting step fails their reproducibility gate: slice-width standard deviation has to be at or below 0.5 mm, and the pooled within-run figure is 0.664 mm. They cannot transfer the process to a second facility until that closes. This repo is the investigation — rule out the cheap variables, work out what the most consistent technician does differently, and write it into an SOP someone else can follow.

## What is real and what is not

I recorded the six videos myself, playing all four technicians. I gave "Molly" a deliberate technique and varied everyone else. Then I generated the QA and LIMS data with Molly's consistency written in as the ground truth.

So this is not a discovery that Molly is the better technician. That was the premise. It is a test of whether a video pipeline can find a difference I planted on purpose, and describe it precisely enough to write into a procedure.

| Real | Synthetic |
| --- | --- |
| The six videos, and everything derived from them: transcripts, step breakdowns, both SOPs, the Word document | `runs.csv`, `slices.csv`, `lims_batches.csv`, `run_batch_map.csv` — the QA and LIMS numbers the investigation starts from |

## What it found

Apple variety does not explain the variation: the two varieties differ by 0.016 mm on a 4 mm target. The technician does.

Molly runs a quality control loop on herself that the others do not. She turns the piece so a fresh face meets the blade, starts each section from the bigger end so the cut stays visible, checks slices against both sides of the knife, and removes any that came out too thin. The baseline procedure judges the slices too — and then keeps cutting the same way.

Most of that never appears in her narration. She turns the piece between cuts and pulls the first two halves apart to look at the cut face without mentioning either one across three runs. Those are ghost steps, and they only show up because the pipeline reads the frames and the audio separately, then reconciles them.

## Running it

```bash
pip install -r requirements.txt
python run_all.py --analysis
```

Every stage's output is committed, so this reproduces every figure and finding with no API key and no video files. `run_all.py` reports what it is skipping and why.

To re-run the pipeline itself you need the source videos, `ffmpeg`, and `ANTHROPIC_API_KEY` in a `.env` file at the repo root. The four extraction stages cost roughly $3.20 in total.

```bash
python run_all.py --dry-run   # show the plan, run nothing
python run_all.py             # run whatever this machine can
```

## What is in here

```
datasets/                    the tables everything reads
                             runs.csv (100), slices.csv (1757),
                             lims_batches.csv (25), run_batch_map.csv (100),
                             process_steps.csv (173, produced by the pipeline)

synthetic_data_generation/   makes the QA and LIMS tables

investigation_variable/      rules out apple variety

investigation_operator/      the video pipeline and the technician comparison
  pipeline/                  00 prepare videos -> 06 render the SOP
  frames/                    one frame per second, 287 of them
  transcripts/               what each technician said while working
  output/                    per-video step breakdowns from each pass
  sops/                      the two synthesized procedures
  figures/                   the two comparison figures and their builders
  operator_approach.py       compares Molly against the other three

deliverables/                what the customer gets
  SOP - Slicing an Apple into Sections and Slices.docx
  check_adoption.py          did adopting it actually reduce variation?
```

The pipeline runs each video through two independent passes — one on the frames, one on the transcript — then reconciles them into a single breakdown where every action is tagged with which pass surfaced it. That tag is the point: an action only the frames saw is something the technician did without saying.

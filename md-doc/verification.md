# How the timeline and investments are verified

Status on 4 Oct 2026: **277 milestones** (1843 → 30 Sep 2026) and **56 investments** (2010 → Sep 2026).
Every entry has a `link` to the source that confirms it.

## Method

1. **Wikipedia text match.** About 230 relevant articles were downloaded as wikitext. An entry is
   confirmed when one of its distinctive names (e.g. "LSTM", "Falcon", "GPT-4", not just "Google")
   appears within ~350 characters of its date. Citation `access-date`/`archive-date` fields are
   ignored, so a citation's access date cannot count as evidence.
2. **arXiv.** Research papers are checked against arXiv's own first-submission date.
3. **Official or primary sources** for what Wikipedia doesn't state: European Commission (AI Act
   timeline), UN News (21 Mar 2024 resolution), OpenAI's RSS feed (Dots), The National (Falcon 180B),
   CNBC/Bloomberg (France €109B).
4. **Amounts** (investments) must appear next to the deal's date in the same source.
5. **Figures in summaries** (parameter counts, hours of audio, costs) must appear in the source too;
   unconfirmed figures were removed.
6. **Precision.** `precision: "month"` or `"year"` in the data means only that much of the date is
   confirmed. Cards then show the month or the year only, never a guessed day.

## Corrections made during verification

| Entry | Was | Now (source) |
|---|---|---|
| R.U.R. premiere | 25 Jan 1921 | 2 Jan 1921 (Wikipedia infobox) |
| McCulloch & Pitts neuron | Dec 1943 | 1943 |
| Strachey's draughts program | 1951, with Prinz chess | 1952, Prinz claim removed |
| GMDH (Ivakhnenko) | 1965 | 1968 |
| SNARC | "3,000 vacuum tubes" | figure removed: Wikipedia says 300; sources disagree |
| Batch normalization | 2 Mar 2015 | 11 Feb 2015 (arXiv) |
| PyTorch | 18 Jan 2017 | Sep 2016 |
| MIT AI Lab 1959 | unconfirmed | replaced by Project MAC, 1 Jul 1963 |
| GLM-130B | 4 Aug 2022 | 5 Oct 2022 (arXiv paper) |
| Qwen open release | 3 Aug 2023 | Sep 2023 (public release) |
| OpenClaw | 1 Nov 2025 | 24 Nov 2025 (first released as Warelay) |
| Claude 2 / Kimi / DeepSeek-V3 | 100K context / 200K chars / $5.6M | figures removed (not in source) |
| NVIDIA one-day loss | ~$590B on 27 Jan 2025 | ~$600B, January 2025 |
| Mistral Sept 2025 round | €1.7B at €11.7B | ASML €1.3B for 11% |
| xAI May 2024 round | $6B at $24B | $6B (valuation unconfirmed) |
| ~25 others | exact day | month or year precision |

## Removed (no supporting evidence found)

GPUs accelerate deep learning (2009) · Cursor launch date · China warns about OpenClaw (Feb 2026) ·
Mistral Large & Le Chat (26 Feb 2024) · K2 Think (Sep 2025) · Intel buys Habana Labs (amount).

## Added from verified sources

The 2026 gap was filled from Wikipedia's *List of large language models* and *2026 in artificial
intelligence*, for example Claude Fable 5 (9 Jun 2026) and its suspension (13 Jun 2026), GPT-6 Sol,
Gemini 4 Argon, Meta Muse, and OpenAI Dots (OpenAI RSS, 29 Sep 2026). 2026 investments come from the
OpenAI, Anthropic, xAI, Mistral AI, Moonshot AI, MGX and MiniMax articles.

## Limits

Wikipedia is a secondary source and can change. The scripts and article cache live outside the repo
(they were run once on 4 Oct 2026). Auto-detected "New" launches on the timeline come from the labs'
own RSS feeds and are not part of this verification.

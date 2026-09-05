# Project to-do list

Suggested improvements from the project review. These are proposals, not completed work.

## Reliability (first priority)

- [ ] **Make GPU fallback reliable.** Verify NVIDIA encoding works at runtime instead of only checking FFmpeg's encoder list. Retry on CPU if hardware encoding fails, with clear progress feedback.
- [ ] **Make export failures explicit.** Report failed attempts, retain useful FFmpeg diagnostics, and flag incomplete highlight reels. Do not report overall success when required processing steps fail.

## Editing quality (next priority)

- [ ] **Add video playback and precise trimming.** Preview attempts and adjust start and stop boundaries frame by frame, beyond the current thumbnail sampling intervals.
- [ ] **Support attempts spanning GoPro chapters.** Allow selection and export across consecutive chapter files belonging to the same recording.

## Larger feature

- [ ] **Suggest attempts automatically for review.** Explore motion analysis on lightweight GoPro `.LRV` footage to propose start and stop times for users to accept or adjust. Validate against real footage before treating suggestions as reliable.

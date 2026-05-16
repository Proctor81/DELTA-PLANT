# Render Free Pilot Test Plan

This checklist defines the first one-month live validation window for DELTA on
Render Free.

## Goal

Validate that the public service is usable in production-like conditions before
upgrading the backend to Starter and re-enabling persistent storage.

## Test window

- start: 17 May 2026
- duration: 30 days
- target end: 16 June 2026

## Success criteria

- public root remains reachable at `https://deltaplant.ai/`
- API health remains reachable at `https://api.deltaplant.ai/api/health`
- public workflow can complete at least one real area analysis per test cycle
- no unacceptable cold-start or failure rate is observed for public use
- bandwidth and build usage stay within acceptable limits
- no blocking issue is found in cookie, privacy, or PDF flow

## Weekly checks

1. open `https://deltaplant.ai/` and confirm `Live pipeline connected`
2. call `https://api.deltaplant.ai/api/health`
3. run one smoke analysis from the public UI
4. download one PDF report
5. confirm the legal pages still load correctly
6. review Render dashboard events for suspensions, restarts, or repeated failures

## Exit decision after 30 days

Move to Starter if all of the following are true:

- the live backend stayed usable for the full pilot window
- no structural blocker remains unresolved
- cold-start behavior is the main remaining limitation
- privacy and log durability should be restored for continued public operation

If those conditions are met, execute the switch checklist in
[RENDER_FREE_PILOT_RUNBOOK.md](RENDER_FREE_PILOT_RUNBOOK.md).
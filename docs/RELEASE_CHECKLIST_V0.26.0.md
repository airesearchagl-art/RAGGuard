# RAGGuard v0.26.0 Release Checklist

## Source and compatibility

- [ ] v0.25 authorization and usage are exact-bound from actual canonical objects.
- [ ] The full v0.24 approved-trial chain is revalidated.
- [ ] CLI exit codes are unchanged.
- [ ] Report schema is unchanged.
- [ ] v0.10-v0.25 governance contracts pass regression.

## Fixed boundary statements

- [ ] access authorized != actual read executed
- [ ] read started != read verified
- [ ] read succeeded != masking verified
- [ ] verified read != embedding authorized
- [ ] verified read != persistence authorized
- [ ] eligible_for_explicit_one_shot_trial_execution != executed

## Pre-read and controlled execution

- [ ] Request, authorization, selector, policy, trial, assignment, operator, and usage match.
- [ ] Internal-low-only, one-document, one-read, small-document constraints pass.
- [ ] The maximum stage is the masking-complete chunking candidate.
- [ ] Retention, raw logging, raw cache, persistence, export, and network are denied.
- [ ] Operator is distinct from access and trial approvers.
- [ ] All timestamps are explicit, timezone-aware UTC and correctly ordered.
- [ ] Automated execution uses only the immutable controlled fixture adapter.
- [ ] No arbitrary file reader or production read adapter exists.

## Verification, usage, and atomic ledger

- [ ] Raw content is represented only by a digest in evidence.
- [ ] Post-read classification and masking are exact-bound and passed.
- [ ] A receipt is minted only for a successfully verified read.
- [ ] Successful verified read consumes remaining usage exactly once, one to zero.
- [ ] Failure and injected fault consume nothing and leave replay sets unchanged.
- [ ] Request, target, result, classification, masking, receipt, and usage replay are blocked.
- [ ] Expired, revoked, exhausted, and superseded authorizations are rejected.
- [ ] Receipt, usage update, exhausted record, masked candidate, and replay state commit atomically.
- [ ] The final state is only `verified_masked_content_candidate`.

## Prohibited downstream and side effects

- [ ] Embedding, persistent vector write, retrieval, prompt/LLM input, export, and persistence are unauthorized.
- [ ] Actual arbitrary-file open/read counts are zero.
- [ ] Designated real-material and restricted-material access counts are zero.
- [ ] Real-data access count is zero.
- [ ] External network, HTTP, and cloud counts are zero.
- [ ] Filesystem, database, persistent-vector, and production-registry write counts are zero.
- [ ] Credential and token use counts are zero.
- [ ] Runtime activation and switch counts are zero.
- [ ] No persistent Vector DB is used.
- [ ] The actual one-shot real-data trial remains unexecuted and requires separate user approval.

## Validation and publication

- [ ] v0.26 targeted and Security E2E suites pass.
- [ ] Full pytest regression passes.
- [ ] CLI help, compileall, workflow YAML parse, and `git diff --check` pass.
- [ ] Bidi, CR-only, null-byte, secret, credential, URL/IP, and absolute-path scans pass or contain only reviewed documentation references.
- [ ] GitHub Actions succeeds on Python 3.11 and 3.12.
- [ ] Pull request remains Draft and is not merged.
- [ ] No tag or Release is created.

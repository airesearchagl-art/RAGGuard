# RAGGuard v0.30.0 Release Checklist

## Implementation PR gate

- [ ] Complete v0.29 packet/source object chain is canonical and exact-bound.
- [ ] A valid, live Human execution approval exact-binds packet and operator before open.
- [ ] One explicit root and one explicit relative target are capability-bound without scan.
- [ ] Raw content digest is derived after read, not trusted as a pre-read identity.
- [ ] Canonical v0.24/v0.25/v0.28 classification objects are exact-bound as positive evidence.
- [ ] No-match, missing/forged evidence, unknown, opaque, numeric-only, and ambiguity fail closed.
- [ ] Classification, masking, and chunking are derived from the controlled synthetic read.
- [ ] Controlled integration open/read counts are exactly one/one.
- [ ] Successful commit changes usage one-to-zero and exhausts authorization atomically.
- [ ] Pre-read failures mutate nothing; post-read failures spend approval but not usage.
- [ ] v0.30 targeted, Security E2E, regressions, CLI, compile, YAML, and safety checks pass.
- [ ] GitHub Actions succeeds on Python 3.11 and 3.12.
- [ ] Pull request remains Draft and is not merged by implementation work.
- [ ] No actual material trial, tag, or Release occurs in the implementation PR.

## Post-merge actual trial gate

- [ ] Main remains clean and matches the reviewed merge head.
- [ ] One exact packet/operator/root/target has a separately recorded Human approval.
- [ ] Approved actual file open count is one and read count is one.
- [ ] Positive object-backed classification evidence is valid and exact-bound to the target.
- [ ] Actual-content verification agrees with expected `internal_low` without sensitive/unknown
  signals.
- [ ] Masking is verified and transformed/raw digests differ.
- [ ] A residue-free digest-only chunking candidate is generated.
- [ ] Raw retention, logging, cache, persistence, and export counts are zero.
- [ ] Usage changes from one to zero exactly once and authorization is exhausted.
- [ ] Receipt, post-read evidence, and closure commit together.
- [ ] Embedding, vector DB, network/HTTP/cloud, production writes, credentials, and runtime counts
  are zero.
- [ ] Trial result receives explicit Human review.

## Publication

- [ ] All post-merge regression and actual-trial gates pass before tagging.
- [ ] Annotated tag v0.30.0 points to the reviewed main head.
- [ ] Published non-draft, non-prerelease GitHub Release uses that tag and has no custom asset.
- [ ] If the actual trial fails, no tag or Release is created.

# RAGGuard v0.23.0 Release Checklist

## Contract

- [ ] Environment manifest is immutable, metadata-only, canonical, and safe to represent.
- [ ] Seven concrete environment verification objects exact-bind manifest, suite, evidence, and verifier.
- [ ] Network disabled, credentials none, synthetic fixture, and test-only storage hard gates pass.
- [ ] Environment verifier, reviewer, and approver are pairwise distinct.
- [ ] Session request exact-binds environment approval and actual v0.22 manifest/plan/fixture objects.
- [ ] Session requester, operator, reviewer, and approver separation is enforced.
- [ ] Registry generation, predecessor, replay, terminal lifecycle, and fault atomicity tests pass.
- [ ] Controlled execution emits exactly eleven metadata-only stage results.
- [ ] Receipt exact-binds session, environment, v0.22 chain, fixture, operator, stages, and accounting.
- [ ] Forged operator, role context, stage, receipt, review, and approval fail closed.
- [ ] Independent security review and approval are required for review eligibility.

## Fixed safety boundary

- [ ] `environment attested != production environment approved`
- [ ] `approved session != real-data use approved`
- [ ] `controlled execution passed != real-data approved`
- [ ] `real-data trial approval review eligible != real-data use authorized`
- [ ] External network / HTTP / cloud counts are 0.
- [ ] Credential / token use counts are 0.
- [ ] Real-data access count is 0.
- [ ] Real filesystem / database / persistent vector write counts are 0.
- [ ] Production registry write / runtime activation / runtime switch counts are 0.

## Verification

- [ ] v0.23 targeted tests pass.
- [ ] Full regression passes.
- [ ] v0.22 and v0.21-v0.10 regression groups pass.
- [ ] Compatibility, profile integration, and HTTP security tests pass.
- [ ] CLI help, compileall, workflow YAML parse, and `git diff --check` pass.
- [ ] Bidi, CR-only, null-byte, secret, credential, URL, IP, absolute-path, and real-data scans pass.
- [ ] GitHub Actions succeeds on Python 3.11 and 3.12.
- [ ] Draft PR remains unmerged; no tag or Release is created.

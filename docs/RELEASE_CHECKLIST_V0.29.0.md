# RAGGuard v0.29.0 Release Checklist

## Source and packet

- [ ] Expected base is the reviewed v0.28 release head.
- [ ] Packet fields are immutable, metadata-only, canonical, and exact-bound.
- [ ] Allowed read count is one and stage ceiling is the chunking candidate.
- [ ] Raw retention/log/cache, persistence, export, and network are false.
- [ ] Public packet and summary contain no raw locator, payload, identity, credential, or token.

## Object-backed preparation gates

- [ ] Actual v0.25 authorization, operator, usage, policy, and source objects are revalidated.
- [ ] Actual v0.27 root descriptor, resolver policy, and opaque target are revalidated.
- [ ] Actual v0.28 purpose, root results/attestation, target, reviews, approval, and trial are
  revalidated.
- [ ] Authorization remains live with exactly one remaining use.
- [ ] Trial, authorization, root, attestation, approval, packet, and request have valid time order.
- [ ] Internal-low, one-document, fixed-purpose, role-separation, and closure gates pass.
- [ ] Forgery, widening, expiry, conflict, and replay fail closed.

## Human stop and side effects

- [ ] Maximum state is `ready_for_explicit_execution_approval`.
- [ ] Ready is not execution authorization and is not a file read.
- [ ] No execute/read/open/run-trial/auto-approval entrypoint exists.
- [ ] Actual/arbitrary file open/read and real-material access counts are zero.
- [ ] Filesystem/database/vector/production-registry write counts are zero.
- [ ] Network/HTTP/cloud, credential/token, and runtime activation/switch counts are zero.

## Validation and publication

- [ ] v0.29 targeted and Security E2E suites pass.
- [ ] v0.28-v0.22, v0.21-v0.10, compatibility/profile/HTTP, and full pytest pass.
- [ ] CLI help, compileall, workflow YAML parse, and `git diff --check` pass.
- [ ] Bidi, CR-only, null-byte, secret/credential, URL/IP, and unsafe-path scans pass or contain
  only reviewed documentation/test denial literals.
- [ ] GitHub Actions succeeds on Python 3.11 and 3.12.
- [ ] Pull request remains Draft and is not merged.
- [ ] No tag or Release is created.

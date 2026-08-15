# RAGGuard v0.27.0 Release Checklist

## Source and compatibility

- [ ] Expected main is the reviewed v0.26 release head and the feature branch is cleanly based.
- [ ] Actual v0.25 authorization and v0.26 request/target/context objects are exact-bound.
- [ ] CLI exit codes and report schema are unchanged.
- [ ] v0.10-v0.26 governance contracts pass regression.

## Resolver and pre-open boundary

- [ ] Root descriptor and target reference expose digest-only metadata.
- [ ] Policy denies symlink, junction, reparse, traversal, and absolute user input.
- [ ] Drive/UNC/device, alternate stream, wildcard, root escape, directory, wrong type, and
  oversized targets fail before open.
- [ ] No public arbitrary-path reader, unrestricted open, directory scanner, real-material root
  connector, credential loader, persistent writer, or runtime activator exists.
- [ ] Authorization, operator, one remaining read, selector, root, file class, and pre-identity
  are revalidated before open.

## TOCTOU, verification, usage, and closure

- [ ] Pre-open, opened-target, and post-read identity snapshots agree on stable success.
- [ ] Replacement/swap, content/metadata mutation, and link/reparse swap fail closed.
- [ ] v0.26 classification and masking remain distinct object-backed checks.
- [ ] Raw and transformed digests differ; raw/transformed document text is not retained.
- [ ] Only successful verified read consumes usage exactly once from one to zero.
- [ ] Receipt, exhausted authorization, usage, execution replay sets, and pending closure commit
  in one swap.
- [ ] Failure and injected fault leave usage, ledger state, and replay state unchanged and retryable.
- [ ] Explicit closure binds the same operator and produces metadata-only post-read evidence.
- [ ] Completed closure grants no downstream-processing or persistent-storage approval.

## Side effects and prohibited authority

- [ ] Controlled synthetic fixture target is read once on the success path.
- [ ] Arbitrary file, actual material, and restricted-material access counts are zero.
- [ ] External network, HTTP, cloud, credential, and token counts are zero.
- [ ] Filesystem/database/persistent-vector/production-registry production writes are zero.
- [ ] Runtime activation and switch counts are zero.
- [ ] Receipt does not authorize embedding, persistence, export, or runtime activation.
- [ ] The actual Local RAG material trial remains unexecuted and separately approval-gated.

## Validation and publication

- [ ] v0.27 targeted resolver, execution, Security E2E, and release-contract suites pass.
- [ ] v0.26, v0.25-v0.22, v0.21-v0.10, compatibility/profile/HTTP, and full pytest pass.
- [ ] CLI help, compileall, workflow YAML parse, and `git diff --check` pass.
- [ ] Bidi, CR-only, null-byte, secret/credential, URL/IP, and unsafe path scans pass or contain
  only reviewed documentation/test rejection literals.
- [ ] GitHub Actions succeeds on Python 3.11 and 3.12.
- [ ] Pull request remains Draft and is not merged.
- [ ] No tag or Release is created.

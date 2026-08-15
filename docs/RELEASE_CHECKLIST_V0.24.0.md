# RAGGuard v0.24.0 Release Checklist

## Contract

- [ ] Trial scope is immutable, metadata-only, canonical, and exact-bound to v0.23 objects.
- [ ] Classification prohibits personal, credential-like, and highly restricted data by default.
- [ ] Stage policy partitions all eleven stages and stops before embedding.
- [ ] Raw/log/cache/persistent retention is none and export is prohibited.
- [ ] Security review, governance review, and approval are independent objects.
- [ ] Requester, session operator, environment approver, reviewers, and approver are separated.
- [ ] Approved record includes request/reviews/approval/session/environment digests.
- [ ] Generation, predecessor, replay, retry, lifecycle, and fault atomicity tests pass.
- [ ] Explicit evaluation time is UTC with canonical six-digit microseconds.

## Fixed boundary

- [ ] `trial review eligible != trial approved`
- [ ] `trial approved != real-data access authorized`
- [ ] `approved trial != actual real-data read`
- [ ] `real-data access review eligible != real-data use authorized`
- [ ] Actual real-data read count is 0.
- [ ] No `C:\AI_Local_RAG` material access.
- [ ] No `C:\AI_Restricted` access.
- [ ] No arbitrary filesystem read or actual storage write.
- [ ] No persistent Vector DB.
- [ ] No credential or token use.
- [ ] No external API, cloud, or private LAN.
- [ ] No production registry write or runtime activation/switch.
- [ ] CLI exit codes and report schema remain unchanged.

## Verification

- [ ] v0.24 targeted tests pass.
- [ ] v0.23 and v0.22 targeted regressions pass.
- [ ] v0.21-v0.10 regressions pass.
- [ ] Compatibility, profile integration, and HTTP security regressions pass.
- [ ] Full pytest, CLI help, compileall, workflow YAML, and diff checks pass.
- [ ] Bidi, CR-only, null-byte, secret, credential, real-data, URL, IP, and path scans pass.
- [ ] GitHub Actions succeeds on Python 3.11 and 3.12.
- [ ] Draft PR remains unmerged; no tag or Release is created.

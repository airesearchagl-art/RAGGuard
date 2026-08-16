# RAGGuard v0.30 Actual One-Shot Execution Bridge and Trial Gate

## Scope

v0.30 supplies the last code boundary needed for one separately approved, one-document actual
trial. This implementation pull request itself reads only controlled synthetic temporary files.
It does not read actual Local RAG material or restricted material, and it does not create a tag or
Release.

Fixed distinctions:

- `packet prepared != execution approved`
- `Human execution approved != file read executed`
- `one-shot receipt != embedding authorization`
- `one-shot receipt != persistence authorization`
- `closure completed != downstream processing approval`
- `implementation merged != actual trial passed`
- `actual trial passed != unrestricted real-data processing`

## Exact object-backed gate

`ActualExecutionObjectChain` carries the actual preparation request, approved trial, v0.25 access
source, purpose, five root-verification results, attestation, target, closure requirement,
independent reviews, execution approval, eight-role context, and a
`PositiveInternalLowEvidence` object. That evidence exact-binds the canonical v0.24
classification policy, v0.25 selector/authorization/source trial, v0.28 approved one-shot trial,
and actual target selection. `evaluate_actual_trial_gate()`
reuses the v0.29 evaluator to validate every canonical object and binding. It requires the exact
`OneShotTrialExecutionPacket` object in
`ready_for_explicit_execution_approval` state. No digest string, reconstructed packet, Boolean
readiness claim, or caller override is trusted.

## Human execution approval

`HumanExecutionApproval` is immutable and canonical. It includes an approval ID, exact packet
digest, exact assigned operator, UTC approval and expiry times, and an approved/rejected result.
The executor cannot open the selected target without one valid, approved, live object. A rejected,
forged, expired, packet-mismatched, or operator-mismatched approval fails before open.

## Root and target authority

`provision_human_selected_actual_root()` accepts exactly one Human-supplied root and relative
target. It never scans, walks, expands a wildcard, discovers a root, creates a candidate list, or
chooses a fallback. UNC/network shares, root/drive-level scopes, traversal, absolute targets,
symlinks, junctions/reparse points, non-regular files, unsupported extensions, and oversized files
fail closed.

The public target is opaque metadata. The internal capability holds the root directory handle,
relative component chain, expected component identities, root/target/policy digests, and an
internally fixed actual-or-controlled-fixture use class. It contains no public raw path authority.
The executor opens relative to that root capability with no-follow semantics and never reopens a
raw path. Pre-read target identity is filesystem metadata, not a pre-known content digest. The raw
content digest is derived only after the one read and is exact-bound to the receipt.

## Raw-derived processing

The pure local classifier accepts only bytes already in memory plus the actual object-backed
positive evidence chain. It derives the raw digest, observed class, sensitive classes, matched
rule IDs, credential-like detection, and ambiguity. Absence of a sensitive-pattern match is not positive
classification evidence: without the valid exact-bound evidence, ordinary-looking content is
`unknown` and fails closed. Numeric-only candidates, opaque code-only content, unrecognized
sensitive wording, and new credential-like shapes also fail closed. Only positive evidence plus
an unambiguous actual-content verification agreeing on `internal_low` continues. It uses no LLM,
external API, cloud, HTTP, or network.

Masking is calculated from the actual bytes and classification. Every non-space token becomes an
irreversible index-bound digest token. Evidence binds raw and transformed digests, masked/blocked
class digests, token count, and residue verification; raw and transformed digests must differ.
The transformed value receives a non-authorizing residue inspection before it can become a
chunking candidate.

Chunking receives only the verified transformed value. Its metadata contains the masking digest,
transformed digest, chunking-policy digest, chunk count, chunk digests, and residue result. It does
not retain raw text and grants no embedding, vector-store, retrieval, prompt, LLM, persistence, or
export authority.

## Exactly-once ledger and failures

`ActualTrialExecutionLedger` is process-local and exposes no disk/database persistence surface.
Only the executor's private authority can mutate it. A verified success constructs the exhausted
authorization, zero-remaining usage, receipt, post-read evidence, completed closure, and replay
sets before one immutable candidate-state swap. A second packet/approval/target execution and an
exhausted authorization fail before another open.

Packet, approval, authorization, root, target, open, read, identity, classification, masking,
chunking, and commit failures do not consume authorization usage. Pre-read denial leaves the
ledger unchanged. Because a raw read cannot be undone, a failure after open/read records only the
Human approval as spent; retry requires a new Human approval and cannot happen automatically.
Commit fault never installs the candidate receipt/usage/authorization state.

## Side-effect contract

Controlled integration success has exactly one approved file open and one approved file read.
During this pull request all other counters are zero: actual Local RAG and restricted-material
access, arbitrary filesystem scan, network/HTTP/cloud, persistent vector DB, production
filesystem/database/registry write, credential/token use, runtime activation/switch, embedding,
persistence, export, and raw retention/log/cache.

## Release gate

The order is mandatory: merge the implementation PR, run main regression, obtain a Human approval
for one exact target, execute one actual trial, review its metadata-only result, and only then—if
all success/zero-side-effect gates pass—create the v0.30.0 tag and Release. A failed trial produces
a raw-free review reason and no tag or Release.

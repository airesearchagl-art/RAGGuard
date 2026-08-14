# Local RAG Integration Validation Boundary v0.22

## Scope

v0.22 validates a Local RAG data flow with synthetic or controlled fixtures only. It does
not read `C:\AI_Local_RAG`, `C:\AI_Restricted`, customer data, credentials, private LAN
resources, cloud services, external APIs, or a persistent vector database.

The fixed flow is: input candidate → RAGGuard policy decision → masking/sanitization →
chunking candidate → embedding input candidate → vector-store write candidate → retrieval
candidate → prompt construction candidate → LLM input candidate → response candidate →
logging/cache candidate. Every stage exact-binds its input/output digests, allowed and
prohibited data classes, persistence, logging, and external-I/O policy.

## Trust boundaries

- Raw fixture values are transient. A transformation record contains source/transformed
  digests and sensitive-class decisions, never the raw text.
- Every synthetic confidential class is masked before controlled chunking. A prohibited or
  credential-like value is blocked before embedding. No vector can reproduce raw text;
  v0.22 does not implement a real embedding operation.
- `TestOnlyVectorStore` is in-memory and test-only. It accepts only exact-bound approved
  transformed content. Raw, rejected, replaced, revoked, stale, or forged chunks do not
  mutate its state. There is no actual persistent vector DB.
- Retrieval returns only an approved chunk bound to its transformation record. Prompt input
  is rebuilt from approved masked retrieval, rejects credential-like content, hidden system
  data, uncontrolled metadata, and prompt injection through metadata.
- Logging/cache contain safe summary, opaque digest, approved metadata, and reason code only.
  They never contain a raw prompt, raw retrieval, raw confidential value, or credential.

## Receipt and governance

A passed receipt is issued only by the controlled evaluator after canonical-object,
exact-binding, accepted-boundary, and zero-side-effect checks. Caller-created passed
receipts and mutated canonical objects are rejected. Replay, stale fixture, future timestamp,
forged transformation record, forged receipt, and role conflict fail closed with downstream
state unchanged.

The integration operator, integration reviewer, and integration approver are three distinct
identities. An approved chain may reach `eligible_for_real_data_trial_review`; a separate
security review and separate authorization are still required.

## Release contract

- controlled integration passed != real data approved
- real-data trial review eligible != real-data use authorized
- Local RAG integration != production runtime activation
- no real customer data and no actual credential
- no external API, cloud, or private LAN
- no actual persistent vector DB and no production registry write
- external network count = 0; HTTP count = 0; cloud count = 0
- external API count = 0; credential use count = 0; token use count = 0

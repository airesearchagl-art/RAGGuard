"""RAGGuard package."""

from ragguard.manual_evidence_import import (
    ManualEvidenceImportError,
    ManualEvidenceImportErrorCategory,
    ManualEvidenceImportRequest,
    ManualEvidenceImportResult,
    ManualEvidenceSourceKind,
    import_manual_validation_evidence,
)
from ragguard.production_admission import (
    ProductionAdmissionDecision,
    ProductionAdmissionError,
    ProductionAdmissionErrorCategory,
    ProductionAdmissionReason,
    ProductionAdmissionRequest,
    ReviewerAttestation,
    ReviewerAttestationOutcome,
    RevalidationTrigger,
    evaluate_production_admission,
)
from ragguard.registry_admission import (
    CANONICAL_REGISTRY_ADMISSION_DIGEST_ALGORITHM,
    RegistryAdmissionEntry,
    RegistryAdmissionEntrySafeSummary,
    RegistryAdmissionError,
    RegistryAdmissionEvent,
    RegistryAdmissionReason,
    RegistryAdmissionRequest,
    RegistryAdmissionRequestSafeSummary,
    RegistryAdmissionResult,
    RegistryAdmissionSafeSummary,
    TestRegistryAdmissionStore,
    enforce_registry_admission,
)

__version__ = "0.1.0"

__all__ = [
    "CANONICAL_REGISTRY_ADMISSION_DIGEST_ALGORITHM",
    "ManualEvidenceImportError",
    "ManualEvidenceImportErrorCategory",
    "ManualEvidenceImportRequest",
    "ManualEvidenceImportResult",
    "ManualEvidenceSourceKind",
    "ProductionAdmissionDecision",
    "ProductionAdmissionError",
    "ProductionAdmissionErrorCategory",
    "ProductionAdmissionReason",
    "ProductionAdmissionRequest",
    "RegistryAdmissionEntry",
    "RegistryAdmissionEntrySafeSummary",
    "RegistryAdmissionError",
    "RegistryAdmissionEvent",
    "RegistryAdmissionReason",
    "RegistryAdmissionRequest",
    "RegistryAdmissionRequestSafeSummary",
    "RegistryAdmissionResult",
    "RegistryAdmissionSafeSummary",
    "ReviewerAttestation",
    "ReviewerAttestationOutcome",
    "RevalidationTrigger",
    "TestRegistryAdmissionStore",
    "enforce_registry_admission",
    "evaluate_production_admission",
    "import_manual_validation_evidence",
]

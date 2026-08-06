"""Compatibility exports for the preceding observe-only discovery foundation."""

from channel_engine.channel.pdd_discovery import (
    FakePDDDiscoveryObservationPort,
    InMemoryPDDDiscoveryObservationStore,
    PDDDiscoveryAdapter,
    PDDDiscoveryCapture,
    PDDDiscoveryMessageMapper,
    PDDDiscoveryObservation,
    PDDDiscoverySafetyViolation,
    PDDMessageMappingPreview,
    SyntheticPDDMessageEvidence,
)

__all__ = [
    "FakePDDDiscoveryObservationPort",
    "InMemoryPDDDiscoveryObservationStore",
    "PDDDiscoveryAdapter",
    "PDDDiscoveryCapture",
    "PDDDiscoveryMessageMapper",
    "PDDDiscoveryObservation",
    "PDDDiscoverySafetyViolation",
    "PDDMessageMappingPreview",
    "SyntheticPDDMessageEvidence",
]

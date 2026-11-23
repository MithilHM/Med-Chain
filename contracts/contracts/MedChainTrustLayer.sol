// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title MedChainTrustLayer
 * @notice DEPRECATED design sketch. Not deployed and not used by the API. Do not deploy.
 *
 * Kept only as a reference for the original blueprint. It violates the MedChain privacy model:
 * - Pseudonyms, requester IDs, scopes, and purposes are public plaintext strings on-chain, so
 *   activity is linkable to patients and research programmes forever.
 * - setConsent / anchorRecord / logAccessEvent have no access control: any account can grant
 *   or revoke any patient's consent and forge audit entries.
 * - isAccessPermitted loops over an unbounded per-patient array (gas grows without limit).
 * The deployed contract is MedChainAudit (keyed pseudonyms, writer authorization, versioning).
 */
contract MedChainTrustLayer {
    
    enum AccessType { Anonymized, FullText, Aggregated }
    enum ConsentState { REVOKED, ACTIVE }

    struct ConsentPolicy {
        string requesterId;
        string dataScope;      // e.g., "ICD-10:E11" (Diabetes)
        AccessType accessType;
        uint256 validFrom;
        uint256 validUntil;
        ConsentState state;
    }

    struct RecordAnchor {
        string recordId;
        bytes32 payloadHash;
        uint256 timestamp;
        address registeredBy;
    }

    struct AccessLog {
        string requesterId;
        string recordId;
        uint256 timestamp;
        string purpose;
        bool accessGranted;
    }

    // Mapping: patientPseudonym => list of consent policies
    mapping(string => ConsentPolicy[]) private patientConsents;
    
    // Mapping: recordId => RecordAnchor
    mapping(string => RecordAnchor) public recordAnchors;
    
    // Global Audit Trail
    AccessLog[] public auditLogs;

    // Events
    event ConsentUpdated(string indexed patientPseudonym, string indexed requesterId, ConsentState state);
    event RecordAnchored(string indexed recordId, bytes32 payloadHash);
    event AccessAttempted(string indexed requesterId, string indexed recordId, bool granted);

    // Anchor a record hash to the blockchain
    function anchorRecord(string calldata recordId, bytes32 payloadHash) external {
        require(recordAnchors[recordId].timestamp == 0, "Record hash already anchored");
        recordAnchors[recordId] = RecordAnchor({
            recordId: recordId,
            payloadHash: payloadHash,
            timestamp: block.timestamp,
            registeredBy: msg.sender
        });
        emit RecordAnchored(recordId, payloadHash);
    }

    // Patient grants or updates consent
    function setConsent(
        string calldata patientPseudonym,
        string calldata requesterId,
        string calldata dataScope,
        AccessType accessType,
        uint256 validUntil,
        ConsentState state
    ) external {
        patientConsents[patientPseudonym].push(ConsentPolicy({
            requesterId: requesterId,
            dataScope: dataScope,
            accessType: accessType,
            validFrom: block.timestamp,
            validUntil: validUntil,
            state: state
        }));
        
        emit ConsentUpdated(patientPseudonym, requesterId, state);
    }

    // Verify if access is currently valid
    function isAccessPermitted(
        string calldata patientPseudonym,
        string calldata requesterId,
        string calldata requestedScope
    ) public view returns (bool) {
        ConsentPolicy[] memory policies = patientConsents[patientPseudonym];
        for (uint256 i = policies.length; i > 0; i--) {
            ConsentPolicy memory policy = policies[i - 1];
            if (
                keccak256(bytes(policy.requesterId)) == keccak256(bytes(requesterId)) &&
                keccak256(bytes(policy.dataScope)) == keccak256(bytes(requestedScope))
            ) {
                if (policy.state == ConsentState.ACTIVE && block.timestamp <= policy.validUntil) {
                    return true;
                } else {
                    return false; // Latest state takes precedence
                }
            }
        }
        return false;
    }

    // Record an access event for immutable audit trailing
    function logAccessEvent(
        string calldata requesterId,
        string calldata recordId,
        string calldata patientPseudonym,
        string calldata scope,
        string calldata purpose
    ) external returns (bool) {
        bool granted = isAccessPermitted(patientPseudonym, requesterId, scope);
        
        auditLogs.push(AccessLog({
            requesterId: requesterId,
            recordId: recordId,
            timestamp: block.timestamp,
            purpose: purpose,
            accessGranted: granted
        }));

        emit AccessAttempted(requesterId, recordId, granted);
        return granted;
    }

    // Public getters for audit trail inspection
    function getAuditLogsCount() external view returns (uint256) {
        return auditLogs.length;
    }

    function getAuditLog(uint256 index) external view returns (
        string memory requesterId,
        string memory recordId,
        uint256 timestamp,
        string memory purpose,
        bool accessGranted
    ) {
        require(index < auditLogs.length, "Index out of bounds");
        AccessLog memory logEntry = auditLogs[index];
        return (
            logEntry.requesterId,
            logEntry.recordId,
            logEntry.timestamp,
            logEntry.purpose,
            logEntry.accessGranted
        );
    }

    function getPatientConsentCount(string calldata patientPseudonym) external view returns (uint256) {
        return patientConsents[patientPseudonym].length;
    }
}

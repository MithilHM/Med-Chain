// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title MedChainAudit
 * @dev Append-only evidence and audit anchor for patient consent and record integrity.
 * Strictly stores opaque keyed pseudonyms (HMAC-SHA256 computed off-chain) and commitments.
 * Never stores raw clinical notes, patient names, PII, or diagnosis details.
 *
 * Integrity rules enforced on-chain:
 * - Only authorized writers (hospital signing keys) can record evidence; the owner manages writers,
 *   so a signing key can be rotated or a second hospital node added without redeploying.
 * - A consent ID is recorded once; it can move GRANTED -> REVOKED but never be silently re-granted.
 * - Record commitments are versioned and versions only increase, so an anchored commitment can be
 *   superseded by an amendment but never overwritten or rolled back. Every version stays in the
 *   RecordAnchored event log.
 */
contract MedChainAudit {
    address public owner;
    mapping(address => bool) public writers;

    enum ConsentStatus { NONE, GRANTED, REVOKED }

    struct ConsentRecord {
        bytes32 patientRefHash;
        bytes32 projectRefHash;
        uint64 validUntil;
        ConsentStatus status;
        uint256 updatedAt;
    }

    struct RecordCommitment {
        bytes32 commitmentHash;
        uint32 version;
        uint256 anchoredAt;
    }

    // consentIdHash => ConsentRecord
    mapping(bytes32 => ConsentRecord) public consents;

    // recordRefHash => RecordCommitment
    mapping(bytes32 => RecordCommitment) public recordCommitments;

    event ConsentGranted(
        bytes32 indexed consentIdHash,
        bytes32 indexed patientRefHash,
        bytes32 indexed projectRefHash,
        uint64 validUntil,
        uint256 timestamp
    );

    event ConsentRevoked(
        bytes32 indexed consentIdHash,
        bytes32 indexed patientRefHash,
        uint256 timestamp
    );

    event AccessLogged(
        bytes32 indexed eventIdHash,
        bytes32 indexed actorHash,
        bytes32 indexed resourceRefHash,
        string action,
        string decision,
        uint256 timestamp
    );

    event RecordAnchored(
        bytes32 indexed recordRefHash,
        bytes32 indexed commitmentHash,
        uint32 version,
        uint256 timestamp
    );

    event WriterUpdated(address indexed writer, bool authorized);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    modifier onlyOwner() {
        require(msg.sender == owner, "Only contract owner can execute");
        _;
    }

    modifier onlyWriter() {
        require(writers[msg.sender], "Caller is not an authorized writer");
        _;
    }

    constructor() {
        owner = msg.sender;
        writers[msg.sender] = true;
        emit WriterUpdated(msg.sender, true);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "Invalid new owner");
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    function setWriter(address writer, bool authorized) external onlyOwner {
        require(writer != address(0), "Invalid writer");
        writers[writer] = authorized;
        emit WriterUpdated(writer, authorized);
    }

    /**
     * @notice Records a granted consent commitment on-chain.
     */
    function grantConsent(
        bytes32 consentIdHash,
        bytes32 patientRefHash,
        bytes32 projectRefHash,
        uint64 validUntil
    ) external onlyWriter {
        require(consentIdHash != bytes32(0), "Invalid consent ID hash");
        require(patientRefHash != bytes32(0), "Invalid patient ref hash");
        require(validUntil > block.timestamp, "Expiry must be in the future");
        require(consents[consentIdHash].status == ConsentStatus.NONE, "Consent already recorded");

        consents[consentIdHash] = ConsentRecord({
            patientRefHash: patientRefHash,
            projectRefHash: projectRefHash,
            validUntil: validUntil,
            status: ConsentStatus.GRANTED,
            updatedAt: block.timestamp
        });

        emit ConsentGranted(
            consentIdHash,
            patientRefHash,
            projectRefHash,
            validUntil,
            block.timestamp
        );
    }

    /**
     * @notice Revokes a previously granted consent commitment on-chain.
     */
    function revokeConsent(
        bytes32 consentIdHash,
        bytes32 patientRefHash
    ) external onlyWriter {
        require(consents[consentIdHash].status == ConsentStatus.GRANTED, "Consent not active or not found");
        require(consents[consentIdHash].patientRefHash == patientRefHash, "Patient hash mismatch");

        consents[consentIdHash].status = ConsentStatus.REVOKED;
        consents[consentIdHash].updatedAt = block.timestamp;

        emit ConsentRevoked(consentIdHash, patientRefHash, block.timestamp);
    }

    /**
     * @notice Checks whether a given consent is currently active on-chain.
     */
    function isConsentActive(bytes32 consentIdHash) external view returns (bool) {
        ConsentRecord memory c = consents[consentIdHash];
        return (c.status == ConsentStatus.GRANTED && c.validUntil >= block.timestamp);
    }

    /**
     * @notice Anchors a cryptographic commitment of a clinical document or record.
     */
    function anchorRecord(
        bytes32 recordRefHash,
        bytes32 commitmentHash,
        uint32 version
    ) external onlyWriter {
        require(recordRefHash != bytes32(0), "Invalid record ref hash");
        require(commitmentHash != bytes32(0), "Invalid commitment hash");
        require(version > 0, "Version must be positive");
        require(version > recordCommitments[recordRefHash].version, "Version must increase");

        recordCommitments[recordRefHash] = RecordCommitment({
            commitmentHash: commitmentHash,
            version: version,
            anchoredAt: block.timestamp
        });

        emit RecordAnchored(
            recordRefHash,
            commitmentHash,
            version,
            block.timestamp
        );
    }

    /**
     * @notice Logs an access event hash to the ledger for tamper-evident auditability.
     */
    function logAccessEvent(
        bytes32 eventIdHash,
        bytes32 actorHash,
        bytes32 resourceRefHash,
        string calldata action,
        string calldata decision
    ) external onlyWriter {
        require(eventIdHash != bytes32(0), "Invalid event ID hash");
        emit AccessLogged(
            eventIdHash,
            actorHash,
            resourceRefHash,
            action,
            decision,
            block.timestamp
        );
    }

    /**
     * @notice Retrieves the anchored commitment hash and version for a given record reference.
     */
    function getRecordCommitment(bytes32 recordRefHash)
        external
        view
        returns (bytes32 commitmentHash, uint32 version, uint256 anchoredAt)
    {
        RecordCommitment memory rc = recordCommitments[recordRefHash];
        return (rc.commitmentHash, rc.version, rc.anchoredAt);
    }
}

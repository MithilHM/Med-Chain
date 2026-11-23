const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("MedChainAudit Contract", function () {
  let medchainAudit;
  let owner;
  let unauthorized;

  const mockConsentIdHash = ethers.keccak256(ethers.toUtf8Bytes("consent-uuid-101"));
  const mockPatientRefHash = ethers.keccak256(ethers.toUtf8Bytes("patient-uuid-pt1"));
  const mockProjectRefHash = ethers.keccak256(ethers.toUtf8Bytes("project-uuid-proj1"));

  const mockRecordRefHash = ethers.keccak256(ethers.toUtf8Bytes("doc-uuid-555"));
  const mockCommitmentHash = ethers.keccak256(ethers.toUtf8Bytes("canonical-json-salted-hash-abc"));

  const mockEventIdHash = ethers.keccak256(ethers.toUtf8Bytes("event-uuid-999"));
  const mockActorHash = ethers.keccak256(ethers.toUtf8Bytes("user-uuid-researcher1"));

  beforeEach(async function () {
    [owner, unauthorized] = await ethers.getSigners();
    const MedChainAuditFactory = await ethers.getContractFactory("MedChainAudit");
    medchainAudit = await MedChainAuditFactory.deploy();
    await medchainAudit.waitForDeployment();
  });

  describe("Deployment", function () {
    it("Should set the correct deployer as owner", async function () {
      expect(await medchainAudit.owner()).to.equal(owner.address);
    });
  });

  describe("Consent Management", function () {
    it("Should allow owner to grant consent and emit ConsentGranted event", async function () {
      const latestBlock = await ethers.provider.getBlock("latest");
      const futureExpiry = latestBlock.timestamp + 86400; // +1 day

      await expect(
        medchainAudit.grantConsent(
          mockConsentIdHash,
          mockPatientRefHash,
          mockProjectRefHash,
          futureExpiry
        )
      )
        .to.emit(medchainAudit, "ConsentGranted")
        .withArgs(
          mockConsentIdHash,
          mockPatientRefHash,
          mockProjectRefHash,
          futureExpiry,
          (ts) => ts > 0
        );

      const isActive = await medchainAudit.isConsentActive(mockConsentIdHash);
      expect(isActive).to.be.true;
    });

    it("Should reject granting consent with past expiry", async function () {
      const latestBlock = await ethers.provider.getBlock("latest");
      const pastExpiry = latestBlock.timestamp - 100;

      await expect(
        medchainAudit.grantConsent(
          mockConsentIdHash,
          mockPatientRefHash,
          mockProjectRefHash,
          pastExpiry
        )
      ).to.be.revertedWith("Expiry must be in the future");
    });

    it("Should allow owner to revoke active consent and emit ConsentRevoked event", async function () {
      const latestBlock = await ethers.provider.getBlock("latest");
      const futureExpiry = latestBlock.timestamp + 86400;

      await medchainAudit.grantConsent(
        mockConsentIdHash,
        mockPatientRefHash,
        mockProjectRefHash,
        futureExpiry
      );

      await expect(
        medchainAudit.revokeConsent(mockConsentIdHash, mockPatientRefHash)
      )
        .to.emit(medchainAudit, "ConsentRevoked")
        .withArgs(mockConsentIdHash, mockPatientRefHash, (ts) => ts > 0);

      const isActive = await medchainAudit.isConsentActive(mockConsentIdHash);
      expect(isActive).to.be.false;
    });

    it("Should reject unauthorized caller from granting consent", async function () {
      const latestBlock = await ethers.provider.getBlock("latest");
      const futureExpiry = latestBlock.timestamp + 86400;

      await expect(
        medchainAudit
          .connect(unauthorized)
          .grantConsent(
            mockConsentIdHash,
            mockPatientRefHash,
            mockProjectRefHash,
            futureExpiry
          )
      ).to.be.revertedWith("Caller is not an authorized writer");
    });

    it("Should never re-grant a consent ID that was already recorded or revoked", async function () {
      const latestBlock = await ethers.provider.getBlock("latest");
      const futureExpiry = latestBlock.timestamp + 86400;
      await medchainAudit.grantConsent(mockConsentIdHash, mockPatientRefHash, mockProjectRefHash, futureExpiry);
      await medchainAudit.revokeConsent(mockConsentIdHash, mockPatientRefHash);

      await expect(
        medchainAudit.grantConsent(mockConsentIdHash, mockPatientRefHash, mockProjectRefHash, futureExpiry + 10)
      ).to.be.revertedWith("Consent already recorded");
      expect(await medchainAudit.isConsentActive(mockConsentIdHash)).to.be.false;
    });
  });

  describe("Writer Authorization", function () {
    it("Should let the owner authorize and remove additional writers", async function () {
      await expect(medchainAudit.setWriter(unauthorized.address, true))
        .to.emit(medchainAudit, "WriterUpdated")
        .withArgs(unauthorized.address, true);
      await medchainAudit.connect(unauthorized).anchorRecord(mockRecordRefHash, mockCommitmentHash, 1);

      await medchainAudit.setWriter(unauthorized.address, false);
      await expect(
        medchainAudit.connect(unauthorized).anchorRecord(mockRecordRefHash, mockCommitmentHash, 2)
      ).to.be.revertedWith("Caller is not an authorized writer");
    });

    it("Should prevent non-owners from managing writers", async function () {
      await expect(
        medchainAudit.connect(unauthorized).setWriter(unauthorized.address, true)
      ).to.be.revertedWith("Only contract owner can execute");
    });
  });

  describe("Record Integrity Anchoring", function () {
    it("Should anchor a cryptographic commitment and retrieve it", async function () {
      await expect(
        medchainAudit.anchorRecord(mockRecordRefHash, mockCommitmentHash, 1)
      )
        .to.emit(medchainAudit, "RecordAnchored")
        .withArgs(mockRecordRefHash, mockCommitmentHash, 1, (ts) => ts > 0);

      const [storedCommitment, version, anchoredAt] =
        await medchainAudit.getRecordCommitment(mockRecordRefHash);

      expect(storedCommitment).to.equal(mockCommitmentHash);
      expect(version).to.equal(1);
      expect(anchoredAt).to.be.gt(0);
    });

    it("Should reject zero commitment hash", async function () {
      await expect(
        medchainAudit.anchorRecord(
          mockRecordRefHash,
          ethers.ZeroHash,
          1
        )
      ).to.be.revertedWith("Invalid commitment hash");
    });

    it("Should accept a newer amendment version but refuse overwrite or rollback", async function () {
      const amendedCommitment = ethers.keccak256(ethers.toUtf8Bytes("amended-version-2"));
      await medchainAudit.anchorRecord(mockRecordRefHash, mockCommitmentHash, 1);
      await medchainAudit.anchorRecord(mockRecordRefHash, amendedCommitment, 2);

      const [stored, version] = await medchainAudit.getRecordCommitment(mockRecordRefHash);
      expect(stored).to.equal(amendedCommitment);
      expect(version).to.equal(2);

      const forged = ethers.keccak256(ethers.toUtf8Bytes("tampered"));
      await expect(medchainAudit.anchorRecord(mockRecordRefHash, forged, 2)).to.be.revertedWith("Version must increase");
      await expect(medchainAudit.anchorRecord(mockRecordRefHash, forged, 1)).to.be.revertedWith("Version must increase");
    });
  });

  describe("Audit & Access Logging", function () {
    it("Should emit AccessLogged event with action and decision", async function () {
      await expect(
        medchainAudit.logAccessEvent(
          mockEventIdHash,
          mockActorHash,
          mockRecordRefHash,
          "EXPORT_RESEARCH_COHORT",
          "GRANTED"
        )
      )
        .to.emit(medchainAudit, "AccessLogged")
        .withArgs(
          mockEventIdHash,
          mockActorHash,
          mockRecordRefHash,
          "EXPORT_RESEARCH_COHORT",
          "GRANTED",
          (ts) => ts > 0
        );
    });
  });
});

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

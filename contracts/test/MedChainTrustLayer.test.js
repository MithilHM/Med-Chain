const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("MedChainTrustLayer Contract", function () {
  let trustLayer;
  let owner;
  let researcher;
  let patient;

  const PATIENT_PSEUDONYM = "P1024";
  const REQUESTER_ID = "RES-PROJECT-01";
  const DATA_SCOPE = "ICD-10:E11";
  const RECORD_ID = "DOC-99201";
  const SAMPLE_HASH = ethers.keccak256(ethers.toUtf8Bytes("canonical-medical-payload-test"));

  beforeEach(async function () {
    [owner, researcher, patient] = await ethers.getSigners();
    const TrustLayerFactory = await ethers.getContractFactory("MedChainTrustLayer");
    trustLayer = await TrustLayerFactory.deploy();
    await trustLayer.waitForDeployment();
  });

  describe("Record Anchoring", function () {
    it("Should successfully anchor off-chain payload hash and emit RecordAnchored", async function () {
      await expect(trustLayer.anchorRecord(RECORD_ID, SAMPLE_HASH))
        .to.emit(trustLayer, "RecordAnchored")
        .withArgs(RECORD_ID, SAMPLE_HASH);

      const anchor = await trustLayer.recordAnchors(RECORD_ID);
      expect(anchor.recordId).to.equal(RECORD_ID);
      expect(anchor.payloadHash).to.equal(SAMPLE_HASH);
      expect(anchor.registeredBy).to.equal(owner.address);
      expect(anchor.timestamp).to.be.gt(0);
    });

    it("Should reject re-anchoring an already anchored recordId", async function () {
      await trustLayer.anchorRecord(RECORD_ID, SAMPLE_HASH);
      await expect(
        trustLayer.anchorRecord(RECORD_ID, SAMPLE_HASH)
      ).to.be.revertedWith("Record hash already anchored");
    });
  });

  describe("Consent Management", function () {
    it("Should grant active consent policy and permit access", async function () {
      const latestBlock = await ethers.provider.getBlock("latest");
      const validUntil = latestBlock.timestamp + 86400 * 30; // 30 days

      await expect(
        trustLayer.setConsent(
          PATIENT_PSEUDONYM,
          REQUESTER_ID,
          DATA_SCOPE,
          0, // AccessType.Anonymized
          validUntil,
          1  // ConsentState.ACTIVE
        )
      )
        .to.emit(trustLayer, "ConsentUpdated")
        .withArgs(PATIENT_PSEUDONYM, REQUESTER_ID, 1);

      const permitted = await trustLayer.isAccessPermitted(
        PATIENT_PSEUDONYM,
        REQUESTER_ID,
        DATA_SCOPE
      );
      expect(permitted).to.be.true;
    });

    it("Should reject access if consent was never granted", async function () {
      const permitted = await trustLayer.isAccessPermitted(
        PATIENT_PSEUDONYM,
        "UNKNOWN-REQ",
        DATA_SCOPE
      );
      expect(permitted).to.be.false;
    });

    it("Should reject access if consent was revoked", async function () {
      const latestBlock = await ethers.provider.getBlock("latest");
      const validUntil = latestBlock.timestamp + 86400 * 30;

      // Grant
      await trustLayer.setConsent(
        PATIENT_PSEUDONYM,
        REQUESTER_ID,
        DATA_SCOPE,
        0,
        validUntil,
        1 // ACTIVE
      );

      // Revoke
      await trustLayer.setConsent(
        PATIENT_PSEUDONYM,
        REQUESTER_ID,
        DATA_SCOPE,
        0,
        validUntil,
        0 // REVOKED
      );

      const permitted = await trustLayer.isAccessPermitted(
        PATIENT_PSEUDONYM,
        REQUESTER_ID,
        DATA_SCOPE
      );
      expect(permitted).to.be.false;
    });

    it("Should reject access if scope does not match", async function () {
      const latestBlock = await ethers.provider.getBlock("latest");
      const validUntil = latestBlock.timestamp + 86400 * 30;

      await trustLayer.setConsent(
        PATIENT_PSEUDONYM,
        REQUESTER_ID,
        DATA_SCOPE,
        0,
        validUntil,
        1
      );

      const permitted = await trustLayer.isAccessPermitted(
        PATIENT_PSEUDONYM,
        REQUESTER_ID,
        "ICD-10:I10" // Different scope
      );
      expect(permitted).to.be.false;
    });
  });

  describe("Access Event Logging & Audit Trail", function () {
    it("Should log access attempt on-chain and record audit entry", async function () {
      const latestBlock = await ethers.provider.getBlock("latest");
      const validUntil = latestBlock.timestamp + 86400 * 30;

      await trustLayer.setConsent(
        PATIENT_PSEUDONYM,
        REQUESTER_ID,
        DATA_SCOPE,
        0,
        validUntil,
        1
      );

      await expect(
        trustLayer.logAccessEvent(
          REQUESTER_ID,
          RECORD_ID,
          PATIENT_PSEUDONYM,
          DATA_SCOPE,
          "Longitudinal observational trial"
        )
      )
        .to.emit(trustLayer, "AccessAttempted")
        .withArgs(REQUESTER_ID, RECORD_ID, true);

      const count = await trustLayer.getAuditLogsCount();
      expect(count).to.equal(1);

      const log = await trustLayer.getAuditLog(0);
      expect(log.requesterId).to.equal(REQUESTER_ID);
      expect(log.recordId).to.equal(RECORD_ID);
      expect(log.purpose).to.equal("Longitudinal observational trial");
      expect(log.accessGranted).to.be.true;
    });

    it("Should record denied access attempt in audit trail when unconsented", async function () {
      await expect(
        trustLayer.logAccessEvent(
          "UNAUTHORIZED_REQ",
          RECORD_ID,
          PATIENT_PSEUDONYM,
          DATA_SCOPE,
          "Unauthorized data harvest"
        )
      )
        .to.emit(trustLayer, "AccessAttempted")
        .withArgs("UNAUTHORIZED_REQ", RECORD_ID, false);

      const log = await trustLayer.getAuditLog(0);
      expect(log.accessGranted).to.be.false;
    });
  });
});

const hre = require("hardhat");
const fs = require("fs");
const path = require("path");

// Deploys the MedChainAudit evidence contract. MedChainTrustLayer is a deprecated design sketch
// (public plaintext identifiers, no access control) and is intentionally not deployed.
//
// Optional: EXTRA_WRITER_ADDRESSES=0xabc...,0xdef... authorizes additional hospital signing keys.
async function main() {
  console.log("Deploying MedChainAudit to network:", hre.network.name);
  const MedChainAudit = await hre.ethers.getContractFactory("MedChainAudit");
  const auditContract = await MedChainAudit.deploy();
  await auditContract.waitForDeployment();
  const auditAddress = await auditContract.getAddress();
  console.log("MedChainAudit deployed successfully at address:", auditAddress);

  const extraWriters = (process.env.EXTRA_WRITER_ADDRESSES || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  for (const writer of extraWriters) {
    const tx = await auditContract.setWriter(writer, true);
    await tx.wait();
    console.log("Authorized additional writer:", writer);
  }

  const deployInfo = {
    network: hre.network.name,
    medChainAuditAddress: auditAddress,
    contractAddress: auditAddress,
    writers: extraWriters,
    deployedAt: new Date().toISOString(),
  };

  const outPath = path.join(__dirname, "../deployment.json");
  fs.writeFileSync(outPath, JSON.stringify(deployInfo, null, 2));
  console.log("Wrote deployment artifact to:", outPath);
}

main().catch((error) => {
  console.error("Deployment failed:", error);
  process.exitCode = 1;
});

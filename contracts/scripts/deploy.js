const hre = require("hardhat");
const fs = require("fs");
const path = require("path");

async function main() {
  console.log("Deploying MedChainAudit to network:", hre.network.name);

  const MedChainAudit = await hre.ethers.getContractFactory("MedChainAudit");
  const contract = await MedChainAudit.deploy();
  await contract.waitForDeployment();

  const address = await contract.getAddress();
  console.log("MedChainAudit deployed successfully at address:", address);

  // Write deployment info to deployment.json
  const deployInfo = {
    network: hre.network.name,
    contractAddress: address,
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

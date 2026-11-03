FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

RUN npx hardhat compile

EXPOSE 8545

CMD ["sh", "-c", "npx hardhat node --hostname 0.0.0.0 & node_pid=$!; until node -e 'fetch(\"http://127.0.0.1:8545\",{method:\"POST\",headers:{\"content-type\":\"application/json\"},body:JSON.stringify({jsonrpc:\"2.0\",method:\"eth_chainId\",params:[],id:1})}).then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))'; do sleep 1; done; npx hardhat run scripts/deploy.js --network localhost; wait $node_pid"]

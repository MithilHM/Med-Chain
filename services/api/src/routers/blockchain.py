from fastapi import APIRouter
from src.services.blockchain import BlockchainService

router = APIRouter(prefix="/blockchain", tags=["Blockchain Integration"])

@router.get("/status")
def get_blockchain_status():
    return BlockchainService.get_status()

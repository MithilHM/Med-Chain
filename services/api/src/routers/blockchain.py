from fastapi import APIRouter, Depends
from src.models import AppUser
from src.routers.deps import require_role
from src.services.blockchain import BlockchainService

router = APIRouter(prefix="/blockchain", tags=["Blockchain Integration"])

@router.get("/status")
def get_blockchain_status(current_user: AppUser = Depends(require_role(["admin"]))):
    return BlockchainService.get_status()

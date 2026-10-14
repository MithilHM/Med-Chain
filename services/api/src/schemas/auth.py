from typing import Optional
from pydantic import BaseModel

class LoginRequest(BaseModel):
    email: Optional[str] = None
    username: Optional[str] = None
    password: str

    @property
    def user_email(self) -> str:
        return self.email or self.username or ""

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"

class UserOut(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool
    patient_id: Optional[str] = None
    doctor_id: Optional[str] = None

    class Config:
        from_attributes = True

TokenResponse.model_rebuild()

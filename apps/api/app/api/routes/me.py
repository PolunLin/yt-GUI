from fastapi import APIRouter

router = APIRouter()

@router.get("")
def me():
    return {"ok": True}
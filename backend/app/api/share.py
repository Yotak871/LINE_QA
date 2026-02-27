from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.database import ShareLink, Analysis, get_db

router = APIRouter(prefix="/api/share", tags=["share"])


@router.post("/{analysis_id}")
async def create_share_link(
    analysis_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """공유 링크를 생성한다. expires_days: 7 / 30 / null (영구)"""
    result = await db.execute(select(Analysis).where(Analysis.id == analysis_id))
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "분석을 찾을 수 없습니다.")

    expires_days = body.get("expires_days")
    expires_at = None
    if expires_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=int(expires_days))

    link = ShareLink(analysis_id=analysis_id, expires_at=expires_at)
    db.add(link)
    await db.commit()
    await db.refresh(link)

    return {"short_id": link.short_id, "expires_at": expires_at}


@router.get("/{short_id}")
async def get_shared_result(short_id: str, db: AsyncSession = Depends(get_db)):
    """공유 링크로 분석 결과를 조회한다."""
    result = await db.execute(select(ShareLink).where(ShareLink.short_id == short_id))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(404, "유효하지 않은 링크입니다.")

    if link.expires_at and link.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(410, "만료된 링크입니다.")

    # 분석 결과 가져오기 (analyze.py의 get_result 재사용)
    from app.api.analyze import get_result
    return await get_result(link.analysis_id, db)

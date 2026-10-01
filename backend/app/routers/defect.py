"""缺陷登记接口：维护机组缺陷，覆盖确认定级、提交消除、验收消除、退回与复核，并提供分级看板。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.defect import LEVELS, DefectService

router = APIRouter(prefix="/api/defect", tags=["缺陷登记"])

service = DefectService()

LIST_FIELDS = ["缺陷编号", "缺陷部位", "缺陷等级", "发现方式", "发现时间", "报告人", "计划消除日", "缺陷状态"]
STATUSES = ["待定级", "已定级", "处置中", "已消除"]


class StandardRule(BaseModel):
    keyword: str = ""
    level: str = ""


class StandardPayload(BaseModel):
    """定级标准调整入参：关键字规则（按顺序匹配）与默认等级。"""

    rules: list[StandardRule] = Field(default_factory=list)
    default: str = "三级"


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按缺陷编号检索"),
    status: str | None = Query(default=None, description="待定级、已定级、处置中、已消除"),
    part: str | None = Query(default=None, description="按缺陷部位过滤，看板点分区时使用"),
    level: str | None = Query(default=None, description="按判定等级过滤：一级至四级"),
    review: bool = Query(default=False, description="只看待复核名单"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按缺陷编号、状态、部位、等级过滤缺陷登记列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if status and status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"状态仅支持：{'、'.join(STATUSES)}")
    if level and level not in LEVELS:
        raise HTTPException(status_code=400, detail=f"等级仅支持：{'、'.join(LEVELS)}")
    items, total = service.list_entries(
        keyword=keyword, status=status, part=part, level=level, review=review, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/board")
def defect_board() -> dict[str, Any]:
    """缺陷分级看板：按部位分区统计四态数量、等级分布、最近计划消除项与提示名单。"""
    return service.board()


@router.get("/standard")
def get_standard() -> dict[str, Any]:
    """读取当前定级标准。"""
    return service.get_standard()


@router.put("/standard", response_model=ActionResult)
def update_standard(payload: StandardPayload) -> ActionResult:
    """调整定级标准并重新判定全部缺陷；历史定级结论保留，只刷新判定等级。"""
    rules = [rule.model_dump() for rule in payload.rules]
    data, message = service.update_standard(rules, payload.default)
    if data is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=f"定级标准已更新，{data['changed']} 条缺陷按新标准重新判定", entry=data["standard"])


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出缺陷登记清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "defect", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条机组缺陷明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"机组缺陷 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条机组缺陷，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="机组缺陷已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条机组缺陷执行确认定级、提交消除、验收消除、退回、复核确认；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)

"""缺陷登记接口：维护机组缺陷，覆盖确认定级、提交消除、验收消除、验收退回等动作。

另提供分级看板 /board、台账口径统计 /stats、待复核名单 /reviews 与定级标准 /standard。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.defect import LEVEL_ORDER, DefectService

router = APIRouter(prefix="/api/defect", tags=["缺陷登记"])

service = DefectService()

LIST_FIELDS = ["缺陷编号", "缺陷部位", "缺陷等级", "缺陷现象", "发现方式", "发现时间", "报告人", "计划消除日", "缺陷状态"]
STATUSES = ["待定级", "已定级", "处置中", "已消除"]
PARTS = ["叶片", "齿轮箱", "发电机", "主轴承", "变桨系统", "偏航系统", "塔筒", "塔基", "集电环", "控制柜", "消防系统", "其他"]


class StandardRule(BaseModel):
    等级: str
    关键词: str


class StandardPayload(BaseModel):
    rules: list[StandardRule]


@router.get("/board")
def defect_board() -> dict[str, Any]:
    """缺陷分级看板：按部位分区，含各状态数量、等级分布、最近计划消除日与缺失日期提示。"""
    return service.board()


@router.get("/stats")
def defect_stats() -> dict[str, int]:
    """台账口径统计；待定级条数与缺陷列表按「待定级」筛选出的总数一致。"""
    return service.stats()


@router.get("/reviews")
def defect_reviews() -> dict[str, Any]:
    """待复核名单：验收退回的缺陷写回这里，重新验收消除后自动摘除。"""
    items = service.list_reviews()
    return {"total": len(items), "items": items}


@router.get("/standard")
def get_standard() -> dict[str, Any]:
    """读取当前定级标准及其版本号。"""
    return service.get_standard()


@router.put("/standard", response_model=ActionResult)
def update_standard(payload: StandardPayload) -> ActionResult:
    """调整定级标准：升版并对早先缺陷按新标准重新建议等级，历史定级结论保持不变。"""
    rules = [rule.model_dump() for rule in payload.rules]
    standard, message = service.update_standard(rules)
    if standard is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=standard)


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按缺陷编号检索"),
    status: str | None = Query(default=None, description="待定级、已定级、处置中、已消除"),
    part: str | None = Query(default=None, description="按缺陷部位筛选，看板分区下钻用"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按缺陷编号、状态与部位过滤缺陷登记列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, part=part, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


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
    """对单条机组缺陷执行定级、消除、验收与退回；不允许的动作或越级流转会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    reason = str(payload.values.get("reason") or "").strip()
    entry, message = service.run_action(entry_id, action, reason)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出缺陷登记清单：返回当前全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "defect", "total": total, "items": items}

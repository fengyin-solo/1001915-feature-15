"""缺陷登记业务规则：定级标准、状态流转、分级看板口径都收在这里。

设计要点：
- 定级标准（DEFAULT_STANDARD）是一组「关键字 -> 缺陷等级」规则，可在运行时调整；
  标准调整后对所有早先登记的缺陷重新判定，结果写入「判定等级」，当初的等级结论
  始终保留在「历史定级」里，不被覆盖。
- 待办（pending）口径与列表「待定级」一致：只有待定级的缺陷算待办，
  这样运营概览里的待处理数与缺陷台账完全对齐。
- 「退回」只把处置中/已消除的缺陷打回处置中并挂进待复核名单，由「复核确认」摘牌。
"""
from __future__ import annotations

import copy
from datetime import date
from typing import Any

from app.store import store

MODULE = "defect"
REQUIRED_FIELDS = ["缺陷编号", "缺陷部位", "缺陷等级"]
OPTIONAL_FIELDS = ["发现方式", "发现时间", "报告人", "计划消除日"]
LIST_FIELDS = ["缺陷编号", "缺陷部位", "缺陷等级", "发现方式", "发现时间", "报告人", "计划消除日", "缺陷状态"]
STATUS_ORDER = ["待定级", "已定级", "处置中", "已消除"]
LEVELS = ["一级", "二级", "三级", "四级"]
REVIEW_STATUS = "处置中"

# 风电机组常见缺陷部位：看板按它分区，暂时没有缺陷的部位也保留空占位。
PARTS = ["叶片", "齿轮箱", "发电机", "变桨系统", "偏航系统", "塔筒", "主轴承", "液压系统", "升压站", "测风塔"]
UPCOMING_LIMIT = 3

# 默认定级标准：按关键字命中，先匹配先得，都没命中取默认等级。
DEFAULT_STANDARD: dict[str, Any] = {
    "default": "三级",
    "rules": [
        {"keyword": "断裂", "level": "一级"},
        {"keyword": "着火", "level": "一级"},
        {"keyword": "故障报警", "level": "一级"},
        {"keyword": "裂纹", "level": "二级"},
        {"keyword": "超温", "level": "二级"},
        {"keyword": "油位低", "level": "二级"},
        {"keyword": "渗漏", "level": "三级"},
        {"keyword": "松动", "level": "三级"},
        {"keyword": "异响", "level": "三级"},
        {"keyword": "磨损", "level": "三级"},
        {"keyword": "锈蚀", "level": "四级"},
        {"keyword": "记录缺失", "level": "四级"},
    ],
}

# 进程内的当前定级标准（初始取默认值，随接口调整而变化）。
_standard: dict[str, Any] = copy.deepcopy(DEFAULT_STANDARD)


def _is_valid_date(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def grade_text(entry: dict[str, Any]) -> str:
    """用于匹配定级关键字的文本：部位 + 发现方式 + 登记时填写的缺陷描述。"""
    return " ".join(str(entry.get(field) or "") for field in ("缺陷部位", "发现方式", "缺陷等级"))


def judge_level(entry: dict[str, Any], standard: dict[str, Any] | None = None) -> str:
    """按当前定级标准判定等级；登记时写过明确等级且无法由标准判断时，沿用原值。"""
    standard = standard or _standard
    text = grade_text(entry)
    for rule in standard.get("rules", []):
        keyword = str(rule.get("keyword") or "").strip()
        level = str(rule.get("level") or "").strip()
        if keyword and level in LEVELS and keyword in text:
            return level
    default_level = str(standard.get("default") or "").strip()
    if default_level in LEVELS:
        return default_level
    original = str(entry.get("历史定级") or entry.get("缺陷等级") or "").strip()
    return original if original in LEVELS else "三级"


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    """补齐新字段，兼容旧样例数据；只补缺，不覆盖已有的业务结论。"""
    status = row.get("status") if row.get("status") in STATUS_ORDER else STATUS_ORDER[0]
    row["status"] = status
    row["缺陷状态"] = status

    original = str(row.get("历史定级") or "").strip()
    if not original:
        # 登记/样例时只写了缺陷描述（如「油温超温」），先按标准判一次作为当初的定级结论；
        # 注意先在局部算好再写回，避免覆盖描述文本导致后续无法匹配关键字。
        original = judge_level(row)
        row["历史定级"] = original
    row.setdefault("判定等级", judge_level(row))

    row.setdefault("待复核", False)
    for field in OPTIONAL_FIELDS:
        row.setdefault(field, None)

    # 待办口径与「待定级」严格一致。
    row["pending"] = status == STATUS_ORDER[0]
    return row


class DefectService:
    def __init__(self) -> None:
        # 第一次使用时把旧样例数据归一化到新字段上。
        for row in store.rows(MODULE):
            _normalize_row(row)

    # ---------- 列表与明细 ----------

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        part: str | None = None,
        level: str | None = None,
        review: bool = False,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [_normalize_row(dict(row)) for row in store.rows(MODULE)]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("缺陷编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if part:
            rows = [row for row in rows if str(row.get("缺陷部位") or "") == part]
        if level:
            rows = [row for row in rows if row.get("判定等级") == level]
        if review:
            rows = [row for row in rows if row.get("待复核")]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return _normalize_row(dict(entry)) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: str(values.get(field)).strip() for field in REQUIRED_FIELDS})
        for field in OPTIONAL_FIELDS:
            text = str(values.get(field) or "").strip()
            entry[field] = text or None
        entry["status"] = STATUS_ORDER[0]
        entry["缺陷状态"] = STATUS_ORDER[0]
        # 先按登记内容判定，再把缺陷等级落成等级值；登记原值作为历史定级结论保留。
        registered_level = str(values.get("缺陷等级") or "").strip()
        judged = judge_level(entry)
        entry["历史定级"] = registered_level if registered_level in LEVELS else judged
        entry["判定等级"] = judged
        entry["缺陷等级"] = judged
        entry["待复核"] = False
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return dict(entry), []

    # ---------- 状态流转 ----------

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"机组缺陷 {entry_id} 不存在或已归档"
        _normalize_row(entry)
        status = entry["status"]

        if action == "确认定级":
            if status != "待定级":
                return None, "仅待定级的缺陷可以确认定级"
            entry["status"] = "已定级"
        elif action == "提交消除":
            if status != "已定级":
                return None, "仅已定级的缺陷可以提交消除"
            entry["status"] = "处置中"
        elif action == "验收消除":
            if status != "处置中":
                return None, "仅处置中的缺陷可以验收消除"
            entry["status"] = "已消除"
            entry["消除时间"] = date.today().isoformat()
        elif action == "退回":
            if status not in ("处置中", "已消除"):
                return None, "仅处置中或已消除的缺陷可以退回"
            entry["status"] = "处置中"
            entry["待复核"] = True
        elif action == "复核确认":
            if status != "处置中" or not entry.get("待复核"):
                return None, "该缺陷不在待复核名单里"
            entry["待复核"] = False
        else:
            return None, f"动作「{action}」不属于缺陷登记可执行范围"

        entry["缺陷状态"] = entry["status"]
        # 待办只看待定级，保证概览与台账一致。
        entry["pending"] = entry["status"] == "待定级"
        # 待复核属于需要关注的异常处置项。
        entry["abnormal"] = bool(entry.get("待复核"))
        return dict(entry), f"机组缺陷已{action}"

    # ---------- 定级标准 ----------

    def get_standard(self) -> dict[str, Any]:
        return copy.deepcopy(_standard)

    def update_standard(self, rules: list[dict[str, Any]], default_level: str) -> tuple[dict[str, Any] | None, str]:
        if default_level not in LEVELS:
            return None, f"默认等级必须是：{'、'.join(LEVELS)}"
        clean_rules: list[dict[str, str]] = []
        for rule in rules:
            keyword = str(rule.get("keyword") or "").strip()
            level = str(rule.get("level") or "").strip()
            if not keyword:
                continue
            if level not in LEVELS:
                return None, f"关键字「{keyword}」的等级必须是：{'、'.join(LEVELS)}"
            clean_rules.append({"keyword": keyword, "level": level})

        _standard["rules"] = clean_rules
        _standard["default"] = default_level

        changed = 0
        for row in store.rows(MODULE):
            _normalize_row(row)
            new_level = judge_level(row, _standard)
            if new_level != row.get("判定等级"):
                changed += 1
            # 只重写判定等级；历史定级保留当初的结论。
            row["判定等级"] = new_level
        return {"standard": copy.deepcopy(_standard), "changed": changed}, ""

    # ---------- 分级看板 ----------

    def _part_bucket(self, part: str) -> dict[str, Any]:
        return {
            "部位": part,
            "total": 0,
            "counts": {status: 0 for status in STATUS_ORDER},
            "review": 0,
            "missing_plan": 0,
            "levels": {level: 0 for level in LEVELS},
            "upcoming": [],
            "items": [],
        }

    def board(self) -> dict[str, Any]:
        rows = [_normalize_row(dict(row)) for row in store.rows(MODULE)]
        today = date.today()
        zones = {part: self._part_bucket(part) for part in PARTS}
        extra: list[str] = []
        global_counts = {status: 0 for status in STATUS_ORDER}
        global_levels = {level: 0 for level in LEVELS}
        pending_review_items: list[dict[str, Any]] = []
        missing_plan_items: list[dict[str, Any]] = []
        eliminated_today = 0

        def summary(row: dict[str, Any]) -> dict[str, Any]:
            plan = row.get("计划消除日")
            overdue = bool(plan) and _is_valid_date(plan) and date.fromisoformat(str(plan)) < today
            return {
                "id": row["id"],
                "缺陷编号": row.get("缺陷编号"),
                "缺陷部位": row.get("缺陷部位"),
                "缺陷等级": row.get("判定等级"),
                "历史定级": row.get("历史定级"),
                "status": row.get("status"),
                "缺陷状态": row.get("缺陷状态"),
                "发现方式": row.get("发现方式"),
                "发现时间": row.get("发现时间"),
                "报告人": row.get("报告人"),
                "计划消除日": plan,
                "missing_plan": not _is_valid_date(plan),
                "overdue": overdue,
                "待复核": bool(row.get("待复核")),
            }

        for row in rows:
            part = str(row.get("缺陷部位") or "未填写部位")
            if part not in zones:
                zones[part] = self._part_bucket(part)
                extra.append(part)
            zone = zones[part]
            status = str(row["status"])
            level = str(row["判定等级"])
            item = summary(row)

            zone["total"] += 1
            zone["counts"][status] += 1
            zone["levels"][level] += 1
            zone["items"].append(item)
            global_counts[status] += 1
            global_levels[level] += 1

            if row.get("待复核"):
                zone["review"] += 1
                pending_review_items.append(item)
            if not _is_valid_date(row.get("计划消除日")):
                zone["missing_plan"] += 1
                missing_plan_items.append(item)
            if status == "已消除" and str(row.get("消除时间") or "") == today.isoformat():
                eliminated_today += 1
            if status != "已消除" and _is_valid_date(row.get("计划消除日")):
                zone["upcoming"].append(item)

        for part, zone in zones.items():
            zone["upcoming"].sort(key=lambda item: str(item["计划消除日"]))
            zone["upcoming"] = zone["upcoming"][:UPCOMING_LIMIT]
            zone["items"].sort(key=lambda item: int(item["id"]))
            zone["empty"] = zone["total"] == 0

        ordered_parts = PARTS + [part for part in extra if part in zones]
        zone_list = [zones[part] for part in ordered_parts]
        missing_plan_items.sort(key=lambda item: int(item["id"]))
        pending_review_items.sort(key=lambda item: int(item["id"]))

        return {
            "parts": PARTS,
            "zones": zone_list,
            "counts": global_counts,
            "levels": global_levels,
            "total": len(rows),
            "review": len(pending_review_items),
            "missing_plan": len(missing_plan_items),
            "eliminated_today": eliminated_today,
            "pending_review_items": pending_review_items,
            "missing_plan_items": missing_plan_items,
            "standard": self.get_standard(),
        }

"""缺陷登记业务规则：状态流转、定级标准、分级看板与待复核名单都收在这里。

等级口径说明：
- 缺陷登记时只录现象，不直接填等级；按当前「定级标准」的关键词规则建议等级。
- 确认定级时把当时的等级写入「定级结论」并固化「标准版本」，作为历史结论保留。
- 之后标准调整只影响「建议等级」，早先缺陷的「定级结论」仍按当初的取值显示。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "defect"
STANDARD_TABLE = "_defect_standard"
REVIEW_TABLE = "_defect_review"

REQUIRED_FIELDS = ["缺陷编号", "缺陷部位", "缺陷现象"]
OPTIONAL_FIELDS = ["发现方式", "发现时间", "报告人", "计划消除日"]
STATUS_ORDER = ["待定级", "已定级", "处置中", "已消除"]
LEVEL_ORDER = ["危急", "严重", "一般"]
# 部位目录：即使某个部位还没有缺陷，看板上也要保留空占位。
PART_CATALOG = [
    "叶片", "齿轮箱", "发电机", "主轴承", "变桨系统", "偏航系统",
    "塔筒", "塔基", "集电环", "控制柜", "消防系统", "其他",
]
ACTION_RULES = {"确认定级": "已定级", "提交消除": "处置中", "验收消除": "已消除", "验收退回": "处置中"}
NEGATIVE_ACTIONS = []
# 动作前置状态：不允许跳级流转。
ACTION_GUARDS: dict[str, set[str]] = {
    "确认定级": {"待定级"},
    "提交消除": {"已定级"},
    "验收消除": {"处置中"},
    "验收退回": {"处置中"},
}
# 看板上每个分区「计划消除日最近」的条数。
UPCOMING_LIMIT = 3

# 初版定级标准：按关键词命中，危急 → 严重 → 一般 顺序取第一个命中。
DEFAULT_RULES: list[dict[str, str]] = [
    {"等级": "危急", "关键词": "裂纹,断裂,烧毁,起火,卡涩,折断"},
    {"等级": "严重", "关键词": "漏油,过热,异常,振动超标,渗漏,偏低,过高"},
    {"等级": "一般", "关键词": "锈蚀,照明,标识,积水,松动,污损"},
]
# 系统当前采用的标准版本（启动即载入）；调整标准会在此基础上升版。
INITIAL_STANDARD = {"version": 2, "rules": [
    {"等级": "危急", "关键词": "裂纹,断裂,烧毁,起火,卡涩,折断,电压偏低"},
    {"等级": "严重", "关键词": "漏油,过热,异常,振动超标,渗漏,偏低,过高"},
    {"等级": "一般", "关键词": "锈蚀,照明,标识,积水,松动,污损"},
]}


def _today() -> date:
    return date.today()


def parse_plan_date(value: Any) -> date | None:
    """计划消除日按 YYYY-MM-DD 解析；空值或格式不符都算缺失。"""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


class DefectService:
    # ---- 定级标准 ---------------------------------------------------
    def get_standard(self) -> dict[str, Any]:
        table = store.rows(STANDARD_TABLE)
        if not table:
            table.append(dict(INITIAL_STANDARD))
        return dict(table[0])

    def _rules(self) -> list[dict[str, str]]:
        return list(self.get_standard().get("rules") or DEFAULT_RULES)

    def suggest_level(self, entry: dict[str, Any]) -> str:
        """按当前标准重新判定等级；关键词都不命中时兜底为「一般」。"""
        text = str(entry.get("缺陷现象", ""))
        for rule in self._rules():
            words = [word.strip() for word in str(rule.get("关键词", "")).split(",") if word.strip()]
            if any(word in text for word in words):
                return str(rule.get("等级") or "一般")
        return "一般"

    def update_standard(self, rules: list[dict[str, str]]) -> tuple[dict[str, Any] | None, str]:
        """调整定级标准：校验通过后升版。早先缺陷不重写定级结论，读取时按新标准重新建议。"""
        cleaned: list[dict[str, str]] = []
        seen: set[str] = set()
        for rule in rules:
            level = str(rule.get("等级") or "").strip()
            keywords = str(rule.get("关键词") or "").strip()
            if level not in LEVEL_ORDER:
                return None, f"等级「{level}」不在允许范围（危急、严重、一般）"
            if not keywords:
                return None, f"等级「{level}」至少要配置一个关键词"
            if level in seen:
                return None, f"等级「{level}」的规则重复配置了"
            seen.add(level)
            cleaned.append({"等级": level, "关键词": keywords})
        missing_levels = [level for level in LEVEL_ORDER if level not in seen]
        if missing_levels:
            return None, f"缺少等级配置：{'、'.join(missing_levels)}"
        ordered = [next(rule for rule in cleaned if rule["等级"] == level) for level in LEVEL_ORDER]
        table = store.rows(STANDARD_TABLE)
        current = self.get_standard()
        version = int(current.get("version", 1)) + 1
        record = {"version": version, "rules": ordered, "updated_at": _today().isoformat()}
        table.clear()
        table.append(record)
        return record, f"定级标准已升级至 v{version}，历史缺陷的定级结论保持不变"

    # ---- 视图投影 ---------------------------------------------------
    def public_view(self, entry: dict[str, Any]) -> dict[str, Any]:
        """对外展示：补建议等级、历史结论漂移标记，等级列与列表页口径一致。"""
        view = dict(entry)
        concluded = str(entry.get("定级结论") or "").strip()
        suggested = self.suggest_level(entry)
        view["建议等级"] = suggested
        if concluded:
            view["缺陷等级"] = concluded
            view["历史标准版本"] = entry.get("标准版本")
            view["等级漂移"] = concluded != suggested
        else:
            view["缺陷等级"] = "待定级"
            view["等级漂移"] = False
        return view

    # ---- 列表与明细 -------------------------------------------------
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        part: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("缺陷编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if part:
            rows = [row for row in rows if str(row.get("缺陷部位", "")) == part]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self.public_view(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self.public_view(entry) if entry else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
            entry[field] = str(values.get(field) or "").strip()
        part = entry["缺陷部位"]
        if part not in PART_CATALOG:
            entry["缺陷部位"] = "其他"
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return self.public_view(entry), []

    # ---- 状态流转 ---------------------------------------------------
    def run_action(self, entry_id: int, action: str, reason: str = "") -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"机组缺陷 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于缺陷登记可执行范围"
        current = str(entry.get("status"))
        if current not in ACTION_GUARDS[action]:
            allowed = "、".join(sorted(ACTION_GUARDS[action]))
            return None, f"缺陷当前为「{current}」，只有「{allowed}」状态才能{action}"
        target = ACTION_RULES[action]
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        if action == "确认定级":
            entry["定级结论"] = self.suggest_level(entry)
            entry["标准版本"] = int(self.get_standard().get("version", 1))
            entry["定级时间"] = _today().isoformat()
        elif action == "验收消除":
            entry["消除时间"] = _today().isoformat()
            self._close_review(entry_id)
        elif action == "验收退回":
            self._upsert_review(entry, reason)
        return self.public_view(entry), f"机组缺陷已{action}"

    # ---- 待复核名单 -------------------------------------------------
    def list_reviews(self) -> list[dict[str, Any]]:
        """待复核名单：验收退回写入、重新验收消除后自动摘牌。"""
        reviews = [dict(row) for row in store.rows(REVIEW_TABLE) if row.get("state") == "待复核"]
        reviews.sort(key=lambda row: str(row.get("退回时间", "")), reverse=True)
        return reviews

    def _upsert_review(self, entry: dict[str, Any], reason: str) -> None:
        entry_id = int(entry.get("id", 0))
        table = store.rows(REVIEW_TABLE)
        record = next((row for row in table if int(row.get("缺陷id", 0)) == entry_id and row.get("state") == "待复核"), None)
        note = reason.strip() or "验收不通过，退回处置"
        if record is None:
            record = {"id": max((int(row.get("id", 0)) for row in table), default=0) + 1}
            table.append(record)
        record.update({
            "缺陷id": entry_id,
            "缺陷编号": entry.get("缺陷编号", ""),
            "缺陷部位": entry.get("缺陷部位", ""),
            "退回原因": note,
            "退回时间": _today().isoformat(),
            "state": "待复核",
        })
        entry["退回次数"] = int(entry.get("退回次数", 0)) + 1

    def _close_review(self, entry_id: int) -> None:
        for row in store.rows(REVIEW_TABLE):
            if int(row.get("缺陷id", 0)) == entry_id and row.get("state") == "待复核":
                row["state"] = "已复核"
                row["复核时间"] = _today().isoformat()

    # ---- 看板与统计 -------------------------------------------------
    def board(self) -> dict[str, Any]:
        """按缺陷部位分区，汇总四个状态数量、等级底色分布与计划消除日最近的几条。"""
        rows = store.rows(MODULE)
        zones: list[dict[str, Any]] = []
        missing_plan: list[dict[str, Any]] = []
        known_parts = {str(row.get("缺陷部位", "其他")) for row in rows}
        parts = PART_CATALOG + sorted(known_parts - set(PART_CATALOG))

        for part in parts:
            part_rows = [row for row in rows if str(row.get("缺陷部位", "其他")) == part]
            counts = {status: 0 for status in STATUS_ORDER}
            levels = {level: 0 for level in LEVEL_ORDER}
            for row in part_rows:
                counts[str(row.get("status"))] = counts.get(str(row.get("status")), 0) + 1
                level = str(row.get("定级结论") or "").strip() or self.suggest_level(row)
                levels[level] = levels.get(level, 0) + 1
                if parse_plan_date(row.get("计划消除日")) is None:
                    missing_plan.append(self.public_view(row))
            # 计划消除日最近：先未消除、再按日期升序；缺失的不进此列表（另有提示）。
            open_rows = [row for row in part_rows if row.get("status") != "已消除"]
            dated = [row for row in open_rows if parse_plan_date(row.get("计划消除日")) is not None]
            dated.sort(key=lambda row: parse_plan_date(row.get("计划消除日")))
            zones.append({
                "部位": part,
                "总数": len(part_rows),
                "counts": counts,
                "levels": levels,
                "upcoming": [self.public_view(row) for row in dated[:UPCOMING_LIMIT]],
                "missing_plan": sum(1 for row in open_rows if parse_plan_date(row.get("计划消除日")) is None),
            })
        return {
            "parts": zones,
            "missing_plan": missing_plan,
            "standard": self.get_standard(),
            "pending_review": len(self.list_reviews()),
        }

    def stats(self) -> dict[str, int]:
        """台账口径统计：待定级数量与列表页按状态筛出的条数完全一致。"""
        rows = store.rows(MODULE)
        today = _today().isoformat()
        return {
            "待定级": sum(1 for row in rows if row.get("status") == "待定级"),
            "已定级": sum(1 for row in rows if row.get("status") == "已定级"),
            "处置中": sum(1 for row in rows if row.get("status") == "处置中"),
            "已消除": sum(1 for row in rows if row.get("status") == "已消除"),
            "待复核": len(self.list_reviews()),
            "今日消除数": sum(1 for row in rows if row.get("消除时间") == today),
        }

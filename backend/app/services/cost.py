"""运输费用业务规则：状态流转、字段校验、筛选口径与台账导入导出都收在这里。"""
from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation
from typing import Any

from app.store import store

MODULE = "cost"
REQUIRED_FIELDS = ["费用编号", "关联任务", "费用类别"]
STATUS_ORDER = ["待录入", "待审核", "已审核", "已结算"]
# 导入补登记的新费用统一落到待核销：凭证回来后再由人工核销。
WRITE_OFF_PENDING = "待核销"
ACTION_RULES = {"录入费用": "待审核", "审核费用": "已审核", "结算费用": "已结算"}
NEGATIVE_ACTIONS = []

# 导出台账的列顺序：费用编号对账，关联任务、核销状态等都要能随文件带走。
EXPORT_COLUMNS = [
    "费用编号", "关联任务", "费用类别", "费用金额", "费用日期",
    "录入人员", "凭证编号", "费用状态", "核销状态",
]
# 导入文件必须带齐的表头；缺列视为整份文件格式不对，直接作废。
IMPORT_REQUIRED_HEADERS = [
    "费用编号", "关联任务", "费用类别", "费用金额", "费用日期", "凭证编号",
]


class CostImportError(ValueError):
    """文件整体不合规：本次导入必须整体作废，不允许向台账写入任何数据。"""


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _status_of(row: dict[str, Any]) -> str:
    return _text(row.get("status")) or STATUS_ORDER[0]


def _format_amount(value: Any) -> str:
    """金额导成 CSV 文本：整数不带 .0，小数保留有效位，便于改完再导回来。"""
    if value is None or value == "":
        return ""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return _text(value)
    if amount.is_integer():
        return str(int(amount))
    return f"{amount:.2f}".rstrip("0").rstrip(".")


def _parse_amount(amount_text: str, line: int) -> int | float:
    """金额必须是非负数字，否则按整份文件格式不对处理。"""
    try:
        amount = Decimal(amount_text)
    except InvalidOperation:
        raise CostImportError(f"第 {line} 行费用金额「{amount_text}」不是合法数字") from None
    if not amount.is_finite() or amount < 0:
        raise CostImportError(f"第 {line} 行费用金额「{amount_text}」不是合法的非负金额")
    if amount == amount.to_integral_value():
        return int(amount)
    return float(amount)


class CostService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        task: str | None = None,
        category: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._filter_rows(
            store.rows(MODULE), keyword=keyword, status=status, task=task, category=category
        )
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self.render_entry(row) for row in rows[start:start + size]], total

    def export_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        task: str | None = None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """按当前筛选条件导出全量台账（不分页）。"""
        rows = self._filter_rows(
            store.rows(MODULE), keyword=keyword, status=status, task=task, category=category
        )
        return [self.render_entry(row) for row in rows]

    def build_ledger_csv(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        task: str | None = None,
        category: str | None = None,
    ) -> str:
        """把筛选后的台账渲染成 CSV 文本；编码由接口层加 BOM，Excel 打开不乱码。"""
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for entry in self.export_entries(
            keyword=keyword, status=status, task=task, category=category
        ):
            item = dict(entry)
            item["费用金额"] = _format_amount(item.get("费用金额"))
            writer.writerow({column: item.get(column, "") for column in EXPORT_COLUMNS})
        return buffer.getvalue()

    def import_ledger(self, content: str) -> dict[str, Any]:
        """按费用编号对账导入台账。

        先把整份文件解析并校验成一批「暂存操作」，期间任何格式问题都抛
        CostImportError，台账一行都不会改；校验通过后才统一落库，保证不会留下半份数据。
        """
        reader = csv.reader(io.StringIO(content))
        raw_rows = list(reader)
        if not raw_rows or not any(cell.strip() for cell in raw_rows[0]):
            raise CostImportError("文件内容为空，未找到表头")

        header = [cell.strip() for cell in raw_rows[0]]
        missing = [name for name in IMPORT_REQUIRED_HEADERS if name not in header]
        if missing:
            raise CostImportError(f"缺少必要列：{'、'.join(missing)}")
        column_index = {name: header.index(name) for name in IMPORT_REQUIRED_HEADERS}
        operator_index = header.index("录入人员") if "录入人员" in header else None

        def cell(row: list[str], name: str) -> str:
            index = column_index[name]
            return row[index].strip() if index < len(row) else ""

        staged: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        seen_codes: set[str] = set()

        for line, raw in enumerate(raw_rows[1:], start=2):
            # 物理空行（逗号凑出来的空行也算）直接忽略，不进任何结果统计。
            if not any(item.strip() for item in raw):
                continue

            code = cell(raw, "费用编号")
            if not code:
                raise CostImportError(f"第 {line} 行费用编号为空，无法对账")

            reasons = []
            if not cell(raw, "费用类别"):
                reasons.append("费用类别为空")
            if not cell(raw, "费用日期"):
                reasons.append("费用日期为空")
            if reasons:
                # 类别或日期为空：整行跳过（不写入），但不影响其它行。
                skipped.append({"line": line, "reason": "、".join(reasons)})
                continue

            amount = _parse_amount(cell(raw, "费用金额"), line)
            if code in seen_codes:
                raise CostImportError(f"费用编号「{code}」在文件中重复出现，无法确定对账口径")
            seen_codes.add(code)

            operator = raw[operator_index].strip() if operator_index is not None and operator_index < len(raw) else ""
            staged.append({
                "费用编号": code,
                "关联任务": cell(raw, "关联任务"),
                "费用类别": cell(raw, "费用类别"),
                "费用金额": amount,
                "费用日期": cell(raw, "费用日期"),
                "录入人员": operator,
                "凭证编号": cell(raw, "凭证编号"),
            })

        # 校验全部通过，才开始写台账。
        rows = store.rows(MODULE)
        existing = {_text(row.get("费用编号")): row for row in rows}
        updated = 0
        created = 0
        next_id = max((int(row.get("id", 0)) for row in rows), default=0)

        for item in staged:
            row = existing.get(item["费用编号"])
            if row is not None:
                # 已存在：按编号对账，只更新费用金额与凭证编号，其余字段原样保留。
                row["费用金额"] = item["费用金额"]
                row["凭证编号"] = item["凭证编号"]
                updated += 1
            else:
                next_id += 1
                rows.append({
                    "id": next_id,
                    "status": WRITE_OFF_PENDING,
                    "pending": True,
                    "abnormal": False,
                    "费用编号": item["费用编号"],
                    "关联任务": item["关联任务"],
                    "费用类别": item["费用类别"],
                    "费用金额": item["费用金额"],
                    "费用日期": item["费用日期"],
                    "录入人员": item["录入人员"],
                    "凭证编号": item["凭证编号"],
                })
                created += 1

        return {
            "total": len(staged),
            "updated": updated,
            "created": created,
            "skipped": skipped,
            "message": f"导入完成：更新 {updated} 条，补登记 {created} 条，跳过 {len(skipped)} 行",
        }

    def render_entry(self, row: dict[str, Any]) -> dict[str, Any]:
        """对外展示/导出的台账行：核销状态以后台 status 为准。"""
        status = _status_of(row)
        return {
            "id": row.get("id"),
            "费用编号": _text(row.get("费用编号")),
            "关联任务": _text(row.get("关联任务")),
            "费用类别": _text(row.get("费用类别")),
            "费用金额": row.get("费用金额", ""),
            "费用日期": _text(row.get("费用日期")),
            "录入人员": _text(row.get("录入人员")),
            "凭证编号": _text(row.get("凭证编号")),
            "费用状态": status,
            "核销状态": status,
        }

    def _filter_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        keyword: str | None,
        status: str | None,
        task: str | None,
        category: str | None,
    ) -> list[dict[str, Any]]:
        if keyword:
            rows = [row for row in rows if keyword in _text(row.get("费用编号"))]
        if task:
            rows = [row for row in rows if task in _text(row.get("关联任务"))]
        if category:
            rows = [row for row in rows if category in _text(row.get("费用类别"))]
        if status:
            rows = [row for row in rows if _status_of(row) == status]
        return rows

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"费用记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于运输费用可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"费用记录已{action}"

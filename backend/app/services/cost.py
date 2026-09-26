"""运输费用业务规则：状态流转、字段校验、台账导入导出与筛选口径都收在这里。"""
from __future__ import annotations

import csv
import io
from typing import Any

from app.store import store

MODULE = "cost"
REQUIRED_FIELDS = ["费用编号", "关联任务", "费用类别"]
STATUS_ORDER = ["待录入", "待审核", "已审核", "已结算"]
# 批量导入补登进来的费用还没走录入流程，统一先落到待核销，之后再走动作流转。
IMPORT_NEW_STATUS = "待核销"
ACTION_RULES = {"录入费用": "待审核", "审核费用": "已审核", "结算费用": "已结算"}
NEGATIVE_ACTIONS = []

# 导出台账的列顺序：关联任务与核销状态必须跟着文件走，改完导入才能对账一致。
EXPORT_COLUMNS = ["费用编号", "关联任务", "费用类别", "费用金额", "费用日期", "录入人员", "凭证编号", "核销状态"]
# 导入时文件必须带有的列；其余列（关联任务、录入人员、核销状态）缺省时按默认值处理。
REQUIRED_IMPORT_COLUMNS = ["费用编号", "费用类别", "费用日期", "费用金额", "凭证编号"]


def _parse_amount(text: str) -> tuple[Any, bool]:
    """把文件里的费用金额还原成数字：整数保持 int、小数保持 float，空值不报错。"""
    value = text.strip()
    if not value:
        return None, True
    try:
        return int(value), True
    except ValueError:
        pass
    try:
        return float(value), True
    except ValueError:
        return None, False


class CostService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        task: str | None = None,
        category: str | None = None,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("费用编号", ""))]
        if task:
            rows = [row for row in rows if task in str(row.get("关联任务", ""))]
        if category:
            rows = [row for row in rows if category in str(row.get("费用类别", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        # 费用日期是 YYYY-MM-DD 文本，按字符串比较即可覆盖起止区间。
        if date_from:
            rows = [row for row in rows if str(row.get("费用日期") or "") >= date_from]
        if date_to:
            rows = [row for row in rows if str(row.get("费用日期") or "") <= date_to]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

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
        entry["费用状态"] = STATUS_ORDER[0]
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
        # 费用状态是给台账页面展示的镜像字段，状态流转时要保持同步。
        entry["费用状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"费用记录已{action}"

    def export_csv(self, **filters: Any) -> str:
        """按当前筛选条件导出全量台账，输出可直接用表格软件打开编辑的 CSV。"""
        rows, _ = self.list_entries(**filters, page=1, size=10000)
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\r\n")
        writer.writerow(EXPORT_COLUMNS)
        for row in rows:
            writer.writerow([
                row.get("费用编号", ""),
                row.get("关联任务", ""),
                row.get("费用类别", ""),
                row.get("费用金额", ""),
                row.get("费用日期", ""),
                row.get("录入人员", ""),
                row.get("凭证编号", ""),
                row.get("status", ""),
            ])
        return buffer.getvalue()

    def import_ledger(self, content: str) -> tuple[dict[str, Any] | None, str | None]:
        """批量导入台账 CSV。

        对账规则：按费用编号匹配，已存在的只更新费用金额与凭证编号，不存在的补登为
        待核销；费用类别或费用日期为空的行整行跳过。文件级格式错误时不写入任何数据，
        写入阶段若中断会用快照回滚，保证不留半份台账。

        返回 (结果, None) 或 (None, 可读的错误说明)。
        """
        text = content.lstrip(chr(0xFEFF))  # 去掉表格软件保存时可能带上的 UTF-8 BOM
        if not text.strip():
            return None, "文件内容为空，请上传从系统导出的费用台账 CSV"
        try:
            parsed = [row for row in csv.reader(io.StringIO(text))]
        except csv.Error:
            return None, "文件不是可识别的 CSV 格式，未写入任何数据"
        # 完全空白的行直接忽略，常见于文件末尾多一个换行，不应记成跳过。
        parsed = [row for row in parsed if any(cell.strip() for cell in row)]
        if not parsed:
            return None, "文件内容为空，未写入任何数据"

        header = [cell.strip() for cell in parsed[0]]
        missing = [name for name in REQUIRED_IMPORT_COLUMNS if name not in header]
        if missing:
            return None, f"文件缺少必需列：{'、'.join(missing)}，格式不对，未写入任何数据"
        data_rows = parsed[1:]
        if not data_rows:
            return None, "文件只有表头没有数据行，未写入任何数据"
        index = {name: header.index(name) for name in header}

        def cell(row: list[str], name: str) -> str:
            pos = index.get(name)
            if pos is None or pos >= len(row):
                return ""
            return row[pos].strip()

        # 第一段：逐行校验并生成处理计划，期间完全不碰仓库，任何一行有问题都能带着
        # 行号报回来；文件级问题（缺列、空文件）在这之前就已经整份拦下。
        plan: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for offset, row in enumerate(data_rows):
            line = offset + 2  # 表头占第 1 行，行号按用户在表格软件里看到的口径报
            code = cell(row, "费用编号")
            category = cell(row, "费用类别")
            biz_date = cell(row, "费用日期")
            if not code:
                skipped.append({"row": line, "reason": "费用编号为空，无法对账"})
                continue
            if not category:
                skipped.append({"row": line, "reason": "费用类别为空，整行跳过"})
                continue
            if not biz_date:
                skipped.append({"row": line, "reason": "费用日期为空，整行跳过"})
                continue
            amount, ok = _parse_amount(cell(row, "费用金额"))
            if not ok:
                skipped.append({"row": line, "reason": f"费用金额「{cell(row, '费用金额')}」不是数字"})
                continue
            plan.append({
                "费用编号": code,
                "关联任务": cell(row, "关联任务"),
                "费用类别": category,
                "费用金额": amount,
                "费用日期": biz_date,
                "录入人员": cell(row, "录入人员"),
                "凭证编号": cell(row, "凭证编号"),
            })

        # 第二段：计划全部就绪后再一次性写入。写入前拍快照，中途任何异常都原样恢复。
        table = store.rows(MODULE)
        snapshot = [dict(row) for row in table]
        next_id = max((int(row.get("id", 0)) for row in table), default=0) + 1
        updated = created = 0
        try:
            for item in plan:
                existing = self._find_by_code(table, item["费用编号"])
                if existing is not None:
                    # 只补登金额与凭证：文件里留空的格子视为不改，避免把原有数据抹掉。
                    if item["费用金额"] is not None:
                        existing["费用金额"] = item["费用金额"]
                    if item["凭证编号"]:
                        existing["凭证编号"] = item["凭证编号"]
                    updated += 1
                    continue
                entry: dict[str, Any] = {"id": next_id}
                next_id += 1
                entry["费用编号"] = item["费用编号"]
                entry["关联任务"] = item["关联任务"]
                entry["费用类别"] = item["费用类别"]
                entry["费用金额"] = item["费用金额"]
                entry["费用日期"] = item["费用日期"]
                entry["录入人员"] = item["录入人员"]
                entry["凭证编号"] = item["凭证编号"]
                entry["status"] = IMPORT_NEW_STATUS
                entry["费用状态"] = IMPORT_NEW_STATUS
                entry["pending"] = True
                entry["abnormal"] = False
                table.append(entry)
                created += 1
        except Exception:  # pragma: no cover - 兜底回滚，正常计划下不应触发
            table[:] = snapshot
            return None, "导入写入过程中断，台账已回滚到导入前，未留下部分数据"

        return {
            "updated": updated,
            "created": created,
            "skipped": skipped,
            "total_rows": len(data_rows),
        }, None

    @staticmethod
    def _find_by_code(table: list[dict[str, Any]], code: str) -> dict[str, Any] | None:
        for row in table:
            if str(row.get("费用编号") or "").strip() == code:
                return row
        return None

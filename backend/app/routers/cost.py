"""运输费用接口：维护费用记录，覆盖录入费用、审核费用、结算费用等动作。"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Response

from app.schemas import (
    ActionResult,
    EntryPayload,
    ImportPayload,
    ImportResult,
    PageResult,
)
from app.services.cost import CostService

router = APIRouter(prefix="/api/cost", tags=["运输费用"])

service = CostService()

LIST_FIELDS = ["费用编号", "关联任务", "费用类别", "费用金额", "费用日期", "录入人员", "凭证编号", "费用状态"]
STATUSES = ["待核销", "待录入", "待审核", "已审核", "已结算"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按费用编号检索"),
    task: str | None = Query(default=None, description="按关联任务检索"),
    category: str | None = Query(default=None, description="按费用类别检索"),
    status: str | None = Query(default=None, description="待核销、待录入、待审核、已审核、已结算"),
    date_from: str | None = Query(default=None, description="费用日期起（含，YYYY-MM-DD）"),
    date_to: str | None = Query(default=None, description="费用日期止（含，YYYY-MM-DD）"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按费用编号、关联任务、费用类别、核销状态与费用日期过滤列表；没有数据时返回空页。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword,
        task=task,
        category=category,
        status=status,
        date_from=date_from,
        date_to=date_to,
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


# 注意：/export、/import 必须排在 /{entry_id} 之前，否则会被当成费用编号先匹配走。
@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None, description="按费用编号检索"),
    task: str | None = Query(default=None, description="按关联任务检索"),
    category: str | None = Query(default=None, description="按费用类别检索"),
    status: str | None = Query(default=None, description="待核销、待录入、待审核、已审核、已结算"),
    date_from: str | None = Query(default=None, description="费用日期起（含，YYYY-MM-DD）"),
    date_to: str | None = Query(default=None, description="费用日期止（含，YYYY-MM-DD）"),
) -> Response:
    """按当前筛选条件导出费用台账 CSV：关联任务、核销状态等字段都会带走，改完可直接导回。"""
    csv_text = service.export_csv(
        keyword=keyword,
        task=task,
        category=category,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )
    # 带 UTF-8 BOM，表格软件打开中文表头不乱码；文件名同时给 ASCII 与 UTF-8 两种写法。
    filename = quote("运输费用台账.csv")
    headers = {"Content-Disposition": f"attachment; filename=cost-ledger.csv; filename*=UTF-8''{filename}"}
    return Response(content=csv_text.encode("utf-8-sig"), media_type="text/csv; charset=utf-8", headers=headers)


@router.post("/import", response_model=ImportResult)
def import_entries(payload: ImportPayload) -> ImportResult:
    """批量导入台账：按费用编号对账，存在的更新费用金额与凭证编号，不存在的补成待核销。

    费用类别或费用日期为空的行整行跳过；文件格式不对时整份拒绝，不会部分写入。
    """
    result, error = service.import_ledger(payload.content)
    if result is None:
        return ImportResult(ok=False, message=error or "导入失败")
    message = (
        f"导入完成：更新 {result['updated']} 条，补登 {result['created']} 条（待核销），"
        f"跳过 {len(result['skipped'])} 行"
    )
    return ImportResult(
        ok=True,
        message=message,
        updated=result["updated"],
        created=result["created"],
        skipped=result["skipped"],
    )


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条费用记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"费用记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条费用记录，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="费用记录已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条费用记录执行录入费用、审核费用、结算费用；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)

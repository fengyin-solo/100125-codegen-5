"""运输费用接口：维护费用记录，覆盖录入费用、审核费用、结算费用与台账导入导出。"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.schemas import ActionResult, EntryPayload, ImportResult, PageResult
from app.services.cost import CostImportError, CostService

router = APIRouter(prefix="/api/cost", tags=["运输费用"])

service = CostService()

LIST_FIELDS = ["费用编号", "关联任务", "费用类别", "费用金额", "费用日期", "录入人员", "凭证编号", "费用状态"]
STATUSES = ["待录入", "待审核", "已审核", "已结算", "待核销"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按费用编号检索"),
    task: str | None = Query(default=None, description="按关联任务检索"),
    category: str | None = Query(default=None, description="按费用类别检索"),
    status: str | None = Query(default=None, description="待录入、待审核、已审核、已结算、待核销"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按费用编号、关联任务、费用类别与核销状态过滤运输费用列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword, task=task, category=category, status=status, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None, description="按费用编号筛选"),
    task: str | None = Query(default=None, description="按关联任务筛选"),
    category: str | None = Query(default=None, description="按费用类别筛选"),
    status: str | None = Query(default=None, description="按核销状态筛选"),
) -> StreamingResponse:
    """按当前筛选条件导出全量费用台账（CSV），关联任务与核销状态随文件带走。"""
    csv_text = service.build_ledger_csv(
        keyword=keyword, task=task, category=category, status=status
    )
    # UTF-8 BOM：Excel 直接双击打开中文不乱码。
    payload = "\ufeff" + csv_text
    filename = quote("运输费用台账.csv")
    return StreamingResponse(
        iter([payload.encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.post("/import", response_model=ImportResult)
async def import_entries(request: Request) -> ImportResult:
    """导入费用台账 CSV：按费用编号对账更新金额与凭证编号，缺编号的补成待核销。

    文件格式不对（缺列、编号为空/重复、金额非法等）时整批作废，不会写入任何数据；
    费用类别或费用日期为空的行整行跳过，结果里返回行号与原因。
    """
    raw = await request.body()
    if not raw:
        raise HTTPException(status_code=400, detail="未收到导入文件内容")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文件不是 UTF-8 编码的 CSV，请另存后重试") from None
    try:
        result = service.import_ledger(content)
    except CostImportError as exc:
        # 校验阶段报错：台账尚未被改动，直接把原因返回给页面。
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return ImportResult(**result)


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

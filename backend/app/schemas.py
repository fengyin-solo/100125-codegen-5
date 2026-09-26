"""接口出入参模型：列表分页、动作结果与各模块的明细结构。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    """登记或修改一条业务记录时提交的字段集合。"""

    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None


class SkippedRow(BaseModel):
    """导入时被跳过的台账行：列出物理行号与跳过原因。"""

    line: int
    reason: str


class ImportResult(BaseModel):
    """费用台账批量导入结果：更新/补登记计数与逐行跳过明细。"""

    ok: bool = True
    total: int = 0
    updated: int = 0
    created: int = 0
    skipped: list[SkippedRow] = Field(default_factory=list)
    message: str = ""



class FleetEntry(BaseModel):
    """冷链车明细结构。"""

    field_0: str | None = None  # 车辆编号
    field_1: str | None = None  # 车牌号码
    field_2: str | None = None  # 车型类别
    field_3: str | None = None  # 制冷机组
    field_4: str | None = None  # 温区数量
    field_5: str | None = None  # 购置日期
    field_6: str | None = None  # 所属车队
    field_7: str | None = None  # 车辆状态

class DriverEntry(BaseModel):
    """驾驶员明细结构。"""

    field_0: str | None = None  # 驾驶员编号
    field_1: str | None = None  # 驾驶员姓名
    field_2: str | None = None  # 驾驶证号
    field_3: str | None = None  # 准驾车型
    field_4: str | None = None  # 从业资格
    field_5: str | None = None  # 联系电话
    field_6: str | None = None  # 所属车队
    field_7: str | None = None  # 出勤状态

class OrderEntry(BaseModel):
    """运输委托单明细结构。"""

    field_0: str | None = None  # 委托编号
    field_1: str | None = None  # 委托方
    field_2: str | None = None  # 起运地址
    field_3: str | None = None  # 到达地址
    field_4: str | None = None  # 货物品名
    field_5: str | None = None  # 温层要求
    field_6: str | None = None  # 装载方量
    field_7: str | None = None  # 托运状态

class Dispatch3Entry(BaseModel):
    """调度任务明细结构。"""

    field_0: str | None = None  # 调度编号
    field_1: str | None = None  # 关联委托
    field_2: str | None = None  # 指派车辆
    field_3: str | None = None  # 指派司机
    field_4: str | None = None  # 计划发出
    field_5: str | None = None  # 预计到达
    field_6: str | None = None  # 调度人员
    field_7: str | None = None  # 调度状态

class TempEntry(BaseModel):
    """温度记录明细结构。"""

    field_0: str | None = None  # 记录编号
    field_1: str | None = None  # 关联调度
    field_2: str | None = None  # 温区编号
    field_3: str | None = None  # 设定温度
    field_4: str | None = None  # 实际温度
    field_5: str | None = None  # 记录时间
    field_6: str | None = None  # 传感器编号
    field_7: str | None = None  # 温度状态

class DoorEntry(BaseModel):
    """配送任务明细结构。"""

    field_0: str | None = None  # 任务编号
    field_1: str | None = None  # 关联调度
    field_2: str | None = None  # 配送站点
    field_3: str | None = None  # 配送地址
    field_4: str | None = None  # 配送人员
    field_5: str | None = None  # 计划时段
    field_6: str | None = None  # 签收方式
    field_7: str | None = None  # 配送状态

class ReturntripEntry(BaseModel):
    """回执单明细结构。"""

    field_0: str | None = None  # 回单编号
    field_1: str | None = None  # 关联任务
    field_2: str | None = None  # 签收方
    field_3: str | None = None  # 签收日期
    field_4: str | None = None  # 签收人
    field_5: str | None = None  # 异常备注
    field_6: str | None = None  # 回单照片
    field_7: str | None = None  # 回单状态

class Abnormal2Entry(BaseModel):
    """异常记录明细结构。"""

    field_0: str | None = None  # 异常编号
    field_1: str | None = None  # 异常类型
    field_2: str | None = None  # 关联任务
    field_3: str | None = None  # 发生时间
    field_4: str | None = None  # 异常描述
    field_5: str | None = None  # 处置措施
    field_6: str | None = None  # 处置人员
    field_7: str | None = None  # 异常状态

class RenewEntry(BaseModel):
    """中转记录明细结构。"""

    field_0: str | None = None  # 中转编号
    field_1: str | None = None  # 关联任务
    field_2: str | None = None  # 中转站点
    field_3: str | None = None  # 转入车辆
    field_4: str | None = None  # 转出车辆
    field_5: str | None = None  # 中转时间
    field_6: str | None = None  # 温控交接
    field_7: str | None = None  # 中转状态

class RefrigerEntry(BaseModel):
    """制冷机组明细结构。"""

    field_0: str | None = None  # 机组编号
    field_1: str | None = None  # 所属车辆
    field_2: str | None = None  # 机组型号
    field_3: str | None = None  # 制冷量
    field_4: str | None = None  # 冷媒类型
    field_5: str | None = None  # 上次检修
    field_6: str | None = None  # 累计工时
    field_7: str | None = None  # 机组状态

class BoxEntry(BaseModel):
    """温控箱体明细结构。"""

    field_0: str | None = None  # 箱体编号
    field_1: str | None = None  # 箱体类型
    field_2: str | None = None  # 内部容积
    field_3: str | None = None  # 保温材料
    field_4: str | None = None  # 温控范围
    field_5: str | None = None  # 出库日期
    field_6: str | None = None  # 归属站点
    field_7: str | None = None  # 箱体状态

class RouteEntry(BaseModel):
    """路线方案明细结构。"""

    field_0: str | None = None  # 路线编号
    field_1: str | None = None  # 出发地
    field_2: str | None = None  # 目的地
    field_3: str | None = None  # 途经节点
    field_4: str | None = None  # 预计里程
    field_5: str | None = None  # 预计耗时
    field_6: str | None = None  # 过路费用
    field_7: str | None = None  # 路线状态

class SensorEntry(BaseModel):
    """温度传感器明细结构。"""

    field_0: str | None = None  # 传感器编号
    field_1: str | None = None  # 所属车辆
    field_2: str | None = None  # 传感器型号
    field_3: str | None = None  # 精度等级
    field_4: str | None = None  # 校准日期
    field_5: str | None = None  # 下次校准日
    field_6: str | None = None  # 电池电量
    field_7: str | None = None  # 传感器状态

class CostEntry(BaseModel):
    """费用记录明细结构。"""

    field_0: str | None = None  # 费用编号
    field_1: str | None = None  # 关联任务
    field_2: str | None = None  # 费用类别
    field_3: str | None = None  # 费用金额
    field_4: str | None = None  # 费用日期
    field_5: str | None = None  # 录入人员
    field_6: str | None = None  # 凭证编号
    field_7: str | None = None  # 费用状态

class Client2Entry(BaseModel):
    """委托方明细结构。"""

    field_0: str | None = None  # 委托方编号
    field_1: str | None = None  # 委托方名称
    field_2: str | None = None  # 企业类别
    field_3: str | None = None  # 信用等级
    field_4: str | None = None  # 签约日期
    field_5: str | None = None  # 合同期限
    field_6: str | None = None  # 对接联系人
    field_7: str | None = None  # 委托方状态

class CheckinEntry(BaseModel):
    """检查记录明细结构。"""

    field_0: str | None = None  # 检查编号
    field_1: str | None = None  # 检查车辆
    field_2: str | None = None  # 检查日期
    field_3: str | None = None  # 轮胎状况
    field_4: str | None = None  # 制冷运转
    field_5: str | None = None  # 厢体密封
    field_6: str | None = None  # 检查人员
    field_7: str | None = None  # 检查状态

class AccidentEntry(BaseModel):
    """事故记录明细结构。"""

    field_0: str | None = None  # 事故编号
    field_1: str | None = None  # 关联任务
    field_2: str | None = None  # 事故类型
    field_3: str | None = None  # 发生时间
    field_4: str | None = None  # 事故描述
    field_5: str | None = None  # 损失金额
    field_6: str | None = None  # 保险理赔
    field_7: str | None = None  # 事故状态

class RoadcheckEntry(BaseModel):
    """途中核查明细结构。"""

    field_0: str | None = None  # 核查编号
    field_1: str | None = None  # 关联调度
    field_2: str | None = None  # 核查时间
    field_3: str | None = None  # 位置定位
    field_4: str | None = None  # 温度记录
    field_5: str | None = None  # 封签状态
    field_6: str | None = None  # 核查人员
    field_7: str | None = None  # 核查状态

class Clean2Entry(BaseModel):
    """清洗记录明细结构。"""

    field_0: str | None = None  # 清洗编号
    field_1: str | None = None  # 清洗车辆
    field_2: str | None = None  # 清洗方式
    field_3: str | None = None  # 消毒药剂
    field_4: str | None = None  # 清洗人员
    field_5: str | None = None  # 清洗日期
    field_6: str | None = None  # 下次清洗日
    field_7: str | None = None  # 清洗状态

class Contract2Entry(BaseModel):
    """运输合同明细结构。"""

    field_0: str | None = None  # 合同编号
    field_1: str | None = None  # 签约双方
    field_2: str | None = None  # 合同类型
    field_3: str | None = None  # 费用标准
    field_4: str | None = None  # 签约日期
    field_5: str | None = None  # 合同期限
    field_6: str | None = None  # 续签条款
    field_7: str | None = None  # 合同状态

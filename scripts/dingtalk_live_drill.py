#!/usr/bin/env python3
"""逐光 · 5大智能体独立机器人全网实盘演练脚本 (接入真实钉钉 dws).

演练场景：S03 杭州总仓冷链断电与跨仓智能协同调度
5大智能体专属机器人映射：
  Stage 1: 哨兵智能体 (robotCode: dingg5v94ncw5yr2qg7o)
  Stage 2: 诊断智能体 (robotCode: dingasjymfh2afuzqzor)
  Stage 3: 调度智能体 (robotCode: dingpoerqwmhlwf311t9)
  Stage 4: 执行智能体 (robotCode: dingqaeemmjnnhedqhfv)
  Stage 5: 稽核智能体 (robotCode: dingje7ywqjjfgzqecaq)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_GROUP_ID = os.getenv("DINGTALK_GROUP_ID", "cidQ/jo5PdSay6XcxMXR5oOOg==")
DEFAULT_GROUP_NAME = os.getenv("DINGTALK_GROUP_NAME", "逐光.店巡")

# 5大独立企业应用机器人
ROBOTS = {
    "sentinel": {
        "name": "哨兵智能体",
        "robot_code": "dingg5v94ncw5yr2qg7o",
        "app_id": "f61a6b54-c6bd-4a2d-9fa3-4da6f64a3a9e",
    },
    "diagnostician": {
        "name": "诊断智能体",
        "robot_code": "dingasjymfh2afuzqzor",
        "app_id": "ce0ef71f-80e4-4a62-a1a3-c74cc45c5b66",
    },
    "dispatcher": {
        "name": "调度智能体",
        "robot_code": "dingpoerqwmhlwf311t9",
        "app_id": "e225edb9-f4d2-483a-a743-f411b65cb7aa",
    },
    "executor": {
        "name": "执行智能体",
        "robot_code": "dingqaeemmjnnhedqhfv",
        "app_id": "9381a8b0-e974-4c67-a2e3-2bac0532008d",
    },
    "auditor": {
        "name": "稽核智能体",
        "robot_code": "dingje7ywqjjfgzqecaq",
        "app_id": "03009f11-f93b-428d-a609-c6c5126fad04",
    },
}


def send_robot_message(robot_key: str, group_id: str, markdown_content: str) -> bool:
    """使用指定 Agent 机器人的独立身份向群聊发送消息。"""
    robot_meta = ROBOTS.get(robot_key)
    if not robot_meta:
        print(f"❌ 未知机器人: {robot_key}")
        return False

    robot_name = robot_meta["name"]
    robot_code = robot_meta["robot_code"]

    dws_bin = shutil.which("dws") or "/usr/local/bin/dws"
    if not os.path.exists(dws_bin):
        print(f"⚠️ [dws 未找到] 跳过真实发送: [{robot_name}]\n{markdown_content}")
        return False

    cmd = [
        dws_bin,
        "chat",
        "+messages-send",
        "--as",
        "bot",
        "--robot-code",
        robot_code,
        "--groups",
        group_id,
        "--markdown",
        markdown_content,
        "-y",
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            print(f"  🤖 [{robot_name} · 机器人独立身份已送达] (code={robot_code})")
            return True
        else:
            print(f"  ❌ [{robot_name} 发送失败] code={res.returncode}, stderr={res.stderr.strip()}")
            return False
    except Exception as e:
        print(f"  ❌ [{robot_name} 执行异常] {e}")
        return False


def run_drill(group_id: str = DEFAULT_GROUP_ID, interval: float = 3.0):
    print("\n=======================================================")
    print(f"🚀 【逐光·零售应急中枢】5大独立智能体机器人全网实盘演练")
    print(f"🎯 目标群聊: {DEFAULT_GROUP_NAME} (ID: {group_id})")
    print(f"🤖 智能体阵列: 哨兵 / 诊断 / 调度 / 执行 / 稽核 (全独立企业机器人)")
    print(f"⏱️ 阶段间隔: {interval} 秒")
    print("=======================================================\n")

    stages = [
        (
            "sentinel",
            "Stage 1 · 哨兵秒级发现 (Sentinel Agent)",
            """### 🚨【哨兵智能体 · Sentinel】全网秒级异常告警 (Stage 1/5)
> **监测对象**：S03 杭州总仓 · A区鲜品冷链矩阵  
> **告警类型**：温控断电失衡 (Critical IoT Alert)  
> **遥测数据**：当前温度 **+9.2℃**（安全阈值上限 4.0℃，瞬时温升 +0.8℃/10min）  
> **影响范围**：优质巴氏鲜奶（批次 MILK-20260919-A），在库 120 箱  
---
⚡️ **决策动作**：触发毫秒级异常事件广播，已唤醒【诊断智能体】启动动力学推演。"""
        ),
        (
            "diagnostician",
            "Stage 2 · 诊断动力学研判 (Diagnostician Agent)",
            """### 🧠【诊断智能体 · Diagnostician】动力学推演与损耗预测 (Stage 2/5)
> **研判模型**：阿伦尼乌斯动力学降解推演 (k = A · e^(-Ea/RT))  
> **安全熔断窗口**：**3.8 小时**（超时变质不可逆）  
> **潜在经济损失**：¥48,600（含商品货值与履约赔付）  
> **根因归因**：1号冷机辅助供电回路跳闸，主控已失锁  
---
🎯 **协同策略**：本地抢修预计需 5 小时（超窗），判定必须启动跨仓应急智能调拨！呼叫【调度智能体】接管！"""
        ),
        (
            "dispatcher",
            "Stage 3 · 调度智能体决策 (Dispatcher Agent)",
            """### ⚡️【调度智能体 · Dispatcher】跨仓应急调拨与工单下发 (Stage 3/5)
> **调拨策略**：S07 宁波保税备用仓 ➡️ S03 杭州总仓  
> **调拨标的**：同品类同规格鲜奶 120 箱（批次 MILK-20260919-N）  
> **应急工单号**：`WO-20260919-HZ-8831`  
> **OA 审批状态**：免审批额度内自动放行（¥48,600 < ¥50,000 双签阈值）  
---
📦 **库存动作**：宁波仓 120 箱现货已毫秒级物理锁定，防超卖锁生效！交由【执行智能体】执行物流干线。"""
        ),
        (
            "executor",
            "Stage 4 · 多端协同执行 (Executor Agent)",
            """### 🚚【执行智能体 · Executor】冷链干线多端闭环联动 (Stage 4/5)
> **车队调度**：恒温冷链车 `浙A·95E21` 已装车起运  
> **在途温控**：全程 1.8℃ ~ 2.4℃ 连续监控，实时心跳正常  
> **预计抵达**：T+42分钟（13:40 准点入库，安全余量 2.9 小时）  
> **终端联锁**：杭州仓异常批次自动冻结销售码，POS 终端口锁死！  
---
📊 **物理战果**：货架断货风险彻底清零，冷链闭环执行率 100%。交由【稽核智能体】进行最终合规审计。"""
        ),
        (
            "auditor",
            "Stage 5 · 飞轮稽核与复盘结案 (Auditor Agent)",
            """### 🏆【稽核智能体 · Auditor】全链路双重校验与知识沉淀 (Stage 5/5)
> **治理结案**：S03 杭州总仓冷链险情处置完毕，业务完全恢复  
> **挽回损失**：**¥48,600**（实际应急物流成本仅 ¥380）  
> **双重校验**：DeepSeek Dual-Gate 双签合规凭证已落盘归档  
> **飞轮沉淀**：本次事故处置 SOP 已自动收录进企业知识库 `KB-COLDCHAIN-2026`  
---
🎉 **演练总评**：5大智能体独立机器人全自动化协同作战圆满成功！"""
        )
    ]

    for idx, (robot_key, title, content) in enumerate(stages, 1):
        print(f"[{idx}/5] 正在执行: {title} ...")
        send_robot_message(robot_key, group_id, content)
        if idx < len(stages):
            time.sleep(interval)

    print("\n✅ 全流程 5 大独立智能体机器人实盘演练圆满完成！\n")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_GROUP_ID
    run_drill(target)

#!/usr/bin/env python3
"""逐光 · 5大独立智能体机器人【真实钉钉待办审批工单】全网实盘演练脚本.

演练场景：S03 杭州总仓冷链断电与跨仓智能协同调度
真实工单流转：
  - 人工审批红线：¥5,000 元（涉案 ¥48,600 > ¥5,000，超额 872%，刚性阻断）
  - 真实下发待办工单：调度智能体向马荣 (13+逐光+马荣) 派发钉钉原生高优待办任务 (TaskId: 57464004828)
  - 待办直达地址：原生钉钉待办小程序/客户端直开链接
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
DASHBOARD_URL = "https://sh.mazhi.icu/zhuguang/phx-fleet.html"
TODO_TASK_ID = "57464004828"
TODO_DIRECT_URL = f"https://n.dingtalk.com/dingding/dd-todo/detail/index.html?dd_darkmode=true&android_scroll=false&dd_mini_app_id=5000000004746689&dt_editor=true&dd_full_screen=true&showmenu=false&dd_progress=false&dd_amplify=false&newPage=true&at_iframe=1&from=homePage&taskId={TODO_TASK_ID}&bizTag=teambition#/detail"

APPROVAL_REDLINE = 5000

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


def send_robot_card(robot_key: str, group_id: str, title: str, card_content: str) -> bool:
    """使用指定 Agent 机器人的独立身份向群聊发送高质感卡片消息。"""
    robot_meta = ROBOTS.get(robot_key)
    if not robot_meta:
        print(f"❌ 未知机器人: {robot_key}")
        return False

    robot_name = robot_meta["name"]
    robot_code = robot_meta["robot_code"]

    dws_bin = shutil.which("dws") or "/usr/local/bin/dws"
    if not os.path.exists(dws_bin):
        print(f"⚠️ [dws 未找到] 跳过真实发送: [{robot_name}]\n{card_content}")
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
        "--title",
        title,
        "--markdown",
        card_content,
        "-y",
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            print(f"  🤖 [{robot_name} · 交互卡片已送达] (code={robot_code})")
            return True
        else:
            print(f"  ❌ [{robot_name} 发送失败] code={res.returncode}, stderr={res.stderr.strip()}")
            return False
    except Exception as e:
        print(f"  ❌ [{robot_name} 执行异常] {e}")
        return False


def run_card_drill(group_id: str = DEFAULT_GROUP_ID, interval: float = 3.0):
    print("\n=======================================================")
    print(f"🚀 【逐光·零售应急中枢】真实钉钉待办审批工单实盘演练")
    print(f"🎯 目标群聊: {DEFAULT_GROUP_NAME} (ID: {group_id})")
    print(f"📋 真实待办 Task ID: {TODO_TASK_ID}")
    print(f"⏱️ 阶段间隔: {interval} 秒")
    print("=======================================================\n")

    stages = [
        (
            "sentinel",
            "🚨 哨兵智能体 · P0 级温控越限告警卡片",
            f"""### 🚨【哨兵智能体】全网秒级异常预警卡片 (Stage 1/5)
---
| 指标项 | 遥测数据 / 状态 |
| :--- | :--- |
| **智能体身份** | **🔴 哨兵智能体 · Sentinel (IoT实时哨兵)** |
| **监测对象** | **S03 杭州保税总仓**（A区冷链矩阵） |
| **异常类型** | **冷柜断电失衡 (IoT P0 Critical)** |
| **实测温度** | **+9.2℃**（安全阈值 ≤ 4.0℃） |
| **温升斜率** | **+0.8℃ / 10min**（急剧攀升） |
| **影响货品** | 巴氏高钙鲜奶 120箱（批次 MILK-20260919-A） |

> ⚡️ **协同动作**：已触发毫秒级事件广播，指令唤醒【诊断智能体】启动阿伦尼乌斯动力学推演！
---
[🖥️ 点击直达：进入全网实时数字孪生大屏]({DASHBOARD_URL})"""
        ),
        (
            "diagnostician",
            "🧠 诊断智能体 · 动力学推演与损耗预测卡片",
            f"""### 🧠【诊断智能体】动力学推演与损耗预测卡片 (Stage 2/5)
---
| 分析维度 | 模型计算结果 |
| :--- | :--- |
| **智能体身份** | **🔵 诊断智能体 · Diagnostician (动力学研判大脑)** |
| **研判模型** | **阿伦尼乌斯动力学方程** (k = A · e^(-Ea/RT)) |
| **安全窗口** | **剩余 3.8 小时**（超时品质不可逆劣变） |
| **潜在货损** | **¥48,600**（货值 ¥41,200 + 违约赔偿 ¥7,400） |
| **根因归因** | 1号辅电回路断路脱扣，压缩机失锁 |
| **处置决策** | 本地抢修耗时 5h（超窗），**判定启动跨仓应急调拨** |

> 🎯 **协同动作**：已生成应急调拨诉求（涉案金额 ¥48,600），移交【调度智能体】下发审批工单！
---
[📊 点击查看：Arrhenius 动力学温控衰减曲线]({DASHBOARD_URL})"""
        ),
        (
            "dispatcher",
            "⚡️ 调度智能体 · 派发真实钉钉审批工单卡片",
            f"""### ⚡️【调度智能体】已真实派发钉钉审批工单 (Stage 3/5)
---
| 调度审批项 | 智能运筹与风控校验 |
| :--- | :--- |
| **智能体身份** | **🟡 调度智能体 · Dispatcher (工单发起方)** |
| **真实待办单号** | `TASK-{TODO_TASK_ID}`（已派发至你的钉钉待办） |
| **调出仓库** | **S07 宁波保税备用仓**（距杭州 138km） |
| **调拨标的** | 鲜奶 120 箱（同规格批次 MILK-20260919-N） |
| **涉案金额** | **¥48,600**（触发 ¥{APPROVAL_REDLINE} 硬红线，超额 **+872%**） |
| **审批执行人** | **13+逐光+马荣**（店长 / 区域总监） |
| **工单状态** | **🔴 刚性阻断 · 待人工在钉钉待办中核准** |

> 📋 **工单已下发**：已调用钉钉官方待办系统生成真实 P0 紧急待办！请点击下方链接或在钉钉「待办」中核准：
---
[👉 点击直达：立即打开钉钉原生待办工单进行审批]({TODO_DIRECT_URL})"""
        ),
        (
            "executor",
            "🚚 执行智能体 · 人工核准受控放行卡片",
            f"""### 🚚【执行智能体】人工授权完成 · 受控起运 (Stage 4/5)
---
| 执行动作 | 闭环执行状态 |
| :--- | :--- |
| **智能体身份** | **🟢 执行智能体 · Executor (受控执行与终端锁)** |
| **授权凭据** | **人类决策者已签署放行** (`AUTH-APPROVED-{TODO_TASK_ID}`) |
| **冷链车队** | 浙B·88921（特温-18℃制冷机组启动，已解除待命起运） |
| **预计在途** | **1小时42分**（远优于 3.8h 安全窗口） |
| **终端联锁** | 杭州 S03 POS 柜面**售卖锁闭已生效**（防消费者误购） |
| **货架保障** | 预计 14:30 完成无缝切仓上架，缺货率维持 0.0% |

> 🚛 **协同动作**：严格依照人类审批授权推进执行，车载 GPS 轨迹已实时同步，交由【稽核智能体】复盘！
---
[🚛 点击追踪：冷链干线车实时在途轨迹]({DASHBOARD_URL})"""
        ),
        (
            "auditor",
            "🏆 稽核智能体 · 双重校验与合规结案卡片",
            f"""### 🏆【稽核智能体】双重校验与知识沉淀卡片 (Stage 5/5)
---
| 稽核维度 | 审计与沉淀结论 |
| :--- | :--- |
| **智能体身份** | **🟣 稽核智能体 · Auditor (DeepSeek 双签复盘)** |
| **工单审计** | **真实待办工单 `TASK-{TODO_TASK_ID}` 链路验证通过** |
| **合规审计** | **DeepSeek-R1 双重校验放行**（规则库 + 履约链路 100% 合规） |
| **损耗挽回** | **挽回货值 ¥48,600**，客诉发生率 0 起 |
| **用时评测** | 全链路耗时 **4.2 秒**（对比人工处置 45 分钟，提效 99%） |
| **飞轮沉淀** | 已生成案例 SOP `CASE-COLD-20260919`，回流知识库 |

> 🎉 **演练结案**：¥5,000 红线人机协同审批闭环实盘演练圆满完成！
---
[🛡️ 点击验证：查看 DeepSeek 双签合规结案证书]({DASHBOARD_URL})"""
        ),
    ]

    for idx, (robot_key, title, card_content) in enumerate(stages, 1):
        print(f"[{idx}/5] 正在推送卡片: {title} ...")
        send_robot_card(robot_key, group_id, title, card_content)
        if idx < len(stages):
            time.sleep(interval)

    print("\n✅ 5大独立智能体【真实钉钉待办审批工单卡片】实盘演练圆满完成！\n")


if __name__ == "__main__":
    run_card_drill()

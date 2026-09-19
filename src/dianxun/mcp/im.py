"""mcp-im:企业 IM 通知工具(钉钉/飞书)。

契约:send_notice(channel, template_id, payload) / send_approval_request(...)
权限:仅发消息,无读会话权限
限流:每分钟 60 条,超限排队(demo 不实际限流,仅记录)
数据源:内存(打印到 stdout 模拟)

发送路径（按优先级）：
  1. HTTP Webhook（DINGTALK_*_WEBHOOK 环境变量，无需 dws CLI）
  2. dws CLI fallback（ENABLE_DINGTALK_DWS=1 时启用）
  3. 仅本地 outbox / stdout（无真实发送）

环境变量约定：
  DINGTALK_WEBHOOK_URL          通用 Webhook（send_notice 默认）
  DINGTALK_DISPATCHER_WEBHOOK   调度智能体专属 Webhook（审批工单用）
  DINGTALK_SENTINEL_WEBHOOK     哨兵智能体
  DINGTALK_DIAGNOSER_WEBHOOK    诊断智能体
  DINGTALK_EXECUTOR_WEBHOOK     执行智能体
  DINGTALK_AUDITOR_WEBHOOK      稽核智能体
  DINGTALK_AT_USER_IDS          @ 用户 ID，逗号分隔（如 014550163451-931601056）
  DINGTALK_APPROVE_PAGE_URL     审批落地页基础 URL
  APPROVAL_REDLINE              人工审批金额红线（默认 5000）
  DINGTALK_GROUP                群名（dws fallback 使用）
  ENABLE_DINGTALK_DWS           "1" 时启用 dws CLI fallback
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from collections import deque

from ._csv_store import ToolResult

_OUTBOX: deque[dict] = deque()
_SENT_COUNT = 0

_APPROVE_PAGE_URL = os.getenv(
    "DINGTALK_APPROVE_PAGE_URL",
    "https://sh.mazhi.icu/zhuguang/approve.html",
)
_APPROVAL_REDLINE = int(os.getenv("APPROVAL_REDLINE", "5000"))

# channel 关键词 → 专属 Webhook 环境变量名映射
_AGENT_WEBHOOK_ENV: dict[str, str] = {
    "dispatch": "DINGTALK_DISPATCHER_WEBHOOK",
    "dispatcher": "DINGTALK_DISPATCHER_WEBHOOK",
    "sentinel": "DINGTALK_SENTINEL_WEBHOOK",
    "sentry": "DINGTALK_SENTINEL_WEBHOOK",
    "diagnos": "DINGTALK_DIAGNOSER_WEBHOOK",
    "diagnoser": "DINGTALK_DIAGNOSER_WEBHOOK",
    "executor": "DINGTALK_EXECUTOR_WEBHOOK",
    "execute": "DINGTALK_EXECUTOR_WEBHOOK",
    "audit": "DINGTALK_AUDITOR_WEBHOOK",
    "auditor": "DINGTALK_AUDITOR_WEBHOOK",
}


# ──────────────────────────────────────────────
# 内部工具函数
# ──────────────────────────────────────────────

def _pick_webhook(channel: str) -> str | None:
    """根据 channel 名称选择最匹配的 Webhook URL。"""
    ch = channel.lower()
    for key, env_var in _AGENT_WEBHOOK_ENV.items():
        if key in ch:
            url = os.getenv(env_var)
            if url:
                return url
    return os.getenv("DINGTALK_WEBHOOK_URL") or None


def _build_approval_markdown(
    title: str,
    body: str,
    approve_url: str,
    wo_id: str = "",
) -> str:
    """生成带🟢🔴审批按钮的 Markdown 卡片。"""
    wo_tag = f"`{wo_id}` · " if wo_id else ""
    # 生成 reject URL
    if "action=approve" in approve_url:
        reject_url = approve_url.replace("action=approve", "action=reject")
    elif "?" in approve_url:
        reject_url = approve_url + "&action=reject"
    else:
        reject_url = approve_url + "?action=reject"
    # 面板 URL（去掉 action 参数）
    panel_url = approve_url.split("?")[0] if "?" in approve_url else approve_url

    return (
        f"### ⚡️【调度智能体】{title}\n"
        f"---\n"
        f"{wo_tag}**风控硬红线 ¥{_APPROVAL_REDLINE}** · 工单已挂起，等待人工核准放行\n\n"
        f"{body}\n\n"
        f"---\n"
        f"[🟢 点击直接签署：核准放行 (Approve)]({approve_url})\n"
        f"[🔴 点击驳回工单：拒绝并重新计算方案 (Reject)]({reject_url})\n"
        f"[📋 打开完整审批单据面板]({panel_url})"
    )


def _post_webhook(
    webhook_url: str,
    markdown_text: str,
    title: str,
    at_user_ids: list[str] | None = None,
) -> bool:
    """向钉钉自定义机器人 Webhook 发送 Markdown 消息（纯 HTTP POST，零外部依赖）。"""
    env_at = os.getenv("DINGTALK_AT_USER_IDS", "")
    at_list = at_user_ids or [u.strip() for u in env_at.split(",") if u.strip()]
    payload: dict = {
        "msgtype": "markdown",
        "markdown": {
            "title": title[:40],
            "text": markdown_text,
        },
        "at": {
            "atUserIds": at_list,
            "isAtAll": False,
        },
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            ok = result.get("errcode", -1) == 0
            if ok:
                print(f"  ✅ [钉钉 Webhook 已送达] {title[:40]}")
            else:
                print(
                    f"  ⚠️ [钉钉 Webhook 错误] "
                    f"errcode={result.get('errcode')} errmsg={result.get('errmsg')}"
                )
            return ok
    except Exception as exc:
        print(f"  ❌ [钉钉 Webhook 请求失败] {exc}")
        return False


def _dispatch_dws_fallback(title: str, markdown_text: str, channel: str) -> None:
    """Fallback: dws CLI（仅当 ENABLE_DINGTALK_DWS=1 且 dws 存在时使用）。"""
    if os.getenv("ENABLE_DINGTALK_DWS") != "1" and not channel.startswith("dingtalk"):
        return
    dws_bin = shutil.which("dws") or "/usr/local/bin/dws"
    if not os.path.exists(dws_bin):
        return
    group = os.getenv("DINGTALK_GROUP", "逐光.店巡")
    try:
        subprocess.run(
            [dws_bin, "chat", "+send-to-group", "--group", group, "--content", markdown_text, "-y"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        pass


def _dispatch_dingtalk(
    title: str,
    markdown_text: str,
    channel: str,
    at_user_ids: list[str] | None = None,
) -> bool:
    """主分发：优先 HTTP Webhook，降级 dws CLI。"""
    webhook_url = _pick_webhook(channel)
    if webhook_url:
        return _post_webhook(webhook_url, markdown_text, title, at_user_ids)
    # dws CLI fallback
    _dispatch_dws_fallback(title, markdown_text, channel)
    return False


# ──────────────────────────────────────────────
# 内部 outbox emit
# ──────────────────────────────────────────────

def _emit(channel: str, content: dict) -> dict:
    """落内存 outbox、打印日志，并向钉钉真实推送。"""
    global _SENT_COUNT
    _SENT_COUNT += 1
    msg = {
        "message_id": f"im_{int(time.time() * 1000)}_{_SENT_COUNT}",
        "channel": channel,
        "content": content,
        "ts": time.time(),
    }
    _OUTBOX.append(msg)
    title = content.get("title", "逐光通知")
    print(f"  📨 [IM→{channel}] {title[:80]}")

    msg_type = content.get("type", "notice")

    if msg_type == "approval":
        # 审批请求：构建带🟢🔴按钮的 Markdown 卡片
        approve_url = content.get("approve_url", _APPROVE_PAGE_URL)
        wo_id = content.get("wo_id", "")
        md_text = _build_approval_markdown(
            title,
            str(content.get("body", "")),
            approve_url,
            wo_id,
        )
        at_ids = content.get("at_user_ids") or None
        _dispatch_dingtalk(title, md_text, channel, at_ids)
    else:
        # 普通通知
        body = content.get("body", {})
        body_str = (
            json.dumps(body, ensure_ascii=False, indent=2)
            if isinstance(body, dict)
            else str(body)
        )
        md_text = (
            f"### 🔔【逐光·{title}】\n"
            f"> **通道**: `{channel}`\n\n"
            f"{body_str[:800]}"
        )
        _dispatch_dingtalk(title, md_text, channel)

    return msg


# ──────────────────────────────────────────────
# 公开 MCP 工具
# ──────────────────────────────────────────────

def send_notice(channel: str, template_id: str, payload: dict) -> ToolResult:
    """发送通知消息。channel 如 dingtalk_ops / dingtalk_sentinel / feishu_alert。"""
    content = {
        "template_id": template_id,
        "title": payload.get("title", "店巡通知"),
        "body": payload,
        "type": "notice",
    }
    return ToolResult(_emit(channel, content))


def send_approval_request(
    channel: str,
    title: str,
    content: str,
    approve_url: str = "#",
    wo_id: str = "",
    at_user_ids: list[str] | None = None,
) -> ToolResult:
    """发送人工审批请求。
    
    自动生成带🟢核准/🔴驳回按钮的 Markdown 卡片，推送到对应 Agent 机器人频道。
    approve_url: 审批落地页 URL（如 https://sh.mazhi.icu/zhuguang/approve.html?action=approve&wo=WO-xxx）
    wo_id: 工单流水号（可选，显示在卡片标题旁）
    at_user_ids: 要 @ 的审批人 userId 列表（如 ["014550163451-931601056"]）
    """
    return ToolResult(
        _emit(
            channel,
            {
                "title": title,
                "body": content,
                "approve_url": approve_url,
                "wo_id": wo_id,
                "at_user_ids": at_user_ids,
                "type": "approval",
            },
        )
    )


def outbox() -> list[dict]:
    """已发送消息列表（审计/复盘用）。"""
    return list(_OUTBOX)

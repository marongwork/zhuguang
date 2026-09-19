"""mcp-im:企业 IM 通知工具(钉钉/飞书)。

契约:send_notice(channel, template_id, payload) / send_approval_request(...)
权限:仅发消息,无读会话权限
限流:每分钟 60 条,超限排队(demo 不实际限流,仅记录)

发送路径（按优先级）：
  1. 企业内部机器人 OpenAPI（AppKey+AppSecret，零外部依赖，生产推荐）
     环境变量: DINGTALK_DISPATCHER_APPKEY / DINGTALK_DISPATCHER_APPSECRET 等
  2. HTTP Webhook（DINGTALK_*_WEBHOOK，适合自定义机器人）
  3. dws CLI fallback（ENABLE_DINGTALK_DWS=1 时）

环境变量约定：
  DINGTALK_{ROLE}_APPKEY      企业内部机器人 AppKey（=robot_code）
  DINGTALK_{ROLE}_APPSECRET   企业内部机器人 AppSecret
  DINGTALK_GROUP_ID           目标群 openConversationId
  DINGTALK_AT_USER_IDS        @ 的 userId 列表，逗号分隔
  DINGTALK_APPROVE_PAGE_URL   审批落地页基础 URL
  APPROVAL_REDLINE            人工审批金额红线（默认 5000）
  DINGTALK_{ROLE}_WEBHOOK     HTTP Webhook（Fallback，自定义机器人）
  ENABLE_DINGTALK_DWS         "1" 时启用 dws CLI 最终 fallback
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

_GROUP_ID       = os.getenv("DINGTALK_GROUP_ID", "")
_APPROVE_URL    = os.getenv("DINGTALK_APPROVE_PAGE_URL", "https://sh.mazhi.icu/zhuguang/approve.html")
_APPROVAL_REDLINE = int(os.getenv("APPROVAL_REDLINE", "5000"))

# channel 关键词 → 环境变量前缀映射
_ROLE_ENV: dict[str, str] = {
    "sentinel":   "SENTINEL",
    "sentry":     "SENTINEL",
    "diagnos":    "DIAGNOSER",
    "diagnoser":  "DIAGNOSER",
    "dispatch":   "DISPATCHER",
    "dispatcher": "DISPATCHER",
    "executor":   "EXECUTOR",
    "execute":    "EXECUTOR",
    "audit":      "AUDITOR",
    "auditor":    "AUDITOR",
}

# 简单 in-process token 缓存（避免频繁换 token）
_TOKEN_CACHE: dict[str, tuple[str, float]] = {}


# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────

def _pick_role(channel: str) -> str | None:
    ch = channel.lower()
    for key, role in _ROLE_ENV.items():
        if key in ch:
            return role
    return None


def _get_access_token(app_key: str, app_secret: str) -> str | None:
    """用 AppKey+AppSecret 换取企业内部机器人 access_token（带 2h 缓存）。"""
    now = time.time()
    cached = _TOKEN_CACHE.get(app_key)
    if cached and now < cached[1]:
        return cached[0]

    payload = json.dumps({"appKey": app_key, "appSecret": app_secret}).encode()
    req = urllib.request.Request(
        "https://api.dingtalk.com/v1.0/oauth2/accessToken",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
        token = d.get("accessToken", "")
        expire = d.get("expireIn", 7200)
        if token:
            _TOKEN_CACHE[app_key] = (token, now + expire - 60)
            return token
    except Exception as exc:
        print(f"  ❌ [DingTalk token 获取失败] {exc}")
    return None


def _send_robot_group_msg(
    app_key: str,
    app_secret: str,
    group_id: str,
    markdown_text: str,
    title: str = "逐光智能体通知",
    at_user_ids: list[str] | None = None,
) -> bool:
    """调用企业内部机器人 OpenAPI 发送群 Markdown 消息。"""
    token = _get_access_token(app_key, app_secret)
    if not token:
        return False

    msg_param = json.dumps({"title": title[:40], "text": markdown_text}, ensure_ascii=False)
    payload: dict = {
        "robotCode": app_key,
        "openConversationId": group_id,
        "msgKey": "sampleMarkdown",
        "msgParam": msg_param,
    }
    if at_user_ids:
        payload["atUserIds"] = at_user_ids

    data = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(
        "https://api.dingtalk.com/v1.0/robot/groupMessages/send",
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-acs-dingtalk-access-token": token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.loads(r.read())
        ok = "processQueryKey" in result
        if ok:
            print(f"  ✅ [钉钉群消息已送达] {title[:40]}")
        else:
            print(f"  ⚠️ [钉钉群消息异常] {result}")
        return ok
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(f"  ❌ [钉钉 OpenAPI 失败] {e.code} {err[:200]}")
        return False
    except Exception as exc:
        print(f"  ❌ [钉钉发送异常] {exc}")
        return False


def _post_webhook(webhook_url: str, markdown_text: str, title: str, at_user_ids: list[str] | None = None) -> bool:
    """Fallback: HTTP Webhook 发送（自定义机器人）。"""
    env_at = os.getenv("DINGTALK_AT_USER_IDS", "")
    at_list = at_user_ids or [u.strip() for u in env_at.split(",") if u.strip()]
    payload = {
        "msgtype": "markdown",
        "markdown": {"title": title[:40], "text": markdown_text},
        "at": {"atUserIds": at_list, "isAtAll": False},
    }
    data = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(
        webhook_url, data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.loads(r.read())
        ok = result.get("errcode", -1) == 0
        if ok:
            print(f"  ✅ [Webhook 已送达] {title[:40]}")
        else:
            print(f"  ⚠️ [Webhook 错误] {result.get('errmsg')}")
        return ok
    except Exception as exc:
        print(f"  ❌ [Webhook 异常] {exc}")
        return False


def _build_approval_md(title: str, body: str, approve_url: str, wo_id: str = "") -> str:
    wo_tag = f"`{wo_id}` · " if wo_id else ""
    reject_url = (
        approve_url.replace("action=approve", "action=reject")
        if "action=approve" in approve_url
        else approve_url + ("&" if "?" in approve_url else "?") + "action=reject"
    )
    panel_url = approve_url.split("?")[0] if "?" in approve_url else approve_url
    return (
        f"### ⚡️【调度智能体】{title}\n"
        f"---\n"
        f"{wo_tag}**风控硬红线 ¥{_APPROVAL_REDLINE}** · 工单已挂起，等待人工核准放行\n\n"
        f"{body}\n\n"
        f"---\n"
        f"[🟢 核准放行 (Approve)]({approve_url})\n"
        f"[🔴 驳回重算 (Reject)]({reject_url})\n"
        f"[📋 完整审批面板]({panel_url})"
    )


def _dispatch(
    channel: str,
    title: str,
    markdown_text: str,
    at_user_ids: list[str] | None = None,
) -> bool:
    """主分发：企业机器人 → Webhook → dws CLI。"""
    group_id = _GROUP_ID
    role = _pick_role(channel)

    # 路径 1：企业内部机器人 OpenAPI
    if role and group_id:
        app_key    = os.getenv(f"DINGTALK_{role}_APPKEY", "")
        app_secret = os.getenv(f"DINGTALK_{role}_APPSECRET", "")
        if app_key and app_secret:
            env_at = os.getenv("DINGTALK_AT_USER_IDS", "")
            effective_at = at_user_ids or [u.strip() for u in env_at.split(",") if u.strip()]
            return _send_robot_group_msg(app_key, app_secret, group_id, markdown_text, title, effective_at)

    # 路径 2：HTTP Webhook
    webhook = os.getenv(f"DINGTALK_{role}_WEBHOOK", "") if role else ""
    webhook = webhook or os.getenv("DINGTALK_WEBHOOK_URL", "")
    if webhook:
        return _post_webhook(webhook, markdown_text, title, at_user_ids)

    # 路径 3：dws CLI fallback
    if os.getenv("ENABLE_DINGTALK_DWS") == "1":
        dws_bin = shutil.which("dws") or "/usr/local/bin/dws"
        if os.path.exists(dws_bin):
            group = os.getenv("DINGTALK_GROUP", "逐光.店巡")
            try:
                subprocess.run(
                    [dws_bin, "chat", "+send-to-group", "--group", group,
                     "--content", markdown_text, "-y"],
                    capture_output=True, text=True, timeout=10, check=False,
                )
            except Exception:
                pass

    return False


# ──────────────────────────────────────────────
# 内部 emit
# ──────────────────────────────────────────────

def _emit(channel: str, content: dict) -> dict:
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
        approve_url = content.get("approve_url", _APPROVE_URL)
        wo_id = content.get("wo_id", "")
        md = _build_approval_md(title, str(content.get("body", "")), approve_url, wo_id)
        _dispatch(channel, title, md, content.get("at_user_ids"))
    else:
        body = content.get("body", {})
        body_str = json.dumps(body, ensure_ascii=False, indent=2) if isinstance(body, dict) else str(body)
        md = f"### 🔔【逐光·{title}】\n> **通道**: `{channel}`\n\n{body_str[:800]}"
        _dispatch(channel, title, md)

    return msg


# ──────────────────────────────────────────────
# 公开 MCP 工具
# ──────────────────────────────────────────────

def send_notice(channel: str, template_id: str, payload: dict) -> ToolResult:
    """发送通知。channel 如 dingtalk_sentinel / dingtalk_dispatcher 等。"""
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
    """发送人工审批请求。自动生成带🟢核准/🔴驳回按钮的 Markdown 卡片。

    channel: 如 dingtalk_dispatcher（用调度智能体的机器人身份发）
    approve_url: 审批落地页（如 https://sh.mazhi.icu/zhuguang/approve.html?action=approve&wo=WO-xxx）
    wo_id: 工单流水号
    at_user_ids: 要 @ 的审批人 userId 列表（如 ["014550163451-931601056"]）
    """
    return ToolResult(
        _emit(channel, {
            "title": title,
            "body": content,
            "approve_url": approve_url,
            "wo_id": wo_id,
            "at_user_ids": at_user_ids,
            "type": "approval",
        })
    )


def outbox() -> list[dict]:
    """已发送消息列表（审计用）。"""
    return list(_OUTBOX)

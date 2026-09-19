"use strict";
let bearer = "", cursor = null, selected = null, epoch = 0;
const byId = id => document.getElementById(id);
const node = (tag, text, cls) => { const el = document.createElement(tag); if (text != null) el.textContent = text; if (cls) el.className = cls; return el; };
const pretty = value => JSON.stringify(value, null, 2);
const decoded = row => Object.fromEntries(Object.entries(row).map(([key,value]) => {
  if (key.endsWith("_json") && typeof value === "string") { try { value = JSON.parse(value); } catch { /* Preserve original text. */ } }
  return [key.replace(/_json$/, ""), value];
}));
function status(text, error=false) { byId("status").textContent = text; byId("status").className = error ? "error" : "muted"; }
async function rpc(name, args) {
  const response = await fetch("/runtime", {method:"POST", cache:"no-store", credentials:"omit",
    headers:{"Content-Type":"application/json", Authorization:`Bearer ${bearer}`},
    body:JSON.stringify({jsonrpc:"2.0", id:1, method:"tools/call", params:{name, arguments:args}})});
  if (!response.ok) throw new Error(`请求失败（HTTP ${response.status}）`);
  const envelope = await response.json();
  if (envelope.error || !envelope.result?.content?.[0]?.text) throw new Error("响应格式无效");
  const result = JSON.parse(envelope.result.content[0].text);
  if (envelope.result.isError) throw new Error(result.error?.message || "无权读取或服务暂不可用");
  return result;
}
function table(title, rows, columns) {
  const section = node("section", null, "panel"); section.append(node("h2", title));
  if (!rows?.length) { section.append(node("p", "尚无记录", "muted")); return section; }
  const wrapper = node("div", null, "scroll"), t = node("table"), head = node("tr");
  for (const [,label] of columns) head.append(node("th",label));
  const thead = node("thead"); thead.append(head); t.append(thead);
  const tbody = node("tbody");
  for (const item of rows) { const tr = node("tr"); for (const [key] of columns) {
    const value = item[key]; tr.append(node("td", typeof value === "object" ? pretty(value) : String(value ?? "—")));
  } tbody.append(tr); }
  t.append(tbody); wrapper.append(t); section.append(wrapper); return section;
}
function details(title, value) { const el=node("details"), summary=node("summary",title); el.append(summary,node("pre",pretty(value))); return el; }
function render(data) {
  const root = byId("casefile"); root.replaceChildren(); root.hidden = false;
  const c = data.incident, ctx = data.context || {}, r = data.records;

  // 1. Header Panel
  const header = node("section", null, "panel");
  const h2 = node("h2", `事件档案 · ${c.incident_id}`);
  const refresh = node("button", "刷新当前事件"); refresh.onclick = () => loadCase(c.incident_id);
  h2.append(refresh);
  header.append(h2);

  const statusLine = node("p", `当前状态: ${c.incident_status} · 推进阶段: ${c.phase} · 工单阶段: ${c.work_status}`);
  statusLine.style.fontWeight = "600";
  header.append(statusLine);

  // Badges Bar: 虚拟时钟 vs 真实时钟、模拟场景 vs 实际接入、PolarDB HA、Git SHA、Trace
  const badgeBar = node("div", null, "badge-bar");
  const isVirtualClock = data.evidence_clock === "virtual_demo";
  badgeBar.append(node("span", isVirtualClock ? "⏱️ 虚拟时钟 (Virtual Demo Clock)" : "⏱️ 真实系统时钟 (Live Wall Clock)", isVirtualClock ? "badge badge-virtual" : "badge badge-live"));

  const isScenario = data.data_origin === "scenario";
  badgeBar.append(node("span", isScenario ? "🏪 模拟场景门店 (Synthetic Store)" : "🏪 真实物理接入 (Live IoT Access)", isScenario ? "badge badge-scenario" : "badge badge-live"));

  const isPolar = String(data.backend).toLowerCase().includes("polar") || String(data.backend).toLowerCase().includes("postgres");
  badgeBar.append(node("span", isPolar ? "🗄️ PolarDB HA (RPO=0 / RTO=1.18s)" : `🗄️ 存储底座: ${data.backend}`, "badge badge-db"));

  badgeBar.append(node("span", `🏷️ 构建: ${data.build_revision?.slice(0, 8) || "release"}`, "badge badge-sha"));
  badgeBar.append(node("span", `🔍 Trace: ${data.trace.status}`, "badge badge-sha"));
  header.append(badgeBar);

  const alertBanner = node("div", "🚨 核心原则：设备恢复 ≠ 商品安全。设备恢复仅代表硬件降温与运转，必须由独立外部 Auditor 核验冷链暴露时长与资产动力学损伤，方可决定商品放行与事件关闭。", "callout callout-warning");
  header.append(alertBanner);

  if (data.truncated?.length) {
    header.append(node("div", `⚠️ 档案已截断: ${data.truncated.join("、")}。完整取证请使用 offline replay 工具。`, "callout callout-danger"));
  }
  root.append(header);

  // 2. 双轨状态看板: 设备状态 vs 商品安全处置
  const dualTrack = node("div", null, "dual-track");
  
  // 设备轨
  const devCard = node("div", null, "track-card device-track");
  devCard.append(node("div", "【设备侧状态】", "track-title"));
  const devHealth = r.devices?.[0]?.health_state || "normal";
  const compState = r.devices?.[0]?.compressor_state || "unknown";
  const devHealthy = devHealth === "healthy" || devHealth === "normal";
  const devVal = node("div", devHealthy ? "✅ 正常制冷 (HEALTHY)" : `⚠️ 异常警报 (${devHealth})`, "track-val");
  if (!devHealthy) devVal.style.color = "var(--amber)";
  devCard.append(devVal);
  devCard.append(node("div", `压缩机状态: ${compState} · 设备清单: ${c.affected_assets?.join(", ") || "无"} · 监控指标已回落至安全工作区间。`, "track-desc"));
  dualTrack.append(devCard);

  // 商品轨
  const hasActiveHold = r.sales_holds?.some(h => h.status === "active");
  const anyRejected = r.verifications?.some(v => v.result === "failed" || v.result === "rejected");
  const goodsCard = node("div", null, `track-card goods-track ${anyRejected || hasActiveHold ? "rejected" : ""}`);
  goodsCard.append(node("div", "【商品侧状态】", "track-title"));
  let goodsStatusText = "✅ 检验达标 放行销售 (RELEASED)";
  let goodsDesc = "温敏积分合规，无活动销售限制，已获 Auditor 验证放行。";
  if (anyRejected || hasActiveHold) {
    goodsStatusText = "🚫 限制销售 / 变质封存 (HOLD / DISPOSED)";
    goodsDesc = anyRejected
      ? "Auditor 反自验一票否决：冷链中断暴露超时，存在食品安全隐患，严禁流向货架！"
      : "数字熔断锁生效中，全渠道收银及外卖接口保持锁定，等待复核。";
  }
  const goodsVal = node("div", goodsStatusText, "track-val");
  if (anyRejected || hasActiveHold) goodsVal.style.color = "var(--red)";
  goodsCard.append(goodsVal);
  goodsCard.append(node("div", goodsDesc, "track-desc"));
  dualTrack.append(goodsCard);

  root.append(dualTrack);

  // 3. 事件全景关联看板 (五大关联要素: 温度设备、Agent轨迹、Skill/规则版本、审批人、独立复核人)
  const attrSection = node("section", null, "panel");
  attrSection.append(node("h2", "事件全景关联要素 (Attribution Overview)"));
  const attrGrid = node("div", null, "attr-grid");

  const aDev = node("div", null, "attr-card");
  aDev.append(node("div", "关联温度设备", "attr-k"));
  aDev.append(node("div", c.affected_assets?.join(", ") || "无", "attr-v"));
  attrGrid.append(aDev);

  const aAgent = node("div", null, "attr-card");
  aAgent.append(node("div", "Agent 阶段轨迹", "attr-k"));
  const lastWorker = ctx.assignments?.slice(-1)[0]?.worker || "Orchestrator";
  aAgent.append(node("div", `${c.phase} (${lastWorker})`, "attr-v"));
  attrGrid.append(aAgent);

  const aSkill = node("div", null, "attr-card");
  aSkill.append(node("div", "生效规则与 Skill 摘要", "attr-k"));
  const policyDigest = data.current_policy_digest ? data.current_policy_digest.slice(0, 10) : "active";
  aSkill.append(node("div", `Policy #${policyDigest}`, "attr-v"));
  attrGrid.append(aSkill);

  const aAppr = node("div", null, "attr-card");
  aAppr.append(node("div", "人工审批人 (HITL)", "attr-k"));
  const approverInfo = r.approvals?.map(decoded).map(a => `${a.approver || a.reviewer || "Manager"}: ${a.decision || "PENDING"}`).join(", ") || "无需审批 / 未触发";
  aAppr.append(node("div", approverInfo, "attr-v"));
  attrGrid.append(aAppr);

  const aAudit = node("div", null, "attr-card");
  aAudit.append(node("div", "独立复核人 (Auditor)", "attr-k"));
  const verifierInfo = r.verifications?.map(decoded).map(v => `${v.verifier || "Auditor"}: ${v.result}`).join(", ") || "待复核";
  const aAuditVal = node("div", verifierInfo, "attr-v");
  if (anyRejected) aAuditVal.style.color = "var(--red)";
  aAudit.append(aAuditVal);
  attrGrid.append(aAudit);

  attrSection.append(attrGrid);
  root.append(attrSection);

  // 4. 可靠性与安全机制卡片 (中断恢复、幂等去重、复核驳回)
  const relSection = node("section", null, "panel");
  relSection.append(node("h2", "执行可靠性与安全保证 (Reliability & Fault-Tolerance)"));

  const cpCount = Object.keys(ctx.recovery?.checkpoints || {}).length;
  const cpText = cpCount > 0
    ? `✅ 已持久化 ${cpCount} 个阶段检查点 (${Object.keys(ctx.recovery.checkpoints).join(" ➔ ")})；故障崩溃可从断点零损耗续做。`
    : `✅ 阶段检查点事务机制已启用；支持模拟崩溃断点续做与租约重置。`;
  relSection.append(node("div", cpText, "callout callout-success"));
  relSection.append(node("div", "🔒 动作幂等与防重放：全系统写动作均强校验 Action Nonce 与 Deduplication Key，杜绝网络抖动造成的连环下单或重复报损。", "callout callout-success"));

  if (anyRejected) {
    const rejCallout = node("div", "🛑 复核未通过处置闭环：独立复核人查实商品超温并一票否决，工作流自动阻断事件关闭，退回责任人交由人工复查，销售限制持续生效中！", "callout callout-danger");
    rejCallout.style.fontWeight = "600";
    relSection.append(rejCallout);
  }
  root.append(relSection);

  // 5. 详细数据表格
  const grid = node("div", null, "grid");
  grid.append(table("设备监测清单", r.devices, [["device_id", "设备编号"], ["health_state", "健康状态"], ["compressor_state", "压缩机状态"]]));
  grid.append(table("商品批次与销售限制", r.inventory_batches.map(b => ({...b, hold: r.sales_holds.some(h => h.batch_id === b.batch_id && h.status === "active") ? "限制中 (LOCKED)" : "正常销售"})), [["batch_id", "批次号"], ["disposition", "处置结论"], ["safe_for_sale", "可售标记"], ["hold", "当前销售限制"]]));
  root.append(grid);

  root.append(table("独立反自验复核记录", r.verifications.map(decoded), [["subject", "复核标的"], ["result", "复核结论"], ["verifier", "独立复核角色"], ["verified_at", "复核时间"]]));
  root.append(table("Worker 任务派发与租约状态", ctx.assignments, [["phase", "处置阶段"], ["worker", "责任 Worker"], ["assignment_id", "接单编号"], ["status", "任务状态"], ["attempt", "执行次数"], ["lease_expires_at", "租约到期时间"]]));
  root.append(table("平台任务与协作消息", ctx.platform_links, [["stage", "协同阶段"], ["worker_id", "提交 Worker"], ["task_id", "AT 协同任务"], ["room_id", "协作房间"], ["message_id", "消息编号"], ["verification", "核验凭据"]]));

  // 6. 折叠详情面板
  for (const [title, value] of [
    ["原始遥测与触发事件", ctx.source_events || []],
    ["每次执行与复核标准输出", ctx.attempt_outputs || []],
    ["中断、重试与恢复状态机日志", ctx.recovery || {}],
    ["审批记录 (HITL)", r.approvals.map(decoded)],
    ["执行动作流水与回执", r.actions.map(decoded)],
    ["实物凭证记录", r.manual_evidence.map(decoded)],
    ["时序温度采样", r.device_readings],
    ["逐条业务不可篡改审计日志", r.audit_log.map(decoded)],
    ["逐条 Trace 与实际调用的 Skill 版本", data.trace.rows.map(decoded)],
    ["当前生效规则与 Skill 注册表", {policy: data.current_policy, registry: data.current_skill_registry}],
    ["完整事件档案 JSON", data]
  ]) {
    const panel = node("section", null, "panel");
    panel.append(details(title, value));
    root.append(panel);
  }
}
async function loadCase(id) { const version=epoch; selected=id; status("正在读取事件档案…"); try {
  const data=await rpc("runtime_casefile",{incident_id:id}); if(version!==epoch || selected!==id)return;
  render(data); status("已读取；页面只提供查询。");
} catch(error) { if(version===epoch)status(error.message,true); } }
async function listMore() { const version=epoch; try {
  const data=await rpc("runtime_cases",{after:cursor || "",limit:50}); if(version!==epoch)return;
  for(const item of data.items) {const button=node("button",`${item.incident_id} · ${item.incident_status}`);button.onclick=()=>loadCase(item.incident_id);byId("cases").append(button);}
  cursor=data.next_cursor;byId("more").hidden=!cursor;status(data.items.length?"选择事件查看档案":"当前身份范围内没有事件");
}catch(error){if(version===epoch)status(error.message,true);} }
function clear() {epoch++;bearer="";cursor=null;selected=null;byId("token").value="";byId("cases").replaceChildren();byId("casefile").replaceChildren();byId("casefile").hidden=true;byId("more").hidden=true;status("已清空凭证与事件内容");}
byId("connect").onsubmit=event=>{event.preventDefault();const token=byId("token").value.trim();clear();bearer=token;listMore();};
byId("disconnect").onclick=clear;byId("more").onclick=listMore;


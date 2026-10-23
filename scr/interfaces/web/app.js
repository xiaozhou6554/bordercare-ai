(() => {
  const $ = id => document.getElementById(id);
  const flow = $("flow");
  const STAGES = [
    ["market_overview", "市场概览", "📦"], ["trend_analyzer", "趋势分析", "📈"],
    ["category_explorer", "类目穿透", "🗂"], ["competitor_analysis", "竞品分析", "🥊"],
    ["review_miner", "评论洞察", "💬"], ["keyword_research", "关键词研究", "🔑"],
    ["profit_calculator", "利润测算", "💰"], ["supplier_search", "供应商寻源", "🏭"],
    ["product_scorer", "综合评分", "🎯"]
  ];
  const LABELS = {
    total_product_count: "在售商品数", avg_price: "平均售价", median_price: "价格中位数",
    min_price: "最低价", max_price: "最高价", avg_rating: "平均评分", avg_review_count: "平均评论数",
    brand_count: "品牌数量", brand_concentration: "品牌集中度", new_product_ratio: "新品占比",
    direction: "趋势方向", growth_rate: "增长率", yoy_growth: "同比增长", peak_months: "峰值月份",
    competitor_count: "竞品数量", sampled_listing_count: "本次采样商品数", review_count: "评论数", selling_price: "售价", cost_price: "成本价",
    referral_fee: "平台佣金", fba_fulfillment: "FBA 配送费", storage_fee: "月仓储费", shipping: "头程运费",
    import_duty: "关税", total_fees: "费用合计", net_profit: "净利润", profit_margin: "利润率",
    overall_score: "综合评分", grade: "等级", recommendation: "建议动作", note: "数据说明"
  };
  const STAGE_LABEL = Object.fromEntries(STAGES.map(([key, label]) => [key, label]));
  let busy = false;
  let selectedMarket = "US";
  let authToken = sessionStorage.getItem("research-auth-token") || "";
  const apiHeaders = headers => ({...headers, ...(authToken ? {Authorization:`Bearer ${authToken}`} : {})});
  const sessionStorageKey = "product-research-session-id";
  const sessionId = localStorage.getItem(sessionStorageKey) || crypto.randomUUID();
  localStorage.setItem(sessionStorageKey, sessionId);
  const esc = value => String(value ?? "—").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const currencySymbol = currency => ({USD:"$",GBP:"£",EUR:"€",JPY:"¥",CAD:"CA$"}[currency] || "$ ");
  const fmt = (key, value, currency = "USD") => {
    if (value === null || value === undefined || value === "") return "暂无数据";
    if (key.includes("ratio") || key.includes("margin") || key.includes("growth") || key === "brand_concentration") return `${value}%`;
    if (key.includes("price") || key === "net_profit" || key.includes("fee") || key === "shipping" || key === "import_duty" || key === "suggested_cpc") return `${currencySymbol(currency)}${Number(value).toFixed(currency === "JPY" ? 0 : 2)}`;
    if (typeof value === "number" && !Number.isInteger(value)) return Number(value.toFixed(2)).toString();
    if (Array.isArray(value)) return value.join("、") || "暂无数据";
    return String(value);
  };
  const safeSourceLink = value => { try { const url = new URL(String(value || "")); return url.protocol === "https:" ? url.href : ""; } catch { return ""; } };
  const srcNote = data => {
    const url = safeSourceLink(data.source_url);
    const market = ({US:"美国",UK:"英国",DE:"德国",JP:"日本",CA:"加拿大"}[data.marketplace] || data.marketplace || "");
    return "<div class=\"src\"><span>来源：" + esc(sourceLabel(data.source)) + "</span>" + (market ? "<span>站点：" + esc(market) + "</span>" : "") +
      (url ? "<a href=\"" + esc(url) + "\" target=\"_blank\" rel=\"noopener noreferrer\">查看原始页面</a>" : "") +
      "<span class=\"conf " + esc(data.confidence || "Low") + "\">置信度 " + esc(confidenceLabel(data.confidence)) + "</span><span>采集时间：" + esc(data.data_timestamp || "未知") + "</span>" +
      (data.expires_at ? "<span>缓存有效至：" + esc(data.expires_at) + "</span>" : "") + "<span class=\"src-disclaimer\">结果仅供参考</span></div>";
  };
  function userMsg(text) { const wrap = document.createElement("div"); wrap.className = "umsg"; wrap.innerHTML = `<div class="b">${esc(text)}</div>`; flow.appendChild(wrap); scrollDown(); }
  function scrollDown() { const chat = $("chat"); chat.scrollTop = chat.scrollHeight; }
  function addAgentCard(title, body) {
    const row = document.createElement("div"); row.className = "agent-row";
    row.innerHTML = `<div class="avatar" aria-hidden="true">🤖</div><div class="agent-body"><div class="card"><h3><span class="ic">⌕</span>${esc(title)}</h3>${body}</div></div>`;
    flow.appendChild(row); scrollDown(); return row;
  }
  function intentCard(data) {
    const names = {full_pipeline:"完整选品调研", profit:"利润测算", supplier:"供应商寻源", qna:"通用问答", trend:"趋势分析", market_overview:"市场概览", competitor:"竞品分析", review:"评论分析", keyword:"关键词研究", category:"类目穿透", score:"综合评分"};
    addAgentCard("意图识别", `<div class="intent">识别为 <span class="tag">${esc(names[data.intent] || data.intent)}</span><span class="tag dark">关键词：${esc(data.keyword || "—")}</span><span class="tag dark">站点：${esc(data.marketplace || selectedMarket)}</span><span class="tag ok">${data.intent === "full_pipeline" ? "9 阶段流程" : "单项查询"}</span></div>`);
  }
  function stageNode(key) {
    if ($(`nd-${key}`)) return;
    const [, name, icon] = STAGES.find(stage => stage[0] === key) || [key, key, "•"];
    const node = document.createElement("div"); node.className = "stage";
    node.innerHTML = `<div class="rail"><div class="node" id="nd-${esc(key)}">${icon}</div><div class="vline" id="vl-${esc(key)}"></div></div><div class="s-main"><div class="s-head"><b>${esc(name)}</b><span class="st" id="st-${esc(key)}">待执行</span><span class="cached" id="ch-${esc(key)}" style="display:none">缓存命中</span></div><div class="s-body" id="sb-${esc(key)}"></div></div>`;
    flow.appendChild(node); scrollDown();
  }
  function status(key, value, cached = false) {
    stageNode(key);
    const node = $(`nd-${key}`), label = $(`st-${key}`);
    node.className = `node ${value}`;
    node.textContent = ({run:"…", done:"✓", skip:"–", abort:"■", fail:"!"})[value] || "·";
    label.textContent = ({run:"运行中", done:"已完成", skip:"已跳过", abort:"已终止", fail:"失败"})[value] || "待执行";
    if (cached) $(`ch-${key}`).style.display = "inline-block";
    if (value !== "run") $(`vl-${key}`).classList.add("off");
  }
  function kvGrid(data, omit = []) {
    return `<div class="grid">${Object.entries(data).filter(([key, value]) => !omit.includes(key) && !["source", "source_url", "confidence", "evidence", "data_timestamp", "expires_at", "note", "available", "marketplace", "competitors", "suppliers", "keywords", "groups", "tree", "trend_data", "points", "rating_distribution", "sentiment_scores", "top_praise_points", "top_pain_points", "improvement_suggestions", "score_breakdown", "weights", "raw_products", "listing_quality_signals", "price_stddev", "rating_stddev", "review_count_stddev"].includes(key) && typeof value !== "object").map(([key, value]) => `<div class="kpi"><div class="l">${esc(LABELS[key] || key)}</div><div class="v">${esc(fmt(key, value, data.currency || "USD"))}</div></div>`).join("") || `<p class="empty">数据源暂未返回可用指标。</p>`}</div>`;
  }
  function displayCell(value) {
    if (value === null || value === undefined || value === "" || value === "null") return "暂无";
    if (Array.isArray(value)) return value.map(displayCell).join("、");
    if (typeof value === "object") return Object.values(value).map(displayCell).filter(Boolean).join(" / ") || "暂无";
    return String(value);
  }
  function table(items, columns) {
    if (!items?.length) return "<p class=\"empty\">暂未获取到可展示的数据。</p>";
    return "<div class=\"table-scroll\"><table><thead><tr>" + columns.map(([, label]) => "<th>" + esc(label) + "</th>").join("") +
      "</tr></thead><tbody>" + items.map(item => "<tr>" + columns.map(([key]) => "<td>" + esc(displayCell(item[key])) + "</td>").join("") + "</tr>").join("") +
      "</tbody></table></div>";
  }
  function lineChart(values, label = "趋势数据") {
    const nums = values.map(value => Number(typeof value === "object" ? value.value : value)).filter(Number.isFinite);
    if (!nums.length) return `<p class="empty">暂无可绘制的数据。</p>`;
    const min = Math.min(...nums), max = Math.max(...nums), span = max - min || 1;
    const points = nums.map((value, i) => `${(i * 500 / Math.max(1, nums.length - 1)).toFixed(1)},${(112 - ((value - min) / span) * 96).toFixed(1)}`).join(" ");
    return `<div class="chart"><svg viewBox="0 0 500 130" role="img" aria-label="${esc(label)}"><line x1="0" y1="112" x2="500" y2="112" stroke="#dfe5f0"/><polyline points="${points}" fill="none" stroke="#3d6be5" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>${nums.map((value,i)=>`<circle cx="${(i*500/Math.max(1,nums.length-1)).toFixed(1)}" cy="${(112-((value-min)/span)*96).toFixed(1)}" r="2.5" fill="#3d6be5"><title>${esc(value)}</title></circle>`).join("")}</svg><div class="trend-note">${esc(min)} — ${esc(max)} · ${nums.length} 个数据点</div></div>`;
  }
  function bars(items, key, label, color = "#3d6be5") {
    const rows = (items || []).filter(item => Number.isFinite(Number(item[key])));
    if (!rows.length) return "";
    const max = Math.max(1, ...rows.map(item => Number(item[key])));
    return `<div class="chart bar-chart" role="img" aria-label="${esc(label)}">${rows.slice(0, 8).map(item => `<div class="bar-row"><span title="${esc(item.title || item.asin || item.keyword || "")}">${esc(String(item.title || item.asin || item.keyword || "").slice(0,24))}</span><i><b style="width:${Math.max(2,Number(item[key])/max*100)}%;background:${color}"></b></i><strong>${esc(item[key])}</strong></div>`).join("")}</div>`;
  }
  function sentimentChart(scores = {}) {
    const parts = [["positive","正面","#38a36b"],["neutral","中性","#8994aa"],["negative","负面","#d65b5b"]].map(([key,label,color])=>({label,color,value:Number(scores[key] || 0)}));
    if (!parts.some(part=>part.value)) return `<p class="empty">暂无情感分布数据。</p>`;
    return `<div class="chart sentiment-chart" aria-label="评论情感分布">${parts.map(part=>`<div><span>${part.label}</span><b>${part.value}%</b><i><b style="width:${Math.max(0,Math.min(100,part.value))}%;background:${part.color}"></b></i></div>`).join("")}</div>`;
  }
  const SOURCE_LABELS = {
    "Amazon Search Results Page": "亚马逊公开商品搜索页",
    "Onebound Taobao Item Search API": "万邦淘宝商品搜索接口",
    "Onebound Taobao API": "万邦淘宝商品搜索接口",
    "Onebound 1688 Product Search API": "万邦 1688 商品搜索接口",
    "Onebound 1688 API": "万邦 1688 商品搜索接口",
    "本地演示数据": "本地演示数据"
  };
  const SOURCE_NAMES = {
    market_overview: "市场概览", trend_analyzer: "趋势分析", category_explorer: "类目分析",
    competitor_analysis: "竞品分析", review_miner: "评论分析", keyword_research: "关键词分析",
    profit_calculator: "利润测算", supplier_search: "供应商线索", product_scorer: "综合评分"
  };
  const DIMENSION_NAMES = {
    market_demand: "市场需求", competition: "竞争程度", profitability: "利润空间",
    trend: "趋势表现", supply_chain: "供应链"
  };
  const sourceLabel = source => SOURCE_LABELS[source] || (source && /[\u4e00-\u9fff]/.test(source) ? source : "外部数据源");
  const confidenceLabel = level => ({High:"高", Medium:"中", Low:"低"}[level] || level || "低");
  function localizeNote(note = "") {
    const text = String(note || "").trim();
    if (!text) return "";
    if (/[\u4e00-\u9fff]/.test(text)) return text;
    const error = text.match(/provider error code\s+([\w-]+)/i);
    if (error) return "数据服务返回错误码 " + error[1] + "，本次未取得有效数据；这不代表市场上没有相关商品。";
    if (/no matching|no results|returned no/i.test(text)) return "数据源没有返回匹配结果，建议换关键词或稍后重试。";
    if (/request failed|temporarily unavailable|network error/i.test(text)) return "数据请求暂时失败，请检查数据源配置或稍后重试。";
    if (/taobao public product|not 1688 wholesale|MOQ/i.test(text)) return "这是淘宝公开商品线索，不是 1688 批发报价；起订量和供应商资质尚未核实。";
    if (/price statistics use|does not provide comparable|sales-volume metrics/i.test(text)) return "价格统计基于当前返回的商品样本；销量、品牌份额等未提供的数据不会推算。";
    if (/amazon/i.test(text)) return "数据来自公开商品列表，商品详情和价格可能变化，请在来源平台页面复核。";
    return "数据源提供了补充说明，当前未展示未翻译的原始英文提示。";
  }
  function renderTree(node) {
    const rows = Array.isArray(node) ? node : (node && typeof node === "object" ? Object.entries(node).map(([name, value]) => ({name, children:value})) : []);
    if (!rows.length) return "<p class=\"empty\">暂无类目数据。</p>";
    return "<ul class=\"tree-list\">" + rows.map(row => {
      if (!row || typeof row !== "object") return "<li>" + esc(displayCell(row)) + "</li>";
      const name = row.name || row.title || row.label || row.category || row.category_name || "类目";
      const children = row.children || row.subcategories || row.items || row.nodes || [];
      const details = [row.count, row.product_count].filter(value => value !== undefined && value !== null).map(value => "商品数：" + displayCell(value)).join(" · ");
      const childCount = Array.isArray(children) ? children.length : (children && typeof children === "object" ? Object.keys(children).length : 0);
      return "<li><span>" + esc(name) + "</span>" + (details ? "<small>" + esc(details) + "</small>" : "") + (childCount ? renderTree(children) : "") + "</li>";
    }).join("") + "</ul>";
  }
  function scoreTable(data) {
    const breakdown = data.score_breakdown || {};
    const rows = Object.entries(breakdown).map(([key, value]) => ({
      dimension: DIMENSION_NAMES[key] || key,
      score: typeof value === "object" ? (value.score ?? value.value) : value,
      weight: data.weights?.[key] ?? (typeof value === "object" ? value.weight : null)
    }));
    return rows.length ? table(rows, [["dimension","评分维度"],["score","得分"],["weight","权重"]]) : "<p class=\"empty\">暂无评分明细。</p>";
  }
  function renderStage(key, output) {
    const data = output?.data || {};
    let body = "";
    if (!output?.success) body = `<p class="empty">本阶段处理失败：${esc(output?.error || "请稍后重试")}</p>`;
    else if (key === "market_overview") body = kvGrid(data);
    else if (key === "trend_analyzer") {
      const points = data.points?.length ? data.points : (data.trend_data || []);
      body = kvGrid(data) + (points.length ? lineChart(points, "市场趋势") : `<p class="empty">${esc(data.note || "暂无趋势序列")}</p>`);
    } else if (key === "category_explorer") body = renderTree(data.tree || []);
    else if (key === "competitor_analysis") body = bars(data.competitors, "price", "竞品价格") + table(data.competitors, [["asin","商品编号"],["title","商品标题（原文）"],["price","价格"],["rating","评分"],["review_count","评论数"],["brand","品牌"],["bsr","BSR"],["estimated_sales","估算销量/月"],["listing_quality_score","Listing 质量分"]]);
    else if (key === "review_miner") body = `${kvGrid(data)}${sentimentChart(data.sentiment_scores)}<div class="grid"><div class="kpi wide"><div class="l">用户称赞点</div><div>${esc((data.top_praise_points || []).join("、") || "暂无数据")}</div></div><div class="kpi wide"><div class="l">用户痛点</div><div>${esc((data.top_pain_points || []).join("、") || "暂无数据")}</div></div><div class="kpi wide"><div class="l">改进建议</div><div>${esc((data.improvement_suggestions || []).join("；") || "暂无数据")}</div></div></div>`;
    else if (key === "keyword_research") body = `${Object.entries(data.groups || {}).map(([group,terms])=>`<div class="keyword-group"><b>${esc(({core:"核心词",long_tail:"长尾词",low_competition:"低竞争词"}[group] || group))}</b><div>${(terms || []).map(term=>{const keyword=typeof term==="string"?term:(term?.keyword||term?.term||term?.title||term?.text||"");const volume=typeof term==="object"?(term.search_volume??term.volume):null;return keyword?`<span>${esc(keyword)}${volume!==null?` · ${esc(volume)}/月`:""}</span>`:""}).join("") || "暂无"}</div></div>`).join("")}${table(data.keywords, [["keyword","关键词"],["search_volume","搜索量/月"],["competition_level","竞争度"],["suggested_cpc","建议 CPC"],["is_long_tail","长尾词"]])}`;
    else if (key === "profit_calculator") body = kvGrid(data);
    else if (key === "supplier_search") body = table(data.suppliers, [["name","供应商"],["platform","平台"],["price","单价"],["min_order_qty","MOQ"],["store_rating","店铺评分"],["total_revenue","营收"],["contact_info","联系方式"]]);
    else if (key === "product_scorer") body = "<div class=\"score-summary\"><b>" + esc(data.overall_score ?? "证据不足") + "</b><span> / 100 · 数据覆盖 " + esc(data.score_coverage ?? 0) + "%</span><strong>等级 " + esc(data.grade || "待评估") + " · " + esc(data.recommendation || "暂无建议") + "</strong></div>" + scoreTable(data);
    body += "<p class=\"data-note\">" + esc(localizeNote(data.note || "")) + "</p>" + srcNote(data);
    $(`sb-${key}`).innerHTML = body;
    scrollDown();
  }
  function stageSummary(stage, output) {
    const data = output?.data || {};
    const label = SOURCE_NAMES[stage] || stage;
    if (!output?.success || output?.error || data.available === false) {
      const reason = localizeNote(output?.error || data.note || "");
      return label + "：本次未取得有效数据。" + (reason || "请检查数据源后重试；空结果不代表市场上没有相关商品。");
    }
    if (stage === "competitor_analysis") {
      const count = data.competitor_count ?? data.competitors?.length ?? 0;
      return count ? label + "：找到 " + count + " 条海外商品线索，明细已列在上方。" : label + "：暂未找到可展示的商品线索。";
    }
    if (stage === "supplier_search") {
      const count = data.supplier_count ?? data.suppliers?.length ?? 0;
      return count ? label + "：返回 " + count + " 条商品线索；报价、起订量和供应商资质请逐项核实。" : label + "：本次没有取得供应商线索，不能据此判断市场上没有供应商。";
    }
    if (stage === "market_overview") {
      const count = data.total_product_count;
      return count !== undefined ? label + "：当前样本涉及 " + displayCell(count) + " 条商品记录。" : label + "：结果已生成，指标明细见上方。";
    }
    if (stage === "trend_analyzer") {
      const direction = ({up:"上升", stable:"稳定", down:"下降"}[data.direction] || data.direction);
      return label + "：" + (direction ? "趋势判断为“" + displayCell(direction) + "”" : "结果已生成") + "，请结合页面中的时间范围和样本来源判断。";
    }
    return label + "：结果已生成，明细见上方。";
  }
  function report(data) {
    const stages = Object.entries(data?.stages || {});
    if (!stages.length) return;
    const market = ({US:"美国", UK:"英国", DE:"德国", JP:"日本", CA:"加拿大"}[data.marketplace] || data.marketplace || "未指定");
    const successful = stages.filter(([, output]) => output?.success && !output?.error && output?.data?.available !== false).length;
    const sources = [...new Set(stages.map(([, output]) => sourceLabel(output?.data?.source)).filter(source => source !== "未知来源"))];
    const lines = stages.map(([stage, output]) => "<li>" + esc(stageSummary(stage, output)) + "</li>").join("");
    const sourceText = sources.length ? sources.map(esc).join("、") : "本次没有可用的数据来源";
    const headline = successful
      ? "本次完成 " + successful + "/" + stages.length + " 项数据分析。"
      : "本次未取得可用的市场数据，请按下方提示检查后重试。";
    const body = "<section class=\"report-summary\">" +
      "<p class=\"report-lead\">" + esc(data.keyword || data.intent?.keyword || "本次查询") + " · 目标市场：" + esc(market) + "</p>" +
      "<p class=\"report-headline\">" + headline + "</p>" +
      "<h4>查询结果</h4><ul class=\"report-list\">" + lines + "</ul>" +
      "<div class=\"report-source\"><b>数据来源</b><span>" + sourceText + "</span></div>" +
      "<p class=\"report-footnote\">商品标题保留平台原文；价格和商品状态可能变化，请以来源平台页面为准。</p></section>";
    addAgentCard("调研结论", body);
  }
  function abort(data) {
    const row = document.createElement("div"); row.className = "abort-banner";
    row.innerHTML = `<span aria-hidden="true">⛔</span><div><b>Pipeline 提前终止</b><br>${esc(data.reason || "触发业务终止规则")}</div>`;
    flow.appendChild(row); scrollDown();
  }
  const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
  async function run(query, intent = null) {
    if (busy || !query.trim()) return;
    busy = true; $("send").disabled = true; $("typing").classList.add("show");
    userMsg(query);
    const request = {message: query, marketplace: selectedMarket, intent, params: {}, session_id: sessionId};
    try {
      const response = await fetch("/api/tasks", {method:"POST", headers:apiHeaders({"Content-Type":"application/json"}), body:JSON.stringify(request)});
      const submitted = await response.json();
      if (!response.ok) throw new Error(submitted.detail || "任务提交失败，请稍后重试");
      STAGES.forEach(([key]) => stageNode(key));
      addAgentCard("任务进度", `<p class="mini" id="task-progress-${esc(submitted.task_id)}">任务已提交，正在准备执行……</p><button type="button" class="secondary" data-cancel-task="${esc(submitted.task_id)}">取消任务</button>`);
      const progressEl = $(`task-progress-${submitted.task_id}`);
      let task;
      for (let attempt = 0; attempt < 1800; attempt++) {
        await wait(1000);
        const poll = await fetch(`/api/tasks/${encodeURIComponent(submitted.task_id)}`, {headers:apiHeaders({})});
        task = await poll.json();
        if (!poll.ok) throw new Error(task.detail || "读取任务状态失败");
        const progress = task.progress || {};
        if (progressEl) progressEl.textContent = task.status === "queued" ? "排队中……" : task.status === "cancelled" ? "任务已取消" : `当前阶段：${STAGE_LABEL[progress.stage] || progress.stage || "准备中"} · 已完成 ${progress.completed || 0} 项`;
        const runningIndex = STAGES.findIndex(([key]) => key === progress.stage);
        STAGES.forEach(([key], index) => {
          if (index < (progress.completed || 0)) status(key, "done");
          else if (index === runningIndex && task.status === "running") status(key, "run");
        });
        if (["completed", "failed", "cancelled"].includes(task.status)) break;
      }
      if (!task || !["completed", "failed", "cancelled"].includes(task.status)) throw new Error("任务等待超时，请查看调研历史或稍后重试");
      if (task.status === "failed") throw new Error(task.error || "调研任务执行失败，请稍后重试");
      if (task.status === "cancelled") throw new Error("调研任务已取消");
      if (progressEl) progressEl.textContent = "任务已完成";
      const finalData = task.result || {};
      if (finalData.stages) {
        const executedStages = new Set(Object.keys(finalData.stages));
        Object.entries(finalData.stages).forEach(([key, output]) => {
          if (!$("sb-" + key)) stageNode(key);
          status(key, output.success && output.data?.available !== false ? "done" : "fail", output.cached);
          renderStage(key, output);
        });
        STAGES.forEach(([key]) => {
          if (executedStages.has(key)) return;
          status(key, "skip");
          $("sb-" + key).innerHTML = `<p class="empty">${finalData.aborted ? "完整调研流程已提前终止，后续阶段未执行。" : "本次按单项查询执行，未运行此阶段。"}</p>`;
        });
        report(finalData);
      }
      if (finalData.answer) addAgentCard("调研答复", `<div class="report-text">${esc(finalData.answer)}</div><p class="data-note">来源：${esc(finalData.source || "未注明")} · 置信度：${esc(confidenceLabel(finalData.confidence || "Low"))}</p>`);
      localStorage.setItem("research-last-query", query);
      await refreshHistory();
    } catch (error) {
      addAgentCard("本次查询未完成", `<p class="empty">${esc(error.message || "请求失败，请稍后重试")}</p>`);
      await refreshHistory();
    } finally { busy = false; $("typing").classList.remove("show"); $("send").disabled = false; $("inp").focus(); }
  }
  const actionQuery = {full:"帮我分析宠物饮水机的市场机会", profit:"计算一下卖 $29.99 的利润", supplier:"找一下宠物饮水机的 1688 供应商", qna:"宠物用品选品时应该关注哪些方面？"};
  $("send").addEventListener("click", () => {const value = $("inp").value.trim(); if (value) {$("inp").value = ""; run(value);}});
  $("inp").addEventListener("keydown", event => {if (event.key === "Enter") $("send").click();});
  document.querySelectorAll(".chip").forEach(chip => chip.addEventListener("click", () => run(chip.dataset.q)));
  document.querySelectorAll(".act").forEach(action => action.addEventListener("click", () => {
    document.querySelectorAll(".act").forEach(item => {item.classList.remove("on"); item.setAttribute("aria-pressed", "false");});
    action.classList.add("on"); action.setAttribute("aria-pressed", "true");
    const key = action.dataset.act; const intent = key === "full" ? "full_pipeline" : key;
    run(actionQuery[key] || actionQuery.full, intent);
  }));
  $("mkt").addEventListener("click", event => {
    const selected = event.target.closest("button");
    if (!selected || !event.currentTarget.contains(selected)) return;
    document.querySelectorAll("#mkt button").forEach(item => {item.classList.remove("on"); item.setAttribute("aria-pressed", "false");});
    selected.classList.add("on"); selected.setAttribute("aria-pressed", "true"); selectedMarket = selected.textContent.trim();
  });
  document.querySelectorAll(".hist").forEach(item => item.addEventListener("click", () => run(item.textContent.includes("饮水机") ? "帮我分析宠物饮水机的市场机会" : item.textContent.trim())));
  async function refreshHistory() {
    const host = $("history-list");
    if (!host) return;
    try {
      const response = await fetch("/api/tasks?limit=12", {headers:apiHeaders({})});
      if (!response.ok) return;
      const data = await response.json();
      const rows = data.tasks || [];
      host.innerHTML = rows.length ? rows.map(task => `<div class="history-item" data-task-id="${esc(task.task_id)}"><button class="history-title" data-history-open="${esc(task.task_id)}" title="${esc(task.message)}">${esc(task.message)}</button><span class="history-meta">${esc(({queued:"\u6392\u961f\u4e2d",running:"\u8fdb\u884c\u4e2d",completed:"\u5df2\u5b8c\u6210",failed:"\u5931\u8d25",cancelled:"\u5df2\u53d6\u6d88"})[task.status] || task.status)} \u00b7 ${esc((task.created_at || "").slice(0,16).replace("T"," "))}</span><span class="history-actions"><button type="button" data-favorite="${esc(task.task_id)}" aria-label="${task.favorite ? "\u53d6\u6d88\u6536\u85cf" : "\u6536\u85cf"}" title="${task.favorite ? "\u53d6\u6d88\u6536\u85cf" : "\u6536\u85cf"}">${task.favorite ? "\u2605" : "\u2606"}</button>${task.status === "completed" ? `<button type="button" data-export="${esc(task.task_id)}" title="\u5bfc\u51fa\u62a5\u544a">\u5bfc\u51fa</button>` : ""}${task.status === "failed" ? `<button type="button" data-retry="${esc(task.task_id)}" title="\u91cd\u8bd5">\u91cd\u8bd5</button>` : ""}</span></div>`).join("") : `<div class="history-empty">\u6682\u65e0\u8c03\u7814\u5386\u53f2</div>`;
    } catch (_) { /* Keep the workspace usable when history storage is unavailable. */ }
  }
  $("history-list")?.addEventListener("click", async event => {
    const favorite = event.target.closest("[data-favorite]");
    const exportButton = event.target.closest("[data-export]");
    const retryButton = event.target.closest("[data-retry]");
    const cancelButton = event.target.closest("[data-cancel-task]");
    const openButton = event.target.closest("[data-history-open]");
    if (cancelButton) {
      cancelButton.disabled = true;
      const response = await fetch(`/api/tasks/${encodeURIComponent(cancelButton.dataset.cancelTask)}`, {method:"DELETE", headers:apiHeaders({})});
      const result = await response.json();
      const progress = $(`task-progress-${cancelButton.dataset.cancelTask}`);
      if (!response.ok && progress) progress.textContent = result.detail || "取消失败，请稍后重试。";
      else cancelButton.textContent = "已取消";
    } else if (retryButton) {
      const response = await fetch(`/api/tasks/${encodeURIComponent(retryButton.dataset.retry)}/retry`, {method:"POST", headers:apiHeaders({})});
      if (response.ok) { const result = await response.json(); await refreshHistory(); addAgentCard("重试任务", `<p class="mini">已重新提交任务：${esc(result.task_id)}</p>`); }
    } else if (favorite) {
      const row = favorite.closest(".history-item");
      const response = await fetch(`/api/tasks/${encodeURIComponent(favorite.dataset.favorite)}/favorite`, {method:"POST",headers:apiHeaders({"Content-Type":"application/json"}),body:JSON.stringify({favorite:favorite.textContent.trim() !== "\u2605"})});
      if (response.ok) await refreshHistory();
    } else if (exportButton) {
      const response = await fetch(`/api/tasks/${encodeURIComponent(exportButton.dataset.export)}/export`, {headers:apiHeaders({})});
      if (!response.ok) return;
      const blob = await response.blob(), url = URL.createObjectURL(blob), anchor = document.createElement("a");
      anchor.href = url; anchor.download = "\u9009\u54c1\u8c03\u7814\u62a5\u544a.md"; anchor.click(); URL.revokeObjectURL(url);
    } else if (openButton) {
      const response = await fetch(`/api/tasks/${encodeURIComponent(openButton.dataset.historyOpen)}`, {headers:apiHeaders({})});
      const task = await response.json();
      if (response.ok && task.result) {
        if (task.result.stages) { Object.entries(task.result.stages).forEach(([key, output]) => { if (!$("sb-"+key)) stageNode(key); status(key, output.success && output.data?.available !== false ? "done" : "fail", output.cached); renderStage(key, output); }); report(task.result); }
        if (task.result.answer) addAgentCard("调研答复", `<div class="report-text">${esc(task.result.answer)}</div>`);
      }
    }
  });
  refreshHistory();
  fetch("/api/health").then(response => response.json()).then(data => {
    const badge = $("service-status");
    if (badge) { badge.textContent = data.status === "ok" ? "● 服务正常" : "● 服务降级"; badge.classList.toggle("gray", data.status !== "ok"); }
    const model = $("model-status");
    if (model) { model.textContent = "模型状态以本次查询为准"; model.classList.add("gray"); }
    const cache = document.querySelector(".cache-card");
    if (cache) cache.innerHTML = `<b>数据与运行状态</b><br><span class="dot"></span>具体数据源、更新时间和可用指标请查看每次查询结果。<br><small>未取得数据时会明确标注；空结果不代表市场上没有相关商品或供应商。</small>`;
    if (data.auth_enabled) {
      const verify = authToken ? fetch("/api/auth/me", {headers:apiHeaders({})}).then(response => response.ok) : Promise.resolve(false);
      verify.then(valid => { if (!valid) showAuthGate(Boolean(data.auth_allow_signup || data.auth_bootstrap_available)); });
    }
  }).catch(() => {});

  function showAuthGate(allowSignup) {
    if ($("auth-gate")) return;
    const gate = document.createElement("div"); gate.id = "auth-gate";
    gate.innerHTML = `<style>#auth-gate{position:fixed;inset:0;z-index:1000;background:rgba(14,22,40,.72);display:grid;place-items:center;padding:20px}#auth-gate .auth-box{background:#fff;width:min(420px,100%);padding:28px;border-radius:16px;box-shadow:0 20px 60px #0003}#auth-gate h2{margin:0 0 8px;color:#1c2333}#auth-gate p{color:#6b7488;margin:0 0 18px}#auth-gate label{display:block;font-size:13px;margin:12px 0 5px}#auth-gate input{width:100%;padding:11px;border:1px solid #d8deea;border-radius:8px}#auth-gate button{margin-top:16px;padding:11px 15px;border:0;border-radius:8px;background:#3d6be5;color:#fff;cursor:pointer}#auth-gate .auth-switch{background:transparent;color:#3d6be5;margin-left:8px}#auth-gate .auth-error{color:#b42318;min-height:20px;margin-top:12px}</style><form class="auth-box"><h2>登录选品调研工作台</h2><p>账号和报告按工作区隔离保存。</p><div class="auth-register" style="display:none"><label for="auth-display-name">姓名</label><input id="auth-display-name" name="display_name" maxlength="120"><label for="auth-organization-name">工作区名称</label><input id="auth-organization-name" name="organization_name" maxlength="160"></div><label for="auth-email">邮箱</label><input id="auth-email" name="email" type="email" autocomplete="username" required><label for="auth-password">密码</label><input id="auth-password" name="password" type="password" autocomplete="current-password" required><button type="submit">登录</button>${allowSignup ? `<button type="button" class="auth-switch">初始化工作区</button>` : ""}<div class="auth-error" role="alert"></div></form>`;
    document.body.appendChild(gate);
    const form = gate.querySelector("form"), registerFields = gate.querySelector(".auth-register"), submit = form.querySelector("button[type=submit]"), switchButton = gate.querySelector(".auth-switch");
    let registering = false;
    if (switchButton) switchButton.addEventListener("click", () => { registering = !registering; registerFields.style.display = registering ? "block" : "none"; submit.textContent = registering ? "创建工作区" : "登录"; switchButton.textContent = registering ? "返回登录" : "初始化工作区"; form.querySelector('[name=password]').minLength = registering ? 12 : 1; });
    form.addEventListener("submit", async event => {
      event.preventDefault(); const values = Object.fromEntries(new FormData(form));
      const endpoint = registering ? "/api/auth/register" : "/api/auth/login";
      const payload = registering ? {email:values.email,password:values.password,display_name:values.display_name,organization_name:values.organization_name} : {email:values.email,password:values.password};
      const error = gate.querySelector(".auth-error"); error.textContent = ""; submit.disabled = true;
      try { const response = await fetch(endpoint,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)}); const result = await response.json(); if (!response.ok) throw new Error(result.detail || "登录失败"); authToken = result.access_token; sessionStorage.setItem("research-auth-token",authToken); location.reload(); }
      catch (reason) { error.textContent = reason.message || "登录失败，请重试。"; }
      finally { submit.disabled = false; }
    });
  }
})();

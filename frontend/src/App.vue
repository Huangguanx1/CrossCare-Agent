<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { generateDraft, getHealth, getTicket, listTickets, reviewDraft, type Ticket, type TicketListItem } from './api'

const tickets = ref<TicketListItem[]>([])
const selected = ref<Ticket | null>(null)
const editedReply = ref('')
const reviewNote = ref('')
const busy = ref(false)
const error = ref('')
const draftMode = ref('')
const modeText = computed(() => ({ offline_rules: '离线规则演示', openai_tool_calling: '模型工具调用', misconfigured: '模型配置不完整' })[draftMode.value] || '模式加载中')
const statusText: Record<string, string> = {
  new: '未处理', needs_review: '待审核', approved_demo_only: '已批准（仅演示）', rejected: '已退回',
}
const pendingCount = computed(() => tickets.value.filter(t => t.status === 'needs_review').length)

async function refreshTickets() {
  tickets.value = await listTickets()
}

async function openTicket(id: string) {
  error.value = ''
  try {
    selected.value = await getTicket(id)
    editedReply.value = selected.value.draft?.reply_text || ''
    reviewNote.value = selected.value.draft?.review_note || ''
  } catch (err) { error.value = (err as Error).message }
}

async function runDraft() {
  if (!selected.value) return
  busy.value = true
  error.value = ''
  try {
    await generateDraft(selected.value.id)
    await Promise.all([openTicket(selected.value.id), refreshTickets()])
  } catch (err) { error.value = (err as Error).message }
  finally { busy.value = false }
}

async function submitReview(action: 'approve' | 'reject') {
  if (!selected.value) return
  busy.value = true
  error.value = ''
  try {
    await reviewDraft(selected.value.id, action, editedReply.value, reviewNote.value)
    await Promise.all([openTicket(selected.value.id), refreshTickets()])
  } catch (err) { error.value = (err as Error).message }
  finally { busy.value = false }
}

onMounted(async () => {
  try {
    const [health] = await Promise.all([getHealth(), refreshTickets()])
    draftMode.value = health.draft_mode
    if (tickets.value[0]) await openTicket(tickets.value[0].id)
  } catch (err) { error.value = (err as Error).message }
})
</script>

<template>
  <div class="shell">
    <header class="masthead">
      <div class="brand"><span class="brand-mark">C</span><span>CrossCare <small>售后审核台</small></span></div>
      <div class="demo-badge">合成数据 · {{ modeText }}</div>
    </header>

    <div class="workspace-heading">
      <div><h1>跨境电商售后回复助手</h1><p>给客服使用：核对客户消息、订单、物流和售后政策，生成英文回复草稿，由人工决定是否采用。</p></div>
      <div class="queue-count"><strong>{{ pendingCount }}</strong><span>条草稿待审核</span></div>
    </div>
    <div class="workflow" aria-label="处理流程">
      <span><b>1</b>选择客户工单</span><i aria-hidden="true">→</i>
      <span><b>2</b>核对订单与政策</span><i aria-hidden="true">→</i>
      <span><b>3</b>生成英文草稿</span><i aria-hidden="true">→</i>
      <span><b>4</b>人工审核</span>
    </div>

    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <main class="desk">
      <aside class="ticket-rail" aria-label="工单列表">
        <div class="rail-heading"><h2>客户工单</h2><span>{{ tickets.length }} 条演示消息</span></div>
        <button v-for="ticket in tickets" :key="ticket.id" class="ticket-item" :class="{ active: selected?.id === ticket.id }" @click="openTicket(ticket.id)">
          <span class="ticket-top"><strong>{{ ticket.id }}</strong><span class="status" :class="ticket.status">{{ statusText[ticket.status] || ticket.status }}</span></span>
          <span class="ticket-subject">{{ ticket.subject }}</span>
          <span class="ticket-preview">{{ ticket.message }}</span>
        </button>
      </aside>

      <template v-if="selected">
        <section class="case-panel" aria-label="工单详情">
          <div class="section-heading"><span class="case-id">{{ selected.id }}</span><span class="status" :class="selected.status">{{ statusText[selected.status] || selected.status }}</span></div>
          <h2>{{ selected.subject }}</h2>
          <div class="case-meta"><span>{{ selected.customer_name }}</span><span>{{ selected.market }} 市场</span><span>{{ selected.order_id || '无订单号' }}</span></div>
          <div class="customer-message"><span class="message-label">客户原话</span><p>{{ selected.message }}</p></div>
          <div class="section-heading evidence-title"><h3>订单、物流与政策依据</h3><span v-if="selected.draft">{{ selected.draft.mode === 'offline_rules' ? '离线规则草稿' : '模型工具调用草稿' }}</span></div>
          <template v-if="selected.draft">
            <div v-if="selected.draft.risk_flags.length" class="risk-box"><strong>需要人工核对</strong><span v-for="flag in selected.draft.risk_flags" :key="flag">{{ flag }}</span></div>
            <div v-for="tool in selected.draft.tool_results" :key="tool.tool" class="evidence-card">
              <span class="evidence-type">只读工具</span><strong>{{ tool.tool }}</strong>
              <p v-if="tool.found === false">当前客户无法验证此订单。未返回订单内容。</p>
              <template v-else-if="tool.events"><p v-for="event in tool.events" :key="event.event_time">{{ event.event_time.slice(0, 10) }} · {{ event.description }}</p></template>
              <p v-else>订单 {{ tool.order_id }} 已通过客户归属校验。</p>
            </div>
            <div v-for="citation in selected.draft.citations" :key="citation.id" class="evidence-card policy"><span class="evidence-type">政策依据</span><strong>{{ citation.title }}</strong><p>{{ citation.id }} · {{ citation.version }}</p></div>
            <p v-if="!selected.draft.citations.length && !selected.draft.risk_flags.length" class="muted">没有匹配的政策依据。</p>
          </template>
          <div v-else class="empty-evidence">点击右侧“生成待审草稿”，系统会校验订单归属、读取物流并查找适用政策；结果会显示在这里。</div>
        </section>

        <aside class="review-panel" aria-label="草稿审核">
          <div class="review-heading"><h2>英文回复草稿</h2><span>人工确认后仅更新演示状态</span></div>
          <button class="primary" :disabled="busy" @click="runDraft">{{ busy ? '处理中…' : selected.draft ? '重新生成草稿' : '生成待审草稿' }}</button>
          <template v-if="selected.draft">
            <label for="reply">英文回复</label>
            <textarea id="reply" v-model="editedReply" rows="10" :disabled="busy" />
            <div class="rationale"><strong>内部处理说明</strong><p>{{ selected.draft.rationale }}</p></div>
            <label for="note">审核备注</label>
            <input id="note" v-model="reviewNote" placeholder="可写退回原因或修改说明" :disabled="busy" />
            <div v-if="selected.status === 'needs_review'" class="review-actions"><button class="secondary" :disabled="busy" @click="submitReview('reject')">退回草稿</button><button class="approve" :disabled="busy || !editedReply.trim()" @click="submitReview('approve')">批准演示草稿</button></div>
            <p v-else-if="selected.status === 'approved_demo_only'" class="muted">草稿已批准，仅记录在本地演示数据库。</p>
            <p v-else-if="selected.status === 'rejected'" class="muted">草稿已退回，可重新生成后审核。</p>
            <p class="safety-note">批准不会发送消息，也不会修改真实订单或退款。</p>
          </template>
          <p v-else class="muted">草稿只供客服审阅，不会自动发送给客户。</p>
        </aside>
      </template>
      <section v-else class="empty-selection">选择一条工单开始处理。</section>
    </main>
  </div>
</template>

export interface TicketListItem {
  id: string
  subject: string
  message: string
  status: string
  created_at: string
}

export interface Citation { id: string; title: string; version: string }
export interface ToolResult { tool: string; order_id: string; found?: boolean; events?: { event_time: string; status: string; description: string }[] }
export interface Draft {
  reply_text: string
  rationale: string
  citations: Citation[]
  tool_results: ToolResult[]
  risk_flags: string[]
  mode: string
  created_at: string
  reviewed_at: string | null
  review_note: string | null
}
export interface Ticket extends TicketListItem {
  customer_id: string
  customer_name: string
  market: string
  order_id: string | null
  draft: Draft | null
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, options)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `请求失败 (${response.status})`)
  }
  return response.json() as Promise<T>
}

export const listTickets = () => request<TicketListItem[]>('/tickets')
export const getTicket = (id: string) => request<Ticket>(`/tickets/${encodeURIComponent(id)}`)
export const generateDraft = (id: string) => request<Draft>(`/tickets/${encodeURIComponent(id)}/draft`, { method: 'POST' })
export const reviewDraft = (id: string, action: 'approve' | 'reject', edited_reply: string, note: string) =>
  request<{ status: string; external_message_sent: false }>(`/tickets/${encodeURIComponent(id)}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, edited_reply, note }),
  })

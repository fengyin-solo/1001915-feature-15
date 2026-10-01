<template>
  <section class="page" data-module="defect">
    <header class="page-head">
      <div>
        <h2>缺陷登记管理</h2>
        <p class="page-desc">维护机组缺陷，围绕缺陷编号、缺陷部位、缺陷等级、发现方式做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn primary" :to="boardLink">缺陷分级看板</RouterLink>
        <button class="btn" type="button" @click="exportRows">导出缺陷登记清单</button>
      </div>
    </header>

    <div v-if="fromBoard" class="board-context">
      <RouterLink class="link" :to="boardBackLink">‹ 返回缺陷分级看板</RouterLink>
      <span>当前按部位「{{ filters.缺陷部位 }}」展开，共 {{ total }} 条</span>
      <button v-if="filters.缺陷部位" class="link" type="button" @click="clearPartFilter">清除部位筛选</button>
    </div>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>缺陷编号</span>
        <input v-model="filters.keyword" placeholder="按缺陷编号检索" />
      </label>
      <label class="filter-item">
        <span>缺陷部位</span>
        <input v-model="filters.缺陷部位" placeholder="按缺陷部位检索" />
      </label>
      <label class="filter-item">
        <span>缺陷等级</span>
        <select v-model="filters.level">
          <option value="">全部等级</option>
          <option v-for="level in levels" :key="level" :value="level">{{ level }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>缺陷状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <label class="filter-check">
        <input v-model="reviewOnly" type="checkbox" /> 只看待复核名单
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td>{{ row['缺陷编号'] ?? '—' }}</td>
          <td>{{ row['缺陷部位'] ?? '—' }}</td>
          <td>
            <span class="level-badge" :class="levelClass(String(row['判定等级'] ?? ''))">{{ row['判定等级'] ?? '—' }}</span>
            <span
              v-if="row['历史定级'] && row['历史定级'] !== row['判定等级']"
              class="history-tag"
              :title="`定级标准调整前的结论：${row['历史定级']}`"
            >原{{ row['历史定级'] }}</span>
          </td>
          <td>{{ row['发现方式'] ?? '—' }}</td>
          <td>{{ row['发现时间'] ?? '—' }}</td>
          <td>{{ row['报告人'] ?? '—' }}</td>
          <td>
            <span v-if="!isValidDate(row['计划消除日'])" class="missing-text">计划消除日缺失</span>
            <span v-else :class="{ 'overdue': isOverdue(String(row['计划消除日'])) }">
              {{ row['计划消除日'] }}<i v-if="isOverdue(String(row['计划消除日']))">（已逾期）</i>
            </span>
          </td>
          <td>
            {{ row.status ?? '—' }}
            <span v-if="row['待复核']" class="review-flag">待复核</span>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actionsFor(row)"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无缺陷登记数据，可先登记机组缺陷</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条缺陷登记记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/defect'
const columns = ['缺陷编号', '缺陷部位', '缺陷等级', '发现方式', '发现时间', '报告人', '计划消除日', '缺陷状态']
const statuses = ['待定级', '已定级', '处置中', '已消除']
const levels = ['一级', '二级', '三级', '四级']

const route = useRoute()
const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const reviewOnly = ref(false)
const filters = ref<Record<string, string>>({
  keyword: '',
  缺陷部位: '',
  level: '',
  status: '',
})
const stats = ref([
  { label: '待定级缺陷', value: 0 },
  { label: '处置中缺陷', value: 0 },
  { label: '待复核', value: 0 },
  { label: '今日消除数', value: 0 },
])

const fromBoard = computed(() => route.query.from === 'board')
const boardLink = computed(() => '/defect/board')
const boardBackLink = computed(() =>
  filters.value.缺陷部位 ? `/defect/board?part=${encodeURIComponent(filters.value.缺陷部位)}` : '/defect/board',
)

function levelClass(level: string): string {
  return `lv-${level.replace('级', '') || 'none'}`
}

function isValidDate(value: unknown): boolean {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value))
}

function isOverdue(plan: string): boolean {
  if (!isValidDate(plan)) return false
  return new Date(`${plan}T00:00:00`).getTime() < Date.now()
}

function actionsFor(row: Row): string[] {
  const status = String(row.status ?? '')
  if (status === '待定级') return ['确认定级']
  if (status === '已定级') return ['提交消除']
  if (status === '处置中') {
    return row['待复核'] ? ['复核确认', '验收消除', '退回'] : ['验收消除', '退回']
  }
  if (status === '已消除') return ['退回']
  return []
}

function clearPartFilter() {
  filters.value.缺陷部位 = ''
  void reload()
}

function resetFilters() {
  filters.value = { keyword: '', 缺陷部位: '', level: '', status: '' }
  reviewOnly.value = false
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload?.message || '缺陷登记动作未生效，请稍后重试')
    }
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '缺陷登记操作失败'
  }
}

async function loadStats() {
  // 数字与看板同源，保证列表概览、看板、台账口径一致。
  try {
    const response = await request(`${ENDPOINT}/board`)
    if (!response.ok) return
    const board = await response.json()
    stats.value = [
      { label: '待定级缺陷', value: board.counts?.['待定级'] ?? 0 },
      { label: '处置中缺陷', value: board.counts?.['处置中'] ?? 0 },
      { label: '待复核', value: board.review ?? 0 },
      { label: '今日消除数', value: board.eliminated_today ?? 0 },
    ]
  } catch {
    // 统计读不出来时保留上一次的值，不影响列表本身。
  }
}

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  if (filters.value.keyword) params.set('keyword', filters.value.keyword)
  if (filters.value.缺陷部位) params.set('part', filters.value.缺陷部位)
  if (filters.value.level) params.set('level', filters.value.level)
  if (filters.value.status) params.set('status', filters.value.status)
  if (reviewOnly.value) params.set('review', 'true')
  params.set('size', '200')
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) {
      const detail = await response.json().catch(() => null)
      throw new Error(detail?.detail || '机组缺陷列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '缺陷登记列表读取失败'
  }
}

onMounted(async () => {
  // 从看板点分区进来时带上部位筛选，方便看完后原路退回看板。
  const part = route.query.part
  if (typeof part === 'string' && part) {
    filters.value.缺陷部位 = part
  }
  await Promise.all([reload(), loadStats()])
})
</script>

<style scoped>
.board-context { display: flex; gap: 12px; align-items: center; background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 6px; padding: 6px 10px; font-size: 13px; margin-bottom: 10px; }
.level-badge { display: inline-block; border-radius: 4px; padding: 1px 8px; font-size: 12px; border: 1px solid transparent; }
.lv-1 { background: #fee2e2; color: #991b1b; border-color: #fca5a5; }
.lv-2 { background: #ffedd5; color: #9a3412; border-color: #fdba74; }
.lv-3 { background: #fef9c3; color: #854d0e; border-color: #fde047; }
.lv-4 { background: #dcfce7; color: #166534; border-color: #86efac; }
.lv-none { background: #f1f5f9; color: #64748b; border-color: #cbd5e1; }
.history-tag { margin-left: 6px; background: #e2e8f0; color: #475569; border-radius: 4px; padding: 0 6px; font-size: 12px; }
.review-flag { margin-left: 6px; background: #fee2e2; color: #b91c1c; border-radius: 4px; padding: 0 6px; font-size: 12px; }
.missing-text { color: #b45309; font-weight: 600; }
.overdue { color: #b42318; }
.overdue i { font-style: normal; }
.filter-check { display: flex; align-items: center; gap: 4px; font-size: 13px; }
.filter-item select { padding: 4px 8px; border: 1px solid var(--border); border-radius: 6px; }
</style>

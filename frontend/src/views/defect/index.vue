<template>
  <section class="page" data-module="defect">
    <header class="page-head">
      <div>
        <h2>缺陷登记管理</h2>
        <p class="page-desc">维护机组缺陷，围绕缺陷编号、缺陷部位、缺陷等级、发现方式做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn primary" to="/defect/board">缺陷分级看板</RouterLink>
        <button class="btn" type="button" @click="exportRows">导出缺陷登记清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value" :class="item.cls">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>缺陷编号</span>
        <input v-model="keyword" placeholder="按缺陷编号检索" />
      </label>
      <label class="filter-item">
        <span>缺陷部位</span>
        <select v-model="partFilter">
          <option value="">全部部位</option>
          <option v-for="part in parts" :key="part" :value="part">{{ part }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>缺陷状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
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
          <template v-for="column in columns" :key="column">
            <td v-if="column === '缺陷部位'">
              <RouterLink class="link" :to="`/defect/board?part=${encodeURIComponent(String(row[column] ?? ''))}`">
                {{ row[column] ?? '—' }}
              </RouterLink>
            </td>
            <td v-else-if="column === '缺陷等级'">
              <i class="level-chip sm" :class="levelClass(String(row[column] ?? ''))">{{ row[column] ?? '—' }}</i>
              <span v-if="row.等级漂移" class="drift-tag" title="历史定级与当前标准建议不一致">标准已变</span>
            </td>
            <td v-else>{{ row[column] ?? '—' }}</td>
          </template>
          <td class="row-actions">
            <button
              v-for="action in actions"
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
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null> & { status?: string }
type StatCard = { label: string; value: number; cls?: string }

const ENDPOINT = '/api/defect'
const columns = ['缺陷编号', '缺陷部位', '缺陷等级', '缺陷现象', '发现方式', '发现时间', '报告人', '计划消除日']
const actions = ['确认定级', '提交消除', '验收消除', '验收退回']
const statuses = ['待定级', '已定级', '处置中', '已消除']
const parts = ['叶片', '齿轮箱', '发电机', '主轴承', '变桨系统', '偏航系统', '塔筒', '塔基', '集电环', '控制柜', '消防系统', '其他']

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const keyword = ref('')
const partFilter = ref('')
const statusFilter = ref('')
const stats = ref<StatCard[]>([
  { label: '待定级缺陷', value: 0 },
  { label: '处置中缺陷', value: 0 },
  { label: '待复核缺陷', value: 0, cls: 'warn-text' },
  { label: '今日消除数', value: 0, cls: 'ok-text' },
])

function levelClass(level: string) {
  if (level === '危急') return 'lv-critical'
  if (level === '严重') return 'lv-serious'
  if (level === '一般') return 'lv-minor'
  return 'lv-pending'
}

function resetFilters() {
  keyword.value = ''
  partFilter.value = ''
  statusFilter.value = ''
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
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!response.ok || payload.ok === false) {
      errorMessage.value = payload?.message || '缺陷登记动作未生效，请稍后重试'
      return
    }
    await Promise.all([reload(), reloadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '缺陷登记操作失败'
  }
}

async function reloadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) return
    const payload = (await response.json()) as Record<string, number>
    stats.value = [
      { label: '待定级缺陷', value: payload['待定级'] ?? 0 },
      { label: '处置中缺陷', value: payload['处置中'] ?? 0 },
      { label: '待复核缺陷', value: payload['待复核'] ?? 0, cls: 'warn-text' },
      { label: '今日消除数', value: payload['今日消除数'] ?? 0, cls: 'ok-text' },
    ]
  } catch {
    // 统计失败不阻断列表使用
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value) query.set('keyword', keyword.value)
  if (partFilter.value) query.set('part', partFilter.value)
  if (statusFilter.value) query.set('status', statusFilter.value)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('机组缺陷列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '缺陷登记列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void reloadStats()
})
</script>

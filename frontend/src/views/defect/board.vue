<template>
  <section class="page" data-module="defect-board">
    <header class="page-head">
      <div>
        <h2>缺陷分级看板</h2>
        <p class="page-desc">按缺陷部位分区，缺陷等级以底色区分；每个分区汇总待定级、已定级、处置中、已消除数量，并列出计划消除日最近的几条。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/defect">返回缺陷列表</RouterLink>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value" :class="item.cls">{{ item.value }}</strong>
      </article>
    </div>

    <div v-if="board && board.missing_plan.length" class="warn-bar">
      <strong>计划消除日缺失（{{ board.missing_plan.length }} 条）：</strong>
      <span v-for="(row, index) in board.missing_plan" :key="String(row.id)">
        <RouterLink :to="`/defect/board?part=${encodePart(String(row['缺陷部位']))}`">{{ row['缺陷编号'] }}</RouterLink>
        （{{ row['缺陷部位'] }}）<span v-if="index < board.missing_plan.length - 1">、</span>
      </span>
      <span class="warn-hint">请补录计划消除日后再安排消缺</span>
    </div>

    <div class="board-toolbar">
      <div class="legend">
        <span>等级底色：</span>
        <i v-for="level in levels" :key="level" class="level-chip" :class="levelClass(level)">{{ level }}</i>
        <span class="legend-hint">待定级条目显示当前标准建议等级</span>
      </div>
      <button class="btn ghost" type="button" @click="toggleStandard">
        {{ showStandard ? '收起定级标准' : `定级标准 v${standardVersion}` }}
      </button>
    </div>

    <form v-if="showStandard" class="standard-panel" @submit.prevent="saveStandard">
      <p class="standard-tip">
        调整标准后立即按新口径重新判定全部缺陷的建议等级并升版；早先缺陷的历史定级结论仍按当初的取值保留。
        每行一个等级，关键词用英文逗号分隔，按「危急 → 严重 → 一般」顺序取第一个命中。
      </p>
      <label v-for="rule in draftRules" :key="rule.等级" class="standard-row">
        <i class="level-chip" :class="levelClass(rule.等级)">{{ rule.等级 }}</i>
        <input v-model="rule.关键词" placeholder="关键词，逗号分隔" />
      </label>
      <div class="standard-actions">
        <button class="btn primary" type="submit">保存并重新判定</button>
        <span v-if="standardMessage" :class="standardOk ? 'ok-text' : 'error-text'">{{ standardMessage }}</span>
      </div>
    </form>

    <div v-if="board" class="board-grid">
      <article
        v-for="zone in board.parts"
        :key="zone.部位"
        class="zone-card"
        :class="{ 'is-empty': zone.总数 === 0, 'is-active': activePart === zone.部位 }"
      >
        <header class="zone-head" role="button" tabindex="0" @click="openZone(zone.部位)" @keyup.enter="openZone(zone.部位)">
          <h3>{{ zone.部位 }}</h3>
          <span class="zone-total">{{ zone.总数 }}</span>
        </header>
        <div class="zone-counts">
          <span v-for="status in statuses" :key="status" class="zone-count">
            <em>{{ status }}</em><strong>{{ zone.counts[status] ?? 0 }}</strong>
          </span>
        </div>
        <div class="zone-levels">
          <i v-for="level in levels" :key="level" class="level-dot" :class="levelClass(level)">
            {{ level }} {{ zone.levels[level] ?? 0 }}
          </i>
        </div>
        <div v-if="zone.总数 === 0" class="zone-empty">该部位暂无缺陷，保留占位</div>
        <div v-else class="zone-upcoming">
          <p class="upcoming-title">计划消除日最近</p>
          <ul v-if="zone.upcoming.length">
            <li v-for="row in zone.upcoming" :key="String(row.id)">
              <i class="level-chip sm" :class="levelClass(displayLevel(row))">{{ displayLevel(row) }}</i>
              <span class="upcoming-no">{{ row['缺陷编号'] }}</span>
              <span class="upcoming-date" :class="{ overdue: isOverdue(String(row['计划消除日'])) }">
                {{ row['计划消除日'] }}{{ isOverdue(String(row['计划消除日'])) ? '（已逾期）' : '' }}
              </span>
            </li>
          </ul>
          <p v-else class="upcoming-none">未消除缺陷均未填写计划消除日</p>
          <p v-if="zone.missing_plan" class="upcoming-missing">另有 {{ zone.missing_plan }} 条缺失计划消除日</p>
        </div>
        <button class="btn sm btn-block" type="button" @click="openZone(zone.部位)">查看该部位缺陷</button>
      </article>
    </div>

    <section v-if="board" class="review-panel">
      <h3>待复核名单（{{ board.pending_review }}）</h3>
      <p v-if="!board.pending_review" class="review-empty">暂无待复核缺陷；验收退回的缺陷会写回这里，重新验收消除后自动摘除。</p>
      <table v-else class="data-table">
        <thead>
          <tr><th>缺陷编号</th><th>缺陷部位</th><th>退回原因</th><th>退回时间</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in reviews" :key="String(item.id)">
            <td>{{ item.缺陷编号 }}</td>
            <td>{{ item.缺陷部位 }}</td>
            <td>{{ item.退回原因 }}</td>
            <td>{{ item.退回时间 }}</td>
            <td><button class="link" type="button" @click="openZone(String(item.缺陷部位))">去分区查看</button></td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- 分区下钻抽屉：从看板展开该部位缺陷，处置完成后数字随动作实时刷新 -->
    <div v-if="drawerPart" class="drawer-mask" @click.self="closeDrawer">
      <aside class="drawer">
        <header class="drawer-head">
          <h3>{{ drawerPart }} · 缺陷清单（{{ drawerRows.length }}）</h3>
          <button class="link" type="button" @click="closeDrawer">退回看板</button>
        </header>
        <p v-if="drawerError" class="error-text">{{ drawerError }}</p>
        <ul v-if="drawerRows.length" class="drawer-list">
          <li v-for="row in drawerRows" :key="String(row.id)" class="defect-row">
            <div class="defect-main">
              <div class="defect-line">
                <i class="level-chip" :class="levelClass(displayLevel(row))">{{ displayLevel(row) }}</i>
                <strong>{{ row['缺陷编号'] }}</strong>
                <span class="defect-status status-tag" :class="`st-${row.status}`">{{ row.status }}</span>
                <span v-if="row.等级漂移" class="drift-tag" title="历史定级结论与当前标准建议不一致">标准已变</span>
              </div>
              <p class="defect-desc">{{ row['缺陷现象'] }}</p>
              <p class="defect-meta">
                {{ row['发现方式'] || '—' }} · 报告人 {{ row['报告人'] || '—' }} ·
                计划消除日
                <span :class="!row['计划消除日'] ? 'warn-text' : (isOverdue(String(row['计划消除日'])) ? 'overdue' : '')">
                  {{ row['计划消除日'] || '缺失，待补录' }}
                </span>
              </p>
              <p v-if="row.定级结论" class="defect-meta sub">
                历史定级：{{ row.定级结论 }}（v{{ row.标准版本 }} 口径）<template v-if="row.等级漂移">，当前标准建议 {{ row.建议等级 }}</template>
              </p>
            </div>
            <div class="defect-ops">
              <button
                v-for="action in actions"
                :key="action.name"
                class="btn sm"
                :class="action.cls"
                type="button"
                :disabled="!actionEnabled(row.status, action.name)"
                @click="executeAction(action.name, row)"
              >
                {{ action.name }}
              </button>
              <input
                v-if="returnTargetId === Number(row.id)"
                v-model="returnReason"
                class="return-input"
                placeholder="退回原因（可空）"
                @keyup.enter="confirmReturn(row)"
              />
              <button
                v-if="returnTargetId === Number(row.id)"
                class="link"
                type="button"
                @click="cancelReturn"
              >
                取消退回
              </button>
            </div>
          </li>
        </ul>
        <p v-else class="empty-state">该部位暂无缺陷</p>
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type BoardZone = {
  部位: string
  总数: number
  counts: Record<string, number>
  levels: Record<string, number>
  upcoming: DefectRow[]
  missing_plan: number
}
type DefectRow = Record<string, string | number | boolean | null> & { status: string }
type Board = {
  parts: BoardZone[]
  missing_plan: DefectRow[]
  standard: { version: number; rules: { 等级: string; 关键词: string }[] }
  pending_review: number
}
type Stats = Record<string, number>
type Review = Record<string, string | number>

const ENDPOINT = '/api/defect'
const statuses = ['待定级', '已定级', '处置中', '已消除']
const levels = ['危急', '严重', '一般']
const actions = [
  { name: '确认定级', cls: '' },
  { name: '提交消除', cls: '' },
  { name: '验收消除', cls: 'primary' },
  { name: '验收退回', cls: 'ghost' },
] as const

const route = useRoute()
const router = useRouter()

const board = ref<Board | null>(null)
const stats = ref<Stats>({})
const reviews = ref<Review[]>([])
const activePart = ref('')
const drawerPart = ref('')
const drawerRows = ref<DefectRow[]>([])
const drawerError = ref('')
const returnTargetId = ref<number | null>(null)
const returnReason = ref('')

const showStandard = ref(false)
const draftRules = ref<{ 等级: string; 关键词: string }[]>([])
const standardMessage = ref('')
const standardOk = ref(true)

const statCards = computed(() => [
  { label: '待定级', value: stats.value['待定级'] ?? 0, cls: '' },
  { label: '已定级', value: stats.value['已定级'] ?? 0, cls: '' },
  { label: '处置中', value: stats.value['处置中'] ?? 0, cls: '' },
  { label: '已消除', value: stats.value['已消除'] ?? 0, cls: '' },
  { label: '待复核', value: stats.value['待复核'] ?? 0, cls: 'warn-text' },
  { label: '今日消除数', value: stats.value['今日消除数'] ?? 0, cls: 'ok-text' },
])

const standardVersion = computed(() => board.value?.standard.version ?? '-')

function encodePart(part: string) {
  return encodeURIComponent(part)
}

function levelClass(level: string) {
  if (level === '危急') return 'lv-critical'
  if (level === '严重') return 'lv-serious'
  if (level === '一般') return 'lv-minor'
  return 'lv-pending'
}

function displayLevel(row: DefectRow): string {
  // 已定级及以后的缺陷按历史定级结论上色；待定级按当前标准建议（灰字提示）。
  const concluded = String(row['定级结论'] ?? '').trim()
  return concluded || String(row['建议等级'] ?? '一般')
}

function isOverdue(dateText: string) {
  if (!dateText) return false
  return dateText < new Date().toISOString().slice(0, 10)
}

function actionEnabled(status: string, action: string) {
  // 正在填写退回原因时，其他动作先收起，避免与退回确认并发。
  if (returnTargetId.value !== null) return action === '验收退回'
  if (action === '确认定级') return status === '待定级'
  if (action === '提交消除') return status === '已定级'
  return status === '处置中'
}

async function loadBoard() {
  const response = await request(`${ENDPOINT}/board`)
  if (!response.ok) throw new Error('缺陷分级看板读取失败')
  board.value = await response.json()
}

async function loadStats() {
  const response = await request(`${ENDPOINT}/stats`)
  if (response.ok) stats.value = await response.json()
}

async function loadReviews() {
  const response = await request(`${ENDPOINT}/reviews`)
  if (response.ok) {
    const payload = await response.json()
    reviews.value = payload.items ?? []
  }
}

async function refreshAll() {
  await Promise.all([loadBoard(), loadStats(), loadReviews()])
  if (drawerPart.value) await loadDrawer(drawerPart.value)
}

async function loadDrawer(part: string) {
  drawerError.value = ''
  try {
    const response = await request(`${ENDPOINT}?part=${encodePart(part)}&size=200`)
    if (!response.ok) throw new Error('该部位缺陷读取失败')
    const payload = await response.json()
    drawerRows.value = payload.items ?? []
  } catch (error) {
    drawerError.value = error instanceof Error ? error.message : '该部位缺陷读取失败'
  }
}

function openZone(part: string) {
  drawerPart.value = part
  activePart.value = part
  returnTargetId.value = null
  returnReason.value = ''
  router.replace({ path: route.path, query: { part } })
  void loadDrawer(part)
}

function closeDrawer() {
  drawerPart.value = ''
  activePart.value = ''
  returnTargetId.value = null
  router.replace({ path: route.path, query: {} })
}

async function executeAction(action: string, row: DefectRow) {
  if (action === '验收退回') {
    if (returnTargetId.value === Number(row.id)) {
      await confirmReturn(row)
    } else {
      returnTargetId.value = Number(row.id)
      returnReason.value = ''
    }
    return
  }
  returnTargetId.value = null
  drawerError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!response.ok || payload.ok === false) {
      drawerError.value = payload?.message || '缺陷动作未生效，请稍后重试'
      return
    }
    // 处置完成后看板数字、统计、待复核名单一起跟着变
    await refreshAll()
  } catch (error) {
    drawerError.value = error instanceof Error ? error.message : '缺陷动作未生效'
  }
}

function cancelReturn() {
  returnTargetId.value = null
  returnReason.value = ''
}

async function confirmReturn(row: DefectRow) {  drawerError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action: '验收退回', reason: returnReason.value } }),
    })
    const payload = await response.json()
    if (!response.ok || payload.ok === false) {
      drawerError.value = payload?.message || '退回未生效，请稍后重试'
      return
    }
    returnTargetId.value = null
    returnReason.value = ''
    // 退回后写回待复核名单，看板同步刷新
    await refreshAll()
  } catch (error) {
    drawerError.value = error instanceof Error ? error.message : '退回未生效'
  }
}

function toggleStandard() {
  if (!showStandard.value && board.value) {
    draftRules.value = board.value.standard.rules.map((rule) => ({ ...rule }))
  }
  showStandard.value = !showStandard.value
  standardMessage.value = ''
}

async function saveStandard() {
  standardMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/standard`, {
      method: 'PUT',
      body: JSON.stringify({ rules: draftRules.value }),
    })
    const payload = await response.json()
    standardOk.value = response.ok && payload.ok !== false
    if (!standardOk.value) {
      standardMessage.value = payload?.message || '定级标准保存失败'
      return
    }
    standardMessage.value = payload.message || '定级标准已更新'
    await refreshAll()
    if (board.value) draftRules.value = board.value.standard.rules.map((rule) => ({ ...rule }))
  } catch (error) {
    standardOk.value = false
    standardMessage.value = error instanceof Error ? error.message : '定级标准保存失败'
  }
}

onMounted(async () => {
  await refreshAll()
  const part = typeof route.query.part === 'string' ? route.query.part : ''
  if (part) openZone(part)
})
</script>

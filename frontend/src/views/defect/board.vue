<template>
  <section class="page board-page" data-module="defect-board">
    <header class="page-head">
      <div>
        <h2>缺陷分级看板</h2>
        <p class="page-desc">按缺陷部位分区，缺陷等级用底色区分；分区给出待定级、已定级、处置中、已消除数量与最近计划消除日。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" :to="listLink">返回缺陷列表</RouterLink>
        <button class="btn" type="button" @click="showStandard = !showStandard">定级标准</button>
        <button class="btn primary" type="button" @click="loadBoard">刷新看板</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="card in statCards" :key="card.label" class="stat-card" :class="card.cls">
        <span class="stat-label">{{ card.label }}</span>
        <strong class="stat-value">{{ card.value }}</strong>
      </article>
    </div>

    <p v-if="message" class="board-tip" :class="{ 'error-text': !messageOk }">{{ message }}</p>

    <!-- 定级标准：调整后全部早先缺陷按新标准重新判定，历史定级结论原样保留 -->
    <section v-if="showStandard" class="standard-panel">
      <header class="standard-head">
        <h3>定级标准</h3>
        <span class="page-desc">按关键字顺序匹配缺陷描述，命中即定级；都不命中时取默认等级。保存后早先登记的缺陷会重新判定，历史结论保留在「原级」标记里。</span>
      </header>
      <div v-for="(rule, index) in ruleDraft" :key="index" class="standard-row">
        <input v-model="rule.keyword" placeholder="关键字，如：裂纹" />
        <select v-model="rule.level">
          <option v-for="level in levels" :key="level" :value="level">{{ level }}</option>
        </select>
        <button class="link danger" type="button" @click="ruleDraft.splice(index, 1)">删除</button>
      </div>
      <div class="standard-row">
        <button class="btn" type="button" @click="ruleDraft.push({ keyword: '', level: '三级' })">新增关键字</button>
        <label class="default-level">默认等级
          <select v-model="defaultDraft">
            <option v-for="level in levels" :key="level" :value="level">{{ level }}</option>
          </select>
        </label>
        <button class="btn primary" type="button" @click="saveStandard">保存并重判</button>
        <button class="btn ghost" type="button" @click="resetStandardDraft">放弃修改</button>
      </div>
    </section>

    <!-- 等级图例 -->
    <div class="legend-row">
      <span v-for="level in levels" :key="level" class="level-badge" :class="levelClass(level)">{{ level }}</span>
      <span class="legend-note">底色随判定等级；与当初定级不一致时标注「原级」。</span>
    </div>

    <!-- 计划消除日缺失单独提示 -->
    <section v-if="board" class="notice-panel warn">
      <h3>计划消除日缺失（{{ board.missing_plan }} 条）</h3>
      <p v-if="!board.missing_plan" class="page-desc">暂无缺失计划消除日的缺陷。</p>
      <ul v-else class="notice-list">
        <li v-for="item in board.missing_plan_items" :key="item.id">
          <RouterLink :to="`/defect?part=${encodePart(item.缺陷部位)}&from=board`">{{ item.缺陷编号 }}</RouterLink>
          <span class="level-badge" :class="levelClass(item.缺陷等级)">{{ item.缺陷等级 }}</span>
          <span>{{ item.缺陷部位 }}</span>
          <em>计划消除日缺失，请尽快补录</em>
        </li>
      </ul>
    </section>

    <!-- 待复核名单：被退回的缺陷写回这里，复核确认后摘牌 -->
    <section v-if="board" class="notice-panel review">
      <h3>待复核名单（{{ board.review }} 条）</h3>
      <p v-if="!board.review" class="page-desc">暂无被退回、等待复核的缺陷。</p>
      <ul v-else class="notice-list">
        <li v-for="item in board.pending_review_items" :key="item.id">
          <RouterLink :to="`/defect?part=${encodePart(item.缺陷部位)}&from=board`">{{ item.缺陷编号 }}</RouterLink>
          <span class="level-badge" :class="levelClass(item.缺陷等级)">{{ item.缺陷等级 }}</span>
          <span>{{ item.缺陷部位 }}</span>
          <em>处置退回，等待复核</em>
          <button class="btn tiny" type="button" @click="runAction('复核确认', item)">复核确认</button>
        </li>
      </ul>
    </section>

    <!-- 分区看板 -->
    <div v-if="board" class="zone-grid">
      <article
        v-for="zone in board.zones"
        :key="zone.部位"
        class="zone-card"
        :class="{ 'zone-empty': zone.empty }"
      >
        <header class="zone-head" @click="toggleZone(zone.部位)">
          <h3>{{ zone.部位 }}</h3>
          <span class="zone-total">共 {{ zone.total }} 条</span>
          <span v-if="zone.review" class="review-flag">待复核 {{ zone.review }}</span>
          <span class="expand-mark">{{ expandedParts.has(zone.部位) ? '收起▲' : '展开▼' }}</span>
        </header>

        <template v-if="!zone.empty">
          <div class="count-row">
            <span v-for="status in statuses" :key="status" class="count-chip" :class="`st-${status}`">
              {{ status }}<strong>{{ zone.counts[status] ?? 0 }}</strong>
            </span>
          </div>
          <div class="level-line">
            <span v-for="level in levels" :key="level" :class="['level-dot', levelClass(level)]">
              {{ level }} {{ zone.levels[level] ?? 0 }}
            </span>
            <span v-if="zone.missing_plan" class="missing-flag">{{ zone.missing_plan }} 条缺计划日</span>
          </div>

          <div class="upcoming">
            <h4>最近计划消除</h4>
            <p v-if="!zone.upcoming.length" class="page-desc">未消除项均未排定计划消除日。</p>
            <ul>
              <li v-for="item in zone.upcoming" :key="item.id">
                <span class="level-badge" :class="levelClass(item.缺陷等级)">{{ item.缺陷等级 }}</span>
                <span class="item-code">{{ item.缺陷编号 }}</span>
                <span :class="{ 'overdue': item.overdue }">
                  {{ item.计划消除日 }}<i v-if="item.overdue">（已逾期）</i>
                </span>
              </li>
            </ul>
          </div>

          <div v-if="expandedParts.has(zone.部位)" class="zone-items">
            <h4>{{ zone.部位 }}的缺陷（{{ zone.total }}）</h4>
            <ul>
              <li v-for="item in zone.items" :key="item.id" class="defect-line" :class="levelClass(item.缺陷等级)">
                <div class="defect-main">
                  <span class="level-badge" :class="levelClass(item.缺陷等级)">{{ item.缺陷等级 }}</span>
                  <span
                    v-if="item.历史定级 && item.历史定级 !== item.缺陷等级"
                    class="history-tag"
                    :title="`定级标准调整前的结论：${item.历史定级}`"
                  >原{{ item.历史定级 }}</span>
                  <strong>{{ item.缺陷编号 }}</strong>
                  <span class="page-desc">{{ item.发现方式 || '发现方式未填' }}</span>
                  <span v-if="item.missing_plan" class="missing-text">计划消除日缺失</span>
                  <span v-else :class="{ 'overdue': item.overdue }">
                    计划 {{ item.计划消除日 }}<i v-if="item.overdue">（已逾期）</i>
                  </span>
                  <span v-if="item.待复核" class="review-flag">待复核</span>
                </div>
                <div class="defect-actions">
                  <button
                    v-for="action in actionsFor(item)"
                    :key="action"
                    class="link"
                    type="button"
                    @click="runAction(action, item)"
                  >{{ action }}</button>
                </div>
              </li>
            </ul>
          </div>
        </template>

        <p v-else class="zone-placeholder">该部位暂无缺陷，保留分区占位</p>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { request } from '@/api/client'

type BoardItem = {
  id: number
  缺陷编号: string
  缺陷部位: string
  缺陷等级: string
  历史定级: string
  status: string
  缺陷状态: string
  发现方式: string | null
  发现时间: string | null
  报告人: string | null
  计划消除日: string | null
  missing_plan: boolean
  overdue: boolean
  待复核: boolean
}

type Zone = {
  部位: string
  total: number
  counts: Record<string, number>
  review: number
  missing_plan: number
  levels: Record<string, number>
  upcoming: BoardItem[]
  items: BoardItem[]
  empty: boolean
}

type StandardRule = { keyword: string; level: string }

type Board = {
  parts: string[]
  zones: Zone[]
  counts: Record<string, number>
  levels: Record<string, number>
  total: number
  review: number
  missing_plan: number
  eliminated_today: number
  pending_review_items: BoardItem[]
  missing_plan_items: BoardItem[]
  standard: { default: string; rules: StandardRule[] }
}

const ENDPOINT = '/api/defect'
const statuses = ['待定级', '已定级', '处置中', '已消除']
const levels = ['一级', '二级', '三级', '四级']

const route = useRoute()
const board = ref<Board | null>(null)
const message = ref('')
const messageOk = ref(true)
const expandedParts = ref<Set<string>>(new Set())
const showStandard = ref(false)
const ruleDraft = ref<StandardRule[]>([])
const defaultDraft = ref('三级')

const focusPart = computed(() => {
  const part = route.query.part
  return typeof part === 'string' ? part : ''
})

const listLink = computed(() =>
  focusPart.value ? `/defect?part=${encodeURIComponent(focusPart.value)}&from=board` : '/defect?from=board',
)

const statCards = computed(() => {
  const counts = board.value?.counts ?? {}
  return [
    { label: '待定级缺陷', value: counts['待定级'] ?? 0, cls: 'st-card-待定级' },
    { label: '已定级缺陷', value: counts['已定级'] ?? 0, cls: 'st-card-已定级' },
    { label: '处置中缺陷', value: counts['处置中'] ?? 0, cls: 'st-card-处置中' },
    { label: '已消除缺陷', value: counts['已消除'] ?? 0, cls: 'st-card-已消除' },
    { label: '待复核', value: board.value?.review ?? 0, cls: 'st-card-review' },
    { label: '今日消除', value: board.value?.eliminated_today ?? 0, cls: '' },
  ]
})

function levelClass(level: string): string {
  return `lv-${level.replace('级', '')}`
}

function encodePart(part: string): string {
  return encodeURIComponent(part)
}

function toggleZone(part: string) {
  const next = new Set(expandedParts.value)
  if (next.has(part)) {
    next.delete(part)
  } else {
    next.add(part)
  }
  expandedParts.value = next
}

function actionsFor(item: BoardItem): string[] {
  if (item.status === '待定级') return ['确认定级']
  if (item.status === '已定级') return ['提交消除']
  if (item.status === '处置中') {
    return item.待复核 ? ['复核确认', '验收消除', '退回'] : ['验收消除', '退回']
  }
  if (item.status === '已消除') return ['退回']
  return []
}

function resetStandardDraft() {
  if (!board.value) return
  ruleDraft.value = board.value.standard.rules.map((rule) => ({ ...rule }))
  defaultDraft.value = board.value.standard.default
}

async function saveStandard() {
  message.value = ''
  try {
    const response = await request(`${ENDPOINT}/standard`, {
      method: 'PUT',
      body: JSON.stringify({ rules: ruleDraft.value, default: defaultDraft.value }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload?.message || '定级标准未生效')
    }
    messageOk.value = true
    message.value = payload.message
    await loadBoard()
  } catch (error) {
    messageOk.value = false
    message.value = error instanceof Error ? error.message : '定级标准保存失败'
  }
}

async function runAction(action: string, item: BoardItem) {
  message.value = ''
  try {
    const response = await request(`${ENDPOINT}/${item.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload?.message || '动作未生效，请稍后重试')
    }
    messageOk.value = true
    message.value = payload.message
    await loadBoard()
  } catch (error) {
    messageOk.value = false
    message.value = error instanceof Error ? error.message : '缺陷操作失败'
  }
}

async function loadBoard() {
  try {
    const response = await request(`${ENDPOINT}/board`)
    if (!response.ok) {
      throw new Error('缺陷分级看板读取失败')
    }
    board.value = (await response.json()) as Board
    resetStandardDraft()
  } catch (error) {
    messageOk.value = false
    message.value = error instanceof Error ? error.message : '缺陷分级看板读取失败'
  }
}

onMounted(async () => {
  await loadBoard()
  // 从缺陷列表页带部位进来时，自动展开对应分区。
  if (focusPart.value) {
    expandedParts.value = new Set([focusPart.value])
  }
})
</script>

<style scoped>
.board-page .stat-card { border-left-width: 4px; border-left-style: solid; }
.st-card-待定级 { border-left-color: #d97706; }
.st-card-已定级 { border-left-color: #2563eb; }
.st-card-处置中 { border-left-color: #7c3aed; }
.st-card-已消除 { border-left-color: #16a34a; }
.st-card-review { border-left-color: #dc2626; }

.board-tip { font-size: 13px; margin: 0 0 10px; }

.legend-row { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; font-size: 12px; }
.legend-note { color: var(--muted); }

.level-badge { display: inline-block; border-radius: 4px; padding: 1px 8px; font-size: 12px; border: 1px solid transparent; }
.lv-1 { background: #fee2e2; color: #991b1b; border-color: #fca5a5; }
.lv-2 { background: #ffedd5; color: #9a3412; border-color: #fdba74; }
.lv-3 { background: #fef9c3; color: #854d0e; border-color: #fde047; }
.lv-4 { background: #dcfce7; color: #166534; border-color: #86efac; }

.notice-panel { background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 10px 14px; margin-bottom: 12px; }
.notice-panel h3, .upcoming h4, .zone-items h4 { margin: 0 0 6px; font-size: 14px; }
.notice-panel.warn { border-color: #f59e0b; background: #fffbeb; }
.notice-panel.review { border-color: #ef4444; background: #fef2f2; }
.notice-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.notice-list li { display: flex; align-items: center; gap: 10px; font-size: 13px; }
.notice-list em { color: #b45309; font-style: normal; }
.notice-panel.review em { color: #b91c1c; }
.btn.tiny { padding: 2px 8px; font-size: 12px; }

.standard-panel { background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; margin-bottom: 12px; }
.standard-head h3 { margin: 0 0 4px; font-size: 14px; }
.standard-row { display: flex; gap: 8px; align-items: center; margin-top: 8px; }
.standard-row input { flex: 0 1 220px; padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; }
.standard-row select, .default-level select { padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; }
.default-level { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--muted); }
.link.danger { color: #b42318; }

.zone-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; }
.zone-card { background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; }
.zone-card.zone-empty { border-style: dashed; background: #fafbfd; }
.zone-head { display: flex; align-items: center; gap: 8px; cursor: pointer; }
.zone-head h3 { margin: 0; font-size: 15px; }
.zone-total { color: var(--muted); font-size: 12px; }
.expand-mark { margin-left: auto; color: var(--brand); font-size: 12px; }
.review-flag { background: #fee2e2; color: #b91c1c; border-radius: 4px; padding: 0 6px; font-size: 12px; }
.zone-placeholder { color: var(--muted); font-size: 13px; margin: 10px 0 0; }

.count-row { display: flex; gap: 6px; margin: 10px 0 6px; flex-wrap: wrap; }
.count-chip { display: flex; flex-direction: column; align-items: center; flex: 1; border-radius: 6px; padding: 4px 0; font-size: 12px; border: 1px solid var(--border); background: #f8fafc; }
.count-chip strong { font-size: 16px; }
.st-待定级 { color: #b45309; }
.st-已定级 { color: #1d4ed8; }
.st-处置中 { color: #6d28d9; }
.st-已消除 { color: #15803d; }

.level-line { display: flex; gap: 10px; align-items: center; font-size: 12px; flex-wrap: wrap; }
.level-dot { border-radius: 4px; padding: 0 6px; }
.missing-flag { color: #b45309; }

.upcoming { margin-top: 8px; }
.upcoming ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.upcoming li { display: flex; gap: 8px; align-items: center; font-size: 12px; }
.item-code { min-width: 76px; }
.overdue { color: #b42318; }
.overdue i { font-style: normal; }

.zone-items { margin-top: 10px; border-top: 1px dashed var(--border); padding-top: 8px; }
.zone-items ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.defect-line { display: flex; justify-content: space-between; gap: 8px; align-items: center; border-radius: 6px; padding: 6px 8px; border: 1px solid var(--border); }
.defect-line.lv-1 { background: #fef2f2; }
.defect-line.lv-2 { background: #fff7ed; }
.defect-line.lv-3 { background: #fefce8; }
.defect-line.lv-4 { background: #f0fdf4; }
.defect-main { display: flex; align-items: center; gap: 8px; font-size: 12px; flex-wrap: wrap; }
.defect-actions { display: flex; gap: 8px; flex-shrink: 0; }
.history-tag { background: #e2e8f0; color: #475569; border-radius: 4px; padding: 0 6px; font-size: 12px; }
.missing-text { color: #b45309; font-weight: 600; }
</style>

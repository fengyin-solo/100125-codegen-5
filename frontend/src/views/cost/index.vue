<template>
  <section class="page" data-module="cost">
    <header class="page-head">
      <div>
        <h2>运输费用管理</h2>
        <p class="page-desc">维护费用记录，围绕费用编号、关联任务、费用类别、费用金额做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记费用记录</button>
        <button class="btn" type="button" @click="exportRows">导出费用台账</button>
        <button class="btn" type="button" @click="triggerImport">导入费用台账</button>
        <input
          ref="fileInput"
          type="file"
          accept=".csv,text/csv"
          hidden
          @change="handleFile"
        />
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <section v-if="importResult" class="import-result">
      <h3>导入结果</h3>
      <p :class="{ 'error-text': !importResult.ok }">{{ importResult.message }}</p>
      <ul v-if="importResult.skipped.length">
        <li v-for="item in importResult.skipped" :key="item.row">
          第 {{ item.row }} 行：{{ item.reason }}
        </li>
      </ul>
    </section>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>费用编号</span>
        <input v-model="filters.keyword" placeholder="按费用编号检索" />
      </label>
      <label class="filter-item">
        <span>关联任务</span>
        <input v-model="filters.task" placeholder="按关联任务检索" />
      </label>
      <label class="filter-item">
        <span>费用类别</span>
        <input v-model="filters.category" placeholder="按费用类别检索" />
      </label>
      <label class="filter-item">
        <span>费用状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>费用日期起</span>
        <input v-model="filters.date_from" type="date" />
      </label>
      <label class="filter-item">
        <span>费用日期止</span>
        <input v-model="filters.date_to" type="date" />
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
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
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
          <td :colspan="columns.length + 1" class="empty-state">暂无运输费用数据，可先登记费用记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条运输费用记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type Filters = {
  keyword: string
  task: string
  category: string
  status: string
  date_from: string
  date_to: string
}
type ImportResponse = {
  ok: boolean
  message: string
  updated: number
  created: number
  skipped: { row: number; reason: string }[]
}

const ENDPOINT = '/api/cost'
const columns = ["费用编号", "关联任务", "费用类别", "费用金额", "费用日期", "录入人员", "凭证编号", "费用状态"]
const actions = ["录入费用", "审核费用", "结算费用"]
// 待核销是批量导入补登记录的初始状态，也能作为筛选条件查到。
const statuses = ["待核销", "待录入", "待审核", "已审核", "已结算"]
const stats = [{"label": "待录入费用", "value": 0}, {"label": "待审核费用", "value": 0}, {"label": "已结算费用", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const importResult = ref<ImportResponse | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const filters = ref<Filters>({
  keyword: '',
  task: '',
  category: '',
  status: '',
  date_from: '',
  date_to: '',
})

function buildQuery(): string {
  const params = new URLSearchParams()
  Object.entries(filters.value).forEach(([key, value]) => {
    if (value) {
      params.set(key, value)
    }
  })
  const query = params.toString()
  return query ? `?${query}` : ''
}

function resetFilters() {
  filters.value = { keyword: '', task: '', category: '', status: '', date_from: '', date_to: '' }
  void reload()
}

// 导出按当前筛选条件走，浏览器拿到带文件名的 CSV 直接落盘。
function exportRows() {
  window.open(`${ENDPOINT}/export${buildQuery()}`, '_blank')
}

function triggerImport() {
  errorMessage.value = ''
  fileInput.value?.click()
}

async function handleFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) {
    return
  }
  errorMessage.value = ''
  importResult.value = null
  try {
    const content = await file.text()
    const response = await request(`${ENDPOINT}/import`, {
      method: 'POST',
      body: JSON.stringify({ filename: file.name, content }),
    })
    const payload = (await response.json()) as ImportResponse
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '费用台账导入失败，数据未更新')
    }
    importResult.value = payload
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '费用台账导入失败'
  } finally {
    // 允许同名文件再次选择时仍触发 change
    input.value = ''
  }
}

function openCreate() {
  errorMessage.value = '费用记录登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('运输费用动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '运输费用操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}${buildQuery()}`)
    if (!response.ok) {
      throw new Error('费用记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '运输费用列表读取失败'
  }
}

onMounted(reload)
</script>

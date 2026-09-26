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
        <button class="btn" type="button" :disabled="importing" @click="triggerImport">
          {{ importing ? '导入中…' : '导入费用台账' }}
        </button>
        <input ref="fileInput" class="file-input" type="file" accept=".csv,text/csv" @change="importRows" />
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

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
        <span>核销状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div v-if="importResult" class="import-panel" :class="{ failed: !importResult.ok }">
      <p class="import-summary">
        <strong>{{ importResult.ok ? importResult.message : '导入失败' }}</strong>
        <template v-if="importResult.ok">
          （更新 {{ importResult.updated }} 条，补登记 {{ importResult.created }} 条，跳过 {{ importResult.skipped.length }} 行）
        </template>
        <button class="link" type="button" @click="importResult = null">关闭</button>
      </p>
      <ul v-if="importResult.skipped.length" class="skip-list">
        <li v-for="item in importResult.skipped" :key="item.line">
          第 {{ item.line }} 行：{{ item.reason }}
        </li>
      </ul>
      <p v-if="!importResult.ok" class="error-text">{{ importResult.message }}</p>
    </div>

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
type SkippedRow = { line: number; reason: string }
type ImportResultState = {
  ok: boolean
  message: string
  updated: number
  created: number
  skipped: SkippedRow[]
}

const ENDPOINT = '/api/cost'
const columns = ["费用编号", "关联任务", "费用类别", "费用金额", "费用日期", "录入人员", "凭证编号", "费用状态"]
const actions = ["录入费用", "审核费用", "结算费用"]
const statuses = ["待录入", "待审核", "已审核", "已结算", "待核销"]
const stats = [{"label": "待录入费用", "value": 0}, {"label": "待审核费用", "value": 0}, {"label": "已结算费用", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const importing = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const importResult = ref<ImportResultState | null>(null)
const filters = ref<Record<string, string>>({
  keyword: '',
  task: '',
  category: '',
  status: '',
})

function resetFilters() {
  filters.value = { keyword: '', task: '', category: '', status: '' }
  void reload()
}

function buildQuery() {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters.value)) {
    if (value.trim()) {
      params.set(key, value.trim())
    }
  }
  const query = params.toString()
  return query ? `?${query}` : ''
}

function exportRows() {
  // 导出严格跟随当前筛选条件；后端返回带 BOM 的 CSV，浏览器直接落盘。
  window.open(`${ENDPOINT}/export${buildQuery()}`, '_blank')
}

function triggerImport() {
  importResult.value = null
  fileInput.value?.click()
}

async function importRows(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) {
    return
  }
  if (!file.name.toLowerCase().endsWith('.csv')) {
    importResult.value = {
      ok: false,
      message: '仅支持导入 CSV 格式的费用台账文件，请先导出模板再修改',
      updated: 0,
      created: 0,
      skipped: [],
    }
    return
  }

  importing.value = true
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'text/csv; charset=utf-8' },
      body: await file.text(),
    })
    const payload = await response.json()
    if (!response.ok) {
      // 文件整体不合规：后端没有写入任何数据。
      importResult.value = {
        ok: false,
        message: payload.detail ?? '台账文件格式不对，已整批作废，未写入任何数据',
        updated: 0,
        created: 0,
        skipped: [],
      }
      return
    }
    importResult.value = {
      ok: true,
      message: payload.message ?? '导入完成',
      updated: payload.updated ?? 0,
      created: payload.created ?? 0,
      skipped: payload.skipped ?? [],
    }
    await reload()
  } catch (error) {
    importResult.value = {
      ok: false,
      message: error instanceof Error ? error.message : '运输费用台账导入失败',
      updated: 0,
      created: 0,
      skipped: [],
    }
  } finally {
    importing.value = false
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

<style scoped>
.file-input {
  display: none;
}

.import-panel {
  margin: 12px 0;
  padding: 12px 16px;
  border: 1px solid #b7d5b1;
  border-radius: 8px;
  background: #f2f9f0;
}

.import-panel.failed {
  border-color: #e0a5a5;
  background: #fdf1f1;
}

.import-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0;
}

.skip-list {
  margin: 8px 0 0;
  padding-left: 20px;
  color: #8a6d3b;
}
</style>

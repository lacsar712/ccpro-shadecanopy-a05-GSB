<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import api from '../api'

const list = ref([])
const zones = ref([])
const error = ref('')
const filterZoneId = ref('')

function localInputValue(d = new Date()) {
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const form = reactive({
  zoneId: '',
  toCrop: '',
  transplantedAt: localInputValue(),
  operator: '',
  notes: '',
})

const selectedZone = computed(
  () => zones.value.find((z) => z.id === Number(form.zoneId)) || null
)
const notesRequired = computed(() => selectedZone.value?.status === 'idle')

function resetForm() {
  form.zoneId = zones.value[0]?.id || ''
  form.toCrop = ''
  form.transplantedAt = localInputValue()
  form.operator = ''
  form.notes = ''
}

async function loadZones() {
  const { data } = await api.get('/zones/')
  zones.value = data.results || data
  if (!form.zoneId && zones.value.length) form.zoneId = zones.value[0].id
}

async function load() {
  error.value = ''
  try {
    const params = {}
    if (filterZoneId.value) params.zoneId = filterZoneId.value
    const { data } = await api.get('/transplant-events/', { params })
    list.value = data.results || data
  } catch {
    error.value = '加载移栽事件失败'
  }
}

async function save() {
  error.value = ''
  if (!form.toCrop.trim()) {
    error.value = '新作物不能为空'
    return
  }
  if (!form.operator.trim()) {
    error.value = '操作人不能为空'
    return
  }
  if (notesRequired.value && !form.notes.trim()) {
    error.value = '空闲分区移栽时备注必填'
    return
  }
  const payload = {
    zoneId: Number(form.zoneId),
    toCrop: form.toCrop.trim(),
    transplantedAt: new Date(form.transplantedAt).toISOString(),
    operator: form.operator.trim(),
    notes: form.notes.trim(),
  }
  try {
    // 只有这条接口能改作物名：服务端同事务回写分区作物 + 写气候记录
    await api.post('/transplant-events/', payload)
    resetForm()
    await load()
  } catch (e) {
    if (e.response?.status === 409) {
      error.value =
        typeof e.response.data?.detail === 'string'
          ? e.response.data.detail
          : '冲突：该分区移栽时刻前后 60 分钟内已有移栽，或落入移栽窗口'
    } else {
      error.value = JSON.stringify(e.response?.data || '移栽失败')
    }
  }
}

onMounted(async () => {
  await loadZones()
  await load()
})
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>移栽换茬事件</h1>
        <p>
          事件挂分区；创建后服务端同事务更新分区作物名并写一条气候记录（湿度默认 70%）。
          同分区移栽时刻前后 60 分钟内禁止重复移栽（409），窗口内禁止新建轮灌。
        </p>
      </div>
      <div class="actions">
        <select v-model="filterZoneId" @change="load">
          <option value="">全部分区</option>
          <option v-for="z in zones" :key="z.id" :value="z.id">
            {{ z.greenhouseName }} / {{ z.zoneCode }}
          </option>
        </select>
      </div>
    </div>

    <div class="panel">
      <h3 style="margin-top:0">新建移栽事件</h3>
      <div class="form-grid">
        <label>
          所属分区
          <select v-model="form.zoneId">
            <option v-for="z in zones" :key="z.id" :value="z.id">
              {{ z.greenhouseName }} / {{ z.zoneCode }}（当前：{{ z.cropName || '无作物' }}）
            </option>
          </select>
        </label>
        <label>新作物（必填）<input v-model="form.toCrop" required /></label>
        <label>移栽时刻<input v-model="form.transplantedAt" type="datetime-local" /></label>
        <label>操作人（必填）<input v-model="form.operator" required /></label>
        <label class="full">
          备注<span v-if="notesRequired" class="error" style="display:inline">（空闲分区必填）</span>
          <textarea v-model="form.notes" rows="2"></textarea>
        </label>
      </div>
      <p v-if="selectedZone?.status === 'fallow'" class="error">
        休耕分区禁止移栽，请改选其他分区。
      </p>
      <p v-if="error" class="error">{{ error }}</p>
      <div class="actions" style="margin-top:12px">
        <button class="btn" @click="save">登记移栽</button>
      </div>
    </div>

    <div class="panel">
      <table>
        <thead>
          <tr>
            <th>移栽时刻</th>
            <th>温室/分区</th>
            <th>原作物</th>
            <th>新作物</th>
            <th>操作人</th>
            <th>备注</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in list" :key="row.id">
            <td>{{ new Date(row.transplantedAt).toLocaleString() }}</td>
            <td>{{ row.greenhouseName }} / {{ row.zoneCode }}</td>
            <td>{{ row.fromCrop || '—' }}</td>
            <td>{{ row.toCrop }}</td>
            <td>{{ row.operator }}</td>
            <td>{{ row.notes || '—' }}</td>
          </tr>
          <tr v-if="!list.length">
            <td colspan="6" style="color:var(--muted)">暂无移栽事件</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

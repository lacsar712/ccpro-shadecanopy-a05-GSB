<script setup>
import { onMounted, reactive, ref } from 'vue'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
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
  transplantedAt: localInputValue(),
  newCrop: '',
  operator: auth.user?.username || '',
  notes: '',
})

function selectedZone() {
  return zones.value.find((z) => z.id === Number(form.zoneId))
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

function resetForm() {
  form.transplantedAt = localInputValue()
  form.newCrop = ''
  form.notes = ''
}

async function save() {
  error.value = ''
  const payload = {
    zoneId: Number(form.zoneId),
    transplantedAt: new Date(form.transplantedAt).toISOString(),
    newCrop: form.newCrop,
    operator: form.operator,
    notes: form.notes,
  }
  try {
    await api.post('/transplant-events/', payload)
    resetForm()
    await Promise.all([load(), loadZones()])
  } catch (e) {
    if (e.response?.status === 409) {
      error.value = e.response?.data?.detail || '与该分区 60 分钟内的移栽事件冲突（409）'
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
        <h1>移栽事件</h1>
        <p>挂在分区上的换茬记录；成功后由服务端改作物名并补写一条气候记录</p>
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
      <h3 style="margin-top:0">登记移栽</h3>
      <div class="form-grid">
        <label>
          所属分区
          <select v-model="form.zoneId">
            <option v-for="z in zones" :key="z.id" :value="z.id">
              {{ z.greenhouseName }} / {{ z.zoneCode }}（{{ z.cropName || '空地' }}）
            </option>
          </select>
        </label>
        <label>
          原作物
          <input :value="selectedZone()?.cropName || '（空）'" disabled />
        </label>
        <label>新作物<input v-model="form.newCrop" required placeholder="必填" /></label>
        <label>移栽时刻<input v-model="form.transplantedAt" type="datetime-local" /></label>
        <label>操作人<input v-model="form.operator" required /></label>
        <label class="full">
          备注（空闲分区移栽时必填）
          <textarea v-model="form.notes" rows="2"></textarea>
        </label>
      </div>
      <p class="hint" style="margin:10px 0 0">
        规则：休耕分区禁止移栽；空闲分区移栽需填备注且移栽后进入在种；同分区移栽时刻前后 60
        分钟内不可重复移栽，且该窗口内禁止新建轮灌（冲突返回 409）。
      </p>
      <p v-if="error" class="error">{{ error }}</p>
      <div class="actions" style="margin-top:12px">
        <button class="btn" @click="save">提交移栽</button>
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
            <td>{{ row.previousCrop || '—' }}</td>
            <td>{{ row.newCrop }}</td>
            <td>{{ row.operator }}</td>
            <td>{{ row.notes || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

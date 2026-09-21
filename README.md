# ShadeCanopy-01 · 分区气候日志与轮灌计划

温室「分区气候日志与轮灌计划」全栈种子项目（非考勤 OA、非库存）。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python Django 5 · Django REST Framework · SimpleJWT · django-cors-headers · Gunicorn |
| 前端 | Vue 3 · Vite · Pinia · Vue Router |
| 数据库 | PostgreSQL 15 |
| 部署 | Docker Compose · Nginx（前端容器反代 `/api` → Django） |

## 路径与端口

- **项目路径**：`D:\work\document\bytecode\claudeCodePro\ShadeCanopy\ShadeCanopy-01\`
- **前端**：http://localhost:3500
- **后端 API**：http://localhost:8500（也可经前端同源 `/api` 访问）
- **PostgreSQL**：localhost:5435

## 演示账号

| 用户名 | 密码 | 角色 |
| --- | --- | --- |
| `admin` | `123456` | admin（管理员，可进 Django Admin） |
| `grower` | `123456` | grower（种植员） |

启动时 `entrypoint.sh` 会执行 `migrate` + `seed_data` 自动写入账号与示例业务数据。

## 快速启动

```bash
cd D:\work\document\bytecode\claudeCodePro\ShadeCanopy\ShadeCanopy-01
docker compose up --build
```

浏览器打开 http://localhost:3500 ，使用 `grower` / `123456` 登录。

停止：

```bash
docker compose down
```

## 业务模块

1. **Auth**：JWT `POST /api/auth/token/`，当前用户 `GET /api/auth/me/`
2. **Greenhouse**：name / location / areaM2 / notes
3. **Zone**：greenhouseId / zoneCode / ~~cropName（只读）~~ / status(`idle|growing|fallow`)；同温室 zoneCode 唯一。**作物名不能在分区接口里直接修改，只能通过移栽换茬事件由服务端回写**
4. **ClimateLog**：zoneId / recordedAt / tempC / humidityPct / parUmol / co2Ppm；**humidityPct ∈ [20, 100]**
5. **IrrigationCycle**：zoneId / startAt / durationMin / waterLiters / status(`scheduled|running|done|skipped`)；**起灌时刻落入该区任一移栽事件前后 60 分钟窗口时禁止新建（409）**
6. **TransplantEvent（移栽换茬）**：zoneId / fromCrop（服务端取分区当前作物名）/ toCrop（非空）/ transplantedAt / operator / notes（可空）；创建后在**同一数据库事务**内完成：
   - 写移栽事件；
   - 把分区 `cropName` 改成新作物；
   - 写一条气候记录：`recordedAt = transplantedAt`，**湿度取默认值 70%（默认值约定在 60～80 之间，见 `core/services.py` 的 `TRANSPLANT_DEFAULT_HUMIDITY`）**，温度默认 24℃。
   只写事件、只改作物名或只写气候记录都不会发生（事务整体回滚）。
   - **冲突规则**：同一分区在移栽时刻前后 **60 分钟**内不得有第二条移栽，冲突返回 **409**；
   - 该 60 分钟窗口与轮灌拦截**共用同一时间窗函数** `core.services.window_events_qs`；
   - **休耕（fallow）分区禁止移栽**；**空闲（idle）分区允许移栽但备注必填**；空闲分区移栽后自动转为在种，**在种分区移栽后仍保持在种**。
   - 分区列表每行同源返回 `lastTransplantAt` 与 `inTransplantWindow`（与看板计数共用 `annotate_zone_window`，看板「处于移栽窗口分区」数 = 列表 `inTransplantWindow=true` 行数）。
7. **Dashboard**：温室数、growing 分区数、近 24h 气候日志数、今日 scheduled 轮灌数、处于移栽窗口分区数 → `GET /api/dashboard/`

## API 一览

| 方法 | 路径 |
| --- | --- |
| POST | `/api/auth/token/` |
| POST | `/api/auth/token/refresh/` |
| GET | `/api/auth/me/` |
| CRUD | `/api/greenhouses/` |
| CRUD | `/api/zones/?greenhouseId=&status=` |
| CRUD | `/api/climate-logs/?zoneId=` |
| CRUD | `/api/irrigation-cycles/?zoneId=&status=` |
| CRUD | `/api/transplant-events/?zoneId=`（移栽换茬，仅创建有事务副作用） |
| GET | `/api/dashboard/` |

字段对外使用 camelCase（如 `areaM2`、`zoneCode`、`humidityPct`）。

## 本地开发（可选）

**后端**（需本机 Postgres 或已启动 compose 中的 db）：

```bash
cd backend
pip install -r requirements.txt
set POSTGRES_HOST=127.0.0.1
set POSTGRES_PORT=5435
python manage.py migrate
python manage.py seed_data
python manage.py runserver 0.0.0.0:8500
```

**前端**：

```bash
cd frontend
npm install
npm run dev
```

Vite 已将 `/api` 代理到 `http://127.0.0.1:8500`。

## 目录结构

```
ShadeCanopy-01/
├── docker-compose.yml
├── README.md
├── .gitignore
├── backend/
│   ├── Dockerfile
│   ├── entrypoint.sh      # migrate + seed + gunicorn
│   ├── requirements.txt
│   ├── manage.py
│   ├── config/            # settings / urls
│   ├── accounts/          # 自定义 User + role
│   └── core/              # 温室/分区/气候/轮灌/移栽事件 + services 时间窗 + seed_data
└── frontend/
    ├── Dockerfile
    ├── nginx.conf         # 静态资源 + /api 反代
    ├── package.json
    └── src/               # Vue 页面（叶绿/土色主题）
```

## 配色说明

前端采用叶绿（`#3d6b3a`）与土色（`#8b6b45`）主色，米色底与侧栏深绿渐变，贴近温室场景。

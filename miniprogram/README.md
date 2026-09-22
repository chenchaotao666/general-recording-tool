# 通用记录工具 · 小程序端

基于 uni-app（Vue3 + Vite）开发的微信小程序，复用后端全部 API。一套代码后续也可编译为 App。

## 功能

| 底部 Tab | 内容 |
|---|---|
| 数据 | 数据表列表（长按删除）、**新建数据表**（手动建表 / **Excel 导入向导**：选文件 → AI 分析结构 → 确认字段 → 建表并导入）、记录列表（卡片式、加载更多）、新增/编辑记录（动态表单 + **拍照/相册智能识别填表**） |
| 报表 | 模板列表、报表详情（时间口径切换、统计卡片、柱状/折线/饼图、明细表）、**新建/编辑报表**（时间口径、区块拼装：统计卡片/图表/明细表/文本、筛选、定时推送，支持 **AI 生成**） |
| 任务 | 任务列表、启用开关、试运行 / 立即执行、**新建/编辑任务**（结构化条件构建器 / LLM 判断、周期、动作、冷却期，支持 **AI 生成**） |
| 通知 | 通知列表、点击已读并跳转数据表、全部已读 |
| 设置 | **大模型供应商管理**（增删改、测试、设默认）、**SMTP 配置**（含发送测试邮件）、短信网关配置 |

功能与 Web 端对齐；Excel 导入通过「从聊天文件中选择」选取 .xlsx/.csv 文件。

## 运行方式（开发）

### 1. 启动后端（必须监听局域网）

```bash
cd backend
uvicorn app.main:app --reload --port 8000 --host 0.0.0.0
```

> ⚠️ 不加 `--host 0.0.0.0` 时 uvicorn 只监听 127.0.0.1，手机和模拟器都访问不到。

### 2. 配置后端地址

编辑 `src/config.js`，把 `BASE_URL` 改为电脑的局域网 IP（手机/模拟器要能访问到）：

```js
export const BASE_URL = 'http://192.168.43.4:8000'
```

查看本机 IP：Windows 用 `ipconfig` 看 WLAN 的 IPv4 地址。换网络环境（如换 WiFi）后 IP 可能变化，需要更新。

### 3. 启动编译

```bash
cd miniprogram
npm install        # 首次
npm run dev:mp-weixin
```

编译产物输出到 `dist/dev/mp-weixin`（改代码自动重新编译）。一次性构建用 `npm run build:mp-weixin`（输出到 `dist/build/mp-weixin`）。

### 4. 微信开发者工具

1. 下载安装[微信开发者工具](https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html)（稳定版即可）
2. **导入项目**：选择 `miniprogram/dist/dev/mp-weixin` 目录
3. **AppID**：开发阶段点"测试号"即可，不用注册小程序
4. **关闭域名校验**：右上角「详情」→「本地设置」→ 勾选 **「不校验合法域名、web-view（业务域名）、TLS 版本以及 HTTPS 证书」**

### 5. 真机预览

开发者工具点「预览」生成二维码，手机微信扫码即可。

- 手机需与电脑连接**同一 WiFi**
- 请求不通时检查：后端是否带 `--host 0.0.0.0` 启动、`src/config.js` 的 IP 是否正确、Windows 防火墙是否放行 8000 端口（控制面板 → Windows Defender 防火墙 → 入站规则）

## 正式发布（需要时）

微信小程序正式环境**强制要求**：服务器公网可访问 + **HTTPS** + **已备案域名**，并在小程序后台「开发管理 → 服务器域名」中配置 `request 合法域名`。

1. 后端部署到云服务器，前置 Nginx/Caddy 终结 HTTPS
2. `src/config.js` 改为 `https://你的域名`
3. `npm run build:mp-weixin`，在微信开发者工具中上传 `dist/build/mp-weixin`
4. 到微信公众平台提交审核发布

## 目录结构

```
miniprogram/
├── src/
│   ├── config.js            # 后端地址（仅此一处需要按环境修改）
│   ├── api/index.js         # API 封装（uni.request，与后端 /api 对应）
│   ├── pages.json           # 页面与 TabBar 配置
│   ├── manifest.json        # 应用配置（mp-weixin.appid 正式发布时填写）
│   ├── components/
│   │   └── UChart.vue       # 图表组件（@qiun/ucharts 封装）
│   └── pages/
│       ├── tables/          # 数据表列表
│       ├── records/         # 记录列表 + 动态表单编辑
│       ├── reports/         # 报表列表 + 报表详情（图表）
│       ├── tasks/           # 任务列表（开关/试运行/执行）
│       └── notify/          # 站内通知
└── dist/                    # 编译产物（dev / build）
```

## 其他编译目标（可选）

同一套代码可编译到其他平台：

```bash
npm run dev:h5        # 手机浏览器 H5
npm run build:h5
# 支付宝/抖音等小程序见 package.json scripts
```

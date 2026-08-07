# v8.6.8 发行说明 - 新增固定义齿修复知情同意书 & OCR优化 & 部署稳定性提升

## 概述
本版本在 v8.6.5/v8.6.6 的基础上，新增了第5种知情同意书类型（固定义齿修复），优化了腾讯云OCR识别交互方式，并提升了系统部署升级时的稳定性，确保历史文件不受部署操作影响。

---

## 新增功能

### 1. 固定义齿修复知情同意书（第5种同意书类型）
- **类型标识**：`固定义齿修复`
- **显示名称**：固定义齿修复知情同意书
- **字段**：
  - 临床诊断（文本）
  - 修复牙位（FDI牙位选择器，多选）
  - 主治医生（文本，用于条款填空）
- **条款**：10条原文条款，涵盖：
  - 固定修复过程及牙体预备说明
  - 替代方案及修复风险（牙髓损伤、牙龈萎缩等）
  - 临时冠佩戴不适说明
  - 口腔卫生维护要求
  - 手术/药物/麻醉并发症说明
  - 专业制作中心及石膏模型邮寄风险
  - 主治医生和牙位确认（填空）
  - 治疗资料授权
  - 不保证百分百成功声明
  - 程序和风险已理解确认
- **签名区域**：患者签名 / 家属签名（关系） / 主治医生签名
- **PDF生成**：支持生成含完整条款和签名的PDF文件

### 2. 腾讯云OCR采购单文字识别（入库管理）
- 调用腾讯云 `GeneralBasicOCR` 接口（广州地域 `ap-guangzhou`）
- 支持 JPG/PNG 格式，最大 10MB
- **交互方式优化**：复用现有的"出库单照片"上传区域，上传后自动OCR识别
- **左右对半布局**：左侧照片预览，右侧识别结果（可选中复制）
- **使用方式**：选中需要的文字 → Ctrl+C 复制 → 粘贴到下方表单

---

## 修复与优化

### 3. 部署升级稳定性提升
- **问题**：上传目录 `backend/uploads/` 在 backend 文件夹内部，替换 backend 时签名图片、条码照片、PDF 文件一并被删除
- **解决方案**：
  - 上传目录迁移到 **项目根目录**（与 backend 同级）
  - `app.py` 中 `UPLOAD_FOLDER` 指向项目根目录
  - `routes/consents.py` / `routes/inventory.py` 中的文件存储路径同步更新
  - `serve_uploads` 路由使用绝对路径指向新位置
  - **启动时自动迁移**：旧 `backend/uploads/` 中的文件自动移动到 `uploads/`
  - **数据库路径自动更新**：启动时自动修正数据库中存储的旧路径记录

### 4. 签名图片无法正常显示
- **问题**：数据库保存的是服务器绝对文件路径，浏览器 `<img src>` 无法直接访问
- **修复**：详情查询接口返回时，三个签名路径字段统一经过 `_to_url_path()` 转换为 `/uploads/...` URL 格式

### 5. 标签照片预览 404
- **问题**：条码照片保存到数据库的是绝对路径，前端无法直接加载
- **修复**：上传接口和详情查询接口的 `barcode_image_path` 统一转换为 `/uploads/...` URL 格式

### 6. PDF 生成 404
- **问题**：预览弹窗的"生成PDF"按钮直接打开下载链接，同意书尚未归档时 PDF 不存在
- **修复**：`generateConsentPDF()` 先检查 PDF 是否已存在 → 不存在则提示并自动完成归档 → 归档成功后自动下载

### 7. 移动端菜单无法滚动
- **问题**：`nav#mobile-menu` 没有滚动设置，超出屏幕的菜单项无法选择
- **修复**：
  - 添加 `overflow-y-auto` + `max-height: calc(100vh - 60px)` 支持滚动
  - 补全缺失菜单项：原菜单仅有5项，现补全为全部功能

---

## 密钥管理

### 腾讯云OCR密钥存放位置
- 密钥文件：`env/.env`（与 `.config/` 并列在项目根目录）
- 格式：
  ```
  TENCENTCLOUD_SECRET_ID=你的SecretId
  TENCENTCLOUD_SECRET_KEY=你的SecretKey
  ```
- 启动时 `app.py` 自动加载
- 已添加至 `.gitignore`，真实密钥不会提交到Git

---

## 文件变更清单

| 文件 | 变更 |
|------|------|
| `backend/database.py` | 新增固定义齿修复模板数据；版本号更新 |
| `backend/routes/consents.py` | title_map添加新类型；PDF变量替换添加`doctor_name`；版本号更新 |
| `backend/static/js/app.js` | 预览标题映射、额外信息、变量替换添加新类型；版本号更新 |
| `backend/static/index.html` | 下拉菜单、筛选器添加"固定义齿修复"；OCR布局优化；版本号更新 |
| `backend/routes/inventory.py` | 新增OCR接口 `/api/inventory/ocr-purchase`；版本号更新 |
| `backend/app.py` | 上传目录指向项目根目录；环境变量自动加载；版本号更新 |
| `backend/requirements.txt` | 新增 `python-dotenv` 和 `tencentcloud-sdk-python` |
| `env/.env.example` | 新增腾讯云密钥模板 |
| `.gitignore` | 添加 `env/.env` 和 `__pycache__` |

---

## 部署说明

### 升级步骤

```bash
# 1. 安装新依赖
pip install python-dotenv==1.0.1 tencentcloud-sdk-python==3.0.1200

# 2. 配置腾讯云密钥（手动创建 env/.env 文件）
cat > env/.env << 'EOF'
TENCENTCLOUD_SECRET_ID=你的SecretId
TENCENTCLOUD_SECRET_KEY=你的SecretKey
EOF

# 3. 解压新代码（uploads 目录在 backend 外部，替换 backend 时不受影响）
# 启动时会自动完成以下操作：
#   - 将 backend/uploads/ 中的文件迁移到 uploads/（如存在）
#   - 更新数据库中所有旧路径记录

# 4. 重启 Flask 服务
```

### 新目录结构
```
HRKQ_QA_git/
├── uploads/              ← 上传文件（签名、条码、PDF、库存照片）
│   ├── consents/
│   ├── inventory/
│   └── supplier/
├── env/                  ← 环境变量（腾讯云密钥等）
│   ├── .env              ← 真实密钥（不提交Git）
│   └── .env.example      ← 模板
├── backend/              ← 可随意替换
│   ├── static/
│   └── routes/
└── start.py
```

### 固定义齿修复模板导入
如果启动后条款未自动加载，请在数据库中执行：
```sql
INSERT INTO consent_templates (doc_type, title, clauses, field_schema)
VALUES (
    '固定义齿修复',
    '固定义齿修复知情同意书',
    '["...10条条款..."]',
    '[{"name":"diagnosis",...}]'
)
ON DUPLICATE KEY UPDATE title=VALUES(title), clauses=VALUES(clauses), field_schema=VALUES(field_schema);
```
（完整SQL见项目文件或联系开发）

---

## 版本信息
- **版本号**：v8.6.8
- **发布日期**：2026-08-07
- **上一个版本**：v8.6.6

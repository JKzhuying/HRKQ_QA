# v8.6.6 发行说明 - 稳定性修复与部署优化

## 概述
本版本在 v8.6.5 文件签署中心的基础上，重点修复了签名/图片预览、PDF生成、移动端菜单以及部署升级稳定性等关键问题。

---

## 修复内容

### 1. 签名图片无法正常显示
- **问题**：数据库保存的是服务器绝对文件路径，浏览器 `<img src>` 无法直接访问
- **修复**：详情查询接口返回时，三个签名路径字段（`patient_signature_path`/`guardian_signature_path`/`doctor_signature_path`）统一经过 `_to_url_path()` 转换为 `/uploads/...` URL 格式

### 2. 标签照片预览 404
- **问题**：条码照片保存到数据库的是绝对路径，前端无法直接加载
- **修复**：上传接口和详情查询接口的 `barcode_image_path` 统一转换为 `/uploads/...` URL 格式

### 3. PDF 生成 404
- **问题**：预览弹窗的"生成PDF"按钮直接打开下载链接，同意书尚未归档时 PDF 不存在
- **修复**：`generateConsentPDF()` 先检查 PDF 是否已存在 → 不存在则提示并自动完成归档 → 归档成功后自动下载

### 4. 移动端菜单无法滚动
- **问题**：`nav#mobile-menu` 没有滚动设置，超出屏幕的菜单项无法选择
- **修复**：
  - 添加 `overflow-y-auto` + `max-height: calc(100vh - 60px)` 支持滚动
  - **补全缺失菜单项**：原菜单仅有5项，现补全为全部功能（库存管理分组、文件签署中心、会计凭证、财务核算等）

### 5. 升级部署丢失上传文件
- **问题**：上传目录 `backend/uploads/` 在 backend 文件夹内部，替换 backend 时签名图片、条码照片、PDF 文件一并被删除
- **修复**：
  - 上传目录迁移到 **项目根目录**（与 backend 同级）
  - `app.py` 中 `UPLOAD_FOLDER` 指向项目根目录
  - `routes/consents.py` / `routes/inventory.py` 中的文件存储路径同步更新
  - `serve_uploads` 路由使用绝对路径指向新位置
  - **启动时自动迁移**：旧 `backend/uploads/` 中的文件自动移动到 `uploads/`
  - **数据库路径自动更新**：启动时自动修正数据库中存储的旧路径记录

---

## 文件变更清单

| 文件 | 变更 |
|------|------|
| `backend/app.py` | 上传目录指向项目根目录；serve_uploads 用绝对路径；启动自动迁移旧文件 |
| `backend/routes/consents.py` | CONSENT_DIR 指向项目根目录；签名/条码路径URL转换；PDF生成逻辑 |
| `backend/routes/inventory.py` | UPLOAD_DIR / SUPPLIER_PHOTO_DIR 指向项目根目录 |
| `backend/database.py` | 新增 `_migrate_upload_paths()` 自动更新数据库旧路径 |
| `backend/static/js/app.js` | generateConsentPDF 先检查再归档；标签预览加载 |
| `backend/static/index.html` | 移动端菜单补全 + 滚动支持 |

---

## 部署说明

### 升级步骤

```bash
# 1. 解压新代码（uploads 目录在 backend 外部，替换 backend 时不受影响）
unzip HRKQ_QA_v866.zip
cd HRKQ_QA_git

# 2. 重启 Flask 服务
# 启动时会自动完成以下操作：
#   - 将 backend/uploads/ 中的文件迁移到 uploads/（如存在）
#   - 更新数据库中所有旧路径记录

# 3. 刷新浏览器
```

### 新目录结构
```
HRKQ_QA_git/
├── uploads/              ← 上传文件（签名、条码、PDF、库存照片）
│   ├── consents/
│   ├── inventory/
│   └── supplier/
├── backend/              ← 可随意替换
│   ├── static/
│   └── routes/
└── start.py
```

---

## 版本信息
- **版本号**：v8.6.6
- **发布日期**：2026-08-04
- **上一个版本**：v8.6.5

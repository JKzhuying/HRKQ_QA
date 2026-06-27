// ==================== 全局状态 ====================
let currentPage = 'dashboard';
let queryPage = 1;
let queryTotal = 0;
let categoryData = [];
const pageSize = 20;
let selectedIds = new Set(); // 批量选中的记录ID
let queryPageSize = 20; // 记录查询每页条数
let isQueryAllSelected = false; // 记录查询全选状态
let queryAllRecordsCache = []; // 缓存查询结果，用于编辑弹窗
const paymentLabels = { alipay: '支付宝', wechat: '微信支付', cash: '现金' };
const typeLabels = { income: '收入', expense: '支出', transfer: '调拨' };
const typeClasses = { income: 'bg-emerald-100 text-emerald-700', expense: 'bg-red-100 text-red-700', transfer: 'bg-blue-100 text-blue-700' };

// 记录查询排序状态
let querySortField = '';  // 'date' | 'counterparty' | ''
let querySortDir = 'asc'; // 'asc' | 'desc'

// ==================== API 请求 ====================
async function api(url, options = {}) {
    var opts = { ...options };
    // 只在有body时设置Content-Type，避免DELETE等请求出错
    if (opts.body && !opts.headers) {
        opts.headers = { 'Content-Type': 'application/json' };
    }
    const res = await fetch(url, opts);
    return res.json();
}

async function uploadFile(url, file) {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(url, { method: 'POST', body: formData });
    return res.json();
}

// ==================== 日期格式化 ====================
function formatDate(dateStr) {
    if (!dateStr) return '';
    var d = new Date(dateStr);
    if (isNaN(d.getTime())) {
        // 如果无法解析，尝试直接截取前10位（YYYY-MM-DD格式）
        var s = String(dateStr);
        if (s.length >= 10 && /^\d{4}-\d{2}-\d{2}/.test(s)) {
            return s.slice(0, 10);
        }
        return s;
    }
    var y = d.getFullYear();
    var m = String(d.getMonth() + 1).padStart(2, '0');
    var day = String(d.getDate()).padStart(2, '0');
    return y + '-' + m + '-' + day;
}

// ==================== 排序功能 ====================
function toggleSort(field) {
    if (querySortField === field) {
        querySortDir = querySortDir === 'asc' ? 'desc' : 'asc';
    } else {
        querySortField = field;
        querySortDir = 'asc';
    }
    // 更新排序图标
    document.getElementById('sort-icon-date').innerHTML = querySortField === 'date'
        ? (querySortDir === 'asc' ? '&#9650;' : '&#9660;')
        : '&#9650;';
    document.getElementById('sort-icon-date').className = querySortField === 'date'
        ? 'inline-block ml-1 text-primary font-bold'
        : 'inline-block ml-1 text-gray-300 group-hover:text-primary transition-colors';
    document.getElementById('sort-icon-counterparty').innerHTML = querySortField === 'counterparty'
        ? (querySortDir === 'asc' ? '&#9650;' : '&#9660;')
        : '&#9650;';
    document.getElementById('sort-icon-counterparty').className = querySortField === 'counterparty'
        ? 'inline-block ml-1 text-primary font-bold'
        : 'inline-block ml-1 text-gray-300 group-hover:text-primary transition-colors';
    loadQuery();
}

function sortData(list) {
    if (!querySortField) return list;
    const sorted = [...list];
    const dir = querySortDir === 'asc' ? 1 : -1;
    sorted.sort(function(a, b) {
        if (querySortField === 'date') {
            const av = formatDate(a.trans_date);
            const bv = formatDate(b.trans_date);
            return av.localeCompare(bv) * dir;
        } else if (querySortField === 'counterparty') {
            const av = (a.counterparty || '').toLowerCase();
            const bv = (b.counterparty || '').toLowerCase();
            return av.localeCompare(bv) * dir;
        }
        return 0;
    });
    return sorted;
}

// ==================== 收费大类明细弹窗 v7.3.1 ====================
function openCatDetailModal(catName) {
    var list = window._dashboardIncomeList || [];
    var filtered = list.filter(function(r) {
        return (r.category || '未分类') === catName;
    });

    document.getElementById('cat-detail-title').textContent = catName + ' — 明细';
    document.getElementById('cat-detail-subtitle').textContent = '共 ' + filtered.length + ' 条记录，应收合计 ¥' +
        filtered.reduce(function(s, r) { return s + (r.amount_receivable || 0); }, 0).toFixed(2) +
        '，实收合计 ¥' +
        filtered.reduce(function(s, r) { return s + (r.amount_real || 0); }, 0).toFixed(2);

    var tbody = document.getElementById('cat-detail-body');
    if (filtered.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="px-4 py-8 text-center text-gray-400">暂无记录</td></tr>';
    } else {
        tbody.innerHTML = filtered.map(function(row) {
            var fee = (row.amount_receivable || 0) - (row.amount_real || 0);
            var feeRate = row.amount_receivable > 0 ? (((row.amount_receivable - row.amount_real) / row.amount_receivable) * 100).toFixed(2) + '%' : '--';
            return '<tr class="hover:bg-gray-50">' +
                '<td class="px-4 py-3 text-gray-900 whitespace-nowrap">' + formatDate(row.trans_date) + '</td>' +
                '<td class="px-4 py-3 text-gray-900">' + (row.counterparty || '') + '</td>' +
                '<td class="px-4 py-3 text-gray-600">' + (row.item_name || '') + '</td>' +
                '<td class="px-4 py-3 text-right text-gray-900">¥' + (row.amount_receivable || 0).toFixed(2) + '</td>' +
                '<td class="px-4 py-3 text-right text-gray-900">¥' + (row.amount_real || 0).toFixed(2) + '</td>' +
                '<td class="px-4 py-3 text-right"><span class="text-amber-600 font-medium">¥' + fee.toFixed(2) + '</span><span class="text-xs text-gray-400 ml-1">(' + feeRate + ')</span></td>' +
                '<td class="px-4 py-3 text-gray-500">' + (row.remark || '') + '</td>' +
            '</tr>';
        }).join('');
    }

    document.getElementById('cat-detail-count').textContent = '共 ' + filtered.length + ' 条记录';
    document.getElementById('cat-detail-modal').classList.remove('hidden');
}

function closeCatDetailModal() {
    document.getElementById('cat-detail-modal').classList.add('hidden');
}

// ==================== 页面导航 ====================
function showPage(page) {
    currentPage = page;
    document.querySelectorAll('.page-content').forEach(el => el.classList.add('hidden'));
    document.getElementById(`page-${page}`).classList.remove('hidden');
    
    document.querySelectorAll('.nav-item').forEach(el => {
        el.classList.remove('bg-primary', 'text-white');
        el.classList.add('text-slate-300');
        if (el.dataset.page === page) {
            el.classList.add('bg-primary', 'text-white');
            el.classList.remove('text-slate-300');
        }
    });
    
    document.querySelectorAll('.mobile-nav-item').forEach(el => {
        el.classList.remove('bg-primary', 'text-white');
        el.classList.add('text-slate-300');
        if (el.dataset.page === page) {
            el.classList.add('bg-primary', 'text-white');
            el.classList.remove('text-slate-300');
        }
    });
    
    document.getElementById('mobile-menu').classList.add('hidden');
    
    if (page === 'dashboard') loadDashboard();
    else if (page === 'query') { loadCategoriesForSelect(); loadQuery(); }
    else if (page === 'statistics') loadStatistics();
    else if (page === 'settings') { loadSettings(); loadBanks(); }
    else if (page === 'entry') initEntryPage();
    else if (page === 'vouchers') loadVouchers('');
    else if (page === 'finance') { checkOpeningBalance(); loadFinanceL1(); loadFinanceL2(); loadFinanceMapping(); }
    else if (page === 'inventory-entry') { loadSuppliersForSelect(); initInventoryEntryPage(); }
    else if (page === 'inventory-history') { loadSuppliersForHistory(); loadInventoryHistory(); }
    else if (page === 'inventory-warnings') loadInventoryWarnings('all');
    else if (page === 'inventory-suppliers') loadSuppliers();
}

// v8.5: 库存管理子菜单切换
document.querySelector('.inventory-nav-group').addEventListener('click', function(e) {
    e.preventDefault();
    var el = e.target.closest('.nav-item, .nav-subitem');
    if (!el) return;
    if (el.classList.contains('nav-item')) {
        var submenu = this.querySelector('.inventory-submenu');
        submenu.classList.toggle('hidden');
        showPage('inventory-entry');
    } else if (el.classList.contains('nav-subitem')) {
        showPage(el.dataset.page);
    }
});

document.querySelectorAll('.nav-item:not(.inventory-nav-group .nav-item), .mobile-nav-item').forEach(el => {
    el.addEventListener('click', (e) => {
        e.preventDefault();
        showPage(el.dataset.page);
    });
});

document.getElementById('mobile-menu-btn').addEventListener('click', () => {
    document.getElementById('mobile-menu').classList.toggle('hidden');
});

// ==================== 仪表盘 ====================
async function loadDashboard() {
    const now = new Date();
    const startOfMonth = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-01`;
    const endOfMonth = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
    
    // 同时请求本月汇总和最近50条收入记录
    const [summaryRes, incomeListRes] = await Promise.all([
        api(`/api/transactions/statistics/summary?start_date=${startOfMonth}&end_date=${endOfMonth}`),
        api('/api/transactions/list?trans_type=income&page_size=50'),
    ]);
    
    if (summaryRes.code !== 200) return;
    
    const data = summaryRes.data;
    const container = document.getElementById('dashboard-cards');
    container.innerHTML = `
        <div class="bg-white rounded-xl shadow-sm border p-5">
            <div class="flex items-center justify-between">
                <div><p class="text-sm text-gray-500">本月收入</p><p class="text-2xl font-bold text-emerald-600 mt-1">¥${data.total_income.toFixed(2)}</p></div>
                <div class="w-10 h-10 bg-emerald-100 rounded-lg flex items-center justify-center"><svg class="w-5 h-5 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"/></svg></div>
            </div>
        </div>
        <div class="bg-white rounded-xl shadow-sm border p-5">
            <div class="flex items-center justify-between">
                <div><p class="text-sm text-gray-500">本月支出</p><p class="text-2xl font-bold text-red-600 mt-1">¥${data.total_expense.toFixed(2)}</p></div>
                <div class="w-10 h-10 bg-red-100 rounded-lg flex items-center justify-center"><svg class="w-5 h-5 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 17h8m0 0V9m0 8l-8-8-4 4-6-6"/></svg></div>
            </div>
        </div>
        <div class="bg-white rounded-xl shadow-sm border p-5">
            <div class="flex items-center justify-between">
                <div><p class="text-sm text-gray-500">平均手续费率</p><p class="text-2xl font-bold text-amber-600 mt-1" id="avg-fee-rate">--</p></div>
                <div class="w-10 h-10 bg-amber-100 rounded-lg flex items-center justify-center"><svg class="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z"/></svg></div>
            </div>
        </div>`;
    
    // 渲染手续费表格：按收费大类分组，显示平均手续费率
    const feeChart = document.getElementById('fee-chart');
    if (incomeListRes.code === 200 && incomeListRes.data && incomeListRes.data.list && incomeListRes.data.list.length > 0) {
        const incomeList = incomeListRes.data.list;
        let totalReceivable = 0;
        let totalReal = 0;
        
        // 按收费大类汇总
        const categoryStats = {};
        for (let i = 0; i < incomeList.length; i++) {
            const row = incomeList[i];
            const receivable = row.amount_receivable || 0;
            const real = row.amount_real || 0;
            totalReceivable += receivable;
            totalReal += real;
            const cat = row.category || '未分类';
            if (!categoryStats[cat]) {
                categoryStats[cat] = { receivable: 0, real: 0, count: 0 };
            }
            categoryStats[cat].receivable += receivable;
            categoryStats[cat].real += real;
            categoryStats[cat].count += 1;
        }
        
        // 缓存收入列表，供弹窗使用 v7.3.1
        window._dashboardIncomeList = incomeList;

        // 表格：按收费大类显示平均手续费率
        let html = '<table class="w-full text-sm"><thead class="bg-gray-50"><tr><th class="px-4 py-2 text-left font-medium text-gray-600">收费大类</th><th class="px-4 py-2 text-right font-medium text-gray-600">记录数</th><th class="px-4 py-2 text-right font-medium text-gray-600">应收合计</th><th class="px-4 py-2 text-right font-medium text-gray-600">实收合计</th><th class="px-4 py-2 text-right font-medium text-gray-600">平均手续费率</th></tr></thead><tbody class="divide-y">';

        const sortedCategories = Object.entries(categoryStats).sort((a, b) => b[1].receivable - a[1].receivable);
        for (let i = 0; i < sortedCategories.length; i++) {
            const [catName, stat] = sortedCategories[i];
            let feeRate = 0;
            if (stat.receivable > 0) {
                feeRate = ((stat.receivable - stat.real) / stat.receivable) * 100;
            }
            const feeRateStr = feeRate.toFixed(2) + '%';
            const feeColor = feeRate > 0 ? 'text-amber-600' : 'text-gray-400';

            html += '<tr class="hover:bg-gray-50 cursor-pointer" onclick="openCatDetailModal(\'' + catName.replace(/'/g, "\\'") + '\')">';
            html += '<td class="px-4 py-2"><span class="text-xs px-2 py-0.5 bg-blue-50 text-blue-700 rounded hover:bg-blue-100 hover:shadow transition-all inline-flex items-center gap-1"><svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>' + catName + '</span></td>';
            html += '<td class="px-4 py-2 text-right text-gray-900">' + stat.count + ' 条</td>';
            html += '<td class="px-4 py-2 text-right text-gray-900">' + stat.receivable.toFixed(2) + '</td>';
            html += '<td class="px-4 py-2 text-right text-gray-900">' + stat.real.toFixed(2) + '</td>';
            html += '<td class="px-4 py-2 text-right font-medium ' + feeColor + '">' + feeRateStr + '</td>';
            html += '</tr>';
        }
        html += '</tbody></table>';
        feeChart.innerHTML = html;
        
        // 更新平均手续费率卡片（最近50条收入的总体平均）
        let avgFeeRate = 0;
        if (totalReceivable > 0) {
            avgFeeRate = ((totalReceivable - totalReal) / totalReceivable) * 100;
        }
        document.getElementById('avg-fee-rate').textContent = avgFeeRate.toFixed(2) + '%';
    } else {
        feeChart.innerHTML = '<p class="text-gray-400 text-center py-8">暂无收入数据</p>';
        document.getElementById('avg-fee-rate').textContent = '--';
    }
    
    // 收入大类对比 - 3D立体柱状图 v7.3
    const chartContainer = document.getElementById('payment-chart');
    var incomeCats = {};
    if (data.by_category) {
        for (var i = 0; i < data.by_category.length; i++) {
            var item = data.by_category[i];
            if (item.trans_type === 'income' && item.category) {
                incomeCats[item.category] = (incomeCats[item.category] || 0) + item.total;
            }
        }
    }
    var catEntries = Object.entries(incomeCats).sort(function(a, b) { return b[1] - a[1]; });
    var maxCatVal = catEntries.length > 0 ? Math.max.apply(null, catEntries.map(function(e) { return e[1]; })) : 1;
    if (catEntries.length > 0) {
        var barColors = ['#059669', '#10b981', '#34d399', '#047857', '#0891b2', '#06b6d4', '#0e7490', '#14b8a6'];
        var barsHtml = catEntries.map(function(entry, idx) {
            var catName = entry[0];
            var catVal = entry[1];
            var pct = maxCatVal > 0 ? (catVal / maxCatVal) * 100 : 0;
            var color = barColors[idx % barColors.length];
            return '<div class="flex flex-col items-center gap-1 flex-1 min-w-[60px]">' +
                '<span class="text-xs font-medium text-gray-700">¥' + catVal.toFixed(0) + '</span>' +
                '<div class="w-full flex justify-center" style="perspective:200px;">' +
                    '<div style="width:36px;height:' + Math.max(pct * 1.5, 8) + 'px;background:linear-gradient(180deg,' + color + ',#047857);border-radius:4px 4px 0 0;box-shadow:2px 2px 8px rgba(0,0,0,0.15),inset 0 1px 0 rgba(255,255,255,0.3);transform:rotateX(5deg);transform-origin:bottom;position:relative;">' +
                        '<div style="position:absolute;top:0;left:0;right:0;height:30%;background:linear-gradient(180deg,rgba(255,255,255,0.25),transparent);border-radius:4px 4px 0 0;"></div>' +
                    '</div>' +
                '</div>' +
                '<span class="text-xs text-gray-500 text-center truncate w-full px-1" title="' + catName + '">' + catName + '</span>' +
            '</div>';
        }).join('');
        chartContainer.innerHTML = '<div class="flex items-end justify-center gap-3 pb-2 min-h-[200px]">' + barsHtml + '</div>';
    } else {
        chartContainer.innerHTML = '<p class="text-gray-400 text-center py-8">暂无收入数据</p>';
    }
}

// ==================== 导入功能 ====================
let selectedFile = null;
let previewAllData = [];       // 存储全部预览数据
let previewTotalCount = 0;     // 总记录数
let previewCurrentPage = 1;    // 当前页码
const PREVIEW_MAX_PAGE_SIZE = 50; // 每页最多50条

function clearCurrentPreview() {
    previewAllData = [];
    previewTotalCount = 0;
    previewCurrentPage = 1;
    selectedFile = null;
    document.getElementById('preview-section').classList.add('hidden');
    document.getElementById('preview-check-report').classList.add('hidden');
    document.getElementById('preview-body').innerHTML = '';
    document.getElementById('file-info').classList.add('hidden');
    document.getElementById('excel-file').value = '';
    document.getElementById('import-result').classList.add('hidden');
}

document.getElementById('excel-file').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    selectedFile = file;
    document.getElementById('file-name').textContent = file.name;
    document.getElementById('file-info').classList.remove('hidden');
    document.getElementById('import-result').classList.add('hidden');

    const previewSection = document.getElementById('preview-section');
    const resultDiv = document.getElementById('import-result');
    previewSection.classList.add('hidden');

    try {
        const res = await uploadFile('/api/import/preview', file);
        if (res.code === 200 && res.data) {
            previewAllData = res.data.preview || [];
            previewTotalCount = res.data.total || 0;
            previewCurrentPage = 1;

            previewSection.classList.remove('hidden');

            // v8.1: 加载有效收费大类集合（用于实时校验）
            try {
                var catRes = await api('/api/settings/categories');
                if (catRes.code === 200 && catRes.data) {
                    validCategoriesSet = new Set(catRes.data.map(function(c) { return c.name; }));
                }
            } catch (e) {
                validCategoriesSet = new Set();
            }

            // 渲染预览表格（根据选择的条数）
            renderPreviewPage();

            // 渲染检查报告（v8.1 动态获取收费大类）
            await renderCheckReport(res.data.check_report || {});

            // 检查通过则弹窗
            const cr = res.data.check_report || {};
            const noIssues = (!cr.empty_counterparty || cr.empty_counterparty.length === 0)
                          && (!cr.empty_category || cr.empty_category.length === 0)
                          && (!cr.invalid_category || cr.invalid_category.length === 0);
            if (noIssues && previewTotalCount > 0) {
                setTimeout(() => alert('导入数据完整，正常'), 100);
            }
        } else if (res.code !== 200) {
            resultDiv.classList.remove('hidden');
            resultDiv.innerHTML = `<div class="bg-red-50 rounded-lg p-4 text-red-700"><strong>预览失败：</strong>${res.message || '无法解析该Excel文件'}</div>`;
        }
    } catch (err) {
        resultDiv.classList.remove('hidden');
        resultDiv.innerHTML = `<div class="bg-red-50 rounded-lg p-4 text-red-700"><strong>预览出错：</strong>${err.message || '网络连接失败或服务器异常'}</div>`;
    }
});

async function renderCheckReport(checkReport) {
    const checkDiv = document.getElementById('preview-check-report');
    let hasIssues = false;
    let checkHtml = '<div class="px-6 py-3 border-b space-y-2">';

    // 动态获取当前数据库中的收费大类
    var validCategoryNames = '';
    try {
        var res = await api('/api/settings/categories');
        if (res.code === 200 && res.data) {
            var allNames = [...new Set(res.data.map(function(c) { return c.name; }))];
            validCategoryNames = allNames.join('、');
        }
    } catch (e) {
        validCategoryNames = '（请前往系统设置查看）';
    }

    if (checkReport.empty_counterparty && checkReport.empty_counterparty.length > 0) {
        hasIssues = true;
        checkHtml += `<div class="flex items-center gap-2 text-amber-700 bg-amber-50 rounded-lg px-3 py-2"><svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg><span class="text-sm font-medium">第 <strong>${checkReport.empty_counterparty.join(', ')}</strong> 行的【对象】（第三列）为空，共 ${checkReport.empty_counterparty.length} 行</span></div>`;
    }
    if (checkReport.empty_category && checkReport.empty_category.length > 0) {
        hasIssues = true;
        checkHtml += `<div class="flex items-center gap-2 text-amber-700 bg-amber-50 rounded-lg px-3 py-2"><svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg><span class="text-sm font-medium">第 <strong>${checkReport.empty_category.join(', ')}</strong> 行的【收费大类】（第四列）为空，共 ${checkReport.empty_category.length} 行</span></div>`;
    }
    if (checkReport.invalid_category && checkReport.invalid_category.length > 0) {
        hasIssues = true;
        const invalidRows = checkReport.invalid_category.map(item => `第${item.row}行"${item.value}"`).join('、');
        checkHtml += `<div class="flex items-start gap-2 text-red-700 bg-red-50 rounded-lg px-3 py-2"><svg class="w-4 h-4 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg><div class="text-sm"><span class="font-medium">收费大类不在有效范围内（共 ${checkReport.invalid_category.length} 行）：</span><span class="text-red-600">${invalidRows}</span><div class="text-xs text-gray-500 mt-1">有效类别：${validCategoryNames}</div></div></div>`;
    }
    // v8.3: 银行账号不匹配报告
    if (checkReport.invalid_bank_from && checkReport.invalid_bank_from.length > 0) {
        hasIssues = true;
        const invalidRows = checkReport.invalid_bank_from.map(item => `第${item.row}行"${item.value}"`).join('、');
        checkHtml += `<div class="flex items-start gap-2 text-red-700 bg-red-50 rounded-lg px-3 py-2"><svg class="w-4 h-4 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg><div class="text-sm"><span class="font-medium">转出账户不在银行账号列表中（共 ${checkReport.invalid_bank_from.length} 行）：</span><span class="text-red-600">${invalidRows}</span><div class="text-xs text-gray-500 mt-1">请在系统设置 > 银行账号管理中维护</div></div></div>`;
    }
    if (checkReport.invalid_bank_to && checkReport.invalid_bank_to.length > 0) {
        hasIssues = true;
        const invalidRows = checkReport.invalid_bank_to.map(item => `第${item.row}行"${item.value}"`).join('、');
        checkHtml += `<div class="flex items-start gap-2 text-red-700 bg-red-50 rounded-lg px-3 py-2"><svg class="w-4 h-4 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg><div class="text-sm"><span class="font-medium">转入账户不在银行账号列表中（共 ${checkReport.invalid_bank_to.length} 行）：</span><span class="text-red-600">${invalidRows}</span><div class="text-xs text-gray-500 mt-1">请在系统设置 > 银行账号管理中维护</div></div></div>`;
    }
    checkHtml += '</div>';

    if (hasIssues) {
        checkDiv.innerHTML = checkHtml;
        checkDiv.classList.remove('hidden');
    } else {
        checkDiv.classList.add('hidden');
        checkDiv.innerHTML = '';
    }
}

function renderPreviewPage() {
    const pageSizeSelect = document.getElementById('preview-page-size');
    let selectedSize = parseInt(pageSizeSelect.value);
    const isShowAll = selectedSize === 0;
    const isLargePage = selectedSize >= 70; // 70条或全部时不限制每页条数

    // 计算实际每页条数：20/50时最多50条/页（超过需分页），70/全部时不限制
    let pageSize;
    if (isShowAll) {
        pageSize = previewAllData.length || 1; // 全部：一页显示所有
    } else if (isLargePage) {
        pageSize = selectedSize; // 70条：一页显示70条
    } else {
        pageSize = selectedSize; // 20/50条：正常分页
    }
    const totalPages = Math.ceil(previewAllData.length / pageSize);

    // 确保当前页有效
    if (previewCurrentPage > totalPages) previewCurrentPage = 1;

    // 计算切片范围
    const start = (previewCurrentPage - 1) * pageSize;
    const end = Math.min(start + pageSize, previewAllData.length);
    const pageData = previewAllData.slice(start, end);

    // 更新计数显示
    const showInfo = totalPages <= 1
        ? `共 ${previewTotalCount} 条，显示全部`
        : `共 ${previewTotalCount} 条，第 ${previewCurrentPage}/${totalPages} 页`;
    document.getElementById('preview-count').textContent = showInfo;

    // 渲染表格（可编辑）
    const previewBody = document.getElementById('preview-body');
    previewBody.innerHTML = pageData.map((row, idx) => {
        const realIdx = start + idx;
        const dateVal = formatDate(row.trans_date);
        const isTransfer = row.trans_type === 'transfer';
        // v8.3: 调拨行显示专用字段
        var counterpartyVal = isTransfer ? (row.from_account || '') : (row.counterparty || '');
        var categoryVal = isTransfer ? '资金调拨' : (row.category || '');
        var itemVal = isTransfer ? (row.to_account || '') : (row.item_name || '');
        var receivableVal = isTransfer ? (row.amount_planned ?? 0) : (row.amount_receivable ?? 0);
        var realVal = isTransfer ? (row.amount_real ?? 0) : (row.amount_real ?? 0);
        var catClass = row._valid_category === false ? 'border-red-400 bg-red-50 text-red-700' : 'border-gray-200 text-blue-700 bg-blue-50/30';
        var bankFromClass = row._valid_bank_from === false ? 'border-red-400 bg-red-50 text-red-700' : 'border-gray-200 text-gray-600';
        return `<tr class="hover:bg-gray-50">
            <td class="px-2 py-2"><input type="text" value="${dateVal}" onchange="updatePreviewData(${realIdx}, 'trans_date', this.value)" class="w-full px-2 py-1 text-sm border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-primary text-gray-900"></td>
            <td class="px-2 py-2">
                <select onchange="updatePreviewData(${realIdx}, 'trans_type', this.value)" class="px-2 py-1 text-xs border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-primary bg-white ${typeClasses[row.trans_type] || 'bg-gray-100 text-gray-600'}">
                    <option value="income" ${row.trans_type === 'income' ? 'selected' : ''}>收入</option>
                    <option value="expense" ${row.trans_type === 'expense' ? 'selected' : ''}>支出</option>
                    <option value="transfer" ${isTransfer ? 'selected' : ''}>调拨</option>
                </select>
            </td>
            <td class="px-2 py-2"><input type="text" value="${counterpartyVal}" onchange="updatePreviewData(${realIdx}, '${isTransfer ? 'from_account' : 'counterparty'}', this.value)" class="w-full px-2 py-1 text-sm border rounded focus:outline-none focus:ring-1 focus:ring-primary ${isTransfer ? bankFromClass : 'border-gray-200 text-gray-600'}"></td>
            <td class="px-2 py-2"><input type="text" value="${categoryVal}" onchange="updatePreviewData(${realIdx}, 'category', this.value); ${isTransfer ? '' : 'validatePreviewCategory(this, ' + realIdx + ')'}" class="w-full px-2 py-1 text-sm border rounded focus:outline-none focus:ring-1 focus:ring-primary ${catClass}" ${isTransfer ? 'readonly' : ''}></td>
            <td class="px-2 py-2"><input type="text" value="${itemVal}" onchange="updatePreviewData(${realIdx}, '${isTransfer ? 'to_account' : 'item_name'}', this.value)" class="w-full px-2 py-1 text-sm border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-primary text-gray-600"></td>
            <td class="px-2 py-2"><input type="number" step="0.01" value="${receivableVal}" onchange="updatePreviewData(${realIdx}, '${isTransfer ? 'amount_planned' : 'amount_receivable'}', parseFloat(this.value)||0)" class="w-full px-2 py-1 text-sm border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-primary text-right text-gray-900"></td>
            <td class="px-2 py-2"><input type="number" step="0.01" value="${realVal}" onchange="updatePreviewData(${realIdx}, 'amount_real', parseFloat(this.value)||0)" class="w-full px-2 py-1 text-sm border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-primary text-right font-medium text-gray-900"></td>
            <td class="px-2 py-2"><input type="text" value="${row.remark || ''}" onchange="updatePreviewData(${realIdx}, 'remark', this.value)" class="w-full px-2 py-1 text-sm border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-primary text-gray-500 max-w-[200px]"></td>
        </tr>`;
    }).join('');

    // 分页控件
    const paginationDiv = document.getElementById('preview-pagination');
    if (totalPages > 1) {
        paginationDiv.classList.remove('hidden');
        document.getElementById('preview-page-info').textContent = `显示 ${start + 1}-${end} 条，共 ${previewAllData.length} 条`;
        let buttons = '';
        buttons += `<button onclick="changePreviewPage(${previewCurrentPage - 1})" ${previewCurrentPage <= 1 ? 'disabled' : ''} class="p-2 rounded-lg hover:bg-gray-100 disabled:opacity-30 transition-colors"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/></svg></button>`;
        for (let i = 1; i <= totalPages; i++) {
            if (i === 1 || i === totalPages || (i >= previewCurrentPage - 1 && i <= previewCurrentPage + 1)) {
                buttons += `<button onclick="changePreviewPage(${i})" class="w-8 h-8 rounded-lg text-sm font-medium transition-colors ${previewCurrentPage === i ? 'bg-primary text-white' : 'hover:bg-gray-100 text-gray-600'}">${i}</button>`;
            } else if (i === previewCurrentPage - 2 || i === previewCurrentPage + 2) {
                buttons += `<span class="px-2 text-gray-400">...</span>`;
            }
        }
        buttons += `<button onclick="changePreviewPage(${previewCurrentPage + 1})" ${previewCurrentPage >= totalPages ? 'disabled' : ''} class="p-2 rounded-lg hover:bg-gray-100 disabled:opacity-30 transition-colors"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg></button>`;
        document.getElementById('preview-page-buttons').innerHTML = buttons;
    } else {
        paginationDiv.classList.add('hidden');
    }
}

function updatePreviewData(idx, field, value) {
    // 更新预览数据数组中的指定字段
    if (idx >= 0 && idx < previewAllData.length) {
        previewAllData[idx][field] = value;
    }
}

// v8.1: 实时校验收费大类是否匹配数据库
function validatePreviewCategory(inputEl, idx) {
    if (idx < 0 || idx >= previewAllData.length) return;
    var val = (inputEl.value || '').trim();
    var isValid = !val || validCategoriesSet.size === 0 || validCategoriesSet.has(val);
    previewAllData[idx]._valid_category = isValid;
    if (isValid) {
        inputEl.classList.remove('border-red-400', 'bg-red-50', 'text-red-700');
        inputEl.classList.add('border-gray-200', 'text-blue-700', 'bg-blue-50/30');
    } else {
        inputEl.classList.add('border-red-400', 'bg-red-50', 'text-red-700');
        inputEl.classList.remove('border-gray-200', 'text-blue-700', 'bg-blue-50/30');
    }
}

function changePreviewPage(page) {
    const pageSizeSelect = document.getElementById('preview-page-size');
    let selectedSize = parseInt(pageSizeSelect.value);
    let pageSize;
    if (selectedSize === 0) {
        pageSize = previewAllData.length || 1;
    } else if (selectedSize >= 70) {
        pageSize = selectedSize;
    } else {
        pageSize = selectedSize;
    }
    const totalPages = Math.ceil(previewAllData.length / pageSize);
    if (page < 1 || page > totalPages) return;
    previewCurrentPage = page;
    renderPreviewPage();
}

let compareDuplicateIndices = []; // 缓存比对结果中的重复索引
let userSkipDuplicates = false; // 用户选择是否跳过重复

// ==================== 数据比对弹窗 ====================
function showCompareModal(duplicates, records) {
    const modal = document.getElementById('compare-modal');
    const countEl = document.getElementById('compare-dup-count');
    const tbody = document.getElementById('compare-body');
    countEl.textContent = duplicates.length;

    let html = '';
    for (let i = 0; i < duplicates.length; i++) {
        const idx = duplicates[i];
        const row = records[idx];
        html += '<tr class="hover:bg-gray-50">';
        html += '<td class="px-4 py-2 text-gray-900">' + formatDate(row.trans_date) + '</td>';
        html += '<td class="px-4 py-2 text-gray-600">' + (row.counterparty || '-') + '</td>';
        html += '<td class="px-4 py-2 text-gray-600"><span class="text-xs px-2 py-0.5 bg-blue-50 text-blue-700 rounded">' + (row.category || '-') + '</span></td>';
        html += '<td class="px-4 py-2 text-gray-600">' + (row.item_name || '-') + '</td>';
        html += '<td class="px-4 py-2 text-right font-medium">&yen;' + (row.amount_real ? row.amount_real.toFixed(2) : '0.00') + '</td>';
        html += '</tr>';
    }
    tbody.innerHTML = html;
    modal.classList.remove('hidden');
}

function closeCompareModal() {
    document.getElementById('compare-modal').classList.add('hidden');
    compareDuplicateIndices = [];
    userSkipDuplicates = false;
}

async function confirmImport(skipDuplicates) {
    closeCompareModal();
    userSkipDuplicates = skipDuplicates;
    // 执行导入
    await doImport();
}

// ==================== 实际导入执行 ====================
async function doImport() {
    if (!selectedFile) return;

    // v8.3: 导入前检查收费大类和银行账号匹配
    var invalidCatRecords = previewAllData.filter(function(r) { return r._valid_category === false; });
    if (invalidCatRecords.length > 0) {
        var rows = invalidCatRecords.map(function(r, i) { return (i + 1) + '. ' + (r.category || '(空)') + ' — ' + (r.counterparty || r.from_account || ''); }).join('\n');
        alert('有 ' + invalidCatRecords.length + ' 条记录的收费大类与系统配置不匹配，请修改后再导入：\n\n' + rows);
        return;
    }
    var invalidBankFrom = previewAllData.filter(function(r) { return r._valid_bank_from === false; });
    if (invalidBankFrom.length > 0) {
        var rows = invalidBankFrom.map(function(r, i) { return (i + 1) + '. 调出账户: ' + (r.from_account || '(空)'); }).join('\n');
        alert('有 ' + invalidBankFrom.length + ' 条调拨记录的转出账户与系统银行账号不匹配，请修改后再导入：\n\n' + rows + '\n\n可在系统设置 > 银行账号管理中维护。');
        return;
    }
    var invalidBankTo = previewAllData.filter(function(r) { return r._valid_bank_to === false; });
    if (invalidBankTo.length > 0) {
        var rows = invalidBankTo.map(function(r, i) { return (i + 1) + '. 转入账户: ' + (r.to_account || '(空)'); }).join('\n');
        alert('有 ' + invalidBankTo.length + ' 条调拨记录的转入账户与系统银行账号不匹配，请修改后再导入：\n\n' + rows + '\n\n可在系统设置 > 银行账号管理中维护。');
        return;
    }

    const loadingModal = document.getElementById('import-loading-modal');
    loadingModal.classList.remove('hidden');
    const startTime = Date.now();

    try {
        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('skip_duplicates', userSkipDuplicates ? 'true' : 'false');

        const res = await fetch('/api/import/excel', {
            method: 'POST',
            body: formData,
        }).then(r => r.json());

        const elapsed = Date.now() - startTime;
        const minDelay = Math.max(0, 5000 - elapsed);

        setTimeout(() => {
            loadingModal.classList.add('hidden');
            const resultDiv = document.getElementById('import-result');
            document.getElementById('preview-section').classList.add('hidden');
            resultDiv.classList.remove('hidden');

            if (res.code === 200) {
                const stats = res.data.stats;
                const checkReport = res.data.check_report || {};

                let checkHtml = '';
                if (checkReport.empty_counterparty && checkReport.empty_counterparty.length > 0) {
                    checkHtml += '<div class="flex items-center gap-2 text-amber-700 bg-amber-50 rounded-lg px-3 py-2 mb-2 text-sm"><svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg><span>第 <strong>' + checkReport.empty_counterparty.join(', ') + '</strong> 行的【对象】为空</span></div>';
                }
                if (checkReport.empty_category && checkReport.empty_category.length > 0) {
                    checkHtml += '<div class="flex items-center gap-2 text-amber-700 bg-amber-50 rounded-lg px-3 py-2 mb-2 text-sm"><svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg><span>第 <strong>' + checkReport.empty_category.join(', ') + '</strong> 行的【收费大类】为空</span></div>';
                }
                if (checkReport.invalid_category && checkReport.invalid_category.length > 0) {
                    const invalidRows = checkReport.invalid_category.map(item => '第' + item.row + '行"' + item.value + '"').join('、');
                    checkHtml += '<div class="flex items-start gap-2 text-red-700 bg-red-50 rounded-lg px-3 py-2 mb-2 text-sm"><svg class="w-4 h-4 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg><div><span class="font-medium">收费大类无效：</span><span class="text-red-600">' + invalidRows + '</span></div></div>';
                }

                // 显示重复处理信息
                const skipped = res.data.skipped || 0;
                let dupInfo = '';
                if (skipped > 0) {
                    dupInfo = '<div class="mb-4 bg-blue-50 rounded-lg p-3 text-sm text-blue-700">已跳过 <strong>' + skipped + '</strong> 条重复记录（用户选择"忽略重复"）</div>';
                }

                resultDiv.innerHTML = '<div class="flex items-center gap-3 mb-4"><svg class="w-6 h-6 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg><h3 class="text-lg font-semibold">导入完成</h3></div>' + dupInfo + (checkHtml ? '<div class="mb-4">' + checkHtml + '</div>' : '') + '<div class="grid grid-cols-3 gap-4"><div class="bg-gray-50 rounded-lg p-4 text-center"><p class="text-2xl font-bold text-slate-800">' + stats.total_rows + '</p><p class="text-sm text-gray-500">总行数</p></div><div class="bg-emerald-50 rounded-lg p-4 text-center"><p class="text-2xl font-bold text-emerald-600">' + stats.imported + '</p><p class="text-sm text-gray-500">成功导入</p></div><div class="bg-orange-50 rounded-lg p-4 text-center"><p class="text-2xl font-bold text-orange-600">' + (stats.skipped_other || 0) + '</p><p class="text-sm text-gray-500">非收支行</p></div></div>' + (res.data.errors && res.data.errors.length > 0 ? '<div class="mt-4 bg-red-50 rounded-lg p-4 max-h-40 overflow-y-auto"><p class="text-sm font-medium text-red-800 mb-2">错误详情：</p>' + res.data.errors.map(e => '<p class="text-sm text-red-600">' + e + '</p>').join('') + '</div>' : '');

                document.getElementById('file-info').classList.add('hidden');
                document.getElementById('excel-file').value = '';
                selectedFile = null;
                previewAllData = [];
                compareDuplicateIndices = [];
                userSkipDuplicates = false;
            } else {
                const resultDiv = document.getElementById('import-result');
                resultDiv.classList.remove('hidden');
                resultDiv.innerHTML = '<div class="bg-red-50 rounded-lg p-4 text-red-700"><strong>导入失败：</strong>' + (res.message || '未知错误') + '</div>';
            }
        }, minDelay);
    } catch (err) {
        const elapsed = Date.now() - startTime;
        const minDelay = Math.max(0, 5000 - elapsed);
        setTimeout(() => {
            loadingModal.classList.add('hidden');
            const resultDiv = document.getElementById('import-result');
            document.getElementById('preview-section').classList.add('hidden');
            resultDiv.classList.remove('hidden');
            resultDiv.innerHTML = '<div class="bg-red-50 rounded-lg p-4 text-red-700"><strong>请求出错：</strong>' + (err.message || '网络连接失败或服务器异常') + '</div>';
        }, minDelay);
    }
}

// ==================== 点击开始导入：先比对 ====================
document.getElementById('import-btn').addEventListener('click', async () => {
    if (!selectedFile || previewAllData.length === 0) return;

    const btn = document.getElementById('import-btn');
    btn.textContent = '比对中...';
    btn.disabled = true;

    try {
        // 第一步：发送比对请求
        const compareRes = await api('/api/import/compare', {
            method: 'POST',
            body: JSON.stringify({ records: previewAllData }),
        });

        btn.textContent = '开始导入';
        btn.disabled = false;

        if (compareRes.code === 200 && compareRes.data && compareRes.data.duplicates && compareRes.data.duplicates.length > 0) {
            // 发现重复，显示比对弹窗让用户选择
            compareDuplicateIndices = compareRes.data.duplicates;
            showCompareModal(compareRes.data.duplicates, previewAllData);
        } else {
            // 无重复，直接进入导入流程
            userSkipDuplicates = false;
            await doImport();
        }
    } catch (err) {
        btn.textContent = '开始导入';
        btn.disabled = false;
        // 比对失败直接尝试导入
        userSkipDuplicates = false;
        await doImport();
    }
});

// ==================== 查询功能 ====================
async function loadCategoriesForSelect() {
    const res = await api('/api/settings/categories');
    if (res.code === 200) {
        categoryData = res.data;
        const select = document.getElementById('q-category');
        const allCats = [...new Set(res.data.map(c => c.name))];
        select.innerHTML = '<option value="">全部</option>' + allCats.map(name =>
            `<option value="${name}">${name}</option>`
        ).join('');
    }
}

async function loadQuery() {
    const params = new URLSearchParams();
    params.append('page', String(queryPage));
    const requestPageSize = queryPageSize === 0 ? 9999 : queryPageSize;
    params.append('page_size', String(requestPageSize));

    const startDate = document.getElementById('q-start-date').value;
    const endDate = document.getElementById('q-end-date').value;
    const transType = document.getElementById('q-type').value;
    const category = document.getElementById('q-category').value;
    const itemName = document.getElementById('q-item').value;
    const paymentMethod = document.getElementById('q-payment').value;
    const keyword = document.getElementById('q-keyword').value;

    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    // v8.2: 调拨类型走独立接口
    var apiUrl;
    if (transType === 'transfer') {
        apiUrl = '/api/transfers/?' + params.toString();
    } else {
        if (transType) params.append('trans_type', transType);
        if (category) params.append('category', category);
        if (itemName) params.append('item_name', itemName);
        if (paymentMethod) params.append('payment_method', paymentMethod);
        if (keyword) params.append('keyword', keyword);
        apiUrl = '/api/transactions/list?' + params.toString();
    }

    // v8.3.1: 同时获取列表和已凭证link_no
    const [res, linkRes] = await Promise.all([
        api(apiUrl),
        api('/api/vouchers/link-nos'),
    ]);
    if (res.code !== 200) return;
    if (linkRes.code === 200 && linkRes.data) {
        linkedVoucherNos = new Set(linkRes.data);
    }

    const respData = res.data;
    queryTotal = respData.total;
    queryAllRecordsCache = respData.list || []; // 缓存结果供编辑弹窗使用
    document.getElementById('q-total').textContent = '共 ' + respData.total + ' 条记录';

    const batchToolbar = document.getElementById('batch-toolbar');
    if (respData.list.length > 0) {
        batchToolbar.classList.remove('hidden');
        batchToolbar.classList.add('flex');
    } else {
        batchToolbar.classList.add('hidden');
        batchToolbar.classList.remove('flex');
    }

    const renderPageSize = queryPageSize === 0 ? 100 : queryPageSize;
    const totalRenderPages = Math.ceil(respData.list.length / renderPageSize);
    const renderPage = Math.min(queryPage, totalRenderPages) || 1;
    // 应用排序
    const sortedList = sortData(respData.list);
    const sliceStart = (renderPage - 1) * renderPageSize;
    const sliceEnd = Math.min(sliceStart + renderPageSize, sortedList.length);
    const displayList = sortedList.slice(sliceStart, sliceEnd);

    const tbody = document.getElementById('query-body');
    if (respData.list.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" class="text-center py-8 text-gray-400">暂无数据</td></tr>';
    } else {
        let html = '';
        for (let idx = 0; idx < displayList.length; idx++) {
            const row = displayList[idx];
            const isChecked = selectedIds.has(row.id) ? 'checked' : '';
            // v8.3.1: 检查是否已生成凭证（link_no 或短格式回退）
            const shortType = row.trans_type === 'income' ? 'I' : row.trans_type === 'expense' ? 'E' : 'T';
            const fallbackKey = 'FK-' + shortType + row.id;
            const hasVoucher = (row.link_no && linkedVoucherNos.has(row.link_no)) || linkedVoucherNos.has(fallbackKey);
            const rowClass = hasVoucher ? 'bg-emerald-50/40 border-l-4 border-emerald-400' : 'hover:bg-gray-50';
            const checkboxDisabled = hasVoucher ? 'disabled' : '';
            const checkboxTitle = hasVoucher ? 'title="已生成凭证，不可重复选择"' : '';
            const voucherBadge = hasVoucher ? '<span class="ml-1 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-100 text-emerald-700">已凭证</span>' : '';
            html += '<tr class="' + rowClass + ' transition-colors" data-id="' + row.id + '">';
            html += '<td class="px-3 py-3 text-center"><input type="checkbox" class="row-checkbox w-4 h-4 text-primary rounded border-gray-300 focus:ring-primary" value="' + row.id + '" ' + isChecked + ' ' + checkboxDisabled + ' ' + checkboxTitle + ' onchange="toggleRowSelect(' + row.id + ', this.checked)"></td>';
            html += '<td class="px-4 py-3 text-gray-900 whitespace-nowrap">' + formatDate(row.trans_date) + '</td>';
            html += '<td class="px-4 py-3"><span class="inline-flex px-2 py-0.5 rounded text-xs font-medium ' + typeClasses[row.trans_type] + '">' + typeLabels[row.trans_type] + '</span>' + voucherBadge + '</td>';
            html += '<td class="px-4 py-3 text-gray-600">' + (row.counterparty || '') + '</td>';
            html += '<td class="px-4 py-3 text-gray-600"><span class="text-xs px-2 py-0.5 bg-blue-50 text-blue-700 rounded">' + (row.category || '-') + '</span></td>';
            html += '<td class="px-4 py-3 text-gray-600">' + (row.item_name || '') + '</td>';
            html += '<td class="px-4 py-3 text-right text-gray-600">' + (row.amount_receivable ? row.amount_receivable.toFixed(2) : '0.00') + '</td>';
            html += '<td class="px-4 py-3 text-right font-medium text-gray-900">' + (row.amount_real ? row.amount_real.toFixed(2) : '0.00') + '</td>';
            html += '<td class="px-4 py-3 text-gray-600">' + (paymentLabels[row.payment_method] || row.payment_method || '') + '</td>';
            html += '<td class="px-4 py-3 text-gray-500 max-w-[200px] truncate">' + (row.remark || '') + '</td>';
            html += '<td class="px-4 py-3 text-center">';
            html += '<button onclick="openEditModal(' + row.id + ')" class="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs text-blue-600 bg-blue-50 hover:bg-blue-100 rounded-lg transition-colors mr-1">';
            html += '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/></svg>编辑';
            html += '</button>';
            html += '<button onclick="deleteTransaction(' + row.id + ')" class="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs text-red-600 bg-red-50 hover:bg-red-100 rounded-lg transition-colors">';
            html += '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>删除';
            html += '</button>';
            html += '</td>';
            html += '</tr>';
        }
        if (queryPageSize === 0 && respData.list.length > 100) {
            html += '<tr><td colspan="10" class="text-center py-4 text-gray-400 bg-gray-50">已渲染 ' + sliceEnd + ' / ' + respData.list.length + ' 条，数据量较大，建议使用分页模式查看</td></tr>';
        }
        tbody.innerHTML = html;
        updateSelectedCount();
    }

    const totalPages = Math.ceil(queryTotal / (queryPageSize === 0 ? 100 : queryPageSize));
    const paginationDiv = document.getElementById('query-pagination');
    if (totalPages > 1) {
        paginationDiv.classList.remove('hidden');
        document.getElementById('query-page-info').textContent = '第 ' + queryPage + ' / ' + totalPages + ' 页';
        let buttons = '';
        buttons += '<button onclick="changeQueryPage(' + (queryPage - 1) + ')"' + (queryPage <= 1 ? ' disabled' : '') + ' class="p-2 rounded-lg hover:bg-gray-100 disabled:opacity-30 transition-colors"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/></svg></button>';
        for (let i = 1; i <= totalPages; i++) {
            if (i === 1 || i === totalPages || (i >= queryPage - 1 && i <= queryPage + 1)) {
                buttons += '<button onclick="changeQueryPage(' + i + ')" class="w-8 h-8 rounded-lg text-sm font-medium transition-colors ' + (queryPage === i ? 'bg-primary text-white' : 'hover:bg-gray-100 text-gray-600') + '">' + i + '</button>';
            } else if (i === queryPage - 2 || i === queryPage + 2) {
                buttons += '<span class="px-2 text-gray-400">...</span>';
            }
        }
        buttons += '<button onclick="changeQueryPage(' + (queryPage + 1) + ')"' + (queryPage >= totalPages ? ' disabled' : '') + ' class="p-2 rounded-lg hover:bg-gray-100 disabled:opacity-30 transition-colors"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg></button>';
        document.getElementById('query-page-buttons').innerHTML = buttons;
    } else {
        paginationDiv.classList.add('hidden');
    }
}

function changeQueryPageSize() {
    const select = document.getElementById('q-page-size');
    queryPageSize = parseInt(select.value);
    queryPage = 1;
    isQueryAllSelected = false;
    document.getElementById('header-select-all').checked = false;
    document.getElementById('select-all').checked = false;
    loadQuery();
}

function changeQueryPage(page) {
    const totalPages = Math.ceil(queryTotal / queryPageSize);
    if (page < 1 || page > totalPages) return;
    queryPage = page;
    // 翻页时重置全选状态
    isQueryAllSelected = false;
    document.getElementById('header-select-all').checked = false;
    document.getElementById('select-all').checked = false;
    loadQuery();
}

// ==================== 清空所有记录 ====================
async function clearAllRecords() {
    if (!confirm('⚠️ 确定要清空所有记录吗？此操作不可恢复！\n\n将删除数据库中所有已导入的交易记录。')) return;
    if (!confirm('再次确认：是否真的要删除所有记录？')) return;
    try {
        const res = await api('/api/transactions/clear', { method: 'POST' });
        if (res.code === 200) {
            alert('已清空所有记录');
            selectedIds.clear();
            // 同时清除导入数据预览和复位导入状态
            clearCurrentPreview();
            if (currentPage === 'query') loadQuery();
            if (currentPage === 'dashboard') loadDashboard();
            if (currentPage === 'statistics') loadStatistics();
        } else {
            alert('清空失败: ' + res.message);
        }
    } catch (err) {
        alert('请求出错: ' + (err.message || '网络连接失败'));
    }
}

// ==================== 批量删除 ====================
function toggleRowSelect(id, checked) {
    // v8.3.1: 检查是否已生成凭证（link_no 或短格式回退），已凭证不可选择
    var row = queryAllRecordsCache.find(function(r) { return r.id === id; });
    if (checked && row) {
        var shortType = row.trans_type === 'income' ? 'I' : row.trans_type === 'expense' ? 'E' : 'T';
        var fallbackKey = 'FK-' + shortType + id;
        var hasVoucher = (row.link_no && linkedVoucherNos.has(row.link_no)) || linkedVoucherNos.has(fallbackKey);
        if (hasVoucher) return; // 已生成凭证，不允许选择
    }
    if (checked) {
        selectedIds.add(id);
    } else {
        selectedIds.delete(id);
    }
    updateSelectedCount();
}

function toggleSelectAll() {
    // 切换全选状态（取反）
    isQueryAllSelected = !isQueryAllSelected;
    
    const checkboxes = document.querySelectorAll('.row-checkbox');
    const headerCb = document.getElementById('header-select-all');
    const toolbarCb = document.getElementById('select-all');
    
    // 同步两个全选框状态
    headerCb.checked = isQueryAllSelected;
    toolbarCb.checked = isQueryAllSelected;
    
    // v8.3.1: 同步所有行复选框（跳过已凭证行）
    checkboxes.forEach(cb => {
        // 跳过已禁用的复选框（已凭证行）
        if (cb.disabled) {
            cb.checked = false;
            return;
        }
        cb.checked = isQueryAllSelected;
        const id = parseInt(cb.value);
        if (isQueryAllSelected) {
            selectedIds.add(id);
        } else {
            selectedIds.delete(id);
        }
    });
    
    updateSelectedCount();
}

function updateSelectedCount() {
    document.getElementById('selected-count').textContent = `已选 ${selectedIds.size} 条`;
}

async function batchDelete() {
    if (selectedIds.size === 0) {
        alert('请先勾选要删除的记录');
        return;
    }
    if (!confirm(`确定删除选中的 ${selectedIds.size} 条记录吗？`)) return;
    try {
        const res = await api('/api/transactions/batch-delete', {
            method: 'POST',
            body: JSON.stringify({ ids: Array.from(selectedIds) }),
        });
        if (res.code === 200) {
            alert(res.message);
            selectedIds.clear();
            document.getElementById('header-select-all').checked = false;
            document.getElementById('select-all').checked = false;
            loadQuery();
        } else {
            alert('删除失败: ' + res.message);
        }
    } catch (err) {
        alert('请求出错: ' + (err.message || '网络连接失败'));
    }
}

// ==================== 批量生成凭证 v8.0 ====================

async function batchGenerateVouchers() {
    if (selectedIds.size === 0) {
        alert('请先勾选要生成凭证的记录');
        return;
    }
    // v8.3.1: 强制从数据库刷新已凭证状态，不依赖缓存
    try {
        var linkRes = await api('/api/vouchers/link-nos');
        if (linkRes.code === 200 && linkRes.data) {
            linkedVoucherNos = new Set(linkRes.data);
        }
    } catch (e) {}
    // v8.3.1: 过滤已凭证记录（link_no 或短格式回退检查）
    var eligibleIds = Array.from(selectedIds).filter(function(id) {
        var row = queryAllRecordsCache.find(function(r) { return r.id === id; });
        if (!row) return false;
        // 检查 link_no
        if (row.link_no && linkedVoucherNos.has(row.link_no)) return false;
        // 回退检查：短格式 FK-{T/E/I}{id}
        var shortType = row.trans_type === 'income' ? 'I' : row.trans_type === 'expense' ? 'E' : 'T';
        var fKey = 'FK-' + shortType + id;
        if (linkedVoucherNos.has(fKey)) return false;
        return true;
    });
    var skippedCount = selectedIds.size - eligibleIds.length;
    if (eligibleIds.length === 0) {
        alert('选中的 ' + selectedIds.size + ' 条记录均已生成凭证，无需重复操作。');
        return;
    }
    var confirmMsg = '确定为 ' + eligibleIds.length + ' 条记录生成凭证草稿吗？';
    if (skippedCount > 0) {
        confirmMsg += '\n（另有 ' + skippedCount + ' 条已生成凭证的记录将自动跳过）';
    }
    if (!confirm(confirmMsg)) return;

    const btn = document.querySelector('button[onclick="batchGenerateVouchers()"]');
    const origText = btn.innerHTML;
    btn.innerHTML = '<svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg> 生成中...';
    btn.disabled = true;

    try {
        const res = await api('/api/vouchers/batch-generate', {
            method: 'POST',
            body: JSON.stringify({ record_ids: eligibleIds }),
        });

        btn.innerHTML = origText;
        btn.disabled = false;

        if (res.code === 200) {
            const data = res.data;
            let msg = `成功生成 ${data.success} 条凭证`;
            if (data.failed > 0) {
                msg += `，失败 ${data.failed} 条`;
                // 显示前5条错误
                if (data.errors && data.errors.length > 0) {
                    msg += '\n\n失败原因：\n' + data.errors.slice(0, 5).join('\n');
                    if (data.errors.length > 5) msg += '\n...等共 ' + data.errors.length + ' 条错误';
                }
            }
            alert(msg);

            if (data.success > 0) {
                selectedIds.clear();
                document.getElementById('header-select-all').checked = false;
                document.getElementById('select-all').checked = false;
                // v8.3.1: 生成凭证后强制刷新已凭证集合，再刷新列表
                var linkRes = await api('/api/vouchers/link-nos');
                if (linkRes.code === 200 && linkRes.data) {
                    linkedVoucherNos = new Set(linkRes.data);
                }
                loadQuery();
                // 询问是否跳转到凭证管理
                if (confirm('是否跳转到凭证管理页面查看生成的凭证？')) {
                    showPage('vouchers');
                }
            }
        } else {
            alert('生成失败: ' + res.message);
        }
    } catch (err) {
        btn.innerHTML = origText;
        btn.disabled = false;
        alert('请求出错: ' + (err.message || '网络连接失败'));
    }
}

async function deleteTransaction(id) {
    if (!confirm('确定删除这条记录？')) return;
    const res = await api(`/api/transactions/${id}`, { method: 'DELETE' });
    if (res.code === 200) {
        selectedIds.delete(id);
        loadQuery();
    }
}

document.getElementById('q-search-btn').addEventListener('click', () => { queryPage = 1; loadQuery(); });
document.getElementById('q-reset-btn').addEventListener('click', () => {
    document.getElementById('q-start-date').value = '';
    document.getElementById('q-end-date').value = '';
    document.getElementById('q-type').value = '';
    document.getElementById('q-category').value = '';
    document.getElementById('q-item').value = '';
    document.getElementById('q-payment').value = '';
    document.getElementById('q-keyword').value = '';
    queryPage = 1;
    loadQuery();
});

// ==================== 统计分析 ====================
async function loadStatistics() {
    const year = document.getElementById('stat-year').value || String(new Date().getFullYear());
    const month = document.getElementById('stat-month').value || new Date().toISOString().slice(0, 7);
    const startDate = document.getElementById('stat-start-date').value;
    const endDate = document.getElementById('stat-end-date').value;
    
    // 构建带日期参数的URL
    const summaryParams = new URLSearchParams();
    if (startDate) summaryParams.append('start_date', startDate);
    if (endDate) summaryParams.append('end_date', endDate);
    const summaryUrl = '/api/transactions/statistics/summary' + (summaryParams.toString() ? '?' + summaryParams.toString() : '');
    
    const [summaryRes, monthlyRes, dailyRes] = await Promise.all([
        api(summaryUrl),
        api(`/api/transactions/statistics/monthly?year=${year}${startDate ? '&start_date=' + startDate : ''}${endDate ? '&end_date=' + endDate : ''}`),
        api(`/api/transactions/statistics/daily?month=${month}`),
    ]);
    
    if (summaryRes.code === 200) renderSummary(summaryRes.data);
    if (monthlyRes.code === 200) renderMonthlyChart(monthlyRes.data, year);
    if (dailyRes.code === 200) renderDailyChart(dailyRes.data);
}

function renderSummary(data) {
    const container = document.getElementById('stat-summary');
    container.innerHTML = `
        <div class="bg-white rounded-xl shadow-sm border p-5">
            <div class="flex items-center justify-between">
                <div><p class="text-sm text-gray-500">累计收入</p><p class="text-2xl font-bold text-emerald-600 mt-1">¥${data.total_income.toFixed(2)}</p></div>
                <div class="w-10 h-10 bg-emerald-100 rounded-lg flex items-center justify-center"><svg class="w-5 h-5 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"/></svg></div>
            </div>
        </div>
        <div class="bg-white rounded-xl shadow-sm border p-5">
            <div class="flex items-center justify-between">
                <div><p class="text-sm text-gray-500">累计支出</p><p class="text-2xl font-bold text-red-600 mt-1">¥${data.total_expense.toFixed(2)}</p></div>
                <div class="w-10 h-10 bg-red-100 rounded-lg flex items-center justify-center"><svg class="w-5 h-5 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 17h8m0 0V9m0 8l-8-8-4 4-6-6"/></svg></div>
            </div>
        </div>
        <div class="bg-white rounded-xl shadow-sm border p-5">
            <div class="flex items-center justify-between">
                <div><p class="text-sm text-gray-500">净结余</p><p class="text-2xl font-bold ${data.balance >= 0 ? 'text-emerald-600' : 'text-red-600'} mt-1">¥${data.balance.toFixed(2)}</p></div>
                <div class="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center"><svg class="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z"/></svg></div>
            </div>
        </div>`;

    // 收费大类拆分
    const incomeCategory = {};
    const expenseCategory = {};
    if (data.by_category) {
        data.by_category.forEach(item => {
            const cat = item.category || '未分类';
            if (item.trans_type === 'income') {
                incomeCategory[cat] = (incomeCategory[cat] || 0) + item.total;
            } else {
                expenseCategory[cat] = (expenseCategory[cat] || 0) + item.total;
            }
        });
    }

    // 收入：SVG圆饼图 + 表格
    const incomeTotal = Object.values(incomeCategory).reduce((a, b) => a + b, 0);
    if (incomeTotal > 0) {
        document.getElementById('income-pie-chart').innerHTML = renderPieChart(incomeCategory, 'emerald');
        document.getElementById('income-category-table').innerHTML = renderCategoryTable(incomeCategory, incomeTotal);
    } else {
        document.getElementById('income-pie-chart').innerHTML = '<p class="text-gray-400 py-8">暂无收入数据</p>';
        document.getElementById('income-category-table').innerHTML = '<p class="text-gray-400 py-8">暂无收入数据</p>';
    }

    // 支出：SVG圆饼图 + 表格
    const expenseTotal = Object.values(expenseCategory).reduce((a, b) => a + b, 0);
    if (expenseTotal > 0) {
        document.getElementById('expense-pie-chart').innerHTML = renderPieChart(expenseCategory, 'red');
        document.getElementById('expense-category-table').innerHTML = renderCategoryTable(expenseCategory, expenseTotal);
    } else {
        document.getElementById('expense-pie-chart').innerHTML = '<p class="text-gray-400 py-8">暂无支出数据</p>';
        document.getElementById('expense-category-table').innerHTML = '<p class="text-gray-400 py-8">暂无支出数据</p>';
    }
}

function renderPieChart(categoryData, colorScheme) {
    const colors = {
        emerald: ['#059669', '#10b981', '#34d399', '#6ee7b7', '#a7f3d0', '#047857', '#0e7490', '#0891b2', '#06b6d4'],
        red: ['#dc2626', '#ef4444', '#f87171', '#fca5a5', '#fecaca', '#991b1b', '#b91c1c', '#c2410c', '#ea580c']
    };
    const palette = colors[colorScheme] || colors.emerald;
    const entries = Object.entries(categoryData).sort((a, b) => b[1] - a[1]);
    const total = entries.reduce((s, [, v]) => s + v, 0);
    const r = 100;
    const cx = 120;
    const cy = 120;
    let angle = -Math.PI / 2;
    let paths = '';
    let legend = '';
    entries.forEach(([name, val], i) => {
        const sweep = (val / total) * Math.PI * 2;
        const x1 = cx + r * Math.cos(angle);
        const y1 = cy + r * Math.sin(angle);
        const x2 = cx + r * Math.cos(angle + sweep);
        const y2 = cy + r * Math.sin(angle + sweep);
        const large = sweep > Math.PI ? 1 : 0;
        paths += `<path d="M${cx},${cy} L${x1},${y1} A${r},${r} 0 ${large},1 ${x2},${y2} Z" fill="${palette[i % palette.length]}" stroke="white" stroke-width="2"/>`;
        legend += `<div class="flex items-center gap-2 mb-1 text-sm"><span class="w-3 h-3 rounded-sm" style="background:${palette[i % palette.length]}"></span><span class="text-gray-700">${name}</span><span class="ml-auto font-medium">${(val/total*100).toFixed(1)}%</span></div>`;
        angle += sweep;
    });
    return `
        <svg width="240" height="240" viewBox="0 0 240 240">${paths}<circle cx="${cx}" cy="${cy}" r="55" fill="white"/></svg>
        <div class="ml-4 min-w-[140px]">${legend}</div>`;
}

function renderCategoryTable(categoryData, total) {
    const entries = Object.entries(categoryData).sort((a, b) => b[1] - a[1]);
    return `<table class="w-full text-sm"><thead class="bg-gray-50"><tr><th class="px-4 py-3 text-left font-medium text-gray-600">收费大类</th><th class="px-4 py-3 text-right font-medium text-gray-600">金额</th><th class="px-4 py-3 text-right font-medium text-gray-600">占比</th></tr></thead><tbody class="divide-y">${entries.map(([name, val]) => `<tr class="hover:bg-gray-50"><td class="px-4 py-3 font-medium text-gray-900">${name || '未分类'}</td><td class="px-4 py-3 text-right">¥${val.toFixed(2)}</td><td class="px-4 py-3 text-right text-gray-500">${(val/total*100).toFixed(1)}%</td></tr>`).join('')}</tbody></table>`;
}

function renderMonthlyChart(data, year) {
    const yearSelect = document.getElementById('stat-year');
    if (yearSelect.innerHTML === '') {
        for (let y = new Date().getFullYear() - 2; y <= new Date().getFullYear() + 2; y++) {
            yearSelect.innerHTML += `<option value="${y}" ${y === Number(year) ? 'selected' : ''}>${y}年</option>`;
        }
    }
    
    const grouped = {};
    data.forEach(item => {
        if (!grouped[item.month]) grouped[item.month] = { month: item.month, income: 0, expense: 0 };
        if (item.trans_type === 'income') grouped[item.month].income += item.total;
        else grouped[item.month].expense += item.total;
    });
    const chartData = Object.values(grouped);
    const maxVal = Math.max(...chartData.map(d => Math.max(d.income, d.expense)), 1);
    
    const container = document.getElementById('stat-monthly-chart');
    if (chartData.length === 0) {
        container.innerHTML = '<p class="text-gray-400 text-center py-8">暂无数据</p>';
        return;
    }
    
    container.innerHTML = `
        <div class="flex items-center gap-6 text-sm mb-3">
            <div class="flex items-center gap-2"><div class="w-3 h-3 bg-emerald-500 rounded-sm"></div><span class="text-gray-600">收入</span></div>
            <div class="flex items-center gap-2"><div class="w-3 h-3 bg-red-400 rounded-sm"></div><span class="text-gray-600">支出</span></div>
        </div>
        ${chartData.map(d => `
            <div class="space-y-1">
                <div class="flex items-center justify-between text-xs text-gray-500">
                    <span>${d.month}</span>
                    <div class="flex gap-4"><span class="text-emerald-600">收: ¥${d.income.toFixed(0)}</span><span class="text-red-500">支: ¥${d.expense.toFixed(0)}</span></div>
                </div>
                <div class="flex gap-1 h-6">
                    <div class="bg-emerald-500 rounded-l transition-all" style="width: ${(d.income / maxVal) * 50}%"></div>
                    <div class="w-px bg-gray-200"></div>
                    <div class="bg-red-400 rounded-r transition-all" style="width: ${(d.expense / maxVal) * 50}%"></div>
                </div>
            </div>
        `).join('')}`;
}

function renderDailyChart(data) {
    const monthInput = document.getElementById('stat-month');
    if (!monthInput.value) monthInput.value = new Date().toISOString().slice(0, 7);
    
    const grouped = {};
    data.forEach(item => {
        if (!grouped[item.date]) grouped[item.date] = { date: item.date, income: 0, expense: 0 };
        if (item.trans_type === 'income') grouped[item.date].income += item.total;
        else grouped[item.date].expense += item.total;
    });
    const chartData = Object.values(grouped).slice(-31);
    const maxVal = Math.max(...chartData.map(d => Math.max(d.income, d.expense)), 1);
    
    const container = document.getElementById('stat-daily-chart');
    if (chartData.length === 0) {
        container.innerHTML = '<p class="text-gray-400 text-center py-8">暂无数据</p>';
        return;
    }
    
    container.innerHTML = chartData.map(d => `
        <div class="flex items-center gap-3">
            <span class="w-24 text-xs text-gray-500 flex-shrink-0">${d.date}</span>
            <div class="flex-1 flex h-5 bg-gray-100 rounded overflow-hidden">
                <div class="bg-emerald-500 transition-all" style="width: ${(d.income / maxVal) * 100}%"></div>
            </div>
            <span class="w-16 text-xs text-emerald-600 text-right">${d.income > 0 ? d.income.toFixed(0) : ''}</span>
            <div class="flex-1 flex h-5 bg-gray-100 rounded overflow-hidden">
                <div class="bg-red-400 transition-all" style="width: ${(d.expense / maxVal) * 100}%"></div>
            </div>
            <span class="w-16 text-xs text-red-500 text-right">${d.expense > 0 ? d.expense.toFixed(0) : ''}</span>
        </div>
    `).join('');
}

document.getElementById('stat-year').addEventListener('change', loadStatistics);
document.getElementById('stat-month').addEventListener('change', loadStatistics);

// ==================== 编辑弹窗 ====================
let currentEditId = null;

async function openEditModal(id) {
    // 从当前列表中找到记录
    const row = queryAllRecordsCache.find(r => r.id === id);
    if (!row) {
        alert('记录不存在，请先查询');
        return;
    }

    // 动态加载收费大类到下拉框
    var catSelect = document.getElementById('edit-category');
    try {
        var res = await api('/api/settings/categories');
        if (res.code === 200 && res.data) {
            var options = '<option value="">请选择</option>';
            var allNames = [...new Set(res.data.map(function(c) { return c.name; }))];
            allNames.forEach(function(name) {
                options += '<option value="' + name + '">' + name + '</option>';
            });
            catSelect.innerHTML = options;
        }
    } catch (e) {
        // 加载失败时保持原有选项
    }

    currentEditId = id;
    document.getElementById('edit-id').value = id;
    document.getElementById('edit-date').value = row.trans_date;
    document.getElementById('edit-type').value = row.trans_type;
    document.getElementById('edit-counterparty').value = row.counterparty || '';
    catSelect.value = row.category || '';
    document.getElementById('edit-item').value = row.item_name || '';
    document.getElementById('edit-receivable').value = row.amount_receivable || 0;
    document.getElementById('edit-real').value = row.amount_real || 0;
    document.getElementById('edit-payment').value = row.payment_method || 'cash';
    document.getElementById('edit-remark').value = row.remark || '';
    document.getElementById('edit-modal').classList.remove('hidden');
}

function closeEditModal() {
    document.getElementById('edit-modal').classList.add('hidden');
    currentEditId = null;
}

async function saveEditRecord(event) {
    event.preventDefault();
    if (!currentEditId) return;
    const data = {
        trans_date: document.getElementById('edit-date').value,
        trans_type: document.getElementById('edit-type').value,
        counterparty: document.getElementById('edit-counterparty').value,
        category: document.getElementById('edit-category').value,
        item_name: document.getElementById('edit-item').value,
        amount_receivable: parseFloat(document.getElementById('edit-receivable').value) || 0,
        amount_real: parseFloat(document.getElementById('edit-real').value) || 0,
        payment_method: document.getElementById('edit-payment').value,
        remark: document.getElementById('edit-remark').value,
    };
    try {
        const res = await api('/api/transactions/' + currentEditId, {
            method: 'PUT',
            body: JSON.stringify(data),
        });
        if (res.code === 200) {
            closeEditModal();
            alert('保存成功');
            loadQuery();
        } else {
            alert('保存失败: ' + res.message);
        }
    } catch (err) {
        alert('保存出错: ' + (err.message || '网络异常'));
    }
}

// ==================== 手动录入表格 v7.2 ====================
let entryCategoryOptions = ''; // 动态加载的收费大类选项 HTML
let entryBankOptions = '';     // v8.3 动态加载的银行账号选项 HTML
let entryIncomeCount = 0;
let entryExpenseCount = 0;
let entryTransferCount = 0;
let currentEntryTab = 'income'; // v8.3 当前选中的录入Tab

function getTodayStr() {
    var t = new Date();
    return t.getFullYear() + '-' + String(t.getMonth() + 1).padStart(2, '0') + '-' + String(t.getDate()).padStart(2, '0');
}

function getDefaultCategoryOptions() {
    return '<option value="">选择</option><option value="治疗">治疗</option><option value="治疗加固定修复">治疗加固定修复</option><option value="固定修复">固定修复</option><option value="种植">种植</option><option value="活动牙">活动牙</option><option value="财务费用">财务费用</option><option value="美学">美学</option><option value="治疗加美学">治疗加美学</option>';
}

function switchEntryTab(tab) {
    // v8.3 Tab切换
    currentEntryTab = tab;
    document.getElementById('entry-panel-income').classList.add('hidden');
    document.getElementById('entry-panel-expense').classList.add('hidden');
    document.getElementById('entry-panel-transfer').classList.add('hidden');
    document.getElementById('entry-panel-' + tab).classList.remove('hidden');

    // 更新Tab样式
    ['income', 'expense', 'transfer'].forEach(function(t) {
        var btn = document.getElementById('entry-tab-' + t);
        if (t === tab) {
            var colorClass = tab === 'income' ? 'emerald' : tab === 'expense' ? 'red' : 'blue';
            btn.className = 'px-5 py-3 text-sm font-medium border-b-2 border-' + colorClass + '-500 text-' + colorClass + '-600 bg-' + colorClass + '-50/50 rounded-t-lg transition-colors';
        } else {
            btn.className = 'px-5 py-3 text-sm font-medium border-b-2 border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50 rounded-t-lg transition-colors';
        }
    });
}

async function initEntryPage() {
    // 动态加载收费大类
    if (!entryCategoryOptions) {
        try {
            var res = await api('/api/settings/categories');
            if (res.code === 200 && res.data) {
                var allNames = [...new Set(res.data.map(function(c) { return c.name; }))];
                var opts = '<option value="">选择</option>';
                allNames.forEach(function(name) {
                    opts += '<option value="' + name + '">' + name + '</option>';
                });
                entryCategoryOptions = opts;
            }
        } catch (e) {
            // 加载失败时使用默认
        }
        if (!entryCategoryOptions) {
            entryCategoryOptions = getDefaultCategoryOptions();
        }
    }
    // v8.3: 动态加载银行账号
    if (!entryBankOptions) {
        try {
            var res = await api('/api/bank-accounts');
            if (res.code === 200 && res.data) {
                var opts = '<option value="">选择</option>';
                res.data.forEach(function(b) {
                    if (b.is_active) {
                        opts += '<option value="' + b.account_name + '" data-id="' + b.id + '">' + b.account_name + '</option>';
                    }
                });
                entryBankOptions = opts;
            }
        } catch (e) {
            entryBankOptions = '<option value="">选择</option>';
        }
    }
    // 首次进入时初始化1行空行
    if (entryIncomeCount === 0) {
        addEntryRow('income');
    }
    if (entryExpenseCount === 0) {
        addEntryRow('expense');
    }
    if (entryTransferCount === 0) {
        addEntryRow('transfer');
    }
    // 默认显示收入Tab
    switchEntryTab('income');
}

function addEntryRow(type) {
    var isIncome = type === 'income';
    var isExpense = type === 'expense';
    var isTransfer = type === 'transfer';
    var tbodyId = isIncome ? 'entry-income-body' : isExpense ? 'entry-expense-body' : 'entry-transfer-body';
    var countElId = isIncome ? 'income-row-count' : isExpense ? 'expense-row-count' : 'transfer-row-count';
    var idx = isIncome ? ++entryIncomeCount : isExpense ? ++entryExpenseCount : ++entryTransferCount;
    var rowId = 'entry-row-' + type + '-' + idx;
    var tbody = document.getElementById(tbodyId);
    var tr = document.createElement('tr');
    tr.id = rowId;
    tr.className = 'hover:bg-gray-50 transition-colors';

    if (isTransfer) {
        // v8.3 调拨行
        tr.innerHTML =
            '<td class="px-3 py-2"><input type="date" class="entry-transfer-date w-full px-2 py-1.5 border border-gray-200 rounded text-sm focus:outline-none focus:ring-1 focus:ring-primary" value="' + getTodayStr() + '"></td>' +
            '<td class="px-3 py-2"><select class="entry-transfer-from w-full px-2 py-1.5 border border-gray-200 rounded text-sm focus:outline-none focus:ring-1 focus:ring-primary bg-white">' + (entryBankOptions || '<option value="">选择</option>') + '</select></td>' +
            '<td class="px-3 py-2"><select class="entry-transfer-to w-full px-2 py-1.5 border border-gray-200 rounded text-sm focus:outline-none focus:ring-1 focus:ring-primary bg-white">' + (entryBankOptions || '<option value="">选择</option>') + '</select></td>' +
            '<td class="px-3 py-2"><input type="number" step="0.01" class="entry-transfer-planned w-full px-2 py-1.5 border border-gray-200 rounded text-sm text-right focus:outline-none focus:ring-1 focus:ring-primary" placeholder="0.00"></td>' +
            '<td class="px-3 py-2"><input type="number" step="0.01" class="entry-transfer-real w-full px-2 py-1.5 border border-gray-200 rounded text-sm text-right focus:outline-none focus:ring-1 focus:ring-primary" placeholder="0.00"></td>' +
            '<td class="px-3 py-2"><input type="text" class="entry-transfer-remark w-full px-2 py-1.5 border border-gray-200 rounded text-sm focus:outline-none focus:ring-1 focus:ring-primary" placeholder="备注"></td>' +
            '<td class="px-3 py-2 text-center"><button onclick="removeEntryRow(\'transfer\', ' + idx + ')" class="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded transition-colors"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg></button></td>';
    } else {
        // 收入/支出行
        tr.innerHTML =
            '<td class="px-3 py-2"><input type="date" class="entry-' + type + '-date w-full px-2 py-1.5 border border-gray-200 rounded text-sm focus:outline-none focus:ring-1 focus:ring-primary" value="' + getTodayStr() + '"></td>' +
            '<td class="px-3 py-2"><input type="text" class="entry-' + type + '-counterparty w-full px-2 py-1.5 border border-gray-200 rounded text-sm focus:outline-none focus:ring-1 focus:ring-primary" placeholder="对象"></td>' +
            '<td class="px-3 py-2"><select class="entry-' + type + '-category w-full px-2 py-1.5 border border-gray-200 rounded text-sm focus:outline-none focus:ring-1 focus:ring-primary bg-white">' + (entryCategoryOptions || getDefaultCategoryOptions()) + '</select></td>' +
            '<td class="px-3 py-2"><input type="text" class="entry-' + type + '-item w-full px-2 py-1.5 border border-gray-200 rounded text-sm focus:outline-none focus:ring-1 focus:ring-primary" placeholder="项目"></td>' +
            '<td class="px-3 py-2"><input type="number" step="0.01" class="entry-' + type + '-receivable w-full px-2 py-1.5 border border-gray-200 rounded text-sm text-right focus:outline-none focus:ring-1 focus:ring-primary" placeholder="0.00"></td>' +
            '<td class="px-3 py-2"><input type="number" step="0.01" class="entry-' + type + '-real w-full px-2 py-1.5 border border-gray-200 rounded text-sm text-right focus:outline-none focus:ring-1 focus:ring-primary" placeholder="0.00"></td>' +
            '<td class="px-3 py-2"><input type="text" class="entry-' + type + '-remark w-full px-2 py-1.5 border border-gray-200 rounded text-sm focus:outline-none focus:ring-1 focus:ring-primary" placeholder="备注"></td>' +
            '<td class="px-3 py-2 text-center"><button onclick="removeEntryRow(\'' + type + '\', ' + idx + ')" class="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded transition-colors"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg></button></td>';
    }
    tbody.appendChild(tr);
    var actualCount = tbody.children.length;
    document.getElementById(countElId).textContent = actualCount + ' 行';
}

function removeEntryRow(type, idx) {
    var rowId = 'entry-row-' + type + '-' + idx;
    var row = document.getElementById(rowId);
    if (row) row.remove();
    var countElId = type === 'income' ? 'income-row-count' : type === 'expense' ? 'expense-row-count' : 'transfer-row-count';
    var tbodyId = type === 'income' ? 'entry-income-body' : type === 'expense' ? 'entry-expense-body' : 'entry-transfer-body';
    var actualCount = document.getElementById(tbodyId).children.length;
    document.getElementById(countElId).textContent = actualCount + ' 行';
}

function clearAllEntryRows() {
    if (!confirm('确定要清空所有录入行吗？')) return;
    document.getElementById('entry-income-body').innerHTML = '';
    document.getElementById('entry-expense-body').innerHTML = '';
    document.getElementById('entry-transfer-body').innerHTML = '';
    entryIncomeCount = 0;
    entryExpenseCount = 0;
    entryTransferCount = 0;
    document.getElementById('income-row-count').textContent = '0 行';
    document.getElementById('expense-row-count').textContent = '0 行';
    document.getElementById('transfer-row-count').textContent = '0 行';
    addEntryRow('income');
    addEntryRow('expense');
    addEntryRow('transfer');
}

async function saveAllEntries() {
    // v8.3.2: 保存按钮只对当前激活标签页负责
    var tab = currentEntryTab;
    var records = [];
    var transferRecords = [];
    var errors = [];
    var successCount = 0;
    var failCount = 0;
    var apiUrl = '';

    if (tab === 'income') {
        // ===== 只收集收入行 =====
        var incomeDates = document.querySelectorAll('.entry-income-date');
        var incomeCounterparties = document.querySelectorAll('.entry-income-counterparty');
        var incomeCategories = document.querySelectorAll('.entry-income-category');
        var incomeItems = document.querySelectorAll('.entry-income-item');
        var incomeReceivables = document.querySelectorAll('.entry-income-receivable');
        var incomeReals = document.querySelectorAll('.entry-income-real');
        var incomeRemarks = document.querySelectorAll('.entry-income-remark');

        for (var i = 0; i < incomeDates.length; i++) {
            var realVal = parseFloat(incomeReals[i].value);
            if (!incomeDates[i].value && !incomeCounterparties[i].value && !realVal) continue;
            if (!realVal || realVal <= 0) {
                errors.push('收入第' + (i + 1) + '行：实收金额必须大于0');
                continue;
            }
            records.push({
                trans_date: incomeDates[i].value,
                trans_type: 'income',
                counterparty: incomeCounterparties[i].value || '',
                category: incomeCategories[i].value || '',
                item_name: incomeItems[i].value || '',
                amount_receivable: parseFloat(incomeReceivables[i].value) || 0,
                amount_real: realVal,
                payment_method: 'cash',
                remark: incomeRemarks[i].value || '',
            });
        }
        apiUrl = '/api/transactions/';

    } else if (tab === 'expense') {
        // ===== 只收集支出行 =====
        var expenseDates = document.querySelectorAll('.entry-expense-date');
        var expenseCounterparties = document.querySelectorAll('.entry-expense-counterparty');
        var expenseCategories = document.querySelectorAll('.entry-expense-category');
        var expenseItems = document.querySelectorAll('.entry-expense-item');
        var expenseReceivables = document.querySelectorAll('.entry-expense-receivable');
        var expenseReals = document.querySelectorAll('.entry-expense-real');
        var expenseRemarks = document.querySelectorAll('.entry-expense-remark');

        for (var i = 0; i < expenseDates.length; i++) {
            var realVal = parseFloat(expenseReals[i].value);
            if (!expenseDates[i].value && !expenseCounterparties[i].value && !realVal) continue;
            if (!realVal || realVal <= 0) {
                errors.push('支出第' + (i + 1) + '行：实付金额必须大于0');
                continue;
            }
            records.push({
                trans_date: expenseDates[i].value,
                trans_type: 'expense',
                counterparty: expenseCounterparties[i].value || '',
                category: expenseCategories[i].value || '',
                item_name: expenseItems[i].value || '',
                amount_receivable: parseFloat(expenseReceivables[i].value) || 0,
                amount_real: realVal,
                payment_method: 'cash',
                remark: expenseRemarks[i].value || '',
            });
        }
        apiUrl = '/api/transactions/';

    } else if (tab === 'transfer') {
        // ===== 只收集调拨行 =====
        var transferDates = document.querySelectorAll('.entry-transfer-date');
        var transferFroms = document.querySelectorAll('.entry-transfer-from');
        var transferTos = document.querySelectorAll('.entry-transfer-to');
        var transferPlanneds = document.querySelectorAll('.entry-transfer-planned');
        var transferReals = document.querySelectorAll('.entry-transfer-real');
        var transferRemarks = document.querySelectorAll('.entry-transfer-remark');

        for (var i = 0; i < transferDates.length; i++) {
            var plannedVal = parseFloat(transferPlanneds[i].value);
            if (!transferDates[i].value && !transferFroms[i].value && !plannedVal) continue;
            if (!plannedVal || plannedVal <= 0) {
                errors.push('调拨第' + (i + 1) + '行：计划金额必须大于0');
                continue;
            }
            if (!transferFroms[i].value) {
                errors.push('调拨第' + (i + 1) + '行：转出账户不能为空');
                continue;
            }
            if (!transferTos[i].value) {
                errors.push('调拨第' + (i + 1) + '行：转入账户不能为空');
                continue;
            }
            var fromSel = transferFroms[i];
            var toSel = transferTos[i];
            var fromBankId = fromSel.options[fromSel.selectedIndex].getAttribute('data-id');
            var toBankId = toSel.options[toSel.selectedIndex].getAttribute('data-id');
            transferRecords.push({
                trans_date: transferDates[i].value,
                from_account: fromSel.value,
                to_account: toSel.value,
                from_bank_id: fromBankId || null,
                to_bank_id: toBankId || null,
                amount_planned: plannedVal,
                amount_real: parseFloat(transferReals[i].value) || plannedVal,
                remark: transferRemarks[i].value || '',
            });
        }
    }

    // 校验
    if (errors.length > 0) {
        alert('请修正以下问题后再保存：\n' + errors.join('\n'));
        return;
    }

    var itemsToSave = tab === 'transfer' ? transferRecords : records;
    if (itemsToSave.length === 0) {
        alert('没有可保存的数据，请至少填写一行');
        return;
    }

    // 逐条保存
    for (var i = 0; i < itemsToSave.length; i++) {
        try {
            var res = await api(tab === 'transfer' ? '/api/transfers/' : apiUrl, {
                method: 'POST',
                body: JSON.stringify(itemsToSave[i]),
            });
            if (res.code === 200) {
                successCount++;
            } else {
                failCount++;
            }
        } catch (err) {
            failCount++;
        }
    }

    if (failCount === 0) {
        var typeLabel = tab === 'income' ? '收入' : tab === 'expense' ? '支出' : '调拨';
        alert(typeLabel + '保存成功！共 ' + successCount + ' 条记录');

        // 只清空当前标签页，保留其他标签页数据
        if (tab === 'income') {
            document.getElementById('entry-income-body').innerHTML = '';
            entryIncomeCount = 0;
            addEntryRow('income');
        } else if (tab === 'expense') {
            document.getElementById('entry-expense-body').innerHTML = '';
            entryExpenseCount = 0;
            addEntryRow('expense');
        } else if (tab === 'transfer') {
            document.getElementById('entry-transfer-body').innerHTML = '';
            entryTransferCount = 0;
            addEntryRow('transfer');
        }

        // 刷新仪表盘
        if (currentPage === 'dashboard') loadDashboard();
    } else {
        alert('保存结果：成功 ' + successCount + ' 条，失败 ' + failCount + ' 条');
    }
}

// ==================== 备份与恢复 ====================
let backupDataCache = null; // 缓存备份数据

async function startBackup() {
    const modal = document.getElementById('backup-modal');
    const progress = document.getElementById('backup-progress');
    const percentEl = document.getElementById('backup-percent');
    const detailEl = document.getElementById('backup-detail');
    const statusEl = document.getElementById('backup-status');
    modal.classList.remove('hidden');

    const steps = [
        { pct: 10, text: '正在连接数据核心...', detail: '验证数据库连接' },
        { pct: 25, text: '正在扫描交易记录...', detail: '读取transactions表' },
        { pct: 45, text: '正在序列化数据结构...', detail: 'JSON格式转换中' },
        { pct: 65, text: '正在生成备份文件...', detail: '构建备份数据包' },
        { pct: 85, text: '正在执行数据校验...', detail: 'MD5完整性校验' },
        { pct: 100, text: '备份完成，准备下载...', detail: '文件生成完毕' },
    ];

    let currentStep = 0;

    // 获取备份数据（v8.0.1 全量备份）
    let backupData = null;
    try {
        const res = await api('/api/settings/backup');
        if (res.code === 200) {
            backupData = res.data;
            backupDataCache = res.data;
        }
    } catch (e) {
        statusEl.textContent = '连接失败，请重试';
        detailEl.textContent = '错误';
        setTimeout(() => modal.classList.add('hidden'), 2000);
        return;
    }

    // 科幻进度动画
    const interval = setInterval(() => {
        if (currentStep < steps.length) {
            const step = steps[currentStep];
            progress.style.width = step.pct + '%';
            percentEl.textContent = step.pct + '%';
            statusEl.textContent = step.text;
            detailEl.textContent = step.detail;
            currentStep++;
        } else {
            clearInterval(interval);
            // 下载文件
            const blob = new Blob([JSON.stringify(backupData, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            const now = new Date();
            const filename = 'dental_backup_' + now.getFullYear() + String(now.getMonth()+1).padStart(2,'0') + String(now.getDate()).padStart(2,'0') + '_' + String(now.getHours()).padStart(2,'0') + String(now.getMinutes()).padStart(2,'0') + String(now.getSeconds()).padStart(2,'0') + '.json';
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);

            statusEl.textContent = '备份已下载到本地';
            detailEl.textContent = '文件: ' + filename;
            setTimeout(() => modal.classList.add('hidden'), 1500);
        }
    }, 400);
}

async function startRestore(input) {
    const file = input.files[0];
    if (!file) return;

    // 读取文件
    let restoreData = null;
    try {
        const text = await file.text();
        restoreData = JSON.parse(text);
    } catch (e) {
        alert('文件格式错误，请选择正确的备份文件');
        input.value = '';
        return;
    }

    if (!restoreData.tables || typeof restoreData.tables !== 'object') {
        // 兼容旧版备份格式（v8.0之前）
        if (restoreData.records && Array.isArray(restoreData.records)) {
            alert('检测到旧版备份格式（v8.0之前），不支持恢复。请使用v8.0.1及之后版本的备份文件。');
        } else {
            alert('备份文件格式不正确');
        }
        input.value = '';
        return;
    }

    const recordCount = (restoreData.record_count || 0);
    if (!confirm('确定要恢复备份吗？这将覆盖现有的所有数据（交易记录、收费大类、银行账号、会计科目、凭证等）！\n\n版本: ' + (restoreData.version || '未知') + '\n备份时间: ' + (restoreData.backup_time || '未知') + '\n交易记录: ' + recordCount + ' 条')) {
        input.value = '';
        return;
    }

    const modal = document.getElementById('restore-modal');
    const progress = document.getElementById('restore-progress');
    const percentEl = document.getElementById('restore-percent');
    const detailEl = document.getElementById('restore-detail');
    const statusEl = document.getElementById('restore-status');
    modal.classList.remove('hidden');

    const steps = [
        { pct: 15, text: '正在解析备份文件...', detail: 'JSON数据结构验证' },
        { pct: 35, text: '正在清理现有数据...', detail: '清空当前记录表' },
        { pct: 55, text: '正在写入备份数据...', detail: '批量插入 ' + (restoreData.record_count || '所有') + ' 条记录' },
        { pct: 75, text: '正在重建索引...', detail: '数据库索引优化' },
        { pct: 95, text: '正在执行最终校验...', detail: '数据一致性检查' },
        { pct: 100, text: '恢复完成！', detail: '系统已还原到备份状态' },
    ];

    let currentStep = 0;

    // 科幻进度动画
    const interval = setInterval(() => {
        if (currentStep < steps.length - 1) {
            const step = steps[currentStep];
            progress.style.width = step.pct + '%';
            percentEl.textContent = step.pct + '%';
            statusEl.textContent = step.text;
            detailEl.textContent = step.detail;
            currentStep++;
        }
    }, 500);

    // 发送恢复请求
    try {
        const res = await api('/api/settings/restore', {
            method: 'POST',
            body: JSON.stringify(restoreData),
        });

        clearInterval(interval);
        const finalStep = steps[steps.length - 1];
        progress.style.width = finalStep.pct + '%';
        percentEl.textContent = finalStep.pct + '%';
        statusEl.textContent = finalStep.text;
        detailEl.textContent = finalStep.detail;

        if (res.code === 200) {
            setTimeout(() => {
                modal.classList.add('hidden');
                alert('恢复成功！' + res.message);
                if (currentPage === 'query') loadQuery();
                if (currentPage === 'dashboard') loadDashboard();
                if (currentPage === 'statistics') loadStatistics();
                if (currentPage === 'vouchers') loadVouchers('');
                if (currentPage === 'finance') { loadFinanceL1(); loadFinanceL2(); loadFinanceMapping(); }
                if (currentPage === 'settings') { loadSettings(); loadBanks(); }
            }, 1500);
        } else {
            modal.classList.add('hidden');
            alert('恢复失败: ' + res.message);
        }
    } catch (err) {
        clearInterval(interval);
        modal.classList.add('hidden');
        alert('恢复出错: ' + (err.message || '网络异常'));
    }

    input.value = '';
}

// ==================== 自动备份 v8.1 ====================
let autoBackupConfig = { is_enabled: false, interval_hours: 24, save_path: '' };
let validCategoriesSet = new Set(); // v8.1 有效的收费大类集合（导入用）
let linkedVoucherNos = new Set();   // v8.3.1 已生成凭证的link_no集合

async function loadAutoBackupConfig() {
    try {
        const res = await api('/api/auto-backup/config');
        if (res.code === 200 && res.data) {
            autoBackupConfig = res.data;
            updateAutoBackupStatusBar();
        }
    } catch (e) {
        // 静默失败，自动备份是可选功能
    }
}

function updateAutoBackupStatusBar() {
    const bar = document.getElementById('auto-backup-status-bar');
    const text = document.getElementById('auto-backup-status-text');
    if (autoBackupConfig.is_enabled) {
        bar.classList.remove('hidden');
        var hours = autoBackupConfig.interval_hours;
        var label = hours >= 168 ? (hours / 168) + '周' : hours >= 24 ? (hours / 24) + '天' : hours + '小时';
        text.textContent = '自动备份已启用，每' + label + '执行一次';
    } else {
        bar.classList.add('hidden');
    }
}

function openAutoBackupModal() {
    loadAutoBackupModalData();
    document.getElementById('auto-backup-modal').classList.remove('hidden');
}

function closeAutoBackupModal() {
    document.getElementById('auto-backup-modal').classList.add('hidden');
}

async function loadAutoBackupModalData() {
    await loadAutoBackupConfig();
    var cfg = autoBackupConfig;

    // 开关
    document.getElementById('ab-enabled').checked = cfg.is_enabled;

    // 间隔按钮高亮
    document.querySelectorAll('.ab-interval-btn').forEach(function(btn) {
        var h = parseInt(btn.dataset.hours);
        if (h === cfg.interval_hours) {
            btn.classList.add('bg-primary', 'text-white', 'border-primary');
            btn.classList.remove('bg-white', 'text-gray-700', 'border-gray-200');
        } else {
            btn.classList.remove('bg-primary', 'text-white', 'border-primary');
            btn.classList.add('bg-white', 'text-gray-700', 'border-gray-200');
        }
    });
    document.getElementById('ab-interval-custom').value = cfg.interval_hours;

    // 保存路径
    document.getElementById('ab-save-path').value = cfg.save_path || '/www/wwwroot/dental-finance/backups';

    // 摘要
    var summary = document.getElementById('ab-summary');
    if (cfg.is_enabled) {
        summary.classList.remove('hidden');
        document.getElementById('ab-summary-interval').textContent = cfg.interval_hours;
        document.getElementById('ab-summary-path').textContent = cfg.save_path || '--';
        document.getElementById('ab-summary-last').textContent = cfg.last_backup_time ? formatDate(cfg.last_backup_time) : '尚未执行';
    } else {
        summary.classList.add('hidden');
    }
}

function toggleAutoBackupEnabled() {
    autoBackupConfig.is_enabled = document.getElementById('ab-enabled').checked;
    var summary = document.getElementById('ab-summary');
    if (autoBackupConfig.is_enabled) {
        summary.classList.remove('hidden');
        document.getElementById('ab-summary-interval').textContent = autoBackupConfig.interval_hours;
        document.getElementById('ab-summary-path').textContent = document.getElementById('ab-save-path').value;
    } else {
        summary.classList.add('hidden');
    }
}

function setBackupInterval(hours) {
    hours = parseInt(hours);
    if (isNaN(hours) || hours < 1) return;
    autoBackupConfig.interval_hours = hours;
    document.getElementById('ab-interval-custom').value = hours;
    // 更新按钮样式
    document.querySelectorAll('.ab-interval-btn').forEach(function(btn) {
        var h = parseInt(btn.dataset.hours);
        if (h === hours) {
            btn.classList.add('bg-primary', 'text-white', 'border-primary');
            btn.classList.remove('bg-white', 'text-gray-700', 'border-gray-200');
        } else {
            btn.classList.remove('bg-primary', 'text-white', 'border-primary');
            btn.classList.add('bg-white', 'text-gray-700', 'border-gray-200');
        }
    });
    if (document.getElementById('ab-enabled').checked) {
        document.getElementById('ab-summary-interval').textContent = hours;
    }
}

async function saveAutoBackupConfig() {
    var isEnabled = document.getElementById('ab-enabled').checked;
    var intervalHours = parseInt(document.getElementById('ab-interval-custom').value) || 24;
    var savePath = document.getElementById('ab-save-path').value.trim();

    if (!savePath) {
        alert('请输入备份文件保存路径');
        return;
    }

    try {
        var btn = document.querySelector('#auto-backup-modal button[onclick="saveAutoBackupConfig()"]');
        btn.textContent = '保存中...';
        btn.disabled = true;

        var res = await api('/api/auto-backup/config', {
            method: 'POST',
            body: JSON.stringify({
                is_enabled: isEnabled,
                interval_hours: intervalHours,
                save_path: savePath,
            }),
        });

        btn.textContent = '保存';
        btn.disabled = false;

        if (res.code === 200) {
            autoBackupConfig = res.data;
            updateAutoBackupStatusBar();
            closeAutoBackupModal();
            alert(res.message);
        } else {
            alert('保存失败: ' + res.message);
        }
    } catch (err) {
        alert('保存出错: ' + (err.message || '网络异常'));
    }
}

// ==================== 设置功能 ====================
async function loadSettings() {
    const [catRes, clinicRes, abRes] = await Promise.all([
        api('/api/settings/categories'),
        api('/api/settings/clinic'),
        api('/api/auto-backup/config'),
    ]);
    if (abRes.code === 200 && abRes.data) {
        autoBackupConfig = abRes.data;
        updateAutoBackupStatusBar();
    }
    if (clinicRes.code === 200) {
        document.getElementById('setting-clinic-name').value = clinicRes.data.clinic_name;
        document.getElementById('clinic-name').textContent = clinicRes.data.clinic_name;
        document.getElementById('mobile-clinic-name').textContent = clinicRes.data.clinic_name;
    }
    if (catRes.code === 200) renderCategories(catRes.data);
}

function renderCategories(cats) {
    categoryData = cats;
    var incCats = cats.filter(function(c) { return c.trans_type === 'income'; });
    var expCats = cats.filter(function(c) { return c.trans_type === 'expense'; });
    document.getElementById('setting-cat-count').textContent = '共 ' + cats.length + ' 个';
    document.getElementById('setting-cat-income-list').innerHTML = incCats.map(function(cat) {
        return '<div class="flex items-center justify-between py-2.5 px-3 group hover:bg-gray-50">' +
            '<span class="font-medium text-gray-900 text-sm cat-name-' + cat.id + '">' + cat.name + '</span>' +
            '<div class="flex items-center gap-1">' +
            '<button onclick="editCategory(' + cat.id + ')" class="p-1 text-blue-600 hover:bg-blue-100 rounded"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg></button>' +
            '<button onclick="deleteCategory(' + cat.id + ')" class="p-1 text-red-600 hover:bg-red-100 rounded"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg></button>' +
            '</div></div>' +
            '<div class="hidden py-2 px-3 bg-gray-50" id="cat-edit-form-' + cat.id + '">' +
            '<div class="flex items-center gap-2">' +
            '<input type="text" class="edit-cat-name-' + cat.id + ' flex-1 px-3 py-1.5 border border-gray-300 rounded text-sm focus:outline-none focus:ring-1 focus:ring-primary" value="' + cat.name + '">' +
            '<button onclick="saveCategory(' + cat.id + ')" class="p-1.5 text-emerald-600 hover:bg-emerald-100 rounded"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg></button>' +
            '<button onclick="cancelCatEdit(' + cat.id + ')" class="p-1.5 text-gray-500 hover:bg-gray-200 rounded"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg></button>' +
            '</div></div>';
    }).join('') || '<div class="py-3 px-3 text-sm text-gray-400">暂无收入收费大类</div>';

    document.getElementById('setting-cat-expense-list').innerHTML = expCats.map(function(cat) {
        return '<div class="flex items-center justify-between py-2.5 px-3 group hover:bg-gray-50">' +
            '<span class="font-medium text-gray-900 text-sm cat-name-' + cat.id + '">' + cat.name + '</span>' +
            '<div class="flex items-center gap-1">' +
            '<button onclick="editCategory(' + cat.id + ')" class="p-1 text-blue-600 hover:bg-blue-100 rounded"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg></button>' +
            '<button onclick="deleteCategory(' + cat.id + ')" class="p-1 text-red-600 hover:bg-red-100 rounded"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg></button>' +
            '</div></div>' +
            '<div class="hidden py-2 px-3 bg-gray-50" id="cat-edit-form-' + cat.id + '">' +
            '<div class="flex items-center gap-2">' +
            '<input type="text" class="edit-cat-name-' + cat.id + ' flex-1 px-3 py-1.5 border border-gray-300 rounded text-sm focus:outline-none focus:ring-1 focus:ring-primary" value="' + cat.name + '">' +
            '<button onclick="saveCategory(' + cat.id + ')" class="p-1.5 text-emerald-600 hover:bg-emerald-100 rounded"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg></button>' +
            '<button onclick="cancelCatEdit(' + cat.id + ')" class="p-1.5 text-gray-500 hover:bg-gray-200 rounded"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg></button>' +
            '</div></div>';
    }).join('') || '<div class="py-3 px-3 text-sm text-gray-400">暂无支出收费大类</div>';
}

async function addCategory() {
    var name = document.getElementById('new-cat-name').value.trim();
    var transType = document.getElementById('new-cat-type').value;
    if (!name) { alert('请输入收费大类名称'); return; }
    var res = await api('/api/settings/categories', {
        method: 'POST',
        body: JSON.stringify({ name: name, trans_type: transType }),
    });
    if (res.code === 200) {
        document.getElementById('new-cat-name').value = '';
        loadSettings();
    } else {
        alert(res.message || '添加失败');
    }
}

async function deleteCategory(id) {
    if (!confirm('确定要删除这个收费大类吗？')) return;
    var res = await api('/api/settings/categories/' + id, { method: 'DELETE' });
    if (res.code === 200) loadSettings();
}

function editCategory(id) {
    document.querySelectorAll('[id^="cat-edit-form-"]').forEach(function(el) { el.classList.add('hidden'); });
    document.getElementById('cat-edit-form-' + id).classList.remove('hidden');
}

function cancelCatEdit(id) {
    document.getElementById('cat-edit-form-' + id).classList.add('hidden');
}

async function saveCategory(id) {
    var name = document.querySelector('.edit-cat-name-' + id).value.trim();
    if (!name) { alert('请输入大类名称'); return; }
    var res = await api('/api/settings/categories/' + id, {
        method: 'PUT',
        body: JSON.stringify({ name: name }),
    });
    if (res.code === 200) loadSettings();
}

document.getElementById('save-clinic-btn').addEventListener('click', async () => {
    const name = document.getElementById('setting-clinic-name').value.trim();
    if (!name) { alert('请输入诊所名称'); return; }
    const res = await api('/api/settings/clinic', {
        method: 'PUT',
        body: JSON.stringify({ clinic_name: name }),
    });
    if (res.code === 200) {
        alert('诊所名称已更新');
        loadSettings();
    }
});

// ==================== 初始化 ====================
document.addEventListener('DOMContentLoaded', () => {
    // 设置默认月份
    const now = new Date();
    document.getElementById('stat-month').value = now.toISOString().slice(0, 7);
    
    // 设置默认统计日期范围（本月1号到今天）
    const startOfMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`;
    const endOfMonth = now.toISOString().slice(0, 10);
    document.getElementById('stat-start-date').value = startOfMonth;
    document.getElementById('stat-end-date').value = endOfMonth;
    
    // 加载仪表盘
    loadDashboard();
});


// ==================== 银行账号维护 v8.0 ====================

async function loadBanks() {
    var res = await api('/api/bank-accounts/');
    if (res.code === 200) renderBanks(res.data);
}

function renderBanks(list) {
    var el = document.getElementById('bank-list');
    document.getElementById('bank-count').textContent = list.length + ' 个账号';
    if (!el) return;
    if (!list || list.length === 0) {
        el.innerHTML = '<p class="text-gray-400 text-center py-4">暂无银行账号</p>';
        return;
    }
    el.innerHTML = list.map(function(b) {
        var isDefault = b.is_default ? '<span class="ml-2 text-xs px-2 py-0.5 bg-amber-100 text-amber-700 rounded">★ 默认</span>' : '';
        var statusBadge = b.is_active
            ? '<span class="ml-2 text-xs px-2 py-0.5 bg-emerald-100 text-emerald-600 rounded">启用</span>'
            : '<span class="ml-2 text-xs px-2 py-0.5 bg-gray-100 text-gray-400 rounded">停用</span>';
        var accountInfo = b.account_no ? '<span class="text-xs text-gray-400 ml-2">' + b.account_no + '</span>' : '';
        var bankInfo = b.bank_name ? '<span class="text-xs text-gray-400 ml-1">(' + b.bank_name + ')</span>' : '';
        return '<div class="flex items-center justify-between py-3 px-2 hover:bg-gray-50 rounded-lg">' +
            '<div class="flex items-center">' +
                '<span class="font-medium text-gray-900 text-sm">' + b.account_name + '</span>' + isDefault + statusBadge + accountInfo + bankInfo +
            '</div>' +
            '<div class="flex items-center gap-1">' +
                '<button onclick="openEditBank(' + b.id + ', \'' + (b.account_name || '').replace(/'/g, "\\'") + '\', \'' + (b.bank_name || '').replace(/'/g, "\\'") + '\', \'' + (b.account_no || '') + '\')" class="p-1 text-blue-500 hover:bg-blue-50 rounded text-xs" title="编辑">编</button>' +
                (b.is_default ? '' : '<button onclick="setDefaultBank(' + b.id + ')" class="p-1 text-amber-600 hover:bg-amber-50 rounded text-xs" title="设为默认">★</button>') +
                '<button onclick="toggleBank(' + b.id + ')" class="p-1 text-gray-500 hover:bg-gray-100 rounded text-xs">' + (b.is_active ? '停' : '启') + '</button>' +
                '<button onclick="deleteBank(' + b.id + ')" class="p-1 text-red-500 hover:bg-red-50 rounded text-xs">删</button>' +
            '</div></div>';
    }).join('');
}

async function addBank() {
    var name = document.getElementById('new-bank-name').value.trim();
    if (!name) { alert('请输入账户名称'); return; }
    var res = await api('/api/bank-accounts/', {
        method: 'POST',
        body: JSON.stringify({ account_name: name, bank_name: document.getElementById('new-bank-branch').value, account_no: document.getElementById('new-bank-no').value }),
    });
    if (res.code === 200) {
        document.getElementById('new-bank-name').value = '';
        document.getElementById('new-bank-branch').value = '';
        document.getElementById('new-bank-no').value = '';
        loadBanks();
    } else { alert(res.message || '添加失败'); }
}

async function deleteBank(id) {
    if (!confirm('确定删除？')) return;
    var res = await api('/api/bank-accounts/' + id, { method: 'DELETE' });
    if (res.code === 200) loadBanks(); else alert(res.message);
}

async function setDefaultBank(id) {
    var res = await api('/api/bank-accounts/' + id + '/set-default', { method: 'POST' });
    if (res.code === 200) loadBanks(); else alert(res.message);
}

async function toggleBank(id) {
    var res = await api('/api/bank-accounts/' + id + '/toggle', { method: 'POST' });
    if (res.code === 200) loadBanks(); else alert(res.message);
}

// v8.5: 银行账号编辑
var _currentEditBankId = null;

function openEditBank(id, name, branch, accountNo) {
    _currentEditBankId = id;
    document.getElementById('edit-bank-id').value = id;
    document.getElementById('edit-bank-name').value = name || '';
    document.getElementById('edit-bank-branch').value = branch || '';
    document.getElementById('edit-bank-no').value = accountNo || '';
    document.getElementById('edit-bank-modal').classList.remove('hidden');
}

function closeEditBankModal() {
    document.getElementById('edit-bank-modal').classList.add('hidden');
    _currentEditBankId = null;
}

async function updateBank() {
    if (!_currentEditBankId) return;
    var name = document.getElementById('edit-bank-name').value.trim();
    if (!name) { alert('请输入账户名称'); return; }
    var res = await api('/api/bank-accounts/' + _currentEditBankId, {
        method: 'PUT',
        body: JSON.stringify({
            account_name: name,
            bank_name: document.getElementById('edit-bank-branch').value,
            account_no: document.getElementById('edit-bank-no').value,
        }),
    });
    if (res.code === 200) {
        closeEditBankModal();
        loadBanks();
    } else {
        alert(res.message || '更新失败');
    }
}

// ==================== 凭证管理 v8.0 ====================
let voucherFilterStatus = '';
let voucherAuditId = null;

async function loadVouchers(status) {
    voucherFilterStatus = status || '';
    document.querySelectorAll('.voucher-filter').forEach(function(el) {
        var isActive = el.dataset.filter === voucherFilterStatus;
        el.className = isActive
            ? 'finance-tab px-3 py-1.5 text-sm rounded-lg bg-gray-200 text-gray-900 font-medium voucher-filter active'
            : 'finance-tab px-3 py-1.5 text-sm rounded-lg bg-gray-100 text-gray-700 hover:bg-gray-200 transition-colors voucher-filter';
    });

    var res = await api('/api/vouchers/?status=' + voucherFilterStatus);
    if (res.code === 200) renderVouchers(res.data.list || []);
}

async function clearDraftVouchers() {
    // v8.3.1: 一键清理所有草稿凭证 + 孤儿凭证
    if (!confirm('确定要清理无效凭证吗？\n\n此操作将删除：\n1. 所有草稿状态的凭证\n2. 所有已审核但对应交易记录已不存在的孤儿凭证\n\n此操作不可恢复！')) return;

    try {
        var clearRes = await api('/api/vouchers/clear-drafts', { method: 'POST' });
        if (clearRes.code === 200) {
            alert(clearRes.message);
            loadVouchers(voucherFilterStatus);
            var linkRes = await api('/api/vouchers/link-nos');
            if (linkRes.code === 200 && linkRes.data) {
                linkedVoucherNos = new Set(linkRes.data);
            }
        } else {
            alert('清理失败: ' + clearRes.message);
        }
    } catch (err) {
        alert('清理出错: ' + (err.message || '网络异常'));
    }
}

async function clearAllVouchers() {
    // v8.3.1: 强制清空所有凭证（包括已审核）- 紧急重置
    if (!confirm('【危险操作】\n\n确定要强制清空所有凭证吗？\n\n此操作将删除 vouchers 表中的全部数据（包括已审核凭证），且不可恢复！\n\n仅在凭证数据异常、无法正常生成凭证时使用。')) return;
    if (!confirm('再次确认：你真的要删除所有凭证吗？此操作不可恢复！')) return;

    try {
        var res = await api('/api/vouchers/clear-all', { method: 'POST' });
        if (res.code === 200) {
            alert(res.message);
            loadVouchers(voucherFilterStatus);
            linkedVoucherNos = new Set();
        } else {
            alert('清空失败: ' + res.message);
        }
    } catch (err) {
        alert('清空出错: ' + (err.message || '网络异常'));
    }
}

function renderVouchers(list) {
    var tbody = document.getElementById('voucher-list-body');
    if (!list || list.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="px-4 py-8 text-center text-gray-400">暂无凭证</td></tr>';
        return;
    }
    tbody.innerHTML = list.map(function(v) {
        var statusBadge = v.status === 'draft'
            ? '<span class="px-2 py-0.5 text-xs bg-amber-100 text-amber-700 rounded">草稿</span>'
            : '<span class="px-2 py-0.5 text-xs bg-emerald-100 text-emerald-700 rounded">已审核</span>';
        var actionBtn = v.status === 'draft'
            ? '<button onclick="openVoucherAuditModal(' + v.id + ')" class="px-2 py-1 text-xs bg-primary text-white rounded hover:bg-primary-dark mr-1">审核</button><button onclick="deleteVoucher(' + v.id + ')" class="px-2 py-1 text-xs bg-red-50 text-red-600 rounded hover:bg-red-100">删除</button>'
            : '<span class="text-xs text-gray-400">—</span>';
        var sourceLabel = v.source_type === 'income' ? '收入' : v.source_type === 'expense' ? '支出' : v.source_type === 'transfer' ? '调拨' : v.source_type || '-';
        var previewBtn = '<button onclick="previewVoucher(' + v.id + ')" class="px-2 py-1 text-xs bg-blue-50 text-blue-600 rounded hover:bg-blue-100 mr-1">预览</button>';
        return '<tr class="hover:bg-gray-50">' +
            '<td class="px-4 py-3 font-mono text-sm text-gray-900">' + v.voucher_no + '</td>' +
            '<td class="px-4 py-3 text-gray-600">' + formatDate(v.voucher_date) + '</td>' +
            '<td class="px-4 py-3"><span class="text-xs px-2 py-0.5 bg-blue-50 text-blue-700 rounded">' + sourceLabel + '</span></td>' +
            '<td class="px-4 py-3 font-mono text-xs text-gray-500">' + (v.link_no || '') + '</td>' +
            '<td class="px-4 py-3 text-right font-medium">¥' + (v.total_amount || 0).toFixed(2) + '</td>' +
            '<td class="px-4 py-3 text-center">' + statusBadge + '</td>' +
            '<td class="px-4 py-3 text-center">' + previewBtn + actionBtn + '</td>' +
        '</tr>';
    }).join('');
}

async function openVoucherAuditModal(vid) {
    voucherAuditId = vid;
    var res = await api('/api/vouchers/' + vid);
    if (res.code !== 200) { alert('获取凭证失败'); return; }

    var v = res.data.voucher;
    var entries = res.data.entries;
    var html = '<div class="font-bold text-gray-900 mb-2">' + v.voucher_no + ' (' + formatDate(v.voucher_date) + ')</div>';
    entries.forEach(function(e) {
        var dirLabel = e.direction === 'debit' ? '借' : '贷';
        var bankInfo = e.bank_name ? ' — ' + e.bank_name : '';
        html += '<div class="flex items-center justify-between py-1"><span>' + dirLabel + '：' + (e.subject_l2_code || e.subject_l1_code) + ' ' + e.subject_name + bankInfo + '</span><span class="font-medium">¥' + (e.amount || 0).toFixed(2) + '</span></div>';
    });
    document.getElementById('voucher-audit-preview').innerHTML = html;

    // v8.3.1: 加载银行下拉（支持调拨凭证双银行选择）
    var bankRes = await api('/api/bank-accounts/');
    var activeBanks = [];
    if (bankRes.code === 200) {
        activeBanks = bankRes.data.filter(function(b) { return b.is_active; });
    }
    var bankOptions = activeBanks.map(function(b) {
        var defaultMark = b.is_default ? ' ★默认' : '';
        return '<option value="' + b.id + '">' + b.account_name + defaultMark + '</option>';
    }).join('');

    if (v.source_type === 'transfer') {
        // 调拨凭证：显示双银行选择
        document.getElementById('audit-bank-single').classList.add('hidden');
        document.getElementById('audit-bank-double').classList.remove('hidden');
        document.getElementById('audit-bank-debit').innerHTML = '<option value="">请选择转入银行</option>' + bankOptions;
        document.getElementById('audit-bank-credit').innerHTML = '<option value="">请选择转出银行</option>' + bankOptions;
    } else {
        // 普通凭证：显示单银行选择
        document.getElementById('audit-bank-single').classList.remove('hidden');
        document.getElementById('audit-bank-double').classList.add('hidden');
        document.getElementById('audit-bank-select').innerHTML = '<option value="">使用默认账号</option>' + bankOptions;
    }

    document.getElementById('voucher-audit-modal').classList.remove('hidden');
}

function closeVoucherAuditModal() {
    document.getElementById('voucher-audit-modal').classList.add('hidden');
    voucherAuditId = null;
}

async function confirmVoucherAudit() {
    if (!voucherAuditId) return;
    var isTransfer = !document.getElementById('audit-bank-double').classList.contains('hidden');
    var body;
    if (isTransfer) {
        // v8.3.1: 调拨凭证需要指定借方和贷方银行
        var debitBank = document.getElementById('audit-bank-debit').value;
        var creditBank = document.getElementById('audit-bank-credit').value;
        if (!debitBank) { alert('请选择借方银行（转入账户）'); return; }
        if (!creditBank) { alert('请选择贷方银行（转出账户）'); return; }
        body = JSON.stringify({
            debit_bank_id: parseInt(debitBank),
            credit_bank_id: parseInt(creditBank)
        });
    } else {
        var bankId = document.getElementById('audit-bank-select').value;
        body = JSON.stringify({ bank_account_id: bankId ? parseInt(bankId) : null });
    }
    var res = await api('/api/vouchers/' + voucherAuditId + '/audit', {
        method: 'POST',
        body: body,
    });
    if (res.code === 200) {
        closeVoucherAuditModal();
        loadVouchers(voucherFilterStatus);
        alert('审核成功');
    } else {
        alert(res.message || '审核失败');
    }
}

async function deleteVoucher(vid) {
    if (!confirm('确定删除这张凭证草稿吗？')) return;
    var res = await api('/api/vouchers/' + vid, { method: 'DELETE' });
    if (res.code === 200) {
        loadVouchers(voucherFilterStatus);
        alert('删除成功');
    } else {
        alert(res.message || '删除失败');
    }
}

// ==================== 凭证预览 v8.3.1 ====================
let previewVoucherId = null;

async function previewVoucher(vid) {
    previewVoucherId = vid;
    var res = await api('/api/vouchers/' + vid);
    if (res.code !== 200) { alert('获取凭证失败'); return; }

    var v = res.data.voucher;
    var entries = res.data.entries;

    // 填充凭证头
    document.getElementById('preview-vno').textContent = v.voucher_no;
    document.getElementById('preview-vdate').textContent = formatDate(v.voucher_date);
    var statusEl = document.getElementById('preview-vstatus');
    if (v.status === 'draft') {
        statusEl.innerHTML = '<span class="px-2 py-0.5 text-xs bg-amber-100 text-amber-700 rounded">草稿</span>';
    } else {
        statusEl.innerHTML = '<span class="px-2 py-0.5 text-xs bg-emerald-100 text-emerald-700 rounded">已审核</span>';
    }
    var srcMap = { income: '收入', expense: '支出', transfer: '调拨' };
    document.getElementById('preview-vsource').textContent = srcMap[v.source_type] || (v.source_type || '-');
    document.getElementById('preview-vremark').textContent = v.remark || '-';

    // 填充分录表格
    var tbody = document.getElementById('preview-entries-body');
    var totalDebit = 0, totalCredit = 0;
    tbody.innerHTML = entries.map(function(e) {
        var isDebit = e.direction === 'debit';
        var amount = e.amount || 0;
        if (isDebit) totalDebit += amount; else totalCredit += amount;
        // v8.3.1: 显示银行名（已审核）或待定（未审核）
        var bankDisplay = '';
        if (e.bank_account_id) {
            var bname = e.bank_name || e.subject_name;
            bankDisplay = '（' + bname + '）';
        } else if (e.subject_l1_code === '1002') {
            bankDisplay = '（<span class="text-amber-600">待定</span>）';
        }
        var debitCell = isDebit ? '¥' + amount.toFixed(2) : '';
        var creditCell = !isDebit ? '¥' + amount.toFixed(2) : '';
        return '<tr class="' + (isDebit ? 'bg-white' : 'bg-gray-50/50') + '">' +
            '<td class="px-4 py-2.5 text-gray-800">' + (e.subject_l2_code || e.subject_l1_code) + ' ' + e.subject_name + bankDisplay + '</td>' +
            '<td class="px-4 py-2.5 text-right font-mono text-gray-900">' + debitCell + '</td>' +
            '<td class="px-4 py-2.5 text-right font-mono text-gray-900">' + creditCell + '</td>' +
        '</tr>';
    }).join('');
    document.getElementById('preview-total-debit').textContent = '¥' + totalDebit.toFixed(2);
    document.getElementById('preview-total-credit').textContent = '¥' + totalCredit.toFixed(2);

    // 操作按钮
    var actions = document.getElementById('preview-actions');
    if (v.status === 'draft') {
        actions.innerHTML =
            '<button onclick="closeVoucherPreview()" class="px-4 py-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors text-sm">关闭</button>' +
            '<button onclick="previewDelete()" class="px-4 py-2 text-red-600 bg-red-50 hover:bg-red-100 rounded-lg transition-colors text-sm">删除凭证</button>' +
            '<button onclick="previewAudit()" class="px-5 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark transition-colors text-sm font-medium">审核凭证</button>';
    } else {
        actions.innerHTML = '<button onclick="closeVoucherPreview()" class="px-5 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors text-sm">关闭</button>';
    }

    document.getElementById('voucher-preview-modal').classList.remove('hidden');
}

function closeVoucherPreview() {
    document.getElementById('voucher-preview-modal').classList.add('hidden');
    previewVoucherId = null;
}

async function previewAudit() {
    if (!previewVoucherId) return;
    // 复用审核弹窗逻辑
    closeVoucherPreview();
    openVoucherAuditModal(previewVoucherId);
}

async function previewDelete() {
    if (!previewVoucherId) return;
    if (!confirm('确定删除这张凭证草稿吗？\n删除后对应的交易记录可以再次生成凭证。')) return;
    var res = await api('/api/vouchers/' + previewVoucherId, { method: 'DELETE' });
    if (res.code === 200) {
        closeVoucherPreview();
        loadVouchers(voucherFilterStatus);
        // 刷新已凭证集合（让记录查询中的记录恢复可生成状态）
        var linkRes = await api('/api/vouchers/link-nos');
        if (linkRes.code === 200 && linkRes.data) {
            linkedVoucherNos = new Set(linkRes.data);
        }
        alert('删除成功，对应的交易记录可以再次生成凭证');
    } else {
        alert(res.message || '删除失败');
    }
}

// ==================== 财务数据维护 v8.0 ====================

function switchFinanceTab(tab) {
    document.querySelectorAll('.finance-tab').forEach(function(el) {
        el.classList.remove('border-primary', 'text-primary');
        el.classList.add('border-transparent', 'text-gray-500');
    });
    document.getElementById('tab-' + tab).classList.remove('border-transparent', 'text-gray-500');
    document.getElementById('tab-' + tab).classList.add('border-primary', 'text-primary');

    document.querySelectorAll('.finance-panel').forEach(function(el) { el.classList.add('hidden'); });
    document.getElementById('finance-' + tab).classList.remove('hidden');
}

async function loadFinanceL1() {
    var res = await api('/api/account-subjects/l1');
    if (res.code !== 200) return;
    document.getElementById('finance-l1-body').innerHTML = res.data.map(function(s) {
        var catColor = { '资产': 'text-blue-600', '负债': 'text-red-600', '权益': 'text-purple-600', '损益-收入': 'text-emerald-600', '损益-费用': 'text-orange-600' };
        return '<tr class="hover:bg-gray-50"><td class="px-4 py-3 font-mono text-sm font-medium">' + s.code + '</td><td class="px-4 py-3 font-medium">' + s.name + '</td><td class="px-4 py-3 ' + (catColor[s.category] || 'text-gray-600') + '">' + s.category + '</td><td class="px-4 py-3">' + s.direction + '</td></tr>';
    }).join('');
}

async function loadFinanceL2() {
    var res = await api('/api/account-subjects/l2');
    if (res.code !== 200) return;
    // 更新上级科目下拉
    var l1Res = await api('/api/account-subjects/l1');
    if (l1Res.code === 200) {
        document.getElementById('new-l2-parent').innerHTML = '<option value="">选择上级科目</option>' + l1Res.data.map(function(s) {
            return '<option value="' + s.id + '">' + s.code + ' ' + s.name + '</option>';
        }).join('');
    }
    document.getElementById('finance-l2-body').innerHTML = res.data.map(function(s) {
        return '<div class="flex items-center justify-between py-3 px-2 hover:bg-gray-50 rounded-lg"><div><span class="font-mono text-sm text-gray-500">' + s.code + '</span><span class="ml-3 font-medium text-sm">' + s.name + '</span><span class="ml-2 text-xs text-gray-400">← ' + (s.parent_code || '') + '</span></div><div class="flex gap-1"><button onclick="deleteL2Subject(' + s.id + ')" class="p-1 text-red-500 hover:bg-red-50 rounded text-xs">删</button></div></div>';
    }).join('') || '<p class="text-gray-400 text-center py-4">暂无二级科目</p>';
}

async function addL2Subject() {
    var parentId = document.getElementById('new-l2-parent').value;
    var name = document.getElementById('new-l2-name').value.trim();
    if (!parentId || !name) { alert('请选择上级科目并输入名称'); return; }
    var res = await api('/api/account-subjects/l2', { method: 'POST', body: JSON.stringify({ parent_id: parseInt(parentId), name: name }) });
    if (res.code === 200) { document.getElementById('new-l2-name').value = ''; loadFinanceL2(); }
    else alert(res.message || '添加失败');
}

async function deleteL2Subject(id) {
    if (!confirm('确定删除？')) return;
    var res = await api('/api/account-subjects/l2/' + id, { method: 'DELETE' });
    if (res.code === 200) loadFinanceL2();
}

async function loadFinanceMapping() {
    var res = await api('/api/account-subjects/mapping');
    if (res.code !== 200) return;

    // 更新下拉
    var catRes = await api('/api/settings/categories');
    var subRes = await api('/api/account-subjects/l2');
    if (catRes.code === 200) {
        document.getElementById('new-map-cat').innerHTML = '<option value="">选择收费大类</option>' + catRes.data.map(function(c) {
            return '<option value="' + c.id + '">' + c.name + ' (' + (c.trans_type === 'income' ? '收入' : '支出') + ')</option>';
        }).join('');
    }
    if (subRes.code === 200) {
        document.getElementById('new-map-sub').innerHTML = '<option value="">选择会计科目</option>' + subRes.data.map(function(s) {
            return '<option value="' + s.id + '">' + s.code + ' ' + s.name + '</option>';
        }).join('');
    }

    document.getElementById('finance-mapping-list').innerHTML = res.data.map(function(m) {
        var typeColor = m.trans_type === 'income' ? 'text-emerald-600' : 'text-red-500';
        return '<div class="flex items-center justify-between py-3 px-2 hover:bg-gray-50 rounded-lg"><div class="flex items-center gap-3"><span class="font-medium text-sm">' + m.category_name + '</span><span class="text-xs ' + typeColor + '">(' + (m.trans_type === 'income' ? '收' : '支') + ')</span><span class="text-gray-400">→</span><span class="font-mono text-xs text-gray-500">' + m.subject_code + '</span><span class="text-sm">' + m.subject_name + '</span></div><button onclick="deleteMapping(' + m.id + ')" class="p-1 text-red-500 hover:bg-red-50 rounded text-xs">删</button></div>';
    }).join('') || '<p class="text-gray-400 text-center py-4">暂无映射，请添加</p>';
}

async function addMapping() {
    var catId = document.getElementById('new-map-cat').value;
    var subId = document.getElementById('new-map-sub').value;
    if (!catId || !subId) { alert('请选择收费大类和会计科目'); return; }
    var res = await api('/api/account-subjects/mapping', { method: 'POST', body: JSON.stringify({ category_id: parseInt(catId), subject_l2_id: parseInt(subId) }) });
    if (res.code === 200) { loadFinanceMapping(); }
    else alert(res.message || '映射失败');
}

async function deleteMapping(id) {
    if (!confirm('确定删除映射？')) return;
    var res = await api('/api/account-subjects/mapping/' + id, { method: 'DELETE' });
    if (res.code === 200) loadFinanceMapping();
}

// ==================== v8.5.0 期初余额录入 ====================

var openingSubjectsData = [];  // 缓存科目数据
var openingRowCounter = 0;     // 行计数器

/** 检测是否需要录入期初余额 */
async function checkOpeningBalance() {
    try {
        var res = await api('/api/accounting/check-opening');
        if (res.code === 200 && res.required) {
            // 需要录入，延迟一点再弹，让页面先加载完
            setTimeout(function() { openOpeningBalanceModal(); }, 500);
        }
    } catch (e) {
        console.log('[OpeningBalance] check failed:', e);
    }
}

/** 打开期初余额录入弹窗 */
async function openOpeningBalanceModal() {
    document.getElementById('opening-balance-modal').classList.remove('hidden');
    await loadOpeningSubjects();
    // 默认添加5行空行
    var tbody = document.getElementById('opening-balance-body');
    tbody.innerHTML = '';
    for (var i = 0; i < 5; i++) { addOpeningRow(); }
}

/** 关闭弹窗 */
function closeOpeningBalanceModal() {
    document.getElementById('opening-balance-modal').classList.add('hidden');
}

/** 加载科目列表 */
async function loadOpeningSubjects() {
    var res = await api('/api/accounting/subjects');
    if (res.code === 200) {
        openingSubjectsData = res.data.subjects;
    }
}

/** 获取一级科目下拉HTML */
function getL1SelectHtml(selectedCode) {
    var html = '<option value="">选择一级科目</option>';
    for (var i = 0; i < openingSubjectsData.length; i++) {
        var s = openingSubjectsData[i];
        var sel = (s.code === selectedCode) ? ' selected' : '';
        html += '<option value="' + s.code + '" data-category="' + s.category + '"' + sel + '>' + s.code + ' ' + s.name + '</option>';
    }
    return html;
}

/** 获取二级科目下拉HTML（根据一级科目编码） */
function getL2SelectHtml(l1Code, selectedCode) {
    var html = '<option value="">直接录入一级科目</option>';
    if (!l1Code) return html;
    for (var i = 0; i < openingSubjectsData.length; i++) {
        if (openingSubjectsData[i].code === l1Code) {
            var children = openingSubjectsData[i].children;
            for (var j = 0; j < children.length; j++) {
                var c = children[j];
                var sel = (c.code === selectedCode) ? ' selected' : '';
                html += '<option value="' + c.code + '"' + sel + '>' + c.code + ' ' + c.name + '</option>';
            }
            break;
        }
    }
    return html;
}

/** 添加一行 */
function addOpeningRow() {
    openingRowCounter++;
    var tbody = document.getElementById('opening-balance-body');
    var tr = document.createElement('tr');
    tr.id = 'opening-row-' + openingRowCounter;
    tr.className = 'opening-row';
    tr.innerHTML =
        '<td class="px-2 py-2">' +
            '<select class="opening-l1 w-full px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary focus:border-primary" onchange="onL1Change(this)">' +
                getL1SelectHtml() +
            '</select>' +
        '</td>' +
        '<td class="px-2 py-2">' +
            '<select class="opening-l2 w-full px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary focus:border-primary" onchange="onL2Change(this)">' +
                '<option value="">直接录入一级科目</option>' +
            '</select>' +
        '</td>' +
        '<td class="px-2 py-2">' +
            '<input type="number" class="opening-balance w-full px-2 py-1.5 border border-gray-300 rounded-lg text-sm text-right focus:ring-2 focus:ring-primary focus:border-primary" placeholder="0.00" step="0.01">' +
        '</td>' +
        '<td class="px-2 py-2 text-center">' +
            '<button type="button" onclick="removeOpeningRow(this)" class="text-red-500 hover:text-red-700 p-1" title="删除">' +
                '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>' +
            '</button>' +
        '</td>';
    tbody.appendChild(tr);
}

/** 删除一行 */
function removeOpeningRow(btn) {
    var row = btn.closest('tr');
    var tbody = document.getElementById('opening-balance-body');
    if (tbody.children.length <= 1) {
        alert('至少保留一行');
        return;
    }
    row.remove();
}

/** 一级科目变化时更新二级选项 */
function onL1Change(select) {
    var l1Code = select.value;
    var row = select.closest('tr');
    var l2Select = row.querySelector('.opening-l2');
    l2Select.innerHTML = getL2SelectHtml(l1Code);
}

/** 二级科目变化时：如果选择了二级，禁用余额输入的一级模式标记 */
function onL2Change(select) {
    // 不需要特殊处理，保存时判断即可
}

/** 收集表格数据 */
function collectOpeningEntries() {
    var entries = [];
    var rows = document.querySelectorAll('.opening-row');
    for (var i = 0; i < rows.length; i++) {
        var row = rows[i];
        var l1 = row.querySelector('.opening-l1').value;
        var l2 = row.querySelector('.opening-l2').value;
        var bal = parseFloat(row.querySelector('.opening-balance').value) || 0;
        if (!l1) continue;  // 跳过空行
        entries.push({
            l1_code: l1,
            l2_code: l2 || null,
            balance: bal,
            is_l1_entry: !l2,
        });
    }
    return entries;
}

/** 保存期初余额 */
async function saveOpeningBalance() {
    var entries = collectOpeningEntries();
    if (entries.length === 0) {
        alert('请至少录入一个科目');
        return;
    }
    var res = await api('/api/accounting/opening-balance', {
        method: 'POST',
        body: JSON.stringify({ entries: entries })
    });
    if (res.code === 200) {
        alert('期初余额录入成功！');
        closeOpeningBalanceModal();
    } else {
        alert(res.message || '保存失败');
    }
}

/** 跳过 */
async function skipOpeningBalance() {
    if (!confirm('确定跳过？24小时内不再提醒您录入期初余额。')) return;
    var res = await api('/api/accounting/opening-balance/skip', { method: 'POST' });
    if (res.code === 200) {
        closeOpeningBalanceModal();
    }
}

/** 下载模板 */
function downloadOpeningTemplate() {
    window.location.href = '/api/accounting/opening-balance/template';
}

/** 导入Excel */
async function importOpeningExcel() {
    var input = document.createElement('input');
    input.type = 'file';
    input.accept = '.xlsx';
    input.onchange = async function() {
        var file = input.files[0];
        if (!file) return;
        var formData = new FormData();
        formData.append('file', file);
        try {
            var resp = await fetch('/api/accounting/opening-balance/import', {
                method: 'POST',
                body: formData
            });
            var res = await resp.json();
            if (res.code === 200) {
                // 将导入的数据填充到表格
                var tbody = document.getElementById('opening-balance-body');
                tbody.innerHTML = '';
                var entries = res.data.entries;
                for (var i = 0; i < entries.length; i++) {
                    addOpeningRow();
                    var row = tbody.lastChild;
                    var e = entries[i];
                    row.querySelector('.opening-l1').value = e.l1_code;
                    // 更新二级选项
                    onL1Change(row.querySelector('.opening-l1'));
                    if (e.l2_code) row.querySelector('.opening-l2').value = e.l2_code;
                    row.querySelector('.opening-balance').value = e.balance;
                }
                alert('成功导入 ' + entries.length + ' 条记录，请核对后保存');
            } else {
                alert(res.message || '导入失败');
            }
        } catch (err) {
            alert('导入失败: ' + err.message);
        }
    };
    input.click();
}

// ==================== 通用工具函数 v8.5 ====================

function formatDateTime(dt) {
    if (!dt || dt === 'null' || dt === 'None') return '-';
    var d = new Date(dt);
    if (isNaN(d.getTime())) return dt;
    var year = d.getFullYear();
    var month = String(d.getMonth() + 1).padStart(2, '0');
    var day = String(d.getDate()).padStart(2, '0');
    var hour = String(d.getHours()).padStart(2, '0');
    var min = String(d.getMinutes()).padStart(2, '0');
    var sec = String(d.getSeconds()).padStart(2, '0');
    return year + '年' + month + '月' + day + '日 ' + hour + ':' + min + ':' + sec;
}

function formatDate(dt) {
    if (!dt || dt === 'null' || dt === 'None') return '-';
    var d = new Date(dt);
    if (isNaN(d.getTime())) return dt;
    var year = d.getFullYear();
    var month = String(d.getMonth() + 1).padStart(2, '0');
    var day = String(d.getDate()).padStart(2, '0');
    return year + '年' + month + '月' + day + '日';
}

// ==================== v8.5 库存管理 ====================

var _invPhotoId = null;
var _invCurrentField = null;
var _invRowCount = 0;
var _currentEditSupplierId = null;
var _invhCurrentPage = 1;

function initInventoryEntryPage() {
    document.getElementById('inv-date').value = new Date().toISOString().split('T')[0];
    document.getElementById('inv-items-body').innerHTML = '';
    _invRowCount = 0;
    addInventoryRow();
    bindInventoryPhotoUpload();
    bindInventoryPhotoSelection();
}

function loadSuppliersForSelect() {
    api('/api/inventory/suppliers').then(function(res) {
        if (res.code !== 200) return;
        var sel = document.getElementById('inv-supplier');
        if (!sel) return;
        var html = '<option value="">选择供应商</option>';
        res.data.forEach(function(s) { html += '<option value="' + s.id + '">' + s.name + '</option>'; });
        sel.innerHTML = html;
    }).catch(function(e) { console.log(e); });
}

function bindInventoryPhotoUpload() {
    var uploadArea = document.getElementById('inv-photo-upload-area');
    var fileInput = document.getElementById('inv-photo-input');
    if (!uploadArea || !fileInput) return;
    uploadArea.onclick = function() { fileInput.click(); };
    fileInput.onchange = function() {
        var file = fileInput.files[0];
        if (!file) return;
        var formData = new FormData();
        formData.append('file', file);
        fetch('/api/inventory/upload-photo', { method: 'POST', body: formData })
            .then(function(r) { return r.json(); })
            .then(function(res) {
                if (res.code === 200) {
                    _invPhotoId = res.data.photo_id;
                    document.getElementById('inv-photo-upload-area').classList.add('hidden');
                    document.getElementById('inv-photo-preview-area').classList.remove('hidden');
                    var path = res.data.path;
                    var parts = path.split('/');
                    var fname = parts[parts.length - 1];
                    document.getElementById('inv-preview-img').src = '/uploads/inventory/' + fname;
                } else { alert(res.message || '上传失败'); }
            }).catch(function(e) { alert('上传失败: ' + e.message); });
    };
}

function removeInventoryPhoto() {
    _invPhotoId = null;
    document.getElementById('inv-photo-upload-area').classList.remove('hidden');
    document.getElementById('inv-photo-preview-area').classList.add('hidden');
    document.getElementById('inv-preview-img').src = '';
    document.getElementById('inv-photo-input').value = '';
}

function bindInventoryPhotoSelection() {
    // v8.6: 移除OCR框选功能，仅保留图片预览
    var img = document.getElementById('inv-preview-img');
    if (!img) return;
    if (img._selectionBound) return;
    img._selectionBound = true;
    // 图片仅用于参考，手动录入信息
}

function onInvFieldFocus(input) {
    if (_invCurrentField) _invCurrentField.classList.remove('ring-2', 'ring-blue-400');
    _invCurrentField = input;
    input.classList.add('ring-2', 'ring-blue-400');
}

function addInventoryRow() {
    _invRowCount++;
    var tbody = document.getElementById('inv-items-body');
    var tr = document.createElement('tr');
    tr.className = 'inv-item-row border-b';
    tr.dataset.rowId = _invRowCount;

    var catOpts = '<option value="耗材">耗材</option><option value="药品">药品</option><option value="器械">器械</option><option value="设备">设备</option><option value="消毒用品">消毒用品</option>';
    var unitOpts = '<option value="箱">箱</option><option value="盒">盒</option><option value="支">支</option><option value="瓶">瓶</option><option value="袋">袋</option><option value="套">套</option><option value="个">个</option>';

    tr.innerHTML =
        '<td class="px-2 py-2"><select class="inv-cat w-full px-1 py-1 border border-gray-300 rounded text-xs">' + catOpts + '</select></td>' +
        '<td class="px-2 py-2"><input type="text" class="inv-name w-full px-2 py-1 border border-gray-300 rounded text-xs" placeholder="商品名称"></td>' +
        '<td class="px-2 py-2"><input type="text" class="inv-spec w-full px-2 py-1 border border-gray-300 rounded text-xs"></td>' +
        '<td class="px-2 py-2"><input type="number" class="inv-qty w-full px-2 py-1 border border-gray-300 rounded text-xs" step="0.01" value="1"></td>' +
        '<td class="px-2 py-2"><select class="inv-unit w-full px-1 py-1 border border-gray-300 rounded text-xs">' + unitOpts + '</select></td>' +
        '<td class="px-2 py-2"><input type="text" class="inv-batch w-full px-2 py-1 border border-gray-300 rounded text-xs"></td>' +
        '<td class="px-2 py-2"><input type="date" class="inv-prod-date w-full px-1 py-1 border border-gray-300 rounded text-xs"></td>' +
        '<td class="px-2 py-2"><input type="date" class="inv-expiry w-full px-1 py-1 border border-gray-300 rounded text-xs"></td>' +
        '<td class="px-2 py-2"><input type="text" class="inv-mfr w-full px-2 py-1 border border-gray-300 rounded text-xs"></td>' +
        '<td class="px-2 py-2"><input type="text" class="inv-license w-full px-2 py-1 border border-gray-300 rounded text-xs"></td>' +
        '<td class="px-2 py-2"><input type="number" class="inv-price w-full px-2 py-1 border border-gray-300 rounded text-xs" step="0.0001" placeholder="选填" onblur="calcInvTax(this)"></td>' +
        '<td class="px-2 py-2"><input type="text" class="inv-tax w-full px-2 py-1 border border-gray-200 rounded text-xs bg-gray-50" readonly placeholder="自动"></td>' +
        '<td class="px-2 py-2"><input type="number" class="inv-total w-full px-2 py-1 border border-gray-300 rounded text-xs" step="0.0001" placeholder="必填" onblur="calcInvTax(this)"></td>' +
        '<td class="px-2 py-2 text-center"><span class="inline-flex items-center px-1.5 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800">合格</span></td>' +
        '<td class="px-2 py-2"><button onclick="this.closest(\'tr\').remove()" class="text-red-400 hover:text-red-600 text-xs p-1">✕</button></td>';

    tbody.appendChild(tr);
}

function calcInvTax(input) {
    var row = input.closest('tr');
    var price = parseFloat(row.querySelector('.inv-price').value) || 0;
    var total = parseFloat(row.querySelector('.inv-total').value) || 0;
    var taxInput = row.querySelector('.inv-tax');
    if (price > 0 && total > 0) {
        var tax = total - price;
        taxInput.value = tax > 0 ? tax.toFixed(2) : '0';
    } else { taxInput.value = ''; }
}

function clearInventoryForm() {
    if (!confirm('确定清空所有已录入的数据？')) return;
    document.getElementById('inv-items-body').innerHTML = '';
    _invRowCount = 0;
    addInventoryRow();
    removeInventoryPhoto();
    document.getElementById('inv-remark').value = '';
}

function submitInventory() {
    var supplierId = document.getElementById('inv-supplier').value;
    var remark = document.getElementById('inv-remark').value;

    var items = [];
    var rows = document.querySelectorAll('.inv-item-row');
    for (var i = 0; i < rows.length; i++) {
        var row = rows[i];
        var name = row.querySelector('.inv-name').value.trim();
        var qty = row.querySelector('.inv-qty').value;
        var unit = row.querySelector('.inv-unit').value;
        var total = row.querySelector('.inv-total').value;
        if (!name) { alert('第' + (i+1) + '行：名称不能为空'); return; }
        if (!qty) { alert('第' + (i+1) + '行：数量不能为空'); return; }
        if (!unit) { alert('第' + (i+1) + '行：单位不能为空'); return; }
        if (!total) { alert('第' + (i+1) + '行：总价不能为空'); return; }

        items.push({
            category: row.querySelector('.inv-cat').value,
            name: name,
            specification: row.querySelector('.inv-spec').value || null,
            quantity: parseFloat(qty),
            unit: unit,
            batch_no: row.querySelector('.inv-batch').value || null,
            production_date: row.querySelector('.inv-prod-date').value || null,
            expiry_date: row.querySelector('.inv-expiry').value || null,
            manufacturer: row.querySelector('.inv-mfr').value || null,
            manufacturer_license: row.querySelector('.inv-license').value || null,
            unit_price: parseFloat(row.querySelector('.inv-price').value) || null,
            tax_amount: parseFloat(row.querySelector('.inv-tax').value) || null,
            total_price: parseFloat(total)
        });
    }

    if (items.length === 0) { alert('请至少录入一个商品'); return; }

    api('/api/inventory/', {
        method: 'POST',
        body: JSON.stringify({ photo_id: _invPhotoId, supplier_id: supplierId || null, operator: null, remark: remark, items: items })
    }).then(function(res) {
        if (res.code === 200) { alert(res.message); clearInventoryForm(); }
        else { alert(res.message || '入库失败'); }
    }).catch(function(e) { alert('入库失败: ' + e.message); });
}

// ==================== 供应商管理 ====================

function openSupplierModal(supplier) {
    document.getElementById('supplier-modal').classList.remove('hidden');
    if (supplier && supplier.id) {
        _currentEditSupplierId = supplier.id;
        document.getElementById('supplier-modal-title').textContent = '编辑供应商';
        document.getElementById('supplier-id').value = supplier.id;
        document.getElementById('supplier-name').value = supplier.name || '';
        document.getElementById('supplier-contact').value = supplier.contact_person || '';
        document.getElementById('supplier-phone').value = supplier.phone || '';
        document.getElementById('supplier-address').value = supplier.address || '';
        document.getElementById('supplier-license-no').value = supplier.business_license_no || '';
        document.getElementById('supplier-remark').value = supplier.remark || '';
        document.getElementById('supplier-photo-section').classList.remove('hidden');
        loadSupplierPhotos(supplier.id);
    } else {
        _currentEditSupplierId = null;
        document.getElementById('supplier-modal-title').textContent = '新增供应商';
        document.getElementById('supplier-id').value = '';
        document.getElementById('supplier-name').value = '';
        document.getElementById('supplier-contact').value = '';
        document.getElementById('supplier-phone').value = '';
        document.getElementById('supplier-address').value = '';
        document.getElementById('supplier-license-no').value = '';
        document.getElementById('supplier-remark').value = '';
        // v8.6.3: 新增时也显示证照区域，但显示提示
        document.getElementById('supplier-photo-section').classList.remove('hidden');
        showSupplierPhotoUploadHint();
    }
}

function showSupplierPhotoUploadHint() {
    // 新增状态下显示提示文字
    var types = { '营业执照': 'supplier-photo-business', '医疗器械经营许可证': 'supplier-photo-medical', '其他': 'supplier-photo-other' };
    for (var t in types) {
        var el = document.getElementById(types[t]); if (!el) continue;
        el.innerHTML = '<div class="text-xs text-gray-400 py-1">保存后可上传</div>';
    }
}

function closeSupplierModal() {
    document.getElementById('supplier-modal').classList.add('hidden');
    _currentEditSupplierId = null;
}

function saveSupplier() {
    var name = document.getElementById('supplier-name').value.trim();
    if (!name) { alert('供应商名称不能为空'); return; }

    var data = {
        name: name,
        contact_person: document.getElementById('supplier-contact').value,
        phone: document.getElementById('supplier-phone').value,
        address: document.getElementById('supplier-address').value,
        business_license_no: document.getElementById('supplier-license-no').value,
        remark: document.getElementById('supplier-remark').value
    };

    var url = '/api/inventory/suppliers';
    var method = 'POST';
    if (_currentEditSupplierId) { url = '/api/inventory/suppliers/' + _currentEditSupplierId; method = 'PUT'; }

    api(url, { method: method, body: JSON.stringify(data) }).then(function(res) {
        if (res.code === 200) {
            if (!_currentEditSupplierId && res.data && res.data.id) {
                // 新增成功：自动切换到编辑模式，方便上传证照
                var newSupplier = {
                    id: res.data.id,
                    name: data.name,
                    contact_person: data.contact_person,
                    phone: data.phone,
                    address: data.address,
                    business_license_no: data.business_license_no,
                    remark: data.remark
                };
                openSupplierModal(newSupplier);
                loadSuppliers();
                loadSuppliersForSelect();
                alert('供应商已保存，现在可以上传证照了');
            } else {
                // 编辑成功：关闭弹窗
                closeSupplierModal(); loadSuppliers(); loadSuppliersForSelect();
            }
        }
        else { alert(res.message || '保存失败'); }
    }).catch(function(e) { alert('保存失败: ' + e.message); });
}

function loadSuppliers() {
    var keyword = document.getElementById('invs-search') ? document.getElementById('invs-search').value.trim() : '';
    api('/api/inventory/suppliers').then(function(res) {
        if (res.code !== 200) return;
        var tbody = document.getElementById('invs-list-body');
        if (!tbody) return;
        var items = res.data;
        if (keyword) items = items.filter(function(s) { return s.name.indexOf(keyword) >= 0; });
        if (items.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="px-4 py-8 text-center text-gray-400">暂无供应商</td></tr>';
            return;
        }
        tbody.innerHTML = items.map(function(s) {
            return '<tr>' +
                '<td class="px-4 py-3 font-medium">' + (s.name || '') + '</td>' +
                '<td class="px-4 py-3 text-gray-500">' + (s.contact_person || '-') + '</td>' +
                '<td class="px-4 py-3 text-gray-500">' + (s.phone || '-') + '</td>' +
                '<td class="px-4 py-3 text-gray-500">' + (s.business_license_no || '-') + '</td>' +
                '<td class="px-4 py-3 text-center"><span class="text-xs text-blue-500 cursor-pointer hover:underline" onclick="viewSupplierPhotos(' + s.id + ')">查看</span></td>' +
                '<td class="px-4 py-3 text-center"><span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs ' + (s.status === '启用' ? 'bg-emerald-100 text-emerald-800' : 'bg-gray-100 text-gray-500') + '">' + (s.status || '启用') + '</span></td>' +
                '<td class="px-4 py-3 text-center">' +
                    '<button onclick="editSupplier(' + s.id + ')" class="text-blue-500 hover:text-blue-700 text-xs mr-2">编辑</button>' +
                    '<button onclick="deleteSupplier(' + s.id + ')" class="text-red-400 hover:text-red-600 text-xs">停用</button>' +
                '</td></tr>';
        }).join('');
    }).catch(function(e) { console.log(e); });
}

function editSupplier(id) {
    api('/api/inventory/suppliers').then(function(res) {
        if (res.code !== 200) return;
        var s = res.data.find(function(x) { return x.id === id; });
        if (s) openSupplierModal(s);
    }).catch(function(e) { console.log(e); });
}

function deleteSupplier(id) {
    if (!confirm('确定停用此供应商？')) return;
    api('/api/inventory/suppliers/' + id, { method: 'DELETE' }).then(function(res) {
        if (res.code === 200) loadSuppliers();
    }).catch(function(e) { alert('停用失败: ' + e.message); });
}

function uploadSupplierPhoto(photoType) {
    if (!_currentEditSupplierId) { alert('请先保存供应商信息'); return; }
    var input = document.createElement('input');
    input.type = 'file';
    input.accept = '.jpeg,.jpg,.pdf';
    input.onchange = function() {
        var file = input.files[0]; if (!file) return;
        // 校验文件类型
        var isJpeg = /\.jpe?g$/i.test(file.name);
        var isPdf = /\.pdf$/i.test(file.name);
        if (!isJpeg && !isPdf) { alert('仅支持 JPEG/JPG 和 PDF 格式'); return; }
        if (file.size > 10 * 1024 * 1024) { alert('文件大小不能超过10MB'); return; }
        var formData = new FormData();
        formData.append('file', file); formData.append('photo_type', photoType);
        fetch('/api/inventory/suppliers/' + _currentEditSupplierId + '/photos', { method: 'POST', body: formData })
            .then(function(r) { return r.json(); })
            .then(function(res) {
                if (res.code === 200) { alert('上传成功'); loadSupplierPhotos(_currentEditSupplierId); }
                else { alert(res.message || '上传失败'); }
            }).catch(function(e) { alert('上传失败: ' + e.message); });
    };
    input.click();
}

function loadSupplierPhotos(supplierId) {
    api('/api/inventory/suppliers/' + supplierId + '/photos').then(function(res) {
        if (res.code !== 200) return;
        var types = { '营业执照': 'supplier-photo-business', '医疗器械经营许可证': 'supplier-photo-medical', '其他': 'supplier-photo-other' };
        for (var t in types) {
            var el = document.getElementById(types[t]); if (!el) continue;
            var photos = res.data.filter(function(p) { return p.photo_type === t; });
            if (photos.length > 0) {
                el.innerHTML = photos.map(function(p) {
                    var isPdf = /\.pdf$/i.test(p.storage_path || '');
                    var fname = (p.storage_path || '').split('/').pop();
                    var icon = isPdf ? '📄' : '🖼️';
                    var action = isPdf
                        ? 'window.open(\'/uploads/supplier/' + fname + '\',\'_blank\')'
                        : 'window.open(\'/uploads/supplier/' + fname + '\',\'_blank\')';
                    return '<div class="flex items-center justify-between bg-gray-50 rounded px-2 py-1">' +
                        '<span class="text-xs text-gray-600 truncate flex-1 mr-1 cursor-pointer hover:text-blue-600" onclick="' + action + '" title="' + fname + '">' + icon + ' ' + fname.substring(0, 12) + '..' + '</span>' +
                        '<button onclick="if(confirm(\'删除这张证照?\'))deleteSupplierPhoto(' + p.id + ')" class="text-red-400 hover:text-red-600 text-xs px-1">✕</button>' +
                        '</div>';
                }).join('') +
                    '<button onclick="uploadSupplierPhoto(\'' + t + '\')" class="w-full px-2 py-1 text-xs bg-gray-100 text-gray-600 rounded hover:bg-gray-200 mt-1">+ 上传</button>';
            } else {
                el.innerHTML = '<button onclick="uploadSupplierPhoto(\'' + t + '\')" class="w-full px-2 py-1 text-xs bg-gray-100 text-gray-600 rounded hover:bg-gray-200">上传</button>';
            }
        }
    }).catch(function(e) { console.log(e); });
}

function deleteSupplierPhoto(photoId) {
    api('/api/inventory/supplier-photos/' + photoId, { method: 'DELETE' }).then(function(res) {
        if (res.code === 200) { loadSupplierPhotos(_currentEditSupplierId); }
        else { alert(res.message || '删除失败'); }
    }).catch(function(e) { alert('删除失败: ' + e.message); });
}

function viewSupplierPhotos(supplierId) {
    api('/api/inventory/suppliers/' + supplierId + '/photos').then(function(res) {
        if (res.code !== 200 || res.data.length === 0) { alert('暂无证照'); return; }
        var listEl = document.getElementById('supplier-photo-view-list');
        if (!listEl) { alert('暂无证照'); return; }
        listEl.innerHTML = res.data.map(function(p) {
            var fname = (p.storage_path || '').split('/').pop();
            var isPdf = /\.pdf$/i.test(p.storage_path || '');
            var url = '/uploads/supplier/' + fname;
            if (isPdf) {
                return '<div class="border rounded-lg p-3 bg-gray-50">' +
                    '<div class="flex items-center justify-between mb-2">' +
                    '<span class="text-sm font-medium">📄 ' + (p.photo_type || 'PDF') + '</span>' +
                    '<a href="' + url + '" target="_blank" class="text-xs text-blue-500 hover:underline">下载/打开</a>' +
                    '</div>' +
                    '<div class="text-xs text-gray-400">' + fname + '</div>' +
                    '</div>';
            } else {
                return '<div class="border rounded-lg p-3">' +
                    '<div class="text-sm font-medium mb-2">🖼️ ' + (p.photo_type || '图片') + '</div>' +
                    '<img src="' + url + '" class="max-h-60 border rounded cursor-pointer" onclick="window.open(\'' + url + '\')" title="点击放大">' +
                    '<div class="text-xs text-gray-400 mt-1">' + fname + '</div>' +
                    '</div>';
            }
        }).join('');
        document.getElementById('supplier-photo-view-modal').classList.remove('hidden');
    }).catch(function() { alert('查看失败'); });
}

// ==================== 入库历史查询 ====================

function loadSuppliersForHistory() {
    api('/api/inventory/suppliers').then(function(res) {
        if (res.code !== 200) return;
        var sel = document.getElementById('invh-supplier');
        if (!sel) return;
        var html = '<option value="">全部</option>';
        res.data.forEach(function(s) { html += '<option value="' + s.id + '">' + s.name + '</option>'; });
        sel.innerHTML = html;
    }).catch(function(e) { console.log(e); });
}

function loadInventoryHistory(page) {
    page = page || _invhCurrentPage || 1;
    _invhCurrentPage = page;

    var keyword = document.getElementById('invh-keyword') ? document.getElementById('invh-keyword').value : '';
    var supplierId = document.getElementById('invh-supplier') ? document.getElementById('invh-supplier').value : '';
    var dateFrom = document.getElementById('invh-date-from') ? document.getElementById('invh-date-from').value : '';
    var dateTo = document.getElementById('invh-date-to') ? document.getElementById('invh-date-to').value : '';

    var params = new URLSearchParams();
    params.append('page', page); params.append('page_size', 20);
    if (keyword) params.append('keyword', keyword);
    if (supplierId) params.append('supplier_id', supplierId);
    if (dateFrom) params.append('date_from', dateFrom);
    if (dateTo) params.append('date_to', dateTo);

    api('/api/inventory/?' + params.toString()).then(function(res) {
        if (res.code !== 200) return;
        var tbody = document.getElementById('invh-list-body');
        var items = res.data.items || [];
        if (items.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" class="px-4 py-8 text-center text-gray-400">暂无入库记录</td></tr>';
            document.getElementById('invh-pagination').innerHTML = '';
            return;
        }

        tbody.innerHTML = items.map(function(r) {
            var date = formatDateTime(r.created_at);
            var batch = r.batch_no_rk || '';
            var supplier = r.supplier_name || '-';
            var qualified = r.is_qualified === '合格'
                ? '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800"><span class="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1"></span>合格</span>'
                : '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800"><span class="w-1.5 h-1.5 rounded-full bg-red-500 mr-1"></span>' + (r.is_qualified || '待检') + '</span>';
            return '<tr class="hover:bg-gray-50">' +
                '<td class="px-4 py-3 text-gray-600">' + date + '</td>' +
                '<td class="px-4 py-3 font-mono text-xs text-gray-500">' + batch + '</td>' +
                '<td class="px-4 py-3">' + supplier + '</td>' +
                '<td class="px-4 py-3 font-medium">' + (r.name || '') + '</td>' +
                '<td class="px-4 py-3 text-right">' + (r.quantity || 0) + ' ' + (r.unit || '') + '</td>' +
                '<td class="px-4 py-3 text-center text-gray-600">' + formatDate(r.production_date) + '</td>' +
                '<td class="px-4 py-3 text-center text-gray-600">' + formatDate(r.expiry_date) + '</td>' +
                '<td class="px-4 py-3 text-center">' + qualified + '</td>' +
                '<td class="px-4 py-3 text-center">' +
                    '<button onclick="showInventoryDetail(' + r.id + ')" class="text-blue-500 hover:text-blue-700 text-xs mr-2">详情</button>' +
                    '<button onclick="openInventoryEdit(' + r.id + ')" class="text-emerald-600 hover:text-emerald-800 text-xs mr-2">编辑</button>' +
                    '<button onclick="deleteInventory(' + r.id + ')" class="text-red-400 hover:text-red-600 text-xs">删除</button>' +
                '</td></tr>';
        }).join('');

        var total = res.data.total || 0;
        var pageSize = res.data.page_size || 20;
        var totalPages = Math.ceil(total / pageSize);
        var pgHtml = '<span class="text-sm text-gray-500">共 ' + total + ' 条</span><div class="flex gap-1">';
        for (var i = 1; i <= totalPages; i++) {
            pgHtml += '<button onclick="loadInventoryHistory(' + i + ')" class="px-2 py-1 text-xs rounded ' + (i === page ? 'bg-primary text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200') + '">' + i + '</button>';
        }
        pgHtml += '</div>';
        document.getElementById('invh-pagination').innerHTML = pgHtml;
    }).catch(function(e) { console.log('[InventoryHistory] error', e); });
}

function showInventoryDetail(id) {
    api('/api/inventory/' + id).then(function(res) {
        if (res.code !== 200) { alert('记录不存在'); return; }
        var r = res.data;
        var html = '<div class="grid grid-cols-2 gap-3">' +
            '<div><span class="text-gray-500">名称:</span> ' + (r.name || '') + '</div>' +
            '<div><span class="text-gray-500">规格:</span> ' + (r.specification || '-') + '</div>' +
            '<div><span class="text-gray-500">数量:</span> ' + (r.quantity || 0) + ' ' + (r.unit || '') + '</div>' +
            '<div><span class="text-gray-500">总价:</span> ' + (r.total_price || 0) + '</div>' +
            '<div><span class="text-gray-500">批号:</span> ' + (r.batch_no || '-') + '</div>' +
            '<div><span class="text-gray-500">生产日期:</span> ' + formatDate(r.production_date) + '</div>' +
            '<div><span class="text-gray-500">有效期:</span> ' + formatDate(r.expiry_date) + '</div>' +
            '<div><span class="text-gray-500">生产企业:</span> ' + (r.manufacturer || '-') + '</div>' +
            '<div><span class="text-gray-500">供应商:</span> ' + (r.supplier_name || '-') + '</div>' +
            '<div class="col-span-2"><span class="text-gray-500">入库时间:</span> ' + formatDateTime(r.created_at) + '</div>' +
            '<div class="col-span-2"><span class="text-gray-500">合格状态:</span> <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800 ml-1"><span class="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1"></span>合格</span></div>';
        if (r.photo_path) {
            var pathParts = r.photo_path.split('/');
            var fname = pathParts[pathParts.length - 1];
            html += '<div class="col-span-2 mt-2"><span class="text-gray-500">出库单照片:</span><br><img src="/uploads/inventory/' + fname + '" class="mt-2 max-h-60 border rounded"></div>';
        }
        html += '</div>';
        document.getElementById('inventory-detail-content').innerHTML = html;
        // 绑定编辑按钮
        document.getElementById('inv-detail-edit-btn').onclick = function() {
            closeInventoryDetail();
            openInventoryEdit(id);
        };
        document.getElementById('inventory-detail-modal').classList.remove('hidden');
    }).catch(function() { alert('加载失败'); });
}

function closeInventoryDetail() {
    document.getElementById('inventory-detail-modal').classList.add('hidden');
}

function deleteInventory(id) {
    if (!confirm('确定删除这条入库记录？')) return;
    api('/api/inventory/' + id, { method: 'DELETE' }).then(function(res) {
        if (res.code === 200) { alert('已删除'); loadInventoryHistory(_invhCurrentPage); }
        else { alert(res.message || '删除失败'); }
    }).catch(function(e) { alert('删除失败: ' + e.message); });
}

// ==================== 入库编辑 ====================

var _currentEditInvId = null;

function openInventoryEdit(id) {
    _currentEditInvId = id;
    // 加载供应商列表
    var supplierSelect = document.getElementById('inv-edit-supplier');
    if (supplierSelect && supplierSelect.options.length <= 1) {
        api('/api/inventory/suppliers').then(function(res) {
            if (res.code === 200) {
                supplierSelect.innerHTML = '<option value="">无</option>';
                (res.data || []).forEach(function(s) {
                    supplierSelect.innerHTML += '<option value="' + s.id + '">' + s.name + '</option>';
                });
            }
        });
    }
    // 加载记录数据
    api('/api/inventory/' + id).then(function(res) {
        if (res.code !== 200) { alert('加载失败'); return; }
        var r = res.data;
        document.getElementById('inv-edit-id').value = r.id || '';
        document.getElementById('inv-edit-name').value = r.name || '';
        document.getElementById('inv-edit-cat').value = r.category || '耗材';
        document.getElementById('inv-edit-spec').value = r.specification || '';
        document.getElementById('inv-edit-qty').value = r.quantity || '';
        document.getElementById('inv-edit-unit').value = r.unit || '';
        document.getElementById('inv-edit-batch').value = r.batch_no || '';
        document.getElementById('inv-edit-prod-date').value = (r.production_date || '').split('T')[0];
        document.getElementById('inv-edit-expiry').value = (r.expiry_date || '').split('T')[0];
        document.getElementById('inv-edit-mfr').value = r.manufacturer || '';
        document.getElementById('inv-edit-license').value = r.manufacturer_license || '';
        document.getElementById('inv-edit-price').value = r.unit_price || '';
        document.getElementById('inv-edit-total').value = r.total_price || '';
        document.getElementById('inv-edit-tax').value = r.tax_amount || '';
        document.getElementById('inv-edit-supplier').value = r.supplier_id || '';
        document.getElementById('inv-edit-remark').value = r.remark || '';
        document.getElementById('inventory-edit-modal').classList.remove('hidden');
    }).catch(function() { alert('加载失败'); });
}

function closeInventoryEdit() {
    document.getElementById('inventory-edit-modal').classList.add('hidden');
    _currentEditInvId = null;
}

function calcInvEditTax() {
    var price = parseFloat(document.getElementById('inv-edit-price').value) || 0;
    var total = parseFloat(document.getElementById('inv-edit-total').value) || 0;
    var taxInput = document.getElementById('inv-edit-tax');
    if (price > 0 && total > 0) {
        var tax = total - price;
        taxInput.value = tax > 0 ? tax.toFixed(2) : '0';
    } else { taxInput.value = ''; }
}

function submitInventoryEdit() {
    if (!_currentEditInvId) return;
    var name = document.getElementById('inv-edit-name').value.trim();
    var qty = document.getElementById('inv-edit-qty').value;
    var unit = document.getElementById('inv-edit-unit').value;
    var total = document.getElementById('inv-edit-total').value;
    if (!name) { alert('名称不能为空'); return; }
    if (!qty) { alert('数量不能为空'); return; }
    if (!unit) { alert('单位不能为空'); return; }
    if (!total) { alert('总价不能为空'); return; }

    var price = parseFloat(document.getElementById('inv-edit-price').value) || 0;
    var totalVal = parseFloat(total);
    var tax = null;
    if (price > 0 && totalVal > 0) {
        tax = totalVal - price;
        if (tax < 0) tax = 0;
    }

    var data = {
        name: name,
        category: document.getElementById('inv-edit-cat').value,
        specification: document.getElementById('inv-edit-spec').value || null,
        quantity: parseFloat(qty),
        unit: unit,
        batch_no: document.getElementById('inv-edit-batch').value || null,
        production_date: document.getElementById('inv-edit-prod-date').value || null,
        expiry_date: document.getElementById('inv-edit-expiry').value || null,
        manufacturer: document.getElementById('inv-edit-mfr').value || null,
        manufacturer_license: document.getElementById('inv-edit-license').value || null,
        unit_price: price || null,
        tax_amount: tax,
        total_price: totalVal,
        supplier_id: document.getElementById('inv-edit-supplier').value || null,
        remark: document.getElementById('inv-edit-remark').value
    };

    api('/api/inventory/' + _currentEditInvId, {
        method: 'PUT',
        body: JSON.stringify(data)
    }).then(function(res) {
        if (res.code === 200) {
            alert('更新成功');
            closeInventoryEdit();
            loadInventoryHistory(_invhCurrentPage);
        } else { alert(res.message || '更新失败'); }
    }).catch(function(e) { alert('更新失败: ' + e.message); });
}

// ==================== 库存预警 ====================

function loadInventoryWarnings(level) {
    level = level || 'all';
    document.querySelectorAll('.invw-filter').forEach(function(btn) {
        if (btn.dataset.filter === level) {
            btn.classList.remove('bg-gray-100', 'text-gray-600');
            btn.classList.add('bg-primary', 'text-white');
        } else {
            btn.classList.remove('bg-primary', 'text-white');
            btn.classList.add('bg-gray-100', 'text-gray-600');
        }
    });

    api('/api/inventory/warnings?level=' + level).then(function(res) {
        if (res.code !== 200) return;
        var tbody = document.getElementById('invw-list-body');
        var items = res.data || [];
        if (items.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="px-4 py-8 text-center text-gray-400">暂无预警商品</td></tr>';
            return;
        }
        tbody.innerHTML = items.map(function(r) {
            var remain = r.remain_days || 0;
            var status;
            if (r.warn_level === 'expired') {
                status = '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800"><span class="w-1.5 h-1.5 rounded-full bg-red-500 mr-1"></span>已过期</span>';
            } else if (r.warn_level === 'critical') {
                status = '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-800"><span class="w-1.5 h-1.5 rounded-full bg-orange-500 mr-1"></span>30天内</span>';
            } else if (r.warn_level === 'warning') {
                status = '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800"><span class="w-1.5 h-1.5 rounded-full bg-yellow-500 mr-1"></span>90天内</span>';
            } else {
                status = '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800"><span class="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1"></span>正常</span>';
            }
            return '<tr class="hover:bg-gray-50">' +
                '<td class="px-4 py-3 font-medium">' + (r.name || '') + '</td>' +
                '<td class="px-4 py-3 text-gray-500 text-xs">' + (r.batch_no || '-') + '</td>' +
                '<td class="px-4 py-3 text-gray-500">' + (r.specification || '-') + '</td>' +
                '<td class="px-4 py-3 text-right">' + (r.current_stock || 0) + ' ' + (r.unit || '') + '</td>' +
                '<td class="px-4 py-3 text-center text-gray-600">' + formatDate(r.production_date) + '</td>' +
                '<td class="px-4 py-3 text-center text-gray-600">' + formatDate(r.expiry_date) + '</td>' +
                '<td class="px-4 py-3 text-right ' + (remain < 0 ? 'text-red-600 font-medium' : (remain <= 30 ? 'text-orange-600' : '')) + '">' + (remain < 0 ? '已过期' : remain + ' 天') + '</td>' +
                '<td class="px-4 py-3 text-center">' + status + '</td></tr>';
        }).join('');
    }).catch(function(e) { console.log(e); });
}
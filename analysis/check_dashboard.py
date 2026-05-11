#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""检查 dashboard.html 是否包含 plotly.js 和图表渲染代码"""

import re

HTML_FILE = r"F:\douban\analysis\output\dashboard.html"

with open(HTML_FILE, "r", encoding="utf-8") as f:
    content = f.read()

print(f"文件大小: {len(content):,d} 字节")

# 1. 检查 plotly.js 嵌入
if "window.PlotlyConfig" in content:
    print("✅ plotly.js 配置已嵌入")
else:
    print("❌ plotly.js 配置未找到")

if "window.Plotly" in content and "window.Plotly" not in content[:content.find("window.PlotlyConfig")+1]:
    # Check if plotly.js script actually defines Plotly
    print("✅ window.Plotly 定义检查通过")
else:
    print("❌ window.Plotly 定义可能有问题")

# 2. 检查 Plotly.newPlot 调用次数
newplot_calls = content.count("Plotly.newPlot")
print(f"📊 Plotly.newPlot 调用次数: {newplot_calls}")

# 3. 检查 jQuery/DataTables CDN
if "cdn.bootcdn.net/ajax/libs/jquery" in content:
    print("✅ jQuery CDN: bootcdn")
else:
    print("❌ jQuery CDN 未找到")

if "cdn.bootcdn.net/ajax/libs/datatables" in content:
    print("✅ DataTables CDN: bootcdn")
else:
    print("❌ DataTables CDN 未找到")

# 4. 检查是否有旧的 cdn.plot.ly 引用
if "cdn.plot.ly" in content:
    print("⚠️  警告: 仍存在 cdn.plot.ly 引用 (应该已移除)")
else:
    print("✅ 无 cdn.plot.ly 引用 (正确)")

# 5. 检查第一个 chart-card 结构
first_card = content.find('<div class="chart-card">')
if first_card != -1:
    card_section = content[first_card:first_card+200]
    if "<script>" in card_section:
        print("✅ 第一个 chart-card 包含内嵌 <script>")
    else:
        print("❌ 第一个 chart-card 没有内嵌 script")

# 6. 检查 tab 结构
tabs = re.findall(r'id="tab-(\w+)"', content)
print(f"📑 找到标签页: {tabs}")

print("\n🎯 请打开浏览器检查:")
print(f"   1. 按 Ctrl+F5 强制刷新")
print(f"   2. 按 F12 打开开发者工具")
print(f"   3. 查看 Console 标签是否有 JavaScript 错误")
print(f"   4. 查看 Network 标签检查 plotly.js 是否加载成功")

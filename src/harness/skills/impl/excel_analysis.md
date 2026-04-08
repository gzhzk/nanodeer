---
name: excel_analysis
description: Analyze Excel files with pandas, generate charts and statistics. Use when user asks to analyze data, process Excel files, create charts, or generate data reports.
disable-model-invocation: true
compatibility: ReadFile ExecPython WriteFile Ls
---

# Excel Data Analysis

用 pandas 读取 Excel、用 matplotlib 生成图表，输出分析报告。

## 工作流程

### 1. 读取文件
使用 ReadFile 确认文件路径和格式。

### 2. 数据分析
使用 ExecPython 执行分析：
- 基本统计：`df.describe()`
- 分组聚合：`df.groupby().sum()`
- 指标计算：完成率、同比、环比等

### 3. 生成图表
matplotlib 保存到 `/mnt/user-data/outputs/` 目录。

### 4. 输出结果
WriteFile 保存分析结果或图表路径。

## 分析模式

### 基础分析
```python
import pandas as pd
import matplotlib.pyplot as plt
matplotlib.use('Agg')

df = pd.read_excel("file.xlsx")
print("数据形状:", df.shape)
print("列名:", df.columns.tolist())
print(df.describe())
```

### 完成率计算
```python
df["完成率"] = df["实际"] / df["指标"] * 100
df["完成率"] = df["完成率"].round(2)
```

### 分组统计
```python
# 按部门汇总
dept_sum = df.groupby("部门")["销售额"].sum().sort_values(ascending=False)
```

### 排名
```python
top10 = df.nlargest(10, "销售额")[["姓名", "销售额", "部门"]]
```

## 图表模式

### 中文配置
```python
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
```

### 柱状图 - 排名
```python
fig, ax = plt.subplots(figsize=(12, 6))
top10 = df.nlargest(10, "销售额")
ax.barh(top10["姓名"], top10["销售额"], color='steelblue')
ax.set_title("销售额 Top10")
plt.tight_layout()
plt.savefig("/mnt/user-data/outputs/top10.png", dpi=150)
```

### 饼图 - 占比
```python
fig, ax = plt.subplots()
dept_sum = df.groupby("部门")["销售额"].sum()
ax.pie(dept_sum, labels=dept_sum.index, autopct='%1.1f%%')
ax.set_title("部门销售占比")
plt.tight_layout()
plt.savefig("/mnt/user-data/outputs/dept_pie.png", dpi=150)
```

### 折线图 - 趋势
```python
fig, ax = plt.subplots()
monthly = df.groupby("月份")["销售额"].sum()
ax.plot(monthly.index.astype(str), monthly.values, marker='o')
ax.set_title("月度销售额趋势")
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig("/mnt/user-data/outputs/trend.png", dpi=150)
```

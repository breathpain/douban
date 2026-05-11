#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
豆瓣电影 Top250 增强交互式数据仪表盘生成器
=============================================
生成一个独立的 HTML 文件，包含：
  - 概览统计卡片
  - 筛选面板（类型/国家/年代联动）
  - 12+ 个交互式 Plotly 图表
  - 可搜索、排序的电影数据表格（支持详情弹窗）
  - 现代化深色主题 UI + 标签页导航
"""

import json
import os
import re
import sys
import warnings
from collections import Counter, defaultdict
from datetime import datetime

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

try:
    import plotly.express as px
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
except ImportError:
    print("请安装 plotly: pip install plotly")
    sys.exit(1)

# ======== 路径 ========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATA_FILE = os.path.join(PROJECT_ROOT, "data", "member_b", "backup", "douban_movies.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 内嵌的依赖文件路径 (预先下载好)
JQUERY_PATH = os.path.join(OUTPUT_DIR, "jquery.min.js")
DATATABLES_JS_PATH = os.path.join(OUTPUT_DIR, "datatables.min.js")
DATATABLES_CSS_PATH = os.path.join(OUTPUT_DIR, "datatables.min.css")

RATING_MAP = {"力荐": 5, "推荐": 4, "还行": 3, "较差": 2, "很差": 1, "": np.nan}

# ======== 国家→ISO代码映射 (用于世界地图) ========
COUNTRY_ISO = {
    "美国": "USA", "英国": "GBR", "法国": "FRA", "德国": "DEU", "意大利": "ITA",
    "日本": "JPN", "韩国": "KOR", "印度": "IND", "中国大陆": "CHN", "中国香港": "HKG",
    "中国台湾": "TWN", "加拿大": "CAN", "澳大利亚": "AUS", "西班牙": "ESP",
    "瑞典": "SWE", "丹麦": "DNK", "新西兰": "NZL", "巴西": "BRA", "墨西哥": "MEX",
    "阿根廷": "ARG", "俄罗斯": "RUS", "荷兰": "NLD", "比利时": "BEL",
    "瑞士": "CHE", "奥地利": "AUT", "波兰": "POL", "捷克": "CZE",
    "爱尔兰": "IRL", "挪威": "NOR", "芬兰": "FIN", "葡萄牙": "PRT",
    "泰国": "THA", "伊朗": "IRN", "土耳其": "TUR", "南非": "ZAF",
    "匈牙利": "HUN", "罗马尼亚": "ROU", "希腊": "GRC",
}


def load_and_clean():
    """加载并清洗数据。"""
    print("[加载] 读取数据...")
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)
    df = pd.DataFrame(raw)

    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
    df["comment_count"] = pd.to_numeric(df["comment_count"], errors="coerce").fillna(0).astype(int)
    df["rank"] = pd.to_numeric(df["rank"], errors="coerce").fillna(0).astype(int)
    df["runtime"] = pd.to_numeric(df["runtime"], errors="coerce").fillna(0).astype(int)

    df["release_year"] = df["release_date"].apply(
        lambda x: int(re.search(r"(\d{4})", str(x)).group(1))
        if isinstance(x, str) and re.search(r"(\d{4})", x) else np.nan
    )
    df["decade"] = (df["release_year"] // 10 * 10).astype("Int64")

    df["genre_list"] = df["genres"].apply(
        lambda x: [g.strip() for g in str(x).split("/") if g.strip()] if x else []
    )
    df["director_list"] = df["director"].apply(
        lambda x: [d.strip() for d in str(x).split("/") if d.strip()] if x else []
    )
    df["country_list"] = df["country"].apply(
        lambda x: [c.strip() for c in str(x).split("/") if c.strip() and c.strip() != "未知"] if x else []
    )
    df["language_list"] = df["language"].apply(
        lambda x: [l.strip() for l in str(x).split("/") if l.strip()] if x else []
    )

    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(lambda x: x.replace("\u00a0", " ").strip() if isinstance(x, str) else x)

    # 提取短评
    comments_list = []
    for _, row in df.iterrows():
        raw_comments = row.get("comments", [])
        if not raw_comments or not isinstance(raw_comments, list):
            continue
        for c in raw_comments:
            c["movie_id"] = row.get("id")
            c["movie_title"] = row.get("title_cn", row.get("title", ""))
            c["movie_rating"] = row.get("rating")
            comments_list.append(c)

    comments_df = pd.DataFrame(comments_list)
    if "rating" in comments_df.columns:
        comments_df["rating_score"] = comments_df["rating"].map(RATING_MAP)
        comments_df["rating_score"] = pd.to_numeric(comments_df["rating_score"], errors="coerce")
    comments_df["comment"] = comments_df["comment"].apply(
        lambda x: x.replace("\u00a0", " ").strip() if isinstance(x, str) else ""
    )
    comments_df["comment_time"] = pd.to_datetime(comments_df["comment_time"], errors="coerce")
    if "helpful" in comments_df.columns:
        comments_df["helpful"] = pd.to_numeric(comments_df["helpful"], errors="coerce").fillna(0).astype(int)

    print(f"  电影: {len(df)} 条, 短评: {len(comments_df)} 条")
    return df, comments_df


# ======== 概览卡片 ========

def build_overview_cards(df, comments_df):
    """概览统计卡片 HTML。"""
    total = len(df)
    avg_rating = df["rating"].mean()
    total_comments = df["comment_count"].sum()
    pos_pct = (comments_df["rating_score"].dropna() >= 4).mean() * 100
    avg_runtime = df[df["runtime"] > 0]["runtime"].mean()
    country_set = set()
    for cl in df["country_list"]:
        for c in cl:
            country_set.add(c)
    country_count = len(country_set)
    # 获奖统计 (imdb 不为空)
    imdb_count = df["imdb"].apply(lambda x: 1 if x and str(x).startswith("tt") else 0).sum()
    # 类型数量
    genre_set = set()
    for gl in df["genre_list"]:
        for g in gl:
            genre_set.add(g)

    cards_html = f"""
    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-icon">🎬</div>
            <div class="stat-number">{total}</div>
            <div class="stat-label">电影总数</div>
        </div>
        <div class="stat-card">
            <div class="stat-icon">⭐</div>
            <div class="stat-number">{avg_rating:.1f}</div>
            <div class="stat-label">平均评分</div>
        </div>
        <div class="stat-card">
            <div class="stat-icon">💬</div>
            <div class="stat-number">{total_comments/1e6:.1f}M</div>
            <div class="stat-label">总评论数</div>
        </div>
        <div class="stat-card">
            <div class="stat-icon">👍</div>
            <div class="stat-number">{pos_pct:.1f}%</div>
            <div class="stat-label">好评率</div>
        </div>
        <div class="stat-card">
            <div class="stat-icon">⏱️</div>
            <div class="stat-number">{avg_runtime:.0f}分</div>
            <div class="stat-label">平均片长</div>
        </div>
        <div class="stat-card">
            <div class="stat-icon">🌍</div>
            <div class="stat-number">{country_count}</div>
            <div class="stat-label">覆盖国家/地区</div>
        </div>
        <div class="stat-card">
            <div class="stat-icon">🏷️</div>
            <div class="stat-number">{len(genre_set)}</div>
            <div class="stat-label">电影类型</div>
        </div>
        <div class="stat-card">
            <div class="stat-icon">🎯</div>
            <div class="stat-number">{imdb_count}</div>
            <div class="stat-label">IMDb收录</div>
        </div>
    </div>"""
    return cards_html


# ======== 图表构建函数 ========

def build_rating_histogram(df):
    """评分分布直方图。"""
    ratings = df["rating"].dropna()
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=ratings, nbinsx=18, marker_color="#636efa",
        opacity=0.75, name="评分数", histnorm="probability"
    ))
    fig.add_vline(x=ratings.mean(), line_dash="dash", line_color="red",
                  annotation_text=f"均值 ★{ratings.mean():.2f}")
    fig.add_vline(x=ratings.median(), line_dash="dot", line_color="orange",
                  annotation_text=f"中位数 ★{ratings.median():.1f}")
    fig.update_layout(
        title="📊 评分分布直方图", xaxis_title="豆瓣评分", yaxis_title="频率",
        template="plotly_dark", height=380, margin=dict(l=40, r=20, t=50, b=40),
        bargap=0.05
    )
    return fig


def build_sentiment_pie(comments_df):
    """短评情感倾向饼图。"""
    scores = comments_df["rating_score"].dropna()
    pos = (scores >= 4).sum()
    neu = (scores == 3).sum()
    neg = (scores <= 2).sum()
    total = len(scores)

    fig = go.Figure(go.Pie(
        labels=["正面 (力荐+推荐)", "中性 (还行)", "负面 (较差+很差)"],
        values=[pos, neu, neg],
        hole=0.55,
        marker_colors=["#00cc96", "#ffa15a", "#ef553b"],
        textinfo="percent+label",
        textfont_size=12,
        hovertemplate="%{label}<br>%{value:,d} 条短评<br>占比: %{percent}"
    ))
    fig.update_layout(
        title="😊 短评情感倾向分析", template="plotly_dark",
        height=400, margin=dict(l=20, r=20, t=50, b=20),
        annotations=[dict(text=f"好评率<br>{pos/total*100:.1f}%",
                          x=0.5, y=0.5, font_size=22, showarrow=False)]
    )
    return fig


def build_rating_vs_comments(df):
    """评分 vs 评论人数散点图。"""
    valid = df[(df["comment_count"] > 0) & df["rating"].notna()].copy()
    valid["log_comments"] = np.log10(valid["comment_count"])

    fig = px.scatter(
        valid, x="rating", y="log_comments", color="rating",
        size="comment_count", size_max=25,
        hover_name="title_cn", hover_data={
            "director": True, "release_year": True, "comment_count": True
        },
        color_continuous_scale="Viridis",
        title="📈 评分 vs 评论人数 (log₁₀ 坐标)",
        labels={"rating": "豆瓣评分", "log_comments": "log₁₀(评论人数)"},
        template="plotly_dark", height=450,
    )
    fig.update_layout(margin=dict(l=40, r=20, t=50, b=40))
    return fig


def build_time_trend(df):
    """时间趋势双轴图。"""
    year_data = df[df["release_year"].notna() & (df["release_year"] > 1900)].copy()
    year_data["release_year"] = year_data["release_year"].astype(int)
    yearly = year_data.groupby("release_year").agg(
        count=("id", "count"), avg_rating=("rating", "mean")
    ).reset_index()
    yearly = yearly[(yearly["release_year"] >= 1930) & (yearly["release_year"] <= 2025)]

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=yearly["release_year"], y=yearly["count"],
        name="电影数量", marker_color="#636efa", opacity=0.7
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=yearly["release_year"], y=yearly["avg_rating"],
        name="平均评分", mode="lines+markers", line=dict(color="#ef553b", width=2.5),
        marker=dict(size=6)
    ), secondary_y=True)
    fig.update_layout(
        title="📅 电影发行年份趋势 (数量 vs 平均评分)",
        template="plotly_dark", height=400, hovermode="x unified",
        margin=dict(l=40, r=40, t=50, b=40),
    )
    fig.update_xaxes(title_text="发行年份")
    fig.update_yaxes(title_text="电影数量", secondary_y=False)
    fig.update_yaxes(title_text="平均评分 ★", secondary_y=True, range=[8.0, 9.8])
    return fig


def build_genre_bar(df):
    """类型分布柱状图。"""
    genre_counter = Counter()
    for gl in df["genre_list"]:
        for g in gl:
            if g:
                genre_counter[g] += 1
    top = genre_counter.most_common(15)
    names = [g for g, _ in top]
    counts = [c for _, c in top]

    fig = go.Figure(go.Bar(
        x=counts, y=names, orientation="h",
        marker=dict(color=counts, colorscale="Bluered", showscale=True, colorbar=dict(title="数量")),
        text=counts, textposition="outside",
        hovertemplate="%{y}: %{x} 部电影"
    ))
    fig.update_layout(
        title="🎭 电影类型分布 Top 15", xaxis_title="电影数量",
        template="plotly_dark", height=420, margin=dict(l=40, r=60, t=50, b=40),
        yaxis=dict(autorange="reversed")
    )
    return fig


def build_country_map(df):
    """国别分布柱状图。"""
    country_counter = Counter()
    for cl in df["country_list"]:
        for c in cl:
            country_counter[c] += 1
    top = country_counter.most_common(15)
    names = [c for c, _ in top]
    counts = [cnt for _, cnt in top]

    fig = go.Figure(go.Bar(
        x=names, y=counts,
        marker=dict(color=counts, colorscale="Tealgrn"),
        text=counts, textposition="outside",
        hovertemplate="%{x}: %{y} 部电影"
    ))
    fig.update_layout(
        title="🌍 电影国别/地区分布 Top 15", xaxis_title="国家/地区", yaxis_title="电影数量",
        template="plotly_dark", height=380, margin=dict(l=40, r=20, t=50, b=80),
        xaxis_tickangle=-30
    )
    return fig


def build_world_choropleth(df):
    """世界地图 - 各国电影数量分布。"""
    country_counter = Counter()
    for cl in df["country_list"]:
        for c in cl:
            country_counter[c] += 1

    iso_data = []
    for cname, cnt in country_counter.items():
        iso = COUNTRY_ISO.get(cname)
        if iso:
            iso_data.append({"country": iso, "count": cnt, "name": cname})

    map_df = pd.DataFrame(iso_data)
    if map_df.empty:
        return go.Figure()

    fig = px.choropleth(
        map_df, locations="country", locationmode="ISO-3",
        color="count", hover_name="name", hover_data={"count": True, "country": False},
        color_continuous_scale="Blues",
        title="🗺️ 全球电影数量分布",
        labels={"count": "电影数量"},
        template="plotly_dark", height=450,
    )
    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20))
    return fig


def build_runtime_violin(df):
    """片长分布小提琴图。"""
    valid = df[df["runtime"] > 0].copy()
    decade_order = sorted([d for d in valid["decade"].dropna().unique() if 1940 <= d <= 2030])
    fig = go.Figure()
    for decade in decade_order:
        subset = valid[valid["decade"] == decade]["runtime"]
        if len(subset) > 0:
            fig.add_trace(go.Violin(
                y=subset, name=str(decade), box_visible=True,
                meanline_visible=True, line_color="white"
            ))
    fig.update_layout(
        title="🎻 各年代影片时长分布 (小提琴图)", yaxis_title="片长 (分钟)",
        template="plotly_dark", height=420, showlegend=False,
        margin=dict(l=40, r=20, t=50, b=60),
        xaxis=dict(title="年代", tickangle=-30)
    )
    return fig


def build_correlation_heatmap(df):
    """数值字段相关性热力图。"""
    cols = ["rating", "comment_count", "runtime", "release_year"]
    corr_df = df[cols].dropna()
    corr_matrix = corr_df.corr().round(3)
    labels_map = {"rating": "评分", "comment_count": "评论数", "runtime": "片长", "release_year": "发行年份"}
    fig = go.Figure(go.Heatmap(
        z=corr_matrix.values,
        x=[labels_map.get(c, c) for c in corr_matrix.columns],
        y=[labels_map.get(c, c) for c in corr_matrix.index],
        text=corr_matrix.values, texttemplate="%{text:.3f}",
        colorscale="RdBu_r", zmid=0, zmin=-1, zmax=1,
        hovertemplate="%{y} vs %{x}<br>r = %{z:.3f}"
    ))
    fig.update_layout(
        title="🔗 数值字段相关性热力图", template="plotly_dark",
        height=380, margin=dict(l=60, r=20, t=50, b=60),
    )
    return fig


def build_genre_radar(df):
    """类型评分雷达图。"""
    genre_counter = Counter()
    for gl in df["genre_list"]:
        for g in gl:
            if g:
                genre_counter[g] += 1
    top_genres = [g for g, _ in genre_counter.most_common(10)]

    genre_ratings = defaultdict(list)
    for gl, r in zip(df["genre_list"], df["rating"]):
        for g in gl:
            if g in top_genres and pd.notna(r):
                genre_ratings[g].append(r)

    values = [np.mean(genre_ratings[g]) for g in top_genres]
    counts = [len(genre_ratings[g]) for g in top_genres]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values, theta=top_genres, fill="toself",
        name="平均评分", marker=dict(color="#636efa", size=8),
        line=dict(color="#636efa", width=2.5),
        hovertemplate="%{theta}: ★%{r:.2f}<extra></extra>"
    ))
    # 整体均值
    overall = df["rating"].mean()
    fig.add_trace(go.Scatterpolar(
        r=[overall] * len(top_genres), theta=top_genres,
        name=f"整体均值 ★{overall:.2f}", mode="lines",
        line=dict(color="#ef553b", width=1.5, dash="dash"),
        hovertemplate="整体均值: ★%{r:.2f}<extra></extra>"
    ))
    fig.update_layout(
        title="🎯 主要类型平均评分雷达图",
        template="plotly_dark", height=450,
        polar=dict(
            radialaxis=dict(visible=True, range=[8.2, 9.5], tickfont_size=10),
            angularaxis=dict(tickfont_size=11)
        ),
        margin=dict(l=40, r=40, t=60, b=40),
        showlegend=True, legend=dict(x=0.85, y=0.05)
    )
    return fig


def build_director_bubble(df):
    """导演气泡图。"""
    director_info = defaultdict(list)
    for dl, r, cc in zip(df["director_list"], df["rating"], df["comment_count"]):
        for d in dl:
            if d and d != "未知" and pd.notna(r):
                director_info[d].append({"rating": r, "comments": cc})

    dir_data = []
    for d, items in director_info.items():
        if len(items) >= 2:
            avg_r = np.mean([it["rating"] for it in items])
            total_cc = sum([it["comments"] for it in items])
            dir_data.append({"director": d, "count": len(items),
                             "avg_rating": avg_r, "total_comments": total_cc})

    dir_df = pd.DataFrame(dir_data).sort_values("count", ascending=False).head(30)

    fig = px.scatter(
        dir_df, x="avg_rating", y="count",
        size="total_comments", size_max=45,
        color="avg_rating", color_continuous_scale="RdYlGn",
        hover_name="director",
        hover_data={"count": True, "avg_rating": ":.2f", "total_comments": True},
        title="🎬 导演作品数 vs 平均评分 (气泡大小=总评论数)",
        labels={"avg_rating": "平均评分", "count": "作品数量", "total_comments": "总评论数"},
        template="plotly_dark", height=480,
        text="director"
    )
    fig.update_traces(textposition="top center", textfont_size=9)
    fig.update_layout(margin=dict(l=40, r=20, t=50, b=40))
    return fig


def build_language_chart(df):
    """语言分布饼图。"""
    lang_counter = Counter()
    for ll in df["language_list"]:
        for l in ll:
            lang_counter[l] += 1
    top = lang_counter.most_common(8)
    other = sum(cnt for _, cnt in lang_counter.most_common()[8:])
    labels = [l for l, _ in top]
    values = [cnt for _, cnt in top]
    if other > 0:
        labels.append("其他")
        values.append(other)

    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.5,
        textinfo="percent+label", textfont_size=12,
        marker=dict(colors=px.colors.qualitative.Set3[:len(labels)]),
        hovertemplate="%{label}<br>%{value} 部电影<br>%{percent}"
    ))
    fig.update_layout(
        title="🗣️ 电影语言分布",
        template="plotly_dark", height=400,
        margin=dict(l=20, r=20, t=50, b=20)
    )
    return fig


def build_comment_timeline(comments_df):
    """短评时间线 - 按月统计。"""
    valid = comments_df[comments_df["comment_time"].notna()].copy()
    if len(valid) == 0:
        return go.Figure()
    valid["month"] = valid["comment_time"].dt.to_period("M").dt.to_timestamp()
    monthly = valid.groupby("month").agg(
        count=("comment", "count"),
        avg_score=("rating_score", "mean")
    ).reset_index()
    monthly = monthly.sort_values("month")

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(
        x=monthly["month"], y=monthly["count"],
        name="短评数量", mode="lines", fill="tozeroy",
        line=dict(color="#636efa", width=2), fillcolor="rgba(99,110,250,0.2)"
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=monthly["month"], y=monthly["avg_score"],
        name="平均评分", mode="lines+markers",
        line=dict(color="#00cc96", width=2), marker=dict(size=4)
    ), secondary_y=True)
    fig.update_layout(
        title="📝 短评月度趋势",
        template="plotly_dark", height=380, hovermode="x unified",
        margin=dict(l=40, r=40, t=50, b=40),
    )
    fig.update_xaxes(title_text="时间")
    fig.update_yaxes(title_text="短评数量", secondary_y=False)
    fig.update_yaxes(title_text="平均用户评分", secondary_y=True, range=[3.5, 5.0])
    return fig


def build_rating_boxplot_decade(df):
    """各年代评分箱线图。"""
    valid = df[df["release_year"].notna() & (df["release_year"] > 1900) & df["rating"].notna()].copy()
    valid["decade"] = (valid["release_year"] // 10 * 10).astype(int)
    valid = valid[valid["decade"].between(1930, 2030)]
    decade_order = sorted(valid["decade"].unique())

    fig = go.Figure()
    for decade in decade_order:
        subset = valid[valid["decade"] == decade]["rating"].dropna()
        if len(subset) > 0:
            fig.add_trace(go.Box(
                y=subset, name=str(decade),
                marker_color=px.colors.qualitative.Plotly[decade_order.index(decade) % 10],
                boxmean="sd"
            ))
    fig.update_layout(
        title="📦 各年代电影评分箱线图",
        yaxis_title="豆瓣评分",
        template="plotly_dark", height=420, showlegend=False,
        margin=dict(l=40, r=20, t=50, b=60),
        xaxis=dict(title="年代", tickangle=-30)
    )
    return fig


def build_genre_decade_heatmap(df):
    """类型-年代热力图。"""
    genre_counter = Counter()
    for gl in df["genre_list"]:
        for g in gl:
            if g:
                genre_counter[g] += 1
    top_genres = [g for g, _ in genre_counter.most_common(12)]

    valid = df[df["release_year"].notna() & (df["release_year"] > 1900)].copy()
    valid["decade"] = (valid["release_year"] // 10 * 10).astype(int)
    decades = sorted([d for d in valid["decade"].unique() if d >= 1940])

    matrix = pd.DataFrame(0, index=top_genres, columns=decades)
    for _, row in valid.iterrows():
        decade = int(row["decade"])
        for g in row["genre_list"]:
            if g in top_genres:
                if decade in matrix.columns:
                    matrix.at[g, decade] += 1

    fig = go.Figure(go.Heatmap(
        z=matrix.values, x=[str(d) for d in matrix.columns],
        y=matrix.index.tolist(), text=matrix.values,
        texttemplate="%{text}", colorscale="YlOrRd",
        hovertemplate="年代: %{x}<br>类型: %{y}<br>电影数: %{z}"
    ))
    fig.update_layout(
        title="🔢 类型 × 年代热力图",
        template="plotly_dark", height=420,
        margin=dict(l=40, r=20, t=50, b=40),
        xaxis=dict(title="年代", tickangle=-30),
        yaxis=dict(title="电影类型")
    )
    return fig


def build_top_reviewers_chart(comments_df):
    """影评人贡献分析。"""
    if len(comments_df) == 0 or "helpful" not in comments_df.columns:
        return go.Figure()
    user_stats = comments_df.groupby("user").agg(
        total_helpful=("helpful", "sum"),
        comment_count=("comment", "count"),
    ).reset_index()
    user_stats = user_stats[user_stats["total_helpful"] > 0].sort_values("total_helpful", ascending=False).head(20)

    fig = go.Figure(go.Bar(
        x=user_stats["total_helpful"], y=user_stats["user"], orientation="h",
        marker=dict(color=user_stats["total_helpful"], colorscale="YlOrRd", showscale=True, colorbar=dict(title="有用数")),
        hovertemplate="%{y}<br>总有用数: %{x:,d}<br>评论数: %{customdata}",
        customdata=user_stats["comment_count"],
        text=user_stats["total_helpful"].apply(lambda x: f"{x/1000:.0f}k"),
        textposition="outside"
    ))
    fig.update_layout(
        title="🏆 Top 20 最有影响力影评人",
        xaxis_title="总有用数",
        template="plotly_dark", height=420,
        margin=dict(l=40, r=20, t=50, b=40),
        yaxis=dict(autorange="reversed")
    )
    return fig


# ======== 组装完整仪表盘 ========

def build_dashboard(df, comments_df):
    """组装完整的仪表盘 HTML 页面。"""
    print("[构建] 生成交互图表...")

    cards_html = build_overview_cards(df, comments_df)

    # 第一个图表 embed plotly.js，其余不重复嵌入
    fig_hist = build_rating_histogram(df)
    fig_pie = build_sentiment_pie(comments_df)
    fig_scatter = build_rating_vs_comments(df)
    fig_trend = build_time_trend(df)
    fig_genre = build_genre_bar(df)
    fig_country = build_country_map(df)
    fig_world = build_world_choropleth(df)
    fig_violin = build_runtime_violin(df)
    fig_heatmap = build_correlation_heatmap(df)
    fig_radar = build_genre_radar(df)
    fig_director = build_director_bubble(df)
    fig_lang = build_language_chart(df)
    fig_comment_timeline = build_comment_timeline(comments_df)
    fig_boxplot = build_rating_boxplot_decade(df)
    fig_genre_decade = build_genre_decade_heatmap(df)
    fig_reviewers = build_top_reviewers_chart(comments_df)

    # 将图表转为 HTML 字符串 (第一个图表包含 plotly.js)
    hist_html  = fig_hist.to_html(full_html=False, include_plotlyjs=True)
    pie_html   = fig_pie.to_html(full_html=False, include_plotlyjs=False)
    scatter_html = fig_scatter.to_html(full_html=False, include_plotlyjs=False)
    trend_html = fig_trend.to_html(full_html=False, include_plotlyjs=False)
    genre_html = fig_genre.to_html(full_html=False, include_plotlyjs=False)
    country_html = fig_country.to_html(full_html=False, include_plotlyjs=False)
    world_html = fig_world.to_html(full_html=False, include_plotlyjs=False)
    violin_html = fig_violin.to_html(full_html=False, include_plotlyjs=False)
    heatmap_html = fig_heatmap.to_html(full_html=False, include_plotlyjs=False)
    radar_html = fig_radar.to_html(full_html=False, include_plotlyjs=False)
    director_html = fig_director.to_html(full_html=False, include_plotlyjs=False)
    lang_html = fig_lang.to_html(full_html=False, include_plotlyjs=False)
    comment_timeline_html = fig_comment_timeline.to_html(full_html=False, include_plotlyjs=False)
    boxplot_html = fig_boxplot.to_html(full_html=False, include_plotlyjs=False)
    genre_decade_html = fig_genre_decade.to_html(full_html=False, include_plotlyjs=False)
    reviewers_html = fig_reviewers.to_html(full_html=False, include_plotlyjs=False)

    # 表格数据
    table_df = df[["rank", "title_cn", "rating", "comment_count", "genres",
                    "director", "release_year", "runtime", "country", "language", "summary"]].copy()
    table_df.columns = ["排名", "电影名称", "评分", "评论数", "类型", "导演", "年份", "片长(分)", "国家", "语言", "简介"]
    table_df = table_df.sort_values("排名")
    table_data = table_df.to_dict(orient="records")

    # 筛选选项
    all_genres = sorted(set(g for gl in df["genre_list"] for g in gl if g))
    all_countries = sorted(set(c for cl in df["country_list"] for c in cl if c))
    all_decades = sorted([d for d in df["decade"].dropna().unique() if 1930 <= d <= 2030])

    genre_options = "\n".join(f'<option value="{g}">{g}</option>' for g in all_genres)
    country_options = "\n".join(f'<option value="{c}">{c}</option>' for c in all_countries)
    decade_options = "\n".join(f'<option value="{d}">{d}s</option>' for d in all_decades)

    # ── 读取内嵌依赖 ──
    with open(JQUERY_PATH, "r", encoding="utf-8") as f:
        jquery_js = f.read()
    with open(DATATABLES_JS_PATH, "r", encoding="utf-8") as f:
        datatables_js = f.read()
    with open(DATATABLES_CSS_PATH, "r", encoding="utf-8") as f:
        datatables_css = f.read()

    print("[构建] 生成 HTML...")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🎬 豆瓣电影 Top250 增强数据仪表盘</title>
<style id="datatables-css">{datatables_css}</style>
<style>
  :root {{
    --bg: #0f172a;
    --card-bg: #1e293b;
    --card-border: #334155;
    --text: #e2e8f0;
    --text-muted: #94a3b8;
    --accent: #636efa;
    --green: #00cc96;
    --orange: #ffa15a;
    --red: #ef553b;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
    min-height: 100vh;
    padding: 20px;
  }}
  .container {{ max-width: 1500px; margin: 0 auto; }}

  /* Header */
  .header {{
    text-align: center;
    padding: 30px 20px;
    margin-bottom: 20px;
    background: linear-gradient(135deg, #1e3a5f 0%, #1e293b 100%);
    border-radius: 16px;
    border: 1px solid var(--card-border);
  }}
  .header h1 {{
    font-size: 2.2em;
    background: linear-gradient(90deg, #636efa, #00cc96, #ffa15a);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 8px;
  }}
  .header p {{ color: var(--text-muted); font-size: 1.05em; }}

  /* Tabs */
  .tab-nav {{
    display: flex;
    gap: 4px;
    margin-bottom: 20px;
    overflow-x: auto;
    padding-bottom: 4px;
    border-bottom: 2px solid var(--card-border);
    flex-wrap: wrap;
  }}
  .tab-btn {{
    background: transparent;
    color: var(--text-muted);
    border: none;
    padding: 10px 20px;
    cursor: pointer;
    font-size: 0.95em;
    font-weight: 500;
    border-radius: 8px 8px 0 0;
    transition: all 0.2s;
    white-space: nowrap;
  }}
  .tab-btn:hover {{ color: var(--text); background: rgba(99,110,250,0.1); }}
  .tab-btn.active {{ color: var(--accent); background: rgba(99,110,250,0.15); border-bottom: 2px solid var(--accent); }}
  .tab-panel {{ display: none; }}
  .tab-panel.active {{ display: block; }}

  /* Filter Panel */
  .filter-panel {{
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 12px;
    padding: 16px 20px;
    margin-bottom: 20px;
    display: flex;
    gap: 16px;
    align-items: center;
    flex-wrap: wrap;
  }}
  .filter-panel label {{
    color: var(--text-muted);
    font-size: 0.9em;
    font-weight: 600;
    margin-right: 6px;
  }}
  .filter-panel select {{
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--card-border);
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 0.9em;
    min-width: 140px;
    cursor: pointer;
  }}
  .filter-panel select:focus {{
    outline: none;
    border-color: var(--accent);
  }}
  .filter-badge {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(99,110,250,0.15);
    color: var(--accent);
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.85em;
    font-weight: 500;
  }}
  .filter-badge .clear-btn {{
    cursor: pointer;
    font-weight: bold;
    font-size: 1.1em;
    line-height: 1;
  }}
  .filter-badge .clear-btn:hover {{ color: var(--red); }}

  /* Stats Cards */
  .stats-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 14px;
    margin-bottom: 24px;
  }}
  .stat-card {{
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 12px;
    padding: 18px 14px;
    text-align: center;
    transition: transform 0.2s, box-shadow 0.2s;
  }}
  .stat-card:hover {{
    transform: translateY(-3px);
    box-shadow: 0 8px 25px rgba(99, 110, 250, 0.15);
  }}
  .stat-icon {{ font-size: 1.8em; margin-bottom: 4px; }}
  .stat-number {{
    font-size: 1.8em;
    font-weight: 700;
    background: linear-gradient(135deg, #636efa, #00cc96);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }}
  .stat-label {{
    color: var(--text-muted);
    margin-top: 4px;
    font-size: 0.85em;
  }}

  /* Chart Grid */
  .chart-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(480px, 1fr));
    gap: 20px;
    margin-bottom: 24px;
  }}
  .chart-card {{
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 12px;
    padding: 16px;
    overflow: hidden;
    transition: box-shadow 0.2s;
  }}
  .chart-card:hover {{ box-shadow: 0 4px 20px rgba(0,0,0,0.3); }}
  .chart-card.full-width {{ grid-column: 1 / -1; }}

  .section-title {{
    color: var(--text);
    font-size: 1.3em;
    font-weight: 600;
    margin-bottom: 16px;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--card-border);
  }}

  /* Table */
  .table-section {{
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 24px;
    overflow-x: auto;
  }}

  /* DataTables dark */
  .dataTables_wrapper .dataTables_length,
  .dataTables_wrapper .dataTables_filter,
  .dataTables_wrapper .dataTables_info,
  .dataTables_wrapper .dataTables_paginate {{
    color: var(--text-muted) !important;
  }}
  .dataTables_wrapper input, .dataTables_wrapper select {{
    background: var(--bg) !important;
    color: var(--text) !important;
    border: 1px solid var(--card-border) !important;
    border-radius: 6px !important;
    padding: 6px 10px !important;
  }}
  table.dataTable {{
    color: var(--text) !important;
    border-collapse: collapse;
  }}
  table.dataTable thead th {{
    background: var(--bg) !important;
    color: var(--accent) !important;
    border-bottom: 2px solid var(--card-border) !important;
    padding: 10px 12px !important;
    font-weight: 600;
  }}
  table.dataTable tbody td {{
    border-bottom: 1px solid var(--card-border) !important;
    padding: 8px 12px !important;
    background-color: transparent !important;
  }}
  table.dataTable tbody tr {{
    background-color: var(--card-bg) !important;
  }}
  table.dataTable.stripe tbody tr.odd,
  table.dataTable.display tbody tr.odd {{
    background-color: rgba(30, 41, 59, 0.5) !important;
  }}
  table.dataTable.stripe tbody tr.even,
  table.dataTable.display tbody tr.even {{
    background-color: var(--card-bg) !important;
  }}
  table.dataTable tbody tr:hover {{
    background: rgba(99, 110, 250, 0.08) !important;
    cursor: pointer;
  }}
  /* 彻底覆盖 DataTables 内置的排序列和偶数列亮色 */
  table.dataTable tbody td.sorting_1,
  table.dataTable tbody td.sorting_2,
  table.dataTable tbody td.sorting_3 {{
    background-color: transparent !important;
  }}
  table.dataTable.stripe tbody tr.odd td.sorting_1,
  table.dataTable.display tbody tr.odd td.sorting_1 {{
    background-color: rgba(30, 41, 59, 0.3) !important;
  }}
  .rating-badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-weight: 600;
    font-size: 0.9em;
  }}
  .rating-high {{ background: rgba(0,204,150,0.2); color: #00cc96; }}
  .rating-mid {{ background: rgba(255,161,90,0.2); color: #ffa15a; }}
  .rating-low {{ background: rgba(239,85,59,0.2); color: #ef553b; }}

  /* Modal */
  .modal-overlay {{
    display: none;
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.7);
    z-index: 1000;
    justify-content: center;
    align-items: center;
  }}
  .modal-overlay.show {{ display: flex; }}
  .modal {{
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 16px;
    padding: 30px;
    max-width: 600px;
    width: 90%;
    max-height: 80vh;
    overflow-y: auto;
    position: relative;
  }}
  .modal-close {{
    position: absolute;
    top: 12px; right: 16px;
    background: none;
    border: none;
    color: var(--text-muted);
    font-size: 1.5em;
    cursor: pointer;
  }}
  .modal-close:hover {{ color: var(--red); }}
  .modal h2 {{ margin-bottom: 12px; font-size: 1.5em; }}
  .modal .detail-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin: 16px 0;
  }}
  .modal .detail-item {{ }}
  .modal .detail-label {{ color: var(--text-muted); font-size: 0.85em; }}
  .modal .detail-value {{ color: var(--text); font-size: 1em; font-weight: 500; }}
  .modal .detail-summary {{
    margin-top: 12px;
    color: var(--text-muted);
    line-height: 1.7;
    font-size: 0.95em;
  }}

  /* Footer */
  .footer {{
    text-align: center;
    padding: 20px;
    color: var(--text-muted);
    font-size: 0.85em;
  }}

  @media (max-width: 600px) {{
    .chart-grid {{ grid-template-columns: 1fr; }}
    .header h1 {{ font-size: 1.5em; }}
    .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .filter-panel {{ flex-direction: column; align-items: stretch; }}
    .modal .detail-grid {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>

<div class="container">

  <!-- Header -->
  <div class="header">
    <h1>🎬 豆瓣电影 Top250 增强数据仪表盘</h1>
    <p>基于 {len(df)} 部电影 · {len(comments_df):,d} 条短评 · 数据更新至 {datetime.now().strftime("%Y-%m-%d")}</p>
  </div>

  <!-- Tabs -->
  <div class="tab-nav">
    <button class="tab-btn active" onclick="switchTab('overview')">📊 概览</button>
    <button class="tab-btn" onclick="switchTab('distribution')">📈 分布分析</button>
    <button class="tab-btn" onclick="switchTab('geography')">🌍 地域分析</button>
    <button class="tab-btn" onclick="switchTab('people')">👤 人物分析</button>
    <button class="tab-btn" onclick="switchTab('table')">📋 数据表</button>
  </div>

  <!-- Filter Panel -->
  <div class="filter-panel" id="filterPanel">
    <div style="display:flex;align-items:center;gap:8px;">
      <label>🎭 类型:</label>
      <select id="filterGenre" onchange="applyFilters()">
        <option value="">全部类型</option>
        {genre_options}
      </select>
    </div>
    <div style="display:flex;align-items:center;gap:8px;">
      <label>🌍 国家:</label>
      <select id="filterCountry" onchange="applyFilters()">
        <option value="">全部国家</option>
        {country_options}
      </select>
    </div>
    <div style="display:flex;align-items:center;gap:8px;">
      <label>📅 年代:</label>
      <select id="filterDecade" onchange="applyFilters()">
        <option value="">全部年代</option>
        {decade_options}
      </select>
    </div>
    <div id="activeFilters" style="display:flex;gap:8px;flex-wrap:wrap;"></div>
    <button onclick="clearFilters()" style="background:var(--red);color:white;border:none;padding:8px 16px;border-radius:8px;cursor:pointer;font-size:0.9em;margin-left:auto;">✕ 清除筛选</button>
  </div>

  <!-- Overview Cards -->
  {cards_html}

  <!-- ===== TAB: 概览 ===== -->
  <div class="tab-panel active" id="tab-overview">
    <div class="chart-grid">
      <div class="chart-card">{hist_html}</div>
      <div class="chart-card">{pie_html}</div>
    </div>
    <div class="chart-grid">
      <div class="chart-card full-width">{scatter_html}</div>
    </div>
    <div class="chart-grid">
      <div class="chart-card full-width">{trend_html}</div>
    </div>
    <div class="chart-grid">
      <div class="chart-card full-width">{comment_timeline_html}</div>
    </div>
    <div class="chart-grid">
      <div class="chart-card">{heatmap_html}</div>
      <div class="chart-card">{genre_decade_html}</div>
    </div>
  </div>

  <!-- ===== TAB: 分布分析 ===== -->
  <div class="tab-panel" id="tab-distribution">
    <div class="chart-grid">
      <div class="chart-card">{genre_html}</div>
      <div class="chart-card">{radar_html}</div>
    </div>
    <div class="chart-grid">
      <div class="chart-card full-width">{boxplot_html}</div>
    </div>
    <div class="chart-grid">
      <div class="chart-card">{violin_html}</div>
      <div class="chart-card">{lang_html}</div>
    </div>
  </div>

  <!-- ===== TAB: 地域分析 ===== -->
  <div class="tab-panel" id="tab-geography">
    <div class="chart-grid">
      <div class="chart-card full-width">{world_html}</div>
    </div>
    <div class="chart-grid">
      <div class="chart-card full-width">{country_html}</div>
    </div>
  </div>

  <!-- ===== TAB: 人物分析 ===== -->
  <div class="tab-panel" id="tab-people">
    <div class="chart-grid">
      <div class="chart-card full-width">{director_html}</div>
    </div>
    <div class="chart-grid">
      <div class="chart-card full-width">{reviewers_html}</div>
    </div>
  </div>

  <!-- ===== TAB: 数据表 ===== -->
  <div class="tab-panel" id="tab-table">
    <div class="table-section">
      <h3 class="section-title">📋 电影数据表 (点击行查看详情)</h3>
      <table id="movieTable" class="display stripe" style="width:100%">
        <thead>
          <tr>
            <th>排名</th><th>电影名称</th><th>评分</th><th>评论数</th>
            <th>类型</th><th>导演</th><th>年份</th><th>片长(分)</th><th>国家</th>
          </tr>
        </thead>
        <tbody></tbody>
      </table>
    </div>
  </div>

  <!-- Movie Detail Modal -->
  <div class="modal-overlay" id="movieModal">
    <div class="modal">
      <button class="modal-close" onclick="closeModal()">✕</button>
      <h2 id="modalTitle"></h2>
      <div class="detail-grid" id="modalDetails"></div>
      <div class="detail-summary" id="modalSummary"></div>
    </div>
  </div>

  <!-- Footer -->
  <div class="footer">
    <p>Douban Top 250 Enhanced Data Dashboard · Generated by Python + Plotly · 数据来源: 豆瓣电影</p>
  </div>
</div>

<script id="jquery-js">{jquery_js}</script>
<script id="datatables-js">{datatables_js}</script>
<script>
const tableData = {json.dumps(table_data, ensure_ascii=False)};
let dataTable;

// ===== 标签页切换 =====
function switchTab(tabName) {{
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  const btn = document.querySelector(`.tab-btn[onclick="switchTab('${{tabName}}')"]`);
  const panel = document.getElementById(`tab-${{tabName}}`);
  if (btn) btn.classList.add('active');
  if (panel) {{
    panel.classList.add('active');
    // 关键：Plotly 图表在隐藏容器中渲染尺寸为0，切换后需要重绘
    setTimeout(() => {{
      const plotlyDivs = panel.querySelectorAll('.plotly-graph-div, .js-plotly-plot');
      plotlyDivs.forEach(div => {{
        if (div._fullLayout && Plotly) Plotly.Plots.resize(div);
      }});
      // DataTables 在隐藏标签中初始化后需要调整列宽
      if (tabName === 'table' && dataTable) {{
        dataTable.columns.adjust().draw();
      }}
    }}, 150);
  }}
}}

// ===== 筛选逻辑 =====
function getActiveFilters() {{
  return {{
    genre: document.getElementById('filterGenre').value,
    country: document.getElementById('filterCountry').value,
    decade: document.getElementById('filterDecade').value,
  }};
}}

function applyFilters() {{
  const f = getActiveFilters();
  // 更新筛选标签
  const badges = [];
  if (f.genre) badges.push(`<span class="filter-badge">🎭 ${{f.genre}} <span class="clear-btn" onclick="clearFilter('genre')">×</span></span>`);
  if (f.country) badges.push(`<span class="filter-badge">🌍 ${{f.country}} <span class="clear-btn" onclick="clearFilter('country')">×</span></span>`);
  if (f.decade) badges.push(`<span class="filter-badge">📅 ${{f.decade}}s <span class="clear-btn" onclick="clearFilter('decade')">×</span></span>`);
  document.getElementById('activeFilters').innerHTML = badges.join('');
  // 过滤表格
  if (dataTable) {{
    $.fn.dataTable.ext.search = [];
    if (f.genre || f.country || f.decade) {{
      $.fn.dataTable.ext.search.push(function(settings, rowData, dataIndex) {{
        const row = tableData[dataIndex];
        if (!row) return true;
        if (f.genre && !(row['类型'] || '').includes(f.genre)) return false;
        if (f.country && !(row['国家'] || '').includes(f.country)) return false;
        if (f.decade && row['年份']) {{
          const rowDecade = Math.floor(row['年份'] / 10) * 10;
          if (rowDecade != parseInt(f.decade)) return false;
        }}
        return true;
      }});
    }}
    dataTable.draw();
  }}
}}

function clearFilter(type) {{
  if (type === 'genre') document.getElementById('filterGenre').value = '';
  if (type === 'country') document.getElementById('filterCountry').value = '';
  if (type === 'decade') document.getElementById('filterDecade').value = '';
  applyFilters();
}}

function clearFilters() {{
  document.getElementById('filterGenre').value = '';
  document.getElementById('filterCountry').value = '';
  document.getElementById('filterDecade').value = '';
  applyFilters();
}}

// ===== 模态框 =====
function showMovieDetail(rowData) {{
  document.getElementById('modalTitle').textContent = rowData['电影名称'] + ' ★' + rowData['评分'];
  const details = [
    {{ label: '排名', value: '#' + rowData['排名'] }},
    {{ label: '评分', value: '★ ' + rowData['评分'] }},
    {{ label: '评论数', value: (rowData['评论数'] || 0).toLocaleString() }},
    {{ label: '类型', value: rowData['类型'] }},
    {{ label: '导演', value: rowData['导演'] }},
    {{ label: '年份', value: rowData['年份'] || '未知' }},
    {{ label: '片长', value: (rowData['片长(分)'] || 0) + ' 分钟' }},
    {{ label: '国家', value: rowData['国家'] }},
    {{ label: '语言', value: rowData['语言'] }},
  ];
  document.getElementById('modalDetails').innerHTML = details.map(d =>
    `<div class="detail-item"><div class="detail-label">${{d.label}}</div><div class="detail-value">${{d.value}}</div></div>`
  ).join('');
  document.getElementById('modalSummary').textContent = rowData['简介'] || '暂无简介';
  document.getElementById('movieModal').classList.add('show');
}}

function closeModal() {{
  document.getElementById('movieModal').classList.remove('show');
}}

document.getElementById('movieModal').addEventListener('click', function(e) {{
  if (e.target === this) closeModal();
}});

// ===== 初始化数据表 =====
$(document).ready(function() {{
  dataTable = $('#movieTable').DataTable({{
    data: tableData,
    columns: [
      {{ data: '排名' }},
      {{ data: '电影名称' }},
      {{
        data: '评分',
        render: function(d) {{
          let cls = d >= 9.2 ? 'rating-high' : (d >= 8.8 ? 'rating-mid' : 'rating-low');
          return `<span class="rating-badge ${{cls}}">★ ${{d}}</span>`;
        }}
      }},
      {{ data: '评论数', render: function(d) {{ return (d || 0).toLocaleString(); }} }},
      {{ data: '类型' }},
      {{ data: '导演' }},
      {{ data: '年份', render: function(d) {{ return d || '-'; }} }},
      {{ data: '片长(分)' }},
      {{ data: '国家' }}
    ],
    pageLength: 25,
    lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, "全部"]],
    language: {{
      search: "🔍 搜索:",
      lengthMenu: "每页显示 _MENU_ 条",
      info: "显示第 _START_ 至 _END_ 条，共 _TOTAL_ 条",
      infoEmpty: "无记录",
      infoFiltered: "(从 _MAX_ 条中筛选)",
      paginate: {{
        first: "首页", last: "末页", next: "下一页", previous: "上一页"
      }},
      zeroRecords: "未找到匹配的电影"
    }},
    order: [[0, 'asc']]
  }});

  // 行点击打开详情
  $('#movieTable tbody').on('click', 'tr', function() {{
    const row = dataTable.row(this).data();
    if (row) showMovieDetail(row);
  }});

  // 键盘快捷键
  document.addEventListener('keydown', function(e) {{
    if (e.key === 'Escape') closeModal();
  }});
}});
</script>

</body>
</html>"""

    output_path = os.path.join(OUTPUT_DIR, "dashboard.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"\n✅ 增强仪表盘已生成: {output_path} ({size_mb:.1f} MB)")
    return output_path


def main():
    print("=" * 60)
    print("  豆瓣电影 Top250 增强交互仪表盘生成器")
    print("=" * 60)

    df, comments_df = load_and_clean()
    output = build_dashboard(df, comments_df)
    print(f"\n用浏览器打开: {output}")


if __name__ == "__main__":
    main()

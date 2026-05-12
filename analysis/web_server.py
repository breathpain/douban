#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
豆瓣电影数据采集 - Web 集成服务
==============================
单文件 Flask Web 服务，整合三大功能模块到统一的 Web 界面：

  📊 数据仪表盘 — 16+ 交互式 Plotly 图表，类型/国家/年代联动筛选
  🕷️ 爬虫控制   — 启停爬虫、实时日志、参数配置（Top250 / 自定义URL / 导入）
  🗄️ 数据库管理 — MySQL 连接状态、表统计、备份导出

启动方式:
    python web_server.py                # 默认 http://localhost:5000
    python web_server.py --port 8080    # 自定义端口
    python web_server.py --host 0.0.0.0 # 允许局域网访问

依赖:
    pip install flask plotly pandas numpy
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import sys
import threading
import time
import traceback
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ── Flask ──────────────────────────────────────────────────────────────
try:
    from flask import Flask, Response, jsonify, request, send_from_directory
except ImportError:
    print("请安装 Flask: pip install flask")
    sys.exit(1)

# ── Plotly ─────────────────────────────────────────────────────────────
try:
    import plotly.express as px
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
except ImportError:
    print("请安装 plotly: pip install plotly")
    sys.exit(1)

# ── 路径 ───────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 图片目录
POSTER_IMAGES_DIR = PROJECT_ROOT / "data" / "crawler" / "images"
ANALYSIS_IMAGES_DIR = BASE_DIR / "output"

# 内嵌依赖路径
JQUERY_PATH = OUTPUT_DIR / "jquery.min.js"
DATATABLES_JS_PATH = OUTPUT_DIR / "datatables.min.js"
DATATABLES_CSS_PATH = OUTPUT_DIR / "datatables.min.css"

DATA_FILE = PROJECT_ROOT / "data" / "database" / "backup" / "douban_movies.json"

RATING_MAP = {"力荐": 5, "推荐": 4, "还行": 3, "较差": 2, "很差": 1, "": np.nan}

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

# ── Flask App ──────────────────────────────────────────────────────────
app = Flask(__name__)

# ── 爬虫状态 ───────────────────────────────────────────────────────────
_crawl_state: dict[str, Any] = {
    "running": False,
    "mode": "",
    "start_time": None,
    "items_collected": 0,
    "error": None,
}
_crawl_stop_event = threading.Event()
_log_queue: queue.Queue[str] = queue.Queue()
_crawl_thread: threading.Thread | None = None

# ── 缓存仪表盘数据 ─────────────────────────────────────────────────────
_dashboard_df: pd.DataFrame | None = None
_dashboard_comments_df: pd.DataFrame | None = None
_chart_html_cache: dict[str, str] = {}
_html_cache: str | None = None
_cache_timestamp: float = 0.0


# ========================================================================
#  数据加载与清洗
# ========================================================================

def load_and_clean():
    """加载并清洗数据。"""
    print("[加载] 读取数据...")
    if not DATA_FILE.exists():
        print(f"  ⚠ 数据文件不存在: {DATA_FILE}")
        return pd.DataFrame(), pd.DataFrame()

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
    if "comment" in comments_df.columns:
        comments_df["comment"] = comments_df["comment"].apply(
            lambda x: x.replace("\u00a0", " ").strip() if isinstance(x, str) else ""
        )
    comments_df["comment_time"] = pd.to_datetime(comments_df["comment_time"], errors="coerce")
    if "helpful" in comments_df.columns:
        comments_df["helpful"] = pd.to_numeric(comments_df["helpful"], errors="coerce").fillna(0).astype(int)

    print(f"  电影: {len(df)} 条, 短评: {len(comments_df)} 条")
    return df, comments_df


# ========================================================================
#  图表构建函数
# ========================================================================

def build_rating_histogram(df):
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
        template="plotly_dark", height=380, margin=dict(l=40, r=20, t=50, b=40), bargap=0.05
    )
    return fig


def build_sentiment_pie(comments_df):
    scores = comments_df["rating_score"].dropna()
    pos = (scores >= 4).sum()
    neu = (scores == 3).sum()
    neg = (scores <= 2).sum()
    total = len(scores)
    fig = go.Figure(go.Pie(
        labels=["正面 (力荐+推荐)", "中性 (还行)", "负面 (较差+很差)"],
        values=[pos, neu, neg], hole=0.55,
        marker_colors=["#00cc96", "#ffa15a", "#ef553b"],
        textinfo="percent+label", textfont_size=12,
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
    valid = df[(df["comment_count"] > 0) & df["rating"].notna()].copy()
    valid["log_comments"] = np.log10(valid["comment_count"])
    fig = px.scatter(
        valid, x="rating", y="log_comments", color="rating",
        size="comment_count", size_max=25,
        hover_name="title_cn", hover_data={"director": True, "release_year": True, "comment_count": True},
        color_continuous_scale="Viridis",
        title="📈 评分 vs 评论人数 (log₁₀ 坐标)",
        labels={"rating": "豆瓣评分", "log_comments": "log₁₀(评论人数)"},
        template="plotly_dark", height=450,
    )
    fig.update_layout(margin=dict(l=40, r=20, t=50, b=40))
    return fig


def build_time_trend(df):
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
        name="平均评分", mode="lines+markers", line=dict(color="#ef553b", width=2.5), marker=dict(size=6)
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
    genre_counter = Counter()
    for gl in df["genre_list"]:
        for g in gl:
            if g: genre_counter[g] += 1
    top = genre_counter.most_common(15)
    names, counts = [g for g, _ in top], [c for _, c in top]
    fig = go.Figure(go.Bar(
        x=counts, y=names, orientation="h",
        marker=dict(color=counts, colorscale="Bluered", showscale=True, colorbar=dict(title="数量")),
        text=counts, textposition="outside", hovertemplate="%{y}: %{x} 部电影"
    ))
    fig.update_layout(
        title="🎭 电影类型分布 Top 15", xaxis_title="电影数量",
        template="plotly_dark", height=420, margin=dict(l=40, r=60, t=50, b=40),
        yaxis=dict(autorange="reversed")
    )
    return fig


def build_country_map(df):
    country_counter = Counter()
    for cl in df["country_list"]:
        for c in cl: country_counter[c] += 1
    top = country_counter.most_common(15)
    names, counts = [c for c, _ in top], [cnt for _, cnt in top]
    fig = go.Figure(go.Bar(
        x=names, y=counts, marker=dict(color=counts, colorscale="Tealgrn"),
        text=counts, textposition="outside", hovertemplate="%{x}: %{y} 部电影"
    ))
    fig.update_layout(
        title="🌍 电影国别/地区分布 Top 15", xaxis_title="国家/地区", yaxis_title="电影数量",
        template="plotly_dark", height=380, margin=dict(l=40, r=20, t=50, b=80), xaxis_tickangle=-30
    )
    return fig


def build_world_choropleth(df):
    country_counter = Counter()
    for cl in df["country_list"]:
        for c in cl: country_counter[c] += 1
    iso_data = []
    for cname, cnt in country_counter.items():
        iso = COUNTRY_ISO.get(cname)
        if iso: iso_data.append({"country": iso, "count": cnt, "name": cname})
    map_df = pd.DataFrame(iso_data)
    if map_df.empty: return go.Figure()
    fig = px.choropleth(
        map_df, locations="country", locationmode="ISO-3",
        color="count", hover_name="name", hover_data={"count": True, "country": False},
        color_continuous_scale="Blues", title="🗺️ 全球电影数量分布",
        labels={"count": "电影数量"}, template="plotly_dark", height=450,
    )
    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20))
    return fig


def build_runtime_violin(df):
    valid = df[df["runtime"] > 0].copy()
    decade_order = sorted([d for d in valid["decade"].dropna().unique() if 1940 <= d <= 2030])
    fig = go.Figure()
    for decade in decade_order:
        subset = valid[valid["decade"] == decade]["runtime"]
        if len(subset) > 0:
            fig.add_trace(go.Violin(y=subset, name=str(decade), box_visible=True, meanline_visible=True, line_color="white"))
    fig.update_layout(
        title="🎻 各年代影片时长分布 (小提琴图)", yaxis_title="片长 (分钟)",
        template="plotly_dark", height=420, showlegend=False,
        margin=dict(l=40, r=20, t=50, b=60), xaxis=dict(title="年代", tickangle=-30)
    )
    return fig


def build_correlation_heatmap(df):
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
    genre_counter = Counter()
    for gl in df["genre_list"]:
        for g in gl:
            if g: genre_counter[g] += 1
    top_genres = [g for g, _ in genre_counter.most_common(10)]
    genre_ratings = defaultdict(list)
    for gl, r in zip(df["genre_list"], df["rating"]):
        for g in gl:
            if g in top_genres and pd.notna(r): genre_ratings[g].append(r)
    values = [np.mean(genre_ratings[g]) for g in top_genres]
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values, theta=top_genres, fill="toself", name="平均评分",
        marker=dict(color="#636efa", size=8), line=dict(color="#636efa", width=2.5),
        hovertemplate="%{theta}: ★%{r:.2f}<extra></extra>"
    ))
    overall = df["rating"].mean()
    fig.add_trace(go.Scatterpolar(
        r=[overall] * len(top_genres), theta=top_genres,
        name=f"整体均值 ★{overall:.2f}", mode="lines",
        line=dict(color="#ef553b", width=1.5, dash="dash"),
    ))
    fig.update_layout(
        title="🎯 主要类型平均评分雷达图", template="plotly_dark", height=450,
        polar=dict(radialaxis=dict(visible=True, range=[8.2, 9.5], tickfont_size=10),
                   angularaxis=dict(tickfont_size=11)),
        margin=dict(l=40, r=40, t=60, b=40), showlegend=True, legend=dict(x=0.85, y=0.05)
    )
    return fig


def build_director_bubble(df):
    director_info = defaultdict(list)
    for dl, r, cc in zip(df["director_list"], df["rating"], df["comment_count"]):
        for d in dl:
            if d and d != "未知" and pd.notna(r):
                director_info[d].append({"rating": r, "comments": cc})
    dir_data = []
    for d, items in director_info.items():
        if len(items) >= 2:
            dir_data.append({"director": d, "count": len(items),
                             "avg_rating": np.mean([it["rating"] for it in items]),
                             "total_comments": sum([it["comments"] for it in items])})
    dir_df = pd.DataFrame(dir_data).sort_values("count", ascending=False).head(30)
    fig = px.scatter(
        dir_df, x="avg_rating", y="count", size="total_comments", size_max=45,
        color="avg_rating", color_continuous_scale="RdYlGn",
        hover_name="director",
        hover_data={"count": True, "avg_rating": ":.2f", "total_comments": True},
        title="🎬 导演作品数 vs 平均评分 (气泡大小=总评论数)",
        labels={"avg_rating": "平均评分", "count": "作品数量", "total_comments": "总评论数"},
        template="plotly_dark", height=480, text="director"
    )
    fig.update_traces(textposition="top center", textfont_size=9)
    fig.update_layout(margin=dict(l=40, r=20, t=50, b=40))
    return fig


def build_language_chart(df):
    lang_counter = Counter()
    for ll in df["language_list"]:
        for l in ll: lang_counter[l] += 1
    top = lang_counter.most_common(8)
    other = sum(cnt for _, cnt in lang_counter.most_common()[8:])
    labels = [l for l, _ in top]
    values = [cnt for _, cnt in top]
    if other > 0:
        labels.append("其他"); values.append(other)
    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.5,
        textinfo="percent+label", textfont_size=12,
        marker=dict(colors=px.colors.qualitative.Set3[:len(labels)]),
        hovertemplate="%{label}<br>%{value} 部电影<br>%{percent}"
    ))
    fig.update_layout(
        title="🗣️ 电影语言分布", template="plotly_dark",
        height=400, margin=dict(l=20, r=20, t=50, b=20)
    )
    return fig


def build_comment_timeline(comments_df):
    valid = comments_df[comments_df["comment_time"].notna()].copy()
    if len(valid) == 0: return go.Figure()
    valid["month"] = valid["comment_time"].dt.to_period("M").dt.to_timestamp()
    monthly = valid.groupby("month").agg(count=("comment", "count"), avg_score=("rating_score", "mean")).reset_index()
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
        title="📝 短评月度趋势", template="plotly_dark",
        height=380, hovermode="x unified", margin=dict(l=40, r=40, t=50, b=40),
    )
    fig.update_xaxes(title_text="时间")
    fig.update_yaxes(title_text="短评数量", secondary_y=False)
    fig.update_yaxes(title_text="平均用户评分", secondary_y=True, range=[3.5, 5.0])
    return fig


def build_rating_boxplot_decade(df):
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
                marker_color=px.colors.qualitative.Plotly[decade_order.index(decade) % 10], boxmean="sd"
            ))
    fig.update_layout(
        title="📦 各年代电影评分箱线图", yaxis_title="豆瓣评分",
        template="plotly_dark", height=420, showlegend=False,
        margin=dict(l=40, r=20, t=50, b=60), xaxis=dict(title="年代", tickangle=-30)
    )
    return fig


def build_genre_decade_heatmap(df):
    genre_counter = Counter()
    for gl in df["genre_list"]:
        for g in gl:
            if g: genre_counter[g] += 1
    top_genres = [g for g, _ in genre_counter.most_common(12)]
    valid = df[df["release_year"].notna() & (df["release_year"] > 1900)].copy()
    valid["decade"] = (valid["release_year"] // 10 * 10).astype(int)
    decades = sorted([d for d in valid["decade"].unique() if d >= 1940])
    matrix = pd.DataFrame(0, index=top_genres, columns=decades)
    for _, row in valid.iterrows():
        decade = int(row["decade"])
        for g in row["genre_list"]:
            if g in top_genres and decade in matrix.columns:
                matrix.at[g, decade] += 1
    fig = go.Figure(go.Heatmap(
        z=matrix.values, x=[str(d) for d in matrix.columns],
        y=matrix.index.tolist(), text=matrix.values,
        texttemplate="%{text}", colorscale="YlOrRd",
        hovertemplate="年代: %{x}<br>类型: %{y}<br>电影数: %{z}"
    ))
    fig.update_layout(
        title="🔢 类型 × 年代热力图", template="plotly_dark", height=420,
        margin=dict(l=40, r=20, t=50, b=40),
        xaxis=dict(title="年代", tickangle=-30), yaxis=dict(title="电影类型")
    )
    return fig


def build_top_reviewers_chart(comments_df):
    if len(comments_df) == 0 or "helpful" not in comments_df.columns: return go.Figure()
    user_stats = comments_df.groupby("user").agg(
        total_helpful=("helpful", "sum"), comment_count=("comment", "count"),
    ).reset_index()
    user_stats = user_stats[user_stats["total_helpful"] > 0].sort_values("total_helpful", ascending=False).head(20)
    fig = go.Figure(go.Bar(
        x=user_stats["total_helpful"], y=user_stats["user"], orientation="h",
        marker=dict(color=user_stats["total_helpful"], colorscale="YlOrRd", showscale=True, colorbar=dict(title="有用数")),
        hovertemplate="%{y}<br>总有用数: %{x:,d}<br>评论数: %{customdata}",
        customdata=user_stats["comment_count"],
        text=user_stats["total_helpful"].apply(lambda x: f"{x/1000:.0f}k"), textposition="outside"
    ))
    fig.update_layout(
        title="🏆 Top 20 最有影响力影评人", xaxis_title="总有用数",
        template="plotly_dark", height=420, margin=dict(l=40, r=20, t=50, b=40),
        yaxis=dict(autorange="reversed")
    )
    return fig


# ========================================================================
#  爬虫后台执行
# ========================================================================

def _emit_log(msg: str) -> None:
    """向日志队列写入一条消息。"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    _log_queue.put(f"[{timestamp}] {msg}")


def _run_crawl_in_thread(cfg: dict[str, Any]) -> None:
    """在线程中执行爬虫任务。"""
    global _crawl_state
    try:
        from requests_douban.config import CrawlConfig
        from requests_douban.crawler import DoubanCrawler, expand_paginated_urls, save_items
        from requests_douban.cleaner import clean_items

        output_dir = Path(cfg["output_dir"])
        image_dir = output_dir / "images"

        proxy_pool = _build_proxy_pool(cfg["proxies"])
        detail_workers = 4 if cfg["fast_mode"] else 1
        image_workers = 6 if cfg["fast_mode"] else 1
        delay_min = 0.5 if cfg["fast_mode"] else cfg["delay_min"]
        delay_max = 1.5 if cfg["fast_mode"] else cfg["delay_max"]

        config = CrawlConfig(
            output_dir=output_dir, image_dir=image_dir,
            max_pages=cfg["max_pages"], page_param=cfg["page_param"],
            page_size=max(1, cfg["page_size"]),
            proxies=proxy_pool[0] if len(proxy_pool) == 1 else None,
            proxy_pool=proxy_pool if len(proxy_pool) > 1 else (),
            cookie=cfg["cookie"],
            use_selenium=cfg["use_selenium"],
            selenium_headless=not cfg["show_browser"],
            chrome_driver_path=cfg["driver_path"],
            download_images=cfg["download_images"],
            crawl_details=cfg["crawl_details"],
            comment_limit=max(0, cfg["comment_limit"]),
            detail_workers=detail_workers, image_workers=image_workers,
            delay_min=delay_min, delay_max=delay_max,
        )

        _emit_log(f"📂 输出目录：{output_dir}")
        _emit_log(f"📄 采集页数：{cfg['max_pages']}")
        _emit_log(f"💬 短评条数：{cfg['comment_limit']}")
        if cfg["cookie"]: _emit_log("🔑 已注入 Cookie")
        if cfg["use_selenium"] or cfg["driver_path"]: _emit_log("🌐 Selenium 兜底已启用")
        if cfg["download_images"]: _emit_log("🖼️ 将下载封面图片")
        if cfg["save_mysql"]: _emit_log(f"🗄️ 将保存到 MySQL：{cfg['mysql_host']}:{cfg['mysql_port']}/{cfg['mysql_database']}")

        crawler = DoubanCrawler(config)
        _emit_log("🔄 正在采集数据...")

        if cfg["mode"] == "urls":
            if not cfg["urls"]:
                raise ValueError("自定义 URL 模式下必须提供网址")
            items = crawler.crawl_urls(expand_paginated_urls(cfg["urls"], config))
        else:
            items = crawler.crawl_movie_top250()

        if _crawl_stop_event.is_set():
            _emit_log("⏹ 爬虫已停止")
            return

        if not items:
            _emit_log("⚠️ 未采集到任何数据。")
            return

        _crawl_state["items_collected"] = len(items)
        _emit_log(f"✅ 采集到 {len(items)} 条数据，正在清洗...")
        clean_items(items)

        json_path, csv_path = save_items(items, config.output_dir)
        _emit_log(f"📄 JSON 已保存：{json_path}")
        _emit_log(f"📄 CSV 已保存：{csv_path}")

        if cfg["save_mysql"] and items:
            _save_to_mysql_from_crawl(items, cfg)

        _emit_log("✅ 任务完成！")
        _crawl_state["error"] = None

    except Exception as exc:
        _emit_log(f"❌ 出错：{exc}")
        traceback.print_exc()
        _crawl_state["error"] = str(exc)
    finally:
        _crawl_state["running"] = False
        _emit_log("__DONE__")


def _save_to_mysql_from_crawl(items: list, cfg: dict[str, Any]) -> None:
    """爬虫后写入 MySQL。"""
    try:
        from database_service import save_to_mysql
        backup_dir = str(_resolve_path(cfg["mysql_backup_dir"]))
        _emit_log("🗄️ 正在写入 MySQL...")
        inserted = save_to_mysql(
            [item.to_dict() for item in items],
            recreate=(cfg["mode"] in ("import", "top250")),
            host=cfg["mysql_host"], port=cfg["mysql_port"],
            user=cfg["mysql_user"], password=cfg["mysql_password"],
            database=cfg["mysql_database"], backup_dir=backup_dir,
        )
        _emit_log(f"✅ MySQL 写入 {inserted} 条记录")
        _emit_log(f"📂 备份已导出到 {backup_dir}")
    except Exception as exc:
        _emit_log(f"❌ MySQL 写入失败：{exc}")


def _resolve_path(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _build_proxy_pool(proxy_urls: list[str]) -> tuple:
    proxies = []
    for u in proxy_urls:
        u = u.strip()
        if u: proxies.append({"http": u, "https": u})
    return tuple(proxies)


# ========================================================================
#  Flask Routes - API
# ========================================================================

@app.route("/api/crawl/start", methods=["POST"])
def api_crawl_start():
    """启动爬虫任务。"""
    global _crawl_state, _crawl_stop_event, _crawl_thread

    if _crawl_state["running"]:
        return jsonify({"ok": False, "error": "爬虫已在运行中"}), 409

    try:
        data = request.get_json() or {}
    except Exception:
        return jsonify({"ok": False, "error": "无效的 JSON 数据"}), 400

    _crawl_stop_event.clear()
    _crawl_state = {
        "running": True, "mode": data.get("mode", "top250"),
        "start_time": datetime.now().isoformat(), "items_collected": 0, "error": None,
    }

    cfg = {
        "mode": data.get("mode", "top250"),
        "urls": data.get("urls", []),
        "max_pages": data.get("max_pages", 1),
        "page_param": data.get("page_param", "start"),
        "page_size": data.get("page_size", 25),
        "comment_limit": data.get("comment_limit", 20),
        "download_images": data.get("download_images", True),
        "crawl_details": data.get("crawl_details", True),
        "fast_mode": data.get("fast_mode", False),
        "cookie": data.get("cookie") or None,
        "delay_min": data.get("delay_min", 1.2),
        "delay_max": data.get("delay_max", 3.5),
        "use_selenium": data.get("use_selenium", False),
        "show_browser": data.get("show_browser", False),
        "driver_path": data.get("driver_path") or None,
        "proxies": data.get("proxies", []),
        "output_dir": data.get("output_dir", "data/crawler"),
        "save_mysql": data.get("save_mysql", False),
        "mysql_host": data.get("mysql_host", "localhost"),
        "mysql_port": data.get("mysql_port", 3306),
        "mysql_user": data.get("mysql_user", "root"),
        "mysql_password": data.get("mysql_password", "123456"),
        "mysql_database": data.get("mysql_database", "douban"),
        "mysql_backup_dir": data.get("mysql_backup_dir", "data/database/backup")
    }

    _crawl_thread = threading.Thread(target=_run_crawl_in_thread, args=(cfg,), daemon=True)
    _crawl_thread.start()

    return jsonify({"ok": True, "message": "爬虫已启动"})


@app.route("/api/crawl/stop", methods=["POST"])
def api_crawl_stop():
    """停止爬虫任务。"""
    if not _crawl_state["running"]:
        return jsonify({"ok": False, "error": "爬虫未在运行"}), 409
    _crawl_stop_event.set()
    _emit_log("⏹ 用户请求停止...")
    return jsonify({"ok": True, "message": "停止信号已发送"})


@app.route("/api/crawl/status")
def api_crawl_status():
    """获取爬虫状态。"""
    return jsonify(_crawl_state)


@app.route("/api/crawl/logs")
def api_crawl_logs():
    """SSE 端点 - 推送实时日志。"""
    def generate():
        while True:
            try:
                msg = _log_queue.get(timeout=30)
                yield f"data: {json.dumps({'msg': msg})}\n\n"
                if msg == "__DONE__":
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'msg': ''})}\n\n"
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/db/status")
def api_db_status():
    """获取数据库状态。"""
    try:
        from database_service.config import MySQLConfig
        from database_service.database import get_dict_connection

        cfg = MySQLConfig()
        conn = get_dict_connection(cfg)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS cnt FROM movies")
                movie_count = cur.fetchone()["cnt"]
                cur.execute("SELECT COUNT(*) AS cnt FROM comments")
                comment_count = cur.fetchone()["cnt"]
                # 最近更新时间
                cur.execute("SELECT MAX(created_at) AS last_update FROM movies")
                last_update = cur.fetchone()["last_update"]
                if last_update and hasattr(last_update, "isoformat"):
                    last_update = last_update.isoformat()
        finally:
            conn.close()

        return jsonify({
            "ok": True,
            "connected": True,
            "movie_count": movie_count,
            "comment_count": comment_count,
            "last_update": str(last_update) if last_update else None,
            "host": cfg.host,
            "database": cfg.database,
        })
    except Exception as exc:
        return jsonify({"ok": False, "connected": False, "error": str(exc)})


@app.route("/api/db/export", methods=["POST"])
def api_db_export():
    """导出数据库备份。"""
    try:
        from database_service.config import MySQLConfig
        from database_service.exporter import export_backup

        cfg = MySQLConfig()
        json_path, movies_csv, comments_csv = export_backup(cfg)
        return jsonify({
            "ok": True,
            "json": str(json_path),
            "movies_csv": str(movies_csv),
            "comments_csv": str(comments_csv),
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/db/reload-dashboard", methods=["POST"])
def api_reload_dashboard():
    """重新加载仪表盘数据（爬虫完成后调用）。"""
    global _dashboard_df, _dashboard_comments_df, _chart_html_cache, _html_cache, _cache_timestamp
    _dashboard_df, _dashboard_comments_df = None, None
    _chart_html_cache = {}
    _html_cache = None
    _cache_timestamp = 0.0
    return jsonify({"ok": True, "message": "缓存已清除，下次访问将重新加载"})


# ── 图片服务路由 ───────────────────────────────────────────────────────


@app.route("/images/poster/<path:filename>")
def serve_poster_image(filename):
    """提供电影海报图片。"""
    return send_from_directory(str(POSTER_IMAGES_DIR), filename)


@app.route("/images/analysis/<path:filename>")
def serve_analysis_image(filename):
    """提供分析输出图片。"""
    return send_from_directory(str(ANALYSIS_IMAGES_DIR), filename)


# ========================================================================
#  HTML 构建
# ========================================================================

def _get_dashboard_data():
    """获取/缓存仪表盘数据。"""
    global _dashboard_df, _dashboard_comments_df, _cache_timestamp
    now = time.time()
    if _dashboard_df is None or (now - _cache_timestamp > 300):  # 5分钟缓存
        _dashboard_df, _dashboard_comments_df = load_and_clean()
        _cache_timestamp = now
    return _dashboard_df, _dashboard_comments_df


def _get_chart_html(chart_name: str, df, comments_df) -> str:
    """获取/缓存单个图表的 HTML。"""
    global _chart_html_cache
    if chart_name in _chart_html_cache:
        return _chart_html_cache[chart_name]

    builders = {
        "hist": build_rating_histogram,
        "pie": build_sentiment_pie,
        "scatter": build_rating_vs_comments,
        "trend": build_time_trend,
        "genre": build_genre_bar,
        "country": build_country_map,
        "world": build_world_choropleth,
        "violin": build_runtime_violin,
        "heatmap": build_correlation_heatmap,
        "radar": build_genre_radar,
        "director": build_director_bubble,
        "lang": build_language_chart,
        "comment_timeline": build_comment_timeline,
        "boxplot": build_rating_boxplot_decade,
        "genre_decade": build_genre_decade_heatmap,
        "reviewers": build_top_reviewers_chart,
    }

    if chart_name not in builders:
        return ""

    args = (df,) if chart_name != "pie" and chart_name != "comment_timeline" and chart_name != "reviewers" else (comments_df,)
    if chart_name == "pie" or chart_name == "comment_timeline" or chart_name == "reviewers":
        args = (comments_df,)

    fig = builders[chart_name](*args)
    include_js = (chart_name == "hist")
    html = fig.to_html(full_html=False, include_plotlyjs=include_js)
    _chart_html_cache[chart_name] = html
    return html


def build_html() -> str:
    """构建完整的仪表盘 HTML。"""
    global _html_cache
    if _html_cache is not None:
        return _html_cache

    df, comments_df = _get_dashboard_data()
    if len(df) == 0:
        _html_cache = "<html><body><h1>暂无数据，请先运行爬虫采集数据</h1></body></html>"
        return _html_cache

    print("[构建] 生成交互图表 HTML...")

    charts = [
        "hist", "pie", "scatter", "trend", "genre", "country", "world",
        "violin", "heatmap", "radar", "director", "lang",
        "comment_timeline", "boxplot", "genre_decade", "reviewers",
    ]
    chart_html = {}
    for name in charts:
        chart_html[name] = _get_chart_html(name, df, comments_df)

    # 概览卡片
    total = len(df)
    avg_rating = df["rating"].mean()
    total_comments = df["comment_count"].sum()
    pos_pct = (comments_df["rating_score"].dropna() >= 4).mean() * 100 if len(comments_df) > 0 else 0
    avg_runtime = df[df["runtime"] > 0]["runtime"].mean()
    country_set = set()
    for cl in df["country_list"]:
        for c in cl: country_set.add(c)
    imdb_count = df["imdb"].apply(lambda x: 1 if x and str(x).startswith("tt") else 0).sum()
    genre_set = set()
    for gl in df["genre_list"]:
        for g in gl: genre_set.add(g)

    cards_html = f"""
    <div class="stats-grid">
        <div class="stat-card"><div class="stat-icon">🎬</div><div class="stat-number">{total}</div><div class="stat-label">电影总数</div></div>
        <div class="stat-card"><div class="stat-icon">⭐</div><div class="stat-number">{avg_rating:.1f}</div><div class="stat-label">平均评分</div></div>
        <div class="stat-card"><div class="stat-icon">💬</div><div class="stat-number">{total_comments/1e6:.1f}M</div><div class="stat-label">总评论数</div></div>
        <div class="stat-card"><div class="stat-icon">👍</div><div class="stat-number">{pos_pct:.1f}%</div><div class="stat-label">好评率</div></div>
        <div class="stat-card"><div class="stat-icon">⏱️</div><div class="stat-number">{avg_runtime:.0f}分</div><div class="stat-label">平均片长</div></div>
        <div class="stat-card"><div class="stat-icon">🌍</div><div class="stat-number">{len(country_set)}</div><div class="stat-label">覆盖国家/地区</div></div>
        <div class="stat-card"><div class="stat-icon">🏷️</div><div class="stat-number">{len(genre_set)}</div><div class="stat-label">电影类型</div></div>
        <div class="stat-card"><div class="stat-icon">🎯</div><div class="stat-number">{imdb_count}</div><div class="stat-label">IMDb收录</div></div>
    </div>"""

    # 构建电影标题 → 海报文件名映射
    poster_map = {}
    if POSTER_IMAGES_DIR.exists():
        image_files = [f.name for f in POSTER_IMAGES_DIR.iterdir() if f.is_file() and f.suffix.lower() in (".webp", ".jpg", ".jpeg", ".png")]
        for _, row in df.iterrows():
            title = str(row.get("title_cn", "") or row.get("title", "")).strip()
            if not title:
                continue
            for fname in image_files:
                if fname.startswith(title):
                    poster_map[title] = fname
                    break

    # 表格数据
    table_df = df[["rank", "title_cn", "rating", "comment_count", "genres",
                    "director", "release_year", "runtime", "country", "language", "summary"]].copy()
    table_df.columns = ["排名", "电影名称", "评分", "评论数", "类型", "导演", "年份", "片长(分)", "国家", "语言", "简介"]
    table_df["海报文件"] = table_df["电影名称"].apply(lambda t: poster_map.get(t, ""))
    table_df = table_df.sort_values("排名")
    table_data = table_df.to_dict(orient="records")

    # 筛选选项
    all_genres = sorted(set(g for gl in df["genre_list"] for g in gl if g))
    all_countries = sorted(set(c for cl in df["country_list"] for c in cl if c))
    all_decades = sorted([d for d in df["decade"].dropna().unique() if 1930 <= d <= 2030])
    genre_options = "\n".join(f'<option value="{g}">{g}</option>' for g in all_genres)
    country_options = "\n".join(f'<option value="{c}">{c}</option>' for c in all_countries)
    decade_options = "\n".join(f'<option value="{d}">{d}s</option>' for d in all_decades)

    # 分析输出图片列表
    analysis_images = []
    if ANALYSIS_IMAGES_DIR.exists():
        for f in sorted(ANALYSIS_IMAGES_DIR.iterdir()):
            if f.is_file() and f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif") and f.stem not in ("jquery.min", "datatables.min"):
                analysis_images.append({
                    "name": f.name,
                    "stem": f.stem,
                })
    analysis_gallery_html = ""
    if analysis_images:
        cards = []
        for img in analysis_images:
            label = img["stem"].replace("_", " ").replace("-", " ")
            cards.append(f'''<div class="gallery-item" onclick="openImageViewer('/images/analysis/{img["name"]}', '{label}')">
                <img src="/images/analysis/{img["name"]}" alt="{label}" loading="lazy">
                <div class="gallery-caption">{label}</div>
            </div>''')
        analysis_gallery_html = f'<div class="gallery-grid">{"".join(cards)}</div>'
    else:
        analysis_gallery_html = '<p style="color:var(--text-muted);text-align:center;padding:40px;">暂无分析图片，请先运行分析脚本生成图表。</p>'

    # 内嵌依赖
    jquery_js = ""
    datatables_js = ""
    datatables_css = ""
    if JQUERY_PATH.exists():
        with open(JQUERY_PATH, "r", encoding="utf-8") as f:
            jquery_js = f.read()
    if DATATABLES_JS_PATH.exists():
        with open(DATATABLES_JS_PATH, "r", encoding="utf-8") as f:
            datatables_js = f.read()
    if DATATABLES_CSS_PATH.exists():
        with open(DATATABLES_CSS_PATH, "r", encoding="utf-8") as f:
            datatables_css = f.read()

    print("[构建] 生成完整 HTML...")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🎬 豆瓣电影数据采集与管理平台</title>
<style id="datatables-css">{datatables_css}</style>
<style>
  :root {{
    --bg: #0f172a; --card-bg: #1e293b; --card-border: #334155;
    --text: #e2e8f0; --text-muted: #94a3b8; --accent: #636efa;
    --green: #00cc96; --orange: #ffa15a; --red: #ef553b;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
    min-height: 100vh; padding: 20px;
  }}
  .container {{ max-width: 1500px; margin: 0 auto; }}

  .header {{
    text-align: center; padding: 30px 20px; margin-bottom: 20px;
    background: linear-gradient(135deg, #1e3a5f 0%, #1e293b 100%);
    border-radius: 16px; border: 1px solid var(--card-border);
  }}
  .header h1 {{
    font-size: 2.2em;
    background: linear-gradient(90deg, #636efa, #00cc96, #ffa15a);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
    margin-bottom: 8px;
  }}
  .header p {{ color: var(--text-muted); font-size: 1.05em; }}

  .tab-nav {{
    display: flex; gap: 4px; margin-bottom: 20px; overflow-x: auto;
    padding-bottom: 4px; border-bottom: 2px solid var(--card-border); flex-wrap: wrap;
  }}
  .tab-btn {{
    background: transparent; color: var(--text-muted); border: none;
    padding: 10px 20px; cursor: pointer; font-size: 0.95em; font-weight: 500;
    border-radius: 8px 8px 0 0; transition: all 0.2s; white-space: nowrap;
  }}
  .tab-btn:hover {{ color: var(--text); background: rgba(99,110,250,0.1); }}
  .tab-btn.active {{ color: var(--accent); background: rgba(99,110,250,0.15); border-bottom: 2px solid var(--accent); }}
  .tab-panel {{ display: none; }}
  .tab-panel.active {{ display: block; }}

  .filter-panel {{
    background: var(--card-bg); border: 1px solid var(--card-border);
    border-radius: 12px; padding: 16px 20px; margin-bottom: 20px;
    display: flex; gap: 16px; align-items: center; flex-wrap: wrap;
  }}
  .filter-panel label {{ color: var(--text-muted); font-size: 0.9em; font-weight: 600; margin-right: 6px; }}
  .filter-panel select {{
    background: var(--bg); color: var(--text); border: 1px solid var(--card-border);
    border-radius: 8px; padding: 8px 12px; font-size: 0.9em; min-width: 140px; cursor: pointer;
  }}
  .filter-panel select:focus {{ outline: none; border-color: var(--accent); }}
  .filter-badge {{
    display: inline-flex; align-items: center; gap: 6px;
    background: rgba(99,110,250,0.15); color: var(--accent);
    padding: 4px 12px; border-radius: 20px; font-size: 0.85em; font-weight: 500;
  }}

  .stats-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 14px; margin-bottom: 24px;
  }}
  .stat-card {{
    background: var(--card-bg); border: 1px solid var(--card-border);
    border-radius: 12px; padding: 18px 14px; text-align: center;
    transition: transform 0.2s, box-shadow 0.2s;
  }}
  .stat-card:hover {{ transform: translateY(-3px); box-shadow: 0 8px 25px rgba(99,110,250,0.15); }}
  .stat-icon {{ font-size: 1.8em; margin-bottom: 4px; }}
  .stat-number {{
    font-size: 1.8em; font-weight: 700;
    background: linear-gradient(135deg, #636efa, #00cc96);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
  }}
  .stat-label {{ color: var(--text-muted); margin-top: 4px; font-size: 0.85em; }}

  .chart-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(480px, 1fr));
    gap: 20px; margin-bottom: 24px;
  }}
  .chart-card {{
    background: var(--card-bg); border: 1px solid var(--card-border);
    border-radius: 12px; padding: 16px; overflow: hidden; transition: box-shadow 0.2s;
  }}
  .chart-card:hover {{ box-shadow: 0 4px 20px rgba(0,0,0,0.3); }}
  .chart-card.full-width {{ grid-column: 1 / -1; }}

  .section-title {{
    color: var(--text); font-size: 1.3em; font-weight: 600;
    margin-bottom: 16px; padding-bottom: 10px; border-bottom: 1px solid var(--card-border);
  }}

  .table-section {{
    background: var(--card-bg); border: 1px solid var(--card-border);
    border-radius: 12px; padding: 20px; margin-bottom: 24px; overflow-x: auto;
  }}

  /* DataTables dark theme */
  .dataTables_wrapper .dataTables_length,
  .dataTables_wrapper .dataTables_filter,
  .dataTables_wrapper .dataTables_info,
  .dataTables_wrapper .dataTables_paginate {{ color: var(--text-muted) !important; }}
  .dataTables_wrapper input, .dataTables_wrapper select {{
    background: var(--bg) !important; color: var(--text) !important;
    border: 1px solid var(--card-border) !important; border-radius: 6px !important; padding: 6px 10px !important;
  }}
  table.dataTable {{ color: var(--text) !important; border-collapse: collapse; }}
  table.dataTable thead th {{
    background: var(--bg) !important; color: var(--accent) !important;
    border-bottom: 2px solid var(--card-border) !important; padding: 10px 12px !important; font-weight: 600;
  }}
  table.dataTable tbody td {{
    border-bottom: 1px solid var(--card-border) !important; padding: 8px 12px !important;
    background-color: transparent !important;
  }}
  table.dataTable tbody tr {{ background-color: var(--card-bg) !important; }}
  table.dataTable.stripe tbody tr.odd,
  table.dataTable.display tbody tr.odd {{ background-color: rgba(30,41,59,0.5) !important; }}
  table.dataTable.stripe tbody tr.even,
  table.dataTable.display tbody tr.even {{ background-color: var(--card-bg) !important; }}
  table.dataTable tbody tr:hover {{ background: rgba(99,110,250,0.08) !important; cursor: pointer; }}
  table.dataTable tbody td.sorting_1,
  table.dataTable tbody td.sorting_2,
  table.dataTable tbody td.sorting_3 {{ background-color: transparent !important; }}
  table.dataTable.stripe tbody tr.odd td.sorting_1,
  table.dataTable.display tbody tr.odd td.sorting_1 {{ background-color: rgba(30,41,59,0.3) !important; }}
  .rating-badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-weight: 600; font-size: 0.9em; }}
  .rating-high {{ background: rgba(0,204,150,0.2); color: #00cc96; }}
  .rating-mid {{ background: rgba(255,161,90,0.2); color: #ffa15a; }}
  .rating-low {{ background: rgba(239,85,59,0.2); color: #ef553b; }}

  /* Modal */
  .modal-overlay {{
    display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.7); z-index: 1000; justify-content: center; align-items: center;
  }}
  .modal-overlay.show {{ display: flex; }}
  .modal {{
    background: var(--card-bg); border: 1px solid var(--card-border);
    border-radius: 16px; padding: 30px; max-width: 600px; width: 90%;
    max-height: 80vh; overflow-y: auto; position: relative;
  }}
  .modal-close {{
    position: absolute; top: 12px; right: 16px; background: none;
    border: none; color: var(--text-muted); font-size: 1.5em; cursor: pointer;
  }}
  .modal-close:hover {{ color: var(--red); }}
  .modal h2 {{ margin-bottom: 12px; font-size: 1.5em; }}
  .modal-movie {{ max-width: 700px; }}
  .modal-poster {{
    float: right; width: 160px; margin: 0 0 12px 16px; border-radius: 8px; overflow: hidden;
    box-shadow: 0 4px 15px rgba(0,0,0,0.4);
  }}
  .modal-poster img {{
    width: 100%; display: block; border-radius: 8px;
    transition: transform 0.3s;
  }}
  .modal-poster img:hover {{ transform: scale(1.05); }}
  .image-viewer-modal {{ max-width: 900px; padding: 20px 24px; }}
  .modal .detail-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 16px 0; }}
  .modal .detail-label {{ color: var(--text-muted); font-size: 0.85em; }}
  .modal .detail-value {{ color: var(--text); font-size: 1em; font-weight: 500; }}
  .modal .detail-summary {{ margin-top: 12px; color: var(--text-muted); line-height: 1.7; font-size: 0.95em; }}

  /* Crawl Panel Styles */
  .crawl-grid {{
    display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px;
  }}
  .crawl-panel {{
    background: var(--card-bg); border: 1px solid var(--card-border);
    border-radius: 12px; padding: 20px;
  }}
  .crawl-panel h3 {{ margin-bottom: 16px; font-size: 1.1em; color: var(--accent); }}
  .form-row {{
    display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap;
  }}
  .form-row label {{ color: var(--text-muted); font-size: 0.85em; min-width: 80px; }}
  .form-row input, .form-row select {{
    background: var(--bg); color: var(--text); border: 1px solid var(--card-border);
    border-radius: 6px; padding: 6px 10px; font-size: 0.9em;
  }}
  .form-row input:focus, .form-row select:focus {{
    outline: none; border-color: var(--accent);
  }}
  .form-row input[type="number"] {{ width: 80px; }}
  .form-row input[type="text"] {{ flex: 1; min-width: 150px; }}

  .btn {{
    padding: 10px 24px; border: none; border-radius: 8px; cursor: pointer;
    font-size: 0.95em; font-weight: 600; transition: all 0.2s;
  }}
  .btn-primary {{ background: var(--accent); color: white; }}
  .btn-primary:hover {{ background: #4f5bd5; }}
  .btn-primary:disabled {{ opacity: 0.5; cursor: not-allowed; }}
  .btn-danger {{ background: var(--red); color: white; }}
  .btn-danger:hover {{ background: #d63e30; }}
  .btn-danger:disabled {{ opacity: 0.5; cursor: not-allowed; }}
  .btn-success {{ background: var(--green); color: white; }}
  .btn-success:hover {{ background: #00a87a; }}

  .log-console {{
    background: #0a0e1a; border: 1px solid var(--card-border);
    border-radius: 8px; padding: 12px; height: 300px; overflow-y: auto;
    font-family: "Cascadia Code", "Consolas", monospace; font-size: 0.85em;
    line-height: 1.6; color: var(--text); margin-top: 12px;
  }}
  .log-console .log-info {{ color: #94a3b8; }}
  .log-console .log-success {{ color: #00cc96; }}
  .log-console .log-error {{ color: #ef553b; }}
  .log-console .log-warn {{ color: #ffa15a; }}

  .db-status-card {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px; margin-bottom: 16px;
  }}
  .db-stat {{
    background: rgba(99,110,250,0.08); border-radius: 10px;
    padding: 14px; text-align: center;
  }}
  .db-stat .db-stat-value {{ font-size: 1.5em; font-weight: 700; color: var(--accent); }}
  .db-stat .db-stat-label {{ font-size: 0.8em; color: var(--text-muted); margin-top: 4px; }}

  .status-dot {{
    display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px;
  }}
  .status-dot.connected {{ background: var(--green); box-shadow: 0 0 6px var(--green); }}
  .status-dot.disconnected {{ background: var(--red); }}

  @media (max-width: 800px) {{
    .crawl-grid {{ grid-template-columns: 1fr; }}
    .chart-grid {{ grid-template-columns: 1fr; }}
    .header h1 {{ font-size: 1.5em; }}
    .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .filter-panel {{ flex-direction: column; align-items: stretch; }}
    .modal .detail-grid {{ grid-template-columns: 1fr; }}
    .modal-poster {{ float: none; width: 100%; max-width: 200px; margin: 0 auto 16px; }}
    .gallery-grid {{ grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); }}
  }}

  /* Gallery */
  .gallery-grid {{
    display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 16px;
  }}
  .gallery-item {{
    background: var(--card-bg); border: 1px solid var(--card-border);
    border-radius: 10px; overflow: hidden; cursor: pointer;
    transition: transform 0.25s, box-shadow 0.25s;
  }}
  .gallery-item:hover {{
    transform: translateY(-4px);
    box-shadow: 0 8px 25px rgba(99,110,250,0.25);
    border-color: var(--accent);
  }}
  .gallery-item img {{
    width: 100%; height: 160px; object-fit: cover; display: block;
  }}
  .gallery-caption {{
    padding: 10px 12px; font-size: 0.82em; color: var(--text-muted);
    text-align: center; line-height: 1.3; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }}
</style>
</head>
<body>
<div class="container">

  <div class="header">
    <h1>🎬 豆瓣电影数据采集与管理平台</h1>
    <p>基于 {len(df)} 部电影 · {len(comments_df):,d} 条短评 · {datetime.now().strftime("%Y-%m-%d")}</p>
  </div>

  <div class="tab-nav">
    <button class="tab-btn active" onclick="switchTab('overview')">📊 概览</button>
    <button class="tab-btn" onclick="switchTab('distribution')">📈 分布分析</button>
    <button class="tab-btn" onclick="switchTab('geography')">🌍 地域分析</button>
    <button class="tab-btn" onclick="switchTab('people')">👤 人物分析</button>
    <button class="tab-btn" onclick="switchTab('table')">📋 数据表</button>
    <button class="tab-btn" onclick="switchTab('gallery')">📸 分析图集</button>
    <button class="tab-btn" onclick="switchTab('crawl')">🕷️ 爬虫控制</button>
    <button class="tab-btn" onclick="switchTab('database')">🗄️ 数据库</button>
  </div>

  {cards_html}

  <!-- ===== TAB: 概览 ===== -->
  <div class="tab-panel active" id="tab-overview">
    <div class="chart-grid">
      <div class="chart-card">{chart_html["hist"]}</div>
      <div class="chart-card">{chart_html["pie"]}</div>
    </div>
    <div class="chart-grid">
      <div class="chart-card full-width">{chart_html["scatter"]}</div>
    </div>
    <div class="chart-grid">
      <div class="chart-card full-width">{chart_html["trend"]}</div>
    </div>
    <div class="chart-grid">
      <div class="chart-card full-width">{chart_html["comment_timeline"]}</div>
    </div>
    <div class="chart-grid">
      <div class="chart-card">{chart_html["heatmap"]}</div>
      <div class="chart-card">{chart_html["genre_decade"]}</div>
    </div>
  </div>

  <!-- ===== TAB: 分布分析 ===== -->
  <div class="tab-panel" id="tab-distribution">
    <div class="chart-grid">
      <div class="chart-card">{chart_html["genre"]}</div>
      <div class="chart-card">{chart_html["radar"]}</div>
    </div>
    <div class="chart-grid">
      <div class="chart-card full-width">{chart_html["boxplot"]}</div>
    </div>
    <div class="chart-grid">
      <div class="chart-card">{chart_html["violin"]}</div>
      <div class="chart-card">{chart_html["lang"]}</div>
    </div>
  </div>

  <!-- ===== TAB: 地域分析 ===== -->
  <div class="tab-panel" id="tab-geography">
    <div class="chart-grid">
      <div class="chart-card full-width">{chart_html["world"]}</div>
    </div>
    <div class="chart-grid">
      <div class="chart-card full-width">{chart_html["country"]}</div>
    </div>
  </div>

  <!-- ===== TAB: 人物分析 ===== -->
  <div class="tab-panel" id="tab-people">
    <div class="chart-grid">
      <div class="chart-card full-width">{chart_html["director"]}</div>
    </div>
    <div class="chart-grid">
      <div class="chart-card full-width">{chart_html["reviewers"]}</div>
    </div>
  </div>

  <!-- ===== TAB: 数据表 ===== -->
  <div class="tab-panel" id="tab-table">
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
    <div class="table-section">
      <h3 class="section-title">📋 电影数据表 (点击行查看详情)</h3>
      <table id="movieTable" class="display stripe" style="width:100%">
        <thead><tr><th>排名</th><th>电影名称</th><th>评分</th><th>评论数</th><th>类型</th><th>导演</th><th>年份</th><th>片长(分)</th><th>国家</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
  </div>

  <!-- ===== TAB: 分析图集 ===== -->
  <div class="tab-panel" id="tab-gallery">
    <h2 class="section-title">📸 数据分析输出图集</h2>
    {analysis_gallery_html}
  </div>

  <!-- ===== TAB: 爬虫控制 ===== -->
  <div class="tab-panel" id="tab-crawl">
    <div class="crawl-grid">
      <div class="crawl-panel">
        <h3>⚙️ 采集配置</h3>
        <div class="form-row">
          <label>采集模式:</label>
          <select id="crawlMode">
            <option value="top250">Top250 排行榜</option>
            <option value="urls">自定义 URL</option>
            <option value="import">导入已有数据</option>
          </select>
        </div>
        <div class="form-row">
          <label>最大页数:</label>
          <input type="number" id="crawlMaxPages" value="1" min="1" max="50">
          <label style="min-width:70px">短评条数:</label>
          <input type="number" id="crawlCommentLimit" value="20" min="0" max="200">
        </div>
        <div class="form-row" id="urlRow" style="display:none">
          <label>自定义网址:</label>
        </div>
        <div class="form-row" id="urlInputRow" style="display:none">
          <textarea id="crawlUrls" rows="3" style="flex:1;background:var(--bg);color:var(--text);border:1px solid var(--card-border);border-radius:6px;padding:8px;font-size:0.85em;" placeholder="每行一个豆瓣电影列表/搜索 URL"></textarea>
        </div>
        <div class="form-row">
          <label>输出目录:</label>
          <input type="text" id="crawlOutputDir" value="data/crawler" style="flex:1">
        </div>
        <div class="form-row">
          <label style="display:flex;align-items:center;gap:6px;">
            <input type="checkbox" id="crawlDownloadImages" checked> 下载封面图
          </label>
          <label style="display:flex;align-items:center;gap:6px;">
            <input type="checkbox" id="crawlDetails" checked> 采集详情页
          </label>
          <label style="display:flex;align-items:center;gap:6px;">
            <input type="checkbox" id="crawlFastMode"> 快速模式
          </label>
        </div>
      </div>

      <div class="crawl-panel">
        <h3>🔧 高级设置</h3>
        <div class="form-row">
          <label>延迟范围:</label>
          <input type="number" id="crawlDelayMin" value="1.2" step="0.1" min="0" max="10" style="width:70px">
          <span>~</span>
          <input type="number" id="crawlDelayMax" value="3.5" step="0.1" min="0" max="15" style="width:70px">
          <span style="color:var(--text-muted)">秒</span>
        </div>
        <div class="form-row">
          <label>Cookie:</label>
          <input type="text" id="crawlCookie" placeholder="可选，已登录的豆瓣 Cookie" style="flex:1">
        </div>
        <div class="form-row">
          <label>代理:</label>
          <input type="text" id="crawlProxy" placeholder="如 http://127.0.0.1:7890" style="flex:1">
        </div>
        <div class="form-row">
          <label style="display:flex;align-items:center;gap:6px;">
            <input type="checkbox" id="crawlSelenium"> Selenium 兜底
          </label>
          <label style="display:flex;align-items:center;gap:6px;">
            <input type="checkbox" id="crawlShowBrowser"> 显示浏览器
          </label>
        </div>

        <h3 style="margin-top:16px">🗄️ MySQL 存储</h3>
        <div class="form-row">
          <label style="display:flex;align-items:center;gap:6px;">
            <input type="checkbox" id="crawlSaveMysql"> 保存到 MySQL
          </label>
        </div>
        <div class="form-row">
          <label>主机:</label>
          <input type="text" id="mysqlHost" value="localhost" style="width:130px">
          <label style="min-width:40px">端口:</label>
          <input type="number" id="mysqlPort" value="3306" style="width:80px">
        </div>
        <div class="form-row">
          <label>用户名:</label>
          <input type="text" id="mysqlUser" value="root" style="width:130px">
          <label style="min-width:40px">密码:</label>
          <input type="password" id="mysqlPassword" value="123456" style="width:130px">
        </div>
        <div class="form-row">
          <label>数据库:</label>
          <input type="text" id="mysqlDatabase" value="douban" style="width:200px">
        </div>
      </div>
    </div>

    <div style="display:flex;gap:10px;margin-bottom:12px;">
      <button class="btn btn-primary" id="btnCrawlStart" onclick="startCrawl()">📥 开始采集</button>
      <button class="btn btn-danger" id="btnCrawlStop" onclick="stopCrawl()" disabled>⏹ 停止</button>
      <button class="btn btn-success" id="btnRefreshDashboard" onclick="refreshDashboard()">🔄 刷新仪表盘</button>
      <span id="crawlStatus" style="display:flex;align-items:center;font-size:0.9em;color:var(--text-muted);margin-left:12px;"></span>
    </div>

    <div class="log-console" id="logConsole">
      <div class="log-info">💡 点击"开始采集"启动爬虫，日志将实时显示在此处。</div>
    </div>
  </div>

  <!-- ===== TAB: 数据库 ===== -->
  <div class="tab-panel" id="tab-database">
    <h2 class="section-title">🗄️ MySQL 数据库状态</h2>
    <div class="db-status-card" id="dbStatusCards">
      <div class="db-stat"><div class="db-stat-value">...</div><div class="db-stat-label">正在检测...</div></div>
    </div>
    <div style="display:flex;gap:10px;margin-bottom:20px;">
      <button class="btn btn-primary" onclick="checkDbStatus()">🔄 刷新状态</button>
      <button class="btn btn-success" onclick="exportDb()">📥 导出备份 (JSON/CSV)</button>
    </div>
    <div id="dbExportResult" style="margin-top:10px;"></div>
  </div>

  <!-- Movie Detail Modal -->
  <div class="modal-overlay" id="movieModal">
    <div class="modal modal-movie">
      <button class="modal-close" onclick="closeModal()">✕</button>
      <div class="modal-poster" id="modalPoster"></div>
      <h2 id="modalTitle"></h2>
      <div class="detail-grid" id="modalDetails"></div>
      <div class="detail-summary" id="modalSummary"></div>
    </div>
  </div>

  <!-- Image Viewer Modal -->
  <div class="modal-overlay" id="imageViewer" onclick="closeImageViewer()">
    <div class="modal image-viewer-modal" onclick="event.stopPropagation()">
      <button class="modal-close" onclick="closeImageViewer()">✕</button>
      <h3 id="imageViewerTitle" style="margin-bottom:16px;"></h3>
      <img id="imageViewerImg" src="" alt="" style="width:100%;border-radius:8px;">
    </div>
  </div>

</div>

<script id="jquery-js">{jquery_js}</script>
<script id="datatables-js">{datatables_js}</script>
<script>
const tableData = {json.dumps(table_data, ensure_ascii=False)};
let dataTable;
let eventSource = null;

// ===== 标签页切换 =====
function switchTab(tabName) {{
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  const btn = document.querySelector(`.tab-btn[onclick="switchTab('${{tabName}}')"]`);
  const panel = document.getElementById(`tab-${{tabName}}`);
  if (btn) btn.classList.add('active');
  if (panel) {{
    panel.classList.add('active');
    setTimeout(() => {{
      const plotlyDivs = panel.querySelectorAll('.plotly-graph-div, .js-plotly-plot');
      plotlyDivs.forEach(div => {{ if (div._fullLayout && Plotly) Plotly.Plots.resize(div); }});
      if (tabName === 'table' && dataTable) dataTable.columns.adjust().draw();
      if (tabName === 'database') checkDbStatus();
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
  const badges = [];
  if (f.genre) badges.push(`<span class="filter-badge">🎭 ${{f.genre}} <span class="clear-btn" onclick="clearFilter('genre')">×</span></span>`);
  if (f.country) badges.push(`<span class="filter-badge">🌍 ${{f.country}} <span class="clear-btn" onclick="clearFilter('country')">×</span></span>`);
  if (f.decade) badges.push(`<span class="filter-badge">📅 ${{f.decade}}s <span class="clear-btn" onclick="clearFilter('decade')">×</span></span>`);
  document.getElementById('activeFilters').innerHTML = badges.join('');
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

  // 海报图片
  const posterDiv = document.getElementById('modalPoster');
  const posterFile = rowData['海报文件'] || '';
  if (posterFile) {{
    posterDiv.innerHTML = `<img src="/images/poster/${{encodeURIComponent(posterFile)}}" alt="${{rowData['电影名称']}}" loading="lazy" onerror="this.parentElement.style.display='none'">`;
    posterDiv.style.display = 'block';
  }} else {{
    posterDiv.style.display = 'none';
  }}

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
document.addEventListener('keydown', function(e) {{ if (e.key === 'Escape') {{ closeModal(); closeImageViewer(); }} }});

// ===== 图片查看器 =====
function openImageViewer(src, title) {{
  document.getElementById('imageViewerImg').src = src;
  document.getElementById('imageViewerTitle').textContent = title || '';
  document.getElementById('imageViewer').classList.add('show');
}}

function closeImageViewer() {{
  document.getElementById('imageViewer').classList.remove('show');
}}

// ===== 初始化数据表 =====
$(document).ready(function() {{
  dataTable = $('#movieTable').DataTable({{
    data: tableData,
    columns: [
      {{ data: '排名' }},
      {{ data: '电影名称' }},
      {{ data: '评分', render: function(d) {{
          let cls = d >= 9.2 ? 'rating-high' : (d >= 8.8 ? 'rating-mid' : 'rating-low');
          return `<span class="rating-badge ${{cls}}">★ ${{d}}</span>`;
      }}}},
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
      search: "🔍 搜索:", lengthMenu: "每页显示 _MENU_ 条",
      info: "显示第 _START_ 至 _END_ 条，共 _TOTAL_ 条",
      infoEmpty: "无记录", infoFiltered: "(从 _MAX_ 条中筛选)",
      paginate: {{ first: "首页", last: "末页", next: "下一页", previous: "上一页" }},
      zeroRecords: "未找到匹配的电影"
    }},
    order: [[0, 'asc']]
  }});
  $('#movieTable tbody').on('click', 'tr', function() {{
    const row = dataTable.row(this).data();
    if (row) showMovieDetail(row);
  }});

  // 爬虫模式切换
  document.getElementById('crawlMode').addEventListener('change', function() {{
    const urlRows = document.getElementById('urlRow');
    const urlInputRow = document.getElementById('urlInputRow');
    if (this.value === 'urls') {{
      urlRows.style.display = 'flex'; urlInputRow.style.display = 'flex';
    }} else {{
      urlRows.style.display = 'none'; urlInputRow.style.display = 'none';
    }}
  }});

  // 快速模式自动调整延迟
  document.getElementById('crawlFastMode').addEventListener('change', function() {{
    if (this.checked) {{
      document.getElementById('crawlDelayMin').value = '0.5';
      document.getElementById('crawlDelayMax').value = '1.5';
    }}
  }});
}});

// ===== 爬虫控制 =====
function startCrawl() {{
  const mode = document.getElementById('crawlMode').value;
  const urls = [];
  if (mode === 'urls') {{
    const text = document.getElementById('crawlUrls').value.trim();
    if (!text) {{ alert('请填写至少一个 URL'); return; }}
    urls.push(...text.split('\\n').map(s => s.trim()).filter(s => s));
  }}

  const cfg = {{
    mode: mode,
    urls: urls,
    max_pages: parseInt(document.getElementById('crawlMaxPages').value) || 1,
    page_param: 'start',
    page_size: 25,
    comment_limit: parseInt(document.getElementById('crawlCommentLimit').value) || 20,
    download_images: document.getElementById('crawlDownloadImages').checked,
    crawl_details: document.getElementById('crawlDetails').checked,
    fast_mode: document.getElementById('crawlFastMode').checked,
    cookie: document.getElementById('crawlCookie').value.trim() || null,
    delay_min: parseFloat(document.getElementById('crawlDelayMin').value) || 1.2,
    delay_max: parseFloat(document.getElementById('crawlDelayMax').value) || 3.5,
    use_selenium: document.getElementById('crawlSelenium').checked,
    show_browser: document.getElementById('crawlShowBrowser').checked,
    driver_path: null,
    proxies: document.getElementById('crawlProxy').value.trim() ? [document.getElementById('crawlProxy').value.trim()] : [],
    output_dir: document.getElementById('crawlOutputDir').value.trim() || 'data/crawler',
    save_mysql: document.getElementById('crawlSaveMysql').checked,
    mysql_host: document.getElementById('mysqlHost').value.trim() || 'localhost',
    mysql_port: parseInt(document.getElementById('mysqlPort').value) || 3306,
    mysql_user: document.getElementById('mysqlUser').value.trim() || 'root',
    mysql_password: document.getElementById('mysqlPassword').value || '123456',
    mysql_database: document.getElementById('mysqlDatabase').value.trim() || 'douban',
    mysql_backup_dir: 'data/database/backup'
  }};

  document.getElementById('btnCrawlStart').disabled = true;
  document.getElementById('btnCrawlStop').disabled = false;
  document.getElementById('crawlStatus').textContent = '🔄 正在运行...';

  const logConsole = document.getElementById('logConsole');
  logConsole.innerHTML = '';

  // 关闭旧的 SSE
  if (eventSource) eventSource.close();

  fetch('/api/crawl/start', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify(cfg)
  }}).then(r => r.json()).then(data => {{
    if (!data.ok) {{
      appendLog('❌ ' + data.error, 'log-error');
      document.getElementById('btnCrawlStart').disabled = false;
      document.getElementById('btnCrawlStop').disabled = true;
      document.getElementById('crawlStatus').textContent = '';
      return;
    }}
    appendLog('🚀 爬虫已启动', 'log-success');
    // 开始 SSE 日志流
    eventSource = new EventSource('/api/crawl/logs');
    eventSource.onmessage = function(e) {{
      const data = JSON.parse(e.data);
      if (!data.msg) return;
      if (data.msg === '__DONE__') {{
        eventSource.close();
        document.getElementById('btnCrawlStart').disabled = false;
        document.getElementById('btnCrawlStop').disabled = true;
        document.getElementById('crawlStatus').textContent = '✅ 任务完成';
        return;
      }}
      let cls = 'log-info';
      if (data.msg.includes('✅')) cls = 'log-success';
      if (data.msg.includes('❌')) cls = 'log-error';
      if (data.msg.includes('⚠️')) cls = 'log-warn';
      appendLog(data.msg, cls);
    }};
    eventSource.onerror = function() {{
      eventSource.close();
      document.getElementById('btnCrawlStart').disabled = false;
      document.getElementById('btnCrawlStop').disabled = true;
    }};
  }}).catch(err => {{
    appendLog('❌ 请求失败: ' + err, 'log-error');
    document.getElementById('btnCrawlStart').disabled = false;
    document.getElementById('btnCrawlStop').disabled = true;
  }});
}}

function stopCrawl() {{
  fetch('/api/crawl/stop', {{ method: 'POST' }}).then(r => r.json()).then(data => {{
    appendLog('⏹ ' + data.message, 'log-warn');
    document.getElementById('btnCrawlStop').disabled = true;
    document.getElementById('crawlStatus').textContent = '⏹ 正在停止...';
  }});
}}

function appendLog(msg, cls) {{
  const consoleEl = document.getElementById('logConsole');
  const div = document.createElement('div');
  div.className = cls || 'log-info';
  div.textContent = msg;
  consoleEl.appendChild(div);
  consoleEl.scrollTop = consoleEl.scrollHeight;
}}

function refreshDashboard() {{
  fetch('/api/db/reload-dashboard', {{ method: 'POST' }}).then(r => r.json()).then(data => {{
    alert(data.message);
    location.reload();
  }});
}}

// ===== 数据库管理 =====
function checkDbStatus() {{
  fetch('/api/db/status').then(r => r.json()).then(data => {{
    const container = document.getElementById('dbStatusCards');
    if (!data.ok) {{
      container.innerHTML = `<div class="db-stat">
        <div><span class="status-dot disconnected"></span>未连接</div>
        <div class="db-stat-label">${{data.error || '无法连接数据库'}}</div>
      </div>`;
      return;
    }}
    const lastUpdate = data.last_update ? new Date(data.last_update).toLocaleString('zh-CN') : '未知';
    container.innerHTML = `
      <div class="db-stat"><span class="status-dot connected"></span><div class="db-stat-label">连接状态</div></div>
      <div class="db-stat"><div class="db-stat-value">${{data.movie_count.toLocaleString()}}</div><div class="db-stat-label">电影数量</div></div>
      <div class="db-stat"><div class="db-stat-value">${{data.comment_count.toLocaleString()}}</div><div class="db-stat-label">短评数量</div></div>
      <div class="db-stat"><div class="db-stat-value">${{lastUpdate}}</div><div class="db-stat-label">最后更新</div></div>
      <div class="db-stat"><div class="db-stat-value">${{data.host}}</div><div class="db-stat-label">主机:端口 (${{data.database}})</div></div>
    `;
  }}).catch(err => {{
    document.getElementById('dbStatusCards').innerHTML = `<div class="db-stat"><div class="db-stat-label">检测失败: ${{err}}</div></div>`;
  }});
}}

function exportDb() {{
  const btn = event.target;
  btn.disabled = true;
  btn.textContent = '⏳ 导出中...';
  fetch('/api/db/export', {{ method: 'POST' }}).then(r => r.json()).then(data => {{
    btn.disabled = false;
    btn.textContent = '📥 导出备份 (JSON/CSV)';
    const resultDiv = document.getElementById('dbExportResult');
    if (data.ok) {{
      resultDiv.innerHTML = `<div style="background:rgba(0,204,150,0.1);border:1px solid var(--green);border-radius:8px;padding:12px;">
        <div style="color:var(--green);font-weight:600;">✅ 导出成功</div>
        <div style="color:var(--text-muted);margin-top:4px;">JSON: ${{data.json}}</div>
        <div style="color:var(--text-muted);">CSV(电影): ${{data.movies_csv}}</div>
        <div style="color:var(--text-muted);">CSV(短评): ${{data.comments_csv}}</div>
      </div>`;
    }} else {{
      resultDiv.innerHTML = `<div style="background:rgba(239,85,59,0.1);border:1px solid var(--red);border-radius:8px;padding:12px;color:var(--red);">❌ ${{data.error}}</div>`;
    }}
  }}).catch(err => {{
    btn.disabled = false;
    btn.textContent = '📥 导出备份 (JSON/CSV)';
    document.getElementById('dbExportResult').innerHTML = `<div style="color:var(--red);">❌ ${{err}}</div>`;
  }});
}}
</script>
</body>
</html>"""

    _html_cache = html
    return html


# ========================================================================
#  Flask Routes - Main
# ========================================================================

@app.route("/")
def index():
    """主页面 - 仪表盘。"""
    return build_html()


# ========================================================================
#  Entry Point
# ========================================================================

def main():
    parser = argparse.ArgumentParser(description="豆瓣电影数据采集 Web 集成服务")
    parser.add_argument("--host", default="127.0.0.1", help="绑定地址 (默认 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000, help="端口 (默认 5000)")
    parser.add_argument("--debug", action="store_true", help="开启 Flask 调试模式")
    args = parser.parse_args()

    # 检查依赖是否存在
    deps_ok = True
    if not JQUERY_PATH.exists():
        print("⚠ jquery.min.js 未找到，请先运行 download_deps.py 下载")
        deps_ok = False
    if not DATATABLES_JS_PATH.exists():
        print("⚠ datatables.min.js 未找到，请先运行 download_deps.py 下载")
        deps_ok = False

    if not deps_ok:
        print("  运行: python analysis/download_deps.py")
        print()

    print("=" * 60)
    print("  豆瓣电影数据采集与管理平台")
    print("=" * 60)
    print()
    print(f"  🌐 访问地址: http://{args.host}:{args.port}")
    print()
    print("  📊 仪表盘   - 16+ 交互图表 + 数据表")
    print("  🕷️ 爬虫控制 - Top250/URL/导入模式")
    print("  🗄️ 数据库   - MySQL 状态查看与备份导出")
    print()
    print("  按 Ctrl+C 停止服务")
    print("=" * 60)

    # 预热：提前加载数据
    print("[预热] 加载数据...")
    _get_dashboard_data()
    build_html()  # 预生成 HTML
    print("[就绪] 服务启动中...\n")

    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == "__main__":
    main()
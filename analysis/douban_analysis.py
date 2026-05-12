#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
豆瓣电影 Top250 数据分析脚本
=============================
功能：
  1. 数据清洗（缺失值处理、类型转换、去重）
  2. 统计分析（高分Top10、导演/类型分布、评分与评论数相关性、短评情感倾向）
  3. 可视化（评分分布直方图、类型饼图、散点图、短评词云、时间趋势线图）

数据源：data/database/backup/douban_movies.json
输出目录：analysis/output/
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

# ========== 可视化库 ==========
import matplotlib
matplotlib.use("Agg")  # 非交互后端，适配无 GUI 环境

import matplotlib.font_manager as fm

# 1. 清除 matplotlib 字体缓存
_cache_dir = matplotlib.get_cachedir()
for _f in os.listdir(_cache_dir):
    if _f.endswith(".json"):
        _fp = os.path.join(_cache_dir, _f)
        os.remove(_fp)
        print(f"[字体] 已删除缓存: {_f}")

# 2. 强制重建字体列表（不从缓存读取）
fm._load_fontmanager(try_read_cache=False)

# 3. 查找并注册系统中文字体
_FONT_PATH = None
_FONT_NAME = None
for _fp in ["C:\\Windows\\Fonts\\simhei.ttf", "C:\\Windows\\Fonts\\msyh.ttc"]:
    if os.path.exists(_fp):
        _FONT_PATH = _fp
        break

if _FONT_PATH:
    fm.fontManager.addfont(_FONT_PATH)
    _FONT_NAME = fm.FontProperties(fname=_FONT_PATH).get_name()
else:
    _FONT_NAME = None

# 先导入 pyplot 和 seaborn（它们可能会重置 rcParams）
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
sns.set_style("whitegrid")

# ⚠️ 关键：字体 rcParams 必须在 seaborn set_style 之后设置！
# seaborn 导入和 set_style 会重置部分 rcParams，之后设置才能生效。
if _FONT_PATH and _FONT_NAME:
    print(f"[字体] 使用字体: {_FONT_NAME} ({_FONT_PATH})")
    plt.rcParams["font.sans-serif"] = [_FONT_NAME, "SimHei", "Microsoft YaHei", "DejaVu Sans"]
    plt.rcParams["font.family"] = "sans-serif"
else:
    print("[字体] ⚠ 未找到系统中文字体，使用默认配置")
    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]

plt.rcParams["axes.unicode_minus"] = False

# Plotly 可选
try:
    import plotly.express as px
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

# 词云
from wordcloud import WordCloud

# 中文分词
import jieba
import jieba.analyse

warnings.filterwarnings("ignore")

# ========== 路径配置 ==========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATA_FILE = os.path.join(PROJECT_ROOT, "data", "database", "backup", "douban_movies.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ========== 豆瓣评分 → 数值映射 ==========
RATING_MAP = {
    "力荐": 5,
    "推荐": 4,
    "还行": 3,
    "较差": 2,
    "很差": 1,
    "": np.nan,
}


# ====================================================================
#  第一部分：数据加载
# ====================================================================

def load_data(filepath: str) -> pd.DataFrame:
    """从 JSON 加载豆瓣电影数据，返回 DataFrame。"""
    print(f"[加载] 读取数据: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        raw = json.load(f)
    df = pd.DataFrame(raw)
    print(f"[加载] 共 {len(df)} 条电影记录")
    return df


# ====================================================================
#  第二部分：数据清洗
# ====================================================================

def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    数据清洗三步走：
      1. 缺失值处理
      2. 类型转换
      3. 去重
    """
    print("\n" + "=" * 60)
    print("  数据清洗")
    print("=" * 60)

    df = df.copy()
    n_before = len(df)

    # ---- 2.1 缺失值概览 ----
    print("\n[缺失值统计]")
    missing = df.isnull().sum()
    missing_pct = (df.isnull().mean() * 100).round(2)
    for col in df.columns:
        if missing[col] > 0:
            print(f"  {col}: {missing[col]} 缺失 ({missing_pct[col]}%)")

    # 处理关键字段缺失
    # rating 缺失 → 填中位数
    if df["rating"].isnull().any():
        median_rating = df["rating"].median()
        df["rating"].fillna(median_rating, inplace=True)
        print(f"  → rating 缺失值已填充为中位数 {median_rating:.1f}")

    # comment_count 缺失 → 填 0
    df["comment_count"] = df["comment_count"].fillna(0).astype(int)

    # genres 缺失 → 填 "未知"
    df["genres"] = df["genres"].fillna("未知")

    # director 缺失 → 填 "未知"
    df["director"] = df["director"].fillna("未知")

    # country 缺失 → 填 "未知"
    df["country"] = df["country"].fillna("未知")

    # runtime 缺失 → 填中位数
    if df["runtime"].isnull().any():
        df["runtime"].fillna(df["runtime"].median(), inplace=True)

    # title_cn / title_en 缺失 → 填空字符串
    for c in ["title_cn", "title_en", "summary", "language", "release_date", "imdb"]:
        if c in df.columns:
            df[c] = df[c].fillna("")

    # ---- 2.2 类型转换 ----
    print("\n[类型转换]")

    # rating → float
    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
    print("  rating → float")

    # comment_count → int
    df["comment_count"] = pd.to_numeric(df["comment_count"], errors="coerce").fillna(0).astype(int)
    print("  comment_count → int")

    # rank → int
    df["rank"] = pd.to_numeric(df["rank"], errors="coerce").fillna(0).astype(int)
    print("  rank → int")

    # runtime → int
    df["runtime"] = pd.to_numeric(df["runtime"], errors="coerce").fillna(0).astype(int)
    print("  runtime → int")

    # created_at → datetime
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    print("  created_at → datetime")

    # 从 release_date 提取年份
    def extract_year(date_str):
        if not date_str or not isinstance(date_str, str):
            return np.nan
        m = re.search(r"(\d{4})", date_str)
        return int(m.group(1)) if m else np.nan

    df["release_year"] = df["release_date"].apply(extract_year)
    df["release_year"] = pd.to_numeric(df["release_year"], errors="coerce")
    print("  release_year 已从 release_date 提取")

    # 拆分 genres 为列表
    df["genre_list"] = df["genres"].apply(
        lambda x: [g.strip() for g in str(x).split("/") if g.strip()] if x else []
    )
    print("  genre_list 已拆分")

    # 拆分导演列表
    df["director_list"] = df["director"].apply(
        lambda x: [d.strip() for d in str(x).split("/") if d.strip()] if x else []
    )
    print("  director_list 已拆分")

    # ---- 2.3 去重 ----
    print("\n[去重]")
    dups = df.duplicated(subset=["title_cn", "url"], keep="first")
    n_dup = dups.sum()
    if n_dup > 0:
        df = df[~dups]
        print(f"  移除 {n_dup} 条重复记录（基于 title_cn + url）")
    else:
        print("  未发现重复记录")

    # 清理 \u00a0 (NBSP) 字符
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(
                lambda x: x.replace("\u00a0", " ").strip()
                if isinstance(x, str) else x
            )
    print("  NBSP 字符已清理")

    n_after = len(df)
    print(f"\n  清洗前后: {n_before} → {n_after} 条记录")

    return df


# ====================================================================
#  第三部分：提取短评
# ====================================================================

def extract_comments(df: pd.DataFrame) -> pd.DataFrame:
    """从电影数据中提取所有短评为扁平 DataFrame。"""
    print("\n[提取短评]")
    comments_list = []
    for _, row in df.iterrows():
        movie_id = row.get("id")
        title = row.get("title_cn", row.get("title", ""))
        rating = row.get("rating")
        raw_comments = row.get("comments", [])
        if not raw_comments or not isinstance(raw_comments, list):
            continue
        for c in raw_comments:
            c["movie_id"] = movie_id
            c["movie_title"] = title
            c["movie_rating"] = rating
            comments_list.append(c)

    comments_df = pd.DataFrame(comments_list)
    print(f"  共提取 {len(comments_df)} 条短评")

    # 清洗短评
    # 用户评分映射
    if "rating" in comments_df.columns:
        comments_df["rating_score"] = comments_df["rating"].map(RATING_MAP)
        comments_df["rating_score"] = pd.to_numeric(comments_df["rating_score"], errors="coerce")

    # helpful → int
    comments_df["helpful"] = pd.to_numeric(comments_df["helpful"], errors="coerce").fillna(0).astype(int)

    # comment_time → datetime
    comments_df["comment_time"] = pd.to_datetime(comments_df["comment_time"], errors="coerce")

    # 清理评论文本中的 NBSP
    comments_df["comment"] = comments_df["comment"].apply(
        lambda x: x.replace("\u00a0", " ").strip() if isinstance(x, str) else ""
    )

    return comments_df


# ====================================================================
#  第四部分：统计分析
# ====================================================================

def statistics(df: pd.DataFrame, comments_df: pd.DataFrame):
    """综合统计分析并输出报告。"""
    print("\n" + "=" * 60)
    print("  统计分析")
    print("=" * 60)

    # ---- 4.1 高分电影 Top10 ----
    print("\n[1] 高分电影 Top 10 (按评分降序, 同分按评论数降序):")
    top10 = df.nlargest(10, ["rating", "comment_count"])[
        ["rank", "title_cn", "rating", "comment_count", "genres", "director", "release_year"]
    ]
    for i, (_, r) in enumerate(top10.iterrows(), 1):
        print(f"  {i:2d}. {r['title_cn']:<20s}  ★{r['rating']:.1f}  "
              f"评论 {r['comment_count']:>10,d}  | {r['genres'][:30]}  | {r['director']}")

    top10.to_csv(os.path.join(OUTPUT_DIR, "top10_movies.csv"), index=False, encoding="utf-8-sig")

    # ---- 4.2 导演分布 ----
    print("\n[2] 导演分布 Top 15:")
    director_counter = Counter()
    for dl in df["director_list"]:
        for d in dl:
            if d and d != "未知":
                director_counter[d] += 1
    for i, (d, cnt) in enumerate(director_counter.most_common(15), 1):
        print(f"  {i:2d}. {d:<25s} {cnt} 部")

    # 导演平均评分
    director_ratings = defaultdict(list)
    for dl, r in zip(df["director_list"], df["rating"]):
        for d in dl:
            if d and d != "未知" and pd.notna(r):
                director_ratings[d].append(r)
    print("\n  导演平均评分 Top 10 (至少 2 部):")
    dir_avg = [(d, np.mean(rs), len(rs)) for d, rs in director_ratings.items() if len(rs) >= 2]
    dir_avg.sort(key=lambda x: x[1], reverse=True)
    for i, (d, avg, cnt) in enumerate(dir_avg[:10], 1):
        print(f"  {i:2d}. {d:<25s} 平均 ★{avg:.2f}  ({cnt} 部)")

    # ---- 4.3 类型分布 ----
    print("\n[3] 类型分布:")
    genre_counter = Counter()
    for gl in df["genre_list"]:
        for g in gl:
            if g:
                genre_counter[g] += 1
    for i, (g, cnt) in enumerate(genre_counter.most_common(20), 1):
        print(f"  {i:2d}. {g:<15s} {cnt:3d} 部")

    # 各类型平均评分
    genre_ratings = defaultdict(list)
    for gl, r in zip(df["genre_list"], df["rating"]):
        for g in gl:
            if g and pd.notna(r):
                genre_ratings[g].append(r)
    print("\n  各类型平均评分 (至少 3 部):")
    genre_avg = [(g, np.mean(rs), len(rs)) for g, rs in genre_ratings.items() if len(rs) >= 3]
    genre_avg.sort(key=lambda x: x[1], reverse=True)
    for i, (g, avg, cnt) in enumerate(genre_avg[:15], 1):
        print(f"  {i:2d}. {g:<15s} 平均 ★{avg:.2f}  ({cnt} 部)")

    # ---- 4.4 评分与评论数相关性 ----
    print("\n[4] 评分与评论人数相关性分析:")
    valid = df[df["comment_count"] > 0].copy()
    if len(valid) > 0:
        corr_pearson = valid["rating"].corr(valid["comment_count"])
        corr_spearman = valid["rating"].corr(valid["comment_count"], method="spearman")
        print(f"  Pearson  相关系数: {corr_pearson:.4f}")
        print(f"  Spearman 相关系数: {corr_spearman:.4f}")
        if corr_pearson > 0.5:
            print("  → 评分与评论人数呈较强正相关")
        elif corr_pearson > 0.2:
            print("  → 评分与评论人数呈弱正相关")
        elif corr_pearson > -0.2:
            print("  → 评分与评论人数相关性较弱")
        else:
            print("  → 评分与评论人数呈负相关")

    # 评分分布统计
    print("\n  评分分布:")
    print(f"    均值: {df['rating'].mean():.2f}  中位数: {df['rating'].median():.1f}")
    print(f"    标准差: {df['rating'].std():.2f}  最低: {df['rating'].min():.1f}  最高: {df['rating'].max():.1f}")

    # ---- 4.5 短评情感倾向 ----
    print("\n[5] 短评情感倾向分析:")
    if len(comments_df) > 0 and "rating_score" in comments_df.columns:
        scores = comments_df["rating_score"].dropna()
        if len(scores) > 0:
            # 豆瓣评分: 5=力荐 4=推荐 3=还行 2=较差 1=很差
            pos_mask = scores >= 4  # 力荐+推荐
            neg_mask = scores <= 2  # 较差+很差
            neu_mask = scores == 3
            print(f"  正面 (力荐+推荐): {pos_mask.sum():,d} ({pos_mask.mean()*100:.1f}%)")
            print(f"  中性 (还行):       {neu_mask.sum():,d} ({neu_mask.mean()*100:.1f}%)")
            print(f"  负面 (较差+很差): {neg_mask.sum():,d} ({neg_mask.mean()*100:.1f}%)")
            print(f"  平均用户评分: {scores.mean():.2f} / 5")

    # 按电影统计正面/负面比例
    print("\n  正面评价比例最高的电影 Top 5 (至少 20 条短评):")
    movie_sentiment = []
    for movie_id, grp in comments_df.groupby("movie_id"):
        if len(grp) < 20:
            continue
        valid_scores = grp["rating_score"].dropna()
        if len(valid_scores) == 0:
            continue
        pos_pct = (valid_scores >= 4).mean()
        movie_sentiment.append({
            "title": grp["movie_title"].iloc[0],
            "total": len(grp),
            "positive_pct": pos_pct,
            "avg_score": valid_scores.mean()
        })
    movie_sentiment.sort(key=lambda x: x["positive_pct"], reverse=True)
    for i, ms in enumerate(movie_sentiment[:5], 1):
        print(f"  {i}. {ms['title']:<20s}  正面率 {ms['positive_pct']*100:.1f}%  "
              f"({ms['total']} 条, 均分 {ms['avg_score']:.2f})")

    return {
        "top10": top10,
        "director_counter": director_counter,
        "genre_counter": genre_counter,
        "corr_pearson": corr_pearson if len(valid) > 0 else 0,
        "corr_spearman": corr_spearman if len(valid) > 0 else 0,
    }


# ====================================================================
#  第五部分：可视化
# ====================================================================

# 调色板
PALETTE = sns.color_palette("Set2", 10)
COLORS_10 = sns.color_palette("tab10", 10).as_hex()


def save_fig(fig, name):
    """统一保存图表。"""
    fp = os.path.join(OUTPUT_DIR, name)
    fig.savefig(fp, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"  ✓ 已保存: {fp}")
    plt.close(fig)


# ---- 5.1 评分分布直方图 ----
def plot_rating_distribution(df: pd.DataFrame):
    """评分分布直方图 + KDE 曲线。"""
    print("\n[图表1] 评分分布直方图")
    fig, ax = plt.subplots(figsize=(10, 6))
    ratings = df["rating"].dropna()

    # 直方图
    n_bins = 15
    ax.hist(ratings, bins=n_bins, color=PALETTE[0], edgecolor="white",
            alpha=0.85, density=True, label="频率密度")

    # KDE
    from scipy.stats import gaussian_kde
    kde = gaussian_kde(ratings)
    x_kde = np.linspace(ratings.min(), ratings.max(), 200)
    ax.plot(x_kde, kde(x_kde), color=PALETTE[1], linewidth=2.5, label="KDE 密度曲线")

    # 均值线
    mean_val = ratings.mean()
    ax.axvline(mean_val, color="red", linestyle="--", linewidth=2,
               label=f"均值 ★{mean_val:.2f}")
    ax.axvline(ratings.median(), color="orange", linestyle=":", linewidth=2,
               label=f"中位数 ★{ratings.median():.1f}")

    ax.set_xlabel("豆瓣评分", fontsize=13)
    ax.set_ylabel("频率密度", fontsize=13)
    ax.set_title("豆瓣 Top250 评分分布", fontsize=16, fontweight="bold")
    ax.legend(fontsize=11)
    ax.set_xlim(ratings.min() - 0.2, ratings.max() + 0.2)

    save_fig(fig, "01_rating_distribution.png")


# ---- 5.2 类型饼图 ----
def plot_genre_pie(df: pd.DataFrame):
    """电影类型分布饼图（Top 12 类型，其余归为 '其他'）。"""
    print("\n[图表2] 类型分布饼图")
    genre_counter = Counter()
    for gl in df["genre_list"]:
        for g in gl:
            if g:
                genre_counter[g] += 1

    top12 = genre_counter.most_common(12)
    other = sum(cnt for _, cnt in genre_counter.most_common()[12:])
    labels = [g for g, _ in top12]
    sizes = [cnt for _, cnt in top12]
    if other > 0:
        labels.append("其他")
        sizes.append(other)

    fig, ax = plt.subplots(figsize=(12, 10))
    explode = [0.03] * len(labels)
    explode[-1] = 0.08  # "其他" 稍微突出

    wedges, texts, autotexts = ax.pie(
        sizes, labels=None, autopct="%1.1f%%", startangle=140,
        explode=explode, colors=sns.color_palette("Set3", len(labels)),
        pctdistance=0.82, wedgeprops={"edgecolor": "white", "linewidth": 1}
    )

    # 图例
    legend_labels = [f"{l} ({s}部)" for l, s in zip(labels, sizes)]
    ax.legend(wedges, legend_labels, title="电影类型", loc="center left",
              bbox_to_anchor=(1, 0.5), fontsize=10, title_fontsize=12)

    ax.set_title("豆瓣 Top250 电影类型分布", fontsize=16, fontweight="bold")

    for at in autotexts:
        at.set_fontsize(9)
        at.set_fontweight("bold")

    save_fig(fig, "02_genre_pie.png")


# ---- 5.3 散点图：评分 vs 评论人数 ----
def plot_rating_vs_comments(df: pd.DataFrame):
    """评分与评论人数的散点图 + 回归线。"""
    print("\n[图表3] 评分 vs 评论人数 散点图")
    valid = df[(df["comment_count"] > 0) & df["rating"].notna()].copy()
    valid["log_comment_count"] = np.log10(valid["comment_count"])

    fig, axes = plt.subplots(1, 2, figsize=(16, 7))

    # 左：原始数据
    ax1 = axes[0]
    scatter1 = ax1.scatter(valid["rating"], valid["comment_count"],
                           c=valid["rating"], cmap="RdYlGn", alpha=0.6,
                           edgecolors="grey", linewidths=0.3, s=60)
    ax1.set_xlabel("豆瓣评分", fontsize=12)
    ax1.set_ylabel("评论人数", fontsize=12)
    ax1.set_title("评分 vs 评论人数 (原始坐标)", fontsize=14, fontweight="bold")
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x/1e6:.0f}M"))
    cbar1 = plt.colorbar(scatter1, ax=ax1)
    cbar1.set_label("评分", fontsize=10)

    # 右：log 坐标 + 回归线
    ax2 = axes[1]
    sns.regplot(data=valid, x="rating", y="log_comment_count", ax=ax2,
                scatter_kws={"alpha": 0.5, "s": 50, "color": PALETTE[0],
                             "edgecolors": "grey", "linewidths": 0.2},
                line_kws={"color": "red", "linewidth": 2, "linestyle": "--"},
                ci=95)

    ax2.set_xlabel("豆瓣评分", fontsize=12)
    ax2.set_ylabel("评论人数 (log₁₀)", fontsize=12)
    ax2.set_title("评分 vs log₁₀(评论人数) + 回归线", fontsize=14, fontweight="bold")

    # 标注相关系数
    corr = valid["rating"].corr(valid["log_comment_count"])
    ax2.text(0.05, 0.95, f"Pearson r = {corr:.3f}", transform=ax2.transAxes,
             fontsize=12, verticalalignment="top",
             bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.8))

    plt.suptitle("豆瓣评分与评论人数关系", fontsize=16, fontweight="bold", y=1.01)
    save_fig(fig, "03_rating_vs_comments.png")


# ---- 5.4 短评词云 ----
def plot_wordcloud(comments_df: pd.DataFrame):
    """生成短评词云。"""
    print("\n[图表4] 短评词云")
    texts = comments_df["comment"].dropna().tolist()
    if not texts:
        print("  ⚠ 无短评数据，跳过词云")
        return

    # 合并所有文本
    all_text = " ".join(texts)

    # 加载停用词
    stopwords = set([
        "的", "了", "是", "我", "你", "他", "她", "它", "这", "那",
        "在", "不", "有", "就", "都", "也", "和", "与", "但", "而",
        "很", "要", "会", "可以", "这个", "那个", "一个", "自己",
        "没有", "什么", "怎么", "为什么", "因为", "所以", "如果",
        "还是", "只是", "而且", "虽然", "但是", "然后", "之后",
        "一些", "这些", "那些", "一种", "一样", "还是", "不是",
        "我们", "他们", "她们", "它们", "大家", "觉得", "知道",
        "看到", "感觉", "应该", "可能", "已经", "其实", "真的",
        "有点", "不过", "比较", "非常", "特别", "这么", "那么",
        "还有", "以及", "所有", "时候", "这样", "那样", "现在",
        "今天", "明天", "昨天", "以后", "以前", "一直", "总是",
        "又", "再", "去", "来", "说", "看", "让", "把", "被",
        "从", "到", "对", "向", "跟", "比", "过", "着", "能",
        "更", "只", "还", "才", "便", "却", "得", "所", "中",
        "上", "下", "好", "吧", "吗", "呢", "啊", "哦", "嗯",
        "哈", "呀", "嘛", "呗", "哇", "电影", "这部", "片子",
        "一部", "因为", "所以", "如果", "虽然", "的时候", "豆瓣",
        "评分", "五星", "四星", "三星", "好评", "差评", "推荐",
        "观看", "剧情", "导演", "演员", "角色", "故事", "结局",
        "感觉", "其实", "真的", "就是", "不是", "还是", "有点",
        "真的", "了", "的", "是", "在", "我", "有", "和", "就",
        "不", "人", "都", "一", "一个", "上", "也", "很", "到",
        "说", "要", "去", "你", "会", "着", "没有", "看", "好",
        "自己", "这", "他", "她", "它", "们", "那", "什么",
    ])

    # 分词
    words = jieba.cut(all_text)
    words_filtered = [w.strip() for w in words if len(w.strip()) >= 2
                      and w.strip() not in stopwords]

    if not words_filtered:
        print("  ⚠ 分词后无有效词汇")
        return

    word_freq = Counter(words_filtered)
    print(f"  词云词汇量: {len(word_freq)}")

    # 生成词云
    wc = WordCloud(
        width=1200, height=700,
        background_color="white",
        font_path=_FONT_PATH,  # 使用检测到的中文字体路径
        max_words=200,
        max_font_size=180,
        min_font_size=10,
        collocations=False,
        colormap="viridis",
        random_state=42,
        prefer_horizontal=0.7,
    ).generate_from_frequencies(word_freq)

    fig, ax = plt.subplots(figsize=(14, 8))
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")
    ax.set_title("豆瓣短评词云", fontsize=20, fontweight="bold", pad=20)

    save_fig(fig, "04_comment_wordcloud.png")

    # 额外：Top 20 关键词柱状图
    fig2, ax2 = plt.subplots(figsize=(12, 7))
    top_words = word_freq.most_common(20)
    words_labels = [w for w, _ in top_words]
    words_cnts = [c for _, c in top_words]
    bars = ax2.barh(range(len(words_labels)), words_cnts, color=PALETTE[2], edgecolor="white")
    ax2.set_yticks(range(len(words_labels)))
    ax2.set_yticklabels(words_labels, fontsize=11)
    ax2.invert_yaxis()
    ax2.set_xlabel("词频", fontsize=12)
    ax2.set_title("短评高频词 Top 20", fontsize=16, fontweight="bold")
    for bar, cnt in zip(bars, words_cnts):
        ax2.text(bar.get_width() + max(words_cnts) * 0.01, bar.get_y() + bar.get_height() / 2,
                 str(cnt), va="center", fontsize=10)
    save_fig(fig2, "04_keywords_top20.png")


# ---- 5.5 时间趋势线图 ----
def plot_time_trend(df: pd.DataFrame):
    """按发行年份统计电影数量和平均评分的时间趋势。"""
    print("\n[图表5] 时间趋势线图")
    year_data = df[df["release_year"].notna() & (df["release_year"] > 1900)].copy()
    year_data["release_year"] = year_data["release_year"].astype(int)

    # 按年份聚合
    yearly = year_data.groupby("release_year").agg(
        count=("id", "count"),
        avg_rating=("rating", "mean"),
        total_comments=("comment_count", "sum"),
    ).reset_index()
    yearly = yearly.sort_values("release_year")

    # 过滤年份范围（避免极端值）
    yearly = yearly[(yearly["release_year"] >= 1930) & (yearly["release_year"] <= 2025)]

    print(f"  覆盖年份: {yearly['release_year'].min()} - {yearly['release_year'].max()} ({len(yearly)} 个年份)")

    fig, axes = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

    # 上图：每年电影数量
    ax1 = axes[0]
    ax1.fill_between(yearly["release_year"], yearly["count"], alpha=0.35, color=PALETTE[0])
    ax1.plot(yearly["release_year"], yearly["count"], "o-", color=PALETTE[0],
             linewidth=2, markersize=6, markerfacecolor="white")
    ax1.set_ylabel("电影数量", fontsize=13)
    ax1.set_title("豆瓣 Top250 电影发行年份分布", fontsize=16, fontweight="bold")
    ax1.grid(True, alpha=0.3)

    # 下图：每年平均评分
    ax2 = axes[1]
    ax2.plot(yearly["release_year"], yearly["avg_rating"], "s-", color=PALETTE[2],
             linewidth=2, markersize=7, markerfacecolor="white")
    ax2.fill_between(yearly["release_year"], yearly["avg_rating"], alpha=0.2, color=PALETTE[2])

    # 整体均值线
    overall_mean = year_data["rating"].mean()
    ax2.axhline(overall_mean, color="red", linestyle="--", linewidth=1.5,
                alpha=0.7, label=f"整体均值 ★{overall_mean:.2f}")

    ax2.set_xlabel("发行年份", fontsize=13)
    ax2.set_ylabel("平均评分", fontsize=13)
    ax2.set_title("各年份电影平均评分趋势", fontsize=14, fontweight="bold")
    ax2.legend(fontsize=11)
    ax2.grid(True, alpha=0.3)

    # 标注峰值年份
    peak_year = yearly.loc[yearly["count"].idxmax()]
    ax1.annotate(f"{int(peak_year['release_year'])}年\n{int(peak_year['count'])}部",
                 xy=(peak_year["release_year"], peak_year["count"]),
                 xytext=(10, 20), textcoords="offset points",
                 arrowprops=dict(arrowstyle="->", color="darkred"),
                 fontsize=11, color="darkred", fontweight="bold")

    plt.tight_layout()
    save_fig(fig, "05_time_trend.png")


# ---- 5.6 导演作品数柱状图 ----
def plot_director_bar(df: pd.DataFrame):
    """导演作品数量 Top15 横向柱状图。"""
    print("\n[图表6] 导演作品数 Top15")
    director_counter = Counter()
    for dl in df["director_list"]:
        for d in dl:
            if d and d != "未知":
                director_counter[d] += 1
    top15 = director_counter.most_common(15)

    fig, ax = plt.subplots(figsize=(12, 8))
    names = [d for d, _ in top15]
    counts = [c for _, c in top15]
    colors = sns.color_palette("viridis", len(names))

    bars = ax.barh(range(len(names)), counts, color=colors, edgecolor="white", height=0.7)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=11)
    ax.invert_yaxis()
    ax.set_xlabel("作品数量", fontsize=13)
    ax.set_title("豆瓣 Top250 导演作品数量 Top 15", fontsize=16, fontweight="bold")

    for bar, cnt in zip(bars, counts):
        ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2,
                str(cnt), va="center", fontsize=11, fontweight="bold")
    ax.set_xlim(0, max(counts) + 2)
    save_fig(fig, "06_director_top15.png")


# ---- 5.7 国家/地区分布柱状图 ----
def plot_country_bar(df: pd.DataFrame):
    """国家/地区电影数量分布柱状图。"""
    print("\n[图表7] 国家/地区电影分布")
    country_counter = Counter()
    for c in df["country"]:
        if c and c != "未知":
            for part in str(c).split("/"):
                part = part.strip()
                if part:
                    country_counter[part] += 1
    top15 = country_counter.most_common(15)

    fig, ax = plt.subplots(figsize=(12, 7))
    names = [c for c, _ in top15]
    counts = [cnt for _, cnt in top15]
    colors = sns.color_palette("rocket", len(names))

    bars = ax.bar(names, counts, color=colors, edgecolor="white", width=0.65)
    ax.set_xlabel("国家/地区", fontsize=13)
    ax.set_ylabel("电影数量", fontsize=13)
    ax.set_title("豆瓣 Top250 电影国别/地区分布 Top 15", fontsize=16, fontweight="bold")
    ax.tick_params(axis="x", rotation=30, labelsize=10)

    for bar, cnt in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                str(cnt), ha="center", fontsize=10, fontweight="bold")
    ax.set_ylim(0, max(counts) * 1.15)
    save_fig(fig, "07_country_distribution.png")


# ---- 5.8 片长分布直方图 ----
def plot_runtime_distribution(df: pd.DataFrame):
    """影片时长分布直方图 + KDE。"""
    print("\n[图表8] 影片时长分布")
    runtimes = df[df["runtime"] > 0]["runtime"].dropna()

    fig, ax = plt.subplots(figsize=(10, 6))
    n_bins = 20
    ax.hist(runtimes, bins=n_bins, color=PALETTE[2], edgecolor="white",
            alpha=0.85, density=True, label="频率密度")

    from scipy.stats import gaussian_kde
    kde = gaussian_kde(runtimes)
    x_kde = np.linspace(runtimes.min(), runtimes.max(), 300)
    ax.plot(x_kde, kde(x_kde), color="#e74c3c", linewidth=2.5, label="KDE 密度曲线")

    mean_rt = runtimes.mean()
    ax.axvline(mean_rt, color="red", linestyle="--", linewidth=2,
               label=f"均值 {mean_rt:.0f} 分钟")
    ax.axvline(runtimes.median(), color="orange", linestyle=":", linewidth=2,
               label=f"中位数 {runtimes.median():.0f} 分钟")

    ax.set_xlabel("片长 (分钟)", fontsize=13)
    ax.set_ylabel("频率密度", fontsize=13)
    ax.set_title("豆瓣 Top250 影片时长分布", fontsize=16, fontweight="bold")
    ax.legend(fontsize=11)
    save_fig(fig, "08_runtime_distribution.png")


# ---- 5.9 短评情感环形图 ----
def plot_sentiment_donut(comments_df: pd.DataFrame):
    """短评情感倾向环形图（Donut chart）。"""
    print("\n[图表9] 短评情感环形图")
    scores = comments_df["rating_score"].dropna()
    if len(scores) == 0:
        return

    pos = (scores >= 4).sum()   # 力荐+推荐
    neu = (scores == 3).sum()   # 还行
    neg = (scores <= 2).sum()   # 较差+很差

    labels = ["正面 (力荐+推荐)", "中性 (还行)", "负面 (较差+很差)"]
    sizes = [pos, neu, neg]
    colors = ["#27ae60", "#f39c12", "#e74c3c"]
    explode = (0.02, 0.02, 0.05)

    fig, ax = plt.subplots(figsize=(8, 8))
    wedges, texts, autotexts = ax.pie(
        sizes, labels=None, autopct="%1.1f%%", startangle=90,
        explode=explode, colors=colors, pctdistance=0.75,
        wedgeprops={"edgecolor": "white", "linewidth": 2, "width": 0.45}
    )

    # 中心文字
    total = len(scores)
    ax.text(0, 0.1, f"{pos/total*100:.1f}%", ha="center", va="center",
            fontsize=28, fontweight="bold", color="#27ae60")
    ax.text(0, -0.15, "好评率", ha="center", va="center", fontsize=13, color="gray")
    ax.text(0, -0.35, f"共 {total:,d} 条短评", ha="center", va="center", fontsize=11, color="gray")

    ax.legend(wedges, [f"{l} ({s:,d})" for l, s in zip(labels, sizes)],
              title="情感倾向", loc="center left", bbox_to_anchor=(1, 0.5),
              fontsize=11, title_fontsize=12)
    ax.set_title("豆瓣短评情感倾向分析", fontsize=16, fontweight="bold")

    for at in autotexts:
        at.set_fontsize(11)
        at.set_fontweight("bold")
    save_fig(fig, "09_sentiment_donut.png")


# ---- 5.10 评分与片长关系 ----
def plot_rating_vs_runtime(df: pd.DataFrame):
    """豆瓣评分与影片时长的散点图。"""
    print("\n[图表10] 评分 vs 片长")
    valid = df[(df["runtime"] > 0) & df["rating"].notna()].copy()

    fig, ax = plt.subplots(figsize=(10, 7))
    scatter = ax.scatter(valid["runtime"], valid["rating"],
                         c=valid["rating"], cmap="RdYlGn", alpha=0.6,
                         edgecolors="grey", linewidths=0.3, s=70)

    # 回归线
    sns.regplot(data=valid, x="runtime", y="rating", ax=ax,
                scatter=False, line_kws={"color": "red", "linewidth": 2, "linestyle": "--"},
                ci=95)

    ax.set_xlabel("片长 (分钟)", fontsize=13)
    ax.set_ylabel("豆瓣评分", fontsize=13)
    ax.set_title("评分与片长关系", fontsize=16, fontweight="bold")

    corr = valid["runtime"].corr(valid["rating"])
    ax.text(0.05, 0.05, f"Pearson r = {corr:.3f}", transform=ax.transAxes,
            fontsize=13, bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.8))

    cbar = plt.colorbar(scatter, ax=ax)
    cbar.set_label("评分", fontsize=11)
    save_fig(fig, "10_rating_vs_runtime.png")


# ---- 5.11 类型-年代热力图 ----
def plot_genre_heatmap(df: pd.DataFrame):
    """主要电影类型按年代的分布热力图。"""
    print("\n[图表11] 类型-年代热力图")
    # 选取 Top 10 类型
    genre_counter = Counter()
    for gl in df["genre_list"]:
        for g in gl:
            if g:
                genre_counter[g] += 1
    top_genres = [g for g, _ in genre_counter.most_common(10)]

    # 按年代分组
    valid = df[df["release_year"].notna() & (df["release_year"] > 1900)].copy()
    valid["decade"] = (valid["release_year"] // 10 * 10).astype(int)

    # 构建矩阵
    decades = sorted(valid["decade"].unique())
    matrix = pd.DataFrame(0, index=top_genres, columns=decades)
    for _, row in valid.iterrows():
        decade = int(row["decade"])
        for g in row["genre_list"]:
            if g in top_genres:
                matrix.at[g, decade] += 1

    fig, ax = plt.subplots(figsize=(14, 8))
    sns.heatmap(matrix, annot=True, fmt="d", cmap="YlOrRd", ax=ax,
                linewidths=0.5, linecolor="white", cbar_kws={"label": "电影数量"})
    ax.set_xlabel("年代", fontsize=13)
    ax.set_ylabel("电影类型", fontsize=13)
    ax.set_title("豆瓣 Top250 主要类型 × 年代热力图", fontsize=16, fontweight="bold")
    plt.tight_layout()
    save_fig(fig, "11_genre_decade_heatmap.png")


# ---- 5.12 导演评分气泡图 ----
def plot_director_bubble(df: pd.DataFrame):
    """导演作品数量 vs 平均评分 气泡图。"""
    print("\n[图表12] 导演评分气泡图")
    director_info = defaultdict(list)
    for dl, r, cc in zip(df["director_list"], df["rating"], df["comment_count"]):
        for d in dl:
            if d and d != "未知" and pd.notna(r):
                director_info[d].append({"rating": r, "comments": cc})

    # 筛选至少2部作品的导演
    dir_data = []
    for d, items in director_info.items():
        if len(items) >= 2:
            avg_r = np.mean([it["rating"] for it in items])
            total_cc = sum([it["comments"] for it in items])
            dir_data.append({"director": d, "count": len(items), "avg_rating": avg_r, "total_comments": total_cc})

    dir_df = pd.DataFrame(dir_data).sort_values("count", ascending=False).head(25)

    fig, ax = plt.subplots(figsize=(14, 9))
    sizes = np.log10(dir_df["total_comments"]) * 40
    scatter = ax.scatter(
        dir_df["avg_rating"], dir_df["count"],
        s=sizes, c=dir_df["avg_rating"], cmap="RdYlGn",
        alpha=0.7, edgecolors="grey", linewidths=0.5
    )

    # 标注导演名
    for _, row in dir_df.iterrows():
        ax.annotate(row["director"], (row["avg_rating"], row["count"]),
                    fontsize=8, ha="center", va="bottom",
                    xytext=(0, 6), textcoords="offset points",
                    alpha=0.85)

    ax.set_xlabel("平均评分", fontsize=13)
    ax.set_ylabel("作品数量", fontsize=13)
    ax.set_title("豆瓣 Top250 导演作品数 vs 平均评分 (气泡大小=总评论数)", fontsize=15, fontweight="bold")
    cbar = plt.colorbar(scatter, ax=ax)
    cbar.set_label("平均评分", fontsize=11)
    ax.grid(True, alpha=0.3)
    save_fig(fig, "12_director_bubble.png")


# ---- 5.13 类型评分雷达图 ----
def plot_genre_radar(df: pd.DataFrame):
    """主要电影类型平均评分雷达图。"""
    print("\n[图表13] 类型评分雷达图")
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

    labels = top_genres
    values = [np.mean(genre_ratings[g]) for g in top_genres]
    counts = [len(genre_ratings[g]) for g in top_genres]

    # 雷达图
    N = len(labels)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]  # 闭合
    values_closed = values + values[:1]

    fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(polar=True))
    ax.fill(angles, values_closed, alpha=0.25, color=PALETTE[0])
    ax.plot(angles, values_closed, "o-", color=PALETTE[0], linewidth=2.5, markersize=8)

    # 添加均值圆
    overall_mean = df["rating"].mean()
    ax.axhline(y=overall_mean, color="red", linestyle="--", linewidth=1.5, alpha=0.6,
               label=f"整体均值 ★{overall_mean:.2f}")

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels([f"{l}\n({c}部)" for l, c in zip(labels, counts)], fontsize=10)
    ax.set_ylim(8.0, 9.5)
    ax.set_title("主要电影类型平均评分雷达图", fontsize=16, fontweight="bold", pad=30)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=10)
    ax.grid(True, alpha=0.3)
    save_fig(fig, "13_genre_radar.png")


# ---- 5.14 各年代评分箱线图 ----
def plot_rating_boxplot_by_decade(df: pd.DataFrame):
    """各年代电影评分箱线图。"""
    print("\n[图表14] 各年代评分箱线图")
    valid = df[df["release_year"].notna() & (df["release_year"] > 1900) & df["rating"].notna()].copy()
    valid["decade"] = (valid["release_year"] // 10 * 10).astype(int)
    valid = valid[valid["decade"].between(1930, 2030)]

    decade_order = sorted(valid["decade"].unique())
    box_data = [valid[valid["decade"] == d]["rating"].dropna().values for d in decade_order]

    fig, ax = plt.subplots(figsize=(14, 7))
    bp = ax.boxplot(box_data, patch_artist=True, widths=0.6,
                    medianprops=dict(color="red", linewidth=2),
                    whiskerprops=dict(linewidth=1.2),
                    capprops=dict(linewidth=1.2))

    # 颜色
    colors = sns.color_palette("viridis", len(decade_order))
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.75)

    # 叠加散点
    for i, d in enumerate(decade_order):
        y = valid[valid["decade"] == d]["rating"].dropna()
        x = np.random.normal(i + 1, 0.06, size=len(y))
        ax.scatter(x, y, alpha=0.35, s=20, color="grey", edgecolors="none")

    ax.set_xticklabels([str(d) for d in decade_order], fontsize=11)
    ax.set_xlabel("年代", fontsize=13)
    ax.set_ylabel("豆瓣评分", fontsize=13)
    ax.set_title("各年代电影评分箱线图", fontsize=15, fontweight="bold")

    # 均值连线
    means = [np.mean(d) for d in box_data]
    ax.plot(range(1, len(decade_order) + 1), means, "o-", color="red", linewidth=2,
            markersize=7, markerfacecolor="white", label="各年代均值")
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.2, axis="y")
    save_fig(fig, "14_rating_boxplot_decade.png")


# ---- 5.15 Top 影评人贡献分析 ----
def plot_top_reviewers(comments_df: pd.DataFrame):
    """最有影响力的影评人分析。"""
    print("\n[图表15] Top 影评人贡献分析")
    if len(comments_df) == 0 or "helpful" not in comments_df.columns:
        print("  ⚠ 无影评人数据")
        return

    user_stats = comments_df.groupby("user").agg(
        total_helpful=("helpful", "sum"),
        comment_count=("comment", "count"),
        avg_score=("rating_score", "mean")
    ).reset_index()
    user_stats = user_stats[user_stats["total_helpful"] > 0].sort_values("total_helpful", ascending=False).head(20)

    fig, axes = plt.subplots(1, 2, figsize=(16, 8))

    # 左：最有帮助的影评人 (横向柱状图)
    ax1 = axes[0]
    colors1 = sns.color_palette("YlOrRd", len(user_stats))
    bars = ax1.barh(range(len(user_stats)), user_stats["total_helpful"].values, color=colors1, edgecolor="white")
    ax1.set_yticks(range(len(user_stats)))
    ax1.set_yticklabels(user_stats["user"].values, fontsize=9)
    ax1.invert_yaxis()
    ax1.set_xlabel("总有用数", fontsize=12)
    ax1.set_title("Top 20 最有影响力影评人", fontsize=14, fontweight="bold")

    for bar, val in zip(bars, user_stats["total_helpful"].values):
        ax1.text(bar.get_width() + max(user_stats["total_helpful"]) * 0.01,
                 bar.get_y() + bar.get_height() / 2, f"{val/1000:.0f}k", va="center", fontsize=8)

    # 右：评论数 vs 平均评分
    ax2 = axes[1]
    scatter = ax2.scatter(user_stats["comment_count"], user_stats["avg_score"],
                          s=user_stats["total_helpful"] / 500, c=user_stats["avg_score"],
                          cmap="RdYlGn", alpha=0.7, edgecolors="grey", linewidths=0.5)
    for _, row in user_stats.iterrows():
        ax2.annotate(row["user"], (row["comment_count"], row["avg_score"]),
                     fontsize=7, alpha=0.8, xytext=(3, 3), textcoords="offset points")
    ax2.set_xlabel("评论数", fontsize=12)
    ax2.set_ylabel("平均评分 (1-5)", fontsize=12)
    ax2.set_title("影评人评论数 vs 平均评分", fontsize=14, fontweight="bold")
    ax2.grid(True, alpha=0.3)
    cbar2 = plt.colorbar(scatter, ax=ax2)
    cbar2.set_label("平均评分", fontsize=10)

    plt.suptitle("豆瓣短评影评人贡献分析", fontsize=16, fontweight="bold", y=1.01)
    save_fig(fig, "15_top_reviewers.png")


# ---- 5.16 语言分布 ----
def plot_language_distribution(df: pd.DataFrame):
    """电影语言分布环形图。"""
    print("\n[图表16] 语言分布")
    lang_counter = Counter()
    for lang in df["language"]:
        if lang and lang != "":
            for part in str(lang).split("/"):
                part = part.strip()
                if part:
                    lang_counter[part] += 1

    top = lang_counter.most_common(10)
    other = sum(cnt for _, cnt in lang_counter.most_common()[10:])
    labels = [l for l, _ in top]
    sizes = [cnt for _, cnt in top]
    if other > 0:
        labels.append("其他")
        sizes.append(other)

    fig, ax = plt.subplots(figsize=(10, 10))
    colors = sns.color_palette("Set3", len(labels))
    wedges, texts, autotexts = ax.pie(
        sizes, labels=None, autopct="%1.1f%%", startangle=140,
        colors=colors, pctdistance=0.78,
        wedgeprops={"edgecolor": "white", "linewidth": 1.5, "width": 0.4}
    )

    legend_labels = [f"{l} ({s}部)" for l, s in zip(labels, sizes)]
    ax.legend(wedges, legend_labels, title="语言", loc="center left",
              bbox_to_anchor=(1, 0.5), fontsize=10, title_fontsize=12)

    ax.set_title("豆瓣 Top250 电影语言分布", fontsize=16, fontweight="bold")
    for at in autotexts:
        at.set_fontsize(9)
        at.set_fontweight("bold")
    save_fig(fig, "16_language_donut.png")


# ---- 5.17 片长 vs 评论数 ----
def plot_runtime_vs_comments(df: pd.DataFrame):
    """影片时长与评论人数的散点图。"""
    print("\n[图表17] 片长 vs 评论数")
    valid = df[(df["runtime"] > 0) & (df["comment_count"] > 0)].copy()
    valid["log_comments"] = np.log10(valid["comment_count"])

    fig, ax = plt.subplots(figsize=(11, 7))
    scatter = ax.scatter(valid["runtime"], valid["log_comments"],
                         c=valid["rating"], cmap="RdYlGn", alpha=0.6,
                         edgecolors="grey", linewidths=0.3, s=70)

    # 回归线
    sns.regplot(data=valid, x="runtime", y="log_comments", ax=ax,
                scatter=False, line_kws={"color": "red", "linewidth": 2, "linestyle": "--"},
                ci=95)

    # 标注高分电影
    top5 = valid.nlargest(5, "rating")
    for _, row in top5.iterrows():
        ax.annotate(row["title_cn"][:8], (row["runtime"], row["log_comments"]),
                    fontsize=7, alpha=0.8, xytext=(5, 5), textcoords="offset points",
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="yellow", alpha=0.5))

    ax.set_xlabel("片长 (分钟)", fontsize=13)
    ax.set_ylabel("评论人数 (log₁₀)", fontsize=13)
    ax.set_title("影片时长与评论人数关系", fontsize=15, fontweight="bold")

    corr = valid["runtime"].corr(valid["log_comments"])
    ax.text(0.05, 0.95, f"Pearson r = {corr:.3f}", transform=ax.transAxes,
            fontsize=12, bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.8),
            verticalalignment="top")

    cbar = plt.colorbar(scatter, ax=ax)
    cbar.set_label("评分", fontsize=11)
    save_fig(fig, "17_runtime_vs_comments.png")


# ---- 5.18 评分段类型偏好分析 ----
def plot_rating_tier_genre(df: pd.DataFrame):
    """不同评分段的类型分布对比。"""
    print("\n[图表18] 评分段类型偏好")
    # Top 10 类型
    genre_counter = Counter()
    for gl in df["genre_list"]:
        for g in gl:
            if g:
                genre_counter[g] += 1
    top_genres = [g for g, _ in genre_counter.most_common(10)]

    # 分段
    valid = df[df["rating"].notna()].copy()
    valid["tier"] = pd.cut(valid["rating"], bins=[0, 8.8, 9.2, 10.0],
                           labels=["< 8.8 分", "8.8-9.2 分", "≥ 9.2 分"])

    # 每个分段中各类型数量
    tier_genre = defaultdict(lambda: defaultdict(int))
    tier_total = defaultdict(int)
    for _, row in valid.iterrows():
        tier = row["tier"]
        tier_total[tier] += 1
        for g in row["genre_list"]:
            if g in top_genres:
                tier_genre[tier][g] += 1

    tiers_order = ["< 8.8 分", "8.8-9.2 分", "≥ 9.2 分"]
    # 计算百分比
    x = np.arange(len(top_genres))
    width = 0.25
    fig, ax = plt.subplots(figsize=(14, 7))
    colors_tier = [PALETTE[0], PALETTE[1], PALETTE[2]]

    for i, tier in enumerate(tiers_order):
        pcts = [tier_genre[tier][g] / tier_total[tier] * 100 if tier_total[tier] > 0 else 0
                for g in top_genres]
        bars = ax.bar(x + i * width, pcts, width, label=tier, color=colors_tier[i], edgecolor="white")

    ax.set_xticks(x + width)
    ax.set_xticklabels(top_genres, fontsize=10, rotation=20, ha="right")
    ax.set_ylabel("占比 (%)", fontsize=13)
    ax.set_title("不同评分段电影类型偏好对比", fontsize=15, fontweight="bold")
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.2, axis="y")
    save_fig(fig, "18_rating_tier_genre.png")


# ---- 5.19 额外可视化：Plotly 交互图 ----
def plot_plotly_interactive(df: pd.DataFrame):
    """使用 Plotly 生成交互式图表。"""
    if not HAS_PLOTLY:
        print("\n[Plotly] 未安装 plotly，跳过交互式图表。")
        return

    print("\n[图表6] Plotly 交互式图表")

    # 6.1 评分分布 + 箱线图
    fig1 = go.Figure()
    fig1.add_trace(go.Box(
        y=df["rating"].dropna(),
        name="评分箱线图",
        marker_color="steelblue",
        boxmean="sd"
    ))
    fig1.update_layout(
        title="豆瓣 Top250 评分箱线图",
        yaxis_title="评分",
        height=500,
    )
    fp1 = os.path.join(OUTPUT_DIR, "06_plotly_box.html")
    fig1.write_html(fp1)
    print(f"  ✓ 已保存: {fp1}")

    # 6.2 各国电影数量 (交互式柱状图)
    country_counter = Counter()
    for c in df["country"]:
        if c and c != "未知":
            for part in str(c).split("/"):
                part = part.strip()
                if part:
                    country_counter[part] += 1
    top_countries = country_counter.most_common(15)
    fig2 = go.Figure(go.Bar(
        x=[cnt for _, cnt in top_countries],
        y=[c for c, _ in top_countries],
        orientation="h",
        marker=dict(
            color=[cnt for _, cnt in top_countries],
            colorscale="Portland",
            showscale=True,
            colorbar=dict(title="电影数"),
        ),
        text=[cnt for _, cnt in top_countries],
        textposition="outside",
    ))
    fig2.update_layout(
        title="豆瓣 Top250 电影国别分布",
        xaxis_title="电影数量",
        height=550,
        yaxis=dict(autorange="reversed"),
    )
    fp2 = os.path.join(OUTPUT_DIR, "06_plotly_country.html")
    fig2.write_html(fp2)
    print(f"  ✓ 已保存: {fp2}")

    # 6.3 评分与评论数交互散点图
    valid = df[(df["comment_count"] > 0) & df["rating"].notna()].copy()
    fig3 = px.scatter(
        valid,
        x="rating",
        y="comment_count",
        size="comment_count",
        color="rating",
        hover_name="title_cn",
        hover_data=["director", "genres", "release_year"],
        title="评分 vs 评论人数 (可交互)",
        labels={"rating": "豆瓣评分", "comment_count": "评论人数"},
        color_continuous_scale="RdYlGn",
        log_y=True,
        height=600,
    )
    fp3 = os.path.join(OUTPUT_DIR, "06_plotly_scatter.html")
    fig3.write_html(fp3)
    print(f"  ✓ 已保存: {fp3}")


# ====================================================================
#  主流程
# ====================================================================

def main():
    print("=" * 60)
    print("  豆瓣电影 Top250 数据分析")
    print("=" * 60)
    print(f"  数据源: {DATA_FILE}")
    print(f"  输出目录: {OUTPUT_DIR}")

    # 1. 加载数据
    df = load_data(DATA_FILE)

    # 2. 数据清洗
    df = clean_data(df)

    # 3. 提取短评
    comments_df = extract_comments(df)

    # 4. 统计分析
    stats = statistics(df, comments_df)

    # 5. 可视化
    print("\n" + "=" * 60)
    print("  可视化图表生成")
    print("=" * 60)

    plot_rating_distribution(df)
    plot_genre_pie(df)
    plot_rating_vs_comments(df)
    plot_wordcloud(comments_df)
    plot_time_trend(df)
    plot_director_bar(df)
    plot_country_bar(df)
    plot_runtime_distribution(df)
    plot_sentiment_donut(comments_df)
    plot_rating_vs_runtime(df)
    plot_genre_heatmap(df)
    plot_director_bubble(df)
    plot_genre_radar(df)
    plot_rating_boxplot_by_decade(df)
    plot_top_reviewers(comments_df)
    plot_language_distribution(df)
    plot_runtime_vs_comments(df)
    plot_rating_tier_genre(df)
    plot_plotly_interactive(df)

    # 6. 导出清洗后数据
    print("\n[导出] 清洗后数据")
    export_cols = ["id", "rank", "title_cn", "title_en", "rating", "comment_count",
                   "genres", "director", "country", "language", "release_date",
                   "release_year", "runtime", "imdb", "created_at"]
    export_df = df[[c for c in export_cols if c in df.columns]].copy()
    csv_path = os.path.join(OUTPUT_DIR, "cleaned_movies.csv")
    export_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"  ✓ 已保存: {csv_path}")

    # 导出清洗后短评
    if len(comments_df) > 0:
        comment_csv = os.path.join(OUTPUT_DIR, "cleaned_comments.csv")
        comments_df.to_csv(comment_csv, index=False, encoding="utf-8-sig")
        print(f"  ✓ 已保存: {comment_csv}")

    # 汇总报告
    print("\n" + "=" * 60)
    print("  分析完成！")
    print("=" * 60)
    print(f"\n生成文件列表:")
    for f in sorted(os.listdir(OUTPUT_DIR)):
        fpath = os.path.join(OUTPUT_DIR, f)
        size_kb = os.path.getsize(fpath) / 1024
        print(f"  [{size_kb:>7.1f} KB]  {f}")
    print(f"\n所有文件位于: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()

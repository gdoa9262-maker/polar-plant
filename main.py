# main.py
import io
import os

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

st.set_page_config(page_title="극지식물 생육 분석", layout="wide")

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR&display=swap');
html, body, [class*="css"] {
   font-family: 'Noto Sans KR', 'Malgun Gothic', sans-serif;
}
</style>
""",
    unsafe_allow_html=True,
)

# ---------- 데이터 로딩 ----------
@st.cache_data
def load_env(path):
    if path is None:
        return pd.DataFrame()
    encs = ("utf-8-sig", "cp949")
    for enc in encs:
        try:
            return pd.read_csv(path, encoding=enc, dtype=str)
        except Exception:
            pass
    return pd.DataFrame()


def std_cols(df):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    rename = {}
    for c in df.columns:
        k = c.lower().replace(" ", "")
        if k in ("time", "categories", "시간", "날짜", "datetime", "date"):
            rename[c] = "time"
        elif k in ("temperature", "온도"):
            rename[c] = "temperature"
        elif k in ("humidity", "습도"):
            rename[c] = "humidity"
        elif k == "ph":
            rename[c] = "ph"
        elif k == "ec":
            rename[c] = "ec"
        elif "생중량" in k:
            rename[c] = "생중량"
        elif "잎" in k:
            rename[c] = "잎 수"
        elif "지상부" in k and "길이" in k:
            rename[c] = "지상부 길이"
        elif "지하부" in k and "길이" in k:
            rename[c] = "지하부 길이"
        elif "지상부" in k and ("질량" in k or "무게" in k):
            rename[c] = "지상부 질량"
        elif "지하부" in k and ("질량" in k or "무게" in k):
            rename[c] = "지하부 질량"
        elif "개체" in k:
            rename[c] = "개체번호"
    df = df.rename(columns=rename)
    for c in df.columns:
        if c in ("time", "개체번호"):
            continue
        if not pd.api.types.is_numeric_dtype(df[c]):
            num = pd.to_numeric(
                df[c].astype(str).str.replace(",", "").str.extract(r"(-?\d+\.?\d*)")[0],
                errors="coerce",
            )
            if num.notna().mean() >= 0.5:
                df[c] = num
    if "생중량" not in df.columns and {"지상부 질량", "지하부 질량"} <= set(df.columns):
        df["생중량"] = df["지상부 질량"] + df["지하부 질량"]
    if "time" in df.columns:
        t = df["time"].astype(str).str.strip()
        parsed = pd.to_datetime(t, errors="coerce", format="mixed")
        bad = parsed.isna() & t.str.match(r"^\d{8}_\d{1,2}$")
        if bad.any():
            parts = t[bad].str.split("_", expand=True)
            parsed[bad] = pd.to_datetime(parts[0], format="%Y%m%d") + pd.to_timedelta(
                parts[1].astype(int), unit="h"
            )
        df["time"] = parsed
    return df


def read_csv(file):
    data = file.getvalue()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return pd.read_csv(io.BytesIO(data), encoding=enc)
        except Exception:
            pass
    return pd.DataFrame()


# ---------- 앱 시작 ----------
st.title("🌱 우리 학교 극지식물 개체별 생육 차이 분석")

env_raw = st.sidebar.file_uploader("환경 CSV", type="csv")
growth_raw = st.sidebar.file_uploader("생육 CSV", type="csv")

school_name = "익명"
for f in (env_raw, growth_raw):
    if f is not None:
        name = os.path.basename(f.name)
        base = name.split("_")[0] if "_" in name else name
        if base != "익명":
            school_name = base

env_df = None
growth_df = None
with st.spinner("데이터 로딩 중..."):
    if env_raw is not None:
        env_df = std_cols(read_csv(env_raw))
    if growth_raw is not None:
        growth_df = std_cols(read_csv(growth_raw))

st.sidebar.caption(f"학교명: {school_name}")

st.sidebar.markdown("### 생육 측정 항목 선택")
growth_metrics = ["잎 수", "지상부 길이", "지하부 길이"]
selected_metrics = []
for m in growth_metrics:
    if m in growth_df.columns if growth_df is not None else False:
        if st.sidebar.checkbox(f"{m} 비교하기", value=True):
            selected_metrics.append(m)
    else:
        selected_metrics.append(m)

tabs = st.tabs(["📖 실험 개요", "🌡️ 환경 데이터", "📊 생육 결과"])


# ============ Tab 1 ============
with tabs[0]:
    try:
        st.markdown("## 연구 배경 및 목적")
        st.write(
            """
우리 학교 극지식물은 같은 환경에서도 개체마다 생육 상태가 달라질 수 있습니다.
이 대시보드는 학생들이 업로드한 환경 데이터와 생육 결과 데이터를 바탕으로
개체별 생중량 분포를 살펴보고, 잎 수·지상부 길이와 생중량의 관계를 확인합니다.

- **평균**: 여러 값을 더해 개수로 나눈 대표값
- **표준편차**: 값들이 평균 주변에 얼마나 퍼져 있는지 나타내는 값
- **CV(변동계수)**: 표준편차를 평균으로 나눈 값, 서로 다른 규모의 비교에 사용
- **상관계수**: 두 변수가 함께 움직이는 정도(−1 ~ 1), 0에 가까우면 관계가 약함
"""
        )

        # 데이터 요약
        total_n = len(growth_df) if growth_df is not None and not growth_df.empty else 0
        if env_df is not None and not env_df.empty:
            t_col = "time" if "time" in env_df.columns else None
            if t_col:
                t_s = env_df[t_col].dropna()
                period = f"{t_s.min().date()} ~ {t_s.max().date()}" if len(t_s) else "측정 기간 확인 불가"
            else:
                period = "시간 열 없음"
            env_cols = [c for c in ["temperature", "humidity", "ph", "ec"] if c in env_df.columns]
            env_items = ", ".join(env_cols) if env_cols else "환경 항목 없음"
        else:
            period = "환경 데이터 없음"
            env_items = "환경 데이터 없음"

        growth_cols = [c for c in growth_metrics + ["생중량"] if c in (growth_df.columns if growth_df is not None else [])]
        growth_items = ", ".join(growth_cols) if growth_cols else "생육 항목 없음"

        st.markdown("### 데이터 요약")
        rows = []
        rows.append(["개체 수", f"{total_n}개"])
        rows.append(["측정 기간", period])
        rows.append(["환경 측정 항목", env_items])
        rows.append(["생육 측정 항목", growth_items])
        st.table(pd.DataFrame(rows, columns=["항목", "내용"]))

        # 주요 지표 카드
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("총 개체수", f"{total_n}개" if total_n else "데이터 없음")
        with col2:
            t_vals = env_df["temperature"].dropna() if env_df is not None and "temperature" in env_df.columns else pd.Series(dtype=float)
            if len(t_vals) >= 2:
                st.metric("평균 온도", f"{t_vals.mean():.1f} °C")
            else:
                st.metric("평균 온도", "데이터 부족")
        with col3:
            h_vals = env_df["humidity"].dropna() if env_df is not None and "humidity" in env_df.columns else pd.Series(dtype=float)
            if len(h_vals) >= 2:
                st.metric("평균 습도", f"{h_vals.mean():.1f} %")
            else:
                st.metric("평균 습도", "데이터 부족")
        with col4:
            g_vals = growth_df["생중량"].dropna() if growth_df is not None and "생중량" in growth_df.columns else pd.Series(dtype=float)
            if len(g_vals) >= 2:
                st.metric("평균 생중량", f"{g_vals.mean():.2f} g")
            else:
                st.metric("평균 생중량", "데이터 부족")
    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")


# ============ Tab 2 ============
with tabs[1]:
    try:
        if env_df is None or env_df.empty:
            st.info("환경 CSV를 업로드하면 환경 데이터가 표시됩니다.")
        else:
            st.markdown("## 환경 데이터 요약")
            env_numeric = {}
            for c in ["temperature", "humidity", "ph", "ec"]:
                if c in env_df.columns:
                    v = pd.to_numeric(env_df[c], errors="coerce").dropna()
                    if len(v) >= 2:
                        env_numeric[c] = {
                            "평균": round(float(v.mean()), 3),
                            "최소": round(float(v.min()), 3),
                            "최대": round(float(v.max()), 3),
                        }
            if env_numeric:
                env_ts = pd.DataFrame(env_numeric).T
                env_ts.index.name = "항목"
                st.dataframe(env_ts, width="stretch")
            else:
                st.info("계산 가능한 환경 수치 열이 없습니다.")

            # 일별 시계열
            if "time" not in env_df.columns:
                st.info("환경 데이터에 시간 열이 없어 시계열을 그릴 수 없습니다.")
            else:
                daily = env_df.set_index("time").resample("D").mean(numeric_only=True)
                daily = daily.reset_index()
                env_line_cols = [c for c in ["temperature", "humidity", "ph", "ec"] if c in daily.columns]
                if not env_line_cols:
                    st.info("일별 평균을 계산할 환경 수치 열이 없습니다.")
                else:
                    line_figs = []
                    for c in env_line_cols:
                        unit = {"temperature": "°C", "humidity": "%", "ph": "", "ec": "mS/cm"}.get(c, "")
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(x=daily["time"], y=daily[c], mode="lines", name=c))
                        fig.update_layout(
                            title=f"{c.replace('_',' ')} 변화",
                            xaxis_title="날짜",
                            yaxis_title=f"{c} {unit}" if unit else c,
                            font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"),
                            margin=dict(l=40, r=20, t=40, b=40),
                            hovermode="x unified",
                        )
                        line_figs.append(fig)

                    if len(line_figs) == 1:
                        st.plotly_chart(line_figs[0], width="stretch")
                    elif len(line_figs) == 2:
                        fig = make_subplots(rows=1, cols=2, subplot_titles=[f['layout']['title']['text'] for f in line_figs])
                        for i, f in enumerate(line_figs, start=1):
                            for tr in f.data:
                                fig.add_trace(tr, row=1, col=i)
                        fig.update_layout(font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"), margin=dict(l=40, r=20, t=40, b=40))
                        st.plotly_chart(fig, width="stretch")
                    else:
                        fig = make_subplots(rows=2, cols=2, subplot_titles=[f['layout']['title']['text'] for f in line_figs])
                        pos = [(1, 1), (1, 2), (2, 1), (2, 2)]
                        for f, (r, c) in zip(line_figs, pos):
                            for tr in f.data:
                                fig.add_trace(tr, row=r, col=c)
                        fig.update_layout(font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"), margin=dict(l=40, r=20, t=40, b=40))
                        st.plotly_chart(fig, width="stretch")

            with st.expander("📄 환경 데이터 원본 테이블"):
                st.dataframe(env_df, width="stretch")
                csv_bytes = env_df.to_csv(index=False).encode("utf-8-sig")
                st.download_button("CSV 다운로드", csv_bytes, file_name="환경데이터.csv", mime="text/csv")
    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")


# ============ Tab 3 ============
def growth_bar_chart(df, col):
    v = df[col].dropna()
    if len(v) < 2:
        return None
    order = v.sort_values(ascending=False)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=order.index.astype(str), y=order.values, marker_color="#6366f1"))
    mean_v = float(v.mean())
    fig.add_hline(y=mean_v, line_dash="dash", line_color="orange", annotation_text=f"평균 {mean_v:.2f}")
    fig.update_layout(
        title=f"개체별 {col.replace('_',' ')} 비교",
        xaxis_title="개체",
        yaxis_title=col.replace("_", " "),
        font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"),
        margin=dict(l=40, r=20, t=40, b=40),
        hovermode="x unified",
    )
    return fig


def growth_dist_chart(df, col):
    v = df[[col, "개체번호"]].dropna().copy() if "개체번호" in df.columns else df[[col]].dropna()
    if len(v) < 2:
        return None
    fig = go.Figure()
    fig.add_trace(go.Box(y=v[col], fillcolor="#10b981", boxmean=True))
    mean_v = float(v[col].mean())
    fig.add_hline(y=mean_v, line_dash="dash", line_color="orange", annotation_text=f"평균 {mean_v:.2f}")
    fig.update_layout(
        title=f"{col.replace('_',' ')} 분포",
        xaxis_title="",
        yaxis_title=col.replace("_", " "),
        font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"),
        margin=dict(l=40, r=20, t=40, b=40),
        hovermode="x unified",
    )
    return fig


def scatter_with_trend(df, xcol, ycol):
    d = df[[xcol, ycol]].dropna()
    if len(d) < 2:
        return None
    x = d[xcol].astype(float).values
    y = d[ycol].astype(float).values
    slope, intercept = np.polyfit(x, y, 1)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=y, mode="markers", marker=dict(color="#8b5cf6", size=8), name="개체"))
    xs = np.linspace(float(x.min()), float(x.max()), 50)
    fig.add_trace(go.Scatter(x=xs, y=slope * xs + intercept, mode="lines", line=dict(color="orange", width=2), name=f"추세선(기울기={slope:.3f})"))
    r = float(np.corrcoef(x, y)[0, 1])
    fig.update_layout(
        title=f"{xcol.replace('_',' ')} vs {ycol.replace('_',' ')}",
        xaxis_title=xcol.replace("_", " "),
        yaxis_title=ycol.replace("_", " "),
        font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"),
        margin=dict(l=40, r=20, t=40, b=40),
        hovermode="x unified",
        legend=dict(orientation="h", y=1.02, x=0.5, xanchor="center"),
    )
    fig.add_annotation(text=f"상관계수 r = {r:.3f}", xref="paper", yref="paper", x=0.02, y=0.98, showarrow=False, font=dict(size=12))
    return fig


with tabs[2]:
    try:
        if growth_df is None or growth_df.empty:
            st.info("생육 CSV를 업로드하면 생육 결과가 표시됩니다.")
        else:
            col1, col2 = st.columns(2)
            with col1:
                g_vals = growth_df["생중량"].dropna() if "생중량" in growth_df.columns else pd.Series(dtype=float)
                if len(g_vals) >= 2:
                    mean_g = float(g_vals.mean())
                    max_idx = g_vals.idxmax()
                    min_idx = g_vals.idxmin()
                    st.markdown("### 🥇 핵심 결과 카드")
                    st.metric("평균 생중량", f"{mean_g:.2f} g")
                    st.caption(f"최대 개체: {growth_df.loc[max_idx, '개체번호'] if '개체번호' in growth_df.columns else max_idx}, {float(g_vals.max()):.2f} g")
                    st.caption(f"최소 개체: {growth_df.loc[min_idx, '개체번호'] if '개체번호' in growth_df.columns else min_idx}, {float(g_vals.min()):.2f} g")
                else:
                    st.info("생중량 데이터가 부족해 카드를 표시할 수 없습니다.")

            with col2:
                if "생중량" in growth_df.columns:
                    stats = g_vals.dropna()
                    if len(stats) >= 2:
                        mad = float(stats.std())
                        cv = mad / float(stats.mean()) if float(stats.mean()) != 0 else float("nan")
                        st.markdown("### 생육 분포 요약")
                        drows = []
                        drows.append(["평균(g)", f"{stats.mean():.2f}"])
                        drows.append(["표준편차(g)", f"{mad:.2f}"])
                        drows.append(["CV", f"{cv:.3f}" if not np.isnan(cv) else "N/A"])
                        st.table(pd.DataFrame(drows, columns=["지표", "값"]))
                    else:
                        st.info("생중량 데이터가 부족해 요약 통계를 표시할 수 없습니다.")

            st.markdown("## 개체별 생육 비교")

            charts = []
            if "생중량" in growth_df.columns:
                charts.append(growth_bar_chart(growth_df, "생중량"))
            for m in selected_metrics:
                if m in growth_df.columns:
                    charts.append(growth_bar_chart(growth_df, m))
            for fig in charts:
                if fig is not None:
                    st.plotly_chart(fig, width="stretch")
                else:
                    st.info(f"{m if m != '생중량' else '생중량'} 그래프에 사용할 데이터가 부족합니다.")

            st.markdown("## 생중량 분포")
            dist_fig = growth_dist_chart(growth_df, "생중량") if "생중량" in growth_df.columns else None
            if dist_fig is not None:
                st.plotly_chart(dist_fig, width="stretch")
            else:
                st.info("생중량 분포 그래프를 그릴 데이터가 부족합니다.")

            st.markdown("## 상관관계 분석")
            corr_pairs = []
            if "생중량" in growth_df.columns:
                for m in selected_metrics + (["생중량"] if "생중량" in selected_metrics else []):
                    if m != "생중량" and m in growth_df.columns:
                        corr_pairs.append((m, "생중량"))
            if not corr_pairs:
                st.info("상관관계를 계산할 생육 항목 쌍이 없습니다.")
            for x, y in corr_pairs:
                fig = scatter_with_trend(growth_df, x, y)
                if fig is not None:
                    st.plotly_chart(fig, width="stretch")
                else:
                    st.info(f"{x} vs {y} 산점도를 그릴 데이터가 부족합니다.")

            with st.expander("📄 생육 데이터 원본 테이블"):
                st.dataframe(growth_df, width="stretch")
                csv_bytes = growth_df.to_csv(index=False).encode("utf-8-sig")
                st.download_button("CSV 다운로드", csv_bytes, file_name="생육결과.csv", mime="text/csv")
    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")

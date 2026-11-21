# main.py
import io
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

st.set_page_config(page_title="극지식물 재배 환경 비교", layout="wide")

# ---------- 한글 폰트 CSS ----------
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


# ---------- CSV 읽기 (인코딩 대응) ----------
@st.cache_data
def read_upload(raw_file):
    """업로드된 파일을 utf-8-sig → cp949 순으로 읽고 std_cols 적용"""
    if raw_file is None:
        return None
    data = raw_file.getvalue()
    for enc in ("utf-8-sig", "cp949"):
        try:
            df = pd.read_csv(io.BytesIO(data), encoding=enc)
            return std_cols(df)
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
        elif "지하부" in k and ("길이" in k or k == "지하부길이"):
            rename[c] = "지하부 길이"
        elif "지상부" in k and ("질량" in k or "무게" in k):
            rename[c] = "지상부 질량"
        elif "지하부" in k and ("질량" in k or "무게" in k):
            rename[c] = "지하부 질량"
        elif k in ("지하부길이",):
            rename[c] = "지하부 길이"
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


# ---------- 사이드바 ----------
st.title("토양재배와 수경재배 환경이 극지식물의 생육 특성에 미치는 영향은 무엇일까?")

st.sidebar.markdown("### 업로드할 데이터 선택")
env_raw = st.sidebar.file_uploader("환경 CSV", type="csv")
growth_raw = st.sidebar.file_uploader("생육 CSV", type="csv")

school_name = "익명"
for f in (env_raw, growth_raw):
    if f is not None:
        name = os.path.basename(f.name)
        if "_" in name:
            base = name.split("_")[0]
        elif "." in name:
            base = name.rsplit(".", 1)[0]
        else:
            base = name
        if base and base != "익명":
            school_name = base

st.sidebar.caption(f"학교명: {school_name}")
st.sidebar.info(
    "예제 데이터를 바로 보려면 아래 '예제 데이터 불러오기'를 눌러 주세요. "
    "직접 업로드한 CSV가 있으면 업로드 파일이 우선 사용됩니다."
)

use_sample = st.sidebar.checkbox("예제 데이터 불러오기", value=False)

if use_sample:
    with st.spinner("예제 데이터를 불러오는 중..."):
        env_df = std_cols(
            pd.read_csv(
                "/home/user/uploads/0___________.csv.csv",
                encoding="utf-8-sig",
                dtype=str,
            )
        )
        growth_df = std_cols(
            pd.read_csv(
                "/home/user/uploads/1_____________.csv.csv",
                encoding="utf-8-sig",
                dtype=str,
            )
        )
        growth_df2 = std_cols(
            pd.read_csv(
                "/home/user/uploads/2____________.csv",
                encoding="utf-8-sig",
                dtype=str,
            )
        )
else:
    with st.spinner("데이터 로딩 중..."):
        env_df = read_upload(env_raw)
        growth_df = read_upload(growth_raw)
        growth_df2 = None

# 생육 데이터 2개가 모두 있을 때는 합쳐서 하나로 사용
if growth_df is not None and growth_df2 is not None and not growth_df.empty and not growth_df2.empty:
    growth_all = pd.concat([growth_df, growth_df2], ignore_index=True)
elif growth_df is not None and not growth_df.empty:
    growth_all = growth_df
elif growth_df2 is not None and not growth_df2.empty:
    growth_all = growth_df2
else:
    growth_all = pd.DataFrame()

st.sidebar.markdown("### 생육 측정 항목 선택")
growth_metric_keys = ["잎 수", "지상부 길이", "지하부 길이"]
selected_metrics = []
for m in growth_metric_keys:
    present = m in growth_all.columns if growth_all is not None and not growth_all.empty else False
    if present and st.sidebar.checkbox(f"{m} 비교하기", value=True):
        selected_metrics.append(m)
    elif not present:
        selected_metrics.append(m)

tabs = st.tabs(["📖 주제 및 가설", "🌡️ 환경·생육 데이터 비교", "📊 재배 적합성 검토"])


# ---------- 공통 헬퍼 ----------
def plotly_font(fig):
    fig.update_layout(
        font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif"),
        margin=dict(l=40, r=20, t=40, b=40),
        hovermode="x unified",
    )


def bar_chart(df, col, mean_line=True):
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    if len(s) < 2:
        return None
    order = s.sort_values(ascending=False)
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=order.index.astype(str),
            y=order.values,
            marker_color="#6366f1",
        )
    )
    if mean_line:
        mean_v = float(s.mean())
        fig.add_hline(
            y=mean_v,
            line_dash="dash",
            line_color="orange",
            annotation_text=f"평균 {mean_v:.2f}",
        )
    fig.update_layout(
        title=f"개체별 {col.replace('_',' ')} 비교",
        xaxis_title="개체",
        yaxis_title=col.replace("_", " "),
    )
    plotly_font(fig)
    return fig


def dist_chart(df, col):
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    if len(s) < 2:
        return None
    fig = go.Figure()
    fig.add_trace(go.Box(y=s, fillcolor="#10b981", boxmean=True))
    mean_v = float(s.mean())
    fig.add_hline(
        y=mean_v,
        line_dash="dash",
        line_color="orange",
        annotation_text=f"평균 {mean_v:.2f}",
    )
    fig.update_layout(
        title=f"{col.replace('_',' ')} 분포",
        xaxis_title="",
        yaxis_title=col.replace("_", " "),
    )
    plotly_font(fig)
    return fig


def scatter_trend(df, xcol, ycol):
    d = pd.DataFrame(
        {
            xcol: pd.to_numeric(df[xcol], errors="coerce"),
            ycol: pd.to_numeric(df[ycol], errors="coerce"),
        }
    ).dropna()
    if len(d) < 2:
        return None
    x = d[xcol].values.astype(float)
    y = d[ycol].values.astype(float)
    slope, intercept = np.polyfit(x, y, 1)
    r = float(np.corrcoef(x, y)[0, 1])
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y,
            mode="markers",
            marker=dict(color="#8b5cf6", size=8),
            name="개체",
        )
    )
    xs = np.linspace(float(x.min()), float(x.max()), 50)
    fig.add_trace(
        go.Scatter(
            x=xs,
            y=slope * xs + intercept,
            mode="lines",
            line=dict(color="orange", width=2),
            name=f"추세선(기울기={slope:.3f})",
        )
    )
    fig.update_layout(
        title=f"{xcol.replace('_',' ')} vs {ycol.replace('_',' ')}",
        xaxis_title=xcol.replace("_", " "),
        yaxis_title=ycol.replace("_", " "),
    )
    fig.add_annotation(
        text=f"상관계수 r = {r:.3f}",
        xref="paper",
        yref="paper",
        x=0.02,
        y=0.98,
        showarrow=False,
        font=dict(size=12),
    )
    fig.update_layout(
        legend=dict(orientation="h", y=1.02, x=0.5, xanchor="center")
    )
    plotly_font(fig)
    return fig


# ============ Tab 1 ============
with tabs[0]:
    try:
        st.markdown("## 연구 주제")
        st.write(
            """
극지식물을 **토양재배**와 **수경재배** 환경에서 키웠을 때
온도와 습도 같은 환경 조건이 생육 특성(잎 수, 지상부 길이, 지하부 길이, 생중량)에
어떤 차이를 만드는지 비교하는 탐구입니다.

이 대시보드에는 아래 데이터가 포함되어 있습니다.
"""
        )
        info_rows = []
        info_rows.append(["강화여고 환경 데이터", f"{len(env_df) if env_df is not None and not env_df.empty else 0}개 시점"])
        info_rows.append(["강화여고 생육 데이터", f"{len(growth_df) if growth_df is not None and not growth_df.empty else 0}개체"])
        info_rows.append(["강화중 생육 데이터", f"{len(growth_df2) if growth_df2 is not None and not growth_df2.empty else 0}개체"])
        info_rows.append(["통합 생육 데이터", f"{len(growth_all) if growth_all is not None and not growth_all.empty else 0}개체"])
        st.table(pd.DataFrame(info_rows, columns=["데이터", "규모"]))

        st.markdown("## 연구 가설")
        hyps = [
            (
                "가설 1: 온도와 광조건이 잎 수에 미치는 영향",
                "상대적으로 높은 기온과 제어된 광조건은 식물의 대사 활동을 촉진하여 "
                "잎 수(수경재배 평균 32.17장)를 토양재배(평균 21.73장)보다 "
                "유의미하게 증가시키는 원인이 될 것이다.",
            ),
            (
                "가설 2: 상대습도와 지하부 길이의 관계",
                "높은 상대습도에서는 식물이 수분 스트레스를 덜 받아 지하부 길이가 짧아지고, "
                "상대습도가 낮은 환경에서는 수분을 찾아 뿌리가 깊이 뻗으므로 지하부 길이가 길어질 것이다.",
            ),
            (
                "가설 3: 낮은 습도와 잎의 형태적 적응",
                "상대습도가 낮은 환경 조건에서는 증산 작용을 조절하기 위해 잎이 "
                "수경재배 특유의 두껍고 조밀한 형태적 구조를 형성할 것이다.",
            ),
        ]
        for title, body in hyps:
            st.markdown(f"### {title}")
            st.write(body)

        st.markdown("### 통계 용어 안내")
        st.write(
            """
- **평균**: 여러 값을 더해 개수로 나눈 대표값
- **표준편차**: 값들이 평균 주변에 얼마나 퍼져 있는지 나타내는 값
- **CV(변동계수)**: 표준편차를 평균으로 나눈 값, 서로 다른 규모의 비교에 사용
- **상관계수**: 두 변수가 함께 움직이는 정도(−1 ~ 1), 0에 가까우면 관계가 약함
- **유의미하다**: 우연이라고 보기 어려울 정도로 차이나 관계가 뚜렷한 상태
- **증산 작용**: 식물 잎의 기공으로 수분이 증발하는 현상
"""
        )
    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")


# ============ Tab 2 ============
with tabs[1]:
    try:
        # --- 환경 요약 ---
        st.markdown("## 환경 데이터 요약")
        if env_df is None or env_df.empty:
            st.info("환경 CSV를 업로드하면 환경 요약이 표시됩니다.")
        else:
            env_summary_cols = []
            for c in ["temperature", "humidity", "ph", "ec"]:
                if c in env_df.columns:
                    v = pd.to_numeric(env_df[c], errors="coerce").dropna()
                    if len(v) >= 2:
                        env_summary_cols.append(
                            pd.Series(
                                {
                                    "평균": round(float(v.mean()), 3),
                                    "최소": round(float(v.min()), 3),
                                    "최대": round(float(v.max()), 3),
                                },
                                name=c,
                            )
                        )
            if env_summary_cols:
                env_ts = pd.DataFrame(env_summary_cols).T
                env_ts.index.name = "항목"
                st.dataframe(env_ts, width="stretch")
            else:
                st.info("계산 가능한 환경 수치 열이 없습니다.")

        # --- 생육 요약 ---
        st.markdown("## 생육 데이터 요약")
        if growth_all is None or growth_all.empty:
            st.info("생육 CSV를 업로드하면 생육 요약이 표시됩니다.")
        else:
            g_summary = {}
            for c in growth_metric_keys + ["생중량"]:
                if c in growth_all.columns:
                    v = pd.to_numeric(growth_all[c], errors="coerce").dropna()
                    if len(v) >= 2:
                        g_summary[c] = {
                            "평균": round(float(v.mean()), 3),
                            "최소": round(float(v.min()), 3),
                            "최대": round(float(v.max()), 3),
                        }
            if g_summary:
                g_ts = pd.DataFrame(g_summary).T
                g_ts.index.name = "항목"
                st.dataframe(g_ts, width="stretch")
            else:
                st.info("계산 가능한 생육 수치 열이 없습니다.")

        # --- 환경 시계열 (일별 평균) ---
        st.markdown("## 환경 시계열 (일별 평균)")
        if env_df is None or env_df.empty or "time" not in env_df.columns:
            st.info("환경 CSV에 시간 열이 있어야 일별 평균을 그릴 수 있습니다.")
        else:
            env_df_t = env_df.copy()
            env_df_t["time"] = pd.to_datetime(env_df_t["time"], errors="coerce")
            daily = (
                env_df_t.set_index("time")
                .resample("D")
                .mean(numeric_only=True)
                .reset_index()
            )
            env_line_cols = [c for c in ["temperature", "humidity", "ph", "ec"] if c in daily.columns]
            if not env_line_cols:
                st.info("일별 평균을 계산할 환경 수치 열이 없습니다.")
            else:
                figs = []
                for c in env_line_cols:
                    unit = {"temperature": "°C", "humidity": "%", "ph": "", "ec": "mS/cm"}.get(c, "")
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=daily["time"], y=daily[c], mode="lines", name=c))
                    fig.update_layout(title=f"{c.replace('_',' ')} 변화")
                    ylab = f"{c} {unit}" if unit else c
                    fig.update_yaxes(title=ylab)
                    fig.update_xaxes(title="날짜")
                    plotly_font(fig)
                    figs.append(fig)

                if len(figs) == 1:
                    st.plotly_chart(figs[0], width="stretch")
                else:
                    subplot_titles = [f["layout"]["title"]["text"] for f in figs]
                    if len(figs) == 2:
                        fig = make_subplots(rows=1, cols=2, subplot_titles=subplot_titles)
                        for i, f in enumerate(figs, start=1):
                            for tr in f.data:
                                fig.add_trace(tr, row=1, col=i)
                    else:
                        nrows = len(figs) // 2 + (len(figs) % 2)
                        fig = make_subplots(rows=nrows, cols=2, subplot_titles=subplot_titles)
                        positions = []
                        for r in range(1, nrows + 1):
                            for c in range(1, 3):
                                positions.append((r, c))
                        for f, (r, c) in zip(figs, positions):
                            for tr in f.data:
                                fig.add_trace(tr, row=r, col=c)
                    plotly_font(fig)
                    st.plotly_chart(fig, width="stretch")

        # --- 환경 변수 사분면 (온도 vs 습도) ---
        st.markdown("## 환경 변수 사분면 (온도 vs 습도)")
        if env_df is None or env_df.empty or "temperature" not in env_df.columns or "humidity" not in env_df.columns:
            st.info("환경 데이터에 온도와 습도 열이 모두 있어야 사분면을 그릴 수 있습니다.")
        else:
            te = pd.to_numeric(env_df["temperature"], errors="coerce").dropna()
            hu = pd.to_numeric(env_df["humidity"], errors="coerce").dropna()
            if len(te) < 2 or len(hu) < 2:
                st.info("온도와 습도 데이터 수가 부족해 사분면을 그릴 수 없습니다.")
            else:
                df_q = pd.DataFrame({"temperature": te.values, "humidity": hu.values})
                if len(df_q) != len(te):
                    df_q = df_q.dropna()
                if len(df_q) < 2:
                    st.info("온도와 습도를 함께 가진 데이터가 부족해 사분면을 그릴 수 없습니다.")
                else:
                    te_mean = float(df_q["temperature"].mean())
                    hu_mean = float(df_q["humidity"].mean())
                    fig = go.Figure()
                    fig.add_trace(
                        go.Scatter(
                            x=df_q["temperature"],
                            y=df_q["humidity"],
                            mode="markers",
                            marker=dict(color="#3b82f6", size=6, opacity=0.7),
                            name="측정값",
                        )
                    )
                    fig.add_hline(y=hu_mean, line_dash="dot", line_color="gray")
                    fig.add_vline(x=te_mean, line_dash="dot", line_color="gray")
                    fig.add_annotation(
                        text=f"온도 평균 {te_mean:.1f}°C",
                        x=te_mean,
                        y=df_q["humidity"].max(),
                        showarrow=False,
                        yanchor="top",
                    )
                    fig.add_annotation(
                        text=f"습도 평균 {hu_mean:.1f}%",
                        x=df_q["temperature"].max(),
                        y=hu_mean,
                        showarrow=False,
                        xanchor="right",
                    )
                    fig.update_layout(
                        title="환경 변수 사분면 — 온도와 습도의 분포",
                        xaxis_title="온도 (°C)",
                        yaxis_title="습도 (%)",
                    )
                    plotly_font(fig)
                    st.plotly_chart(fig, width="stretch")
                    st.caption(
                        f"점선은 온도와 습도의 평균입니다. "
                        f"평균보다 높은 값은 오른쪽/위쪽, 낮은 값은 왼쪽/아래쪽에 모입니다."
                    )

        # --- 산점도: 생육 항목 vs 생중량 (추세선) ---
        st.markdown("## 생육 데이터 산점도 (생중량과의 관계)")
        if growth_all is None or growth_all.empty or "생중량" not in growth_all.columns:
            st.info("생육 데이터에 생중량 열이 있어야 산점도를 그릴 수 있습니다.")
        else:
            scatter_pairs = []
            for m in selected_metrics:
                if m != "생중량" and m in growth_all.columns:
                    scatter_pairs.append((m, "생중량"))
            if not scatter_pairs:
                st.info("산점도를 그릴 생육 항목 쌍이 없습니다.")
            for xcol, ycol in scatter_pairs:
                fig = scatter_trend(growth_all, xcol, ycol)
                if fig is not None:
                    st.plotly_chart(fig, width="stretch")
                else:
                    st.info(f"{xcol} vs {ycol} 산점도를 그릴 데이터가 부족합니다.")

        # --- 토양·수경재배 비교용: 재배 방식 구분 열이 있으면 그룹별 요약 ---
        st.markdown("## 재배 방식별 생육 비교 (데이터에 방식 열이 있을 때)")
        if growth_all is None or growth_all.empty:
            st.info("생육 데이터가 있어야 이 비교를 할 수 있습니다.")
        else:
            mode_col = None
            for candidate in ["재배방식", "재배방식", "방식", "mode", "group", "그룹", "재배"]:
                if candidate in growth_all.columns:
                    mode_col = candidate
                    break
            if mode_col is not None:
                mode_vals = growth_all[mode_col].astype(str).str.strip()
                groups = []
                for mv in mode_vals.unique():
                    if mv == "" or mv.lower() == "nan":
                        continue
                    sub = growth_all[mode_vals == mv]
                    row = {"재배방식": mv, "개체수": len(sub)}
                    for c in growth_metric_keys + ["생중량"]:
                        if c in sub.columns:
                            v = pd.to_numeric(sub[c], errors="coerce").dropna()
                            if len(v) >= 2:
                                row[c] = round(float(v.mean()), 3)
                            else:
                                row[c] = None
                    groups.append(row)
                if groups:
                    comp_df = pd.DataFrame(groups)
                    st.dataframe(comp_df, width="stretch")
                    st.caption("재배방식 구분 열이 있는 학교 데이터에서만 표시됩니다.")
                else:
                    st.info("재배방식 열의 값이 비어 있어 비교할 수 없습니다.")
            else:
                st.info("생육 데이터에 재배방식 구분 열이 없습니다. 업로드한 CSV에 '재배방식' 열이 있으면 자동으로 비교됩니다.")

        # --- 원본 테이블 + 다운로드 ---
        if env_df is not None and not env_df.empty:
            with st.expander("📄 환경 데이터 원본 테이블"):
                st.dataframe(env_df, width="stretch")
                st.download_button(
                    "환경 CSV 다운로드",
                    env_df.to_csv(index=False).encode("utf-8-sig"),
                    file_name="환경데이터.csv",
                    mime="text/csv",
                )
        if growth_all is not None and not growth_all.empty:
            with st.expander("📄 생육 데이터 원본 테이블"):
                st.dataframe(growth_all, width="stretch")
                st.download_button(
                    "생육 CSV 다운로드",
                    growth_all.to_csv(index=False).encode("utf-8-sig"),
                    file_name="생육결과.csv",
                    mime="text/csv",
                )
    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")


# ============ Tab 3 ============
with tabs[2]:
    try:
        st.markdown("## 재배 목적에 따른 토양·수경재배의 적합성 검토")
        st.write(
            """
이 탭은 업로드된 데이터를 바탕으로 토양재배와 수경재배 환경의 특성을 정리한 것입니다.
실제 데이터에서 재배 방식을 구분하는 열이 없는 경우에는
**업로드된 생육 데이터 전체의 분포**를 기준으로 해석합니다.
"""
        )

        # --- 환경 조건별 요약 (환경 데이터에 재배 방식 열이 있을 때) ---
        st.markdown("### 환경 조건별 요약")
        if env_df is None or env_df.empty:
            st.info("환경 데이터가 있어야 환경 조건별 요약을 볼 수 있습니다.")
        else:
            env_mode_col = None
            for candidate in ["재배방식", "재배방식", "방식", "mode", "group", "그룹"]:
                if candidate in env_df.columns:
                    env_mode_col = candidate
                    break
            if env_mode_col is not None and "temperature" in env_df.columns and "humidity" in env_df.columns:
                env_mode = env_df[env_mode_col].astype(str).str.strip()
                grp = (
                    env_df.assign(
                        temperature=pd.to_numeric(env_df["temperature"], errors="coerce"),
                        humidity=pd.to_numeric(env_df["humidity"], errors="coerce"),
                    )
                    .groupby(env_mode)
                    .agg(
                        개체수=("temperature", "size"),
                        평균온도=("temperature", "mean"),
                        평균습도=("humidity", "mean"),
                    )
                    .reset_index()
                )
                grp["평균온도"] = grp["평균온도"].round(1)
                grp["평균습도"] = grp["평균습도"].round(1)
                st.dataframe(grp, width="stretch")
                st.caption("환경 데이터에 재배 방식 구분 열이 있을 때만 표시됩니다.")
            else:
                st.info("환경 데이터에 재배 방식 구분 열이 없거나 필요한 환경 열이 없습니다.")

        # --- 생육 분포 요약 (전체 개체) ---
        st.markdown("### 생육 분포 요약 (전체 개체)")
        if growth_all is None or growth_all.empty:
            st.info("생육 데이터를 업로드하면 생육 분포 요약이 표시됩니다.")
        else:
            g_stats = {}
            for c in growth_metric_keys + ["생중량"]:
                if c in growth_all.columns:
                    v = pd.to_numeric(growth_all[c], errors="coerce").dropna()
                    if len(v) >= 2:
                        g_stats[c] = {
                            "평균": round(float(v.mean()), 3),
                            "표준편차": round(float(v.std()), 3),
                            "최소": round(float(v.min()), 3),
                            "최대": round(float(v.max()), 3),
                        }
            if g_stats:
                gs_df = pd.DataFrame(g_stats).T
                gs_df.index.name = "항목"
                st.dataframe(gs_df, width="stretch")
            else:
                st.info("계산 가능한 생육 수치 열이 없습니다.")

        # --- 개체별 생중량 비교 (상위·하위 강조) ---
        st.markdown("### 개체별 생중량 비교 (상위·하위 강조)")
        if growth_all is None or growth_all.empty or "생중량" not in growth_all.columns:
            st.info("생육 데이터에 생중량 열이 있어야 이 그래프를 그릴 수 있습니다.")
        else:
            g = pd.to_numeric(growth_all["생중량"], errors="coerce").dropna()
            if len(g) < 2:
                st.info("생중량 데이터 수가 부족해 그래프를 그릴 수 없습니다.")
            else:
                order = g.sort_values(ascending=False)
                mean_v = float(g.mean())
                colors = []
                for idx in order.index:
                    val = float(order[idx])
                    if val >= mean_v * 1.1:
                        colors.append("#22c55e")
                    elif val <= mean_v * 0.9:
                        colors.append("#ef4444")
                    else:
                        colors.append("#6366f1")
                fig = go.Figure()
                fig.add_trace(
                    go.Bar(
                        x=order.index.astype(str),
                        y=order.values,
                        marker_color=colors,
                    )
                )
                fig.add_hline(
                    y=mean_v,
                    line_dash="dash",
                    line_color="orange",
                    annotation_text=f"평균 {mean_v:.2f} g",
                )
                fig.update_layout(
                    title="개체별 생중량 비교",
                    xaxis_title="개체",
                    yaxis_title="생중량 (g)",
                )
                plotly_font(fig)
                st.plotly_chart(fig, width="stretch")
                st.caption(
                    "초록색은 평균보다 10% 이상 높은 개체, 빨간색은 10% 이상 낮은 개체, "
                    "보라색은 평균 근처 개체입니다."
                )

        # --- 해석 안내 ---
        st.markdown("### 해석 안내")
        st.write(
            """
- 온도와 습도가 함께 높은 구간에서는 잎 수와 지상부 길이가 커지는 경향이 나타날 수 있습니다.
- 상대습도가 낮은 환경에서는 지하부 길이가 상대적으로 길어지는 패턴이 나타날 수 있습니다.
- 수경재배처럼 온도와 광조건이 제어된 환경에서는 잎 수가 많고 생중량이 큰 개체가 많이 나타날 수 있습니다.

이 해석은 업로드된 데이터의 분포를 바탕으로 한 일반적인 안내이며,
재배 방식 구분 열이 있을 때만 토양재배·수경재배를 직접 비교할 수 있습니다.
"""
        )
    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")

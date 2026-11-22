from pathlib import Path
import matplotlib.pyplot as plt


def generate_charts(
    tg_results: dict,
    ye_results: dict,
    output_dir: Path,
) -> list:
    """블로그 및 리포트 첨부용 차트 2종 생성"""
    output_dir.mkdir(parents=True, exist_ok=True)
    saved_files = []

    plt.style.use("seaborn-v0_8-whitegrid")

    tg_series = tg_results.get("yearly_series", {})
    if tg_series.get("years") and tg_results.get("tg_week_avg_vol_change_pct") is not None:
        fig, ax = plt.subplots(figsize=(11, 4.8), dpi=150)
        years = tg_series["years"]
        vol_chg = tg_series["vol_change_pct"]
        ax.plot(years, vol_chg, color="#1f4e78", linewidth=1.3, alpha=0.85, label="Thanksgiving Week Vol Change (%)")
        ax.axhline(
            tg_results["tg_week_avg_vol_change_pct"],
            color="#c00000",
            linestyle="--",
            linewidth=1.5,
            label=f"Mean: {tg_results['tg_week_avg_vol_change_pct']}%",
        )
        ax.axhline(0, color="black", linewidth=0.8, alpha=0.5)
        ax.set_title("S&P 500 Thanksgiving Week Volume Change vs 20D Avg (%)", fontsize=12, fontweight="bold")
        ax.set_xlabel("Year")
        ax.set_ylabel("Volume Change (%)")
        ax.legend(loc="best")
        fig.tight_layout()
        p1 = output_dir / "chart_thanksgiving_volume.png"
        fig.savefig(p1)
        plt.close(fig)
        saved_files.append(str(p1))

    ye_series = ye_results.get("yearly_index_series", {})
    if ye_series.get("years"):
        fig, ax = plt.subplots(figsize=(11, 4.8), dpi=150)
        years = ye_series["years"]
        spread = ye_series["spread_pct"]
        colors = ["#2e7d32" if s >= 0 else "#c62828" for s in spread]
        ax.bar(years, spread, color=colors, alpha=0.8, width=0.65, label="KOSPI - KOSDAQ Spread (%p)")
        ax.axhline(0, color="black", linewidth=0.9)
        ax.set_title(f"Year-End ({ye_results.get('window', '11-20~12-26')}) KOSPI vs KOSDAQ Return Spread (%p)", fontsize=12, fontweight="bold")
        ax.set_xlabel("Year")
        ax.set_ylabel("Return Spread (%p)")
        ax.legend(loc="best")
        fig.tight_layout()
        p2 = output_dir / "chart_yearend_spread.png"
        fig.savefig(p2)
        plt.close(fig)
        saved_files.append(str(p2))

    return saved_files

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd
import plotly.graph_objects as go


def value_format(value, pos=None):
    """
    Formats numeric values into human-readable strings
    using K (thousands), M (millions), and B (billions).

    Parameters:
        value : float
            Numeric value to format.
        pos : int, optional
            Tick position (required by matplotlib, not used here).

    Returns
    -------
    str
        Formatted string representation of the number.
    """
    value = float(value)
    n = abs(value)
    if n >= 1_000_000_000:
        return f"{value/1_000_000_000:.2f}B"
    elif n >= 1_000_000:
        return f"{ value/1_000_000:.2f}M"
    elif n >= 1_000:
        return f"{ value/1_000:.2f}K"
    else:
        return f"{ value:.0f}"



def plot_history_and_forecast_plotly(
    df_inventory: pd.DataFrame,
    inv_col: str,
    start_date: pd.Timestamp,
    inp,
    p2_5, 
    p50, 
    p97_5, 
    paths
):

    df_inv = df_inventory.copy()

    if not pd.api.types.is_datetime64_any_dtype(df_inv["inventory_date"]):
        df_inv["inventory_date"] = pd.to_datetime(df_inv["inventory_date"])

    df_inv = df_inv.sort_values("inventory_date")

    # Create connected versions by prepending last actual point
    last_actual_date = df_inv["inventory_date"].iloc[-1]
    last_actual_value = df_inv[inv_col].iloc[-1]

    fc_dates = pd.date_range(start=start_date, periods=inp.horizon_days + 1, freq="D")
    fc_dates_connected = np.concatenate([[last_actual_date], fc_dates])
    p50_connected = np.concatenate([[last_actual_value], p50])
    p2_5_connected = np.concatenate([[last_actual_value], p2_5])
    p97_5_connected = np.concatenate([[last_actual_value], p97_5])
    forecast_end = fc_dates.max()




    ACTUAL_COLOR = "blue"
    FORECAST_COLOR = "orange"
    LIMIT_COLOR = "red"
    PLANNING_COLOR = "gray"

    fig = go.Figure()

    # -------------------------
    # MEDIAN + PLANNING
    # -------------------------

    fig.add_trace(go.Scatter(
        x=fc_dates_connected,
        y=p50_connected,
        mode="lines",
        name="Forecast Median (P50)",
        line=dict(color=FORECAST_COLOR, dash="dot")
    ))

    # -------------------------
    # ONE RANDOM SIMULATION
    # -------------------------

    rng = np.random.default_rng(42)   # create generator with seed
    rand_idx = rng.integers(paths.shape[0])  # generate random index
    random_path = paths[rand_idx]
    random_path_connected = np.concatenate([[last_actual_value], random_path])
    
    fig.add_trace(go.Scatter(
        x=fc_dates_connected,
        y=random_path_connected,
        mode="lines",
        name="One Realization",
        line=dict(color=ACTUAL_COLOR, dash="dot")
    ))

  
    # -------------------------
    # FORECAST INTERVAL (95%)
    # -------------------------
    fig.add_trace(go.Scatter(
        x=fc_dates_connected,
        y=p97_5_connected,
        line=dict(width=0),
        showlegend=False
    ))

    fig.add_trace(go.Scatter(
        x=fc_dates_connected,
        y=p2_5_connected,
        fill='tonexty',
        fillcolor= "rgba(255, 140, 0, 0.3)",
        line=dict(width=0),
        name="Forecast Interval (95%)"
    ))


    # -------------------------
    # HISTORICAL
    # -------------------------
    fig.add_trace(go.Scatter(
        x=df_inv["inventory_date"],
        y=df_inv[inv_col],
        mode="lines",
        name="Actual",
        line=dict(color=ACTUAL_COLOR)
    ))

    # -------------------------
    # MIN / MAX LINES
    # -------------------------
    fig.add_shape(
        type="line",
        x0=start_date,
        x1=forecast_end,
        y0=inp.MAX,
        y1=inp.MAX,
        line=dict(color=LIMIT_COLOR, width=1.5)
    )

    fig.add_shape(
        type="line",
        x0=start_date,
        x1=forecast_end,
        y0=inp.MIN,
        y1=inp.MIN,
        line=dict(color=LIMIT_COLOR, width=1.5)
    )
    # -------------------------
    # LAYOUT
    # -------------------------
    fig.update_layout(
        title=dict(
            text=(
                f"{inp.item_no} - {inp.description}"
                "<br>"
                "<span style='font-size:14px; color:gray;'>"
                "This data is mock and AI-generated for demonstration purposes."
                "</span>"
            ),
            font=dict(size=24)
        ),
        xaxis_title="Date",
        yaxis_title="Inventory Level",
        legend=dict(
            orientation="v",
            x=1.02,
            y=0.9
        ),
        height=700,
        margin=dict(r=150)  # space for legend
    )

    return fig



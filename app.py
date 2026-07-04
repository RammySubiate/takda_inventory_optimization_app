import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
import plotly.express as px
import plotly.graph_objects as go
import importlib

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(page_title="Takda", layout="wide")

st.markdown("""
<style>
div[data-baseweb="select"] > div {
    color: black;
    border-color: gray;
}
div.stButton > button:hover,
button[kind="secondaryFormSubmit"]:hover,
div[data-testid="stForm"] button:hover {
    background-color: white !important;
    color: black !important;
}
</style>
""", unsafe_allow_html=True)


# =========================
# LOAD PROJECT MODULES
# =========================
PROJECT_ROOT = Path(__file__).resolve().parent

from lib import metrics, plots, vectorization
importlib.reload(metrics)
importlib.reload(plots)
importlib.reload(vectorization)

logo_path_main = str(PROJECT_ROOT / "assets" / "takda_logo.png")
st.image(logo_path_main, width=500)


# =========================
# CACHED DATA LOADERS     
# =========================

if "entity" not in st.session_state:
    st.session_state.entity = None

chosen_entity = st.selectbox("Select an Entity", options=["--Select--", 
                                                          "Analytical Laboratory Department", 
                                                          "Maintenance Department",
                                                          "Engineering Department"], 
                                                         index=0)


if chosen_entity != "--Select--":
    st.session_state.entity = chosen_entity

if st.session_state.entity is None:
    st.info("Please Select an Entity.")
    st.stop()


# =========================
# RESET ITEM WHEN ENTITY CHANGES  
# =========================
if "prev_entity" not in st.session_state:
    st.session_state.prev_entity = None\

if st.session_state.entity != st.session_state.prev_entity:
    st.session_state.item_ok = False
    st.session_state.item = None
    st.session_state.prev_entity = st.session_state.entity
    ######
    st.session_state.edited_receipt_dates = None
    st.session_state.run_simulation = False  
    ######

if st.session_state.entity == "Analytical Laboratory Department":
    ENTITY = "laboratory"
if st.session_state.entity == "Maintenance Department":
    ENTITY = "maintenance"
if st.session_state.entity == "Engineering Department":
    ENTITY = "engineering"


@st.cache_data(show_spinner=False)
def get_items(entity: str):
    path = PROJECT_ROOT / "transformed_data" / f"{entity}_classification.csv"
    df_item_classification = pd.read_csv(path)

    path = PROJECT_ROOT / "transformed_data" / f"{entity}_daily_inventory.csv"
    df_inventory = pd.read_csv(path)
    df_inventory["inventory_date"] = pd.to_datetime(df_inventory["inventory_date"], errors="coerce")

    path = PROJECT_ROOT / "transformed_data" / f"{entity}_consumption.csv"
    df_consumption = pd.read_csv(path)
    df_consumption["consumption_date"] = pd.to_datetime(df_consumption["consumption_date"], errors="coerce")

    path = PROJECT_ROOT / "transformed_data" / f"{entity}_lead_time.csv"
    df_lead_time = pd.read_csv(path)
    
    path = PROJECT_ROOT / "transformed_data" / f"{entity}_yearly_metrics.csv"
    df_yearly_metrics = pd.read_csv(path)

    path = PROJECT_ROOT / "transformed_data" / f"{entity}_po_status.csv"
    df_po_status_base = pd.read_csv(path)

    return (df_item_classification, 
            df_inventory, 
            df_consumption, 
            df_lead_time, 
            df_yearly_metrics,
            df_po_status_base)


(df_item_classification,
    df_inventory, 
    df_consumption, 
    df_lead_time, 
    df_yearly_metrics,
    df_po_status_base) = get_items(ENTITY)
# =========================
# UI: LOGOS
# =========================

logo_path_sidebar = str(PROJECT_ROOT / "assets" / "tagline.png")
st.sidebar.image(logo_path_sidebar, width="stretch")

# =========================
# SIDEBAR: ITEM SELECTION
# =========================
st.sidebar.header("Select an Item")
# Safe session state defaults
if "item_ok" not in st.session_state:
    st.session_state.item_ok = False
if "item" not in st.session_state:
    st.session_state.item = None

movement_class_selected = st.sidebar.multiselect(
    "Movement Class",
    options=sorted(df_item_classification["movement_class"].dropna().unique().tolist())[0:3],
    default=["A", "B", "C"],
    help="""
    **Movement Class**

    Based on the number of months with consumption over the last 12 months.

    - **A** – Movement in 10–12 months
    - **B** – Movement in 6–9 months
    - **C** – Movement in 3–5 months
    """
)

value_class_selected = st.sidebar.multiselect(
    "Value Class",
    options=sorted(df_item_classification["value_class"].dropna().unique().tolist()),
    default=["A", "B", "C"],
    help="""
    **Value Class**

    Based on cumulative on-hand inventory value (ABC Analysis).

    - **A** – Top 80% of inventory value
    - **B** – Next 15% (80–95%)
    - **C** – Remaining 5% (>95%)
    """
)

item_dict = {}
item_selected_now = None
disable_select = True

if len(movement_class_selected) == 0:
    st.sidebar.warning("Please select at least one Movement Class.")

elif len(value_class_selected) == 0:
    st.sidebar.warning("Please select at least one Value Class.")

else:
    type_selected = df_item_classification[
        (df_item_classification["movement_class"].isin(movement_class_selected)) &
        (df_item_classification["value_class"].isin(value_class_selected))
    ]

    df_temp = (
        type_selected[["item_no", "description"]]
        .dropna()
        .drop_duplicates()
        .sort_values(["item_no", "description"])
        .reset_index(drop=True)
    )

    for _, row in df_temp.iterrows():
        label = f'{row["item_no"]} - {row["description"]}'
        item_dict[label] = row["item_no"]

    if len(item_dict) == 0:
        st.sidebar.warning("No items found for this Movement/Value class.")
    else:
        disable_select = False
        option_labels = list(item_dict.keys())
        option_values = list(item_dict.values())

        default_index = 0
        if st.session_state.item in option_values:
            default_index = option_values.index(st.session_state.item)

        item_selected_now = st.sidebar.selectbox(
            "Item",
            options=option_labels,
            index=default_index
        )

select_item = st.sidebar.button("Select", disabled=disable_select, type="primary")

if select_item and item_selected_now is not None:
    st.session_state.item = item_dict[item_selected_now]
    st.session_state.item_ok = True
    ######
    st.session_state.edited_receipt_dates = None
    st.session_state.run_simulation = False
    #####

if not st.session_state.item_ok:
    st.info("Select an item, then click **Select**.")
    st.stop()

item_selected = st.session_state.item

# =========================
# SIDEBAR: DATE RANGE
# =========================
st.sidebar.header("Year Range")

df_yearly_metrics = df_yearly_metrics[df_yearly_metrics["item_no"] == item_selected]
min_allowed = (df_yearly_metrics["year"].min())
max_allowed = (df_yearly_metrics["year"].max())

if "min_year" not in st.session_state:
    st.session_state.min_year = min_allowed
if "max_year" not in st.session_state:
    st.session_state.max_year = max_allowed

with st.sidebar.form("year_form"):
    if "year_item" not in st.session_state:
        st.session_state.year_item = None

    if st.session_state.year_item != item_selected:
        st.session_state.min_year = min_allowed
        st.session_state.max_year = max_allowed
        st.session_state.year_item = item_selected

    min_year_ui = st.selectbox(
        "Min Year",
       options=sorted(df_yearly_metrics["year"].tolist()),
       index=0
    )
    max_year_ui = st.selectbox(
        "Max Year",
        options=sorted(df_yearly_metrics["year"].tolist()),
        index=(len(df_yearly_metrics["year"].tolist())) - 1
    )

    apply_dates = st.form_submit_button("Apply Dates", type="primary")

if apply_dates:
    if min_year_ui > max_year_ui:
        st.sidebar.error("Min date must be <= Max date.")
    else:
        st.session_state.min_year = min_year_ui
        st.session_state.max_year = max_year_ui

# =========================
# SIDEBAR: SIMULATION SETTINGS
# =========================
st.sidebar.header("Simulation Settings")
# if "kpi_monthly_util" not in st.session_state:
#     st.session_state.kpi_monthly_util = 20
with st.sidebar.form("forecast_form"):
    lead_time_percentile = st.slider("Lead time percentile", 10, 100, 80, 10)
    lead_time_manual = st.number_input("Lead time (days):", value=0, step=1,
            help="""
            Choose how the lead time is determined.

            - Unchecked: Uses the selected lead time percentile.
            - Checked: Allows you to manually enter the lead time in days.
            """
    )
    manual_mode = st.checkbox("Use manual Lead Time")



    min_year = st.session_state.min_year
    max_year = st.session_state.max_year

    # Inventory history
    df_item_inventory = df_inventory[df_inventory["item_no"] == item_selected]
    df_item_inventory["year"] = df_item_inventory["inventory_date"].dt.year

    df_item_inventory = df_item_inventory[df_item_inventory["year"] >= min_year]

    df_yearly_metrics_window = (df_yearly_metrics[(df_yearly_metrics["year"] >= min_year) &
                         (df_yearly_metrics["year"] <= max_year)]
    )

    
    # Calculation of DOH and Monntly Utilization
    # Calculated ahead of time so Monthly utilization can be shown in the side bar

    monthly_utilization = metrics.calculate_monthly_utilization(df_yearly_metrics_window)
    average_doh = metrics.calculate_doh(df_yearly_metrics_window)
    doh = df_item_inventory["inventory_level"].iloc[-1] / (monthly_utilization / 30)
   

    min_level = st.slider("MIN Inventory (Months of Demand)", 1, 24, 2, 1)
    max_level = st.slider("MAX Inventory (Months of Demand)", 1, 24, 6, 1)

    min_level = monthly_utilization * min_level
    max_level = monthly_utilization * max_level

    col1, col2 = st.columns(2)
    col1.metric("MIN Inventory (Units)", f"{plots.value_format(min_level)}")
    col2.metric("MAX Inventory (Units)", f"{plots.value_format(max_level)}")

    n_sims = st.selectbox("Simulations", options=[10, 1000, 2000, 5000, 10000, 20000], index=4)
    horizon_days = st.slider("Horizon (days)", min_value=30, max_value=3650, value=365, step=10)
    run_forecast = st.form_submit_button("Run Forecast", type="primary")

# =========================
# RUN GATE
# =========================
# First time: require Run Forecast
# After first run: allow toggles to update plot without rerunning simulation
# if not run_forecast:
#     st.info("Adjust parameters on the left, then click **Run Forecast**.")
#     st.stop()

# if max_level <= min_level:
#     st.error("MAX must be greater than MIN.")
#     st.stop()

# =========================
# RUN SIMULATION ONLY WHEN BUTTON PRESSED
# =========================
# if run_forecast:
#     with st.spinner("Running simulation..."):

# =========================
# RUN GATE
# =========================
if "run_simulation" not in st.session_state:
    st.session_state.run_simulation = False

if run_forecast:
    st.session_state.run_simulation = True

if not st.session_state.run_simulation:
    st.info("Adjust parameters on the left, then click **Run Forecast**.")
    st.stop()

if max_level <= min_level:
    st.error("MAX must be greater than MIN.")
    st.stop()


@st.fragment
def open_po_editor():
    # Read from session state
    frag_open_po_no = st.session_state.get("frag_open_po_no", np.array([]))
    frag_open_po_dates = st.session_state.get("frag_open_po_dates", np.array([]))
    frag_open_po_receipt_dates = st.session_state.get("frag_open_po_receipt_dates", np.array([]))
    frag_open_po_qty = st.session_state.get("frag_open_po_qty", np.array([]))

    st.markdown("<br><br>", unsafe_allow_html=True)
    st.caption("""Update delivery dates or quantities based on supplier confirmation. 
        Split into partial deliveries or add entries as needed.  \nClick Re-run to update.""")


    with st.expander("⚙️Manage Open POs"):
        if len(frag_open_po_dates) > 0:
            df_open_po_edit = pd.DataFrame({
                "PO NO": list(frag_open_po_no),
                "ORDER DATE": pd.to_datetime(frag_open_po_dates),
                "RECEIPT DATE": pd.to_datetime(frag_open_po_receipt_dates),
                "QUANTITY": frag_open_po_qty.astype(int),
            })
        else:
            df_open_po_edit = pd.DataFrame({
                "PO NO": pd.Series(dtype="str"),
                "ORDER DATE": pd.Series(dtype="datetime64[ns]"),
                "RECEIPT DATE": pd.Series(dtype="datetime64[ns]"),
                "QUANTITY": pd.Series(dtype="int"),
            })

        edited_open_po = st.data_editor(
            df_open_po_edit,
            column_config={
                "PO NO": st.column_config.TextColumn("PO NO"),
                "ORDER DATE": st.column_config.DateColumn("ORDER DATE"),
                "RECEIPT DATE": st.column_config.DateColumn("RECEIPT DATE"),
                "QUANTITY": st.column_config.NumberColumn("QUANTITY"),
            },
            num_rows="dynamic",
            hide_index=True,
            key="open_po_editor"
        )

        if st.button("Re-run", type="primary"):
            cleaned = edited_open_po.dropna(subset=["RECEIPT DATE", "QUANTITY"])
            st.session_state.edited_receipt_dates = pd.to_datetime(cleaned["RECEIPT DATE"]).values
            st.session_state.edited_qty = cleaned["QUANTITY"].values.astype(float)
            st.session_state.edited_open_po_dates = pd.to_datetime(cleaned["ORDER DATE"]).values
            st.session_state.edited_open_po_no = cleaned["PO NO"].values
            st.session_state.run_simulation = True
            st.rerun()



# =========================
# RUN SIMULATION
# =========================
with st.spinner("Running simulation..."):

        # Calculate Lead Time
        df_item_lead_time = df_lead_time[df_lead_time["item_no"] == item_selected]
        arr_lead_time, percentile_lead_time = metrics.calculate_lead_time(df=df_item_lead_time,
                                                              percentile=lead_time_percentile)
        if manual_mode:
            percentile_lead_time = lead_time_manual
    
        start_stock = df_item_inventory["inventory_level"].iloc[-1]
        start_date = pd.to_datetime(df_item_inventory["inventory_date"].iloc[-1]).normalize()
        description = type_selected.loc[type_selected["item_no"] == item_selected, "description"].values[0]

        # include min-max
        df_item_consumption = df_consumption[df_consumption["item_no"] == item_selected]
        arr_consumption = metrics.extract_consumption_values(df_consumption=df_item_consumption,
                                                             start_year=min_year,
                                                             end_year=max_year)
    
        arr_consumption = arr_consumption * -1
       

        df_item_po_status_base = df_po_status_base[df_po_status_base["item_no"] == item_selected]

    
        con_fcst = vectorization.ItemConsumptionForecaster()
        con_fcst.fit(X=arr_consumption, 
                    start_date=start_date,
                    beg_quantity=start_stock, 
                    h=horizon_days)
        con_fcst_result = con_fcst.predict(n_sims=n_sims)

        proc_qty = max_level - min_level

        open_po_dates, open_po_qty, open_po_no = metrics.get_open_po_and_qty(
                                            item=item_selected,
                                            df_po_status_base=df_item_po_status_base
        )

        if (st.session_state.get("edited_receipt_dates") is not None 
            and st.session_state.get("edited_qty") is not None):
            open_po_receipt_dates = st.session_state.get("edited_receipt_dates")
            open_po_qty = st.session_state.get("edited_qty")
            open_po_dates = st.session_state.get("edited_open_po_dates")
            open_po_no = st.session_state.get("edited_open_po_no")
        else:
            open_po_receipt_dates = (
                pd.to_datetime(open_po_dates) 
                + pd.to_timedelta(percentile_lead_time, unit='D')
            ).values

        st.session_state.frag_open_po_no = open_po_no
        st.session_state.frag_open_po_dates = open_po_dates
        st.session_state.frag_open_po_receipt_dates = open_po_receipt_dates
        st.session_state.frag_open_po_qty = open_po_qty


        open_po_arrivals = vectorization.simulate_open_po_arrivals(
            open_po_receipt_dates=open_po_receipt_dates,
            open_po_qty=open_po_qty,
            start_date=start_date,
            horizon_days=horizon_days,
            n_sims=n_sims
        )


        open_po_arrival_median = np.median(open_po_arrivals, axis=0)

        po_dates = vectorization.estimate_reorder_point_from_policy(
        df=con_fcst_result["res"],
        min_stock=min_level,
        proc_qty=proc_qty,
        lead_time=percentile_lead_time,
        start_date=start_date,
        horizon_days=horizon_days,
        open_po_arrival_median=open_po_arrival_median
        )


        all_po_dates = np.concatenate([open_po_dates, po_dates])

        all_quantities = np.concatenate([
            open_po_qty,                       
            np.full(len(po_dates), proc_qty)   
        ])


        arr_fcst = vectorization.ItemArrivalForecaster()
        recommended_arrivals = arr_fcst.fit_predict2(
                                            X=arr_lead_time,
                                            po_dates= po_dates,
                                            quantities=np.full(len(po_dates), proc_qty),  
                                            start_date=start_date,
                                            h=horizon_days,
                                            n_sims=n_sims
                                            )
        
       
        total_inventory = con_fcst_result['preds'] + open_po_arrivals + recommended_arrivals
        # so_prob_at_least_one_stockout = ((total_inventory <= 0).any(axis=1).mean()) * 100
        so_prob_on_any_given_day = (total_inventory <= 0).mean() * 100

        # os_prob_at_least_one_stockout = ((total_inventory > max_level).any(axis=1).mean()) * 100
        os_prob_on_any_given_day = (total_inventory > max_level).mean() * 100


        p50 = np.percentile(total_inventory, 50, axis=0)
        p2_5 = np.percentile(total_inventory, 2.5, axis=0)
        p97_5 = np.percentile(total_inventory, 97.5, axis=0)
        
        st.markdown("<br>", unsafe_allow_html=True)
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric(f"Stockout Probability", f"{so_prob_on_any_given_day:.2f}%") 
        col2.metric(f"Overstock Probability", f"{os_prob_on_any_given_day:.2f}%")
        col3.metric(f"Monthly Utilization ({min_year} - {max_year})", plots.value_format(monthly_utilization))
        col4.metric(f"Days on Hand (Current)", f"{doh:.0f}")
        if manual_mode:
            col5.metric(
            f"Lead Time (Days) - Manual",
            f"{np.ceil(percentile_lead_time):.0f}")

        else:
            col5.metric(
                f"Lead Time (Days) {lead_time_percentile}th Percentile",
                f"{np.ceil(percentile_lead_time):.0f}"
            )


        inp = metrics.Inputs(item_no=item_selected,
                            description=description,
                            MIN=int(min_level),
                            MAX= int(max_level),
                            horizon_days=horizon_days,
                            seed=42
        )

        fig = plots.plot_history_and_forecast_plotly(
            df_inventory=df_item_inventory,
            inv_col="inventory_level",
            start_date=start_date,
            inp=inp,
            p2_5=p2_5,
            p50=p50,
            p97_5=p97_5,
            paths=total_inventory
        )
        st.markdown("<br>", unsafe_allow_html=True)
        st.plotly_chart(fig)
        
        df_yearly_inventory_value_combined = metrics.compute_yearly_inventory_value_with_projection(
            df_inventory=df_item_inventory,
            actual_end_date=start_date,
            horizon_days=horizon_days,
            one_path=p50
        )

        col1, col2 = st.columns([1, 1.1])   # wider chart, smaller table
        # ---- LEFT COLUMN : HISTOGRAM ----
        with col1:
            st.markdown("<h3 style='text-align: center;'>Lead Time Distribution</h3>", unsafe_allow_html=True)

            fig_lt = px.histogram(
                x=arr_lead_time,
                nbins=7,
                labels={"x": "Lead Time (Days)", "y": "Frequency"}
            )
            fig_lt.update_layout(height=375, yaxis_title="Frequency")
            fig_lt.update_traces(marker_color="#0e6caf")
            st.plotly_chart(fig_lt, use_container_width=True)

        # ---- RIGHT COLUMN : SUMMARY TABLE ----
        with col2:

            st.markdown("<h3 style='text-align: center;'>Yearly Average Inventory Value</h3>", unsafe_allow_html=True)
        
            fig = go.Figure()

            fig.add_bar(
                x=df_yearly_inventory_value_combined["year"],
                y=df_yearly_inventory_value_combined["avg_inv_value_actual"],
                name="Actual",
                marker_color="#0e6caf"
            )

            fig.add_bar(
                x=df_yearly_inventory_value_combined["year"],
                y=df_yearly_inventory_value_combined["avg_inv_value_plan"],
                name=f"Projected Inventory",
                marker_color="#fbaa64"
            )

            fig.update_layout(
                height=375,
                barmode="stack",   
                xaxis_title="Year",
                yaxis_title="Inventory Value"
            )

            st.plotly_chart(fig, use_container_width=True)


        def build_po_dataframe(po_dates, quantities, open_po_no, lead_time, open_po_receipt_dates):
            po_dates = pd.to_datetime(po_dates)
            n_open = len(open_po_no)
            n_recommended = len(po_dates) - n_open

            today = pd.Timestamp.today().normalize()

            # Open PO receipt dates from user (or default), recommended from lead_time
            recommended_receipt_dates = po_dates[n_open:] + pd.to_timedelta(lead_time, unit='D')
            receipt_dates = np.concatenate([
                pd.to_datetime(open_po_receipt_dates),
                recommended_receipt_dates
            ])

            # Status for open POs: OVERDUE or ON-TRACK
            open_receipt_dt = pd.to_datetime(open_po_receipt_dates)
            open_status = ["Overdue" if rd < today else "On-track" for rd in open_receipt_dt]
            open_action = ["Expedite" if rd < today else "Monitor" for rd in open_receipt_dt]

            df_po = pd.DataFrame({
                "TYPE": ["Open PO"] * n_open + ["Recommended"] * n_recommended,
                "PO NO": list(open_po_no) + ["-"] * n_recommended,
                "ORDER DATE": po_dates,
                "LEAD TIME BASED RECEIPT DATE": receipt_dates,
                "QUANTITY": [plots.value_format(qty) for qty in quantities],
                "STATUS": open_status + ["Future Order"] * n_recommended,
                "ACTION": open_action + ["Plan"] * n_recommended,
            })

            df_po["ORDER DATE"] = pd.to_datetime(df_po["ORDER DATE"]).dt.strftime("%Y-%m-%d")
            df_po["LEAD TIME BASED RECEIPT DATE"] = pd.to_datetime(
                df_po["LEAD TIME BASED RECEIPT DATE"]).dt.strftime("%Y-%m-%d")

            return df_po


        def highlight_status(row):
            if row["STATUS"] == "Overdue":
                return ["background-color: #ffcccc"] * len(row)
            elif row["STATUS"] == "On-track":
                return ["background-color: #d4edda"] * len(row)
            else:
                return [""] * len(row)


        df_result = build_po_dataframe(
            po_dates=all_po_dates,
            open_po_no=open_po_no,
            quantities=all_quantities,
            lead_time=percentile_lead_time,
            open_po_receipt_dates=open_po_receipt_dates
        )

        st.markdown(
            f"""
            <h2 style='
                text-align: center;
                font-weight: 800;
                font-size: 28px;
                margin-bottom: 10px;
            '>
                Inventory Replenishment Plan
            </h2>
            """,
            unsafe_allow_html=True
        )

        df_result.index = df_result.index + 1
        styled_df = df_result.style.apply(highlight_status, axis=1)
        st.dataframe(styled_df)

open_po_editor()
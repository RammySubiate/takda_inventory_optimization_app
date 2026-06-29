from dataclasses import dataclass
from datetime import timedelta, datetime
import numpy as np
import pandas as pd

def calculate_doh(df):
    return int(np.ceil(df["total_inventory_value_days"].sum() / df["total_usage_value"].sum()))

def calculate_monthly_utilization(df):
    monthy_util = df["total_usage_qty"].sum() / df["non_stockout_days"].sum()
    return int(np.ceil(monthy_util * 30))

def calculate_lead_time(df, percentile):
    """
    Calculate the lead time at a specified percentile.

    Args:
        df (pd.DataFrame):
            DataFrame containing the column
            'po_to_rcpt_lead_time_days'.

        percentile (int):
            Percentile value from 0 to 100.

    Returns:
        tuple:
            A tuple containing:
            - numpy.ndarray:
                Array of lead time values.
            - int:
                Percentile lead time rounded up
                to the nearest whole number.
    """
    arr_lead_time = np.array(df["po_to_rcpt_lead_time_days"].tolist())
    percentile_lead_time = int(np.ceil(np.percentile(arr_lead_time, percentile)))
    
    return arr_lead_time, percentile_lead_time

def get_open_po_active(
        item,
        lead_time,
        df_po_status_base

):
   
    # df_po_status_base is the result from build_po_status_base

    df = (df_po_status_base[(df_po_status_base["item_no"] == item) &
                            (df_po_status_base["is_stale"] == False) & 
                            (df_po_status_base["open_qty"] > 0)]).copy()

    
    today = pd.Timestamp.today().normalize()
    df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
    df["lead_time_based_rcpt_date"] = df["order_date"] + pd.to_timedelta(lead_time, unit="D")
    df["lead_time_based_rcpt_date"] = pd.to_datetime(df["lead_time_based_rcpt_date"], errors="coerce")
    df["days_left"] = (df["lead_time_based_rcpt_date"] - today).dt.days


    # Default values
    df["type"] = "OPEN PO"
    df["status"] = "ARRIVING"
    df["action"] = "MONITOR"

    # Overdue condition
    df.loc[df["days_left"] < 0, "status"] = "OVERDUE"
    df.loc[df["days_left"] < 0, "action"] = "EXPEDITE"

    df["lead_time_based_rcpt_date"] = pd.to_datetime(df["lead_time_based_rcpt_date"]).dt.strftime("%Y-%m-%d")
    df["order_date"] = pd.to_datetime(df["order_date"]).dt.strftime("%Y-%m-%d")
    df = df.rename(columns={
        "type": "TYPE",
        "po_no": "PO NO",
        "order_date": "ORDER DATE",
        "lead_time_based_rcpt_date": "LEAD TIME BASED RECEIPT DATE",
        "open_qty": "QUANTITY",
        "days_left": "DAYS UNTIL RECEIPT",
        "status": "STATUS",
        "action": "ACTION"
    })
    df = (df[["TYPE", "PO NO", "ORDER DATE", "LEAD TIME BASED RECEIPT DATE", 
                            "QUANTITY", "DAYS UNTIL RECEIPT", "STATUS", "ACTION"]])
    
   

    # simulation_list = list(
    #     df[["days_left", "open_qty"]]
    #     .itertuples(index=False, name=None)
    # )

    if not df.empty:
        return df.sort_values(by="ORDER DATE").reset_index(drop=True)
    else:
        return pd.DataFrame(columns=["TYPE", "PO NO", "ORDER DATE", "LEAD TIME BASED RECEIPT DATE", 
                            "QUANTITY", "DAYS UNTIL RECEIPT", "STATUS", "ACTION"]) 
    

def get_open_po_floating(
        item,
        lead_time,
        df_po_status_base
):
    # df_po_status_base is the result from build_po_status_base

    df_for_verification = (df_po_status_base[(df_po_status_base["is_stale"] == True) & (df_po_status_base["item_no"] == item)]).copy()
                            
    df_for_verification["order_date"] = pd.to_datetime(df_for_verification["order_date"], errors="coerce")
    df_for_verification["LEAD TIME BASED RECEIPT DATE"] = df_for_verification["order_date"] + pd.to_timedelta(lead_time, unit="D")

    df_for_verification = df_for_verification.rename(columns={
        "po_no": "PO NO",
        "order_date" : "ORDER DATE",
        "qty_ordered": "QUANTITY ORDERED",
        "qty_received": "QUANTITY RECEIVED",
        "open_qty": "OPEN QUANTITY",
        "days_since_order": "DAYS SINCE ORDER"
    })

    df_for_verification["TYPE"] = "OPEN PO"
    df_for_verification["STATUS"] = "OVERDUE"
    df_for_verification["ACTION"] = "VERIFY"
    df_for_verification["ORDER DATE"] = pd.to_datetime(df_for_verification["ORDER DATE"]).dt.strftime("%Y-%m-%d")
    df_for_verification["LEAD TIME BASED RECEIPT DATE"] = pd.to_datetime(df_for_verification["LEAD TIME BASED RECEIPT DATE"]).dt.strftime("%Y-%m-%d")
    df_for_verification = df_for_verification[["TYPE", "PO NO", "ORDER DATE", "LEAD TIME BASED RECEIPT DATE", 
                                            "QUANTITY ORDERED", "QUANTITY RECEIVED","OPEN QUANTITY",
                                            "DAYS SINCE ORDER", "STATUS", "ACTION"]]
    if not df_for_verification.empty:
        return df_for_verification.sort_values(by="ORDER DATE").reset_index(drop=True)
    else:
        return pd.DataFrame(columns=["TYPE", "PO NO", "ORDER DATE", "LEAD TIME BASED RECEIPT DATE", 
                                    "QUANTITY ORDERED", "QUANTITY RECEIVED","OPEN QUANTITY",
                                    "DAYS SINCE ORDER", "STATUS", "ACTION"])


def extract_consumption_values(df_consumption, start_year, end_year):
    """
    Extract consumption quantities within a given year range.

    Filters the dataset based on consumption_date and returns
    the corresponding consumption quantities as a NumPy array.
    """
    df = df_consumption.copy()
    df["year"] = pd.to_datetime(df["consumption_date"]).dt.year

    filtered_df = df[(df["year"] >= start_year) & (df["year"] <= end_year)]

    return np.array(filtered_df["consumption_qty"].tolist())

@dataclass(frozen=True)
class Inputs:
    """
    Container for simulation inputs.

    Using a dataclass helps because:
    - You keep related parameters together
    - Function signatures stay clean
    - It's harder to accidentally mismatch arguments
    """
    item_no: str
    description: str
    MIN: int
    MAX: int
    horizon_days: int
    seed: int = 42


def compute_yearly_inventory_value_with_projection(
    df_inventory,
    actual_end_date,
    horizon_days,
    one_path
):
    """
    Compute yearly average inventory value by combining historical (actual)
    data and forward-looking (simulated) projections.

    This function calculates:
    - Historical average inventory value per year up to `actual_end_date`
    - Projected average inventory value per year using a simulated inventory path
    - A weighted combination for the current year based on number of days covered
      by actual vs simulated data

    Args:
        df_inventory : pandas.DataFrame
            Historical inventory data with the following required columns:
            - 'inventory_date' (datetime)
            - 'inventory_level' (numeric)
            - 'unit_cost' (numeric)

        actual_end_date : datetime-like
            The last date of available actual inventory data (cutoff point between
            historical and simulated data).

        horizon_days : int
            Number of days to project into the future.

        one_path : array-like
            Simulated inventory levels for the forecast horizon.
            Length must equal `horizon_days`.

    Returns
        pandas.DataFrame
            DataFrame containing yearly average inventory values:
            - 'year' (str)
            - 'avg_inv_value_actual' (historical component)
            - 'avg_inv_value_plan' (projected component)

            Note:
            For the current year, values are weighted based on number of actual vs
            simulated days.

    Notes
    -----
    - Assumes daily granularity with no missing dates.
    - Uses the latest available unit cost for projected inventory valuation.
    - Weighting is only applied to the current year.
    """

    df_inventory = df_inventory.copy()
    current_year = actual_end_date.year
    latest_idx = df_inventory["inventory_date"].idxmax()
    latest_unit_cost = df_inventory.loc[latest_idx, "unit_cost"]

    df_inventory["inventory_value"] = df_inventory["inventory_level"] * df_inventory["unit_cost"]
    df_inventory["year"] = df_inventory["inventory_date"].dt.year

    df_actual_partial = df_inventory[df_inventory["inventory_date"] <= actual_end_date]

    num_of_days_current_year_actual_inventory = (
        df_actual_partial["inventory_date"].dt.year == current_year
    ).sum()

    df_yearly_actual = (
        df_actual_partial.groupby("year")["inventory_value"]
        .mean()
        .reset_index(name="avg_inv_value_actual")
    )

    # Simulation
    dates = pd.date_range(
        start=actual_end_date + pd.Timedelta(days=1),
        periods=horizon_days
    )

    df_avg_inv_plan = pd.DataFrame({
        "date": dates,
        "inventory_level": one_path
    })

    df_avg_inv_plan["inventory_value"] = (
        df_avg_inv_plan["inventory_level"] * latest_unit_cost
    )
    df_avg_inv_plan["year"] = df_avg_inv_plan["date"].dt.year

    df_sim_partial = df_avg_inv_plan

    num_of_days_current_year_plan_inventory = (
        df_sim_partial["date"].dt.year == current_year
    ).sum()

    df_yearly_plan = (
        df_sim_partial.groupby("year")["inventory_value"]
        .mean()
        .reset_index(name="avg_inv_value_plan")
    )

    total_days = (
        num_of_days_current_year_actual_inventory +
        num_of_days_current_year_plan_inventory
    )

    if total_days > 0:
        weighted_avg_ratio_actual = num_of_days_current_year_actual_inventory / total_days
        weighted_avg_ratio_plan = num_of_days_current_year_plan_inventory / total_days
    else:
        weighted_avg_ratio_actual = 0
        weighted_avg_ratio_plan = 0

    if current_year in df_yearly_actual["year"].values:
        df_yearly_actual.loc[
            df_yearly_actual["year"] == current_year,
            "avg_inv_value_actual"
        ] *= weighted_avg_ratio_actual

    if current_year in df_yearly_plan["year"].values:
        df_yearly_plan.loc[
            df_yearly_plan["year"] == current_year,
            "avg_inv_value_plan"
        ] *= weighted_avg_ratio_plan

    df_yearly_combined = (
        df_yearly_actual
        .merge(df_yearly_plan, on="year", how="outer")
        .fillna(0)
        .sort_values("year")
    )

    df_yearly_combined["year"] = df_yearly_combined["year"].astype(str)

    return df_yearly_combined


def get_open_po_and_qty(
        item,
        df_po_status_base
):
    """
    Retrieve open purchase order dates and quantities
    for a specific item.

    Args:
        item (str):
            Item number to filter.

        df_po_status_base (pandas.DataFrame):
            Purchase order status DataFrame generated
            from build_po_status_base().

    Returns:
        tuple:
            A tuple containing:
            - numpy.ndarray:
                Array of purchase order dates.
            - numpy.ndarray:
                Array of open quantities.

    Notes:
        Filters only:
        - matching item numbers
        - non-stale records
        - rows with open quantity greater than 0
    """
    # df_po_status_base is the result from build_po_status_base

    df = (df_po_status_base[(df_po_status_base["item_no"] == item) &
                            (df_po_status_base["is_stale"] == False) & 
                            (df_po_status_base["open_qty"] > 0)]).copy()

    df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
   
    open_po_dates = df["order_date"].to_numpy()
    open_qty = df["open_qty"].to_numpy()
    open_po_no = df["po_no"].to_numpy()

    return open_po_dates, open_qty, open_po_no




import pandas as pd

def build_item_segmentation(df_ledger_entry, df_item):
    """
    Build item segmentation based on movement frequency and inventory value.

    This function classifies items using two dimensions:

    1. Movement Class (A–F)
       - Based on the number of months with consumption activity
         over the last 12 months.
       - Derived from item ledger entries (issue transactions only).

    2. Value Class (A–C)
       - Based on cumulative on-hand inventory value (ABC analysis).
       - Items are ranked by on-hand value contribution.

    Notes:
    - In NAV data, `positive == 0` indicates issue/consumption transactions.
    - `quantity` is negative for issues and positive for receipts.
    - Remaining stock is computed as the net sum of quantities per item.

    Args:
        df_ledger_entry (pd.DataFrame):
            Item ledger transactions containing:
            - item_no
            - posting_date
            - quantity
            - positive flag

        df_item (pd.DataFrame):
            Item master data containing:
            - item_no
            - unit_cost
            - description

    Returns:
        pd.DataFrame:
            A DataFrame with item segmentation:
            - item_no
            - description
            - movement_class (A–F)
            - value_class (A–C)
    """
    df_ledger_entry = df_ledger_entry.copy()
    df_item = df_item.copy()

    df_ledger_entry["posting_date"] = pd.to_datetime(
        df_ledger_entry["posting_date"], errors="coerce"
    )

    # Keep issue/consumption transactions only
    df_usage = df_ledger_entry[df_ledger_entry["positive"] == 0].copy()

    # Define rolling 12-month window based on latest usage month
    df_usage["month"] = df_usage["posting_date"].dt.to_period("M")
    max_month = df_usage["month"].max()

    if pd.isna(max_month):
        start_month = None
        #Returns an empty df with fields similar to df_usage
        df_usage_12m = df_usage.iloc[0:0].copy()
    else:
        start_month = max_month - 11
        df_usage_12m = df_usage[df_usage["month"] >= start_month].copy()

    # Count months with movement
    months_with_movement = (
        df_usage_12m.groupby("item_no")["month"]
        .nunique()
        .reset_index(name="months_with_movement")
    )
    
    # Total consumed quantity in last 12 months
    total_consumed_qty_12m = (
        df_usage_12m.groupby("item_no")["quantity"]
        .sum()
        .abs()
        .reset_index(name="total_consumed_qty_12m")
    )

    # Net remaining stock
    remaining_stock = (
        df_ledger_entry.groupby("item_no")["quantity"]
        .sum()
        .reset_index(name="remaining_qty")
    )

    remaining_stock["remaining_qty"] = remaining_stock["remaining_qty"].clip(lower=0)
    remaining_stock["has_remaining_stock"] = remaining_stock["remaining_qty"] > 0
 
    # Base item list
    all_items = pd.DataFrame(df_item["item_no"].dropna().unique(), columns=["item_no"])

    # Combine metrics
    item_movement = (
        all_items
        .merge(months_with_movement, on="item_no", how="left")
        .merge(total_consumed_qty_12m, on="item_no", how="left")
        .merge(
            remaining_stock[["item_no", "remaining_qty", "has_remaining_stock"]],
            on="item_no",
            how="left"
        )
    )

    item_movement["months_with_movement"] = item_movement["months_with_movement"].fillna(0)
    item_movement["total_consumed_qty_12m"] = item_movement["total_consumed_qty_12m"].fillna(0)
    item_movement["remaining_qty"] = item_movement["remaining_qty"].fillna(0)



    def classify_movement(n):
        if n >= 10:
            return "A"
        elif n >= 6:
            return "B"
        elif n >= 3:
            return "C"
        elif n == 2:
            return "D"
        elif n == 1:
            return "E"
        else:
            return "F"

    item_movement["movement_class"] = item_movement["months_with_movement"].apply(classify_movement)

    # Add cost fields
    df_movement_cost = item_movement.merge(
        df_item[["item_no", "unit_cost", "description"]],
        on="item_no",
        how="left"
    )

    df_movement_cost["unit_cost"] = df_movement_cost["unit_cost"].fillna(0)

    df_movement_cost["movement_value"] = (
        df_movement_cost["total_consumed_qty_12m"] * df_movement_cost["unit_cost"]
    ).round()

    df_movement_cost["on_hand_value"] = (
        df_movement_cost["remaining_qty"] * df_movement_cost["unit_cost"]
    ).round()

    
    # ABC classification based on on-hand value
    df_abc_stock = df_movement_cost.sort_values(["on_hand_value", "item_no"], ascending=[False, True]).copy()
    df_abc_stock["cum_value"] = df_abc_stock["on_hand_value"].cumsum()
    

    

    total_on_hand_value = df_abc_stock["on_hand_value"].sum()

    if total_on_hand_value > 0:
        df_abc_stock["cum_value_pct"] = (
            df_abc_stock["cum_value"] / total_on_hand_value * 100
        )
    else:
        df_abc_stock["cum_value_pct"] = 0

    def abc_class(pct):
        if pct <= 80:
            return "A"
        elif pct <= 95:
            return "B"
        else:
            return "C"
    

    df_abc_stock["value_class"] = df_abc_stock["cum_value_pct"].apply(abc_class)
    
 
    return df_abc_stock[["item_no", "description", "movement_class", "value_class"]].reset_index(drop=True)


def create_master_calendar (min_date, max_date):
    """
    Creates a daily master calendar between two dates (inclusive).

    Args: 
        min_date : str or datetime (Start date of the calendar)
        max_date : str or datetime (End date of the calendar)

    Returns:
        pd.DataFrame : A DataFrame with a single column (posting_date : daily dates from min_date to max_date)
    """
    min_date = pd.to_datetime(min_date, errors="coerce")
    max_date = pd.to_datetime(max_date, errors="coerce")
    
    master_calendar = pd.DataFrame({
        "posting_date" : pd.date_range(start=min_date, end=max_date, freq='D')
    })

    return master_calendar


def create_inventory_level (df_ledger_entry, item):
    """
    Builds a daily inventory level time series for a single item.

    Args:
        df : pd.DataFrame
            Ledger entry data containing at least:
            - item_no
            - posting_date
            - quantity (positive for receipts, negative for issues)

        item : str
            Item number to build the inventory level for.

    Returns:
        pd.DataFrame
            Daily inventory level time series with columns:
            - posting_date
            - inventory_level
    """
    # Filter data for the selected item
    df = df_ledger_entry.copy()
    df = df[df["item_no"] == item]

    # Ensure posting_date is datetime and properly ordered
    df["posting_date"] = pd.to_datetime(df["posting_date"], errors="coerce")
    df.sort_values("posting_date", inplace=True)

    # This converts movement data (in/out quantities)
    # into inventory-on-hand over time
    df["inventory_level"] = df["quantity"].cumsum()

    # If multiple transactions occur on the same day,
    # keep the last inventory level as the EOD balance
    df_daily = df.groupby("posting_date", as_index=False)["inventory_level"].last()
    
    # Create a complete daily calendar for the item
    min_date = df["posting_date"].min()
    max_date = pd.Timestamp.today().normalize()
    master_calendar = create_master_calendar(min_date, max_date)

    # Merge calendar with inventory data
    df_merged = master_calendar.merge(df_daily, on="posting_date", how="left")

    # Forward fill ensures inventory level is carried forward
    # on days with no transactions
    df_merged["inventory_level"] = df_merged["inventory_level"].ffill()


    return df_merged

def build_item_inventory_with_cost(df_ledger, df_journal, df_item, item_list):
    """
    Builds a transaction-level inventory time series for multiple items,
    enriched with the latest known unit cost as of each posting date.

    If unit_cost is still missing after the merge (e.g., an item has no journal
    entries), unit_cost is filled using df_item["unit_cost"] when available.

    Args:
        df_ledger : pd.DataFrame
            Ledger entry data containing inventory movements
            (must include item_no, posting_date, quantity, etc.).

        df_journal : pd.DataFrame
            Journal line data containing unit cost updates
            (must include item_no, posting_date, unit_cost).

        df_item : pd.DataFrame
            Item master data used as fallback for unit cost
            (must include item_no, unit_cost).

        item_list : list
            List of item numbers to build inventory cost time series for.

    Returns:
        pd.DataFrame
            Transaction-level inventory data with:
            - item_no
            - inventory_date
            - inventory_level
            - unit_cost
    """
    all_inventory = []
    for item in item_list:
        # Filter journal entries for the selected item
        df_j = df_journal[df_journal["item_no"] == item].copy()

        # Ensure valid posting dates
        df_j["posting_date"] = pd.to_datetime(df_j["posting_date"], errors="coerce")
        df_j = df_j.dropna(subset=["posting_date"])

        # Keep only valid, positive unit costs
        df_j = df_j[df_j["unit_cost"] > 0]               

        # If multiple cost updates occur on the same day,
        # keep the last (most recent) unit cost for that date
        df_j = (
            df_j
            .sort_values("posting_date")
            .groupby("posting_date", as_index=False)["unit_cost"]
            .last()                                                   
        )

        # Extract ledger movements for the item
        df_l = create_inventory_level(df_ledger, item)
        df_l["posting_date"] = pd.to_datetime(df_l["posting_date"], errors="coerce")
        df_l = df_l.dropna(subset=["posting_date"])
        df_l = df_l.sort_values("posting_date")

        # For each ledger transaction date, attach the most recent
        # unit cost on or before that date
        df_inventory = pd.merge_asof(df_l, 
            df_j,
            on="posting_date",
            direction="backward"
        )

        # If early ledger entries occur before the first known cost,
        # backfill using the next available unit cost
        df_inventory["unit_cost"] = df_inventory["unit_cost"].bfill()

        # Fallback to item master unit cost
        # If the item has no journal-based unit cost (or still contains NaN
        # after time-series filling), use the static unit_cost from the
        # item master table to ensure value-based metrics can still be computed.
    
        fallback = df_item.loc[df_item["item_no"] == item, "unit_cost"]
        if not fallback.empty:
            df_inventory["unit_cost"] = df_inventory["unit_cost"].fillna(fallback.iloc[0])
        df_inventory["item_no"] = item
        df_inventory = df_inventory[["item_no", "posting_date", "inventory_level", "unit_cost"]].rename(columns={"posting_date":"inventory_date"})
        df_inventory = df_inventory.sort_values(by=["item_no", "inventory_date"])
        all_inventory.append(df_inventory)
    if all_inventory:
        return pd.concat(all_inventory, ignore_index=True).reset_index(drop=True)
    else:
        return pd.DataFrame(columns=["item_no", "inventory_date", "inventory_level", "unit_cost"])

    
def build_item_consumption(df_item_daily_inventory, item_list):
    """
    Derive item-level consumption time series from daily inventory data.

    This function computes consumption quantities based on changes in
    inventory levels over time. A decrease in inventory level between
    consecutive days is treated as consumption.

    Logic:
    - Inventory levels are first clipped at zero to avoid negative stock values.
    - Daily consumption is calculated using the difference in inventory levels.
    - Negative differences (inventory drops) are treated as consumption.
    - Zero differences with positive inventory are retained to preserve continuity.
    - Consumption quantities are converted to positive values.

    Args:
        df_item_daily_inventory (pd.DataFrame):
            Daily inventory dataset containing:
            - item_no
            - inventory_date
            - inventory_level

        item_list (list):
            List of item numbers to compute consumption for.

    Returns:
        pd.DataFrame:
            A DataFrame containing item-level consumption:
            - item_no
            - consumption_date
            - consumption_qty
    """
    all_consumption = []

    for item in item_list:
        df_inventory = df_item_daily_inventory[
            df_item_daily_inventory["item_no"] == item
        ].copy()

        df_inventory = df_inventory.sort_values("inventory_date")

        df_inventory["inventory_level"] = df_inventory["inventory_level"].clip(lower=0)

        df_inventory["consumption_qty"] = df_inventory["inventory_level"].diff()

        df_consumption = df_inventory[
            (df_inventory["consumption_qty"] < 0) |
            ((df_inventory["consumption_qty"] == 0) &
             (df_inventory["inventory_level"] > 0))
        ].copy()

        df_consumption["consumption_qty"] = df_consumption["consumption_qty"].abs()

        df_consumption = df_consumption[
            ["item_no", "inventory_date", "consumption_qty"]
        ].rename(columns={"inventory_date": "consumption_date"})

        all_consumption.append(df_consumption)

    if all_consumption:
        return (
            pd.concat(all_consumption, ignore_index=True)
            .sort_values(by=["item_no", "consumption_date"])
            .reset_index(drop=True)
        )
    else:
        return pd.DataFrame(columns=["item_no", "consumption_date", "consumption_qty"])

def build_item_procurement_lead_time(
    item_list,
    df_pr_lines_archive,
    df_pr_header,
    df_pr_header_archive,
    df_purchase_line,
    df_purchase_line_archive,
    df_purchase_header,
    df_purchase_header_archive,
    df_purch_rcpt_header,
    df_purch_rcpt_line
):
    
    """
    Build item-level procurement lead time dataset by linking PR, PO, and receipt data.

    This function derives procurement lead times by reconstructing the full
    procurement lifecycle for each item:
        Purchase Requisition (PR) → Purchase Order (PO) → Receipt (PPR)

    Logic:
    - Extract PR records from both active and archive tables.
    - Retain only valid PRs (released or archived versions).
    - Identify all related POs from purchase line and archive tables.
    - Filter PO headers to include:
        - Active released POs (status == 1)
        - Archive-only POs (first version)
    - Combine PR and PO data to reconstruct procurement flow.
    - Link PO to receipt data (PPR) and compute:
        - First and last receipt dates per PO
    - Calculate lead times:
        - PR to Receipt Lead Time
        - PO to Receipt Lead Time
    - Filter out invalid or negative lead times.

    Args:
        item_list (list):
            List of item numbers to process.

        df_pr_lines_archive (pd.DataFrame):
            PR line archive data containing item-to-PR relationships.

        df_pr_header (pd.DataFrame):
            Active PR header data (with status and dates).

        df_pr_header_archive (pd.DataFrame):
            Archived PR header versions.

        df_purchase_line (pd.DataFrame):
            Active purchase line data.

        df_purchase_line_archive (pd.DataFrame):
            Archived purchase line data.

        df_purchase_header (pd.DataFrame):
            Active purchase header data (with order dates and status).

        df_purchase_header_archive (pd.DataFrame):
            Archived purchase header versions.

        df_purch_rcpt_header (pd.DataFrame):
            Purchase receipt header data linking receipts to POs.

        df_purch_rcpt_line (pd.DataFrame):
            Purchase receipt line data containing receipt dates per item.

    Returns:
        pd.DataFrame:
            Item-level procurement lead time dataset with:
            - lead_time_id
            - item_no
            - pr_date
            - po_date
            - rcpt_date
            - pr_to_rcpt_lead_time_days
            - po_to_rcpt_lead_time_days

    Notes:
    - Only valid PRs and released POs are considered.
    - Archive tables are used to recover historical records.
    - Lead times are filtered to include only positive durations.
    - Order dates before 2020 are excluded if more recent data exists.
    """
    
    all_lead_time = []
    for item in item_list:

        # =========================================================
        # STEP 1: Extract PRs linked to the item
        # =========================================================
        df_pr_lines_archive_item = (df_pr_lines_archive[df_pr_lines_archive["item_no"] == item][["pr_no"]]
                                .dropna(subset=["pr_no"])
                                .drop_duplicates(subset=["pr_no"])
                                .reset_index(drop=True))
        all_pr_list = df_pr_lines_archive_item["pr_no"].tolist()


        # =========================================================
        # STEP 2: Get PR headers (active + archive)
        # =========================================================
        df_pr_header_item = (df_pr_header[df_pr_header["pr_no"].isin(all_pr_list)]
                        [["pr_no", "pr_date", "status"]] 
        )

        df_pr_header_archive_item = (df_pr_header_archive[df_pr_header_archive["pr_no"].isin(all_pr_list)]
                        [["pr_no", "pr_date", "version_no"]] 

        )
        # Keep archive-only PRs (not present in active)
        df_pr_header_archive_only = df_pr_header_archive_item.merge(df_pr_header_item, on="pr_no", how="left", indicator=True)

        df_pr_header_archive_only = (df_pr_header_archive_only[df_pr_header_archive_only["_merge"] == "left_only"]
                                    [["pr_no", "pr_date_x", "version_no"]].rename(columns={"pr_date_x":"pr_date"})
        )

        # Keep earliest version per PR
        df_pr_header_archive_only = (df_pr_header_archive_only
                            .sort_values(["pr_no", "version_no"])
                            .drop_duplicates("pr_no", keep="first")
                            .reset_index(drop=True)
        )

        df_pr_header_archive_only = df_pr_header_archive_only[["pr_no", "pr_date"]]

        # Keep active released PRs only
        df_pr_header_active_released = df_pr_header_item[df_pr_header_item["status"] == 1]

        df_pr_header_active_released = df_pr_header_active_released[["pr_no", "pr_date"]]

        # Combine all valid PRs
        df_all_posted_pr = (pd.concat([df_pr_header_archive_only, df_pr_header_active_released],
                        ignore_index=True)
                        .drop_duplicates()
                        .dropna(subset=["pr_no", "pr_date"])
                        .reset_index(drop=True)
        )
        # =========================================================
        # STEP 3: Extract all POs linked to the item
        # =========================================================
        df_purchase_line_item = df_purchase_line[df_purchase_line ["item_no"] == item][["po_no"]]
        df_purchase_line_archive_item = df_purchase_line_archive [df_purchase_line_archive["item_no"] == item][["po_no"]]

        df_purchase_line_all_pos = (
            pd.concat(
            [df_purchase_line_item[["po_no"]], df_purchase_line_archive_item[["po_no"]]],
            ignore_index=True
            )
            .dropna(subset=["po_no"])
            .drop_duplicates(subset=["po_no"])
            .reset_index(drop=True)
        )

        # List of all POs in an Item specified
        all_pos_list = df_purchase_line_all_pos["po_no"].tolist()

 
        # =========================================================
        # STEP 4: Get PO headers (active + archive)
        # =========================================================
        df_purchase_header_item = (
            df_purchase_header[df_purchase_header["po_no"].isin(all_pos_list)]
            [["po_no", "pr_no", "order_date","status"]]
        )
        df_purchase_header_archive_item = (
            df_purchase_header_archive[df_purchase_header_archive["po_no"].isin(all_pos_list)]
            [["po_no", "pr_no", "order_date", "version_no"]]
        )

        # Archive-only POs
        df_po_in_header_archive_only = (
            df_purchase_header_archive_item.merge(df_purchase_header_item[["po_no"]], on="po_no", how="left", indicator=True)
        )
        df_po_in_header_archive_only = (
            df_po_in_header_archive_only[df_po_in_header_archive_only["_merge"] == "left_only"]
            [["po_no","pr_no", "order_date", "version_no"]]
        )

        df_po_in_header_archive_only = (df_po_in_header_archive_only
            .sort_values(["po_no", "version_no"])
            .drop_duplicates("po_no", keep="first")
            .reset_index(drop=True)
        )
        df_po_in_header_archive_only = df_po_in_header_archive_only[["po_no", "pr_no", "order_date"]]

         # Active released POs
        df_po_in_header_active_released = df_purchase_header_item[df_purchase_header_item["status"] == 1] 
        
    
        # PO in df_purchase active is unique, has no version field
        df_po_in_header_active_released = (df_po_in_header_active_released
            .sort_values("order_date")
            .drop_duplicates("po_no", keep="first")
            .reset_index(drop=True)
        )
        
        df_po_in_header_active_released = df_po_in_header_active_released[["po_no", "pr_no", "order_date"]]


        # Combine all valid POs
        df_all_posted_po = (
            pd.concat(
                [
                df_po_in_header_archive_only[["po_no", "pr_no","order_date"]], 
                df_po_in_header_active_released[["po_no", "pr_no",  "order_date"]]
                ],
                ignore_index=True
            )
            .dropna(subset=["po_no", "pr_no", "order_date"])
            .reset_index(drop=True)
        )
  


        # =========================================================
        # STEP 5: Filter invalid dates (before 2020)
        # =========================================================
        df_all_posted_po["order_date"] = pd.to_datetime(df_all_posted_po["order_date"], errors="coerce")
        df_all_posted_po = df_all_posted_po.dropna(subset=["order_date"])
        min_date = pd.to_datetime("2020-01-01")

        all_posted_po_max_date = df_all_posted_po["order_date"].max()


        if pd.notna(all_posted_po_max_date) and all_posted_po_max_date >= min_date:
            df_all_posted_po = df_all_posted_po[df_all_posted_po["order_date"] >= min_date].copy()
        else:
            df_all_posted_po = df_all_posted_po.copy()
     

        # =========================================================
        # STEP 6: Extract receipt (PPR) data
        # =========================================================
        df_purch_rcpt_line_item = df_purch_rcpt_line[df_purch_rcpt_line["item_no"] == item]
        df_rcpt = (df_purch_rcpt_line_item[["ppr_no", "ppr_posting_date"]]
                .merge(df_purch_rcpt_header[["ppr_no", "po_no"]], on="ppr_no", how="inner")
                [["po_no", "ppr_posting_date"]]
        )

        df_rcpt["ppr_posting_date"] = pd.to_datetime(df_rcpt["ppr_posting_date"], errors="coerce")
        df_rcpt = df_rcpt.dropna(subset=["ppr_posting_date"])
    
        # Aggregate receipt dates per PO
        df_rcpt_po = (df_rcpt.groupby("po_no", as_index=False)
            .agg(
            first_ppr_posting_date = ("ppr_posting_date", "min"),
            last_ppr_posting_date = ("ppr_posting_date", "max")
            )
        )


        # =========================================================
        # STEP 7: Combine PR → PO → Receipt
        # =========================================================
        df =(df_all_posted_pr[["pr_no", "pr_date"]]
            .merge(df_all_posted_po[["po_no", "pr_no", "order_date"]], on="pr_no", how="inner")
            .merge(
                df_rcpt_po[["po_no", "first_ppr_posting_date", "last_ppr_posting_date"]],
                on="po_no", 
                how="inner"
            )
        )

        df["item_no"] = item

        # =========================================================
        # STEP 8: Compute lead times
        # =========================================================
        df["pr_date"] = pd.to_datetime(df["pr_date"], errors="coerce")
        df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
        df["first_ppr_posting_date"] = pd.to_datetime(df["first_ppr_posting_date"], errors="coerce")
        df["last_ppr_posting_date"] = pd.to_datetime(df["last_ppr_posting_date"], errors="coerce")
        df["pr_to_rcpt_lead_time_days"] = (df["last_ppr_posting_date"] - df["pr_date"]).dt.days
        df["po_to_rcpt_lead_time_days"] = (df["last_ppr_posting_date"] - df["order_date"]).dt.days

        # Keep only valid lead times
        df = df[ (df["pr_to_rcpt_lead_time_days"] > 0) & (df["po_to_rcpt_lead_time_days"] > 0)]

        # Final formatting
        df = (df[["item_no", "pr_date", "order_date", "last_ppr_posting_date", "pr_to_rcpt_lead_time_days", "po_to_rcpt_lead_time_days"]]
            .rename(columns={"order_date": "po_date",
                            "last_ppr_posting_date": "rcpt_date"})
        )
        all_lead_time.append(df)

    # =========================================================
    # FINAL STEP: Combine all items
    # =========================================================
    if all_lead_time:
        result = pd.concat(all_lead_time, ignore_index=True).sort_values(by=["item_no", "pr_date"]).reset_index(drop=True)
        lead_time_ids = range(1, len(result)+1)
        result["lead_time_id"] = lead_time_ids
        cols = ["lead_time_id"] + [col for col in result.columns if col != "lead_time_id"]
        return result[cols]

    else:
        return pd.DataFrame(columns=["lead_time_id", "item_no", "pr_date", "po_date", "rcpt_date", "pr_to_rcpt_lead_time_days", "po_to_rcpt_lead_time_days"])
   

def build_yearly_metrics(
        item_list,
        df_item_inventory_with_cost,
        df_item_consumption
):
    """
    Build yearly item-level inventory and consumption performance metrics.

    This function aggregates inventory and consumption data to produce
    annual key performance indicators (KPIs) for each item.

    Metrics Computed:
    - Total Usage Quantity:
        Sum of consumption quantities per year.

    - Total Usage Value:
        Consumption value computed as:
            consumption_qty × unit_cost (matched by date).

    - Non-Stockout Days:
        Number of days per year where inventory level is greater than zero.

    - Total Inventory Value Days:
        Sum of daily inventory value:
            inventory_level × unit_cost

    - Calendar Days:
        Number of unique inventory dates per year.


    Args:
        item_list (list):
            List of item numbers to process.

        df_item_inventory_with_cost (pd.DataFrame):
            Daily inventory dataset (output of build_item_inventory_with_cost)
            containing:
            - item_no
            - inventory_date
            - inventory_level
            - unit_cost

        df_item_consumption (pd.DataFrame):
            Item consumption dataset (output of build_item_consumption)
            containing:
            - item_no
            - consumption_date
            - consumption_qty

    Returns:
        pd.DataFrame:
            Yearly item-level metrics with:
            - item_no
            - year
            - total_usage_qty
            - total_usage_value
            - non_stockout_days
            - total_inventory_value_days
            - calendar_days
    """
    df_inventory = df_item_inventory_with_cost.copy()
    df_consumption = df_item_consumption.copy()
    
    all_items = []
    for item in item_list:  
        df_inventory_item = df_inventory[df_inventory["item_no"] == item]
        df_consumption_item = df_consumption[df_consumption["item_no"] == item]

        #total usage qty
        df_total_usage_qty = df_consumption_item.copy()
        df_total_usage_qty["year"] = df_total_usage_qty["consumption_date"].dt.year
        df_total_usage_qty = df_total_usage_qty.groupby("year", as_index=False)["consumption_qty"].sum()
        df_total_usage_qty = df_total_usage_qty.rename(columns={"consumption_qty":"total_usage_qty"})
        
        #total usage value
        df_total_usage_value = df_consumption_item.merge(df_inventory_item[["inventory_date", "unit_cost"]], left_on="consumption_date", right_on="inventory_date", how="left")
        df_total_usage_value["usage_value"] = df_total_usage_value["consumption_qty"] * df_total_usage_value["unit_cost"]
        df_total_usage_value["year"] = df_total_usage_value["consumption_date"].dt.year
        df_total_usage_value = df_total_usage_value.groupby("year", as_index=False)["usage_value"].sum()
        df_total_usage_value = df_total_usage_value.rename(columns={"usage_value": "total_usage_value"})
        df_total_usage_value["total_usage_value"] = df_total_usage_value["total_usage_value"].round(2)

        # non stockout days
        df_non_stockout_days = df_inventory_item.copy()
        df_non_stockout_days["is_non_stockout"] = df_non_stockout_days["inventory_level"] > 0
        df_non_stockout_days["year"] = df_non_stockout_days["inventory_date"].dt.year
        df_non_stockout_days = df_non_stockout_days.groupby("year", as_index=False)["is_non_stockout"].sum()
        df_non_stockout_days = df_non_stockout_days.rename(columns={"is_non_stockout": "non_stockout_days"})

        # total inventory value days, calendar days
        df_total_inventory_value_days = df_inventory_item.copy()
        df_total_inventory_value_days["total_inventory_value_days"] = df_total_inventory_value_days["inventory_level"] * df_total_inventory_value_days["unit_cost"]
        df_total_inventory_value_days["year"] = df_total_inventory_value_days["inventory_date"].dt.year
        df_total_inventory_value_days = (df_total_inventory_value_days.groupby("year", as_index=False)
                                         .agg(total_inventory_value_days=("total_inventory_value_days", "sum"),
                                              calendar_days=("inventory_date", "nunique")))
        df_total_inventory_value_days["total_inventory_value_days"] = (df_total_inventory_value_days["total_inventory_value_days"]
                                                                    .round(2))
        
        df = (df_total_usage_qty.merge(df_total_usage_value, on="year", how="left")
              .merge(df_non_stockout_days, on="year", how="left")
              .merge(df_total_inventory_value_days, on="year", how="left")
        )

        df["total_usage_qty"] = df["total_usage_qty"].fillna(0)
        df["total_usage_value"] = df["total_usage_value"].fillna(0)
        df["non_stockout_days"] = df["non_stockout_days"].fillna(0)
        df["item_no"] = item
        df = df[["item_no", "year", "total_usage_qty", "total_usage_value", "non_stockout_days", "total_inventory_value_days", "calendar_days"]]
        all_items.append(df)

    if all_items:
        return pd.concat(all_items, ignore_index=False).sort_values(["item_no", "year"]).reset_index(drop=True)
    else:
        return pd.DataFrame(columns=["item_no", "year", "total_usage_qty", "total_usage_value", "non_stockout_days", "total_inventory_value_days", "calendar_days"])


def build_po_status_base(
    item_list,
    df_purchase_line,
    df_purchase_line_archive,
    df_purchase_header,
    df_purchase_header_archive,
    df_purch_rcpt_header,
    df_purch_rcpt_line
):
    """
    Build item-level purchase order (PO) status dataset.

    This function reconstructs purchase order activity and evaluates
    fulfillment status by comparing ordered quantities against received quantities.

    It integrates active and archived purchase data to produce a unified
    PO status view, including open quantities, receipt flags, and aging metrics.

    Metrics Computed:
    - Quantity Ordered:
        Total quantity ordered per PO.

    - Quantity Received:
        Total quantity received per PO based on receipt records.

    - Open Quantity:
        Remaining unfulfilled quantity:
            qty_ordered - qty_received

    - Receipt Flag:
        Indicates whether a PO has at least one receipt.

    - Days Since Order:
        Number of days from order date to current date.

    - Stale Flag:
        Identifies POs that:
        - Have remaining open quantity
        - Are older than 365 days

    Logic:
    - Extract PO numbers from both active and archived purchase line tables.
    - Filter only valid purchase documents (document_type == 1).
    - Combine active and archived purchase headers.
    - Retain only released POs (status == 1).
    - Compute ordered quantities from purchase line data.
    - Compute received quantities from receipt tables.
    - Merge order and receipt data to determine fulfillment status.
    - Calculate open quantities and aging metrics.

    Args:
        item_list (list):
            List of item numbers to process.

        df_purchase_line (pd.DataFrame):
            Active purchase line data.

        df_purchase_line_archive (pd.DataFrame):
            Archived purchase line data.

        df_purchase_header (pd.DataFrame):
            Active purchase header data.

        df_purchase_header_archive (pd.DataFrame):
            Archived purchase header data.

        df_purch_rcpt_header (pd.DataFrame):
            Purchase receipt header data.

        df_purch_rcpt_line (pd.DataFrame):
            Purchase receipt line data.

    Returns:
        pd.DataFrame:
            Item-level PO status dataset with:
            - item_no
            - po_no
            - order_date
            - qty_ordered
            - qty_received
            - has_rcpt
            - open_qty
            - days_since_order
            - is_stale

    Notes:
    - Archive tables are used to reconstruct historical purchase activity.
    - Only released POs are considered.
    - Open quantity is clipped to zero to avoid negative values.
    - Stale POs indicate potential procurement inefficiencies or delays.
    """
    
    all_items = []
    for item in item_list:
        # =========================================================
        # STEP 1: Extract all POs for the item (active + archive)
        # =========================================================
        df_purchase_line_item = (df_purchase_line[(df_purchase_line ["item_no"] == item) &
            (df_purchase_line ["document_type"] == 1)])
        df_purchase_line_archive_item = (df_purchase_line_archive [(df_purchase_line_archive["item_no"] == item) & 
            (df_purchase_line_archive["document_type"] == 1)])

        # Extract PO numbers
        df_purchase_line_pos = df_purchase_line_item[["po_no"]]
        df_purchase_line_archive_pos = df_purchase_line_archive_item[["po_no"]]

        # Combine active + archive PO list
        df_purchase_line_all_pos = (
            pd.concat(
            [df_purchase_line_pos[["po_no"]], df_purchase_line_archive_pos[["po_no"]]],
            ignore_index=True
            )
            .dropna(subset=["po_no"])
            .drop_duplicates(subset=["po_no"])
            .reset_index(drop=True)
        )

        # List of all POs for the item
        all_pos_list = df_purchase_line_all_pos["po_no"].tolist()


        # =========================================================
        # STEP 2: Retrieve PO headers (active + archive)
        # ========================================================
        df_purchase_header_item = (
            df_purchase_header[df_purchase_header["po_no"].isin(all_pos_list)]
            [["po_no", "order_date", "status"]]
        )
        df_purchase_header_archive_item = (
            df_purchase_header_archive[df_purchase_header_archive["po_no"].isin(all_pos_list)]
            [["po_no", "order_date", "version_no", "status"]]
        )

        # Keep latest version per PO in archive (final state)
        df_purchase_header_archive_item = (df_purchase_header_archive_item
        .sort_values(["po_no", "version_no"])
        .drop_duplicates("po_no", keep="last")
        .reset_index(drop=True)
        )

        # =========================================================
        # STEP 3: Identify archive-only POs
        # =========================================================
        df_po_in_header_archive_only = (
            df_purchase_header_archive_item.merge(df_purchase_header_item[["po_no"]], on="po_no", how="left", indicator=True)
        )

        # Keep only those NOT present in active table
        df_po_in_header_archive_only = (
            df_po_in_header_archive_only[df_po_in_header_archive_only["_merge"] == "left_only"]
            [["po_no", "order_date", "status"]]
        )

        # Keep only released POs
        df_po_in_header_archive_only = df_po_in_header_archive_only[df_po_in_header_archive_only["status"] == 1]
    
        df_po_in_header_archive_only = df_po_in_header_archive_only[["po_no", "order_date"]]


        # =========================================================
        # STEP 4: Active released POs
        # =========================================================
        df_po_in_header_active_released = df_purchase_header_item[df_purchase_header_item["status"] == 1] 
    
         # Active POs are already unique -> keep earliest order date
        df_po_in_header_active_released = (df_po_in_header_active_released
            .sort_values("order_date")
            .drop_duplicates("po_no", keep="first")
            .reset_index(drop=True)
        )
        
        df_po_in_header_active_released = df_po_in_header_active_released[["po_no", "order_date"]]

        # =========================================================
        # STEP 5: Combine all valid POs
        # =========================================================
        df_pos = (
            pd.concat(
            [df_po_in_header_archive_only [["po_no", "order_date"]], 
            df_po_in_header_active_released[["po_no", "order_date"]]],
            ignore_index=True
            )
            .dropna(subset=["po_no"])
            .drop_duplicates(subset=["po_no"])
            .reset_index(drop=True)
        )

        # =========================================================
        # STEP 6: Compute ordered quantities
        # =========================================================
        df_qty_line_archived = (
            df_purchase_line_archive_item
            .sort_values("version_no") 
            .drop_duplicates(["po_no", "line_no"], keep="last")
            .reset_index(drop=True)
        )[["po_no", "quantity"]]

        # Aggregate archived quantities
        df_ordered_archived = (
            df_qty_line_archived
            .groupby("po_no", as_index=False)
            .agg(qty_ordered=("quantity", "sum"))
        )[["po_no", "qty_ordered"]]

        # Aggregate active quantities
        df_ordered_active = (
            df_purchase_line_item
            .groupby("po_no", as_index=False)
            .agg(qty_ordered=("quantity", "sum"))
        )[["po_no", "qty_ordered"]]

        # Merge active + archive -> prioritize active if available
        df_pos_with_qty_ordered = df_ordered_archived.merge(
            df_ordered_active, on="po_no", how="outer", suffixes=("_arch", "_active")
        )
        df_pos_with_qty_ordered["qty_ordered"] = (
            df_pos_with_qty_ordered["qty_ordered_active"]
            .fillna(df_pos_with_qty_ordered["qty_ordered_arch"])
        )
        df_pos_with_qty_ordered = df_pos_with_qty_ordered[["po_no", "qty_ordered"]]

        

        # Keep only POs with valid ordered quantity
        df_pos_final = df_pos.merge(df_pos_with_qty_ordered, on="po_no", how="inner")
    
        # =========================================================
        # STEP 7: Compute received quantities
        # =========================================================
        df_purch_rcpt_line_item =(df_purch_rcpt_line[df_purch_rcpt_line["item_no"] == item]) 

        # Link receipt header to line              
        df_rcpt = df_purch_rcpt_header.merge(df_purch_rcpt_line_item, on="ppr_no", how="inner")

        # Aggregate total received quantity per PO
        df_rcpt_po = df_rcpt.groupby("po_no", as_index=False).agg(
                                                qty_received=("quantity", "sum"))
        

        # Flag POs that have receipts
        df_rcpt_po_flagged = df_rcpt_po.copy()
        df_rcpt_po_flagged["has_rcpt"] = True

        # =========================================================
        # STEP 8: Combine ordered vs received
        # =========================================================
        df_purchase_vs_rcpt = df_pos_final.merge(
            df_rcpt_po_flagged,
            on="po_no",
            how="left"
        )

        # Convert missing receipt flag to False
        df_purchase_vs_rcpt["has_rcpt"] = df_purchase_vs_rcpt["has_rcpt"].astype(bool).fillna(False)

        # Fill missing received quantity with 0
        df_purchase_vs_rcpt["qty_received"] = df_purchase_vs_rcpt["qty_received"].fillna(0).astype(int)

         # Compute open quantity
        df_purchase_vs_rcpt["open_qty"] = (
            df_purchase_vs_rcpt["qty_ordered"] - df_purchase_vs_rcpt["qty_received"]
        )
        
        df_purchase_vs_rcpt["open_qty"] = df_purchase_vs_rcpt["open_qty"].clip(lower=0)

        # =========================================================
        # STEP 9: Compute aging and stale flag
        # =========================================================
        df_purchase_vs_rcpt["order_date"] = pd.to_datetime(df_purchase_vs_rcpt["order_date"], errors="coerce")

        today = pd.Timestamp.today().normalize()

        # Days since order creation
        df_purchase_vs_rcpt["days_since_order"] = (today - df_purchase_vs_rcpt["order_date"]).dt.days
    
        # Flag stale POs (open > 0 and older than 1 year)
        df_purchase_vs_rcpt["is_stale"] = ((df_purchase_vs_rcpt["open_qty"] > 0.01) &
                                            (df_purchase_vs_rcpt["days_since_order"] > 365)
        )
        # Add item identifier
        df_purchase_vs_rcpt["item_no"] = item

        # Final column selection
        df_purchase_vs_rcpt = df_purchase_vs_rcpt[["item_no", "po_no", "order_date", "qty_ordered", "qty_received", 
                              "has_rcpt", "open_qty", "days_since_order", "is_stale"]]
        all_items.append(df_purchase_vs_rcpt)

    # =========================================================
    # FINAL STEP: Combine all items
    # =========================================================
    if all_items:
        return pd.concat(all_items, ignore_index=True).sort_values(by="item_no").reset_index(drop=True)

    else:
        return pd.DataFrame(columns=["item_no", "po_no", "order_date", "qty_ordered", "qty_received", 
                              "has_rcpt", "open_qty", "days_since_order", "is_stale"])
  


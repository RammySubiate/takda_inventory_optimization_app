from datetime import timedelta, datetime
import pandas as pd
import numpy as np


    
class ItemConsumptionForecaster:

    def __init__(self):
        self.fitted = False
        self.rng = np.random.default_rng(seed=42)

    def fit(self, X, start_date, beg_quantity, h):
        self.X = X
        self.start_date = start_date + timedelta(days=1)
        self.beg_inventory = beg_quantity
        self.horizon = h
        self.fitted = True

    def predict_one(self, h):
        preds = self.rng.choice(self.X, size=(1, h)).cumsum() + self.beg_inventory
        return preds

    def predict(self, n_sims):
        preds = self.rng.choice(self.X, size=(n_sims, self.horizon)).cumsum(axis=1) + self.beg_inventory

        P05 = np.percentile(preds, 5, axis=0)
        P10 = np.percentile(preds, 10, axis=0)
        P25 = np.percentile(preds, 25, axis=0)
        P50 = np.percentile(preds, 50, axis=0)
        P75 = np.percentile(preds, 75, axis=0)
        P80 = np.percentile(preds, 80, axis=0)
        P90 = np.percentile(preds, 90, axis=0)
        P95 = np.percentile(preds, 95, axis=0)
        EV = np.mean(preds, axis=0)

        P_zero_stock = (preds < 0).sum(axis=0) / n_sims

        results = pd.DataFrame(
            data=np.vstack([P05, P10, P25, P50, P75, P80, P90, P95, EV, P_zero_stock]).T,
            index=pd.date_range(self.start_date, self.start_date + timedelta(days=self.horizon - 1)),
            columns=['p5', 'p10', 'p25', 'p50', 'p75', 'p80', 'p90', 'p95', 'ev', 'p_zero_stock']
            )
        
        return {'preds': preds, 'res': results}


class ItemArrivalForecaster:

    def __init__(self):
        pass
        self.rng = np.random.default_rng(seed=42)

    def set_forecast_horizon(self, h):
        self.horizon = h
        self.end_date = datetime.now() + timedelta(days=self.horizon)

    def fit_predict2(
        self,
        X,
        po_dates,
        quantities,   # 🔥 NEW: array of quantities
        start_date,
        h,
        n_sims=1000
    ):
        """
        Simulate arrivals for multiple PO dates with different quantities.

        Args:
            X : array-like
                Lead time distribution (in days)

            po_dates : array-like (datetime64)
                Purchase order dates

            quantities : array-like
                Quantity per PO (same length as po_dates)

            start_date : datetime
                Forecast start date

            h : int
                Horizon in days

            n_sims : int
                Number of simulations

        Returns
            np.ndarray
                Shape: (n_sims, horizon_days)
                Simulated inventory arrivals over time
        """

        self.X = X
        self.set_forecast_horizon(h)

        # Forecast timeline
        date_range = pd.date_range(
            start=start_date + timedelta(days=1),
            periods=self.horizon
        )
        dates_arr = date_range.values.reshape(1, -1)

        results = []

        for i, po_date in enumerate(po_dates):
            # simulate arrival dates
            lead_time_arr = (
                np.datetime64(po_date)
                + self.rng.choice(self.X, size=n_sims).astype("timedelta64[D]")
            )

            # check if arrived by each date
            arrivals = (lead_time_arr.reshape(-1, 1) <= dates_arr)

            # apply quantity per PO
            arrivals = arrivals * quantities[i]
           

            results.append(arrivals)

        # sum across all POs
        arrivals_result = np.sum(results, axis=0)

        return arrivals_result


def simulate_open_po_arrivals(open_po_receipt_dates, open_po_qty, start_date, horizon_days, n_sims):
    """
    Simulate ONLY the open PO arrivals using provided receipt dates.
    All sims get the same deterministic arrival (no random sampling).
    
    Args:
        open_po_receipt_dates: array of datetime64 — one receipt date per open PO
        open_po_qty: array of float — quantity per open PO
        start_date: datetime — forecast start date
        horizon_days: int — number of forecast days
        n_sims: int — number of simulations
    
    Returns:
        np.ndarray: shape (n_sims, horizon_days)
    """
    date_range = pd.date_range(
        start=start_date + timedelta(days=1),
        periods=horizon_days
    )
    dates_arr = date_range.values.reshape(1, -1)

    results = []
    for i, receipt_date in enumerate(open_po_receipt_dates):
        lead_time_arr = np.full(n_sims, np.datetime64(receipt_date))
        arrivals = (lead_time_arr.reshape(-1, 1) <= dates_arr)
        arrivals = arrivals * open_po_qty[i]
        results.append(arrivals)

    if results:
        return np.sum(results, axis=0)
    else:
        return np.zeros((n_sims, horizon_days))



# def estimate_reorder_point_from_policy(df, min_stock, proc_qty, lead_time, 
#                                         start_date, horizon_days,
#                                         open_po_arrival_median=None):
#     """
#     Now accepts the median open PO arrival curve to adjust the anchor point.
#     """
#     start_date = np.datetime64(start_date)
#     end_date = start_date + np.timedelta64(horizon_days, 'D')

#     # Adjust the expected value by adding open PO arrivals
#     ev = df['ev'].copy()
#     if open_po_arrival_median is not None:
#         ev = ev + open_po_arrival_median  # ← inventory is higher after open PO lands




#         above = ev > min_stock
#         below = ev <= min_stock

#         if above.all():
#             return np.array([], dtype='datetime64[D]')
#         elif below.all():
#             first_arr_date = df.index[0]
#         else: 
#             first_arr_date = ev[below].index[0]


#     # Rest is the same...
#     util_rate = np.abs(df['ev'].diff().mean())
#     proc_interval = proc_qty / util_rate

#     temp_dates = []
#     current = first_arr_date
#     while current <= end_date:
#         temp_dates.append(current)
#         current += np.timedelta64(int(proc_interval), 'D')

#     arrival_dates = np.array(temp_dates, dtype='datetime64[D]')
#     rop = arrival_dates - np.timedelta64(int(lead_time), 'D')
#     rop = np.maximum(rop, start_date)
#     rop = np.unique(rop)
    
#     return rop


def estimate_reorder_point_from_policy(df, min_stock, proc_qty, lead_time, 
                                        start_date, horizon_days,
                                        open_po_arrival_median=None):
    start_date = np.datetime64(start_date)
    end_date = start_date + np.timedelta64(horizon_days, 'D')

    # Adjusted EV with open PO
    ev = df['ev'].copy()
    if open_po_arrival_median is not None:
        ev = ev + open_po_arrival_median

    # Utilization rate (daily consumption)
    util_rate = np.abs(df['ev'].diff().mean())

    # Iteratively find reorder points
    rop_dates = []
    projected_ev = ev.copy()

    while True:
        below = projected_ev <= min_stock
        below_indices = projected_ev[below].index

        if len(below_indices) == 0:
            break  # inventory never drops below min — no more orders needed

        # First date inventory hits min
        hit_date = below_indices[0]

        # PO date = hit_date - lead_time (order must be placed earlier)
        po_date = hit_date - np.timedelta64(int(lead_time), 'D')
        po_date = max(po_date, start_date)

        if po_date > end_date:
            break

        rop_dates.append(po_date)

        # Simulate the effect: after hit_date, inventory gets proc_qty boost
        # This shifts the projected_ev up from hit_date onward
        hit_idx = projected_ev.index.get_indexer([hit_date], method='nearest')[0]
        projected_ev.iloc[hit_idx:] += proc_qty

    return np.array(rop_dates, dtype='datetime64[D]')

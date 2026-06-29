
import pandas as pd
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from urllib.parse import quote_plus

ENV_MAP = {
    "SCPC": ".env.sem_calaca",
    "SLPGC": ".env.slpgc",
    "SMPC": ".env.semirara"
}

ENTITY_CONFIG = {
    "SCPC": {
        "db": "CPC2019BC",
        "prefix": "Sem Calaca Power Corporation",
        "schema": "dbo"
    },
    "SLPGC": {
        "db": "CPC2019BC",
        "prefix": "Southwest Luzon Power Gen Corp",
        "schema": "dbo"
    },
    "SMPC": {
        "db": "Semirara2019BC",
        "prefix": "Semirara",
        "schema": "dbo"
    }
}

def create_db_engine():
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={os.getenv('DB_HOST')},{os.getenv('DB_PORT')};"
        f"DATABASE={os.getenv('DB_NAME')};"
        f"UID={os.getenv('DB_USER')};"
        f"PWD={os.getenv('DB_PASSWORD')};"
        f"TrustServerCertificate=Yes;"
    )
    conn_str = quote_plus(conn_str)
    return create_engine(f"mssql+pyodbc:///?odbc_connect={conn_str}")


def filter_non_inventoriable_items(
    df_item,
    entity_code,
    database_name,
    schema_name,
    company_name,
    engine
):
    """
    Filters out non-inventoriable items based on accounting transactions
    and entity-specific business rules.

    This function:
    1. Extracts valid item codes from G/L transactions linked to purchasing documents
    2. Applies entity-specific exclusion rules (services, software, non-stock items, etc.)
    3. Returns a cleaned dataset of inventoriable items

    Parameters
    ----------
    df_item : pandas.DataFrame
        Item master dataset containing item metadata such as:
        - item_no
        - description
        - unit_of_measure
        - item_category_code

    entity_code : str
        Short identifier of the entity (e.g., 'SCPC', 'SLPGC', 'SMPC').

    database_name : str
        Name of the SQL Server database (e.g., 'CPC2019BC').

    schema_name : str
        Database schema name (e.g., 'dbo').

    company_name : str
        Business Central company name used as table prefix.
        Example: 'Sem Calaca Power Corporation'

    engine : sqlalchemy.engine.Engine
        SQLAlchemy engine used to execute queries.

    Returns
    -------
    pandas.DataFrame
        Cleaned dataframe containing only inventoriable items.
        Includes all original item columns after filtering.
    """

    query = f"""
    WITH subquery AS (
    SELECT ppr.[No_] AS 'ItemCode'
        ,ppr.[Description]
    FROM [{database_name}].[{schema_name}].[{company_name}$G_L Entry] AS gl
    LEFT JOIN [{database_name}].[{schema_name}].[{company_name}$Purch_ Rcpt_ Line] AS ppr
    ON gl.[Document No_] = ppr.[Document No_]
    WHERE gl.[G_L Account No_] LIKE '14%' AND gl.[Amount] > 0 AND gl.[Document No_] LIKE 'PPR%'
    UNION
    SELECT pinv.[No_] AS 'ItemCode'
        ,pinv.[Description]
    FROM [{database_name}].[{schema_name}].[{company_name}$G_L Entry] AS gl
    LEFT JOIN [{database_name}].[{schema_name}].[{company_name}$Purch_ Inv_ Line] AS pinv
    ON gl.[Document No_] = pinv.[Document No_]
    WHERE gl.[G_L Account No_] LIKE '14%' AND gl.[Amount] > 0 AND gl.[Document No_] LIKE 'APV%'
    )

    SELECT DISTINCT ItemCode AS item_no FROM subquery
    """
    df_item_filtered = pd.read_sql(query, engine)


    if entity_code == "SCPC":

        df_item["item_code"] = df_item["item_no"].str[:3]

        """
        Software / Licenses
        - Identified by item codes 1CA / 2CA with descriptions containing
        'LICENSE' or 'SOFTWARE' and unit of measure = 'LOT'.
        - These are non-physical assets / not stocked or consumed through inventory.
        """
        mask_software = (
        df_item["item_code"].isin(["1CA", "2CA"]) &
        df_item["description"].str.contains("LICENSE|SOFTWARE", case=False, na=False) &
        (df_item["unit_of_measure"] == "LOT")
        )

        """
        Services
        - Items with item_category_code = 'SERVICES'.
        - These represent labor, repairs, rentals, inspections, and work orders.
        - Services do not have on-hand quantities and should not be included 
        in inventory movement or holding calculations.
        """
        mask_services = (
        df_item["item_category_code"] == "SERVICES"
        )


        """
        Work Orders, Coal, and Non-Stock Codes
        - Identified under item code 'CCO'
        - Coal is not treated as an inventoriable item
        since it is expected demand and sourced internally by the company.

        - Item codes such as 'WK0', 'IT-', 'C', 'Q', '2LA', 'CCO'
        - These are tracking, accounting, or operational references rather than
        physical inventory items.
        """
        mask_codes = df_item["item_code"].isin([
        "IT-", "WK0", "C", "Q", "2LA", "CCO"
        ])


        """
        Data Quality Failures
        - Records with missing descriptions or unit of measure.
        - These cannot be reliably classified or analyzed.
        """
        mask_bad_master = (
        (df_item["description"].isna()) |
        (df_item["unit_of_measure"].isna())
        )

        df_item["exclude_from_inventory"] = (
        mask_software |
        mask_services |
        mask_codes |
        mask_bad_master 
        )

        df_item_to_remove = df_item[df_item["exclude_from_inventory"]].reset_index(drop=True)
        df_item_to_remove = df_item_to_remove[["item_no", "description"]]

    if entity_code == "SLPGC":
        df_item["item_code"] = df_item["item_no"].str[:3]

        """
        Software / Licenses
        - Identified by item codes 1CA / 2CA with descriptions containing
            'LICENSE' or 'SOFTWARE' and unit of measure = 'LOT'.
        - These are non-physical assets / not stocked or consumed through inventory.
        """
        mask_software = (
            df_item["item_code"].isin(["1CA", "2CA"]) &
            df_item["description"].str.contains("LICENSE|SOFTWARE", case=False, na=False) &
            (df_item["unit_of_measure"] == "LOT")
        )

        mask_text = df_item["description"].str.contains(
            r"WORK ORDER|DELIVERY CHARGE|BROKERAGE|ADVANCES",
            case=False,
            na=False
        )

        """
        Services
        - Items with item_category_code = 'SERVICES'.
        - These represent labor, repairs, rentals, inspections, and work orders.
        - Services do not have on-hand quantities and should not be included 
            in inventory movement or holding calculations.
        """
        NON_INV_CATS = [
            "FIXEDASSET",
            "SSERVICES",
            "SERVICES",
            "SRVC-COAL",
            "SERV-EXP",
            # "BLDGCONS", FOR CONFIRMATION
            "FRGHT&STVD",
            "COAL"
        ]
        mask_services = df_item["item_category_code"].isin(NON_INV_CATS)

        """
        Data Quality Failures
        - Records with missing descriptions or unit of measure.
        - These cannot be reliably classified or analyzed.
        """
        mask_bad_master = (
            df_item["description"].isna() 
        )

        df_item["exclude_from_inventory"] = (
            mask_software |
            mask_text |
            mask_services |
            mask_bad_master 
        )

        df_item_to_remove = df_item[df_item["exclude_from_inventory"]].reset_index(drop=True)
        df_item_to_remove = df_item_to_remove[["item_no", "description"]]

    if entity_code == "SMPC":

        df_item["item_code"] = df_item["item_no"].str[:3]
        """
        Software / Licenses
        - Identified by item codes 1CA / 2CA with descriptions containing
            'LICENSE' or 'SOFTWARE' and unit of measure = 'LOT'.
        - These are non-physical assets / not stocked or consumed through inventory.
        """
        mask_software = (
            df_item["item_code"].isin(["1CA", "2CA"]) &
            df_item["description"].str.contains("LICENSE|SOFTWARE", case=False, na=False) &
            (df_item["unit_of_measure"] == "LOT")
        )


        """
        Services
        - Items with item_category_code = 'SERVICES'.
        - These represent labor, repairs, rentals, inspections, and work orders.
        - Services do not have on-hand quantities and should not be included 
            in inventory movement or holding calculations.
        """
        mask_services = (
            df_item["item_category_code"].isin(["SERVICES", "FIXEDASSET", "CS", "TA"])
        )


        """
        Work-order and tool/equipment items
        - WK0 items primarily represent services, project charges,
        installations, maintenance fees, logistics charges,
        and non-stock operational transactions.

        - TA0 items primarily represent reusable tools,
        measuring instruments, operational equipment,
        and durable maintenance devices that do not behave
        as fast-moving consumable inventory.
        """

        mask_codes = df_item["item_code"].isin(["WK0", "TA0"])
        

        df_item["exclude_from_inventory"] = (
            mask_software |
            mask_services |
            mask_codes
        )


        df_item_to_remove = df_item[df_item["exclude_from_inventory"]].reset_index(drop=True)
        df_item_to_remove = df_item_to_remove[["item_no", "description"]]
                        

    df_item_cleaned = df_item_filtered[~df_item_filtered["item_no"].isin(df_item_to_remove["item_no"])].copy()

    df_item_cleaned = df_item_cleaned[['item_no']].merge(df_item, on='item_no', how='left')


    df_item_cleaned = df_item_cleaned.dropna(subset=["item_no", "description"])
    df_item_cleaned = df_item_cleaned[
    (df_item_cleaned["item_no"].str.strip() != "") &
    (df_item_cleaned["description"].str.strip() != "")
    ]

    return df_item_cleaned

def load_nav_datasets(entity,
    df_item=False,
    df_journal_line=False,
    df_ledger_entry=False,
    df_pr_lines_archive=False,
    df_pr_header=False,
    df_pr_header_archive=False,
    df_purchase_line=False,
    df_purchase_header=False,
    df_purchase_line_archive=False,
    df_purchase_header_archive=False,
    df_purch_rcpt_header=False,
    df_purch_rcpt_line=False
):
    """
    Extracts and transforms datasets from Microsoft Dynamics NAV / Business Central
    for a given entity.

    This function:
    1. Loads environment-specific database credentials
    2. Connects to the appropriate database
    3. Extracts selected datasets based on input flags
    4. Applies standard cleaning and transformations
    5. Returns results as a dictionary of DataFrames

    Parameters
    ----------
    entity : str
        Entity code used to determine environment and configuration.
        Supported values:
        - 'SCPC'
        - 'SLPGC'
        - 'SMPC'

    df_item : bool, optional
        If True, loads and cleans item master data.

    df_journal_line : bool, optional
        If True, loads item journal line data.

    df_ledger_entry : bool, optional
        If True, loads item ledger entries with cancellation logic applied.

    df_pr_lines_archive : bool, optional
        If True, loads PR lines archive data.

    df_pr_header : bool, optional
        If True, loads PR header data.

    df_pr_header_archive : bool, optional
        If True, loads PR header archive data.

    df_purchase_line : bool, optional
        If True, loads purchase line data.

    df_purchase_header : bool, optional
        If True, loads purchase header data.

    df_purchase_line_archive : bool, optional
        If True, loads purchase line archive data.

    df_purchase_header_archive : bool, optional
        If True, loads purchase header archive data.

    df_purch_rcpt_header : bool, optional
        If True, loads purchase receipt header data.

    df_purch_rcpt_line : bool, optional
        If True, loads purchase receipt line data.

    Returns
    -------
    dict[str, pandas.DataFrame]
        Dictionary where keys are dataset names and values are cleaned DataFrames.

        Example:
        {
            "df_item": DataFrame,
            "df_ledger_entry": DataFrame
        }

    Raises
    ------
    ValueError
        If the provided entity is not supported.
    """
    

    if entity not in ENV_MAP:
        raise ValueError(f"Invalid entity: {entity}")

    load_dotenv(ENV_MAP[entity], override=True)

    config = ENTITY_CONFIG[entity]
    db = config["db"]
    prefix = config["prefix"]
    schema = config["schema"]

    engine = create_db_engine()
    out = {}

    if df_item:
        query = f"""
        SELECT 
            [No_],
            [Description],
            [Base Unit of Measure],
            [Unit Cost],
            [Item Category Code],
            [Search Description],
            [Description 2],
            [Description 3],
            [Vendor Item No_]
        FROM [{db}].[{schema}].[{prefix}$Item];
        """
        df_item = pd.read_sql(query, engine)

        df_item = df_item.rename(columns={
        "No_": "item_no",
        "Description": "description",
        "Base Unit of Measure": "unit_of_measure",
        "Unit Cost": "unit_cost",
        "Item Category Code": "item_category_code",
        "Search Description": "search_description",
        "Description 2": "description_2",
        "Description 3": "description_3",
        "Vendor Item No_": "vendor_item_no"
        })

        df_item_cleaned = filter_non_inventoriable_items(
                df_item=df_item,
                entity_code=entity,
                database_name=db,
                schema_name=schema,
                company_name=prefix,
                engine=engine
        )

        out["df_item"] = df_item_cleaned


    if df_journal_line:
        query = f"""
        SELECT 
        [Item No_],
        [Posting Date],
        [Unit Cost]
        FROM [{db}].[{schema}].[{prefix}$Item Journal Line];
        """

        df_journal_line = pd.read_sql(query, engine)

        # Renaming of columns
        df_journal_line_cleaned = df_journal_line.rename(columns={
        'Item No_': "item_no",
        'Posting Date': "posting_date",
        'Unit Cost': "unit_cost"
        })
        df_journal_line_cleaned["posting_date"] = pd.to_datetime(df_journal_line_cleaned["posting_date"])

        out["df_journal_line"] = df_journal_line_cleaned


    if df_ledger_entry:
        query = f"""
        /* ============================================================
        Purpose:
        Remove fully cancelled Purchase Receipt (PPR) ledger entries
        from inventory analysis.

        Business Logic:
        Some Purchase Receipts are later reversed/corrected, creating
        multiple ledger entries for the same (Document No_, Item No_)
        whose quantities cancel out to zero. These should not be
        treated as real inventory movements.

        Steps:
        1. Identify PPR purchase entries grouped by (Document No_, Item No_)
            where:
                - Entry Type = 0 (Purchase)
                - At least 2 entries exist (original + reversal)
                - Net quantity ≈ 0 (fully cancelled)

        2. Confirm that the pair corresponds to a corrected purchase
            receipt line (Correction = 1).

        3. Exclude those confirmed cancelled entries from the final result.

        Result:
        Returns Item Ledger Entries excluding cancelled PPR purchases,
        ensuring only true inventory movements remain for analysis.
        ============================================================ */


        /* ------------------------------------------------------------
        Step 1: Detect candidate cancelled PPR pairs
        ------------------------------------------------------------ */
        WITH cancel_pairs AS (
        SELECT
            [Document No_] AS doc_no,
            [Item No_]     AS item_no
        FROM [{db}].[{schema}].[{prefix}$Item Ledger Entry]
        WHERE [Document No_] LIKE 'PPR%'     -- Purchase Receipt documents
            AND [Entry Type] = 0               -- Purchase entries only
        GROUP BY [Document No_], [Item No_]
        HAVING COUNT(*) >= 2                 -- Must have reversal pair
            AND ABS(SUM([Quantity])) < 0.000001  -- Net quantity ≈ 0 (fully cancelled)
        ),

        /* ------------------------------------------------------------
        Step 2: Confirm true corrections using Purch. Receipt Line
        ------------------------------------------------------------ */
        confirmed AS (
        SELECT DISTINCT
            cp.doc_no,
            cp.item_no
        FROM cancel_pairs cp
        JOIN [{db}].[{schema}].[{prefix}$Purch_ Rcpt_ Line] prl
            ON prl.[Document No_] = cp.doc_no
            AND prl.[No_] = cp.item_no
        WHERE prl.[Correction] = 1           -- Confirmed reversal/correction
        )

        /* ------------------------------------------------------------
        Step 3: Return Item Ledger Entries excluding cancelled PPR
        ------------------------------------------------------------ */
        SELECT 
            ile.[Entry No_]
        ,ile.[Document No_]
        ,ile.[Item No_]
        ,ile.[Posting Date]
        ,ile.[Location Code]
        ,ile.[Entry Type]
        ,ile.[Quantity]
        ,ile.[Remaining Quantity]
        ,ile.[Open]
        ,ile.[Positive]
        ,ile.[Applies-to Entry]
        ,ile.[Expiration Date]

        FROM [{db}].[{schema}].[{prefix}$Item Ledger Entry] ile

        LEFT JOIN confirmed c
        ON c.doc_no = ile.[Document No_]
        AND c.item_no = ile.[Item No_]

        WHERE NOT (
        ile.[Document No_] LIKE 'PPR%'   -- Purchase Receipt
        AND ile.[Entry Type] = 0         -- Purchase entry
        AND c.doc_no IS NOT NULL         -- Confirmed cancelled pair
        );

        """
        df_ledger_entry = pd.read_sql(query, engine)

        df_ledger_entry.rename(columns={
        'Entry No_':'entry_no',
        'Document No_': "document_no",
        'Item No_': 'item_no',
        'Posting Date': 'posting_date',
        'Location Code': 'location_code',
        'Entry Type': 'entry_type',
        'Quantity': 'quantity',
        'Remaining Quantity': 'remaining_quantity',
        'Open': 'open',
        'Positive' : 'positive',
        'Applies-to Entry': "applies_to_entry",
        'Expiration Date': 'expiration_date'
        }, inplace=True)

        df_ledger_entry['posting_date'] = pd.to_datetime(df_ledger_entry["posting_date"])
        df_ledger_entry_cleaned = df_ledger_entry

        out["df_ledger_entry"] = df_ledger_entry_cleaned

    if df_pr_lines_archive:
        query = f"""
        SELECT 
        [Journal Batch Name],
        [No_],
        [Version No_]
        FROM [{db}].[{schema}].[{prefix}$PR Lines Archive]
        """
        df_pr_lines_archive = pd.read_sql(query, engine)


        df_pr_lines_archive = df_pr_lines_archive.rename(columns={
        "Journal Batch Name": "pr_no",
        "No_": "item_no",
        "Version No_": "version_no"
        })

        out["df_pr_lines_archive"] = df_pr_lines_archive

    if df_pr_header:
        query = f"""
        SELECT
        [No_],
        [PR Date],
        [Status]
        FROM [{db}].[{schema}].[{prefix}$PR Header]
        """
        df_pr_header =  pd.read_sql(query, engine)

        df_pr_header = df_pr_header.rename(columns={
        "No_": "pr_no",
        "PR Date": "pr_date",
        "Status": "status"
        })

        out["df_pr_header"] = df_pr_header


    if df_pr_header_archive:
        query = f"""
        SELECT 
        [No_],
        [PR Date],
        [Version No_]
        FROM [{db}].[{schema}].[{prefix}$PR Header Archive]
        """
        df_pr_header_archive = pd.read_sql(query, engine)


        df_pr_header_archive = df_pr_header_archive.rename(columns={
        "No_": "pr_no",
        "PR Date": "pr_date",
        "Version No_": "version_no"
        })

        df_pr_header_archive["pr_date"] = pd.to_datetime(df_pr_header_archive["pr_date"])

        out["df_pr_header_archive"] = df_pr_header_archive


    if df_purchase_line:
        query = f"""
        SELECT 
        [Document No_],
        [Document Type],
        [No_],
        [Quantity],
        [Outstanding Quantity],
        [Status]
        FROM [{db}].[{schema}].[{prefix}$Purchase Line]
        """
        df_purchase_line = pd.read_sql(query, engine)


        df_purchase_line = df_purchase_line.rename(columns={
        "Document No_": "po_no",
        "Document Type": "document_type",
        "No_": "item_no",
        "Quantity": "quantity",
        "Outstanding Quantity": "outstanding_quantity",
        "Status": "status"
        })


        out["df_purchase_line"] = df_purchase_line

    if df_purchase_header:
        query = f"""
        SELECT
        [No_],
        [PR No_],
        [Order Date],
        [Status],
        [Document Type],
        [Expected Receipt Date]
        FROM [{db}].[{schema}].[{prefix}$Purchase Header]
        """
        df_purchase_header = pd.read_sql(query, engine)


        df_purchase_header = df_purchase_header.rename(columns={
        "No_": "po_no",
        "PR No_": "pr_no",
        "Order Date": "order_date",
        "Status": "status",
        "Document Type": "document_type",
        "Expected Receipt Date": "expected_receipt_date"
        })
        df_purchase_header["order_date"] = pd.to_datetime(df_purchase_header["order_date"])
        df_purchase_header["expected_receipt_date"] = pd.to_datetime(df_purchase_header["expected_receipt_date"])

        out["df_purchase_header"] = df_purchase_header

    

    if df_purchase_line_archive:
        query = f"""
        SELECT 
        [Document No_],
        [Document Type],
        [No_],
        [Quantity],
        [Line No_],
        [Version No_]
        FROM [{db}].[{schema}].[{prefix}$Purchase Line Archive]
        """
        df_purchase_line_archive = pd.read_sql(query, engine)


        df_purchase_line_archive = df_purchase_line_archive.rename(columns={
        "Document No_": "po_no",
        "Document Type": "document_type",
        "No_": "item_no",
        "Quantity": "quantity",
        "Line No_": "line_no",
        "Version No_": "version_no"
        })

        out["df_purchase_line_archive"] = df_purchase_line_archive

    if df_purchase_header_archive:
        query = f"""
        SELECT
        [No_],
        [PR No_],
        [Order Date],
        [Version No_],
        [Status],
        [Expected Receipt Date]
        FROM [{db}].[{schema}].[{prefix}$Purchase Header Archive]
        """
        df_purchase_header_archive = pd.read_sql(query, engine)


        df_purchase_header_archive = df_purchase_header_archive.rename(columns={
        "No_": "po_no",
        "PR No_": "pr_no",
        "Order Date": "order_date",
        "Version No_": "version_no",
        "Status": "status",
        "Expected Receipt Date": "expected_receipt_date"
        })
        df_purchase_header_archive["order_date"] = pd.to_datetime(df_purchase_header_archive["order_date"])
        df_purchase_header_archive["expected_receipt_date"] = pd.to_datetime(df_purchase_header_archive["order_date"])

        out["df_purchase_header_archive"] = df_purchase_header_archive

    if df_purch_rcpt_header:
        query = f"""
        SELECT
        [No_],
        [Order No_]
        FROM [{db}].[{schema}].[{prefix}$Purch_ Rcpt_ Header]
        """
        df_purch_rcpt_header = pd.read_sql(query, engine)

        df_purch_rcpt_header = df_purch_rcpt_header.rename(columns={
        "No_": "ppr_no",
        "Order No_": "po_no"
        })

        out["df_purch_rcpt_header"] = df_purch_rcpt_header


    if df_purch_rcpt_line:
        query = f"""
        SELECT
        [Document No_], 
        [No_],
        [Posting Date],
        [Quantity],
        [Correction],
        [Type]
        FROM [{db}].[{schema}].[{prefix}$Purch_ Rcpt_ Line]
        """
        df_purch_rcpt_line = pd.read_sql(query, engine)


        df_purch_rcpt_line = df_purch_rcpt_line.rename(columns={
        "Document No_": "ppr_no",
        "No_": "item_no",
        "Posting Date": "ppr_posting_date",
        "Quantity": "quantity",
        "Correction": "correction",
        "Type": "type"
        })

        df_purch_rcpt_line["ppr_posting_date"] = pd.to_datetime(df_purch_rcpt_line["ppr_posting_date"])

        out["df_purch_rcpt_line"] = df_purch_rcpt_line

    return out
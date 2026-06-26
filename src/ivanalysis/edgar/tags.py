"""XBRL tag alias table (spec section 2.1).

Companies tag the same economic concept with different us-gaap elements, so each
model field maps to an *ordered* list of candidate tags. Ingestion takes the
first tag that has data for a period. Order = most-specific / most-common first.
"""

# model_attr -> [candidate us-gaap (or dei) tags], tried in order
TAG_ALIASES = {
    # Income statement
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
    ],
    "cogs": [
        "CostOfGoodsAndServicesSold",
        "CostOfRevenue",
        "CostOfGoodsSold",
    ],
    "gross_profit": ["GrossProfit"],
    "operating_expenses": [
        "OperatingExpenses",
        "OperatingCostsAndExpenses",
        "CostsAndExpenses",
    ],
    "depreciation": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "DepreciationAndAmortization",
        "Depreciation",
    ],
    "ebit": ["OperatingIncomeLoss"],
    "interest_expense": [
        "InterestExpense",
        "InterestAndDebtExpense",
        "InterestExpenseDebt",
    ],
    "ebt": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ],
    "taxes": ["IncomeTaxExpenseBenefit"],
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
    ],
    "preferred_dividends": [
        "PreferredStockDividendsAndOtherAdjustments",
        "DividendsPreferredStock",
    ],
    "diluted_shares": [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfShareOutstandingBasicAndDiluted",
    ],
    "eps": ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"],
    # Balance sheet
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "marketable_securities": [
        "MarketableSecuritiesCurrent",
        "ShortTermInvestments",
        "AvailableForSaleSecuritiesCurrent",
    ],
    "accounts_receivable": [
        "AccountsReceivableNetCurrent",
        "ReceivablesNetCurrent",
    ],
    "inventory": ["InventoryNet"],
    "other_current_assets": ["OtherAssetsCurrent"],
    "current_assets": ["AssetsCurrent"],
    "net_fixed_assets": [
        "PropertyPlantAndEquipmentNet",
    ],
    "total_assets": ["Assets"],
    "accounts_payable": [
        "AccountsPayableCurrent",
        "AccountsPayableAndAccruedLiabilitiesCurrent",
    ],
    "other_current_liabilities": ["OtherLiabilitiesCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "long_term_debt": [
        "LongTermDebtNoncurrent",
        "LongTermDebt",
        "LongTermDebtAndCapitalLeaseObligations",
    ],
    "total_liabilities": ["Liabilities"],
    "preferred_equity": [
        "PreferredStockValue",
        "PreferredStockValueOutstanding",
    ],
    "common_equity": [
        "StockholdersEquity",
        "CommonStockholdersEquity",
    ],
    "total_equity": [
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "StockholdersEquity",
    ],
    # Cash flow
    "cfo": ["NetCashProvidedByUsedInOperatingActivities"],
    "cfi": ["NetCashProvidedByUsedInInvestingActivities"],
    "cff": ["NetCashProvidedByUsedInFinancingActivities"],
    "net_change_cash": [
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
        "CashAndCashEquivalentsPeriodIncreaseDecrease",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ],
    "lease_payments": [
        "OperatingLeasePayments",
        "FinanceLeasePrincipalPayments",
    ],
}

# Tags that live in the dei taxonomy rather than us-gaap.
DEI_TAGS = {"EntityCommonStockSharesOutstanding"}

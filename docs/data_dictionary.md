# Data Dictionary

Definitions, units, and calculation methodologies for all metrics and
series used in the Energy Terminal.

---

## Instruments

### Crude Oil

| Ticker  | Name                 | Exchange | Unit      | Notes |
|---------|----------------------|----------|-----------|-------|
| `CL=F`  | WTI Crude Oil        | NYMEX    | USD/bbl   | US benchmark; physical delivery Cushing, OK |
| `BZ=F`  | Brent Crude Oil      | ICE      | USD/bbl   | Global benchmark; cash-settled |

### Natural Gas

| Ticker  | Name                | Exchange | Unit     | Notes |
|---------|---------------------|----------|----------|-------|
| `NG=F`  | Natural Gas (HH)    | NYMEX    | USD/MMBtu| Henry Hub, Louisiana delivery point |

### Refined Products (NYMEX)

| Ticker  | Name                  | Unit      | Notes |
|---------|-----------------------|-----------|-------|
| `RB=F`  | RBOB Gasoline         | USD/gal   | Reformulated Blendstock for Oxygenate Blending |
| `HO=F`  | Heating Oil / ULSD    | USD/gal   | Ultra-low sulphur diesel proxy |

---

## Derived Analytics

### 3-2-1 Crack Spread
**Definition:** Approximate refinery margin assuming 3 barrels of crude
produce 2 barrels of gasoline and 1 barrel of distillate.

**Formula:**
```
crack_3_2_1 = (2 × RBOB_bbl + 1 × ULSD_bbl − 3 × WTI) / 3
```
where `RBOB_bbl = RBOB_USC_per_gal × 42 / 100`
and  `ULSD_bbl = HO_USC_per_gal × 42 / 100`

**Unit:** USD per barrel  
**Reference:** CME Group Petroleum Crack Spread Handbook (2015)

---

### 2-1-1 Crack Spread
**Definition:** Equal-split gasoline/distillate refinery margin. Commonly
used for European (Brent-based) refinery margin approximation.

**Formula:**
```
crack_2_1_1 = (1 × RBOB_bbl + 1 × ULSD_bbl − 2 × Brent) / 2
```

**Unit:** USD per barrel

---

### Spark Spread
**Definition:** Profitability of gas-fired electricity generation.
Positive = generation is profitable; negative = uneconomical to generate.

**Formula:**
```
spark_spread = power_price_MWh − (gas_price_MMBtu × heat_rate_BTU_kWh / 1_000)
```

**Default heat rate:** 7,000 BTU/kWh (≈ 49% efficiency; combined-cycle gas turbine)  
**Unit:** USD per MWh  
**Reference:** EIA "Spark Spread" glossary

---

### Contango / Backwardation
**Contango:** Deferred futures price > spot/front price.
Implies positive carry cost; typical in oversupplied markets.

**Backwardation:** Spot/front price > deferred futures price.
Implies scarcity premium; typical in undersupplied markets.

**Term structure slope formula (linear OLS):**
```
slope = polyfit(tenors_months, prices, degree=1)[0]
```
Negative slope → backwardation; positive slope → contango.

---

### Annualised Roll Yield
**Definition:** Cost (or benefit) of rolling a futures position from the
front month into the next contract, annualised.

**Formula:**
```
monthly_roll    = (next_price − front_price) / front_price
annualised_roll = monthly_roll × (365 / days_to_expiry)
```
Positive in contango (roll cost); negative in backwardation (roll benefit).

---

### Heating Degree Days (HDD)
**Definition:** Measure of residential heating energy demand relative to
a base temperature of 18.3°C (65°F).

**Formula:** `HDD = max(0, 18.3 − T_mean)`

One HDD = one degree Celsius of average daily temperature below base.

---

### Cooling Degree Days (CDD)
**Definition:** Measure of residential cooling (air conditioning) energy
demand.

**Formula:** `CDD = max(0, T_mean − 18.3)`

---

## Risk Metrics

### Value at Risk (VaR)
**Definition:** Maximum expected loss at a given confidence level over a
given holding period.

**Historical VaR (95%, 1-day):**
```
VaR = −percentile(returns, 5%)
```

**Parametric VaR (Gaussian):**
```
VaR = −(μ + z_α × σ)   where z_0.95 = 1.645
```

**Multi-day scaling (square-root-of-time rule):**
```
VaR(T days) = VaR(1 day) × √T
```
Note: SRoT rule assumes i.i.d. returns; use with caution for fat-tailed
energy return distributions.

**Reference:** Jorion (2007), *Value at Risk*, 3rd ed., McGraw-Hill.

---

### Conditional VaR (CVaR / Expected Shortfall)
**Definition:** Expected loss *given that* the loss exceeds VaR.
A coherent risk measure satisfying sub-additivity.

**Formula:**
```
CVaR = −E[returns | returns ≤ VaR_quantile]
```

CVaR ≥ VaR always. Preferred by Basel III and FRTB frameworks.

**Reference:** Rockafellar & Uryasev (2000), *Journal of Risk*.

---

### Volatility Cone
**Definition:** Distribution of realised volatility for a given look-back
window over historical data. The current realised vol is plotted against
the historical percentile range.

**Annualisation:** `σ_annual = σ_daily × √252` (252 trading days assumed).

Interpretation:
- Current vol above 75th percentile → elevated regime
- Current vol below 25th percentile → compressed regime

---

## EIA Supply/Demand Data

### Inventory Change
**Definition:** Week-over-week change in US commercial crude oil
inventories as reported in the EIA Weekly Petroleum Status Report.
Released every Wednesday at 10:30 EST.

**Seasonal interpretation:**
- Build above seasonal norm → bearish price signal
- Draw vs seasonal norm → bullish price signal

### Refinery Utilisation Rate
**Definition:** Percentage of operable atmospheric crude distillation
capacity in use. Published weekly by EIA.

**Interpretation:** High utilisation (>90%) → tight refined product
supply. Low utilisation → maintenance season or demand weakness.

---

## Weather / Demand

### HDD/CDD Base Temperature
All HDD and CDD calculations use a **base of 18.3°C (65°F)**, which is
the US residential energy industry standard. European markets sometimes
use 15.5°C (60°F); this terminal uses the US convention consistently.

### Demand Centre Locations
| City      | Latitude | Longitude | Relevance |
|-----------|----------|-----------|-----------|
| New York  | 40.71    | −74.01    | Northeast US heating/cooling demand |
| Chicago   | 41.88    | −87.63    | Midwest US, Henry Hub basis |
| Houston   | 29.76    | −95.37    | Gulf Coast refining complex |
| London    | 51.51    | −0.12     | Northwest Europe gas/power |
| Rotterdam | 51.92    | 4.48      | ARA storage hub, NWE oil |
| Tokyo     | 35.69    | 139.69    | LNG demand proxy (JKM region) |

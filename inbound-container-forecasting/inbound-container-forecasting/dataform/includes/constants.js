// Shared helpers for SQLX files. Available in SQLX as `constants.<name>`.
const HORIZON = () => parseInt(dataform.projectConfig.vars.forecast_horizon_days, 10);

// "LAG(col, n) OVER w AS col_lag_n" for each lag.
function lagCols(col, lags) {
  return lags.map(n => `LAG(${col}, ${n}) OVER w AS ${col}_lag_${n}`).join(",\n  ");
}

// Rolling mean over the `size` rows that END `shift` rows before the current row.
function rollingMean(col, size, shift) {
  return `AVG(${col}) OVER (PARTITION BY dc_id ORDER BY arrival_date ` +
         `ROWS BETWEEN ${size + shift - 1} PRECEDING AND ${shift} PRECEDING) AS ${col}_roll${size}_mean`;
}

module.exports = { HORIZON, lagCols, rollingMean };

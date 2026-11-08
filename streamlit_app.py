import streamlit as st
import pandas as pd
from snowflake.snowpark.context import get_active_session

# Page Configuration
st.set_page_config(
    page_title="Healthcare Executive Analytics Dashboard",
    layout="wide"
)

st.title("🏥 Healthcare Clinical & Revenue Cycle Analytics")
st.caption("Powered by AWS S3 + Snowflake Medallion Architecture (Bronze → Silver → Gold) & Streamlit in Snowflake")

# Connect to active Snowflake session
session = get_active_session()

# ----------------------------------------------------------------------------
# 1. Load Gold Views into Pandas DataFrames
# ----------------------------------------------------------------------------
df_monthly = session.sql("""
    SELECT
        TO_VARCHAR(admission_month, 'YYYY-MM') AS month_label,
        admission_month,
        total_encounters,
        unique_patients,
        avg_length_of_stay_days,
        readmission_count,
        readmission_rate_pct,
        total_billed_charges,
        total_allowed_amount,
        total_insurance_paid,
        net_collection_rate_pct,
        claim_denial_rate_pct,
        avg_days_in_ar
    FROM HEALTHCARE_DB.GOLD.vw_monthly_executive_kpis
    ORDER BY admission_month
""").to_pandas()

df_dept = session.sql("""
    SELECT
        facility_name,
        department,
        total_encounters,
        avg_los_days,
        readmission_rate_pct,
        avg_cost_per_encounter,
        total_reimbursement,
        avg_provider_satisfaction
    FROM HEALTHCARE_DB.GOLD.vw_department_facility_scorecard
    ORDER BY total_encounters DESC
""").to_pandas()

df_payer = session.sql("""
    SELECT
        insurance_payer,
        total_claims,
        paid_claims,
        denied_claims,
        denial_rate_pct,
        total_billed,
        total_allowed,
        total_paid_by_payer,
        avg_days_to_payment,
        top_denial_reason
    FROM HEALTHCARE_DB.GOLD.vw_payer_denial_analysis
    ORDER BY total_billed DESC
""").to_pandas()

df_diag = session.sql("""
    SELECT
        primary_icd10_code,
        diagnosis_description,
        age_group,
        encounter_volume,
        avg_los_days,
        readmission_rate_pct,
        avg_systolic_bp,
        avg_billed_per_case
    FROM HEALTHCARE_DB.GOLD.vw_diagnosis_clinical_cohorts
    ORDER BY encounter_volume DESC
""").to_pandas()

# ----------------------------------------------------------------------------
# 2. Top-Level Executive KPI Cards
# ----------------------------------------------------------------------------
total_encounters = int(df_monthly["TOTAL_ENCOUNTERS"].sum())
overall_readm_rate = round(df_monthly["READMISSION_COUNT"].sum() * 100.0 / max(1, total_encounters), 2)
overall_los = round(df_monthly["AVG_LENGTH_OF_STAY_DAYS"].mean(), 2)
total_billed_m = df_monthly["TOTAL_BILLED_CHARGES"].sum() / 1_000_000
overall_denial_rate = round(df_payer["DENIED_CLAIMS"].sum() * 100.0 / max(1, df_payer["TOTAL_CLAIMS"].sum()), 2)
overall_ar_days = round(df_monthly["AVG_DAYS_IN_AR"].mean(), 1)

col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Total Encounters", f"{total_encounters:,}")
col2.metric("30-Day Readmission Rate", f"{overall_readm_rate}%")
col3.metric("Avg Length of Stay", f"{overall_los} Days")
col4.metric("Total Billed Charges", f"${total_billed_m:.2f}M")
col5.metric("Claim Denial Rate", f"{overall_denial_rate}%")
col6.metric("Avg Days in AR", f"{overall_ar_days} Days")

st.divider()

# ----------------------------------------------------------------------------
# 3. Sidebar / Interactive Filters
# ----------------------------------------------------------------------------
st.subheader("📈 Monthly Clinical & Financial Trend Analysis")

chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.markdown("**Monthly 30-Day Readmission Rate (%) vs. Claim Denial Rate (%)**")
    st.line_chart(
        df_monthly.set_index("MONTH_LABEL")[["READMISSION_RATE_PCT", "CLAIM_DENIAL_RATE_PCT"]]
    )

with chart_col2:
    st.markdown("**Monthly Billed Charges vs. Insurance Paid ($)**")
    st.area_chart(
        df_monthly.set_index("MONTH_LABEL")[["TOTAL_BILLED_CHARGES", "TOTAL_INSURANCE_PAID"]]
    )

st.divider()

# ----------------------------------------------------------------------------
# 4. Department & Payer Breakdown
# ----------------------------------------------------------------------------
mid_col1, mid_col2 = st.columns(2)

with mid_col1:
    st.subheader("🏥 Clinical Performance by Department")
    selected_facility = st.selectbox(
        "Filter by Hospital Facility:",
        ["All Facilities"] + sorted(df_dept["FACILITY_NAME"].unique().tolist())
    )
    if selected_facility != "All Facilities":
        df_dept_filtered = df_dept[df_dept["FACILITY_NAME"] == selected_facility]
    else:
        df_dept_filtered = df_dept.groupby("DEPARTMENT", as_index=False).agg({
            "TOTAL_ENCOUNTERS": "sum",
            "AVG_LOS_DAYS": "mean",
            "READMISSION_RATE_PCT": "mean",
            "AVG_COST_PER_ENCOUNTER": "mean",
            "AVG_PROVIDER_SATISFACTION": "mean"
        })
    st.bar_chart(df_dept_filtered.set_index("DEPARTMENT")["TOTAL_ENCOUNTERS"])
    st.dataframe(df_dept_filtered, use_container_width=True)

with mid_col2:
    st.subheader("💳 Revenue Cycle & Payer Denial Scorecard")
    st.bar_chart(df_payer.set_index("INSURANCE_PAYER")["DENIAL_RATE_PCT"])
    st.dataframe(
        df_payer[[
            "INSURANCE_PAYER", "TOTAL_CLAIMS", "DENIAL_RATE_PCT",
            "TOTAL_BILLED", "TOTAL_PAID_BY_PAYER", "AVG_DAYS_TO_PAYMENT", "TOP_DENIAL_REASON"
        ]],
        use_container_width=True
    )

st.divider()

# ----------------------------------------------------------------------------
# 5. High-Burden ICD-10 Diagnosis Cohort Explorer
# ----------------------------------------------------------------------------
st.subheader("🧬 High-Burden ICD-10 Diagnosis & Patient Age Cohorts")
selected_age = st.multiselect(
    "Filter by Patient Age Group:",
    options=sorted(df_diag["AGE_GROUP"].unique().tolist()),
    default=sorted(df_diag["AGE_GROUP"].unique().tolist())
)
df_diag_filtered = df_diag[df_diag["AGE_GROUP"].isin(selected_age)]
st.dataframe(df_diag_filtered, use_container_width=True)

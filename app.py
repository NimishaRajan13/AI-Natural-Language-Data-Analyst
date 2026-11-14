
import os
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
import sqlglot
from sqlglot import exp
from dotenv import load_dotenv
from google import genai
from google.genai.errors import APIError

# ==========================================
# 1. CONFIGURATION
# ==========================================

load_dotenv()

DB_PATH = Path(__file__).parent / "Ecommerce_Sales.db"
MODEL = "gemini-3.1-flash-lite"

MAX_ROWS = 100
QUERY_TIMEOUT = 5
MAX_AI_REQUESTS_PER_SESSION = 20

st.set_page_config(
    page_title="AI Data Analyst | Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

def get_api_key():
    try:
        key = st.secrets.get("GEMINI_API_KEY")
        if key:
            return key
    except Exception:
        pass

    return os.getenv("GEMINI_API_KEY")


# ==========================================
# 2. STYLING
# ==========================================

st.markdown("""
<style>
.block-container {
    padding-top: 2rem;
    padding-bottom: 2rem;
    max-width: 1450px;
}
[data-testid="stMetric"] {
    background: rgba(120,120,120,0.09);
    border: 1px solid rgba(150,150,150,0.18);
    border-radius: 12px;
    padding: 18px;
}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. DATABASE SCHEMA
# ==========================================

TABLE_COLUMNS = {
    "products": {
        "product_id", "product_name", "category",
        "unit_price_inr", "unit_cost_inr"
    },
    "order_items": {
        "order_item_id", "order_id", "product_id",
        "quantity", "discount_pct"
    },
    "orders": {
        "order_id", "customer_id", "order_date",
        "order_status", "payment_method"
    },
    "customers": {
        "customer_id", "customer_name", "segment",
        "city", "region_id", "signup_date"
    },
    "regions": {
        "region_id", "region_name", "country"
    }
}

SCHEMA = """
Products(Product_ID, Product_Name, Category,
         Unit_Price_INR, Unit_Cost_INR)

Order_Items(Order_Item_ID, Order_ID, Product_ID,
            Quantity, Discount_Pct)

Orders(Order_ID, Customer_ID, Order_Date,
       Order_Status, Payment_Method)

Customers(Customer_ID, Customer_Name, Segment,
          City, Region_ID, Signup_Date)

Regions(Region_ID, Region_Name, Country)

RELATIONSHIPS:
Orders.Customer_ID = Customers.Customer_ID
Order_Items.Order_ID = Orders.Order_ID
Order_Items.Product_ID = Products.Product_ID
Customers.Region_ID = Regions.Region_ID

ORDER VALUE:
Quantity * Unit_Price_INR *
(1 - Discount_Pct / 100.0)

PROFIT ESTIMATE:
Quantity * (
    Unit_Price_INR * (1 - Discount_Pct / 100.0)
    - Unit_Cost_INR
)

Unless a suitable order status is explicitly
selected, label monetary sales totals as
order value rather than realized revenue.
"""

# ==========================================
# 4. DATABASE CONNECTION
# ==========================================

def get_connection():
    uri = DB_PATH.resolve().as_uri() + "?mode=ro"

    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only = ON")
    conn.execute("PRAGMA busy_timeout = 3000")

    return conn


def get_database_counts():
    counts = {}

    with get_connection() as conn:
        for table in TABLE_COLUMNS:
            counts[table.title()] = conn.execute(
                f'SELECT COUNT(*) FROM "{table}"'
            ).fetchone()[0]

    return counts


# ==========================================
# 5. SQL VALIDATION
# ==========================================

ALLOWED_FUNCTIONS = {
    "ROUND", "COALESCE", "IFNULL", "NULLIF", "ABS", "LOWER",
    "UPPER", "SUBSTR", "LENGTH", "TRIM", "STRFTIME", "DATE",
    "DATETIME", "JULIANDAY", "SUM", "COUNT", "AVG", "MIN", "MAX",
    "TOTAL"
}


def validate_sql(sql):
    """Conservatively validate the shape of a model-generated query."""
    if not isinstance(sql, str) or not sql.strip() or len(sql) > 12000:
        raise ValueError("SQL is empty or too long.")
    if "--" in sql or "/*" in sql or "*/" in sql:
        raise ValueError("SQL comments are not permitted.")

    try:
        statements = sqlglot.parse(sql, read="sqlite", error_level="RAISE")
    except Exception as error:
        raise ValueError("Invalid SQL syntax.") from error

    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise ValueError("Only one SELECT query is allowed.")
    query = statements[0]

    forbidden = (
        exp.Subquery, exp.Union, exp.Intersect, exp.Except,
        exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Alter,
        exp.Create, exp.Command, exp.Pragma, exp.Attach, exp.Detach,
        exp.Window, exp.Star
    )
    # COUNT(*) is valid, but all other star expansions are blocked.
    for node in query.walk():
        if isinstance(node, forbidden):
            if isinstance(node, exp.Star) and isinstance(node.parent, exp.Count):
                continue
            raise ValueError("Unsupported or unsafe SQL structure.")

    if query.args.get("with_") or query.args.get("into"):
        raise ValueError("CTEs and SELECT INTO are not permitted.")

    tables = list(query.find_all(exp.Table))
    if not tables or len(tables) > 5:
        raise ValueError("Query must use between 1 and 5 tables.")
    joins = list(query.find_all(exp.Join))
    if len(joins) > 4:
        raise ValueError("Too many JOIN operations.")
    if any(j.args.get("kind", "").upper() == "CROSS" for j in joins):
        raise ValueError("CROSS JOIN is not permitted.")

    aliases = {}
    for table in tables:
        name = table.name.lower()
        if table.args.get("db") or table.args.get("catalog"):
            raise ValueError("Database-qualified table names are not permitted.")
        if name not in TABLE_COLUMNS:
            raise ValueError(f"Table not permitted: {name}")
        alias = (table.alias or table.name).lower()
        if alias in aliases:
            raise ValueError("Duplicate table alias.")
        aliases[alias] = name

    for column in query.find_all(exp.Column):
        name = column.name.lower()
        if column.args.get("db") or column.args.get("catalog"):
            raise ValueError("Database-qualified columns are not permitted.")
        if column.table:
            alias = column.table.lower()
            if alias not in aliases or name not in TABLE_COLUMNS[aliases[alias]]:
                raise ValueError(f"Column not permitted: {column.sql()}")
        else:
            matches = sum(name in TABLE_COLUMNS[t] for t in aliases.values())
            # An unqualified reference must match exactly one available table.
            # Output aliases in ORDER BY are handled by SQLite's authorizer.
            output_aliases = {
                item.alias.lower() for item in query.expressions if item.alias
            }
            if matches != 1 and not (name in output_aliases and matches == 0):
                raise ValueError(f"Unknown or ambiguous column: {name}")

    for func in query.find_all(exp.Anonymous):
        if func.name.upper() not in ALLOWED_FUNCTIONS:
            raise ValueError(f"Function not permitted: {func.name}")

    return query


def readonly_authorizer(action, arg1, arg2, db_name, source):
    """Enforce table, column and function permissions inside SQLite itself."""
    if action == sqlite3.SQLITE_SELECT:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_READ:
        table = (arg1 or "").lower()
        column = (arg2 or "").lower()
        if db_name == "main" and table in TABLE_COLUMNS:
            # SQLite may report an empty column for COUNT(*)/existence checks.
            if not column or column in TABLE_COLUMNS[table]:
                return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION:
        function_name = (arg2 or arg1 or "").upper()
        if function_name in ALLOWED_FUNCTIONS:
            return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


# ==========================================
# 6. GEMINI CLIENT
# ==========================================

def get_gemini_client():
    api_key = get_api_key()

    if not api_key:
        raise ValueError(
            "Gemini API key is missing. "
            "Check your .env file or Streamlit secrets."
        )

    return genai.Client(api_key=api_key)


def call_gemini(prompt):
    client = get_gemini_client()

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt
        )

        result = (response.text or "").strip()

        if not result:
            raise ValueError(
                "Gemini returned an empty response."
            )

        return result

    except APIError as error:
        if error.code == 503:
            raise RuntimeError(
                "Gemini is temporarily busy. "
                "Please try again later."
            ) from error

        if error.code == 429:
            raise RuntimeError(
                "Gemini API quota or rate limit reached. "
                "Please try again later."
            ) from error

        raise RuntimeError(
            f"Gemini API error (code {error.code})."
        ) from error


# ==========================================
# 7. SQL GENERATION
# ==========================================

def generate_sql(question):
    prompt = f"""
You are an expert SQLite data analyst.

Generate exactly one SQLite SELECT query.

DATABASE SCHEMA:
{SCHEMA}

RULES:
1. Return SQL only, without markdown.
2. Use only the supplied tables and columns.
3. Use explicit JOINs and qualified columns.
4. Do not use CTEs or nested queries.
5. Do not use database-changing operations.
6. Limit results to 100 rows.
7. Use clear column aliases.
8. Round monetary calculations to 2 decimals.
9. Do not invent columns or business assumptions.
10. If order status is unspecified, call the
    monetary result order value.

USER QUESTION:
{question}
"""

    sql = call_gemini(prompt)

    if sql.startswith("```"):
        sql = sql.split("\n", 1)[-1]
        sql = sql.rsplit("```", 1)[0].strip()

    return sql


# ==========================================
# 8. EXECUTE SQL
# ==========================================

def execute_sql(sql):
    validate_sql(sql)
    safe_sql = f"SELECT * FROM ({sql.strip().rstrip(';')}) LIMIT {MAX_ROWS}"

    # A read-only connection, SQLite authorizer, and progress timeout provide
    # independent protections beyond the model prompt and SQL parser.
    with closing(get_connection()) as conn:
        conn.set_authorizer(readonly_authorizer)
        started = time.monotonic()

        def progress_handler():
            return int(time.monotonic() - started > QUERY_TIMEOUT)

        conn.set_progress_handler(progress_handler, 1000)
        try:
            return pd.read_sql_query(safe_sql, conn)
        finally:
            conn.set_progress_handler(None, 0)
            conn.set_authorizer(None)


# ==========================================
# 9. AI BUSINESS INSIGHTS
# ==========================================

def generate_insights(question, df):
    if df.empty:
        return "No matching records found."

    prompt = f"""
You are a professional business analyst.

USER QUESTION:
{question}

QUERY RESULTS:
{df.to_csv(index=False)}

RULES:
- Use only the supplied results.
- Never invent numbers or causes.
- Provide 3 to 5 concise insights.
- Mention useful comparisons.
- Clearly explain limitations.
- Do not confuse order value with
  confirmed realized revenue.
- Monetary values are in INR.
- Write in simple professional English.
"""

    return call_gemini(prompt)


# ==========================================
# 10. SIDEBAR
# ==========================================

with st.sidebar:
    st.title("📊 AI Analyst")
    st.caption("E-Commerce Intelligence Platform")

    st.divider()

    page = st.radio(
        "Navigation",
        ["AI Data Analysis", "Database Overview"]
    )

    st.divider()

    st.subheader("Technology Stack")
    st.write("🤖 Google Gemini AI")
    st.write("🐍 Python")
    st.write("🗄️ SQLite")
    st.write("📊 Plotly")
    st.write("🌐 Streamlit")


# ==========================================
# 11. DATABASE OVERVIEW
# ==========================================

if page == "Database Overview":
    st.title("🗄️ Database Overview")

    try:
        counts = get_database_counts()
        cols = st.columns(5)

        for col, (name, count) in zip(
            cols, counts.items()
        ):
            col.metric(name, count)

        st.divider()
        st.subheader("Database Tables")

        st.dataframe(
            pd.DataFrame([
                {"Table": name, "Records": count}
                for name, count in counts.items()
            ]),
            hide_index=True,
            use_container_width=True
        )

    except Exception as error:
        st.error(f"Database error: {error}")


# ==========================================
# 12. AI DATA ANALYSIS
# ==========================================

else:
    st.title("🤖 AI-Powered Data Analyst")

    st.write(
        "Analyze products, customers, regions, "
        "orders, and sales using natural language."
    )

    st.divider()

    st.subheader("💬 Ask Your Data")

    question = st.text_input(
        "Enter your business question",
        placeholder="Which region has the highest order value?"
    )

    # Counts Gemini requests for both analysis and AI insights in this session.
    if "ai_requests_used" not in st.session_state:
        st.session_state["ai_requests_used"] = 0

    remaining = max(0, MAX_AI_REQUESTS_PER_SESSION - st.session_state["ai_requests_used"])
    st.caption(f"AI requests remaining this session: {remaining} / {MAX_AI_REQUESTS_PER_SESSION}")

    if st.button(
        "🔍 Analyze Data", type="primary",
        disabled=remaining == 0,
    ):

        if not question.strip():
            st.warning("Please enter a question.")

        else:
            # Count the request before contacting Gemini, even if it fails.
            st.session_state["ai_requests_used"] += 1
            try:
                with st.spinner("Analyzing your data..."):
                    sql = generate_sql(question)
                    df = execute_sql(sql)

                st.session_state["result_df"] = df
                st.session_state["result_sql"] = sql
                st.session_state["result_question"] = question
                st.session_state["result_insights"] = None

            except Exception as error:
                st.error(f"Analysis failed: {error}")

    # ======================================
    # 13. RESULTS AND KPIs
    # ======================================

    if "result_df" in st.session_state:
        df = st.session_state["result_df"]

        st.divider()
        st.success("Analysis completed successfully!")

        st.subheader("📌 Analysis Summary")

        cols = st.columns(3)

        cols[0].metric("Rows Returned", len(df))
        cols[1].metric("Columns Returned", len(df.columns))

        numeric_cols = df.select_dtypes(
            include="number"
        ).columns.tolist()

        if numeric_cols:
            first_numeric = numeric_cols[0]

            cols[2].metric(
                f"Sum of {first_numeric}",
                f"{df[first_numeric].sum():,.2f}"
            )
        else:
            cols[2].metric("Numeric Columns", 0)

        st.divider()
        st.subheader("📋 Analysis Results")

        st.dataframe(
            df,
            hide_index=True,
            use_container_width=True
        )

        st.download_button(
            "⬇️ Download Results as CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="ai_analysis_results.csv",
            mime="text/csv"
        )

        # ==================================
        # 14. INTERACTIVE CHARTS
        # ==================================

        text_cols = df.select_dtypes(
            include=["object", "string"]
        ).columns.tolist()

        numeric_cols = df.select_dtypes(
            include="number"
        ).columns.tolist()

        if not df.empty and text_cols and numeric_cols:
            st.divider()
            st.subheader("📊 Interactive Visualization")

            left, right = st.columns(2)

            with left:
                chart_type = st.selectbox(
                    "Chart Type",
                    ["Bar Chart", "Line Chart", "Pie Chart"]
                )

            with right:
                value_col = st.selectbox(
                    "Measure",
                    numeric_cols
                )

            category_col = st.selectbox(
                "Category",
                text_cols
            )

            if chart_type == "Bar Chart":
                fig = px.bar(
                    df,
                    x=category_col,
                    y=value_col,
                    color=category_col,
                    text_auto=True,
                    title=f"{value_col} by {category_col}"
                )
                fig.update_layout(showlegend=False)

            elif chart_type == "Line Chart":
                fig = px.line(
                    df,
                    x=category_col,
                    y=value_col,
                    markers=True,
                    title=f"{value_col} by {category_col}"
                )

            else:
                fig = px.pie(
                    df,
                    names=category_col,
                    values=value_col,
                    title=f"{value_col} Distribution"
                )

            st.plotly_chart(
                fig,
                use_container_width=True
            )

        # ==================================
        # 15. AI INSIGHTS
        # ==================================

        st.divider()
        st.subheader("🧠 AI Business Insights")

        if st.button(
            "✨ Generate AI Insights",
            disabled=(st.session_state["ai_requests_used"] >= MAX_AI_REQUESTS_PER_SESSION),
        ):
            # Insights also consume Gemini API quota.
            st.session_state["ai_requests_used"] += 1
            try:
                with st.spinner("Generating insights..."):
                    st.session_state["result_insights"] = (
                        generate_insights(
                            st.session_state["result_question"],
                            df
                        )
                    )

            except Exception as error:
                st.error(
                    f"Insight generation failed: {error}"
                )

        if st.session_state.get("result_insights"):
            st.markdown(
                st.session_state["result_insights"]
            )

        with st.expander("🔎 View Generated SQL"):
            st.code(
                st.session_state["result_sql"],
                language="sql"
            )


# ==========================================
# 16. FOOTER
# ==========================================

st.divider()

st.caption(
    "AI-Powered Natural Language Data Analyst | "
    "Gemini AI • Python • SQLite • Streamlit • Plotly"
)

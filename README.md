# 📊 AI-Powered Natural Language Data Analyst

### Transform Business Questions into SQL Queries, Interactive Visualizations, and AI-Generated Insights

An AI-powered data analytics application built using **Python, Streamlit, Google Gemini AI, SQLite, Pandas, and Plotly**.

This project allows users to analyze e-commerce data using everyday English without writing SQL queries manually. The application converts natural language questions into SQL, retrieves relevant data, generates interactive visualizations, and provides AI-powered business insights.

## 🚀 Live Demo

**Try the application:** [AI Data Analyst — Streamlit](https://ai-natural-language-analyst.streamlit.app/)

*Update this link if your deployed Streamlit URL is different.*

## ✨ Key Features

- **Natural Language to SQL:** Converts English business questions into SQLite queries using Google Gemini AI.
- **Automated Data Analysis:** Executes validated SQL queries against an e-commerce database.
- **Interactive Dashboard:** Visualizes results using bar charts, line charts, and pie charts.
- **AI-Powered Business Insights:** Generates easy-to-understand insights from query results.
- **Database Overview:** Displays table information and record counts.
- **CSV Export:** Allows users to download analysis results.
- **SQL Query Transparency:** Displays generated SQL queries for learning and verification.
- **SQL Security:** Uses read-only database access, query validation, and execution restrictions.
- **Session Usage Limit:** Includes a 20-request-per-session limit for AI operations.

## 🛠️ Technology Stack

| Technology | Purpose |
|---|---|
| Python | Backend application logic |
| Streamlit | Interactive web application |
| Google Gemini AI | Natural language processing and SQL generation |
| SQLite | Relational database |
| Pandas | Data processing and analysis |
| Plotly | Interactive data visualization |
| SQLGlot | SQL parsing and validation |
| Git & GitHub | Version control and source code management |
| Streamlit Community Cloud | Application deployment |

## 🗄️ Database Architecture

The application uses a synthetic e-commerce dataset containing five relational tables.

| Table | Records | Description |
|---|---:|---|
| Products | 40 | Product information, categories, prices, and costs |
| Customers | 120 | Customer profiles and geographical information |
| Orders | 500 | Customer orders, dates, statuses, and payment methods |
| Order_Items | 1,017 | Ordered products, quantities, and discounts |
| Regions | 5 | Regional information |

### Database Relationships

- `Orders.Customer_ID` → `Customers.Customer_ID`
- `Order_Items.Order_ID` → `Orders.Order_ID`
- `Order_Items.Product_ID` → `Products.Product_ID`
- `Customers.Region_ID` → `Regions.Region_ID`

## 💬 Example Business Questions

Users can ask questions such as:

1. Which region has the highest order value?
2. What are the top five products by order value?
3. Which product categories generate the highest order value?
4. How many customers belong to each customer segment?
5. What is the monthly order value trend?
6. Which payment methods are used most frequently?
7. Which products have the highest estimated profit?

The application generates SQL queries, displays the results, and offers interactive visualizations and AI-generated insights.

## ⚙️ How It Works

**User Question → Gemini AI → SQL Generation → SQL Validation → SQLite Database → Results → Charts & AI Insights**

1. The user enters a business question in natural language.
2. Google Gemini AI generates a SQL query using the database schema.
3. The application validates the generated SQL.
4. The query runs against the read-only SQLite database.
5. Pandas processes the returned data.
6. Plotly generates interactive charts.
7. Gemini AI can generate additional business insights.

## 💻 Installation and Local Setup

### 1. Clone the Repository

```bash
git clone https://github.com/NimishaRajan13/AI-Natural-Language-Data-Analyst.git
```

```bash
cd AI-Natural-Language-Data-Analyst
```

### 2. Install Dependencies

Python 3.12 is recommended.

```bash
pip install -r requirements.txt
```

### 3. Configure the Gemini API Key

Create a `.env` file in the project directory.

```env
GEMINI_API_KEY=your_gemini_api_key_here
```

Obtain an API key from [Google AI Studio](https://aistudio.google.com/).

**Security:** Never commit API keys or `.env` files to GitHub.

### 4. Run the Application

```bash
python -m streamlit run app.py
```

Open the local URL displayed in your terminal, usually:

`http://localhost:8501`

## 🔒 Security Considerations

The application incorporates several safeguards:

- Read-only SQLite database access.
- SQL query parsing and validation.
- Restrictions on database modification operations.
- Query execution timeout.
- Maximum returned-row limit.
- Session-based AI request limits.
- API key management using environment variables and Streamlit Secrets.

**Note:** Session limits are not equivalent to global rate limiting. Public deployments should also monitor API quotas and apply additional abuse-prevention controls.

## 📈 Business Value

This project demonstrates how generative AI can simplify data analysis by reducing the need to write SQL manually.

Potential applications include:

- E-commerce sales analysis
- Customer segmentation
- Product performance analysis
- Regional business reporting
- Order trend analysis
- Business intelligence demonstrations

The dataset is synthetic and intended for demonstration and learning purposes.

## 🔮 Future Enhancements

- Support for Excel and CSV uploads
- Multi-database connectivity
- Advanced AI-driven chart recommendations
- Conversational analytics with follow-up questions
- User authentication
- Centralized API rate limiting
- Power BI integration
- Automated analytical reports

## 👩‍💻 Project Development

**Project:** AI-Powered Natural Language Data Analyst

**GitHub:** [NimishaRajan13](https://github.com/NimishaRajan13)

**Repository:** [AI-Natural-Language-Data-Analyst](https://github.com/NimishaRajan13/AI-Natural-Language-Data-Analyst)

---

⭐ If you find this project useful, consider starring the repository.

*Built with Python, Google Gemini AI, SQLite, Streamlit, and Plotly.*

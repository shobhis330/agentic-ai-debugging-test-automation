# 🐞 DebugEngage AI
### Agentic AI-Powered Python Debugging & Test Automation System

**DebugEngage AI** is an AI-powered Python debugging and test automation system that helps developers identify programming errors, understand bugs, generate code corrections, and validate fixes through automated testing.

The system integrates Google's Gemini AI with Python testing and analysis tools to support an intelligent debugging workflow. It provides an interactive Streamlit interface for analyzing individual Python files and complete multi-file projects.

**Repository:** [agentic-ai-debugging-test-automation](https://github.com/shobhis330/agentic-ai-debugging-test-automation)

---

## 🚀 Key Features

### 1. Single Python Code Debugging
- Upload and analyze individual Python files.
- Identify syntax and logical errors.
- Generate AI-assisted code corrections.
- Validate corrected code through automated tests.

### 2. Complete ZIP Project Debugging
- Upload complete Python projects in ZIP format.
- Extract and analyze multiple project files.
- Identify issues across different modules.
- Apply and validate project-level corrections.

### 3. Code Quality Analysis
- Analyze Python source code.
- Identify potential bugs and code quality issues.
- Examine function complexity.
- Display a code quality score and analysis results.

### 4. AI Bug Explanation
- Explain detected programming errors.
- Identify possible causes of bugs.
- Describe the impact of errors.
- Suggest appropriate corrections and testing recommendations.

### 5. Test Coverage Report
- Execute automated test cases.
- Display passed, failed and skipped tests.
- Generate code coverage reports.
- Identify uncovered lines of code.

### 6. Debugging History
- Maintain records of debugging sessions.
- Track debugging and validation status.
- Search previous debugging records.
- Review earlier analysis results.

### 7. Original vs Corrected Comparison
- Compare original and corrected Python programs.
- Execute tests against both versions.
- Display passed and failed test counts.
- Measure improvement in test success rate.

---

## 🛠️ Technology Stack

| Category | Technology |
|---|---|
| Programming Language | Python |
| AI Model Integration | Google Gemini API |
| Frontend | Streamlit |
| Automated Testing | pytest |
| Code Coverage | coverage.py |
| Data Processing | Pandas |
| Data Visualization | Plotly |
| Environment Management | python-dotenv |
| Version Control | Git and GitHub |

---

## 🏗️ System Architecture

The system follows an AI-assisted debugging workflow:

```text
        User
         |
         v
   Streamlit Interface
         |
         v
   Code / ZIP Upload
         |
         v
   Code Analysis
         |
         v
   Gemini AI Integration
         |
         v
   Bug Detection & Explanation
         |
         v
   Suggested Code Corrections
         |
         v
   Automated Test Execution
         |
         v
   Test & Coverage Analysis
         |
         v
   Results and Validation
```

---

## 📂 Project Structure

```text
agentic-ai-debugging-test-automation/
│
├── archive/
│
├── core/
│   ├── bug_explainer.py
│   ├── code_quality.py
│   ├── debugging_history.py
│   ├── project_analyzer.py
│   ├── project_upload.py
│   ├── repair_engine.py
│   ├── test_comparison.py
│   ├── test_coverage.py
│   ├── test_runner.py
│   └── zip_extractor.py
│
├── data/
│   └── debugging_history.json
│
├── evaluation_cases/
│   ├── TC01/
│   ├── TC02/
│   ├── ...
│   └── TC15/
│
├── frontend/
│   ├── app.py
│   └── pages/
│       ├── AI_Bug_Explanation.py
│       ├── Code_Quality.py
│       ├── Debugging_History.py
│       ├── Original_vs_Corrected_Comparison.py
│       └── Test_Coverage_Report.py
│
├── multi_agent/
│
├── notebooks/
│
├── agent_cli.py
├── debugging_agent.py
├── check_syntax.py
├── bug_cases.json
├── requirements.txt
└── README.md
```

---

## ⚙️ Installation and Setup

### Prerequisites

- Python 3.10 or later
- Git
- Google Gemini API key
- Visual Studio Code (recommended)

### Step 1: Clone the repository

```bash
git clone https://github.com/shobhis330/agentic-ai-debugging-test-automation.git
```

### Step 2: Navigate to the project directory

```bash
cd agentic-ai-debugging-test-automation
```

### Step 3: Create a virtual environment

```bash
python -m venv venv
```

Activate the environment:

**Windows:**
```bash
venv\Scripts\activate
```

**Linux / macOS:**
```bash
source venv/bin/activate
```

### Step 4: Install dependencies

```bash
pip install -r requirements.txt
```

### Step 5: Configure the Gemini API key

Create a `.env` file in the project root directory.

Add your API key:

```env
GEMINI_API_KEY=your_gemini_api_key
```

Replace `your_gemini_api_key` with your actual Gemini API key.

**Security:** Never upload your `.env` file or expose your API key in GitHub.

### Step 6: Run the application

```bash
python -m streamlit run frontend/app.py
```

Open the local URL displayed in your terminal, usually:

```text
http://localhost:8501
```

---

## 🧪 Testing and Validation

DebugEngage AI uses automated testing to evaluate Python programs and validate suggested corrections.

The project includes 15 evaluation test-case folders (`TC01`–`TC15`) and supports testing individual Python files and multi-file projects.

### Sample Validation Results

The following results were observed during testing of a sample Python debugging case:

| Metric | Original Code | Corrected Code |
|---|---:|---:|
| Passed Tests | 1 | 5 |
| Failed Tests | 4 | 0 |
| Test Success Rate | 20% | 100% |

These results demonstrate the improvement achieved in that particular test scenario. Results may vary depending on the submitted program.

---

## 🔐 Security Considerations

- Store API keys using environment variables.
- Exclude `.env` files from version control.
- Review AI-generated code corrections before using them.
- Run uploaded code and tests in a controlled environment.
- Treat static-analysis findings as potential issues requiring review.

---

## 🔮 Future Enhancements

- Support for additional programming languages.
- Improved multi-agent collaboration.
- Advanced automated test-case generation.
- Enhanced debugging analytics and reports.
- Integration with development environments.
- More advanced code repair and validation capabilities.

---

## 👩‍💻 Project Information

| Detail | Description |
|---|---|
| Project Name | DebugEngage AI |
| Project Domain | Agentic AI and Software Test Automation |
| Primary Language | Python |
| AI Integration | Google Gemini |
| Frontend Framework | Streamlit |
| Testing Framework | pytest |
| Repository | GitHub |

---

## 📌 Conclusion

DebugEngage AI demonstrates how Agentic AI and automated software testing can work together to improve the Python debugging process.

By combining AI-assisted bug analysis, code correction, automated test execution, coverage reporting and debugging history, the system provides an integrated environment for understanding and validating software fixes.

**Built with Python, Google Gemini and Streamlit.**

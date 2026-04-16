from fpdf import FPDF


class PDF(FPDF):
    def header(self):
        self.set_font('Helvetica', 'B', 11)
        self.set_text_color(100, 50, 200)
        self.cell(0, 8, 'FUSION MIND - Project Documentation', 0, 1, 'C')
        self.set_draw_color(100, 50, 200)
        self.line(10, 15, 200, 15)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', 0, 0, 'C')

    def ch_title(self, title):
        self.set_font('Helvetica', 'B', 14)
        self.set_text_color(60, 30, 150)
        self.ln(4)
        self.cell(0, 10, title, 0, 1)
        self.set_draw_color(60, 30, 150)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(3)

    def sec_title(self, title):
        self.set_font('Helvetica', 'B', 11)
        self.set_text_color(80, 80, 80)
        self.ln(2)
        self.cell(0, 7, title, 0, 1)
        self.ln(1)

    def txt(self, text):
        self.set_font('Helvetica', '', 10)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 5.5, text)
        self.ln(1)

    def bul(self, text):
        self.set_font('Helvetica', '', 10)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 5.5, '  - ' + text)

    def code(self, text):
        self.set_font('Courier', '', 8)
        self.set_fill_color(240, 240, 245)
        self.set_text_color(60, 60, 60)
        # Wrap long lines
        lines = []
        for line in text.split('\n'):
            while len(line) > 85:
                lines.append(line[:85])
                line = '  ' + line[85:]
            lines.append(line)
        self.multi_cell(0, 4.5, '\n'.join(lines), 0, 'L', True)
        self.ln(2)


pdf = PDF()
pdf.alias_nb_pages()
pdf.set_auto_page_break(auto=True, margin=20)

# TITLE PAGE
pdf.add_page()
pdf.ln(30)
pdf.set_font('Helvetica', 'B', 28)
pdf.set_text_color(60, 30, 150)
pdf.cell(0, 15, 'FUSION MIND', 0, 1, 'C')
pdf.set_font('Helvetica', '', 14)
pdf.set_text_color(100, 100, 100)
pdf.cell(0, 10, 'Automatic Quiz Generation from PDF Documents', 0, 1, 'C')
pdf.ln(10)
pdf.set_font('Helvetica', '', 11)
pdf.cell(0, 7, 'A Rule-Based NLP Approach Without Pre-Trained Models', 0, 1, 'C')
pdf.ln(15)
pdf.set_font('Helvetica', '', 10)
pdf.set_text_color(120, 120, 120)
pdf.cell(0, 6, 'GitHub: https://github.com/Rallu25/Fusion-Mind', 0, 1, 'C')
pdf.cell(0, 6, 'Stack: Python, FastAPI, scikit-learn, PyMuPDF, SQLite', 0, 1, 'C')
pdf.cell(0, 6, 'Date: March 2026', 0, 1, 'C')

# 1. OVERVIEW
pdf.add_page()
pdf.ch_title('1. Project Overview')
pdf.txt('Fusion Mind is a web application that automatically generates multiple-choice quizzes from PDF documents. It uses rule-based Natural Language Processing (NLP) techniques - no pre-trained models, no LLMs, no spaCy, no NLTK, no transformers. Everything is built from scratch using regex patterns, TF-IDF ranking, and a self-expanding knowledge base.')
pdf.txt('The application supports three user roles:')
pdf.bul('Guest - uploads PDFs and generates quizzes for practice (no login required)')
pdf.bul('Teacher - creates quizzes, shares them via unique links with timer, views student results')
pdf.bul('Student - opens a shared link, takes the quiz once, score saved for the teacher')

# 2. QUIZ TYPES
pdf.ch_title('2. Quiz Types (6 Types)')

pdf.sec_title('2.1 Cloze (Fill-in-the-Blank)')
pdf.txt('Extracts the most important sentences using TF-IDF ranking, selects a key term, replaces it with a blank, and generates 3 plausible distractors from the knowledge base and document vocabulary.')
pdf.txt('Example: "_____ protects food from contamination." -> Packaging / Wrapping / Sealing / Containerization')

pdf.sec_title('2.2 Full Questions (Template-Based)')
pdf.txt('Uses 12 regex patterns to detect sentence structures and transforms them into complete questions. Patterns: Definition, Property, Function, Cause-Effect, Location, Composition, Value, Comparison, Action, Purpose, Reference, Enables.')
pdf.txt('Example: "What is an autoencoder?" -> "a neural network trained to reconstruct its input"')

pdf.sec_title('2.3 True/False')
pdf.txt('Takes factual sentences and either keeps them TRUE or modifies them to be FALSE using three strategies: Term Swap (replace key term with KB distractor), Negation (insert "not"), Number Swap (change numeric value). Maintains ~50/50 balance.')

pdf.sec_title('2.4 Visual (Image Answers)')
pdf.txt('Extracts images from PDFs using PyMuPDF, detects captions by spatial proximity, generates "Which image shows X?" questions with 4 images as options. Falls back to cloze if <4 images.')

pdf.sec_title('2.5 Matching (Drag & Drop)')
pdf.txt('Extracts term-definition pairs using definition patterns. Presents terms and scrambled definitions for matching. Falls back to template if <4 definitions found.')

pdf.sec_title('2.6 Mixed (All Types Combined)')
pdf.txt('Combines ~30% cloze + 30% template + 20% T/F + 20% matching, all shuffled randomly.')

# 3. ARCHITECTURE
pdf.add_page()
pdf.ch_title('3. System Architecture')

pdf.sec_title('3.1 Processing Pipeline')
pdf.code('PDF -> pypdf/PyMuPDF -> Raw Text + Images\n  -> preprocess.py (cleanup, sentence segmentation)\n  -> tfidf_rank.py (rank by importance)\n  -> [Quiz Generator] (cloze/template/truefalse/matching/image)\n  -> distractors.py (generate wrong answers)\n  -> kb_expand.py (auto-expand knowledge base)\n  -> main.py (FastAPI) -> frontend (HTML/JS)')

pdf.sec_title('3.2 File Structure')
pdf.code('Fusion-Mind/\n  main.py                - FastAPI backend (20+ endpoints)\n  database.py            - SQLite (teachers, quizzes, submissions)\n  auth.py                - Token-based authentication\n  fusion_mind.html       - Guest mode frontend\n  teacher_dashboard.html - Teacher panel\n  student_quiz.html      - Student quiz page\n  quizgen/\n    __init__.py          - Cloze generator + difficulty filter\n    pdf_text.py          - PDF text extraction\n    preprocess.py        - Text normalization\n    tfidf_rank.py        - TF-IDF sentence ranking\n    cloze.py             - Target word selection\n    distractors.py       - Distractor generation + grammar filter\n    template_patterns.py - 12 regex question patterns\n    template_quiz.py     - Full question generator\n    truefalse_quiz.py    - True/False generator\n    matching_quiz.py     - Matching generator\n    image_extract.py     - Image extraction (PyMuPDF)\n    image_quiz.py        - Visual quiz generator\n    kb_expand.py         - Auto-expanding knowledge base\n  data/knowledge_base.json - 392+ terms\n  tests/                   - 109 unit tests')

pdf.sec_title('3.3 Technology Stack')
pdf.bul('Backend: Python 3.12, FastAPI, uvicorn')
pdf.bul('NLP: scikit-learn (TF-IDF only), regex, rule-based patterns')
pdf.bul('PDF: pypdf (text), PyMuPDF/fitz (images)')
pdf.bul('Database: SQLite (built-in)')
pdf.bul('Auth: PBKDF2 hashing, HMAC-signed tokens')
pdf.bul('Email: SMTP (Yahoo/Gmail/any)')
pdf.bul('Frontend: Vanilla HTML/CSS/JS (no frameworks)')
pdf.bul('Testing: pytest (109 tests)')

# 4. KNOWLEDGE BASE
pdf.add_page()
pdf.ch_title('4. Knowledge Base')
pdf.txt('Maps technical terms to plausible distractors. Started with 82 terms, grew to 291 manually, then to 392+ with auto-expansion.')

pdf.sec_title('4.1 Domains Covered (9)')
pdf.txt('Biology, Physics, Chemistry, Machine Learning, Computer Science, Statistics, Mathematics, Economics, Geography.')

pdf.sec_title('4.2 Auto-Expansion')
pdf.txt('Every quiz generation scans the PDF for related terms:')
pdf.bul('Coordination: "X, Y, and Z" -> mutual distractors')
pdf.bul('"Such as/including" patterns -> children as distractors')
pdf.bul('"X or Y" -> mutual distractors')
pdf.bul('"Is found in" -> subjects in same domain grouped')
pdf.txt('Duplicates are detected and skipped. KB grows permanently with each new PDF.')

# 5. DISTRACTOR QUALITY
pdf.ch_title('5. Distractor Quality System')
pdf.sec_title('5.1 Source Priority')
pdf.bul('1st: Knowledge base (same domain, curated)')
pdf.bul('2nd: Document vocabulary (same PDF)')
pdf.bul('3rd: Noun-phrase fallback')

pdf.sec_title('5.2 Ambiguity Filter')
pdf.bul('Stem check: rejects same-root words ("supervised"/"supervision")')
pdf.bul('Context check: rejects words appearing in similar context in document')

pdf.sec_title('5.3 Grammatical Validation')
pdf.bul('Article agreement (a/an)')
pdf.bul('Number agreement (singular/plural)')
pdf.bul('Word type consistency (noun/verb/adjective/adverb)')
pdf.bul('Common verb filter (no verbs after "the/a/an")')

# 6. TEACHER/STUDENT
pdf.add_page()
pdf.ch_title('6. Teacher/Student System')

pdf.sec_title('6.1 Teacher Flow')
pdf.txt('Register (email, password, name, institution) -> Login -> Upload PDF -> Configure quiz (type, difficulty, timer, show answers) -> Generate & Share -> Get unique link -> View student results -> Export CSV')

pdf.sec_title('6.2 Student Flow')
pdf.txt('Open link -> Enter name -> Start quiz -> Timer counts down -> Answer questions (changeable) -> Submit (auto on timer expiry) -> See score -> Session persists through refresh')

pdf.sec_title('6.3 Security')
pdf.bul('PBKDF2 password hashing (100,000 iterations)')
pdf.bul('HMAC-signed tokens (24h expiry)')
pdf.bul('Triple duplicate prevention: localStorage + name check + IP check')
pdf.bul('SMTP credentials in .env (gitignored)')

# 7. FRONTEND
pdf.ch_title('7. Frontend Features')
pdf.bul('Dark/Light theme toggle')
pdf.bul('Keyboard shortcuts (A/B/C/D, arrows, T/F, Enter)')
pdf.bul('Question stepper (clickable dots)')
pdf.bul('Animated score ring + confetti on 100%')
pdf.bul('Quiz history + save/load JSON')
pdf.bul('Dashboard: score timeline, averages by type and difficulty')
pdf.bul('Shuffle, retry wrong, review all')
pdf.bul('Email results (HTML formatted)')

# 8. DIFFICULTY
pdf.ch_title('8. Difficulty System')
pdf.bul('Easy: highest quality scores, clearest questions')
pdf.bul('Medium: middle range')
pdf.bul('Hard: lower quality threshold, shorter context')
pdf.txt('True/False: Easy=60% true, Hard=30% true (more subtle false questions).')

# 9. TESTING
pdf.add_page()
pdf.ch_title('9. Testing (109 Unit Tests)')
pdf.bul('test_preprocess.py (9): normalization, splitting, filtering')
pdf.bul('test_distractors.py (42): vocab, stems, KB, grammar filter')
pdf.bul('test_cloze.py (9): target selection, cloze generation')
pdf.bul('test_tfidf_rank.py (5): ranking, ordering')
pdf.bul('test_template_patterns.py (17): all patterns, validation')
pdf.bul('test_truefalse.py (14): swap, negation, scoring')
pdf.bul('test_matching.py (4): pair extraction')
pdf.bul('test_image_extract.py (4): encoding, captions')
pdf.bul('test_quiz_generation.py (5): difficulty filtering')
pdf.code('Run: py -m pytest tests/ -v')

# 10. SETUP
pdf.ch_title('10. Installation')
pdf.code('git clone https://github.com/Rallu25/Fusion-Mind.git\ncd Fusion-Mind\npip install -r requirements.txt\n\n# Optional: create .env for email\n# SMTP_HOST=smtp.mail.yahoo.com\n# SMTP_USER=your@email.com\n# SMTP_PASS=your-app-password\n\npython -m uvicorn main:app --reload\n\n# Guest:   http://127.0.0.1:8000\n# Teacher: http://127.0.0.1:8000/teacher\n# Student: http://127.0.0.1:8000/student/<id>')

# 11. API
pdf.ch_title('11. API Endpoints (20+)')
pdf.code('POST /generate-quiz          - Single PDF\nPOST /generate-quiz-multi    - Multiple PDFs\nPOST /auth/register          - Create teacher\nPOST /auth/login             - Login\nGET  /auth/me                - Verify token\nPOST /teacher/create-quiz    - Generate + share\nGET  /teacher/my-quizzes     - List quizzes\nGET  /teacher/quiz/{id}/results - Submissions\nDELETE /teacher/quiz/{id}    - Delete quiz\nGET  /quiz/{id}              - Get quiz (student)\nPOST /quiz/{id}/submit       - Submit answers\nPOST /send-results-email     - Email results\nGET  /teacher                - Dashboard HTML\nGET  /student/{id}           - Quiz HTML')

# 12. UNIQUE
pdf.ch_title('12. What Makes This Project Unique')
pdf.bul('No pre-trained models: pure rule-based NLP')
pdf.bul('Self-improving: KB grows with every PDF')
pdf.bul('6 quiz types from a single PDF')
pdf.bul('3-level distractor quality system')
pdf.bul('Complete educational platform (teacher/student)')
pdf.bul('Graceful fallbacks (visual->cloze, matching->template)')
pdf.bul('109 unit tests')
pdf.bul('Zero external AI dependencies: works fully offline')

output = 'C:/Users/Raluca/Downloads/Fusion_Mind_Documentation.pdf'
pdf.output(output)
print(f'PDF saved: {output}')
print(f'Pages: {pdf.page_no()}')

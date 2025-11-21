# MedicalBot
A FastAPI-based local application that records audio from the OS microphone, streams it to OpenAI for transcription, and generates formatted medical visit reports for clinicians.

Brief helper to evaluate transcription and generate structured medical reports locally.

SETUP
-----
- Create and activate a virtual environment:

```bash
python -m venv ./venv
source ./venv/bin/activate
```

- Install dependencies:

```bash
pip install -r requirements.txt
```

- Copy `.env.example` to `.env` and set your OpenAI API key (if you plan to use the real API):

```bash
cp .env.example .env
# edit .env and set OPENAI_API_KEY
```

- Run tests (includes end-to-end coverage with mocked OpenAI):

```bash
./venv/bin/python -m pytest tests/ -v
```

- Run the app locally:

```bash
./venv/bin/python main.py
```

Quick checks
------------
- Example E2E script that runs transcription on the included `tests/AtTheDoctors.mp3` and prints the transcript/report is available in `tests/test_e2e_mp3_to_report.py`.

@echo off
REM Quick Study Guide Generator
REM Usage: generate_study_guide.bat "Topic Name"

if "%~1"=="" (
    echo Usage: generate_study_guide.bat "Topic Name"
    echo Example: generate_study_guide.bat "World War II"
    exit /b 1
)

cd /d "%~dp0scripts"
python -c "from wiki_study_guide_generator import WikiStudyGuideGenerator; generator = WikiStudyGuideGenerator(); generator.generate_study_guide('%~1', r'C:\Users\CodyW\OneDrive\Documents\StudyFlow')"

pause

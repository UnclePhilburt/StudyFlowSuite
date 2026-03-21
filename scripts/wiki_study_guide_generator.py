"""
Wikipedia Study Guide Generator
---------------------------------
Automatically creates comprehensive study guides from Wikipedia articles
"""

import wikipediaapi
import re
from typing import Dict, List
import os


class WikiStudyGuideGenerator:
    def __init__(self):
        self.wiki = wikipediaapi.Wikipedia(
            user_agent='StudyFlowBot/1.0 (Educational; contact@studyflowsuite.com)',
            language='en'
        )

    def clean_text(self, text: str) -> str:
        """Clean up Wikipedia text formatting"""
        # Remove multiple newlines
        text = re.sub(r'\n\n+', '\n\n', text)
        # Remove citation markers [1], [2], etc.
        text = re.sub(r'\[\d+\]', '', text)
        # Clean up whitespace
        text = re.sub(r'[ \t]+', ' ', text)
        return text.strip()

    def extract_sections(self, page) -> Dict[str, str]:
        """Extract all sections from Wikipedia page"""
        sections = {}

        def process_section(section, level=0):
            # Add section title and text
            if section.title:
                title = section.title
                text = self.clean_text(section.text)

                # Skip empty sections
                if text and len(text) > 50:
                    sections[title] = {
                        'text': text,
                        'level': level
                    }

            # Process subsections
            for subsection in section.sections:
                process_section(subsection, level + 1)

        # Start with the main page
        process_section(page)

        return sections

    def format_study_guide(self, title: str, sections: Dict) -> str:
        """Format sections into a comprehensive study guide"""

        guide = []
        guide.append("=" * 80)
        guide.append(f"{'STUDY GUIDE: ' + title.upper():^80}")
        guide.append("=" * 80)
        guide.append("")
        guide.append(f"Generated from Wikipedia article: {title}")
        guide.append("")

        # Create table of contents
        guide.append("TABLE OF CONTENTS")
        guide.append("-" * 80)

        toc_entries = []
        for idx, (section_title, section_data) in enumerate(sections.items(), 1):
            indent = "  " * section_data['level']
            toc_entries.append(f"{indent}{idx}. {section_title}")

        guide.extend(toc_entries)
        guide.append("")

        # Add all sections
        for idx, (section_title, section_data) in enumerate(sections.items(), 1):
            guide.append("")
            guide.append("=" * 80)
            guide.append(f"{idx}. {section_title.upper()}")
            guide.append("=" * 80)
            guide.append("")

            # Wrap text to 80 characters
            text = section_data['text']
            paragraphs = text.split('\n')

            for para in paragraphs:
                if not para.strip():
                    continue

                # Word wrap
                words = para.split()
                line = ""
                for word in words:
                    if len(line + word) + 1 <= 78:
                        line += (word + " ")
                    else:
                        guide.append(line.strip())
                        line = word + " "
                if line:
                    guide.append(line.strip())
                guide.append("")

        # Add footer
        guide.append("")
        guide.append("=" * 80)
        guide.append("END OF STUDY GUIDE")
        guide.append("=" * 80)
        guide.append("")
        guide.append("This study guide was automatically generated from Wikipedia content.")
        guide.append("Wikipedia content is licensed under CC BY-SA.")
        guide.append(f"Original article: https://en.wikipedia.org/wiki/{title.replace(' ', '_')}")

        return "\n".join(guide)

    def generate_study_guide(self, topic: str, output_dir: str = None) -> str:
        """
        Generate a study guide for a Wikipedia topic

        Args:
            topic: Wikipedia article title
            output_dir: Directory to save file (default: current directory)

        Returns:
            Path to generated file
        """
        print(f"[*] Generating study guide for: {topic}")

        # Fetch Wikipedia page
        page = self.wiki.page(topic)

        if not page.exists():
            raise ValueError(f"Wikipedia article '{topic}' not found")

        print(f"[+] Found article: {page.title}")
        print(f"[*] Length: {len(page.text)} characters")

        # Extract sections
        sections = self.extract_sections(page)
        print(f"[*] Extracted {len(sections)} sections")

        # Format as study guide
        guide_content = self.format_study_guide(page.title, sections)

        # Save to file
        if output_dir is None:
            output_dir = os.getcwd()

        # Create safe filename
        safe_filename = re.sub(r'[^\w\s-]', '', topic).strip().replace(' ', '_')
        filename = f"{safe_filename}_Study_Guide.txt"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(guide_content)

        print(f"[+] Study guide saved to: {filepath}")
        print(f"[*] File size: {len(guide_content)} characters")

        return filepath

    def generate_multiple(self, topics: List[str], output_dir: str = None) -> List[str]:
        """Generate study guides for multiple topics"""
        filepaths = []

        for i, topic in enumerate(topics, 1):
            print(f"\n[{i}/{len(topics)}] Processing: {topic}")
            try:
                filepath = self.generate_study_guide(topic, output_dir)
                filepaths.append(filepath)
            except Exception as e:
                print(f"[-] Error: {e}")
                continue

        return filepaths


def main():
    """Interactive CLI"""
    print("=" * 80)
    print("Wikipedia Study Guide Generator".center(80))
    print("=" * 80)
    print()

    generator = WikiStudyGuideGenerator()

    while True:
        print("\nOptions:")
        print("1. Generate study guide for a topic")
        print("2. Generate from list (comma-separated)")
        print("3. Generate from file (one topic per line)")
        print("4. Exit")

        choice = input("\nSelect option (1-4): ").strip()

        if choice == "1":
            topic = input("\nEnter Wikipedia topic: ").strip()
            if not topic:
                print("[-] Topic cannot be empty")
                continue

            output_dir = input("Output directory (press Enter for current): ").strip()
            if not output_dir:
                output_dir = None

            try:
                filepath = generator.generate_study_guide(topic, output_dir)
                print(f"\n[+] Success! Study guide created at:\n   {filepath}")
            except Exception as e:
                print(f"\n[-] Error: {e}")

        elif choice == "2":
            topics_input = input("\nEnter topics (comma-separated): ").strip()
            if not topics_input:
                print("[-] Topics cannot be empty")
                continue

            topics = [t.strip() for t in topics_input.split(',') if t.strip()]
            output_dir = input("Output directory (press Enter for current): ").strip()
            if not output_dir:
                output_dir = None

            print(f"\n[*] Generating {len(topics)} study guides...")
            filepaths = generator.generate_multiple(topics, output_dir)
            print(f"\n[+] Generated {len(filepaths)}/{len(topics)} study guides")

        elif choice == "3":
            filepath = input("\nEnter path to topics file: ").strip()

            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    topics = [line.strip() for line in f if line.strip()]

                if not topics:
                    print("[-] File is empty")
                    continue

                output_dir = input("Output directory (press Enter for current): ").strip()
                if not output_dir:
                    output_dir = None

                print(f"\n[*] Found {len(topics)} topics. Generating study guides...")
                filepaths = generator.generate_multiple(topics, output_dir)
                print(f"\n[+] Generated {len(filepaths)}/{len(topics)} study guides")

            except FileNotFoundError:
                print(f"[-] File not found: {filepath}")
            except Exception as e:
                print(f"[-] Error: {e}")

        elif choice == "4":
            print("\nGoodbye!")
            break

        else:
            print("[-] Invalid option")


if __name__ == "__main__":
    # Example usage
    generator = WikiStudyGuideGenerator()

    # Single topic
    generator.generate_study_guide(
        "Photosynthesis",
        output_dir=r"C:\Users\CodyW\OneDrive\Documents\StudyFlow"
    )

    # Or run interactive mode
    # main()

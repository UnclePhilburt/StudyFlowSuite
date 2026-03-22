"""
Import 220 Most Academic Wikipedia Articles
-------------------------------------------
Curated list of the most important academic articles across major subjects.
"""

import os
import sys

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wikipedia_bulk_importer import WikipediaBulkImporter

# 220 Curated Academic Wikipedia Articles
ACADEMIC_ARTICLES = {
    'Mathematics (30)': [
        'Calculus', 'Algebra', 'Geometry', 'Trigonometry', 'Statistics',
        'Probability theory', 'Linear algebra', 'Differential equations', 'Number theory',
        'Set theory', 'Graph theory', 'Topology', 'Complex analysis', 'Real analysis',
        'Abstract algebra', 'Mathematical proof', 'Prime number', 'Euclidean geometry',
        'Pythagorean theorem', 'Fibonacci sequence', 'Fundamental theorem of calculus',
        'Binomial theorem', 'Taylor series', 'Fourier transform', 'Matrix (mathematics)',
        'Vector space', 'Group theory', 'Ring theory', 'Field theory', 'Combinatorics'
    ],

    'Physics (30)': [
        'Physics', 'Classical mechanics', 'Quantum mechanics', 'Thermodynamics',
        'Electromagnetism', 'Relativity', 'Special relativity', 'General relativity',
        'Newton\'s laws of motion', 'Gravity', 'Light', 'Wave', 'Energy', 'Force',
        'Momentum', 'Entropy', 'Quantum field theory', 'String theory', 'Particle physics',
        'Atomic physics', 'Nuclear physics', 'Optics', 'Acoustics', 'Fluid dynamics',
        'Maxwell\'s equations', 'Schrödinger equation', 'E=mc²', 'Planck constant',
        'Speed of light', 'Conservation of energy'
    ],

    'Chemistry (25)': [
        'Chemistry', 'Organic chemistry', 'Inorganic chemistry', 'Physical chemistry',
        'Biochemistry', 'Chemical bond', 'Periodic table', 'Atom', 'Molecule', 'Ion',
        'Chemical reaction', 'Acid', 'Base (chemistry)', 'pH', 'Oxidation',
        'Reduction (chemistry)', 'Chemical equilibrium', 'Thermochemistry', 'Electrochemistry',
        'Stoichiometry', 'Atomic orbital', 'Covalent bond', 'Ionic bond', 'Hydrogen bond',
        'Catalysis'
    ],

    'Biology (30)': [
        'Biology', 'Cell (biology)', 'DNA', 'RNA', 'Protein', 'Evolution',
        'Natural selection', 'Genetics', 'Mitosis', 'Meiosis', 'Photosynthesis',
        'Cellular respiration', 'Enzyme', 'Metabolism', 'Homeostasis', 'Ecology',
        'Ecosystem', 'Gene', 'Chromosome', 'Biodiversity', 'Species', 'Taxonomy',
        'Prokaryote', 'Eukaryote', 'Virus', 'Bacteria', 'Neuron', 'Immune system',
        'Mendelian inheritance', 'Cell membrane'
    ],

    'History (25)': [
        'World War I', 'World War II', 'American Civil War', 'French Revolution',
        'Industrial Revolution', 'Renaissance', 'Enlightenment', 'Cold War',
        'Roman Empire', 'Ancient Greece', 'Ancient Egypt', 'Middle Ages',
        'Age of Discovery', 'American Revolution', 'Russian Revolution',
        'Protestant Reformation', 'Byzantine Empire', 'Ottoman Empire',
        'Holy Roman Empire', 'Great Depression', 'Holocaust', 'Magna Carta',
        'Declaration of Independence', 'United States Constitution', 'Colonialism'
    ],

    'Computer Science (20)': [
        'Computer science', 'Algorithm', 'Data structure', 'Programming language',
        'Artificial intelligence', 'Machine learning', 'Computer network',
        'Database', 'Operating system', 'Compiler', 'Recursion', 'Sorting algorithm',
        'Binary search', 'Graph (data structure)', 'Tree (data structure)',
        'Hash table', 'Linked list', 'Big O notation', 'Turing machine', 'Computational complexity'
    ],

    'Philosophy (15)': [
        'Philosophy', 'Logic', 'Ethics', 'Metaphysics', 'Epistemology',
        'Socrates', 'Plato', 'Aristotle', 'Immanuel Kant', 'René Descartes',
        'Utilitarianism', 'Categorical imperative', 'Social contract', 'Empiricism', 'Rationalism'
    ],

    'Economics (15)': [
        'Economics', 'Supply and demand', 'Macroeconomics', 'Microeconomics',
        'Inflation', 'Gross domestic product', 'Monetary policy', 'Fiscal policy',
        'Market economy', 'Capitalism', 'Socialism', 'Opportunity cost',
        'Comparative advantage', 'Game theory', 'Adam Smith'
    ],

    'Literature (15)': [
        'William Shakespeare', 'Hamlet', 'Romeo and Juliet', 'Macbeth',
        'Poetry', 'Novel', 'Epic poetry', 'Sonnet', 'Metaphor', 'Irony',
        'Homer', 'Iliad', 'Odyssey', 'Jane Austen', 'Charles Dickens'
    ],

    'Psychology (15)': [
        'Psychology', 'Cognitive psychology', 'Behavioral psychology',
        'Sigmund Freud', 'Classical conditioning', 'Operant conditioning',
        'Neuroscience', 'Memory', 'Perception', 'Consciousness', 'Motivation',
        'Emotion', 'Intelligence', 'Personality', 'Social psychology'
    ]
}


def main():
    print("="*70)
    print("Importing 220 Most Academic Wikipedia Articles")
    print("="*70)
    print()

    # Flatten the article list
    all_articles = []
    for subject, articles in ACADEMIC_ARTICLES.items():
        print(f"{subject}: {len(articles)} articles")
        all_articles.extend(articles)

    total = len(all_articles)
    print(f"\nTotal articles to import: {total}")
    print(f"Estimated time: ~{total} minutes (~{total//60} hours)")
    print("\nStarting import...")
    print()

    # Initialize importer
    importer = WikipediaBulkImporter(progress_file='academic_220_progress.json')

    # Import all articles
    importer.import_articles(
        articles=all_articles,
        university="Wikipedia",
        course_code="Academic Encyclopedia",
        delay=1.0  # 1 second between articles for rate limiting
    )

    print("\n" + "="*70)
    print("Import complete!")
    print("="*70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Progress saved. Run again to resume!")
    except Exception as e:
        print(f"\n[-] Error: {e}")
        import traceback
        traceback.print_exc()

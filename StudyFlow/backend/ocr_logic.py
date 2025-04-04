import difflib
from StudyFlow.logging_utils import debug_log

def fallback_structure(mapping, expected_answers):
    lines = {}
    for tag, info in mapping.items():
        line = info.get('line_num', 0)
        lines.setdefault(line, []).append((tag, info['text']))

    sorted_line_nums = sorted(lines.keys())
    sorted_lines = [lines[line_num] for line_num in sorted_line_nums]

    line_texts = []
    line_tags = []

    for line in sorted_lines:
        line.sort(key=lambda x: x[0])
        first_tag = line[0][0]
        text = " ".join(word for tag, word in line)
        line_texts.append(text)
        line_tags.append(first_tag)

    total_lines = len(line_texts)

    if total_lines <= expected_answers:
        question = " ".join(line_texts)
        answers = {}
    else:
        question = " ".join(line_texts[:-expected_answers])
        answers = {}
        for i in range(expected_answers):
            answers[str(i + 1)] = {
                "text": line_texts[-expected_answers + i],
                "tag": line_tags[-expected_answers + i]
            }

    return {"question": question, "answers": answers}


def assign_tags_from_ocr(ai_answers, ocr_mapping):
    for key, answer in ai_answers.items():
        if answer.get("tag") is None:
            ocr_texts = {tag: data['text'] for tag, data in ocr_mapping.items()}
            best_match = difflib.get_close_matches(answer["text"], list(ocr_texts.values()), n=1)
            if best_match:
                for tag, text in ocr_texts.items():
                    if text == best_match[0]:
                        answer["tag"] = tag
                        debug_log(f"Assigned tag {tag} to answer '{answer['text']}' using text similarity.")
                        break
    return ai_answers


def merge_ai_and_fallback(ai_json, fallback_json, ocr_mapping):
    merged = {}
    merged["question"] = ai_json.get("question", fallback_json.get("question", ""))
    ai_answers = ai_json.get("answers", {})
    fallback_answers = fallback_json.get("answers", {})

    merged_answers = {}
    for key, answer in ai_answers.items():
        if answer.get("tag") is None and key in fallback_answers:
            merged_answers[key] = {
                "text": answer.get("text", fallback_answers[key].get("text")),
                "tag": fallback_answers[key].get("tag")
            }
        else:
            merged_answers[key] = answer

    if any(a.get("tag") is None for a in merged_answers.values()):
        debug_log("Missing tags detected after merge. Attempting reassignment.")
        merged_answers = assign_tags_from_ocr(merged_answers, ocr_mapping)

    merged["answers"] = merged_answers
    return merged
